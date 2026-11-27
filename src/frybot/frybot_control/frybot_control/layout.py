"""FryBot store layout (single source of truth for the virtual store (proto)).

Map, roadmap and named places of the proto store.

실측 지도(test_map_*)의 그래프·stations·docks 는 maps/<map_id>/roadmap.json 이
원본이고, 이 파일은 가상 매장(proto)만 맡음.

Source: "FryBot 매장 맵 구성도" and the route sheets on Confluence (System Architecture, 2026-11-13):
200 x 100 cm, origin top-left, y down, unit cm.
ROS map frame: metres, x right, y up  ->  x = x_cm/100, y = (100 - y_cm)/100.
"""
import math

from .map_catalog import PROTO_MAP_ID, active_map_id, profile

# 바닥 가로·세로와 조리 구역 쪽 벽 두께(cm)
W_CM, H_CM, WALL_CM = 200, 100, 4
SAFE_DIST = 0.155          # min centre distance between two AMRs (m): 12 cm body + margin


def m(x_cm, y_cm):
    """도면 좌표(cm, 왼쪽 위 원점, y 아래)를 지도 좌표(m, y 위)로 바꾼다.

    Args:
        x_cm: 도면 x(cm).
        y_cm: 도면 y(cm).

    Returns:
        (x, y) 미터.
    """
    return (x_cm / 100.0, (H_CM - y_cm) / 100.0)


# name: (x0, y0, x1, y1) in cm
ZONES = {
    'charge':        (0, 0, 12, 100),
    'charge_aisle':  (12, 0, 32, 100),
    'upper_aisle':   (32, 12, 166, 44),      # 32 cm wide (map sheet 2026-11-13)
    'lower_aisle':   (32, 56, 166, 88),
    'link_aisle':    (88, 44, 114, 56),      # 26 x 12 between the two 4-seat tables
    'cook_zone':     (166, 0, 200, 100),
    'fry_pickup':    (166, 12, 200, 44),
    'wok_pickup':    (166, 56, 200, 88),
    'wall':          (200, 0, 204, 100),
    'entrance':      (12, -2, 32, 0),
}
# From the route sheet: lay-bys between the wall-side tables and standby spots next to the cook zone (cm)
BAYS = {'BAY_U': (72, 1, 116, 11), 'BAY_L': (72, 89, 116, 99)}
STANDBY = {'STANDBY_U': (150, 1, 164, 11), 'STANDBY_L': (150, 89, 164, 99)}
# 비켜 서는 곳·대기 위치에 두는 로드맵 노드(cm), 충전대 사각형(cm)
BAY_NODES = {'BAY_U1': (88, 6), 'BAY_U2': (114, 6), 'BAY_L1': (88, 94), 'BAY_L2': (114, 94)}
STANDBY_NODES = {'STANDBY_U': (157, 6), 'STANDBY_L': (157, 94)}
CHARGERS = {'CH1': (0, 13, 12, 27), 'CH2': (0, 43, 12, 57), 'CH3': (0, 73, 12, 87)}
# Home spot of AMR number i (0-based): the chargers first, then waiting spots without a charger. The fleet size is
# a launch argument (robots:=N); to go beyond this list, add a charger / spot here (keep them SAFE_DIST apart).
# The charger zone only fits three chargers 15.5 cm apart, so AMR 4.. wait in the lay-bys and charge at a free charger.
HOME_SPOTS = ['CH1', 'CH2', 'CH3', 'BAY_U1', 'BAY_L1', 'BAY_U2', 'BAY_L2']
MAX_ROBOTS = len(HOME_SPOTS)  # 가상 매장에서 띄울 수 있는 AMR 최대 대수


def robot_ids(n):
    """['pinky1', ..., 'pinkyN'] - the one place the AMR naming lives.

    Args:
        n: AMR 대수(문자열도 받음, 런치 인자 robots:=N).

    Returns:
        로봇 이름 목록.

    Raises:
        ValueError: n 이 1..MAX_ROBOTS 밖일 때.
    """
    n = int(n)
    if not 1 <= n <= MAX_ROBOTS:
        raise ValueError(f'robots must be 1..{MAX_ROBOTS} (add home spots to layout.HOME_SPOTS for more)')
    return [f'pinky{i + 1}' for i in range(n)]


def robot_index(rid):
    """0-based number of an AMR from its id ('pinky4' -> 3).

    이름에 숫자가 없으면 0 을 돌려준다.
    """
    digits = ''.join(c for c in rid if c.isdigit())
    return int(digits) - 1 if digits else 0

# table id: seats, seat zone (no-go for robots), table rect, chair rects (cm), and the roadmap nodes used for it:
#   guide = where the AMR stops when it brings guests to the table, serve = where it serves and collects dishes.
# Map sheet of 2026-11-13 (Confluence, System Architecture): every table is 12 x 12, the numbers count from the cook
# zone (1 top right, 2 bottom right, 3 middle right, 4 middle left, 5 top left, 6 bottom left), and the AMR stops at
# one spot in front of the table for guiding, serving and collecting alike; the 4-seat tables in the middle have such
# a spot on the upper and on the lower aisle, and the Task Manager picks the quicker one.
# The sheet gives no dimensions for the table x positions and the stop spots: they are read off the drawing, and the
# stops are STOP_GAP away from the seat zone: at 8 cm the nose of the 12 cm robot came within 2 cm of the table and
# Nav2's collision check refused every approach (the AMR node then drove the segment blind), so they sit at 11 cm.
AISLE_U, AISLE_L = 28, 72          # centre lines of the two 32 cm aisles
STOP_GAP = 11
GAP_R = 153                        # column right of table 3: 12 cm clear of its seat zone (150 was refused by Nav2)


# 벽 쪽 2인석. x: 테이블 가운데 x(cm), top: 위쪽 벽이면 True.
# 오른쪽(x > 100) 테이블의 정지 지점은 3 cm 왼쪽(x=131, 3번과 같은 열)
def _wall_table(x, top):
    y0, y1 = (0, 12) if top else (88, 100)
    stop = (x - 3 if x > 100 else x, 12 + STOP_GAP if top else 88 - STOP_GAP)
    return dict(seats=2, zone=(x - 12, y0, x + 12, y1), table=(x - 6, y0, x + 6, y1),
                chairs=[(x - 12, y0, x - 6, y1), (x + 6, y0, x + 12, y1)], guide=[stop], serve=[stop])


# 가운데 4인석. x: 테이블 가운데 x(cm), sx: 정지 지점 x(cm).
# 위·아래 통로 쪽에 정지 지점이 하나씩 있음
def _mid_table(x, sx):
    stops = [(sx, 44 - STOP_GAP), (sx, 56 + STOP_GAP)]
    return dict(seats=4, zone=(x - 13, 44, x + 13, 56), table=(x - 6, 44, x + 6, 56),
                chairs=[(x - 13, 44, x - 6, 50), (x - 13, 50, x - 6, 56), (x + 6, 44, x + 13, 50), (x + 6, 50, x + 13, 56)],
                guide=stops, serve=stops)


# 테이블 번호 -> 정보(위 설명의 번호 순서)
TABLES = {
    1: _wall_table(134, True),
    2: _wall_table(134, False),
    3: _mid_table(128, 131),
    4: _mid_table(74, 74),
    5: _wall_table(54, True),
    6: _wall_table(54, False),
}

# 메뉴 코드 -> 화면 이름, 음식을 받으러 갈 곳(alias 이름)
MENU = {
    'FRIED':      dict(name='후라이드치킨', pickup='FRY_PICKUP'),
    'SEASONED':   dict(name='양념치킨', pickup='WOK_PICKUP'),
    'FRIED_RICE': dict(name='볶음밥', pickup='WOK_PICKUP'),
}

# Cooking arms stand outside the wall (the counter is outside the map)
COOK_ARMS = {'cook_arm_a': dict(pos_cm=(214, AISLE_U), label='튀김 로봇팔 A'),
             'cook_arm_b': dict(pos_cm=(214, AISLE_L), label='웍 로봇팔 B')}
ENTRANCE_DOOR_CM = (22, 6)        # where a guest group waits (just inside the entrance)
GREET_CM = (22, 20)               # 손님 응대 위치: where the AMR meets the group
DISH_RETURN_CM = (183, 50)        # 퇴식구: not on the dimension sheet -> assumed in the middle of the cook zone


# ---- precise docking (Nav2 docking server, see frybot_mobile/config/nav2_store.yaml)
# The AMR docks at the chargers, the two pick-up spots and the dish return on an ArUco marker fixed to the wall it
# faces there, and at the table stops on its map pose (no marker at the tables). A dock is entered from the roadmap
# node just before it; `yaw` is the heading the robot must have when it stands on the dock.
ARUCO_DICT = 'DICT_4X4_50'  # OpenCV ArUco 사전(gz_world_gen 이 마커 그림에 씀)
MARKER_SIZE = 0.04                 # side of the black square (m)
MARKER_Z = 0.05                    # height of the marker centre above the floor: the Pinky camera sits at 6.3 cm and
#                                    looks 8 deg down, so the marker stays in view until the robot stops
LEFT_WALL_X, COOK_WALL_X = -0.06, 2.00       # inner faces of the wall behind the chargers / in front of the counter (m)
# place: (marker id, face of the wall the marker is on)
DOCK_MARKERS = {'CH1': (1, 'left'), 'CH2': (2, 'left'), 'CH3': (3, 'left'),
                'FRY_PICKUP': (11, 'cook'), 'WOK_PICKUP': (12, 'cook'), 'DISH_RETURN': (13, 'cook')}


# 도면 좌표(cm)로 만든 노드 이름(예: N22_28)
def _nid(x, y):
    return f'N{x}_{y}'


def docks():
    """node id -> dict(name, kind 'marker'|'pose', x, y, yaw [, marker id, marker (x, y, facing yaw)]) in the map frame.
    'facing yaw' is the direction the marker looks (out of the wall).

    실측 지도면 map_docks() 결과를, 가상 매장이면 충전대·음식 받는 곳·
    퇴식구(마커 도크)와 테이블 정지 지점(pose 도크)을 돌려준다.
    """
    # [수정 2026-11-20] 실측 지도는 roadmap.json 의 docks 를 읽음(예전에는
    # 항상 빈 값). 서빙 팔 시험에서 음식 받는 곳에 정밀 정차하기 위함
    if active_map_id():
        return map_docks(active_map_id())
    nodes, _, alias = build_roadmap()
    out = {}
    for name, (mid, wall) in DOCK_MARKERS.items():
        x, y = nodes[alias[name]]
        # 왼쪽 벽: 로봇은 벽(-x, pi)을 향하고 마커는 +x(0)를 봄.
        # 조리 쪽 벽은 반대
        yaw, wx, face = (math.pi, LEFT_WALL_X, 0.0) if wall == 'left' else (0.0, COOK_WALL_X, math.pi)
        out[alias[name]] = dict(name=name, kind='marker', x=x, y=y, yaw=yaw, marker_id=mid, marker=(wx, y, face))
    for tid, t in TABLES.items():
        for (sx, sy) in t['serve']:                 # stop spot: 5 cm off the aisle, facing the table
            x, y = m(sx, sy)
            # 테이블을 바라보는 방향: 위쪽 2인석과 4인석의 아래 통로 쪽
            # 정지 지점은 +y(pi/2), 나머지는 -y
            out[_nid(sx, sy)] = dict(name=f'T{tid}', kind='pose', x=x, y=y,
                                     yaw=math.pi / 2 if sy < 50 and t['seats'] == 2 or sy > 50 and t['seats'] == 4
                                     else -math.pi / 2)
    return out


# [수정 2026-11-20] 신규: 실측 지도의 도크(roadmap.json 의 docks)
def map_docks(map_id: str) -> dict:
    """실측 지도의 도크를 docks() 와 같은 형식으로 돌려준다.

    roadmap.json 의 docks 는 {노드: {yaw_deg, marker_id, marker}} 이다.
    yaw_deg 는 도크에 섰을 때 로봇이 향하는 방향(도). marker_id 와
    marker([x, y, 마커가 바라보는 방향(도)])가 있으면 ArUco 마커 도크,
    없으면 지도 좌표만으로 서는 도크(kind 'pose')이다.

    Args:
        map_id: 실측 지도 이름.

    Returns:
        노드 이름 -> dict(name, kind, x, y, yaw[, marker_id, marker]).

    Raises:
        ValueError: 도크의 노드가 지도에 없거나 marker_id 만 있고 marker
            위치가 없을 때.
    """
    data = profile(map_id)
    out = {}
    for node, spec in (data.get('docks') or {}).items():
        if node not in data['nodes']:
            raise ValueError(f'{map_id}: docks 의 {node} 는 없는 노드입니다')
        x, y = data['nodes'][node]
        dock = dict(name=node, kind='pose', x=x, y=y,
                    yaw=math.radians(float(spec.get('yaw_deg', 0.0))))
        if spec.get('marker_id') is not None:
            if not spec.get('marker'):
                raise ValueError(
                    f'{map_id}: docks 의 {node} 에 marker 위치가 없습니다')
            mx, my, face = spec['marker']
            dock.update(kind='marker', marker_id=int(spec['marker_id']),
                        marker=(mx, my, math.radians(face)))
        out[node] = dock
    return out


def build_roadmap():
    """Single-lane roadmap along aisle centre lines. Returns (nodes{id:(x_m,y_m)}, edges[(a,b)], alias{name:id})."""
    pts, edges = set(), set()

    # 점들을 차례로 이어 노드와 통로(간선)를 더함(중복은 set 이 걸러 냄)
    def line(points):
        for p in points:
            pts.add(p)
        for a, b in zip(points, points[1:]):
            edges.add((a, b))

    U, L = AISLE_U, AISLE_L
    # 위·아래 통로의 노드 x(cm): 충전대 앞 통로, 세로 통로, 테이블 정지 지점
    # 열, 비켜 서는 곳 입구, 조리 구역
    xs = [22, 38, 54, 74, 88, 101, 114, 131, GAP_R, 166, 183]
    line([(x, U) for x in xs])                                    # upper aisle
    line([(x, L) for x in xs])                                    # lower aisle
    line([(22, y) for y in (20, U, 50, L, 80, 92)])               # charger-front aisle (greeting spot at the top)
    for x in (38, 101, GAP_R):                                      # left gap, link aisle, right gap
        line([(x, U), (x, 50), (x, L)])
    line([(22, 50), (38, 50)])
    line([(GAP_R, 50), (166, 50), (183, 50)])
    line([(183, y) for y in (8, U, 50, L, 92)])                   # cook zone
    line([(88, U), (88, 6), (114, 6), (114, U)])                  # upper lay-by (비켜 서는 곳)
    line([(88, L), (88, 94), (114, 94), (114, L)])                # lower lay-by
    line([(GAP_R, U), (157, 6)])                                    # upper standby (대기)
    line([(GAP_R, L), (157, 94)])                                   # lower standby
    for t in TABLES.values():                                     # stop spot in front of each table, off the aisle
        for (x, y) in t['serve']:
            line([(x, U if y < 50 else L), (x, y)])
    # 충전대 노드(CH1~CH3)를 충전대 앞 통로에 이음
    line([(6, 20), (22, 20)])
    line([(6, 50), (22, 50)])
    line([(6, 80), (22, 80)])
    nodes = {_nid(x, y): m(x, y) for (x, y) in pts}
    e = [(_nid(*a), _nid(*b)) for a, b in sorted(edges)]
    # 이름 -> 노드: 충전대, 손님 응대 위치(ENTRANCE), 음식 받는 곳, 퇴식구,
    # 테이블(T1, T1:serve, T1:guide), 비켜 서는 곳·대기 위치
    alias = {'CH1': _nid(6, 20), 'CH2': _nid(6, 50), 'CH3': _nid(6, 80), 'ENTRANCE': _nid(*GREET_CM),
             'FRY_PICKUP': _nid(183, AISLE_U), 'WOK_PICKUP': _nid(183, AISLE_L), 'DISH_RETURN': _nid(*DISH_RETURN_CM)}
    for tid, t in TABLES.items():
        alias[f'T{tid}'] = alias[f'T{tid}:serve'] = _nid(*t['serve'][0])
        alias[f'T{tid}:guide'] = _nid(*t['guide'][0])
    for k, v in {**BAY_NODES, **STANDBY_NODES}.items():
        alias[k] = _nid(*v)
    return nodes, e, alias


class Graph:
    """관제와 로봇이 함께 쓰는 로드맵 그래프(노드·통로·이름).

    실측 지도는 roadmap.json 에서, 가상 매장(proto)은 build_roadmap() 에서
    만든다. 주요 속성: nodes(노드 -> (x, y) m), adj(이웃과 거리),
    edges, alias(지점 이름 -> 노드), conflict(SAFE_DIST 안의 노드),
    table_nodes, standby_nodes, bay_nodes, home_nodes(충전대).

    Args:
        map_id: 지도 이름. None 이면 FRYBOT_MAP_ID, '' 나 'proto' 면 가상
            매장.

    Raises:
        ValueError: roadmap.json 의 stations 가 없는 노드를 가리킬 때.
    """

    def __init__(self, map_id=None):
        self.map_id = active_map_id() if map_id is None else map_id
        # [수정 2026-11-17] 'proto' 는 가상 매장 도면: 아래 build_roadmap() 사용
        if self.map_id == PROTO_MAP_ID:
            self.map_id = ''
        if self.map_id:
            data = profile(self.map_id)
            self.nodes = {key: tuple(point) for key, point in data['nodes'].items()}
            edge_list = [tuple(edge) for edge in data['edges']]
            self.alias = {}
        else:
            self.nodes, edge_list, self.alias = build_roadmap()
        # 양방향 이웃 목록: 노드 -> [(이웃, 거리 m)]
        self.adj = {n: [] for n in self.nodes}
        for a, b in edge_list:
            d = math.dist(self.nodes[a], self.nodes[b])
            self.adj[a].append((b, d))
            self.adj[b].append((a, d))
        self.edges = edge_list
        # robots are bigger than the node spacing in places: nodes closer than this cannot be occupied together
        self.conflict = {n: {k for k in self.nodes if k != n and math.dist(self.nodes[n], self.nodes[k]) < SAFE_DIST}
                         for n in self.nodes}
        self._sp = {}  # sp_from() 의 결과 캐시: 출발 노드 -> 거리표
        if self.map_id:
            # [수정 2026-11-20] 실측 지도의 매장 지점(roadmap.json 의
            # stations)을 읽음. 없는 지도는 예전처럼 빈 값
            self.table_nodes = {}
            stations = data.get('stations') or {}
            self.alias = dict(stations.get('places') or {})
            for tid, stops in (stations.get('tables') or {}).items():
                for kind in ('guide', 'serve'):
                    self.table_nodes[f'T{tid}:{kind}'] = list(stops)
                    self.alias[f'T{tid}:{kind}'] = stops[0]
                self.alias[f'T{tid}'] = stops[0]
            unknown = sorted(n for n in set(self.alias.values()).union(
                *self.table_nodes.values()) if n not in self.nodes)
            if unknown:
                raise ValueError(
                    f'{self.map_id}: stations 의 {unknown} 는 없는 노드입니다')
            # 실측 지도: 대기 위치(waiting)를 비켜 서는 곳으로도 씀. 충전대는
            # 없음(빈 집합)
            self.standby_nodes = list(data.get('waiting', ()))
            self.bay_nodes = set(self.standby_nodes)
            self.home_nodes = set()
            return
        # 'T3:guide' / 'T3:serve' -> nodes usable for that table (the middle 4-seat tables have two of each)
        self.table_nodes = {f'T{tid}:{kind}': [_nid(*p) for p in t[kind]]
                            for tid, t in TABLES.items() for kind in ('guide', 'serve')}
        # 가상 매장: 비켜 서는 곳, 조리 쪽 대기 위치, 충전대 노드
        self.bay_nodes = {self.alias[k] for k in BAY_NODES}
        self.standby_nodes = [self.alias[k] for k in STANDBY_NODES]
        self.home_nodes = {self.alias[k] for k in CHARGERS}

    def home_of(self, rid):
        """Home node of an AMR (its charger, or a waiting spot for AMRs beyond the number of chargers).

        실측 지도는 roadmap.json 의 homes 를 로봇 번호 순서로 쓴다.

        Args:
            rid: 로봇 이름(pinkyN).

        Returns:
            출발 노드 이름.

        Raises:
            ValueError: 그 번호의 출발 노드가 없을 때.
        """
        i = robot_index(rid)
        if self.map_id:
            homes = profile(self.map_id)['homes']
            if not 0 <= i < len(homes):
                raise ValueError(f'No start vertex for {rid} on {self.map_id}')
            return homes[i]
        if not 0 <= i < len(HOME_SPOTS):
            raise ValueError(f'no home spot for {rid}: add one to layout.HOME_SPOTS')
        return self.alias[HOME_SPOTS[i]]

    def resolve(self, name):
        """지점 이름(alias)을 노드 이름으로 바꾼다. 노드 이름은 그대로 둔다."""
        return self.alias.get(name, name)

    def pos(self, n):
        """지점 이름이나 노드의 지도 좌표 (x, y) m 를 돌려준다."""
        return self.nodes[self.resolve(n)]

    def dist(self, a, b):
        """두 노드 사이의 직선 거리(m)."""
        return math.dist(self.nodes[a], self.nodes[b])

    def sp_from(self, src):
        """Static shortest-path distances from src to every node (Dijkstra, cached).

        다른 로봇의 예약은 보지 않는 통로 길이만의 거리이다. 닿지 않는
        노드는 결과에 없다.
        """
        if src in self._sp:
            return self._sp[src]
        import heapq
        dist = {src: 0.0}
        pq = [(0.0, src)]
        while pq:
            d, u = heapq.heappop(pq)
            if d > dist.get(u, 1e18):
                continue
            for v, w in self.adj[u]:
                nd = d + w
                if nd < dist.get(v, 1e18):
                    dist[v] = nd
                    heapq.heappush(pq, (nd, v))
        self._sp[src] = dist
        return dist

    def shortest_dist(self, a, b):
        """통로를 따라 a 에서 b 까지 가는 최단 거리(m). 길이 없으면 1e9.

        통로가 양방향이라 b 에서 출발한 거리표(캐시)를 쓴다. a, b 에는
        지점 이름도 쓸 수 있다.
        """
        return self.sp_from(self.resolve(b)).get(self.resolve(a), 1e9)

    def nearest_node(self, x, y):
        """지도 좌표 (x, y) m 에서 직선으로 가장 가까운 노드."""
        return min(self.nodes, key=lambda n: math.dist(self.nodes[n], (x, y)))


def obstacle_rects_cm():
    """Rectangles robots must not enter (seat zones + wall)."""
    r = [t['zone'] for t in TABLES.values()]
    r.append(ZONES['wall'])
    return r


def to_json():
    """가상 매장 도면을 화면·시뮬용 JSON dict 로 돌려준다.

    web_service(/api/layout), 매장 시뮬(world_node), Gazebo 월드 생성
    (gz_world_gen)이 쓴다. 좌표는 지도 좌표(m, y 위)이다.

    Returns:
        구역·충전대·테이블·메뉴·노드·통로·조리 팔 위치 등을 담은 dict.
    """
    g = Graph(map_id='')
    rect = lambda r: [r[0] / 100, (H_CM - r[3]) / 100, r[2] / 100, (H_CM - r[1]) / 100]  # x0,y0,x1,y1 metres (y up)
    return {
        'width': W_CM / 100, 'height': H_CM / 100,
        'zones': {k: rect(v) for k, v in ZONES.items()},
        'chargers': {k: rect(v) for k, v in CHARGERS.items()},
        'bays': {k: rect(v) for k, v in BAYS.items()}, 'standby': {k: rect(v) for k, v in STANDBY.items()},
        'tables': {str(k): {'seats': t['seats'], 'zone': rect(t['zone']), 'table': rect(t['table']),
                            'chairs': [rect(c) for c in t['chairs']], 'service': list(m(*t['serve'][0])),
                            'guide': [list(m(*p)) for p in t['guide']], 'serve': [list(m(*p)) for p in t['serve']]}
                   for k, t in TABLES.items()},
        'menu': MENU,
        'nodes': {k: list(v) for k, v in g.nodes.items()}, 'edges': g.edges, 'alias': g.alias,
        'cook_arms': {k: {'pos': list(m(*v['pos_cm'])), 'label': v['label']} for k, v in COOK_ARMS.items()},
        'max_robots': MAX_ROBOTS,
        'door': list(m(*ENTRANCE_DOOR_CM)), 'dish_return': list(m(*DISH_RETURN_CM)),
    }
