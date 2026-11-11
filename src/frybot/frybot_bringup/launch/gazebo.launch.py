"""FryBot in Gazebo (gz sim): store world + 3 Pinky Pro, each with its own Nav2 stack (costmaps from the map and lidar).

  ros2 launch frybot_bringup gazebo.launch.py                 # Nav2 driving (default)
  ros2 launch frybot_bringup gazebo.launch.py drive:=cmd_vel  # old straight-line driving without costmaps
  ros2 launch frybot_bringup gazebo.launch.py gui:=false      # headless server

The Task Manager still decides routes and the order at shared nodes; every granted segment is a Nav2 goal.
Arms, guests and food stay simulated by the lightweight nodes.
"""
import os
import shutil
import tempfile

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription, OpaqueFunction,
                            SetEnvironmentVariable, TimerAction)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration as LC
from launch_ros.actions import Node

from frybot_bringup.urdf_tools import pinky_gz_urdf
from frybot_control.layout import Graph
from frybot_sim.gz_world_gen import world_sdf

ROBOTS = ['pinky1', 'pinky2', 'pinky3']


def setup(context):
    share = get_package_share_directory('frybot_bringup')
    tmp = tempfile.mkdtemp(prefix='frybot_gz_')
    world = os.path.join(tmp, 'frybot_store.sdf')
    open(world, 'w').write(world_sdf())
    fortress = shutil.which('ign') is not None
    gz = ['ign', 'gazebo'] if fortress else ['gz', 'sim']
    gui = LC('gui').perform(context) == 'true'
    drive = LC('drive').perform(context)
    nav2 = drive == 'nav2'
    acts = [ExecuteProcess(cmd=gz + ['-r'] + ([] if gui else ['-s']) + [world], output='screen'),
            Node(package='ros_gz_bridge', executable='parameter_bridge', name='clock_tf_bridge', output='screen',
                 arguments=['/clock@rosgraph_msgs/msg/Clock[ignition.msgs.Clock',
                            '/world/frybot_store/dynamic_pose/info@tf2_msgs/msg/TFMessage[ignition.msgs.Pose_V'] +
                           (['/tf@tf2_msgs/msg/TFMessage[ignition.msgs.Pose_V'] if nav2 else []),
                 remappings=[('/world/frybot_store/dynamic_pose/info', '/gz/model_poses')])]
    g = Graph()
    params_src = open(os.path.join(share, 'config', 'nav2_amr.yaml')).read()
    bt = os.path.join(share, 'config', 'segment_bt.xml')
    for i, rid in enumerate(ROBOTS):
        path = os.path.join(tmp, rid + '.urdf')
        open(path, 'w').write(pinky_gz_urdf(rid, fortress))
        x, y = g.pos(f'CH{i + 1}')
        acts += [
            Node(package='ros_gz_sim', executable='create', output='screen',
                 arguments=['-world', 'frybot_store', '-name', rid, '-file', path, '-x', str(x), '-y', str(y), '-z', '0.03']),
            Node(package='ros_gz_bridge', executable='parameter_bridge', name=rid + '_bridge', output='screen',
                 arguments=[f'/{rid}/cmd_vel@geometry_msgs/msg/Twist]ignition.msgs.Twist',
                            f'/{rid}/odom@nav_msgs/msg/Odometry[ignition.msgs.Odometry',
                            f'/{rid}/scan@sensor_msgs/msg/LaserScan[ignition.msgs.LaserScan']),
        ]
        if not nav2:
            continue
        pfile = os.path.join(tmp, rid + '_nav2.yaml')
        body = params_src.replace('__NS__', rid).replace('__BT__', bt)
        # the nodes run in the robot's namespace, so the parameter file needs the namespace as its root key
        open(pfile, 'w').write(rid + ':\n' + ''.join('  ' + ln if ln.strip() else ln for ln in body.splitlines(True)))
        # localisation (map -> odom) is published by the AMR node from the simulator's true pose
        # start the three Nav2 stacks a few seconds apart: brought up together, lifecycle transitions time out
        acts.append(TimerAction(period=6.0 + 7.0 * i, actions=[
            Node(package='nav2_controller', executable='controller_server', namespace=rid, output='screen', parameters=[pfile]),
            Node(package='nav2_planner', executable='planner_server', namespace=rid, output='screen', parameters=[pfile]),
            Node(package='nav2_bt_navigator', executable='bt_navigator', namespace=rid, output='screen', parameters=[pfile]),
            Node(package='nav2_lifecycle_manager', executable='lifecycle_manager', name='lifecycle_manager', namespace=rid,
                 output='screen', parameters=[{'use_sim_time': True, 'autostart': True, 'bond_timeout': 0.0,
                                               'node_names': ['controller_server', 'planner_server', 'bt_navigator']}]),
        ]))
    acts.append(IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(share, 'launch', 'sim.launch.py')),
        launch_arguments={'drive': drive, 'rviz': LC('rviz'), 'scheduler': LC('scheduler'), 'planner': LC('planner'),
                          'sim_time': 'true' if nav2 else 'false', 'standby': LC('standby')}.items()))
    return acts


def generate_launch_description():
    res = os.path.dirname(get_package_share_directory('pinky_description'))
    args = [('gui', 'true'), ('rviz', 'true'), ('drive', 'nav2'), ('scheduler', 'hungarian'), ('planner', 'sipp'),
            ('standby', 'true')]
    return LaunchDescription([DeclareLaunchArgument(k, default_value=v) for k, v in args] + [
        SetEnvironmentVariable('IGN_GAZEBO_RESOURCE_PATH', res + ':' + os.environ.get('IGN_GAZEBO_RESOURCE_PATH', '')),
        SetEnvironmentVariable('GZ_SIM_RESOURCE_PATH', res + ':' + os.environ.get('GZ_SIM_RESOURCE_PATH', '')),
        OpaqueFunction(function=setup)])
