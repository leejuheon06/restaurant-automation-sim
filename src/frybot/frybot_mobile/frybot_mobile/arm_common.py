"""Shared helpers for the JetCobot 280 (myCobot 280) arm controllers: joint names, poses, UDP camera streamer.

서빙 팔(대역) 공용 도구. mobile_controller 가 JOINTS·REST·arm_pose 로
RViz 용 관절값을 만들고 CameraStreamer 로 AI 서버에 프레임을 보낸다.
serving_arm_driver 는 JOINTS 만, frybot_sim world_node 는
CameraStreamer 만 쓴다. 조리 팔은 frybot_arm/arm_motion.py 를 쓴다.
"""
import json
import math
import socket

# 팔 관절 이름(myCobot 280 URDF 의 관절 이름, 베이스 -> 끝 순서)
JOINTS = ['joint2_to_joint1', 'joint3_to_joint2', 'joint4_to_joint3', 'joint5_to_joint4', 'joint6_to_joint5',
          'joint6output_to_joint6']
# 접은 휴식 자세(rad, JOINTS 순서). 대역 애니메이션의 시작·끝
REST = [0.0, 0.5, -1.9, 1.3, 0.0, 0.0]
# job -> (base yaw, reach pose). Yaw is relative to the arm base.
POSES = {
    'LOAD': (math.pi / 2, [0.0, -1.0, -0.6, -0.1, 0.0, 0.0]),
    'UNLOAD': (math.pi / 2, [0.0, -1.1, -0.5, 0.0, 0.0, 0.0]),
    'COLLECT_DISHES': (math.pi / 2, [0.0, -1.1, -0.5, 0.0, 0.0, 0.0]),
    'RETURN_DISHES': (math.pi / 2, [0.0, -1.0, -0.6, -0.1, 0.0, 0.0]),
    # 서빙 팔 작업만 둠. 조리 팔 자세는 frybot_arm/arm_motion.py 가 맡음
}


def arm_pose(job, progress):
    """Joint angles for a job at progress 0..1 (rest -> reach -> rest).

    작업 자세가 없는 job 은 REST 그대로 둔다. 첫 관절(베이스 회전)은
    k 의 1.5배로 먼저 돌아가 yaw 에 닿는다.

    Args:
        job: ArmJob 작업 이름(POSES 의 키).
        progress: 진행률 0..1. 범위 밖 값은 잘라 씀.

    Returns:
        JOINTS 순서의 관절 각도(rad) 6개.
    """
    yaw, reach = POSES.get(job, (0.0, REST))
    k = math.sin(math.pi * min(max(progress, 0.0), 1.0))          # 0 -> 1 -> 0
    q = [REST[i] + (reach[i] - REST[i]) * k for i in range(6)]
    q[0] = yaw * min(1.0, k * 1.5)
    return q


class CameraStreamer:
    """Sends small JSON 'frames' to the AI server over UDP (stand-in for the real video stream).

    AI 서버(대역)가 UDP 로 받는 프레임 형식: {"camera", "kind", ...}.

    Args:
        camera_id: 프레임의 camera 값(예: pinky1_front, ceiling).
        host: AI 서버 주소.
        port: AI 서버 UDP 포트.
    """

    def __init__(self, camera_id, host='127.0.0.1', port=9100):
        self.camera_id, self.addr = camera_id, (host, port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send(self, kind, **data):
        """프레임 하나를 보낸다. 전송 실패(OSError)는 무시한다.

        Args:
            kind: 프레임 종류('amr', 'guide', 'ceiling' 등).
            **data: 프레임에 함께 실을 값(JSON 으로 바꿀 수 있어야 함).
        """
        try:
            self.sock.sendto(json.dumps(dict(camera=self.camera_id, kind=kind, **data)).encode(), self.addr)
        except OSError:
            pass
