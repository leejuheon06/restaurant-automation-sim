"""Guest simulator UI (NOT part of the system architecture - a test tool).
It plays the guests: walks in (-> reception tablet API), picks food at the table (-> table tablet API), leaves.
It only uses the same HTTP API as the real tablets plus /sim/customer_cmd for physical behaviour in the sim world.

손님 시뮬레이터 UI(아키텍처 밖의 시험 도구, HTTP :8090). 접수·주문·
이용 종료는 web_service 의 HTTP API 로 넘기고, 매장 안 손님의 행동
(걸어 나가기, 멈춰 서기)은 /sim/customer_cmd 토픽으로 world 에 보낸다.
"""
import json
import urllib.request

import rclpy
from ament_index_python.packages import get_package_share_directory
from rclpy.node import Node
from std_msgs.msg import String

from frybot_web.httpd import serve


class CustomerUi(Node):
    """손님 시뮬레이터 화면(customer.html)과 그 API 를 내는 노드."""
    def __init__(self):
        super().__init__('customer_ui')
        port = self.declare_parameter('port', 8090).value  # 이 UI 의 포트
        # web_url: 요청을 넘길 web_service 주소
        self.web = self.declare_parameter('web_url', 'http://127.0.0.1:8080').value
        # 매장 시뮬(world)에 손님 행동 명령(JSON)을 보냄
        self.pub = self.create_publisher(String, '/sim/customer_cmd', 20)
        # [수정 2026-11-25] I/F 정의서 v0.2 경로: /api/checkin·/api/order ->
        # /api/visits·/api/orders (이 UI 의 주문 경로도 웹과 같게 /api/orders)
        # /api/enter → web 의 /api/visits, /api/orders·/api/state·/api/layout
        # 은 그대로 web_service 로 넘김. leave·straggle 은 아래 메서드
        serve(port, get_package_share_directory('frybot_sim') + '/static',
              get_routes={'/api/state': lambda q: self._get('/api/state'), '/api/layout': lambda q: self._get('/api/layout')},
              post_routes={'/api/enter': lambda b: self._post(
                               '/api/visits', {'party_size': b['party_size']}),
                           '/api/orders':
                               lambda b: self._post('/api/orders', b),
                           '/api/leave': self._leave, '/api/straggle': self._straggle},
              pages={'/': 'customer.html'})
        self.get_logger().info(f'guest simulator UI: http://localhost:{port}/')

    # web_service 에 GET 하고 JSON 을 돌려줌
    def _get(self, path):
        return json.loads(urllib.request.urlopen(self.web + path, timeout=3).read())

    # web_service 에 JSON 을 POST 하고 응답 JSON 을 돌려줌
    def _post(self, path, body):
        req = urllib.request.Request(self.web + path, json.dumps(body).encode(), {'Content-Type': 'application/json'})
        return json.loads(urllib.request.urlopen(req, timeout=6).read())

    # 퇴장: mode 가 'walkout' 이면 버튼 없이 나감(world 에 알림), 아니면
    # 테이블 태블릿의 이용 종료(/api/end_use)
    def _leave(self, b):
        if b.get('mode') == 'walkout':               # no button: the ceiling camera must notice the empty chairs
            self.pub.publish(String(data=json.dumps({'cmd': 'walkout', 'visit_id': b['visit_id']})))
            return {'ok': True, 'message': '손님이 버튼 없이 나갔습니다. 의자 QR 판정을 기다립니다.'}
        return self._post('/api/end_use', {'table_id': b['table_id'], 'source': 'TABLET'})

    # 안내 중 손님 멈춰 서기(on=True) / 다시 따라가기(on=False)
    def _straggle(self, b):
        self.pub.publish(String(data=json.dumps({'cmd': 'straggle', 'visit_id': b['visit_id'], 'on': bool(b['on'])})))
        return {'ok': True, 'message': '손님이 멈춰 섰습니다.' if b['on'] else '손님이 다시 따라갑니다.'}


def main():
    """손님 시뮬레이터 UI 노드를 띄우고 Ctrl+C 까지 돈다."""
    rclpy.init()
    try:
        rclpy.spin(CustomerUi())
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
