"""Continuous-time Conflict-Based Search with SIPP as the low-level planner (CCBS family, Andreychuk et al. 2022).

Unlike prioritized SIPP, nobody has a fixed priority: all robots that are moving are planned together. When two
plans collide, the search branches - either robot may be the one that waits or detours - and keeps the cheaper
outcome (sum of arrival times). Constraints are "do not hold node n during [t0, t1]" in the shared lock semantics.
This is a bounded search (node / time limit); when it runs out, the caller falls back to prioritized planning.
"""
import heapq
import itertools
import time

from .base import PathPlanner, ReservationTable, INF
from .sipp import SippPlanner


class CbsPlanner(PathPlanner):
    name = 'ccbs'
    coordinated = True
    joint = True
    description = 'CCBS 계열: 충돌 기반 탐색 + SIPP 하위 탐색 (움직이는 로봇 전체를 함께 계획)'

    def __init__(self, max_nodes=120, time_limit=0.25):
        self.low = SippPlanner()
        self.max_nodes, self.time_limit = max_nodes, time_limit

    def plan(self, graph, req, table):                       # single-robot query: same as prioritized SIPP
        return self.low.plan(graph, req, table)

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
        t_start = time.perf_counter()
        holds = {r.robot_id: r.goal_hold for r in reqs}
        by_id = {r.robot_id: r for r in reqs}
        root_cons = {r.robot_id: () for r in reqs}
        plans = {}
        for r in reqs:
            p = self._low(graph, r, static, ())
            if p is None:
                return None
            plans[r.robot_id] = p
        cost = lambda ps: sum(p[-1].arrive - by_id[k].t0 for k, p in ps.items())
        tie = itertools.count()
        heap = [(cost(plans), next(tie), root_cons, plans)]
        n = 0
        while heap and n < self.max_nodes and time.perf_counter() - t_start < self.time_limit:
            _, _, cons, plans = heapq.heappop(heap)
            n += 1
            c = self._conflict(graph, plans, holds)
            if c is None:
                self.last_nodes = n
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
