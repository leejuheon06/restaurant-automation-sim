"""Cooperative A* (Silver 2005): prioritized space-time A* on a fixed time grid with a reservation table.

비교용 협조 A*. 시간을 dt(기본 0.5초) 칸으로 나눈 (노드, 칸 번호) 상태를
탐색하며, 칸마다 그 자리에서 기다리거나 이웃 노드로 간다. 구간 시간은
칸 단위로 올림하므로 SIPP 보다 최대 한 칸 늦게 계획된다.
"""
import heapq
import math
from .base import PathPlanner, Step, INF, start_interval_end


class CooperativeAStarPlanner(PathPlanner):
    """협조 A* 플래너(PLANNERS['cooperative_astar']).

    Args:
        dt: 시간 격자 한 칸(초).
        horizon: 탐색할 최대 칸 수. 넘는 상태는 더 펼치지 않음.
    """

    name = 'cooperative_astar'
    coordinated = True
    description = '협조 A* (시간 격자 0.5초 + 예약 테이블)'

    def __init__(self, dt=0.5, horizon=600):
        self.dt, self.horizon = dt, horizon

    def plan(self, graph, req, table):
        """시간 격자 위에서 다른 로봇 예약을 피하는 경로를 찾는다.

        Args:
            graph: 로드맵(layout.Graph).
            req: 계획 요청(PlanRequest).
            table: 다른 로봇의 예약표.

        Returns:
            list[Step] | None: 경로. horizon 안에 없으면 None.
        """
        start, goal, t0, v, dt = req.start, req.goal, req.t0, req.speed, self.dt
        h = graph.sp_from(goal)  # 목적까지의 정적 최단 거리(휴리스틱)
        if start not in h:
            return None
        s_end = start_interval_end(table, start, t0)

        # 노드 n 이 [a, b) 동안 쓸 수 있는지. 출발 노드는 s_end 까지 내 것
        def free(n, a, b):
            if n == start and b <= s_end:
                return True
            return table.is_free(n, a, b)

        g = {(start, 0): 0}  # 상태 (노드, 칸 번호 k) -> 도착 칸
        parent = {(start, 0): None}  # 상태 -> 이전 상태
        pq = [(h[start] / v, 0, start)]  # (추정 총 시간, 칸 번호, 노드)
        while pq:
            _, k, u = heapq.heappop(pq)
            t = t0 + k * dt
            # 목적 도착: goal_hold 동안 비어 있어야 함. INF 면 뒤에
            # 시작하는 예약이 없고 지금 1초 동안 비어 있어야 함
            if u == goal:
                hold = req.goal_hold
                if (hold == INF and table.first_block_after(u, t) == INF and free(u, t, t + 1)) or \
                   (hold < INF and free(u, t, t + hold)):
                    return self._path(parent, (u, k), t0, dt, req)
            if k >= self.horizon:  # 탐색 시간 범위 밖
                continue
            cand = []  # 다음 상태 후보 (노드, 칸 번호)
            if free(u, t, t + dt):
                cand.append((u, k + 1))                                  # wait
            for w, d in graph.adj[u]:
                if w in req.blocked or w not in h:
                    continue
                # [수정 2026-11-18] W6: 구간 지연 포함
                n = max(1, math.ceil(req.segment_time(d) / dt))
                # 이동하는 n 칸 동안 도착 노드와 떠나는 노드를 함께 점유
                if free(w, t, t + n * dt) and free(u, t, t + n * dt):
                    cand.append((w, k + n))
            for (w, k2) in cand:
                if k2 < g.get((w, k2), 1 << 30):
                    g[(w, k2)] = k2
                    parent[(w, k2)] = (u, k)
                    heapq.heappush(pq, (k2 * dt + h[w] / v, k2, w))
        return None

    # (노드, 칸) 열을 list[Step] 으로 바꾼다. 같은 노드가 이어지면 기다림
    # (depart 를 늦춤). 마지막 노드의 depart = 도착 + goal_hold(INF 면 0)
    @staticmethod
    def _path(parent, key, t0, dt, req):
        seq = []
        while key is not None:
            seq.append(key)
            key = parent[key]
        seq.reverse()
        # [수정 2026-11-17] 결과를 쓰지 않던 첫 번째 steps 루프와
        # 빈 반복문, 쓰지 않는 idx 삭제. 아래 루프가 같은 값을 만듦
        # leave node i at the last time we were still there
        out = []
        for n, k in seq:
            t = t0 + k * dt
            if out and out[-1].node == n:
                out[-1].depart = t             # waiting in place
            else:
                out.append(Step(n, t, t))
        out[-1].depart = out[-1].arrive + (req.goal_hold if req.goal_hold < INF else 0.0)
        return out
