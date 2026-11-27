"""Store world simulation: occupancy map, RViz markers, guests, ceiling camera (chair QR) streamer."""
# 가상 매장 시뮬 노드: 점유 격자(/map), RViz 마커, 손님 움직임, 천장
# 카메라(의자 QR) 대역. 가상 매장(proto) 시뮬에서만 뜬다.
import json
import math
import time

import rclpy
from geometry_msgs.msg import Point
from nav_msgs.msg import OccupancyGrid
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy
from std_msgs.msg import String
from visualization_msgs.msg import Marker, MarkerArray

from frybot_control import layout as L
from frybot_interfaces.msg import RobotStatus

from frybot_mobile.arm_common import CameraStreamer

# RViz 마커 색 (r, g, b, a)
COL = {'table': (0.55, 0.38, 0.28, 1.0), 'chair': (0.95, 0.95, 0.95, 1.0), 'chair_used': (0.45, 0.45, 0.5, 1.0),
       'charge': (0.75, 0.85, 1.0, 0.6), 'cook': (1.0, 0.9, 0.8, 0.6), 'wall': (0.15, 0.15, 0.15, 1.0),
       'counter': (0.85, 0.85, 0.85, 1.0), 'node': (0.3, 0.5, 0.9, 0.7)}
# 손님 무리(방문)별 색. visit_id 로 돌려 씀
GUEST_COL = [(0.9, 0.3, 0.3), (0.2, 0.6, 0.9), (0.3, 0.75, 0.4), (0.9, 0.6, 0.1), (0.6, 0.4, 0.9), (0.2, 0.75, 0.75)]
# 로봇별 이름표·경로 색
ROBOT_COL = {'pinky1': (0.1, 0.7, 0.3), 'pinky2': (0.9, 0.5, 0.1), 'pinky3': (0.6, 0.3, 0.9), 'pinky4': (0.0, 0.5, 0.8),
             'pinky5': (0.85, 0.15, 0.5), 'pinky6': (0.8, 0.55, 0.0), 'pinky7': (0.05, 0.6, 0.55)}


from frybot_control.store_map import build_grid  # noqa: E402  (1 cm occupancy grid of the store)


class World(Node):
    """가상 매장의 손님·의자·지도·마커를 시뮬레이션하는 노드."""
    def __init__(self):
        super().__init__('world')
        p = self.declare_parameter
        self.guest_speed = p('guest_speed', 0.07).value  # 손님 속도(m/s)
        self.lay = L.to_json()  # 가상 매장 도면 JSON
        self.graph = L.Graph()  # 로드맵(노드 위치 조회용)
        # /map·고정 마커용 래치 QoS(늦게 붙은 RViz 도 받음)
        latched = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL, reliability=ReliabilityPolicy.RELIABLE)
        # 지도, 고정 마커, 움직이는 마커, 손님·의자 상태(/sim/world_state)
        self.pub_map = self.create_publisher(OccupancyGrid, '/map', latched)
        self.pub_static = self.create_publisher(MarkerArray, '/frybot/markers_static', latched)
        self.pub_mk = self.create_publisher(MarkerArray, '/frybot/markers', 10)
        self.pub_world = self.create_publisher(String, '/sim/world_state', 10)
        # 식당·관제 상태, 손님 시뮬레이터 명령, 로봇 상태(위치) 구독
        # [수정 2026-11-25] I/F 정의서 v0.2 이름: /frybot/state ->
        # /frybot/central/view_state
        # [수정 2026-11-26] I/F v0.3 최종 판 이름:
        # /frybot/central/view_state -> /frybot/state
        self.create_subscription(
            String, '/frybot/state',
            lambda m: self._json('rest', m), 10)
        self.create_subscription(String, '/fms/state', lambda m: self._json('fms', m), 10)
        self.create_subscription(String, '/sim/customer_cmd', self._cmd, 20)
        self.create_subscription(RobotStatus, '/fleet/robot_status', self._robot, 50)
        self.state = {'rest': {}, 'fms': {}}  # 받은 상태 JSON
        self.robots, self.guests = {}, {}      # guests: visit_id -> dict(x, y, straggle, gone, phase)
        # 천장 카메라 대역: 의자 QR 프레임을 AI 서버(UDP)로 보냄
        self.cam = CameraStreamer('ceiling', port=p('ai_udp_port', 9100).value)
        self._publish_map()
        self.pub_static.publish(self._static_markers())
        self.create_timer(0.1, self._step)  # 손님 이동·상태 발행
        self.create_timer(0.2, self._markers)  # 움직이는 마커
        self.create_timer(1.0, self._ceiling)  # 천장 카메라 프레임
        self._last = time.time()  # _step 의 dt 계산용

    # 상태 토픽 JSON 을 self.state[key] 에 넣음. 깨진 JSON 은 버림
    def _json(self, key, m):
        try:
            self.state[key] = json.loads(m.data)
        except ValueError:
            pass

    # 로봇별 마지막 RobotStatus(안내 중 손님이 따라갈 위치)
    def _robot(self, m):
        self.robots[m.robot_id] = m

    # 손님 시뮬레이터 명령: straggle(멈춰 서기 켜기/끄기), walkout(나가기)
    def _cmd(self, m):
        try:
            d = json.loads(m.data)
        except ValueError:
            return
        g = self.guests.get(int(d.get('visit_id', 0)))
        if not g:
            return
        if d.get('cmd') == 'straggle':
            g['straggle'] = bool(d.get('on', True))
        elif d.get('cmd') == 'walkout':
            g['gone'] = True

    # ------------------------------------------------------------ guests
    # 0.1초마다 방문 상태에 따라 손님을 움직이고 /sim/world_state 발행.
    # ASSIGNED 는 입구, GUIDING 은 15 cm 넘게 떨어지면 로봇 쪽으로,
    # SEATED 는 테이블 가운데로(걸어 나간 손님은 GONE 으로 멈춤)
    def _step(self):
        now = time.time()
        dt, self._last = now - self._last, now
        door = self.lay['door']
        live = set()
        for v in self.state['rest'].get('visits', []):
            vid, st = v['id'], v['state']
            if st in ('REJECTED', 'LEFT', 'CANCELED'):  # 끝난 방문
                continue
            live.add(vid)
            g = self.guests.setdefault(vid, dict(x=door[0] + 0.03 * ((vid % 3) - 1), y=door[1] + 0.05, straggle=False,
                                                 gone=False, phase='DOOR', party=v['party'], table=v['table']))
            tgt = None
            if st == 'ASSIGNED':
                tgt, g['phase'] = (door[0], door[1]), 'DOOR'
            elif st in ('GUIDING', 'GUIDE_FAILED'):
                g['phase'] = 'FOLLOW'
                r = self.robots.get(v.get('robot', ''))
                if r and not g['straggle']:
                    d = math.hypot(r.x - g['x'], r.y - g['y'])
                    if d > 0.15:
                        tgt = (r.x, r.y)
            elif st == 'SEATED':
                g['phase'] = 'GONE' if g['gone'] else 'SEATED'
                z = self.lay['tables'][str(v['table'])]['table']
                tgt = ((z[0] + z[2]) / 2, (z[1] + z[3]) / 2)
            if tgt and g['phase'] != 'GONE':
                dx, dy = tgt[0] - g['x'], tgt[1] - g['y']
                d = math.hypot(dx, dy)
                # 착석하러 갈 때는 1.6배 빠르게
                step = self.guest_speed * dt * (1.6 if g['phase'] == 'SEATED' else 1.0)
                if d > step:
                    g['x'] += dx / d * step
                    g['y'] += dy / d * step
                elif g['phase'] != 'FOLLOW':  # 가까우면 목표에 바로 맞춤
                    g['x'], g['y'] = tgt
        # 끝난 방문의 손님은 지움
        for vid in list(self.guests):
            if vid not in live:
                del self.guests[vid]
        self.pub_world.publish(String(data=json.dumps({
            'guests': {str(k): dict(x=g['x'], y=g['y'], phase=g['phase'], straggle=g['straggle'], party=g['party'],
                                    table=g['table']) for k, g in self.guests.items()},
            'chairs': self._chairs()})))

    def _chairs(self):
        """table id -> number of chairs whose QR is visible (a seated guest covers the QR)."""
        out = {}
        for tid, t in self.lay['tables'].items():
            used = 0
            for g in self.guests.values():
                if g['table'] == int(tid) and g['phase'] == 'SEATED':
                    z = t['table']
                    if math.hypot(g['x'] - (z[0] + z[2]) / 2, g['y'] - (z[1] + z[3]) / 2) < 0.03:
                        used = min(t['seats'], g['party'])
            out[tid] = t['seats'] - used
        return out

    # 천장 카메라 프레임: 테이블마다 좌석 수와 보이는 QR 수
    def _ceiling(self):
        ch = self._chairs()
        self.cam.send('ceiling', tables=[dict(table_id=int(t), seats=v['seats'], qr_visible=ch[t])
                                         for t, v in self.lay['tables'].items()])

    # ------------------------------------------------------------ map + markers
    # 1 cm 점유 격자를 /map 으로 한 번 발행(래치)
    def _publish_map(self):
        w, h, data, ox, oy = build_grid()
        m = OccupancyGrid()
        m.header.frame_id = 'map'
        m.header.stamp = self.get_clock().now().to_msg()
        m.info.resolution, m.info.width, m.info.height = 0.01, w, h
        m.info.origin.position.x, m.info.origin.position.y = ox, oy
        m.info.origin.orientation.w = 1.0
        m.data = data
        self.pub_map.publish(m)

    # Marker 하나를 만듦. 크기 (sx, sy, sz), 색 c 는 (r, g, b[, a])
    def _mk(self, ns, i, typ, x, y, z, sx, sy, sz, c, text=''):
        m = Marker()
        m.header.frame_id, m.ns, m.id, m.type, m.action = 'map', ns, i, typ, Marker.ADD
        m.pose.position.x, m.pose.position.y, m.pose.position.z = float(x), float(y), float(z)
        m.pose.orientation.w = 1.0
        m.scale.x, m.scale.y, m.scale.z = float(sx), float(sy), float(sz)
        m.color.r, m.color.g, m.color.b = [float(v) for v in c[:3]]
        m.color.a = float(c[3]) if len(c) > 3 else 1.0
        m.text = text
        return m

    # 바닥 사각형 r=[x0, y0, x1, y1] 위, 높이 z0 부터 h 만큼의 상자 마커
    def _box(self, ns, i, r, z0, h, c):
        return self._mk(ns, i, Marker.CUBE, (r[0] + r[2]) / 2, (r[1] + r[3]) / 2, z0 + h / 2, r[2] - r[0], r[3] - r[1], h, c)

    # 고정 마커: 구역, 벽, 카운터, 비켜 서는 곳, 대기, 충전대, 테이블,
    # 이름표, 로드맵. label ns 의 id 는 테이블 번호, 충전대 100번대,
    # 입구·퇴식구 200번대, 조리 팔 210번대, 비켜 서는 곳 300번대, 대기 310번대
    def _static_markers(self):
        a, lay = MarkerArray(), self.lay
        a.markers.append(self._box('zone', 0, lay['zones']['charge'], 0.0, 0.001, COL['charge']))
        a.markers.append(self._box('zone', 1, lay['zones']['cook_zone'], 0.0, 0.001, COL['cook']))
        a.markers.append(self._box('wall', 0, lay['zones']['wall'], 0.0, 0.12, COL['wall']))
        a.markers.append(self._box('counter', 0, [2.045, 0.08, 2.11, 0.92], 0.0, 0.10, COL['counter']))
        for i, (k, r) in enumerate(lay['bays'].items()):
            a.markers.append(self._box('bay', i, r, 0.0, 0.002, (0.6, 0.85, 0.6, 0.7)))
            a.markers.append(self._mk('label', 300 + i, Marker.TEXT_VIEW_FACING, (r[0] + r[2]) / 2, (r[1] + r[3]) / 2, 0.03,
                                      0, 0, 0.03, (0.1, 0.45, 0.15), '비켜 서는 곳'))
        for i, (k, r) in enumerate(lay['standby'].items()):
            a.markers.append(self._box('standby', i, r, 0.0, 0.002, (0.45, 0.8, 0.5, 0.8)))
            a.markers.append(self._mk('label', 310 + i, Marker.TEXT_VIEW_FACING, (r[0] + r[2]) / 2, (r[1] + r[3]) / 2, 0.03,
                                      0, 0, 0.03, (0.1, 0.45, 0.15), '대기'))
        for i, (k, r) in enumerate(lay['chargers'].items()):
            a.markers.append(self._box('charger', i, r, 0.001, 0.002, (0.2, 0.45, 0.9, 0.9)))
            a.markers.append(self._mk('label', 100 + i, Marker.TEXT_VIEW_FACING, (r[0] + r[2]) / 2, (r[1] + r[3]) / 2, 0.02,
                                      0, 0, 0.03, (0.1, 0.2, 0.6), k))
        for tid, t in lay['tables'].items():
            i = int(tid)
            a.markers.append(self._box('table', i, t['table'], 0.0, 0.07, COL['table']))
            a.markers.append(self._mk('label', i, Marker.TEXT_VIEW_FACING, (t['table'][0] + t['table'][2]) / 2,
                                      (t['table'][1] + t['table'][3]) / 2, 0.11, 0, 0, 0.04, (1, 1, 1), f'T{tid}'))
        for i, (name, key) in enumerate((('입구', 'door'), ('퇴식구', 'dish_return'))):
            x, y = lay[key]
            a.markers.append(self._mk('label', 200 + i, Marker.TEXT_VIEW_FACING, x, y, 0.16, 0, 0, 0.035, (0.4, 0.2, 0.8), name))
        for i, (k, v) in enumerate(lay['cook_arms'].items()):
            a.markers.append(self._mk('label', 210 + i, Marker.TEXT_VIEW_FACING, v['pos'][0] + 0.12, v['pos'][1], 0.3, 0, 0,
                                      0.035, (0.8, 0.3, 0.1), v['label']))
        ln = self._mk('roadmap', 0, Marker.LINE_LIST, 0, 0, 0.002, 0.004, 0, 0, COL['node'])
        for e0, e1 in lay['edges']:
            for n in (e0, e1):
                ln.points.append(Point(x=lay['nodes'][n][0], y=lay['nodes'][n][1], z=0.0))
        a.markers.append(ln)
        pts = self._mk('roadmap', 1, Marker.SPHERE_LIST, 0, 0, 0.002, 0.012, 0.012, 0.004, COL['node'])
        pts.points = [Point(x=v[0], y=v[1], z=0.0) for v in lay['nodes'].values()]
        a.markers.append(pts)
        return a

    # 0.2초마다 움직이는 마커(전부 지우고 다시 그림): 의자 빈/사용,
    # 테이블 상태, 손님, 접시, 로봇 이름·경로, 조리 팔 작업, 알고리즘 이름
    def _markers(self):
        a = MarkerArray()
        a.markers.append(Marker(action=Marker.DELETEALL))
        lay, rest, fms = self.lay, self.state['rest'], self.state['fms']
        chairs = self._chairs()
        tstate = {str(t['id']): t['state'] for t in rest.get('tables', [])}
        k = 0
        for tid, t in lay['tables'].items():
            free = chairs[tid]
            for j, c in enumerate(t['chairs']):
                a.markers.append(self._box('chair', int(tid) * 10 + j, c, 0.0, 0.04,
                                           COL['chair'] if j < free else COL['chair_used']))
            st = tstate.get(tid, '')
            col = {'AVAILABLE': (0.2, 0.7, 0.3), 'ASSIGNED': (0.9, 0.7, 0.1), 'IN_USE': (0.2, 0.5, 0.9),
                   'VACANT_CHECK': (0.9, 0.5, 0.1), 'COLLECTING': (0.8, 0.3, 0.3)}.get(st, (0.5, 0.5, 0.5))
            a.markers.append(self._mk('tstate', int(tid), Marker.TEXT_VIEW_FACING, (t['zone'][0] + t['zone'][2]) / 2,
                                      (t['zone'][1] + t['zone'][3]) / 2, 0.16, 0, 0, 0.028, col, st))
        for vid, g in self.guests.items():
            if g['phase'] == 'GONE':
                continue
            c = GUEST_COL[vid % len(GUEST_COL)]
            for j in range(g['party']):
                ox, oy = 0.035 * (j % 2) - 0.017, 0.035 * (j // 2) - 0.017
                a.markers.append(self._mk('guest', vid * 10 + j, Marker.CYLINDER, g['x'] + ox, g['y'] + oy,
                                          0.14 if g['phase'] == 'SEATED' else 0.05, 0.03, 0.03, 0.10, c))
            a.markers.append(self._mk('guest_label', vid, Marker.TEXT_VIEW_FACING, g['x'], g['y'], 0.24, 0, 0, 0.03, c,
                                      f"손님{vid} ({g['party']}명)" + (' 멈춤' if g['straggle'] else '')))
        # dishes: on hand-off counters, on robots, on tables
        slots = fms.get('cooking', {}).get('slots', {})
        for name, n in slots.items():
            x, y = self.graph.pos(name)
            for j in range(n):
                a.markers.append(self._mk('dish', 500 + k, Marker.CYLINDER, 1.96, y - 0.05 + 0.05 * j, 0.02, 0.035, 0.035, 0.012, (1.0, 0.75, 0.2)))
                k += 1
        # 전달된 음식은 회수 로봇이 실을 때까지 테이블 위에 그림
        for o in rest.get('orders', []):
            n = sum(1 for it in o['items'] if it['state'] == 'DELIVERED')
            if n and tstate.get(str(o['table'])) in ('IN_USE', 'VACANT_CHECK', 'COLLECTING') and \
                    not any(r['task_type'] == 'COLLECT' and r['carrying'] and
                            any(t['id'] == r['task'] and t['table'] == o['table'] for t in fms.get('tasks', []))
                            for r in fms.get('robots', [])):
                z = lay['tables'][str(o['table'])]['table']
                for j in range(n):
                    a.markers.append(self._mk('dish', 500 + k, Marker.CYLINDER, z[0] + 0.03 + 0.04 * (j % 5), (z[1] + z[3]) / 2,
                                              0.076, 0.035, 0.035, 0.012, (1.0, 0.75, 0.2)))
                    k += 1
        # 로봇 이름·상태·임무, 실은 음식, 남은 경로
        for r in fms.get('robots', []):
            c = ROBOT_COL.get(r['id'], (0.5, 0.5, 0.5))
            a.markers.append(self._mk('rlabel', int(r['id'][-1]), Marker.TEXT_VIEW_FACING, r['x'], r['y'], 0.22, 0, 0, 0.028, c,
                                      f"{r['id']} {r['state']}" + (f" [{r['task']}]" if r['task'] else '')))
            if r.get('carrying'):
                a.markers.append(self._mk('dish', 500 + k, Marker.CYLINDER, r['x'], r['y'], 0.125, 0.035, 0.035, 0.012, (1.0, 0.75, 0.2)))
                k += 1
            if r.get('route'):
                ln = self._mk('route', int(r['id'][-1]), Marker.LINE_STRIP, 0, 0, 0.004, 0.008, 0, 0, c + (0.9,))
                ln.points = [Point(x=r['x'], y=r['y'], z=0.0)] + [Point(x=self.lay['nodes'][n][0], y=self.lay['nodes'][n][1], z=0.0)
                                                                  for n in r['route'][1:] or r['route']]
                a.markers.append(ln)
        # 조리 팔이 맡은 작업(메뉴 · 단계)
        res = fms.get('cooking', {}).get('resources', {})
        jobs = {j['task']: j for j in fms.get('cooking', {}).get('jobs', [])}
        for i, (arm, key) in enumerate((('cook_arm_a', 'ARM_A'), ('cook_arm_b', 'ARM_B'))):
            j = jobs.get(res.get(key) or '')
            x, y = lay['cook_arms'][arm]['pos']
            a.markers.append(self._mk('cook', i, Marker.TEXT_VIEW_FACING, x + 0.12, y, 0.36, 0, 0, 0.028, (0.2, 0.2, 0.2),
                                      f"{j['menu']} · {j['step']}" if j else 'IDLE'))
        # 위쪽에 쓰는 스케줄러·플래너 이름
        alg = fms.get('algorithms', {})
        a.markers.append(self._mk('hud', 0, Marker.TEXT_VIEW_FACING, 1.0, 1.13, 0.05, 0, 0, 0.04, (0.1, 0.1, 0.1),
                                  f"scheduler={alg.get('scheduler', '?')}  planner={alg.get('planner', '?')}"))
        self.pub_mk.publish(a)


def main():
    """매장 시뮬(world) 노드를 띄우고 Ctrl+C 까지 돈다."""
    rclpy.init()
    try:
        rclpy.spin(World())
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
