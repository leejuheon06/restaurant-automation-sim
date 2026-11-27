"""노드에서 벗어나 서 있는 로봇의 보고 위치로 허가를 막는지(T-48).

2026-11-20 2대 시험(runs/20261120_07_two_robot_v05) 상황: pinky1 이 W1 에서
B1 쪽으로 7.7 cm 벗어나 서 있는데 관제는 W1 락만 보고 pinky2 에게 B1 을
허가해 두 로봇 중심이 약 11 cm 까지 가까워졌음. ROS 없이 실행된다.
"""
# [수정 2026-11-20] T-48: 신규
import math
import os

os.environ['FRYBOT_MAP_ID'] = 'test_map_v05'

from frybot_control.layout import SAFE_DIST  # noqa: E402
from frybot_control.mock_fleet import MockFleet  # noqa: E402
from frybot_control.mock_fleet import TimeModel  # noqa: E402

# 오늘 스캔 맞춤으로 잰 pinky1 의 실제 자리(W1 = (0.091, -0.552))
_OFF_W1 = (0.095, -0.475)


def _world(p1_xy: tuple[float, float] | None) -> MockFleet:
    """pinky1 은 W1(또는 p1_xy), pinky2 는 W2 에 세운 모의 관제."""
    os.environ['FRYBOT_MAP_ID'] = 'test_map_v05'
    w = MockFleet(['pinky1', 'pinky2'], TimeModel('ideal', 0.08), dt=0.1,
                  pv_base=0, scheduler='min_cost_eta_rh', planner='sipp')
    w.place('pinky1', 'W1')
    w.place('pinky2', 'W2')
    if p1_xy is not None:
        w.bots['pinky1'].x, w.bots['pinky1'].y = p1_xy
    for _ in range(5):
        w.step()
    return w


def _drive_pinky2_to_b1(w: MockFleet, limit: float = 60.0) -> float:
    """pinky2 를 B1 으로 보내고 그동안 두 로봇 중심 거리의 최솟값."""
    ok, msg = w.core.command('MOVE_TO_VERTEX', 'pinky2', 'B1')
    assert ok, msg
    closest = math.inf
    start = w.t
    while w.t < start + limit:
        w.step()
        a, b = w.bots['pinky1'], w.bots['pinky2']
        closest = min(closest, math.dist((a.x, a.y), (b.x, b.y)))
    return closest


def test_off_node_robot_blocks_neighbour_node():
    """W1 에서 7.7 cm 벗어난 pinky1 옆 B1 을 pinky2 에게 허가하지 않음."""
    # 두 로봇 중심이 SAFE_DIST(15.5 cm) 밑으로 가까워진 적이 없어야 함
    w = _world(_OFF_W1)
    closest = _drive_pinky2_to_b1(w)
    assert closest >= SAFE_DIST - 1e-6
    b1 = w.core.graph.nodes['B1']
    p2 = w.bots['pinky2']
    p1 = w.bots['pinky1']
    # B1 에 들어갔다면 pinky1 이 먼저 비켜 났어야 함
    if math.dist((p2.x, p2.y), b1) < 0.01:
        assert math.dist((p1.x, p1.y), b1) >= SAFE_DIST
    # 지금은 계획 단계에서 B1 을 피해 출발하지 않고, 20초 뒤 PLAN_FAIL 보류
    move = [t for t in w.core.tasks.values() if t.type == 'MOVE']
    assert move and move[0].state == 'SUSPENDED'
    assert move[0].reason == 'PLAN_FAIL'


def test_on_node_robot_allows_neighbour_node():
    """pinky1 이 W1 위에 있으면 예전처럼 B1 을 허가(W1-B1 15.7 cm)."""
    w = _world(None)
    _drive_pinky2_to_b1(w)
    b1 = w.core.graph.nodes['B1']
    p2 = w.bots['pinky2']
    assert math.dist((p2.x, p2.y), b1) < 0.01
    assert w.core.robots['pinky1'].route is None


# [수정 2026-11-20] T-52: 6 cm 문턱 대신 보고 위치와 노드 사이 거리(12 cm)
def test_robot_5_9_cm_off_blocks_neighbour_node():
    """실기기 09: W1 에서 B1 쪽으로 5.9 cm(B1 까지 9.9 cm)면 B1 을 막음."""
    w1 = (0.091, -0.552)
    w = _world((w1[0], w1[1] + 0.059))
    closest = _drive_pinky2_to_b1(w)
    assert closest >= 0.12
    b1 = w.core.graph.nodes['B1']
    p2 = w.bots['pinky2']
    assert math.dist((p2.x, p2.y), b1) > 0.01


def test_jitter_on_node_does_not_block():
    """노드 위 3 cm 흔들림(B1 까지 12.7 cm)은 막지 않음(W1-B1 15.7 cm)."""
    w1 = (0.091, -0.552)
    w = _world((w1[0], w1[1] + 0.03))
    _drive_pinky2_to_b1(w)
    b1 = w.core.graph.nodes['B1']
    p2 = w.bots['pinky2']
    assert math.dist((p2.x, p2.y), b1) < 0.01


def test_move_to_same_vertex_resettles_robot():
    """노드에서 4 cm 벗어난 로봇을 그 노드로 다시 세움, 1 cm 면 거절."""
    w1 = (0.091, -0.552)
    w = _world((w1[0], w1[1] + 0.04))
    ok, msg = w.core.command('MOVE_TO_VERTEX', 'pinky1', 'W1')
    assert ok, msg
    for _ in range(300):
        w.step()
    p1 = w.bots['pinky1']
    assert math.dist((p1.x, p1.y), w1) < 0.01
    w = _world((w1[0], w1[1] + 0.01))
    ok, msg = w.core.command('MOVE_TO_VERTEX', 'pinky1', 'W1')
    assert not ok and '이미' in msg


def test_move_reject_says_why():
    """이동 명령 거절 메시지에 걸린 조건이 들어감."""
    w = _world(None)
    assert w.core.command('ESTOP', 'pinky1', 'test')[0]
    ok, msg = w.core.command('MOVE_TO_VERTEX', 'pinky1', 'C1')
    assert not ok and '비상 정지' in msg
    w = _world(None)
    w.core.robots['pinky1'].error = 'SENSOR_ERROR'
    ok, msg = w.core.command('MOVE_TO_VERTEX', 'pinky1', 'C1')
    assert not ok and 'SENSOR_ERROR' in msg


# [수정 2026-11-20] T-53: 관리자 화면 '남은 거리'(snapshot remaining)가 누적
# 주행 거리가 아니라 현재 경로 기준인지. 예전에는 r.dist 를 그대로 보여 줌
def _snap(w: MockFleet, rid: str) -> dict:
    """snapshot 의 로봇 항목 하나."""
    return next(r for r in w.core.snapshot()['robots'] if r['id'] == rid)


def _route_len(w: MockFleet, rid: str) -> float:
    """관제가 가진 경로 전체의 통로 길이 합(대기 스텝 제외)."""
    nodes = [s.node for s in w.core.robots[rid].route]
    g = w.core.graph
    return sum(g.dist(a, b)
               for a, b in zip(nodes, nodes[1:], strict=False) if a != b)


def _move_and_watch(w: MockFleet, rid: str, goal: str) -> list[float]:
    """이동 명령 뒤 경로가 끝날 때까지 remaining 값을 모은다."""
    ok, msg = w.core.command('MOVE_TO_VERTEX', rid, goal)
    assert ok, msg
    for _ in range(50):
        if w.core.robots[rid].route:
            break
        w.step()
    total = _route_len(w, rid)
    seen = [_snap(w, rid)['remaining']]
    # 출발 노드 위에서 시작하므로 차이는 출발 오차(2 cm) 이내
    assert abs(seen[0] - total) < 0.02, (seen[0], total)
    for _ in range(4000):
        w.step()
        seen.append(_snap(w, rid)['remaining'])
        if not w.core.robots[rid].route:
            break
    return seen


def test_remaining_follows_current_route():
    """배정 직후 = 경로 길이, 주행 중 감소, 도착 뒤 0, 왕복 W1→B5→W1."""
    w = _world(None)
    assert _snap(w, 'pinky1')['remaining'] == 0.0
    for goal in ('B5', 'W1'):
        seen = _move_and_watch(w, 'pinky1', goal)
        # 중간 보고에서 줄어들고, 늘지 않음(대기 중에는 그대로)
        assert [v for v in seen if 0 < v < seen[0] - 0.05], seen[:20]
        assert all(b <= a + 0.01
                   for a, b in zip(seen, seen[1:], strict=False))
        p1 = w.bots['pinky1']
        node = w.core.graph.nodes[goal]
        assert math.dist((p1.x, p1.y), node) < 0.01
        assert _snap(w, 'pinky1')['remaining'] == 0.0
    # 누적 주행 거리(dist)는 따로 쌓임: W1-B5 편도 1.607 m 의 왕복
    assert abs(_snap(w, 'pinky1')['dist'] - 3.21) < 0.05

