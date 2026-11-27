"""후진 도킹(모든 도크 후진, 2026-11-26 사용자 결정 방안 다)의 접근·뒤 라이다.

[수정 2026-11-26] 신규. ROS 실행기·도킹 서버 없이 MobileController 를 __new__ 로
만들어 _dock_segment 의 앞부분(start 판정, docking 단계의 라이다 정지)과
_rear_clear, navigator 의 dock_backwards 덮어쓰기를 본다.
"""
import math
import time
import types

from builtin_interfaces.msg import Time

from frybot_control.map_catalog import dock_backwards
from frybot_control.map_catalog import profile
from frybot_mobile import mobile_controller as mcm
from frybot_mobile import navigator


class _Log:
    """get_logger() 대역."""

    def __init__(self) -> None:
        self.lines = []

    def warn(self, msg):
        self.lines.append(msg)

    info = error = warn


class _Pub:
    """publish 를 모으는 발행기 대역."""

    def __init__(self) -> None:
        self.msgs = []

    def publish(self, m):
        self.msgs.append(m)


class _Handle:
    """도킹 목표 핸들 대역."""

    def __init__(self) -> None:
        self.canceled = False

    def cancel_goal_async(self):
        self.canceled = True


# test_map_v06 의 D1_STOP(조리대): D1_IN(0.124, 0.2015) 에서 왼쪽으로 11 cm,
# 도킹한 로봇은 오른쪽(+x, yaw 0)을 봄 -> 뒤로 들어감
DOCK = {'name': 'D1_STOP', 'x': 0.014, 'y': 0.2015, 'yaw': 0.0,
        'kind': 'pose'}
PREV = types.SimpleNamespace(x=0.124, y=0.2015)


def _ctrl(backwards: bool):
    """도킹 판정에 필요한 것만 채운 MobileController(로봇은 D1_IN, +x)."""
    c = mcm.MobileController.__new__(mcm.MobileController)
    log = _Log()
    c.get_logger = lambda: log
    c.rid, c.drive, c.measured_map, c.use_docking = 'pinky1', 'nav2', True, True
    c.dock_backwards = backwards
    c.x, c.y, c.yaw = 0.124, 0.2015, 0.0
    c.dk = dict(key=None, stage='', state='', handle=None, marker=-1)
    c.det, c.nav_state = None, ''
    c.pub_cmd, c.pub_dock_target = _Pub(), _Pub()
    c.sent = []                     # 도킹 서버로 보낸 목표

    def send(goal):
        c.sent.append(goal)
        return types.SimpleNamespace(add_done_callback=lambda cb: None)
    c.dock_cli = types.SimpleNamespace(server_is_ready=lambda: True,
                                       send_goal_async=send)
    c.get_clock = lambda: types.SimpleNamespace(
        now=lambda: types.SimpleNamespace(to_msg=Time))
    c._nav2_segment = lambda *a, **k: False
    c.front_stop, c.front, c.front_t = 0.10, None, 0.0
    c.front_wanted, c.front_since = 0.0, 0.0
    c.rear_stop, c.rear, c.rear_t = 0.10, None, 0.0
    c.rear_wanted, c.rear_since = 0.0, 0.0
    c.trim_timeout, c.yaw_tol, c.trim_w = 6.0, 0.012, 0.15
    return c, log


def test_backward_dock_starts_server_from_the_node_in_front():
    """후진: D1_IN(+x 를 봄)에서 D1_STOP 은 등 뒤 11 cm -> 도킹 서버 단계."""
    c, _ = _ctrl(backwards=True)
    assert c._dock_segment((1, 1), DOCK, True, 0.05, PREV) is False
    assert c.dk['stage'] == 'docking' and len(c.sent) == 1
    g = c.sent[0]
    # 도크 자세는 지도 좌표
    assert abs(g.dock_pose.pose.position.x - 0.014) < 1e-9
    # [수정 2026-11-27] T-64: 방향은 도킹 서버 규약(진행 방향 = 도킹한 로봇
    # 방향 + 180도). 전에는 도킹한 로봇 방향(yaw 0, z 0)을 기대했음
    assert abs(abs(g.dock_pose.pose.orientation.z) - 1.0) < 1e-9


def test_forward_dock_same_place_is_not_approachable():
    """같은 자리에서 전진 기준이면 도크가 뒤쪽이라(along < 0) 서버를 안 씀."""
    c, _ = _ctrl(backwards=False)
    c._dock_segment((1, 1), DOCK, False, 0.05, PREV)
    assert c.dk['stage'] in ('align', 'drive')


def _docking(c):
    """docking 단계(도킹 서버 주행 중)로 맞춤."""
    c._dock_segment((1, 1), DOCK, True, 0.05, PREV)
    h = _Handle()
    c.dk.update(stage='docking', state='ACTIVE', handle=h)
    return h


def test_backward_docking_stops_on_rear_lidar():
    """후진 도킹 중 뒤 라이다가 rear_stop_dist 안이면 취소하고 그 자리 도착."""
    c, log = _ctrl(backwards=True)
    h = _docking(c)
    c.x = 0.05                      # 도크까지 3.6 cm 남음
    c.rear_since = time.time() - 2.0
    c.rear_wanted = time.time() + 2.0
    c.rear, c.rear_t = 0.08, time.time()
    c._dock_segment((1, 1), DOCK, True, 0.05, PREV)
    assert h.canceled
    assert c.dk['stage'] == 'trim' and c.dk['front_stop']
    assert any('rear lidar' in s for s in log.lines)


def test_backward_docking_ignores_front_lidar():
    """후진 도킹은 앞 라이다(앞이 가까워도)로 서지 않음."""
    c, _ = _ctrl(backwards=True)
    h = _docking(c)
    c.x = 0.05
    c.rear_since = time.time() - 2.0
    c.rear_wanted = time.time() + 2.0
    c.rear, c.rear_t = 0.30, time.time()
    c.front, c.front_t = 0.05, time.time()
    c._dock_segment((1, 1), DOCK, True, 0.05, PREV)
    assert not h.canceled and c.dk['stage'] == 'docking'


def test_backward_docking_ends_level_with_dock_pose():
    """다가가는 방향(로봇 방향의 반대) 기준으로 도크 자세와 나란해지면 끝냄."""
    c, _ = _ctrl(backwards=True)
    h = _docking(c)
    c.x = 0.016                     # 도크 자세를 2 mm 앞둠(<= 6 mm)
    c.rear_since = time.time() - 2.0
    c.rear_wanted = time.time() + 2.0
    c.rear, c.rear_t = 0.30, time.time()
    c._dock_segment((1, 1), DOCK, True, 0.05, PREV)
    assert h.canceled and c.dk['stage'] == 'trim'
    assert not c.dk['front_stop']


def test_forward_docking_still_uses_front_lidar():
    """전진 도킹(가상 매장)은 예전처럼 앞 라이다로 섬."""
    c, log = _ctrl(backwards=False)
    c.yaw = math.pi                 # 왼쪽(도크 쪽)을 봄
    dock = dict(DOCK, yaw=math.pi)
    c._dock_segment((1, 1), dock, False, 0.05, PREV)
    assert c.dk['stage'] == 'docking'
    h = _Handle()
    c.dk.update(stage='docking', state='ACTIVE', handle=h)
    c.x = 0.05
    c.front_since = time.time() - 2.0
    c.front_wanted = time.time() + 2.0
    c.front, c.front_t = 0.08, time.time()
    c._dock_segment((1, 1), dock, False, 0.05, PREV)
    assert h.canceled and any('front lidar' in s for s in log.lines)


def test_rear_clear_states():
    """_rear_clear: 새 스캔 전 None, 막히면 False, 트이면 True, 0 이면 끔."""
    c, _ = _ctrl(backwards=True)
    assert c._rear_clear() is None          # 방금 켬
    c.rear, c.rear_t = 0.05, time.time()
    assert c._rear_clear() is False
    c.rear = 0.2
    assert c._rear_clear() is True
    c.rear_stop = 0.0
    assert c._rear_clear() is True


def test_navigator_sets_dock_backwards_on_measured_map_only():
    """실측 지도의 docking_server 만 dock_backwards true 로 덮어씀."""
    def dock_params(measured, map_id=''):
        nodes = navigator.navigator_nodes('pinky1', False, measured=measured,
                                          map_id=map_id)
        for n in nodes:
            if getattr(n, '_Node__node_name', None) == 'docking_server':
                return n._Node__parameters
        return None
    measured = dock_params(True, 'test_map_v06')
    proto = dock_params(False)
    assert measured is not None and proto is not None
    def overrides(params):
        # launch_ros 가 dict 키를 TextSubstitution 묶음으로 바꿔 둠
        return {''.join(s.text for s in k): v for p in params
                if isinstance(p, dict) for k, v in p.items()}
    assert overrides(measured).get('dock_backwards') is True
    assert 'dock_backwards' not in overrides(proto)


# [수정 2026-11-26] 2단계 보완: 지도 단위 "dock_backwards"
def test_map_dock_backwards_key():
    """v04·v05 는 false(전진), v06 은 true(후진), 가상 매장은 false."""
    assert dock_backwards('test_map_v04') is False
    assert dock_backwards('test_map_v05') is False
    assert dock_backwards('test_map_v06') is True
    assert dock_backwards('proto') is False
    assert dock_backwards('') is False


def test_v05_forward_dock_goes_to_server_and_v06_backward():
    """지도 값으로: v05 D1_STOP(yaw 90)은 전진 서버 단계, v06 은 후진."""
    for mid, n in (('test_map_v05', 'D1_STOP'), ('test_map_v06', 'D1_STOP')):
        p = profile(mid)
        back = dock_backwards(mid)
        d = {'name': n, 'x': p['nodes'][n][0], 'y': p['nodes'][n][1],
             'yaw': math.radians(p['docks'][n]['yaw_deg']), 'kind': 'pose'}
        din = p['nodes']['D1_IN']
        c, _ = _ctrl(backwards=back)
        c.x, c.y, c.yaw = din[0], din[1], d['yaw']
        prev = types.SimpleNamespace(x=din[0], y=din[1])
        c._dock_segment((1, 1), d, back, 0.05, prev)
        assert c.dk['stage'] == 'docking', mid
        assert len(c.sent) == 1


def test_navigator_override_follows_map_key():
    """v05 는 덮어쓰지 않고(전진), v06 은 dock_backwards true."""
    def over(map_id):
        for n in navigator.navigator_nodes('pinky1', False, measured=True,
                                           map_id=map_id):
            if getattr(n, '_Node__node_name', None) == 'docking_server':
                return {''.join(s.text for s in k): v
                        for p in n._Node__parameters
                        if isinstance(p, dict) for k, v in p.items()}
        return None
    assert 'dock_backwards' not in over('test_map_v05')
    assert over('test_map_v06').get('dock_backwards') is True


# [수정 2026-11-27] T-64: 도킹 서버에 넘기는 도크 자세의 방향
def _goal_yaw(goal) -> float:
    """DockRobot 목표의 도크 자세 yaw(rad)."""
    q = goal.dock_pose.pose.orientation
    return math.atan2(2 * q.w * q.z, 1 - 2 * q.z * q.z)


def test_backward_dock_goal_yaw_is_travel_direction():
    """후진 D1_STOP(도킹한 로봇 방향 0도): 서버에 진행 방향 180도로 넘김.

    서버(opennav_docking 1.3.13)는 목표를 도크 자세 방향으로 0.25 m 밀므로,
    0도로 넘기면 목표가 도크 앞(로봇 쪽)이 되어 도크 반대로 후진했음.
    """
    c, _ = _ctrl(backwards=True)
    c._dock_segment((1, 1), DOCK, True, 0.05, PREV)
    assert c.dk['stage'] == 'docking' and len(c.sent) == 1
    yaw = _goal_yaw(c.sent[0])
    assert abs(abs(yaw) - math.pi) < 1e-6
    # 서버가 미는 목표(도크 + 0.25 m x 방향)가 도크 너머(벽 쪽, -x)
    assert DOCK['x'] + 0.25 * math.cos(yaw) < DOCK['x']


def test_backward_dock_goal_yaw_h2():
    """후진 H2(도킹한 로봇 방향 180도, C3 에서 -x 를 보고 출발): 0도로 넘김."""
    c, _ = _ctrl(backwards=True)
    c.x, c.y, c.yaw = 1.474, 0.2015, math.pi
    h2 = {'name': 'H2', 'x': 1.681, 'y': 0.2015, 'yaw': math.pi,
          'kind': 'pose'}
    prev = types.SimpleNamespace(x=1.474, y=0.2015)
    c._dock_segment((1, 1), h2, True, 0.05, prev)
    assert c.dk['stage'] == 'docking' and len(c.sent) == 1
    yaw = _goal_yaw(c.sent[0])
    assert abs(yaw) < 1e-6
    assert h2['x'] + 0.25 * math.cos(yaw) > h2['x']   # 도크 너머(벽 쪽, +x)


def test_forward_dock_goal_yaw_unchanged():
    """전진 도킹(가상 매장·v04·v05)은 도크 자세 방향을 그대로 넘김."""
    c, _ = _ctrl(backwards=False)
    c.yaw = math.pi
    dock = dict(DOCK, yaw=math.pi)
    c._dock_segment((1, 1), dock, False, 0.05, PREV)
    assert c.dk['stage'] == 'docking' and len(c.sent) == 1
    assert abs(abs(_goal_yaw(c.sent[0])) - math.pi) < 1e-6
