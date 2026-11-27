"""런치에 든 로봇이 모두 상태를 보고할 때까지 기다렸다가 끝난다.

[수정 2026-11-19] T-40: real.launch.py 가 이 프로그램이 끝난 뒤에 RViz 를
띄운다. 세 대를 RViz 와 함께 띄우면 관제와 로봇의 연결이 2~3분 걸렸음.
구독은 /fleet/robot_status 하나뿐이다.
"""
import time

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node

from frybot_interfaces.msg import RobotStatus


class WaitOnline(Node):
    """기다리는 로봇 목록에서 상태를 보고한 로봇을 지워 나가는 노드."""

    def __init__(self) -> None:
        super().__init__('wait_online')
        # robot_ids: 기다릴 로봇 이름 목록
        robots = self.declare_parameter('robot_ids', ['pinky1']).value
        # timeout_sec: 이 초가 지나면 기다리지 않고 끝냄(런치의 rviz_wait_sec)
        self.timeout = float(
            self.declare_parameter('timeout_sec', 120.0).value)
        self.waiting = set(robots)  # 아직 보고하지 않은 로봇
        # 로봇 상태 보고(10 Hz)를 받으면 그 로봇을 목록에서 지움
        self.create_subscription(
            RobotStatus, '/fleet/robot_status', self._status, 50)

    def _status(self, status: RobotStatus) -> None:
        """상태를 보고한 로봇을 기다리는 목록에서 지운다.

        Args:
            status: 로봇이 보낸 상태 보고.
        """
        self.waiting.discard(status.robot_id)


def wait(node: WaitOnline) -> bool:
    """모든 로봇이 보고하거나 시간 제한이 지날 때까지 돈다.

    Args:
        node: 기다리는 노드.

    Returns:
        모든 로봇이 보고했으면 True, 시간 제한으로 끝났으면 False.
    """
    start = time.monotonic()
    while rclpy.ok() and node.waiting:
        if time.monotonic() - start > node.timeout:
            node.get_logger().warning(
                f'{node.timeout:.0f}초 동안 보고 없음: '
                f'{sorted(node.waiting)} -> 기다리지 않고 진행')
            return False
        rclpy.spin_once(node, timeout_sec=0.2)
    if not node.waiting:
        node.get_logger().info(
            f'모든 로봇이 보고함 ({time.monotonic() - start:.1f}초)')
    return not node.waiting


def main() -> None:
    """모든 로봇의 보고나 시간 제한을 기다린 뒤 종료 코드 0 으로 끝난다."""
    rclpy.init()
    node = WaitOnline()
    try:
        wait(node)  # 결과와 상관없이 종료 코드 0
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
