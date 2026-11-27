"""Launch actions that start the registered robots over SSH.

See robot_remote.py and the registry ~/.config/frybot/robots.yaml.
[수정 2026-11-18] P2: 등록부 위치를 실제 경로로(예전 config/robots.yaml).
"""
import os

from ament_index_python.packages import get_package_prefix
from launch.actions import ExecuteProcess, LogInfo

# [수정 2026-11-20] T-47: load_arms, mounted_arms 추가(서빙 팔을 올린 로봇)
from .robot_remote import load_arms
from .robot_remote import load_registry
from .robot_remote import mounted_arms
from .robot_remote import registry_file
from .robot_remote import registry_missing


def registered(robots_file=''):
    """Enabled robots of the registry, {} when there is no usable registry."""
    try:  # 등록부가 없거나(OSError) 형식 오류(ValueError)면 빈 dict
        return load_registry(robots_file)
    except (OSError, ValueError):
        return {}


# [수정 2026-11-18] T-30: remote 기동인데 등록부가 없으면 아무 말 없이
# 관제만 뜨던 것을, 같은 동작에 안내 로그를 남기도록 함
def registry_notice(robots_file: str = '') -> list:
    """등록부가 없을 때 런치에 넣을 안내 로그를 돌려준다.

    Args:
        robots_file: 런치의 robots_file 인자.

    Returns:
        등록부가 있으면 빈 목록, 없으면 LogInfo 하나가 든 목록.
    """
    missing = registry_missing(robots_file)
    if not missing:
        return []
    return [LogInfo(msg=missing + ' -> 로봇 쪽은 기동하지 않음')]


# [수정 2026-11-20] T-47: 신규. 관제가 SERVE·COLLECT 를 맡길 로봇
def serving_robots(robots_file: str = '') -> list:
    """등록부에서 켜진 서빙 팔의 mount 에 든 로봇을 모두 돌려준다.

    이번 런치에 든 로봇으로 줄이지 않는다. 팔 있는 로봇이 런치에 없으면
    관제가 SERVE 를 거절하게 하려는 것(비어 있으면 모든 로봇이 받음).

    Args:
        robots_file: 런치의 robots_file 인자. 비우면 기본 위치.

    Returns:
        로봇 이름 목록(정렬). 등록부나 arms 구역이 없거나 읽지 못하면 빈
        목록.
    """
    try:
        arms = load_arms(robots_file)
        reg = load_registry(robots_file)
    except (OSError, ValueError):
        return []
    return sorted(rid for rid in reg if mounted_arms(rid, arms))


def pick_robots(arg, reg):
    """Robot ids for a launch: 'pinky1,pinky3' = exactly these, '2' = pinky1..pinky2, '' = all registered ones."""
    from frybot_control.layout import robot_ids
    arg = arg.strip()  # 런치 인자 robots 의 값
    if arg and not arg.isdigit():  # 'pinky1,pinky3': 적은 이름 그대로
        return [s.strip() for s in arg.split(',') if s.strip()]
    if arg:  # 숫자 N: pinky1..pinkyN (범위 밖이면 ValueError)
        return robot_ids(arg)
    return list(reg) or robot_ids(1)  # 빈 값: 등록부 전부, 없으면 pinky1


# [수정 2026-11-19] hide_displays 추가: 화면 녹화용으로 왼쪽 Displays 창
# 없이 띄움 (RViz 메뉴 Panels > Add New Panel > Displays 로 다시 열 수 있음).
# 설정의 "Hide Left Dock" 은 창이 뜨기 전에 적용돼 듣지 않아 쓰지 않음
def fleet_rviz_config(robot_ids, hide_displays: bool = False):
    """RViz config for exactly these robots, made from rviz/fleet.rviz (which is written for pinky1 and pinky2):
    one display group per robot (global / local costmap, footprint, model) and one "2D Pose Estimate" tool per robot
    (in robot order) that publishes on /<robot>/initialpose for that robot's AMCL.

    Args:
        robot_ids: 표시할 로봇 이름 목록.
        hide_displays: True 면 왼쪽 Displays 창 없이 띄운다.

    Returns:
        만든 설정 파일의 경로.
    """
    import tempfile
    from ament_index_python.packages import get_package_share_directory
    # 원본 설정(rviz/fleet.rviz)을 문자열로 읽어 로봇 수만큼 늘림
    # [수정 2026-11-18] P2: RViz 설정 이름 fleet_real.rviz -> fleet.rviz
    text = open(os.path.join(get_package_share_directory('frybot_bringup'),
                             'rviz', 'fleet.rviz')).read()
    # 자르는 기준 줄: mark = 로봇별 표시 그룹의 시작, tail_mark = 그룹 뒤
    # MarkerArray 표시의 시작, tools = 도구 목록의 시작
    mark, tail_mark, tools = '  - Class: rviz_common/Group\n', '  - Class: rviz_default_plugins/MarkerArray\n', '  Tools:\n'
    head, rest = text.split(mark, 1)  # head: 첫 그룹 앞(공용 표시)
    group = mark + rest.split(mark, 1)[0]  # 첫 그룹(pinky1)을 틀로 씀
    tail = tail_mark + text.split(tail_mark, 1)[1]  # 원본의 다른 그룹은 버림
    # 로봇마다 /<rid>/initialpose 로 내는 2D Pose Estimate 도구 하나씩
    pose = ''.join(f'  - Class: rviz_default_plugins/SetInitialPose\n    Covariance x: 0.02\n    Covariance y: 0.02\n'
                   f'    Covariance yaw: 0.03\n    Topic:\n      Depth: 5\n      Durability Policy: Volatile\n'
                   f'      History Policy: Keep Last\n      Reliability Policy: Reliable\n'
                   f'      Value: /{rid}/initialpose\n' for rid in robot_ids)
    # 도구는 Tools 목록 끝('  Views:' 바로 앞)에 넣고, head 의
    # /pinky1/map(실측 지도 표시)은 첫 로봇 이름으로 바꿈
    before, after = tail.split(tools, 1)
    out = head.replace('pinky1', robot_ids[0]) + ''.join(group.replace('pinky1', rid) for rid in robot_ids) + \
        before + tools + after.replace('  Views:\n', pose + '  Views:\n', 1)
    # Panels 목록의 유일한 항목(Displays 창)을 빈 목록으로 바꿈
    if hide_displays:
        out = out.replace('Panels:\n- Class: rviz_common/Displays\n'
                          '  Name: Displays\n', 'Panels: []\n', 1)
    # 임시 폴더는 지우지 않음
    path = os.path.join(tempfile.mkdtemp(prefix='frybot_fleet_rviz_'), 'fleet.rviz')
    with open(path, 'w') as stream:
        stream.write(out)
    return path


def start_poses(arg, map_id):
    """'pinky1:A2,pinky3:W3:90' -> {'pinky1': 'x y yaw', ...}: where each robot stands at start, as a roadmap node
    and an optional heading in degrees (0 = +x of the map). Given to AMCL as the initial pose."""
    import math
    from frybot_control.layout import Graph
    out = {}
    # poses 가 비면 지도를 읽지 않음(아래 루프도 건너뜀)
    graph = Graph(map_id) if arg.strip() else None
    for item in arg.split(','):
        if not item.strip():
            continue
        parts = item.strip().split(':')
        # '로봇:노드[:방향(도)]'. 노드는 이 지도의 로드맵에 있어야 함
        if len(parts) < 2 or parts[1] not in graph.nodes:
            raise ValueError(f'poses: "{item}" must be robot:node[:heading_deg] with a node of the map')
        x, y = graph.nodes[parts[1]]
        yaw = math.radians(float(parts[2])) if len(parts) > 2 else 0.0
        # 'x y yaw'(m, m, rad): robot.launch.py 의 initial_pose 형식
        out[parts[0]] = f'{x:.3f} {y:.3f} {yaw:.3f}'
    return out


# [수정 2026-11-18] T-38: 관제 PC 가 탐색 상대로 삼을 로봇 주소 목록
def static_peers(robot_ids: list, reg: dict) -> str:
    """관제 PC 의 ROS_STATIC_PEERS 값을 만든다.

    Args:
        robot_ids: 이번 런치에 든 로봇 이름.
        reg: load_registry 가 돌려준 등록부.

    Returns:
        터미널에 있던 ROS_STATIC_PEERS 값 뒤에 등록된 로봇의 host 를
        ';' 로 이은 문자열. 없으면 빈 문자열.
    """
    hosts = [str(reg[rid]['host']) for rid in robot_ids if rid in reg]
    old = os.environ.get('ROS_STATIC_PEERS', '')  # 터미널의 기존 값은 앞에 둠
    return ';'.join(([old] if old else []) + hosts)


# [수정 2026-11-18] map_yaml 인자(--map)를 지움(사용자 결정). 다른 yaml 을
# 끼우면 roadmap.json 과 지도 이미지가 어긋남. 필요하면 maps/ 에 새 map_id
# 로 추가
# [수정 2026-11-18] T-38: discovery 인자를 robot_remote 에 넘김
# [수정 2026-11-23] T-57: extra_args(robot.launch.py 인자 '키:=값' 목록)를
# 모든 로봇에 --arg 로 넘김. real.launch 의 ceiling_camera:=false 용
def remote_bringup(robot_ids, map_id='', robots_file='', poses=None,
                   discovery='peers', extra_args=()):
    """One SSH bring-up process per robot. Ctrl-C on the launch stops the robots too."""
    # 로봇마다 robot_remote <rid> 프로세스 하나(robot_remote.up). 등록부에
    # 없는 로봇은 기동하지 않고 손으로 띄우라는 로그만 남김
    reg = registered(robots_file)
    exe = os.path.join(get_package_prefix('frybot_bringup'), 'lib', 'frybot_bringup', 'robot_remote')
    acts = []
    for rid in robot_ids:
        if rid not in reg:
            acts.append(LogInfo(msg=f'{rid} is not in {registry_file(robots_file)}: start it on the robot by hand'))
            continue
        cmd = [exe, rid]
        if map_id:
            cmd += ['--map-id', map_id]
        if robots_file:
            cmd += ['--robots-file', robots_file]
        if poses and rid in poses:  # poses:= 로 준 출발 자세를 AMCL 초기 자세로
            cmd += ['--arg', f'initial_pose:={poses[rid]}']
        cmd += ['--discovery', discovery]
        for arg in extra_args:
            cmd += ['--arg', arg]
        # sigterm_timeout 100초: 종료 신호 뒤 robot_remote 가 로봇 쪽
        # 스택 정지를 재시도(최대 4회, 회당 22초 제한)할 시간을 줌
        acts.append(ExecuteProcess(cmd=cmd, name=f'remote_{rid}', output='screen', emulate_tty=True,
                                   sigterm_timeout='100', sigkill_timeout='20'))
    return acts
