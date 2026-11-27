"""천장 카메라 후보 판정 시험: 실제 천장 프레임으로 판정을 재현(T-55).

[수정 2026-11-23] 신규: 작업 지시 18. 자료는 test/data/ceiling 의 JPEG
(작업 지시 17-B runs/20261123_01, 18-T runs/20261123_02·03, 17-A 09 실행).
후보 위치는 그때 auto_localize 로그의 best·다음 후보. ROS 없이 실행.
"""
import math
import os

import cv2
import pytest

os.environ.setdefault('FRYBOT_MAP_ID', 'test_map_v05')

from test_scan_match import _INC  # noqa: E402
from test_scan_match import _scan  # noqa: E402

from frybot_control import ceiling_view as cv  # noqa: E402
from frybot_control.map_catalog import profile  # noqa: E402
from frybot_mobile.scan_match import Candidate  # noqa: E402
from frybot_mobile.scan_match import ScanMatcher  # noqa: E402
from frybot_mobile.scan_match import pick_by_camera  # noqa: E402

_DATA = os.path.join(os.path.dirname(__file__), 'data', 'ceiling')
_BOX = cv.map_box(profile('test_map_v05')['yaml'])
_CAL = cv.Calib.from_walls(_BOX)


def _img(name: str):
    """시험 자료 이미지."""
    img = cv2.imread(os.path.join(_DATA, name + '.jpg'))
    assert img is not None, name
    return img


def _cands(*poses) -> list[Candidate]:
    """(x, y, yaw 도) 목록 -> Candidate 목록."""
    return [Candidate(x, y, math.radians(a), 0.0) for x, y, a in poses]


def _judge(frame: str, ref: str, cands, others=()):
    """프레임의 후보 점수와 pick_by_camera 결과."""
    r = cv.spot_check(_img(frame), _img(ref), _CAL, _BOX,
                      [(c.x, c.y) for c in cands], others)
    assert r.ok, r.reason
    return r.scores, pick_by_camera(cands, r.scores)[0]


# (프레임, 실제 자리 후보, 다른 후보, 기대: 0 이면 실제 자리를 고름)
_CASES = [
    ('17b_s1_W1', (0.043, -0.460, 90), (1.634, 0.175, -90), 0),
    ('17b_s2_TR', (1.576, 0.075, -95), (0.109, -0.412, 85), 0),
    ('17b_s3_W3', (1.541, -0.485, 88), (0.143, 0.135, -92), 0),
    ('18t_r1_wall', (0.121, 0.015, 46), (1.591, -0.357, -130), 0),
    ('18t_r2_TR', (1.516, 0.050, -95), (0.164, -0.400, 85), 0),
    # 가운데 C2: 두 후보 11 cm, 방향만 다름 -> 카메라는 고르지 않음
    ('17b_s4_C2', (0.786, -0.190, -2), (0.881, -0.140, 180), None),
]


@pytest.mark.parametrize('frame,real,other,want', _CASES)
def test_replay_recorded_frames(frame, real, other, want):
    """기록된 프레임에서 1·2·3번·18-T 는 실제 자리, 4번은 고르지 않음."""
    scores, k = _judge(frame, 'empty_ref_20261123', _cands(real, other))
    assert k == want, scores


def test_other_robot_next_to_symmetric_spot_is_explained():
    """17-A #26: 대칭 자리 15 cm 옆에 다른 로봇(pinky2) -> 고르지 않음."""
    cands = _cands((1.1535, -0.395, 0), (0.579, 0.035, 180))
    scores, k = _judge('09_b4_a2', '09_bg', cands,
                       others=[('pinky2', 0.4285, 0.045)])
    assert scores[1] == cv.EXPLAINED and k is None


def test_pick_rule_thresholds():
    """한 후보만 높고 나머지 낮고 30 cm 넘게 떨어질 때만 고름."""
    two = _cands((0.0, 0.0, 0), (1.0, 0.0, 0))
    assert pick_by_camera(two, [0.30, 0.00])[0] == 0
    assert pick_by_camera(two, [0.30, 0.10])[0] is None   # 나머지가 높음
    assert pick_by_camera(two, [0.12, 0.00])[0] is None   # 둘 다 낮음
    assert pick_by_camera(two, [0.30, -1.0])[0] is None   # 설명된 자리
    near = _cands((0.0, 0.0, 0), (0.2, 0.0, 180))
    assert pick_by_camera(near, [0.30, 0.00])[0] is None  # 30 cm 안


def _localize_at_s2(chooser):
    """17-B 2번 자리의 가짜 스캔, 저장 자세는 W1(틀린 쪽)."""
    m = ScanMatcher(profile('test_map_v05')['yaml'])
    pts = m.points(_scan(m, 1.576, 0.075, math.radians(-95)),
                   -math.pi, _INC)
    # 가짜 스캔은 실제보다 깨끗해 모호하지 않을 수 있어 margin 을 넓혀
    # 실기기처럼 모호하게 만듦(실기기 차 0.5 mm)
    return m.localize(pts, saved=(0.109, -0.412, math.radians(85)),
                      margin=0.03, chooser=chooser)


def test_camera_beats_saved_pose_at_symmetric_spot():
    """저장 자세가 W1 이어도 카메라가 실제 자리(오른쪽 위)를 고름(T-55)."""
    old = _localize_at_s2(None)
    assert old.status == 'OK_SAVED' and old.pose.x < 0.5   # 예전: 틀린 W1

    def chooser(cands):
        r = cv.spot_check(_img('17b_s2_TR'), _img('empty_ref_20261123'),
                          _CAL, _BOX, [(c.x, c.y) for c in cands])
        return pick_by_camera(cands, r.scores)

    res = _localize_at_s2(chooser)
    assert res.status == 'OK_CAMERA', res.camera
    assert math.hypot(res.pose.x - 1.576, res.pose.y - 0.075) < 0.05
    assert abs(math.remainder(res.pose.yaw - math.radians(-95),
                              2 * math.pi)) < 0.2


def test_camera_without_answer_keeps_old_rule():
    """카메라가 답하지 못하면(None) 예전 규칙 그대로(OK_SAVED)."""
    res = _localize_at_s2(lambda cands: (None, 'no service'))
    assert res.status == 'OK_SAVED' and res.camera == 'no service'
