"""Guest simulator UI (NOT part of the system architecture - a test tool).
It plays the guests: walks in (-> reception tablet API), picks food at the table (-> table tablet API), leaves.
It only uses the same HTTP API as the real tablets plus /sim/customer_cmd for physical behaviour in the sim world.
"""
import json
import urllib.request

import rclpy
from ament_index_python.packages import get_package_share_directory
from rclpy.node import Node
from std_msgs.msg import String

from frybot_web.httpd import serve


class CustomerUi(Node):
    def __init__(self):
        super().__init__('customer_ui')
        port = self.declare_parameter('port', 8090).value
        self.web = self.declare_parameter('web_url', 'http://127.0.0.1:8080').value
        self.pub = self.create_publisher(String, '/sim/customer_cmd', 20)
        serve(port, get_package_share_directory('frybot_sim') + '/static',
              get_routes={'/api/state': lambda q: self._get('/api/state'), '/api/layout': lambda q: self._get('/api/layout')},
              post_routes={'/api/enter': lambda b: self._post('/api/checkin', {'party_size': b['party_size']}),
                           '/api/order': lambda b: self._post('/api/order', b),
                           '/api/leave': self._leave, '/api/straggle': self._straggle},
              pages={'/': 'customer.html'})
        self.get_logger().info(f'guest simulator UI: http://localhost:{port}/')

    def _get(self, path):
        return json.loads(urllib.request.urlopen(self.web + path, timeout=3).read())

    def _post(self, path, body):
        req = urllib.request.Request(self.web + path, json.dumps(body).encode(), {'Content-Type': 'application/json'})
        return json.loads(urllib.request.urlopen(req, timeout=6).read())

    def _leave(self, b):
        if b.get('mode') == 'walkout':               # no button: the ceiling camera must notice the empty chairs
            self.pub.publish(String(data=json.dumps({'cmd': 'walkout', 'visit_id': b['visit_id']})))
            return {'ok': True, 'message': '손님이 버튼 없이 나갔습니다. 의자 QR 판정을 기다립니다.'}
        return self._post('/api/end_use', {'table_id': b['table_id'], 'source': 'TABLET'})

    def _straggle(self, b):
        self.pub.publish(String(data=json.dumps({'cmd': 'straggle', 'visit_id': b['visit_id'], 'on': bool(b['on'])})))
        return {'ok': True, 'message': '손님이 멈춰 섰습니다.' if b['on'] else '손님이 다시 따라갑니다.'}


def main():
    rclpy.init()
    try:
        rclpy.spin(CustomerUi())
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
