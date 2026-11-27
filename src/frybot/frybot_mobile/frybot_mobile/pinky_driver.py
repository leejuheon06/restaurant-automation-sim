#!/usr/bin/env python3
# [수정 2026-11-17] pinky_pro 의존 제거: pinky_pro(pinklab-art, Apache-2.0,
# 커밋 014a09f)의 pinky_bringup/bringup.py 를 복사해 시작함. 그 뒤 A1(cmd_vel
# 시간 초과 정지)·T-37(serial_port 파라미터) 등으로 동작이 원본과 달라짐
# (아래 표기 참고)
# [수정 2026-11-18] P2(D3): 노드 이름만 원본의 pinky_bringup 에서 실행 파일과
# 같은 pinky_driver 로 바꿈
# [수정 2026-11-18] T-37: 위 커밋의 포트(/dev/ttyAMA4)는 우리 로봇과 달랐음.
# 로봇에 설치된 pinky_bringup(/dev/ttyAMA5)에 맞추고 serial_port 파라미터로 받음

"""Pinky Pro 바퀴 구동 노드(실기기 전용, robot.launch.py 가 Pinky Pi 에서 띄움).

cmd_vel(geometry_msgs/Twist)을 좌우 다이나믹셀 바퀴의 RPM 으로 바꿔 보내고,
엔코더로 적분한 바퀴 오도메트리를 odom 토픽과 odom -> base_footprint TF 로,
바퀴 관절값을 joint_states 로 낸다. battery/voltage 를 받아 저전압 경고만
남긴다. 토픽 이름은 상대 이름이라 노드 네임스페이스 아래에 붙는다.
"""

import rclpy
from rclpy.node import Node
import math
# [수정 2026-11-25] T-59: 종료 중 신호 처리(토크가 켜진 채 남던 문제)
import signal
import time

from geometry_msgs.msg import Twist, TransformStamped
from nav_msgs.msg import Odometry
from sensor_msgs.msg import JointState
from tf2_ros import TransformBroadcaster
from tf_transformations import quaternion_from_euler
from std_msgs.msg import Float32

from rclpy.executors import ExternalShutdownException
# [수정 2026-11-26] T-62: 종료 중 publish 가 내는 RCLError 를 받으려고 가져옴
# (rclpy 내부 모듈들과 같은 경로)
from rclpy.impl.implementation_singleton import rclpy_implementation as _rclpy

from .dynamixel_driver import DynamixelDriver

# 토픽·TF 프레임 이름(상대 이름)
TWIST_SUB_TOPIC_NAME = "cmd_vel"
ODOM_PUB_TOPIC_NAME = "odom"
JOINT_PUB_TOPIC_NAME = "joint_states"
ODOM_FRAME_ID = "odom"
ODOM_CHILD_FRAME_ID = "base_footprint"

# 모터 직렬 통신: 포트 기본값(serial_port 파라미터로 덮어씀), 통신 속도, 모터 ID
# [수정 2026-11-18] T-37: 로봇에 설치된 pinky_bringup 과 같은 포트(uart5)
SERIAL_PORT_NAME = "/dev/ttyAMA5"
BAUDRATE = 1000000  # bps
DYNAMIXEL_IDS = [1, 2] # [왼쪽 바퀴 ID, 오른쪽 바퀴 ID]

# joint_states 에 내는 바퀴 관절 이름. frybot_description 의 URDF 는
# l_wheel_joint / r_wheel_joint 라 이름이 다름(확인 필요: RViz 바퀴 표시)
JOINT_NAME_WHEEL_L = "left_wheel_joint"
JOINT_NAME_WHEEL_R = "right_wheel_joint"

# 바퀴 한 바퀴당 엔코더 펄스 수, RPM -> rad/s 변환 계수
PULSE_PER_ROT = 4096 
RPM2RAD = 2 * math.pi / 60

# 배터리 전압 토픽(pinky_battery 가 발행)과 저전압 경고 기준(V)
BATTERY_VOLTAGE_TOPIC = "battery/voltage"
LOW_BATTERY_THRESHOLD = 6.8

# [수정 2026-11-25] MT-7: cmd_vel 감시 시간 기본값 0.5 -> 0.3 s. MT-6 V2·V3
# (세 대 20회 왕복)에서 로봇 안 cmd_vel 간격 최대 67 ms, 0.3 s 로 발동 0회,
# 끊긴 뒤 더 가는 거리 약 5 -> 3.3~3.7 cm(0.08 m/s). 런치 인자로 바꿀 수 있음
CMD_VEL_TIMEOUT_DEFAULT = 0.3  # s

class Pinky(Node):
    """다이나믹셀 바퀴 두 개를 구동하고 바퀴 오도메트리를 내는 노드.

    초기화(포트 열기, 모터 재부팅·속도 모드 설정, 0 RPM, 엔코더 읽기) 중
    하나라도 실패하면 생성자가 일찍 return 해 토픽·타이머 없이 남는다.
    is_initialized 는 그 성공 여부지만 다른 곳에서 읽지 않는다.
    """

    def __init__(self):
        super().__init__('pinky_driver')
        self.is_initialized = False
        
        self.get_logger().info('Initializing Pinky Bringup Node with Dynamixel...')
        
        # 바퀴 반지름(m), 좌우 바퀴 중심 간격(m). robot.launch.py 도 같은 값
        self.declare_parameter('wheel_radius', 0.027)
        self.declare_parameter('wheel_separation', 0.0961)
        
        self.wheel_radius = self.get_parameter('wheel_radius').get_parameter_value().double_value
        self.wheel_separation = self.get_parameter('wheel_separation').get_parameter_value().double_value
        
        self.get_logger().info(f'Wheel radius: {self.wheel_radius}')
        self.get_logger().info(f'Wheel separation: {self.wheel_separation}')
        
        # 바퀴 둘레(m): 엔코더 회전 수 -> 이동 거리
        self.circumference = 2 * math.pi * self.wheel_radius
        # [수정 2026-11-18] T-37: 모터 직렬 포트를 파라미터로 받음
        port = self.declare_parameter('serial_port', SERIAL_PORT_NAME).value
        self.get_logger().info(f'Serial port: {port}')
        self.driver = DynamixelDriver(port, BAUDRATE, DYNAMIXEL_IDS)

        # 모터 초기화 1~4단계. 실패하면 로그만 남기고 생성자를 끝냄
        self.get_logger().info("1. Opening serial port...")
        if not self.driver.begin():
            self.get_logger().error("Failed to open serial port! Shutting down.")
            return

        self.get_logger().info("2. Initializing motors...")
        if not self.driver.initialize_motors():
            self.get_logger().error("Failed to initialize motors! Shutting down.")
            self.driver.terminate()
            return
        
        self.get_logger().info("Waiting for motors to be ready...")
        time.sleep(1.0)

        self.get_logger().info("3. Setting initial RPM to zero...")
        if not self.driver.set_double_rpm(0, 0):
            self.get_logger().error("Failed to set initial RPM! Shutting down.")
            self.driver.terminate()
            return

        self.get_logger().info("4. Reading initial encoder values...")
        _, _, self.last_encoder_l, self.last_encoder_r = self.driver.get_feedback()
        if self.last_encoder_l is None:
            self.get_logger().error("Failed to read initial encoder position! Shutting down.")
            self.driver.terminate()
            return

        self.get_logger().info(f"Initial Encoder read: L={self.last_encoder_l}, R={self.last_encoder_r}. Controller is responsive.")
            
        # [수정 2026-11-17] A1: 속도 명령 감시. cmd_vel 이 cmd_vel_timeout 초
        # 넘게 끊기면 0 RPM 을 보냄(0 이하면 감시 안 함). 다이나믹셀은 속도
        # 모드라 마지막 RPM 을 유지하므로, 보내는 쪽(Nav2, mobile_controller,
        # 네트워크)이 죽으면 로봇이 그 속도로 계속 갔음
        # [수정 2026-11-25] MT-7: 기본값 0.5 -> CMD_VEL_TIMEOUT_DEFAULT(0.3)
        self.cmd_timeout = self.declare_parameter(
            'cmd_vel_timeout', CMD_VEL_TIMEOUT_DEFAULT).value
        self._cmd_time = time.monotonic()   # 마지막 cmd_vel 수신 시각
        self._stop_pending = False   # 0 이 아닌 명령을 보냈고 아직 세우지 않음
        self._zero_failed = False    # 0 속도 명령의 전송이 실패함

        # 오도메트리·바퀴 관절값 발행, cmd_vel 구독, TF 송신,
        # 30 Hz 타이머(명령 감시 + 엔코더 읽기 + 발행)
        self.odom_pub = self.create_publisher(Odometry, ODOM_PUB_TOPIC_NAME, 10)
        self.joint_pub = self.create_publisher(JointState, JOINT_PUB_TOPIC_NAME, 10)
        self.twist_sub = self.create_subscription(Twist, TWIST_SUB_TOPIC_NAME, self.twist_callback, 10)
        self.tf_broadcaster = TransformBroadcaster(self)
        self.timer = self.create_timer(1.0 / 30.0, self.update_and_publish)

        # 배터리 전압(V) 구독: 저전압 경고 로그용
        self.battery_sub = self.create_subscription(
            Float32,
            BATTERY_VOLTAGE_TOPIC,
            self.battery_voltage_callback,
            10
        )

        # 바퀴 오도메트리 누적 자세(odom 프레임, m·rad). 기동 위치가 원점
        self.x = 0.0
        self.y = 0.0
        self.theta = 0.0
        self.last_time = self.get_clock().now()
        self.is_initialized = True
        self.get_logger().info('Pinky Bringup with Dynamixel has been started successfully.')

    def twist_callback(self, msg: Twist):
        """속도 명령을 좌우 바퀴 RPM 으로 바꿔 모터에 보낸다.

        차동 구동 역기구학(바퀴 선속도 = v -/+ w * 간격 / 2)을 쓴다.
        오른쪽 모터는 회전 방향이 반대라 부호를 뒤집는다(오도메트리도 같음).
        한쪽이 MAX_RPM 을 넘으면 두 바퀴를 같은 비율로 줄여 곡률을 유지한다.

        Args:
            msg: 속도 명령. linear.x(m/s)와 angular.z(rad/s)만 쓴다.
        """
        linear_x = msg.linear.x
        angular_z = msg.angular.z

        v_l = linear_x - (angular_z * self.wheel_separation / 2.0)
        v_r = linear_x + (angular_z * self.wheel_separation / 2.0)

        wheel_rads_l = v_l / self.wheel_radius
        wheel_rads_r = v_r / self.wheel_radius

        rpm_l = wheel_rads_l * 60.0 / (2 * math.pi)
        rpm_r = -wheel_rads_r * 60.0 / (2 * math.pi)

        max_val = max(abs(rpm_l), abs(rpm_r))
        MAX_RPM = 100.0  # 바퀴 RPM 상한
        if max_val > MAX_RPM:
            scale = MAX_RPM / max_val
            rpm_l *= scale
            rpm_r *= scale

        # [수정 2026-11-17] A1: 0 이 아닌 명령은 보내기 전에 "정지 필요"로
        # 표시하고, 0 RPM 전송이 성공했을 때만 지움. 0 명령 전송이 실패하면
        # 다음 주기(30 Hz)에 _watch_cmd_vel 이 바로 다시 보냄
        moving = abs(rpm_l) > 1e-6 or abs(rpm_r) > 1e-6
        self._cmd_time = time.monotonic()
        if moving:
            self._stop_pending, self._zero_failed = True, False
        if not self.driver.set_double_rpm(rpm_l, rpm_r):
            self.get_logger().warn("Failed to send motor command.")
            if not moving:
                self._zero_failed = True
        elif not moving:
            self._stop_pending = self._zero_failed = False

    # [수정 2026-11-17] 신규 (A1): 속도 명령 시간 초과 감시
    def _watch_cmd_vel(self) -> None:
        """명령이 끊겼거나 정지 전송이 실패했으면 0 RPM 을 보낸다.

        update_and_publish(30 Hz)의 맨 앞에서 불린다. 전송에 실패하면 표시를
        남겨 다음 주기에 다시 시도한다. 전송 성공은 패킷을 보냈다는 뜻이며
        실제 정지 여부는 오도메트리로 확인한다(실기기 확인 필요).
        """
        silent = time.monotonic() - self._cmd_time
        timed_out = (self._stop_pending and self.cmd_timeout > 0
                     and silent > self.cmd_timeout)
        if not (timed_out or self._zero_failed):
            return
        if self.driver.set_double_rpm(0, 0):
            self._stop_pending = self._zero_failed = False
            if timed_out:
                self.get_logger().warn(
                    f'cmd_vel silent for {silent:.2f} s: motors stopped')
        else:
            self.get_logger().warn(
                'Failed to send the stop command, retrying.',
                throttle_duration_sec=1.0)

    def update_and_publish(self):
        """30 Hz 타이머: 엔코더로 오도메트리를 적분해 TF·odom·관절값을 낸다.

        맨 앞에서 _watch_cmd_vel 로 명령 시간 초과를 감시한다. 모터 읽기에
        실패하면 그 주기를 건너뛴다(last_time 을 갱신하지 않음).
        """
        self._watch_cmd_vel()
        current_time = self.get_clock().now()
        dt = (current_time - self.last_time).nanoseconds / 1e9
        if dt <= 0: return

        feedback = self.driver.get_feedback()
        if feedback[0] is None:
            self.get_logger().warn("Failed to read motor data. Skipping update cycle.")
            return
        rpm_l, rpm_r, encoder_l, encoder_r = feedback

        # 주기 사이 엔코더 변화(펄스). 오른쪽은 모터 방향이 반대라 부호 반전
        delta_l = encoder_l - self.last_encoder_l
        delta_r = -(encoder_r - self.last_encoder_r)
        
        self.last_encoder_l = encoder_l
        self.last_encoder_r = encoder_r

        # 펄스 -> 바퀴 이동 거리(m)
        dist_l = (delta_l / PULSE_PER_ROT) * self.circumference
        dist_r = (delta_r / PULSE_PER_ROT) * self.circumference

        # 순기구학: 중심 이동 거리(m)와 방향 변화(rad). 방향을 먼저 갱신하고
        # 새 방향으로 위치를 적분함. theta 는 -pi~pi 로 감지 않음
        delta_distance = (dist_r + dist_l) / 2.0
        delta_theta = (dist_r - dist_l) / self.wheel_separation
        
        self.theta += delta_theta
        self.x += delta_distance * math.cos(self.theta)
        self.y += delta_distance * math.sin(self.theta)
        
        # odom twist 에 넣을 선속도(m/s)·각속도(rad/s)
        v_x = delta_distance / dt if dt > 0 else 0.0
        vth = delta_theta / dt if dt > 0 else 0.0

        self._publish_tf(current_time)
        self._publish_odometry(current_time, v_x, vth)
        self._publish_joint_states(current_time, rpm_l, rpm_r)

        self.last_time = current_time

    def _publish_tf(self, current_time):
        """바퀴 오도메트리 TF(odom -> base_footprint)를 보낸다.

        map -> odom 은 AMCL 이 낸다.
        """
        t = TransformStamped()
        t.header.stamp = current_time.to_msg()
        t.header.frame_id = ODOM_FRAME_ID
        t.child_frame_id = ODOM_CHILD_FRAME_ID
        t.transform.translation.x = self.x
        t.transform.translation.y = self.y
        q = quaternion_from_euler(0, 0, self.theta)
        t.transform.rotation.x, t.transform.rotation.y, t.transform.rotation.z, t.transform.rotation.w = q
        self.tf_broadcaster.sendTransform(t)

    def _publish_odometry(self, current_time, v_x, vth):
        """오도메트리 토픽을 발행한다. 공분산은 채우지 않는다(0)."""
        odom_msg = Odometry()
        odom_msg.header.stamp = current_time.to_msg()
        odom_msg.header.frame_id = ODOM_FRAME_ID
        odom_msg.child_frame_id = ODOM_CHILD_FRAME_ID
        odom_msg.pose.pose.position.x, odom_msg.pose.pose.position.y = self.x, self.y
        q = quaternion_from_euler(0, 0, self.theta)
        odom_msg.pose.pose.orientation.x, odom_msg.pose.pose.orientation.y, odom_msg.pose.pose.orientation.z, odom_msg.pose.pose.orientation.w = q
        odom_msg.twist.twist.linear.x, odom_msg.twist.twist.angular.z = v_x, vth
        self.odom_pub.publish(odom_msg)

    def _publish_joint_states(self, current_time, rpm_l, rpm_r):
        """바퀴 관절 위치(rad)·속도(rad/s)를 발행한다.

        오도메트리와 달리 오른쪽 바퀴 부호를 뒤집지 않은 원시값이다(확인 필요).
        """
        joint_msg = JointState()
        joint_msg.header.stamp = current_time.to_msg()
        joint_msg.name = [JOINT_NAME_WHEEL_L, JOINT_NAME_WHEEL_R]
        
        pos_l_rad = (self.last_encoder_l / PULSE_PER_ROT) * (2 * math.pi)
        pos_r_rad = (self.last_encoder_r / PULSE_PER_ROT) * (2 * math.pi)
        joint_msg.position = [pos_l_rad, pos_r_rad]
        joint_msg.velocity = [rpm_l * RPM2RAD, rpm_r * RPM2RAD]

        self.joint_pub.publish(joint_msg)

    def battery_voltage_callback(self, msg):
        """배터리 전압이 LOW_BATTERY_THRESHOLD 이하이면 경고를 남긴다.

        Args:
            msg: std_msgs/Float32, 배터리 전압(V). 5초마다 온다(pinky_battery).
        """
        self.current_voltage = msg.data
        
        # msg.data 는 항상 float 라 아래 None 분기는 실행되지 않음
        if self.current_voltage is None:
            self.get_logger().warn("Battery voltage data has not been received yet.")
        elif self.current_voltage <= LOW_BATTERY_THRESHOLD:
            self.get_logger().warn(
                f"!!! LOW BATTERY WARNING !!! Voltage: {self.current_voltage:.2f}V. Please charge the robot."
            )


# [수정 2026-11-25] 신규 (T-59): rclpy 가 신호를 받은 뒤 넘겨 부를 Python 처리기
def _ignore_signal(_signum, _frame) -> None:
    """아무것도 하지 않는 SIGINT 처리기(KeyboardInterrupt 를 내지 않음)."""


def main(args=None):
    """pinky_driver 노드를 띄우고, 끝날 때 모터를 세우고 토크를 끈다.

    Args:
        args: rclpy.init 에 넘길 명령행 인자.
    """
    # [수정 2026-11-25] T-59: rclpy 의 신호 처리기는 SIGINT 를 받으면 그 전에
    # 있던 Python 처리기도 부름. 기본 처리기면 KeyboardInterrupt 가 아무 데서나
    # 나서 (1) 다이나믹셀 통신 도중이면 포트가 '사용 중'으로 남아 terminate 의
    # 쓰기가 모두 조용히 실패하고 (2) 두 번째 SIGINT(stop_script 직접 + launch
    # 전달)가 terminate 를 중간에 끊어 토크가 켜진 채 남았음. 종료는 rclpy 가
    # 컨텍스트를 내려 spin 을 끝내는 길(ExternalShutdownException)로만 함
    signal.signal(signal.SIGINT, _ignore_signal)
    rclpy.init(args=args)
    node = None
    try:
        node = Pinky()
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    # [수정 2026-11-26] T-62: 신호로 컨텍스트가 내려간 뒤 30 Hz 타이머의
    # publish 가 "publisher's context is invalid" RCLError 를 내 종료 코드 1
    # 이 됐음. 종료 중(rclpy.ok() 거짓)의 것만 정상 종료로 받고, 컨텍스트가
    # 살아 있을 때 난 RCLError 는 통신 오류를 숨기지 않도록 다시 올림
    except _rclpy.RCLError:
        if rclpy.ok():
            raise
    # [수정 2026-11-25] T-59: 정리하는 동안 SIGINT·SIGTERM 을 무시해
    # terminate 가 끝까지 돌게 함. Pinky() 생성 중 예외(node None,
    # R16-29)도 막음.
    # rclpy.shutdown 은 신호로 이미 내려간 컨텍스트에서 RCLError 를 내므로
    # try_shutdown 으로
    finally:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        if node is not None:
            if not node.driver.terminate():
                node.get_logger().error(
                    'torque off failed on some motor (check torque_enable)')
            node.destroy_node()
        rclpy.try_shutdown()

if __name__ == '__main__':
    main()