"""막힘 뒤 물러나기(T-63, _blocked_backoff)의 조건·거리·중단.

[수정 2026-11-27] 신규. ROS 실행기 없이 MobileController 를 __new__ 로 만들고,
cmd_vel 을 받으면 오도메트리를 움직이고 스캔을 다시 만드는 가짜 로봇으로
본다. 라이다는 몸 중심 1.7 cm 뒤에 pi 만큼 돌아 붙음(Pinky).
"""
import math
import time
import types

from sensor_msgs.msg import LaserScan

from frybot_mobile import mobile_controller as mcm


class _Log:
    """get_logger() 대역."""

    def __init__(self) -> None:
        self.lines = []

    def warn(self, msg):
        self.lines.append(msg)

    info = error = warn


def _scan(x: float, front_wall: float, rear_wall: float) -> LaserScan:
    """몸 중심 x(오도메트리, +x 를 봄)에서 앞·뒤 벽까지의 스캔."""
    lidar = x - 0.017
    m = LaserScan()
    m.angle_min, m.angle_increment = -math.pi, 2 * math.pi / 360
    ranges = [float('inf')] * 360
    # 라이다가 pi 돌아 붙어 로봇 앞 = 스캔 각 pi(마지막 칸 근처)
    front, rear = front_wall - lidar, lidar - rear_wall
    for i in range(360):
        a = mcm.wrap(m.angle_min + i * m.angle_increment + math.pi)
        if abs(a) < math.radians(5):
            ranges[i] = front / math.cos(a)
        elif abs(mcm.wrap(a - math.pi)) < math.radians(5):
            ranges[i] = rear / math.cos(mcm.wrap(a - math.pi))
    m.ranges = ranges
    return m


class _Robot:
    """cmd_vel 을 받아 오도메트리·스캔을 갱신하는 가짜 로봇."""

    def __init__(self, c, front_wall, rear_wall, on_cmd=None):
        self.c, self.fw, self.rw, self.msgs = c, front_wall, rear_wall, []
        self.on_cmd = on_cmd
        self.refresh()

    def refresh(self):
        self.c.last_scan = _scan(self.c.odom[0], self.fw, self.rw)
        self.c.last_scan_t = time.time()

    def publish(self, m):
        self.msgs.append(m)
        x, y, th = self.c.odom
        self.c.odom = (x + m.linear.x * 0.05, y, th)
        self.refresh()
        if self.on_cmd:
            self.on_cmd(len(self.msgs))


def _ctrl(front_wall=0.09, rear_wall=-1.0, dist=0.05, on_cmd=None):
    """물러나기에 필요한 것만 채운 MobileController(몸 중심 x=0, +x)."""
    c = mcm.MobileController.__new__(mcm.MobileController)
    log = _Log()
    c.get_logger = lambda: log
    c.rid, c.odom, c.estop, c.nav_state = 'pinky2', (0.0, 0.0, 0.0), False, ''
    c.lidar_yaw, c.front_half_w = math.pi, 0.065
    c.rear_stop, c.front_stop = 0.10, 0.10
    c.speed, c.guide_speed = 0.08, 0.05
    c.backoff_dist, c.backoff_trigger, c.backoff_timeout = dist, 0.20, 4.0
    c._fms_alive = lambda: True
    c._loc_lost = lambda: False
    gh = types.SimpleNamespace(is_cancel_requested=False)
    c.cur = gh
    c.pub_cmd = _Robot(c, front_wall, rear_wall, on_cmd)
    return c, gh, log


def test_backs_off_when_blocked_ahead():
    """앞 9 cm(R2.5 실측)에 막히면 뒤로 5 cm 물러나고 0 속도로 끝냄."""
    c, gh, log = _ctrl(front_wall=0.09)
    assert c._blocked_backoff(False, gh) == 'done'
    assert 0.05 <= -c.odom[0] < 0.06
    assert c.pub_cmd.msgs[-1].linear.x == 0.0
    assert all(m.linear.x <= 0 for m in c.pub_cmd.msgs)
    assert 'moved 5' in log.lines[-1] and 'backwards' in log.lines[-1]


def test_no_backoff_when_clear():
    """진행 방향 띠가 문턱(20 cm) 밖이면 움직이지 않음."""
    c, gh, _ = _ctrl(front_wall=0.30)
    assert c._blocked_backoff(False, gh) == 'clear'
    assert c.odom[0] == 0.0 and c.pub_cmd.msgs == []


def test_stops_short_when_rear_blocked():
    """뒤가 rear_stop_dist(라이다 기준 10 cm) 안이 되면 덜 가고 섬."""
    # 뒤 벽: 라이다에서 12 cm -> 2 cm 남짓 물러나면 10 cm 안
    c, gh, _ = _ctrl(front_wall=0.09, rear_wall=-0.137)
    assert c._blocked_backoff(False, gh) == 'blocked'
    assert 0.0 < -c.odom[0] < 0.04
    assert c.pub_cmd.msgs[-1].linear.x == 0.0


def test_off_when_dist_not_positive():
    """blocked_backoff_dist 가 0 이하면 끔."""
    c, gh, _ = _ctrl(front_wall=0.09, dist=0.0)
    assert c._blocked_backoff(False, gh) == 'off'
    assert c.pub_cmd.msgs == []


def test_estop_during_backoff():
    """물러나는 도중 비상 정지가 오면 바로 0 속도로 멈춤."""
    holder = {}

    def on_cmd(n):
        if n == 3:
            holder['c'].estop = True
    c, gh, _ = _ctrl(front_wall=0.09, on_cmd=on_cmd)
    holder['c'] = c
    assert c._blocked_backoff(False, gh) == 'estop'
    assert -c.odom[0] < 0.05
    assert c.pub_cmd.msgs[-1].linear.x == 0.0


def test_reverse_segment_backs_off_forwards():
    """후진 구간이 뒤에서 막혔으면 앞으로 물러남."""
    c, gh, log = _ctrl(front_wall=1.0, rear_wall=-0.09)
    assert c._blocked_backoff(True, gh) == 'done'
    assert 0.05 <= c.odom[0] < 0.06
    assert 'forwards' in log.lines[-1]


def test_no_scan_skips():
    """새 스캔이 없으면 물러나지 않음."""
    c, gh, _ = _ctrl(front_wall=0.09)
    c.last_scan_t = time.time() - 5.0
    assert c._blocked_backoff(False, gh) == 'no_scan'
    assert c.pub_cmd.msgs == []
