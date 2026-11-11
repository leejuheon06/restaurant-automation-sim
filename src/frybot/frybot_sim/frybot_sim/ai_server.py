"""AI Server (separate machine in the architecture; plain Python, no ROS).
  Camera Streamers --UDP--> AI Interface --IPC--> Inference Model
  AI Interface --HTTP POST--> Central Control  (/ai/result)
The 'model' here is a threshold on simulated features; swap InferenceModel for the trained network later.
"""
import argparse
import json
import socket
import time
import urllib.request


class InferenceModel:
    """Stand-in for the trained models (doneness classifier, chair-QR detector)."""
    version = 'sim-threshold-0.1'

    def doneness(self, golden_ratio):
        # the team's OpenCV test: golden pixel ratio 96.2% (done) vs 30.4% (pale)
        return ('DONE' if golden_ratio >= 0.9 else 'UNDERCOOKED'), round(abs(golden_ratio - 0.9) / 0.9 + 0.5, 2)

    def seat_qr(self, table):
        return int(table['qr_visible'])


class AiInterface:
    def __init__(self, udp_port, central_url):
        self.model = InferenceModel()
        self.url = central_url
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(('0.0.0.0', udp_port))
        self.last = {}
        self.frames = 0

    def post(self, result):
        result['model_version'] = self.model.version
        try:
            req = urllib.request.Request(self.url, json.dumps(result).encode(), {'Content-Type': 'application/json'})
            urllib.request.urlopen(req, timeout=0.5).read()
        except Exception:
            pass                                  # central control not up yet

    def run(self):
        print(f'[ai_server] UDP in :{self.sock.getsockname()[1]}  ->  HTTP out {self.url}', flush=True)
        while True:
            data, _ = self.sock.recvfrom(65535)
            try:
                f = json.loads(data)
            except ValueError:
                continue
            self.frames += 1
            if f['kind'] == 'fryer':
                decision, conf = self.model.doneness(f['golden_ratio'])
                key = ('d', f['cook_task_id'])
                self.post(dict(kind='DONENESS', cook_task_id=f['cook_task_id'], decision=decision, confidence=conf,
                               golden_ratio=f['golden_ratio'], changed=self.last.get(key) != decision, camera=f['camera']))
                self.last[key] = decision
            elif f['kind'] == 'ceiling':
                for t in f['tables']:
                    self.post(dict(kind='SEAT_QR', table_id=t['table_id'], seats=t['seats'],
                                   visible=self.model.seat_qr(t), camera=f['camera']))


def main():
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
