"""위치를 모르는 로봇의 상태 보고(LOCALIZING 등)를 관제가 다루는 방식(T-49).

ROS 없이 실행된다.
"""
# [수정 2026-11-20] T-49: 신규
import os

os.environ['FRYBOT_MAP_ID'] = 'test_map_v05'

from frybot_control.mock_fleet import MockFleet  # noqa: E402
from frybot_control.mock_fleet import TimeModel  # noqa: E402


def _core():
    """pinky1 한 대만 있는 test_map_v05 모의 관제(FleetCore)."""
    os.environ['FRYBOT_MAP_ID'] = 'test_map_v05'
    w = MockFleet(['pinky1'], TimeModel('ideal', 0.08), dt=0.1, pv_base=0,
                  scheduler='min_cost_eta_rh', planner='sipp')
    return w.core


def _robot_view(core):
    """snapshot() 의 pinky1 항목(관리자 화면이 받는 값)."""
    return next(r for r in core.snapshot()['robots'] if r['id'] == 'pinky1')


def test_localizing_robot_is_shown_but_not_used():
    """LOCALIZING: 화면에는 기동 중, 위치·노드 점유·배정 없음."""
    core = _core()
    core.on_robot_status('pinky1', 0.0, 0.0, 0.0, 90.0, False, 'LOCALIZING')
    r = core.robots['pinky1']
    assert not r.online and not core.locks
    view = _robot_view(core)
    assert view['state'] == 'LOCALIZING'
    assert view['device']['state'] == 'INITIALIZING'
    assert not view['available']


def test_not_localized_reports_error_then_recovers():
    """NOT_LOCALIZED 는 SELF_CHECK_ERROR, 위치가 잡히면 보통 로봇."""
    core = _core()
    core.on_robot_status('pinky1', 0.0, 0.0, 0.0, 90.0, False,
                         'NOT_LOCALIZED', 'SELF_CHECK_ERROR')
    view = _robot_view(core)
    assert view['device']['error'] == 'SELF_CHECK_ERROR'
    w1 = core.graph.nodes['W1']
    core.on_robot_status('pinky1', w1[0], w1[1], 1.57, 90.0, False, 'IDLE')
    r = core.robots['pinky1']
    assert r.online and r.node == 'W1' and core.locks.get('W1') == 'pinky1'
    # W1 은 대기 위치라 STANDBY(위치를 모른다는 상태에서 벗어남)
    assert _robot_view(core)['state'] in ('IDLE', 'STANDBY')
    assert _robot_view(core)['device']['error'] != 'SELF_CHECK_ERROR'
