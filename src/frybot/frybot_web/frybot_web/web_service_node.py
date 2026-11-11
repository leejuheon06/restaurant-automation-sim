"""Web Service (Main Server). Browsers talk HTTP; the service talks ROS 2 to Central Control and holds no state.

  /            index          /reception   입구 접수 태블릿
  /table?id=N  테이블 주문 태블릿   /admin       관리자 화면
"""
import json
import threading

import rclpy
from ament_index_python.packages import get_package_share_directory
from rclpy.node import Node
from std_msgs.msg import String

from frybot_control import layout
from frybot_interfaces.srv import AdminCommand, CheckIn, EndUse, PlaceOrder

from .httpd import serve


class WebService(Node):
    def __init__(self):
        super().__init__('web_service')
        port = self.declare_parameter('port', 8080).value
        self.cli = {'check_in': self.create_client(CheckIn, '/frybot/check_in'),
                    'order': self.create_client(PlaceOrder, '/frybot/place_order'),
                    'end_use': self.create_client(EndUse, '/frybot/end_use'),
                    'admin': self.create_client(AdminCommand, '/frybot/admin')}
        self.rest, self.fms, self.world = {}, {}, {}
        self.create_subscription(String, '/frybot/state', lambda m: self._set('rest', m), 10)
        self.create_subscription(String, '/fms/state', lambda m: self._set('fms', m), 10)
        self.create_subscription(String, '/sim/world_state', lambda m: self._set('world', m), 10)
        self.layout = layout.to_json()
        static = get_package_share_directory('frybot_web') + '/static'
        serve(port, static,
              get_routes={'/api/state': lambda q: {'rest': self.rest, 'fms': self.fms, 'world': self.world},
                          '/api/layout': lambda q: self.layout},
              post_routes={'/api/checkin': self._checkin, '/api/order': self._order, '/api/end_use': self._end_use,
                           '/api/admin': self._admin},
              pages={'/': 'index.html', '/reception': 'reception.html', '/table': 'table.html', '/admin': 'admin.html'})
        self.get_logger().info(f'web service: http://localhost:{port}/')

    def _set(self, key, m):
        try:
            setattr(self, key, json.loads(m.data))
        except ValueError:
            pass

    def _call(self, name, req, timeout=4.0):
        c = self.cli[name]
        if not c.service_is_ready():
            raise RuntimeError('central control is not running')
        ev = threading.Event()
        fut = c.call_async(req)
        fut.add_done_callback(lambda f: ev.set())
        if not ev.wait(timeout):
            raise RuntimeError('central control did not answer')
        return fut.result()

    def _checkin(self, b):
        r = self._call('check_in', CheckIn.Request(party_size=int(b.get('party_size', 0))))
        return {'ok': r.accepted, 'visit_id': r.visit_id, 'table_id': r.table_id, 'message': r.message}

    def _order(self, b):
        items = [(i['menu'], int(i['qty'])) for i in b.get('items', []) if int(i.get('qty', 0)) > 0]
        r = self._call('order', PlaceOrder.Request(table_id=int(b['table_id']), menu_codes=[m for m, _ in items],
                                                   quantities=[q for _, q in items]))
        return {'ok': r.accepted, 'order_id': r.order_id, 'message': r.message}

    def _end_use(self, b):
        r = self._call('end_use', EndUse.Request(table_id=int(b['table_id']), source=b.get('source', 'TABLET')))
        return {'ok': r.accepted, 'message': r.message}

    def _admin(self, b):
        r = self._call('admin', AdminCommand.Request(command=b['command'], target=str(b.get('target', '')),
                                                     arg=str(b.get('arg', ''))))
        return {'ok': r.ok, 'message': r.message}


def main():
    rclpy.init()
    try:
        rclpy.spin(WebService())
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
