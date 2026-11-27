"""계획 실패가 20초 넘게 이어지면 임무 보류와 알림 (작업 지시서 3 W8-3).

실측 지도의 막다른 대기 위치(W3)에 비상 정지된 로봇을 세워 두고 다른 로봇을
그리로 보내, 20초 뒤 보류되는지, Restaurant 가 알림을 남기는지, RETRY_TASK 로
재개되는지 본다. ROS 없이 실행된다.
"""
# [수정 2026-11-18] W8-3: 신규
import os

os.environ['FRYBOT_MAP_ID'] = 'test_map_v001'

from frybot_control.fleet_core import PLAN_FAIL_SUSPEND_SEC  # noqa: E402
from frybot_control.mock_fleet import MockFleet  # noqa: E402
from frybot_control.mock_fleet import TimeModel  # noqa: E402
from frybot_control.restaurant import Restaurant  # noqa: E402
from frybot_control.restaurant import RestaurantIO  # noqa: E402


class _IO(RestaurantIO):
    """Restaurant 의 출력만 모아 두는 대역."""

    def __init__(self):
        self.logs = []

    def submit_task(self, cb, **kw):
        """임무 요청(쓰지 않음)."""
        cb('x')

    def fleet_command(self, cmd, target, arg=''):
        """관제 명령(쓰지 않음)."""
        return True, ''

    def log(self, event, **f):
        """로그를 모음."""
        self.logs.append((event, f))

    def persist(self, table, row):
        """DB 저장 대신 모음."""
        self.logs.append(('PERSIST_' + table, row))


def _blocked_world():
    """W3 에 비상 정지된 pinky1, 그리로 가라는 명령을 받은 pinky2."""
    # 다른 테스트 파일이 import 할 때 지도를 바꿀 수 있어, 만들 때 정함
    os.environ['FRYBOT_MAP_ID'] = 'test_map_v001'
    w = MockFleet(['pinky1', 'pinky2'], TimeModel('ideal', 0.08), dt=0.1,
                  pv_base=0, scheduler='min_cost_eta_rh', planner='sipp')
    w.place('pinky1', 'W3')
    w.place('pinky2', 'B4')
    for _ in range(5):
        w.step()
    assert w.core.command('ESTOP', 'pinky1', 'test')[0]
    assert w.core.command('MOVE_TO_VERTEX', 'pinky2', 'W3')[0]
    return w


def _run_until_suspend(w, limit):
    """보류(SUSPENDED)가 한 번 날 때까지(최대 limit 초) 돌린 시간(초)."""
    start = w.t
    w.suspended = 0
    while w.t < start + limit and not w.suspended:
        w.step()
    return w.t - start


def test_suspend_after_plan_fail_limit():
    """같은 목적지 계획 실패가 20초를 넘으면 PLAN_FAIL 로 보류."""
    w = _blocked_world()
    took = _run_until_suspend(w, 60.0)
    assert w.suspended == 1
    assert PLAN_FAIL_SUSPEND_SEC <= took <= PLAN_FAIL_SUSPEND_SEC + 2.0
    sus = [e for e in w.task_events if e['state'] == 'SUSPENDED']
    assert sus and sus[0]['reason'] == 'PLAN_FAIL'


def test_restaurant_alert_and_retry():
    """Restaurant 가 ALERT·incident 를 남기고, RETRY_TASK 로 재개됨."""
    w = _blocked_world()
    _run_until_suspend(w, 60.0)
    io = _IO()
    rest = Restaurant(io)
    for ev in w.task_events:
        if ev['state'] == 'SUSPENDED':
            rest.on_task_event(ev)
    assert rest.incidents and rest.incidents[0]['reason'] == 'PLAN_FAIL'
    assert any(e == 'ALERT' for e, _ in io.logs)
    task_id = rest.incidents[0]['task']
    assert w.core.command('RETRY_TASK', task_id)[0]
    states = [e['state'] for e in w.task_events if e['task_id'] == task_id]
    assert states[-1] == 'RESUMED'
    # 길이 계속 막혀 있으면 다시 20초 뒤 보류됨
    took = _run_until_suspend(w, 60.0)
    assert w.suspended == 1 and took <= PLAN_FAIL_SUSPEND_SEC + 2.0
