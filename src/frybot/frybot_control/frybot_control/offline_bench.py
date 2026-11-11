"""Offline algorithm comparison: runs the real Task Manager core + restaurant logic against simple kinematic robots
(no ROS, faster than real time) and prints one row per (scheduler, planner) pair for the same customer script.

    ros2 run frybot_control fleet_bench            # all combinations
    ros2 run frybot_control fleet_bench --scenario rush --schedulers hungarian --planners sipp independent_astar
"""
import argparse
import itertools
import math
import statistics as st

from .fleet_core import FleetCore, FleetIO
from .restaurant import Restaurant, RestaurantIO
from .planners import PLANNERS
from .schedulers import SCHEDULERS

# (arrival time s, party size, [(menu, qty)], seconds from seated to order, seconds from last dish to leaving)
SCENARIOS = {
    'normal': [(0, 2, [('FRIED', 1)], 8, 25), (20, 4, [('FRIED_RICE', 2), ('SEASONED', 1)], 10, 30),
               (45, 2, [('FRIED_RICE', 1)], 8, 25), (80, 3, [('FRIED', 1), ('FRIED_RICE', 1)], 10, 30),
               (120, 2, [('SEASONED', 1)], 8, 25)],
    # entrance guiding and pick-ups at the same moment + long hand-overs at tables on the aisles
    'bottleneck': [(0, 2, [('FRIED_RICE', 2)], 4, 30), (2, 2, [('FRIED_RICE', 2)], 4, 30), (4, 4, [('FRIED_RICE', 2), ('FRIED', 1)], 4, 30),
                   (34, 2, [('FRIED_RICE', 1)], 4, 20), (36, 4, [('FRIED_RICE', 2)], 4, 20), (38, 2, [('FRIED_RICE', 2)], 4, 20),
                   (100, 2, [('FRIED_RICE', 1)], 4, 20), (102, 2, [('SEASONED', 1)], 4, 20)],
    'rush': [(0, 2, [('FRIED_RICE', 1)], 5, 20), (3, 4, [('FRIED_RICE', 2)], 5, 25), (6, 2, [('FRIED', 1)], 5, 20),
             (9, 4, [('FRIED_RICE', 1), ('SEASONED', 1)], 5, 25), (12, 2, [('FRIED_RICE', 2)], 5, 20),
             (15, 2, [('FRIED_RICE', 1)], 5, 20), (70, 2, [('FRIED_RICE', 1)], 5, 20), (75, 4, [('FRIED', 1), ('FRIED_RICE', 2)], 5, 20),
             (140, 2, [('FRIED_RICE', 1)], 5, 20), (145, 2, [('SEASONED', 1)], 5, 20)],
}


class SimRobot:
    def __init__(self, rid, x, y):
        self.id, self.x, self.y, self.yaw = rid, x, y, 0.0
        self.route, self.pv, self.granted, self.reached, self.mode = None, 0, 0, 0, 'NORMAL'


class OfflineWorld(FleetIO, RestaurantIO):
    def __init__(self, scheduler, planner, scenario, dt=0.1, speed=0.08, guide_speed=0.05, cook_scale=20.0, verbose=False, standby=True):
        self.dt, self.t, self.verbose = dt, 0.0, verbose
        self.speed, self.guide_speed = speed, guide_speed
        self.core = FleetCore(self, scheduler=scheduler, planner=planner, speed=speed, guide_speed=guide_speed,
                              cook_time_scale=cook_scale, use_doneness=False, use_standby=standby)
        self.rest = Restaurant(self)
        self.bots = {r.id: SimRobot(r.id, r.x, r.y) for r in self.core.robots.values()}
        self.arm = []                 # (finish, arm_id, task_id)
        self.accepted = []
        self.todo = [(a[0], 'arrive', a) for a in scenario]
        self.plan_of = {}             # visit -> scenario row
        self.events = []
        self.min_sep = 9.9
        self.stats = dict(seat=[], deliver=[], ready_to_deliver=[], turnaround=[], rejected=0)

    # ---- FleetIO
    def send_route(self, rid, task_id, pv, mode, visit_id, steps):
        b = self.bots[rid]
        b.route, b.pv, b.mode, b.granted = [(s.node,) + self.core.graph.nodes[s.node] for s in steps], pv, mode, 0
        b.reached = 0 if math.hypot(b.x - b.route[0][1], b.y - b.route[0][2]) < 1e-3 else -1
        if b.reached == 0:
            self.accepted.append((rid, pv))          # like the action's first feedback (ACCEPTED, index 0)

    def grant(self, rid, task_id, pv, index):
        b = self.bots[rid]
        if pv == b.pv:
            b.granted = index

    def cancel_route(self, rid):
        self.bots[rid].route = None

    def arm_job(self, arm_id, task_id, job, duration, params):
        self.arm.append((self.t + duration, arm_id, task_id))

    def task_event(self, ev):
        self.events.append(ev)

    def log(self, event, **f):
        if self.verbose:
            print(f'{self.t:7.1f} {event:15s}', {k: v for k, v in f.items() if v != ''})
        r = f.get('reason', '')
        if event == 'SEATED':
            self.stats['seat'].append(float(r.split('=')[1]))
        elif event == 'DELIVERED':
            a, b = r.split()
            self.stats['deliver'].append(float(a.split('=')[1]))
            self.stats['ready_to_deliver'].append(float(b.split('=')[1]))
        elif event == 'TABLE_AVAILABLE' and r:
            self.stats['turnaround'].append(float(r.split('=')[1]))
        elif event == 'CHECKIN_REJECT':
            self.stats['rejected'] += 1

    # ---- RestaurantIO
    def submit_task(self, cb, **kw):
        kw['type'] = kw.pop('task_type')
        cb(self.core.submit_task(**kw))

    def fleet_command(self, cmd, target, arg=''):
        return self.core.command(cmd, target, arg)

    def persist(self, table, row):
        pass

    # ---- simulation
    def step(self):
        self.t += self.dt
        t = self.t
        for item in [x for x in self.todo if x[0] <= t]:
            self.todo.remove(item)
            _, kind, a = item
            if kind == 'arrive':
                ok, vid, _, _ = self.rest.check_in(a[1])
                if ok:
                    self.plan_of[vid] = a
            elif kind == 'order':
                v = self.rest.visits[a]
                self.rest.place_order(v['table'], self.plan_of[a][2])
            elif kind == 'leave':
                self.rest.end_use(self.rest.visits[a]['table'], 'TABLET')
        for rid, pv in self.accepted:
            self.core.on_route_progress(rid, pv, 0)
        self.accepted = []
        for f in [x for x in self.arm if x[0] <= t]:
            self.arm.remove(f)
            self.core.on_arm_result(f[1], f[2], True)
        for b in self.bots.values():
            if b.route:
                tgt = b.reached + 1
                if tgt < len(b.route) and (tgt <= b.granted or b.reached == -1):
                    _, tx, ty = b.route[tgt]
                    d = math.hypot(tx - b.x, ty - b.y)
                    v = (self.guide_speed if b.mode == 'GUIDE' else self.speed) * self.dt
                    if d <= v:
                        b.x, b.y, b.reached = tx, ty, tgt
                        pv, last = b.pv, tgt == len(b.route) - 1
                        self.core.on_route_progress(b.id, pv, tgt)
                        if last and b.pv == pv:
                            b.route = None
                    else:
                        b.x += (tx - b.x) / d * v
                        b.y += (ty - b.y) / d * v
            self.core.on_robot_status(b.id, b.x, b.y, 0.0, 100.0, False, '')
        for a, b in itertools.combinations(self.bots.values(), 2):
            self.min_sep = min(self.min_sep, math.hypot(a.x - b.x, a.y - b.y))
        self.rest.tick(t)
        self.core.tick(t)
        for ev in self.events:
            self.rest.on_task_event(ev)
            if ev['task_type'] == 'GUIDE' and ev['state'] == 'ARRIVED':
                self.todo.append((t + self.plan_of[ev['visit_id']][3], 'order', ev['visit_id']))
            if ev['task_type'] == 'SERVE' and ev['state'] == 'DELIVERED':
                o = self.rest.orders[ev['order_id']]
                if o['state'] == 'COMPLETED':
                    self.todo.append((t + self.plan_of[o['visit']][4], 'leave', o['visit']))
        self.events.clear()

    def finished(self):
        return (not self.todo and all(t['state'] == 'AVAILABLE' for t in self.rest.tables.values())
                and all(r.task is None and not r.route and not r.pending_goal for r in self.core.robots.values()))


def run(scheduler, planner, scenario='normal', max_t=1500.0, verbose=False, standby=True, seed=0):
    import random
    random.seed(seed)
    script = SCENARIOS[scenario]
    if seed:                                          # same guests, arrival times shifted a little per seed
        script = sorted((max(0.0, a[0] + random.uniform(-4, 4)),) + a[1:] for a in script)
    w = OfflineWorld(scheduler, planner, script, verbose=verbose, standby=standby)
    while w.t < max_t and not (w.t > 5 and w.finished()):
        w.step()
    m, s = w.core.m, w.stats
    avg = lambda a: round(st.mean(a), 1) if a else float('nan')
    return dict(scheduler=scheduler, planner=planner, finished=w.finished(), makespan=round(w.t, 1),
                seat_avg=avg(s['seat']), deliver_avg=avg(s['deliver']), deliver_max=round(max(s['deliver'], default=0), 1),
                ready_to_deliver=avg(s['ready_to_deliver']), turnaround=avg(s['turnaround']), rejected=s['rejected'],
                blocked_wait=round(m['blocked_wait'], 1), stalls=m['stalls'], replans=m['replans'],
                retreats=m['retreats'], flips=m['flips'], plan_fail=m['plan_fail'],
                plan_ms=round(m['plan_ms'] / max(1, m['plan_calls']), 2),
                dist=round(sum(r.dist for r in w.core.robots.values()), 1), min_sep=round(w.min_sep, 3),
                tasks=m['tasks_done'], reassign=m['reassign'], joint=m['joint_plans'])


COLS = ['scheduler', 'planner', 'finished', 'makespan', 'seat_avg', 'deliver_avg', 'deliver_max', 'ready_to_deliver',
        'turnaround', 'blocked_wait', 'stalls', 'replans', 'retreats', 'flips', 'plan_fail', 'plan_ms', 'dist', 'min_sep', 'reassign', 'joint', 'tasks']


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--scenario', default='normal', choices=sorted(SCENARIOS))
    ap.add_argument('--schedulers', nargs='*', default=sorted(SCHEDULERS))
    ap.add_argument('--planners', nargs='*', default=sorted(PLANNERS))
    ap.add_argument('--csv', default='')
    ap.add_argument('--seeds', type=int, default=1, help='runs per pair (arrival times jittered); values are means')
    ap.add_argument('--verbose', action='store_true')
    ap.add_argument('--no-standby', action='store_true', help='idle robots always return to their charger')
    a = ap.parse_args()
    rows = []
    for s in a.schedulers:
        for p in a.planners:
            rs = [run(s, p, a.scenario, verbose=a.verbose, standby=not a.no_standby, seed=k) for k in range(a.seeds)]
            row = dict(scheduler=s, planner=p, finished=f"{sum(r['finished'] for r in rs)}/{len(rs)}")
            for c in COLS[3:]:
                vals = [r[c] for r in rs if r[c] == r[c]]
                row[c] = (min(vals) if c == 'min_sep' else round(sum(vals) / len(vals), 2)) if vals else float('nan')
            rows.append(row)
    w = {c: max(len(c), *(len(str(r[c])) for r in rows)) for c in COLS}
    print(f'scenario={a.scenario} seeds={a.seeds}  (times in s, dist in m, min_sep = closest robot centres in m)')
    print('  '.join(c.ljust(w[c]) for c in COLS))
    for r in rows:
        print('  '.join(str(r[c]).ljust(w[c]) for c in COLS))
    if a.csv:
        import csv
        with open(a.csv, 'w', newline='') as f:
            cw = csv.DictWriter(f, COLS, extrasaction='ignore')
            cw.writeheader()
            cw.writerows(rows)
        print('saved', a.csv)


if __name__ == '__main__':
    main()
