"""Open-RMF task allocation (rmf_task::TaskPlanner) as a scheduler plug-in.

[수정 2026-11-18] W6: 외부 도우미가 속도만 받아 관제의 구간
지연(plan_overhead)은 배정 비용에 들어가지 않음.

Every pending AMR task becomes an rmf_task Delivery request (first stop + waiting time there, last stop + waiting
time there, high / low priority). Every AMR is an agent: a free one from where it stands now, a busy one from where
and when its current task is expected to end. rmf_task then builds a task queue per AMR that minimises its cost
(travel time from Open-RMF's planner, without traffic). A free AMR gets the first task of its queue now; tasks
queued behind a busy AMR stay pending and are planned again at the next call, as when Open-RMF re-plans on a new
request. Battery is switched off (a very large battery), like in the other schedulers of this comparison.

Open-RMF 비교용 배정기. 도우미(rmf_plan_server)의 T 명령으로
rmf_task::TaskPlanner 를 부르고, 도우미가 없거나 실패하면
MinCostScheduler 의 배정으로 대신한다. 도우미가 빌드된 경우에만
SCHEDULERS 에 등록된다(schedulers/__init__.py).
"""
from ..planners.rmf import RmfServer, available            # noqa: F401
from . import MinCostScheduler


class RmfTaskScheduler(MinCostScheduler):
    """rmf_task::TaskPlanner 로 로봇별 임무 대기열을 짜는 배정기.

    대기열의 첫 임무만 지금 빈 로봇에 배정하고, 나머지는 다음 호출에서
    다시 계획한다.
    """

    name = 'rmf_task'
    description = 'Open-RMF rmf_task 임무 배정 (로봇별 임무 대기열 최적화)'
    uses_eta = False  # 관제의 cost 는 대신 배정(MinCost)에서만 씀
    rebalance = False  # 롤링 호라이즌 재배정 안 함
    core = None              # set by FleetCore

    def __init__(self):
        self.server = None  # 도우미 프로세스(RmfServer). 첫 assign 때 띄움

    # 배정기가 버려질 때 도우미 프로세스를 끝냄
    def __del__(self):
        if self.server:
            self.server.close()

    def _remaining(self, r):
        """(node, seconds) where and when a busy robot is expected to finish its current task.

        남은 move 단계는 그래프 최단 거리 / 속도(GUIDE 는 안내 속도),
        arm 단계는 작업 시간으로 더한다(통로 대기는 넣지 않음). 지금
        하는 팔 작업은 arm_until 까지 남은 시간으로 이미 셌으므로 뺀다.
        """
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
        """도우미의 임무 대기열로 (임무, 로봇) 짝을 고른다.

        Args:
            tasks: 배정할 임무 목록(.phases, .priority 사용).
            robots: 지금 임무를 받을 수 있는 로봇 목록.
            cost: cost(robot, task) -> 예상 초. 대신 배정에서만 씀.
            now: 관제 현재 시각(초). 대신 배정에서만 씀.

        Returns:
            list[tuple]: (task, robot) 목록. 대기열 첫 임무가 있는 빈
            로봇만 나옴. 관제가 없거나 도우미가 실패하면 MinCost 배정.
        """
        c = self.core
        if c is None or not tasks or not robots:
            return super().assign(tasks, robots, cost, now)
        g = c.graph
        # 도우미가 없거나 죽었으면 새로 띄우고 로드맵을 보냄
        if self.server is None or not self.server.alive():
            self.server = RmfServer(g)
        srv, free = self.server, {r.id for r in robots}
        # 에이전트: 빈 로봇 + 임무 중인(연결됨, 비상 정지 아님) 로봇
        agents = [r for r in c.robots.values() if r.id in free or (r.online and not r.estop and r.task is not None)]
        # T 명령 머리줄: 속도, 에이전트 수, 임무 수, 탐욕 풀이(임무 5건 초과)
        lines = [f'T {c.speed} {len(agents)} {len(tasks)} {1 if len(tasks) > 5 else 0}']
        # 에이전트마다 "출발 노드 번호, 출발 가능 시각(지금부터 초)"
        for r in agents:
            node, t = (r.heading or r.node, 0.0) if r.id in free else self._remaining(r)
            lines.append(f'{srv.index[node]} {t}')
        # 임무마다 "id, 첫 지점, 대기, 마지막 지점, 대기, 0(최소 시작 시각),
        # 높은 우선순위(priority 3 이상이면 1)". 대기는 그 move 바로 뒤
        # arm 단계의 작업 시간
        for t in tasks:
            moves = [(i, ph) for i, ph in enumerate(t.phases) if ph[0] == 'move']
            wait = lambda i: sum(ph[2] for ph in t.phases[i + 1:i + 2] if ph[0] == 'arm')
            (i0, first), (i1, last) = moves[0], moves[-1]
            lines.append(f'{t.id} {srv.index[g.resolve(first[1])]} {wait(i0)} {srv.index[g.resolve(last[1])]} {wait(i1)} '
                         f'0 {1 if t.priority >= 3 else 0}')
        srv.send(lines)
        # 응답: "OK" 뒤 에이전트 순서대로 "A n" + 임무 줄 n 개. 실패면 대신 배정
        if srv.line()[:1] != ['OK']:
            return super().assign(tasks, robots, cost, now)
        by_id, by_robot, out = {t.id: t for t in tasks}, {r.id: r for r in robots}, []
        for r in agents:
            n = int(srv.line()[1])
            queue = [srv.line()[0] for _ in range(n)]
            if queue and r.id in free:
                out.append((by_id[queue[0]], by_robot[r.id]))
        return out
