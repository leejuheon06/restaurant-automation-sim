"""Central Control business logic (ROS-independent): visits, tables, orders, food items.

State names follow State Diagram v4:
  visit  ASSIGNED -> GUIDING -> SEATED -> LEFT        (REJECTED, GUIDE_FAILED, CANCELED)
  table  AVAILABLE -> ASSIGNED -> IN_USE -> COLLECTING -> AVAILABLE   (VACANT_CHECK)
  order  ORDERED -> COOKING -> SERVING -> COMPLETED   (ON_HOLD, CANCELED)
  item   QUEUED -> COOKING -> READY -> SERVING -> DELIVERED  (ON_HOLD, CANCELED)
Safety rules kept here: no double table assignment; a table becomes AVAILABLE only after the dish return is confirmed.
"""
from .layout import TABLES, MENU


class RestaurantIO:
    def submit_task(self, cb, **kw): ...          # cb(task_id) when the task manager accepted it
    def fleet_command(self, cmd, target, arg=''): ...
    def log(self, event, **f): ...
    def persist(self, table, row): ...


class Restaurant:
    def __init__(self, io: RestaurantIO, qr_vacant_sec=8.0, max_qty=5):
        self.io = io
        self.qr_vacant_sec, self.max_qty = qr_vacant_sec, max_qty
        self.tables = {tid: dict(id=tid, seats=t['seats'], state='AVAILABLE', visit=0, vacant_since=None, t_end=0.0)
                       for tid, t in TABLES.items()}
        self.visits, self.orders, self.items = {}, {}, {}
        self.incidents = []
        self.seq = dict(visit=0, order=0, item=0)
        self.now = 0.0
        for t in self.tables.values():
            self._save_table(t)

    # ------------------------------------------------------------ reception tablet
    def check_in(self, party_size):
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
        t = self.tables[table_id]
        if t['state'] not in ('IN_USE', 'VACANT_CHECK'):
            return False
        return all(self.items[i]['state'] in ('DELIVERED', 'CANCELED')
                   for o in self.orders.values() if o['visit'] == t['visit'] for i in o['items'])

    def end_use(self, table_id, source='TABLET'):
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

    def _free_table(self, t):
        self.io.log('TABLE_AVAILABLE', zone_id=f"T{t['id']}", visit_id=t['visit'],
                    reason=f"turnaround={self.now - t['t_end']:.1f}" if t['t_end'] else '')
        t.update(state='AVAILABLE', visit=0, vacant_since=None)
        self._save_table(t)

    # ------------------------------------------------------------ events from the task manager
    def on_task_event(self, e):
        ty, st = e['task_type'], e['state']
        self.io.persist('task', dict(task_id=e['task_id'], task_type=ty, state=st, robot_id=e['robot_id'],
                                     visit_id=e['visit_id'], order_id=e['order_id'], item_id=e['item_id'],
                                     table_id=e['table_id'], reason=e.get('reason', ''), updated_at=self.now))
        if st == 'SUSPENDED':
            self.incidents.append(dict(t=self.now, task=e['task_id'], robot=e['robot_id'], type=ty,
                                       reason=e.get('reason', ''), order=e['order_id'], visit=e['visit_id'],
                                       table=e['table_id'], resolved=''))
            self.io.persist('incident', dict(source='ADMIN_STOP' if e.get('reason') == 'E_STOP' else 'DEVICE_ERROR',
                                             robot_id=e['robot_id'], task_id=e['task_id'], order_id=e['order_id'],
                                             error_code=e.get('reason', ''), failed_state=ty, occurred_at=self.now))
            self.io.log('ALERT', task_id=e['task_id'], robot_id=e['robot_id'], visit_id=e['visit_id'],
                        order_id=e['order_id'], result='ADMIN_NOTIFIED', reason=e.get('reason', ''))
        if st in ('RESUMED', 'REASSIGNED', 'CANCELED'):
            for inc in self.incidents:
                if inc['task'] == e['task_id'] and not inc['resolved']:
                    inc['resolved'] = st
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
        if ty == 'COLLECT':
            t = self.tables.get(e['table_id'])
            if t and st == 'RETURNED' and t['state'] == 'COLLECTING':   # dishes confirmed at the return window
                self._free_table(t)
            return
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
        elif ty == 'SERVE' and st == 'LOADED':
            it['state'] = 'SERVING'
        elif ty == 'SERVE' and st == 'DELIVERED':
            it.update(state='DELIVERED', delivered=self.now)
            self.io.log('DELIVERED', visit_id=o['visit'], order_id=o['id'], task_id=e['task_id'],
                        robot_id=e['robot_id'], zone_id=f"T{o['table']}", result=it['menu'],
                        reason=f"order_to_delivery={self.now - o['created']:.1f} ready_to_delivery={self.now - it['ready']:.1f}")
        self._save_item(it)
        self._recompute_order(o)

    def _recompute_order(self, o):
        st = [self.items[i]['state'] for i in o['items']]
        live = [s for s in st if s != 'CANCELED']
        if not live:
            new = 'CANCELED'
        elif 'ON_HOLD' in live:
            new = 'ON_HOLD'
        elif all(s == 'DELIVERED' for s in live):
            new = 'COMPLETED'
        elif any(s in ('SERVING', 'DELIVERED') for s in live):
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
        self.now = now
        for t in self.tables.values():
            if t['state'] == 'VACANT_CHECK' and now - t['vacant_since'] >= self.qr_vacant_sec:
                ok, _ = self.end_use(t['id'], 'QR')
                if not ok:
                    t['vacant_since'] = now

    # ------------------------------------------------------------ operator
    def admin(self, cmd, target, arg=''):
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
                return True, f"table {t['id']} -> AVAILABLE"
            return False, '이 상태에서는 바꿀 수 없습니다 (중복 배정 방지).'
        if cmd == 'END_USE':
            return self.end_use(int(target), 'ADMIN')
        return None

    # ------------------------------------------------------------ persistence + snapshot
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

    def snapshot(self):
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
