"""One simulated AMR (Pinky Pro + serving arm).  Components from the SW architecture:
AMR Controller (NavigateRoute action, status), OneTeamNavigator (waypoint driving), Arm Controller (ArmJob action),
Camera Streamer (UDP).
  drive:=kinematic  moves the pose directly (lightweight simulation)
  drive:=nav2       every granted roadmap segment is a Nav2 NavigateToPose goal (global + local costmap, lidar)
  drive:=cmd_vel    straight-line cmd_vel/odom driving without costmaps (kept for comparison)
"""
import json
import math
import threading
import time

import rclpy
from geometry_msgs.msg import TransformStamped, Twist
from nav_msgs.msg import Odometry
from nav2_msgs.action import NavigateToPose
from nav2_msgs.srv import ClearEntireCostmap
from rclpy.action import ActionClient
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import JointState
from std_msgs.msg import String
from tf2_msgs.msg import TFMessage
from tf2_ros import TransformBroadcaster

from frybot_control.layout import Graph
from frybot_interfaces.action import ArmJob, NavigateRoute
from frybot_interfaces.msg import RobotStatus, TrafficGrant

from .arm_common import JOINTS, REST, CameraStreamer, arm_pose

QOS = QoSProfile(depth=100, reliability=ReliabilityPolicy.RELIABLE, history=HistoryPolicy.KEEP_LAST)


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


class Amr(Node):
    def __init__(self):
        super().__init__('amr')
        p = self.declare_parameter
        self.rid = p('robot_id', 'pinky1').value
        self.speed, self.guide_speed = p('speed', 0.08).value, p('guide_speed', 0.05).value
        self.turn_rate = p('turn_rate', 2.5).value
        self.drive = p('drive', 'kinematic').value
        self.follow_dist, self.resume_dist = p('follow_pause_dist', 0.30).value, p('follow_resume_dist', 0.22).value
        self.guest_timeout = p('guest_timeout', 20.0).value
        g = Graph()
        idx = int(self.rid[-1]) - 1 if self.rid[-1].isdigit() else 0
        self.home = g.pos(['CH1', 'CH2', 'CH3'][idx % 3])
        self.x, self.y, self.yaw = self.home[0], self.home[1], 0.0
        self.spawn = (self.x, self.y)
        self.battery, self.charging = p('battery', 100.0).value, False
        self.cur, self.grants = None, {}
        self.pv, self.reached, self.task_id, self.nav_state = 0, -1, '', 'IDLE'
        self.arm_state, self.arm_q, self.wheel = 'IDLE', list(REST), 0.0
        self.guests = {}
        self.lock = threading.Lock()
        cb = ReentrantCallbackGroup()
        self.tf = TransformBroadcaster(self)
        self.pub_status = self.create_publisher(RobotStatus, '/fleet/robot_status', 50)
        self.pub_js = self.create_publisher(JointState, f'/{self.rid}/joint_states', 10)
        self.pub_arm_js = self.create_publisher(JointState, f'/{self.rid}/arm/joint_states', 10)
        self.pub_cmd = self.create_publisher(Twist, f'/{self.rid}/cmd_vel', 10)
        self.create_subscription(TrafficGrant, '/fms/traffic_grant', self._grant, QOS, callback_group=cb)
        self.create_subscription(String, '/sim/world_state', self._world, 10, callback_group=cb)
        self.n2 = dict(key=None, state='', handle=None, t_fail=0.0, fails=0)
        if self.drive == 'nav2':
            self.nav2 = ActionClient(self, NavigateToPose, f'/{self.rid}/navigate_to_pose', callback_group=cb)
            self.clear_local = self.create_client(ClearEntireCostmap, f'/{self.rid}/local_costmap/clear_entirely_local_costmap',
                                                  callback_group=cb)
        self.odom, self.have_truth = (0.0, 0.0, 0.0), False
        if self.drive in ('cmd_vel', 'nav2'):
            self.create_subscription(TFMessage, '/gz/model_poses', self._gz_pose, 20, callback_group=cb)
            self.create_subscription(Odometry, f'/{self.rid}/odom', self._odom, 20, callback_group=cb)
        ActionServer(self, NavigateRoute, f'/{self.rid}/navigate_route', execute_callback=self._navigate,
                     goal_callback=lambda g_: GoalResponse.ACCEPT, cancel_callback=lambda g_: CancelResponse.ACCEPT,
                     handle_accepted_callback=self._accepted, callback_group=cb)
        ActionServer(self, ArmJob, f'/{self.rid}/arm_job', execute_callback=self._arm_job, callback_group=cb)
        if self.drive == 'nav2':
            self.create_timer(1.0, self._refresh_costmap, callback_group=cb)
        self.cam = CameraStreamer(f'{self.rid}_front', port=p('ai_udp_port', 9100).value)
        self.create_timer(0.1, self._publish, callback_group=cb)
        self.create_timer(1.0, lambda: self.cam.send('amr', robot_id=self.rid, x=self.x, y=self.y), callback_group=cb)
        self.get_logger().info(f'{self.rid} ready at ({self.x:.2f}, {self.y:.2f}) drive={self.drive}')

    # ------------------------------------------------------------ inputs
    def _grant(self, m):
        if m.robot_id == self.rid:
            self.grants[m.plan_version] = max(self.grants.get(m.plan_version, 0), m.granted_index)

    def _world(self, m):
        try:
            self.guests = json.loads(m.data).get('guests', {})
        except ValueError:
            pass

    def _odom(self, m):
        p, q = m.pose.pose.position, m.pose.pose.orientation
        self.odom = (p.x, p.y, math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z)))
        if not self.have_truth:                    # no localisation source: dead reckoning from the start pose
            self.x, self.y, self.yaw = self.spawn[0] + p.x, self.spawn[1] + p.y, self.odom[2]

    def _gz_pose(self, m):
        """Localisation in Gazebo: the simulator's true model pose (stands in for AMCL). Wheel odometry alone drifts
        badly here because the wheels slip, so map -> odom is corrected from this pose on every update."""
        for t in m.transforms:
            if t.child_frame_id == self.rid:
                q = t.transform.rotation
                self.x, self.y = t.transform.translation.x, t.transform.translation.y
                self.yaw = math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
                self.have_truth = True
                ox, oy, oyaw = self.odom
                dyaw = wrap(self.yaw - oyaw)
                c, s_ = math.cos(dyaw), math.sin(dyaw)
                tf = TransformStamped()
                tf.header.stamp = self.get_clock().now().to_msg()
                tf.header.frame_id, tf.child_frame_id = 'map', f'{self.rid}/odom'
                tf.transform.translation.x = self.x - (c * ox - s_ * oy)
                tf.transform.translation.y = self.y - (s_ * ox + c * oy)
                tf.transform.rotation.z, tf.transform.rotation.w = math.sin(dyaw / 2), math.cos(dyaw / 2)
                if self.drive == 'nav2':
                    self.tf.sendTransform(tf)
                return

    # ------------------------------------------------------------ NavigateRoute (GuideGuest when mode == GUIDE)
    def _accepted(self, gh):
        with self.lock:
            self.cur = gh                 # a newer plan pre-empts the running one
        gh.execute()

    def _navigate(self, gh):
        goal = gh.request
        route, pv, guide = goal.route, goal.plan_version, goal.mode == 'GUIDE'
        self.pv, self.task_id = pv, goal.task_id
        res = NavigateRoute.Result(plan_version=pv)
        reached = 0 if route and math.hypot(route[0].x - self.x, route[0].y - self.y) < 0.012 else -1
        self.reached = reached
        self._fb(gh, pv, reached, 'ACCEPTED')
        dt, lost_since = 0.05, None
        while rclpy.ok():
            if gh is not self.cur or gh.is_cancel_requested:
                self._stop()
                res.reached_index, res.reason = reached, 'CANCELED' if gh.is_cancel_requested else 'PREEMPTED'
                if gh.is_cancel_requested:
                    gh.canceled()
                    self.nav_state = 'IDLE'
                else:
                    gh.abort()
                return res
            if reached >= len(route) - 1:
                break
            tgt = reached + 1
            if tgt > 0 and tgt > self.grants.get(pv, 0):          # wait for the traffic permission
                self._stop()
                self.nav_state = 'WAIT_GRANT'
                time.sleep(dt)
                continue
            if guide and tgt > 0:
                gpos = self.guests.get(str(goal.visit_id))
                if gpos is not None:
                    d = math.hypot(gpos['x'] - self.x, gpos['y'] - self.y)
                    limit = self.resume_dist if self.nav_state == 'PAUSED_GUEST' else self.follow_dist
                    if d > limit:                                 # SR-007: guest fell behind -> stop and wait
                        self._stop()
                        if self.nav_state != 'PAUSED_GUEST':
                            self.nav_state, lost_since = 'PAUSED_GUEST', time.time()
                            self._fb(gh, pv, reached, 'PAUSED_GUEST')
                        if time.time() - lost_since > self.guest_timeout:    # SR-008
                            res.reached_index, res.reason = reached, 'GUEST_LOST'
                            self.nav_state = 'IDLE'
                            gh.abort()
                            return res
                        time.sleep(dt)
                        continue
            self.nav_state = 'MOVING'
            if self.drive == 'nav2':
                done = self._nav2_segment((pv, tgt), route[tgt].x, route[tgt].y)
            else:
                done = self._step_toward(route[tgt].x, route[tgt].y, guide and tgt > 0, dt)
            if done:
                reached = self.reached = tgt
                self._fb(gh, pv, reached, 'MOVING')
            time.sleep(dt)
        self._stop()
        self.nav_state = 'IDLE'
        res.success, res.reached_index, res.reason = True, reached, 'OK'
        gh.succeed()
        return res

    def _fb(self, gh, pv, reached, state):
        gh.publish_feedback(NavigateRoute.Feedback(plan_version=pv, reached_index=reached, state=state))

    def _step_toward(self, tx, ty, reverse, dt):
        """Navigator: turn in place, then drive straight. reverse=True drives backwards (facing the guest)."""
        dx, dy = tx - self.x, ty - self.y
        d = math.hypot(dx, dy)
        v = self.guide_speed if reverse else self.speed
        tol = 0.004 if self.drive == 'kinematic' else 0.015
        if d <= max(tol, v * dt if self.drive == 'kinematic' else 0):
            if self.drive == 'kinematic':
                self.x, self.y = tx, ty
            return True
        want = wrap(math.atan2(dy, dx) + (math.pi if reverse else 0.0))
        err = wrap(want - self.yaw)
        if self.drive == 'kinematic':
            if abs(err) > 0.05:
                self.yaw = wrap(self.yaw + max(-self.turn_rate * dt, min(self.turn_rate * dt, err)))
            else:
                self.yaw = want
                self.x += dx / d * v * dt
                self.y += dy / d * v * dt
                self.wheel += (-1 if reverse else 1) * v * dt / 0.028
                self.battery = max(0.0, self.battery - 0.02 * dt)
        else:
            cmd = Twist()
            if abs(err) > 0.2:
                cmd.angular.z = max(-1.5, min(1.5, 2.5 * err))
            else:
                cmd.linear.x = (-v if reverse else v) * min(1.0, d / 0.03 + 0.3)
                cmd.angular.z = 2.0 * err
            self.pub_cmd.publish(cmd)
        return False

    def _stop(self):
        if self.drive == 'cmd_vel':
            self.pub_cmd.publish(Twist())
        elif self.drive == 'nav2':
            self._nav2_cancel()

    # ------------------------------------------------------------ Nav2 segment driving
    def _nav2_segment(self, key, tx, ty):
        """Drive to one granted roadmap node with Nav2. Returns True once the node is reached."""
        n = self.n2
        if n['key'] != key:
            if not self.nav2.server_is_ready():
                self.nav_state = 'WAIT_NAV2'
                return False
            if n['state'] == 'FAILED' and time.time() - n['t_fail'] < 1.0:
                return False
            # The simulated lidar sometimes returns only invalid ranges; marks from earlier scans would then never
            # be ray-traced away. Start every segment from an empty local costmap that the next scans refill.
            if self.clear_local.service_is_ready():
                self.clear_local.call_async(ClearEntireCostmap.Request())
            g = NavigateToPose.Goal()
            g.pose.header.frame_id = 'map'
            g.pose.header.stamp = self.get_clock().now().to_msg()
            g.pose.pose.position.x, g.pose.pose.position.y = float(tx), float(ty)
            yaw = math.atan2(ty - self.y, tx - self.x)
            g.pose.pose.orientation.z, g.pose.pose.orientation.w = math.sin(yaw / 2), math.cos(yaw / 2)
            n.update(key=key, state='ACTIVE', handle=None)
            self.nav2.send_goal_async(g).add_done_callback(lambda f, key=key: self._nav2_accepted(f, key))
            return False
        if n['state'] == 'SUCCEEDED':
            n.update(key=None, state='', fails=0)
            return True
        if n['state'] == 'FAILED':
            if math.hypot(tx - self.x, ty - self.y) < 0.03:       # close enough: count the node as reached
                n.update(key=None, state='', fails=0)
                return True
            n['key'] = None                                         # blocked (obstacle in the costmap): try again
            self.nav_state = 'NAV2_RETRY'
        return False

    def _refresh_costmap(self):
        """While driving, rebuild the local costmap from the newest scan once a second (see _nav2_segment)."""
        if self.n2['key'] is not None and self.clear_local.service_is_ready():
            self.clear_local.call_async(ClearEntireCostmap.Request())

    def _nav2_accepted(self, fut, key):
        gh, n = fut.result(), self.n2
        if n['key'] != key:
            if gh.accepted:
                gh.cancel_goal_async()
            return
        if not gh.accepted:
            n.update(state='FAILED', t_fail=time.time())
            return
        n['handle'] = gh
        gh.get_result_async().add_done_callback(lambda f, key=key: self._nav2_result(f, key))

    def _nav2_result(self, fut, key):
        n = self.n2
        if n['key'] != key:
            return
        if fut.result().status == 4:                                # GoalStatus.STATUS_SUCCEEDED
            n['state'] = 'SUCCEEDED'
        else:
            n.update(state='FAILED', t_fail=time.time(), fails=n['fails'] + 1)

    def _nav2_cancel(self):
        n = self.n2
        if n['key'] is not None:
            if n['handle'] is not None:
                n['handle'].cancel_goal_async()
            n.update(key=None, state='', handle=None)

    # ------------------------------------------------------------ Arm Controller (serving arm on the AMR)
    def _arm_job(self, gh):
        g = gh.request
        self.arm_state = g.job
        t0, dur = time.time(), max(0.2, g.duration)
        while rclpy.ok():
            pr = (time.time() - t0) / dur
            if pr >= 1.0:
                break
            self.arm_q = arm_pose(g.job, pr, time.time())
            gh.publish_feedback(ArmJob.Feedback(phase=g.job, progress=float(pr)))
            time.sleep(0.05)
        self.arm_q, self.arm_state = list(REST), 'IDLE'
        gh.succeed()
        return ArmJob.Result(success=True, reason='OK')

    # ------------------------------------------------------------ status / TF
    def _publish(self):
        now = self.get_clock().now().to_msg()
        at_home = math.hypot(self.x - self.home[0], self.y - self.home[1]) < 0.02
        self.charging = at_home and self.nav_state == 'IDLE'
        if self.charging:
            self.battery = min(100.0, self.battery + 0.05)
        else:
            self.battery = max(0.0, self.battery - 0.0005)
        state = 'CHARGING' if self.charging else (self.arm_state if self.arm_state != 'IDLE' else self.nav_state)
        self.pub_status.publish(RobotStatus(stamp=now, robot_id=self.rid, state=state, x=self.x, y=self.y, yaw=self.yaw,
                                            battery=float(self.battery), charging=self.charging, task_id=self.task_id,
                                            plan_version=self.pv, reached_index=self.reached, arm_state=self.arm_state))
        t = TransformStamped()
        t.header.stamp, t.header.frame_id, t.child_frame_id = now, 'map', f'{self.rid}/base_footprint'
        t.transform.translation.x, t.transform.translation.y = self.x, self.y
        t.transform.rotation.z, t.transform.rotation.w = math.sin(self.yaw / 2), math.cos(self.yaw / 2)
        if self.drive != 'nav2':               # with Nav2 the pose comes from map -> odom -> base (Gazebo odometry)
            self.tf.sendTransform(t)
        js = JointState()
        js.header.stamp = now
        js.name = ['l_wheel_joint', 'r_wheel_joint', 'caster_rotate_joint', 'caster_wheel_joint']
        js.position = [self.wheel, self.wheel, 0.0, 0.0]
        self.pub_js.publish(js)
        aj = JointState()
        aj.header.stamp, aj.name, aj.position = now, JOINTS, [float(v) for v in self.arm_q]
        self.pub_arm_js.publish(aj)


def main():
    rclpy.init()
    n = Amr()
    ex = MultiThreadedExecutor(num_threads=6)
    ex.add_node(n)
    try:
        ex.spin()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
