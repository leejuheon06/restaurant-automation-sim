"""FrybotArm Controller: 조리 팔 한 대 (A 치킨 / B 웍).

ArmJob 액션(/<arm_id>/arm_job)을 받아 팔을 움직이고, Camera Streamer 로
AI 서버에 영상을 보냅니다. 작업은 FrybotArm Master Controller 가 넘겨줍니다.

팔 구동 방식이 아직 정해지지 않아 지금은 대역입니다: 작업 시간 동안 관절
애니메이션만 내보내고(/<arm_id>/joint_states), 팔 A 는 가상의 튀김기도
맡아 카메라 프레임에 바구니의 '황금색 비율'을 실어 보냅니다.

[수정 2026-11-17] frybot_sim/cook_arm_node.py 를 옮겨 옴 (동작은 같음).
취소는 아직 받지 않습니다.
"""
import json
import random
import time

import rclpy
from rclpy.action import ActionServer
from rclpy.action.server import ServerGoalHandle
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from sensor_msgs.msg import JointState

from frybot_interfaces.action import ArmJob
from frybot_interfaces.msg import ArmStatus

from frybot_arm.arm_motion import JOINTS, REST, arm_pose
from frybot_arm.camera_streamer import CameraStreamer


class ArmController(Node):
    """조리 팔 한 대의 Arm Controller + Camera Streamer."""

    def __init__(self) -> None:
        super().__init__('arm_controller')
        p = self.declare_parameter
        # arm_id: 팔 이름(cook_arm_a | cook_arm_b). 토픽·액션 이름과 보고에 씀
        # undercooked_prob: 튀김이 덜 익어 나올 확률(튀김기 대역)
        self.arm_id = p('arm_id', 'cook_arm_a').value
        self.p_under = p('undercooked_prob', 0.25).value
        # 지금 관절값과 작업 이름('IDLE' = 쉬는 중), 그 작업의 임무 id
        self.q, self.job = list(REST), 'IDLE'
        self.task_id = ''
        self.basket = None                 # dict(task, t0, need)
        cb = ReentrantCallbackGroup()
        # 관절값(RViz 모델용)
        self.pub_js = self.create_publisher(
            JointState, f'/{self.arm_id}/joint_states', 10)
        # 작업 액션. goal·cancel 콜백이 없어 목표는 모두 받고 취소는 거절됨
        ActionServer(self, ArmJob, f'/{self.arm_id}/arm_job',
                     execute_callback=self._job, callback_group=cb)
        # 카메라 대역: ai_host:ai_udp_port 로 JSON 프레임 전송
        self.cam = CameraStreamer(self.arm_id,
                                  host=p('ai_host', '127.0.0.1').value,
                                  port=p('ai_udp_port', 9100).value)
        # 관절값 10 Hz, 카메라 프레임 2 Hz
        self.create_timer(0.1, self._publish, callback_group=cb)
        self.create_timer(0.5, self._stream, callback_group=cb)
        # [수정 2026-11-17] UR-17, 19: 팔의 상태·오류를 관제에 보고
        self.pub_status = self.create_publisher(
            ArmStatus, '/fleet/arm_status', 20)
        self.create_timer(0.5, self._status, callback_group=cb)  # 2 Hz
        self.get_logger().info(f'{self.arm_id} ready')

    def _job(self, gh: ServerGoalHandle) -> ArmJob.Result:
        """작업 하나를 duration 초 동안 수행한다(대역: 관절 애니메이션)."""
        g = gh.request
        params = json.loads(g.params_json or '{}')
        # 보고용 임무 id: 조리 임무 id(params), 없으면 목표의 task_id
        self.job = g.job
        self.task_id = params.get('cook_task_id', '') or g.task_id
        t0, dur = time.time(), max(0.2, g.duration)  # 최소 0.2초
        # 진행률이 1 이 될 때까지 20 Hz 로 자세 갱신·피드백
        while rclpy.ok():
            pr = (time.time() - t0) / dur
            if pr >= 1.0:
                break
            self.q = arm_pose(g.job, pr, time.time())
            gh.publish_feedback(
                ArmJob.Feedback(phase=g.job, progress=float(pr)))
            time.sleep(0.05)
        # 튀김기 대역: 바구니가 황금색(비율 1)이 되기까지 걸리는 시간 need.
        # 확률 p_under 로 fry_time 보다 12~30% 길게(덜 익음), 아니면 8% 짧게.
        # fry_time 이 params 에 없으면 30초. 건지면(LIFT_DRAIN) 바구니를 비움
        if g.job == 'DROP_IN_FRYER':
            extra = (random.uniform(0.12, 0.3)
                     if random.random() < self.p_under else -0.08)
            self.basket = dict(
                task=params.get('cook_task_id', ''), t0=time.time(),
                need=params.get('fry_time', 30.0) * (1.0 + extra))
        elif g.job == 'LIFT_DRAIN':
            self.basket = None
        self.q, self.job = list(REST), 'IDLE'
        gh.succeed()
        return ArmJob.Result(success=True, reason='OK')

    def _status(self) -> None:
        """팔의 상태를 /fleet/arm_status 로 보낸다 (대역: 오류 없음)."""
        busy = self.job != 'IDLE'
        # 완성된 음식을 받는 곳에 올리는 작업은 조리가 아닌 팔 작업
        state = ('IDLE' if not busy else
                 'ARM_OPERATING' if self.job == 'PLACE_HANDOFF' else 'COOKING')
        self.pub_status.publish(ArmStatus(
            stamp=self.get_clock().now().to_msg(), arm_id=self.arm_id,
            state=state, job=self.job if busy else '',
            task_id=self.task_id if busy else '', error=''))

    # 카메라 프레임: 튀기는 중이면 'fryer'(황금색 비율 0..1), 아니면 'idle'
    def _stream(self) -> None:
        if self.basket:
            ratio = min(1.0, (time.time() - self.basket['t0'])
                        / self.basket['need'])
            self.cam.send('fryer', cook_task_id=self.basket['task'],
                          golden_ratio=round(ratio, 3))
        else:
            self.cam.send('idle', job=self.job)

    # 지금 관절값을 /<arm_id>/joint_states 로 발행
    def _publish(self) -> None:
        js = JointState()
        js.header.stamp = self.get_clock().now().to_msg()
        js.name, js.position = JOINTS, [float(v) for v in self.q]
        self.pub_js.publish(js)


def main() -> None:
    """Arm Controller 노드를 4 스레드 실행기로 돌린다."""
    rclpy.init()
    node = ArmController()
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
