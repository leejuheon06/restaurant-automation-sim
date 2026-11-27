"""Everything that runs ON one real Pinky Pro for FryBot: the robot's own drivers, FrybotNavigator and the
FrybotMobile Controller, all in the robot's namespace.

  ros2 launch frybot_mobile robot.launch.py robot_id:=pinky1 \
      map_id:=test_map_v001

[수정 2026-11-18] D7: map_id:= 는 필수(real.launch.py 의 B4 와 같음).
없으면 쓸 수 있는 지도 이름을 안내하고 멈춤. 예전에는 map:= 만 주면
그래프가 가상 매장 도면(proto)으로 조용히 떴음.
[수정 2026-11-18] map:= 인자를 지움(사용자 결정). 다른 yaml 을 끼우면
roadmap.json 과 지도 이미지가 어긋남. 필요하면 maps/ 에 새 map_id 로 추가.

홈에서 시작하는 것은 필수가 아님. initial_pose 를 주면 그 자세, 없으면
auto_localize(기본 켬)가 저장 자세·스캔으로 찾고 모호하면 홈 근처를 고름
(T-49~51). 홈 시작을 계속 권할지는 확인 필요.
The central PC runs
`ros2 launch frybot_bringup real.launch.py` with the same ROS_DOMAIN_ID.
  drivers:=false   the Pinky drivers are already running in this namespace
  drivers:=pinky_pro   use the external pinky_bringup (bringup_robot.launch.xml) as before 2026-11-17
  ai_host:=<ip>    AI server (camera stream stand-in), default: 127.0.0.1
  guest_track_required:=false   [수정 2026-11-17] G4: 기본 true. 손님 추적 값이 없어도 안내를 출발(시험용)
  serving_arm:=real   [수정 2026-11-20] 팔 작업을 서빙 팔의 실물 구동부
      (/<robot>/serving_arm/arm_job, 팔 Pi 의 serving_arm.launch.py)로 넘김.
      기본 '' 는 대역(시간만 지나면 성공)
  wheel_radius:=0.02763 wheel_separation:=0.0992   [수정 2026-11-24] MT-4:
      이 로봇의 바퀴 반지름·간격(m). pinky_driver 의 속도 명령 -> RPM 과
      오도메트리가 함께 씀. 비우면 명목값 0.027 / 0.0961(예전과 같음).
      명목값에서 10% 넘게 벗어나거나 숫자가 아니면 런치가 멈춤.
      robot_remote 는 등록부의 같은 이름 키를 넘김
  cmd_vel_timeout:=0.3   [수정 2026-11-24] MT-6: pinky_driver 가 cmd_vel 이
      이 시간(s) 넘게 끊기면 0 RPM. 비우면 노드 기본값(0.3).
      [수정 2026-11-25] MT-7: 노드 기본값 0.5 -> 0.3 s
      0 이하는 감시를 끔(경고 로그), 2 s 를 넘거나 숫자가 아니면 런치가 멈춤.
      robot_remote 는 --arg cmd_vel_timeout:=0.3 또는 등록부 launch_args
"""
import os
import subprocess

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, GroupAction, IncludeLaunchDescription, OpaqueFunction, SetEnvironmentVariable
# [수정 2026-11-24] MT-4: 적용한 바퀴 치수를 기동 로그에 남김
from launch.actions import LogInfo
from launch.launch_description_sources import AnyLaunchDescriptionSource, PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration as LC
from launch_ros.actions import Node, PushRosNamespace, SetRemap

from frybot_control.layout import Graph
from frybot_control.map_catalog import map_ids, profile


# [수정 2026-11-24] MT-4: 바퀴 치수 명목값(pinky_driver 기본값과 같음)과
# 로봇별 값의 허용 범위(명목값 +-10%). MT-3 실측 보정은 -0.6~+3.2%
WHEEL_RADIUS = 0.027
WHEEL_SEPARATION = 0.0961
WHEEL_TOLERANCE = 0.10


# [수정 2026-11-24] MT-6: cmd_vel_timeout 상한(s). 0.08 m/s 에서 2 s 면 발행이
# 끊긴 뒤 약 17 cm 를 더 가므로 그보다 긴 값은 실수로 봄
CMD_VEL_TIMEOUT_MAX = 2.0
# [수정 2026-11-25] MT-7: pinky_driver 의 cmd_vel_timeout 기본값(s, 이전 0.5).
# 인자를 비우면 노드가 이 값을 씀. 기동 로그 "(node default)" 줄에만 씀
CMD_VEL_TIMEOUT_DEFAULT = 0.3


# [수정 2026-11-24] 신규 (MT-6): cmd_vel_timeout 런치 인자 검사
def cmd_timeout_params(text: str) -> dict:
    """cmd_vel_timeout 인자를 pinky_driver 파라미터로 바꾼다.

    Args:
        text: 런치 인자 문자열(s). 빈 문자열이면 파라미터를 넘기지 않음
            (노드 기본값 CMD_VEL_TIMEOUT_DEFAULT, 2026-11-25 부터 0.3 s).

    Returns:
        {} 또는 {'cmd_vel_timeout': float}. 0 이하는 감시를 끄는 값(드라이버
        규칙)이라 그대로 넘기고, 경고는 부르는 쪽이 남긴다.

    Raises:
        ValueError: 숫자가 아니거나 CMD_VEL_TIMEOUT_MAX 를 넘을 때.
    """
    if not text.strip():
        return {}
    try:
        value = float(text)
    except ValueError:
        raise ValueError(f'cmd_vel_timeout:={text!r} 는 숫자가 아닙니다(s)'
                         ) from None
    if value > CMD_VEL_TIMEOUT_MAX:
        raise ValueError(f'cmd_vel_timeout:={value} 는 상한 '
                         f'{CMD_VEL_TIMEOUT_MAX} s 를 넘습니다')
    return {'cmd_vel_timeout': value}


# [수정 2026-11-24] 신규 (MT-4): 로봇별 바퀴 반지름·간격 런치 인자 검사
def wheel_params(radius: str, separation: str) -> dict:
    """런치 인자 문자열을 pinky_driver 의 바퀴 파라미터로 바꾼다.

    Args:
        radius: wheel_radius 인자(m). 빈 문자열이면 명목값.
        separation: wheel_separation 인자(m). 빈 문자열이면 명목값.

    Returns:
        {'wheel_radius': float, 'wheel_separation': float}.

    Raises:
        ValueError: 숫자가 아니거나 명목값에서 WHEEL_TOLERANCE 넘게
            벗어날 때. 틀린 치수로 오도메트리가 어긋난 채 뜨지 않게 멈춤.
    """
    out = {}
    for key, text, nominal in (('wheel_radius', radius, WHEEL_RADIUS),
                               ('wheel_separation', separation,
                                WHEEL_SEPARATION)):
        if not text.strip():
            out[key] = nominal
            continue
        try:
            value = float(text)
        except ValueError:
            raise ValueError(f'{key}:={text!r} 는 숫자가 아닙니다(m)') from None
        if not abs(value - nominal) <= WHEEL_TOLERANCE * nominal:
            raise ValueError(
                f'{key}:={value} 는 명목값 {nominal} 에서 '
                f'{WHEEL_TOLERANCE:.0%} 넘게 벗어납니다(m 단위인지 확인)')
        out[key] = value
    return out


# [수정 2026-11-17] pinky_pro 의존 제거: 모터·배터리 드라이버는 frybot_mobile,
# 로봇 모델은 frybot_description 의 사본을 씀. 구성은 pinky_bringup 의
# bringup_robot.launch.xml 과 같음. drivers:=pinky_pro 는 이전 방식(되돌리기용)
# [수정 2026-11-18] T-37: 모터·라이다 포트를 인자로 받음(기본은 로봇에 설치된
# pinky_bringup 과 같은 /dev/ttyAMA5, /dev/ttyS0. 11-17 사본은 다른 버전의
# /dev/ttyAMA4, /dev/ttyAMA0 이라 모터·라이다가 뜨지 않았음)
# [수정 2026-11-24] MT-4: wheel 인자(로봇별 바퀴 치수). 없으면 명목값
# [수정 2026-11-24] MT-6: extra 인자(pinky_driver 에 더 넘길 파라미터)
def driver_actions(mode: str, motor_port: str = '/dev/ttyAMA5',
                   lidar_port: str = '/dev/ttyS0',
                   wheel: dict | None = None,
                   extra: dict | None = None) -> list:
    """로봇 네임스페이스 안에서 띄울 Pinky 드라이버 액션을 만든다.

    Args:
        mode: 'pinky_pro' 이면 외부 pinky_bringup 의 런치를 포함하고,
            그 밖에는 frybot 안의 드라이버를 띄운다.
        motor_port: 모터(다이나믹셀) 직렬 포트. frybot 드라이버에만 씀.
        lidar_port: 라이다 직렬 포트. frybot 드라이버에만 씀.
        wheel: wheel_params() 의 결과. None 이면 명목값. frybot 드라이버에만
            씀(pinky_pro 모드는 외부 드라이버의 값을 씀).
        extra: pinky_driver 에 더 넘길 파라미터(예: cmd_timeout_params()).
            None 이면 없음. frybot 드라이버에만 씀.

    Returns:
        GroupAction 에 넣을 launch 액션 목록.
    """
    if mode == 'pinky_pro':
        return [IncludeLaunchDescription(AnyLaunchDescriptionSource(
            os.path.join(get_package_share_directory('pinky_bringup'),
                         'launch', 'bringup_robot.launch.xml')))]
    xacro_file = os.path.join(
        get_package_share_directory('frybot_description'),
        'pinky', 'urdf', 'robot.urdf.xacro')
    urdf = subprocess.check_output(
        ['xacro', xacro_file, 'namespace:=', 'is_sim:=false',
         'cam_tilt_deg:=0']).decode()
    lidar_launch = os.path.join(
        get_package_share_directory('sllidar_ros2'), 'launch',
        'sllidar_c1_launch.py')
    return [
        Node(package='robot_state_publisher',
             executable='robot_state_publisher', name='robot_state_publisher',
             parameters=[{'ignore_timestamp': False, 'use_sim_time': False,
                          'robot_description': urdf, 'frame_prefix': ''}]),
        Node(package='joint_state_publisher',
             executable='joint_state_publisher', name='joint_state_publisher',
             output='screen',
             parameters=[{'source_list': ['joint_states'], 'rate': 20.0,
                          'use_sim_time': False}]),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(lidar_launch),
            launch_arguments={
                'serial_port': lidar_port, 'frame_id': 'rplidar_link',
                'inverted': 'false', 'angle_compensate': 'true',
                'scan_mode': 'DenseBoost'}.items()),
        # [수정 2026-11-24] MT-4: 바퀴 치수를 인자로(예전 0.027, 0.0961 고정)
        Node(package='frybot_mobile', executable='pinky_driver',
             parameters=[{**(wheel or wheel_params('', '')),
                          'serial_port': motor_port, **(extra or {})}]),
        Node(package='frybot_mobile', executable='pinky_battery'),
    ]


def setup(context):
    """런치 인자로 드라이버, Nav2(navigator.launch.py), 제어기를 만든다.

    Args:
        context: 런치 컨텍스트(인자 값을 읽음).

    Returns:
        OpaqueFunction 이 실행할 launch 액션 목록.

    Raises:
        ValueError: map_id 가 비었을 때, 또는 그 지도의 homes 에 robot_id
            번호의 출발 노드가 없을 때(Graph.home_of).
    """
    g = lambda k: LC(k).perform(context)
    rid = g('robot_id')
    map_id = g('map_id')
    # [수정 2026-11-18] D7: map_id 필수. 지도 없이 가상 매장 그래프로 뜨지
    # 않게 함
    if not map_id:
        raise ValueError('robot.launch.py 에는 map_id:= 가 필요합니다. '
                         f'쓸 수 있는 값: {map_ids()}')
    # [수정 2026-11-18] map:= 를 지워 "둘 중 하나만" 검사도 지움
    Graph(map_id).home_of(rid)  # 지도에 이 로봇의 출발 노드가 있는지 확인
    map_yaml = profile(map_id)['yaml']
    # 이 런치에서 뜨는 노드가 같은 지도(FRYBOT_MAP_ID)를 보게 함
    acts = [SetEnvironmentVariable('FRYBOT_MAP_ID', map_id)]
    # [수정 2026-11-24] MT-4: 로봇별 바퀴 치수(잘못된 값이면 여기서 멈춤)
    wheel = wheel_params(g('wheel_radius'), g('wheel_separation'))
    given = bool(g('wheel_radius').strip() or g('wheel_separation').strip())
    if g('drivers') == 'true':
        acts.append(LogInfo(msg=(
            f"[{rid}] wheel_radius {wheel['wheel_radius']} m, wheel_separation "
            f"{wheel['wheel_separation']} m "
            f"({'robot value' if given else 'nominal'})")))
    elif given:
        acts.append(LogInfo(msg=(
            f"[{rid}] wheel_radius/wheel_separation ignored: drivers:="
            f"{g('drivers')} does not start frybot's pinky_driver")))
    # [수정 2026-11-24] MT-6: cmd_vel 감시 시간(잘못된 값이면 여기서 멈춤)
    timeout = cmd_timeout_params(g('cmd_vel_timeout'))
    if g('drivers') == 'true':
        t = timeout.get('cmd_vel_timeout')
        acts.append(LogInfo(msg=(
            f'[{rid}] cmd_vel_timeout {t} s (launch arg)' if t is not None
            # [수정 2026-11-25] MT-7: 노드 기본값 숫자를 상수로(0.5 -> 0.3)
            else f'[{rid}] cmd_vel_timeout {CMD_VEL_TIMEOUT_DEFAULT} s '
            '(node default)')))
        if t is not None and t <= 0:
            acts.append(LogInfo(msg=(
                f'[{rid}] WARNING cmd_vel_timeout {t} <= 0: the motor '
                'watchdog is OFF (motors keep the last cmd_vel)')))
    elif timeout:
        acts.append(LogInfo(msg=(
            f"[{rid}] cmd_vel_timeout ignored: drivers:={g('drivers')}")))
    if g('drivers') != 'false':
        # the drivers have no namespace argument: push the namespace and give the robot its own TF topics, so that
        # several robots can share one ROS domain (frames stay plain: odom, base_footprint, rplidar_link)
        acts.append(GroupAction([
            PushRosNamespace(rid), SetRemap('/tf', 'tf'), SetRemap('/tf_static', 'tf_static')] +
            driver_actions(g('drivers'), g('motor_port'), g('lidar_port'),
                           wheel, timeout)))
    # Nav2 스택: 실기기 모드(map_server + AMCL 포함)
    acts.append(IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(get_package_share_directory('frybot_mobile'), 'launch',
                                                   'navigator.launch.py')),
        launch_arguments={'robot_id': rid, 'mode': 'real', 'map': map_yaml, 'map_id': map_id,
                          'initial_pose': g('initial_pose')}.items()))
    # [수정 2026-11-18] P2(D2): 노드 이름 amr -> mobile_controller
    acts.append(Node(package='frybot_mobile', executable='mobile_controller',
                     name='mobile_controller', namespace=rid, output='screen',
                     remappings=[('/tf', 'tf'), ('/tf_static', 'tf_static')],
                     parameters=[{'robot_id': rid, 'drive': 'nav2', 'pose_source': 'tf', 'base_frame': 'base_footprint',
                                  'battery_topic': f'/{rid}/battery/percent', 'speed': float(g('speed')),
                                  'guide_speed': float(g('guide_speed')), 'ai_host': g('ai_host'),
                                  # [수정 2026-11-17] G4: 실기기는 손님 추적
                                  # (/frybot/guest_track)이 없으면 안내 구간을
                                  # 출발하지 않음(사람 옆에서 후진하는 동작)
                                  'guest_track_required':
                                      g('guest_track_required') == 'true',
                                  # [수정 2026-11-20] 서빙 팔 실물 연결
                                  'serving_arm': g('serving_arm'),
                                  # [수정 2026-11-20] T-49: 초기 자세가 없으면
                                  # 스캔으로 자세를 찾음(initial_pose 우선)
                                  'auto_localize':
                                      g('auto_localize') == 'true',
                                  # [수정 2026-11-23] T-57: 천장 카메라 문의
                                  # 여부와 대기 상한(노드 생성 뒤 s).
                                  # real.launch 의 ceiling_camera:=false 가
                                  # localize_camera:=false 를 넘김
                                  'localize_camera':
                                      g('localize_camera') == 'true',
                                  'localize_camera_wait_sec':
                                      float(g('localize_camera_wait_sec')),
                                  'initial_pose': g('initial_pose')}]))
    return acts


def generate_launch_description():
    """robot.launch.py 의 런치 인자(이름, 기본값)를 선언하고 setup 을 붙인다.

    Returns:
        LaunchDescription.
    """
    # drivers: true(frybot 드라이버), pinky_pro(외부 pinky_bringup),
    # false(이미 떠 있음). speed·guide_speed 는 m/s
    args = [('robot_id', 'pinky1'), ('map_id', ''), ('drivers', 'true'), ('speed', '0.08'), ('guide_speed', '0.05'),
            ('ai_host', '127.0.0.1'), ('initial_pose', ''),
            # [수정 2026-11-18] T-37: 모터·라이다 직렬 포트
            ('motor_port', '/dev/ttyAMA5'), ('lidar_port', '/dev/ttyS0'),
            ('guest_track_required', 'true'),
            # [수정 2026-11-20] '' = 서빙 팔 대역, real = 실물 구동부로 넘김
            ('serving_arm', ''),
            # [수정 2026-11-20] T-49: 기동 때 자동 위치 추정(true 기본)
            ('auto_localize', 'true'),
            # [수정 2026-11-23] T-57: 천장 카메라 문의(기본 켬)와 대기 상한
            ('localize_camera', 'true'), ('localize_camera_wait_sec', '35.0'),
            # [수정 2026-11-24] MT-4: 로봇별 바퀴 치수(m). 비우면 명목값
            ('wheel_radius', ''), ('wheel_separation', ''),
            # [수정 2026-11-24] MT-6: pinky_driver cmd_vel 감시 시간(s). 비우면
            # 노드 기본값 0.5
            ('cmd_vel_timeout', '')]
    return LaunchDescription([DeclareLaunchArgument(k, default_value=v) for k, v in args] +
                             [OpaqueFunction(function=setup)])
