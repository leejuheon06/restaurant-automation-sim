"""Summarise one run folder (events.csv) into the plan's metrics: service times, traffic waits, failures."""
import csv
import os
import re
import statistics as st
import sys


# event 행들의 reason 칸에서 'key=숫자' 값을 모음(예: checkin_to_seat=12.3)
def _vals(rows, event, key):
    out = []
    for r in rows:
        if r['event'] == event:
            m = re.search(key + r'=([0-9.]+)', r['reason'])
            if m:
                out.append(float(m.group(1)))
    return out


def summarize(path):
    """events.csv 하나를 읽어 지표 요약 문자열을 만든다.

    Args:
        path: events.csv 경로.

    Returns:
        여러 줄의 요약(서비스 시간, 통행 허가 대기, 임무·양보 건수 등).
    """
    rows = list(csv.DictReader(open(path)))
    # f: 값 목록의 개수·중앙값·최소·최대, c: 이벤트 건수
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
        # [수정 2026-11-17] T-23: 양보 관련 판단 건수
        f'양보: 대기 {c("YIELD_WAIT")} / 계획 대기 {c("PLAN_WAIT")} / '
        f'양보 안 함(우회) {c("YIELD_SKIP")}',
        # [수정 2026-11-20] T-54: 변경이 없으면 '-'. 예전에는 + 가 or 보다
        # 먼저 계산돼 '-' 가 나오지 않았음(f 접두어도 자리표시자 없이
        # 붙어 있었음)
        '알고리즘 변경: ' + (', '.join(
            f'{r["event"]}={r["result"]}' for r in rows
            if r['event'].startswith('SET_')) or '-'),
    ]
    return '\n'.join(lines)


def main():
    """analyze_run 명령의 진입점.

    인자로 실행 폴더나 events.csv 를 받는다. 없으면 ~/frybot_ws/runs 안에서
    이름순으로 마지막 폴더를 쓴다.
    """
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
