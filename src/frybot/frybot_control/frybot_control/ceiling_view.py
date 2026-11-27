"""천장 카메라 한 장으로 '후보 자리에 로봇이 있는가'를 판정하는 계산부.

[수정 2026-11-23] 신규: 작업 지시 18(천장 카메라 초기 위치). ROS 없이
쓰는 모듈이라 ceiling_locator 노드, ceiling_tool, 시험이 함께 씀. 방법은
작업 지시 17 의 측정(scripts/ceiling_locate.py, runs/20261123_01_ceiling_
loc_pinky1)을 옮긴 것.

판정 순서:
  1. 영상 ↔ 지도 대응(Calib): 바닥 ArUco(MARKER_DICT)가 지도의
     ceiling_markers 에 적힌 것 중 4개 이상 보이면 그 프레임에서 호모그래피를
     구하고, 아니면 벽 바닥선을 손으로 읽은 수동 대응(WALL_PTS)을 씀.
     어느 쪽이든 렌즈 통형 왜곡은 방사 왜곡 한 항(k)으로 먼저 폄.
  2. 빈 바닥 기준 화면과의 Lab 색 차이가 DIFF_THR 를 넘는 화소 = 바뀐 곳.
  3. 후보 자리마다 둘레 정사각형(반 변 SITE_HALF) 안의 바뀐 화소 비율.
     위치가 잡힌 다른 로봇이 가까운 자리는 '설명됨'(점수 EXPLAINED).
"""
from __future__ import annotations

import dataclasses
import json
import math
import os
import time

import cv2
import numpy as np
import yaml

# 벽 바닥선 화소 점(1280x720): 2026-11-20 09 실행 배경을 4배 확대해 손으로
# 읽음(작업 지시 17 A). 천장 카메라를 옮기거나 바꾸면 다시 읽어야 함
# (마커 대응을 쓰면 이 값은 왜곡 계수 k 를 맞추는 데만 씀). 모서리 점은 두
# 벽에 모두 들어감. 오른쪽 위 모서리는 화면 밖이라 두 선의 교점으로 구함
WALL_PTS = {
    'top': [(84, 80), (250, 57), (450, 46), (650, 41), (850, 43),
            (1050, 50), (1190, 60)],
    'bottom': [(207, 600), (500, 609), (700, 612), (1120, 604),
               (1172, 601)],
    'left': [(84, 80), (115, 250), (142, 360), (170, 460), (207, 600)],
    'right': [(1272, 210), (1232, 380), (1208, 460), (1172, 601)],
}
FRAME_SIZE = (1280, 720)       # 위 화소 점의 화면 크기(가로, 세로)
CENTER = (640.0, 360.0)        # 왜곡 중심(화면 가운데로 가정)
NORM = 1000.0                  # 왜곡 반지름 정규화(화소)
# 바닥 ArUco: 도킹 마커(docks 의 marker_id, 0 번대)와 겹치지 않게 40~43
MARKER_DICT = cv2.aruco.DICT_4X4_50
DIFF_THR = 40.0                # 기준 화면과의 색 차이 문턱(Lab 거리)
SITE_HALF = 0.10               # 후보 자리 창의 반 변(m): 로봇 반 크기 6 cm +
#                                보정·시차 오차 여유 4 cm(17-A 평균 오차 5 cm)
EXPLAINED = -1.0               # 다른 로봇이 설명하는 자리의 점수 값


class CameraBusyError(RuntimeError):
    """카메라 장치를 다른 프로그램이 쓰는 중이고 최신 프레임 파일도 없음."""


class CameraFailError(RuntimeError):
    """카메라를 열었으나 프레임을 읽지 못함(장치 없음 포함)."""


def undistort(pts, k: float) -> np.ndarray:
    """방사 왜곡 한 항(k)으로 화소 좌표를 편다.

    Args:
        pts: (N, 2) 화소 좌표.
        k: 왜곡 계수. 0 이면 그대로.

    Returns:
        (N, 2) 편 좌표.
    """
    p = np.asarray(pts, float).reshape(-1, 2) - CENTER
    r2 = (p ** 2).sum(axis=1, keepdims=True) / NORM ** 2
    return p * (1.0 + k * r2) + CENTER


def _line(pts: np.ndarray) -> tuple[np.ndarray, float, float]:
    """점들에 맞춘 직선(법선, 원점 거리)과 잔차 RMS(화소)."""
    c = pts.mean(axis=0)
    _, _, vt = np.linalg.svd(pts - c)
    n = vt[1]
    res = (pts - c) @ n
    return n, float(n @ c), float(np.sqrt((res ** 2).mean()))


def fit_k(walls: dict | None = None) -> float:
    """벽 바닥선이 가장 곧아지는 왜곡 계수를 격자 탐색으로 찾는다.

    Args:
        walls: 벽 이름 → 화소 점 목록. 없으면 WALL_PTS.

    Returns:
        왜곡 계수 k(WALL_PTS 로는 0.288, 벽별 잔차 1.7~3.0 화소).
    """
    walls = WALL_PTS if walls is None else walls
    pts = {w: np.asarray(v, float) for w, v in walls.items()}
    best_k, best = 0.0, None
    for k in np.arange(-0.10, 0.40, 0.002):
        tot = sum(_line(undistort(v, k))[2] ** 2 for v in pts.values())
        if best is None or tot < best:
            best_k, best = float(k), tot
    return best_k


def map_box(map_yaml: str) -> tuple[float, float, float, float]:
    """지도 pgm 의 자유 공간을 둘러싼 사각형 (x0, x1, y0, y1) m.

    벽 안쪽 바닥의 경계로 씀. 경계 칸(해상도) 안 어딘가가 실제 벽 면이라
    변마다 해상도의 반(5 cm 지도에서 ±2.5 cm) 오차가 있음.

    Args:
        map_yaml: Nav2 지도 yaml 경로.

    Returns:
        (x0, x1, y0, y1).
    """
    with open(map_yaml) as stream:
        meta = yaml.safe_load(stream)
    img = cv2.imread(os.path.join(os.path.dirname(map_yaml), meta['image']),
                     cv2.IMREAD_GRAYSCALE)
    occ = img.astype(float) / 255.0
    if not meta.get('negate', 0):
        occ = 1.0 - occ
    rows, cols = np.nonzero(occ < float(meta.get('free_thresh', 0.196)))
    res = float(meta['resolution'])
    ox, oy = float(meta['origin'][0]), float(meta['origin'][1])
    h = img.shape[0]
    return (ox + cols.min() * res, ox + (cols.max() + 1) * res,
            oy + (h - rows.max() - 1) * res, oy + (h - rows.min()) * res)


@dataclasses.dataclass
class Calib:
    """영상 화소 ↔ 지도 좌표 변환(왜곡 한 항 + 호모그래피).

    Attributes:
        k: 왜곡 계수.
        h: 편 화소 → 지도(m) 3x3 호모그래피.
        source: 'manual'(벽 바닥선) 또는 'markers:<개수>'.
    """

    k: float
    h: np.ndarray
    source: str

    @classmethod
    def from_walls(cls, box: tuple, k: float | None = None,
                   walls: dict | None = None) -> Calib:
        """벽 바닥선 수동 대응으로 만든다.

        Args:
            box: map_box() 의 (x0, x1, y0, y1).
            k: 왜곡 계수(없으면 fit_k).
            walls: 벽 바닥선 점(없으면 WALL_PTS).

        Returns:
            Calib(source 'manual').
        """
        walls = WALL_PTS if walls is None else walls
        k = fit_k(walls) if k is None else k

        def cross(a: str, b: str) -> np.ndarray:
            n1, d1, _ = _line(undistort(walls[a], k))
            n2, d2, _ = _line(undistort(walls[b], k))
            return np.linalg.solve(np.array([n1, n2]), np.array([d1, d2]))

        # 모서리: 왼쪽 위, 오른쪽 위, 오른쪽 아래, 왼쪽 아래(지도 +y 가 화면 위)
        px = np.array([cross('top', 'left'), cross('top', 'right'),
                       cross('bottom', 'right'), cross('bottom', 'left')])
        x0, x1, y0, y1 = box
        world = np.array([[x0, y1], [x1, y1], [x1, y0], [x0, y0]])
        h = cv2.getPerspectiveTransform(px.astype(np.float32),
                                        world.astype(np.float32))
        return cls(k, h.astype(float), 'manual')

    @classmethod
    def from_markers(cls, frame: np.ndarray, markers: dict,
                     k: float) -> Calib | None:
        """바닥 ArUco 4개 이상으로 이 프레임의 대응을 만든다.

        Args:
            frame: BGR 프레임.
            markers: 마커 id(문자열 또는 정수) → 중심의 지도 좌표 [x, y].
            k: 왜곡 계수(카메라 렌즈 값이라 수동 대응의 것을 씀).

        Returns:
            Calib(source 'markers:<개수>'). 4개 미만이면 None.
        """
        want = {int(i): xy for i, xy in (markers or {}).items()}
        seen = {i: uv for i, uv in detect_markers(frame).items()
                if i in want}
        if len(seen) < 4:
            return None
        ids = sorted(seen)
        px = undistort([seen[i] for i in ids], k)
        world = np.array([want[i] for i in ids], float)
        h, _ = cv2.findHomography(px, world)
        if h is None:
            return None
        return cls(k, h, f'markers:{len(ids)}')

    def to_map(self, px) -> np.ndarray:
        """화소 (N, 2) → 지도 (N, 2) m."""
        u = undistort(px, self.k).reshape(-1, 1, 2)
        return cv2.perspectiveTransform(u, self.h)[:, 0]

    def to_pix(self, xy) -> np.ndarray:
        """지도 (N, 2) m → 화소 (N, 2). 왜곡은 반복으로 되돌림."""
        w = np.asarray(xy, float).reshape(-1, 1, 2)
        u = cv2.perspectiveTransform(w, np.linalg.inv(self.h))[:, 0]
        p = u.copy()
        for _ in range(20):
            p = p - (undistort(p, self.k) - u)
        return p

    def poly_mask(self, shape: tuple, xy) -> np.ndarray:
        """지도 다각형 xy 를 화면에 옮겨 채운 마스크(uint8 0/255)."""
        mask = np.zeros(shape[:2], np.uint8)
        cv2.fillPoly(mask, [self.to_pix(xy).astype(np.int32)], 255)
        return mask

    def floor_mask(self, shape: tuple, box: tuple,
                   inset: float = 0.02) -> np.ndarray:
        """지도 자유 공간 안쪽(벽에서 inset m 들어온 곳)의 화면 마스크."""
        x0, x1, y0, y1 = (box[0] + inset, box[1] - inset,
                          box[2] + inset, box[3] - inset)
        xs, ys = np.linspace(x0, x1, 40), np.linspace(y0, y1, 20)
        edge = ([(x, y1) for x in xs] + [(x1, y) for y in ys[::-1]]
                + [(x, y0) for x in xs[::-1]] + [(x0, y) for y in ys])
        return self.poly_mask(shape, edge)

    def disc_mask(self, shape: tuple, xy, radius: float) -> np.ndarray:
        """지도 점 xy 둘레 반지름 radius m 원의 화면 마스크."""
        a = np.linspace(0, 2 * math.pi, 24, endpoint=False)
        return self.poly_mask(shape, np.stack(
            [xy[0] + radius * np.cos(a), xy[1] + radius * np.sin(a)], 1))


def detect_markers(frame: np.ndarray) -> dict[int, tuple[float, float]]:
    """바닥 ArUco(MARKER_DICT)를 찾아 id → 화면 중심(u, v)."""
    det = cv2.aruco.ArucoDetector(
        cv2.aruco.getPredefinedDictionary(MARKER_DICT),
        cv2.aruco.DetectorParameters())
    corners, ids, _ = det.detectMarkers(
        cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
    if ids is None:
        return {}
    return {int(i): tuple(float(v) for v in c[0].mean(axis=0))
            for i, c in zip(ids.ravel(), corners, strict=True)}


def change_mask(frame: np.ndarray, ref: np.ndarray, floor: np.ndarray,
                thr: float = DIFF_THR) -> np.ndarray:
    """기준 화면과 색이 달라진 곳(floor 안쪽만)의 마스크(uint8 0/255).

    Args:
        frame: 지금 프레임(BGR).
        ref: 빈 바닥 기준 화면(BGR, 같은 크기).
        floor: 볼 곳의 마스크(floor_mask).
        thr: Lab 거리 문턱.

    Returns:
        바뀐 곳 마스크. 잡음은 열기, 덩어리 구멍은 닫기로 정리.
    """
    a = cv2.cvtColor(cv2.GaussianBlur(frame, (5, 5), 0), cv2.COLOR_BGR2LAB)
    b = cv2.cvtColor(cv2.GaussianBlur(ref, (5, 5), 0), cv2.COLOR_BGR2LAB)
    d = np.sqrt(((a.astype(np.float32) - b) ** 2).sum(axis=2))
    m = ((d > thr) & (floor > 0)).astype(np.uint8) * 255
    ker = np.ones((5, 5), np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, ker)
    return cv2.morphologyEx(m, cv2.MORPH_CLOSE, ker, iterations=2)


def site_score(mask: np.ndarray, cal: Calib, xy,
               half: float = SITE_HALF) -> float:
    """지도 점 둘레 정사각형(반 변 half m) 안에서 바뀐 화소 비율(0~1)."""
    x, y = float(xy[0]), float(xy[1])
    sq = [(x - half, y - half), (x + half, y - half), (x + half, y + half),
          (x - half, y + half)]
    win = cal.poly_mask(mask.shape, sq)
    area = int((win > 0).sum())
    if area == 0:
        return 0.0
    return float(((mask > 0) & (win > 0)).sum()) / area


@dataclasses.dataclass
class SpotResult:
    """spot_check() 결과(SpotCheck.srv 응답과 같은 뜻).

    Attributes:
        ok: 점수를 믿을 수 있으면 True.
        scores: 후보마다 바뀐 화소 비율(0~1), 다른 로봇이 설명하면
            EXPLAINED(-1).
        reason: 'OK ...' 또는 실패 사유 코드와 설명(SpotCheck.srv 참고).
    """

    ok: bool
    scores: list[float]
    reason: str


def spot_check(frame: np.ndarray, ref: np.ndarray | None, cal: Calib,
               box: tuple, pts, others=(), explain_dist: float = 0.20,
               scene_max: float = 0.40) -> SpotResult:
    """후보 자리마다 '바뀐 화소 비율'을 구한다.

    Args:
        frame: 지금 프레임(BGR).
        ref: 빈 바닥 기준 화면(없으면 NO_REFERENCE).
        cal: 영상 ↔ 지도 대응.
        box: map_box() 값.
        pts: 후보 위치 [(x, y), ...] m.
        others: 위치가 잡힌 다른 로봇 [(이름, x, y), ...].
        explain_dist: 다른 로봇이 이 거리(m) 안에 있으면 그 자리는 설명됨.
            로봇 크기 12 cm + 위치 오차를 감안. 17-A #26(대칭 자리에서
            15 cm 떨어진 다른 로봇이 0.228 을 만듦)을 덮음.
        scene_max: 바닥 전체에서 바뀐 비율이 이보다 크면 SCENE_CHANGED(카메라
            이동·조명·다른 장면). 17-A 에서 가구 이동이 많은 날도 12.3%.

    Returns:
        SpotResult.
    """
    if ref is None:
        return SpotResult(False, [], 'NO_REFERENCE: 빈 바닥 기준 화면 없음')
    if ref.shape != frame.shape:
        return SpotResult(False, [], f'CAMERA_FAIL: 화면 크기 {frame.shape}'
                                     f' 가 기준 화면 {ref.shape} 와 다름')
    floor = cal.floor_mask(frame.shape, box)
    mask = change_mask(frame, ref, floor)
    changed = float((mask > 0).sum()) / max(1, int((floor > 0).sum()))
    if changed > scene_max:
        return SpotResult(False, [], f'SCENE_CHANGED: 바닥의 {changed:.0%} '
                                     '가 기준 화면과 다름')
    scores, notes = [], []
    for i, (x, y) in enumerate(pts):
        near = [o for o in others
                if math.hypot(o[1] - x, o[2] - y) < explain_dist]
        if near:
            scores.append(EXPLAINED)
            notes.append(f'#{i} {near[0][0]}')
        else:
            scores.append(site_score(mask, cal, (x, y)))
    reason = f'OK calib={cal.source} changed={changed:.1%}'
    if notes:
        reason += ' explained=' + ','.join(notes)
    return SpotResult(True, scores, reason)


def update_reference(ref: np.ndarray, frame: np.ndarray,
                     keep: np.ndarray) -> np.ndarray:
    """기준 화면을 새 프레임으로 바꾸되 keep 마스크 안은 옛 화소를 둔다."""
    out = frame.copy()
    out[keep > 0] = ref[keep > 0]
    return out


def ref_paths(store_dir: str, map_id: str) -> tuple[str, str]:
    """기준 화면 png 와 정보 json 의 경로."""
    d = os.path.join(os.path.expanduser(store_dir), map_id)
    return os.path.join(d, 'reference.png'), os.path.join(d, 'reference.json')


def load_reference(store_dir: str, map_id: str) -> np.ndarray | None:
    """저장된 기준 화면(없으면 None)."""
    png, _ = ref_paths(store_dir, map_id)
    return cv2.imread(png) if os.path.isfile(png) else None


def save_reference(store_dir: str, map_id: str, img: np.ndarray,
                   note: str) -> str:
    """기준 화면을 저장(임시 파일에 쓰고 바꿔 끼움). 경로를 돌려줌."""
    png, info = ref_paths(store_dir, map_id)
    os.makedirs(os.path.dirname(png), exist_ok=True)
    tmp = png + '.tmp.png'
    cv2.imwrite(tmp, img)
    os.replace(tmp, png)
    with open(info, 'w') as stream:
        json.dump({'time': time.time(), 'note': note, 'map_id': map_id},
                  stream)
    return png


def grab(device: str, latest: str = '', max_age: float = 2.0,
         n: int = 3) -> tuple[np.ndarray, str]:
    """카메라에서 프레임 n 장의 중앙값을 받는다(장치는 바로 닫음).

    cam_record 가 장치를 잡고 있으면 열 수 없으므로, cam_record 가 남기는
    최신 프레임 파일(latest)이 max_age 초 안의 것이면 그것을 씀.

    Args:
        device: 장치 경로(/dev/video0).
        latest: 최신 프레임 파일 경로('' 이면 쓰지 않음).
        max_age: 최신 프레임 파일의 허용 나이(s).
        n: 중앙값을 낼 프레임 수.

    Returns:
        (프레임, 출처 'device' 또는 'latest').

    Raises:
        CameraBusyError: 장치를 열 수 없고 쓸 만한 최신 프레임 파일도 없을 때.
        CameraFailError: 장치를 열었지만 읽지 못할 때.
    """
    cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
    if not cap.isOpened():
        cap.release()
        path = os.path.expanduser(latest) if latest else ''
        if path and os.path.isfile(path) and \
                time.time() - os.path.getmtime(path) <= max_age:
            img = cv2.imread(path)
            if img is not None:
                return img, 'latest'
        raise CameraBusyError(f'{device} 를 열 수 없음(다른 프로그램이 쓰는 '
                              '중이고 최신 프레임 파일도 없음)')
    try:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_SIZE[0])
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_SIZE[1])
        for _ in range(3):              # 처음 몇 장은 버림(노출 안정)
            cap.grab()
        frames = []
        for _ in range(n):
            ok, f = cap.read()
            if ok:
                frames.append(f)
    finally:
        cap.release()
    if not frames:
        raise CameraFailError(f'{device} 에서 프레임을 읽지 못함')
    return np.median(np.stack(frames), axis=0).astype(np.uint8), 'device'


def write_latest(path: str, frame: np.ndarray) -> None:
    """최신 프레임 파일을 쓴다(읽는 쪽이 반쪽 파일을 보지 않게 바꿔 끼움)."""
    path = os.path.expanduser(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    ok, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
    if ok:
        tmp = path + '.tmp'
        with open(tmp, 'wb') as stream:
            stream.write(buf.tobytes())
        os.replace(tmp, path)
