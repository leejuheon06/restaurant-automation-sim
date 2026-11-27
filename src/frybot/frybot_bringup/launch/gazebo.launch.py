"""FryBot in Gazebo (gz sim): store world + 3 Pinky Pro, each with its own Nav2 stack (costmaps from the map and lidar).

  ros2 launch frybot_bringup gazebo.launch.py                 # Nav2 driving (default)
  ros2 launch frybot_bringup gazebo.launch.py drive:=cmd_vel  # old straight-line driving without costmaps
  ros2 launch frybot_bringup gazebo.launch.py gui:=false      # headless server

The Task Manager still decides routes and the order at shared nodes; every granted segment is a Nav2 goal.
Arms, guests and food stay simulated by the lightweight nodes.
"""
import os
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription, OpaqueFunction,
                            SetEnvironmentVariable, TimerAction)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration as LC
from launch_ros.actions import Node

from frybot_bringup.sim_net import apply_sim_network
from frybot_bringup.urdf_tools import pinky_gz_urdf
from frybot_control.layout import Graph, robot_ids
from frybot_mobile.navigator import navigator_nodes
from frybot_sim.gz_world_gen import world_sdf



def urdf_to_model(urdf_path, name, x, y):
    """Convert the robot URDF to an SDF <model> named `name` at (x, y) for embedding in the world file."""
    out = subprocess.check_output(['gz', 'sdf', '-p', urdf_path]).decode()
    root = ET.fromstring(out)
    model = root.find('model')
    model.set('name', name)
    pose = model.find('pose')
    if pose is None:
        pose = ET.Element('pose')
        model.insert(0, pose)
    pose.text = f'{x} {y} 0.03 0 0 0'
    return '\n' + ET.tostring(model, encoding='unicode')


def setup(context):
    """Gazebo 월드·로봇 모델·브리지·로봇별 Nav2 와 경량 시뮬 런치를 만든다.

    Args:
        context: 런치 컨텍스트.

    Returns:
        런치 액션 목록(맨 앞이 gz sim 실행).
    """
    share = get_package_share_directory('frybot_bringup')
    tmp = tempfile.mkdtemp(prefix='frybot_gz_')  # 월드·URDF 임시 폴더
    # [수정 2026-11-17] A2: 통신 범위 설정을 sim_net 으로 옮김(sim.launch.py 와 공용)
    apply_sim_network(LC('net').perform(context),
                      LC('sim_domain').perform(context))
    world = os.path.join(tmp, 'frybot_store.sdf')
    # Humble -> Fortress (ign, ignition.msgs); Jazzy -> Harmonic (gz sim, gz.msgs)
    fortress = os.environ.get('ROS_DISTRO') == 'humble' and shutil.which('ign') is not None
    gm = 'ignition.msgs' if fortress else 'gz.msgs'  # 브리지 메시지 접두사
    gz = ['ign', 'gazebo'] if fortress else ['gz', 'sim']
    gui = LC('gui').perform(context) == 'true'
    drive = LC('drive').perform(context)
    nav2 = drive == 'nav2'  # False 면 cmd_vel 직선 주행
    ROBOTS = robot_ids(LC('robots').perform(context))     # robots:=N -> pinky1..pinkyN
    robot_models = []
    # 공용 브리지: /clock, (Fortress) 모든 모델 자세, (Nav2) Gazebo 의 /tf
    acts = [Node(package='ros_gz_bridge', executable='parameter_bridge', name='clock_tf_bridge', output='screen',
                 arguments=[f'/clock@rosgraph_msgs/msg/Clock[{gm}.Clock'] +
                           ([f'/world/frybot_store/dynamic_pose/info@tf2_msgs/msg/TFMessage[{gm}.Pose_V'] if fortress else []) +
                           ([f'/tf@tf2_msgs/msg/TFMessage[{gm}.Pose_V'] if nav2 else []),
                 remappings=[('/world/frybot_store/dynamic_pose/info', '/gz/model_poses')])]
    g = Graph()  # FRYBOT_MAP_ID 지도, 없으면 proto
    # 로봇마다: URDF 를 만들어 홈 노드에 놓고, cmd_vel·odom·scan
    # (Harmonic 은 자기 자세도) 브리지
    for i, rid in enumerate(ROBOTS):
        path = os.path.join(tmp, rid + '.urdf')
        open(path, 'w').write(pinky_gz_urdf(rid, fortress))
        x, y = g.nodes[g.home_of(rid)]  # 출발 노드 좌표
        if fortress:
            acts.append(Node(package='ros_gz_sim', executable='create', output='screen',
                             arguments=['-world', 'frybot_store', '-name', rid, '-file', path,
                                        '-x', str(x), '-y', str(y), '-z', '0.03']))
        else:
            robot_models.append(urdf_to_model(path, rid, x, y))
        acts += [
            Node(package='ros_gz_bridge', executable='parameter_bridge', name=rid + '_bridge', output='screen',
                 arguments=[f'/{rid}/cmd_vel@geometry_msgs/msg/Twist]{gm}.Twist',
                            f'/{rid}/odom@nav_msgs/msg/Odometry[{gm}.Odometry',
                            f'/{rid}/scan@sensor_msgs/msg/LaserScan[{gm}.LaserScan'] +
                           ([] if fortress else [f'/model/{rid}/pose@tf2_msgs/msg/TFMessage[{gm}.Pose_V']),
                 remappings=[] if fortress else [(f'/model/{rid}/pose', '/gz/model_poses')]),
        ]
        if not nav2:  # 직선 주행이면 카메라·Nav2 없음
            continue
        # Front camera for ArUco docking. lazy: Gazebo renders the camera only while the dock detector listens.
        acts.append(Node(package='ros_gz_bridge', executable='parameter_bridge', name=rid + '_camera_bridge',
                         output='screen', parameters=[{'lazy': True}],
                         arguments=[f'/{rid}/camera/image_raw@sensor_msgs/msg/Image[{gm}.Image']))
        # FrybotNavigator of this robot (frybot_mobile: config/nav2_store.yaml). Localisation (map -> odom) comes from
        # the FrybotMobile Controller, which reads the simulator's true pose.
        # Start the Nav2 stacks a few seconds apart: brought up together, lifecycle transitions time out.
        # [수정 2026-11-18] P1: navigator_nodes 의 real 이 필수 인자가 됨
        acts.append(TimerAction(period=15.0 + 7.0 * i,
                                actions=navigator_nodes(rid, real=False)))
    if nav2:      # a lost lifecycle response at start-up leaves a robot without Nav2: check and restart it
        acts.append(Node(package='frybot_sim', executable='nav2_watchdog', output='screen',
                         parameters=[{'robot_ids': ROBOTS}]))
    # Harmonic: the robots are part of the world file. Spawned later through the create service, the GUI
    # (software rendering, sim well below real time) sometimes misses them and draws only one Pinky.
    sdf = world_sdf(fortress).replace('</world>', ''.join(robot_models) + '\n</world>')
    open(world, 'w').write(sdf)
    # gz sim 을 맨 앞에: -r 바로 재생, gui:=false 면 -s(서버만)
    acts.insert(0, ExecuteProcess(cmd=gz + ['-r'] + ([] if gui else ['-s']) + [world], output='screen'))
    # 관제·매장·AMR 노드는 sim.launch.py 를 그대로 씀(drive, sim_time 등 전달)
    acts.append(IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(share, 'launch', 'sim.launch.py')),
        launch_arguments={'drive': drive, 'rviz': LC('rviz'), 'scheduler': LC('scheduler'), 'planner': LC('planner'),
                          'sim_time': 'true' if nav2 else 'false', 'standby': LC('standby'),
                          'robots': LC('robots'), 'net': LC('net'),
                          'sim_domain': LC('sim_domain'),
                          # [수정 2026-11-18] W6: 계획 구간 지연 전달
                          'plan_overhead': LC('plan_overhead')}.items()))
    return acts


def generate_launch_description():
    """Gazebo 런치의 인자를 선언하고 setup 을 붙인다.

    Returns:
        LaunchDescription.
    """
    # [수정 2026-11-17] 메시를 frybot_description 에서 찾음 (pinky_pro 의존 제거)
    res = os.path.dirname(get_package_share_directory('frybot_description'))
    args = [('gui', 'true'), ('rviz', 'true'), ('drive', 'nav2'), ('scheduler', 'min_cost_eta_rh'), ('planner', 'sipp'),
            # [수정 2026-11-17] A2: net 기본값 lan -> sim (시뮬 전용 도메인.
            # 실기기와 같은 도메인에 시뮬의 /pinky1..3 이 보이지 않게 함)
            ('standby', 'true'), ('robots', '3'), ('net', 'sim'),
            ('sim_domain', '74'),
            # [수정 2026-11-18] W6: 계획의 구간 지연(초).
            # 기본 0.0(보정 전과 같음)
            ('plan_overhead', '0.0')]
    return LaunchDescription([DeclareLaunchArgument(k, default_value=v) for k, v in args] + [
        # Gazebo 메시 검색 경로 앞에 frybot_description 설치 폴더의 상위를 붙임
        SetEnvironmentVariable('IGN_GAZEBO_RESOURCE_PATH', res + ':' + os.environ.get('IGN_GAZEBO_RESOURCE_PATH', '')),
        SetEnvironmentVariable('GZ_SIM_RESOURCE_PATH', res + ':' + os.environ.get('GZ_SIM_RESOURCE_PATH', '')),
        OpaqueFunction(function=setup)])
