# [수정 2026-11-24] 새 파일: AI 서버의 손님 추적(YOLO). frybot_sim/ai_server 의
# 임계값 대역을 실제 추론으로 대신하는 GUEST_TRACK 생산자
r"""AI 서버: AMR 카메라 영상에서 사람을 찾아 GUEST_TRACK 을 보낸다(ROS 없음).

  Camera Streamer(Pinky, rpicam-vid MJPEG TCP :8554)
      --TCP--> guest_tracker(수신 -> YOLO 추론 -> 손님 선택 -> 거리 추정)
      --HTTP POST--> Central Control (:8100 /ai/result, kind = GUEST_TRACK)

- 영상은 ROS 로 보내지 않는다. 노트북(AI 서버)이 로봇 카메라에 직접 붙는다.
- 지연을 쌓지 않도록 카메라마다 최신 프레임 하나만 들고, 추론은 끝날 때마다
  그 최신 프레임을 가져간다(밀린 프레임은 버림).
- 손님: 사람(COCO person)으로 탐지된 것 중 상자 높이가 가장 큰 것(가장 가까운
  사람). 손님 신원 구분은 하지 않는다.
  [수정 2026-11-24] 안내 중에는 손님을 고정한다. Central Control 이 안내 중인
  (로봇, 방문) 목록을 POST /guides 로 보내면, 목록에 새로 들어온 로봇은 그때
  가장 앞(상자가 가장 큰) 사람의 추적 번호(track_id)로 고정하고, 그 뒤로는 그
  번호만 손님으로 본다(다른 사람이 가로질러도 무시). 목록에서 빠지면(자리까지
  안내 완료) 고정을 푼다. 추적은 ultralytics 추적기(기본 BoT-SORT + ReID).
- 거리: 핀홀 근사 distance = 초점거리(px) x 사람 키(m) / 상자 높이(px).
  사람 키(--person-height)와 화각(--hfov-deg)은 실측 보정 전 값(확인 필요).
  상자가 영상 위·아래 끝에 닿으면(잘림) 거리가 실제보다 크게 나온다.
- visit_id 는 고정 중이면 그 방문 번호를 보내고, 아니면 보내지 않는다(Central
  Control 이 그 로봇이 맡은 안내 방문으로 채움). 새 프레임이 없으면(카메라
  끊김) 보내지 않아 로봇이 guest_track_stale 뒤 놓침으로 판단하게 둔다.
- 확인 화면: http://127.0.0.1:<view-port>/ (탐지 상자), /detections (JSON).
  같은 포트의 POST /guides 가 고정 명령을 받는다.

사용(런치가 이 명령을 만든다):
    ~/venv/yolo/bin/python -m frybot_ai.guest_tracker \
        --camera pinky1=192.168.0.9 --model yolov8s.pt
"""

import argparse
import dataclasses
import http.server
import json
import math
import os
import pathlib
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import cv2
import numpy as np

PERSON_CLASS = 0  # COCO 의 person
DEFAULT_PORT = 8554  # camera_streamer.launch.py 의 기본 포트
_EDGE_PX = 2  # 상자가 영상 끝에서 이만큼(px) 안이면 잘린 것으로 봄
_ROTATIONS = {
    'none': None,
    'cw': cv2.ROTATE_90_CLOCKWISE,
    'ccw': cv2.ROTATE_90_COUNTERCLOCKWISE,
    '180': cv2.ROTATE_180,
}


@dataclasses.dataclass
class Camera:
    """로봇 카메라 하나의 연결 정보와 최신 상태.

    Attributes:
        robot_id: 카메라를 단 로봇(GUEST_TRACK 의 robot_id).
        host: 카메라 스트림 주소.
        port: 카메라 스트림 TCP 포트.
        raw: 가장 최근 받은 JPEG.
        raw_n: 받은 프레임 수.
        raw_time: 가장 최근 프레임을 받은 시각(unix 초).
        view: 상자를 그린 최신 JPEG(확인 화면용).
        view_n: view 가 바뀐 횟수.
        result: 가장 최근 추론 결과(dict).
    """

    robot_id: str
    host: str
    port: int = DEFAULT_PORT
    # [수정 2026-11-24] 로봇마다 카메라 장착 방향이 다를 수 있음
    # (None = --rotate)
    rotate: str | None = None
    raw: bytes = b''
    raw_n: int = 0
    raw_time: float = 0.0
    view: bytes = b''
    view_n: int = 0
    result: dict = dataclasses.field(default_factory=dict)
    # [수정 2026-11-24] 손님 고정: 안내 중인 방문 번호(0 = 고정 안 함)와
    # 고정한 추적 번호(None = 다음 프레임에서 가장 앞 사람으로 고정)
    lock_visit: int = 0
    lock_id: int | None = None
    model: object = None  # 로봇마다 따로 둔 YOLO(추적 상태가 섞이지 않게)


# [수정 2026-11-24] 로봇별 회전 '@회전' 추가(pinky1~3 모두 같은 노드로 처리)
def parse_camera(spec: str) -> Camera:
    """'robot=host[:port][@rotate]' 형식의 카메라 지정을 읽는다.

    Args:
        spec: 예 'pinky1=192.168.0.9', 'pinky2=192.168.0.29:8554@180'.

    Returns:
        Camera.

    Raises:
        ValueError: 형식이 틀렸거나 회전 값이 none/cw/ccw/180 이 아닐 때.
    """
    robot_id, sep, addr = spec.partition('=')
    if not sep or not robot_id or not addr:
        raise ValueError(
            f'camera must be robot=host[:port][@rotate]: {spec!r}')
    addr, _, rotate = addr.partition('@')
    if rotate and rotate not in _ROTATIONS:
        raise ValueError(f'unknown rotate {rotate!r} in {spec!r}')
    host, _, port = addr.partition(':')
    return Camera(robot_id=robot_id.strip(), host=host.strip(),
                  port=int(port) if port else DEFAULT_PORT,
                  rotate=rotate or None)


def focal_px(width_px: int, hfov_deg: float) -> float:
    """가로 화소 수와 가로 화각으로 초점거리(px)를 구한다.

    Args:
        width_px: 센서 방향 그대로(회전 전)의 영상 가로 화소 수.
        hfov_deg: 가로 화각(도).

    Returns:
        초점거리(px).
    """
    return (width_px / 2.0) / math.tan(math.radians(hfov_deg) / 2.0)


def estimate_distance(box_h_px: float, person_height_m: float,
                      f_px: float) -> float:
    """사람 상자 높이로 카메라까지의 거리를 추정한다(핀홀 근사).

    Args:
        box_h_px: 상자 높이(px).
        person_height_m: 사람(인형) 키(m).
        f_px: 초점거리(px).

    Returns:
        거리(m). 상자 높이가 0 이하이면 inf.
    """
    if box_h_px <= 0:
        return math.inf
    return f_px * person_height_m / box_h_px


def pick_guest(people: list[dict]) -> dict | None:
    """탐지된 사람 중 손님으로 볼 하나(상자 높이가 가장 큰 것)를 고른다.

    Args:
        people: {'xyxy': [x1, y1, x2, y2], 'conf': float} 목록.

    Returns:
        고른 항목. 없으면 None.
    """
    if not people:
        return None
    return max(people, key=lambda p: p['xyxy'][3] - p['xyxy'][1])


# [수정 2026-11-24] 손님 고정(안내 시작 때 가장 앞 사람, 안내 완료까지 유지)
def select_guest(people: list[dict], lock_visit: int,
                 lock_id: int | None) -> tuple[dict | None, int | None]:
    """고정 상태에 따라 이번 프레임의 손님을 고른다.

    Args:
        people: {'xyxy', 'conf', 'id'} 목록. id 는 추적 번호(없으면 None).
        lock_visit: 안내 중인 방문 번호. 0 이면 고정하지 않음.
        lock_id: 고정한 추적 번호. None 이면 아직 고정 전.

    Returns:
        (손님 항목 또는 None, 이후 고정 번호). 고정하지 않으면 가장 앞 사람과
        None. 고정 전이면 추적 번호가 있는 사람 중 가장 앞 사람으로 고정.
        고정 중이면 그 번호의 사람(없으면 None, 고정은 유지).
    """
    if not lock_visit:
        return pick_guest(people), None
    if lock_id is None:
        guest = pick_guest([p for p in people if p.get('id') is not None])
        return guest, (guest['id'] if guest is not None else None)
    guest = next((p for p in people if p.get('id') == lock_id), None)
    return guest, lock_id


def is_truncated(xyxy: list[int], height_px: int) -> bool:
    """상자가 영상 위나 아래 끝에 닿았는지(사람이 잘렸는지) 본다.

    Args:
        xyxy: 상자 [x1, y1, x2, y2].
        height_px: 영상 높이(px).

    Returns:
        잘렸으면 True.
    """
    return xyxy[1] <= _EDGE_PX or xyxy[3] >= height_px - 1 - _EDGE_PX


# [수정 2026-11-24] 손님을 밖에서 골라 넘김(select_guest), 고정 정보 추가
def guest_result(robot_id: str, people: list[dict], guest: dict | None,
                 height_px: int, person_height_m: float, f_px: float,
                 lock_visit: int = 0) -> dict:
    """한 프레임의 탐지 결과로 GUEST_TRACK 본문을 만든다.

    Args:
        robot_id: 카메라를 단 로봇.
        people: 탐지된 사람 목록(pick_guest 와 같은 형식).
        guest: 손님으로 고른 항목(select_guest). 없으면 None.
        height_px: 영상 높이(px, 회전 뒤).
        person_height_m: 사람(인형) 키(m).
        f_px: 초점거리(px).
        lock_visit: 고정 중인 방문 번호. 0 이면 visit_id 를 넣지 않음.

    Returns:
        /ai/result 로 보낼 dict(kind, robot_id, visible, distance, conf,
        truncated, count, track_id, locked, 고정 중이면 visit_id). 손님이
        없으면 visible False, distance 0.0.
    """
    out = {'kind': 'GUEST_TRACK', 'robot_id': robot_id,
           'visible': guest is not None, 'distance': 0.0, 'conf': 0.0,
           'truncated': False, 'count': len(people), 'track_id': None,
           'locked': bool(lock_visit)}
    if lock_visit:
        out['visit_id'] = lock_visit
    if guest is not None:
        _, y1, _, y2 = guest['xyxy']
        out['distance'] = round(
            estimate_distance(y2 - y1, person_height_m, f_px), 3)
        out['conf'] = guest['conf']
        out['truncated'] = is_truncated(guest['xyxy'], height_px)
        out['box'] = guest['xyxy']
        out['track_id'] = guest.get('id')
    return out


def split_jpegs(buf: bytes) -> tuple[bytes | None, bytes]:
    """MJPEG 바이트열에서 마지막 완성 JPEG 하나를 꺼낸다.

    Args:
        buf: 지금까지 받은 바이트.

    Returns:
        (가장 최근 완성 JPEG 또는 None, 남길 바이트).
    """
    end = buf.rfind(b'\xff\xd9')
    if end < 0:
        return None, buf
    start = buf.rfind(b'\xff\xd8', 0, end)
    if start < 0:
        return None, buf[end + 2:]
    return buf[start:end + 2], buf[end + 2:]


# [수정 2026-11-24] 손님 고정용 추적기 설정
def tracker_config(name: str, track_buffer: int,
                   folder: pathlib.Path) -> str:
    """Ultralytics 추적기 설정 파일을 정한다.

    Args:
        name: 'botsort_reid'(BoT-SORT + ReID), 'botsort', 'bytetrack'.
        track_buffer: 놓친 추적을 살려 두는 프레임 수.
        folder: 설정 파일을 쓸 폴더.

    Returns:
        model.track(tracker=...) 에 넘길 설정 파일 경로.
    """
    base = {
        'track_high_thresh': 0.25, 'track_low_thresh': 0.1,
        'new_track_thresh': 0.25, 'track_buffer': track_buffer,
        'match_thresh': 0.8, 'fuse_score': True,
    }
    if name == 'bytetrack':
        cfg = dict(base, tracker_type='bytetrack')
    else:
        # 로봇이 움직여 카메라가 흔들리므로 움직임 보정(sparseOptFlow)
        cfg = dict(base, tracker_type='botsort', gmc_method='sparseOptFlow',
                   proximity_thresh=0.5, appearance_thresh=0.8,
                   with_reid=name == 'botsort_reid', model='auto')
    path = folder / f'tracker_{name}_{track_buffer}.yaml'
    path.write_text(''.join(f'{k}: {v}\n' for k, v in cfg.items()),
                    encoding='utf-8')
    return str(path)


class GuestTracker:
    """카메라 수신, 추론, 결과 전송, 확인 화면을 묶는다.

    Args:
        cameras: 받을 카메라 목록.
        args: 명령행 인자(모델, 임계값, 회전, 보정값, 전송 주소 등).
    """

    def __init__(self, cameras: list[Camera],
                 args: argparse.Namespace) -> None:
        self.cameras = cameras
        self.args = args
        self.cond = threading.Condition()
        # [수정 2026-11-24] 카메라마다 회전(지정이 없으면 --rotate)
        for cam in cameras:
            cam.rotate = cam.rotate or args.rotate
        self.model = None  # main 에서 load_model 로 채움
        self.model_version = ''
        self.post_ok_after = 0.0  # 전송 실패 뒤 다시 시도할 시각
        self.last_post: dict[str, float] = {}
        self.record_dir = None
        if args.record:
            self.record_dir = pathlib.Path(args.record).expanduser()
            self.record_dir.mkdir(parents=True, exist_ok=True)

    def load_model(self) -> None:
        """YOLO 모델을 읽고 한 번 돌려 첫 추론의 초기화 지연을 미리 치른다."""
        # ultralytics(torch)는 가상 환경에만 있다. 시험(pytest)이 이 모듈의
        # 순수 함수를 시스템 Python 으로 불러올 수 있도록 여기서 가져온다
        from ultralytics import YOLO  # pylint: disable=import-outside-toplevel
        weights = pathlib.Path(self.args.weights_dir).expanduser()
        weights.mkdir(parents=True, exist_ok=True)
        path = pathlib.Path(self.args.model).expanduser()
        if not path.is_absolute():
            path = weights / path  # 없으면 ultralytics 가 이 자리로 내려받음
        self.model_version = path.stem
        # [수정 2026-11-24] 추적기 상태가 카메라끼리 섞이지 않도록 로봇마다
        # 모델을 따로 읽음(s 크기는 하나에 GPU 약 100 MB)
        for cam in self.cameras:
            cam.model = YOLO(str(path))
            cam.model.predict(np.zeros((480, 640, 3), np.uint8),
                              device=self.args.device, verbose=False)
        self.model = self.cameras[0].model
        self.tracker_cfg = tracker_config(self.args.tracker,
                                          self.args.track_buffer, weights)

    # ------------------------------------------------------------ 수신
    def reader(self, cam: Camera) -> None:
        """카메라 하나에 붙어 최신 JPEG 를 cam.raw 에 둔다(끊기면 다시 붙음).

        Args:
            cam: 받을 카메라.
        """
        while True:
            try:
                sock = socket.create_connection((cam.host, cam.port),
                                                timeout=5)
            except OSError:
                time.sleep(0.5)
                continue
            print(f'[guest_tracker] {cam.robot_id}: camera connected '
                  f'{cam.host}:{cam.port}', flush=True)
            buf = b''
            while True:
                try:
                    chunk = sock.recv(65536)
                except OSError:
                    break
                if not chunk:
                    break
                jpg, buf = split_jpegs(buf + chunk)
                if jpg is None:
                    continue
                with self.cond:
                    cam.raw, cam.raw_time = jpg, time.time()
                    cam.raw_n += 1
                    self.cond.notify_all()
                if self.record_dir is not None:
                    self._record(cam, jpg)
            sock.close()
            print(f'[guest_tracker] {cam.robot_id}: camera disconnected',
                  flush=True)
            time.sleep(0.5)

    def _record(self, cam: Camera, jpg: bytes) -> None:
        """받은 원본 JPEG 를 시험용으로 저장한다(모델 비교의 같은 입력).

        Args:
            cam: 프레임을 보낸 카메라.
            jpg: 원본 JPEG(회전 전).
        """
        folder = self.record_dir / cam.robot_id
        if cam.raw_n == 1:
            folder.mkdir(parents=True, exist_ok=True)
        name = f'{cam.raw_n:06d}.jpg'
        (folder / name).write_bytes(jpg)
        with open(folder / 'frames.csv', 'a', encoding='utf-8') as f:
            f.write(f'{name},{cam.raw_time:.3f}\n')

    # ------------------------------------------------------------ 추론
    def infer_loop(self) -> None:
        """새 프레임이 온 카메라를 차례로 추론하고 결과를 보낸다."""
        f_px: dict[str, float] = {}
        seen = {c.robot_id: 0 for c in self.cameras}
        while True:
            with self.cond:
                self.cond.wait_for(
                    lambda: any(c.raw_n != seen[c.robot_id]
                                for c in self.cameras), timeout=1.0)
                todo = [(c, c.raw, c.raw_n, c.raw_time) for c in self.cameras
                        if c.raw_n != seen[c.robot_id]]
            for cam, raw, n, t_frame in todo:
                seen[cam.robot_id] = n
                img = cv2.imdecode(np.frombuffer(raw, np.uint8),
                                   cv2.IMREAD_COLOR)
                if img is None:
                    continue
                # [수정 2026-11-24] 초점거리·회전을 카메라마다
                if cam.robot_id not in f_px:
                    f_px[cam.robot_id] = focal_px(img.shape[1],
                                                  self.args.hfov_deg)
                rot = _ROTATIONS[cam.rotate]
                if rot is not None:
                    img = cv2.rotate(img, rot)
                self._infer_one(cam, img, t_frame, f_px[cam.robot_id])

    def _infer_one(self, cam: Camera, img: np.ndarray, t_frame: float,
                   f_px: float) -> None:
        """프레임 하나를 추론해 결과·확인 화면을 갱신하고 전송한다.

        Args:
            cam: 프레임을 보낸 카메라.
            img: 회전까지 마친 BGR 영상.
            t_frame: 프레임을 받은 시각(unix 초).
            f_px: 초점거리(px).
        """
        t0 = time.time()
        # [수정 2026-11-24] 탐지 대신 추적(사람마다 track_id). 추적기가 낮은
        # 점수 상자로도 이어 붙이도록 추적에는 낮은 임계값(0.1)을 주고,
        # 고정 전 후보·화면 표시는 --conf 이상만 씀
        res = cam.model.track(img, persist=True, tracker=self.tracker_cfg,
                              classes=[PERSON_CLASS], conf=0.1,
                              imgsz=self.args.imgsz, device=self.args.device,
                              verbose=False)[0]
        infer_ms = (time.time() - t0) * 1000.0
        ids = (res.boxes.id.int().tolist() if res.boxes.id is not None
               else [None] * len(res.boxes))
        people = []
        for box, tid in zip(res.boxes, ids, strict=True):
            xyxy = [int(v) for v in box.xyxy[0].tolist()]
            people.append({'xyxy': xyxy, 'conf': round(float(box.conf[0]), 3),
                           'id': tid})
        with self.cond:
            lock_visit, lock_id = cam.lock_visit, cam.lock_id
        # 고정한 손님은 점수가 낮아도 유지, 나머지는 --conf 이상만
        people = [p for p in people if p['conf'] >= self.args.conf
                  or (lock_id is not None and p['id'] == lock_id)]
        guest, new_id = select_guest(people, lock_visit, lock_id)
        with self.cond:
            # 그 사이 /guides 로 고정이 바뀌었으면 이번 결과로 덮지 않음
            if cam.lock_visit == lock_visit and cam.lock_id == lock_id:
                cam.lock_id = new_id
        if new_id is not None and lock_id is None:
            print(f'[guest_tracker] {cam.robot_id}: visit {lock_visit} '
                  f'locked on track {new_id}', flush=True)
        out = guest_result(cam.robot_id, people, guest, img.shape[0],
                           self.args.person_height, f_px, lock_visit)
        out.update(camera=f'{cam.robot_id}_front',
                   model_version=self.model_version,
                   infer_ms=round(infer_ms, 1),
                   latency_ms=round((time.time() - t_frame) * 1000.0, 1),
                   stamp=round(time.time(), 3))
        self._draw(img, people, out)
        ok, jpg = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 80])
        with self.cond:
            cam.result = dict(out, people=people)
            if ok:
                cam.view = jpg.tobytes()
                cam.view_n += 1
            self.cond.notify_all()
        self._maybe_post(cam.robot_id, out)

    @staticmethod
    def _draw(img: np.ndarray, people: list[dict], out: dict) -> None:
        """확인 화면용으로 상자와 손님 거리를 그린다.

        Args:
            img: 그릴 영상(제자리에서 바뀜).
            people: 탐지된 사람 목록.
            out: guest_result 결과(손님 상자 'box').
        """
        for p in people:
            x1, y1, x2, y2 = p['xyxy']
            guest = p['xyxy'] == out.get('box')
            color = (0, 200, 255) if guest else (0, 255, 0)
            cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
            label = f"#{p.get('id')} {p['conf']:.2f}"
            if guest:
                label = ('GUEST(lock) ' if out['locked'] else '') + label
                label += f" {out['distance']:.2f} m"
                if out['truncated']:
                    label += ' (cut)'
            cv2.putText(img, label, (x1, max(15, y1 - 5)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

    def _maybe_post(self, robot_id: str, out: dict) -> None:
        """로봇마다 post_hz 로 줄여 Central Control 에 POST 한다.

        보내지 못하면 2초 동안 보내지 않는다(관제가 아직 안 떴을 때 등).

        Args:
            robot_id: 결과의 로봇.
            out: 보낼 본문.
        """
        if self.args.central_url in ('', 'none'):
            return
        now = time.time()
        if now < self.post_ok_after:
            return
        if now - self.last_post.get(robot_id, 0.0) < 1.0 / self.args.post_hz:
            return
        self.last_post[robot_id] = now
        body = {k: v for k, v in out.items() if k != 'box'}
        req = urllib.request.Request(
            self.args.central_url, json.dumps(body).encode(),
            {'Content-Type': 'application/json'})
        try:
            urllib.request.urlopen(req, timeout=0.3).read()
        except (urllib.error.URLError, OSError) as e:
            self.post_ok_after = now + 2.0
            print(f'[guest_tracker] post failed: {e}', flush=True)

    # [수정 2026-11-24] 손님 고정 명령(Central Control -> POST /guides)
    def set_guides(self, guides: dict) -> dict:
        """안내 중인 (로봇 -> 방문 번호) 목록으로 손님 고정을 맞춘다.

        목록에 새로 들어오거나 방문 번호가 바뀐 로봇은 다음 프레임의 가장 앞
        사람으로 고정하고, 목록에 없는 로봇은 고정을 푼다. 같은 목록을 다시
        받아도 고정은 그대로다(1초마다 다시 받음).

        Args:
            guides: {robot_id: visit_id}.

        Returns:
            로봇별 고정 상태 {robot_id: {'visit': int, 'track_id': int|None}}.
        """
        with self.cond:
            for cam in self.cameras:
                visit = int(guides.get(cam.robot_id, 0) or 0)
                if visit != cam.lock_visit:
                    print(f'[guest_tracker] {cam.robot_id}: '
                          + (f'lock for visit {visit}' if visit else
                             f'unlock (visit {cam.lock_visit} done)'),
                          flush=True)
                    cam.lock_visit, cam.lock_id = visit, None
            return {c.robot_id: {'visit': c.lock_visit, 'track_id': c.lock_id}
                    for c in self.cameras}

    # ------------------------------------------------------------ 확인 화면
    def make_handler(self) -> type:
        """확인 화면 HTTP 처리기 클래스를 만든다.

        Returns:
            BaseHTTPRequestHandler 하위 클래스.
        """
        tracker = self

        class Handler(http.server.BaseHTTPRequestHandler):
            """/ 화면, /stream?robot=ID 탐지 영상, /detections 결과 JSON."""

            def do_GET(self) -> None:
                """경로에 맞는 응답을 보낸다."""
                url = urllib.parse.urlparse(self.path)
                query = urllib.parse.parse_qs(url.query)
                if url.path == '/detections':
                    with tracker.cond:
                        body = json.dumps(
                            {c.robot_id: c.result for c in tracker.cameras})
                    self._send(body.encode(), 'application/json')
                elif url.path == '/stream':
                    rid = query.get('robot', [tracker.cameras[0].robot_id])[0]
                    cam = next((c for c in tracker.cameras
                                if c.robot_id == rid), None)
                    if cam is None:
                        self.send_error(404)
                        return
                    self._stream(cam)
                else:
                    self._send(tracker.page().encode(),
                               'text/html; charset=utf-8')

            def do_POST(self) -> None:
                """POST /guides {'guides': {robot_id: visit_id}} 를 받는다."""
                if urllib.parse.urlparse(self.path).path != '/guides':
                    self.send_error(404)
                    return
                try:
                    n = min(int(self.headers.get('Content-Length', 0)), 65536)
                    body = json.loads(self.rfile.read(n) or b'{}')
                    locks = tracker.set_guides(dict(body.get('guides', {})))
                except (ValueError, TypeError, AttributeError) as e:
                    self.send_error(400, str(e))
                    return
                self._send(json.dumps(locks).encode(), 'application/json')

            def _send(self, body: bytes, ctype: str) -> None:
                self.send_response(200)
                self.send_header('Content-Type', ctype)
                self.end_headers()
                self.wfile.write(body)

            def _stream(self, cam: Camera) -> None:
                self.send_response(200)
                self.send_header('Content-Type',
                                 'multipart/x-mixed-replace; boundary=frame')
                self.end_headers()
                last = -1
                try:
                    while True:
                        with tracker.cond:
                            tracker.cond.wait_for(
                                lambda prev=last: cam.view_n != prev,
                                timeout=5)
                            jpg, last = cam.view, cam.view_n
                        if not jpg:
                            continue
                        self.wfile.write(
                            b'--frame\r\nContent-Type: image/jpeg\r\n'
                            + f'Content-Length: {len(jpg)}\r\n\r\n'.encode()
                            + jpg + b'\r\n')
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def log_message(self, fmt: str, *args: object) -> None:
                """접속 로그는 남기지 않는다."""
                del fmt, args

        return Handler

    def page(self) -> str:
        """카메라마다 탐지 영상과 요약 한 줄을 보여 주는 화면."""
        cells = ''.join(
            f'<div><p id="s_{c.robot_id}">{c.robot_id}</p>'
            f'<img src="/stream?robot={c.robot_id}"></div>'
            for c in self.cameras)
        return (
            '<!doctype html><meta charset=utf-8><title>guest_tracker</title>'
            '<style>body{margin:0;background:#111;color:#ccc;'
            'font:14px sans-serif;display:flex;gap:12px;flex-wrap:wrap;'
            'justify-content:center}img{max-height:88vh}</style>'
            + cells +
            '<script>setInterval(async()=>{try{const d=await(await '
            "fetch('/detections')).json();for(const[k,v]of "
            'Object.entries(d)){const e=document.getElementById("s_"+k);'
            "if(e&&v.robot_id)e.textContent=k+' | '+v.model_version+"
            "' | person '+v.count+' | '+(v.locked?'lock visit '+v.visit_id+"
            "' #'+v.track_id+' | ':'')+'guest '+(v.visible?v.distance+' m':"
            "'-')+' | infer '+v.infer_ms+' ms | latency '+v.latency_ms+"
            "' ms'}}catch(e){}},500)</script>")


def build_parser() -> argparse.ArgumentParser:
    """명령행 인자를 정의한다.

    Returns:
        ArgumentParser.
    """
    p = argparse.ArgumentParser(
        description='AI 서버: AMR 카메라에서 손님을 찾아 GUEST_TRACK 전송')
    p.add_argument('--camera', action='append', required=True,
                   help='robot=host[:port][@rotate], 로봇마다 한 번씩')
    p.add_argument('--model', default='yolov8s.pt',
                   help='yolov8s.pt, yolo11s.pt, yolo26s.pt 등')
    p.add_argument('--weights-dir', default='~/.frybot/models',
                   help='가중치를 두는(없으면 내려받는) 폴더')
    p.add_argument('--device', default='0', help="'0'(GPU) 또는 'cpu'")
    p.add_argument('--conf', type=float, default=0.4)
    p.add_argument('--tracker', default='botsort_reid',
                   choices=['botsort_reid', 'botsort', 'bytetrack'],
                   help='손님 고정용 추적기(시험 C에서 비교)')
    p.add_argument('--track-buffer', type=int, default=90,
                   help='놓친 추적을 살려 두는 프레임 수(30 fps 에서 3 s)')
    p.add_argument('--imgsz', type=int, default=640)
    p.add_argument('--rotate', default='180', choices=sorted(_ROTATIONS),
                   help='카메라 장착 방향 보정 기본값(로봇별 @rotate 가 우선)')
    p.add_argument('--hfov-deg', type=float, default=53.5,
                   help='가로 화각(ov5647 640x480 명목값, 확인 필요)')
    p.add_argument('--person-height', type=float, default=0.17,
                   help='손님(인형) 키 m. 거리 추정용, 실측 필요')
    p.add_argument('--central-url',
                   default='http://127.0.0.1:8100/ai/result',
                   help="결과를 보낼 주소. none 이면 보내지 않음")
    p.add_argument('--post-hz', type=float, default=5.0)
    p.add_argument('--view-port', type=int, default=8095,
                   help='확인 화면 포트(127.0.0.1). 0 이면 끔')
    p.add_argument('--record', default='',
                   help='원본 프레임을 저장할 폴더(모델 비교 시험용)')
    return p


def main(argv: list[str] | None = None) -> None:
    """인자를 읽고 수신·추론 스레드와 확인 화면을 띄운다.

    Args:
        argv: 명령행 인자(None 이면 sys.argv). ros2 launch 가 덧붙이는
            --ros-args 이후는 무시한다.
    """
    parser = build_parser()
    args, _ = parser.parse_known_args(argv)
    cameras = [parse_camera(s) for s in args.camera]
    tracker = GuestTracker(cameras, args)
    tracker.load_model()
    print(f'[guest_tracker] model {tracker.model_version} ready '
          f'(pid {os.getpid()}), central {args.central_url}',
          flush=True)
    for cam in cameras:
        threading.Thread(target=tracker.reader, args=(cam,),
                         daemon=True).start()
    if args.view_port:
        srv = http.server.ThreadingHTTPServer(
            ('127.0.0.1', args.view_port), tracker.make_handler())
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        print(f'[guest_tracker] view http://127.0.0.1:{args.view_port}/',
              flush=True)
    try:
        tracker.infer_loop()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
