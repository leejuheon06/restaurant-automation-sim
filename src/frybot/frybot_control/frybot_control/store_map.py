"""Occupancy grid of the store, generated from layout.py (the simulation publishes it on /map; the real robots load
the exported file in their map_server).

  ros2 run frybot_control export_map <dir>     writes <dir>/store.pgm and <dir>/store.yaml

The grid holds what the layout knows: seat zones (tables + chairs), the cook-side wall and the outer walls 6-8 cm
outside the floor. Build the physical mock-up to these dimensions, or replace the file with a SLAM map that is
aligned to the same origin (floor corner at the charger side = map (0, 0), x toward the cook zone).
"""
import os
import sys

from . import layout as L

MARGIN_CM = 10         # map margin around the 200 x 100 floor; outer walls stand 6-8 cm outside the floor
                       # (chargers and standby spots touch the floor edge, Nav2 needs room in front of the robot)


def build_grid():
    """1 cm occupancy grid. Returns (width, height, data, origin_x, origin_y)."""
    w, h = L.W_CM + L.WALL_CM + 2 * MARGIN_CM, L.H_CM + 2 * MARGIN_CM
    data = [0] * (w * h)

    def fill(x0, y0, x1, y1):                    # cm, floor coordinates with y up
        for yc in range(max(0, int(y0) + MARGIN_CM), min(h, int(y1) + MARGIN_CM)):
            for xc in range(max(0, int(x0) + MARGIN_CM), min(w, int(x1) + MARGIN_CM)):
                data[yc * w + xc] = 100
    for (x0, y0, x1, y1) in L.obstacle_rects_cm():
        fill(x0, L.H_CM - y1, x1, L.H_CM - y0)
    fill(-8, -8, -6, 108)                        # left wall
    fill(-8, -8, 204, -6)                        # bottom wall
    fill(-8, 106, 12, 108)                       # top wall, left of the door
    fill(32, 106, 204, 108)                      # top wall, right of the door
    return w, h, data, -MARGIN_CM / 100.0, -MARGIN_CM / 100.0


def export(out_dir):
    w, h, data, ox, oy = build_grid()
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, 'store.pgm'), 'wb') as f:
        f.write(f'P5\n{w} {h}\n255\n'.encode())
        for row in range(h - 1, -1, -1):                       # image rows run top-down, the grid bottom-up
            f.write(bytes(0 if v else 254 for v in data[row * w:(row + 1) * w]))
    with open(os.path.join(out_dir, 'store.yaml'), 'w') as f:
        f.write(f'image: store.pgm\nmode: trinary\nresolution: 0.01\norigin: [{ox}, {oy}, 0.0]\n'
                'negate: 0\noccupied_thresh: 0.65\nfree_thresh: 0.25\n')
    return os.path.join(out_dir, 'store.yaml')


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else '.'
    print('wrote', export(out))
