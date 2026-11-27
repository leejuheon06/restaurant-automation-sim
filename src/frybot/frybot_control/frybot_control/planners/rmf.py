"""Open-RMF traffic planning (rmf_traffic) as a planner plug-in.

[수정 2026-11-18] W6: 외부 도우미(rmf_plan_server)는 속도만 받아 구간
지연(PlanRequest.overhead)을 지원하지 않음. 지연을 주어도 무시하고
예전처럼 계획함.

The search itself runs in Open-RMF's own library, unchanged: agv::Planner over the nav graph, with the other robots'
itineraries in a traffic schedule (schedule::Database) and ScheduleRouteValidator rejecting any motion whose
footprint would enter another robot's vicinity. A small C++ helper (rmf_bridge/rmf_plan_server.cpp) hosts it; this
class only translates: our roadmap -> RMF graph, the other robots' remaining routes -> schedule itineraries, the
resulting RMF plan -> our list of Steps.

Three back ends, all Open-RMF code unchanged:
  rmf        path planning against the traffic schedule (rmf_traffic agv::Planner)
  rmf_nego   the same + Open-RMF's negotiation: robots that are on the move settle their itineraries together
             (schedule::Negotiation + agv::SimpleNegotiator), used through the Task Manager's joint-planning hook
  rmf_task   (scheduler, see schedulers/rmf_task.py) task allocation with rmf_task::TaskPlanner

Build the helper once:
  source /opt/ros/jazzy/setup.bash
  cmake -S src/frybot/frybot_control/rmf_bridge -B build/rmf_bridge && cmake --build build/rmf_bridge

Open-RMF 비교용 플래너. 도우미 실행 파일(SERVER)을 표준 입출력 줄
규약(rmf_plan_server.cpp 머리말)으로 부려 계획을 받는다. 도우미가
없으면 PLANNERS 에 등록되지 않는다(planners/__init__.py).
"""
import math
import os
import subprocess

from .base import PathPlanner, Step, INF

# 도우미 실행 파일 경로. 환경 변수 FRYBOT_RMF_SERVER 로 바꿀 수 있음
SERVER = os.environ.get('FRYBOT_RMF_SERVER', os.path.expanduser('~/frybot_ws/build/rmf_bridge/rmf_plan_server'))
HOLD_CAP = 3600.0          # "for ever" in the schedule


def available():
    """도우미 실행 파일이 있고 실행할 수 있는지.

    Returns:
        bool: SERVER 가 실행 가능한 파일이면 True.
    """
    return os.path.isfile(SERVER) and os.access(SERVER, os.X_OK)


class RmfServer:
    """One helper process holding the nav graph.

    도우미 프로세스 하나를 띄우고 로드맵을 'G' 명령으로 한 번 보낸다.
    노드 이름은 정렬 순서의 번호(index)로 바꿔 주고받는다.
    rmf_task 스케줄러(schedulers/rmf_task.py)도 이 클래스를 쓴다.

    Args:
        graph: 로드맵(layout.Graph).
        safe_dist: 두 로봇 중심 사이 최소 거리(m). 반씩 나눠
            footprint·vicinity 반지름으로 보냄.
    """

    def __init__(self, graph, safe_dist=0.155):
        self.proc = subprocess.Popen([SERVER], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
        self.graph = graph
        self.ids = sorted(graph.nodes)  # 번호 -> 노드 이름
        self.index = {n: i for i, n in enumerate(self.ids)}  # 이름 -> 번호
        r = safe_dist / 2.0               # footprint + vicinity = minimum centre distance between two robots
        lines = [f'G {len(self.ids)} {len(graph.edges)} {r} {r}']
        lines += [f'{graph.nodes[n][0]} {graph.nodes[n][1]}' for n in self.ids]
        lines += [f'{self.index[a]} {self.index[b]}' for a, b in graph.edges]
        self.send(lines)
        self.proc.stdout.readline()  # 'OK 0' 응답을 읽고 버림

    def alive(self):
        """도우미 프로세스가 아직 살아 있는지.

        Returns:
            bool: 종료되지 않았으면 True.
        """
        return self.proc.poll() is None

    def send(self, lines):
        """줄 목록을 도우미 표준 입력으로 보낸다.

        Args:
            lines: 보낼 줄(줄바꿈 없이) 목록.
        """
        self.proc.stdin.write('\n'.join(lines) + '\n')
        self.proc.stdin.flush()

    def line(self):
        """도우미 응답 한 줄을 읽어 공백으로 나눈다.

        Returns:
            list[str]: 낱말 목록. 도우미가 끝났으면 빈 목록.
        """
        return self.proc.stdout.readline().split()

    def close(self):
        """도우미 프로세스를 끝낸다(이미 끝났어도 오류 없음)."""
        try:
            self.proc.kill()
        except Exception:
            pass

    def obstacles(self, table, base):
        """Other robots' motion as schedule itineraries: lines for the helper + their count.

        table.itineraries(FleetCore._table 이 채움)의 시각을 base 기준
        상대 시각으로 바꾸고, HOLD_CAP 으로 자른다. 시각이 앞 점보다 1 ms
        이상 늦지 않은 점은 같은 노드면 버리고, 다른 노드면 앞 점 + 1 ms 로
        민다. 남은 점이 2개 미만인 로봇은 뺀다.

        Args:
            table: 다른 로봇의 예약표(ReservationTable).
            base: 기준 시각(초). 요청의 t0.

        Returns:
            tuple[list[str], int]: 'O npts' 와 'x y t' 줄들, 장애물 수.
        """
        lines, k = [], 0
        for pts in getattr(table, 'itineraries', []):
            out, last = [], -INF
            for node, t in pts:
                t = min(t, base + HOLD_CAP) - base
                if t <= last + 1e-3:
                    if out and out[-1][0] == node:
                        continue
                    t = last + 1e-3
                out.append((node, t))
                last = t
            if len(out) < 2:
                continue
            k += 1
            lines.append(f'O {len(out)}')
            lines += [f'{self.graph.nodes[n][0]} {self.graph.nodes[n][1]} {t}' for n, t in out]
        return lines, k

    def read_route(self, count, base, req):
        """count trajectory points "x y t" -> list[Step] on roadmap nodes (None if it leaves the roadmap).

        노드에서 2 cm 안의 점만 그 노드로 보고, RMF 가 한 동작으로 합친
        일직선 통로는 _between() 으로 중간 노드를 시각 보간해 채운다.

        Args:
            count: 읽을 궤적 점 수.
            base: 응답 시각에 더할 기준 시각(초).
            req: 계획 요청(PlanRequest). 출발·목적 확인과 goal_hold 에 씀.

        Returns:
            list[Step] | None: 경로. 출발·목적이 맞지 않으면 None.
        """
        g = self.graph
        seq = []
        for _ in range(count):
            x, y, t = (float(v) for v in self.proc.stdout.readline().split())
            n = g.nearest_node(x, y)
            # points just before / after a node (acceleration phases) belong to that node
            if math.hypot(g.nodes[n][0] - x, g.nodes[n][1] - y) > 0.02:
                continue
            if seq and seq[-1][0] == n:
                seq[-1][2] = t + base
            else:
                seq.append([n, t + base, t + base])
        # seq 항목: [노드, 도착 시각, 마지막으로 그 노드에 있던 시각]
        if not seq or seq[0][0] != req.start:
            return None
        steps = [Step(seq[0][0], req.t0, max(req.t0, seq[0][2]))]
        for (a, _, da), (b, ab, db) in zip(seq, seq[1:]):
            mid = _between(g, a, b, da, ab)
            if mid is None:
                return None
            for n, t in mid[:-1]:
                steps.append(Step(n, t, t))
            steps.append(Step(b, ab, db))
        if steps[-1].node != req.goal:
            return None
        last = steps[-1]
        last.depart = last.arrive + (req.goal_hold if req.goal_hold < INF else 0.0)
        return steps


def _between(graph, a, b, ta, tb):
    """RMF merges collinear lanes into one motion: the roadmap nodes passed from a to b (excluding a, including b)
    with interpolated times. None when a and b are not joined by a straight run of lanes.

    a-b 선분 위(수직 거리 1 mm 미만)의 노드를 순서대로 모아, 이웃끼리
    통로로 이어져 있는지 확인한다. 시각은 선분 위 비율로 선형 보간.
    """
    if any(n == b for n, _ in graph.adj[a]):
        return [(b, tb)]
    (ax, ay), (bx, by) = graph.nodes[a], graph.nodes[b]
    L = math.hypot(bx - ax, by - ay)
    mid = []
    for n, (x, y) in graph.nodes.items():
        if n in (a, b):
            continue
        s = ((x - ax) * (bx - ax) + (y - ay) * (by - ay)) / (L * L)
        if 0.0 < s < 1.0 and abs((x - ax) * (by - ay) - (y - ay) * (bx - ax)) / L < 1e-3:
            mid.append((s, n))
    chain = [a] + [n for _, n in sorted(mid)] + [b]
    for u, v in zip(chain, chain[1:]):
        if not any(n == v for n, _ in graph.adj[u]):
            return None
    return [(n, ta + s * (tb - ta)) for s, n in sorted(mid)] + [(b, tb)]


class RmfPlanner(PathPlanner):
    """Open-RMF agv::Planner 플래너(PLANNERS['rmf'], 도우미가 있을 때)."""

    name = 'rmf'
    coordinated = True
    description = 'Open-RMF rmf_traffic 경로 계획 (교통 스케줄 + 시간 확장 탐색)'

    def __init__(self):
        self.server = None  # RmfServer, 처음 계획할 때 띄움

    # 도우미가 없거나 죽었으면 새로 띄움. 그래프가 바뀌어도 다시 보내지
    # 않음(살아 있는 도우미를 그대로 씀, 확인 필요: 실행 중 지도 교체)
    def _srv(self, graph):
        if self.server is None or not self.server.alive():
            self.server = RmfServer(graph)
        return self.server

    def __del__(self):
        if self.server:
            self.server.close()

    def plan(self, graph, req, table):
        """도우미의 'P' 명령으로 교통 스케줄을 피하는 경로를 받는다.

        req.overhead 는 쓰지 않는다(도우미가 속도만 받음).

        Args:
            graph: 로드맵(layout.Graph).
            req: 계획 요청(PlanRequest).
            table: 다른 로봇의 예약표. itineraries 만 씀.

        Returns:
            list[Step] | None: 경로. 도우미가 FAIL 이거나 경로가 로드맵을
            벗어나면 None.
        """
        srv = self._srv(graph)
        if req.start == req.goal:  # 제자리: 도우미에 묻지 않음
            return [Step(req.start, req.t0, req.t0 + (req.goal_hold if req.goal_hold < INF else 0.0))]
        lines, k = srv.obstacles(table, req.t0)
        srv.send([f'P {srv.index[req.start]} {srv.index[req.goal]} {req.speed} {k}'] + lines)
        head = srv.line()
        if not head or head[0] != 'OK':
            return None
        return srv.read_route(int(head[1]), req.t0, req)


class RmfNegotiationPlanner(RmfPlanner):
    """rmf + Open-RMF negotiation. Whenever a robot starts a move while others are on their way, all of them
    negotiate (each proposes an itinerary, the others accommodate or reject it) and adopt the agreed itineraries.
    Without an agreement inside the time budget the robot plans alone, like `rmf`."""
    name = 'rmf_nego'
    joint = True
    description = 'Open-RMF rmf_traffic 경로 계획 + 로봇 간 협상(negotiation)'
    budget = 1.0          # wall seconds per negotiation

    def plan_joint(self, graph, reqs, static):
        """도우미의 'N' 명령으로 여러 로봇이 협상한 경로를 받는다.

        Args:
            graph: 로드맵(layout.Graph).
            reqs: 함께 계획할 로봇들의 PlanRequest 목록.
            static: 계획하지 않는 로봇들의 예약표(itineraries 만 씀).

        Returns:
            dict[str, list[Step]] | None: 로봇 이름 -> 경로. 협상 실패나
            한 대라도 경로가 없으면 None(관제가 혼자 계획으로 되돌림).
        """
        srv = self._srv(graph)
        base = min(r.t0 for r in reqs)  # 상대 시각의 기준(가장 이른 t0)
        lines, k = srv.obstacles(static, base)
        head = [f'N {len(reqs)} {k} {self.budget}']
        head += [f'{srv.index[r.start]} {srv.index[r.goal]} {r.speed} {r.t0 - base}' for r in reqs]
        srv.send(head + lines)
        if srv.line()[:1] != ['OK']:
            return None
        plans, ok = {}, True
        for r in reqs:                         # always read every route so the stream stays in sync
            tag = srv.line()
            steps = srv.read_route(int(tag[1]), base, r) if int(tag[1]) else None
            if steps is None and r.start == r.goal:
                steps = [Step(r.start, r.t0, r.t0 + (r.goal_hold if r.goal_hold < INF else 0.0))]
            ok = ok and steps is not None
            plans[r.robot_id] = steps
        return plans if ok else None
