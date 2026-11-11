"""Summarise one run folder (events.csv) into the plan's metrics: service times, traffic waits, failures."""
import csv
import os
import re
import statistics as st
import sys


def _vals(rows, event, key):
    out = []
    for r in rows:
        if r['event'] == event:
            m = re.search(key + r'=([0-9.]+)', r['reason'])
            if m:
                out.append(float(m.group(1)))
    return out


def summarize(path):
    rows = list(csv.DictReader(open(path)))
    f = lambda a: f'n={len(a)} median={st.median(a):.1f} min={min(a):.1f} max={max(a):.1f}' if a else 'n=0'
    c = lambda e: sum(1 for r in rows if r['event'] == e)
    waits = {}
    req = {}
    for r in rows:                                  # ZONE_REQUEST -> next ZONE_GRANT of the same robot/zone
        k = (r['robot_id'], r['zone_id'])
        if r['event'] == 'ZONE_REQUEST':
            req[k] = float(r['timestamp'])
        elif r['event'] == 'ZONE_GRANT' and k in req:
            waits.setdefault(r['robot_id'], []).append(float(r['timestamp']) - req.pop(k))
    allw = [w for v in waits.values() for w in v]
    lines = [
        f'run: {rows[0]["run_id"] if rows else "?"}   events: {len(rows)}',
        f'접수 -> 착석 (s)            : {f(_vals(rows, "SEATED", "checkin_to_seat"))}',
        f'주문 -> 전달 (s)            : {f(_vals(rows, "DELIVERED", "order_to_delivery"))}',
        f'조리 완료 -> 전달 (s)       : {f(_vals(rows, "DELIVERED", "ready_to_delivery"))}',
        f'이용 종료 -> 테이블 가용 (s): {f(_vals(rows, "TABLE_AVAILABLE", "turnaround"))}',
        f'통행 허가 대기 (s)          : {f(allw)}',
        f'임무 완료 {c("TASK_DONE")} / 중단 {c("TASK_SUSPEND")} / 재계획 {c("REPLAN")} / 비켜서기 {c("RETREAT")} / '
        f'계획 실패 {c("PLAN_FAIL")} / 접수 거절 {c("CHECKIN_REJECT")}',
        f'알고리즘 변경: ' + ', '.join(f'{r["event"]}={r["result"]}' for r in rows if r['event'].startswith('SET_')) or '-',
    ]
    return '\n'.join(lines)


def main():
    base = os.path.expanduser('~/frybot_ws/runs')
    if len(sys.argv) > 1:
        path = sys.argv[1]
    else:
        runs = sorted(d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d)))
        path = os.path.join(base, runs[-1])
    if os.path.isdir(path):
        path = os.path.join(path, 'events.csv')
    print(summarize(path))


if __name__ == '__main__':
    main()
