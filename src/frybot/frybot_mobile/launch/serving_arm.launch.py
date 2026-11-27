"""서빙 팔(JetCobot 280)의 Raspberry Pi 에서 띄우는 것: serving_arm_driver.

  ros2 launch frybot_mobile serving_arm.launch.py robot_id:=pinky1

  robot_id:=<pinky>   팔을 올린 AMR. 액션 이름이 /<pinky>/serving_arm/arm_job
  python:=<경로>      노드를 돌릴 Python. 기본은 pymycobot 이 설치된 가상 환경
                      (~/venv/jetcobot). 비우면 ros2 의 기본 Python 을 씀
  port, speed         직렬 포트, pymycobot 이동 속도(1~100)

[수정 2026-11-20] 신규. 팔 Pi 의 pymycobot 은 가상 환경에만 있어, ROS 설정을
불러온 셸에서 가상 환경의 Python 으로 모듈을 직접 실행함.
"""
import os

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.actions import ExecuteProcess
from launch.actions import OpaqueFunction
from launch.launch_context import LaunchContext
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def setup(context: LaunchContext) -> list:
    """런치 인자를 읽어 serving_arm_driver 를 띄우는 액션을 만든다."""
    def g(key: str) -> str:
        return LaunchConfiguration(key).perform(context)

    params = {'robot_id': g('robot_id'), 'port': g('port'),
              'speed': int(g('speed'))}
    python = os.path.expanduser(g('python'))
    # python:= 를 비우면 보통의 ROS 노드로(ros2 의 기본 Python)
    if not python:
        return [Node(package='frybot_mobile', executable='serving_arm_driver',
                     output='screen', parameters=[params])]
    # 가상 환경 Python 으로 모듈을 직접 실행. 파라미터는 --ros-args -p 로
    args = []
    for key, value in params.items():
        args += ['-p', f'{key}:={value}']
    return [ExecuteProcess(
        cmd=[python, '-m', 'frybot_mobile.serving_arm_driver', '--ros-args']
        + args, output='screen')]


def generate_launch_description() -> LaunchDescription:
    """robot_id, port, speed, python 인자를 선언하고 setup 을 붙인다.

    Returns:
        LaunchDescription.
    """
    # [수정 2026-11-20] speed 기본 '20' → '10'(구동부 기본과 같게)
    # [수정 2026-11-20] speed 기본 '10' → '70'(구동부 기본과 같게)
    # [수정 2026-11-20] speed 기본 '70' → '60'(구동부 기본과 같게)
    args = [('robot_id', 'pinky1'), ('port', '/dev/ttyJETCOBOT'),
            ('speed', '60'), ('python', '~/venv/jetcobot/bin/python3')]
    return LaunchDescription(
        [DeclareLaunchArgument(k, default_value=v) for k, v in args]
        + [OpaqueFunction(function=setup)])
