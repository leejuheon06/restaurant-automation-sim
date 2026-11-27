"""천장 카메라 위치 판정의 준비·점검 도구(ROS 없이 실행).

[수정 2026-11-23] 신규: 작업 지시 18, T-55.

  ros2 run frybot_control ceiling_tool reference --map-id test_map_v05
      맵 안에 로봇·사람이 없을 때 빈 바닥 기준 화면을 저장
      (~/.frybot/ceiling/<map_id>/reference.png)
  ros2 run frybot_control ceiling_tool markers --map-id test_map_v05
      바닥 모서리에 붙인 ArUco(40~43)를 찾아 지금의 수동 대응(벽 바닥선)으로
      중심의 지도 좌표를 구하고 roadmap.json 에 넣을 JSON 조각을 출력
  ros2 run frybot_control ceiling_tool print-markers --out <폴더>
      인쇄용 마커(기본 한 변 8 cm, 300 dpi PNG 와 실제 크기 PDF)
  ros2 run frybot_control ceiling_tool check --map-id test_map_v05 \
      --at 0.12,0.02 1.59,-0.36
      지금 화면에서 후보 자리 점수(ceiling_locator 와 같은 계산)
"""
import argparse
import json
import os
import sys

import cv2
import numpy as np

from frybot_control import ceiling_view as cv
from frybot_control.map_catalog import profile


def _frame(args: argparse.Namespace) -> np.ndarray:
    """--image 가 있으면 그 파일, 없으면 카메라 한 장."""
    if args.image:
        img = cv2.imread(args.image)
        if img is None:
            sys.exit(f'{args.image} 를 읽을 수 없음')
        return img
    try:
        img, _ = cv.grab(args.device, args.latest)
    except (cv.CameraBusyError, cv.CameraFailError) as err:
        sys.exit(str(err))
    return img


def cmd_reference(args: argparse.Namespace) -> None:
    """빈 바닥 기준 화면을 저장한다(맵 안에 로봇이 없어야 함)."""
    img = _frame(args)
    old = cv.load_reference(args.store_dir, args.map_id)
    if old is not None and old.shape == img.shape:
        box = cv.map_box(profile(args.map_id)['yaml'])
        cal = cv.Calib.from_walls(box)
        floor = cal.floor_mask(img.shape, box)
        m = cv.change_mask(img, old, floor)
        print(f'이전 기준 화면과 다른 바닥: '
              f'{(m > 0).sum() / max(1, (floor > 0).sum()):.1%}')
    path = cv.save_reference(args.store_dir, args.map_id, img,
                             'ceiling_tool reference (empty floor)')
    print(f'저장: {path}  (맵 안에 로봇·사람이 없는 화면이어야 함)')


def cmd_markers(args: argparse.Namespace) -> None:
    """보이는 마커 중심의 지도 좌표를 JSON 조각으로 출력한다."""
    img = _frame(args)
    prof = profile(args.map_id)
    box = cv.map_box(prof['yaml'])
    cal = cv.Calib.from_walls(box)
    found = cv.detect_markers(img)
    want = {i: found[i] for i in sorted(found) if i in args.ids}
    if not want:
        sys.exit(f'마커 {args.ids} 가 보이지 않음(보인 것: {sorted(found)})')
    xy = cal.to_map(np.array(list(want.values())))
    snippet = {str(i): [round(float(x), 3), round(float(y), 3)]
               for i, (x, y) in zip(want, xy, strict=True)}
    print(f'보인 마커 {len(want)}개(4개 이상이어야 마커 대응을 씀). '
          f'수동 대응 기준이라 오차는 약 ±3 cm.')
    print('roadmap.json 에 넣을 조각:')
    print(json.dumps({'ceiling_markers': snippet}, ensure_ascii=False))
    old = prof.get('ceiling_markers') or {}
    for i, (x, y) in snippet.items():
        if i in old:
            d = np.hypot(old[i][0] - x, old[i][1] - y)
            print(f'  {i}: 지금 roadmap 값과 {d * 100:.1f} cm 차이')


def cmd_print(args: argparse.Namespace) -> None:
    """인쇄용 마커 PNG(300 dpi)와 실제 크기 PDF 를 만든다."""
    from PIL import Image  # 인쇄 파일을 만들 때만 씀

    os.makedirs(args.out, exist_ok=True)
    dpi = 300
    side = round(args.size_cm / 2.54 * dpi)          # 마커 한 변(화소)
    margin = round(1.0 / 2.54 * dpi)                 # 흰 여백 1 cm
    d = cv2.aruco.getPredefinedDictionary(cv.MARKER_DICT)
    pages = []
    for i in args.ids:
        mk = cv2.aruco.generateImageMarker(d, i, side)
        page = np.full((side + 2 * margin, side + 2 * margin), 255, np.uint8)
        page[margin:margin + side, margin:margin + side] = mk
        # 자를 선(연한 회색)과 번호·크기 글
        cv2.rectangle(page, (2, 2), (page.shape[1] - 3, page.shape[0] - 3),
                      200, 2)
        cv2.putText(page, f'ID {i}  {args.size_cm:g} cm  DICT_4X4_50',
                    (margin, margin - 20), cv2.FONT_HERSHEY_SIMPLEX, 1.2,
                    0, 2)
        path = os.path.join(args.out, f'ceiling_marker_{i}.png')
        Image.fromarray(page).save(path, dpi=(dpi, dpi))
        pages.append(Image.fromarray(page).convert('RGB'))
        print(path)
    pdf = os.path.join(args.out, 'ceiling_markers.pdf')
    pages[0].save(pdf, save_all=True, append_images=pages[1:],
                  resolution=dpi)
    print(pdf, f'(배율 100% 로 인쇄하면 마커 한 변 {args.size_cm:g} cm)')


def cmd_check(args: argparse.Namespace) -> None:
    """지금 화면에서 후보 자리 점수를 낸다(ceiling_locator 와 같은 계산)."""
    img = _frame(args)
    prof = profile(args.map_id)
    box = cv.map_box(prof['yaml'])
    manual = cv.Calib.from_walls(box)
    cal = cv.Calib.from_markers(img, prof.get('ceiling_markers') or {},
                                manual.k) or manual
    ref = cv.load_reference(args.store_dir, args.map_id)
    pts = [tuple(float(v) for v in a.split(',')) for a in args.at]
    print(cv.spot_check(img, ref, cal, box, pts))


def main() -> None:
    """명령줄 진입점."""
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name, fn in (('reference', cmd_reference), ('markers', cmd_markers),
                     ('check', cmd_check)):
        s = sub.add_parser(name)
        s.set_defaults(fn=fn)
        s.add_argument('--map-id', required=True)
        s.add_argument('--device', default='/dev/video0')
        s.add_argument('--latest', default='~/.frybot/ceiling/latest.jpg')
        s.add_argument('--store-dir', default='~/.frybot/ceiling')
        s.add_argument('--image', default='', help='카메라 대신 이 이미지')
        if name == 'markers':
            s.add_argument('--ids', type=int, nargs='+',
                           default=[40, 41, 42, 43])
        if name == 'check':
            s.add_argument('--at', nargs='+', required=True,
                           help='후보 x,y (m)')
    s = sub.add_parser('print-markers')
    s.set_defaults(fn=cmd_print)
    s.add_argument('--out', required=True)
    s.add_argument('--ids', type=int, nargs='+', default=[40, 41, 42, 43])
    s.add_argument('--size-cm', type=float, default=8.0)
    args = ap.parse_args()
    args.fn(args)


if __name__ == '__main__':
    main()
