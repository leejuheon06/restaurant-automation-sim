"""Baseline: every robot takes its own shortest path. No time coordination - conflicts are only
resolved at run time by the node locks of the traffic layer (wait, then re-route around blockers).

[수정 2026-11-18] W6: 시각을 계획하지 않으므로(Step 시각 0) 구간
지연(PlanRequest.overhead)을 쓰지 않음. 경로는 거리 기준 최단 경로 그대로.

기준선 플래너. 예약표(table)를 보지 않고 거리만으로 A* 를 돌린다.
coordinated=False 라 관제는 계획 시각 없이 실행 락으로만 순서를 정한다.
"""
import heapq
from .base import PathPlanner, Step, INF


class IndependentAStarPlanner(PathPlanner):
    """기준선 최단 경로 플래너(PLANNERS['independent_astar'])."""

    name = 'independent_astar'
    coordinated = False
    description = '기준선: 로봇별 최단 경로 A* + 실행 중 구역 점유(락) 대기'

    def plan(self, graph, req, table):
        """거리 기준 최단 경로(시각 없음)를 찾는다.

        Args:
            graph: 로드맵(layout.Graph).
            req: 계획 요청(PlanRequest). blocked 노드만 피함.
            table: 쓰지 않음(규격을 맞추려고 받음).

        Returns:
            list[Step] | None: 노드 순서만 담은 경로(시각 0.0). 없으면 None.
        """
        start, goal = req.start, req.goal
        h = graph.sp_from(goal)
        if start not in h:
            return None
        g, parent = {start: 0.0}, {start: None}  # 누적 거리, 이전 노드
        pq = [(h[start], start)]  # (누적 + 남은 거리, 노드)
        while pq:
            _, u = heapq.heappop(pq)
            if u == goal:
                break
            for w, d in graph.adj[u]:
                if w in req.blocked:
                    continue
                nd = g[u] + d
                if nd < g.get(w, INF):
                    g[w], parent[w] = nd, u
                    heapq.heappush(pq, (nd + h.get(w, INF), w))
        if goal not in parent:
            return None
        # 목적에서 parent 를 거슬러 노드 순서를 만듦
        seq, n = [], goal
        while n is not None:
            seq.append(n)
            n = parent[n]
        seq.reverse()
        return [Step(n, 0.0, 0.0) for n in seq]
