"""기동 때 라이다 스캔으로 자기 자세를 찾아 AMCL 에 넣고, 위치를 저장한다.

[수정 2026-11-20] T-49: 신규. 관제를 띄우고 로봇이 연결되면 초기 자세를 주지
않아도 로봇이 스스로 위치를 찾게 함(사용자 요청). mobile_controller 가
실기기 라이다 구동(drive=nav2, pose_source=tf, 실측 지도)일 때만 붙임. 라이다가
없는 경량 시뮬(kinematic)에는 붙지 않음(sim_backend 와 같은 방식).

흐름:
  1. 위치가 잡힌 동안 5초마다(1 cm 넘게 움직였거나 60초 지났을 때)와 종료 때
     자세를 ~/.frybot/last_pose/<map_id>/<robot_id>.json 에 저장.
  2. 기동 때 initial_pose 를 받지 않았고 auto_localize 가 켜져 있으면, 첫 스캔과
     라이다 장착 자세(TF)를 받은 뒤 별도 스레드에서 한 번만 scan_match 로
     자세를 찾음(저장 자세를 후보로 검증 + 전체 지도 탐색). 그동안 상태
     LOCALIZING.
  3. 확실하면 /<robot>/initialpose 로 AMCL 에 넣음. 모호하거나 맞는 자세가
     없으면 넣지 않고 상태 NOT_LOCALIZED + error SELF_CHECK_ERROR 로 알림.
     관리자가 RViz 2D Pose Estimate 로 정하면(AMCL 이 위치를 내면) 그 자세를
     씀.
"""
from __future__ import annotations

import json
import math
import os
import threading
import time

from geometry_msgs.msg import PoseWithCovarianceStamped
import numpy as np
from rclpy.qos import qos_profile_sensor_data
from rclpy.time import Time
from sensor_msgs.msg import LaserScan
from tf2_ros import TransformException

from frybot_control.map_catalog import profile

# [수정 2026-11-23] T-55: 천장 카메라 후보 판정 서비스
from frybot_interfaces.srv import SpotCheck

from .scan_match import ScanMatcher
from .scan_match import pick_by_camera

# RobotStatus.state 로 보고하는 상태 이름('' 는 정상 보고)
LOCALIZING = 'LOCALIZING'  # 기동 때 자세를 찾는 중
NOT_LOCALIZED = 'NOT_LOCALIZED'  # 찾지 못함(RViz 로 정해야 함)


def _yaw(q) -> float:
    """쿼터니언(geometry_msgs Quaternion)의 yaw(rad)."""
    return math.atan2(2 * (q.w * q.z + q.x * q.y),
                      1 - 2 * (q.y * q.y + q.z * q.z))


class AutoLocalizer:
    """자동 위치 추정과 마지막 자세 저장.

    Args:
        node: MobileController(tf_buf, pub_init, have_truth, tf_ok, x, y,
            yaw, base_frame, get_logger 를 씀).
        cb: 콜백 그룹.
        map_id: 지도 이름.
        search: True 면 기동 때 자세를 찾음(False 면 저장만).
        params: max_score, margin, budget, store_dir, home_prior, monitor,
            check_period, check_score, improve, fix_interval, warn_yaw_deg,
            camera, camera_timeout, camera_hi, camera_lo, camera_sep,
            camera_wait([수정 2026-11-23] T-57)
            (mobile_controller.py 가 노드 파라미터로 채움).

    node 의 rid, home, odom, get_clock, create_* 도 씀.
    """

    def __init__(self, node, cb, map_id: str, search: bool,
                 params: dict) -> None:
        self.node, self.map_id = node, map_id
        self.p = params  # 위 params(탐색·감시 기준값)
        # 마지막 자세 저장 파일: <store_dir>/<map_id>/<robot_id>.json
        self.path = os.path.join(os.path.expanduser(params['store_dir']),
                                 map_id, f'{node.rid}.json')
        self.state = LOCALIZING if search else ''  # tick_state() 가 보고
        self.scan: LaserScan | None = None  # 가장 최근 스캔
        self.started = False  # 탐색 스레드를 띄웠는지(한 번만)
        # 마지막으로 저장한 자세와 그 시각(monotonic)
        self.last_saved: tuple[float, float, float] | None = None
        self.saved_t = 0.0
        self.sub = None  # /<robot>/scan 구독(탐색·감시가 없으면 None)
        # 아래 감시용 필드: odom_hist 는 (monotonic 시각, 오도메트리 자세)의
        # 최근 5초 기록(정지 판정 _still), lock 은 check_now 가 정기 점검과
        # Nav2 실패 처리에서 겹쳐 돌지 않게 함
        # [수정 2026-11-20] T-50: 위치 추정 감시·보정(서 있을 때만)
        self.matcher: ScanMatcher | None = None  # 지도 읽은 맞춤기(재사용)
        self.offset: tuple[float, float, float] | None = None  # 라이다 자세
        self.odom_hist: list[tuple[float, tuple[float, float, float]]] = []
        self.fix_t = -1e9                  # 마지막 보정 시각(monotonic)
        self.check_t = 0.0  # 마지막 정기 점검 시각(monotonic)
        self.lock = threading.Lock()
        # [수정 2026-11-20] T-52: 감시가 실제로 돌았는지 알 수 있게 집계
        self.stats = {'checks': 0, 'fixes': 0, 'last_score': -1.0,
                      'last_t': 0.0, 'skip': {}}
        # 스캔 구독: 기동 탐색이나 감시 중 하나라도 쓰면 만듦
        if search or params['monitor']:
            self.sub = node.create_subscription(
                LaserScan, f'/{node.rid}/scan', self._scan,
                qos_profile_sensor_data, callback_group=cb)
        # 기동 탐색: 0.5초마다 _try 가 스캔·TF 준비를 확인(시작 뒤 _finish 가
        # 타이머를 끔)
        if search:
            self.start_t = time.monotonic()
            self.timer = node.create_timer(0.5, self._try, callback_group=cb)
        # [수정 2026-11-23] T-55: 모호할 때 물을 천장 카메라 서비스(관제 PC
        # ceiling_locator). 없거나 답하지 못하면 저장 자세 -> 홈 규칙
        self.cli = (node.create_client(SpotCheck, '/frybot/spot_check',
                                       callback_group=cb)
                    if search and params.get('camera') else None)
        # [수정 2026-11-23] T-57: 클라이언트를 만든 시각. 카메라 대기 상한
        # (camera_wait)을 이 시각부터 잼(스캔 매칭 동안에도 탐색이 진행)
        self.cli_t = time.monotonic()
        # 마지막 자세 저장(5초마다, 조건은 save 참고)
        node.create_timer(5.0, self.save, callback_group=cb)
        # 감시: 1초마다 오도메트리 기록·정지 확인(_watch)
        if params['monitor']:
            node.create_timer(1.0, self._watch, callback_group=cb)
            # [수정 2026-11-20] T-52: 60초마다 한 줄 요약
            node.create_timer(60.0, self.summary, callback_group=cb)

    # ------------------------------------------------------------ 저장
    def saved_pose(self) -> tuple[float, float, float] | None:
        """저장된 마지막 자세 (x, y, yaw). 없거나 읽지 못하면 None."""
        try:
            with open(self.path) as stream:
                d = json.load(stream)
            return float(d['x']), float(d['y']), float(d['yaw'])
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def save(self, force: bool = False) -> None:
        """위치가 잡혀 있으면 지금 자세를 저장(움직였거나 60초 지났을 때).

        Args:
            force: 조건과 상관없이 저장(종료 때).
        """
        n = self.node
        # 위치가 잡히지 않았거나 아직 찾는 중이면 저장하지 않음
        if not (n.have_truth and n.tf_ok) or self.state == LOCALIZING:
            return
        pose = (n.x, n.y, n.yaw)
        now = time.monotonic()
        # 1 cm·0.02 rad 안으로 그대로이고 60초가 안 지났으면 건너뜀
        if not force and self.last_saved is not None and math.hypot(
                pose[0] - self.last_saved[0],
                pose[1] - self.last_saved[1]) < 0.01 and \
                abs(pose[2] - self.last_saved[2]) < 0.02 and \
                now - self.saved_t < 60.0:
            return
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            # 임시 파일에 쓰고 바꿔 끼워, 쓰다 끊겨도 반쪽 파일이 남지 않게 함
            tmp = self.path + '.tmp'
            with open(tmp, 'w') as stream:
                json.dump({'x': pose[0], 'y': pose[1], 'yaw': pose[2],
                           'time': time.time(), 'map_id': self.map_id},
                          stream)
            os.replace(tmp, self.path)
            self.last_saved, self.saved_t = pose, now
        except OSError as err:
            n.get_logger().warn(f'{n.rid}: cannot save the pose: {err}')

    # ------------------------------------------------------------ 탐색
    def _scan(self, m: LaserScan) -> None:
        """스캔 구독 콜백: 가장 최근 스캔만 보관."""
        self.scan = m

    def _lidar_offset(self, frame: str) -> tuple[float, float, float] | None:
        """base_frame 기준 라이다(frame) 자세 (x, y, yaw). TF 없으면 None."""
        try:
            t = self.node.tf_buf.lookup_transform(self.node.base_frame,
                                                  frame, Time())
        except TransformException:
            return None
        tr = t.transform
        return tr.translation.x, tr.translation.y, _yaw(tr.rotation)

    def _try(self) -> None:
        """0.5초 타이머: 스캔·라이다 TF 가 준비되면 탐색 스레드를 한 번 띄움."""
        n = self.node
        if self.started:
            return
        if n.have_truth:                    # 관리자가 RViz 로 먼저 정함
            self._finish('', 'pose already set (RViz / AMCL)')
            return
        if self.scan is None:
            return
        offset = self._lidar_offset(self.scan.header.frame_id)
        # TF 를 10초 기다려도 없으면 Pinky 기본 장착 자세로 진행
        if offset is None:
            if time.monotonic() - self.start_t < 10.0:
                return
            offset = (-0.017, 0.0, math.pi)          # Pinky URDF 값
            n.get_logger().warn(f'{n.rid}: no TF for the lidar mount, '
                                'using the Pinky default')
        # 탐색은 Pi 에서 수 초 걸릴 수 있어 콜백을 막지 않게 별도 스레드
        self.started = True
        scan = self.scan
        threading.Thread(target=self._run, args=(scan, offset),
                         daemon=True).start()

    def _run(self, scan: LaserScan, offset) -> None:
        """탐색 스레드: 스캔 맞춤으로 자세를 찾아 AMCL 에 넣고 상태를 정함."""
        n = self.node
        log = n.get_logger()
        try:
            m = ScanMatcher(profile(self.map_id)['yaml'], lidar_offset=offset)
        except (OSError, KeyError) as err:
            self._finish(NOT_LOCALIZED, f'cannot load the map: {err}')
            return
        pts = m.points(np.asarray(scan.ranges), scan.angle_min,
                       scan.angle_increment)
        saved = self.saved_pose()
        self.matcher, self.offset = m, offset  # 감시에서 다시 씀
        # [수정 2026-11-20] T-50: 저장 자세가 없으면 자기 홈 근처를 마지막
        # 기준으로(home_prior 켬일 때)
        # [수정 2026-11-23] T-55: 모호하면 저장 자세·홈보다 카메라를 먼저
        res = m.localize(pts, saved=saved, max_score=self.p['max_score'],
                         margin=self.p['margin'], budget=self.p['budget'],
                         home=n.home if self.p['home_prior'] else None,
                         chooser=self._ask_camera if self.cli else None)

        # 후보 하나를 로그용 문자열로
        def fmt(c):
            return ('-' if c is None else f'({c.x:.3f}, {c.y:.3f}, '
                    f'{math.degrees(c.yaw):.0f} deg) score {c.score:.4f}')
        info = (f'{res.status} in {res.seconds:.1f} s, best {fmt(res.best)}, '
                f'next distinct {fmt(res.second)}, saved '
                + ('-' if saved is None else
                   f'({saved[0]:.3f}, {saved[1]:.3f}, '
                   f'{math.degrees(saved[2]):.0f} deg)'))
        # [수정 2026-11-23] T-55: 카메라에 물었으면 점수와 이유도 한 줄에
        if res.camera:
            info += f', camera {res.camera}'
        # 탐색하는 동안 RViz 등으로 자세가 정해졌으면 그것을 따름
        if n.have_truth:
            self._finish('', 'pose set meanwhile (RViz / AMCL); ' + info)
            return
        if res.pose is None:
            self._finish(NOT_LOCALIZED, info + ' -> set the pose with '
                         'RViz 2D Pose Estimate')
            return
        log.info(f'{n.rid}: auto localisation {info} -> '
                 f'({res.pose.x:.3f}, {res.pose.y:.3f}, '
                 f'{math.degrees(res.pose.yaw):.0f} deg)')
        for _ in range(3):                  # 발행 유실 대비 세 번
            self._send(res.pose.x, res.pose.y, res.pose.yaw)
            time.sleep(0.5)
        self._finish('', 'initial pose sent to AMCL')

    # [수정 2026-11-23] T-55: 신규. 천장 카메라에 후보 자리를 물음
    def _ask_camera(self, cands: list) -> tuple[int | None, str]:
        """후보 위치를 ceiling_locator 에 보내 점수로 하나를 고른다.

        탐색 스레드에서 부름(응답은 노드 실행기가 받음). 서비스가 없거나
        실패·시간 초과면 (None, 이유)라 localize 는 다음 규칙으로 넘어감.

        Args:
            cands: localize 가 넘긴 서로 다른 모호한 후보(scan_match.Candidate).

        Returns:
            (고른 후보 번호 또는 None, 기록용 글).
        """
        # [수정 2026-11-23] T-57: 발견·응답을 각각 camera_timeout(3 s)만
        # 기다리던 것을, 클라이언트 생성 뒤 camera_wait(35 s)까지로 바꿈.
        # 세 대 동시 기동(19 1회차)에서 세 대 모두 3 s 안에 서비스를 찾지
        # 못했고, 찾은 뒤 첫 요청도 늦게 도착했음. 응답이 없으면 남은 시간
        # 안에서 다시 요청. 상한을 넘겨 불렸어도 최소 camera_timeout 은 기다림
        log = self.node.get_logger()
        rid = self.node.rid
        t = float(self.p['camera_timeout'])
        t_ask = time.monotonic()
        end = max(self.cli_t + float(self.p['camera_wait']), t_ask + t)
        log.info(f'{rid}: camera: waiting for /frybot/spot_check '
                 f'(node up {t_ask - self.cli_t:.1f} s, '
                 f'wait up to {end - t_ask:.1f} s)')
        if not self.cli.wait_for_service(timeout_sec=end - t_ask):
            return None, (f'no /frybot/spot_check service in '
                          f'{time.monotonic() - t_ask:.1f} s')
        t_found = time.monotonic()
        log.info(f'{rid}: camera: service found after '
                 f'{t_found - t_ask:.1f} s (node up '
                 f'{t_found - self.cli_t:.1f} s)')
        req = SpotCheck.Request()
        req.robot_id = rid
        req.x = [float(c.x) for c in cands]
        req.y = [float(c.y) for c in cands]
        done = threading.Event()
        futs = []
        # 먼저 온 응답 하나를 씀(늦게 도착한 앞 요청의 응답도 받음)
        while True:
            fut = self.cli.call_async(req)
            fut.add_done_callback(lambda _: done.set())
            futs.append(fut)
            left = end - time.monotonic()
            if done.wait(max(min(t, left), 0.0)) or left <= t:
                break
        if not done.is_set():
            for f in futs:
                f.cancel()
            return None, (f'no answer in {time.monotonic() - t_found:.1f} s '
                          f'({len(futs)} requests)')
        r = next(f.result() for f in futs if f.done())
        log.info(f'{rid}: camera: answer after '
                 f'{time.monotonic() - t_found:.1f} s '
                 f'({len(futs)} requests)')
        for f in futs:
            if not f.done():
                f.cancel()
        if r is None or not r.ok:
            return None, ('not ok: ' + (r.reason if r else 'no result'))
        scores = [float(s) for s in r.score]
        k, why = pick_by_camera(cands, scores, self.p['camera_hi'],
                                self.p['camera_lo'], self.p['camera_sep'])
        pos = ', '.join(f'({c.x:.2f}, {c.y:.2f})={s:.3f}'
                        for c, s in zip(cands, scores, strict=False))
        return k, f'[{pos}] {why}; {r.reason}'

    def _send(self, x: float, y: float, yaw: float) -> None:
        """/<robot>/initialpose 로 map 기준 자세를 발행(AMCL 이 받음)."""
        msg = PoseWithCovarianceStamped()
        msg.header.frame_id = 'map'
        msg.header.stamp = self.node.get_clock().now().to_msg()
        msg.pose.pose.position.x, msg.pose.pose.position.y = x, y
        msg.pose.pose.orientation.z = math.sin(yaw / 2)
        msg.pose.pose.orientation.w = math.cos(yaw / 2)
        # 스캔 맞춤의 오차(가짜 스캔 시험 1.5 cm, 4 도 이내)보다 조금 넓게
        msg.pose.covariance[0] = msg.pose.covariance[7] = 0.03 ** 2
        msg.pose.covariance[35] = math.radians(5) ** 2
        self.node.pub_init.publish(msg)

    def _finish(self, state: str, why: str) -> None:
        """기동 탐색을 끝냄: 상태를 정하고 로그, 구독·타이머를 정리.

        state 가 '' 이면 정상, NOT_LOCALIZED 이면 실패. self.timer 는
        search 일 때만 있으므로 탐색 경로(_try, _run)에서만 부름.
        """
        n = self.node
        self.state = state
        if state == NOT_LOCALIZED:
            n.get_logger().error(f'{n.rid}: auto localisation failed: {why}')
        else:
            n.get_logger().info(f'{n.rid}: auto localisation done: {why}')
        # [수정 2026-11-20] T-50: 감시가 켜져 있으면 스캔 구독을 유지
        if self.sub is not None and not self.p['monitor']:
            n.destroy_subscription(self.sub)
            self.sub = None
        self.timer.cancel()

    # ------------------------------------------------------------ 감시·보정
    # [수정 2026-11-20] T-50: 신규. 2026-11-20 실기기 08 에서 회전을 여러 번
    # 한 뒤 AMCL 방향이 25 도 틀어져(트인 통로) NAV2_FAILED 로 갇혔음.
    # 서 있을 때 지금 자세의 스캔 점수를 보고, 나쁘면 근처(+-20 cm, +-45
    # 도)만 다시 맞춰 뚜렷하게 좋으면 AMCL 에 다시 넣음
    def _ensure_matcher(self) -> bool:
        """감시용 ScanMatcher 를 준비. 준비됐으면 True.

        기동 탐색을 하지 않았으면(initial_pose 를 받음 등) 여기서 만든다.
        """
        if self.matcher is not None:
            return True
        if self.scan is None:
            return False
        offset = self._lidar_offset(self.scan.header.frame_id)
        if offset is None:
            return False
        try:
            self.matcher = ScanMatcher(profile(self.map_id)['yaml'],
                                       lidar_offset=offset)
        except (OSError, KeyError):
            return False
        return True

    def _still(self, sec: float = 2.0) -> bool:
        """오도메트리가 sec 초 동안 거의 그대로였는지(서 있음)."""
        now = time.monotonic()
        hist = [p for t_, p in self.odom_hist if now - t_ <= sec + 0.5]
        # 1초마다 쌓이므로 기록이 sec 개보다 적으면(기동 직후) 판단 보류
        if len(hist) < int(sec):
            return False
        x0, y0, a0 = hist[0]
        return all(math.hypot(x - x0, y - y0) < 0.005
                   and abs(math.remainder(a - a0, 2 * math.pi)) < 0.01
                   for x, y, a in hist)

    def _watch(self) -> None:
        """1초 타이머: 오도메트리 기록, 서 있고 점검 주기가 지났으면 점검."""
        n = self.node
        now = time.monotonic()
        self.odom_hist = [(t_, p) for t_, p in self.odom_hist
                          if now - t_ < 5.0] + [(now, n.odom)]
        # 탐색 중·실패 상태, 위치 미확정, 주기 전, 움직이는 중이면 건너뜀
        if (self.state or not (n.have_truth and n.tf_ok)
                or now - self.check_t < self.p['check_period']
                or not self._still()):
            return
        self.check_t = now
        self.check_now('standing')

    def check_now(self, why: str) -> bool:
        """지금(서 있는) 자세를 스캔으로 검사하고 필요하면 보정한다.

        Args:
            why: 로그에 남길 이유(standing, Nav2 실패 등).

        Returns:
            보정해 AMCL 에 새 자세를 넣었으면 True.
        """
        n = self.node
        standing = why == 'standing'  # 정기 점검(_watch)인지, Nav2 실패인지
        if not self.p['monitor'] or self.state or not n.have_truth:
            return self._skip('not localised', why, standing)
        if time.monotonic() - self.fix_t < self.p['fix_interval']:
            return self._skip('just corrected', why, standing)
        if not self.lock.acquire(blocking=False):
            return self._skip('busy', why, standing)
        try:
            t0 = time.monotonic()
            while time.monotonic() - t0 < 1.0:     # 멈춘 뒤의 새 스캔
                s = self.scan
                if s is not None and Time.from_msg(s.header.stamp) \
                        .nanoseconds / 1e9 >= time.time() - 0.3:
                    break
                time.sleep(0.1)
            if self.scan is None or not self._ensure_matcher():
                return self._skip('no scan or lidar TF', why, standing)
            m, s = self.matcher, self.scan
            pts = m.points(np.asarray(s.ranges), s.angle_min,
                           s.angle_increment)
            x, y, yaw = n.x, n.y, n.yaw  # 지금 AMCL(TF) 자세
            score, fix = m.recheck(pts, x, y, yaw,
                                   check_score=self.p['check_score'],
                                   max_score=self.p['max_score'],
                                   improve=self.p['improve'])
            self.stats['checks'] += 1
            self.stats['last_score'] = score
            self.stats['last_t'] = time.monotonic()
            # [수정 2026-11-23] T-56(R16-50): 아래 첫 분기(fix 없음 + Nav2
            # 실패)에 return 이 없어 fix.yaw(fix=None)에서 AttributeError 가
            # 났음(실기기 runs/20261123_03). 로그를 남긴 뒤 False 로 돌아감
            if fix is None and not standing:
                # [수정 2026-11-20] T-52: Nav2 실패 때는 결과를 항상 남김
                # (09: 감시가 돌았는지 로그로 알 수 없었음). 가장 가까운
                # 스캔 점도 함께(무엇을 장애물로 봤는지 가늠)
                verdict = ('no correction needed'
                           if score <= self.p['check_score']
                           else 'no clearly better pose nearby')
                n.get_logger().warn(
                    f'{n.rid}: pose check ({why}): score {score:.4f} at '
                    f'({x:.3f}, {y:.3f}, {math.degrees(yaw):.0f} deg), '
                    f'{verdict}; {self._nearest(s)}')
                return False
            elif fix is None:
                if score > self.p['check_score']:
                    n.get_logger().warn(
                        f'{n.rid}: pose check ({why}): score {score:.4f} at '
                        f'({x:.3f}, {y:.3f}, {math.degrees(yaw):.0f} deg) '
                        'but no clearly better pose nearby, left as is')
                return False
            dyaw = math.degrees(math.remainder(fix.yaw - yaw, 2 * math.pi))
            dist = math.hypot(fix.x - x, fix.y - y)
            msg = (f'{n.rid}: pose corrected ({why}): ({x:.3f}, {y:.3f}, '
                   f'{math.degrees(yaw):.0f} deg) score {score:.4f} -> '
                   f'({fix.x:.3f}, {fix.y:.3f}, {math.degrees(fix.yaw):.0f} '
                   f'deg) score {fix.score:.4f} ({dist * 100:.1f} cm, '
                   f'{dyaw:+.0f} deg)')
            if abs(dyaw) > self.p['warn_yaw_deg']:
                n.get_logger().error(msg + ' - LARGE correction, check it')
            else:
                n.get_logger().warn(msg)
            # 발행 유실 대비 두 번
            for _ in range(2):
                self._send(fix.x, fix.y, fix.yaw)
                time.sleep(0.3)
            self.fix_t = time.monotonic()
            self.stats['fixes'] += 1
            return True
        finally:
            self.lock.release()

    # [수정 2026-11-20] T-52: 신규
    def _skip(self, reason: str, why: str, standing: bool) -> bool:
        """검사를 건너뛴 이유를 세고(Nav2 실패 때는 로그도) False."""
        self.stats['skip'][reason] = self.stats['skip'].get(reason, 0) + 1
        if not standing:
            n = self.node
            n.get_logger().warn(f'{n.rid}: pose check ({why}) skipped: '
                                f'{reason}')
        return False

    # [수정 2026-11-20] T-52: 신규
    @staticmethod
    def _nearest(s: LaserScan) -> str:
        """스캔에서 가장 가까운 점(라이다 기준 거리·각도) 설명."""
        r = np.asarray(s.ranges, float)
        # 6 cm 미만은 자기 몸으로 보고 뺌(ScanMatcher.points 의 rmin 과 같음)
        ok = np.isfinite(r) & (r >= 0.06)
        if not ok.any():
            return 'scan has no valid point'
        i = int(np.argmin(np.where(ok, r, np.inf)))
        a = math.degrees(s.angle_min + i * s.angle_increment)
        return (f'nearest scan point {r[i] * 100:.1f} cm at {a:+.0f} deg '
                '(lidar frame, Pinky front = +-180 deg)')

    # [수정 2026-11-20] T-52: 신규. 감시 동작 요약(60초마다, 종료 때)
    def summary(self) -> None:
        """확인 횟수·마지막 점수·보정 횟수·건너뛴 이유를 한 줄로 남긴다."""
        n = self.node
        st = self.stats
        age = (f'{time.monotonic() - st["last_t"]:.0f} s ago'
               if st['last_t'] else 'never')
        n.get_logger().info(
            f'{n.rid}: pose monitor: checks {st["checks"]}, last score '
            f'{st["last_score"]:.4f} ({age}), corrections {st["fixes"]}, '
            f'skipped {st["skip"] or "-"}, state {self.state or "OK"}')

    def tick_state(self) -> str:
        """지금 보고할 상태('' = 정상 보고). RViz 로 정해지면 풀림."""
        if self.state == NOT_LOCALIZED and self.node.have_truth:
            self.state = ''
        return self.state
