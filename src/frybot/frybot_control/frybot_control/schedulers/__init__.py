"""Task scheduler plug-ins. assign() matches pending AMR tasks to available robots.

cost(robot, task) -> estimated seconds for the robot to reach the task's first stop.
Add a new algorithm: subclass Scheduler and register it in SCHEDULERS.
"""
import itertools


class Scheduler:
    name = 'base'
    description = ''
    uses_eta = False      # cost() = planner ETA incl. reservation waits instead of static distance
    rebalance = False     # re-evaluate assigned-but-unstarted tasks

    def assign(self, tasks, robots, cost, now):
        """Return list[(task, robot)]. tasks have .priority (higher = more urgent) and .created."""
        raise NotImplementedError


class FifoNearestScheduler(Scheduler):
    name = 'fifo_nearest'
    description = '기준선: 접수 순서대로 가장 가까운 가용 AMR'

    def assign(self, tasks, robots, cost, now):
        free, out = list(robots), []
        for t in sorted(tasks, key=lambda t: t.created):
            if not free:
                break
            r = min(free, key=lambda r: cost(r, t))
            free.remove(r)
            out.append((t, r))
        return out


class PriorityGreedyScheduler(Scheduler):
    name = 'priority_greedy'
    description = '우선순위(+대기 시간 가산) 순서대로 가장 가까운 가용 AMR'
    aging = 0.05        # priority points per waiting second

    def assign(self, tasks, robots, cost, now):
        free, out = list(robots), []
        for t in sorted(tasks, key=lambda t: -(t.priority + self.aging * (now - t.created))):
            if not free:
                break
            r = min(free, key=lambda r: cost(r, t))
            free.remove(r)
            out.append((t, r))
        return out


class HungarianScheduler(Scheduler):
    name = 'hungarian'
    description = '최소 비용 매칭(헝가리안): 이동 시간 - 우선순위 - 대기 시간 가산을 전체 합으로 최소화'
    w_priority = 6.0    # seconds of travel one priority point is worth
    w_age = 0.5         # seconds of travel one waiting second is worth

    def assign(self, tasks, robots, cost, now):
        if not tasks or not robots:
            return []
        c = [[cost(r, t) - self.w_priority * t.priority - self.w_age * (now - t.created) for t in tasks]
             for r in robots]
        try:
            from scipy.optimize import linear_sum_assignment
            rows, cols = linear_sum_assignment(c)
            return [(tasks[j], robots[i]) for i, j in zip(rows, cols)]
        except Exception:
            n, m = len(robots), len(tasks)
            k = min(n, m)
            best, best_cost = [], float('inf')
            for rs in itertools.permutations(range(n), k):
                for ts in itertools.combinations(range(m), k):
                    s = sum(c[i][j] for i, j in zip(rs, ts))
                    if s < best_cost:
                        best, best_cost = list(zip(rs, ts)), s
            return [(tasks[j], robots[i]) for i, j in best]


class HungarianEtaScheduler(HungarianScheduler):
    """Same matching, but the cost is the reservation-aware arrival time: the planner is asked when each candidate
    AMR could really reach the task's first stop given the aisle reservations of the other robots."""
    name = 'hungarian_eta'
    description = '예약 기반 ETA 매칭: 통로 예약 대기를 포함한 도착 예상 시각으로 비용 계산'
    uses_eta = True


class HungarianEtaRollingScheduler(HungarianEtaScheduler):
    """ETA matching + event-driven rolling horizon: tasks whose AMR has not reached the first stop yet are
    re-evaluated every few seconds and handed to a better AMR. Guests being guided and loaded food are never moved."""
    name = 'hungarian_eta_rh'
    description = '예약 기반 ETA + 롤링 호라이즌: 아직 시작 지점에 닿지 않은 임무를 주기적으로 재배정'
    rebalance = True
    rebalance_period = 2.0
    rebalance_gain = 5.0      # seconds the swap must save


SCHEDULERS = {c.name: c for c in (HungarianScheduler, HungarianEtaScheduler, HungarianEtaRollingScheduler,
                                         PriorityGreedyScheduler, FifoNearestScheduler)}
DEFAULT_SCHEDULER = 'hungarian'


def make_scheduler(name):
    if name not in SCHEDULERS:
        raise KeyError(f'unknown scheduler {name!r}; available: {sorted(SCHEDULERS)}')
    return SCHEDULERS[name]()
