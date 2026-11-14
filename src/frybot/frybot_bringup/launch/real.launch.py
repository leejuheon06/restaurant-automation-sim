"""Central PC side of FryBot with REAL AMRs: Web Service, Central Control, Task Manager (no simulator, no AMR nodes).

  ros2 launch frybot_bringup real.launch.py robots:=1

Each Pinky runs `ros2 launch frybot_mobile robot.launch.py robot_id:=pinkyN map:=...` in the same ROS_DOMAIN_ID.
The cooking arms and the AI server have no real counterpart yet: sim_cooking:=true (default) starts their stand-ins
so that orders can be cooked and served; guests are entered on the web pages (reception / table tablets).
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration as LC
from launch_ros.actions import Node

from frybot_control.layout import COOK_ARMS, robot_ids


def setup(context):
    g = lambda k: LC(k).perform(context)
    robots = robot_ids(g('robots'))
    nodes = [
        Node(package='frybot_control', executable='central_control', output='screen',
             parameters=[{'run_id': g('run_id'), 'scenario': 'real', 'robot_ids': robots}]),
        Node(package='frybot_control', executable='task_manager', output='screen',
             parameters=[{'scheduler': g('scheduler'), 'planner': g('planner'), 'speed': float(g('speed')),
                          'guide_speed': float(g('guide_speed')), 'cook_time_scale': float(g('cook_time_scale')),
                          'robot_ids': robots, 'use_standby': g('standby') == 'true'}]),
        Node(package='frybot_web', executable='web_service', output='screen'),
    ]
    if g('sim_cooking') == 'true':
        nodes.append(Node(package='frybot_sim', executable='ai_server', output='screen'))
        nodes += [Node(package='frybot_sim', executable='cook_arm', name='cook_arm', namespace=arm_id, output='screen',
                       parameters=[{'arm_id': arm_id, 'undercooked_prob': 0.0}]) for arm_id in COOK_ARMS]
    return nodes


def generate_launch_description():
    args = [('robots', '1'), ('scheduler', 'min_cost_eta_rh'), ('planner', 'sipp'), ('speed', '0.08'),
            ('guide_speed', '0.05'), ('cook_time_scale', '20.0'), ('standby', 'false'), ('sim_cooking', 'true'),
            ('run_id', '')]
    return LaunchDescription([DeclareLaunchArgument(k, default_value=v) for k, v in args] +
                             [OpaqueFunction(function=setup)])
