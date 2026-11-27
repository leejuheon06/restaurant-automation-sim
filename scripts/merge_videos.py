#!/usr/bin/env python3
# [수정 2026-11-19] 새 파일: 카메라 영상과 RViz 영상을 시각으로 맞춰 붙임
# [수정 2026-11-27] 화면 영상 기본값: admin_*.mp4(관리자 화면), 없으면 rviz_*
"""cam_record.py 와 screen_record.py 의 영상을 좌우로 붙인 영상을 만든다.

화면 영상은 폴더의 가장 최근 `admin_*.mp4`(2026-11-27부터 관리자 화면)이고,
없으면 예전 실행 폴더의 `rviz_*.mp4`(RViz 창)를 쓴다.

두 영상의 프레임 시각 파일(`*_frames.csv`, unix 초)을 읽어, 두 영상이
함께 찍힌 구간만 같은 시각의 프레임끼리 붙인다. 녹화를 시작한 순간이
달라도 된다. 결과는 `combined_HHMMSS.mp4` 와 `combined_HHMMSS_frames.csv`.

사용 예:
    python3 scripts/merge_videos.py runs/d1_v001
    python3 scripts/merge_videos.py runs/d1_v001 --fps 15 --height 720
    python3 scripts/merge_videos.py runs/d1_v001 --camera <카메라 영상>
        --screen <화면 영상>      (한 줄로 이어서 씀)
"""

import argparse
import csv
import pathlib
import sys

import cv2
import numpy as np


class TimedVideo:
    """프레임 시각 파일이 딸린 영상을 시각 순서대로 읽는다."""

    def __init__(self, video: pathlib.Path) -> None:
        """영상과 프레임 시각 파일을 연다.

        Args:
            video: 영상 경로. 같은 폴더에 <이름>_frames.csv 가 있어야 함.

        Raises:
            FileNotFoundError: 프레임 시각 파일이 없을 때.
            RuntimeError: 영상을 열 수 없거나 프레임 시각이 비었을 때.
        """
        frames = video.with_name(video.stem + '_frames.csv')
        if not frames.is_file():
            raise FileNotFoundError(f'{frames} 가 없음')
        with open(frames, newline='') as stream:
            self.times = [float(row['timestamp'])
                          for row in csv.DictReader(stream)]
        self.cap = cv2.VideoCapture(str(video))
        if not self.cap.isOpened() or not self.times:
            raise RuntimeError(f'{video} 를 읽을 수 없음')
        self.path = video
        self.index = -1
        self.frame = None

    def at(self, when: float) -> np.ndarray | None:
        """시각 when 에 보이던 프레임(그 시각 이전의 마지막 프레임)을 준다.

        Args:
            when: unix 초. 부를 때마다 같거나 커져야 한다.

        Returns:
            BGR 프레임. 아직 첫 프레임 전이거나 영상이 끝났으면 None.
        """
        while (self.index + 1 < len(self.times)
               and self.times[self.index + 1] <= when):
            ok, frame = self.cap.read()
            if not ok:
                return self.frame
            self.index += 1
            self.frame = frame
        return self.frame

    def close(self) -> None:
        """영상을 닫는다."""
        self.cap.release()


def newest(run_dir: pathlib.Path, prefix: str) -> pathlib.Path:
    """실행 폴더에서 prefix 로 시작하는 가장 최근 영상을 찾는다.

    Args:
        run_dir: 실행 폴더.
        prefix: 'camera', 'admin' 또는 'rviz'.

    Returns:
        영상 경로.

    Raises:
        FileNotFoundError: 그런 영상이 없을 때.
    """
    found = sorted(run_dir.glob(f'{prefix}_*.mp4'))
    if not found:
        raise FileNotFoundError(f'{run_dir} 에 {prefix}_*.mp4 가 없음')
    return found[-1]


# [수정 2026-11-27] 신규: 화면 영상을 admin_ 먼저, 없으면 rviz_ 로 찾음
def newest_screen(run_dir: pathlib.Path) -> pathlib.Path:
    """실행 폴더의 가장 최근 화면 영상(admin_, 없으면 rviz_)을 찾는다.

    Args:
        run_dir: 실행 폴더.

    Returns:
        영상 경로.

    Raises:
        FileNotFoundError: admin_*.mp4 도 rviz_*.mp4 도 없을 때.
    """
    try:
        return newest(run_dir, 'admin')
    except FileNotFoundError:
        pass
    try:
        return newest(run_dir, 'rviz')
    except FileNotFoundError:
        raise FileNotFoundError(
            f'{run_dir} 에 admin_*.mp4 도 rviz_*.mp4 도 없음') from None


def fit(frame: np.ndarray, height: int) -> np.ndarray:
    """프레임을 세로 height 에 맞게 비율을 지켜 줄이거나 늘린다.

    Args:
        frame: BGR 프레임.
        height: 맞출 세로 픽셀.

    Returns:
        세로가 height 이고 가로가 짝수인 프레임.
    """
    width = int(round(frame.shape[1] * height / frame.shape[0]))
    width -= width % 2
    return cv2.resize(frame, (width, height))


def merge(args: argparse.Namespace) -> int:
    """두 영상을 시각으로 맞춰 좌우로 붙인다.

    Args:
        args: 명령행 인자.

    Returns:
        종료 코드 (0 정상, 1 실패).
    """
    run_dir = pathlib.Path(args.run_dir).expanduser()
    camera = TimedVideo(pathlib.Path(args.camera) if args.camera
                        else newest(run_dir, 'camera'))
    # [수정 2026-11-27] 관리자 화면(admin_) 우선, 없으면 예전 rviz_
    screen = TimedVideo(pathlib.Path(args.screen) if args.screen
                        else newest_screen(run_dir))
    start = max(camera.times[0], screen.times[0])
    end = min(camera.times[-1], screen.times[-1])
    if end <= start:
        print('두 영상이 함께 찍힌 구간이 없음', file=sys.stderr)
        return 1
    stamp = camera.path.stem.split('_', 1)[-1]
    out_path = run_dir / f'combined_{stamp}.mp4'
    frames_path = run_dir / f'combined_{stamp}_frames.csv'
    writer = None
    count, worst = 0, 0.0
    with open(frames_path, 'w', newline='') as stream:
        log = csv.writer(stream)
        log.writerow(['frame', 'timestamp', 'camera_frame', 'screen_frame'])
        when = start
        while when <= end:
            left, right = camera.at(when), screen.at(when)
            if left is None or right is None:
                when += 1.0 / args.fps
                continue
            both = np.hstack([fit(left, args.height),
                              fit(right, args.height)])
            if writer is None:
                size = (both.shape[1], both.shape[0])
                writer = cv2.VideoWriter(
                    str(out_path), cv2.VideoWriter_fourcc(*'mp4v'),
                    args.fps, size)
                if not writer.isOpened():
                    print(f'{out_path} 에 쓸 수 없음', file=sys.stderr)
                    return 1
            writer.write(both)
            log.writerow([count, f'{when:.3f}', camera.index, screen.index])
            worst = max(worst, abs(camera.times[camera.index]
                                   - screen.times[screen.index]))
            count += 1
            when += 1.0 / args.fps
    camera.close()
    screen.close()
    if writer is None:
        print('붙일 프레임이 없음', file=sys.stderr)
        return 1
    writer.release()
    print(f'합친 영상: {out_path} ({count}프레임, {end - start:.1f}초, '
          f'{args.fps} fps)')
    print(f'  왼쪽 {camera.path.name}, 오른쪽 {screen.path.name}')
    print(f'  두 영상의 프레임 시각 차이 최대 {worst * 1000:.0f} ms')
    print(f'  프레임 시각: {frames_path}')
    return 0


def main() -> int:
    """명령행 인자를 읽고 영상을 합친다.

    Returns:
        종료 코드.
    """
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('run_dir', help='실행 폴더 (예: runs/d1_v001)')
    ap.add_argument('--camera', default='',
                    help='카메라 영상. 비우면 폴더의 가장 최근 camera_*.mp4')
    ap.add_argument('--screen', default='',
                    # [수정 2026-11-27] 기본 admin_*, 없으면 rviz_*
                    help='화면 영상. 비우면 폴더의 가장 최근 admin_*.mp4'
                         '(관리자 화면), 없으면 rviz_*.mp4(예전 폴더)')
    ap.add_argument('--fps', type=int, default=15)
    ap.add_argument('--height', type=int, default=720,
                    help='합친 영상의 세로 픽셀')
    args = ap.parse_args()
    try:
        return merge(args)
    except (FileNotFoundError, RuntimeError) as err:
        print(err, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
