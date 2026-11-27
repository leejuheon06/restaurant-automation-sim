
"""Estimate each robot's heading at a known roadmap node by matching one lidar scan against the map, then give
AMCL that pose. usage: relocalize.py pinky1:B1 pinky3:A1 [--send]"""
import sys, math, time, json, yaml, rclpy
import numpy as np
from PIL import Image
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan
from geometry_msgs.msg import PoseWithCovarianceStamped
from frybot_control.map_catalog import profile

prof = profile('test_map_v001')
meta = yaml.safe_load(open(prof['yaml']))
img = np.array(Image.open(prof['yaml'].rsplit('/', 1)[0] + '/' + meta['image']).convert('L'))
res, (ox, oy, _) = meta['resolution'], meta['origin']
occ = img < 100                      # dark = occupied
H, Wd = occ.shape
# distance (cells) to the nearest occupied cell, brute force (the map is tiny)
ys, xs = np.nonzero(occ)
gy, gx = np.mgrid[0:H, 0:Wd]
dist = np.sqrt(((gy[..., None] - ys) ** 2 + (gx[..., None] - xs) ** 2).min(axis=2)) * res

def score(x, y, yaw, ang, rng):
    # lidar sits 1.7 cm behind the base centre and is mounted turned by pi
    lx, ly = x - 0.017 * math.cos(yaw), y - 0.017 * math.sin(yaw)
    a = ang + yaw + math.pi
    px, py = lx + rng * np.cos(a), ly + rng * np.sin(a)
    cx = np.floor((px - ox) / res).astype(int); cy = H - 1 - np.floor((py - oy) / res).astype(int)
    inside = (cx >= 0) & (cx < Wd) & (cy >= 0) & (cy < H)
    d = np.full(len(rng), 0.5)
    d[inside] = dist[cy[inside], cx[inside]]
    return float(np.mean(np.exp(-(d / 0.06) ** 2)))

rclpy.init(); n = Node('frybot_relocalize')
jobs = dict(s.split(':') for s in sys.argv[1:] if ':' in s)
scans = {}
for rid in jobs:
    n.create_subscription(LaserScan, f'/{rid}/scan', lambda m, r=rid: scans.setdefault(r, m), qos_profile_sensor_data)
t0 = time.time()
while len(scans) < len(jobs) and time.time() - t0 < 15: rclpy.spin_once(n, timeout_sec=0.2)
pubs = {rid: n.create_publisher(PoseWithCovarianceStamped, f'/{rid}/initialpose', 1) for rid in jobs}
best = {}
for rid, node in jobs.items():
    if rid not in scans: print(rid, 'NO SCAN'); continue
    m = scans[rid]; r = np.array(m.ranges); a = m.angle_min + np.arange(len(r)) * m.angle_increment
    ok = np.isfinite(r) & (r > 0.08) & (r < 3.0)
    r, a = r[ok], a[ok]
    x, y = prof['nodes'][node]
    cands = []
    for deg in range(0, 360, 3):
        for dx in (-0.04, 0, 0.04):
            for dy in (-0.04, 0, 0.04):
                cands.append((score(x + dx, y + dy, math.radians(deg), a, r), deg, dx, dy))
    cands.sort(reverse=True)
    top = cands[0]
    other = max((c for c in cands if min(abs(c[1] - top[1]), 360 - abs(c[1] - top[1])) > 30), default=(0, 0, 0, 0))
    best[rid] = (x + top[2], y + top[3], math.radians(top[1]))
    print(f'{rid} at {node}: heading {top[1]} deg (0 = +x), score {top[0]:.2f}; next best direction {other[1]} deg score {other[0]:.2f}; beams {len(r)}')
if '--send' in sys.argv:
    for k in range(5):
        for rid, (x, y, yaw) in best.items():
            m = PoseWithCovarianceStamped(); m.header.frame_id = 'map'; m.header.stamp = n.get_clock().now().to_msg()
            m.pose.pose.position.x, m.pose.pose.position.y = x, y
            m.pose.pose.orientation.z, m.pose.pose.orientation.w = math.sin(yaw / 2), math.cos(yaw / 2)
            m.pose.covariance[0] = m.pose.covariance[7] = 0.04 ** 2; m.pose.covariance[35] = 0.15 ** 2
            pubs[rid].publish(m)
        rclpy.spin_once(n, timeout_sec=0.1); time.sleep(0.8)
    print('initial poses sent')
