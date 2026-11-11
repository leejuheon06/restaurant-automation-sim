"""Prioritized Safe-Interval Path Planning (Phillips & Likhachev, ICRA 2011) on the roadmap.

Continuous time, one search state per (node, safe interval). Already-planned robots are fixed
obstacles in the reservation table (prioritized planning), so one query costs about as much as A*.
"""
import heapq
from .base import PathPlanner, Step, INF, start_interval_end


class SippPlanner(PathPlanner):
    name = 'sipp'
    coordinated = True
    description = '우선순위 SIPP (연속 시간, 안전 구간 탐색)'

    def plan(self, graph, req, table):
        start, goal, t0, v = req.start, req.goal, req.t0, req.speed
        h = graph.sp_from(goal)
        if start not in h:
            return None
        s_end = start_interval_end(table, start, t0)
        s_key = (start, t0)                       # state key: (node, interval start)
        ivals = {start: [(t0, s_end)]}

        def intervals(n):
            if n not in ivals:
                ivals[n] = table.safe_intervals(n, t0)
            return ivals[n]

        g = {s_key: t0}
        parent = {s_key: None}
        iv_of = {s_key: (t0, s_end)}
        pq = [(t0 + h[start] / v, t0, s_key)]
        while pq:
            _, t, key = heapq.heappop(pq)
            if t > g.get(key, INF):
                continue
            u, (a_u, b_u) = key[0], iv_of[key]
            if u == goal and b_u >= t + min(req.goal_hold, 1e8) and (req.goal_hold < INF or b_u == INF):
                return self._path(parent, g, key, req)
            for w, d in graph.adj[u]:
                if w in req.blocked or w not in h:
                    continue
                dt = d / v
                for (a_w, b_w) in intervals(w):
                    td = max(t, a_w)                  # departure: w must already be ours (free) when we leave u
                    ta = td + dt
                    if ta > b_u or ta >= b_w:         # u must stay ours until we arrive; w must still be free
                        continue
                    k2 = (w, a_w)
                    if ta < g.get(k2, INF):
                        g[k2] = ta
                        parent[k2] = (key, td)
                        iv_of[k2] = (a_w, b_w)
                        heapq.heappush(pq, (ta + h[w] / v, ta, k2))
        return None

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
