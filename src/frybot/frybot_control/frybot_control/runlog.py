"""Per-run evidence folder: manifest.json + events.csv (+ sqlite DB), as specified in the project plan."""
import csv
import json
import os
import subprocess
import time

COLUMNS = ['run_id', 'timestamp', 'event', 'visit_id', 'order_id', 'task_id', 'robot_id', 'zone_id',
           'plan_version', 'result', 'reason']


class RunLogger:
    def __init__(self, base_dir, run_id=None, manifest=None):
        self.run_id = run_id or time.strftime('run_%Y%m%d_%H%M%S')
        self.dir = os.path.join(os.path.expanduser(base_dir), self.run_id)
        os.makedirs(self.dir, exist_ok=True)
        self.path = os.path.join(self.dir, 'events.csv')
        new = not os.path.exists(self.path)
        self._f = open(self.path, 'a', newline='')
        self._w = csv.DictWriter(self._f, COLUMNS, extrasaction='ignore')
        if new:
            self._w.writeheader()
        if manifest is not None:
            self.write_manifest(manifest)

    def write_manifest(self, manifest):
        m = dict(run_id=self.run_id, created=time.strftime('%Y-%m-%d %H:%M:%S'), commit=_commit(), **manifest)
        with open(os.path.join(self.dir, 'manifest.json'), 'w') as f:
            json.dump(m, f, ensure_ascii=False, indent=2)

    def log(self, event, timestamp=None, **f):
        row = {c: f.get(c, '') for c in COLUMNS}
        row.update(run_id=self.run_id, event=event,
                   timestamp=f'{time.time() if timestamp is None else timestamp:.3f}')
        self._w.writerow(row)
        self._f.flush()
        return row


def _commit():
    try:
        return subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD'], cwd=os.path.dirname(__file__),
                                       stderr=subprocess.DEVNULL, timeout=2).decode().strip()
    except Exception:
        return 'uncommitted'
