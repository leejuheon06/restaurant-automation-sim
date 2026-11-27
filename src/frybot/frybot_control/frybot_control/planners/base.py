"""Path planner plug-in interface + shared reservation table.

Lock semantics shared by every planner and by the runtime traffic layer:
a robot holds node n[i] from the moment it departs n[i-1] until it arrives at n[i+1].

경로 계획기 공통 규격(Step, PlanRequest, PathPlanner)과 노드 예약표
(ReservationTable). 예약표는 "노드 n 을 [t0, t1) 동안 누가 점유하는지"를
노드별로 정렬해 두며, 위 점유 규칙을 모든 플래너와 관제 실행 락이 함께 쓴다.
"""
import bisect
from dataclasses import dataclass

INF = float('inf')  # 끝이 없는 시각(예: 목적지에 계속 머묾)


@dataclass
class Step:
    """계획 경로의 한 지점(노드와 그 노드의 도착·출발 시각).

    시각은 관제 시계(FleetCore.now) 기준 초. 시각을 계획하지 않는
    플래너(independent_astar)는 arrive·depart 를 0.0 으로 둔다.

    Attributes:
        node: 로드맵 노드 이름.
        arrive: 이 노드에 닿는 계획 시각(초).
        depart: 이 노드를 떠나 다음 노드로 출발하는 가장 이른 시각(초).
    """

    node: str  # 로드맵 노드 이름
    arrive: float  # 도착 계획 시각(초)
    depart: float          # earliest departure toward the next node (last step: arrive + hold)


@dataclass
class PlanRequest:
    """로봇 한 대의 경로 계획 요청.

    Attributes:
        robot_id: 계획하는 로봇 이름(예: 'pinky1').
        start: 출발 노드.
        goal: 목적 노드.
        t0: 출발 노드를 떠날 수 있는 가장 이른 시각(초).
        speed: 계획 속도(m/s). 관제는 주행 속도 x plan_speed_factor 를 넘김.
        goal_hold: 도착 뒤 목적 노드를 비워 두어야 하는 시간(초).
            INF 면 계속 머묾(대기 자리 등).
        blocked: 쓰지 않을 노드 집합.
        overhead: 구간마다 더하는 출발 지연(초).
    """

    robot_id: str  # 로봇 이름
    start: str  # 출발 노드
    goal: str  # 목적 노드
    t0: float  # 계획 시작 시각(초)
    speed: float  # 계획 속도(m/s)
    goal_hold: float = 5.0          # seconds the goal must stay free after arrival
    blocked: frozenset = frozenset()  # nodes that must not be used (uncoordinated replans)
    # [수정 2026-11-18] W6(E1, R5-4): 구간마다 출발할 때 쓰는 지연(초).
    # 구간 시간 = overhead + 거리 / speed. 예약 규칙은 그대로(앞 노드를
    # 떠날 때부터 다음 노드에 닿을 때까지 점유). 기본 0.0 = 예전과 같음
    overhead: float = 0.0

    def segment_time(self, dist: float) -> float:
        """한 구간(거리 dist m)을 가는 계획 시간(초)."""
        return self.overhead + dist / self.speed


class ReservationTable:
    """노드별 시간 예약표(다른 로봇의 계획·현재 점유).

    관제(FleetCore._table)가 계획할 로봇을 뺀 다른 로봇들의 남은 경로와
    지금 점유한 노드를 넣어 만들고, 플래너는 이 예약을 피해 계획한다.

    Args:
        pad: add() 로 넣는 예약의 앞뒤에 더하는 여유 시간(초).
        conflict: 노드 -> 동시에 점유할 수 없는 가까운 노드 집합
            (보통 Graph.conflict, 중심 거리 SAFE_DIST 미만).
    """

    def __init__(self, pad=0.4, conflict=None):
        self.res = {}        # node -> sorted list of (t0, t1, owner)
        self.pad = pad
        self.conflict = conflict or {}   # node -> nodes too close to be occupied at the same time
        self.itineraries = []            # other robots' motion as [(node, time), ...] (for trajectory-based planners)

    def add(self, node, t0, t1, owner):
        """노드 node 와 가까운 노드들을 [t0 - pad, t1 + pad] 동안 예약한다.

        Args:
            node: 예약할 노드.
            t0: 점유 시작 시각(초).
            t1: 점유 끝 시각(초). INF 가능.
            owner: 예약한 로봇 이름(기록용).
        """
        for n in (node, *self.conflict.get(node, ())):
            bisect.insort(self.res.setdefault(n, []), (t0 - self.pad, t1 + self.pad, owner))

    def add_raw(self, node, t0, t1, owner):
        """여유(pad)·가까운 노드 확장 없이 node 하나만 [t0, t1] 예약한다.

        CCBS 가 이미 확장된 구간을 제약으로 다시 넣을 때 쓴다.

        Args:
            node: 예약할 노드.
            t0: 점유 시작 시각(초).
            t1: 점유 끝 시각(초).
            owner: 예약한 로봇 이름(기록용).
        """
        bisect.insort(self.res.setdefault(node, []), (t0, t1, owner))

    def copy(self):
        """예약과 itineraries 를 복사한 새 예약표(conflict 는 공유).

        Returns:
            ReservationTable: 원본을 바꾸지 않고 예약을 더할 수 있는 사본.
        """
        c = ReservationTable(self.pad, self.conflict)
        c.res = {k: list(v) for k, v in self.res.items()}
        c.itineraries = list(self.itineraries)
        return c

    def add_plan(self, owner, steps, last_hold=INF):
        """Reserve a (remaining) plan using the lock semantics above.

        Args:
            owner: 경로 주인 로봇 이름.
            steps: 남은 경로(list[Step]).
            last_hold: 마지막 노드에 도착한 뒤 점유하는 시간(초).
        """
        for i, s in enumerate(steps):
            t0 = steps[i - 1].depart if i > 0 else s.arrive
            t1 = steps[i + 1].arrive if i + 1 < len(steps) else (s.arrive + last_hold)
            self.add(s.node, t0, t1, owner)

    def safe_intervals(self, node, t_from=0.0):
        """t_from 이후 node 가 비어 있는 시간 구간(SIPP 의 안전 구간).

        Args:
            node: 볼 노드.
            t_from: 이 시각부터 본다(초).

        Returns:
            list[tuple[float, float]]: 시간 순 (시작, 끝) 목록. 마지막
            구간의 끝이 INF 면 그 뒤로 계속 비어 있음.
        """
        out, t = [], t_from
        for a, b, _ in self.res.get(node, []):
            if b <= t:
                continue
            if a > t:
                out.append((t, a))
            t = max(t, b)
            if t == INF:
                break
        if t < INF:
            out.append((t, INF))
        return out

    def is_free(self, node, a, b):
        """노드 node 가 [a, b) 동안 아무 예약과도 겹치지 않는지.

        Args:
            node: 볼 노드.
            a: 구간 시작(초).
            b: 구간 끝(초).

        Returns:
            bool: 겹치는 예약이 없으면 True.
        """
        for r0, r1, _ in self.res.get(node, []):
            if r0 < b and a < r1:
                return False
        return True

    def first_block_after(self, node, t):
        """기준 시각 t 보다 뒤에 시작하는 첫 예약의 시작 시각.

        t 이전에 시작해 아직 이어지는 예약은 보지 않는다.

        Args:
            node: 볼 노드.
            t: 기준 시각(초).

        Returns:
            float: 그 예약의 시작 시각(pad 포함). 없으면 INF.
        """
        for r0, r1, _ in self.res.get(node, []):
            if r1 > t and r0 > t:
                return r0
        return INF


class PathPlanner:
    """경로 계획기 기반 클래스. 새 플래너는 이것을 상속해 plan() 을 구현한다.

    coordinated=False 면 관제는 예약 시각을 쓰지 않고 실행 락만으로
    순서를 정한다. joint=True 면 plan_joint(graph, reqs, static) 로
    움직이는 로봇 전체를 함께 계획한다(FleetCore._plan_joint).
    """

    name = 'base'  # PLANNERS 등록 이름(런치 인자·화면에 쓰임)
    coordinated = True      # False: plans ignore other robots (runtime locks only)
    joint = False           # True: has plan_joint() and re-plans all moving robots together
    description = ''  # 관리자 화면에 보이는 설명

    def plan(self, graph, req: PlanRequest, table: ReservationTable):
        """Return list[Step] from req.start to req.goal, or None when no plan exists.

        Args:
            graph: 로드맵(layout.Graph). adj, sp_from(), conflict 를 씀.
            req: 계획 요청(PlanRequest).
            table: 다른 로봇의 예약(ReservationTable).

        Raises:
            NotImplementedError: 하위 클래스가 구현하지 않았을 때.
        """
        raise NotImplementedError


def start_interval_end(table, node, t0, grace=3.0):
    """We physically stand on the start node, so it is usable from t0 until the next foreign reservation
    (at least `grace` seconds so that an already-conflicting reservation still lets us back off).

    출발 노드에서 쓸 수 있는 첫 안전 구간의 끝 시각. 출발 노드가 t0 에
    이미 남의 예약과 겹치면 최소 grace 초를 주어 물러날 수 있게 하고,
    비어 있으면 다음 예약 시작까지(최소 1 ms)로 본다. 호출처: sipp,
    cooperative_astar.

    Args:
        table: 다른 로봇의 예약표.
        node: 출발 노드.
        t0: 계획 시작 시각(초).
        grace: 이미 겹칠 때 보장하는 최소 시간(초).

    Returns:
        float: 출발 노드 점유가 허용되는 마지막 시각(초).
    """
    return max(table.first_block_after(node, t0), t0 + grace) if not table.is_free(node, t0, t0 + 1e-3) \
        else max(table.first_block_after(node, t0), t0 + 1e-3)
