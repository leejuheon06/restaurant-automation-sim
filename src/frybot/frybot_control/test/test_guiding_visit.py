# [수정 2026-11-24] 새 파일: GUEST_TRACK 의 visit_id 채우기(guiding_visit) 시험
"""Restaurant.guiding_visit 이 안내를 맡은 방문만 돌려주는지 시험한다."""

from frybot_control.restaurant import Restaurant


class _Io:
    """기록·임무 요청을 버리는 RestaurantIO 대역."""

    def submit_task(self, cb, **kw) -> None:
        del cb, kw

    def fleet_command(self, cmd, target, arg='') -> None:
        del cmd, target, arg

    def log(self, event, **f) -> None:
        del event, f

    def persist(self, table, row) -> None:
        del table, row


def _rest() -> Restaurant:
    rest = Restaurant(_Io())
    rest.visits = {
        1: {'id': 1, 'state': 'SEATED', 'robot': 'pinky1'},
        2: {'id': 2, 'state': 'GUIDING', 'robot': 'pinky1'},
        3: {'id': 3, 'state': 'ASSIGNED', 'robot': 'pinky2'},
        4: {'id': 4, 'state': 'ASSIGNED', 'robot': ''},
    }
    return rest


def test_guiding_visit_picks_assigned_or_guiding_of_that_robot() -> None:
    """안내 중·안내하러 가는 방문만, 그 로봇 것만."""
    rest = _rest()
    assert rest.guiding_visit('pinky1') == 2
    assert rest.guiding_visit('pinky2') == 3
    assert rest.guiding_visit('pinky3') == 0


def test_guiding_visits_for_ai_lock() -> None:
    """고정 목록: GUIDING, 그리고 보류(GUIDE_FAILED)도 유지. GUIDING 우선."""
    rest = _rest()
    assert rest.guiding_visits() == {'pinky1': 2}
    rest.visits[5] = {'id': 5, 'state': 'GUIDE_FAILED', 'robot': 'pinky3'}
    rest.visits[6] = {'id': 6, 'state': 'GUIDE_FAILED', 'robot': 'pinky1'}
    assert rest.guiding_visits() == {'pinky1': 2, 'pinky3': 5}
    rest.visits[2]['state'] = 'SEATED'  # 자리 안내 완료 -> 고정 해제
    assert rest.guiding_visits() == {'pinky1': 6, 'pinky3': 5}
