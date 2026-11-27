#!/usr/bin/env python3
# [수정 2026-11-19] 새 파일: 테스트·주행 중 USB 카메라 영상을 runs/에 녹화
"""테스트나 주행을 할 때 USB 카메라 영상을 녹화해 runs/ 아래에 저장한다.

영상(`camera_HHMMSS.mp4`)과 프레임별 시각(`camera_HHMMSS_frames.csv`)을
같은 실행 폴더에 저장한다. 시각은 `events.csv`의 `timestamp`와 같은
unix 초라서, 이벤트가 영상의 몇 번째 프레임인지 바로 맞춰 볼 수 있다.

사용 예:
    python3 scripts/cam_record.py                     # runs/cam_<시각>/
    python3 scripts/cam_record.py --run-id latest     # 가장 최근 실행 폴더
    python3 scripts/cam_record.py --run-id t42 --duration 60 --no-preview

[수정 2026-11-23] 작업 지시 18: 녹화하는 동안 장치를 이 프로그램이 잡고 있어
관제의 ceiling_locator 가 카메라를 열 수 없으므로, 0.5초마다 시각을 찍기 전
원본 프레임을 --latest 파일(기본 ~/.frybot/ceiling/latest.jpg)에 바꿔 끼워
씀. ceiling_locator 는 장치를 못 열면 2초 안의 이 파일을 씀. '' 이면 끔.

멈추기: 미리보기 창에서 q, 또는 터미널에서 Ctrl+C(SIGINT)나 SIGTERM.
"""

import argparse
import csv
import datetime
import os
import pathlib
import signal
import sys
import time

import cv2

_RUNS_DIR = pathlib.Path(__file__).resolve().parents[1] / 'runs'
_WINDOW = 'cam_record (q: stop)'
_FONT = cv2.FONT_HERSHEY_SIMPLEX

_stop_requested = False


def _request_stop(signum: int, frame: object) -> None:
    """SIGINT·SIGTERM을 받으면 녹화 루프가 파일을 닫고 끝나게 한다."""
    del signum, frame
    global _stop_requested
    _stop_requested = True


def resolve_run_dir(runs_dir: pathlib.Path, run_id: str) -> pathlib.Path:
    """녹화 파일을 둘 실행 폴더를 정한다.

    Args:
        runs_dir: 실행 폴더들이 있는 곳 (보통 ~/frybot_ws/runs).
        run_id: 폴더 이름. 'latest'면 가장 최근에 바뀐 폴더,
            빈 문자열이면 cam_YYYYMMDD_HHMMSS.

    Returns:
        만들어 둔 실행 폴더 경로.

    Raises:
        FileNotFoundError: 'latest'인데 runs_dir에 폴더가 없을 때.
    """
    if run_id == 'latest':
        dirs = [d for d in runs_dir.iterdir() if d.is_dir()] \
            if runs_dir.is_dir() else []
        if not dirs:
            raise FileNotFoundError(f'{runs_dir}에 실행 폴더가 없음')
        return max(dirs, key=lambda d: d.stat().st_mtime)
    name = run_id or time.strftime('cam_%Y%m%d_%H%M%S')
    run_dir = runs_dir / name
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def open_camera(device: str, width: int, height: int,
                fps: int) -> cv2.VideoCapture:
    """카메라를 MJPG로 열고 해상도·프레임률을 맞춘다.

    Args:
        device: 장치 경로 (예: /dev/video0).
        width: 요청 가로 픽셀.
        height: 요청 세로 픽셀.
        fps: 요청 프레임률.

    Returns:
        열린 VideoCapture.

    Raises:
        RuntimeError: 장치를 열 수 없거나 다른 프로그램이 쓰고 있을 때.
    """
    cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
    if not cap.isOpened():
        raise RuntimeError(
            f'{device}를 열 수 없음 (다른 프로그램이 쓰는 중인지 확인)')
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, fps)
    return cap


def _stamp(frame, now: float) -> None:
    """프레임 왼쪽 위에 벽시계 시각(밀리초까지)을 찍는다."""
    text = datetime.datetime.fromtimestamp(now).strftime(
        '%Y-%m-%d %H:%M:%S.%f')[:-3] + f'  {now:.3f}'
    cv2.putText(frame, text, (10, 30), _FONT, 0.8, (0, 0, 0), 4,
                cv2.LINE_AA)
    cv2.putText(frame, text, (10, 30), _FONT, 0.8, (255, 255, 255), 1,
                cv2.LINE_AA)


# [수정 2026-11-23] 작업 지시 18: 신규. ceiling_locator 와 카메라 공유
def _write_latest(path: str, frame) -> None:
    """원본 프레임을 path 에 쓴다(임시 파일에 쓰고 바꿔 끼움)."""
    ok, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
    if not ok:
        return
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + '.tmp', 'wb') as stream:
            stream.write(buf.tobytes())
        os.replace(path + '.tmp', path)
    except OSError as err:
        print(f'최신 프레임 파일을 쓸 수 없음: {err}', file=sys.stderr)


def record(args: argparse.Namespace) -> int:
    """녹화 루프를 돌린다.

    Args:
        args: 명령행 인자.

    Returns:
        종료 코드 (0 정상, 1 실패).
    """
    run_dir = resolve_run_dir(pathlib.Path(args.runs_dir).expanduser(),
                              args.run_id)
    cap = open_camera(args.device, args.width, args.height, args.fps)
    ok, frame = cap.read()
    if not ok:
        cap.release()
        print(f'{args.device}에서 프레임을 읽지 못함', file=sys.stderr)
        return 1
    height, width = frame.shape[:2]
    base = run_dir / time.strftime('camera_%H%M%S')
    video_path = base.with_suffix('.mp4')
    writer = cv2.VideoWriter(str(video_path),
                             cv2.VideoWriter_fourcc(*'mp4v'),
                             args.fps, (width, height))
    if not writer.isOpened():
        cap.release()
        print(f'{video_path}에 쓸 수 없음', file=sys.stderr)
        return 1

    signal.signal(signal.SIGINT, _request_stop)
    signal.signal(signal.SIGTERM, _request_stop)
    print(f'녹화 시작: {video_path} ({width}x{height}, {args.fps} fps)',
          flush=True)
    frames_path = base.parent / (base.name + '_frames.csv')
    count = 0
    start = time.time()
    # [수정 2026-11-23] 작업 지시 18: 최신 프레임 파일(0.5초마다)
    latest = os.path.expanduser(args.latest) if args.latest else ''
    latest_t = 0.0
    with open(frames_path, 'w', newline='') as stream:
        log = csv.writer(stream)
        log.writerow(['frame', 'timestamp'])
        while not _stop_requested:
            if count:
                ok, frame = cap.read()
                if not ok:
                    print('프레임 읽기 실패, 녹화를 끝냄', file=sys.stderr)
                    break
            now = time.time()
            if latest and now - latest_t >= 0.5:
                _write_latest(latest, frame)
                latest_t = now
            if not args.no_stamp:
                _stamp(frame, now)
            writer.write(frame)
            log.writerow([count, f'{now:.3f}'])
            count += 1
            if not args.no_preview:
                cv2.imshow(_WINDOW, frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
            if args.duration and now - start >= args.duration:
                break
    elapsed = time.time() - start
    writer.release()
    cap.release()
    if not args.no_preview:
        cv2.destroyAllWindows()
    rate = count / elapsed if elapsed > 0 else 0.0
    print(f'녹화 끝: {count}프레임, {elapsed:.1f}초 (실제 {rate:.1f} fps)')
    print(f'  영상: {video_path}')
    print(f'  프레임 시각: {frames_path}')
    return 0


def main() -> int:
    """명령행 인자를 읽고 녹화한다.

    Returns:
        종료 코드.
    """
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--device', default='/dev/video0')
    # [수정 2026-11-23] 작업 지시 18: ceiling_locator 가 녹화 중에 읽는 파일
    ap.add_argument('--latest', default='~/.frybot/ceiling/latest.jpg',
                    help="최신 원본 프레임 파일. '' 이면 쓰지 않음")
    ap.add_argument('--run-id', default='',
                    help="실행 폴더 이름. 'latest'는 가장 최근 폴더, "
                         '비우면 cam_YYYYMMDD_HHMMSS')
    ap.add_argument('--runs-dir', default=str(_RUNS_DIR))
    ap.add_argument('--width', type=int, default=1280)
    ap.add_argument('--height', type=int, default=720)
    ap.add_argument('--fps', type=int, default=30)
    ap.add_argument('--duration', type=float, default=0.0,
                    help='녹화 시간(초). 0이면 멈출 때까지')
    ap.add_argument('--no-preview', action='store_true',
                    help='미리보기 창 없이 녹화 (SSH 등 화면 없을 때)')
    ap.add_argument('--no-stamp', action='store_true',
                    help='영상에 시각을 찍지 않음')
    args = ap.parse_args()
    try:
        return record(args)
    except (RuntimeError, FileNotFoundError) as err:
        print(err, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
