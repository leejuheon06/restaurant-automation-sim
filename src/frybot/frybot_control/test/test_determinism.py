"""같은 입력에 같은 판단 (작업 지시서 3 W8-1).

관제 코어가 문자열 집합을 도는 순서(PYTHONHASHSEED)에 따라 판단이 달라지지
않는지, 해시 씨앗을 바꾼 하위 프로세스로 같은 모의 실행을 돌려 비교한다.

    cd ~/frybot_ws && source install/setup.bash
    python3 -m pytest src/frybot/frybot_control/test -q
"""
# [수정 2026-11-18] W8-1: 신규
import json
import os
import subprocess
import sys

import pytest

# 하위 프로세스에서 돌릴 모의 실행. 인자: 종류(moves2·moves3·rush), 씨앗,
# 플래너. 실기기 보정 시간 모델(0.135 m/s, 2.27초, 흔들림 0.2)로 돌리고
# 지표 한 줄(JSON)을 출력함. plan_ms 는 벽시계 값이라 뺌
_SCRIPT = r'''
import json, os, sys
from frybot_control import mock_fleet
from frybot_control import offline_bench as ob

kind, seed, planner = sys.argv[1], int(sys.argv[2]), sys.argv[3]
model = mock_fleet.TimeModel('measured', 0.135, 2.27, jitter=0.2)
if kind.startswith('moves'):
    os.environ['FRYBOT_MAP_ID'] = 'test_map_v001'
    row, _ = ob.run_moves('min_cost_eta_rh', planner, seed=seed,
                          robots=int(kind[-1]), model=model, max_t=1500.0)
else:
    os.environ['FRYBOT_MAP_ID'] = ''
    model.guide_speed = 0.05
    row, _ = ob._run_full('min_cost_eta_rh', planner, kind, seed=seed,
                          model=model, max_t=1500.0)
row.pop('plan_ms', None)
print(json.dumps(row, sort_keys=True, default=str))
'''

# (종류, 씨앗, 플래너). moves* 는 실측 지도 test_map_v001, rush 는 가상 매장
CASES = [('moves2', 19, 'independent_astar'),
         ('moves3', 1, 'independent_astar'),
         ('moves3', 5, 'sipp'), ('rush', 3, 'sipp')]


def _run(hash_seed: str, case) -> dict:
    """PYTHONHASHSEED=hash_seed 인 하위 프로세스로 case 를 돌린 지표."""
    env = dict(os.environ, PYTHONHASHSEED=hash_seed)
    cmd = [sys.executable, '-c', _SCRIPT] + [str(c) for c in case]
    out = subprocess.run(cmd,
                         env=env, capture_output=True, text=True, check=True,
                         timeout=600)
    return json.loads(out.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize('case', CASES)
def test_same_result_for_any_hash_seed(case):
    """해시 씨앗 1, 2, 3 에서 지표가 모두 같음(plan_ms 제외)."""
    rows = [_run(h, case) for h in ('1', '2', '3')]
    assert rows[0] == rows[1] == rows[2]
