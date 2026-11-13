"""Scripted guests for a repeatable full-service run (uses the guest simulator's HTTP API).

    ros2 run frybot_sim scenario --scenario demo      (demo | normal | rush | single)
Guests enter on schedule, order after being seated, and leave when everything was delivered
(odd visits press the tablet button, even visits just walk out -> chair QR path).
"""
import argparse
import json
import time
import urllib.request

SCENARIOS = {
    'demo': [(0, 2, [('FRIED', 1)]), (12, 4, [('FRIED_RICE', 1), ('SEASONED', 1)]), (30, 2, [('FRIED_RICE', 1)])],
    'rush': [(0, 2, [('FRIED_RICE', 1)]), (3, 4, [('FRIED_RICE', 2)]), (6, 2, [('FRIED', 1)]),
             (9, 4, [('FRIED_RICE', 1), ('SEASONED', 1)]), (12, 2, [('FRIED_RICE', 1)]), (15, 2, [('FRIED_RICE', 1)])],
    'single': [(0, 2, [('FRIED_RICE', 1)])],
    # same guests as the offline benchmark's `normal`: five groups, 20-40 s apart
    'normal': [(0, 2, [('FRIED', 1)]), (20, 4, [('FRIED_RICE', 2), ('SEASONED', 1)]), (45, 2, [('FRIED_RICE', 1)]),
               (80, 3, [('FRIED', 1), ('FRIED_RICE', 1)]), (120, 2, [('SEASONED', 1)])],
}


def call(url, body=None):
    req = urllib.request.Request(url, json.dumps(body).encode() if body is not None else None,
                                 {'Content-Type': 'application/json'})
    return json.loads(urllib.request.urlopen(req, timeout=8).read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--scenario', default='demo', choices=sorted(SCENARIOS))
    ap.add_argument('--ui', default='http://127.0.0.1:8090')
    ap.add_argument('--eat', type=float, default=12.0, help='seconds between last dish and leaving')
    ap.add_argument('--timeout', type=float, default=2400.0,
                    help='give up after this many seconds (normal takes 20-25 min in Gazebo with the GUI on)')
    a, _ = ap.parse_known_args()
    script = list(SCENARIOS[a.scenario])
    t0 = time.time()
    plan, ordered, leave_at, left = {}, set(), {}, set()
    while time.time() - t0 < a.timeout:
        t = time.time() - t0
        while script and script[0][0] <= t:
            _, party, items = script.pop(0)
            r = call(a.ui + '/api/enter', {'party_size': party})
            print(f'[{t:6.1f}] 손님 {party}명 입장 -> {r["message"]}', flush=True)
            if r['ok']:
                plan[r['visit_id']] = items
        s = call(a.ui + '/api/state')
        rest, fms = s.get('rest', {}), s.get('fms', {})
        tables = {x['id']: x for x in rest.get('tables', [])}
        for v in rest.get('visits', []):
            vid = v['id']
            if vid not in plan or v['state'] != 'SEATED':
                continue
            if vid not in ordered:
                r = call(a.ui + '/api/order', {'table_id': v['table'], 'items': [{'menu': m, 'qty': q} for m, q in plan[vid]]})
                print(f'[{t:6.1f}] 손님{vid} T{v["table"]} 주문 {plan[vid]} -> {r["message"]}', flush=True)
                ordered.add(vid)
            elif tables[v['table']]['can_end'] and vid not in left:
                leave_at.setdefault(vid, t + a.eat)
                if t >= leave_at[vid]:
                    mode = 'tablet' if vid % 2 else 'walkout'
                    r = call(a.ui + '/api/leave', {'table_id': v['table'], 'mode': mode, 'visit_id': vid})
                    print(f'[{t:6.1f}] 손님{vid} 퇴장({mode}) -> {r["message"]}', flush=True)
                    left.add(vid)
        done = (not script and plan and len(left) == len(plan)
                and all(x['state'] == 'AVAILABLE' for x in tables.values())
                and all(r['state'] in ('IDLE', 'CHARGING', 'STANDBY') for r in fms.get('robots', [])))
        if done:
            print(f'[{t:6.1f}] 시나리오 완료: 모든 테이블 이용 가능, 모든 AMR 복귀', flush=True)
            print(json.dumps(fms.get('metrics', {}), ensure_ascii=False))
            return 0
        time.sleep(1.0)
    print('시간 초과: 시나리오가 끝나지 않았습니다.')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
