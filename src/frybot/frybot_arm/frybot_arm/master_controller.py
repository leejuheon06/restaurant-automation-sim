"""FrybotArm Master Controller: 조리 구역의 창구.

SW 아키텍처 v016: Task Manager --ROS2--> FrybotArm Master Controller
--ROS2--> FrybotArm Controller (A, B).

Task Manager 는 조리 팔 작업을 모두 /frybot_arm/arm_job 으로 보내고,
Master Controller 가 목표의 arm_id 를 보고 해당 팔의 /<arm_id>/arm_job 으로
넘깁니다. 피드백·결과는 그대로 전달하고 취소 요청도 넘기지만, 지금
arm_controller(대역)가 취소를 받지 않아 작업은 끝까지 갑니다.
팔 A/B 사이의 순서와 자원
(튀김기, 웍) 조율은 지금처럼 Task Manager(fleet_core 의 조리 셀 조율)가
하며, 여기서는 하지 않습니다.
"""
import time

from action_msgs.msg import GoalStatus
import rclpy
from rclpy.action import ActionClient, ActionServer
from rclpy.action import CancelResponse, GoalResponse
from rclpy.action.server import ServerGoalHandle
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

from frybot_interfaces.action import ArmJob

from frybot_arm import ARM_IDS, MASTER_ACTION

# 하위 팔의 목표 수락·결과를 기다릴 때 확인 간격(초)
_POLL_SEC = 0.02


class ArmMasterController(Node):
    """조리 팔 작업을 받아 팔별 Arm Controller 로 넘기는 노드."""

    def __init__(self) -> None:
        # [수정 2026-11-18] P2: 노드 이름을 실행 파일과 같게
        super().__init__('master_controller')
        p = self.declare_parameter
        # arm_ids: 넘길 팔 목록. server_wait_sec: 팔 액션 서버를 기다릴 시간
        arm_ids = p('arm_ids', list(ARM_IDS)).value
        self._server_wait = p('server_wait_sec', 2.0).value
        cb = ReentrantCallbackGroup()
        # 팔 이름 -> 그 팔의 /<arm_id>/arm_job 액션 클라이언트
        self._arms = {
            arm_id: ActionClient(self, ArmJob, f'/{arm_id}/arm_job',
                                 callback_group=cb)
            for arm_id in arm_ids}
        # Task Manager 가 보내는 /frybot_arm/arm_job. 취소 요청은 받아 팔에 넘김
        ActionServer(self, ArmJob, MASTER_ACTION,
                     execute_callback=self._execute,
                     goal_callback=self._on_goal,
                     cancel_callback=lambda _: CancelResponse.ACCEPT,
                     callback_group=cb)
        self.get_logger().info(
            f'arm master controller up: {", ".join(self._arms)}')

    def _on_goal(self, goal: ArmJob.Goal) -> GoalResponse:
        """모르는 팔로 가는 작업은 받지 않는다."""
        if goal.arm_id not in self._arms:
            self.get_logger().warning(f'unknown arm_id: {goal.arm_id!r}')
            return GoalResponse.REJECT
        return GoalResponse.ACCEPT

    def _execute(self, gh: ServerGoalHandle) -> ArmJob.Result:
        """작업을 해당 팔에 넘기고 끝날 때까지 기다린다.

        Args:
            gh: Task Manager 가 보낸 목표의 핸들.

        Returns:
            팔이 돌려준 결과. 팔과 연결되지 않으면 ARM_OFFLINE, 팔이
            목표를 받지 않으면 REJECTED.
        """
        goal = gh.request
        arm = self._arms[goal.arm_id]
        if not arm.wait_for_server(timeout_sec=self._server_wait):
            gh.abort()
            return ArmJob.Result(success=False, reason='ARM_OFFLINE')
        sent = arm.send_goal_async(
            goal, feedback_callback=lambda fb: self._feedback(gh, fb))
        while not sent.done():
            time.sleep(_POLL_SEC)
        child = sent.result()
        if not child.accepted:
            gh.abort()
            return ArmJob.Result(success=False, reason='REJECTED')
        # 결과를 기다리며, 취소 요청이 오면 팔 쪽 목표에 한 번 넘김
        result_future = child.get_result_async()
        cancel_sent = False
        while not result_future.done():
            if gh.is_cancel_requested and not cancel_sent:
                child.cancel_goal_async()
                cancel_sent = True
            time.sleep(_POLL_SEC)
        # 팔의 결과 상태대로 이 목표도 끝냄(취소, 성공, 그 밖은 중단)
        wrapped = result_future.result()
        result = wrapped.result
        if wrapped.status == GoalStatus.STATUS_CANCELED:
            gh.canceled()
            result.reason = result.reason or 'CANCELED'
        elif result.success:
            gh.succeed()
        else:
            gh.abort()
        return result

    # 팔의 피드백을 Task Manager 쪽 목표로 그대로 전달(끝난 목표는 버림)
    @staticmethod
    def _feedback(gh: ServerGoalHandle, fb) -> None:
        if gh.is_active:
            gh.publish_feedback(fb.feedback)


def main() -> None:
    """Master Controller 노드를 8 스레드 실행기로 돌린다."""
    rclpy.init()
    node = ArmMasterController()
    # 팔마다 실행 중인 작업이 스레드 하나를 잡고 있음
    executor = MultiThreadedExecutor(num_threads=8)
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
