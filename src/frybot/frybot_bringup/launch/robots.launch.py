"""Bring up the robot-side software of every registered Pinky from the central PC (SSH), nothing else.

  ros2 launch frybot_bringup robots.launch.py map_id:=test_map_v001  # all
  ros2 launch frybot_bringup robots.launch.py map_id:=test_map_v001 robots:=2  # only pinky1 and pinky2

real.launch.py includes the same processes, so normally that one launch is all you run.
[수정 2026-11-18] T-30: 등록부는 ~/.config/frybot/robots.yaml
(형식은 config/robots.example.yaml). 없으면 안내 로그만 남김.
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration as LC

# [수정 2026-11-18] T-30: registry_notice 추가
from frybot_bringup.remote import (pick_robots, registered, registry_notice,
                                   remote_bringup)


def setup(context):
    """등록부의 로봇마다 SSH 기동 프로세스(robot_remote)를 만든다.

    discovery, poses 는 넘기지 않아 robot_remote 기본(peers)으로 뜨고,
    관제 PC 쪽 ROS_STATIC_PEERS 는 정하지 않는다(real.launch.py 와 다름).

    Args:
        context: 런치 컨텍스트.

    Returns:
        등록부 안내 로그(없을 때)와 로봇별 ExecuteProcess 목록.
    """
    g = lambda k: LC(k).perform(context)
    reg = registered(g('robots_file'))
    # [수정 2026-11-18] T-30: 등록부가 없으면 안내 로그
    # [수정 2026-11-18] map:= 인자를 지움(사용자 결정). 다른 yaml 을 끼우면
    # roadmap.json 과 지도 이미지가 어긋남. 필요하면 maps/ 에 새 map_id 로 추가
    return registry_notice(g('robots_file')) + remote_bringup(
        pick_robots(g('robots'), reg), g('map_id'),
        robots_file=g('robots_file'))


def generate_launch_description():
    """robots, map_id, robots_file 인자를 선언하고 setup 을 붙인다.

    Returns:
        LaunchDescription.
    """
    args = [('robots', ''), ('map_id', ''), ('robots_file', '')]
    return LaunchDescription([DeclareLaunchArgument(k, default_value=v) for k, v in args] +
                             [OpaqueFunction(function=setup)])
