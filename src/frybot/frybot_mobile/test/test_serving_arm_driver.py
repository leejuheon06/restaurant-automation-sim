"""서빙 팔 구동부의 주행용 접은 자세(rest)·그리퍼 동작 시험(가짜 MyCobot).

실물 팔과 ROS 액션 서버 없이 ServingArmDriver 의 _run 을 직접 부른다.
pymycobot 이 없는 PC 에서도 돌도록 가짜 모듈을 먼저 넣는다.
"""
# [수정 2026-11-20] 신규: rest 자세·rest_gripper(작업 지시 서빙 팔 rest)
# [수정 2026-11-20] rest J5 74 → 0, 속도 10 → 70 에 맞춤(작업 지시 수정)
# [수정 2026-11-20] 속도 70 → 60 에 맞춤(작업 지시 수정 2)
import sys
import threading
import types

import pytest
import rclpy

# pymycobot 이 없으면 가짜 모듈(구동부 import 만 통과시킴)
if 'pymycobot.mycobot280' not in sys.modules:
    _pkg = types.ModuleType('pymycobot')
    _mod = types.ModuleType('pymycobot.mycobot280')
    _mod.MyCobot280 = object
    sys.modules.setdefault('pymycobot', _pkg)
    sys.modules['pymycobot.mycobot280'] = _mod

from frybot_mobile import serving_arm_driver as sad  # noqa: E402

REST = [0.0, 122.0, -148.0, 143.0, 0.0, 60.0]


class FakeArm:
    """send_angles 를 받으면 바로 그 자세에 닿는 가짜 MyCobot280."""

    def __init__(self) -> None:
        self.q = [0.0] * 6
        self.calls = []          # (명령, 값) 순서 기록

    def get_angles(self) -> list[float]:
        return list(self.q)

    def send_angles(self, q: list[float], speed: int) -> None:
        self.calls.append(('angles', list(q), speed))
        self.q = list(q)

    def set_gripper_value(self, value: int, speed: int) -> None:
        self.calls.append(('gripper', value, speed))

    def power_on(self) -> None:
        self.calls.append(('power_on',))

    def stop(self) -> None:
        self.calls.append(('stop',))


class FakeGoal:
    """액션 목표 핸들 대역: 취소 여부와 진행률만."""

    def __init__(self, cancel: bool = False) -> None:
        self.is_cancel_requested = cancel
        self.feedback = []

    def publish_feedback(self, fb) -> None:
        self.feedback.append(fb.progress)


def _write(tmp_path, text: str) -> str:
    p = tmp_path / 'serving_arm.yaml'
    p.write_text(text, encoding='utf-8')
    return str(p)


YAML = """rest: [0, 122, -148, 143, 0, 60]
rest_gripper: 0
jobs:
  LOAD: [[30, 0, 0, 0, 0, 0], [-30, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0]]
  EMPTY: []
"""


@pytest.fixture(scope='module', autouse=True)
def _ros():
    rclpy.init()              # _move 가 rclpy.ok() 를 봄
    yield
    rclpy.shutdown()


def _driver(path: str) -> 'sad.ServingArmDriver':
    """__init__(노드·직렬 포트) 없이 _run 에 필요한 것만 채운 구동부."""
    d = sad.ServingArmDriver.__new__(sad.ServingArmDriver)
    d.rest, d.rest_gripper, d.jobs = sad.load_poses(path)
    # [수정 2026-11-26] 서빙 팔 자세 연동: 0도 home 자세(HOME, 작업 시작 전)
    d.home = sad.load_home(path)
    d.mc = FakeArm()
    d.lock = threading.Lock()
    d.speed, d.tol, d.move_timeout = 60, 3.0, 2.0
    d.q_deg, d.q_t = None, 0.0
    return d


def _moves(d) -> list:
    return [c for c in d.mc.calls if c[0] in ('angles', 'gripper')]


def test_installed_yaml_rest_pose():
    """설치 파일의 rest 는 실물에서 정한 접은 자세, 그리퍼 0."""
    import os
    here = os.path.dirname(__file__)
    rest, grip, _ = sad.load_poses(
        os.path.join(here, '..', 'config', 'serving_arm.yaml'))
    assert rest == REST
    assert grip == 0


def test_home_goes_rest_gripper_first(tmp_path):
    """REST: 그리퍼 0 을 먼저, 그다음 rest 관절 이동, 속도 60.

    [수정 2026-11-26] 작업 이름 통일: 예전 HOME(rest 로 감)은 REST.
    """
    d = _driver(_write(tmp_path, YAML))
    assert d._run(FakeGoal(), 'REST') == 'OK'
    assert _moves(d) == [('gripper', 0, 60), ('angles', REST, 60)]


def test_load_ends_at_rest(tmp_path):
    """LOAD: 경유 자세 3개 뒤 rest 를 덧붙여 rest 로 끝남."""
    d = _driver(_write(tmp_path, YAML))
    gh = FakeGoal()
    assert d._run(gh, 'LOAD') == 'OK'
    m = _moves(d)
    assert [c[1] for c in m if c[0] == 'angles'] == [
        [30.0, 0, 0, 0, 0, 0], [-30.0, 0, 0, 0, 0, 0], [0.0] * 6, REST]
    # 그리퍼는 rest 직전에 한 번
    assert m[-2:] == [('gripper', 0, 60), ('angles', REST, 60)]
    assert gh.feedback[-1] == 1.0
    assert d.mc.q == REST


def test_cancel_does_not_go_rest(tmp_path):
    """취소: 그 자리에 세우고(stop) rest·그리퍼 명령은 없음."""
    d = _driver(_write(tmp_path, YAML))
    assert d._run(FakeGoal(cancel=True), 'LOAD') == 'CANCELED'
    assert ('stop',) in d.mc.calls
    assert not any(c[0] == 'gripper' for c in d.mc.calls)
    assert all(c[1] != REST for c in d.mc.calls if c[0] == 'angles')


def test_timeout_does_not_go_rest(tmp_path):
    """시간 초과: 팔이 움직이지 않으면 ARM_TIMEOUT, rest 로 가지 않음."""
    d = _driver(_write(tmp_path, YAML))
    d.move_timeout = 0.3
    d.mc.send_angles = lambda q, s: d.mc.calls.append(('angles', list(q), s))
    assert d._run(FakeGoal(), 'LOAD') == 'ARM_TIMEOUT'
    assert ('stop',) in d.mc.calls
    assert all(c[1] != REST for c in d.mc.calls if c[0] == 'angles')


def test_no_rest_gripper_key(tmp_path):
    """rest_gripper 키가 없으면 그리퍼 명령을 보내지 않음(예전 동작)."""
    text = YAML.replace('rest_gripper: 0\n', '')
    d = _driver(_write(tmp_path, text))
    assert d.rest_gripper is None
    # [수정 2026-11-26] 작업 이름 통일: rest 로 가는 작업은 REST
    assert d._run(FakeGoal(), 'REST') == 'OK'
    assert not any(c[0] == 'gripper' for c in d.mc.calls)


def test_empty_job_no_pose(tmp_path):
    """자세가 빈 작업은 예전처럼 NO_POSE(rest 를 덧붙이지 않음)."""
    d = _driver(_write(tmp_path, YAML))
    assert d._run(FakeGoal(), 'EMPTY') == 'NO_POSE'
    assert d.mc.calls == []


@pytest.mark.parametrize('bad', [
    'rest: [0, 122, -151, 143, 0, 60]\n',          # J3 한계 밖
    'rest: [0, 122, -148, 143, 0, 60]\nrest_gripper: 101\n',
    'rest: [0, 122, -148, 143, 0, 60]\nrest_gripper: -1\n',
    'rest: [0, 122, -148, 143, 0, 60]\nrest_gripper: true\n',
    'rest: [0, 122, -148, 143, 0, 60]\nrest_gripper: 0.5\n',
])
def test_out_of_range_raises(tmp_path, bad):
    """관절 한계 밖 자세, 0~100 정수가 아닌 그리퍼 값은 ValueError."""
    with pytest.raises(ValueError):
        sad.load_poses(_write(tmp_path, bad))


# [수정 2026-11-26] 서빙 팔 자세 연동: HOME(0도), home 에서 시작, 이미 그 자세면
# 건너뜀. 작업 이름 통일(HOME = 0도 home, REST = rest)
def test_installed_yaml_home_pose():
    """설치 파일의 home 은 0도 자세."""
    import os
    here = os.path.dirname(__file__)
    assert sad.load_home(os.path.join(here, '..', 'config',
                                      'serving_arm.yaml')) == [0.0] * 6


def test_load_from_rest_goes_home_first(tmp_path):
    """rest 에서 LOAD: 0도 -> 30 -> -30 -> 0 -> rest(그리퍼는 rest 직전)."""
    d = _driver(_write(tmp_path, YAML))
    d.mc.q = list(REST)
    assert d._run(FakeGoal(), 'LOAD') == 'OK'
    assert [c[1] for c in _moves(d) if c[0] == 'angles'] == [
        [0.0] * 6, [30.0, 0, 0, 0, 0, 0], [-30.0, 0, 0, 0, 0, 0],
        [0.0] * 6, REST]
    assert d.mc.q == REST


def test_home_job(tmp_path):
    """HOME: rest 에서 0도 home 자세 하나, 그리퍼 명령 없음."""
    d = _driver(_write(tmp_path, YAML))
    d.mc.q = list(REST)
    assert d._run(FakeGoal(), 'HOME') == 'OK'
    assert _moves(d) == [('angles', [0.0] * 6, 60)]


def test_already_there_sends_nothing(tmp_path):
    """이미 rest 면 REST 는, 이미 0도면 HOME 은 명령 없이 OK."""
    d = _driver(_write(tmp_path, YAML))
    d.mc.q = list(REST)
    assert d._run(FakeGoal(), 'REST') == 'OK'
    d.mc.q = [0.0] * 6
    assert d._run(FakeGoal(), 'HOME') == 'OK'
    assert _moves(d) == []


def test_cancel_from_rest_stops_in_place(tmp_path):
    """rest 에서 시작한 작업을 취소: 그 자리에 세우고 rest 로 가지 않음."""
    d = _driver(_write(tmp_path, YAML))
    d.mc.q = list(REST)
    assert d._run(FakeGoal(cancel=True), 'LOAD') == 'CANCELED'
    assert ('stop',) in d.mc.calls
    assert [c[1] for c in _moves(d) if c[0] == 'angles'] == [[0.0] * 6]


@pytest.mark.parametrize('bad', ['home: [0, 0, 0]\n',
                                 'home: [0, 0, 151, 0, 0, 0]\n'])
def test_bad_home_rejected(tmp_path, bad):
    """home 이 6개가 아니거나 한계 밖이면 ValueError."""
    with pytest.raises(ValueError):
        sad.load_home(_write(tmp_path, YAML + bad))
