"""mobile_controller 의 서빙 팔 자세 연동(출발 전 접기, 홈 도착 뒤 펴기).

[수정 2026-11-26] 신규: 서빙 팔 자세 연동
(docs/2026-11-26_SERVING_ARM_POSE_LINK_PLAN.md 5장 2번). ROS 실행기와 실물 팔
구동부 없이 MobileController 를 __new__ 로 만들고 팔 액션 클라이언트를
가짜로 바꿔 _arm_call, _navigate 의 접기, _arm_home_later, _arm_forward 의
자세 추적을 본다. 작업 이름은 HOME = 0도 home 자세, REST = 주행용 접은 자세.
"""
import threading
import time
import types

import pytest
import rclpy

from frybot_mobile import mobile_controller as mcm


@pytest.fixture(scope='module', autouse=True)
def _ros():
    """_navigate 의 루프가 rclpy.ok() 를 봄."""
    rclpy.init()
    yield
    rclpy.shutdown()


class _Log:
    """get_logger() 대역."""

    def __init__(self) -> None:
        self.lines = []

    def warn(self, msg):
        self.lines.append(msg)

    info = error = warn


class _Done:
    """이미 끝난 future 대역."""

    def __init__(self, value) -> None:
        self.value = value

    def done(self):
        return True

    def result(self):
        return self.value


class FakeArmClient:
    """serving_arm/arm_job 액션 클라이언트 대역: 받은 작업 이름을 모은다."""

    def __init__(self, online=True, reason='OK', on_send=None) -> None:
        self.online, self.reason, self.on_send = online, reason, on_send
        self.jobs = []

    def wait_for_server(self, timeout_sec=0.0):
        return self.online

    def server_is_ready(self):
        return self.online

    def send_goal_async(self, goal):
        self.jobs.append(goal.job)
        if self.on_send:
            self.on_send(goal.job)
        res = types.SimpleNamespace(success=self.reason == 'OK',
                                    reason=self.reason)
        child = types.SimpleNamespace(
            accepted=True,
            get_result_async=lambda: _Done(types.SimpleNamespace(
                result=res, status=4)),
            cancel_goal_async=lambda: None)
        return _Done(child)


def _ctrl(arm, pose='REST'):
    """경로 실행과 팔 연동에 필요한 것만 채운 MobileController."""
    c = mcm.MobileController.__new__(mcm.MobileController)
    log = _Log()
    c.get_logger = lambda: log
    c.rid, c.home_node = 'pinky1', 'H1'
    c.arm_cli, c.arm_pose, c.arm_state = arm, pose, 'IDLE'
    c.arm_lock, c.arm_preempt = threading.Lock(), False
    c.arm_wait, c.arm_home_delay = 0.5, 0.05
    c.estop, c.void, c.cur = False, None, None
    c.drive = 'kinematic'
    c.grants, c.pv, c.task_id = {}, 0, ''
    c.x, c.y = 0.0, 0.0
    c.dead_ends, c.dead_end_settle = set(), 0.05
    c.reached, c.node_id, c.nav_state = -1, '', 'IDLE'
    c.guide_goal, c.track_warned = None, False
    c._fb = lambda *a, **k: None
    c._loc_lost = lambda: False
    c._fms_alive = lambda: True
    c._on_lane = lambda a, b: False
    return c, log


class FakeRouteGoal:
    """NavigateRoute 목표 핸들 대역(두 노드 경로)."""

    def __init__(self) -> None:
        def wp(n, x):
            return types.SimpleNamespace(node_id=n, x=x, y=0.0)
        self.request = types.SimpleNamespace(
            route=[wp('B5', 0.0), wp('B4', 0.4)], plan_version=7,
            mode='NORMAL', task_id='M0001', visit_id=0)
        self.is_cancel_requested = False
        self.ended = ''

    def canceled(self):
        self.ended = 'canceled'

    def abort(self):
        self.ended = 'abort'

    def succeed(self):
        self.ended = 'succeed'


def _stop_counter(c, gh, cancel_at):
    """_stop 대역: cancel_at 번째 부름에서 경로를 취소(루프를 끝내려고)."""
    n = {'k': 0}

    def stop():
        n['k'] += 1
        if n['k'] >= cancel_at:
            gh.is_cancel_requested = True
    c._stop = stop
    return n


def test_arm_call_home_ok_sets_rest():
    """REST 성공: 'OK', arm_pose REST."""
    arm = FakeArmClient()
    c, _ = _ctrl(arm, pose='UNKNOWN')
    assert c._arm_call('REST', lambda: False) == 'OK'
    assert arm.jobs == ['REST'] and c.arm_pose == 'REST'


def test_arm_call_offline_and_failure():
    """구동부 없음은 ARM_OFFLINE, 실패 사유는 그대로, 실패 뒤 UNKNOWN."""
    c, _ = _ctrl(FakeArmClient(online=False), pose='UNKNOWN')
    assert c._arm_call('REST', lambda: False) == 'ARM_OFFLINE'
    c, _ = _ctrl(FakeArmClient(reason='ARM_TIMEOUT'), pose='HOME')
    assert c._arm_call('REST', lambda: False) == 'ARM_TIMEOUT'
    assert c.arm_pose == 'UNKNOWN'


def test_route_folds_before_driving_when_not_rest():
    """arm_pose 가 REST 가 아니면 출발 전에 REST 를 한 번 보냄."""
    arm = FakeArmClient()
    c, _ = _ctrl(arm, pose='HOME')
    gh = FakeRouteGoal()
    c.cur = gh
    _stop_counter(c, gh, cancel_at=2)     # 1: 접기 전 정지, 2: 허가 대기
    res = c._navigate(gh)
    assert arm.jobs == ['REST']
    assert c.arm_pose == 'REST'
    assert res.reason == 'CANCELED'


def test_route_does_not_fold_when_rest():
    """arm_pose 가 REST 면 팔 명령 없이 진행."""
    arm = FakeArmClient()
    c, _ = _ctrl(arm, pose='REST')
    gh = FakeRouteGoal()
    c.cur = gh
    _stop_counter(c, gh, cancel_at=1)     # 1: 허가 대기
    res = c._navigate(gh)
    assert arm.jobs == []
    assert res.reason == 'CANCELED'


def test_fold_failure_gives_route_back_without_moving():
    """접기 실패(ARM_OFFLINE): 그 사유로 경로를 돌려주고 움직이지 않음."""
    c, log = _ctrl(FakeArmClient(online=False), pose='UNKNOWN')
    gh = FakeRouteGoal()
    c.cur = gh
    _stop_counter(c, gh, cancel_at=99)
    c._progress_watch = None              # 이동 단계에 닿으면 TypeError
    res = c._navigate(gh)
    assert res.reason == 'ARM_OFFLINE' and not res.success
    assert gh.ended == 'abort'
    assert any('could not fold' in s for s in log.lines)


def test_route_refused_while_arm_job_runs():
    """팔 작업 중에 온 경로는 ARM_BUSY 로 거절."""
    c, _ = _ctrl(FakeArmClient(), pose='REST')
    c.arm_state = 'LOAD'
    gh = FakeRouteGoal()
    c.cur = gh
    res = c._navigate(gh)
    assert res.reason == 'ARM_BUSY' and gh.ended == 'abort'


def test_home_pose_after_home_arrival():
    """홈에서 끝난 경로 뒤 arm_home_delay 가 지나면 HOME(0도)."""
    arm = FakeArmClient()
    c, _ = _ctrl(arm, pose='REST')
    gh = FakeRouteGoal()
    c.cur = gh
    c._arm_home_later(gh)
    assert arm.jobs == ['HOME'] and c.arm_pose == 'HOME'


def test_no_home_pose_when_new_route_came():
    """기다리는 사이 새 경로가 오면 펴지 않음."""
    arm = FakeArmClient()
    c, _ = _ctrl(arm, pose='REST')
    gh = FakeRouteGoal()
    c.cur = gh
    threading.Timer(0.01, lambda: setattr(c, 'cur', object())).start()
    c._arm_home_later(gh)
    time.sleep(0.02)
    assert arm.jobs == [] and c.arm_pose == 'REST'


def test_forwarded_job_updates_pose():
    """관제 팔 작업: 성공이면 REST(HOME 작업은 HOME), 실패면 UNKNOWN."""
    c, _ = _ctrl(FakeArmClient(), pose='HOME')
    c.arm_q = []

    def run(job, ok):
        gh = types.SimpleNamespace(
            request=types.SimpleNamespace(job=job, task_id='S0001'),
            is_cancel_requested=False, succeed=lambda: None,
            abort=lambda: None, canceled=lambda: None)
        c._arm_relay = lambda g: types.SimpleNamespace(
            success=ok, reason='OK' if ok else 'E_STOP')
        c._arm_forward(gh)
        return c.arm_pose

    assert run('LOAD', True) == 'REST'
    assert run('HOME', True) == 'HOME'
    assert run('LOAD', False) == 'UNKNOWN'
