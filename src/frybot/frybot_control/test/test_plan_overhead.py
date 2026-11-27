"""계획의 구간 지연(PlanRequest.overhead) 확인 (작업 지시서 2 W6).

다른 로봇이 없는 지도에서 플래너가 낸 경로의 시각이 구간마다
"지연 + 거리 / 속도"와 맞는지 본다. ROS 없이 실행된다.

    cd ~/frybot_ws && source install/setup.bash
    python3 -m pytest src/frybot/frybot_control/test -q
"""
# [수정 2026-11-18] W6: 신규
import os

import pytest

os.environ['FRYBOT_MAP_ID'] = ''           # 가상 매장 도면(proto)

from frybot_control.layout import Graph  # noqa: E402
from frybot_control.planners.base import PlanRequest  # noqa: E402
from frybot_control.planners.base import ReservationTable  # noqa: E402
from frybot_control.planners.cooperative_astar import CooperativeAStarPlanner  # noqa: E402
from frybot_control.planners.independent_astar import IndependentAStarPlanner  # noqa: E402
from frybot_control.planners.sipp import SippPlanner  # noqa: E402

SPEED = 0.135  # 계획 속도(m/s), 실기기 보정값
OVERHEAD = 2.27  # 구간 지연(초), 실기기 보정값
T0 = 10.0  # 계획 시작 시각(초)


@pytest.fixture(scope='module')
def graph():
    """가상 매장 로드맵."""
    # [수정 2026-11-18] W8-3: 다른 테스트 파일이 지도를 바꿀 수 있어 여기서 정함
    os.environ['FRYBOT_MAP_ID'] = ''
    return Graph()


def _far_pair(graph):
    """구간이 여러 개인 출발·도착 노드 한 쌍."""
    start = graph.resolve('ENTRANCE')
    goal = graph.resolve('DISH_RETURN')
    return start, goal


def _plan(planner, graph, overhead):
    """빈 예약표에서 ENTRANCE -> DISH_RETURN 경로를 계획한 결과."""
    start, goal = _far_pair(graph)
    req = PlanRequest('pinky1', start, goal, T0, SPEED, overhead=overhead)
    table = ReservationTable(conflict=graph.conflict)
    steps = planner.plan(graph, req, table)
    assert steps, '빈 지도에서 경로를 찾지 못함'
    return steps


@pytest.mark.parametrize('overhead', [0.0, OVERHEAD])
def test_sipp_segment_times(graph, overhead):
    """SIPP: 구간마다 도착 시각 차이 = 지연 + 거리 / 속도 (대기 없음)."""
    steps = _plan(SippPlanner(), graph, overhead)
    assert steps[0].arrive == pytest.approx(T0)
    for a, b in zip(steps, steps[1:], strict=False):
        seg = overhead + graph.dist(a.node, b.node) / SPEED
        assert b.arrive - a.arrive == pytest.approx(seg, abs=1e-9)
        assert a.depart == pytest.approx(a.arrive, abs=1e-9)


def test_sipp_total_includes_overhead(graph):
    """지연을 넣으면 도착 시각이 (구간 수 x 지연) 이상 늦어짐."""
    base = _plan(SippPlanner(), graph, 0.0)
    slow = _plan(SippPlanner(), graph, OVERHEAD)
    hops = len(slow) - 1
    assert slow[-1].arrive >= base[-1].arrive + hops * OVERHEAD - 1e-9


@pytest.mark.parametrize('overhead', [0.0, OVERHEAD])
def test_cooperative_astar_segment_times(graph, overhead):
    """협조 A*: 0.5초 격자로 올림하므로 정확한 값 이상, 한 칸 미만 차이."""
    planner = CooperativeAStarPlanner()
    steps = _plan(planner, graph, overhead)
    moves = [(a, b) for a, b in zip(steps, steps[1:], strict=False)
             if a.node != b.node]
    assert moves
    for a, b in moves:
        exact = overhead + graph.dist(a.node, b.node) / SPEED
        took = b.arrive - a.depart
        assert exact - 1e-9 <= took < exact + planner.dt + 1e-9


def test_independent_astar_has_no_times(graph):
    """기준선은 시각을 계획하지 않음(지연을 쓰지 않음): 시각 0, 같은 경로."""
    base = _plan(IndependentAStarPlanner(), graph, 0.0)
    slow = _plan(IndependentAStarPlanner(), graph, OVERHEAD)
    assert [s.node for s in base] == [s.node for s in slow]
    assert all(s.arrive == 0.0 and s.depart == 0.0 for s in slow)


def test_segment_time():
    """PlanRequest.segment_time = 지연 + 거리 / 속도."""
    req = PlanRequest('r', 'a', 'b', 0.0, 0.1, overhead=2.0)
    assert req.segment_time(0.5) == pytest.approx(7.0)
    assert PlanRequest('r', 'a', 'b', 0.0, 0.1).segment_time(0.5) == \
        pytest.approx(5.0)
