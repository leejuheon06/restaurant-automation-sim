"""Frybot Cooking Package 만 띄운다 (Master Controller + Arm Controller A/B).

  ros2 launch frybot_arm cooking.launch.py
  ros2 launch frybot_arm cooking.launch.py ai_host:=192.168.0.10

sim.launch.py(가상 매장)는 같은 노드를 직접 띄우므로 함께 실행하지 않습니다.
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration as LC

from frybot_arm.cooking import cooking_nodes


# 런치 인자를 읽어 조리 노드 목록을 만듦(팔은 ARM_IDS 두 대)
def _setup(context):
    return cooking_nodes(
        undercooked_prob=float(LC('undercooked_prob').perform(context)),
        ai_host=LC('ai_host').perform(context))


def generate_launch_description():
    """조리 노드를 띄우는 런치 설명을 만든다.

    Returns:
        undercooked_prob(덜 익음 확률), ai_host(AI 서버 주소) 인자와
        조리 노드를 담은 LaunchDescription.
    """
    return LaunchDescription([
        DeclareLaunchArgument('undercooked_prob', default_value='0.25'),
        DeclareLaunchArgument('ai_host', default_value='127.0.0.1'),
        OpaqueFunction(function=_setup)])
