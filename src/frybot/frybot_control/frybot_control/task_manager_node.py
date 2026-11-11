"""Task Manager node (Main Server): wraps FleetCore with ROS 2 actions / topics / services."""
import json
import time

import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from std_msgs.msg import String

from frybot_interfaces.action import ArmJob, NavigateRoute
from frybot_interfaces.msg import RobotStatus, TaskEvent, TrafficGrant, Waypoint
from frybot_interfaces.srv import FleetCommand, SubmitTask

from .fleet_core import FleetCore, FleetIO

QOS = QoSProfile(depth=100, reliability=ReliabilityPolicy.RELIABLE, history=HistoryPolicy.KEEP_LAST)


class TaskManager(Node, FleetIO):
    def __init__(self):
        super().__init__('task_manager')
        p = self.declare_parameter
        self.robot_ids = p('robot_ids', ['pinky1', 'pinky2', 'pinky3']).value
        self.core = FleetCore(self, robot_ids=self.robot_ids, scheduler=p('scheduler', 'hungarian').value,
                              planner=p('planner', 'sipp').value, speed=p('speed', 0.08).value,
                              guide_speed=p('guide_speed', 0.05).value, cook_time_scale=p('cook_time_scale', 20.0).value,
                              stall_timeout=p('stall_timeout', 3.0).value, use_doneness=p('use_doneness', True).value,
                              use_standby=p('use_standby', True).value)
        self.nav = {r: ActionClient(self, NavigateRoute, f'/{r}/navigate_route') for r in self.robot_ids}
        self.arm = {r: ActionClient(self, ArmJob, f'/{r}/arm_job') for r in list(self.robot_ids) + ['cook_arm_a', 'cook_arm_b']}
        self.nav_goal = {}
        self.pub_grant = self.create_publisher(TrafficGrant, '/fms/traffic_grant', QOS)
        self.pub_event = self.create_publisher(TaskEvent, '/fms/task_events', QOS)
        self.pub_state = self.create_publisher(String, '/fms/state', 10)
        self.pub_log = self.create_publisher(String, '/frybot/event_log', QOS)
        self.create_subscription(RobotStatus, '/fleet/robot_status', self._status, 50)
        self.create_subscription(String, '/ai/results', self._ai, 50)
        self.create_service(SubmitTask, '/fms/submit_task', self._submit)
        self.create_service(FleetCommand, '/fms/command', self._command)
        self.create_timer(0.1, self._tick)
        self.create_timer(0.25, self._publish_state)
        self.get_logger().info(f'task manager up: scheduler={self.core.scheduler.name} planner={self.core.planner.name}')

    # ---------------------------------------------------------------- FleetIO
    def send_route(self, rid, task_id, pv, mode, visit_id, steps):
        g = NavigateRoute.Goal(task_id=task_id, robot_id=rid, plan_version=pv, mode=mode, visit_id=int(visit_id))
        for s in steps:
            x, y = self.core.graph.nodes[s.node]
            g.route.append(Waypoint(node_id=s.node, x=x, y=y, not_before=float(s.depart)))
        fut = self.nav[rid].send_goal_async(g, feedback_callback=lambda fb, rid=rid: self.core.on_route_progress(
            rid, fb.feedback.plan_version, fb.feedback.reached_index, fb.feedback.state))
        fut.add_done_callback(lambda f, rid=rid, pv=pv: self._nav_accepted(f, rid, pv))

    def _nav_accepted(self, fut, rid, pv):
        gh = fut.result()
        if not gh.accepted:
            self.core.on_route_result(rid, pv, False, 'REJECTED', -1)
            return
        self.nav_goal[rid] = gh
        gh.get_result_async().add_done_callback(lambda f, rid=rid: self._nav_result(f, rid))

    def _nav_result(self, fut, rid):
        r = fut.result().result
        self.core.on_route_result(rid, r.plan_version, r.success, r.reason, r.reached_index)

    def grant(self, rid, task_id, pv, index):
        self.pub_grant.publish(TrafficGrant(robot_id=rid, task_id=task_id, plan_version=pv, granted_index=index))

    def cancel_route(self, rid):
        gh = self.nav_goal.pop(rid, None)
        if gh is not None:
            gh.cancel_goal_async()

    def arm_job(self, arm_id, task_id, job, duration, params):
        g = ArmJob.Goal(task_id=task_id, arm_id=arm_id, job=job, duration=float(duration), params_json=json.dumps(params))
        fut = self.arm[arm_id].send_goal_async(g)

        def accepted(f):
            gh = f.result()
            if not gh.accepted:
                self.core.on_arm_result(arm_id, task_id, False, 'REJECTED')
                return
            gh.get_result_async().add_done_callback(
                lambda f2: self.core.on_arm_result(arm_id, task_id, f2.result().result.success, f2.result().result.reason))
        fut.add_done_callback(accepted)

    def task_event(self, ev):
        m = TaskEvent(task_id=ev['task_id'], task_type=ev['task_type'], state=ev['state'], robot_id=ev['robot_id'],
                      visit_id=int(ev['visit_id']), order_id=int(ev['order_id']), item_id=int(ev['item_id']),
                      table_id=int(ev['table_id']), plan_version=int(ev['plan_version']), reason=str(ev.get('reason', '')))
        m.stamp = self.get_clock().now().to_msg()
        self.pub_event.publish(m)

    def log(self, event, **f):
        f.update(event=event, timestamp=time.time())
        self.pub_log.publish(String(data=json.dumps(f, ensure_ascii=False, default=str)))

    # ---------------------------------------------------------------- inputs
    def _status(self, m):
        self.core.on_robot_status(m.robot_id, m.x, m.y, m.yaw, m.battery, m.charging, m.state)

    def _ai(self, m):
        try:
            d = json.loads(m.data)
        except ValueError:
            return
        if d.get('kind') == 'DONENESS' and d.get('cook_task_id'):
            self.core.on_doneness(d['cook_task_id'], d['decision'], time.time())

    def _submit(self, req, res):
        try:
            res.task_id = self.core.submit_task(req.task_type, req.visit_id, req.order_id, req.item_id, req.table_id,
                                                req.menu, req.priority)
            res.accepted = True
        except Exception as e:  # noqa
            res.accepted, res.message = False, str(e)
        return res

    def _command(self, req, res):
        res.ok, res.message = self.core.command(req.command, req.target, req.arg)
        return res

    def _tick(self):
        self.core.tick(time.time())

    def _publish_state(self):
        self.pub_state.publish(String(data=json.dumps(self.core.snapshot(), ensure_ascii=False)))


def main():
    rclpy.init()
    n = TaskManager()
    try:
        rclpy.spin(n)
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
