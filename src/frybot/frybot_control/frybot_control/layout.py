"""FryBot store layout (single source of truth for map, roadmap and named places).

Source: "FryBot 매장 맵 구성도" and the route sheets on Confluence (System Architecture, 2026-11-13):
200 x 100 cm, origin top-left, y down, unit cm.
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
BAY_NODES = {'BAY_U1': (88, 6), 'BAY_U2': (114, 6), 'BAY_L1': (88, 94), 'BAY_L2': (114, 94)}
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


def _wall_table(x, top):
    y0, y1 = (0, 12) if top else (88, 100)
    stop = (x - 3 if x > 100 else x, 12 + STOP_GAP if top else 88 - STOP_GAP)
    return dict(seats=2, zone=(x - 12, y0, x + 12, y1), table=(x - 6, y0, x + 6, y1),
                chairs=[(x - 12, y0, x - 6, y1), (x + 6, y0, x + 12, y1)], guide=[stop], serve=[stop])


def _mid_table(x, sx):
    stops = [(sx, 44 - STOP_GAP), (sx, 56 + STOP_GAP)]
    return dict(seats=4, zone=(x - 13, 44, x + 13, 56), table=(x - 6, 44, x + 6, 56),
                chairs=[(x - 13, 44, x - 6, 50), (x - 13, 50, x - 6, 56), (x + 6, 44, x + 13, 50), (x + 6, 50, x + 13, 56)],
                guide=stops, serve=stops)


TABLES = {
    1: _wall_table(134, True),
    2: _wall_table(134, False),
    3: _mid_table(128, 131),
    4: _mid_table(74, 74),
    5: _wall_table(54, True),
    6: _wall_table(54, False),
}

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

    U, L = AISLE_U, AISLE_L
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
    line([(6, 20), (22, 20)])
    line([(6, 50), (22, 50)])
    line([(6, 80), (22, 80)])
    nodes = {_nid(x, y): m(x, y) for (x, y) in pts}
    e = [(_nid(*a), _nid(*b)) for a, b in sorted(edges)]
    alias = {'CH1': _nid(6, 20), 'CH2': _nid(6, 50), 'CH3': _nid(6, 80), 'ENTRANCE': _nid(*GREET_CM),
             'FRY_PICKUP': _nid(183, AISLE_U), 'WOK_PICKUP': _nid(183, AISLE_L), 'DISH_RETURN': _nid(*DISH_RETURN_CM)}
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
