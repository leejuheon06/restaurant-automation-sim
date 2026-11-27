"""Central Control business logic (ROS-independent): visits, tables, orders, food items.

[수정 2026-11-18] W2: State Diagram v4 는 주문·음식 상태만 정의함. 방문·테이블은
v4 에 정의가 없어("전체 생명주기는 확정하지 않는다") 자체 이름을 씀.
State names (order, item: State Diagram v4; visit, table: our own):
  visit  ASSIGNED -> GUIDING -> SEATED -> LEFT        (REJECTED, GUIDE_FAILED, CANCELED)
  table  AVAILABLE -> ASSIGNED -> IN_USE -> COLLECTING -> AVAILABLE   (VACANT_CHECK)
  order  ORDERED -> COOKING -> SERVING -> COMPLETED   (ON_HOLD, CANCELED)
  item   QUEUED -> COOKING -> READY -> LOADED -> SERVING -> DELIVERED
         (ON_HOLD, CANCELED)
Safety rules kept here: no double table assignment; a table becomes AVAILABLE only after the dish return is confirmed.
"""
from .layout import TABLES, MENU
from .map_catalog import active_map_id


class RestaurantIO:
    """Restaurant 의 바깥 출력(관제 임무 요청, 관제 명령, 기록, DB 저장).

    central_control_node(ROS), offline_bench(모의), 시험 코드가 구현한다.
    """

    def submit_task(self, cb, **kw): ...          # cb(task_id) when the task manager accepted it
    # [수정 2026-11-25] I/F 정의서 v0.2 이름: /fms/command ->
    # /frybot/tasks/control
    # [수정 2026-11-26] I/F v0.3 최종 판 이름:
    # /frybot/tasks/control -> /fms/command
    # fleet_command: 관제 명령(/fms/command) 보내기
    def fleet_command(self, cmd, target, arg=''): ...
    # log: 실행 로그(events.csv) 한 줄
    def log(self, event, **f): ...
    # persist: DB 표에 한 행 저장(upsert)
    def persist(self, table, row): ...


class Restaurant:
    """방문·테이블·주문·음식 항목의 상태를 가진 매장 업무 모델.

    시각은 tick() 이 넣는 self.now 를 쓴다. 실측 지도에서는 테이블 표가
    비어 있어 접수·주문을 받지 않는다.

    Args:
        io: 바깥 출력(RestaurantIO).
        qr_vacant_sec: 의자 QR 이 모두 보인 뒤 이용 종료로 보기까지의
            시간(초).
        max_qty: 한 주문에서 메뉴 하나의 최대 수량.
    """

    def __init__(self, io: RestaurantIO, qr_vacant_sec=8.0, max_qty=5):
        self.io = io
        self.qr_vacant_sec, self.max_qty = qr_vacant_sec, max_qty
        # 테이블 번호 -> 상태. 실측 지도(active_map_id 있음)면 빈 표
        self.tables = {tid: dict(id=tid, seats=t['seats'], state='AVAILABLE', visit=0, vacant_since=None, t_end=0.0)
                       for tid, t in ({} if active_map_id() else TABLES).items()}
        self.visits, self.orders, self.items = {}, {}, {}
        self.incidents = []
        self.seq = dict(visit=0, order=0, item=0)  # 마지막으로 쓴 번호
        self.now = 0.0  # 업무 시각(unix 초). tick() 이 갱신
        for t in self.tables.values():
            self._save_table(t)

    # ------------------------------------------------------------ reception tablet
    def check_in(self, party_size):
        """손님 접수: 맞는 빈 테이블을 배정하고 안내(GUIDE) 임무를 요청한다.

        거절해도 방문 기록(REJECTED)은 남긴다.

        Args:
            party_size: 인원.

        Returns:
            (접수 여부, 방문 번호, 테이블 번호(거절이면 0), 안내 문구).
        """
        self.seq['visit'] += 1
        vid = self.seq['visit']
        v = dict(id=vid, party=party_size, table=0, state='REJECTED', created=self.now, seated=0.0, left=0.0,
                 guide_task='', robot='')
        self.visits[vid] = v
        cands = [t for t in self.tables.values() if t['state'] == 'AVAILABLE' and t['seats'] >= party_size]
        if party_size < 1 or not cands:
            msg = '5명 이상은 한 테이블에 앉을 수 없습니다.' if party_size > 4 else \
                  ('인원을 확인해 주세요.' if party_size < 1 else '지금은 맞는 빈 테이블이 없습니다.')
            self.io.log('CHECKIN_REJECT', visit_id=vid, result='REJECTED', reason=f'party={party_size}')
            self._save_visit(v)
            return False, vid, 0, msg
        t = min(cands, key=lambda t: (t['seats'], t['id']))        # smallest table that fits
        t.update(state='ASSIGNED', visit=vid, vacant_since=None)
        v.update(state='ASSIGNED', table=t['id'])
        self._save_table(t)
        self._save_visit(v)
        self.io.log('CHECKIN', visit_id=vid, zone_id=f"T{t['id']}", result='ASSIGNED', reason=f'party={party_size}')
        self.io.submit_task(lambda tid: v.update(guide_task=tid), task_type='GUIDE', visit_id=vid, table_id=t['id'])
        return True, vid, t['id'], f"{t['id']}번 테이블로 안내해 드립니다."

    # ------------------------------------------------------------ table tablet
    def place_order(self, table_id, items):
        """주문 접수: 음식 한 접시마다 항목을 만들고 조리(COOK) 임무를 요청한다.

        Args:
            table_id: 테이블 번호(착석 중이어야 함).
            items: (메뉴 코드, 수량) 목록. 수량 0 이하는 빼고 본다.

        Returns:
            (접수 여부, 주문 번호(거절이면 0), 안내 문구).
        """
        t = self.tables.get(table_id)
        if not t or t['state'] not in ('IN_USE', 'VACANT_CHECK'):
            return False, 0, '착석한 테이블에서만 주문할 수 있습니다.'
        items = [(m_, int(q)) for m_, q in items if int(q) > 0]
        if not items or any(m_ not in MENU or q > self.max_qty for m_, q in items):
            return False, 0, '메뉴 또는 수량을 확인해 주세요.'
        self.seq['order'] += 1
        oid = self.seq['order']
        o = dict(id=oid, visit=t['visit'], table=table_id, state='ORDERED', created=self.now, completed=0.0, items=[])
        self.orders[oid] = o
        self.io.log('ORDER', visit_id=o['visit'], order_id=oid, zone_id=f'T{table_id}', result='ORDERED',
                    reason=','.join(f'{m_}x{q}' for m_, q in items))
        for menu, qty in items:
            for _ in range(qty):                                   # one food item = one dish
                self.seq['item'] += 1
                it = dict(id=self.seq['item'], order=oid, menu=menu, state='QUEUED', cook_task='', serve_task='',
                          ready=0.0, delivered=0.0, hold_from='')
                self.items[it['id']] = it
                o['items'].append(it['id'])
                self._save_item(it)
                self.io.submit_task(lambda tid, it=it: it.update(cook_task=tid), task_type='COOK', visit_id=o['visit'],
                                    order_id=oid, item_id=it['id'], table_id=table_id, menu=menu)
        self._save_order(o)
        return True, oid, '주문이 접수되었습니다.'

    def can_end_use(self, table_id):
        """이용 중인 테이블의 음식이 모두 전달(또는 취소)됐는지.

        Args:
            table_id: 테이블 번호.

        Returns:
            이용 종료를 받을 수 있으면 True.
        """
        t = self.tables[table_id]
        if t['state'] not in ('IN_USE', 'VACANT_CHECK'):
            return False
        return all(self.items[i]['state'] in ('DELIVERED', 'CANCELED')
                   for o in self.orders.values() if o['visit'] == t['visit'] for i in o['items'])

    def end_use(self, table_id, source='TABLET'):
        """이용 종료: 방문을 끝내고 식기 회수를 요청하거나 테이블을 비운다.

        Args:
            table_id: 테이블 번호.
            source: 'TABLET'(테이블 화면), 'QR'(빈자리 판정), 'ADMIN'(관리자).
                ADMIN 은 전달되지 않은 음식을 취소하고 강제로 끝낸다.

        Returns:
            (성공 여부, 안내 문구).
        """
        t = self.tables.get(table_id)
        if not t or t['state'] not in ('IN_USE', 'VACANT_CHECK'):
            return False, '이용 중인 테이블이 아닙니다.'
        if not self.can_end_use(table_id):
            if source != 'ADMIN':
                return False, '아직 전달되지 않은 음식이 있습니다.'
            for o in self.orders.values():                         # operator forces the end: cancel the rest
                if o['visit'] == t['visit']:
                    for i in o['items']:
                        it = self.items[i]
                        if it['state'] not in ('DELIVERED', 'CANCELED'):
                            for task in (it['cook_task'], it['serve_task']):
                                if task:
                                    self.io.fleet_command('CANCEL_TASK', task, 'forced end of use')
                            it['state'] = 'CANCELED'
                            self._save_item(it)
                    self._recompute_order(o)
        v = self.visits[t['visit']]
        v.update(state='LEFT', left=self.now)
        self._save_visit(v)
        t['t_end'] = self.now
        # 전달된 음식이 있으면 식기 회수 뒤에, 없으면 바로 테이블을 비움
        used = any(self.items[i]['state'] == 'DELIVERED'
                   for o in self.orders.values() if o['visit'] == v['id'] for i in o['items'])
        self.io.log('END_USE', visit_id=v['id'], zone_id=f'T{table_id}', result=source)
        if used:
            t.update(state='COLLECTING', vacant_since=None)
            self.io.submit_task(lambda tid: None, task_type='COLLECT', visit_id=v['id'], table_id=table_id)
        else:
            self._free_table(t)
        self._save_table(t)
        return True, '이용해 주셔서 감사합니다.'

    # 테이블을 다시 배정 가능(AVAILABLE)으로 돌리고 회전 시간을 기록
    def _free_table(self, t):
        self.io.log('TABLE_AVAILABLE', zone_id=f"T{t['id']}", visit_id=t['visit'],
                    reason=f"turnaround={self.now - t['t_end']:.1f}" if t['t_end'] else '')
        t.update(state='AVAILABLE', visit=0, vacant_since=None)
        self._save_table(t)

    # [수정 2026-11-24] AI 서버(frybot_ai guest_tracker)의 GUEST_TRACK 에는
    # visit_id 가 없어, Central Control 이 그 로봇이 맡은 안내로 채우는 데 씀
    def guiding_visit(self, robot_id: str) -> int:
        """이 로봇이 맡아 안내하러 가거나 안내 중인 방문 번호를 찾는다.

        Args:
            robot_id: 로봇 이름(예: 'pinky1').

        Returns:
            상태가 ASSIGNED 또는 GUIDING 이고 GUIDE 임무가 이 로봇에 배정된
            방문 번호. 없으면 0.
        """
        for v in self.visits.values():
            if (v.get('robot') == robot_id
                    and v['state'] in ('ASSIGNED', 'GUIDING')):
                return v['id']
        return 0

    # [수정 2026-11-24] 손님 고정: 안내 시작(AT_START)부터 자리 안내
    # 완료(ARRIVED)까지 AI 서버가 처음 본 손님을 고정하도록 목록을 줌
    def guiding_visits(self) -> dict[str, int]:
        """안내 중인 로봇과 방문 번호를 돌려준다(AI 서버 손님 고정용).

        GUIDING(안내 시작 뒤)과 GUIDE_FAILED(보류, RESUMED 로 같은 손님을
        다시 안내할 수 있어 고정을 유지)만 넣는다. 한 로봇에 둘 다 있으면
        GUIDING 이 앞선다.

        Returns:
            {robot_id: visit_id}.
        """
        out = {}
        for v in self.visits.values():
            rid = v.get('robot')
            if not rid:
                continue
            if v['state'] == 'GUIDING' or (
                    v['state'] == 'GUIDE_FAILED' and rid not in out):
                out[rid] = v['id']
        return out

    # ------------------------------------------------------------ events from the task manager
    # [수정 2026-11-25] I/F 정의서 v0.2 이름: TaskEvent, /fms/task_events ->
    # TaskProgress, /frybot/tasks/progress
    # [수정 2026-11-26] I/F v0.3 최종 판 이름(docstring):
    # /frybot/tasks/progress -> /fms/task_events, TaskProgress -> TaskEvent
    def on_task_event(self, e):
        """관제의 임무 이벤트(/fms/task_events)로 업무 상태를 갱신한다.

        Args:
            e: TaskEvent 를 옮긴 dict(task_id, task_type, state, robot_id,
                visit_id, order_id, item_id, table_id, reason).
        """
        ty, st = e['task_type'], e['state']
        self.io.persist('task', dict(task_id=e['task_id'], task_type=ty, state=st, robot_id=e['robot_id'],
                                     visit_id=e['visit_id'], order_id=e['order_id'], item_id=e['item_id'],
                                     table_id=e['table_id'], reason=e.get('reason', ''), updated_at=self.now))
        # 임무 보류: 관리자 알람(incident)으로 남김
        if st == 'SUSPENDED':
            self.incidents.append(dict(t=self.now, task=e['task_id'], robot=e['robot_id'], type=ty,
                                       reason=e.get('reason', ''), order=e['order_id'], visit=e['visit_id'],
                                       table=e['table_id'], resolved=''))
            self.io.persist('incident', dict(source='ADMIN_STOP' if e.get('reason') in ('E_STOP', 'PAUSED') else 'DEVICE_ERROR',
                                             robot_id=e['robot_id'], task_id=e['task_id'], order_id=e['order_id'],
                                             error_code=e.get('reason', ''), failed_state=ty, occurred_at=self.now))
            self.io.log('ALERT', task_id=e['task_id'], robot_id=e['robot_id'], visit_id=e['visit_id'],
                        order_id=e['order_id'], result='ADMIN_NOTIFIED', reason=e.get('reason', ''))
        # 재개·재배정·취소되면 그 임무의 알람을 해결로 표시
        if st in ('RESUMED', 'REASSIGNED', 'CANCELED'):
            for inc in self.incidents:
                if inc['task'] == e['task_id'] and not inc['resolved']:
                    inc['resolved'] = st
        # 안내 임무: 방문과 테이블 상태
        if ty == 'GUIDE':
            v = self.visits.get(e['visit_id'])
            if not v:
                return
            t = self.tables[v['table']]
            if st == 'ASSIGNED':
                v['robot'] = e['robot_id']
            elif st == 'AT_START':
                v['state'] = 'GUIDING'
            elif st == 'ARRIVED':
                v.update(state='SEATED', seated=self.now)
                t['state'] = 'IN_USE'
                self.io.log('SEATED', visit_id=v['id'], zone_id=f"T{t['id']}", robot_id=e['robot_id'],
                            reason=f"checkin_to_seat={self.now - v['created']:.1f}")
            elif st == 'SUSPENDED':
                v['state'] = 'GUIDE_FAILED'
            elif st == 'RESUMED':
                v['state'] = 'GUIDING'
            elif st == 'REASSIGNED':
                v['state'] = 'ASSIGNED'
            elif st == 'CANCELED':
                v.update(state='CANCELED', left=self.now)
                self._free_table(t)
            self._save_visit(v)
            self._save_table(t)
            return
        # 식기 회수 임무: 퇴식구 반납이 확인돼야 테이블을 비움
        if ty == 'COLLECT':
            t = self.tables.get(e['table_id'])
            if t and st == 'RETURNED' and t['state'] == 'COLLECTING':   # dishes confirmed at the return window
                self._free_table(t)
            return
        # 나머지(COOK, SERVE): 음식 항목 상태와 주문 상태
        it = self.items.get(e['item_id'])
        if not it:
            return
        o = self.orders[it['order']]
        if st == 'SUSPENDED':
            it['hold_from'], it['state'] = it['state'], 'ON_HOLD'
        elif st in ('RESUMED', 'REASSIGNED') and it['state'] == 'ON_HOLD':
            it['state'] = it['hold_from'] or 'QUEUED'
        elif st == 'CANCELED':
            it['state'] = 'CANCELED'
        elif ty == 'COOK' and st == 'COOKING':
            it['state'] = 'COOKING'
        elif ty == 'COOK' and st == 'READY':
            it.update(state='READY', ready=self.now)
            self.io.submit_task(lambda tid, it=it: it.update(serve_task=tid), task_type='SERVE', visit_id=o['visit'],
                                order_id=o['id'], item_id=it['id'], table_id=o['table'], menu=it['menu'])
        # [수정 2026-11-18] W2: v4 에 맞춰 적재(LOADED)와 테이블 이동 시작
        # (SERVING)을 나눔. 전에는 적재 이벤트에서 바로 SERVING 이었음
        elif ty == 'SERVE' and st == 'LOADED':
            it['state'] = 'LOADED'
        elif ty == 'SERVE' and st == 'SERVING':
            it['state'] = 'SERVING'
        elif ty == 'SERVE' and st == 'DELIVERED':
            it.update(state='DELIVERED', delivered=self.now)
            self.io.log('DELIVERED', visit_id=o['visit'], order_id=o['id'], task_id=e['task_id'],
                        robot_id=e['robot_id'], zone_id=f"T{o['table']}", result=it['menu'],
                        reason=f"order_to_delivery={self.now - o['created']:.1f} ready_to_delivery={self.now - it['ready']:.1f}")
        self._save_item(it)
        self._recompute_order(o)

    # 음식 항목들의 상태로 주문 상태를 다시 정함(바뀌면 저장)
    def _recompute_order(self, o):
        st = [self.items[i]['state'] for i in o['items']]
        live = [s for s in st if s != 'CANCELED']
        if not live:
            new = 'CANCELED'
        elif 'ON_HOLD' in live:
            new = 'ON_HOLD'
        elif all(s == 'DELIVERED' for s in live):
            new = 'COMPLETED'
        # [수정 2026-11-18] W2: 주문에는 LOADED 가 없으므로 SERVING 으로 묶음
        # (주문 상태가 바뀌는 시점은 전과 같음)
        elif any(s in ('LOADED', 'SERVING', 'DELIVERED') for s in live):
            new = 'SERVING'
        elif any(s in ('COOKING', 'READY') for s in live):
            new = 'COOKING'
        else:
            new = 'ORDERED'
        if new != o['state']:
            o['state'] = new
            if new == 'COMPLETED':
                o['completed'] = self.now
                self.io.log('ORDER_COMPLETED', visit_id=o['visit'], order_id=o['id'],
                            reason=f"order_to_complete={self.now - o['created']:.1f}")
            self._save_order(o)

    # ------------------------------------------------------------ AI server results (chair QR)
    def on_seat_qr(self, table_id, visible, seats):
        """AI 서버의 의자 QR 결과로 빈자리 여부를 판단한다.

        착석 5초 뒤부터 QR 이 의자 수만큼 보이면 VACANT_CHECK 로 두고,
        다시 가려지면 IN_USE 로 돌린다. 종료 판단은 tick() 이 한다.

        Args:
            table_id: 테이블 번호.
            visible: 보이는 의자 QR 개수(사람이 앉으면 가려짐).
            seats: 의자 수.
        """
        t = self.tables.get(table_id)
        if not t or t['state'] not in ('IN_USE', 'VACANT_CHECK'):
            return
        v = self.visits[t['visit']]
        if visible >= seats and self.now - v['seated'] > 5.0:
            if t['vacant_since'] is None:
                t.update(vacant_since=self.now, state='VACANT_CHECK')
        elif t['state'] == 'VACANT_CHECK':
            t.update(vacant_since=None, state='IN_USE')            # someone only stepped out for a moment

    def tick(self, now):
        """업무 시각을 갱신하고 빈자리 판정이 끝난 테이블을 이용 종료한다.

        VACANT_CHECK 가 qr_vacant_sec 이상 이어지면 end_use('QR'). 음식이
        남아 거절되면 판정 시각을 다시 센다.

        Args:
            now: 현재 시각(unix 초).
        """
        self.now = now
        for t in self.tables.values():
            if t['state'] == 'VACANT_CHECK' and now - t['vacant_since'] >= self.qr_vacant_sec:
                ok, _ = self.end_use(t['id'], 'QR')
                if not ok:
                    t['vacant_since'] = now

    # ------------------------------------------------------------ operator
    def admin(self, cmd, target, arg=''):
        """매장 쪽 관리자 명령(SET_TABLE, END_USE)을 처리한다.

        Args:
            cmd: 명령 이름.
            target: 테이블 번호(문자열).
            arg: SET_TABLE 의 값('AVAILABLE' 또는 'CLOSED').

        Returns:
            (성공 여부, 안내 문구). 매장 명령이 아니면 None.
        """
        if cmd == 'SET_TABLE':
            t = self.tables.get(int(target))
            if not t:
                return False, 'unknown table'
            if arg == 'AVAILABLE' and t['state'] in ('COLLECTING',) or arg == 'CLOSED' and t['state'] == 'AVAILABLE':
                if arg == 'AVAILABLE':
                    self._free_table(t)
                else:
                    t['state'] = 'CLOSED'
                self._save_table(t)
                return True, f"table {t['id']} -> {t['state']}"
            if arg == 'AVAILABLE' and t['state'] == 'CLOSED':
                t['state'] = 'AVAILABLE'
                # [수정 2026-11-17] T-28: 사용 재개가 DB 에 저장되지 않았음
                self._save_table(t)
                return True, f"table {t['id']} -> AVAILABLE"
            return False, '이 상태에서는 바꿀 수 없습니다 (중복 배정 방지).'
        if cmd == 'END_USE':
            return self.end_use(int(target), 'ADMIN')
        return None

    # ------------------------------------------------------------ persistence + snapshot
    # 아래 _save_* 는 업무 상태를 db.SCHEMA 의 표 형식으로 저장
    def _save_table(self, t):
        self.io.persist('dining_table', dict(table_id=t['id'], seats=t['seats'], status=t['state'], visit_id=t['visit'],
                                             updated_at=self.now))

    def _save_visit(self, v):
        self.io.persist('visit', dict(visit_id=v['id'], party_size=v['party'], table_id=v['table'] or None,
                                      status=v['state'], created_at=v['created'], seated_at=v['seated'], ended_at=v['left']))

    def _save_order(self, o):
        self.io.persist('orders', dict(order_id=o['id'], visit_id=o['visit'], table_id=o['table'], status=o['state'],
                                       created_at=o['created'], completed_at=o['completed']))

    def _save_item(self, it):
        self.io.persist('order_item', dict(item_id=it['id'], order_id=it['order'], menu=it['menu'], status=it['state'],
                                           cook_task_id=it['cook_task'], serve_task_id=it['serve_task'],
                                           ready_at=it['ready'], delivered_at=it['delivered']))

    # [수정 2026-11-25] I/F 정의서 v0.2 이름: /frybot/state ->
    # /frybot/central/view_state
    # [수정 2026-11-26] I/F v0.3 최종 판 이름(docstring):
    # /frybot/central/view_state -> /frybot/state
    def snapshot(self):
        """화면용 업무 상태(/frybot/state 의 본문)를 돌려준다.

        Returns:
            테이블 전체, 최근 방문·주문 30건, 최근 알람 20건, 메뉴를 담은 dict.
        """
        return {
            'now': self.now,
            'tables': [dict(id=t['id'], seats=t['seats'], state=t['state'], visit=t['visit'],
                            can_end=self.can_end_use(t['id'])) for t in self.tables.values()],
            'visits': [dict(v) for v in list(self.visits.values())[-30:]],
            'orders': [dict(id=o['id'], visit=o['visit'], table=o['table'], state=o['state'],
                            age=round(self.now - o['created'], 1),
                            items=[dict(id=i, menu=self.items[i]['menu'], name=MENU[self.items[i]['menu']]['name'],
                                        state=self.items[i]['state']) for i in o['items']])
                       for o in list(self.orders.values())[-30:]],
            'incidents': self.incidents[-20:],
            'menu': MENU,
        }
