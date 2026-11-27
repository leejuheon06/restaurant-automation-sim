"""RViz 만 따로 띄운다 (real.launch.py 를 rviz:=false 로 띄웠을 때).

  ros2 launch frybot_bringup fleet_rviz.launch.py robots:=pinky1,pinky3

[수정 2026-11-19] T-40: robots 인자 추가. 전에는 pinky1·pinky2 만 표시했음.
real.launch.py 와 같은 규칙: 'pinky1,pinky3' 은 그 로봇들, '2' 는
pinky1..pinky2, 비우면 등록부의 로봇 전부(등록부가 없으면 pinky1).
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.actions import OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

from frybot_bringup.remote import fleet_rviz_config
from frybot_bringup.remote import pick_robots
from frybot_bringup.remote import registered


def setup(context) -> list:
    """인자 robots 에 맞는 중계 노드와 RViz 를 만든다.

    Args:
        context: 런치 컨텍스트.

    Returns:
        fleet_rviz 노드와 rviz2 노드.
    """
    arg = LaunchConfiguration('robots').perform(context)
    robots = pick_robots(arg, registered(''))  # 등록부는 기본 위치만 봄
    # [수정 2026-11-18] P2: RViz 설정 이름 fleet_real.rviz -> fleet.rviz
    # [수정 2026-11-19] rviz_displays:=false 면 Displays 창 없이 띄움(녹화용)
    hide = LaunchConfiguration('rviz_displays').perform(context) == 'false'
    config = fleet_rviz_config(robots, hide_displays=hide)
    return [
        # [수정 2026-11-19] map_id 를 주면 그 지도의 로드맵도 그림
        Node(package='frybot_bringup', executable='fleet_rviz',
             output='screen', parameters=[{
                 'robot_ids': robots,
                 'map_id': LaunchConfiguration('map_id').perform(context)}]),
        Node(package='rviz2', executable='rviz2', output='screen',
             arguments=['-d', str(config)]),
    ]


def generate_launch_description():
    """robots, rviz_displays, map_id 인자를 선언하고 setup 을 붙인다.

    Returns:
        LaunchDescription.
    """
    return LaunchDescription([
        DeclareLaunchArgument('robots', default_value=''),
        DeclareLaunchArgument('rviz_displays', default_value='true'),
        DeclareLaunchArgument('map_id', default_value=''),
        OpaqueFunction(function=setup)])
