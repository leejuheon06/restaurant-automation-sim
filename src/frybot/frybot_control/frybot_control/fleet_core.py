"""Task Manager core (ROS-independent so it can also run in the offline benchmark).

Responsibilities
  * task queue + scheduler plug-in   -> which AMR takes which GUIDE / SERVE / COLLECT task
  * path planner plug-in             -> timed route on the single-lane roadmap
  * traffic layer                    -> node locks: request / grant / enter / exit, stall detection, replanning
  * cooking cell coordinator         -> cook arms A/B, fryer, wok, hand-off slots (acquire-all-at-once, no deadlock)

All side effects go through a FleetIO object; all inputs arrive via on_* methods and tick(now).
"""
import math
import random
import time
from dataclasses import dataclass, field

from . import device_state
from .layout import Graph, MENU
from .planners import make_planner, PLANNERS, PlanRequest, ReservationTable, Step, INF, DEFAULT_PLANNER
from .schedulers import make_scheduler, SCHEDULERS, DEFAULT_SCHEDULER

AMR_TASKS = ('GUIDE', 'SERVE', 'COLLECT')
PRIORITY = {'GUIDE': 3, 'SERVE': 3, 'COLLECT': 1}


class FleetIO:
    """Outputs of the core. The ROS node and the offline simulator both implement this."""

    def send_route(self, robot_id, task_id, plan_version, mode, visit_id, steps): ...
    def grant(self, robot_id, task_id, plan_version, index): ...
    def cancel_route(self, robot_id): ...
    def arm_job(self, arm_id, task_id, job, duration, params): ...
    def task_event(self, ev: dict): ...
    def log(self, event, **fields): ...


@dataclass
class Task:
    id: str
    type: str
    visit_id: int = 0
    order_id: int = 0
    item_id: int = 0
    table_id: int = 0
    menu: str = ''
    priority: int = 1
    created: float = 0.0
    state: str = 'PENDING'          # PENDING IN_PROGRESS DONE SUSPENDED CANCELED
    robot_id: str = ''
    phases: list = field(default_factory=list)
    pi: int = 0
    carrying: bool = False
    assigned_at: float = 0.0
    finished_at: float = 0.0
    reason: str = ''
    start_node: str = ''
    rebalanced: int = 0             # times the rolling-horizon scheduler moved it to another robot


@dataclass
class Robot:
    id: str
    home: str
    node: str
    speed: float = 0.08
    heading: str = ''               # node we are driving to (locked), '' when standing on `node`
    route: list = None              # list[Step]
    idx: int = 0
    granted: int = 0
    plan_version: int = 0
    mode: str = 'NORMAL'
    goal: str = ''
    pending_goal: tuple = None      # (goal, mode, next_try)
    task: Task = None
    returning: bool = False
    arm_busy: str = ''
    arm_until: float = 0.0
    estop: bool = False
    battery: float = 100.0
    charging: bool = False
    x: float = 0.0
    y: float = 0.0
    yaw: float = 0.0
    sim_state: str = ''
    wait_since: float = None
    blocked_by: str = ''
    last_replan: float = 0.0
    held: set = field(default_factory=set)
    dist: float = 0.0
    online: bool = False
    needs_replan: bool = False
    park: str = ''                  # where this robot waits when idle (charger or standby spot)
    yield_to: str = ''              # robot we stepped aside for; we resume only once it has passed
    yield_from: str = ''            # node we vacated for it
    yield_until: float = 0.0        # give up waiting for it after this time


class CookJob:
    def __init__(self, task, ops):
        self.task, self.ops, self.pc = task, ops, 0
        self.busy = False            # an arm job / timer is running
        self.until = 0.0
        self.retries = 0
        self.wait_doneness_since = None
        self.label = 'QUEUED'


class FleetCore:
    def __init__(self, io: FleetIO, robot_ids=('pinky1', 'pinky2', 'pinky3'), scheduler=DEFAULT_SCHEDULER,
                 planner=DEFAULT_PLANNER, speed=0.08, guide_speed=0.05, cook_time_scale=20.0,
                 stall_timeout=3.0, min_battery=25.0, handoff_slots=3, use_doneness=True,
                 plan_speed_factor=0.9, use_standby=True, standby_min_battery=40.0):
        self.io = io
        self.graph = Graph()
        self.speed, self.guide_speed = speed, guide_speed
        self.cook_scale = cook_time_scale
        self.stall_timeout = stall_timeout
        self.min_battery = min_battery
        self.use_doneness = use_doneness
        self.plan_speed_factor = plan_speed_factor
        self.use_standby, self.standby_min_battery = use_standby, standby_min_battery
        self.scheduler = make_scheduler(scheduler)
        self.scheduler.core = self
        self.planner = make_planner(planner)
        self.robots = {}
        self.locks = {}                      # node -> robot id
        for rid in robot_ids:                 # any number of AMRs: the home spots come from the layout
            home = self.graph.home_of(rid)
            r = Robot(rid, home, home, speed=speed)
            r.x, r.y = self.graph.nodes[home]
            r.held = {home}
            r.park = home
            self.locks[home] = rid
            self.robots[rid] = r
        self.tasks = {}
        self.seq = 0
        # cooking cell
        self.cook_jobs = []
        self.res_owner = {'ARM_A': None, 'ARM_B': None, 'FRYER': None, 'WOK': None}
        self.slots = {'FRY_PICKUP': 0, 'WOK_PICKUP': 0}
        self.slot_cap = handoff_slots
        self.doneness = {}                   # cook task id -> (decision, stamp)
        self.m = dict(grants=0, blocked_wait=0.0, planned_wait=0.0, replans=0, retreats=0, plan_fail=0,
                      plan_calls=0, plan_ms=0.0, tasks_done=0, stalls=0, flips=0, joint_plans=0, joint_fail=0,
                      reassign=0)
        self.now = 0.0
        self._last_tick = None
        self._last_rebalance = 0.0

    # ------------------------------------------------------------------ algorithms (hot swap)
    def set_scheduler(self, name):
        self.scheduler = make_scheduler(name)
        self.scheduler.core = self
        self.io.log('SET_SCHEDULER', result=name)

    def set_planner(self, name):
        self.planner = make_planner(name)
        self.io.log('SET_PLANNER', result=name)
        for r in self.robots.values():        # re-plan running routes with the new algorithm
            if r.route and not r.estop:
                self._start_move(r, r.goal, r.mode, replan=True)

    # ------------------------------------------------------------------ task intake
    def submit_task(self, type, visit_id=0, order_id=0, item_id=0, table_id=0, menu='', priority=0):
        self.seq += 1
        t = Task(f'{type[0]}{self.seq:04d}', type, visit_id, order_id, item_id, table_id, menu,
                 priority or PRIORITY.get(type, 1), self.now)
        self.tasks[t.id] = t
        if type == 'COOK':
            t.state = 'IN_PROGRESS'
            self.cook_jobs.append(CookJob(t, self._recipe(menu)))
        else:
            t.phases = self._program(t)
            t.start_node = self.graph.resolve(t.phases[0][1])
        self.io.log('TASK_SUBMIT', task_id=t.id, visit_id=visit_id, order_id=order_id, result=type, reason=menu)
        return t.id

    def _program(self, t):
        tbl = f'T{t.table_id}:serve'                 # serving / collecting point(s) of the table
        if t.type == 'GUIDE':
            return [('move', 'ENTRANCE', 'NORMAL'), ('event', 'AT_START'), ('move', f'T{t.table_id}:guide', 'GUIDE'),
                    ('event', 'ARRIVED')]
        if t.type == 'SERVE':
            pickup = MENU[t.menu]['pickup']
            return [('move', pickup, 'NORMAL'), ('arm', 'LOAD', 3.0), ('event', 'LOADED'),
                    ('move', tbl, 'NORMAL'), ('arm', 'UNLOAD', 3.0), ('event', 'DELIVERED')]
        if t.type == 'COLLECT':
            return [('move', tbl, 'NORMAL'), ('arm', 'COLLECT_DISHES', 4.0), ('event', 'COLLECTED'),
                    ('move', 'DISH_RETURN', 'NORMAL'), ('arm', 'RETURN_DISHES', 3.0), ('event', 'RETURNED')]
        raise ValueError(t.type)

    # ------------------------------------------------------------------ main loop
    def tick(self, now):
        dt = 0.0 if self._last_tick is None else now - self._last_tick
        self._last_tick = self.now = now
        self._schedule()
        for r in self.robots.values():
            if r.needs_replan and not (r.pending_goal and not r.route and not self._yield_done(r)):
                r.needs_replan = False
                if (r.route or r.pending_goal) and not r.estop:
                    g, mode = (r.pending_goal[0], r.pending_goal[1]) if r.pending_goal else (r.goal, r.mode)
                    standing = not r.heading
                    if not self._start_move(r, g, mode, replan=True, allow_flip=False) and standing:
                        self._retreat(r, None, goal=g, mode=mode)
            self._drive(r, dt)
            if r.online and r.task is None and not r.route and not r.pending_goal and not r.estop and not r.heading:
                if r.node != r.home and r.battery < self.standby_min_battery:
                    self._go_home(r, force_home=True)          # standby robot running low: go and charge
                elif r.node != r.park and not r.arm_busy:
                    self._go_home(r)                           # left somewhere (e.g. after stepping aside): go and park
        self._cook_tick()

    # ------------------------------------------------------------------ scheduling
    def _available(self, r):
        return (r.online and not r.estop and r.task is None and not r.arm_busy and r.battery >= self.min_battery)

    def _cost_fn(self):
        """Seconds until a robot can be at the task's first stop. ETA schedulers ask the path planner, so waiting for
        aisle reservations of other robots (and a busy pick-up point) is included."""
        cache = {}

        def static(r, t):
            return self.graph.shortest_dist(r.heading or r.node, t.start_node) / self.speed

        def eta(r, t):
            k = (r.id, t.start_node)
            if k not in cache:
                req = PlanRequest(r.id, r.heading or r.node, t.start_node, self.now, self.speed * self.plan_speed_factor,
                                  goal_hold=4.0)
                steps = self.planner.plan(self.graph, req, self._table(r)) if self.planner.coordinated else None
                cache[k] = (steps[-1].arrive - self.now) if steps else static(r, t) * (1.0 if steps is None and not
                                                                                     self.planner.coordinated else 3.0)
            return cache[k]
        return eta if self.scheduler.uses_eta else static

    def _assign(self, t, r):
        t.robot_id, t.state, t.assigned_at, t.pi = r.id, 'IN_PROGRESS', self.now, 0
        r.task, r.returning = t, False
        self.io.log('TASK_ASSIGN', task_id=t.id, robot_id=r.id, visit_id=t.visit_id, order_id=t.order_id,
                    result=self.scheduler.name, reason=f'wait={self.now - t.created:.1f}')
        self._event(t, 'ASSIGNED')
        self._run_phase(r)

    def _schedule(self):
        pend = [t for t in self.tasks.values() if t.state == 'PENDING' and t.type in AMR_TASKS]
        free = [r for r in self.robots.values() if self._available(r)]
        cost = self._cost_fn()
        if self.scheduler.rebalance and self.now - self._last_rebalance >= self.scheduler.rebalance_period:
            self._last_rebalance = self.now
            # not started = still driving to the first stop (no guest picked up, nothing loaded)
            # A task may change hands at most twice, and not within 6 s of its last assignment: otherwise two robots
            # can keep handing the same task to each other (each turns round, which flips the ETA comparison again).
            open_ = [t for t in self.tasks.values() if t.state == 'IN_PROGRESS' and t.type in AMR_TASKS and t.pi == 0
                     and not t.carrying and not self.robots[t.robot_id].estop
                     and t.rebalanced < 2 and self.now - t.assigned_at >= 6.0]
            if open_:
                robots = free + [self.robots[t.robot_id] for t in open_]
                # a robot that is released again plans from where it is now
                pairs = self.scheduler.assign(pend + open_, robots, cost, self.now)
                new = {t.id: r for t, r in pairs}
                if all(t.id in new for t in open_):
                    gain = sum(cost(self.robots[t.robot_id], t) - cost(new[t.id], t) for t in open_)
                    moved = [t for t in open_ if new[t.id].id != t.robot_id]
                    if moved and gain > self.scheduler.rebalance_gain:
                        for t in moved:
                            old = self.robots[t.robot_id]
                            old.task = None
                            t.robot_id, t.state = '', 'PENDING'
                            t.rebalanced += 1
                            self.m['reassign'] += 1
                            self.io.log('TASK_REBALANCE', task_id=t.id, robot_id=old.id, result=new[t.id].id,
                                        reason=f'gain={gain:.1f}')
                        for t in moved:
                            self._assign(t, new[t.id])
                        for o in robots:                       # released robots without a new task go and park
                            if o.task is None and not o.estop and all(o is not new[t.id] for t in moved):
                                if o.route and not o.returning:
                                    self._go_home(o)
                        pend = [t for t in self.tasks.values() if t.state == 'PENDING' and t.type in AMR_TASKS]
                        free = [r for r in self.robots.values() if self._available(r)]
                        cost = self._cost_fn()
        if not pend or not free:
            return
        for t, r in self.scheduler.assign(pend, free, cost, self.now):
            self._assign(t, r)

    # ------------------------------------------------------------------ task programs
    def _run_phase(self, r):
        t = r.task
        while t and t.state == 'IN_PROGRESS':
            if t.pi >= len(t.phases):
                t.state, t.finished_at = 'DONE', self.now
                self.m['tasks_done'] += 1
                self._event(t, 'DONE')
                self.io.log('TASK_DONE', task_id=t.id, robot_id=r.id, visit_id=t.visit_id, order_id=t.order_id,
                            result='OK', reason=f'dur={t.finished_at - t.created:.1f}')
                r.task = None
                self._go_home(r)
                return
            ph = t.phases[t.pi]
            if ph[0] == 'event':
                if ph[1] == 'LOADED':
                    t.carrying = True
                    self.slots[MENU[t.menu]['pickup']] = max(0, self.slots[MENU[t.menu]['pickup']] - 1)
                if ph[1] in ('DELIVERED', 'RETURNED'):
                    t.carrying = False
                if ph[1] == 'COLLECTED':
                    t.carrying = True
                self._event(t, ph[1])
                t.pi += 1
                continue
            if ph[0] == 'move':
                if len(self.graph.table_nodes.get(ph[1], ())) > 1:      # table reachable from several sides
                    ph = t.phases[t.pi] = ('move', self._table_side(r, ph[1]), ph[2])
                goal = self.graph.resolve(ph[1])
                if r.node == goal and not r.heading:
                    # Already standing on the goal. A route may still be active (e.g. the robot was on its way home
                    # and got this task while passing the node): drop it instead of planning a one-node route, whose
                    # arrival is never reported (progress only counts indices above the current one).
                    if r.route:
                        self._stop_route(r)
                    r.returning, r.pending_goal = False, None
                    t.pi += 1
                    continue
                self._start_move(r, goal, ph[2])
                return
            if ph[0] == 'arm':                    # only after the stop at the node is confirmed (no route active)
                r.arm_busy, r.arm_until = ph[1], self.now + ph[2]
                self.io.arm_job(r.id, t.id, ph[1], ph[2], {'table_id': t.table_id, 'menu': t.menu})
                self.io.log('ARM_START', task_id=t.id, robot_id=r.id, zone_id=r.node, result=ph[1])
                return

    def _table_side(self, r, table):
        """Service node of a table that can be approached from several sides: the nearest one for this robot, with a
        penalty when another robot stands on it / is heading for it. The choice is kept for the rest of the move."""
        src = r.heading or r.node

        def cost(n):
            busy = any(o.id != r.id and (o.goal == n and (o.route or o.pending_goal) or o.node == n)
                       for o in self.robots.values())
            return self.graph.shortest_dist(src, n) + (0.6 if busy else 0.0)
        return min(self.graph.table_nodes[table], key=cost)

    def _park_goal(self, r, force_home=False):
        """Where an idle robot waits. Chargers sit next to the entrance (guiding); the standby spots sit next to the
        cook zone (serving). Keep one robot on the entrance side, send the others to a free standby spot."""
        others = [o for o in self.robots.values() if o.id != r.id and not o.estop]
        if r.battery < self.standby_min_battery and r.home not in self.graph.home_nodes:
            # an AMR without its own charger borrows a free one (nobody parked on it or heading for it)
            used = {o.park for o in others} | {o.node for o in others}
            free = [n for n in self.graph.home_nodes if n not in used and self._blocker(n, r.id) is None]
            if free:
                return min(free, key=lambda n: self.graph.shortest_dist(r.heading or r.node, n))
        if force_home or not self.use_standby or r.battery < self.standby_min_battery:
            return r.home
        entrance_side = sum(1 for o in others if o.task is None and (o.park or o.node) in self.graph.home_nodes)
        if entrance_side < 1:
            return r.home
        taken = {o.park for o in others if o.task is None} | {o.node for o in others if o.task is None}
        free = [n for n in self.graph.standby_nodes if n not in taken and self._blocker(n, r.id) is None]
        if not free:
            return r.home
        return min(free, key=lambda n: self.graph.shortest_dist(r.heading or r.node, n))

    def _go_home(self, r, force_home=False):
        goal = self._park_goal(r, force_home)
        r.park = goal
        if r.node == goal and not r.heading:
            return
        r.returning = True
        self._start_move(r, goal, 'NORMAL')

    def _event(self, t, state, reason=''):
        self.io.task_event(dict(task_id=t.id, task_type=t.type, state=state, robot_id=t.robot_id, visit_id=t.visit_id,
                                order_id=t.order_id, item_id=t.item_id, table_id=t.table_id,
                                plan_version=self.robots[t.robot_id].plan_version if t.robot_id in self.robots else 0,
                                reason=reason or t.reason))

    # ------------------------------------------------------------------ planning
    def _table(self, me, optimistic=False, exclude=()):
        """Reservations of all other robots. optimistic=True ignores their future plans (only what they occupy now):
        used when `me` cannot find a plan, so that `me` goes first and the others re-plan around it."""
        tb = ReservationTable(conflict=self.graph.conflict)
        for o in self.robots.values():
            if o.id == me.id or o.id in exclude:
                continue
            if optimistic and (o.route or o.pending_goal) and not o.estop:
                for n in o.held:
                    tb.add(n, self.now, self.now + 5.0, o.id)
                    tb.itineraries.append([(n, self.now), (n, self.now + 5.0)])
            elif o.route and self.planner.coordinated and o.route[0].arrive > 0:
                rem = o.route[max(o.idx, 0):]
                hold = self._hold_estimate(o, at_goal=True)
                tb.add_plan(o.id, rem, last_hold=hold)
                for n in o.held:                       # what it physically occupies right now
                    tb.add(n, self.now, self.now + 1.5, o.id)
                pts = [(rem[0].node, min(self.now, rem[0].depart))]
                for i, st in enumerate(rem):
                    if i:
                        pts.append((st.node, st.arrive))
                    pts.append((st.node, st.depart if i + 1 < len(rem) else st.arrive + hold))
                tb.itineraries.append(pts)
            else:
                hold = self._hold_estimate(o)
                for n in o.held:
                    tb.add(n, self.now, self.now + hold, o.id)
                    tb.itineraries.append([(n, self.now), (n, self.now + hold)])
        return tb

    def _hold_estimate(self, o, at_goal=False):
        if o.estop:
            return INF
        if at_goal:
            if o.returning:
                return INF
            t = o.task
            if t and t.pi + 1 < len(t.phases) and t.phases[t.pi + 1][0] == 'arm':
                return t.phases[t.pi + 1][2] + 2.0
            return 4.0
        if o.arm_busy:
            return max(1.0, o.arm_until - self.now) + 2.0
        if o.task is None and not o.route and not o.pending_goal:
            return INF                               # parked
        return 4.0

    def _start_move(self, r, goal, mode, replan=False, blocked=frozenset(), allow_flip=True):
        goal = self.graph.resolve(goal)
        start = r.heading or r.node
        # plan a little slower than the robots drive, so small execution delays do not flip the planned order
        speed = (self.guide_speed if mode == 'GUIDE' else self.speed) * self.plan_speed_factor
        t0 = self.now + (self.graph.dist(r.node, r.heading) / speed * 0.5 if r.heading else 0.0)
        hold = INF if (r.returning and goal == r.park) else 5.0
        req = PlanRequest(r.id, start, goal, t0, speed, goal_hold=hold, blocked=blocked)
        c0 = time.perf_counter()
        steps = None
        if self.planner.joint and allow_flip and not blocked:
            steps = self._plan_joint(r, req, goal, mode)
        if steps is None:
            steps = self.planner.plan(self.graph, req, self._table(r))
        if steps is None and self.planner.coordinated and allow_flip:
            steps = self.planner.plan(self.graph, req, self._table(r, optimistic=True))
            if steps is not None:                     # priority flip: the others must now plan around us
                self.m['flips'] += 1
                for o in self.robots.values():
                    if o.id != r.id and (o.route or o.pending_goal) and not o.estop:
                        o.needs_replan = True
        self.m['plan_calls'] += 1
        self.m['plan_ms'] += (time.perf_counter() - c0) * 1000.0
        r.goal, r.mode = goal, mode
        if steps is None:
            self.m['plan_fail'] += 1
            r.pending_goal = (goal, mode, self.now + 1.0)
            self.io.log('PLAN_FAIL', robot_id=r.id, task_id=r.task.id if r.task else '', zone_id=goal,
                        result=self.planner.name)
            if r.route:                               # keep standing where we are
                self._stop_route(r)
            return False
        self._adopt(r, steps, goal, mode, replan)
        return True

    def _adopt(self, r, steps, goal, mode, replan=False):
        same_kind = r.goal == goal and r.mode == mode
        r.goal, r.mode, r.pending_goal = goal, mode, None
        if len(steps) == 1 and not r.heading and steps[0].node == r.node:
            # start == goal: nothing to drive, so no progress report would ever come. Treat it as arrived now.
            if r.route:
                self._stop_route(r)
            r.plan_version += 1
            self._arrived(r)
            return
        if replan and r.route and r.heading and same_kind and not r.yield_to and steps[0].arrive > 0:
            # The robot is between two nodes and the new plan visits the same nodes: only the timing changed. Keep the
            # route and its version and take over the new times. Re-sending it restarts the robot's current segment,
            # and a robot that is re-planned every few seconds (others keep changing plans) then never arrives.
            k = r.idx + 1
            if [s.node for s in r.route[k:]] == [s.node for s in steps]:
                for old, new in zip(r.route[k:], steps):
                    old.arrive, old.depart = new.arrive, new.depart
                return
        r.plan_version += 1
        r.route, r.idx, r.granted = steps, -1 if r.heading else 0, 0
        r.wait_since, r.blocked_by = None, ''
        self.io.send_route(r.id, r.task.id if r.task else 'RETURN', r.plan_version, mode,
                           r.task.visit_id if r.task else 0, steps)
        self.io.log('REPLAN' if replan else 'PLAN', robot_id=r.id, task_id=r.task.id if r.task else 'RETURN',
                    plan_version=r.plan_version, zone_id=goal, result=self.planner.name,
                    reason=f'len={len(steps)} eta={steps[-1].arrive - self.now:.1f}' if steps[-1].arrive else f'len={len(steps)}')

    def _request(self, o, goal, mode):
        speed = (self.guide_speed if mode == 'GUIDE' else self.speed) * self.plan_speed_factor
        t0 = self.now + (self.graph.dist(o.node, o.heading) / speed * 0.5 if o.heading else 0.0)
        hold = INF if (o.returning and goal == o.park) else self._hold_estimate(o, at_goal=True)
        return PlanRequest(o.id, o.heading or o.node, goal, t0, speed, goal_hold=hold)

    def _plan_joint(self, r, req, goal, mode):
        """Joint planners (CCBS): plan `r` together with every other robot that is on its way somewhere."""
        others = [o for o in self.robots.values() if o.id != r.id and not o.estop and (o.route or o.pending_goal)]
        if not others:
            return None
        reqs = [req] + [self._request(o, o.pending_goal[0] if o.pending_goal else o.goal,
                                      o.pending_goal[1] if o.pending_goal else o.mode) for o in others]
        plans = self.planner.plan_joint(self.graph, reqs, self._table(r, exclude={o.id for o in others}))
        if plans is None:
            self.m['joint_fail'] += 1
            return None
        self.m['joint_plans'] += 1
        for o in others:
            g, md = (o.pending_goal[0], o.pending_goal[1]) if o.pending_goal else (o.goal, o.mode)
            old = [s.node for s in o.route[max(o.idx, 0):]] if o.route else None
            new = plans[o.id]
            if old == [s.node for s in new] and o.route and abs(new[-1].arrive - o.route[-1].arrive) < 1.0:
                continue                                   # unchanged: do not disturb the robot
            self._adopt(o, new, g, md, replan=True)
        return plans[r.id]

    def _stop_route(self, r):
        self.io.cancel_route(r.id)
        r.route = None

    # ------------------------------------------------------------------ traffic layer
    def _drive(self, r, dt):
        if r.estop:
            return
        if r.pending_goal and self.now >= r.pending_goal[2] and self._yield_done(r):
            g, mode, _ = r.pending_goal
            self._start_move(r, g, mode, replan=True)
        if not r.route or r.idx < 0 or r.idx != r.granted:
            return
        if r.idx >= len(r.route) - 1:
            return
        timed = self.planner.coordinated and r.route[0].arrive > 0
        cur = r.route[r.idx]
        if timed:
            if self.now < cur.depart - 0.05:
                self.m['planned_wait'] += dt
                return
            late = self.now - cur.depart
            if late > 0.2:                                   # we are late: shift the rest of our plan
                for s in r.route[r.idx:]:
                    s.arrive += late if s is not cur else 0.0
                    s.depart += late
        nxt = r.route[r.idx + 1].node
        owner = self._blocker(nxt, r.id)
        if owner is None:
            self.locks[nxt] = r.id
            r.held.add(nxt)
            r.heading = nxt
            r.granted = r.idx + 1
            r.wait_since, r.blocked_by = None, ''
            self.m['grants'] += 1
            self.io.grant(r.id, r.task.id if r.task else 'RETURN', r.plan_version, r.granted)
            self.io.log('ZONE_GRANT', robot_id=r.id, zone_id=nxt, plan_version=r.plan_version,
                        task_id=r.task.id if r.task else 'RETURN')
            return
        # blocked by another robot's lock
        if r.wait_since is None:
            r.wait_since, r.blocked_by = self.now, owner
            self.io.log('ZONE_REQUEST', robot_id=r.id, zone_id=nxt, plan_version=r.plan_version, reason=f'held_by={owner}')
        self.m['blocked_wait'] += dt
        if self.now - r.wait_since > self.stall_timeout and self.now - r.last_replan > 2.0:
            self._resolve_stall(r, owner)

    def _blocker(self, node, rid):
        """Robot that prevents `rid` from entering `node` (holds it or a node too close to it), else None."""
        for n in (node, *self.graph.conflict[node]):
            o = self.locks.get(n)
            if o not in (None, rid):
                return o
        return None

    def _resolve_stall(self, r, owner):
        self.m['stalls'] += 1
        r.last_replan = self.now
        o = self.robots[owner]
        mutual = o.blocked_by == r.id or o.pending_goal is not None or \
            (o.route and 0 <= o.idx and o.idx + 1 < len(o.route) and self._blocker(o.route[o.idx + 1].node, o.id) == r.id)
        # in a mutual block the lower-priority robot yields first; the other one waits one more round
        if mutual and not o.estop and self._rank(r) > self._rank(o) and \
                self.now - r.wait_since < 2.5 * self.stall_timeout:
            return
        blocked = frozenset(n for x in self.robots.values() if x.id != r.id for n in x.held)
        self.m['replans'] += 1
        ok = self._start_move(r, r.goal, r.mode, replan=True,
                              blocked=blocked if not self.planner.coordinated else frozenset())
        if ok and r.route and len(r.route) > 1 and self._blocker(r.route[1].node, r.id) is None:
            return
        if mutual or o.estop:
            self._retreat(r, o)

    def _yield_done(self, r):
        """After stepping aside for robot `o`, stay out of the way until `o` has passed the node we vacated (or finished,
        or 30 s went by). Resuming earlier puts us straight back in its way and the two keep swapping places."""
        if not r.yield_to:
            return True
        o = self.robots.get(r.yield_to)
        region = {r.yield_from} | self.graph.conflict.get(r.yield_from, set())
        ahead = {st.node for st in o.route[max(o.idx, 0):]} if o and o.route else set()
        passed = o is None or o.estop or (not o.route and not o.pending_goal) or \
            (o.route is not None and o.node not in region and o.heading not in region and not (ahead & region))
        if passed or self.now > r.yield_until:
            r.yield_to = r.yield_from = ''
            return True
        return False

    def _rank(self, r):
        p = r.task.priority if r.task else 0
        return (p + (1 if r.task and r.task.carrying else 0), -int(r.id[-1]) if r.id[-1].isdigit() else 0)

    def _retreat(self, r, o, goal=None, mode=None):
        """Step aside so the other robot(s) can pass, then continue to the goal. Searches the free nodes around us and
        prefers a lay-by (비켜 서는 곳), then any node that is not on another robot's route."""
        # keep clear of the others' remaining routes AND of every node too close to them: a side spot next to the
        # aisle node the other robot needs (closer than SAFE_DIST) still blocks it, and the two would swap forever
        avoid = set()
        for x in self.robots.values():
            if x.id != r.id and x.route:
                for st in x.route[max(x.idx, 0):]:
                    avoid.add(st.node)
                    avoid |= self.graph.conflict[st.node]
        prev, order = {r.node: None}, [r.node]
        for u in order:                                   # BFS over nodes we could enter right now
            for n, _ in self.graph.adj[u]:
                if n not in prev and self._blocker(n, r.id) is None:
                    prev[n] = u
                    order.append(n)
        cands = order[1:]
        if not cands:
            r.wait_since = self.now
            return

        def depth(n):
            d = 0
            while prev[n] is not None:
                n, d = prev[n], d + 1
            return d
        # The aisles are one robot wide, so the robot backs out of the way instead of turning round: prefer spots whose
        # first step lies behind it (away from the robot it yields to), then the nearest, counting a lay-by / standby spot as two nodes closer.
        pull_in = self.graph.bay_nodes | set(self.graph.standby_nodes)
        hx, hy = math.cos(r.yaw), math.sin(r.yaw)
        if o is not None:                                 # facing unknown / sideways: "behind" = away from the other robot
            ox, oy = o.x - r.x, o.y - r.y
            if ox * hx + oy * hy <= 0.0 and math.hypot(ox, oy) > 1e-6:
                d = math.hypot(ox, oy)
                hx, hy = ox / d, oy / d
        x0, y0 = self.graph.nodes[r.node]

        def behind(n):
            first = n
            while prev[first] is not None and prev[first] != r.node:
                first = prev[first]
            fx, fy = self.graph.nodes[first]
            return (fx - x0) * hx + (fy - y0) * hy < 0.0
        # a lay-by / standby spot is worth two extra nodes of backing up, no more: long reverse runs block the aisle
        cands.sort(key=lambda n: (n in avoid, not behind(n), depth(n) + (0 if n in pull_in else 2), depth(n)))
        side = cands[0]
        path = [side]
        while prev[path[-1]] is not None:
            path.append(prev[path[-1]])
        path.reverse()
        goal, mode = goal or r.goal, mode or r.mode
        if r.route:
            self.io.cancel_route(r.id)
        self.m['retreats'] += 1
        r.plan_version += 1
        timed = self.planner.coordinated
        t, steps = self.now, []
        for a, b in zip(path, path[1:] + [None]):
            dt = self.graph.dist(a, b) / self.speed if b else 4.0
            steps.append(Step(a, t if timed else 0.0, t if timed else 0.0))
            t += dt
        if timed:
            steps[-1].depart = t
        r.route, r.idx, r.granted = steps, 0, 0
        r.wait_since, r.blocked_by = None, ''
        r.pending_goal = (goal, mode, t + random.uniform(0.0, 3.0))
        r.goal = side
        r.yield_to, r.yield_from, r.yield_until = (o.id if o else ''), r.node, t + 30.0
        self.io.send_route(r.id, r.task.id if r.task else 'RETURN', r.plan_version, 'YIELD', 0, r.route)
        self.io.log('RETREAT', robot_id=r.id, zone_id=side, plan_version=r.plan_version,
                    reason=f'yield_to={o.id if o else "plan"}')

    # ------------------------------------------------------------------ inputs from robots
    def on_robot_status(self, rid, x, y, yaw, battery, charging, state):
        r = self.robots.get(rid)
        if not r:
            return
        if r.online:
            r.dist += math.hypot(x - r.x, y - r.y)
        r.x, r.y, r.yaw, r.battery, r.charging, r.sim_state, r.online = x, y, yaw, battery, charging, state, True

    def on_route_progress(self, rid, plan_version, reached, state=''):
        r = self.robots.get(rid)
        if not r or not r.route or plan_version != r.plan_version or reached <= r.idx:
            return
        reached = min(reached, len(r.route) - 1)
        r.idx = reached
        r.node = r.route[reached].node
        r.heading = ''
        for n in list(r.held):
            if n != r.node:
                r.held.discard(n)
                if self.locks.get(n) == r.id:
                    del self.locks[n]
                self.io.log('ZONE_EXIT', robot_id=r.id, zone_id=n, plan_version=r.plan_version)
        r.held.add(r.node)
        self.locks[r.node] = r.id
        self.io.log('ZONE_ENTER', robot_id=r.id, zone_id=r.node, plan_version=r.plan_version)
        if reached == len(r.route) - 1:
            self._arrived(r)

    def on_route_result(self, rid, plan_version, success, reason, reached):
        r = self.robots.get(rid)
        if not r or plan_version != r.plan_version:
            return                                            # late result of an old plan: ignore
        if success:
            if r.route:
                self.on_route_progress(rid, plan_version, len(r.route) - 1)
            return
        if reason in ('PREEMPTED', 'CANCELED'):
            return
        r.route = None
        if r.task:
            self._suspend(r.task, reason)

    def _arrived(self, r):
        r.route = None
        if r.pending_goal:                                    # we only stepped aside; continue later
            return
        if r.returning:
            r.returning = False
            self.io.log('HOME', robot_id=r.id, zone_id=r.node)
            return
        if r.task and r.task.state == 'IN_PROGRESS':
            ph = r.task.phases[r.task.pi]
            if ph[0] == 'move' and self.graph.resolve(ph[1]) == r.node:
                r.task.pi += 1
            self._run_phase(r)

    def on_arm_result(self, arm_id, task_id, success, reason=''):
        if arm_id in self.robots:
            r = self.robots[arm_id]
            self.io.log('ARM_DONE', task_id=task_id, robot_id=arm_id, zone_id=r.node, result='OK' if success else 'FAIL',
                        reason=reason)
            r.arm_busy = ''
            t = r.task
            if not t or t.id != task_id or t.state != 'IN_PROGRESS':
                return
            if not success:
                self._suspend(t, reason or 'ARM_FAIL')
                return
            t.pi += 1
            self._run_phase(r)
            return
        for j in self.cook_jobs:                              # cooking arms
            if j.task.id == task_id and j.busy:
                j.busy = False
                if not success:
                    j.task.state, j.task.reason = 'SUSPENDED', reason or 'ARM_FAIL'
                    self._event(j.task, 'SUSPENDED', j.task.reason)
                else:
                    j.pc += 1

    def on_doneness(self, task_id, decision, stamp):
        self.doneness[task_id] = (decision, stamp)

    def _suspend(self, t, reason):
        t.state, t.reason = 'SUSPENDED', reason
        self.io.log('TASK_SUSPEND', task_id=t.id, robot_id=t.robot_id, visit_id=t.visit_id, order_id=t.order_id,
                    result='FAIL', reason=reason)
        self._event(t, 'SUSPENDED', reason)

    # ------------------------------------------------------------------ operator commands
    def command(self, cmd, target, arg=''):
        try:
            if cmd == 'SET_SCHEDULER':
                self.set_scheduler(target or arg)
                return True, f'scheduler={self.scheduler.name}'
            if cmd == 'SET_PLANNER':
                self.set_planner(target or arg)
                return True, f'planner={self.planner.name}'
            if cmd == 'ESTOP':
                r = self.robots[target]
                r.estop = True
                if r.route:
                    self._stop_route(r)
                r.pending_goal = None
                self.io.log('ESTOP', robot_id=r.id, zone_id=r.node, reason=arg)
                if r.task and r.task.state == 'IN_PROGRESS':
                    self._suspend(r.task, 'E_STOP')
                return True, f'{target} stopped'
            if cmd == 'SET_STANDBY':
                self.use_standby = (target or arg).lower() in ('1', 'true', 'on')
                return True, f'standby={self.use_standby}'
            if cmd == 'RESUME':
                r = self.robots[target]
                r.estop = False
                self.io.log('RESUME', robot_id=r.id, zone_id=r.node)
                if r.task and r.task.state == 'SUSPENDED':
                    return self.command('RETRY_TASK', r.task.id)
                if r.task is None:
                    self._go_home(r)
                return True, f'{target} resumed'
            if cmd == 'RETRY_TASK':
                t = self.tasks[target]
                if t.state != 'SUSPENDED':
                    return False, 'task is not suspended'
                if t.type == 'COOK':
                    t.state = 'IN_PROGRESS'
                    self._event(t, 'RESUMED')
                    return True, 'cook job resumed'
                r = self.robots[t.robot_id]
                if r.estop:
                    return False, 'robot is still in E-STOP; RESUME it first'
                t.state, t.reason = 'IN_PROGRESS', ''
                self._event(t, 'RESUMED')
                self._run_phase(r)
                return True, 'task resumed from the failed step'
            if cmd == 'REASSIGN':
                t = self.tasks[target]
                if t.state != 'SUSPENDED' or t.type not in AMR_TASKS:
                    return False, 'only a suspended AMR task can be reassigned'
                if t.carrying:
                    return False, 'food/dishes already loaded on the AMR: cannot hand over, remake required'
                old = self.robots.get(t.robot_id)
                if old:
                    old.task = None
                    if not old.estop:
                        self._go_home(old)
                t.robot_id, t.state, t.pi, t.reason = '', 'PENDING', 0, ''
                self._event(t, 'REASSIGNED')
                return True, 'task returned to the queue'
            if cmd == 'CANCEL_TASK':
                t = self.tasks[target]
                if t.state in ('DONE', 'CANCELED'):
                    return False, 'task already finished'
                r = self.robots.get(t.robot_id)
                t.state = 'CANCELED'
                self._event(t, 'CANCELED', arg)
                if r and r.task is t:
                    r.task = None
                    if not r.estop:
                        if r.route:
                            self._stop_route(r)
                        self._go_home(r)
                return True, 'task canceled'
        except KeyError as e:
            return False, f'unknown target {e}'
        return False, f'unknown command {cmd}'

    # ------------------------------------------------------------------ cooking cell
    def _recipe(self, menu):
        s = self.cook_scale
        fry = [('acq', {'ARM_A', 'FRYER'}), ('arm', 'A', 'LOAD_BASKET', 3.0), ('arm', 'A', 'DROP_IN_FRYER', 2.0),
               ('rel', {'ARM_A'}), ('timer', 600.0 / s, 'FRYING'), ('doneness',)]
        if menu == 'FRIED':
            return fry + [('acq', {'ARM_A', 'SLOT:FRY_PICKUP'}), ('arm', 'A', 'LIFT_DRAIN', 3.0), ('arm', 'A', 'PLATE', 3.0),
                          ('arm', 'A', 'PLACE_HANDOFF', 2.0), ('rel', {'ARM_A', 'FRYER'}), ('ready', 'FRY_PICKUP')]
        if menu == 'SEASONED':
            return fry + [('acq', {'ARM_A', 'ARM_B', 'WOK', 'SLOT:WOK_PICKUP'}), ('arm', 'A', 'LIFT_DRAIN', 3.0),
                          ('arm', 'A', 'TO_WOK', 3.0), ('rel', {'ARM_A', 'FRYER'}), ('arm', 'B', 'ADD_SAUCE', 2.0),
                          ('arm', 'B', 'STIR_FRY', 60.0 / s), ('arm', 'B', 'PLATE', 3.0), ('arm', 'B', 'PLACE_HANDOFF', 2.0),
                          ('rel', {'ARM_B', 'WOK'}), ('ready', 'WOK_PICKUP')]
        if menu == 'FRIED_RICE':
            return [('acq', {'ARM_A', 'ARM_B', 'WOK', 'SLOT:WOK_PICKUP'}), ('arm', 'A', 'ADD_INGREDIENTS', 3.0),
                    ('rel', {'ARM_A'}), ('arm', 'B', 'STIR_FRY', 300.0 / s), ('arm', 'B', 'PLATE', 3.0),
                    ('arm', 'B', 'PLACE_HANDOFF', 2.0), ('rel', {'ARM_B', 'WOK'}), ('ready', 'WOK_PICKUP')]
        raise ValueError(f'unknown menu {menu}')

    def _cook_tick(self):
        for j in list(self.cook_jobs):
            t = j.task
            if t.state != 'IN_PROGRESS':
                if t.state in ('CANCELED', 'DONE'):
                    self._cook_release(j, set(self.res_owner))
                    self.cook_jobs.remove(j)
                continue
            for _ in range(8):                              # advance through instant ops
                if j.busy or j.pc >= len(j.ops):
                    break
                op = j.ops[j.pc]
                if op[0] == 'acq':                          # all-or-nothing: never wait while holding an arm
                    arms = {x for x in op[1] if not x.startswith('SLOT:')}
                    slots = [x[5:] for x in op[1] if x.startswith('SLOT:')]
                    if any(self.res_owner[a] not in (None, t.id) for a in arms) or \
                       any(self.slots[s] >= self.slot_cap for s in slots):
                        break
                    for a in arms:
                        self.res_owner[a] = t.id
                    for s in slots:
                        self.slots[s] += 1
                    if j.pc == 0:
                        j.label = 'COOKING'
                        self._event(t, 'COOKING')
                    j.pc += 1
                elif op[0] == 'rel':
                    self._cook_release(j, op[1])
                    j.pc += 1
                elif op[0] == 'arm':
                    j.busy, j.label = True, op[2]
                    params = {'cook_task_id': t.id, 'menu': t.menu}
                    if op[2] == 'DROP_IN_FRYER':
                        params['fry_time'] = 600.0 / self.cook_scale
                    self.io.arm_job('cook_arm_a' if op[1] == 'A' else 'cook_arm_b', t.id, op[2], op[3], params)
                    self.io.log('COOK_STEP', task_id=t.id, order_id=t.order_id, robot_id='cook_arm_' + op[1].lower(),
                                result=op[2])
                elif op[0] == 'timer':
                    if j.until == 0.0:
                        j.until, j.label = self.now + op[1], op[2]
                        self.io.log('COOK_STEP', task_id=t.id, order_id=t.order_id, result=op[2], reason=f'{op[1]:.1f}s')
                        break
                    if self.now < j.until:
                        break
                    j.until = 0.0
                    j.pc += 1
                elif op[0] == 'doneness':
                    if not self.use_doneness:
                        j.pc += 1
                        continue
                    if j.wait_doneness_since is None:
                        j.wait_doneness_since, j.label = self.now, 'DONENESS_CHECK'
                    d = self.doneness.get(t.id)
                    fresh = d and d[1] >= j.wait_doneness_since
                    if not fresh and self.now - j.wait_doneness_since < 5.0:
                        break
                    decision = d[0] if fresh else 'DONE'           # AI server silent: degrade to timer only
                    self.io.log('DONENESS', task_id=t.id, order_id=t.order_id, result=decision,
                                reason='ai' if fresh else 'timeout_fallback')
                    j.wait_doneness_since = None
                    if decision == 'UNDERCOOKED' and j.retries < 2:
                        j.retries += 1
                        j.ops.insert(j.pc, ('timer', 120.0 / self.cook_scale, f'REFRY_{j.retries}'))
                        continue
                    j.pc += 1
                elif op[0] == 'ready':
                    t.state, t.finished_at, j.label = 'DONE', self.now, 'READY'
                    self.io.log('COOK_READY', task_id=t.id, order_id=t.order_id, zone_id=op[1],
                                reason=f'dur={self.now - t.created:.1f}')
                    self._event(t, 'READY', op[1])
                    self.cook_jobs.remove(j)
                    break

    def _cook_release(self, j, names):
        for a in names:
            if not a.startswith('SLOT:') and self.res_owner.get(a) == j.task.id:
                self.res_owner[a] = None

    # ------------------------------------------------------------------ state for UI
    def robot_state(self, r):
        if r.estop:
            return 'E_STOP'
        t = r.task
        if t and t.state == 'SUSPENDED':
            return 'SUSPENDED'
        if r.arm_busy:
            return {'LOAD': 'LOADING', 'UNLOAD': 'UNLOADING', 'COLLECT_DISHES': 'COLLECTING',
                    'RETURN_DISHES': 'RETURNING_DISHES'}.get(r.arm_busy, r.arm_busy)
        if t:
            if t.type == 'GUIDE':
                return 'GUIDING' if t.pi >= 2 else 'TO_START'
            if t.type == 'SERVE':
                return 'SERVING' if t.carrying else 'TO_PICKUP'
            return 'TO_DISH_RETURN' if t.carrying else 'TO_TABLE'
        if r.returning or r.route:
            return 'RETURNING'
        if r.node in self.graph.standby_nodes:
            return 'STANDBY'
        return 'CHARGING' if r.charging else 'IDLE'

    def _arm_job_of(self, arm):
        """Arm job a cooking arm ('A' / 'B') is running right now, '' when it stands still."""
        for j in self.cook_jobs:
            if j.busy and j.pc < len(j.ops) and j.ops[j.pc][0] == 'arm' and j.ops[j.pc][1] == arm:
                return j.ops[j.pc][2]
        return ''

    def snapshot(self):
        return {
            'now': self.now,
            'algorithms': {'scheduler': self.scheduler.name, 'planner': self.planner.name,
                           'schedulers': {k: v.description for k, v in SCHEDULERS.items()},
                           'planners': {k: v.description for k, v in PLANNERS.items()}, 'standby': self.use_standby},
            'robots': [{'id': r.id, 'state': self.robot_state(r), 'node': r.node, 'heading': r.heading,
                        'device': device_state.mobile_state(self.robot_state(r), r.online),
                        'x': r.x, 'y': r.y, 'yaw': r.yaw, 'battery': round(r.battery, 1), 'charging': r.charging,
                        'task': r.task.id if r.task else '', 'task_type': r.task.type if r.task else '',
                        'carrying': bool(r.task and r.task.carrying), 'plan_version': r.plan_version,
                        'blocked_by': r.blocked_by if r.wait_since is not None else '', 'online': r.online,
                        'route': [s.node for s in r.route[max(r.idx, 0):]] if r.route else [],
                        'dist': round(r.dist, 2)} for r in self.robots.values()],
            'tasks': [{'id': t.id, 'type': t.type, 'state': t.state, 'robot': t.robot_id, 'table': t.table_id,
                       'menu': t.menu, 'visit': t.visit_id, 'order': t.order_id, 'item': t.item_id,
                       'reason': t.reason, 'age': round(self.now - t.created, 1), 'carrying': t.carrying}
                      for t in list(self.tasks.values())[-40:]],
            'locks': dict(self.locks),
            'cooking': {'resources': dict(self.res_owner), 'slots': dict(self.slots),
                        'arms': {f'cook_arm_{a.lower()}': device_state.arm_state(self._arm_job_of(a)) for a in 'AB'},
                        'jobs': [{'task': j.task.id, 'menu': j.task.menu, 'step': j.label, 'order': j.task.order_id,
                                  'retries': j.retries} for j in self.cook_jobs]},
            'metrics': {k: (round(v, 2) if isinstance(v, float) else v) for k, v in self.m.items()},
        }
