"""실기기 실행 로그의 이동 명령을 모의 로봇으로 다시 실행해 실제와 비교함.

관제 코어(FleetCore)는 실기기와 같은 코드를 쓰고, 로봇만 모의로 바꿈.
ROS 없이 실행됨. 지도는 실행 폴더의 manifest.json 에서 읽음.

    ros2 run frybot_control replay_run runs/run_20261116_175751
    ros2 run frybot_control replay_run runs/<run> --model measured -v
    ros2 run frybot_control replay_run --find-yield --map-id test_map_v001

모의 로봇의 시간 모델
    ideal     기존 시뮬과 같음: 구간 지연 없이 0.08 m/s
    measured  실제 로그의 구간 시간에 맞춘 값: 구간마다 지연 + 거리 / 속도
"""
# [수정 2026-11-17] T-23: 신규. 시뮬 결과가 실기기와 맞는지 확인하는 도구
import argparse
import collections
import csv
import itertools
import json
import os
import random
import statistics

# [수정 2026-11-18] W3: 모의 로봇은 mock_fleet 을 씀
from .mock_fleet import MockFleet
from .mock_fleet import TimeModel

# 실제·모의 비교표에 횟수를 함께 찍을 관제 이벤트
KEY_EVENTS = ('PLAN', 'REPLAN', 'ZONE_REQUEST', 'PLAN_WAIT', 'YIELD_WAIT',
              'YIELD_SKIP', 'RETREAT', 'ROUTE_RETRY', 'TASK_DONE')


# [수정 2026-11-18] W3: TimeModel·Bot 과 모의 로봇 이동 코드는 mock_fleet 으로
# 옮겨 삭제함(fleet_bench 와 같은 모의 로봇을 씀)
class ReplayWorld(MockFleet):
    """FleetCore 에 모의 로봇을 붙여 시간 순서대로 실행함."""

    def __init__(self, robot_ids: list[str], model: TimeModel,
                 dt: float = 0.1, **core_args) -> None:
        """모의 함대를 만든다(경로 번호는 0부터, 실기기 로그와 맞춤).

        Args:
            robot_ids: 로봇 이름 목록.
            model: 모의 로봇 시간 모델.
            dt: 한 단계의 시간(초).
            **core_args: FleetCore 에 넘길 인자.
        """
        super().__init__(robot_ids, model, dt, pv_base=0, **core_args)


def load_run(run_dir: str) -> tuple[dict, list[dict]]:
    """실행 폴더를 읽음.

    Args:
        run_dir: runs/<run_id> 폴더.

    Returns:
        (manifest, 이벤트 목록). 이벤트의 t 는 첫 줄 기준 초.
    """
    with open(os.path.join(run_dir, 'manifest.json')) as stream:
        manifest = json.load(stream)
    with open(os.path.join(run_dir, 'events.csv')) as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError(f'{run_dir}: events.csv 가 비어 있음')
    # 첫 줄 시각을 0 으로 맞춘 상대 시각(초)을 t 열로 붙임
    t0 = float(rows[0]['timestamp'])
    for row in rows:
        row['t'] = float(row['timestamp']) - t0
    return manifest, rows


def fit_segments(rows: list[dict], graph) -> tuple[float, float, int]:
    """허가부터 도착까지의 구간 시간을 '지연 + 거리 / 속도'로 맞춤.

    Args:
        rows: 실제 이벤트 목록.
        graph: 지도 그래프.

    Returns:
        (구간 지연 초, 속도 m/s, 쓴 구간 수).
    """
    # node: 로봇별 마지막 도착 노드, grant: 로봇별 마지막 허가 (시각, 노드),
    # seg: (구간 거리, 허가 -> 도착 시간). 허가받은 노드에 도착한 구간만 씀
    node, grant, seg = {}, {}, []
    for row in rows:
        rid, zone = row['robot_id'], row['zone_id']
        if row['event'] == 'ZONE_GRANT':
            grant[rid] = (row['t'], zone)
        elif row['event'] == 'ZONE_ENTER':
            if node.get(rid) and grant.get(rid, (0, ''))[1] == zone:
                dist = graph.dist(node[rid], zone)
                if dist > 0.02:  # 2 cm 이하(제자리) 구간은 뺌
                    seg.append((dist, row['t'] - grant[rid][0]))
            node[rid] = zone
    if len(seg) < 5:
        raise ValueError('구간 기록이 부족해 시간 모델을 맞출 수 없음')
    # 시간 = 절편 + 기울기 x 거리 의 최소제곱 직선. 절편이 구간 지연,
    # 기울기의 역수가 속도
    n = len(seg)
    sx, sy = sum(d for d, _ in seg), sum(t for _, t in seg)
    sxx, sxy = sum(d * d for d, _ in seg), sum(d * t for d, t in seg)
    slope = (n * sxy - sx * sy) / (n * sxx - sx * sx)
    return (sy - slope * sx) / n, 1.0 / slope, n


def commands_of(rows: list[dict]) -> list[tuple[float, str, str]]:
    """실제 로그의 이동 명령 (시각, 로봇, 목적지).

    central_control 의 ADMIN 로그는 zone_id 에 대상 로봇, reason 에 명령
    인자(목적지 노드)를 남김.

    Args:
        rows: 실제 이벤트 목록.

    Returns:
        MOVE_TO_VERTEX 명령의 (시각, 로봇, 목적지) 목록.
    """
    return [(r['t'], r['zone_id'], r['reason']) for r in rows
            if r['event'] == 'ADMIN' and r['result'] == 'MOVE_TO_VERTEX']


def start_of(rows: list[dict], graph, plan: dict, prefer: list[str]) -> str:
    """실제 계획 한 건이 어느 노드에서 출발했는지 추정함.

    로그에는 출발 노드가 없어, 경로 길이와 첫 허가 노드로 거꾸로 찾음.

    Args:
        rows: 실제 이벤트 목록.
        graph: 지도 그래프.
        plan: 실제 PLAN 이벤트.
        prefer: 후보가 여럿일 때 먼저 고를 노드(앞쪽이 우선).

    Returns:
        출발 노드. 알 수 없으면 ''.
    """
    rid = plan['robot_id']
    # PLAN 의 reason 'len=N' 은 경로의 노드 수
    length = int(plan['reason'].split('len=')[1].split()[0])
    first = next((r['zone_id'] for r in rows if r['t'] >= plan['t']
                  and r['event'] == 'ZONE_GRANT'
                  and r['robot_id'] == rid), None)
    if first is None:
        return ''
    # 첫 허가 노드의 이웃 중, 거기서 목적지까지의 최단 경로가 같은 길이이고
    # 두 번째 노드가 첫 허가 노드인 것이 출발 후보
    cands = []
    for near, _ in graph.adj[first]:
        path = shortest_path(graph, near, plan['zone_id'])
        if len(path) == length and path[1] == first:
            cands.append(near)
    cands.sort(key=lambda n: prefer.index(n) if n in prefer else len(prefer))
    return cands[0] if cands else ''


def shortest_path(graph, src: str, dst: str) -> list[str]:
    """빈 지도에서의 최단 경로 노드 목록.

    Args:
        graph: 지도 그래프.
        src: 출발 노드.
        dst: 목적지 노드.

    Returns:
        src 부터 dst 까지의 노드 목록. 닿지 못하면 노드 수만큼에서 멈춤.
    """
    dist = graph.sp_from(dst)
    path = [src]
    while path[-1] != dst and len(path) <= len(graph.nodes):
        path.append(min(graph.adj[path[-1]],
                        key=lambda e: e[1] + dist.get(e[0], 1e18))[0])
    return path


def tasks_of(events: list[dict], commands: list) -> list[dict | None]:
    """명령마다 그 임무의 경과를 뽑음(받아들여지지 않았으면 None).

    명령 1초 안의 같은 로봇·목적지 PLAN 을 그 명령의 임무로 봄.

    Args:
        events: 이벤트 목록(실제 로그 또는 모의 events).
        commands: commands_of 의 결과.

    Returns:
        명령별 dict(done: 끝남, dur: PLAN->TASK_DONE 초, route: 들어간
        노드 순서, count: 이벤트별 횟수) 또는 None.
    """
    out = []
    for when, rid, dest in commands:
        plan = next((e for e in events if e['event'] == 'PLAN'
                     and e['robot_id'] == rid and e['zone_id'] == dest
                     and abs(e['t'] - when) < 1.0), None)
        if plan is None:
            out.append(None)
            continue
        tid = plan['task_id']
        done = next((e for e in events if e['event'] == 'TASK_DONE'
                     and e['task_id'] == tid), None)
        end = done['t'] if done else float('inf')
        mine = [e for e in events if plan['t'] <= e['t'] <= end
                and e['robot_id'] == rid]
        out.append(dict(
            done=done is not None,
            dur=(end - plan['t']) if done else float('nan'),
            route=[e['zone_id'] for e in mine if e['event'] == 'ZONE_ENTER'],
            count=collections.Counter(e['event'] for e in mine)))
    return out


# [수정 2026-11-18] W6: 보정한 계획(core_args: plan_overhead 등)으로 재생
def replay(run_dir: str, model: TimeModel, verbose: bool,
           core_args: dict | None = None) -> None:
    """실제 로그의 명령을 모의 로봇으로 실행하고 비교표를 출력함.

    Args:
        run_dir: runs/<run_id> 폴더.
        model: 모의 로봇 시간 모델.
        verbose: 명령별 비교 줄도 출력할지.
        core_args: FleetCore 에 넘길 계획 인자(plan_overhead 등).
    """
    manifest, rows = load_run(run_dir)
    commands = commands_of(rows)
    world = ReplayWorld(list(manifest['robots']), model,
                        **(core_args or {}))
    graph = world.core.graph
    homes = [graph.home_of(rid) for rid in manifest['robots']]
    todo = list(commands)
    end = rows[-1]['t'] + 120.0  # 실제 로그 끝 + 120초까지만 돌림
    moved = 0  # 출발 노드를 실제에 맞춰 다시 놓은 횟수
    while world.t < end and (todo or not world.idle()):
        world.step()
        while todo and todo[0][0] <= world.t:
            when, rid, dest = todo.pop(0)
            robot = world.core.robots[rid]
            plan = next((r for r in rows if r['event'] == 'PLAN'
                         and r['robot_id'] == rid and r['zone_id'] == dest
                         and abs(r['t'] - when) < 1.0), None)
            if plan and not robot.route and robot.task is None:
                # 실험 중 손으로 옮긴 로봇: 실제 출발 노드에 다시 놓음
                node = start_of(rows, graph, plan, [robot.node] + homes)
                if node and node != robot.node:
                    world.place(rid, node)
                    moved += 1
            world.core.command('MOVE_TO_VERTEX', rid, dest)
    # 명령별 실제·모의 경과를 짝지어 비교
    real, sim = tasks_of(rows, commands), tasks_of(world.events, commands)
    print(f'\n== 모델 {model.name}: 구간 = {model.overhead:.2f}초 + 거리 / '
          f'{model.speed:.3f} m/s ==')
    if verbose:
        print(' 시각  로봇    목적지 | 실제 소요 재계획 대기 | 모의 소요 '
              '재계획 대기 | 경로')
    same = both = 0
    ratios = []
    for (when, rid, dest), a, b in zip(commands, real, sim, strict=True):
        if a is None or b is None:
            if verbose and (a is None) != (b is None):
                print(f'{when:6.0f} {rid:7} {dest:6} | 실제 '
                      f'{"거절" if a is None else "수락"}, 모의 '
                      f'{"거절" if b is None else "수락"}')
            continue
        both += 1
        same += a['route'] == b['route']
        # 실제 3초 이하 명령은 비율이 튀므로 뺌
        if a['done'] and b['done'] and a['dur'] > 3.0:
            ratios.append(b['dur'] / a['dur'])
        if verbose:
            ca, cb = a['count'], b['count']
            print(f'{when:6.0f} {rid:7} {dest:6} | {a["dur"]:8.1f} '
                  f'{ca["REPLAN"]:6} {ca["ZONE_REQUEST"]:4} | '
                  f'{b["dur"]:8.1f} {cb["REPLAN"]:6} '
                  f'{cb["ZONE_REQUEST"]:4} | '
                  f'{"같음" if a["route"] == b["route"] else "다름"}')
    print(f'명령 {len(commands)}건 중 양쪽 다 수락 {both}건, '
          f'경로 같음 {same}건 (출발 노드를 실제에 맞춘 횟수 {moved})')
    if ratios:
        print(f'소요 시간 모의/실제: 중앙값 {statistics.median(ratios):.2f} '
              f'(최소 {min(ratios):.2f}, 최대 {max(ratios):.2f})')
    count_real = collections.Counter(r['event'] for r in rows)
    count_sim = collections.Counter(e['event'] for e in world.events)
    print('이벤트        실제  모의')
    for name in KEY_EVENTS:
        print(f'{name:12} {count_real[name]:5} {count_sim[name]:5}')


def _outcome(events: list[dict]) -> str:
    """한 번의 모의 실행에서 관제가 어떤 판단을 했는지 한 단어로."""
    for ev in events:
        if ev['event'] == 'RETREAT':
            return ('비켜 주기' if 'idle_makes_way' in ev['reason']
                    else '비켜 서기')
        if ev['event'] == 'YIELD_WAIT':
            return '대기 양보'
    for ev in events:
        if ev['event'] == 'YIELD_SKIP':
            return '양보 안 함: ' + ev['reason'].split()[0]
    if any(ev['event'] == 'PLAN_WAIT' for ev in events):
        return '계획 대기만'
    return '겹침 없음'


def _trial(map_robots: list[str], model: TimeModel, places: dict,
           moves: list[tuple[str, str]]) -> tuple[str, list[dict]]:
    """정해 둔 자리에서 이동 명령을 넣고 300초까지 돌려 판단을 봄.

    Args:
        map_robots: 로봇 이름 목록.
        model: 모의 로봇 시간 모델.
        places: 로봇 -> 처음 놓을 노드.
        moves: (로봇, 목적지) 이동 명령 목록.

    Returns:
        (_outcome 의 한 단어 또는 '명령 거절', 모의 이벤트 목록).
    """
    world = ReplayWorld(map_robots, model, dt=0.2)
    for rid, node in places.items():
        world.place(rid, node)
    for _ in range(3):
        world.step()
    for rid, dest in moves:
        ok, _ = world.core.command('MOVE_TO_VERTEX', rid, dest)
        if not ok:
            return '명령 거절', world.events
    while world.t < 300.0 and not world.idle():
        world.step()
    return _outcome(world.events), world.events


def find_yield(model: TimeModel, limit: int, seed: int) -> None:
    """양보가 일어나는 명령 조합을 지도에서 찾아 종류별로 출력함.

    Args:
        model: 모의 로봇 시간 모델.
        limit: 종류마다 시험할 조합 수의 상한.
        seed: 조합을 고르는 난수 씨앗.
    """
    robots = ['pinky1', 'pinky2']
    graph = ReplayWorld(robots, model).core.graph
    # 이름에 '_' 가 없는 노드만 출발·목적지 후보
    major = sorted(n for n in graph.nodes if '_' not in n)
    rng = random.Random(seed)
    # idle: (출발, 목적지, 그 최단 경로 가운데에 서 있는 로봇의 노드)
    # moving: (출발1, 목적지1, 출발2, 목적지2) 최단 경로가 2노드 이상 겹침
    idle, moving = [], []
    for src, dst in itertools.permutations(major, 2):
        path = shortest_path(graph, src, dst)
        for node in path[1:-1]:
            near = {node} | graph.conflict[node]
            if src not in near and dst not in near:
                idle.append((src, dst, node))
    for src, dst in itertools.permutations(major, 2):
        path = set(shortest_path(graph, src, dst))
        for src2, dst2 in itertools.permutations(major, 2):
            if {src2, dst2} & {src, dst}:
                continue
            if graph.conflict[src] & {src2} or graph.conflict[dst] & {dst2}:
                continue
            if len(path & set(shortest_path(graph, src2, dst2))) >= 2:
                moving.append((src, dst, src2, dst2))
    for name, cases in (('서 있는 로봇이 길을 막음', idle),
                        ('두 로봇이 동시에 이동', moving)):
        rng.shuffle(cases)
        found = collections.defaultdict(list)  # 판단 -> 사례 목록
        for case in cases[:limit]:
            if len(case) == 3:
                places = {'pinky1': case[0], 'pinky2': case[2]}
                moves = [('pinky1', case[1])]
                text = f'pinky1 {case[0]}→{case[1]}, pinky2 {case[2]}에 정지'
            else:
                places = {'pinky1': case[0], 'pinky2': case[2]}
                moves = [('pinky1', case[1]), ('pinky2', case[3])]
                text = (f'pinky1 {case[0]}→{case[1]}, '
                        f'pinky2 {case[2]}→{case[3]}')
            outcome, events = _trial(robots, model, places, moves)
            pairs = [case[:2]] + ([case[2:]] if len(case) > 3 else [])
            length = sum(graph.shortest_dist(a, b) for a, b in pairs)
            kinds = (('YIELD_SKIP',) if outcome.startswith('양보 안 함')
                     else ('RETREAT', 'YIELD_WAIT'))
            note = next((f'{e["event"]} {e["robot_id"]} {e["zone_id"]} '
                         f'{e["reason"]}' for e in events
                         if e['event'] in kinds), '')
            found[outcome].append((length, text, note))
        total = sum(len(v) for v in found.values())
        print(f'\n== {name}: {total}건 시험 ==')
        ranked = sorted(found.items(), key=lambda kv: -len(kv[1]))
        for outcome, items in ranked:
            print(f'{outcome}: {len(items)}건 '
                  f'({100 * len(items) / total:.0f}%)')
            for _, text, note in sorted(items)[:3]:
                print(f'    {text}' + (f'  [{note}]' if note else ''))


def main() -> None:
    """명령행 진입점."""
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument('run_dir', nargs='?', help='runs/<run_id> 폴더')
    ap.add_argument('--model', default='both',
                    choices=('ideal', 'measured', 'both'))
    ap.add_argument('--overhead', type=float, help='구간 지연(초)')
    ap.add_argument('--speed', type=float, help='주행 속도(m/s)')
    ap.add_argument('--find-yield', action='store_true',
                    help='양보가 일어나는 명령 조합 찾기')
    ap.add_argument('--map-id', default='', help='--find-yield 의 지도')
    ap.add_argument('--limit', type=int, default=400)
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('-v', '--verbose', action='store_true')
    # [수정 2026-11-18] W6: 관제의 계획 시간 모델(보정한 계획으로 재생)
    ap.add_argument('--plan-overhead', type=float,
                    help='계획의 구간 지연(초), 기본 0')
    # [수정 2026-11-18] W10: --plan-speed 는 실기기 런치의 speed:= 와 같이
    # FleetCore 의 speed 로 넘김(계획 속도 = 값 x 배율). 배율 인자 추가
    ap.add_argument('--plan-speed', type=float,
                    help='관제 일반 속도(m/s), 기본 0.08')
    ap.add_argument('--plan-speed-factor', type=float,
                    help='계획 속도 배율, 기본 0.9')
    args = ap.parse_args()
    ideal = TimeModel('ideal', 0.08, 0.0)  # 경량 시뮬과 같은 모델
    if args.find_yield:
        os.environ['FRYBOT_MAP_ID'] = args.map_id
        model = ideal
        if args.overhead is not None or args.speed is not None:
            model = TimeModel('custom', args.speed or 0.08,
                              args.overhead or 0.0)
        find_yield(model, args.limit, args.seed)
        return
    if not args.run_dir:
        ap.error('실행 폴더가 필요함')
    manifest, rows = load_run(args.run_dir)
    # 가상 매장 실행은 map_version 이 'frybot_...' 이라 빈 값(proto)으로 둠
    map_id = manifest.get('map_version', '')
    os.environ['FRYBOT_MAP_ID'] = '' if map_id.startswith('frybot_') else map_id
    # 지역 import 인 이유는 확인 필요(Graph 는 만들 때 FRYBOT_MAP_ID 를 읽음)
    from .layout import Graph
    overhead, speed, n = fit_segments(rows, Graph())
    print(f'{args.run_dir}: 지도 {map_id}, 로봇 {manifest["robots"]}, '
          f'이동 명령 {len(commands_of(rows))}건')
    print(f'실제 구간 {n}개: 시간 = {overhead:.2f}초 + 거리 / {speed:.3f} m/s')
    # 로그에서 맞춘 값(인자로 주면 그 값)으로 measured 모델을 만듦
    measured = TimeModel('measured', args.speed or speed,
                         overhead if args.overhead is None else args.overhead)
    # 관제의 계획 인자(주지 않으면 FleetCore 기본값)
    core_args = {}
    if args.plan_speed:
        core_args['speed'] = args.plan_speed
    if args.plan_speed_factor is not None:
        core_args['plan_speed_factor'] = args.plan_speed_factor
    if args.plan_overhead:
        core_args['plan_overhead'] = args.plan_overhead
    if core_args:
        factor = (0.9 if args.plan_speed_factor is None
                  else args.plan_speed_factor)
        print(f'계획: 구간 지연 {args.plan_overhead or 0.0:g}초, 속도 '
              f'{(args.plan_speed or 0.08) * factor:g} m/s')
    for model in (ideal, measured):
        if args.model in ('both', model.name):
            replay(args.run_dir, model, args.verbose, core_args)


if __name__ == '__main__':
    main()
