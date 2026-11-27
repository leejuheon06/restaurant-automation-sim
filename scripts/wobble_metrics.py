#!/usr/bin/env python3
"""실기기 흔들림 측정 (작업 지시서 6, 3.2).

[수정 2026-11-18] 신규. 관제 PC 에서 남긴 bag 과 실행 기록(events.csv),
지도의 roadmap.json 을 읽어 이동 명령마다 흔들림 지표를 낸다. 관제·로봇
코드는 건드리지 않는다.

    source install/setup.bash
    python3 scripts/wobble_metrics.py runs/<run_id> [--bag runs/<run_id>/bag]
        [--map-id test_map_v001] [--csv out.csv]

지표(이동 명령 하나 = TASK_ASSIGN 부터 TASK_DONE 까지)
    seg_n, dist_m, time_s, seg_time_med  구간 수(ZONE_ENTER), 이동 거리
        (/fleet/robot_status 위치), 소요 시간, 구간당 소요 시간 중앙값
    flip_per_m   cmd_vel.angular.z 부호가 바뀐 횟수 / 이동 거리
                 (|wz| < FLIP_MIN_W 은 0 으로 보고 건너뜀)
    spin_ratio   |vx| < STILL_V 이고 |wz| > SPIN_W 인 시간 / 전체
    stop_ratio   |vx| < STILL_V 이고 |wz| < STOP_W 인 시간과 cmd_vel 이
                 GAP_SEC 넘게 끊긴 시간 / 전체
    flip_near_node, flip_mid  부호 바뀜 위치가 가장 가까운 노드에서
                 NEAR_NODE_M 안인지 밖인지
    amcl_jump    amcl_pose 연속 두 값의 차이가 JUMP_M 또는 JUMP_RAD 를
                 넘은 횟수(토픽이 있을 때)
    plan_shift   같은 구간 안 연속한 plan 사이 가로 방향 최대 차이(cm)의
                 중앙값(토픽이 있을 때)
    route_retry  ROUTE_RETRY 이벤트 수
"""
import argparse
import bisect
import csv
import json
import math
import os
import statistics

from rclpy.serialization import deserialize_message
import rosbag2_py
from rosidl_runtime_py.utilities import get_message

FLIP_MIN_W = 0.1
STILL_V = 0.005
SPIN_W = 0.3
STOP_W = 0.05
GAP_SEC = 0.5
NEAR_NODE_M = 0.05
JUMP_M = 0.03
JUMP_RAD = 0.1
MAP_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..',
                        'src', 'frybot', 'frybot_control', 'frybot_control',
                        'maps')


def _yaw(q) -> float:
    """사원수의 yaw(rad)."""
    return math.atan2(2 * (q.w * q.z + q.x * q.y),
                      1 - 2 * (q.y * q.y + q.z * q.z))


def read_bag(path: str, robots: list[str]) -> dict:
    """Bag 에서 필요한 토픽을 시각(초)과 함께 읽는다.

    Args:
        path: bag 폴더.
        robots: 로봇 이름 목록.

    Returns:
        {'cmd': {rid: [(t, vx, wz)]}, 'amcl': {rid: [(t, x, y, yaw)]},
         'plan': {rid: [(t, [(x, y), ...])]}, 'status': {rid: [(t, x, y)]},
         'topics': 실제로 있던 토픽 이름 목록}
    """
    out = {k: {r: [] for r in robots} for k in ('cmd', 'amcl', 'plan',
                                                  'status')}
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=path, storage_id=''),
                rosbag2_py.ConverterOptions('', ''))
    types = {t.name: t.type for t in reader.get_all_topics_and_types()}
    out['topics'] = sorted(types)
    classes = {name: get_message(kind) for name, kind in types.items()}
    while reader.has_next():
        topic, data, stamp = reader.read_next()
        t = stamp / 1e9
        msg = deserialize_message(data, classes[topic])
        if topic == '/fleet/robot_status':
            if msg.robot_id in out['status']:
                out['status'][msg.robot_id].append((t, msg.x, msg.y))
            continue
        rid = topic.split('/')[1]
        if rid not in robots:
            continue
        if topic.endswith('/cmd_vel'):
            out['cmd'][rid].append((t, msg.linear.x, msg.angular.z))
        elif topic.endswith('/amcl_pose'):
            p = msg.pose.pose
            out['amcl'][rid].append((t, p.position.x, p.position.y,
                                     _yaw(p.orientation)))
        elif topic.endswith('/plan'):
            out['plan'][rid].append(
                (t, [(ps.pose.position.x, ps.pose.position.y)
                     for ps in msg.poses]))
    return out


def read_events(run_dir: str) -> list[dict]:
    """events.csv 를 읽는다(시각은 float)."""
    with open(os.path.join(run_dir, 'events.csv'), newline='') as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r['t'] = float(r['timestamp'])
    return sorted(rows, key=lambda r: r['t'])


def moves(events: list[dict]) -> list[dict]:
    """이동 명령(MOVE 임무)마다 로봇·목적지·시작·끝 시각을 모은다."""
    out, open_ = [], {}
    for e in events:
        tid = e['task_id']
        if e['event'] == 'TASK_ASSIGN' and tid.startswith('M'):
            open_[tid] = dict(task=tid, robot=e['robot_id'], t0=e['t'],
                              dest='', t1=None, result='')
        elif tid in open_:
            m = open_[tid]
            if e['event'] in ('PLAN', 'REPLAN') and not m['dest']:
                m['dest'] = e['zone_id']
            if e['event'] in ('TASK_DONE', 'TASK_CANCEL', 'TASK_SUSPEND',
                              'TASK_FAIL'):
                m['t1'], m['result'] = e['t'], e['event']
                out.append(open_.pop(tid))
    return out


def _slice(rows: list, t0: float, t1: float) -> list:
    """시각 순 목록에서 [t0, t1] 안의 것."""
    ts = [r[0] for r in rows]
    return rows[bisect.bisect_left(ts, t0):bisect.bisect_right(ts, t1)]


def _pos_at(status: list, t: float):
    """시각 t 에 가장 가까운 상태 보고 위치."""
    if not status:
        return None
    ts = [s[0] for s in status]
    i = min(bisect.bisect_left(ts, t), len(status) - 1)
    if i and abs(ts[i - 1] - t) < abs(ts[i] - t):
        i -= 1
    return status[i][1], status[i][2]


def _shift(a: list, b: list) -> float:
    """경로 b 의 점이 경로 a 에서 떨어진 최대 거리(m)."""
    if not a or not b:
        return float('nan')
    return max(min(math.dist(p, q) for q in a[::2] or a) for p in b[::2])


def metrics(m: dict, ev: list[dict], bag: dict | None, nodes: list) -> dict:
    """이동 명령 하나의 지표를 계산한다.

    Args:
        m: moves() 의 한 항목.
        ev: 전체 이벤트.
        bag: read_bag() 결과(없으면 None).
        nodes: 지도 노드 좌표 목록.

    Returns:
        지표 dict. 계산하지 못한 값은 None.
    """
    rid, t0, t1 = m['robot'], m['t0'], m['t1']
    mine = [e for e in ev if t0 <= e['t'] <= t1 and e['robot_id'] == rid]
    enters = [e['t'] for e in mine if e['event'] == 'ZONE_ENTER']
    seg_t = [b - a for a, b in zip([t0] + enters, enters, strict=False)]
    row = dict(robot=rid, task=m['task'], dest=m['dest'],
               result=m['result'], time_s=round(t1 - t0, 1),
               seg_n=len(enters),
               seg_time_med=(round(statistics.median(seg_t), 2)
                             if seg_t else None),
               route_retry=sum(e['event'] == 'ROUTE_RETRY' for e in mine),
               dist_m=None, flip_per_m=None, spin_ratio=None, stop_ratio=None,
               flip_near_node=None, flip_mid=None, amcl_jump=None,
               plan_shift=None)
    if bag is None:
        return row
    status = _slice(bag['status'][rid], t0, t1)
    if len(status) > 1:
        pairs = zip(status, status[1:], strict=False)
        row['dist_m'] = round(sum(math.dist(a[1:], b[1:])
                                  for a, b in pairs), 3)
    cmd = _slice(bag['cmd'][rid], t0, t1)
    if cmd:
        flips, last, near, mid = 0, 0, 0, 0
        spin = stop = 0.0
        edges = [t0] + [c[0] for c in cmd] + [t1]
        stop += max(0.0, cmd[0][0] - t0 - GAP_SEC)
        for i, (t, vx, wz) in enumerate(cmd):
            dt = edges[i + 2] - t
            held = min(dt, GAP_SEC)
            stop += dt - held
            if abs(vx) < STILL_V and abs(wz) > SPIN_W:
                spin += held
            elif abs(vx) < STILL_V and abs(wz) < STOP_W:
                stop += held
            sign = 0 if abs(wz) < FLIP_MIN_W else (1 if wz > 0 else -1)
            if sign and last and sign != last:
                flips += 1
                pos = _pos_at(status, t)
                if pos is not None and nodes:
                    d = min(math.dist(pos, n) for n in nodes)
                    near, mid = (near + 1, mid) if d < NEAR_NODE_M else (
                        near, mid + 1)
            if sign:
                last = sign
        total = max(t1 - t0, 1e-6)
        row.update(spin_ratio=round(spin / total, 3),
                   stop_ratio=round(stop / total, 3),
                   flip_near_node=near, flip_mid=mid)
        if row['dist_m']:
            row['flip_per_m'] = round(flips / row['dist_m'], 2)
    amcl = _slice(bag['amcl'][rid], t0, t1)
    if amcl:
        row['amcl_jump'] = sum(
            math.dist(a[1:3], b[1:3]) > JUMP_M
            or abs(math.remainder(b[3] - a[3], 2 * math.pi)) > JUMP_RAD
            for a, b in zip(amcl, amcl[1:], strict=False))
    plans = _slice(bag['plan'][rid], t0, t1)
    if len(plans) > 1:
        cuts = [t0] + enters + [t1]
        shifts = []
        for a, b in zip(plans, plans[1:], strict=False):
            if bisect.bisect(cuts, a[0]) == bisect.bisect(cuts, b[0]):
                s = _shift(a[1], b[1])
                if s == s:
                    shifts.append(s)
        if shifts:
            row['plan_shift'] = round(statistics.median(shifts) * 100, 1)
    return row


def main() -> None:
    """명령행 진입점."""
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument('run_dir')
    ap.add_argument('--bag', default='')
    ap.add_argument('--map-id', default='')
    ap.add_argument('--csv', default='')
    a = ap.parse_args()
    with open(os.path.join(a.run_dir, 'manifest.json')) as f:
        manifest = json.load(f)
    map_id = a.map_id or manifest.get('map_version', '')
    with open(os.path.join(MAP_ROOT, map_id, 'roadmap.json')) as f:
        nodes = [tuple(p) for p in json.load(f)['nodes'].values()]
    ev = read_events(a.run_dir)
    bag_dir = a.bag or os.path.join(a.run_dir, 'bag')
    bag = read_bag(bag_dir, list(manifest['robots'])) if os.path.isdir(
        bag_dir) else None
    if bag is not None:
        print('bag topics:', ', '.join(bag['topics']))
    else:
        print(f'bag 없음({bag_dir}): 이벤트 지표만 냄')
    rows = [metrics(m, ev, bag, nodes) for m in moves(ev)]
    cols = list(rows[0]) if rows else []
    print('\t'.join(cols))
    for r in rows:
        print('\t'.join('-' if r[c] is None else str(r[c]) for c in cols))
    if a.csv and rows:
        with open(a.csv, 'w', newline='') as f:
            w = csv.DictWriter(f, cols)
            w.writeheader()
            w.writerows(rows)


if __name__ == '__main__':
    main()
