"""Task scheduler plug-ins. assign() matches pending AMR tasks to available robots.

cost(robot, task) -> estimated seconds for the robot to reach the task's first stop.
Add a new algorithm: subclass Scheduler and register it in SCHEDULERS.

임무 배정기(스케줄러) 등록부. SCHEDULERS 의 키가 런치 인자 scheduler:=,
관리자 화면, fleet_bench 의 --schedulers 에 쓰는 이름이다. 관제
(FleetCore)가 대기 중인 AMR 임무와 가용 로봇을 넘겨 assign() 을 부른다.
"""
import itertools
import math


class Scheduler:
    """배정기 기반 클래스. 새 배정기는 이것을 상속해 assign() 을 구현한다.

    rebalance=True 면 관제가 rebalance_period 초마다 아직 첫 지점에 닿지
    않은 임무를 다시 평가해, rebalance_gain 초 넘게 줄면 재배정한다.
    """

    name = 'base'  # SCHEDULERS 등록 이름(런치 인자·화면에 쓰임)
    description = ''  # 관리자 화면에 보이는 설명
    uses_eta = False      # cost() = planner ETA incl. reservation waits instead of static distance
    rebalance = False     # re-evaluate assigned-but-unstarted tasks

    def assign(self, tasks, robots, cost, now):
        """Return list[(task, robot)]. tasks have .priority (higher = more urgent) and .created.

        Args:
            tasks: 배정할 임무 목록.
            robots: 지금 임무를 받을 수 있는 로봇 목록.
            cost: cost(robot, task) -> 첫 지점까지 예상 초.
            now: 관제 현재 시각(초). 대기 시간 가산에 씀.

        Raises:
            NotImplementedError: 하위 클래스가 구현하지 않았을 때.
        """
        raise NotImplementedError


class FifoNearestScheduler(Scheduler):
    """기준선: 접수 순서대로 가장 가까운(비용 최소) 로봇에 배정."""

    name = 'fifo_nearest'
    description = '기준선: 접수 순서대로 가장 가까운 가용 AMR'

    def assign(self, tasks, robots, cost, now):
        """오래된 임무부터 남은 로봇 중 비용 최소 로봇을 하나씩 짝짓는다.

        Args:
            tasks: 배정할 임무 목록(.created 사용).
            robots: 가용 로봇 목록.
            cost: cost(robot, task) -> 예상 초.
            now: 쓰지 않음.

        Returns:
            list[tuple]: (task, robot) 목록. 로봇이 모자라면 남은 임무는 빠짐.
        """
        free, out = list(robots), []
        for t in sorted(tasks, key=lambda t: t.created):
            if not free:
                break
            r = min(free, key=lambda r: cost(r, t))
            free.remove(r)
            out.append((t, r))
        return out


class PriorityGreedyScheduler(Scheduler):
    """기준선: (우선순위 + 대기 가산) 높은 임무부터 가장 가까운 로봇에 배정."""

    name = 'priority_greedy'
    description = '우선순위(+대기 시간 가산) 순서대로 가장 가까운 가용 AMR'
    aging = 0.05        # priority points per waiting second

    def assign(self, tasks, robots, cost, now):
        """급한 임무부터 남은 로봇 중 비용 최소 로봇을 하나씩 짝짓는다.

        Args:
            tasks: 배정할 임무 목록(.priority, .created 사용).
            robots: 가용 로봇 목록.
            cost: cost(robot, task) -> 예상 초.
            now: 관제 현재 시각(초).

        Returns:
            list[tuple]: (task, robot) 목록.
        """
        free, out = list(robots), []
        for t in sorted(tasks, key=lambda t: -(t.priority + self.aging * (now - t.created))):
            if not free:
                break
            r = min(free, key=lambda r: cost(r, t))
            free.remove(r)
            out.append((t, r))
        return out


class MinCostScheduler(Scheduler):
    """Minimum-cost assignment (linear assignment problem): pick the robot-task pairs whose summed cost is smallest.

    Solver choice: with 3 robots there are at most a few hundred candidate assignments, so an exhaustive search
    finds the exact minimum in well under a millisecond, needs no external library and always picks the same
    assignment on ties. That is the solver used at the current fleet size. The number of candidates grows
    factorially with the fleet, so beyond MAX_EXHAUSTIVE candidates a polynomial O(n^3) solver of the Hungarian
    family is used instead: SciPy's linear_sum_assignment (a modified Jonker-Volgenant shortest augmenting path
    algorithm). Kuhn's Hungarian method itself is not implemented. Both solvers return a minimum-cost assignment;
    they can differ only when several assignments tie for the minimum.
    The names 'hungarian*' used before 2026-11-13 are still accepted (LEGACY_NAMES)."""
    name = 'min_cost'
    description = '최소 비용 배정: (이동 시간 - 우선순위 - 대기 시간 가산)의 전체 합이 최소인 배정. 풀이: 3대 규모는 전수 탐색, 대규모는 SciPy(Jonker-Volgenant)'
    w_priority = 6.0    # seconds of travel one priority point is worth
    w_age = 0.5         # seconds of travel one waiting second is worth
    MAX_EXHAUSTIVE = 20000   # candidate assignments up to which exhaustive search is used (3 robots: <= 720 for 10 tasks)

    def assign(self, tasks, robots, cost, now):
        """보정 비용의 합이 최소인 (임무, 로봇) 짝을 고른다.

        Args:
            tasks: 배정할 임무 목록(.priority, .created 사용).
            robots: 가용 로봇 목록.
            cost: cost(robot, task) -> 예상 초.
            now: 관제 현재 시각(초).

        Returns:
            list[tuple]: (task, robot) 목록. min(로봇 수, 임무 수) 쌍.
        """
        if not tasks or not robots:
            return []
        # 비용 행렬 c[로봇][임무] = 이동 초 - 우선순위·대기 가산(초 환산)
        c = [[cost(r, t) - self.w_priority * t.priority - self.w_age * (now - t.created) for t in tasks]
             for r in robots]
        n, m = len(robots), len(tasks)
        k = min(n, m)  # 만들 짝의 수
        # 후보 수 = 로봇 k 대 순열 x 임무 k 건 조합. 많으면 SciPy 로 풂
        if math.perm(n, k) * math.comb(m, k) > self.MAX_EXHAUSTIVE:
            try:
                from scipy.optimize import linear_sum_assignment
                rows, cols = linear_sum_assignment(c)
                return [(tasks[j], robots[i]) for i, j in zip(rows, cols)]
            except ImportError:
                pass        # no SciPy: fall back to the exhaustive search (slow for large fleets)
        best, best_cost = [], float('inf')       # exhaustive search; the first minimum found wins ties
        for rs in itertools.permutations(range(n), k):
            for ts in itertools.combinations(range(m), k):
                s = sum(c[i][j] for i, j in zip(rs, ts))
                if s < best_cost:
                    best, best_cost = list(zip(rs, ts)), s
        return [(tasks[j], robots[i]) for i, j in best]


# uses_eta=True: 관제가 cost 를 플래너 ETA(예약 대기 포함)로 계산해 넘김
class MinCostEtaScheduler(MinCostScheduler):
    """Same assignment, but the cost is the reservation-aware arrival time: the planner is asked when each candidate
    AMR could really reach the task's first stop given the aisle reservations of the other robots."""
    name = 'min_cost_eta'
    description = '예약 기반 ETA 최소 비용 배정: 통로 예약 대기를 포함한 도착 예상 시각으로 비용 계산'
    uses_eta = True


class MinCostEtaRollingScheduler(MinCostEtaScheduler):
    """ETA assignment + event-driven rolling horizon: tasks whose AMR has not reached the first stop yet are
    re-evaluated every few seconds and handed to a better AMR. Guests being guided and loaded food are never moved."""
    name = 'min_cost_eta_rh'
    description = '예약 기반 ETA 최소 비용 배정 + 롤링 호라이즌: 아직 시작 지점에 닿지 않은 임무를 주기적으로 재배정'
    rebalance = True
    rebalance_period = 2.0  # 재평가 주기(초)
    rebalance_gain = 5.0      # seconds the swap must save


# 이름 -> 배정기 클래스. 새 배정기는 이 튜플에 클래스를 더해 등록함
SCHEDULERS = {c.name: c for c in (MinCostScheduler, MinCostEtaScheduler, MinCostEtaRollingScheduler,
                                         PriorityGreedyScheduler, FifoNearestScheduler)}
DEFAULT_SCHEDULER = 'min_cost_eta_rh'  # 관제의 기본 배정기 이름
# names used before 2026-11-13 (old launch args, CSVs and logs); accepted by make_scheduler, not listed in the UI
LEGACY_NAMES = {'hungarian': 'min_cost', 'hungarian_eta': 'min_cost_eta', 'hungarian_eta_rh': 'min_cost_eta_rh'}

from .rmf_task import RmfTaskScheduler, available as _rmf_available      # noqa: E402
if _rmf_available():          # Open-RMF back end: only when its helper has been built (see planners/rmf.py)
    SCHEDULERS[RmfTaskScheduler.name] = RmfTaskScheduler


def make_scheduler(name):
    """이름으로 배정기 객체를 새로 만든다(옛 이름 hungarian* 도 받음).

    Args:
        name: SCHEDULERS 또는 LEGACY_NAMES 의 이름.

    Returns:
        Scheduler 하위 클래스의 새 인스턴스.

    Raises:
        KeyError: 등록되지 않은 이름일 때.
    """
    name = LEGACY_NAMES.get(name, name)
    if name not in SCHEDULERS:
        raise KeyError(f'unknown scheduler {name!r}; available: {sorted(SCHEDULERS)}')
    return SCHEDULERS[name]()
