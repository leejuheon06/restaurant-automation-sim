"""Central Control node (Main Server): restaurant state, DB, event log, AI result ingest (HTTP)."""
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import rclpy
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup, ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from std_msgs.msg import String

from frybot_interfaces.msg import TaskEvent
from frybot_interfaces.srv import AdminCommand, CheckIn, EndUse, FleetCommand, PlaceOrder, SubmitTask

from .db import Store
from .restaurant import Restaurant, RestaurantIO
from .runlog import RunLogger

QOS = QoSProfile(depth=100, reliability=ReliabilityPolicy.RELIABLE, history=HistoryPolicy.KEEP_LAST)
FLEET_CMDS = ('ESTOP', 'RESUME', 'REASSIGN', 'CANCEL_TASK', 'RETRY_TASK', 'SET_SCHEDULER', 'SET_PLANNER', 'SET_STANDBY')


class CentralControl(Node, RestaurantIO):
    def __init__(self):
        super().__init__('central_control')
        p = self.declare_parameter
        self.runlog = RunLogger(p('run_dir', '~/frybot_ws/runs').value, p('run_id', '').value or None,
                                manifest=dict(scenario=p('scenario', 'interactive').value, map_version='frybot_200x100_v1',
                                              robots=['pinky1', 'pinky2', 'pinky3'], simulation=True))
        self.store = Store(os.path.join(self.runlog.dir, 'frybot.db'))
        self.lock = threading.RLock()
        self.pending = []                       # SubmitTask requests waiting for the task manager
        self.ai_latest = {}
        self.rest = Restaurant(self, qr_vacant_sec=p('qr_vacant_sec', 8.0).value)
        self.rest.now = time.time()
        g_srv, g_cli, g_main = ReentrantCallbackGroup(), ReentrantCallbackGroup(), MutuallyExclusiveCallbackGroup()
        self.cli_submit = self.create_client(SubmitTask, '/fms/submit_task', callback_group=g_cli)
        self.cli_fleet = self.create_client(FleetCommand, '/fms/command', callback_group=g_cli)
        self.create_service(CheckIn, '/frybot/check_in', self._check_in, callback_group=g_srv)
        self.create_service(PlaceOrder, '/frybot/place_order', self._place_order, callback_group=g_srv)
        self.create_service(EndUse, '/frybot/end_use', self._end_use, callback_group=g_srv)
        self.create_service(AdminCommand, '/frybot/admin', self._admin, callback_group=g_srv)
        self.create_subscription(TaskEvent, '/fms/task_events', self._task_event, QOS, callback_group=g_main)
        self.create_subscription(String, '/frybot/event_log', self._fleet_log, QOS, callback_group=g_main)
        self.pub_state = self.create_publisher(String, '/frybot/state', 10)
        self.pub_ai = self.create_publisher(String, '/ai/results', 50)
        self.create_timer(0.25, self._tick, callback_group=g_main)
        port = p('ai_http_port', 8100).value
        threading.Thread(target=self._serve_ai, args=(port,), daemon=True).start()
        self.get_logger().info(f'central control up. run folder: {self.runlog.dir}  (AI ingest http://127.0.0.1:{port}/ai/result)')

    # ---------------------------------------------------------------- RestaurantIO
    def submit_task(self, cb, **kw):
        self.pending.append((SubmitTask.Request(**{k: v for k, v in kw.items()}), cb))
        self._flush()

    def _flush(self):
        if not self.cli_submit.service_is_ready():
            return
        while self.pending:
            req, cb = self.pending.pop(0)
            self.cli_submit.call_async(req).add_done_callback(lambda f, cb=cb: self._submitted(f, cb))

    def _submitted(self, fut, cb):
        r = fut.result()
        if r.accepted:
            with self.lock:
                cb(r.task_id)
        else:
            self.get_logger().error(f'task rejected: {r.message}')

    def fleet_command(self, cmd, target, arg=''):
        self.cli_fleet.call_async(FleetCommand.Request(command=cmd, target=str(target), arg=str(arg)))

    def log(self, event, **f):
        row = self.runlog.log(event, **f)
        self.store.event(time.time(), event, row)

    def persist(self, table, row):
        self.store.upsert(table, row)

    # ---------------------------------------------------------------- services (called by the Web Service)
    def _check_in(self, req, res):
        with self.lock:
            self.rest.now = time.time()
            res.accepted, res.visit_id, res.table_id, res.message = self.rest.check_in(req.party_size)
        return res

    def _place_order(self, req, res):
        with self.lock:
            self.rest.now = time.time()
            res.accepted, res.order_id, res.message = self.rest.place_order(
                req.table_id, list(zip(req.menu_codes, req.quantities)))
        return res

    def _end_use(self, req, res):
        with self.lock:
            self.rest.now = time.time()
            res.accepted, res.message = self.rest.end_use(req.table_id, req.source or 'TABLET')
        return res

    def _admin(self, req, res):
        self.log('ADMIN', result=req.command, zone_id=req.target, reason=req.arg)
        if req.command in FLEET_CMDS:
            if not self.cli_fleet.wait_for_service(timeout_sec=1.0):
                res.ok, res.message = False, 'task manager is not running'
                return res
            r = self.cli_fleet.call(FleetCommand.Request(command=req.command, target=req.target, arg=req.arg))
            res.ok, res.message = r.ok, r.message
            return res
        with self.lock:
            self.rest.now = time.time()
            out = self.rest.admin(req.command, req.target, req.arg)
        res.ok, res.message = out if out else (False, f'unknown command {req.command}')
        return res

    # ---------------------------------------------------------------- inputs
    def _task_event(self, m):
        ev = dict(task_id=m.task_id, task_type=m.task_type, state=m.state, robot_id=m.robot_id, visit_id=m.visit_id,
                  order_id=m.order_id, item_id=m.item_id, table_id=m.table_id, plan_version=m.plan_version, reason=m.reason)
        with self.lock:
            self.rest.now = time.time()
            self.rest.on_task_event(ev)
        self.runlog.log('EVT_' + m.state, task_id=m.task_id, robot_id=m.robot_id, visit_id=m.visit_id or '',
                        order_id=m.order_id or '', zone_id=f'T{m.table_id}' if m.table_id else '',
                        plan_version=m.plan_version, result=m.task_type, reason=m.reason)

    def _fleet_log(self, m):
        try:
            d = json.loads(m.data)
        except ValueError:
            return
        self.runlog.log(d.pop('event'), timestamp=d.pop('timestamp', None), **d)

    def _tick(self):
        with self.lock:
            self.rest.tick(time.time())
            self._flush()
            snap = self.rest.snapshot()
        snap['run_id'] = self.runlog.run_id
        snap['run_dir'] = self.runlog.dir
        snap['ai'] = self.ai_latest
        self.pub_state.publish(String(data=json.dumps(snap, ensure_ascii=False)))

    # ---------------------------------------------------------------- AI Interface -> Central Control (HTTP)
    def _serve_ai(self, port):
        node = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                try:
                    d = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
                    node._ai_result(d)
                    self.send_response(200)
                except Exception as e:  # noqa
                    node.get_logger().warn(f'bad AI result: {e}')
                    self.send_response(400)
                self.end_headers()

            def log_message(self, *a):
                pass
        try:
            ThreadingHTTPServer(('0.0.0.0', port), H).serve_forever()
        except OSError as e:
            self.get_logger().error(f'AI ingest port {port} unavailable: {e}')

    def _ai_result(self, d):
        kind = d.get('kind')
        d['received'] = time.time()
        if kind == 'SEAT_QR':
            with self.lock:
                self.rest.now = time.time()
                self.rest.on_seat_qr(int(d['table_id']), int(d['visible']), int(d['seats']))
            self.ai_latest[f"qr_T{d['table_id']}"] = d
        elif kind == 'DONENESS':
            self.ai_latest['doneness'] = d
            self.store.event(time.time(), 'VISION_DONENESS', d) if d.get('changed') else None
            self.pub_ai.publish(String(data=json.dumps(d)))


def main():
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
