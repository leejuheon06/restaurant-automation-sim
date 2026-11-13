"""FryBot full system in the lightweight simulation.

  ros2 launch frybot_bringup sim.launch.py                       # RViz + all nodes
  ros2 launch frybot_bringup sim.launch.py planner:=cooperative_astar scheduler:=fifo_nearest rviz:=false

UIs:  http://localhost:8080 (reception / table / admin)   http://localhost:8090 (guest simulator)
"""
import os
import re
import tempfile

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration as LC
from launch_ros.actions import Node

from frybot_bringup.urdf_tools import jetcobot_urdf, pinky_urdf
from frybot_control.layout import COOK_ARMS, m, robot_ids

ARM_SCALE = 0.3


def rviz_config(robots):
    """RViz config with one robot + serving-arm display per AMR (the file on disk holds pinky1's as the template)."""
    src = open(os.path.join(get_package_share_directory('frybot_bringup'), 'rviz', 'frybot.rviz')).read()
    blocks = src.split('    - Class: ')
    out, base, arm = [], None, None
    for b in blocks:
        name = re.search(r'\n      Name: (\S+)', b)
        name = name.group(1) if name else ''
        if re.fullmatch(r'pinky\d+', name):
            base = base or b.replace(name, 'pinky1')
            if out[-1] != '@AMR@':
                out.append('@AMR@')
        elif re.fullmatch(r'pinky\d+_arm', name):
            arm = arm or b.replace(name[:-4], 'pinky1')
        else:
            out.append(b)
    amr = [base.replace('pinky1', r) for r in robots] + [arm.replace('pinky1', r) for r in robots]
    i = out.index('@AMR@')
    out[i:i + 1] = amr
    path = os.path.join(tempfile.mkdtemp(prefix='frybot_rviz_'), 'frybot.rviz')
    open(path, 'w').write('    - Class: '.join(out))
    return path


def setup(context):
    g = lambda k: LC(k).perform(context)
    if g('net') == 'local':
        # Everything runs on this PC: keep Gazebo transport and ROS discovery on the loopback interface. Bound to the
        # LAN address instead, the whole simulation froze when the Ethernet link dropped for a few minutes.
        os.environ['GZ_IP'] = '127.0.0.1'
        os.environ['ROS_AUTOMATIC_DISCOVERY_RANGE'] = 'LOCALHOST'
    drive, speed, guide = g('drive'), float(g('speed')), float(g('guide_speed'))
    st = {'use_sim_time': g('sim_time') == 'true'}
    ROBOTS = robot_ids(g('robots'))            # robots:=N -> pinky1..pinkyN (cooking arms are fixed)
    nodes = [
        Node(package='frybot_control', executable='central_control', output='screen',
             parameters=[{'run_id': g('run_id'), 'scenario': g('scenario_name'), 'qr_vacant_sec': float(g('qr_vacant_sec')),
                          'robot_ids': ROBOTS}]),
        Node(package='frybot_control', executable='task_manager', output='screen',
             parameters=[{'scheduler': g('scheduler'), 'planner': g('planner'), 'speed': speed, 'guide_speed': guide,
                          'cook_time_scale': float(g('cook_time_scale')), 'robot_ids': ROBOTS,
                          'use_standby': g('standby') == 'true'}]),
        Node(package='frybot_web', executable='web_service', output='screen'),
        Node(package='frybot_sim', executable='ai_server', output='screen'),
        Node(package='frybot_sim', executable='world', output='screen'),
        Node(package='frybot_sim', executable='customer_ui', output='screen'),
    ]
    pinky = pinky_urdf()
    arm_small, arm_full = jetcobot_urdf(ARM_SCALE), jetcobot_urdf(1.0)
    for rid in ROBOTS:
        nodes += [
            Node(package='frybot_sim', executable='amr', name='amr', namespace=rid, output='screen',
                 parameters=[{'robot_id': rid, 'drive': drive, 'speed': speed, 'guide_speed': guide}, st]),
            Node(package='robot_state_publisher', executable='robot_state_publisher', namespace=rid,
                 parameters=[{'robot_description': pinky, 'frame_prefix': rid + '/'}, st]),
            Node(package='robot_state_publisher', executable='robot_state_publisher', namespace=rid + '/arm',
                 parameters=[{'robot_description': arm_small, 'frame_prefix': rid + '_arm/'}, st]),
            Node(package='tf2_ros', executable='static_transform_publisher', name='arm_mount', namespace=rid,
                 arguments=['--x', '0.0', '--y', '0', '--z', '0.105', '--frame-id', rid + '/base_link',
                            '--child-frame-id', rid + '_arm/g_base']),
        ]
    for arm_id, info in COOK_ARMS.items():
        x, y = m(*info['pos_cm'])
        nodes += [
            Node(package='frybot_sim', executable='cook_arm', name='cook_arm', namespace=arm_id, output='screen',
                 parameters=[{'arm_id': arm_id, 'undercooked_prob': float(g('undercooked_prob'))}]),
            Node(package='robot_state_publisher', executable='robot_state_publisher', namespace=arm_id,
                 parameters=[{'robot_description': arm_full, 'frame_prefix': arm_id + '/'}]),
            Node(package='tf2_ros', executable='static_transform_publisher', name='base_tf', namespace=arm_id,
                 arguments=['--x', str(x), '--y', str(y), '--z', '0.0', '--yaw', '3.14159', '--frame-id', 'map',
                            '--child-frame-id', arm_id + '/g_base']),
        ]
    nodes.append(Node(package='rviz2', executable='rviz2', condition=IfCondition(LC('rviz')),
                      arguments=['-d', rviz_config(ROBOTS)]))
    return nodes


def generate_launch_description():
    args = [('scheduler', 'min_cost_eta_rh'), ('planner', 'sipp'), ('rviz', 'true'), ('drive', 'kinematic'),
            ('speed', '0.08'), ('guide_speed', '0.05'), ('cook_time_scale', '20.0'), ('qr_vacant_sec', '8.0'),
            ('undercooked_prob', '0.25'), ('run_id', ''), ('standby', 'true'), ('sim_time', 'false'), ('scenario_name', 'interactive'),
            ('robots', '3'), ('net', 'lan')]
    return LaunchDescription([DeclareLaunchArgument(k, default_value=v) for k, v in args] + [OpaqueFunction(function=setup)])
