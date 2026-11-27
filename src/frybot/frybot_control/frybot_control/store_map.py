"""Occupancy grid of the virtual store (proto), generated from layout.py.

The simulation publishes it on /map; robots in the virtual store load the
exported proto file in their map_server.

실기기는 실측 지도(maps/test_map_*)를 씀. 여기서 만드는 지도는 가상 매장
(proto)용.

  ros2 run frybot_control export_map <dir>     writes <dir>/store.pgm and <dir>/store.yaml
  ros2 run frybot_control export_map --proto   rewrites maps/proto (pgm, yaml, roadmap.json)

The grid holds what the layout knows: seat zones (tables + chairs), the cook-side wall and the outer walls 6-8 cm
outside the floor. Build the physical mock-up to these dimensions, or replace the file with a SLAM map that is
aligned to the same origin (floor corner at the charger side = map (0, 0), x toward the cook zone).
"""
import json
import os
import sys

from . import layout as L

MARGIN_CM = 10         # map margin around the 200 x 100 floor; outer walls stand 6-8 cm outside the floor
                       # (chargers and standby spots touch the floor edge, Nav2 needs room in front of the robot)


def build_grid():
    """1 cm occupancy grid. Returns (width, height, data, origin_x, origin_y).

    data 는 아래 행부터 1 cm 칸마다 0(빈칸) 또는 100(막힘). 원점은 바닥
    모서리(충전대 쪽)에서 MARGIN_CM 만큼 바깥(m).
    """
    w, h = L.W_CM + L.WALL_CM + 2 * MARGIN_CM, L.H_CM + 2 * MARGIN_CM
    data = [0] * (w * h)

    def fill(x0, y0, x1, y1):                    # cm, floor coordinates with y up
        for yc in range(max(0, int(y0) + MARGIN_CM), min(h, int(y1) + MARGIN_CM)):
            for xc in range(max(0, int(x0) + MARGIN_CM), min(w, int(x1) + MARGIN_CM)):
                data[yc * w + xc] = 100
    # 좌석 구역과 조리 구역 벽. layout 은 y 가 아래로 커지므로 위아래를 뒤집음
    for (x0, y0, x1, y1) in L.obstacle_rects_cm():
        fill(x0, L.H_CM - y1, x1, L.H_CM - y0)
    fill(-8, -8, -6, 108)                        # left wall
    fill(-8, -8, 204, -6)                        # bottom wall
    fill(-8, 106, 12, 108)                       # top wall, left of the door
    fill(32, 106, 204, 108)                      # top wall, right of the door
    return w, h, data, -MARGIN_CM / 100.0, -MARGIN_CM / 100.0


# [수정 2026-11-17] 파일 이름을 인자로 받음(maps/proto 저장에 같이 씀)
def export(out_dir, name='store'):
    """점유 격자를 map_server 가 읽는 pgm + yaml 두 파일로 쓴다.

    pgm 은 막힌 칸 0(검정), 빈칸 254(흰색)이고 yaml 은 trinary, 해상도
    1 cm 이다.

    Args:
        out_dir: 쓸 폴더(없으면 만듦).
        name: 파일 이름(확장자 제외).

    Returns:
        쓴 yaml 파일의 경로.
    """
    w, h, data, ox, oy = build_grid()
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, f'{name}.pgm'), 'wb') as f:
        f.write(f'P5\n{w} {h}\n255\n'.encode())
        for row in range(h - 1, -1, -1):                       # image rows run top-down, the grid bottom-up
            f.write(bytes(0 if v else 254 for v in data[row * w:(row + 1) * w]))
    with open(os.path.join(out_dir, f'{name}.yaml'), 'w') as f:
        f.write(f'image: {name}.pgm\nmode: trinary\nresolution: 0.01\norigin: [{ox}, {oy}, 0.0]\n'
                'negate: 0\noccupied_thresh: 0.65\nfree_thresh: 0.25\n')
    return os.path.join(out_dir, f'{name}.yaml')


# [수정 2026-11-17] 가상 매장 도면을 실측 지도와 같은 형식으로 maps/proto 에 저장
def export_proto(out_dir: str = '') -> str:
    """가상 매장 도면을 지도 폴더 형식(pgm, yaml, roadmap.json)으로 쓴다.

    layout.py 가 원본이다. 치수나 로드맵을 바꾸면 이 함수를 다시 실행한다.

    Args:
        out_dir: 쓸 폴더. 비우면 패키지의 maps/proto.

    Returns:
        쓴 roadmap.json 의 경로.
    """
    from .map_catalog import MAP_ROOT, PROTO_LABEL, PROTO_MAP_ID

    out_dir = out_dir or str(MAP_ROOT / PROTO_MAP_ID)
    export(out_dir, PROTO_MAP_ID)
    # map_id='' : 환경 변수와 상관없이 layout.py 의 가상 매장 로드맵을 씀
    graph = L.Graph(map_id='')
    roadmap = {
        'label': PROTO_LABEL,
        'map_yaml': f'{PROTO_MAP_ID}.yaml',
        'homes': [graph.alias[spot] for spot in L.HOME_SPOTS],
        'nodes': {key: [round(v, 4) for v in graph.nodes[key]]
                  for key in sorted(graph.nodes)},
        'edges': [list(edge) for edge in graph.edges],
        'waiting': list(graph.standby_nodes),
        'alias': dict(sorted(graph.alias.items())),
    }
    path = os.path.join(out_dir, 'roadmap.json')
    with open(path, 'w') as f:
        json.dump(roadmap, f, ensure_ascii=False, indent=2)
        f.write('\n')
    return path


def main():
    """export_map 명령의 진입점.

    --proto 면 maps/proto 를 다시 쓰고, 아니면 첫 인자 폴더(없으면 현재
    폴더)에 store.pgm, store.yaml 을 쓴다.
    """
    if '--proto' in sys.argv[1:]:
        print('wrote', export_proto())
        return
    out = sys.argv[1] if len(sys.argv) > 1 else '.'
    print('wrote', export(out))
