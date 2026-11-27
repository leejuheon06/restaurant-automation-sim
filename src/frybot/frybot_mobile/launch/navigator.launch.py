"""FrybotNavigator: the Nav2 stack of one FrybotMobile, in the robot's namespace.

  ros2 launch frybot_mobile navigator.launch.py robot_id:=pinky1 \
      map_id:=test_map_v001 map:=<그 지도의 yaml>
  ros2 launch frybot_mobile navigator.launch.py robot_id:=pinky1 mode:=sim
[수정 2026-11-18] P1: mode 기본을 real(실기기)로 바꿈. 시뮬 런치는
navigator_nodes 를 직접 부름. map_id:= 의 값을 FRYBOT_MAP_ID 로 넣음(도킹
검출기가 그 지도의 도크를 읽음). map:= 만 주고 map_id 를 비우면 그래프와
도크는 가상 매장 도면(proto)의 것이고, 그 사실을 로그에 남김.

mode:=sim   simulator clock, frames "pinky1/...", one shared /tf; the pose comes from the simulator (no AMCL)
mode:=real  wall clock, plain frames on the robot's own /pinky1/tf, map_server + AMCL for localisation
Parameters: config/nav2_store.yaml (edit that file to tune costmaps, tolerances, speeds), tree: config/segment_bt.xml.
"""
import math
import os

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo, OpaqueFunction
from launch.actions import SetEnvironmentVariable
from launch.substitutions import LaunchConfiguration as LC

from frybot_mobile.navigator import navigator_nodes

def setup(context):
    """런치 인자를 읽어 Nav2 스택 액션을 만든다(OpaqueFunction 용).

    Args:
        context: 런치 컨텍스트(인자 값을 읽음).

    Returns:
        FRYBOT_MAP_ID 설정, (map_id 가 없으면) 알림, navigator_nodes() 의
        노드 액션 목록.

    Raises:
        RuntimeError: mode:=real 인데 map:= 파일이 없을 때.
        ValueError: initial_pose 를 시뮬(mode:=sim)에서 주었거나 유한한
            숫자 세 개가 아닐 때(숫자가 아니면 float() 의 ValueError).
    """
    g = lambda k: LC(k).perform(context)
    real = g('mode') == 'real'  # real: 실기기, 그 밖: 시뮬
    if real and not os.path.isfile(g('map')):
        raise RuntimeError('mode:=real needs map:=<store map yaml> (ros2 run frybot_control export_map <dir>)')
    # 'x y yaw'(m, m, rad). 비어 있으면 () 로 AMCL 초기 자세를 넣지 않음
    pose = tuple(map(float, g('initial_pose').split()))
    if pose and (not real or len(pose) != 3 or not all(math.isfinite(value) for value in pose)):
        raise ValueError('initial_pose requires three finite numbers on a real robot: x y yaw')
    # [수정 2026-11-18] P1(D1): 지도 이름을 런치에 드러냄. 비었으면 proto 를
    # 명시하고 알림(예전에는 조용히 proto 로 떴음)
    map_id = g('map_id')
    acts = [SetEnvironmentVariable('FRYBOT_MAP_ID', map_id or 'proto')]
    if not map_id:
        acts.append(LogInfo(
            msg='map_id 가 없어 가상 매장 도면(proto)의 '
                '그래프·도크를 씁니다'))
    return acts + navigator_nodes(g('robot_id'), real, g('map'),
                                  measured=real and bool(map_id),
                                  initial_pose=pose,
                                  # [수정 2026-11-20] 도크 판단에 지도 이름
                                  map_id=map_id)


def generate_launch_description():
    """robot_id, mode, map, map_id, initial_pose 인자와 setup 을 묶는다.

    Returns:
        LaunchDescription.
    """
    return LaunchDescription([DeclareLaunchArgument('robot_id', default_value='pinky1'),
                              # [수정 2026-11-18] P1: 기본 real
                              DeclareLaunchArgument('mode',
                                                    default_value='real'),
                              # map: Nav2 지도 yaml 경로(real 에서 필수)
                              DeclareLaunchArgument('map', default_value=''),
                              DeclareLaunchArgument('map_id', default_value=''),
                              DeclareLaunchArgument('initial_pose', default_value='', description='Map x y yaw'),
                              OpaqueFunction(function=setup)])
