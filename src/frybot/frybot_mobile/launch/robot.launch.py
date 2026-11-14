"""Everything that runs ON one real Pinky Pro for FryBot: the robot's own drivers, FrybotNavigator and the
FrybotMobile Controller, all in the robot's namespace.

  ros2 launch frybot_mobile robot.launch.py robot_id:=pinky1 map:=$HOME/frybot_map/store.yaml

Start the robot on its home spot (charger of that robot), facing into the store (+x). The central PC runs
`ros2 launch frybot_bringup real.launch.py` with the same ROS_DOMAIN_ID.
  drivers:=false   the Pinky drivers (pinky_bringup) are already running in this namespace
  ai_host:=<ip>    address of the AI server (camera stream stand-in), default: none
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, GroupAction, IncludeLaunchDescription, OpaqueFunction
from launch.launch_description_sources import AnyLaunchDescriptionSource, PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration as LC
from launch_ros.actions import Node, PushRosNamespace, SetRemap


def setup(context):
    g = lambda k: LC(k).perform(context)
    rid = g('robot_id')
    acts = []
    if g('drivers') == 'true':
        # pinky_bringup has no namespace argument: push the namespace and give the robot its own TF topics, so that
        # several robots can share one ROS domain (frames stay plain: odom, base_footprint, rplidar_link)
        acts.append(GroupAction([
            PushRosNamespace(rid), SetRemap('/tf', 'tf'), SetRemap('/tf_static', 'tf_static'),
            IncludeLaunchDescription(AnyLaunchDescriptionSource(os.path.join(
                get_package_share_directory('pinky_bringup'), 'launch', 'bringup_robot.launch.xml')))]))
    acts.append(IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(get_package_share_directory('frybot_mobile'), 'launch',
                                                   'navigator.launch.py')),
        launch_arguments={'robot_id': rid, 'mode': 'real', 'map': g('map')}.items()))
    acts.append(Node(package='frybot_mobile', executable='mobile_controller', name='amr', namespace=rid, output='screen',
                     remappings=[('/tf', 'tf'), ('/tf_static', 'tf_static')],
                     parameters=[{'robot_id': rid, 'drive': 'nav2', 'pose_source': 'tf', 'base_frame': 'base_footprint',
                                  'battery_topic': f'/{rid}/battery/percent', 'speed': float(g('speed')),
                                  'guide_speed': float(g('guide_speed')), 'ai_host': g('ai_host')}]))
    return acts


def generate_launch_description():
    args = [('robot_id', 'pinky1'), ('map', ''), ('drivers', 'true'), ('speed', '0.08'), ('guide_speed', '0.05'),
            ('ai_host', '127.0.0.1')]
    return LaunchDescription([DeclareLaunchArgument(k, default_value=v) for k, v in args] +
                             [OpaqueFunction(function=setup)])
