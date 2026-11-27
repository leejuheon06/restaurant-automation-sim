#!/usr/bin/env python3
# [수정 2026-11-19] 새 파일: 테스트·주행 중 RViz 창(화면)을 runs/에 녹화
# [수정 2026-11-27] 관리자 화면 전용: 노트북 모니터(eDP-1) 전체를 찍음
"""테스트나 주행을 할 때 관리자 화면이 뜬 모니터를 녹화해 runs/ 아래에 둔다.

cam_record.py 와 짝이다. 관리자 화면(http://localhost:8080/admin)은 노트북
모니터에 전체 화면(F11)으로 띄우고, 이 스크립트는 그 모니터 영역 전체를
찍는다. 모니터의 위치·크기는 `xrandr --query` 의
`<이름> connected [primary] WxH+X+Y` 줄에서 읽는다(지금 PC:
`eDP-1 connected 1920x1080+1080+0`). 그 모니터를 못 찾으면 다른 화면(터미널)
이 찍히지 않게 연결된 모니터 이름을 보여 주고 끝난다(종료 코드 1).

영상(`admin_HHMMSS.mp4`)과 프레임별 시각(`admin_HHMMSS_frames.csv`)을 같은
실행 폴더에 저장한다. 시각은 카메라 영상, `events.csv` 와 같은 unix 초라서
merge_videos.py 가 두 영상을 시각으로 맞춰 붙일 수 있다. 2026-11-27 전 실행
폴더의 화면 영상은 `rviz_HHMMSS.mp4`(RViz 창) 이다.

화면의 그 영역을 찍는 방식이라, 녹화 중에 그 모니터에 다른 창을 띄우면
그대로 찍힌다. X11 세션에서만 된다.

사용 예:
    python3 scripts/screen_record.py --run-id d1_v001
    python3 scripts/screen_record.py --run-id t42 --duration 60
    python3 scripts/screen_record.py --run-id t43 --monitor HDMI-1-0

멈추기: 터미널에서 Ctrl+C(SIGINT)나 SIGTERM.
"""

import argparse
import csv
import datetime
import pathlib
import re
import signal
import subprocess
import sys
import time

import cv2
import numpy as np
from PIL import ImageGrab

_RUNS_DIR = pathlib.Path(__file__).resolve().parents[1] / 'runs'
_FONT = cv2.FONT_HERSHEY_SIMPLEX

_stop_requested = False


def _request_stop(signum: int, frame: object) -> None:
    """SIGINT·SIGTERM을 받으면 녹화 루프가 파일을 닫고 끝나게 한다."""
    del signum, frame
    global _stop_requested
    _stop_requested = True


def resolve_run_dir(runs_dir: pathlib.Path, run_id: str) -> pathlib.Path:
    """녹화 파일을 둘 실행 폴더를 정한다 (cam_record.py 와 같은 규칙).

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


# [수정 2026-11-27] 창 제목으로 영역을 찾던 find_window 를 지움. 창이 막
# 떴을 때 작은 크기를 잡거나(11-19 400x286), 못 찾으면 두 모니터 전체
# (터미널 포함)를 찍었음. 관리자 화면을 띄운 모니터 전체를 찍도록 바꿈
_MONITOR_LINE = re.compile(
    r'^(\S+) connected (?:primary )?(\d+)x(\d+)\+(-?\d+)\+(-?\d+)')


def find_monitor(name: str) -> tuple[tuple[int, int, int, int] | None,
                                      list[str]]:
    """모니터 name 의 화면 영역을 xrandr 출력에서 찾는다.

    Args:
        name: xrandr 의 출력 이름 (예: eDP-1).

    Returns:
        (영역, 연결된 모니터 이름 목록). 영역은 화면 좌표
        (왼쪽, 위, 오른쪽, 아래)이고, 못 찾으면 None.
    """
    try:
        out = subprocess.run(['xrandr', '--query'], check=True,
                             capture_output=True, text=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None, []
    box, names = None, []
    for line in out.splitlines():
        found = _MONITOR_LINE.match(line)
        if not found:
            continue
        names.append(found.group(1))
        if found.group(1) == name:
            width, height, left, top = (int(v) for v in found.groups()[1:])
            box = (left, top, left + width, top + height)
    return box, names


def grab(box: tuple[int, int, int, int] | None) -> np.ndarray:
    """화면(또는 그 일부)을 BGR 프레임으로 잡는다.

    Args:
        box: (왼쪽, 위, 오른쪽, 아래). None 이면 화면 전체(시작 때 X11
            화면 확인에만 씀).

    Returns:
        가로·세로가 짝수인 BGR 프레임.
    """
    frame = cv2.cvtColor(np.asarray(ImageGrab.grab(bbox=box)),
                         cv2.COLOR_RGB2BGR)
    height, width = frame.shape[:2]
    return np.ascontiguousarray(frame[:height - height % 2,
                                      :width - width % 2])


def _stamp(frame: np.ndarray, now: float) -> None:
    """프레임 왼쪽 위에 벽시계 시각(밀리초까지)을 찍는다."""
    text = datetime.datetime.fromtimestamp(now).strftime(
        '%Y-%m-%d %H:%M:%S.%f')[:-3] + f'  {now:.3f}'
    cv2.putText(frame, text, (10, 30), _FONT, 0.8, (0, 0, 0), 4,
                cv2.LINE_AA)
    cv2.putText(frame, text, (10, 30), _FONT, 0.8, (255, 255, 255), 1,
                cv2.LINE_AA)


def record(args: argparse.Namespace) -> int:
    """녹화 루프를 돌린다.

    Args:
        args: 명령행 인자.

    Returns:
        종료 코드 (0 정상, 1 실패).
    """
    # [수정 2026-11-27] 창 찾기(--window·--wait·크기 안정 대기)와 --full 을
    # 지움. 모니터 영역만 찍고, 못 찾으면 화면 전체로 넘어가지 않고 끝냄
    # (실행 폴더를 만들기 전에 확인해 빈 폴더가 남지 않게 함)
    box, names = find_monitor(args.monitor)
    if box is None:
        print(f"모니터 '{args.monitor}' 를 찾지 못함. 연결된 모니터: "
              f"{', '.join(names) or '없음(xrandr 확인)'}", file=sys.stderr)
        return 1
    run_dir = resolve_run_dir(pathlib.Path(args.runs_dir).expanduser(),
                              args.run_id)
    try:
        screen = grab(None)
    except OSError as err:
        print(f'화면을 잡지 못함 (X11 세션인지 확인): {err}',
              file=sys.stderr)
        return 1
    # [수정 2026-11-27] 모니터가 잡은 화면 밖이면 화면 전체 대신 끝냄
    if box[2] > screen.shape[1] or box[3] > screen.shape[0] \
            or box[0] < 0 or box[1] < 0:
        print(f"모니터 '{args.monitor}' 영역 {box} 이 화면 "
              f'{screen.shape[1]}x{screen.shape[0]} 밖임', file=sys.stderr)
        return 1
    frame = grab(box)
    height, width = frame.shape[:2]
    # [수정 2026-11-27] 파일 이름 rviz_ -> admin_ (관리자 화면 전용)
    base = run_dir / time.strftime('admin_%H%M%S')
    video_path = base.with_suffix('.mp4')
    writer = cv2.VideoWriter(str(video_path),
                             cv2.VideoWriter_fourcc(*'mp4v'),
                             args.fps, (width, height))
    if not writer.isOpened():
        print(f'{video_path}에 쓸 수 없음', file=sys.stderr)
        return 1

    # [수정 2026-11-27] 화면 전체로 넘어가는 경우가 없어짐
    print(f'녹화 시작: {video_path} ({width}x{height}, {args.fps} fps, '
          f'모니터 {args.monitor} 영역 {box})', flush=True)
    frames_path = base.parent / (base.name + '_frames.csv')
    period = 1.0 / args.fps
    count = 0
    start = time.time()
    with open(frames_path, 'w', newline='') as stream:
        log = csv.writer(stream)
        log.writerow(['frame', 'timestamp'])
        while not _stop_requested:
            now = time.time()
            if count:
                frame = grab(box)
                if frame.shape[:2] != (height, width):
                    frame = cv2.resize(frame, (width, height))
            if not args.no_stamp:
                _stamp(frame, now)
            writer.write(frame)
            log.writerow([count, f'{now:.3f}'])
            count += 1
            if args.duration and now - start >= args.duration:
                break
            # 다음 프레임 시각까지 쉼 (늦었으면 쉬지 않음)
            rest = start + count * period - time.time()
            if rest > 0:
                time.sleep(rest)
    elapsed = time.time() - start
    writer.release()
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
    ap.add_argument('--run-id', default='',
                    help="실행 폴더 이름. 'latest'는 가장 최근 폴더, "
                         '비우면 cam_YYYYMMDD_HHMMSS')
    ap.add_argument('--runs-dir', default=str(_RUNS_DIR))
    # [수정 2026-11-27] --window·--wait·--full 을 지우고 --monitor 추가
    # (관리자 화면을 띄운 모니터 전체를 찍음)
    ap.add_argument('--monitor', default='eDP-1',
                    help='녹화할 모니터(xrandr 출력 이름). 관리자 화면을 '
                         '전체 화면으로 띄운 노트북 모니터가 기본')
    ap.add_argument('--fps', type=int, default=15)
    ap.add_argument('--duration', type=float, default=0.0,
                    help='녹화 시간(초). 0이면 멈출 때까지')
    ap.add_argument('--no-stamp', action='store_true',
                    help='영상에 시각을 찍지 않음')
    args = ap.parse_args()
    signal.signal(signal.SIGINT, _request_stop)
    signal.signal(signal.SIGTERM, _request_stop)
    try:
        return record(args)
    except FileNotFoundError as err:
        print(err, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
