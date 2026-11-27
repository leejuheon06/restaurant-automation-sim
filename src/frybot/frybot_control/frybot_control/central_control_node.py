"""Central Control node (Main Server): restaurant state, DB, event log, AI result ingest (HTTP).

식당 업무 상태(restaurant.Restaurant)를 갖고 Web Service 의 서비스
요청(접수, 주문, 이용 종료, 관리자 명령)을 처리한다. AMR·조리 임무는
Task Manager 에 /fms/submit_task 로 맡기고([수정 2026-11-25] I/F 정의서
v0.2 이름: /fms/submit_task -> /frybot/tasks/submit. [수정 2026-11-26] I/F
v0.3 최종 판 이름: 다시 /fms/submit_task), 임무 이벤트와 실행 로그를
받아 runs/<run_id>/ 의 events.csv·frybot.db 에 기록한다. AI 서버 결과는
HTTP(:8100 POST)로 받아 SEAT_QR 은 업무 모델에, DONENESS 는
/ai/results 로, GUEST_TRACK 은 /frybot/guest_track 으로 넘긴다.
"""
import json
import os
import threading
import time
# [수정 2026-11-24] 손님 고정 목록을 AI 서버로 보내는 데 씀
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import rclpy
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup, ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from std_msgs.msg import String

# [수정 2026-11-25] I/F 정의서 v0.2 이름: TaskEvent·CheckIn·PlaceOrder·EndUse·
# AdminCommand·FleetCommand -> TaskProgress·RegisterVisit·SubmitOrder·
# EndVisit·RequestAdminOperation·ControlTask
# [수정 2026-11-26] I/F v0.3 최종 판 이름: TaskProgress -> TaskEvent
from frybot_interfaces.msg import GuestTrack, TaskEvent
# [수정 2026-11-26] I/F v0.3 최종 판 이름: ControlTask -> FleetCommand,
# EndVisit -> EndUse, RegisterVisit -> CheckIn,
# RequestAdminOperation -> AdminCommand, SubmitOrder -> PlaceOrder
from frybot_interfaces.srv import (AdminCommand, CheckIn, EndUse,
                                   FleetCommand, PlaceOrder, SubmitTask)

from .db import Store
from .restaurant import Restaurant, RestaurantIO
from .runlog import RunLogger
from .map_catalog import active_map_id
# [수정 2026-11-18] P1(D1): 지도 이름 없이 뜨지 않음
from .map_catalog import require_map_id

# README 의 EVENT QoS(reliable, volatile, 깊이 100). 임무 이벤트와
# 실행 로그 구독에 씀
QOS = QoSProfile(depth=100, reliability=ReliabilityPolicy.RELIABLE, history=HistoryPolicy.KEEP_LAST)
# [수정 2026-11-25] I/F 정의서 v0.2 이름: /fms/command -> /frybot/tasks/control
# [수정 2026-11-26] I/F v0.3 최종 판 이름: /frybot/tasks/control -> /fms/command
# 관리자 명령 중 Task Manager(/fms/command)로 그대로 넘기는 것.
# 나머지(SET_TABLE, END_USE)는 Restaurant.admin 이 처리
# [수정 2026-11-17] GO_HOME(홈 복귀) 추가
# [수정 2026-11-17] UR-18: PAUSE(일시 중단) 추가
FLEET_CMDS = ('PAUSE', 'ESTOP', 'RESUME', 'REASSIGN', 'CANCEL_TASK', 'RETRY_TASK', 'SET_SCHEDULER', 'SET_PLANNER', 'SET_STANDBY', 'MOVE_TO_VERTEX',
              'GO_HOME')


class CentralControl(Node, RestaurantIO):
    """Central Control 노드. RestaurantIO 의 출력을 ROS 로 구현한다.

    업무 상태(self.rest)는 서비스 콜백, 구독·타이머, AI 수신 스레드가
    함께 쓰므로 self.lock 안에서만 바꾼다.
    """

    def __init__(self):
        super().__init__('central_control')
        # FRYBOT_MAP_ID 가 없으면 RuntimeError 로 멈춤
        require_map_id('central_control')
        p = self.declare_parameter  # 선언하고 값(런치 인자 또는 기본값)을 읽음
        # 실행 로그(RunLogger): run_dir/run_id 폴더에 events.csv,
        # manifest.json 을 씀. run_id 가 비면 run_YYYYMMDD_HHMMSS.
        # robot_ids 는 manifest 에 적는 로봇 목록(기록용)
        # [수정 2026-11-18] P1: 기본값을 실기기 값으로(scenario real -> 실행
        # 기록의 simulation false, robot_ids pinky1). 시뮬 런치는 두 값을 넘김
        scenario = p('scenario', 'real').value
        self.runlog = RunLogger(p('run_dir', '~/frybot_ws/runs').value, p('run_id', '').value or None,
                                manifest=dict(scenario=scenario, map_version=active_map_id() or 'frybot_200x100_v1',
                                              robots=list(p('robot_ids', ['pinky1']).value),
                                              simulation=scenario != 'real'))
        # 업무 DB(SQLite): 실행 폴더의 frybot.db
        self.store = Store(os.path.join(self.runlog.dir, 'frybot.db'))
        self.lock = threading.RLock()  # self.rest 보호(재진입 가능)
        self.pending = []                       # SubmitTask requests waiting for the task manager
        self.ai_latest = {}  # 종류별 최신 AI 결과. 상태 JSON 의 'ai'
        # 업무 모델. qr_vacant_sec: 의자 QR 이 모두 보인 뒤 이용 종료로
        # 보기까지의 시간(초)
        self.rest = Restaurant(self, qr_vacant_sec=p('qr_vacant_sec', 8.0).value)
        self.rest.now = time.time()
        # 콜백 그룹. 서비스(g_srv)·클라이언트(g_cli)는 재진입이라
        # [수정 2026-11-26] I/F v0.3 최종 판 이름:
        # /frybot/tasks/control -> /fms/command
        # _admin 이 서비스 안에서 /fms/command 을 동기 호출할 수 있음.
        # 구독·타이머(g_main)는 상호 배제라 서로 겹치지 않음
        g_srv, g_cli, g_main = ReentrantCallbackGroup(), ReentrantCallbackGroup(), MutuallyExclusiveCallbackGroup()
        # Task Manager 로 가는 클라이언트: 임무 접수, 관제 명령
        # [수정 2026-11-25] I/F 정의서 v0.2 이름: 아래 서비스·토픽의 타입과
        # 주소(/fms/submit_task·/fms/command·/frybot/check_in·place_order·
        # end_use·admin·/fms/task_events·/frybot/state -> /frybot/tasks/·
        # /frybot/central/ 아래 새 이름)
        # [수정 2026-11-26] I/F v0.3 최종 판 이름:
        # /frybot/tasks/submit -> /fms/submit_task
        self.cli_submit = self.create_client(
            SubmitTask, '/fms/submit_task', callback_group=g_cli)
        # [수정 2026-11-26] I/F v0.3 최종 판 이름: ControlTask -> FleetCommand,
        # /frybot/tasks/control -> /fms/command
        self.cli_fleet = self.create_client(
            FleetCommand, '/fms/command', callback_group=g_cli)
        # Web Service 가 부르는 서비스: 접수, 주문, 이용 종료, 관리자 명령
        # [수정 2026-11-26] I/F v0.3 최종 판 이름: RegisterVisit -> CheckIn,
        # /frybot/central/register_visit -> /frybot/check_in
        self.create_service(
            CheckIn, '/frybot/check_in', self._check_in,
            callback_group=g_srv)
        # [수정 2026-11-26] I/F v0.3 최종 판 이름: SubmitOrder -> PlaceOrder,
        # /frybot/central/submit_order -> /frybot/place_order
        self.create_service(
            PlaceOrder, '/frybot/place_order', self._place_order,
            callback_group=g_srv)
        # [수정 2026-11-26] I/F v0.3 최종 판 이름: EndVisit -> EndUse,
        # /frybot/central/end_visit -> /frybot/end_use
        self.create_service(
            EndUse, '/frybot/end_use', self._end_use,
            callback_group=g_srv)
        # [수정 2026-11-26] I/F v0.3 최종 판 이름:
        # RequestAdminOperation -> AdminCommand,
        # /frybot/central/request_admin_operation -> /frybot/admin
        self.create_service(
            AdminCommand, '/frybot/admin',
            self._admin, callback_group=g_srv)
        # Task Manager 의 임무 이벤트와 실행 로그(JSON) 구독
        # [수정 2026-11-26] I/F v0.3 최종 판 이름: TaskProgress -> TaskEvent,
        # /frybot/tasks/progress -> /fms/task_events
        self.create_subscription(
            TaskEvent, '/fms/task_events', self._task_event, QOS,
            callback_group=g_main)
        self.create_subscription(String, '/frybot/event_log', self._fleet_log, QOS, callback_group=g_main)
        # 식당 상태 JSON(Web Service 가 화면에 씀)
        # [수정 2026-11-26] I/F v0.3 최종 판 이름:
        # /frybot/central/view_state -> /frybot/state
        self.pub_state = self.create_publisher(
            String, '/frybot/state', 10)
        # 익힘 판정(DONENESS) JSON. Task Manager 가 조리 판단에 씀
        self.pub_ai = self.create_publisher(String, '/ai/results', 50)
        # [수정 2026-11-17] UR-03: AI 서버의 손님 추적 결과를 AMR 에게 전달
        self.pub_track = self.create_publisher(
            GuestTrack, '/frybot/guest_track', 10)
        # 0.25초마다 상태 갱신·발행, 밀린 임무 요청 전송
        self.create_timer(0.25, self._tick, callback_group=g_main)
        # AI 결과 HTTP 수신(0.0.0.0:ai_http_port)을 데몬 스레드에서 돌림
        port = p('ai_http_port', 8100).value
        threading.Thread(target=self._serve_ai, args=(port,), daemon=True).start()
        # [수정 2026-11-24] 손님 고정: 안내 중인 (로봇 -> 방문) 목록을 AI 서버
        # (frybot_ai guest_tracker)에 POST. 바뀌면 바로, 아니면 1초마다
        # (AI 서버가 다시 떠도 고정이 이어지도록). 'none' 이면 보내지 않음
        self.guides_url = p('ai_guides_url',
                            'http://127.0.0.1:8095/guides').value
        self.guides_sent = (None, 0.0)  # (마지막으로 보낸 목록, 시각)
        self.guides_thread = None
        self.guides_warned = False
        self.get_logger().info(f'central control up. run folder: {self.runlog.dir}  (AI ingest http://127.0.0.1:{port}/ai/result)')

    # ---------------------------------------------------------------- RestaurantIO
    def submit_task(self, cb, **kw):
        """임무 요청을 대기열에 넣고 Task Manager 로 보낸다.

        서비스가 아직 없으면 대기열에 남겨 두고 _tick 에서 다시 보낸다.

        Args:
            cb: 접수되면 task_id 를 넘겨 부를 함수(self.lock 안에서 부름).
            **kw: SubmitTask.Request 필드(task_type, visit_id, table_id 등).
        """
        self.pending.append((SubmitTask.Request(**{k: v for k, v in kw.items()}), cb))
        self._flush()

    # 서비스가 준비됐으면 대기열의 요청을 모두 비동기로 보냄
    def _flush(self):
        if not self.cli_submit.service_is_ready():
            return
        while self.pending:
            req, cb = self.pending.pop(0)
            self.cli_submit.call_async(req).add_done_callback(lambda f, cb=cb: self._submitted(f, cb))

    # 접수 응답: 수락이면 cb(task_id), 거절이면 오류 로그만(재시도 없음)
    def _submitted(self, fut, cb):
        r = fut.result()
        if r.accepted:
            with self.lock:
                cb(r.task_id)
        else:
            self.get_logger().error(f'task rejected: {r.message}')

    # [수정 2026-11-25] I/F 정의서 v0.2 이름: FleetCommand, /fms/command ->
    # ControlTask, /frybot/tasks/control
    # [수정 2026-11-26] I/F v0.3 최종 판 이름(docstring):
    # /frybot/tasks/control -> /fms/command, ControlTask -> FleetCommand
    def fleet_command(self, cmd, target, arg=''):
        """관제 명령을 /fms/command 로 보낸다. 응답은 보지 않는다.

        Args:
            cmd: FleetCommand 명령 이름(예: CANCEL_TASK).
            target: 대상(로봇 id, 임무 id 등). 문자열로 바꿔 보냄.
            arg: 추가 값. 문자열로 바꿔 보냄.
        """
        # [수정 2026-11-26] I/F v0.3 최종 판 이름: ControlTask -> FleetCommand
        self.cli_fleet.call_async(FleetCommand.Request(
            command=cmd, target=str(target), arg=str(arg)))

    def log(self, event, **f):
        """실행 로그 한 줄을 events.csv 에 쓰고 DB event_log 에도 남긴다.

        Args:
            event: 이벤트 이름.
            **f: events.csv 의 열 값(runlog.COLUMNS).
        """
        row = self.runlog.log(event, **f)
        self.store.event(time.time(), event, row)

    def persist(self, table, row):
        """업무 상태 한 행을 DB 표에 저장(upsert)한다.

        Args:
            table: 표 이름(db.SCHEMA).
            row: 열 이름 -> 값.
        """
        self.store.upsert(table, row)

    # ---------------------------------------------------------------- services (called by the Web Service)
    # 접수: 인원수로 테이블을 배정. (수락, visit_id, table_id, 문구)
    def _check_in(self, req, res):
        with self.lock:
            self.rest.now = time.time()
            res.accepted, res.visit_id, res.table_id, res.message = self.rest.check_in(req.party_size)
        return res

    # 주문: 테이블 번호와 (메뉴 코드, 수량) 목록. (수락, order_id, 문구)
    def _place_order(self, req, res):
        with self.lock:
            self.rest.now = time.time()
            res.accepted, res.order_id, res.message = self.rest.place_order(
                req.table_id, list(zip(req.menu_codes, req.quantities)))
        return res

    # 이용 종료: source 가 비면 'TABLET'(테이블 화면)으로 봄
    def _end_use(self, req, res):
        with self.lock:
            self.rest.now = time.time()
            res.accepted, res.message = self.rest.end_use(req.table_id, req.source or 'TABLET')
        return res

    # 관리자 명령: 먼저 기록. FLEET_CMDS 는 Task Manager 에 동기 호출로
    # 넘겨(서비스 대기 1초, 호출 자체의 시간 제한은 없음) 응답을 그대로
    # 돌려주고, 나머지는 매장 명령으로 처리(모르는 명령이면 실패)
    def _admin(self, req, res):
        self.log('ADMIN', result=req.command, zone_id=req.target, reason=req.arg)
        if req.command in FLEET_CMDS:
            if not self.cli_fleet.wait_for_service(timeout_sec=1.0):
                res.ok, res.message = False, 'task manager is not running'
                return res
            # [수정 2026-11-25] I/F 정의서 v0.2 이름:
            # FleetCommand -> ControlTask
            # [수정 2026-11-26] I/F v0.3 최종 판 이름:
            # ControlTask -> FleetCommand
            r = self.cli_fleet.call(FleetCommand.Request(
                command=req.command, target=req.target, arg=req.arg))
            res.ok, res.message = r.ok, r.message
            return res
        with self.lock:
            self.rest.now = time.time()
            out = self.rest.admin(req.command, req.target, req.arg)
        res.ok, res.message = out if out else (False, f'unknown command {req.command}')
        return res

    # ---------------------------------------------------------------- inputs
    # 임무 이벤트를 업무 모델에 반영하고 EVT_<state> 로 기록(DB 에는 안 씀)
    def _task_event(self, m):
        ev = dict(task_id=m.task_id, task_type=m.task_type, state=m.state, robot_id=m.robot_id, visit_id=m.visit_id,
                  order_id=m.order_id, item_id=m.item_id, table_id=m.table_id, plan_version=m.plan_version, reason=m.reason)
        with self.lock:
            self.rest.now = time.time()
            self.rest.on_task_event(ev)
        self.runlog.log('EVT_' + m.state, task_id=m.task_id, robot_id=m.robot_id, visit_id=m.visit_id or '',
                        order_id=m.order_id or '', zone_id=f'T{m.table_id}' if m.table_id else '',
                        plan_version=m.plan_version, result=m.task_type, reason=m.reason)

    # Task Manager 의 실행 로그(JSON: event, timestamp, 나머지 열)를 그대로
    # events.csv 에 씀. JSON 이 아니면 버림. 'event' 키가 없으면 KeyError
    def _fleet_log(self, m):
        try:
            d = json.loads(m.data)
        except ValueError:
            return
        self.runlog.log(d.pop('event'), timestamp=d.pop('timestamp', None), **d)

    # [수정 2026-11-25] I/F 정의서 v0.2 이름: /frybot/state ->
    # /frybot/central/view_state
    # [수정 2026-11-26] I/F v0.3 최종 판 이름:
    # /frybot/central/view_state -> /frybot/state
    # 0.25초 주기: 업무 시계 진행, 밀린 임무 전송, /frybot/state
    # 발행
    def _tick(self):
        with self.lock:
            self.rest.tick(time.time())
            self._flush()
            snap = self.rest.snapshot()
            guides = self.rest.guiding_visits()
        self._send_guides(guides)
        snap['run_id'] = self.runlog.run_id
        snap['run_dir'] = self.runlog.dir
        snap['ai'] = self.ai_latest
        self.pub_state.publish(String(data=json.dumps(snap, ensure_ascii=False)))

    # [수정 2026-11-24] 손님 고정 목록을 AI 서버로 보냄(_tick 에서 부름)
    def _send_guides(self, guides: dict) -> None:
        """안내 중인 (로봇 -> 방문) 목록을 AI 서버에 보낸다.

        목록이 바뀌었거나 1초가 지났을 때만, 앞선 전송이 끝났을 때만 보낸다.
        전송은 데몬 스레드에서 하여 _tick 을 막지 않는다.

        Args:
            guides: Restaurant.guiding_visits() 결과.
        """
        if self.guides_url in ('', 'none'):
            return
        last, t_last = self.guides_sent
        now = time.time()
        if guides == last and now - t_last < 1.0:
            return
        if self.guides_thread is not None and self.guides_thread.is_alive():
            return
        self.guides_sent = (guides, now)
        if guides != last:
            self.get_logger().info(f'guest lock list -> AI server: {guides}')
        self.guides_thread = threading.Thread(
            target=self._post_guides, args=(guides,), daemon=True)
        self.guides_thread.start()

    def _post_guides(self, guides: dict) -> None:
        """목록 하나를 POST 한다. 실패는 처음 한 번만 경고로 남긴다.

        Args:
            guides: {robot_id: visit_id}.
        """
        req = urllib.request.Request(
            self.guides_url, json.dumps({'guides': guides}).encode(),
            {'Content-Type': 'application/json'})
        try:
            urllib.request.urlopen(req, timeout=0.5).read()
            self.guides_warned = False
        except (urllib.error.URLError, OSError) as e:
            # 실패해도 1초 주기 재전송(_send_guides)으로 다시 보냄
            if not self.guides_warned:
                self.guides_warned = True
                self.get_logger().warn(
                    f'AI server guest lock ({self.guides_url}) failed: {e}')

    # ---------------------------------------------------------------- AI Interface -> Central Control (HTTP)
    # AI 결과 HTTP 서버(전용 스레드에서 끝없이 돎). 경로는 보지 않고
    # POST 본문 JSON 을 _ai_result 로 넘김. 처리 실패는 400
    def _serve_ai(self, port):
        node = self

        class H(BaseHTTPRequestHandler):
            """AI 결과 POST 를 받는 요청 처리기."""

            def do_POST(self):
                """본문 JSON 하나를 처리하고 200, 실패하면 400 을 돌려준다."""
                try:
                    d = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
                    node._ai_result(d)
                    self.send_response(200)
                except Exception as e:  # noqa
                    node.get_logger().warn(f'bad AI result: {e}')
                    self.send_response(400)
                self.end_headers()

            def log_message(self, *a):
                """요청마다 찍히는 접속 로그를 끈다."""
                pass
        try:
            ThreadingHTTPServer(('0.0.0.0', port), H).serve_forever()
        except OSError as e:
            self.get_logger().error(f'AI ingest port {port} unavailable: {e}')

    # AI 결과 한 건 처리(kind 별). 모르는 kind 는 무시. 필수 키가 없으면
    # 예외가 do_POST 로 올라가 400
    def _ai_result(self, d):
        kind = d.get('kind')
        d['received'] = time.time()
        # 의자 QR(천장 카메라): 테이블 이용 종료 판단에 씀
        if kind == 'SEAT_QR':
            with self.lock:
                self.rest.now = time.time()
                self.rest.on_seat_qr(int(d['table_id']), int(d['visible']), int(d['seats']))
            self.ai_latest[f"qr_T{d['table_id']}"] = d
        # [수정 2026-11-17] UR-03: 안내 중인 손님의 동행 상태 (AMR 카메라)
        elif kind == 'GUEST_TRACK':
            # [수정 2026-11-24] 실제 AI 서버(frybot_ai guest_tracker)는
            # visit_id 를 모름. 없으면 그 로봇이 맡은 안내 방문으로 채우고,
            # 안내 중인 방문이 없으면 내보내지 않음(대역 ai_server 는 그대로)
            rid = str(d['robot_id'])
            if 'visit_id' in d:
                vid = int(d['visit_id'])
            else:
                with self.lock:
                    vid = self.rest.guiding_visit(rid)
            if vid:
                self.pub_track.publish(GuestTrack(
                    stamp=self.get_clock().now().to_msg(),
                    robot_id=rid, visit_id=vid,
                    visible=bool(d.get('visible', True)),
                    distance=float(d.get('distance', 0.0))))
            self.ai_latest[f"track_{d['robot_id']}"] = d
        # 튀김 익힘 판정: 바뀐 경우만 DB 에 남기고 Task Manager 로 넘김
        elif kind == 'DONENESS':
            self.ai_latest['doneness'] = d
            self.store.event(time.time(), 'VISION_DONENESS', d) if d.get('changed') else None
            self.pub_ai.publish(String(data=json.dumps(d)))


def main():
    """Central Control 노드를 6 스레드 실행기로 돌린다."""
    rclpy.init()
    n = CentralControl()
    ex = MultiThreadedExecutor(num_threads=6)
    ex.add_node(n)
    try:
        ex.spin()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
