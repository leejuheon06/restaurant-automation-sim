"""Task Manager node (Main Server): wraps FleetCore with ROS 2 actions / topics / services."""
import json
import time

import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from std_msgs.msg import String

from frybot_interfaces.action import ArmJob, NavigateRoute
# [수정 2026-11-25] I/F 정의서 v0.2 이름: TaskEvent·FleetCommand ->
# TaskProgress·ControlTask
# [수정 2026-11-26] I/F v0.3 최종 판 이름: TaskProgress -> TaskEvent
from frybot_interfaces.msg import (ArmStatus, FleetHeartbeat, RobotStatus,
                                   TaskEvent, TrafficGrant, Waypoint)
# [수정 2026-11-26] I/F v0.3 최종 판 이름: ControlTask -> FleetCommand
from frybot_interfaces.srv import FleetCommand, SubmitTask

from .fleet_core import FleetCore, FleetIO
# [수정 2026-11-18] P1(D1): 지도 이름 없이 뜨지 않음
from .map_catalog import require_map_id

# 놓치면 안 되는 메시지용 QoS(README 의 EVENT): reliable, volatile, 깊이 100
QOS = QoSProfile(depth=100, reliability=ReliabilityPolicy.RELIABLE, history=HistoryPolicy.KEEP_LAST)


class TaskManager(Node, FleetIO):
    """Task Manager ROS 노드: FleetCore 의 입력·출력을 ROS 통신으로 잇는다.

    FleetIO 를 구현해 관제 코어의 경로·허가·팔 작업·이벤트를 액션과
    토픽으로 내보내고, 로봇 상태·AI 결과·서비스 요청을 코어에 넣는다.

    Raises:
        RuntimeError: FRYBOT_MAP_ID 가 없을 때(require_map_id).
    """

    def __init__(self):
        super().__init__('task_manager')
        require_map_id('task_manager')
        p = self.declare_parameter
        # [수정 2026-11-18] P1: 노드 기본값을 실기기 값으로(robot_ids 는
        # real.launch.py 의 등록 없음 기본과 같은 pinky1, use_standby 끔,
        # auto_home 켬). 시뮬 런치가 예전 값을 명시함. FleetCore 기본값은
        # 그대로(오프라인 도구가 씀)
        self.robot_ids = p('robot_ids', ['pinky1']).value  # 관제할 AMR 이름
        self.core = FleetCore(self, robot_ids=self.robot_ids, scheduler=p('scheduler', 'min_cost_eta_rh').value,
                              planner=p('planner', 'sipp').value, speed=p('speed', 0.08).value,
                              guide_speed=p('guide_speed', 0.05).value, cook_time_scale=p('cook_time_scale', 20.0).value,
                              stall_timeout=p('stall_timeout', 3.0).value, use_doneness=p('use_doneness', True).value,
                              use_standby=p('use_standby', False).value, prefer_yield=p('prefer_yield', True).value,
                              route_retries=p('route_retries', 2).value,
                              # [수정 2026-11-17] 기동 후 출발 노드 자동 이동
                              # (실측 지도에서만 동작)
                              # [수정 2026-11-18] P1: 기본 켬(실기기 값)
                              auto_home=p('auto_home', True).value,
                              # [수정 2026-11-18] W6: 계획의 구간 지연(초)
                              plan_overhead=p('plan_overhead', 0.0).value,
                              # [수정 2026-11-20] T-47: 서빙 팔을 올린 로봇
                              # (쉼표로 구분, 비면 모든 로봇)
                              serving_robots=[
                                  s.strip() for s in
                                  p('serving_robots', '').value.split(',')
                                  if s.strip()])
        self.session = f'{int(time.time()):x}'       # tells the robots when the Task Manager has been restarted
        # 로봇마다 경로 실행 액션 클라이언트(/<robot>/navigate_route)
        self.nav = {r: ActionClient(self, NavigateRoute, f'/{r}/navigate_route') for r in self.robot_ids}
        # [수정 2026-11-17] SW 아키텍처 v016: 조리 팔 작업은 팔마다 따로 보내지
        # 않고 FrybotArm Master Controller(frybot_arm) 한 곳으로 보냄.
        # 서빙 팔은 전처럼 로봇마다 /<robot>/arm_job
        self.arm = {r: ActionClient(self, ArmJob, f'/{r}/arm_job')
                    for r in self.robot_ids}
        cook = ActionClient(self, ArmJob, '/frybot_arm/arm_job')
        self.arm.update({a: cook for a in ('cook_arm_a', 'cook_arm_b')})
        self.nav_goal = {}  # 로봇 -> (plan_version, 수락된 목표 핸들)
        self.nav_sent, self.nav_void = {}, set()     # newest plan version sent per robot / goals canceled before acceptance
        self.arm_goal = {}  # 팔 이름 -> 진행 중인 팔 작업 목표 핸들
        # 출력 토픽: 생존 신호(5 Hz), 통행 허가, 임무 이벤트, 화면 상태,
        # 실행 로그
        self.pub_beat = self.create_publisher(FleetHeartbeat, '/fms/heartbeat', 10)
        self.pub_grant = self.create_publisher(TrafficGrant, '/fms/traffic_grant', QOS)
        # [수정 2026-11-25] I/F 정의서 v0.2 이름: TaskEvent, /fms/task_events
        # -> TaskProgress, /frybot/tasks/progress
        # [수정 2026-11-26] I/F v0.3 최종 판 이름: TaskProgress -> TaskEvent,
        # /frybot/tasks/progress -> /fms/task_events
        self.pub_event = self.create_publisher(
            TaskEvent, '/fms/task_events', QOS)
        self.pub_state = self.create_publisher(String, '/fms/state', 10)
        self.pub_log = self.create_publisher(String, '/frybot/event_log', QOS)
        # 입력: 로봇 상태(10 Hz), central_control 이 넘기는 AI 결과(JSON)
        self.create_subscription(RobotStatus, '/fleet/robot_status', self._status, 50)
        self.create_subscription(String, '/ai/results', self._ai, 50)
        # [수정 2026-11-17] UR-17, 19: 로봇팔(조리 팔, 서빙 팔)의 상태·오류 보고
        self.create_subscription(
            ArmStatus, '/fleet/arm_status',
            lambda m: self.core.on_arm_status(
                m.arm_id, m.state, m.job, m.task_id, m.error), 20)
        # central_control 이 부르는 서비스: 임무 접수, 관리자 명령
        # [수정 2026-11-25] I/F 정의서 v0.2 이름: /fms/submit_task ->
        # /frybot/tasks/submit, FleetCommand /fms/command -> ControlTask
        # /frybot/tasks/control
        # [수정 2026-11-26] I/F v0.3 최종 판 이름:
        # /frybot/tasks/submit -> /fms/submit_task
        self.create_service(SubmitTask, '/fms/submit_task', self._submit)
        # [수정 2026-11-26] I/F v0.3 최종 판 이름: ControlTask -> FleetCommand,
        # /frybot/tasks/control -> /fms/command
        self.create_service(FleetCommand, '/fms/command', self._command)
        # 주기: 코어 계산 0.1초, 화면 상태 0.25초, 생존 신호 0.2초,
        # 허가 재발행 0.5초(모두 같은 단일 스레드 실행기에서 돎)
        self.create_timer(0.1, self._tick)
        self.create_timer(0.25, self._publish_state)
        self.create_timer(0.2, self._heartbeat)
        self.create_timer(0.5, self._regrant)
        self.get_logger().info(f'task manager up: scheduler={self.core.scheduler.name} planner={self.core.planner.name}')
        # [수정 2026-11-20] T-47: 서빙 임무를 받는 로봇을 기동 로그에 남김
        self.get_logger().info(
            'serving robots (SERVE, COLLECT): '
            f'{sorted(self.core.serving_robots) or "all"}')

    # ---------------------------------------------------------------- FleetIO
    def send_route(self, rid, task_id, pv, mode, visit_id, steps):
        """경로를 NavigateRoute 목표로 로봇에 보낸다(FleetIO).

        Args:
            rid: 로봇 이름.
            task_id: 임무 번호(임무 없는 이동은 관제가 정한 값).
            pv: 경로 번호(plan_version).
            mode: NORMAL / GUIDE / YIELD.
            visit_id: 손님 안내면 방문 번호, 아니면 0.
            steps: 노드(node)와 출발 예정 시각(depart)을 가진 경로 단계 목록.
        """
        g = NavigateRoute.Goal(task_id=task_id, robot_id=rid, plan_version=pv, mode=mode, visit_id=int(visit_id))
        for s in steps:
            x, y = self.core.graph.nodes[s.node]
            g.route.append(Waypoint(node_id=s.node, x=x, y=y, not_before=float(s.depart)))
        self.nav_sent[rid] = pv
        fut = self.nav[rid].send_goal_async(g, feedback_callback=lambda fb, rid=rid: self.core.on_route_progress(
            rid, fb.feedback.plan_version, fb.feedback.reached_index))
        fut.add_done_callback(lambda f, rid=rid, pv=pv: self._nav_accepted(f, rid, pv))

    # 경로 목표의 수락 결과: 거절은 REJECTED 실패로 코어에 알리고, 수락 전에
    # 취소된 목표는 바로 취소, 가장 최근 목표면 핸들을 기억
    def _nav_accepted(self, fut, rid, pv):
        gh = fut.result()
        if not gh.accepted:
            self.nav_void.discard((rid, pv))
            self.core.on_route_result(rid, pv, False, 'REJECTED', -1)
            return
        if (rid, pv) in self.nav_void:               # canceled (e.g. emergency stop) before the robot accepted it
            self.nav_void.discard((rid, pv))
            gh.cancel_goal_async()
            return
        if self.nav_sent.get(rid) == pv:
            self.nav_goal[rid] = (pv, gh)
        gh.get_result_async().add_done_callback(lambda f, rid=rid: self._nav_result(f, rid))

    # 경로 실행이 끝난 결과(성공 여부, 사유, 마지막 도달 순번)를 코어로
    def _nav_result(self, fut, rid):
        r = fut.result().result
        self.core.on_route_result(rid, r.plan_version, r.success, r.reason, r.reached_index)

    def grant(self, rid, task_id, pv, index):
        """통행 허가를 발행한다(FleetIO). 로봇은 index 번째 노드까지 간다.

        Args:
            rid: 로봇 이름.
            task_id: 임무 번호(기록용).
            pv: 경로 번호.
            index: 허가한 마지막 경로 순번(granted_index).
        """
        self.pub_grant.publish(TrafficGrant(robot_id=rid, task_id=task_id, plan_version=pv, granted_index=index))

    def cancel_route(self, rid):
        """로봇의 경로 목표를 취소한다(FleetIO).

        아직 수락되지 않은 최신 목표는 nav_void 에 넣어 수락되는 즉시 취소한다.

        Args:
            rid: 로봇 이름.
        """
        pv, gh = self.nav_goal.pop(rid, (None, None))
        if gh is not None:
            gh.cancel_goal_async()
        sent = self.nav_sent.get(rid)
        if sent is not None and sent != pv:          # the newest goal has no handle yet: cancel it once it is accepted
            self.nav_void.add((rid, sent))

    def cancel_arm(self, arm_id):
        """진행 중인 팔 작업을 취소한다(FleetIO). 수락 전이면 아무것도 안 한다.

        Args:
            arm_id: 팔 이름(로봇 이름 또는 cook_arm_a, cook_arm_b).
        """
        gh = self.arm_goal.pop(arm_id, None)
        if gh is not None:
            gh.cancel_goal_async()

    def _heartbeat(self):
        """Liveness + emergency-stop channel: robots stop when this goes silent, and hold while they are listed."""
        self.pub_beat.publish(FleetHeartbeat(stamp=self.get_clock().now().to_msg(), session=self.session,
                                             estop=self.core.estopped()))

    def _regrant(self):
        """Repeat the current permission of every active route (a lost message must not park a robot for ever)."""
        for rid, task_id, pv, index in self.core.active_grants():
            self.pub_grant.publish(TrafficGrant(robot_id=rid, task_id=task_id, plan_version=pv, granted_index=index))

    def arm_job(self, arm_id, task_id, job, duration, params):
        """팔 작업을 ArmJob 목표로 보낸다(FleetIO).

        서빙 팔은 /<robot>/arm_job, 조리 팔 둘은 /frybot_arm/arm_job 으로 간다.
        거절·결과는 코어의 on_arm_result 로 알린다.

        Args:
            arm_id: 팔 이름.
            task_id: 임무 번호.
            job: 작업 이름(LOAD 등).
            duration: 작업 시간(초).
            params: params_json 으로 보낼 dict.
        """
        g = ArmJob.Goal(task_id=task_id, arm_id=arm_id, job=job, duration=float(duration), params_json=json.dumps(params))
        fut = self.arm[arm_id].send_goal_async(g)

        def accepted(f):
            gh = f.result()
            if not gh.accepted:
                self.core.on_arm_result(arm_id, task_id, False, 'REJECTED')
                return
            self.arm_goal[arm_id] = gh

            # 결과가 사유 없이 실패면 CANCELED 로 봄
            def done(f2):
                if self.arm_goal.get(arm_id) is gh:
                    del self.arm_goal[arm_id]
                r = f2.result().result
                self.core.on_arm_result(arm_id, task_id, r.success, r.reason or ('' if r.success else 'CANCELED'))
            gh.get_result_async().add_done_callback(done)
        fut.add_done_callback(accepted)

    # [수정 2026-11-26] I/F v0.3 최종 판 이름(docstring):
    # /frybot/tasks/progress -> /fms/task_events, TaskProgress -> TaskEvent
    def task_event(self, ev):
        """임무 상태 변화를 /fms/task_events 로 보낸다(FleetIO).

        [수정 2026-11-25] I/F 정의서 v0.2 이름: TaskEvent, /fms/task_events
        -> TaskProgress, /frybot/tasks/progress
        [수정 2026-11-26] I/F v0.3 최종 판 이름: 다시 TaskEvent,
        /fms/task_events

        Args:
            ev: 임무 이벤트 dict(task_id, task_type, state, robot_id 등).
        """
        # [수정 2026-11-25] I/F 정의서 v0.2 이름: TaskEvent -> TaskProgress
        # [수정 2026-11-26] I/F v0.3 최종 판 이름: TaskProgress -> TaskEvent
        m = TaskEvent(
            task_id=ev['task_id'], task_type=ev['task_type'],
            state=ev['state'], robot_id=ev['robot_id'],
            visit_id=int(ev['visit_id']), order_id=int(ev['order_id']),
            item_id=int(ev['item_id']), table_id=int(ev['table_id']),
            plan_version=int(ev['plan_version']),
            reason=str(ev.get('reason', '')))
        m.stamp = self.get_clock().now().to_msg()
        self.pub_event.publish(m)

    def log(self, event, **f):
        """실행 로그 한 줄을 JSON 으로 /frybot/event_log 에 보낸다(FleetIO).

        central_control 이 받아 events.csv 와 DB 에 쓴다.

        Args:
            event: 이벤트 이름.
            **f: runlog.COLUMNS 의 열 값.
        """
        f.update(event=event, timestamp=time.time())
        self.pub_log.publish(String(data=json.dumps(f, ensure_ascii=False, default=str)))

    # ---------------------------------------------------------------- inputs
    # 로봇 상태 보고(/fleet/robot_status)를 코어로
    def _status(self, m):
        self.core.on_robot_status(m.robot_id, m.x, m.y, m.yaw, m.battery, m.charging, m.state, m.error)

    # AI 결과 중 익힘 판정(DONENESS)만 코어로 넘김. 다른 kind 는 무시
    def _ai(self, m):
        try:
            d = json.loads(m.data)
        except ValueError:
            return
        if d.get('kind') == 'DONENESS' and d.get('cook_task_id'):
            self.core.on_doneness(d['cook_task_id'], d['decision'], time.time())

    # 임무 접수 서비스: 코어가 거절(예외)하면 accepted=False 와 사유
    def _submit(self, req, res):
        try:
            res.task_id = self.core.submit_task(req.task_type, req.visit_id, req.order_id, req.item_id, req.table_id,
                                                req.menu, req.priority)
            res.accepted = True
        except Exception as e:  # noqa
            res.accepted, res.message = False, str(e)
        return res

    # 관제 명령 서비스(ESTOP, MOVE_TO_VERTEX 등): 코어의 (ok, message)
    def _command(self, req, res):
        res.ok, res.message = self.core.command(req.command, req.target, req.arg)
        return res

    # 코어 주기 계산(배정, 계획, 허가). 시각은 벽시계(unix 초)
    def _tick(self):
        self.core.tick(time.time())

    # 화면용 관제 상태(JSON)
    def _publish_state(self):
        self.pub_state.publish(String(data=json.dumps(self.core.snapshot(), ensure_ascii=False)))


def main():
    """task_manager 명령의 진입점. Ctrl+C 까지 노드를 돌린다."""
    rclpy.init()
    n = TaskManager()
    try:
        rclpy.spin(n)
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
