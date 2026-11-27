"""Frybot Cooking Package 의 노드 목록 (런치 파일들이 같이 씀)."""
from launch_ros.actions import Node

from frybot_arm import ARM_IDS


def cooking_nodes(arm_ids: tuple[str, ...] = ARM_IDS,
                  undercooked_prob: float = 0.25,
                  ai_host: str = '127.0.0.1') -> list[Node]:
    """Master Controller 하나와 팔마다 Arm Controller 하나를 만든다.

    Args:
        arm_ids: 조리 팔 ID 목록.
        undercooked_prob: 튀김이 덜 익어 나올 확률 (튀김기 대역).
        ai_host: Camera Streamer 가 영상을 보낼 AI 서버 주소.

    Returns:
        launch 에 넣을 Node 액션 목록.
    """
    nodes = [Node(package='frybot_arm', executable='master_controller',
                  # [수정 2026-11-18] P2: 노드 이름을 실행 파일과 같게
                  name='master_controller', output='screen',
                  parameters=[{'arm_ids': list(arm_ids)}])]
    # 팔마다 /<arm_id>/arm_controller 노드(이름공간 = 팔 이름)
    for arm_id in arm_ids:
        nodes.append(Node(
            package='frybot_arm', executable='arm_controller',
            name='arm_controller', namespace=arm_id, output='screen',
            parameters=[{'arm_id': arm_id, 'ai_host': ai_host,
                         'undercooked_prob': float(undercooked_prob)}]))
    return nodes
