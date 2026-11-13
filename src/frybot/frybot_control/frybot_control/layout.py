"""FryBot store layout (single source of truth for map, roadmap and named places).

Source: "FryBot 매장 맵 구성도 · 상세 치수" (200 x 100 cm, origin top-left, y down, unit cm).
ROS map frame: metres, x right, y up  ->  x = x_cm/100, y = (100 - y_cm)/100.
"""
import math

W_CM, H_CM, WALL_CM = 200, 100, 4
ROBOT_W, ROBOT_L = 0.11, 0.12
SAFE_DIST = 0.155          # min centre distance between two AMRs (m): 12 cm body + margin


def m(x_cm, y_cm):
    return (x_cm / 100.0, (H_CM - y_cm) / 100.0)


# name: (x0, y0, x1, y1) in cm
ZONES = {
    'charge':        (0, 0, 12, 100),
    'charge_aisle':  (12, 0, 32, 100),
    'upper_aisle':   (32, 12, 166, 36),
    'lower_aisle':   (32, 64, 166, 88),
    'link_aisle':    (88, 36, 114, 64),
    'cook_zone':     (166, 0, 200, 100),
    'fry_pickup':    (166, 12, 200, 36),
    'wok_pickup':    (166, 64, 200, 88),
    'wall':          (200, 0, 204, 100),
    'entrance':      (12, -2, 32, 0),
}
# From the route sheet: lay-bys between the wall-side tables and standby spots next to the cook zone (cm)
BAYS = {'BAY_U': (72, 1, 116, 11), 'BAY_L': (72, 89, 116, 99)}
STANDBY = {'STANDBY_U': (150, 1, 164, 11), 'STANDBY_L': (150, 89, 164, 99)}
BAY_NODES = {'BAY_U1': (86, 6), 'BAY_U2': (101, 6), 'BAY_L1': (86, 94), 'BAY_L2': (101, 94)}
STANDBY_NODES = {'STANDBY_U': (157, 6), 'STANDBY_L': (157, 94)}
CHARGERS = {'CH1': (0, 13, 12, 27), 'CH2': (0, 43, 12, 57), 'CH3': (0, 73, 12, 87)}
# Home spot of AMR number i (0-based): the chargers first, then waiting spots without a charger. The fleet size is
# a launch argument (robots:=N); to go beyond this list, add a charger / spot here (keep them SAFE_DIST apart).
# The charger zone only fits three chargers 15.5 cm apart, so AMR 4.. wait in the lay-bys and charge at a free charger.
HOME_SPOTS = ['CH1', 'CH2', 'CH3', 'BAY_U1', 'BAY_L1', 'BAY_U2', 'BAY_L2']
MAX_ROBOTS = len(HOME_SPOTS)


def robot_ids(n):
    """['pinky1', ..., 'pinkyN'] - the one place the AMR naming lives."""
    n = int(n)
    if not 1 <= n <= MAX_ROBOTS:
        raise ValueError(f'robots must be 1..{MAX_ROBOTS} (add home spots to layout.HOME_SPOTS for more)')
    return [f'pinky{i + 1}' for i in range(n)]


def robot_index(rid):
    """0-based number of an AMR from its id ('pinky4' -> 3)."""
    digits = ''.join(c for c in rid if c.isdigit())
    return int(digits) - 1 if digits else 0

# table id: seats, seat zone (no-go for robots), table rect, chair rects (cm), and the roadmap nodes used for it:
#   guide = where the AMR stops when it brings guests to the table, serve = where it serves and collects dishes.
# A table can have several of each (one per side); the Task Manager picks the quickest one for the robot.
# The two 4-seat tables in the middle are turned 90 deg clockwise from the dimension sheet (long side along y, chairs
# on the left and right) and are reached from the upper and the lower aisle. Points picked by the team on the map.
TABLES = {
    1: dict(seats=2, zone=(40, 0, 68, 12), table=(47, 0, 61, 12), chairs=[(40, 0, 47, 12), (61, 0, 68, 12)],
            guide=[(54, 24)], serve=[(54, 24)]),
    2: dict(seats=2, zone=(120, 0, 148, 12), table=(127, 0, 141, 12), chairs=[(120, 0, 127, 12), (141, 0, 148, 12)],
            guide=[(134, 24)], serve=[(134, 24)]),
    3: dict(seats=4, zone=(61, 37, 89, 63), table=(68, 37, 82, 63),
            chairs=[(61, 37, 68, 50), (61, 50, 68, 63), (82, 37, 89, 50), (82, 50, 89, 63)],
            guide=[(86, 24), (86, 76)], serve=[(70, 76), (70, 24)]),
    4: dict(seats=4, zone=(113, 37, 141, 63), table=(120, 37, 134, 63),
            chairs=[(113, 37, 120, 50), (113, 50, 120, 63), (134, 37, 141, 50), (134, 50, 141, 63)],
            guide=[(134, 24), (134, 76)], serve=[(118, 24), (118, 76)]),
    5: dict(seats=2, zone=(40, 88, 68, 100), table=(47, 88, 61, 100), chairs=[(40, 88, 47, 100), (61, 88, 68, 100)],
            guide=[(54, 76)], serve=[(54, 76)]),
    6: dict(seats=2, zone=(120, 88, 148, 100), table=(127, 88, 141, 100), chairs=[(120, 88, 127, 100), (141, 88, 148, 100)],
            guide=[(134, 76)], serve=[(134, 76)]),
}

MENU = {
    'FRIED':      dict(name='후라이드치킨', pickup='FRY_PICKUP'),
    'SEASONED':   dict(name='양념치킨', pickup='WOK_PICKUP'),
    'FRIED_RICE': dict(name='볶음밥', pickup='WOK_PICKUP'),
}

# Cooking arms stand outside the wall (the counter is outside the map)
COOK_ARMS = {'cook_arm_a': dict(pos_cm=(214, 24), label='튀김 로봇팔 A'),
             'cook_arm_b': dict(pos_cm=(214, 76), label='웍 로봇팔 B')}
ENTRANCE_DOOR_CM = (22, -6)       # where a guest group waits
DISH_RETURN_CM = (183, 50)        # 퇴식구: not on the dimension sheet -> assumed in the middle of the cook zone


def _nid(x, y):
    return f'N{x}_{y}'


def build_roadmap():
    """Single-lane roadmap along aisle centre lines. Returns (nodes{id:(x_m,y_m)}, edges[(a,b)], alias{name:id})."""
    pts, edges = set(), set()

    def line(points):
        for p in points:
            pts.add(p)
        for a, b in zip(points, points[1:]):
            edges.add((a, b))

    xs = [22, 38, 54, 70, 86, 101, 118, 134, 150, 166, 183]
    line([(x, 24) for x in xs])                                   # upper aisle
    line([(x, 76) for x in xs])                                   # lower aisle
    line([(22, y) for y in (8, 24, 37, 50, 63, 76, 92)])          # charger-front aisle
    line([(38, y) for y in (24, 37, 50, 63, 76)])                 # gap left of table 3
    line([(22, 50), (38, 50), (50, 50)])                          # spur left of table 3
    line([(38, 37), (50, 37), (54, 24)])                          # team-added shortcuts left of table 3 ...
    line([(50, 37), (50, 50), (52, 62), (54, 76)])
    line([(38, 63), (52, 62)])                                    # ... linking both aisles past the spur
    line([(101, y) for y in (24, 37, 50, 63, 76)])                # link aisle
    line([(150, y) for y in (24, 37, 50, 63, 76)])                # gap right of table 4
    line([(150, 50), (166, 50), (183, 50)])
    line([(183, y) for y in (8, 24, 37, 50, 63, 76, 92)])         # cook zone
    line([(86, 24), (86, 6), (101, 6), (101, 24)])                # upper lay-by (비켜 서는 곳)
    line([(86, 76), (86, 94), (101, 94), (101, 76)])              # lower lay-by
    line([(150, 24), (157, 6)])                                   # upper standby (대기)
    line([(150, 76), (157, 94)])                                  # lower standby
    line([(6, 20), (22, 24)])
    line([(6, 50), (22, 50)])
    line([(6, 80), (22, 76)])
    nodes = {_nid(x, y): m(x, y) for (x, y) in pts}
    e = [(_nid(*a), _nid(*b)) for a, b in sorted(edges)]
    alias = {'CH1': _nid(6, 20), 'CH2': _nid(6, 50), 'CH3': _nid(6, 80), 'ENTRANCE': _nid(22, 8),
             'FRY_PICKUP': _nid(183, 24), 'WOK_PICKUP': _nid(183, 76), 'DISH_RETURN': _nid(*DISH_RETURN_CM)}
    for tid, t in TABLES.items():
        alias[f'T{tid}'] = alias[f'T{tid}:serve'] = _nid(*t['serve'][0])
        alias[f'T{tid}:guide'] = _nid(*t['guide'][0])
    for k, v in {**BAY_NODES, **STANDBY_NODES}.items():
        alias[k] = _nid(*v)
    return nodes, e, alias


class Graph:
    def __init__(self):
        self.nodes, edge_list, self.alias = build_roadmap()
        self.adj = {n: [] for n in self.nodes}
        for a, b in edge_list:
            d = math.dist(self.nodes[a], self.nodes[b])
            self.adj[a].append((b, d))
            self.adj[b].append((a, d))
        self.edges = edge_list
        # robots are bigger than the node spacing in places: nodes closer than this cannot be occupied together
        self.conflict = {n: {k for k in self.nodes if k != n and math.dist(self.nodes[n], self.nodes[k]) < SAFE_DIST}
                         for n in self.nodes}
        # 'T3:guide' / 'T3:serve' -> nodes usable for that table (the middle 4-seat tables have two of each)
        self.table_nodes = {f'T{tid}:{kind}': [_nid(*p) for p in t[kind]]
                            for tid, t in TABLES.items() for kind in ('guide', 'serve')}
        self.bay_nodes = {self.alias[k] for k in BAY_NODES}
        self.standby_nodes = [self.alias[k] for k in STANDBY_NODES]
        self.home_nodes = {self.alias[k] for k in CHARGERS}
        self._sp = {}

    def home_of(self, rid):
        """Home node of an AMR (its charger, or a waiting spot for AMRs beyond the number of chargers)."""
        i = robot_index(rid)
        if not 0 <= i < len(HOME_SPOTS):
            raise ValueError(f'no home spot for {rid}: add one to layout.HOME_SPOTS')
        return self.alias[HOME_SPOTS[i]]

    def resolve(self, name):
        return self.alias.get(name, name)

    def pos(self, n):
        return self.nodes[self.resolve(n)]

    def dist(self, a, b):
        return math.dist(self.nodes[a], self.nodes[b])

    def sp_from(self, src):
        """Static shortest-path distances from src to every node (Dijkstra, cached)."""
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
        return self.sp_from(self.resolve(b)).get(self.resolve(a), 1e9)

    def nearest_node(self, x, y):
        return min(self.nodes, key=lambda n: math.dist(self.nodes[n], (x, y)))


def obstacle_rects_cm():
    """Rectangles robots must not enter (seat zones + wall)."""
    r = [t['zone'] for t in TABLES.values()]
    r.append(ZONES['wall'])
    return r


def to_json():
    g = Graph()
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
