#!/usr/bin/env python3
"""천장 카메라 영상에서 로봇 위치를 지도 좌표로 구하는 측정 도구.

# [수정 2026-11-23] 신규: 작업 지시 17 1단계(천장 카메라 초기 위치 측정).
frybot 패키지 코드는 쓰지 않고, 녹화 영상·events.csv·지도만 읽는다.

영상 ↔ 지도 대응:
  1. 배경 화면에서 벽 네 개의 바닥선 점을 손으로 읽음(WALL_PTS).
  2. 그 점들이 곧게 펴지도록 방사 왜곡 계수 k 하나를 맞춤(fit_k).
  3. 왜곡을 편 좌표에서 바닥선끼리의 교점을 네 모서리로 잡고, 지도
     pgm 의 자유 공간 경계(MAP_BOX)와 호모그래피를 구함.

하위 명령:
  offline  녹화 실행 폴더 하나를 평가(정지 구간 참값, 검출 방식 비교)
  capture  카메라에서 프레임 몇 장을 받아 저장(B 단계·기준 화면용)
  locate   저장한 프레임 한 장에서 로봇 위치와 후보 판정
"""

import argparse
import csv
import json
import os
import sys
import time

import cv2
import numpy as np

# 지도 test_map_v04·v05 의 자유 공간 경계(m): pgm(5 cm 격자)에서 읽은 값.
# 실제 벽 면은 경계 칸 안 어딘가이므로 변마다 ±2.5 cm 오차가 있음.
MAP_BOX = {'x0': -0.084, 'x1': 1.816, 'y0': -0.63, 'y1': 0.27}

# 2026-11-20 09 실행 배경(시간 중앙값)에서 4배 확대해 읽은 벽 바닥선
# 화소 점(1280×720). 모서리 점은 두 벽에 모두 들어감. 오른쪽 위
# 모서리는 화면 밖이라 위·오른쪽 선의 교점으로 구함.
WALL_PTS = {
    'top': [(84, 80), (250, 57), (450, 46), (650, 41), (850, 43),
            (1050, 50), (1190, 60)],
    'bottom': [(207, 600), (500, 609), (700, 612), (1120, 604),
               (1172, 601)],
    'left': [(84, 80), (115, 250), (142, 360), (170, 460), (207, 600)],
    'right': [(1272, 210), (1232, 380), (1208, 460), (1172, 601)],
}
CENTER = (640.0, 360.0)   # 왜곡 중심(화면 가운데로 가정)
NORM = 1000.0             # 왜곡 반지름 정규화(화소)

# 로봇 덩어리 크기(화소 넓이): Pinky 윗면 약 11×12 cm ≈ 65×70 화소
BLOB_MIN, BLOB_MAX = 1500, 15000
DIFF_THR = 40             # 배경과의 색 차이 문턱(Lab 거리)
HIT_DIST = 0.30           # 판정 기준: 맞는 후보 30 cm 안, 틀린 후보 밖
# 후보 자리 창의 반 변(m): 로봇 반 크기 6 cm + 보정·시차 오차 여유 4 cm
SITE_HALF = 0.10


def undistort(pts: np.ndarray, k: float) -> np.ndarray:
    """방사 왜곡 한 항(k)으로 화소 좌표를 편다.

    Args:
        pts: (N, 2) 화소 좌표.
        k: 왜곡 계수. 0 이면 그대로.

    Returns:
        (N, 2) 편 좌표.
    """
    p = np.asarray(pts, float) - CENTER
    r2 = (p ** 2).sum(axis=1, keepdims=True) / NORM ** 2
    return p * (1.0 + k * r2) + CENTER


def _line(pts: np.ndarray) -> tuple[np.ndarray, float, float]:
    """점들에 맞춘 직선(법선, 거리)과 잔차 RMS(화소)."""
    c = pts.mean(axis=0)
    _, _, vt = np.linalg.svd(pts - c)
    n = vt[1]
    res = (pts - c) @ n
    return n, float(n @ c), float(np.sqrt((res ** 2).mean()))


def fit_k() -> tuple[float, dict]:
    """벽 바닥선이 가장 곧아지는 왜곡 계수를 격자 탐색으로 찾는다.

    Returns:
        (k, 벽별 잔차 RMS 화소).
    """
    best = None
    for k in np.arange(-0.10, 0.40, 0.002):
        tot = sum(_line(undistort(v, k))[2] ** 2 for v in WALL_PTS.values())
        if best is None or tot < best[1]:
            best = (float(k), tot)
    k = best[0]
    return k, {w: _line(undistort(v, k))[2] for w, v in WALL_PTS.items()}


def _cross(a: str, b: str, k: float) -> np.ndarray:
    """두 벽 직선의 교점(편 좌표)."""
    n1, d1, _ = _line(undistort(WALL_PTS[a], k))
    n2, d2, _ = _line(undistort(WALL_PTS[b], k))
    return np.linalg.solve(np.array([n1, n2]), np.array([d1, d2]))


class Calib:
    """영상 화소 ↔ 지도 좌표 변환(왜곡 한 항 + 호모그래피)."""

    def __init__(self, k: float | None = None) -> None:
        """왜곡 계수 k 가 None 이면 벽 바닥선으로 맞춘다."""
        self.k, self.rms = fit_k() if k is None else (k, {})
        # 모서리: 왼쪽 위, 오른쪽 위, 오른쪽 아래, 왼쪽 아래
        self.corners = np.array([
            _cross('top', 'left', self.k), _cross('top', 'right', self.k),
            _cross('bottom', 'right', self.k),
            _cross('bottom', 'left', self.k)])
        b = MAP_BOX
        world = np.array([[b['x0'], b['y1']], [b['x1'], b['y1']],
                          [b['x1'], b['y0']], [b['x0'], b['y0']]])
        self.h = cv2.getPerspectiveTransform(
            self.corners.astype(np.float32), world.astype(np.float32))
        self.hinv = np.linalg.inv(self.h)

    def to_map(self, px: np.ndarray) -> np.ndarray:
        """화소 (N, 2) → 지도 (N, 2) m."""
        u = undistort(np.atleast_2d(px), self.k).reshape(-1, 1, 2)
        return cv2.perspectiveTransform(u.astype(np.float64), self.h)[:, 0]

    def to_pix(self, xy: np.ndarray) -> np.ndarray:
        """지도 (N, 2) m → 화소 (N, 2). 왜곡은 뉴턴 반복으로 되돌림."""
        w = np.atleast_2d(np.asarray(xy, float)).reshape(-1, 1, 2)
        u = cv2.perspectiveTransform(w, self.hinv)[:, 0]
        p = u.copy()
        for _ in range(20):
            p = p - (undistort(p, self.k) - u)
        return p

    def floor_mask(self, shape: tuple) -> np.ndarray:
        """지도 자유 공간 안쪽(벽에서 2 cm 들어온 곳)의 화면 마스크."""
        b, m = MAP_BOX, 0.02
        xs = np.linspace(b['x0'] + m, b['x1'] - m, 40)
        ys = np.linspace(b['y0'] + m, b['y1'] - m, 20)
        edge = ([(x, ys[-1]) for x in xs] + [(xs[-1], y) for y in ys[::-1]]
                + [(x, ys[0]) for x in xs[::-1]] + [(xs[0], y) for y in ys])
        poly = self.to_pix(np.array(edge)).astype(np.int32)
        mask = np.zeros(shape[:2], np.uint8)
        cv2.fillPoly(mask, [poly], 255)
        return mask


def change_mask(frame: np.ndarray, ref: np.ndarray,
                floor: np.ndarray) -> np.ndarray:
    """기준 화면과 색이 달라진 곳(바닥 안쪽만)의 이진 마스크."""
    a = cv2.cvtColor(cv2.GaussianBlur(frame, (5, 5), 0), cv2.COLOR_BGR2LAB)
    b = cv2.cvtColor(cv2.GaussianBlur(ref, (5, 5), 0), cv2.COLOR_BGR2LAB)
    d = np.sqrt(((a.astype(np.float32) - b) ** 2).sum(axis=2))
    m = ((d > DIFF_THR) & (floor > 0)).astype(np.uint8) * 255
    ker = np.ones((5, 5), np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, ker)
    return cv2.morphologyEx(m, cv2.MORPH_CLOSE, ker, iterations=2)


def blobs(mask: np.ndarray) -> list[tuple[float, float, int]]:
    """로봇 크기 덩어리의 (중심 u, 중심 v, 넓이) 목록."""
    n, _, st, cen = cv2.connectedComponentsWithStats(mask)
    return [(float(cen[i][0]), float(cen[i][1]), int(st[i][4]))
            for i in range(1, n) if BLOB_MIN <= st[i][4] <= BLOB_MAX]


def site_score(mask: np.ndarray, cal: Calib, xy: tuple) -> float:
    """지도 점 둘레 정사각형(반 변 SITE_HALF) 안에서 바뀐 화소 비율."""
    h = SITE_HALF
    sq = np.array([[xy[0] - h, xy[1] - h], [xy[0] + h, xy[1] - h],
                   [xy[0] + h, xy[1] + h], [xy[0] - h, xy[1] + h]])
    poly = cal.to_pix(sq).astype(np.int32)
    win = np.zeros(mask.shape, np.uint8)
    cv2.fillPoly(win, [poly], 255)
    area = max(1, int((win > 0).sum()))
    return float(((mask > 0) & (win > 0)).sum()) / area


def median_bg(path: str, n: int = 80) -> np.ndarray:
    """영상 전체에서 고르게 n 장을 뽑아 시간 중앙값 배경을 만든다."""
    cap = cv2.VideoCapture(path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frames = []
    for i in np.linspace(0, total - 1, n).astype(int):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(i))
        ok, f = cap.read()
        if ok:
            frames.append(f)
    return np.median(np.stack(frames), axis=0).astype(np.uint8)


def stand_intervals(events: str, nodes: dict, min_sec: float = 4.0) -> list:
    """events.csv 에서 로봇이 노드에 서 있던 구간을 고른다.

    ZONE_ENTER 와 같은 때 TASK_DONE·HOME·ARM_START 가 있거나 실행 첫
    노드(MOVE_TO_VERTEX 전 자리)인 경우만 '정지'로 보고, 그 노드의
    다음 ZONE_EXIT 까지를 구간으로 함. 시작 2초는 정착 시간으로 뺌.

    Args:
        events: events.csv 경로.
        nodes: 노드 이름 → (x, y).
        min_sec: 이보다 짧은 구간은 버림.

    Returns:
        (로봇, 노드, 시작, 끝) 목록.
    """
    rows = list(csv.DictReader(open(events)))
    stop_ev = {'TASK_DONE', 'HOME', 'ARM_START'}
    out = []
    for i, r in enumerate(rows):
        if r['event'] != 'ZONE_ENTER' or r['zone_id'] not in nodes:
            continue
        t = float(r['timestamp'])
        rid, node = r['robot_id'], r['zone_id']
        near = [q for q in rows[max(0, i - 4):i + 5]
                if q['robot_id'] == rid
                and abs(float(q['timestamp']) - t) < 0.05]
        if not any(q['event'] in stop_ev for q in near):
            continue
        end = next((float(q['timestamp']) for q in rows[i + 1:]
                    if q['event'] == 'ZONE_EXIT' and q['robot_id'] == rid),
                   None)
        out.append((rid, node, t + 2.0, end))
    # 첫 ZONE_EXIT 전 자리(실행 시작 때 서 있던 노드)
    for rid in sorted({r['robot_id'] for r in rows if r['robot_id']}):
        ex = [r for r in rows if r['event'] == 'ZONE_EXIT'
              and r['robot_id'] == rid]
        if ex and ex[0]['zone_id'] in nodes:
            out.append((rid, ex[0]['zone_id'], None,
                        float(ex[0]['timestamp'])))
    return [o for o in out
            if o[2] is None or o[3] is None or o[3] - o[2] >= min_sec]


def frame_at(cap: cv2.VideoCapture, stamps: np.ndarray,
             t: float) -> np.ndarray | None:
    """시각 t(unix 초)에 가장 가까운 프레임."""
    i = int(np.argmin(np.abs(stamps - t)))
    if abs(stamps[i] - t) > 0.5:
        return None
    cap.set(cv2.CAP_PROP_POS_FRAMES, i)
    ok, f = cap.read()
    return f if ok else None


def symmetric(xy: tuple) -> tuple[float, float]:
    """지도 가운데를 중심으로 180도 돌린 점(라이다 대칭 후보의 근사)."""
    b = MAP_BOX
    return (b['x0'] + b['x1'] - xy[0], b['y0'] + b['y1'] - xy[1])


def evaluate(run: str, map_dir: str, refs: dict, cal: Calib,
             out_dir: str, tag: str) -> list[dict]:
    """한 실행의 정지 구간마다 방식별 위치를 구해 행 목록을 돌려준다.

    Args:
        run: 실행 폴더(camera_*.mp4, *_frames.csv, events.csv).
        map_dir: 지도 폴더(roadmap.json).
        refs: 방식 이름 → 기준 화면.
        cal: 화소 ↔ 지도 변환.
        out_dir: 검출 화면을 저장할 폴더.
        tag: 실행 짧은 이름.

    Returns:
        구간·방식별 결과 dict 목록.
    """
    nodes = json.load(open(os.path.join(map_dir, 'roadmap.json')))['nodes']
    vid = sorted(f for f in os.listdir(run)
                 if f.startswith('camera_') and f.endswith('.mp4'))[-1]
    stamps = np.array([float(r['timestamp']) for r in csv.DictReader(
        open(os.path.join(run, vid[:-4] + '_frames.csv')))])
    cap = cv2.VideoCapture(os.path.join(run, vid))
    t0, t1 = stamps[0], stamps[-1]
    rows = []
    for rid, node, a, b in stand_intervals(os.path.join(run, 'events.csv'),
                                           nodes):
        a = t0 + 1.0 if a is None else a
        b = t1 if b is None else b
        if a < t0 or a > t1:
            continue
        t = min(a + 1.0, (a + min(b, t1)) / 2)
        f = frame_at(cap, stamps, t)
        if f is None:
            continue
        truth = tuple(nodes[node])
        sym = symmetric(truth)
        floor = cal.floor_mask(f.shape)
        for meth, ref in refs.items():
            m = change_mask(f, ref, floor)
            bl = blobs(m)
            pts = cal.to_map(np.array([[u, v] for u, v, _ in bl])) \
                if bl else np.zeros((0, 2))
            d = np.hypot(*(pts - truth).T) if len(pts) else np.array([])
            j = int(np.argmin(d)) if len(d) else -1
            s_t, s_s = site_score(m, cal, truth), site_score(m, cal, sym)
            rows.append({
                'run': tag, 'robot': rid, 'node': node, 't': round(t, 2),
                'method': meth, 'truth_x': truth[0], 'truth_y': truth[1],
                'cam_x': round(float(pts[j][0]), 3) if j >= 0 else '',
                'cam_y': round(float(pts[j][1]), 3) if j >= 0 else '',
                'err_cm': round(float(d[j]) * 100, 1) if j >= 0 else '',
                'blob_u': round(bl[j][0]) if j >= 0 else '',
                'blob_v': round(bl[j][1]) if j >= 0 else '',
                'n_blobs': len(bl), 'site_true': round(s_t, 3),
                'site_sym': round(s_s, 3), 'sym_x': round(sym[0], 3),
                'sym_y': round(sym[1], 3)})
            if meth == list(refs)[0]:
                vis = f.copy()
                vis[m > 0] = (0.5 * vis[m > 0] + (0, 0, 127)).astype(
                    np.uint8)
                for u, v, _ in bl:
                    cv2.circle(vis, (int(u), int(v)), 6, (0, 255, 0), -1)
                tp = cal.to_pix(np.array([truth]))[0]
                cv2.drawMarker(vis, (int(tp[0]), int(tp[1])), (255, 0, 0),
                               cv2.MARKER_CROSS, 20, 2)
                cv2.imwrite(os.path.join(
                    out_dir, f'{tag}_{rid}_{node}_{int(t)}.jpg'), vis)
    return rows


def cmd_offline(args: argparse.Namespace) -> None:
    """하위 명령 offline: 실행 폴더들을 평가해 CSV 와 요약을 쓴다."""
    cal = Calib(None if args.k is None else args.k)
    os.makedirs(args.out, exist_ok=True)
    print(f'왜곡 k = {cal.k:.3f}, 벽 잔차 RMS(px) = '
          + ', '.join(f'{w} {v:.1f}' for w, v in cal.rms.items()))
    print('모서리(편 좌표 px):', np.round(cal.corners, 1).tolist())
    bgs = {}
    for run in args.runs:
        vid = sorted(f for f in os.listdir(run)
                     if f.startswith('camera_') and f.endswith('.mp4'))[-1]
        bgs[run] = median_bg(os.path.join(run, vid))
        cv2.imwrite(os.path.join(args.out, os.path.basename(run.rstrip('/'))
                                 + '_bg.png'), bgs[run])
    extra = {os.path.basename(p): cv2.imread(p) for p in args.ref}
    rows = []
    for run, mp in zip(args.runs, args.maps, strict=True):
        tag = os.path.basename(run.rstrip('/'))[:11]
        refs = {'a_own_median': bgs[run]}
        for other, img in bgs.items():
            if other != run:
                refs['b_other_run'] = img
        for name, img in extra.items():
            refs['b_' + name] = img
        rows += evaluate(run, mp, refs, cal, args.out, tag)
    with open(os.path.join(args.out, 'results.csv'), 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    # 기준 화면끼리의 차이: 가구가 옮겨졌을 때 생기는 가짜 덩어리 수
    floor = cal.floor_mask(next(iter(bgs.values())).shape)
    imgs = {os.path.basename(k.rstrip('/')): v for k, v in bgs.items()}
    imgs.update(extra)
    names = list(imgs)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            m = change_mask(imgs[a], imgs[b], floor)
            print(f'기준 화면 차이 {a} vs {b}: 덩어리 {len(blobs(m))}개, '
                  f'바뀐 바닥 {100 * (m > 0).sum() / (floor > 0).sum():.1f}%')
    print(f'{len(rows)}행 → {os.path.join(args.out, "results.csv")}')


def cmd_capture(args: argparse.Namespace) -> None:
    """하위 명령 capture: 카메라 프레임을 몇 장 받아 저장한다."""
    cap = cv2.VideoCapture(args.device, cv2.CAP_V4L2)
    if not cap.isOpened():
        sys.exit(f'{args.device}를 열 수 없음'
                 '(다른 프로그램이 쓰는 중인지 확인)')
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    os.makedirs(args.out, exist_ok=True)
    for _ in range(15):            # 노출이 자리 잡을 때까지 버림
        cap.read()
    frames = []
    for _ in range(args.n):
        ok, f = cap.read()
        if ok:
            frames.append(f)
        time.sleep(0.1)
    cap.release()
    if not frames:
        sys.exit('프레임을 읽지 못함')
    stamp = time.strftime('%Y%m%d_%H%M%S')
    path = os.path.join(args.out, f'ceiling_{args.name}_{stamp}.png')
    cv2.imwrite(path, np.median(np.stack(frames), axis=0).astype(np.uint8))
    print(path, frames[0].shape)


def cmd_locate(args: argparse.Namespace) -> None:
    """하위 명령 locate: 프레임 한 장에서 로봇 위치·후보 판정을 출력."""
    cal = Calib(None if args.k is None else args.k)
    f, ref = cv2.imread(args.frame), cv2.imread(args.ref)
    m = change_mask(f, ref, cal.floor_mask(f.shape))
    bl = blobs(m)
    for u, v, area in bl:
        x, y = cal.to_map(np.array([[u, v]]))[0]
        print(f'덩어리 화소 ({u:.0f}, {v:.0f}) 넓이 {area} → '
              f'지도 ({x:.3f}, {y:.3f})')
    for c in args.cand:
        x, y = (float(v) for v in c.split(','))
        print(f'후보 ({x:.3f}, {y:.3f}): 바뀐 비율 '
              f'{site_score(m, cal, (x, y)):.3f}')


def main() -> None:
    """명령줄 진입점."""
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--k', type=float, default=None,
                    help='왜곡 계수(비우면 벽 바닥선으로 맞춤, 0 이면 끔)')
    sub = ap.add_subparsers(dest='cmd', required=True)
    o = sub.add_parser('offline', help='녹화 실행 폴더 평가')
    o.add_argument('--runs', nargs='+', required=True)
    o.add_argument('--maps', nargs='+', required=True)
    o.add_argument('--ref', nargs='*', default=[],
                   help='다른 때 찍은 기준 화면(빈 바닥) 이미지')
    o.add_argument('--out', required=True)
    c = sub.add_parser('capture', help='카메라 프레임 저장')
    c.add_argument('--device', default='/dev/video0')
    c.add_argument('--n', type=int, default=10)
    c.add_argument('--name', default='frame')
    c.add_argument('--out', required=True)
    lo = sub.add_parser('locate', help='프레임 한 장 판정')
    lo.add_argument('--frame', required=True)
    lo.add_argument('--ref', required=True)
    lo.add_argument('--cand', nargs='*', default=[], help='x,y 후보 점')
    args = ap.parse_args()
    {'offline': cmd_offline, 'capture': cmd_capture,
     'locate': cmd_locate}[args.cmd](args)


if __name__ == '__main__':
    main()
