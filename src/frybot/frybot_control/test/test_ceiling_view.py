"""ceiling_view: 마커 대응, 실패 사유, 기준 화면 갱신(T-55).

[수정 2026-11-23] 신규: 작업 지시 18. 합성 영상만 씀(ROS 없음).
"""
import cv2
import numpy as np

from frybot_control import ceiling_view as cv
from frybot_control.map_catalog import profile

_BOX = cv.map_box(profile('test_map_v05')['yaml'])
_MANUAL = cv.Calib.from_walls(_BOX)
# 바닥 모서리 근처 마커 중심(지도 좌표, m). 오른쪽 위 바닥 모서리는 화면
# 밖(x>1280)이라 41 은 오른쪽 벽에서 약 25 cm 안쪽(화면 x 약 1180)에 둠
_MARKS = {'40': [-0.03, 0.22], '41': [1.56, 0.20], '42': [1.76, -0.58],
          '43': [-0.03, -0.58]}


def _floor() -> np.ndarray:
    """나무 바닥 비슷한 단색 화면(1280x720)."""
    return np.full((720, 1280, 3), (150, 190, 215), np.uint8)


def _paint_markers(img: np.ndarray, cal: cv.Calib, side: float = 0.08):
    """마커를 지도의 한 변 side m 정사각형으로 화면에 그려 넣음."""
    d = cv2.aruco.getPredefinedDictionary(cv.MARKER_DICT)
    for i, (x, y) in _MARKS.items():
        mk = cv2.cvtColor(cv2.aruco.generateImageMarker(d, int(i), 120),
                          cv2.COLOR_GRAY2BGR)
        h = side / 2
        quad = cal.to_pix([(x - h, y + h), (x + h, y + h), (x + h, y - h),
                           (x - h, y - h)]).astype(np.float32)
        src = np.float32([[0, 0], [119, 0], [119, 119], [0, 119]])
        warp = cv2.warpPerspective(mk, cv2.getPerspectiveTransform(src, quad),
                                   (img.shape[1], img.shape[0]),
                                   borderValue=(0, 0, 0))
        mask = cv2.warpPerspective(np.full((120, 120), 255, np.uint8),
                                   cv2.getPerspectiveTransform(src, quad),
                                   (img.shape[1], img.shape[0]))
        img[mask > 0] = warp[mask > 0]
    return img


def test_manual_calib_matches_measured_k():
    """벽 바닥선 수동 대응: k 0.288(작업 지시 17 A), 왕복 변환 1 mm 안."""
    assert abs(_MANUAL.k - 0.288) < 0.01
    pts = np.array([[0.091, -0.552], [1.541, 0.045], [0.766, -0.175]])
    back = _MANUAL.to_map(_MANUAL.to_pix(pts))
    assert np.abs(back - pts).max() < 0.001


def test_markers_give_same_mapping():
    """마커 4개가 보이면 마커 대응을 쓰고, 수동 대응과 1 cm 안으로 같음."""
    img = _paint_markers(_floor(), _MANUAL)
    cal = cv.Calib.from_markers(img, _MARKS, _MANUAL.k)
    assert cal is not None and cal.source == 'markers:4'
    pts = np.array([[0.091, -0.552], [1.541, 0.045], [0.766, -0.175]])
    px = _MANUAL.to_pix(pts)
    assert np.abs(cal.to_map(px) - pts).max() < 0.01


def test_too_few_markers_falls_back():
    """마커가 3개 이하이거나 지도에 키가 없으면 None(수동 대응으로)."""
    img = _paint_markers(_floor(), _MANUAL)
    three = {k: v for k, v in _MARKS.items() if k != '43'}
    assert cv.Calib.from_markers(img, three, _MANUAL.k) is None
    assert cv.Calib.from_markers(img, {}, _MANUAL.k) is None


def test_spot_check_reasons():
    """기준 화면 없음, 크기 다름, 장면이 크게 바뀜은 ok=false."""
    f = _floor()
    assert cv.spot_check(f, None, _MANUAL, _BOX, [(0, 0)]).reason \
        .startswith('NO_REFERENCE')
    small = np.zeros((360, 640, 3), np.uint8)
    assert cv.spot_check(f, small, _MANUAL, _BOX, [(0, 0)]).reason \
        .startswith('CAMERA_FAIL')
    dark = np.zeros_like(f)
    assert cv.spot_check(dark, f, _MANUAL, _BOX, [(0, 0)]).reason \
        .startswith('SCENE_CHANGED')


def test_spot_check_scores_a_robot_and_explains_others():
    """로봇 크기 어두운 덩어리 자리는 높은 점수, 다른 로봇 옆은 -1."""
    ref = _floor()
    f = ref.copy()
    quad = _MANUAL.to_pix([(1.52, 0.11), (1.63, 0.11), (1.63, 0.0),
                           (1.52, 0.0)]).astype(np.int32)
    cv2.fillPoly(f, [quad], (30, 30, 30))
    r = cv.spot_check(f, ref, _MANUAL, _BOX,
                      [(1.576, 0.055), (0.109, -0.412), (0.5, -0.4)],
                      others=[('pinky2', 0.45, -0.40)])
    assert r.ok and r.scores[0] > 0.15 and r.scores[1] < 0.01
    assert r.scores[2] == cv.EXPLAINED and 'pinky2' in r.reason


def test_update_reference_keeps_robot_spot():
    """갱신은 keep 마스크 안의 옛 화소를 두고 나머지만 새 프레임으로."""
    ref = _floor()
    new = ref.copy()
    new[:, :] = (100, 100, 100)
    keep = _MANUAL.disc_mask(ref.shape, (0.766, -0.175), 0.15)
    out = cv.update_reference(ref, new, keep)
    assert (out[keep > 0] == ref[keep > 0]).all()
    assert (out[keep == 0] == new[keep == 0]).all()
