#!/usr/bin/env python3
"""Run every scheduler x planner pair N times per scenario (offline fleet simulation) and keep every single run.

  source install/setup.bash && python3 scripts/bench_all.py --runs 3 --robots 3 --out bench_raw.csv
"""
import argparse
import csv
import multiprocessing as mp
import warnings

warnings.filterwarnings('ignore')
from frybot_control.offline_bench import SCENARIOS, run          # noqa: E402
from frybot_control.planners import PLANNERS                     # noqa: E402
from frybot_control.schedulers import SCHEDULERS                 # noqa: E402


def one(job):
    sc, s, p, seed, robots = job
    r = run(s, p, sc, seed=seed, robots=robots)
    r.update(scenario=sc, seed=seed)
    return r


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--runs', type=int, default=3)
    ap.add_argument('--robots', type=int, default=3)
    ap.add_argument("--out", default="bench_raw.csv")
    ap.add_argument("--jobs", type=int, default=None)
    ap.add_argument('--planners', nargs='*', default=sorted(PLANNERS))
    ap.add_argument('--schedulers', nargs='*', default=sorted(SCHEDULERS))
    a = ap.parse_args()
    jobs = [(sc, s, p, k, a.robots) for sc in sorted(SCENARIOS) for s in a.schedulers for p in a.planners
            for k in range(a.runs)]
    with mp.Pool(a.jobs) as pool:
        rows = pool.map(one, jobs, chunksize=1)
    cols = ['scenario', 'scheduler', 'planner', 'seed'] + [c for c in rows[0] if c not in ('scenario', 'scheduler', 'planner', 'seed')]
    with open(a.out, 'w', newline='') as f:
        w = csv.DictWriter(f, cols)
        w.writeheader()
        w.writerows(rows)
    print(len(rows), 'runs ->', a.out)
