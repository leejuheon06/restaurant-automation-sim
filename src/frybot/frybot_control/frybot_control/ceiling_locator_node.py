"""천장 카메라로 '후보 자리에 로봇이 있는가'를 답하는 관제 PC 노드.

[수정 2026-11-23] 신규: 작업 지시 18, T-55. 로봇의 auto_localize 가 기동 때
라이다 위치 추정이 모호하면 후보 위치들을 /frybot/spot_check(SpotCheck)로
묻는다. 이 노드는 그때만 카메라를 짧게 열어(약 1초) 빈 바닥 기준 화면과
비교한 점수를 돌려준다. 계산은 ceiling_view(ROS 없음)가 맡는다.

카메라 공유: scripts/cam_record.py 가 녹화 중이면 장치를 열 수 없으므로,
cam_record 가 남기는 최신 프레임 파일(latest_file)이 latest_max_age 초 안의
것이면 그것을 쓴다. 둘 다 안 되면 ok=false(CAMERA_BUSY).

빈 바닥 기준 화면(store_dir/<map_id>/reference.png)은 처음 한 번
'ros2 run frybot_control ceiling_tool reference' 로 만든다(맵에 로봇이 없을
때). 그 뒤 가구가 옮겨지는 것은 ref_update_sec 마다 자동 갱신으로 따라간다
(조건은 _update_reference).

파라미터:
  device, latest_file, latest_max_age: 카메라 장치와 최신 프레임 파일
  store_dir: 기준 화면 폴더(기본 ~/.frybot/ceiling)
  image_file: 비어 있지 않으면 카메라 대신 이 이미지를 씀(녹화 재현 시험용)
  robot_ids: 관제가 띄운 로봇 이름(자동 갱신 조건에 씀)
  explain_dist, scene_max: ceiling_view.spot_check 참고
  ref_update_sec: 기준 화면 자동 갱신 주기(s, 0 이하면 끔)
  ref_keep_radius, ref_max_change: 자동 갱신 때 로봇 자리 반지름(m),
      로봇 자리 밖 변화 상한
"""
import os
import threading
import time

import cv2
import numpy as np
import rclpy
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

from frybot_control import ceiling_view as cv
from frybot_control.map_catalog import profile
from frybot_control.map_catalog import require_map_id
from frybot_interfaces.msg import RobotStatus
from frybot_interfaces.srv import SpotCheck

# 위치가 잡히지 않은 로봇의 상태 이름(auto_localize 와 같은 값)
_UNLOCALIZED = ('LOCALIZING', 'NOT_LOCALIZED')
# 자동 갱신은 모든 로봇이 서 있을 때만(이 상태들)
_STILL = ('IDLE', 'CHARGING')


class CeilingLocator(Node):
    """SpotCheck 서비스와 기준 화면 자동 갱신."""

    def __init__(self) -> None:
        super().__init__('ceiling_locator')
        p = self.declare_parameter
        self.map_id = require_map_id('ceiling_locator')
        self.device = p('device', '/dev/video0').value
        self.latest = p('latest_file', '~/.frybot/ceiling/latest.jpg').value
        self.latest_age = float(p('latest_max_age', 2.0).value)
        self.store = p('store_dir', '~/.frybot/ceiling').value
        self.image_file = p('image_file', '').value
        self.robot_ids = list(p('robot_ids', ['']).value)
        self.explain_dist = float(p('explain_dist', 0.20).value)
        self.scene_max = float(p('scene_max', 0.40).value)
        update = float(p('ref_update_sec', 120.0).value)
        self.keep_r = float(p('ref_keep_radius', 0.15).value)
        self.max_change = float(p('ref_max_change', 0.25).value)
        prof = profile(self.map_id)
        self.box = cv.map_box(prof['yaml'])
        self.markers = prof.get('ceiling_markers') or {}
        self.manual = cv.Calib.from_walls(self.box)
        self.ref = cv.load_reference(self.store, self.map_id)
        self.status: dict[str, tuple] = {}  # 로봇 → (x, y, state, 받은 시각)
        self.cam_lock = threading.Lock()    # 카메라·기준 화면을 한 번에 하나
        cb = ReentrantCallbackGroup()
        self.create_subscription(RobotStatus, '/fleet/robot_status',
                                 self._on_status, 50, callback_group=cb)
        self.create_service(SpotCheck, '/frybot/spot_check', self._check,
                            callback_group=cb)
        if update > 0:
            self.create_timer(update, self._update_reference,
                              callback_group=cb)
        self.get_logger().info(
            f'ceiling locator up: map {self.map_id}, device {self.device}, '
            f'reference {"yes" if self.ref is not None else "MISSING"}, '
            f'markers {sorted(self.markers) or "none (manual walls)"}')

    def _on_status(self, m: RobotStatus) -> None:
        """로봇 상태 보고를 받아 둠(다른 로봇 판단, 자동 갱신 조건)."""
        self.status[m.robot_id] = (m.x, m.y, m.state, time.monotonic())

    def _localized(self, exclude: str = '') -> list[tuple]:
        """2초 안에 위치를 보고한 로봇 [(이름, x, y, 상태)] (exclude 제외)."""
        now = time.monotonic()
        return [(rid, x, y, st) for rid, (x, y, st, t) in self.status.items()
                if rid != exclude and now - t < 2.0
                and st not in _UNLOCALIZED]

    def _frame(self) -> tuple[np.ndarray, str]:
        """지금 프레임과 출처. 실패하면 CameraBusyError·CameraFailError."""
        if self.image_file:
            img = cv2.imread(os.path.expanduser(self.image_file))
            if img is None:
                raise cv.CameraFailError(f'cannot read {self.image_file}')
            return img, 'file'
        return cv.grab(self.device, self.latest, self.latest_age)

    def _calib(self, frame: np.ndarray) -> cv.Calib:
        """마커가 4개 이상 보이면 그 대응, 아니면 벽 바닥선 수동 대응."""
        if self.markers:
            c = cv.Calib.from_markers(frame, self.markers, self.manual.k)
            if c is not None:
                return c
        return self.manual

    def _check(self, req: SpotCheck.Request,
               res: SpotCheck.Response) -> SpotCheck.Response:
        """SpotCheck 서비스: 후보 자리마다 바뀐 화소 비율."""
        res.ok, res.score, res.reason = False, [], ''
        if len(req.x) != len(req.y) or not req.x:
            res.reason = 'BAD_REQUEST: x, y 길이가 다르거나 비었음'
            return self._log(req, res)
        with self.cam_lock:
            try:
                frame, src = self._frame()
            except cv.CameraBusyError as err:
                res.reason = f'CAMERA_BUSY: {err}'
                return self._log(req, res)
            except cv.CameraFailError as err:
                res.reason = f'CAMERA_FAIL: {err}'
                return self._log(req, res)
            others = [(rid, x, y) for rid, x, y, _ in
                      self._localized(exclude=req.robot_id)]
            out = cv.spot_check(frame, self.ref, self._calib(frame),
                                self.box, list(zip(req.x, req.y,
                                                   strict=True)),
                                others, self.explain_dist, self.scene_max)
        res.ok, res.score = out.ok, [float(s) for s in out.scores]
        res.reason = out.reason + (f' frame={src}' if out.ok else '')
        return self._log(req, res)

    def _log(self, req, res) -> SpotCheck.Response:
        """요청 한 건을 한 줄로 남기고 응답을 돌려줌."""
        pts = ', '.join(f'({x:.2f}, {y:.2f})' for x, y in
                        zip(req.x, req.y, strict=False))
        sc = ', '.join(f'{s:.3f}' for s in res.score)
        log = self.get_logger().info if res.ok else self.get_logger().warn
        log(f'spot check {req.robot_id}: [{pts}] -> ok={res.ok} '
            f'[{sc}] {res.reason}')
        return res

    def _update_reference(self) -> None:
        """기준 화면 자동 갱신(가구 이동을 따라감).

        다음을 모두 만족할 때만 바꿈(아니면 이유를 debug 로그):
        기준 화면이 있음, 관제가 띄운 로봇이 모두 2초 안에 위치를 보고했고
        서 있음(IDLE·CHARGING), 1초 간격 두 프레임이 거의 같음(사람·움직임
        없음), 각 로봇이 보고한 자리에서 카메라에도 로봇이 보임(점수 0.15
        이상: 틀린 자세를 믿는 로봇의 실제 자리를 기준에 넣지 않게),
        로봇 자리 밖 변화가 ref_max_change 이하. 로봇 자리(반지름
        ref_keep_radius)는 옛 화소를 둠.
        한계: 관제에 없는 로봇(꺼진 채 맵 안에 놓인 로봇)은 알 수 없어,
        그 로봇은 기준 화면에 들어갈 수 있음.
        """
        why = self._try_update()
        if why:
            self.get_logger().debug(f'reference not updated: {why}')

    def _try_update(self) -> str:
        """갱신을 시도하고, 하지 않았으면 그 이유를 돌려줌."""
        if self.ref is None:
            return 'no reference (ros2 run frybot_control ceiling_tool ' \
                   'reference)'
        robots = {rid: (x, y, st) for rid, x, y, st in self._localized()}
        missing = [r for r in self.robot_ids if r and r not in robots]
        if missing:
            return f'not localised / silent: {missing}'
        moving = [r for r, (_, _, st) in robots.items() if st not in _STILL]
        if moving:
            return f'robots not still: {moving}'
        with self.cam_lock:
            try:
                a, _ = self._frame()
                time.sleep(1.0)
                b, _ = self._frame()
            except (cv.CameraBusyError, cv.CameraFailError) as err:
                return f'camera: {err}'
            if a.shape != self.ref.shape:
                return 'frame size differs from the reference'
            cal = self._calib(b)
            floor = cal.floor_mask(b.shape, self.box)
            area = max(1, int((floor > 0).sum()))
            if (cv.change_mask(a, b, floor) > 0).sum() / area > 0.005:
                return 'scene is moving'
            mask = cv.change_mask(b, self.ref, floor)
            keep = np.zeros(b.shape[:2], np.uint8)
            for rid, (x, y, _) in robots.items():
                if cv.site_score(mask, cal, (x, y)) < 0.15:
                    return f'{rid} not seen at its reported pose'
                keep |= cal.disc_mask(b.shape, (x, y), self.keep_r)
            outside = ((mask > 0) & (keep == 0)).sum() / area
            if outside > self.max_change:
                return f'too much changed ({outside:.0%})'
            self.ref = cv.update_reference(self.ref, b, keep)
            cv.save_reference(self.store, self.map_id, self.ref,
                              f'auto, robots kept: {sorted(robots)}')
        self.get_logger().info(
            f'reference updated ({outside:.1%} of the floor changed outside '
            f'{len(robots)} robots)')
        return ''


def main() -> None:
    """노드 실행(카메라 대기 동안 다른 콜백이 돌게 다중 스레드)."""
    rclpy.init()
    node = CeilingLocator()
    ex = MultiThreadedExecutor(num_threads=3)
    ex.add_node(node)
    try:
        ex.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
