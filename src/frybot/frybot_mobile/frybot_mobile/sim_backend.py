"""시뮬 전용 입력·출력 (FrybotMobile Controller 에 붙는 부분).

[수정 2026-11-18] P3(D6): mobile_controller.py 에 섞여 있던 시뮬 전용
입력·출력을 옮겨 왔음. 제어기는 시뮬 값(drive=kinematic 또는
pose_source 가 tf 가 아님)일 때만 이 모듈을 붙이고, 실기기(drive=nav2,
pose_source=tf)에서는 아무것도 구독·발행하지 않음. 동작은 옮기기 전과 같음.

맡는 것
    - /gz/model_poses 로 받은 Gazebo 참값 자세와 map -> odom 보정(Nav2 주행)
    - map -> base TF (Nav2 를 쓰지 않는 주행: 자세를 직접 움직임)
    - 가짜 배터리 증감과 충전대 좌표로 충전 판정(배터리 토픽이 없을 때)
    - 가짜 바퀴 관절값 /<로봇>/joint_states (RViz 모델 표시)
    - /sim/world_state 의 손님 좌표와 안내 중 카메라 프레임(_guide_frame 대역)

주행·허가·비상 정지 로직은 옮기지 않음(drive=kinematic 분기는 제어기에 남음).
"""
import json
import math

from geometry_msgs.msg import TransformStamped
from sensor_msgs.msg import JointState
from std_msgs.msg import String
from tf2_msgs.msg import TFMessage
from tf2_ros import TransformBroadcaster


def _wrap(a: float) -> float:
    """각도를 -pi..pi 로 맞춘다."""
    return (a + math.pi) % (2 * math.pi) - math.pi


class SimBackend:
    """시뮬에서만 쓰는 제어기의 입력·출력.

    Attributes:
        node: 붙은 제어기 노드(MobileController).
        guests: /sim/world_state 의 손님 좌표(visit_id 문자열 -> dict).
        chargers: 충전대 노드 좌표 목록.
    """

    def __init__(self, node, cb, chargers: list) -> None:
        """구독·발행·타이머를 만든다.

        Args:
            node: 제어기 노드. rid, drive, pose_source, x, y, yaw, odom,
                wheel, cur, guide_goal, cam, nav_state, battery, charging,
                have_truth 를 읽고 쓴다.
            cb: 콜백 그룹.
            chargers: 충전대 노드 좌표 (x, y) 목록.
        """
        self.node = node
        self.guests = {}
        # 가상 매장(proto)은 layout 의 충전대 노드, 실측 지도는 빈 목록
        self.chargers = chargers
        self.tf = TransformBroadcaster(node)  # map -> odom / map -> base 송신
        rid = node.rid
        # 가짜 바퀴 관절값(RViz 모델), publish() 에서 냄
        self.pub_js = node.create_publisher(
            JointState, f'/{rid}/joint_states', 10)
        # 매장 시뮬 상태(손님 좌표). _guide_frame 이 씀
        node.create_subscription(String, '/sim/world_state', self._world, 10,
                                 callback_group=cb)
        # 예전 조건 그대로: TF 로 위치를 받지 않고 Gazebo 로 주행할 때
        if node.pose_source != 'tf' and node.drive in ('cmd_vel', 'nav2'):
            node.create_subscription(TFMessage, '/gz/model_poses',
                                     self._gz_pose, 20, callback_group=cb)
        # 안내 카메라 대역 프레임을 5 Hz 로 보냄
        node.create_timer(0.2, self._guide_frame, callback_group=cb)

    def _world(self, m: String) -> None:
        """매장 시뮬의 상태에서 손님 좌표를 받는다."""
        try:
            self.guests = json.loads(m.data).get('guests', {})
        except ValueError:
            pass

    def _guide_frame(self) -> None:
        """안내 중 카메라 영상을 AI 서버로 보낸다 (Camera Streamer 대역).

        실제 영상 대신 손님까지의 거리를 실은 JSON 프레임을 보낸다. 그 거리는
        시뮬의 매장 상태(/sim/world_state)에서 얻는다. 실기기 카메라 영상
        송신은 아직 구현이 없다.
        """
        n = self.node
        gh = n.guide_goal
        # 지금 실행 중인 경로가 손님 안내(GUIDE)일 때만
        if gh is None or gh is not n.cur or not gh.is_active:
            return
        visit_id = gh.request.visit_id
        gpos = self.guests.get(str(visit_id))
        if gpos is not None:
            n.cam.send('guide', robot_id=n.rid, visit_id=visit_id,
                       distance=math.hypot(gpos['x'] - n.x, gpos['y'] - n.y))

    def _gz_pose(self, m: TFMessage) -> None:
        """Gazebo 의 참값 자세로 위치를 정하고 map -> odom 을 보정한다.

        AMCL 대신이다. 바퀴 오도메트리만 쓰면 바퀴가 미끄러져 크게 어긋나므로
        자세가 올 때마다 map -> odom 을 다시 맞춘다.
        """
        n = self.node
        # Gazebo 가 모든 모델 자세를 한 메시지로 보냄. 자기 모델만 씀
        for t in m.transforms:
            if t.child_frame_id == n.rid:
                q = t.transform.rotation
                n.x, n.y = t.transform.translation.x, t.transform.translation.y
                n.yaw = math.atan2(2 * (q.w * q.z + q.x * q.y),
                                   1 - 2 * (q.y * q.y + q.z * q.z))
                n.have_truth = True
                # map -> odom = 참값 자세 x (odom 기준 자세)^-1
                ox, oy, _ = n.odom
                dyaw = _wrap(n.yaw - n.odom[2])
                c, s_ = math.cos(dyaw), math.sin(dyaw)
                tf = TransformStamped()
                tf.header.stamp = n.get_clock().now().to_msg()
                tf.header.frame_id, tf.child_frame_id = 'map', f'{n.rid}/odom'
                tf.transform.translation.x = n.x - (c * ox - s_ * oy)
                tf.transform.translation.y = n.y - (s_ * ox + c * oy)
                tf.transform.rotation.z = math.sin(dyaw / 2)
                tf.transform.rotation.w = math.cos(dyaw / 2)
                # Nav2 주행일 때만 TF 를 냄. cmd_vel 주행은 위치값만 씀
                if n.drive == 'nav2':
                    self.tf.sendTransform(tf)
                return

    def update_battery(self) -> None:
        """가짜 배터리: 충전대에 서 있으면 오르고, 아니면 천천히 내린다."""
        # 상태 보고(_publish, 10 Hz)마다 불림: 충전 +0.5 %/s, 방전 -0.005 %/s
        n = self.node
        # 충전대 노드 2 cm 안에서 서 있으면(IDLE) 충전 중
        on_charger = any(math.hypot(n.x - cx, n.y - cy) < 0.02
                         for cx, cy in self.chargers)
        n.charging = on_charger and n.nav_state == 'IDLE'
        if n.charging:
            n.battery = min(100.0, n.battery + 0.05)
        else:
            n.battery = max(0.0, n.battery - 0.0005)

    def publish(self, now) -> None:
        """Map -> base TF(Nav2 를 쓰지 않는 주행)와 가짜 바퀴 관절값을 낸다.

        Args:
            now: 상태 보고와 같은 시각(builtin_interfaces/Time).
        """
        n = self.node
        # Nav2 주행은 map -> odom(_gz_pose) + odom -> base 로 자세가 나옴
        if n.drive != 'nav2':
            t = TransformStamped()
            t.header.stamp, t.header.frame_id = now, 'map'
            t.child_frame_id = f'{n.rid}/base_footprint'
            t.transform.translation.x, t.transform.translation.y = n.x, n.y
            t.transform.rotation.z = math.sin(n.yaw / 2)
            t.transform.rotation.w = math.cos(n.yaw / 2)
            self.tf.sendTransform(t)
        js = JointState()
        js.header.stamp = now
        js.name = ['l_wheel_joint', 'r_wheel_joint', 'caster_rotate_joint',
                   'caster_wheel_joint']
        # 좌우 바퀴를 같은 각도로(kinematic 주행이 누적한 n.wheel), 캐스터 0
        js.position = [n.wheel, n.wheel, 0.0, 0.0]
        self.pub_js.publish(js)
