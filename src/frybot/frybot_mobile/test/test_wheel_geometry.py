"""pinky_driver 의 바퀴 치수가 속도 명령 -> RPM 과 오도메트리에 함께 쓰이는지.

[수정 2026-11-24] 신규 (MT-4): 로봇별 wheel_radius·wheel_separation. MT-3
바닥 실측(runs/20261124_03_motor_floor_3robots)의 라이다 대 엔코더 비율을
보정값이 재현하는지 숫자로 확인한다. 하드웨어·ROS 실행기 없이 Pinky 를
직접 만들고 모터 읽기·쓰기를 대역으로 바꾼다.
"""
import importlib
import math
import sys
import types

import pytest
from rclpy.time import Time

# PC 의 tf_transformations 는 NumPy 2 에서 import 가 실패함(발행은 대역)
sys.modules.setdefault('tf_transformations', types.SimpleNamespace(
    quaternion_from_euler=lambda *a: (0.0, 0.0, 0.0, 1.0)))
pinky_driver = importlib.import_module('frybot_mobile.pinky_driver')

NOMINAL = (0.027, 0.0961)
# MT-4 에 넣는 값(반지름과 간격을 함께 보정한 조합)
CALIB = {'pinky1': (0.02706, 0.0953), 'pinky2': (0.02685, 0.0960),
         'pinky3': (0.02763, 0.0992)}
# MT-3 실측: 라이다 ÷ 엔코더(명목값) 직진 거리, 회전각
MEASURED = {'pinky1': (1.0022, 1.0104), 'pinky2': (0.9945, 0.9951),
            'pinky3': (1.0235, 0.9916)}


class _Motor:
    """DynamixelDriver 대역: 엔코더 값을 주고 보낸 RPM 을 모음."""

    def __init__(self) -> None:
        self.enc = (0, 0)
        self.sent = []

    def get_feedback(self):
        return 0.0, 0.0, self.enc[0], self.enc[1]

    def set_double_rpm(self, rpm_l, rpm_r):
        self.sent.append((rpm_l, rpm_r))
        return True


class _Clock:
    """get_clock() 대역: now() 를 정해 둔 시각으로."""

    def __init__(self) -> None:
        self.t = Time(nanoseconds=0)

    def now(self):
        return self.t


def _driver(radius: float, separation: float):
    """__init__ 없이 계산에 필요한 값만 채운 Pinky."""
    p = pinky_driver.Pinky.__new__(pinky_driver.Pinky)
    p.wheel_radius, p.wheel_separation = radius, separation
    p.circumference = 2 * math.pi * radius
    p.driver = _Motor()
    p.last_encoder_l = p.last_encoder_r = 0
    p.x = p.y = p.theta = 0.0
    p.clock = _Clock()
    p.get_clock = lambda: p.clock
    p.last_time = p.clock.now()
    p._watch_cmd_vel = lambda: None
    p._publish_tf = lambda *a: None
    p._publish_odometry = lambda *a: None
    p._publish_joint_states = lambda *a: None
    # [수정 2026-11-25] MT-7: 노드 기본값(0.3)과 같게(이 시험은 감시를 끔)
    p.cmd_timeout = pinky_driver.CMD_VEL_TIMEOUT_DEFAULT
    p._stop_pending = p._zero_failed = False
    return p


def _move(p, pulses_l: int, pulses_r: int) -> None:
    """엔코더를 바꾸고 오도메트리를 한 번 갱신(오른쪽은 모터 기준 부호)."""
    p.driver.enc = (pulses_l, pulses_r)
    p.clock.t = Time(nanoseconds=100_000_000)
    p.update_and_publish()


def test_straight_distance_scales_with_radius():
    """같은 펄스에서 직진 거리 비 = 반지름 비 = MT-3 실측 비율."""
    for rid, (r, b) in CALIB.items():
        nom, cal = _driver(*NOMINAL), _driver(r, b)
        for p in (nom, cal):
            _move(p, 4096 * 2, -4096 * 2)  # 두 바퀴 2 바퀴 전진
        assert nom.x == pytest.approx(2 * 2 * math.pi * 0.027)
        ratio = cal.x / nom.x
        assert ratio == pytest.approx(MEASURED[rid][0], abs=0.0005), rid


def test_turn_angle_matches_floor_ratio():
    """같은 펄스에서 회전각 비 = (r/r0)/(b/b0) = MT-3 실측 비율(±0.1%)."""
    for rid, (r, b) in CALIB.items():
        nom, cal = _driver(*NOMINAL), _driver(r, b)
        for p in (nom, cal):
            _move(p, -1000, -1000)  # 좌 뒤, 우 앞: 제자리 좌회전
        assert nom.theta > 0
        ratio = cal.theta / nom.theta
        assert ratio == pytest.approx(MEASURED[rid][1], abs=0.001), rid


def test_nominal_is_unchanged():
    """명목값이면 예전 식 그대로(반지름 0.027, 간격 0.0961)."""
    p = _driver(*NOMINAL)
    _move(p, 4096, 4096)  # 좌 1 바퀴 전진, 우 1 바퀴 후진: 우회전
    arc = 2 * math.pi * 0.027
    assert p.theta == pytest.approx(-2 * arc / 0.0961)
    assert p.x == pytest.approx(0.0, abs=1e-12)


@pytest.mark.parametrize('rid', sorted(CALIB))
def test_cmd_vel_and_odom_use_same_geometry(rid):
    """속도 명령 -> RPM -> 그 RPM 으로 1 초 돈 엔코더 -> 오도메트리 = 명령."""
    r, b = CALIB[rid]
    p = _driver(r, b)
    msg = pinky_driver.Twist()
    msg.linear.x, msg.angular.z = 0.08, 0.5
    p.twist_callback(msg)
    rpm_l, rpm_r = p.driver.sent[-1]
    # 1 초 동안 그 RPM 으로 돈 펄스(모터 기준 부호 그대로)
    pulses = [round(rpm / 60.0 * 4096) for rpm in (rpm_l, rpm_r)]
    _move(p, *pulses)
    assert p.theta == pytest.approx(0.5, rel=2e-3)
    dist = math.hypot(p.x, p.y)
    assert dist == pytest.approx(0.08, rel=2e-3)
