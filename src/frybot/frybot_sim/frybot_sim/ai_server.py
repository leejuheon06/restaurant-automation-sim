"""AI Server (separate machine in the architecture; plain Python, no ROS).
  Camera Streamers --UDP--> AI Interface --IPC--> Inference Model
  AI Interface --HTTP POST--> Central Control  (/ai/result)
The 'model' here is a threshold on simulated features; swap InferenceModel for the trained network later.

AI 서버 대역(ROS 없이 단독 실행). 카메라 대역이 보낸 UDP JSON 프레임
(:9100)을 임계값으로 판정해 central_control 의 HTTP(:8100 /ai/result)로
보낸다.
"""
import argparse
import json
import socket
import urllib.request


# 학습 모델 대역: 튀김 익힘 판정, 의자 QR 개수, 안내 손님 추적
class InferenceModel:
    """Stand-in for the trained models (doneness classifier, chair-QR detector)."""
    version = 'sim-threshold-0.1'  # 결과의 model_version

    def doneness(self, golden_ratio):
        """튀김 익힘을 판정한다.

        Args:
            golden_ratio: 황금색 픽셀 비율(0~1).

        Returns:
            (판정, 신뢰도). 0.9 이상이면 'DONE', 아니면 'UNDERCOOKED'.
            신뢰도는 0.9 에서 떨어진 정도 + 0.5 라 1 을 넘을 수 있다.
        """
        # the team's OpenCV test: golden pixel ratio 96.2% (done) vs 30.4% (pale)
        return ('DONE' if golden_ratio >= 0.9 else 'UNDERCOOKED'), round(abs(golden_ratio - 0.9) / 0.9 + 0.5, 2)

    def seat_qr(self, table):
        """보이는 의자 QR 개수를 돌려준다.

        Args:
            table: 천장 카메라 프레임의 테이블 항목(qr_visible 사용).

        Returns:
            보이는 QR 개수(그대로 정수로 바꿈).
        """
        return int(table['qr_visible'])

    # [수정 2026-11-17] 신규 (UR-03): 안내 중인 손님 추적 (대역)
    def guest(self, distance: float) -> tuple[bool, float]:
        """손님이 보이는지와 거리(m). 2 m 넘게 떨어지면 못 본 것으로 둔다."""
        return distance <= 2.0, round(distance, 3)


class AiInterface:
    """UDP 프레임을 받아 판정 결과를 HTTP 로 보내는 AI Interface 대역.

    Args:
        udp_port: 받을 UDP 포트(0.0.0.0 에 묶음).
        central_url: 결과를 POST 할 central_control 주소.
    """
    def __init__(self, udp_port, central_url):
        self.model = InferenceModel()
        self.url = central_url
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(('0.0.0.0', udp_port))
        self.last = {}  # (종류, 작업 id) → 직전 판정
        self.frames = 0  # 받은 프레임 수(읽는 곳 없음)

    def post(self, result):
        """판정 결과 하나를 central_control 에 POST 한다.

        보내지 못하면 버린다(관제가 아직 안 떴을 때 등).

        Args:
            result: 보낼 dict. model_version 을 덧붙인다.
        """
        result['model_version'] = self.model.version
        try:
            req = urllib.request.Request(self.url, json.dumps(result).encode(), {'Content-Type': 'application/json'})
            urllib.request.urlopen(req, timeout=0.5).read()
        except Exception:
            pass                                  # central control not up yet

    def run(self):
        """UDP 프레임을 끝없이 받아 종류별로 판정해 보낸다.

        fryer → DONENESS, guide → GUEST_TRACK, ceiling → 테이블마다 SEAT_QR.
        JSON 이 아닌 프레임은 버린다.
        """
        print(f'[ai_server] UDP in :{self.sock.getsockname()[1]}  ->  HTTP out {self.url}', flush=True)
        while True:
            data, _ = self.sock.recvfrom(65535)
            try:
                f = json.loads(data)
            except ValueError:
                continue
            self.frames += 1
            if f['kind'] == 'fryer':  # 튀김기 카메라(조리 팔)
                decision, conf = self.model.doneness(f['golden_ratio'])
                key = ('d', f['cook_task_id'])  # changed 판단용
                self.post(dict(kind='DONENESS', cook_task_id=f['cook_task_id'], decision=decision, confidence=conf,
                               golden_ratio=f['golden_ratio'], changed=self.last.get(key) != decision, camera=f['camera']))
                self.last[key] = decision
            elif f['kind'] == 'guide':  # AMR 의 손님 추적 카메라
                visible, distance = self.model.guest(float(f['distance']))
                self.post(dict(kind='GUEST_TRACK', robot_id=f['robot_id'],
                               visit_id=f['visit_id'], visible=visible,
                               distance=distance, camera=f['camera']))
            elif f['kind'] == 'ceiling':  # 매장 천장 카메라(world)
                for t in f['tables']:
                    self.post(dict(kind='SEAT_QR', table_id=t['table_id'], seats=t['seats'],
                                   visible=self.model.seat_qr(t), camera=f['camera']))


def main():
    """AI 서버 대역을 실행한다(--udp-port, --central-url)."""
    ap = argparse.ArgumentParser()
    ap.add_argument('--udp-port', type=int, default=9100)
    ap.add_argument('--central-url', default='http://127.0.0.1:8100/ai/result')
    a, _ = ap.parse_known_args()
    try:
        AiInterface(a.udp_port, a.central_url).run()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
