"""Per-run evidence folder: manifest.json + events.csv (+ sqlite DB), as specified in the project plan."""
import csv
import json
import os
import subprocess
import time

# events.csv 의 열. analyze_run, replay_run 이 이 열 이름으로 읽음
COLUMNS = ['run_id', 'timestamp', 'event', 'visit_id', 'order_id', 'task_id', 'robot_id', 'zone_id',
           'plan_version', 'result', 'reason']


class RunLogger:
    """실행 한 번의 기록 폴더(base_dir/run_id)를 만들고 events.csv 에 쓴다.

    같은 run_id 로 다시 띄우면 events.csv 뒤에 이어 쓴다(머리줄은 처음만).

    Args:
        base_dir: 실행 폴더들을 둘 폴더(~ 허용).
        run_id: 폴더 이름. 비우면 run_YYYYMMDD_HHMMSS.
        manifest: 주면 manifest.json 을 바로 쓴다.
    """

    def __init__(self, base_dir, run_id=None, manifest=None):
        self.run_id = run_id or time.strftime('run_%Y%m%d_%H%M%S')
        self.dir = os.path.join(os.path.expanduser(base_dir), self.run_id)
        os.makedirs(self.dir, exist_ok=True)
        self.path = os.path.join(self.dir, 'events.csv')
        new = not os.path.exists(self.path)  # 새 파일일 때만 머리줄을 씀
        self._f = open(self.path, 'a', newline='')
        self._w = csv.DictWriter(self._f, COLUMNS, extrasaction='ignore')
        if new:
            self._w.writeheader()
        if manifest is not None:
            self.write_manifest(manifest)

    def write_manifest(self, manifest):
        """manifest.json(실행 이름, 만든 시각, git 커밋, 실행 설정)을 쓴다.

        Args:
            manifest: 더 적을 실행 설정(런치 인자 등).
        """
        m = dict(run_id=self.run_id, created=time.strftime('%Y-%m-%d %H:%M:%S'), commit=_commit(), **manifest)
        with open(os.path.join(self.dir, 'manifest.json'), 'w') as f:
            json.dump(m, f, ensure_ascii=False, indent=2)

    def log(self, event, timestamp=None, **f):
        """이벤트 한 줄을 events.csv 에 쓰고 바로 디스크에 내보낸다.

        Args:
            event: 이벤트 이름(예: TASK_DONE, ZONE_GRANT).
            timestamp: 시각(unix 초). 비우면 지금.
            **f: COLUMNS 의 다른 열 값. COLUMNS 에 없는 키는 버린다.

        Returns:
            쓴 행(dict). central_control 이 DB 에도 같은 행을 남긴다.
        """
        row = {c: f.get(c, '') for c in COLUMNS}
        row.update(run_id=self.run_id, event=event,
                   timestamp=f'{time.time() if timestamp is None else timestamp:.3f}')
        self._w.writerow(row)
        self._f.flush()
        return row


# manifest 에 남길 지금 git 커밋(짧은 해시)
def _commit():
    try:
        return subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD'], cwd=os.path.dirname(__file__),
                                       stderr=subprocess.DEVNULL, timeout=2).decode().strip()
    # git 이 없거나 저장소 밖(설치본)이거나 2초 안에 끝나지 않으면
    except Exception:
        return 'uncommitted'
