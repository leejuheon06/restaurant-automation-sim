"""FrybotNavigator: the Nav2 stack of one FrybotMobile, in the robot's namespace.

  ros2 launch frybot_mobile navigator.launch.py robot_id:=pinky1                       # simulation (default)
  ros2 launch frybot_mobile navigator.launch.py robot_id:=pinky1 mode:=real map:=/path/store.yaml

mode:=sim   simulator clock, frames "pinky1/...", one shared /tf; the pose comes from the simulator (no AMCL)
mode:=real  wall clock, plain frames on the robot's own /pinky1/tf, map_server + AMCL for localisation
Parameters: config/nav2_store.yaml (edit that file to tune costmaps, tolerances, speeds), tree: config/segment_bt.xml.
"""
import os

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration as LC

from frybot_mobile.navigator import navigator_nodes

def setup(context):
    g = lambda k: LC(k).perform(context)
    real = g('mode') == 'real'
    if real and not os.path.isfile(g('map')):
        raise RuntimeError('mode:=real needs map:=<store map yaml> (ros2 run frybot_control export_map <dir>)')
    return navigator_nodes(g('robot_id'), real, g('map'))


def generate_launch_description():
    return LaunchDescription([DeclareLaunchArgument('robot_id', default_value='pinky1'),
                              DeclareLaunchArgument('mode', default_value='sim'),
                              DeclareLaunchArgument('map', default_value=''),
                              OpaqueFunction(function=setup)])
