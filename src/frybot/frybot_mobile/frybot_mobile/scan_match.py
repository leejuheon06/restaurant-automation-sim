"""라이다 스캔 한 장을 지도에 맞춰 로봇 자세를 찾는다(ROS 없이 쓰는 계산부).

[수정 2026-11-20] T-49: 신규. 기획 패널의 scan_fit.py(지도 거리장 + (x, y,
yaw) 격자 탐색 + 미세 탐색)와 scripts/relocalize.py 를 정식 코드로 옮김.
지도는 map_id 의 것을 쓰고, 다른 로봇·사람이 스캔에 섞여도 견디도록 점마다
벽까지의 거리를 상한(dist_cap)에서 잘라 평균함. 비슷한 모양의 자리가 여럿인
지도(test_map_v05 의 W1·W2·W3)를 위해, 가장 좋은 후보와 떨어진 다음 후보의
점수 차가 작으면 '모호'로 판정함.

점수 = 스캔 점마다 '가장 가까운 지도 벽까지 거리'를 dist_cap 에서 자른 평균
(m, 작을수록 잘 맞음). 잡음 1 cm 의 맞는 자세는 약 0.01, 틀린 자세는 0.04
이상(가짜 스캔 시험, docs/TROUBLESHOOTING.md T-49).
"""
from __future__ import annotations

from collections.abc import Callable
import dataclasses
import math
import os
import time

import cv2
import numpy as np
import yaml

# 거리장 격자(m). 지도 셀(5 cm)을 5배로 나눠 벽 표면 위치를 1 cm 로 다룸
_FINE = 0.01


@dataclasses.dataclass
class Candidate:
    """자세 후보와 점수."""

    x: float  # 지도(map) 좌표 x(m)
    y: float  # 지도(map) 좌표 y(m)
    yaw: float  # 방향(rad, -pi..pi)
    score: float  # score() 값(m, 작을수록 잘 맞음)


@dataclasses.dataclass
class MatchResult:
    """localize() 의 결과.

    Attributes:
        pose: 고른 자세(없으면 None: 모호하거나 맞는 자세 없음).
        best: 점수가 가장 좋은 후보.
        second: best 와 떨어진 후보 중 가장 좋은 것(없으면 None).
        status: 'OK', 'OK_SAVED'(모호하지만 저장 자세 쪽을 고름),
            'OK_HOME'(모호하지만 홈 근처 후보를 고름),
            'OK_CAMERA'(모호하지만 천장 카메라가 한 후보를 고름, T-55),
            'AMBIGUOUS', 'NO_MATCH', 'TIMEOUT'.
        seconds: 걸린 시간.
        camera: 카메라 판정 한 줄(점수와 이유). 묻지 않았으면 ''.

    걸린 시간의 단위는 초(time.monotonic 기준).
    """

    pose: Candidate | None
    best: Candidate | None
    second: Candidate | None
    status: str
    seconds: float
    # [수정 2026-11-23] T-55: 카메라 판정 기록(로그용)
    camera: str = ''


# [수정 2026-11-23] T-55: 신규. 천장 카메라 점수로 모호한 후보 중 하나를 고름
def pick_by_camera(cands: list[Candidate], scores: list[float],
                   hi: float = 0.15, lo: float = 0.05,
                   sep: float = 0.30) -> tuple[int | None, str]:
    """카메라 점수(후보 자리의 바뀐 화소 비율)로 후보 하나를 고른다.

    한 후보만 hi 이상이고 나머지는 모두 lo 이하이며, 그 후보와 나머지가
    모두 sep 넘게 떨어져 있을 때만 고름. 점수가 -1(다른 로봇이 설명하는
    자리)인 후보가 있으면 고르지 않음.

    기준값 근거(작업 지시 17 A·B, 20 cm 창): 로봇이 선 자리 0.168~0.574
    (A 28구간, B 4곳), 빈 자리 0.000~0.050(가구가 옮겨진 오래된 기준 화면
    포함). 고르지 말아야 할 경우: 가운데 C2 의 앞뒤 혼동 0.294/0.146(두 후보
    11 cm), 다른 로봇이 대칭 자리 15 cm 옆 0.314/0.228(17-A #26).

    Args:
        cands: 후보들.
        scores: 후보마다 카메라 점수(같은 순서).
        hi: 로봇이 있다고 볼 최소 점수.
        lo: 로봇이 없다고 볼 최대 점수.
        sep: 고른 후보와 나머지 사이 최소 거리(m).

    Returns:
        (고른 후보 번호 또는 None, 이유).
    """
    if len(scores) != len(cands) or not cands:
        return None, 'score count mismatch'
    if any(s < 0 for s in scores):
        return None, 'a candidate is explained by another robot'
    hits = [i for i, s in enumerate(scores) if s >= hi]
    if len(hits) != 1:
        return None, f'{len(hits)} candidates scored >= {hi}'
    k = hits[0]
    for i, s in enumerate(scores):
        if i == k:
            continue
        if s > lo:
            return None, f'#{i} scored {s:.3f} > {lo}'
        if math.hypot(cands[i].x - cands[k].x,
                      cands[i].y - cands[k].y) <= sep:
            return None, f'#{i} is within {sep} m of #{k}'
    return k, f'#{k} scored {scores[k]:.3f}, others <= {lo}'


def _wrap(a: float) -> float:
    """각도를 -pi..pi 로 맞춘다."""
    return math.atan2(math.sin(a), math.cos(a))


class ScanMatcher:
    """지도 하나에 대한 스캔 맞춤기.

    Args:
        map_yaml: Nav2 지도 yaml 경로(image, resolution, origin,
            occupied_thresh, negate).
        lidar_offset: 로봇 중심(base_footprint) 기준 라이다 자세 (x, y,
            yaw). Pinky 는 (-0.017, 0, pi)(URDF rplidar_mount, 거꾸로 붙음).
        dist_cap: 점수의 점별 거리 상한(m). 지도에 없는 물체(다른 로봇,
            사람)에 맞은 점이 점수를 크게 흔들지 않게 함. 0.10: 맞는 자세의
            점은 대부분 2 cm 안이라 영향 없고, 가린 점 하나는 최대 10 cm 만
            더함.
        clearance: 후보 중심이 지도 벽에서 떨어져야 하는 거리(m). 로봇 반폭
            5.7 cm 보다 약간 작게 0.05(지도 해상도 5 cm 의 벽 위치 오차).
    """

    def __init__(self, map_yaml: str,
                 lidar_offset: tuple[float, float, float] = (-0.017, 0.0,
                                                             math.pi),
                 dist_cap: float = 0.10, clearance: float = 0.05) -> None:
        with open(map_yaml) as stream:
            meta = yaml.safe_load(stream)
        # image 는 yaml 기준 상대 경로(Nav2 map_server 와 같은 규칙)
        image = os.path.join(os.path.dirname(map_yaml), meta['image'])
        img = cv2.imread(image, cv2.IMREAD_GRAYSCALE)
        if img is None:
            raise OSError(f'cannot read map image {image}')
        # 칸마다 점유 확률(0~1). negate=0 이면 어두울수록 점유
        # (map_server 규칙)
        occ_p = (img.astype(np.float32) / 255.0 if meta.get('negate', 0)
                 else (255.0 - img.astype(np.float32)) / 255.0)
        occupied = occ_p > float(meta.get('occupied_thresh', 0.65))
        res = float(meta['resolution'])
        # 지도 한 칸을 k x k 의 고운 칸(_FINE)으로 쪼갬. 5 cm 지도면 k = 5
        k = max(1, int(round(res / _FINE)))
        fine = np.kron(occupied.astype(np.uint8), np.ones((k, k), np.uint8))
        # 벽(점유) 칸까지의 거리. 점유 칸 자신은 0
        self.dist = cv2.distanceTransform((fine == 0).astype(np.uint8),
                                          cv2.DIST_L2, 5) * (res / k)
        self.cell = res / k  # 거리장 한 칸 크기(m)
        self.h, self.w = self.dist.shape  # 거리장 행·열 수
        # 지도 왼쪽 아래 칸의 지도 좌표(m). origin 의 yaw 는 쓰지 않음
        # (확인 필요: yaw 가 0 이 아닌 지도)
        self.ox, self.oy = float(meta['origin'][0]), float(meta['origin'][1])
        self.lidar = lidar_offset  # (x, y, yaw) 로봇 기준 라이다 자세
        self.cap = dist_cap
        self.clearance = clearance

    # ------------------------------------------------------------ 기본 계산
    def lookup(self, wx: np.ndarray, wy: np.ndarray) -> np.ndarray:
        """지도 좌표 점들의 벽까지 거리(지도 밖은 dist_cap)."""
        # 지도 좌표 -> 거리장 열(c)·행(r). 이미지는 위쪽이 행 0 이라 y 를 뒤집음
        c = np.floor((wx - self.ox) / self.cell).astype(np.int64)
        r = self.h - 1 - np.floor((wy - self.oy) / self.cell).astype(np.int64)
        inside = (c >= 0) & (c < self.w) & (r >= 0) & (r < self.h)
        d = np.full(wx.shape, self.cap, np.float32)
        d[inside] = self.dist[r[inside], c[inside]]
        return np.minimum(d, self.cap)

    def points(self, ranges: np.ndarray, angle_min: float,
               angle_inc: float, max_points: int = 120,
               rmin: float = 0.06, rmax: float = 3.0) -> np.ndarray:
        """스캔을 로봇 기준 점 배열 (N, 2) 로 바꾼다(고르게 솎음).

        Args:
            ranges: 거리 배열.
            angle_min: 첫 광선 각도(라이다 기준).
            angle_inc: 광선 간격.
            max_points: 쓸 점의 최대 수(Pi CPU).
            rmin: 이보다 가까운 점(자기 몸)은 버림.
            rmax: 이보다 먼 점은 버림.

        Returns:
            로봇 기준 (x, y) 점들.
        """
        rng = np.asarray(ranges, np.float64)
        ang = angle_min + angle_inc * np.arange(len(rng))
        ok = np.isfinite(rng) & (rng >= rmin) & (rng <= rmax)
        rng, ang = rng[ok], ang[ok]
        if len(rng) > max_points:
            idx = np.linspace(0, len(rng) - 1, max_points).astype(int)
            rng, ang = rng[idx], ang[idx]
        # 라이다 기준 극좌표 -> 로봇(base_footprint) 기준 x, y
        lx, ly, la = self.lidar
        return np.stack([lx + rng * np.cos(la + ang),
                         ly + rng * np.sin(la + ang)], axis=1)

    def score(self, pts: np.ndarray, x: float, y: float,
              yaw: float) -> float:
        """한 자세의 점수(평균 거리, 작을수록 좋음)."""
        # 로봇 기준 점을 (x, y, yaw) 자세로 지도 좌표에 옮김
        c, s = math.cos(yaw), math.sin(yaw)
        wx = x + pts[:, 0] * c - pts[:, 1] * s
        wy = y + pts[:, 0] * s + pts[:, 1] * c
        return float(self.lookup(wx, wy).mean())

    def refine(self, pts: np.ndarray, cand: Candidate,
               step: float = 0.02, ystep: float = math.radians(4),
               min_step: float = 0.0025) -> Candidate:
        """패턴 탐색으로 후보 근처의 더 나은 자세를 찾는다."""
        # 인자: pts 는 points() 의 점, cand 는 시작 후보, step·ystep 은 처음
        # 위치(m)·방향(rad) 보폭, min_step 은 멈출 위치 보폭(m).
        # 돌려주는 값: 점수가 같거나 더 좋은 Candidate.
        # 6 방향(+-x, +-y, +-yaw)으로 한 칸씩 움직여 좋아지는 동안 계속 가고,
        # 더 나아지지 않으면 보폭을 반으로 줄임
        best = cand
        while step >= min_step:
            moved = True
            while moved:
                moved = False
                for dx, dy, da in ((step, 0, 0), (-step, 0, 0),
                                   (0, step, 0), (0, -step, 0),
                                   (0, 0, ystep), (0, 0, -ystep)):
                    c = Candidate(best.x + dx, best.y + dy,
                                  _wrap(best.yaw + da), 0.0)
                    c.score = self.score(pts, c.x, c.y, c.yaw)
                    if c.score < best.score - 1e-6:
                        best, moved = c, True
            step, ystep = step / 2, ystep / 2
        return best

    # ------------------------------------------------------------ 전체 탐색
    def global_search(self, pts: np.ndarray, step: float = 0.04,
                      yaw_step_deg: float = 5.0, keep: int = 40,
                      deadline: float = math.inf) -> list[Candidate]:
        """지도 전체의 거친 격자에서 좋은 후보를 고른다(겹침 제거).

        Returns:
            점수 순 후보 목록(서로 15 cm 또는 25도 넘게 떨어짐).

        인자: pts 는 points() 의 점, step 은 위치 격자(m), yaw_step_deg 는
        방향 격자(도), keep 은 방향마다·최종으로 남길 후보 수, deadline 은
        time.monotonic() 기준 마감 시각(넘으면 남은 방향을 건너뜀).
        """
        # 벽에서 clearance 넘게 떨어진 칸만 후보 위치로 씀
        ys, xs = np.nonzero(self.dist >= self.clearance)
        gx = self.ox + (xs + 0.5) * self.cell
        gy = self.oy + (self.h - 1 - ys + 0.5) * self.cell
        # 고운 칸을 step 격자로 묶어 격자마다 첫 칸 하나만 남김
        keyx, keyy = np.round(gx / step), np.round(gy / step)
        _, first = np.unique(np.stack([keyx, keyy], 1), axis=0,
                             return_index=True)
        cx, cy = gx[first], gy[first]
        out = []
        # 방향마다 모든 후보 위치의 점수를 한꺼번에(numpy 브로드캐스트) 계산
        for a in np.radians(np.arange(0.0, 360.0, yaw_step_deg)):
            if time.monotonic() > deadline:
                break
            c, s = math.cos(a), math.sin(a)
            rx = pts[:, 0] * c - pts[:, 1] * s
            ry = pts[:, 0] * s + pts[:, 1] * c
            d = self.lookup(cx[:, None] + rx[None, :],
                            cy[:, None] + ry[None, :]).mean(axis=1)
            top = np.argsort(d)[:keep]
            out += [Candidate(float(cx[i]), float(cy[i]), _wrap(float(a)),
                              float(d[i])) for i in top]
        # 점수 순으로 보며 이미 고른 후보와 가까운 것(겹침)은 버림
        out.sort(key=lambda k: k.score)
        picked: list[Candidate] = []
        for k in out:
            if all(not _close(k, p, 0.15, math.radians(25)) for p in picked):
                picked.append(k)
            if len(picked) >= keep:
                break
        return picked

    def localize(self, pts: np.ndarray,
                 saved: tuple[float, float, float] | None = None,
                 max_score: float = 0.03, margin: float = 0.006,
                 distinct_dist: float = 0.20,
                 distinct_yaw: float = math.radians(30),
                 saved_dist: float = 0.30,
                 saved_yaw: float = math.radians(30),
                 budget: float = 30.0,
                 home: tuple[float, float] | None = None,
                 home_dist: float = 0.30,
                 chooser: Callable[[list[Candidate]],
                                   tuple[int | None, str]] | None = None
                 ) -> MatchResult:
        """스캔으로 자세를 정한다.

        순서: (1) 저장 자세가 있으면 그 근처를 미세 탐색해 후보로 넣음
        (2) 전체 지도 탐색(로봇이 꺼진 동안 옮겨졌을 수 있어 항상 함).
        가장 좋은 후보 best 와, best 에서 distinct_dist 또는 distinct_yaw
        넘게 다른 후보 중 가장 좋은 second 의 점수 차가 margin 미만이면
        모호. 모호하면 저장 자세에서 saved_dist·saved_yaw 안에 있고 점수가
        best + margin 안인 후보를 고르고, 없으면 홈 근처 후보(home), 그것도
        없으면 자세를 정하지 않음.

        Args:
            pts: points() 의 로봇 기준 점.
            saved: 마지막 저장 자세 (x, y, yaw) 또는 None.
            max_score: 이보다 점수가 나쁘면 맞는 자세 없음(NO_MATCH).
            margin: 모호 판정의 점수 차(m).
            distinct_dist: '다른 후보'로 볼 위치 차(m).
            distinct_yaw: '다른 후보'로 볼 방향 차(rad).
            saved_dist: 저장 자세에 '가깝다'고 볼 위치 차(m).
            saved_yaw: 저장 자세에 '가깝다'고 볼 방향 차(rad).
            budget: 탐색 시간 상한(s). 넘으면 TIMEOUT(자세 없음).
            home: [수정 2026-11-20] T-50: 자기 홈 노드 (x, y). 모호하고
                저장 자세 근처 후보가 없으면(저장 자세가 없거나 어느 후보와도
                맞지 않으면, T-51) 홈에서 home_dist 안 후보를 고름(OK_HOME).
                홈 노드에는 방향이 없어 거리만 봄. None 이면 쓰지 않음.
            home_dist: 홈 근처로 볼 거리(m).
            chooser: [수정 2026-11-23] T-55: 모호할 때 가장 먼저 부름.
                best 와 점수 차 margin 안의 서로 다른 후보 목록을 받아
                (고른 번호 또는 None, 기록용 글)을 돌려줌(천장 카메라).
                None 을 돌려주면 저장 자세 -> 홈 규칙으로 넘어감.

        Returns:
            MatchResult.
        """
        t0 = time.monotonic()
        deadline = t0 + budget
        cands = []  # 미세 탐색까지 마친 후보들
        if saved is not None:
            s = Candidate(saved[0], saved[1], saved[2], 0.0)
            s.score = self.score(pts, s.x, s.y, s.yaw)
            cands.append(self.refine(pts, s, step=0.04,
                                     ystep=math.radians(8)))
        coarse = self.global_search(pts, deadline=deadline)
        timed_out = time.monotonic() > deadline
        # 거친 후보 중 상위 20개만 미세 탐색(시간 절약)
        for c in coarse[:20]:
            if time.monotonic() > deadline:
                timed_out = True
                break
            cands.append(self.refine(pts, c))
        took = time.monotonic() - t0
        if not cands:
            return MatchResult(None, None, None, 'TIMEOUT', took)
        cands.sort(key=lambda k: k.score)
        best = cands[0]
        second = next((c for c in cands[1:] if not _close(
            c, best, distinct_dist, distinct_yaw)), None)
        if timed_out:
            return MatchResult(None, best, second, 'TIMEOUT', took)
        if best.score > max_score:
            return MatchResult(None, best, second, 'NO_MATCH', took)
        # 다른 자리 후보와 점수 차가 충분하면 모호하지 않음
        if second is None or second.score - best.score >= margin:
            return MatchResult(best, best, second, 'OK', took)
        # [수정 2026-11-23] T-55: 모호하면 먼저 천장 카메라에 물음. 저장
        # 자세·홈은 '로봇이 그 자리에 있었다'는 가정이라, 대칭 자리로 옮겨
        # 놓으면 틀린 자세를 넣었음(17-B 2번 OK_SAVED, 18-T 2회차 OK_HOME)
        camera = ''
        if chooser is not None:
            amb: list[Candidate] = []
            for c in cands:
                if c.score < best.score + margin and all(not _close(
                        c, a, distinct_dist, distinct_yaw) for a in amb):
                    amb.append(c)
            pick, camera = chooser(amb)
            if pick is not None:
                return MatchResult(amb[pick], best, second, 'OK_CAMERA',
                                   time.monotonic() - t0, camera)
        # 모호: 저장 자세 근처이면서 best 와 점수 차 margin 안인 후보 우선
        if saved is not None:
            sv = Candidate(saved[0], saved[1], saved[2], 0.0)
            near = [c for c in cands if c.score < best.score + margin
                    and _close(c, sv, saved_dist, saved_yaw)]
            if near:
                return MatchResult(near[0], best, second, 'OK_SAVED', took,
                                   camera)
        # [수정 2026-11-20] T-50: 저장 자세가 없으면(첫 기동) 자기 홈 노드
        # 근처 후보. 대칭 후보가 홈 근처가 아니면 그대로 AMBIGUOUS
        # [수정 2026-11-20] T-51: 저장 자세가 있어도 어느 후보와도 맞지 않으면
        # (사람이 로봇을 홈으로 옮겨 놓음, 실기기 09) 홈 근처 후보로 넘어감
        if home is not None:
            near = [c for c in cands if c.score < best.score + margin
                    and math.hypot(c.x - home[0], c.y - home[1])
                    <= home_dist]
            if len(near) == 1 or (near and all(_close(
                    c, near[0], distinct_dist, distinct_yaw)
                    for c in near)):
                return MatchResult(near[0], best, second, 'OK_HOME', took,
                                   camera)
        return MatchResult(None, best, second, 'AMBIGUOUS', took, camera)

    # [수정 2026-11-20] T-50: 신규. 위치 추정 감시·보정용 좁은 탐색
    def local_search(self, pts: np.ndarray, x: float, y: float, yaw: float,
                     radius: float = 0.20,
                     yaw_range: float = math.radians(45),
                     step: float = 0.02,
                     yaw_step: float = math.radians(3)) -> Candidate:
        """(x, y, yaw) 주변만 격자로 훑고 가장 좋은 자세를 다듬는다.

        Args:
            pts: points() 의 로봇 기준 점.
            x: 지금 자세 x.
            y: 지금 자세 y.
            yaw: 지금 자세 방향.
            radius: 위치 탐색 반경(m).
            yaw_range: 방향 탐색 범위(+-, rad).
            step: 위치 격자(m).
            yaw_step: 방향 격자(rad).

        Returns:
            가장 좋은 후보(지금 자세를 포함해 비교).
        """
        # 반경 radius 원 안의 위치 격자(지금 자세 기준)
        g = np.arange(-radius, radius + 1e-9, step)
        dx, dy = np.meshgrid(g, g)
        keep = np.hypot(dx, dy) <= radius + 1e-9
        cx, cy = x + dx[keep], y + dy[keep]
        best = Candidate(x, y, yaw, self.score(pts, x, y, yaw))
        # 방향마다 가장 좋은 위치를 보고, 지금 최선보다 좋으면 바꿈
        for a in yaw + np.arange(-yaw_range, yaw_range + 1e-9, yaw_step):
            c, s = math.cos(a), math.sin(a)
            rx = pts[:, 0] * c - pts[:, 1] * s
            ry = pts[:, 0] * s + pts[:, 1] * c
            d = self.lookup(cx[:, None] + rx[None, :],
                            cy[:, None] + ry[None, :]).mean(axis=1)
            i = int(np.argmin(d))
            if d[i] < best.score:
                best = Candidate(float(cx[i]), float(cy[i]),
                                 _wrap(float(a)), float(d[i]))
        return self.refine(pts, best, step=step / 2, ystep=yaw_step / 2)

    # [수정 2026-11-20] T-50: 신규. 서 있을 때 지금 자세를 검사·보정
    def recheck(self, pts: np.ndarray, x: float, y: float, yaw: float,
                check_score: float = 0.012, max_score: float = 0.04,
                improve: float = 0.005,
                ratio: float = 0.6) -> tuple[float, Candidate | None]:
        """지금 자세(AMCL)의 점수가 나쁘면 근처에서 더 나은 자세를 찾는다.

        Args:
            pts: points() 의 로봇 기준 점(서 있을 때의 스캔).
            x: AMCL x.
            y: AMCL y.
            yaw: AMCL 방향.
            check_score: 이 점수(m) 이하면 맞다고 보고 탐색하지 않음.
            max_score: 새 자세가 이보다 나쁘면 보정하지 않음.
            improve: 새 자세가 이만큼(m) 넘게 좋아야 보정.
            ratio: 새 점수가 지금 점수의 이 배 이하여야 보정(뚜렷함).

        Returns:
            (지금 점수, 보정할 자세 또는 None).
        """
        now = self.score(pts, x, y, yaw)  # 지금 자세의 점수
        if now <= check_score:
            return now, None
        best = self.local_search(pts, x, y, yaw)
        # 보정 조건 세 가지를 모두 만족해야 함(허용 상한, 절대 개선, 비율)
        if (best.score <= max_score and now - best.score >= improve
                and best.score <= ratio * now):
            return now, best
        return now, None


def _close(a: Candidate, b: Candidate, dist: float, yaw: float) -> bool:
    """두 후보가 위치 dist(m) 안이고 방향 yaw(rad) 안이면 True."""
    return (math.hypot(a.x - b.x, a.y - b.y) <= dist
            and abs(_wrap(a.yaw - b.yaw)) <= yaw)
