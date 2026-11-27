"""scan_match: 지도에서 만든 가짜 스캔으로 자세 추정과 모호 판정(T-49).

ROS 없이 실행된다. 스캔은 지도 거리장 위 광선 추적 + 잡음 1 cm + 점 5% 누락.
"""
# [수정 2026-11-20] T-49: 신규
import math
import os

import numpy as np

# frybot_control 을 import 하기 전에 지도 이름 환경 변수를 정해 둠(아래
# noqa: E402 는 이 순서 때문). 시험 자체는 지도 이름을 직접 넘김
os.environ.setdefault('FRYBOT_MAP_ID', 'test_map_v05')

from frybot_control.layout import Graph  # noqa: E402
from frybot_control.map_catalog import profile  # noqa: E402
from frybot_mobile.scan_match import ScanMatcher  # noqa: E402

_N = 360  # 가짜 스캔의 광선 수(1도 간격)
_INC = 2 * math.pi / _N  # 광선 간격(rad)


def _scan(m: ScanMatcher, x: float, y: float, yaw: float,
          seed: int = 1) -> np.ndarray:
    """(x, y, yaw) 에 선 로봇의 라이다가 볼 거리 배열."""
    # 라이다 장착 자세를 지도 좌표로 옮김
    lx0, ly0, la = m.lidar
    lx = x + lx0 * math.cos(yaw) - ly0 * math.sin(yaw)
    ly = y + lx0 * math.sin(yaw) + ly0 * math.cos(yaw)
    # 광선을 4 mm 간격으로 3 m 까지 따라가며 벽(거리장 < 4 mm)을 찾음
    t = np.arange(0.0, 3.0, 0.004)
    out = np.full(_N, np.inf)
    for i in range(_N):
        a = yaw + la - math.pi + i * _INC  # angle_min = -pi 인 스캔
        d = m.lookup(lx + t * math.cos(a), ly + t * math.sin(a))
        hit = np.nonzero(d < 0.004)[0]
        if len(hit):
            out[i] = t[hit[0]]
    # 잡음 1 cm(정규분포)와 5% 점 누락(inf)
    rng = np.random.default_rng(seed)
    out = out + rng.normal(0, 0.01, _N)
    out[rng.random(_N) < 0.05] = np.inf
    return out


def _run(node: str, yaw_deg: float, saved=None, home=None):
    """노드 자리에서 만든 가짜 스캔으로 localize() 결과와 참값 자세."""
    m = ScanMatcher(profile('test_map_v05')['yaml'])
    x, y = Graph('test_map_v05').nodes[node]
    pts = m.points(_scan(m, x, y, math.radians(yaw_deg)), -math.pi, _INC)
    return (m.localize(pts, saved=saved, home=home),
            (x, y, math.radians(yaw_deg)))


def test_finds_pose_at_w1():
    """W1 에서 1.5 cm, 3 도 안으로 맞춤."""
    res, (x, y, yaw) = _run('W1', 90)
    assert res.status == 'OK'
    assert math.hypot(res.pose.x - x, res.pose.y - y) < 0.015
    assert abs(math.remainder(res.pose.yaw - yaw, 2 * math.pi)) < 0.05


def test_symmetric_spot_is_ambiguous_without_saved_pose():
    """지도가 180 도 대칭인 W3 은 저장 자세가 없으면 자세를 정하지 않음."""
    res, _ = _run('W3', 90)
    assert res.status == 'AMBIGUOUS' and res.pose is None


def test_saved_pose_breaks_the_tie():
    """저장 자세가 W3 이면 W3 을 고름, W1(옮겨짐)이면 정하지 않음."""
    w = Graph('test_map_v05').nodes
    res, (x, y, _) = _run('W3', 90, saved=(*w['W3'], math.pi / 2))
    assert res.status == 'OK_SAVED'
    assert math.hypot(res.pose.x - x, res.pose.y - y) < 0.015
    res, _ = _run('W3', 90, saved=(*w['W1'], math.pi / 2))
    assert res.pose is None


# [수정 2026-11-20] T-50: 홈 근처 우선, 위치 추정 감시·보정
def test_home_prior_breaks_the_tie_without_saved_pose():
    """저장 자세가 없으면 홈(W3) 근처 후보를 고름, 홈이 W1 이면 모호."""
    w = Graph('test_map_v05').nodes
    res, (x, y, _) = _run('W3', 90, home=w['W3'])
    assert res.status == 'OK_HOME'
    assert math.hypot(res.pose.x - x, res.pose.y - y) < 0.015
    res, _ = _run('W3', 90, home=w['W1'])
    assert res.status == 'AMBIGUOUS'


# [수정 2026-11-20] T-51: 저장 자세가 엉뚱한 곳(사람이 홈으로 옮김)
def test_home_prior_when_saved_pose_matches_nothing():
    """저장 자세가 어느 후보와도 맞지 않으면 홈 근처 후보를 고름."""
    w = Graph('test_map_v05').nodes
    elsewhere = (*w['B2'], math.radians(46))
    res, (x, y, _) = _run('W3', 90, saved=elsewhere, home=w['W3'])
    assert res.status == 'OK_HOME'
    assert math.hypot(res.pose.x - x, res.pose.y - y) < 0.015
    res, _ = _run('W3', 90, saved=elsewhere, home=w['W1'])
    assert res.status == 'AMBIGUOUS'
    # 저장 자세가 맞는 후보 근처면 그것이 먼저(OK_SAVED)
    res, _ = _run('W3', 90, saved=(*w['W3'], math.pi / 2), home=w['W1'])
    assert res.status == 'OK_SAVED'


def _recheck(node, yaw_deg, given_dx, given_dyaw_deg):
    """참값에서 x 로 given_dx(m), 방향 given_dyaw_deg(도) 틀린 자세 recheck."""
    m = ScanMatcher(profile('test_map_v05')['yaml'])
    x, y = Graph('test_map_v05').nodes[node]
    pts = m.points(_scan(m, x, y, math.radians(yaw_deg)), -math.pi, _INC)
    return m.recheck(pts, x + given_dx, y,
                     math.radians(yaw_deg + given_dyaw_deg)), (x, y)


def test_recheck_fixes_a_pose_25_deg_6_cm_off():
    """AMCL 이 25 도·6 cm 틀리면 근처 탐색으로 1.5 cm 안까지 고침."""
    (score, fix), (x, y) = _recheck('B2', 180, 0.06, -25)
    assert score > 0.03 and fix is not None
    assert math.hypot(fix.x - x, fix.y - y) < 0.015
    assert abs(math.remainder(fix.yaw - math.pi, 2 * math.pi)) < 0.05


def test_recheck_leaves_a_good_pose_alone():
    """맞는 자세(1 cm·2 도 안)는 건드리지 않음."""
    (_, fix), _ = _recheck('B2', 180, 0.01, 2)
    assert fix is None
