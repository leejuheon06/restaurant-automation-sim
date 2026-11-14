"""Cooking arm station (JetCobot 280): Arm Controller (ArmJob action) + Camera Streamer (UDP to the AI server).
Arm A also owns the simulated fryer: the camera frame carries the 'golden colour ratio' of the basket."""
import json
import random
import time

import rclpy
from rclpy.action import ActionServer
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from sensor_msgs.msg import JointState

from frybot_interfaces.action import ArmJob

from frybot_mobile.arm_common import JOINTS, REST, CameraStreamer, arm_pose


class CookArm(Node):
    def __init__(self):
        super().__init__('cook_arm')
        p = self.declare_parameter
        self.arm_id = p('arm_id', 'cook_arm_a').value
        self.p_under = p('undercooked_prob', 0.25).value
        self.q, self.job = list(REST), 'IDLE'
        self.basket = None                 # dict(task, t0, need)
        cb = ReentrantCallbackGroup()
        self.pub_js = self.create_publisher(JointState, f'/{self.arm_id}/joint_states', 10)
        ActionServer(self, ArmJob, f'/{self.arm_id}/arm_job', execute_callback=self._job, callback_group=cb)
        self.cam = CameraStreamer(self.arm_id, port=p('ai_udp_port', 9100).value)
        self.create_timer(0.1, self._publish, callback_group=cb)
        self.create_timer(0.5, self._stream, callback_group=cb)
        self.get_logger().info(f'{self.arm_id} ready')

    def _job(self, gh):
        g = gh.request
        params = json.loads(g.params_json or '{}')
        self.job = g.job
        t0, dur = time.time(), max(0.2, g.duration)
        while rclpy.ok():
            pr = (time.time() - t0) / dur
            if pr >= 1.0:
                break
            self.q = arm_pose(g.job, pr, time.time())
            gh.publish_feedback(ArmJob.Feedback(phase=g.job, progress=float(pr)))
            time.sleep(0.05)
        if g.job == 'DROP_IN_FRYER':
            extra = random.uniform(0.12, 0.3) if random.random() < self.p_under else -0.08
            self.basket = dict(task=params.get('cook_task_id', ''), t0=time.time(),
                               need=params.get('fry_time', 30.0) * (1.0 + extra))
        elif g.job == 'LIFT_DRAIN':
            self.basket = None
        self.q, self.job = list(REST), 'IDLE'
        gh.succeed()
        return ArmJob.Result(success=True, reason='OK')

    def _stream(self):
        if self.basket:
            ratio = min(1.0, (time.time() - self.basket['t0']) / self.basket['need'])
            self.cam.send('fryer', cook_task_id=self.basket['task'], golden_ratio=round(ratio, 3))
        else:
            self.cam.send('idle', job=self.job)

    def _publish(self):
        js = JointState()
        js.header.stamp, js.name, js.position = self.get_clock().now().to_msg(), JOINTS, [float(v) for v in self.q]
        self.pub_js.publish(js)


def main():
    rclpy.init()
    n = CookArm()
    ex = MultiThreadedExecutor(num_threads=4)
    ex.add_node(n)
    try:
        ex.spin()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
