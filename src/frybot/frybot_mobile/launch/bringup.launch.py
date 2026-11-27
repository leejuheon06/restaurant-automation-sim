"""Pinky 드라이버만 한 번에 띄우는 런치(Nav2·mobile_controller 없음).

pinky_pro 의 bringup_robot.launch.xml 처럼 로봇 모델, 라이다, 모터 드라이버
(pinky_driver), 배터리(pinky_battery)를 함께 띄운다. 수동 조종(teleop)이나
센서 점검처럼 관제·지도 없이 로봇만 켤 때 쓴다. Pinky 안에서 실행한다.

  ros2 launch frybot_mobile bringup.launch.py robot_id:=pinky1

토픽은 robot.launch.py 와 같이 /<robot_id>/cmd_vel, odom, scan,
battery/percent 등 네임스페이스 안에 나온다. robot.launch.py 와 동시에
띄우지 않는다(같은 직렬 포트를 씀).
"""
# [수정 2026-11-24] 새 파일: 드라이버만 띄우는 런치(사용자 요청, teleop 용).
# 드라이버 구성은 robot.launch.py 의 driver_actions 를 그대로 불러 씀
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchContext
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.actions import GroupAction
from launch.actions import OpaqueFunction
from launch.launch_description_sources import python_launch_file_utilities
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import PushRosNamespace
from launch_ros.actions import SetRemap


def setup(context: LaunchContext) -> list:
    """런치 인자로 네임스페이스를 씌운 드라이버 묶음을 만든다.

    Args:
        context: 런치 컨텍스트(인자 값을 읽음).

    Returns:
        OpaqueFunction 이 실행할 launch 액션 목록.
    """
    load = python_launch_file_utilities.load_python_launch_file_as_module
    robot_launch = load(
        os.path.join(get_package_share_directory('frybot_mobile'),
                     'launch', 'robot.launch.py'))
    rid = LaunchConfiguration('robot_id').perform(context)
    drivers = robot_launch.driver_actions(
        LaunchConfiguration('drivers').perform(context),
        LaunchConfiguration('motor_port').perform(context),
        LaunchConfiguration('lidar_port').perform(context))
    # robot.launch.py 와 같은 네임스페이스·TF 토픽 분리(/<robot_id>/tf)
    return [GroupAction([
        PushRosNamespace(rid), SetRemap('/tf', 'tf'),
        SetRemap('/tf_static', 'tf_static')] + drivers)]


def generate_launch_description() -> LaunchDescription:
    """bringup.launch.py 의 런치 인자를 선언하고 setup 을 붙인다.

    Returns:
        LaunchDescription.
    """
    # 기본값은 robot.launch.py 와 같음. drivers: true(frybot 드라이버),
    # pinky_pro(외부 pinky_bringup)
    args = [('robot_id', 'pinky1'), ('drivers', 'true'),
            ('motor_port', '/dev/ttyAMA5'), ('lidar_port', '/dev/ttyS0')]
    return LaunchDescription(
        [DeclareLaunchArgument(k, default_value=v) for k, v in args] +
        [OpaqueFunction(function=setup)])
