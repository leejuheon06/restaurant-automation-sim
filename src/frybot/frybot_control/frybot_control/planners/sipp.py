"""Prioritized Safe-Interval Path Planning (Phillips & Likhachev, ICRA 2011) on the roadmap.

Continuous time, one search state per (node, safe interval). Already-planned robots are fixed
obstacles in the reservation table (prioritized planning), so one query costs about as much as A*.

기본 경로 계획기. 먼저 계획된 로봇의 예약(ReservationTable)을 고정
장애물로 보고, 로봇 한 대의 경로를 (노드, 안전 구간) 상태 위에서 시간
최단으로 찾는다. 노드에서 기다리는 시간도 결과의 depart 로 나온다.
"""
import heapq
from .base import PathPlanner, Step, INF, start_interval_end


class SippPlanner(PathPlanner):
    """우선순위 SIPP 플래너(PLANNERS['sipp'], 기본값)."""

    name = 'sipp'
    coordinated = True
    description = '우선순위 SIPP (연속 시간, 안전 구간 탐색)'

    def plan(self, graph, req, table):
        """다른 로봇 예약을 피하는 시간 최단 경로를 찾는다.

        Args:
            graph: 로드맵(layout.Graph).
            req: 계획 요청(PlanRequest).
            table: 다른 로봇의 예약표.

        Returns:
            list[Step] | None: 출발부터 목적까지의 경로. 목적 노드에
            goal_hold 만큼 머물 수 있는 경로가 없으면 None.
        """
        start, goal, t0, v = req.start, req.goal, req.t0, req.speed
        # 목적 노드까지의 정적 최단 거리(m). A* 휴리스틱(거리 / 속도)에 씀
        h = graph.sp_from(goal)
        if start not in h:  # 목적과 이어지지 않은 출발 노드
            return None
        # 출발 노드는 지금 서 있는 곳이라 t0 부터 첫 안전 구간으로 둠
        s_end = start_interval_end(table, start, t0)
        s_key = (start, t0)                       # state key: (node, interval start)
        ivals = {start: [(t0, s_end)]}

        # 노드별 안전 구간을 필요할 때 한 번만 계산해 둠
        def intervals(n):
            if n not in ivals:
                ivals[n] = table.safe_intervals(n, t0)
            return ivals[n]

        g = {s_key: t0}  # 상태 -> 가장 이른 도착 시각
        parent = {s_key: None}  # 상태 -> (이전 상태, 이전 노드 출발 시각)
        iv_of = {s_key: (t0, s_end)}  # 상태 -> 그 안전 구간 (시작, 끝)
        # 우선순위 큐: (도착 시각 + 남은 거리 / 속도, 도착 시각, 상태)
        pq = [(t0 + h[start] / v, t0, s_key)]
        while pq:
            _, t, key = heapq.heappop(pq)
            if t > g.get(key, INF):  # 더 이른 도착으로 이미 처리한 상태
                continue
            # [수정 2026-11-17] 쓰지 않는 구간 시작값(a_u)을 _ 로 받음
            u, (_, b_u) = key[0], iv_of[key]
            # 목적 도착 판정: 지금 안전 구간이 goal_hold 동안 이어져야 함.
            # goal_hold 가 INF 면 구간 끝도 INF(영원히 비어 있음)여야 함
            if u == goal and b_u >= t + min(req.goal_hold, 1e8) and (req.goal_hold < INF or b_u == INF):
                return self._path(parent, g, key, req)
            for w, d in graph.adj[u]:
                if w in req.blocked or w not in h:  # 금지·고립 노드
                    continue
                # [수정 2026-11-18] W6: 구간 지연 포함 (휴리스틱 h / v 는
                # 실제보다 작게 잡는 값이라 그대로 둠)
                dt = req.segment_time(d)
                for (a_w, b_w) in intervals(w):
                    td = max(t, a_w)                  # departure: w must already be ours (free) when we leave u
                    ta = td + dt
                    if ta > b_u or ta >= b_w:         # u must stay ours until we arrive; w must still be free
                        continue
                    k2 = (w, a_w)  # 새 상태: (이웃 노드, 그 안전 구간 시작)
                    if ta < g.get(k2, INF):
                        g[k2] = ta
                        parent[k2] = (key, td)
                        iv_of[k2] = (a_w, b_w)
                        heapq.heappush(pq, (ta + h[w] / v, ta, k2))
        return None

    # 목적 상태에서 parent 를 거슬러 list[Step] 을 만든다. 각 노드의 depart
    # 는 다음 노드로 출발한 시각, 마지막 노드는 도착 + goal_hold(INF 면 0)
    @staticmethod
    def _path(parent, g, key, req):
        rev = []
        depart_next = g[key] + (req.goal_hold if req.goal_hold < INF else 0.0)
        while key is not None:
            rev.append(Step(key[0], g[key], depart_next))
            p = parent[key]
            if p is None:
                break
            key, depart_next = p
        rev.reverse()
        return rev
