"""Open-RMF task allocation (rmf_task::TaskPlanner) as a scheduler plug-in.

Every pending AMR task becomes an rmf_task Delivery request (first stop + waiting time there, last stop + waiting
time there, high / low priority). Every AMR is an agent: a free one from where it stands now, a busy one from where
and when its current task is expected to end. rmf_task then builds a task queue per AMR that minimises its cost
(travel time from Open-RMF's planner, without traffic). A free AMR gets the first task of its queue now; tasks
queued behind a busy AMR stay pending and are planned again at the next call, as when Open-RMF re-plans on a new
request. Battery is switched off (a very large battery), like in the other schedulers of this comparison.
"""
from ..planners.rmf import RmfServer, available            # noqa: F401
from . import MinCostScheduler


class RmfTaskScheduler(MinCostScheduler):
    name = 'rmf_task'
    description = 'Open-RMF rmf_task 임무 배정 (로봇별 임무 대기열 최적화)'
    uses_eta = False
    rebalance = False
    core = None              # set by FleetCore

    def __init__(self):
        self.server = None

    def __del__(self):
        if self.server:
            self.server.close()

    def _remaining(self, r):
        """(node, seconds) where and when a busy robot is expected to finish its current task."""
        c, g = self.core, self.core.graph
        cur, t = r.heading or r.node, max(0.0, r.arm_until - c.now) if r.arm_busy else 0.0
        task = r.task
        if task is None:
            return cur, t
        for ph in task.phases[task.pi:]:
            if ph[0] == 'move':
                goal = g.resolve(ph[1])
                v = c.guide_speed if ph[2] == 'GUIDE' else c.speed
                t += g.shortest_dist(cur, goal) / v
                cur = goal
            elif ph[0] == 'arm' and not (r.arm_busy and ph is task.phases[task.pi]):
                t += ph[2]
        return cur, t

    def assign(self, tasks, robots, cost, now):
        c = self.core
        if c is None or not tasks or not robots:
            return super().assign(tasks, robots, cost, now)
        g = c.graph
        if self.server is None or not self.server.alive():
            self.server = RmfServer(g)
        srv, free = self.server, {r.id for r in robots}
        agents = [r for r in c.robots.values() if r.id in free or (r.online and not r.estop and r.task is not None)]
        lines = [f'T {c.speed} {len(agents)} {len(tasks)} {1 if len(tasks) > 5 else 0}']
        for r in agents:
            node, t = (r.heading or r.node, 0.0) if r.id in free else self._remaining(r)
            lines.append(f'{srv.index[node]} {t}')
        for t in tasks:
            moves = [(i, ph) for i, ph in enumerate(t.phases) if ph[0] == 'move']
            wait = lambda i: sum(ph[2] for ph in t.phases[i + 1:i + 2] if ph[0] == 'arm')
            (i0, first), (i1, last) = moves[0], moves[-1]
            lines.append(f'{t.id} {srv.index[g.resolve(first[1])]} {wait(i0)} {srv.index[g.resolve(last[1])]} {wait(i1)} '
                         f'0 {1 if t.priority >= 3 else 0}')
        srv.send(lines)
        if srv.line()[:1] != ['OK']:
            return super().assign(tasks, robots, cost, now)
        by_id, by_robot, out = {t.id: t for t in tasks}, {r.id: r for r in robots}, []
        for r in agents:
            n = int(srv.line()[1])
            queue = [srv.line()[0] for _ in range(n)]
            if queue and r.id in free:
                out.append((by_id[queue[0]], by_robot[r.id]))
        return out
