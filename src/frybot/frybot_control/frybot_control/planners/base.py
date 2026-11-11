"""Path planner plug-in interface + shared reservation table.

Lock semantics shared by every planner and by the runtime traffic layer:
a robot holds node n[i] from the moment it departs n[i-1] until it arrives at n[i+1].
"""
import bisect
import math
from dataclasses import dataclass, field

INF = float('inf')


@dataclass
class Step:
    node: str
    arrive: float
    depart: float          # earliest departure toward the next node (last step: arrive + hold)


@dataclass
class PlanRequest:
    robot_id: str
    start: str
    goal: str
    t0: float
    speed: float
    goal_hold: float = 5.0          # seconds the goal must stay free after arrival
    blocked: frozenset = frozenset()  # nodes that must not be used (uncoordinated replans)


class ReservationTable:
    def __init__(self, pad=0.4, conflict=None):
        self.res = {}        # node -> sorted list of (t0, t1, owner)
        self.pad = pad
        self.conflict = conflict or {}   # node -> nodes too close to be occupied at the same time

    def add(self, node, t0, t1, owner):
        for n in (node, *self.conflict.get(node, ())):
            bisect.insort(self.res.setdefault(n, []), (t0 - self.pad, t1 + self.pad, owner))

    def add_raw(self, node, t0, t1, owner):
        bisect.insort(self.res.setdefault(node, []), (t0, t1, owner))

    def copy(self):
        c = ReservationTable(self.pad, self.conflict)
        c.res = {k: list(v) for k, v in self.res.items()}
        return c

    def add_plan(self, owner, steps, last_hold=INF):
        """Reserve a (remaining) plan using the lock semantics above."""
        for i, s in enumerate(steps):
            t0 = steps[i - 1].depart if i > 0 else s.arrive
            t1 = steps[i + 1].arrive if i + 1 < len(steps) else (s.arrive + last_hold)
            self.add(s.node, t0, t1, owner)

    def safe_intervals(self, node, t_from=0.0):
        out, t = [], t_from
        for a, b, _ in self.res.get(node, []):
            if b <= t:
                continue
            if a > t:
                out.append((t, a))
            t = max(t, b)
            if t == INF:
                break
        if t < INF:
            out.append((t, INF))
        return out

    def is_free(self, node, a, b):
        for r0, r1, _ in self.res.get(node, []):
            if r0 < b and a < r1:
                return False
        return True

    def first_block_after(self, node, t):
        for r0, r1, _ in self.res.get(node, []):
            if r1 > t and r0 > t:
                return r0
        return INF


class PathPlanner:
    name = 'base'
    coordinated = True      # False: plans ignore other robots (runtime locks only)
    joint = False           # True: has plan_joint() and re-plans all moving robots together
    description = ''

    def plan(self, graph, req: PlanRequest, table: ReservationTable):
        """Return list[Step] from req.start to req.goal, or None when no plan exists."""
        raise NotImplementedError


def start_interval_end(table, node, t0, grace=3.0):
    """We physically stand on the start node, so it is usable from t0 until the next foreign reservation
    (at least `grace` seconds so that an already-conflicting reservation still lets us back off)."""
    return max(table.first_block_after(node, t0), t0 + grace) if not table.is_free(node, t0, t0 + 1e-3) \
        else max(table.first_block_after(node, t0), t0 + 1e-3)
