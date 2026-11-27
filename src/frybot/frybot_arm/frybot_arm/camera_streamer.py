"""Camera Streamer: 조리 팔 카메라 영상을 AI 서버로 UDP 전송 (대역).

실제 영상 대신 작은 JSON '프레임'을 보냅니다. 형식은
frybot_mobile/arm_common.py 의 CameraStreamer 와 같습니다.
"""
import json
import socket


class CameraStreamer:
    """JSON 프레임을 AI 서버(AI Interface)에 UDP 로 보낸다."""

    def __init__(self, camera_id: str, host: str = '127.0.0.1',
                 port: int = 9100) -> None:
        """소켓을 연다.

        Args:
            camera_id: 프레임에 실리는 카메라 이름 (조리 팔 ID).
            host: AI 서버 주소.
            port: AI 서버 UDP 포트.
        """
        self.camera_id = camera_id
        self._addr = (host, port)
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send(self, kind: str, **data) -> None:
        """프레임 하나를 보낸다. 전송 실패는 무시한다(영상은 유실 허용).

        Args:
            kind: 프레임 종류 ('fryer', 'idle').
            **data: 프레임에 함께 실을 값.
        """
        frame = dict(camera=self.camera_id, kind=kind, **data)
        try:
            self._sock.sendto(json.dumps(frame).encode(), self._addr)
        except OSError:
            pass
