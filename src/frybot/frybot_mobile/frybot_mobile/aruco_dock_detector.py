"""ArUco dock detector of one FrybotMobile: finds the wall marker of the dock the robot is entering in the front
camera image and publishes where the robot has to stand (`detected_dock_pose`), which the Nav2 docking server's dock
plugin follows (use_external_detection_pose).

  dock_target (std_msgs/Int32)         marker id to look for, sent by the FrybotMobile Controller; < 0 = not docking
  camera/image_raw (sensor_msgs/Image) front camera; only subscribed while docking (the simulator then renders the
                                       camera only during a docking approach)
  camera/camera_info                   intrinsics; without it they are computed from `hfov` (ideal pinhole, simulation)
  detected_dock_pose (PoseStamped)     the dock pose (x, y, heading the robot must reach) in the odometry frame

The marker position and the dock pose of every marker come from frybot_control.layout.docks(). The pose is kept in the
odometry frame and repeated for `hold_time` seconds after the marker was last seen: right in front of the wall the
marker may leave the image or get out of focus, and the last centimetres are then driven on odometry.

The robot's odometry pose comes from the `odom` topic (interpolated at the image time), not from TF: a Python TF
listener on the simulation's shared /tf cost 60 % of a CPU core per robot even while idle. TF is only read once, for
the fixed camera mounting. For the same reason the node does not follow the simulator clock: every time it needs
(image, odometry, the stamp of the published pose) is taken from the odometry and image messages themselves.
"""
import math

import cv2
import numpy as np
import rclpy
from geometry_msgs.msg import PoseStamped
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rclpy.time import Time
from nav_msgs.msg import Odometry
from sensor_msgs.msg import CameraInfo, Image
from std_msgs.msg import Int32
from tf2_ros import Buffer, TransformListener

from frybot_control import layout as L
# [수정 2026-11-18] P1(D1): 지도 이름 없이 뜨지 않음
from frybot_control.map_catalog import require_map_id

# optical frame (x right, y down, z forward) -> camera link (x forward, y left, z up)
R_LINK_OPT = np.array([[0.0, 0.0, 1.0], [-1.0, 0.0, 0.0], [0.0, -1.0, 0.0]])


def quat_matrix(q):
    """쿼터니언을 3x3 회전 행렬로 바꾼다.

    Args:
        q: x, y, z, w 속성을 가진 쿼터니언(geometry_msgs/Quaternion).

    Returns:
        numpy 3x3 회전 행렬.
    """
    x, y, z, w = q.x, q.y, q.z, q.w
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def yaw_of(q):
    """쿼터니언의 z 축 회전각(yaw, rad)을 구한다.

    Args:
        q: x, y, z, w 속성을 가진 쿼터니언.

    Returns:
        -pi~pi 범위의 yaw(rad).
    """
    return math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))


class ArucoDockDetector(Node):
    """도킹 중 앞 카메라로 벽 ArUco 마커를 찾아 도크 자세를 내는 노드.

    navigator.py 가 지도에 마커 도크가 있을 때만 로봇 네임스페이스에서
    띄운다. dock_target 이 마커 도크 ID 일 때만 영상·오도메트리를 구독한다.
    """

    def __init__(self):
        super().__init__('aruco_dock_detector')
        require_map_id('aruco_dock_detector')
        p = self.declare_parameter
        p('robot_id', 'pinky1')     # 선언만 하고 이 노드에서는 읽지 않음
        # base_frame: 로봇 기준, camera_frame: 카메라 장착 링크,
        # fixed_frame: 도크 자세를 내는 오도메트리 프레임
        # [수정 2026-11-18] P1: 프레임 기본값을 실기기 이름(접두어 없음)으로.
        # 시뮬(공유 /tf)은 navigator.py 가 '<로봇>/...' 를 넘김
        self.base_frame = p('base_frame', 'base_footprint').value
        self.camera_frame = p('camera_frame', 'front_camera_link').value
        self.fixed_frame = p('fixed_frame', 'odom').value
        self.optical = p('camera_frame_is_optical', False).value     # True: camera_frame already is an optical frame
        # hfov: camera_info 가 없을 때 쓰는 수평 화각(rad, 약 66도)
        # hold_time: 마커를 놓친 뒤 마지막 도크 자세를 계속 내는 시간(s)
        # marker_size: 마커 검은 사각형 한 변(m), image_topic: 영상 토픽
        self.hfov = p('hfov', 1.1519).value
        self.hold = p('hold_time', 4.0).value
        self.size = p('marker_size', L.MARKER_SIZE).value
        self.image_topic = p('image_topic', 'camera/image_raw').value
        # 마커 ID -> 도크 정보(layout.docks() 중 마커 도크만)
        self.docks = {d['marker_id']: d for d in L.docks().values() if d['kind'] == 'marker'}
        # ArUco 검출기(사전 이름은 layout.ARUCO_DICT)
        self.det = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, L.ARUCO_DICT)),
                                           cv2.aruco.DetectorParameters())
        # 마커 꼭짓점의 마커 좌표(m): 좌상, 우상, 우하, 좌하(검출 순서와 같음)
        s = self.size / 2
        self.obj = np.array([[-s, s, 0], [s, s, 0], [s, -s, 0], [-s, -s, 0]], dtype=np.float64)
        # 찾는 마커 ID(-1 = 도킹 아님), 영상 구독(도킹 중에만 있음)
        self.target, self.sub_img = -1, None
        # 카메라 내부 행렬(camera_info 로 채움)과 왜곡 계수(없으면 0)
        self.K, self.D = None, np.zeros(5)
        self.T_base_cam = None   # base <- 카메라 광학 프레임 (R, t)
        # 마지막 도크 자세(odom 프레임 x, y, yaw)와 그 영상 시각, 이번 도킹에서
        # 마커를 본 적 있는지, 마지막 발행 시각(오도메트리 시각)
        self.last, self.last_t, self.seen, self.pub_t = None, None, False, 0.0
        self.odom, self.pending, self.sub_odom = [], None, None      # [(t, x, y, yaw)] of the last second
        self.tf_buf = Buffer()
        self.tf_listener = TransformListener(self.tf_buf, self)      # dropped again once the camera mounting is known
        # 카메라 장착 TF 를 얻을 때까지 1초마다 시도
        self.tf_timer = self.create_timer(1.0, self._camera_tf)
        # 도크 자세 발행(docking_server 의 marker_dock 이 받음), 목표 마커 ID
        # 구독(mobile_controller 가 보냄), 카메라 내부값 구독
        self.pub = self.create_publisher(PoseStamped, 'detected_dock_pose', 5)
        self.create_subscription(Int32, 'dock_target', self._target, 5)
        self.create_subscription(CameraInfo, p('camera_info_topic', 'camera/camera_info').value, self._info,
                                 qos_profile_sensor_data)

    def _info(self, m):
        """camera_info 로 내부 행렬·왜곡을 갱신한다(k[0]=0 이면 무시)."""
        if m.k[0] > 0:
            self.K, self.D = np.array(m.k).reshape(3, 3), np.array(m.d if len(m.d) else [0.0] * 5)

    def _target(self, m):
        """목표 마커 ID 가 바뀌면 상태를 지우고 구독을 켜거나 끈다.

        마커 도크 ID 이면 영상·odom 구독을 만들고, 아니면(-1 등) 없앤다.
        """
        if m.data == self.target:
            return
        self.target, self.last, self.last_t, self.seen = m.data, None, None, False
        self.pending = None
        if m.data in self.docks and self.sub_img is None:
            self.odom = []
            self.sub_img = self.create_subscription(Image, self.image_topic, self._image, qos_profile_sensor_data)
            self.sub_odom = self.create_subscription(Odometry, 'odom', self._odom, 50)
        elif m.data not in self.docks and self.sub_img is not None:
            self.destroy_subscription(self.sub_img)
            self.destroy_subscription(self.sub_odom)
            self.sub_img = self.sub_odom = None

    def _camera_tf(self):
        """base <- camera optical frame (fixed mounting, read once from TF; the listener is then removed)."""
        try:
            t = self.tf_buf.lookup_transform(self.base_frame, self.camera_frame, Time()).transform
        except Exception:
            return
        R = quat_matrix(t.rotation)
        if not self.optical:
            R = R @ R_LINK_OPT
        self.T_base_cam = (R, np.array([t.translation.x, t.translation.y, t.translation.z]))
        self.destroy_timer(self.tf_timer)
        self.tf_listener.unregister()
        self.tf_listener = None

    def _odom(self, m):
        """오도메트리 1초 이력 갱신, 대기 측정 변환, 도크 자세 발행."""
        t = Time.from_msg(m.header.stamp).nanoseconds * 1e-9
        self.odom.append((t, m.pose.pose.position.x, m.pose.pose.position.y, yaw_of(m.pose.pose.orientation)))
        while self.odom and t - self.odom[0][0] > 1.0:
            self.odom.pop(0)
        self._resolve()
        if t - self.pub_t >= 0.045 or t < self.pub_t:               # publish at 20 Hz, stamped with the odometry time
            self.pub_t = t
            self._repeat(t, m.header.stamp)

    def _resolve(self):
        """Turn the pending measurement (dock pose in the base frame at the image time) into the odometry frame, with
        the robot pose AT THAT TIME: with the newest pose instead, a robot turning in place got the dock heading wrong
        by several degrees (image and odometry 0.1 s apart). Waits until odometry has passed the image time."""
        if self.pending is None or not self.odom:
            return
        ti, bx, by, byaw = self.pending
        if ti > self.odom[-1][0]:
            return
        self.pending = None
        if ti < self.odom[0][0]:
            return                                               # older than the odometry history
        for a, b in zip(self.odom, self.odom[1:] or [self.odom[0]]):
            if a[0] <= ti <= b[0]:
                break
        else:
            a = b = self.odom[0]
        f = 0.0 if b[0] == a[0] else (ti - a[0]) / (b[0] - a[0])
        dyaw = (b[3] - a[3] + math.pi) % (2 * math.pi) - math.pi
        ox, oy, oyaw = a[1] + f * (b[1] - a[1]), a[2] + f * (b[2] - a[2]), a[3] + f * dyaw
        self.last = (ox + math.cos(oyaw) * bx - math.sin(oyaw) * by, oy + math.sin(oyaw) * bx + math.cos(oyaw) * by,
                     oyaw + byaw)
        self.last_t = ti

    def _image(self, m):
        """영상에서 목표 마커를 찾아 base 프레임의 도크 자세를 pending 에 둔다.

        odom 프레임 변환은 _resolve 가 영상 시각의 오도메트리로 한다.
        """
        dock = self.docks.get(self.target)
        cam = self.T_base_cam
        if dock is None or cam is None:
            return
        # 인코딩별 채널 수. 모르는 인코딩이면 경고하고 버림
        ch = {'rgb8': 3, 'bgr8': 3, 'mono8': 1, 'rgba8': 4, 'bgra8': 4}.get(m.encoding)
        if ch is None:
            self.get_logger().warn(f'unsupported image encoding {m.encoding}', throttle_duration_sec=10.0)
            return
        # 행 패딩(step)을 잘라 (높이, 너비, 채널) 배열로 만든 뒤 회색조로
        img = np.frombuffer(m.data, np.uint8).reshape(m.height, m.step)[:, :m.width * ch].reshape(m.height, m.width, ch)
        gray = img[:, :, 0] if ch == 1 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY if m.encoding.startswith('bgr')
                                                         else cv2.COLOR_RGB2GRAY)
        # camera_info 가 없으면 hfov 로 이상적 핀홀 행렬을 만듦(시뮬)
        K = self.K
        if K is None:
            f = m.width / 2 / math.tan(self.hfov / 2)
            K = np.array([[f, 0, m.width / 2], [0, f, m.height / 2], [0, 0, 1]])
        # 마커 검출. 목표 ID 가 없으면 이번 영상은 버림
        corners, ids, _ = self.det.detectMarkers(np.ascontiguousarray(gray))
        if ids is None or self.target not in ids.flatten():
            return
        c = corners[list(ids.flatten()).index(self.target)].reshape(4, 2).astype(np.float64)
        # 정사각형 마커 PnP(IPPE): 해가 최대 2개. n_sol 은 쓰지 않음
        n_sol, rvecs, tvecs, _ = cv2.solvePnPGeneric(self.obj, c, K, self.D, flags=cv2.SOLVEPNP_IPPE_SQUARE)
        R_bc, t_bc = cam
        best = None
        for rvec, tvec in zip(rvecs, tvecs):
            normal = R_bc @ cv2.Rodrigues(rvec)[0][:, 2]            # marker's outward normal in the base frame
            pos = R_bc @ tvec.reshape(3) + t_bc
            # A square seen head-on has two pose solutions. The marker hangs on a vertical wall and faces the robot,
            # so take the one whose normal is the most level and points back at the robot.
            if normal[0] < 0 and (best is None or abs(normal[2]) < abs(best[0][2])):
                best = (normal, pos)
        if best is None:
            return
        normal, pos = best
        into = math.atan2(-normal[1], -normal[0])                   # heading "into the wall" in the base frame
        # 지도에 등록된 마커·도크 위치로 마커 기준 도크 상대 위치를 구해
        # 측정한 마커 자세에 붙여 base 프레임의 도크 자세로 바꿈
        mx, my, face = dock['marker']
        wall = face + math.pi                                       # the same heading in the map frame
        dx, dy = dock['x'] - mx, dock['y'] - my
        rx = math.cos(wall) * dx + math.sin(wall) * dy              # dock relative to the marker, in the wall frame
        ry = -math.sin(wall) * dx + math.cos(wall) * dy
        bx = pos[0] + math.cos(into) * rx - math.sin(into) * ry     # dock pose in the base frame
        by = pos[1] + math.sin(into) * rx + math.cos(into) * ry
        byaw = into + dock['yaw'] - wall
        self.pending = (Time.from_msg(m.header.stamp).nanoseconds * 1e-9, bx, by, byaw)
        self._resolve()
        if not self.seen:
            self.seen = True
            self.get_logger().info(f'marker {self.target} ({dock["name"]}) seen {math.hypot(pos[0], pos[1]):.2f} m ahead')

    def _repeat(self, t, stamp):
        """마지막 도크 자세를 hold_time 안에서만 odom 프레임으로 발행한다.

        t 는 지금 오도메트리 시각(s), stamp 는 발행 메시지에 넣을 시각.
        """
        if self.last is None or self.target not in self.docks or t - self.last_t > self.hold:
            return
        x, y, yaw = self.last
        ps = PoseStamped()
        ps.header.frame_id, ps.header.stamp = self.fixed_frame, stamp
        ps.pose.position.x, ps.pose.position.y = float(x), float(y)
        ps.pose.orientation.z, ps.pose.orientation.w = math.sin(yaw / 2), math.cos(yaw / 2)
        self.pub.publish(ps)


def main():
    """aruco_dock_detector 노드를 띄운다."""
    rclpy.init()
    try:
        rclpy.spin(ArucoDockDetector())
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
