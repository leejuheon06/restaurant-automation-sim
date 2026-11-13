"""Open-RMF traffic planning (rmf_traffic) as a planner plug-in.

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
"""
import math
import os
import subprocess

from .base import PathPlanner, Step, INF

SERVER = os.environ.get('FRYBOT_RMF_SERVER', os.path.expanduser('~/frybot_ws/build/rmf_bridge/rmf_plan_server'))
HOLD_CAP = 3600.0          # "for ever" in the schedule


def available():
    return os.path.isfile(SERVER) and os.access(SERVER, os.X_OK)


class RmfServer:
    """One helper process holding the nav graph."""

    def __init__(self, graph, safe_dist=0.155):
        self.proc = subprocess.Popen([SERVER], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
        self.graph = graph
        self.ids = sorted(graph.nodes)
        self.index = {n: i for i, n in enumerate(self.ids)}
        r = safe_dist / 2.0               # footprint + vicinity = minimum centre distance between two robots
        lines = [f'G {len(self.ids)} {len(graph.edges)} {r} {r}']
        lines += [f'{graph.nodes[n][0]} {graph.nodes[n][1]}' for n in self.ids]
        lines += [f'{self.index[a]} {self.index[b]}' for a, b in graph.edges]
        self.send(lines)
        self.proc.stdout.readline()

    def alive(self):
        return self.proc.poll() is None

    def send(self, lines):
        self.proc.stdin.write('\n'.join(lines) + '\n')
        self.proc.stdin.flush()

    def line(self):
        return self.proc.stdout.readline().split()

    def close(self):
        try:
            self.proc.kill()
        except Exception:
            pass

    def obstacles(self, table, base):
        """Other robots' motion as schedule itineraries: lines for the helper + their count."""
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
        """count trajectory points "x y t" -> list[Step] on roadmap nodes (None if it leaves the roadmap)."""
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
    with interpolated times. None when a and b are not joined by a straight run of lanes."""
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
    name = 'rmf'
    coordinated = True
    description = 'Open-RMF rmf_traffic 경로 계획 (교통 스케줄 + 시간 확장 탐색)'

    def __init__(self):
        self.server = None

    def _srv(self, graph):
        if self.server is None or not self.server.alive():
            self.server = RmfServer(graph)
        return self.server

    def __del__(self):
        if self.server:
            self.server.close()

    def plan(self, graph, req, table):
        srv = self._srv(graph)
        if req.start == req.goal:
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
        srv = self._srv(graph)
        base = min(r.t0 for r in reqs)
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
