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

from frybot_bringup.urdf_tools import pinky_gz_urdf
from frybot_control.layout import Graph, robot_ids
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
    share = get_package_share_directory('frybot_bringup')
    tmp = tempfile.mkdtemp(prefix='frybot_gz_')
    if LC('net').perform(context) == 'local':
        # Everything runs on this PC: keep Gazebo transport and ROS discovery on the loopback interface. Bound to the
        # LAN address instead, the whole simulation froze when the Ethernet link dropped for a few minutes.
        os.environ['GZ_IP'] = '127.0.0.1'
        os.environ['ROS_AUTOMATIC_DISCOVERY_RANGE'] = 'LOCALHOST'
    world = os.path.join(tmp, 'frybot_store.sdf')
    # Humble -> Fortress (ign, ignition.msgs); Jazzy -> Harmonic (gz sim, gz.msgs)
    fortress = os.environ.get('ROS_DISTRO') == 'humble' and shutil.which('ign') is not None
    gm = 'ignition.msgs' if fortress else 'gz.msgs'
    gz = ['ign', 'gazebo'] if fortress else ['gz', 'sim']
    gui = LC('gui').perform(context) == 'true'
    drive = LC('drive').perform(context)
    nav2 = drive == 'nav2'
    ROBOTS = robot_ids(LC('robots').perform(context))     # robots:=N -> pinky1..pinkyN
    robot_models = []
    acts = [Node(package='ros_gz_bridge', executable='parameter_bridge', name='clock_tf_bridge', output='screen',
                 arguments=[f'/clock@rosgraph_msgs/msg/Clock[{gm}.Clock'] +
                           ([f'/world/frybot_store/dynamic_pose/info@tf2_msgs/msg/TFMessage[{gm}.Pose_V'] if fortress else []) +
                           ([f'/tf@tf2_msgs/msg/TFMessage[{gm}.Pose_V'] if nav2 else []),
                 remappings=[('/world/frybot_store/dynamic_pose/info', '/gz/model_poses')])]
    g = Graph()
    params_src = open(os.path.join(share, 'config', 'nav2_amr.yaml')).read()
    bt = os.path.join(share, 'config', 'segment_bt.xml')
    for i, rid in enumerate(ROBOTS):
        path = os.path.join(tmp, rid + '.urdf')
        open(path, 'w').write(pinky_gz_urdf(rid, fortress))
        x, y = g.nodes[g.home_of(rid)]
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
        if not nav2:
            continue
        pfile = os.path.join(tmp, rid + '_nav2.yaml')
        body = params_src.replace('__NS__', rid).replace('__BT__', bt)
        # the nodes run in the robot's namespace, so the parameter file needs the namespace as its root key
        open(pfile, 'w').write(rid + ':\n' + ''.join('  ' + ln if ln.strip() else ln for ln in body.splitlines(True)))
        # localisation (map -> odom) is published by the AMR node from the simulator's true pose
        # start the three Nav2 stacks a few seconds apart: brought up together, lifecycle transitions time out
        acts.append(TimerAction(period=15.0 + 7.0 * i, actions=[
            Node(package='nav2_controller', executable='controller_server', namespace=rid, output='screen', parameters=[pfile]),
            Node(package='nav2_planner', executable='planner_server', namespace=rid, output='screen', parameters=[pfile]),
            Node(package='nav2_bt_navigator', executable='bt_navigator', namespace=rid, output='screen', parameters=[pfile]),
            Node(package='nav2_lifecycle_manager', executable='lifecycle_manager', name='lifecycle_manager', namespace=rid,
                 output='screen', parameters=[{'use_sim_time': True, 'autostart': True, 'bond_timeout': 0.0,
                                               'node_names': ['controller_server', 'planner_server', 'bt_navigator']}]),
        ]))
    if nav2:      # a lost lifecycle response at start-up leaves a robot without Nav2: check and restart it
        acts.append(Node(package='frybot_sim', executable='nav2_watchdog', output='screen',
                         parameters=[{'robot_ids': ROBOTS}]))
    # Harmonic: the robots are part of the world file. Spawned later through the create service, the GUI
    # (software rendering, sim well below real time) sometimes misses them and draws only one Pinky.
    sdf = world_sdf(fortress).replace('</world>', ''.join(robot_models) + '\n</world>')
    open(world, 'w').write(sdf)
    acts.insert(0, ExecuteProcess(cmd=gz + ['-r'] + ([] if gui else ['-s']) + [world], output='screen'))
    acts.append(IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(share, 'launch', 'sim.launch.py')),
        launch_arguments={'drive': drive, 'rviz': LC('rviz'), 'scheduler': LC('scheduler'), 'planner': LC('planner'),
                          'sim_time': 'true' if nav2 else 'false', 'standby': LC('standby'),
                          'robots': LC('robots'), 'net': LC('net')}.items()))
    return acts


def generate_launch_description():
    res = os.path.dirname(get_package_share_directory('pinky_description'))
    args = [('gui', 'true'), ('rviz', 'true'), ('drive', 'nav2'), ('scheduler', 'min_cost_eta_rh'), ('planner', 'sipp'),
            ('standby', 'true'), ('robots', '3'), ('net', 'lan')]
    return LaunchDescription([DeclareLaunchArgument(k, default_value=v) for k, v in args] + [
        SetEnvironmentVariable('IGN_GAZEBO_RESOURCE_PATH', res + ':' + os.environ.get('IGN_GAZEBO_RESOURCE_PATH', '')),
        SetEnvironmentVariable('GZ_SIM_RESOURCE_PATH', res + ':' + os.environ.get('GZ_SIM_RESOURCE_PATH', '')),
        OpaqueFunction(function=setup)])
