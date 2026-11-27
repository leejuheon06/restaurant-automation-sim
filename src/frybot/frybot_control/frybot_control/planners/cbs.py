"""Continuous-time Conflict-Based Search with SIPP as the low-level planner (CCBS family, Andreychuk et al. 2022).

Unlike prioritized SIPP, nobody has a fixed priority: all robots that are moving are planned together. When two
plans collide, the search branches - either robot may be the one that waits or detours - and keeps the cheaper
outcome (sum of arrival times). Constraints are "do not hold node n during [t0, t1]" in the shared lock semantics.
This is a bounded search (node / time limit); when it runs out, the caller falls back to prioritized planning.

CCBS 계열 공동 계획기. FleetCore._plan_joint 가 움직이는 로봇 전체의
요청을 plan_joint() 로 넘기고, None 이 오면 우선순위 SIPP(plan())로
혼자 다시 계획한다. 비용은 로봇별 (도착 시각 - t0) 의 합.
"""
import heapq
import itertools
import time

from .base import PathPlanner, ReservationTable
from .sipp import SippPlanner


class CbsPlanner(PathPlanner):
    """CCBS 계열 플래너(PLANNERS['ccbs']).

    Args:
        max_nodes: 펼칠 수 있는 충돌 트리 노드 수 상한.
        time_limit: plan_joint 한 번의 벽시계 시간 상한(초).
    """

    name = 'ccbs'
    coordinated = True
    joint = True
    description = 'CCBS 계열: 충돌 기반 탐색 + SIPP 하위 탐색 (움직이는 로봇 전체를 함께 계획)'

    def __init__(self, max_nodes=120, time_limit=0.25):
        self.low = SippPlanner()  # 하위 탐색(로봇 한 대) 플래너
        self.max_nodes, self.time_limit = max_nodes, time_limit

    def plan(self, graph, req, table):                       # single-robot query: same as prioritized SIPP
        """로봇 한 대 계획. SippPlanner.plan 과 같다.

        Args:
            graph: 로드맵(layout.Graph).
            req: 계획 요청(PlanRequest).
            table: 다른 로봇의 예약표.

        Returns:
            list[Step] | None: 경로, 없으면 None.
        """
        return self.low.plan(graph, req, table)

    # 고정 예약(static)에 이 로봇의 제약 cons 를 더해 SIPP 로 계획한다.
    # cons 항목 (node, t0, t1, expand): expand 면 pad·가까운 노드까지
    # 넓혀 예약(add), 아니면 이미 넓혀진 구간이라 그대로(add_raw)
    def _low(self, graph, req, static, cons):
        tb = static.copy()
        for (node, t0, t1, expand) in cons:
            if expand:
                tb.add(node, t0, t1, 'cbs')
            else:
                tb.add_raw(node, t0, t1, 'cbs')
        return self.low.plan(graph, req, tb)

    @staticmethod
    def _conflict(graph, plans, holds):
        """First pair of plans that would need the same (or a too-close) node at the same time."""
        # 로봇별 예약표를 따로 만들어, 쌍마다 b 의 점유가 a 의 예약과
        # 겹치는지 본다(a 쪽 예약에는 pad·가까운 노드가 들어 있음)
        tabs = {}
        for rid, steps in plans.items():
            t = ReservationTable(conflict=graph.conflict)
            t.add_plan(rid, steps, last_hold=holds[rid])
            tabs[rid] = t
        for a, b in itertools.combinations(plans, 2):
            sb = plans[b]
            for i, s in enumerate(sb):
                t0 = sb[i - 1].depart if i > 0 else s.arrive
                t1 = sb[i + 1].arrive if i + 1 < len(sb) else s.arrive + holds[b]
                for (r0, r1, _) in tabs[a].res.get(s.node, ()):
                    if r0 < t1 and t0 < r1:
                        return a, b, s.node, (t0, t1), (r0, r1)
        return None

    def plan_joint(self, graph, reqs, static):
        """reqs: list[PlanRequest]; static: reservations of robots that are not being planned. -> {robot_id: steps}|None"""
        t_start = time.perf_counter()  # time_limit 측정 시작(벽시계)
        holds = {r.robot_id: r.goal_hold for r in reqs}
        by_id = {r.robot_id: r for r in reqs}
        root_cons = {r.robot_id: () for r in reqs}
        plans = {}
        # 뿌리 노드: 제약 없이 각자 계획. 한 대라도 못 찾으면 실패
        for r in reqs:
            p = self._low(graph, r, static, ())
            if p is None:
                return None
            plans[r.robot_id] = p
        cost = lambda ps: sum(p[-1].arrive - by_id[k].t0 for k, p in ps.items())
        tie = itertools.count()  # 비용이 같을 때 먼저 넣은 노드부터
        # 충돌 트리 노드: (비용 합, 순번, 로봇별 제약, 로봇별 경로)
        heap = [(cost(plans), next(tie), root_cons, plans)]
        n = 0
        while heap and n < self.max_nodes and time.perf_counter() - t_start < self.time_limit:
            _, _, cons, plans = heapq.heappop(heap)
            n += 1
            c = self._conflict(graph, plans, holds)
            if c is None:
                return plans
            a, b, node, (bt0, bt1), (ar0, ar1) = c
            # branch 1: b keeps away from the node while a needs it; branch 2: a keeps away while b holds it
            for who, con in ((b, (node, ar0, ar1, False)), (a, (node, bt0, bt1, True))):
                nc = dict(cons)
                nc[who] = cons[who] + (con,)
                p = self._low(graph, by_id[who], static, nc[who])
                if p is None:
                    continue
                np_ = dict(plans)
                np_[who] = p
                heapq.heappush(heap, (cost(np_), next(tie), nc, np_))
        return None
