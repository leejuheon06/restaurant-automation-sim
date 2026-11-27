"""FrybotMobile Controller: the software of one AMR (Pinky Pro + serving arm). Components from the SW architecture:
FrybotMobile Controller (NavigateRoute action, status), FrybotNavigator client (one Nav2 goal per granted segment),
FrybotMobile Arm Controller (ArmJob action), Camera Streamer (UDP).
  drive:=kinematic  moves the pose directly (lightweight simulation)
  drive:=nav2       every granted roadmap segment is a Nav2 NavigateToPose goal (global + local costmap, lidar)
  drive:=cmd_vel    straight-line cmd_vel/odom driving without costmaps (kept for comparison)
  pose_source:=gz   pose from the simulator's true model pose; this node publishes map -> odom (simulation)
  pose_source:=tf   pose from TF map -> base_frame, i.e. from AMCL (real robot); sends AMCL the initial pose
                    on proto only (measured maps: initial_pose / auto_localize)
[수정 2026-11-17] B3: 기본값은 실기기 값(drive=nav2, pose_source=tf). 시뮬 런치가 kinematic / gz 를 명시함.
[수정 2026-11-18] P1: base_frame 기본도 실기기 값(base_footprint).
로봇에서 런치 없이 단독 실행할 때는 /tf 리맵(/tf -> tf,
/tf_static -> tf_static)과 FRYBOT_MAP_ID 가 필요(robot.launch.py 참고).
Precise docking: when a route ends on a dock (charger, pick-up spot, dish return, table stop: layout.docks()), the
last segment is not a Nav2 goal. From the node before the dock the robot turns to the dock heading, the Nav2 docking
server drives it onto the dock pose (on the ArUco wall marker where there is one), and the heading is trimmed.
The camera is still a stand-in (JSON "frames"); so is the serving arm
(timed arm jobs) unless serving_arm:=real.
[수정 2026-11-20] serving_arm:=real 이면 팔 작업(/<robot>/arm_job)을 서빙 팔의
실물 구동부(/<robot>/serving_arm/arm_job, serving_arm_driver)로 넘김.
기본('')은 지금처럼 대역(시간만 지나면 성공).
한국어 요약: AMR 한 대에서 도는 제어기. 관제(task_manager)가 보낸
NavigateRoute 경로를 허가(TrafficGrant)받은 구간까지만 주행하고, 팔 작업
(ArmJob)을 수행하거나 실물 구동부로 넘기며, /fleet/robot_status 로
상태를 10 Hz 로 보고한다.
"""
import math
import threading
import time

# [수정 2026-11-20] 서빙 팔 전달: 팔 쪽 결과 상태 확인에 씀
from action_msgs.msg import GoalStatus
import rclpy
# [수정 2026-11-18] P3: TransformStamped·TFMessage·json 은 sim_backend 로 옮김
from geometry_msgs.msg import PoseStamped, PoseWithCovarianceStamped, Twist
from nav_msgs.msg import Odometry
from nav2_msgs.action import DockRobot, NavigateToPose
from nav2_msgs.msg import SpeedLimit
from nav2_msgs.srv import ClearEntireCostmap
from rclpy.action import ActionClient
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
# [수정 2026-11-19] T-41: 기본 QoS 이벤트 처리기를 끄는 데 씀
from rclpy.event_handler import PublisherEventCallbacks
from rclpy.event_handler import SubscriptionEventCallbacks
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.time import Time
from rclpy.qos import DurabilityPolicy
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import JointState, LaserScan
from std_msgs.msg import Float32, Int32, String
from tf2_ros import Buffer, TransformException
from tf2_ros import TransformListener

from frybot_control.layout import Graph, docks
# [수정 2026-11-18] P1(D1): 지도 이름 없이 뜨지 않음
from frybot_control.map_catalog import require_map_id
# [수정 2026-11-26] 2단계 보완: 지도 단위 후진 도킹 설정(roadmap.json)
from frybot_control.map_catalog import dock_backwards as map_dock_backwards
from frybot_interfaces.action import ArmJob, NavigateRoute
from frybot_interfaces.msg import ArmStatus, FleetHeartbeat, GuestTrack
from frybot_interfaces.msg import RobotStatus, TrafficGrant

from .arm_common import JOINTS, REST, CameraStreamer, arm_pose
# [수정 2026-11-20] T-49: 기동 때 자동 위치 추정과 마지막 자세 저장
from .auto_localize import AutoLocalizer
from .sim_backend import SimBackend  # [수정 2026-11-18] P3(D6)

# 이벤트용 QoS(README 의 EVENT): reliable, volatile, 깊이 100. 허가 구독에 씀
QOS = QoSProfile(depth=100, reliability=ReliabilityPolicy.RELIABLE, history=HistoryPolicy.KEEP_LAST)

# [수정 2026-11-19] T-41: QoS·타입 불일치 경고(rclpy 기본 이벤트 처리기)를
# 남겨 둘 토픽. 나머지 발행·구독에서는 끔. 처리기가 발행·구독마다 2개씩
# 붙어 실행기가 돌 때마다 확인하느라 Pinky 의 CPU 를 코어 절반 넘게 썼음
EVENT_TOPICS = ('/fms/heartbeat', '/fms/traffic_grant')

# [수정 2026-11-20] 서빙 팔 전달: 팔 쪽 액션을 확인하는 주기(초)와 취소를
# 보낸 뒤 팔이 멈췄다고 답하기를 기다리는 시간(초)
ARM_POLL_SEC = 0.05
ARM_CANCEL_WAIT_SEC = 5.0
# [수정 2026-11-26] 서빙 팔 자세 연동: 접기(rest)·펴기(0도 home) 작업 이름.
# serving_arm_driver 의 REST_JOB·HOME_JOB 과 같은 값(작업 이름 통일: HOME 은
# 0도 home 자세, REST 는 주행용 접은 자세. 11-20 의 HOME=rest 와 뜻이 다름)
ARM_REST_JOB, ARM_HOME_JOB = 'REST', 'HOME'
SERVING_ARM_MODES = ('', 'real')  # serving_arm 파라미터 허용값


def wrap(a):
    """각도를 [-pi, pi) 범위로 접는다.

    Args:
        a: 각도(rad).

    Returns:
        같은 방향의 [-pi, pi) 각도(rad).
    """
    return (a + math.pi) % (2 * math.pi) - math.pi


# [수정 2026-11-18] P2(D2): 클래스·노드 이름을 실행 파일과 같게(예전 Amr, amr)
class MobileController(Node):
    """AMR 한 대의 제어기(NavigateRoute·ArmJob 액션, 상태 보고)."""

    # [수정 2026-11-19] T-41: 발행·구독을 만드는 두 메서드를 감싸 기본 QoS
    # 이벤트 처리기를 끔. TF 수신(TransformListener)과 sim_backend 가 이
    # 노드에 만드는 것에도 같이 적용됨. 송수신 동작은 바뀌지 않음
    def create_publisher(self, msg_type, topic: str, qos_profile, **kwargs):
        """발행자를 만든다. EVENT_TOPICS 가 아니면 기본 이벤트 처리기를 끈다.

        Args:
            msg_type: 메시지 타입.
            topic: 토픽 이름.
            qos_profile: QoS 프로파일 또는 깊이.
            **kwargs: Node.create_publisher 의 나머지 인자.

        Returns:
            만들어진 발행자.
        """
        if topic not in EVENT_TOPICS:
            kwargs.setdefault('event_callbacks', PublisherEventCallbacks(
                use_default_callbacks=False))
        return super().create_publisher(msg_type, topic, qos_profile,
                                        **kwargs)

    def create_subscription(self, msg_type, topic: str, callback,
                            qos_profile, **kwargs):
        """구독을 만든다. EVENT_TOPICS 가 아니면 기본 이벤트 처리기를 끈다.

        Args:
            msg_type: 메시지 타입.
            topic: 토픽 이름.
            callback: 메시지를 받는 콜백.
            qos_profile: QoS 프로파일 또는 깊이.
            **kwargs: Node.create_subscription 의 나머지 인자.

        Returns:
            만들어진 구독.
        """
        if topic not in EVENT_TOPICS:
            kwargs.setdefault('event_callbacks', SubscriptionEventCallbacks(
                use_default_callbacks=False))
        return super().create_subscription(msg_type, topic, callback,
                                           qos_profile, **kwargs)

    def __init__(self):
        super().__init__('mobile_controller')
        require_map_id('mobile_controller')  # [수정 2026-11-18] P1(D1)
        p = self.declare_parameter  # 파라미터 선언(이름, 기본값)
        self.rid = p('robot_id', 'pinky1').value  # 로봇 이름(네임스페이스)
        # speed: 일반 주행 속도(m/s), guide_speed: 손님 안내 속도(m/s)
        self.speed, self.guide_speed = p('speed', 0.08).value, p('guide_speed', 0.05).value
        self.turn_rate = p('turn_rate', 2.5).value  # rad/s, kinematic
        # [수정 2026-11-17] B3: 기본값을 시뮬 값(kinematic, gz)에서 실기기 값
        # 으로 바꿈. 파라미터 없이 로봇에서 실행하면 움직이지 않고 경로를
        # "성공"으로 끝내던 것을 막음
        self.drive = p('drive', 'nav2').value  # kinematic / nav2 / cmd_vel
        self.pose_source = p('pose_source', 'tf').value  # tf(AMCL) / gz
        # [수정 2026-11-17] D4: 위치 추정(TF map -> base) 신선도 감시.
        # tf_stale_sec 보다 오래된 변환은 쓰지 않고, 새 변환이 이 시간 넘게
        # 없으면 주행을 세우고 SENSOR_ERROR 를 보고(0 이하면 감시 안 함)
        self.tf_stale = p('tf_stale_sec', 1.0).value
        self.tf_ok = False           # 가장 최근 조회에서 새 변환을 받았는지
        # [수정 2026-11-18] P1: 기본을 실기기 프레임 이름으로. 시뮬 런치가
        # '<로봇>/base_footprint' 를 명시함
        self.base_frame = p('base_frame', 'base_footprint').value  # TF 대상
        battery_topic = p('battery_topic', '').value          # real Pinky: battery/percent (std_msgs/Float32)
        # [수정 2026-11-18] P2: 실기기 쪽 이름의 real_ 접두어를 뺌
        # (real_battery -> battery_from_topic)
        self.battery_from_topic = bool(battery_topic)
        # follow_pause_dist: 손님이 이보다(m) 멀면 안내를 멈춤,
        # follow_resume_dist: 이보다(m) 가까워지면 다시 출발(_guest_away)
        self.follow_dist, self.resume_dist = p('follow_pause_dist', 0.30).value, p('follow_resume_dist', 0.22).value
        # 손님을 놓친 채 이 시간(초)이 지나면 GUEST_LOST 로 경로를 돌려줌
        self.guest_timeout = p('guest_timeout', 20.0).value
        # [수정 2026-11-17] UR-03: 손님 동행 확인을 /frybot/guest_track
        # (AI 서버의 추적 결과)으로 받음. 예전에는 시뮬 전용
        # /sim/world_state 의 손님 좌표를 직접 읽어 실기기에서는 확인이 없었음.
        # guest_track_required: 추적 값이 한 번도 오지 않아도 이탈로 볼지
        # guest_track_stale: 이 시간(초)보다 오래된 값은 "놓침"으로 봄
        self.track_required = p('guest_track_required', False).value
        self.track_stale = p('guest_track_stale', 1.5).value
        self.track = None            # (visit_id, visible, distance, 수신 시각)
        self.guide_goal = None       # 진행 중인 안내 경로의 목표 핸들
        self.track_warned = False  # 추적 없음 경고를 한 번만 냄
        # [수정 2026-11-17] UR-03: 실측 지도에서도 안내 구간(입구 -> 테이블)을
        # Nav2 로 후진 주행. 실측 지도의 FollowPath 는 전진 전용이라 후진용
        # 제어기 FollowPathReverse 를 구간마다 고름(_nav2_segment).
        # false 면 실측 지도의 안내 구간을 전진으로 주행
        self.guide_reverse = p('guide_reverse', True).value
        self._controller = ''        # 마지막으로 고른 Nav2 제어기
        # [수정 2026-11-17] UR-21: 실기기의 충전 여부 판정
        # (_charging_from_battery, 2026-11-18 P2 에서 _real_charging 을 고침)
        self.charge_rise = p('charge_rise_pct', 1.0).value  # 상승폭(%)
        self.charge_window = p('charge_window_sec', 300.0).value  # 창(초)
        self.idle_since, self.batt_hist = None, []  # 정지 시작, (시각, %)
        # [수정 2026-11-18] T-39: 충전대(지도의 home_nodes) 근처에 서 있을 때만
        # 충전 여부를 판정. 충전대가 없는 실측 지도에서 배터리 값의 흔들림을
        # 충전으로 잘못 보아 CHARGING 을 보고했고, 관제가 이동 명령을 거절했음
        self.charger_radius = p('charger_radius', 0.10).value
        self.arm_task = ''  # 팔 작업의 task_id
        # [수정 2026-11-20] 서빙 팔: '' = 대역(시간만 지나면 성공),
        # 'real' = 실물 구동부(/<robot>/serving_arm/arm_job)로 넘김.
        # serving_arm_wait_sec: 구동부를 찾거나 끊김을 판정하는 시간(초)
        self.serving_arm = p('serving_arm', '').value
        if self.serving_arm not in SERVING_ARM_MODES:
            raise ValueError(f'serving_arm:={self.serving_arm!r} 는 '
                             f'{SERVING_ARM_MODES} 중 하나여야 합니다')
        self.arm_wait = p('serving_arm_wait_sec', 2.0).value
        # Central control liveness / emergency stop (/fms/heartbeat). 0 = drive without checking the heartbeat.
        # [수정 2026-11-24] 기본 2.0 → 1.0 s: 정량 목표(1초 넘는 끊김 0건)와
        # Nav2 명령 끊김 정지 기준(1.0 s)에 맞춤. 실기기 확인 필요
        self.fms_timeout = p('fms_timeout', 1.0).value
        # hb_t: 마지막 생존 신호 수신 시각, hb_session: 관제 세션 ID,
        # estop: 이 로봇의 비상 정지 여부, void: 관제 재시작으로 버릴 경로 핸들
        self.hb_t, self.hb_session, self.estop, self.void = None, '', False, None
        self.nav2_retries = p('nav2_retries', 2).value       # measured map: extra tries of a segment Nav2 failed
        # Stepping aside (mode YIELD) on the real robot: back up along the granted edge with cmd_vel. The lidar looks
        # behind the robot first: scan angle of the robot's rear = pi - lidar_yaw (Pinky: lidar mounted turned by pi).
        self.yield_reverse = p('yield_reverse', True).value
        self.lidar_yaw = p('lidar_yaw', math.pi).value
        self.rear_stop = p('rear_stop_dist', 0.10).value     # m from the lidar (the rear edge is 4.5 cm behind it)
        self.rear, self.rear_t = None, 0.0                   # nearest return behind the robot, wall time of the scan
        # [수정 2026-11-26] 후진 도킹: 뒤 라이다 평가를 켠 시각(_rear_clear)
        self.rear_since = 0.0
        self.rear_wanted = 0.0                               # scans are evaluated until this wall time
        # [수정 2026-11-20] T-46: 앞쪽 라이다 정지. 도킹 접근(docking 단계와
        # 도크 노드로 가는 creep)과 막다른 노드에서 cmd_vel 로 전진할 때만
        # 검사. 거리는 라이다 기준 앞 방향 성분(m). 라이다는 로봇 중심보다
        # 1.7 cm 뒤(URDF rplidar_mount x = -0.017), footprint 앞끝은 중심에서
        # 6.2 cm -> 라이다에서 앞끝까지 7.9 cm. 0.10 이면 앞끝 2.1 cm 앞에서
        # 정지(10 Hz 스캔 지연 0.1 s x 도킹 최고 0.05 m/s = 5 mm 를 더 감)
        # v05 D1_STOP(벽에서 11.5 cm)의 정상 정지 때 라이다-벽은 약 13 cm
        # 라 오검출 없음. v04(벽 7.5 cm)는 9 cm 라 항상 먼저 정지함
        self.front_stop = p('front_stop_dist', 0.10).value   # 0 = 검사 끔
        # 앞쪽 구역의 옆 폭(라이다 중심선에서 좌우 m): 로봇 반폭 5.7 cm
        # + 0.8 cm. 통로·막다른 곳 옆벽(로봇 옆면에서 10 cm 이상, 통로 폭
        # 32 cm)은 들어오지 않음. 구역 각도는 앞 방향 +-60 도까지만 봄
        self.front_half_w = p('front_half_width', 0.065).value
        self.front, self.front_t = None, 0.0     # 앞 최소 거리, 스캔 시각
        # [수정 2026-11-27] T-63: Nav2 가 장애물 앞에서 구간을 포기하면
        # 돌려주기 전에 진행 반대쪽으로 조금 물러남(관제의 다음 경로가 그
        # 자리에서 제자리 회전할 때 모서리(반경 약 8.1 cm)가 장애물에 닿지
        # 않게). blocked_backoff_dist: 물러날 거리(m, 오도메트리, 0 이하면
        # 끔), blocked_backoff_trigger: 진행 방향 띠의 최소 거리가 이보다
        # (m, 몸 중심 기준) 가까울 때만, blocked_backoff_timeout: 시간
        # 제한(s)
        self.backoff_dist = p('blocked_backoff_dist', 0.05).value
        self.backoff_trigger = p('blocked_backoff_trigger', 0.20).value
        self.backoff_timeout = p('blocked_backoff_timeout', 4.0).value
        self.last_scan, self.last_scan_t = None, 0.0  # 마지막 스캔, 받은 시각
        self.front_wanted, self.front_since = 0.0, 0.0  # 평가 마감, 켠 시각
        # node_id: 마지막으로 도착한 노드, drive_error: 주행 실패
        # (NAV2_FAILED·NO_PROGRESS) 표시. 다음 도착 때 지움
        self.node_id, self.drive_error = '', False
        g = Graph()  # 활성 지도의 로드맵
        self.measured_map = bool(g.map_id)  # 실측 지도인지(proto 면 False)
        self.home = g.nodes[g.home_of(self.rid)]  # 이 로봇의 홈 노드 좌표(m)
        # [수정 2026-11-26] 서빙 팔 자세 연동: 홈(충전소) 노드 이름. 경로가
        # 여기서 끝나면 실물 팔을 0도 home 자세로 폄(_arm_home_later)
        self.home_node = g.home_of(self.rid)
        # [수정 2026-11-18] T-39: 충전 판정에 쓰는 충전대 좌표(실측 지도는 없음)
        self.charger_xy = [g.nodes[n] for n in sorted(g.home_nodes)]
        # [수정 2026-11-20] 막다른 노드(이웃 1개: 도크, 대기 위치). 여기 서
        # 있다가 뒤쪽 노드로 나갈 때는 제자리 회전 대신 후진(_navigate)
        self.dead_ends = {n for n in g.nodes if len(g.adj[n]) == 1}
        # [수정 2026-11-20] T-42(2차): 막다른 노드에서 출발할 때 이 거리(m)
        # 안이면 그 노드는 이미 도착한 것으로 봄(도킹 뒤 남는 1~2 cm 오차로
        # 0번 구간이 Nav2 로 가서 벽 앞 제자리 회전을 했음, serve_v04_real_s3)
        self.dead_end_settle = p('dead_end_settle_dist', 0.05).value
        # [수정 2026-11-20] T-44: 막다른 노드에서 더 벗어나 있어도 '막다른
        # 노드 - 출구 노드' 선분 옆 이 거리(m) 안이면 출구로 바로 감
        self.dead_end_lane = p('dead_end_lane_dist', 0.05).value
        # [수정 2026-11-20] T-44: 무진행 감시. 주행 중 이 시간(초) 동안 위치
        # no_progress_dist(m)·방향 no_progress_yaw(rad) 넘게 바뀌지 않으면
        # NO_PROGRESS 로 경로를 돌려줌(0 이하면 감시 안 함). 허가·관제·위치
        # 추정·손님 대기 중에는 재지 않음
        self.no_progress_sec = p('no_progress_sec', 20.0).value
        self.no_progress_dist = p('no_progress_dist', 0.03).value
        self.no_progress_yaw = p('no_progress_yaw', 0.2).value
        # 현재 자세(지도 좌표 m, rad). 위치를 받기 전에는 홈 좌표로 시작
        self.x, self.y, self.yaw = self.home[0], self.home[1], 0.0
        self.spawn = (self.x, self.y)  # 출발 위치(초기 자세·추측 항법 기준)
        # battery: 잔량(%, 시뮬 초깃값), charging: 충전 중으로 보고할지
        self.battery, self.charging = p('battery', 100.0).value, False
        # cur: 지금 실행할 경로 목표 핸들, grants: plan_version -> 허가 인덱스
        self.cur, self.grants = None, {}
        # pv: 경로 번호, reached: 도착한 경로 인덱스(-1 = route[0] 전),
        # task_id: 임무 ID, nav_state: 보고할 주행 상태
        self.pv, self.reached, self.task_id, self.nav_state = 0, -1, '', 'IDLE'
        # arm_state: 팔 작업 이름 또는 IDLE, arm_q: 팔 관절값(RViz용),
        # wheel: kinematic 주행이 누적한 바퀴 각(rad, sim_backend 가 표시)
        self.arm_state, self.arm_q, self.wheel = 'IDLE', list(REST), 0.0
        self.lock = threading.Lock()  # cur 교체 보호
        cb = ReentrantCallbackGroup()  # 콜백 동시 실행 허용
        # 상태 보고(RobotStatus) -> task_manager, 10 Hz(_publish)
        self.pub_status = self.create_publisher(RobotStatus, '/fleet/robot_status', 50)
        # 서빙 팔 관절값 -> RViz 모델(/<robot>/arm/joint_states)
        self.pub_arm_js = self.create_publisher(JointState, f'/{self.rid}/arm/joint_states', 10)
        # 속도 명령 -> pinky_driver(직접 주행·회전·정지)
        self.pub_cmd = self.create_publisher(Twist, f'/{self.rid}/cmd_vel', 10)
        # 통행 허가(EVENT QoS) 구독
        self.create_subscription(TrafficGrant, '/fms/traffic_grant', self._grant, QOS, callback_group=cb)
        # 관제 생존 신호·비상 정지 목록 구독
        self.create_subscription(FleetHeartbeat, '/fms/heartbeat', self._heartbeat, 10, callback_group=cb)
        # 라이다: 앞뒤 정지 검사용(경량 시뮬은 구독 안 함)
        if self.drive != 'kinematic':
            self.create_subscription(LaserScan, f'/{self.rid}/scan', self._scan, qos_profile_sensor_data, callback_group=cb)
        # 안내 중인 손님의 동행 추적 결과(central_control)
        self.create_subscription(GuestTrack, '/frybot/guest_track',
                                 self._guest_track, 10, callback_group=cb)
        # [수정 2026-11-17] UR-17, 19: 서빙 팔의 상태·오류 보고
        self.pub_arm_status = self.create_publisher(
            ArmStatus, '/fleet/arm_status', 20)
        # n2: 진행 중인 Nav2 구간. key=(pv, 구간), state=ACTIVE/SUCCEEDED/
        # FAILED, handle=목표 핸들, t_fail=실패 시각, fails·fail_key=같은
        # 노드 연속 실패, turning=회전 중 key, direct=직접 주행 노드,
        # try_*=15초 무진행 감시, goal_fk=보낸 목표 노드
        self.n2 = dict(key=None, state='', handle=None, t_fail=0.0, fails=0, fail_key=None, turning=None, direct=None, try_fk=None,
                       try_t0=0.0, try_pos=(0.0, 0.0), goal_fk=None)
        # docks by node position; dk = state of the docking approach in progress
        self.docks = {(round(d['x'], 3), round(d['y'], 3)): d for d in docks().values()}
        # [수정 2026-11-26] 후진 도킹(사용자 결정 방안 다: 모든 도크 후진).
        # 실측 지도는 기본 True(도크에 뒤로 들어감, 도킹 서버 dock_backwards 도
        # navigator.py 가 실측 지도에서 true), 가상 매장(proto)의 마커 도크는
        # 앞 카메라로 마커를 보므로 False(예전대로 전진). 도크의 yaw_deg 는
        # 두 경우 모두 도킹한 로봇이 향하는 방향
        # [수정 2026-11-26] 2단계 보완: 기본값을 지도의 roadmap.json
        # "dock_backwards"(없으면 실측 지도 true)에서 읽음. v04·v05 는 false
        self.dock_backwards = p(
            'dock_backwards',
            map_dock_backwards(g.map_id) if self.measured_map
            else False).value
        self.use_docking = p('docking', True).value          # false: Nav2 segment + heading trim only
        self.yaw_tol = p('dock_yaw_tolerance', 0.012).value  # rad, heading error left after the trim
        self.trim_w = p('dock_trim_speed', 0.15).value       # rad/s, slowest turn of the trim (above the motor deadband)
        # [수정 2026-11-20] 마무리 회전(trim) 시간 제한(초, 0 = 제한 없음).
        # 마커 없는 도크는 AMCL 방향으로 판정해, 흔들림이 허용 오차를 넘나들면
        # 회전이 끝나지 않고 다음 작업(LOAD)도 시작되지 않았음
        self.trim_timeout = p('dock_trim_timeout', 6.0).value
        # dk: 도킹 상태. stage=start/align/turn/docking/drive/settle/trim,
        # state=도킹 서버 결과, handle=목표 핸들, marker=찾을 마커 ID(-1 없음)
        self.dk = dict(key=None, stage='', state='', handle=None, marker=-1)
        self.det = None  # (dock yaw in odom frame, wall time, map x, map y)
        # Nav2 구동일 때만: 도킹·구간 주행 액션, 속도 제한, 코스트맵 비우기
        if self.drive == 'nav2':
            # 도킹 서버 액션(Nav2 docking_server)
            self.dock_cli = ActionClient(self, DockRobot, f'/{self.rid}/dock_robot', callback_group=cb)
            # 찾을 마커 ID -> aruco_dock_detector(0.5초마다 재발행)
            self.pub_dock_target = self.create_publisher(Int32, f'/{self.rid}/dock_target', 5)
            # 검출된 도크 자세(오도메트리 프레임, _detected)
            self.create_subscription(PoseStamped, f'/{self.rid}/detected_dock_pose', self._detected, 5, callback_group=cb)
            self.create_timer(0.5, lambda: self.pub_dock_target.publish(Int32(data=self.dk['marker'])), callback_group=cb)
            # 구간 주행 액션(NavigateToPose)
            self.nav2 = ActionClient(self, NavigateToPose, f'/{self.rid}/navigate_to_pose', callback_group=cb)
            # 안내 속도 제한(_set_speed_limit)
            self.pub_limit = self.create_publisher(SpeedLimit, f'/{self.rid}/speed_limit', 10)
            # [수정 2026-11-17] UR-03: 구간에 쓸 Nav2 제어기 선택
            # (bt_navigator 의 ControllerSelector 가 받음, 마지막 값 유지)
            self.pub_controller = self.create_publisher(
                String, f'/{self.rid}/controller_selector',
                QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                           durability=DurabilityPolicy.TRANSIENT_LOCAL))
            self._limit = None  # 마지막 속도 제한(None = 없음)
            # 지역 코스트맵 비우기 서비스
            self.clear_local = self.create_client(ClearEntireCostmap, f'/{self.rid}/local_costmap/clear_entirely_local_costmap',
                                                  callback_group=cb)
        # odom: 오도메트리 자세(x, y, yaw), have_truth: 위치를 받은 적 있음
        self.odom, self.have_truth = (0.0, 0.0, 0.0), False
        # [수정 2026-11-17] T-25: 실측 지도를 경량 시뮬(drive=kinematic)로
        # 돌리면 위치 추정원이 없어 상태 보고가 나가지 않았음. 자세를 직접
        # 움직이므로 그 값을 참값으로 봄. 실기기(drive=nav2)는 해당 없음
        if self.drive == 'kinematic' and self.measured_map:
            self.have_truth = True
        # 실기기: TF(map -> base_frame)를 20 Hz 로 조회해 위치를 받음
        if self.pose_source == 'tf':
            self.tf_buf = Buffer()
            self.tf_listener = TransformListener(self.tf_buf, self)
            # AMCL 초기 자세(_initial_pose, auto_localize 가 씀)
            self.pub_init = self.create_publisher(PoseWithCovarianceStamped, f'/{self.rid}/initialpose', 1)
            self.create_timer(0.05, self._tf_pose, callback_group=cb)
            if not self.measured_map:  # proto 만 2초마다
                self.create_timer(2.0, self._initial_pose, callback_group=cb)
        if self.battery_from_topic:  # 실기기 배터리 토픽
            # [수정 2026-11-17] UR-21: 충전 판정을 위해 값을 기록하며 받음
            self.create_subscription(Float32, battery_topic, self._battery, 5,
                                     callback_group=cb)
        # 오도메트리: 무진행 감시·도킹 방향 계산에 씀
        if self.drive in ('cmd_vel', 'nav2'):
            self.create_subscription(Odometry, f'/{self.rid}/odom', self._odom, 20, callback_group=cb)
        # 경로 실행 액션 서버(관제 -> 로봇). 새 목표는 _accepted 에서 선점
        ActionServer(self, NavigateRoute, f'/{self.rid}/navigate_route', execute_callback=self._navigate,
                     goal_callback=lambda g_: GoalResponse.ACCEPT, cancel_callback=lambda g_: CancelResponse.ACCEPT,
                     handle_accepted_callback=self._accepted, callback_group=cb)
        # 팔 작업 액션 서버(대역 또는 실물 구동부로 전달)
        ActionServer(self, ArmJob, f'/{self.rid}/arm_job', execute_callback=self._arm_job,
                     cancel_callback=lambda g_: CancelResponse.ACCEPT, callback_group=cb)
        # [수정 2026-11-20] 실물 서빙 팔로 넘길 때만 만드는 액션 클라이언트
        self.arm_cli = None
        if self.serving_arm == 'real':
            self.arm_cli = ActionClient(
                self, ArmJob, f'/{self.rid}/serving_arm/arm_job',
                callback_group=cb)
        # [수정 2026-11-26] 서빙 팔 자세 연동(serving_arm:=real 일 때만 씀).
        # arm_pose: 실물 팔 자세를 작업 결과로 추적(HOME / REST / UNKNOWN).
        # 기동 때는 충전소 대기 조건대로 HOME(구동부는 기동 때 팔을 움직이지
        # 않음). arm_lock: 팔 구동부에 한 번에 한 목표만(접기·펴기·관제 작업),
        # arm_preempt: 펴기(HOME)를 다른 작업이 끊어야 할 때 True.
        # arm_home_delay: 홈에서 경로가 끝난 뒤 펴기까지 기다리는 시간(초)
        self.arm_pose = 'HOME'
        self.arm_lock = threading.Lock()
        self.arm_preempt = False
        self.arm_home_delay = p('arm_home_delay', 1.0).value
        # 지역 코스트맵 1초 주기 비우기(가상 매장만, _refresh_costmap)
        if self.drive == 'nav2':
            self.create_timer(1.0, self._refresh_costmap, callback_group=cb)
        # Camera Streamer 대역: AI 서버로 UDP JSON 프레임
        self.cam = CameraStreamer(f'{self.rid}_front', host=p('ai_host', '127.0.0.1').value,
                                  port=p('ai_udp_port', 9100).value)
        # 상태 보고 10 Hz, AI 서버로 위치 1 Hz, 팔 상태 2 Hz
        self.create_timer(0.1, self._publish, callback_group=cb)
        self.create_timer(1.0, lambda: self.cam.send('amr', robot_id=self.rid, x=self.x, y=self.y), callback_group=cb)
        self.create_timer(0.5, self._publish_arm, callback_group=cb)
        # [수정 2026-11-18] P3(D6): 시뮬 전용 입력·출력(/gz/model_poses,
        # /sim/world_state, map -> base TF, 가짜 배터리·바퀴 관절값)은
        # 시뮬 값일 때만 붙는 sim_backend 가 맡음. 실기기(nav2/tf)는 없음
        self.sim = (SimBackend(self, cb, [g.nodes[n] for n in g.home_nodes])
                    if self.drive == 'kinematic' or self.pose_source != 'tf'
                    else None)
        # [수정 2026-11-20] T-49: 실기기 라이다 구동(nav2 + AMCL, 실측 지도)
        # 에서만 붙음. 초기 자세(initial_pose)를 받았거나 auto_localize 가
        # 꺼져 있으면 찾지 않고 마지막 자세 저장만 함
        self.locz = None
        if (self.drive == 'nav2' and self.pose_source == 'tf'
                and self.measured_map):
            search = (p('auto_localize', True).value
                      and not p('initial_pose', '').value.strip())
            self.locz = AutoLocalizer(self, cb, g.map_id, search, dict(
                # 맞는 자세의 점수 상한(m). 가짜 스캔(잡음 1~2 cm, 가림
                # 포함) 맞는 자세 0.004~0.019, 틀린 자세 0.012 이상이 나옴.
                # 실측 지도의 벽 오차를 감안해 넉넉히 0.04(실기기 확인 필요)
                max_score=p('localize_max_score', 0.04).value,
                # 모호 판정의 점수 차(m). 가짜 스캔에서 지도가 180 도
                # 대칭인 W3 은 차이 0.002~0.003, 다른 자리는 0.008 이상
                margin=p('localize_margin', 0.006).value,
                # 탐색 시간 상한(s). PC 0.3 s, Pi 4 는 약 10 배로 추정
                budget=p('localize_budget_sec', 30.0).value,
                store_dir=p('pose_store_dir', '~/.frybot/last_pose').value,
                # [수정 2026-11-20] T-50: 저장 자세가 없을 때 모호하면 자기 홈
                # 노드 30 cm 안 후보를 고름(실기기 08 첫 기동 두 대 모두 홈에서
                # 대칭 후보와 4.4·5.5 mm 차이로 AMBIGUOUS)
                home_prior=p('localize_home_prior', True).value,
                # [수정 2026-11-23] T-55: 모호하면 관제 PC 의 천장 카메라
                # (/frybot/spot_check)에 먼저 물음. 없으면 아래 규칙 그대로.
                # 문턱 근거는 scan_match.pick_by_camera(17 A·B 측정)
                camera=p('localize_camera', True).value,
                camera_timeout=p('localize_camera_timeout_sec', 3.0).value,
                # [수정 2026-11-23] T-57: 서비스 발견+응답을 기다리는 상한.
                # 노드(클라이언트) 생성 시각부터 잼. 세 대 동시 기동에서
                # 기동 중 생긴 참가자는 발견에 20~28 s 걸렸음(19-B 진단)
                camera_wait=p('localize_camera_wait_sec', 35.0).value,
                camera_hi=p('localize_camera_hi', 0.15).value,
                camera_lo=p('localize_camera_lo', 0.05).value,
                camera_sep=p('localize_camera_sep', 0.30).value,
                # [수정 2026-11-20] T-50: 서 있을 때 위치 추정 감시·보정
                monitor=p('pose_monitor', True).value,
                # 점검 주기(s). 서 있을 때만, 점수 계산은 1 ms 수준(Pi CPU)
                check_period=p('pose_check_period_sec', 8.0).value,
                # 이 점수(m) 이하면 맞다고 봄. 가짜 스캔에서 맞는 자세 0.005~
                # 0.020(잡음 2 cm·다른 로봇 가림 포함), 25 도·6 cm 틀린 자세
                # 0.049~0.062. 그 사이에서 낮게 잡고, 실제 보정 여부는 아래
                # improve·뚜렷함 조건이 정함
                check_score=p('pose_check_score', 0.012).value,
                # 새 자세가 이만큼(m) 넘게, 그리고 0.6 배 이하로 좋아야 보정
                improve=p('pose_fix_improve', 0.005).value,
                # 보정 뒤 다음 보정까지 최소 간격(s)
                fix_interval=p('pose_fix_interval_sec', 20.0).value,
                # 보정 방향 폭이 이보다 크면 오류 로그로 경고(도)
                warn_yaw_deg=p('pose_fix_warn_deg', 30.0).value))
        self.get_logger().info(f'{self.rid} ready at ({self.x:.2f}, {self.y:.2f}) drive={self.drive}')

    # ------------------------------------------------------------ inputs
    def _grant(self, m):
        # Permissions are kept per plan version and only for the current route or a newer one: versions never repeat
        # (the Task Manager numbers them from a time-based start), so anything older is stale.
        if m.robot_id == self.rid and m.plan_version >= self.pv:
            self.grants[m.plan_version] = max(self.grants.get(m.plan_version, 0), m.granted_index)

    def _heartbeat(self, m):
        """관제 생존 신호를 받는다(관제 재시작 감지, 비상 정지 목록)."""
        if self.hb_session and m.session != self.hb_session:      # the Task Manager restarted: it knows nothing of
            self.grants = {}                                       # our route and holds no locks for it
            self.void = self.cur
            self.get_logger().warn(f'{self.rid}: Task Manager restarted, dropping the current route and permissions')
        self.hb_session, self.hb_t = m.session, time.time()
        estop = self.rid in m.estop  # 정지 목록에 이 로봇이 있는지
        if estop != self.estop:
            self.get_logger().warn(f'{self.rid}: emergency stop {"ON" if estop else "released"}')
            if estop and self.drive != 'kinematic':
                self.pub_cmd.publish(Twist())
        self.estop = estop

    def _fms_alive(self):
        """관제 생존 신호가 fms_timeout 안에 왔는지(0 이하면 항상 True)."""
        return self.fms_timeout <= 0 or (self.hb_t is not None and time.time() - self.hb_t <= self.fms_timeout)

    def _scan(self, m):
        """Nearest lidar return in the 50 deg sector behind the robot (for backing out of the way). Only evaluated
        while the robot is about to reverse or reversing: the scan arrives at 10 Hz and the Pinky's CPU is busy.
        앞쪽 구역(T-46, 도킹·막다른 곳 출구)도 필요할 때 같은 스캔에서
        평가함."""
        # [수정 2026-11-20] T-46: 앞쪽 구역도 같은 스캔에서(필요할 때만)
        now = time.time()
        # [수정 2026-11-27] T-63: 막힘 뒤 물러나기(_band_min)용으로 보관
        self.last_scan, self.last_scan_t = m, now
        if now <= self.front_wanted:
            self.front, self.front_t = self._front_min(m), now
        if now > self.rear_wanted:
            return
        rear = math.pi - self.lidar_yaw  # 로봇 뒤쪽의 스캔 각도
        best = float('inf')
        for i, r in enumerate(m.ranges):
            # 0.06 m 미만(자기 몸·무효)은 빼고 뒤쪽 +-0.44 rad(약 25도)
            if 0.06 <= r < best and abs(wrap(m.angle_min + i * m.angle_increment - rear)) <= 0.44:
                best = r
        self.rear, self.rear_t = best, time.time()

    # [수정 2026-11-20] T-46: 신규
    def _front_min(self, m: LaserScan) -> float:
        """로봇 앞 직사각형 구역에서 가장 가까운 점의 앞 방향 거리.

        Args:
            m: 라이다 스캔.

        Returns:
            라이다 기준 앞 방향 거리(m). 구역에 점이 없으면 inf.
        """
        best = float('inf')
        for i, r in enumerate(m.ranges):
            if not 0.06 <= r < 1.0:              # 자기 몸·무효값·먼 점 제외
                continue
            # 로봇 기준 각도(라이다가 lidar_yaw 만큼 돌아 붙음)
            a = wrap(m.angle_min + i * m.angle_increment + self.lidar_yaw)
            if abs(a) > math.pi / 3:  # 앞 +-60도 밖
                continue
            ahead, side = r * math.cos(a), r * math.sin(a)
            if abs(side) <= self.front_half_w and ahead < best:
                best = ahead
        return best

    # [수정 2026-11-20] T-46: 신규
    def _front_clear(self) -> bool | None:
        """앞쪽 라이다 검사 결과를 돌려준다(부를 때마다 스캔 평가를 켬).

        Returns:
            True: 트임(또는 검사 끔). False: front_stop_dist 안에 무엇이
            있음. None: 아직 새 스캔이 없음(검사를 막 켰거나 끊김).
        """
        if self.front_stop <= 0:
            return True
        now = time.time()
        if now > self.front_wanted:              # 꺼져 있다 다시 켬
            self.front_since = now
        self.front_wanted = now + 2.0
        if self.front is None or self.front_t < self.front_since \
                or now - self.front_t > 1.0:
            return None
        return self.front >= self.front_stop

    # [수정 2026-11-18] P3: _world(/sim/world_state)는 sim_backend 로 옮김

    # [수정 2026-11-17] 신규 (UR-03): 손님 추적
    def _guest_track(self, m: GuestTrack) -> None:
        """AI 서버가 본 손님의 동행 상태를 받는다 (이 로봇 것만)."""
        if m.robot_id == self.rid:
            self.track = (m.visit_id, m.visible, m.distance, time.time())

    # [수정 2026-11-18] P3: _guide_frame(안내 카메라 프레임 대역)은 sim_backend 로
    # 옮김. 실기기 카메라 영상 송신은 아직 없음

    def _guest_away(self, visit_id: int, limit: float) -> bool:
        """안내 중인 손님이 따라오지 못하고 있는지 판단한다.

        Args:
            visit_id: 안내 중인 손님 그룹.
            limit: 이 거리(m)보다 멀면 뒤처진 것으로 봄.

        Returns:
            멈춰서 기다려야 하면 True. 추적 값을 받은 적이 없으면
            guest_track_required 값(기본 False: 확인 없이 진행).
        """
        track = self.track
        if track is None or track[0] != visit_id:
            if not self.track_warned:
                self.track_warned = True
                self.get_logger().warn(
                    f'{self.rid}: no guest tracking for visit {visit_id} '
                    '(/frybot/guest_track): guiding without the follow check'
                    if not self.track_required else
                    f'{self.rid}: no guest tracking for visit {visit_id}: '
                    'waiting')
            return self.track_required
        _, visible, distance, stamp = track
        if time.time() - stamp > self.track_stale:
            return True                    # 추적이 끊김: 손님을 놓친 것으로 봄
        return not visible or distance > limit

    # [수정 2026-11-17] 신규 (UR-21): 실기기 충전 여부
    def _battery(self, m: Float32) -> None:
        """배터리 잔량(%)을 받고, 서 있는 동안의 값을 기록한다."""
        self.battery = float(m.data)
        now = time.time()
        # 30초 넘게 서 있을 때만 기록(정지 직후 전압 회복 구간 제외)
        if self.idle_since is not None and now - self.idle_since >= 30.0:
            self.batt_hist.append((now, self.battery))
            self.batt_hist = [s for s in self.batt_hist
                              if now - s[0] <= self.charge_window]

    # [수정 2026-11-18] P2: 이름에서 real_ 접두어를 뺌
    def _charging_from_battery(self) -> bool:
        """실기기가 충전 중인지 배터리 잔량의 변화로 추정한다.

        Pinky 는 충전 신호를 따로 내지 않는다. 30초 넘게 서 있는 동안
        잔량이 charge_window_sec 안에 charge_rise_pct 이상 올랐으면 충전 중으로
        본다 (정지 직후 전압이 회복되는 구간은 제외). 임계값은 실기기 확인 필요.
        """
        # [수정 2026-11-18] T-39: 충전대 근처가 아니면 충전 중이 아님
        on_charger = any(math.hypot(self.x - cx, self.y - cy)
                         < self.charger_radius for cx, cy in self.charger_xy)
        if (self.nav_state != 'IDLE' or self.arm_state != 'IDLE'
                or not on_charger):
            self.idle_since, self.batt_hist = None, []
            return False
        if self.idle_since is None:
            self.idle_since = time.time()
        if len(self.batt_hist) < 2:
            return False
        low = min(pct for _, pct in self.batt_hist)
        return self.batt_hist[-1][1] - low >= self.charge_rise

    # [수정 2026-11-17] 신규 (UR-17, 19): 서빙 팔 상태 보고
    def _publish_arm(self) -> None:
        """서빙 팔의 상태를 /fleet/arm_status 로 보낸다 (대역: 오류 없음)."""
        if self.measured_map and not self.have_truth:  # 위치 모르면 안 냄
            return
        busy = self.arm_state != 'IDLE'
        self.pub_arm_status.publish(ArmStatus(
            stamp=self.get_clock().now().to_msg(), arm_id=self.rid,
            state='ARM_OPERATING' if busy else 'IDLE',
            job=self.arm_state if busy else '',
            task_id=self.arm_task if busy else '', error=''))

    def _odom(self, m):
        """오도메트리를 받는다. 위치 원천이 없으면 출발점 기준 추측 항법."""
        p, q = m.pose.pose.position, m.pose.pose.orientation
        # 쿼터니언 -> yaw
        self.odom = (p.x, p.y, math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z)))
        if not self.have_truth and self.pose_source != 'tf':   # no localisation source: dead reckoning from the start
            self.x, self.y, self.yaw = self.spawn[0] + p.x, self.spawn[1] + p.y, self.odom[2]

    def _tf_pose(self):
        """Localisation on the real robot: map -> base_frame from TF (AMCL publishes map -> odom)."""
        # [수정 2026-11-17] D4: 변환의 시각을 확인. AMCL 이나 오도메트리가
        # 죽으면 최신 변환이 오래된 채 남는데, 전에는 그 굳은 위치를 계속
        # 쓰고 보고했음. except 도 TransformException 으로 좁힘
        try:
            tfm = self.tf_buf.lookup_transform('map', self.base_frame, Time())
        except TransformException:                 # not localised yet
            self.tf_ok = False
            return
        now = self.get_clock().now()  # 노드 시계
        stamp = Time.from_msg(tfm.header.stamp, clock_type=now.clock_type)
        if self.tf_stale > 0 and \
                (now - stamp).nanoseconds / 1e9 > self.tf_stale:
            self.tf_ok = False
            return
        t = tfm.transform
        q = t.rotation
        self.x, self.y = t.translation.x, t.translation.y
        self.yaw = math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
        self.have_truth = self.tf_ok = True  # 새 위치를 받음

    # [수정 2026-11-17] 신규 (D4): 위치 추정을 믿을 수 있는지
    def _loc_lost(self) -> bool:
        """TF 로 위치를 받는 로봇이 지금 위치를 모르는지 판단한다.

        Returns:
            pose_source 가 tf 이고, 위치를 아직 못 받았거나 최신 변환이
            tf_stale_sec 보다 오래됐으면 True. 그 밖(시뮬)에는 항상 False.
        """
        if self.pose_source != 'tf' or self.tf_stale <= 0:
            return False
        return not (self.have_truth and self.tf_ok)

    def _initial_pose(self):
        """Until AMCL answers, tell it where the robot was put down: on its home spot, facing +x (into the store)."""
        if self.have_truth:
            return
        m = PoseWithCovarianceStamped()
        m.header.frame_id, m.header.stamp = 'map', self.get_clock().now().to_msg()
        m.pose.pose.position.x, m.pose.pose.position.y = self.spawn
        m.pose.pose.orientation.w = 1.0
        m.pose.covariance[0] = m.pose.covariance[7] = 0.02 ** 2  # x, y 2 cm
        m.pose.covariance[35] = 0.1 ** 2  # yaw 분산(0.1 rad)
        self.pub_init.publish(m)

    # [수정 2026-11-18] P3: _gz_pose(Gazebo 참값 자세, map -> odom 보정)는
    # sim_backend 로 옮김

    # ------------------------------------------------------------ NavigateRoute (GuideGuest when mode == GUIDE)
    def _accepted(self, gh):
        """새 경로 목표를 cur 로 바꿔(선점) 바로 실행한다."""
        with self.lock:
            self.cur = gh                 # a newer plan pre-empts the running one
        gh.execute()

    def _navigate(self, gh):
        """NavigateRoute 실행: 허가받은 구간까지만 경로를 따라간다.

        매 주기(dt 0.05초) 비상 정지·선점·위치 추정·관제 생존·허가·손님
        동행·무진행을 확인한 뒤, 구간마다 정밀 도킹 / cmd_vel 직접 주행 /
        Nav2 / 직선 주행 중 하나로 움직인다. 결과 reason: OK, E_STOP,
        FMS_RESTART, CANCELED, PREEMPTED, GUEST_LOST, NO_PROGRESS,
        NAV2_FAILED.
        """
        goal = gh.request
        # route: Waypoint 목록, pv: 경로 번호, guide: 손님 안내(후진·저속)
        route, pv, guide = goal.route, goal.plan_version, goal.mode == 'GUIDE'
        yielding = goal.mode == 'YIELD'  # 비켜 서는 경로
        rev, back_streak, yield_rev = {}, True, None   # segment index -> drive in reverse
        self.pv, self.task_id = pv, goal.task_id
        self.grants = {k: v for k, v in self.grants.items() if k >= pv}      # drop permissions of older routes
        res = NavigateRoute.Result(plan_version=pv)
        # route[0] 에서 1.2 cm 안이면 0번 노드에 이미 도착, 아니면 -1
        reached = 0 if route and math.hypot(route[0].x - self.x, route[0].y - self.y) < 0.012 else -1
        # [수정 2026-11-20] T-42(2차): 막다른 노드에서 나가는 경로는 그 노드에
        # 다시 자리 잡지 않음(다음 구간이 실제 자세에서 바로 출발)
        if (reached < 0 and len(route) > 1
                and route[0].node_id in self.dead_ends
                and (math.hypot(route[0].x - self.x, route[0].y - self.y)
                     < self.dead_end_settle
                     or self._on_lane(route[0], route[1]))):
            # [수정 2026-11-20] T-44: 선분 옆이면(_on_lane) 막다른 노드로
            # 돌아가 회전하지 않고 출구로 바로 감
            reached = 0
        self.reached = reached  # 상태 보고용
        if reached == 0:
            self.node_id = route[0].node_id
        self._fb(gh, pv, reached, 'ACCEPTED')  # 수락 피드백
        # [수정 2026-11-26] 서빙 팔 자세 연동: 실물 팔이 작업 중이면 경로를
        # 시작하지 않음(관제도 순서를 지키지만 로봇 쪽에서도 막음)
        if self.arm_cli is not None and self.arm_state != 'IDLE':
            self.get_logger().error(
                f'{self.rid}: arm job {self.arm_state} running, route refused')
            res.reached_index, res.reason = reached, 'ARM_BUSY'
            gh.abort()
            return res
        # [수정 2026-11-17] UR-03: 안내 경로면 카메라 프레임을 보내기 시작
        if guide:
            self.guide_goal, self.track_warned = gh, False
        dt, lost_since = 0.05, None  # 주기(s), 손님 놓친 시각
        tries, rear_since = {}, None     # failed Nav2 attempts per segment / since when the way back is blocked
        pockets = set()                  # segments into a side spot that the route leaves again the way it came
        # [수정 2026-11-20] 막다른 노드에서 뒤쪽으로 나가는 첫 구간(후진)
        dead_exit = set()
        # [수정 2026-11-20] T-44: 무진행 감시
        # [odom x, y, yaw, 시작, 마지막 확인, 구간]
        watch = None
        while rclpy.ok():  # 경로 실행 루프
            if gh is self.cur and not gh.is_cancel_requested and (self.estop or gh is self.void):
                # emergency-stop channel, or the Task Manager restarted: stop here and give the route back
                self._stop()
                if self.drive != 'kinematic':
                    self.pub_cmd.publish(Twist())
                res.reached_index, res.reason = reached, 'E_STOP' if self.estop else 'FMS_RESTART'
                self.nav_state = 'IDLE'
                gh.abort()
                return res
            # 관제가 취소했거나 새 경로가 선점함
            if gh is not self.cur or gh.is_cancel_requested:
                self._stop()
                res.reached_index, res.reason = reached, 'CANCELED' if gh.is_cancel_requested else 'PREEMPTED'
                if gh.is_cancel_requested:
                    gh.canceled()
                    self.nav_state = 'IDLE'
                else:
                    gh.abort()
                return res
            # [수정 2026-11-17] D4: 위치를 모르면 움직이지 않음(Nav2 목표와
            # 직접 주행 모두 정지). 도착 판정보다 먼저 봄
            if self._loc_lost():
                self._stop()
                self.nav_state = 'WAIT_LOC'
                time.sleep(dt)
                continue
            # 마지막 노드에 도착: 루프를 나가 성공으로 끝냄
            if reached >= len(route) - 1:
                break
            tgt = reached + 1  # 다음 목표 인덱스
            if not self._fms_alive():                             # central control silent: do not move on our own
                self._stop()
                if self.drive != 'kinematic':
                    self.pub_cmd.publish(Twist())
                self.nav_state = 'WAIT_FMS'
                time.sleep(dt)
                continue
            # [수정 2026-11-26] 서빙 팔 자세 연동: 실물 팔이 rest 가 아니면
            # 움직이기 전에 접음(REST). 비상 정지·취소·선점이면 접기를 끊고
            # 위의 확인으로 돌아감. 접기에 실패하면(ARM_OFFLINE·ARM_TIMEOUT
            # 등) 출발하지 않고 그 사유로 경로를 돌려줌(관제가 임무를 보류)
            if self.arm_cli is not None and self.arm_pose != 'REST':
                self._stop()
                self.nav_state = 'ARM_FOLD'
                why = self._arm_call(
                    ARM_REST_JOB, lambda: (self.estop or gh is not self.cur
                                           or gh.is_cancel_requested))
                if why in ('OK', 'STOPPED'):
                    continue
                self.get_logger().error(
                    f'{self.rid}: could not fold the arm before driving '
                    f'({why}), giving the route back')
                self.nav_state = 'IDLE'
                res.reached_index, res.reason = reached, why
                gh.abort()
                return res
            if tgt > 0 and tgt > self.grants.get(pv, 0):          # wait for the traffic permission
                self._stop()
                self.nav_state = 'WAIT_GRANT'
                time.sleep(dt)
                continue
            # [수정 2026-11-17] UR-03: 동행 확인을 추적 토픽 기준으로 바꿈
            # (_guest_away). 멈춤·재출발 거리와 시간 초과는 그대로
            if guide and tgt > 0:
                limit = self.resume_dist if self.nav_state == 'PAUSED_GUEST' else self.follow_dist
                if self._guest_away(goal.visit_id, limit):        # SR-007: guest fell behind -> stop and wait
                    self._stop()
                    if self.nav_state != 'PAUSED_GUEST':
                        self.nav_state, lost_since = 'PAUSED_GUEST', time.time()
                        self._fb(gh, pv, reached, 'PAUSED_GUEST')
                    if time.time() - lost_since > self.guest_timeout:    # SR-008
                        res.reached_index, res.reason = reached, 'GUEST_LOST'
                        self.nav_state = 'IDLE'
                        gh.abort()
                        return res
                    time.sleep(dt)
                    continue
            # [수정 2026-11-20] T-44: 무진행 감시. 위의 대기(허가·관제·위치·
            # 손님)에서 돌아오면 1초 넘게 비므로 처음부터 다시 잼
            watch, stuck = self._progress_watch(watch, tgt)
            if stuck:
                self._stop()
                self.get_logger().error(
                    f'{self.rid}: no progress toward {route[tgt].node_id} for '
                    f'{self.no_progress_sec:.0f} s (state {self.nav_state}), '
                    'giving the route back (NO_PROGRESS)')
                self.nav_state, self.drive_error = 'IDLE', True
                res.reached_index, res.reason = reached, 'NO_PROGRESS'
                gh.abort()
                return res
            if tgt not in rev:  # 구간 방향을 한 번 정함
                # GUIDE: back up the whole guided leg, facing the guests.  YIELD: back out of the way into the side
                # spot.  NORMAL: when a new plan starts by going back the way we came (paths crossed), back up those
                # first segments instead of turning round in the one-robot-wide aisle.
                err = abs(wrap(math.atan2(route[tgt].y - self.y, route[tgt].x - self.x) - self.yaw))
                # [수정 2026-11-20] 막다른 노드(D1_STOP 등)에 서 있다가 뒤쪽
                # 노드로 나가는 첫 구간은 후진. 실측 지도 Nav2 는 전진 전용이라
                # 벽 앞에서 제자리 회전하다 실패했음(실기기 serve_v04_real_s2)
                # [수정 2026-11-20] T-42(2차): 출구가 뒤쪽이 아니어도(옆·앞)
                # 첫 구간은 cmd_vel 로. 뒤쪽(오차 > 90도)이면 후진
                if (tgt == 1 and not guide and not yielding
                        and route[0].node_id in self.dead_ends):
                    dead_exit.add(tgt)
                    rev[tgt] = err > math.pi / 2
                elif math.hypot(route[tgt].x - self.x,
                                route[tgt].y - self.y) < 0.05:
                    rev[tgt] = err > math.pi / 2          # settling onto a node a few cm away: never turn round for it
                elif guide and tgt > 0:
                    rev[tgt] = True
                elif yielding:
                    if yield_rev is None:                 # the first real segment decides: back out if the spot is behind
                        yield_rev = err > math.pi / 2
                    rev[tgt] = yield_rev
                    # [수정 2026-11-26] 후진 도킹: 비켜 서는 곳이 도크
                    # (충전소 등)이면 마지막 구간은 후진으로 들어감
                    # (시뮬 2단계에서 pinky2 가 자기 충전소 H2 로 비켜 설 때
                    # 앞으로 들어가 벽을 봤음)
                    if (self.dock_backwards and tgt == len(route) - 1
                            and (round(route[tgt].x, 3), round(route[tgt].y, 3))
                            in self.docks):
                        rev[tgt] = True
                else:
                    # A side spot the route leaves again the way it came (the planner lets another robot pass
                    # there): back into it, so the robot drives out forwards without turning round twice.
                    if 0 < tgt < len(route) - 1 and route[tgt + 1].node_id == route[tgt - 1].node_id:
                        pockets.add(tgt)
                    rev[tgt] = tgt in pockets or (back_streak and tgt <= 2 and err > 2.1)
                    back_streak = rev[tgt]
            self.nav_state = 'MOVING'  # 기본 상태
            dock = None  # 도크로 끝나는 구간이면 도크 정보
            # [수정 2026-11-27] T-63: 일반 Nav2 구간이면 그 진행 방향
            # (True = 후진). 도크·직접 주행 구간은 None(물러나기 안 함)
            nav2_rev = None
            if tgt > 0 and tgt == len(route) - 1 and not guide and not yielding:     # the route ends on a dock
                dock = self.docks.get((round(route[tgt].x, 3), round(route[tgt].y, 3)))
            if dock is not None:  # 정밀 도킹 구간
                if self.drive == 'nav2':
                    self._set_speed_limit(None)
                # [수정 2026-11-26] 후진 도킹이면 마지막 구간(대체 주행
                # 포함)도 후진
                done = self._dock_segment(
                    (pv, tgt), dock,
                    True if self.dock_backwards else rev[tgt], dt,
                    route[tgt - 1])
            # [수정 2026-11-20] 막다른 노드에서 나가는 후진(dead_exit)도 같은
            # 방식(cmd_vel 직접, 뒤 라이다 검사)으로
            # [수정 2026-11-20] T-42(2차): 막다른 곳 첫 구간은 전진이어도 이
            # 분기(Nav2 제자리 회전 없음). 뒤 라이다 검사는 후진일 때만
            elif (self.drive == 'nav2' and self.measured_map
                  and self.yield_reverse
                  and (tgt in dead_exit
                       or rev[tgt] and (yielding or tgt in pockets))):
                # Real robot stepping aside: back up along the granted edge (the Nav2 controller of the measured map
                # does not reverse). The lidar must show the way back clear; if it stays blocked, turn round instead.
                # [수정 2026-11-20] T-46: 막다른 곳에서 전진으로 나갈 때 앞
                # 라이다 검사. 막혔거나 새 스캔이 아직 없으면 서서 기다림
                # (오래 막히면 무진행 감시가 NO_PROGRESS 로 돌려줌)
                front = (None if rev[tgt] or tgt not in dead_exit
                         else self._front_clear())
                if (not rev[tgt] and tgt in dead_exit
                        and front is not True):
                    self.pub_cmd.publish(Twist())
                    if front is False:
                        self.nav_state = 'FRONT_BLOCKED'
                    done = False
                elif rev[tgt] and self._rear_blocked():
                    self.pub_cmd.publish(Twist())
                    self.nav_state = 'YIELD_BLOCKED'
                    rear_since = rear_since or time.time()
                    if time.time() - rear_since > 6.0:
                        self.get_logger().warn(f'{self.rid}: way back to {route[tgt].node_id} is blocked, turning round')
                        rev[tgt], yield_rev, rear_since = False, False, None
                        pockets.discard(tgt)
                        dead_exit.discard(tgt)  # [수정 2026-11-20]
                    done = False
                else:
                    # [수정 2026-11-20] 막다른 곳에서 나가는 후진은 MOVING
                    rear_since = None
                    self.nav_state = 'MOVING' if tgt in dead_exit else 'YIELD'
                    # [수정 2026-11-20] T-42(2차): 방향은 rev 를 따름
                    # (전에는 항상 후진)
                    done = self._step_toward(route[tgt].x, route[tgt].y,
                                             rev[tgt], dt,
                                             min(self.speed, self.guide_speed))
                    if done:
                        self.pub_cmd.publish(Twist())
            elif self.drive == 'nav2':  # 일반 Nav2 구간
                self._set_speed_limit(self.guide_speed if guide and tgt > 0 else None)
                # [수정 2026-11-17] UR-03: 실측 지도에서도 안내 구간은 Nav2 로
                # 후진(후진용 제어기). 그 밖의 후진은 전처럼 실측 지도에서 전진
                # [수정 2026-11-27] T-63: 진행 방향을 남김(막힘 뒤 물러나기)
                nav2_rev = rev[tgt] and (not self.measured_map or (
                    guide and tgt > 0 and self.guide_reverse))
                done = self._nav2_segment(
                    (pv, tgt), route[tgt].x, route[tgt].y, nav2_rev)
            else:  # kinematic·cmd_vel: 직선 주행
                done = self._step_toward(route[tgt].x, route[tgt].y, rev[tgt], dt,
                                         self.guide_speed if guide and tgt > 0 else self.speed)
            # [수정 2026-11-20] T-44: Nav2 실패 처리를 일반 구간 밖으로 옮김.
            # 도크 구간(_dock_segment 의 drive 단계)의 Nav2 실패도 재시도 뒤
            # NAV2_FAILED 로 끝냄. 전에는 결과 없이 무한 대기(serve_v04_real_s4)
            if self.drive == 'nav2' and self.measured_map \
                    and self.n2['state'] == 'FAILED':
                # Nav2 could not drive this segment (15 s without progress, or the goal failed). The FAILED mark
                # must not outlive the attempt: it used to stay set, and every later route failed at once.
                self._stop()
                self.n2.update(key=None, state='', handle=None, try_fk=None, fails=0, fail_key=None)
                # [수정 2026-11-20] T-50: 재시도 전에 위치 추정부터 확인.
                # 틀어져 있으면(실기기 08: 방향 25 도) 다시 맞춰 넣음
                # [수정 2026-11-23] T-56(R16-50): 위치 점검은 보조 진단이라
                # 그 안의 계산 오류(None 값·스캔 배열 모양·numpy 의 ValueError
                # 계열)가 아래 재시도·NAV2_FAILED 반환을 건너뛰게 두지 않음.
                # 전에는 예외가 경로 액션을 결과 없이 끝내 관제가 임무를
                # IN_PROGRESS 로 계속 잡았음(runs/20261123_03)
                fixed = False
                if self.locz is not None:
                    try:
                        fixed = self.locz.check_now(
                            f'Nav2 failed the segment to '
                            f'{route[tgt].node_id}')
                    except (AttributeError, TypeError, ValueError,
                            IndexError) as err:
                        self.get_logger().error(
                            f'{self.rid}: pose check failed ({err!r}), '
                            'going on with the Nav2 retry')
                if fixed:
                    time.sleep(1.0)            # AMCL 이 새 자세를 내도록
                tries[tgt] = tries.get(tgt, 0) + 1
                if tries[tgt] <= self.nav2_retries:
                    self.get_logger().warn(f'{self.rid}: Nav2 failed the segment to {route[tgt].node_id}, '
                                           f'retry {tries[tgt]}/{self.nav2_retries}')
                    if self.clear_local.service_is_ready():
                        self.clear_local.call_async(ClearEntireCostmap.Request())
                    self.nav_state = 'NAV2_RETRY'
                    time.sleep(1.0)
                    continue
                # [수정 2026-11-27] T-63: 장애물에 막혀 실패했으면 돌려주기
                # 전에 조금 물러남(사유·관제 처리는 그대로 NAV2_FAILED)
                if nav2_rev is not None:
                    self._blocked_backoff(nav2_rev, gh)
                self.get_logger().error(
                    f'{self.rid}: Nav2 failed the segment to '
                    f'{route[tgt].node_id} {tries[tgt]} times, giving the '
                    'route back (NAV2_FAILED)')
                self.nav_state, self.drive_error = 'IDLE', True
                res.reached_index, res.reason = reached, 'NAV2_FAILED'
                gh.abort()
                return res
            if done:  # 구간 도착
                reached = self.reached = tgt
                self.node_id, self.drive_error = route[tgt].node_id, False
                self._fb(gh, pv, reached, 'MOVING')
            time.sleep(dt)
        # 경로 끝: 정지, 속도 제한 해제, 성공 결과
        self._stop()
        if self.drive == 'nav2':
            self._set_speed_limit(None)
        self.nav_state = 'IDLE'
        res.success, res.reached_index, res.reason = True, reached, 'OK'
        gh.succeed()
        # [수정 2026-11-26] 서빙 팔 자세 연동: 자기 홈(충전소)에서 끝나면
        # arm_home_delay 뒤 실물 팔을 0도 home 자세로 폄(그동안 새 경로가 오면
        # 안 폄)
        if (self.arm_cli is not None and route
                and route[-1].node_id == self.home_node):
            threading.Thread(target=self._arm_home_later, args=(gh,),
                             daemon=True).start()
        return res

    # [수정 2026-11-20] T-44: 출구 선분 판정
    def _on_lane(self, a, b) -> bool:
        """로봇이 노드 a -> b 선분 옆(dead_end_lane_dist 안)에 있는지.

        Args:
            a: 막다른 노드(Waypoint).
            b: 출구 노드(Waypoint).

        Returns:
            선분 위(양 끝 포함, a 뒤로 dead_end_settle 까지)이고 옆 거리가
            dead_end_lane_dist 안이면 True.
        """
        dx, dy = b.x - a.x, b.y - a.y
        seg = math.hypot(dx, dy)
        if seg < 1e-6:
            return False
        ux, uy = dx / seg, dy / seg
        px, py = self.x - a.x, self.y - a.y
        along = px * ux + py * uy
        side = abs(-px * uy + py * ux)
        return (-self.dead_end_settle <= along <= seg
                and side <= self.dead_end_lane)

    # [수정 2026-11-20] T-44: 무진행 감시
    def _progress_watch(self, watch, tgt):
        """주행 중 진행이 없는 시간을 잰다.

        Args:
            watch: 이전 상태([x, y, yaw, 시작, 마지막 확인, 구간]) 또는 None.
            tgt: 지금 구간의 목표 인덱스.

        Returns:
            (새 상태, 멈춤 여부). no_progress_sec 이하면 항상 멈춤 아님.
        """
        if self.no_progress_sec <= 0:
            return None, False
        now = time.time()
        # 실기기는 오도메트리(위치 추정 흔들림 없음), 경량 시뮬은 자세
        x, y, yaw = self.odom if self.drive != 'kinematic' \
            else (self.x, self.y, self.yaw)
        if (watch is None or watch[5] != tgt or now - watch[4] > 1.0
                or math.hypot(x - watch[0], y - watch[1])
                > self.no_progress_dist
                or abs(wrap(yaw - watch[2])) > self.no_progress_yaw):
            return [x, y, yaw, now, now, tgt], False
        watch[4] = now
        return watch, now - watch[3] > self.no_progress_sec

    def _fb(self, gh, pv, reached, state):
        """경로 진행 피드백(plan_version, 도착 인덱스, 상태)을 보낸다."""
        gh.publish_feedback(NavigateRoute.Feedback(plan_version=pv, reached_index=reached, state=state))

    def _step_toward(self, tx, ty, reverse, dt, v=None):
        """Navigator: turn in place, then drive straight. reverse=True drives backwards (rear toward the target)."""
        dx, dy = tx - self.x, ty - self.y
        d = math.hypot(dx, dy)
        v = self.speed if v is None else v
        tol = 0.004 if self.drive == 'kinematic' else 0.015  # 도착 허용 오차(m)
        if d <= max(tol, v * dt if self.drive == 'kinematic' else 0):
            if self.drive == 'kinematic':
                self.x, self.y = tx, ty
            return True
        # 향할 방향(후진이면 반대)
        want = wrap(math.atan2(dy, dx) + (math.pi if reverse else 0.0))
        err = wrap(want - self.yaw)
        if self.drive == 'kinematic':  # 자세를 직접 움직임
            if abs(err) > 0.05:
                self.yaw = wrap(self.yaw + max(-self.turn_rate * dt, min(self.turn_rate * dt, err)))
            else:
                self.yaw = want
                self.x += dx / d * v * dt
                self.y += dy / d * v * dt
                # 바퀴 각 표시용(반지름 0.028 m. pinky_driver 기본은 0.027)
                self.wheel += (-1 if reverse else 1) * v * dt / 0.028
                # 경량 시뮬 배터리 소모(0.02 %/s)
                self.battery = max(0.0, self.battery - 0.02 * dt)
        else:  # cmd_vel 발행
            cmd = Twist()
            if abs(err) > 0.2:  # 먼저 제자리 회전
                cmd.angular.z = max(-1.5, min(1.5, 2.5 * err))
            else:  # 직진 + 방향 보정, 2.1 cm 안 감속
                cmd.linear.x = (-v if reverse else v) * min(1.0, d / 0.03 + 0.3)
                cmd.angular.z = 2.0 * err
            self.pub_cmd.publish(cmd)
        return False

    def _rear_blocked(self):
        """True when the lidar shows something close behind the robot, or gives no fresh scan to judge by."""
        if self.rear_stop <= 0:
            return False
        self.rear_wanted = time.time() + 2.0
        return self.rear is None or time.time() - self.rear_t > 1.0 or self.rear < self.rear_stop

    # [수정 2026-11-26] 신규: 후진 도킹의 뒤 라이다 검사
    # (_front_clear 와 같은 꼴)
    def _rear_clear(self) -> bool | None:
        """뒤쪽 라이다 검사 결과를 돌려준다(부를 때마다 스캔 평가를 켬).

        Returns:
            True: 트임(또는 검사 끔). False: rear_stop_dist 안에 무엇이
            있음. None: 아직 새 스캔이 없음(검사를 막 켰거나 끊김).
        """
        if self.rear_stop <= 0:
            return True
        now = time.time()
        if now > self.rear_wanted:               # 꺼져 있다 다시 켬
            self.rear_since = now
        self.rear_wanted = now + 2.0
        if self.rear is None or self.rear_t < self.rear_since \
                or now - self.rear_t > 1.0:
            return None
        return self.rear >= self.rear_stop

    # [수정 2026-11-27] T-63: 신규. 진행 방향(앞 또는 뒤) 띠의 최소 거리
    def _band_min(self, back: bool) -> float | None:
        """앞 또는 뒤 띠(폭 front_half_width) 안 가장 가까운 점의 거리.

        Args:
            back: True 면 로봇 뒤쪽 띠, False 면 앞쪽 띠.

        Returns:
            라이다 기준 그 방향 거리(m, 점이 없으면 inf). 1 초 안의 새
            스캔이 없으면 None.
        """
        m = self.last_scan
        if m is None or time.time() - self.last_scan_t > 1.0:
            return None
        turn = self.lidar_yaw + (math.pi if back else 0.0)
        best = float('inf')
        for i, r in enumerate(m.ranges):
            if not 0.06 <= r < 1.0:              # 자기 몸·무효값·먼 점 제외
                continue
            a = wrap(m.angle_min + i * m.angle_increment + turn)
            if abs(a) > math.pi / 3:  # 그 방향 +-60도 밖
                continue
            along, side = r * math.cos(a), r * math.sin(a)
            if abs(side) <= self.front_half_w and along < best:
                best = along
        return best

    # [수정 2026-11-27] T-63: 신규. Nav2 가 막혀 구간을 포기했을 때 물러남
    def _blocked_backoff(self, reverse: bool, gh) -> str:
        """진행 방향이 막혔으면 반대쪽으로 blocked_backoff_dist 만큼 물러난다.

        Nav2 구간이 재시도까지 실패해 NAV2_FAILED 를 돌려주기 직전에 부른다.
        진행 방향 띠의 최소 거리(몸 중심 기준)가 blocked_backoff_trigger
        미만일 때만 cmd_vel 로 직접 물러나고, 거리는 오도메트리로 잰다.
        물러나는 쪽 라이다가 정지 거리(뒤 rear_stop_dist, 앞
        front_stop_dist, 라이다 기준) 안이면 거기서 선다.

        Args:
            reverse: 실패한 구간이 후진이었으면 True(그때는 앞으로 물러남).
            gh: 지금 경로 목표 핸들(취소·선점 확인용).

        Returns:
            결과 이름: off, no_scan, clear, done, blocked, timeout, estop,
            canceled, fms, loc, no_scan_moving.
        """
        if self.backoff_dist <= 0:
            return 'off'
        lidar_x = -0.017   # 라이다는 몸 중심보다 1.7 cm 뒤(URDF rplidar_mount)
        ahead = self._band_min(back=reverse)
        if ahead is None:
            self.get_logger().warn(f'{self.rid}: blocked backoff skipped: '
                                   'no fresh scan')
            return 'no_scan'
        # 몸 중심 기준: 앞쪽은 라이다 거리 + lidar_x, 뒤쪽은 - lidar_x
        before = ahead + (-lidar_x if reverse else lidar_x)
        if before >= self.backoff_trigger:
            return 'clear'
        go_back = not reverse               # 물러나는 쪽이 로봇 뒤인지
        stop_d = self.rear_stop if go_back else self.front_stop
        v = min(self.speed, self.guide_speed)
        x0, y0, _ = self.odom
        t0, why, moved = time.time(), 'done', 0.0
        self.nav_state = 'BACKOFF'
        while True:
            moved = math.hypot(self.odom[0] - x0, self.odom[1] - y0)
            if self.estop:
                why = 'estop'
            elif gh.is_cancel_requested or gh is not self.cur:
                why = 'canceled'
            elif not self._fms_alive():
                why = 'fms'
            elif self._loc_lost():
                why = 'loc'
            elif moved >= self.backoff_dist:
                why = 'done'
            elif time.time() - t0 > self.backoff_timeout:
                why = 'timeout'
            else:
                way = self._band_min(back=go_back)
                if way is None:
                    why = 'no_scan_moving'
                elif stop_d > 0 and way < stop_d:
                    why = 'blocked'
                else:
                    cmd = Twist()
                    cmd.linear.x = -v if go_back else v
                    self.pub_cmd.publish(cmd)
                    time.sleep(0.05)
                    continue
            break
        self.pub_cmd.publish(Twist())
        after = self._band_min(back=reverse)
        after_c = (after + (-lidar_x if reverse else lidar_x)
                   if after is not None else float('nan'))
        self.get_logger().warn(
            f'{self.rid}: blocked backoff ({why}): moved {moved * 100:.1f} cm '
            f'{"forwards" if not go_back else "backwards"}, nearest '
            f'{"behind" if reverse else "ahead"} {before * 100:.1f} -> '
            f'{after_c * 100:.1f} cm (body centre)')
        return why

    def _stop(self):
        """주행을 멈춘다: 0 속도, 도킹 취소, Nav2 목표 취소."""
        # [수정 2026-11-17] R1-1/T-22: 직접 주행(양보 후진, 도킹 creep) 중
        # 취소·선점되면 마지막 cmd_vel이 남아 계속 움직였음.
        # 정지할 때 항상 0 속도를 한 번 보냄
        if self.drive != 'kinematic':
            self.pub_cmd.publish(Twist())
        self._dock_cancel()
        if self.drive == 'cmd_vel':
            self.pub_cmd.publish(Twist())
        elif self.drive == 'nav2':
            self._nav2_cancel()

    # ------------------------------------------------------------ precise docking
    def _detected(self, m):
        """검출된 도크 자세를 det(odom yaw, 시각, 지도 x, y)로 둔다."""
        q = m.pose.orientation
        yaw = math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
        # the same pose in the map frame (through the robot's pose in both frames), to compare it with the layout
        ox, oy, oyaw = self.odom
        dx, dy = m.pose.position.x - ox, m.pose.position.y - oy
        bx, by = math.cos(oyaw) * dx + math.sin(oyaw) * dy, -math.sin(oyaw) * dx + math.cos(oyaw) * dy
        self.det = (yaw, time.time(), self.x + math.cos(self.yaw) * bx - math.sin(self.yaw) * by,
                    self.y + math.sin(self.yaw) * bx + math.cos(self.yaw) * by)

    def _dock_segment(self, key, d, reverse, dt, prev):
        """Last segment of a route that ends on dock `d`. Returns True once the robot stands on the dock pose.
        start -> turn (to the dock heading) -> docking (Nav2 docking server) -> trim (heading), or, when the dock is
        not straight ahead of the node the robot comes from or docking fails, drive (ordinary segment) -> trim.
        align(출발 전 방향 맞춤, T-44)·settle(creep) 단계도 있음. 앞 라이다로
        멈추면(T-46) 도크 자세 앞이어도 True(그 자리를 도착으로 침)."""
        k = self.dk
        fk = (round(d['x'], 3), round(d['y'], 3))  # 도크 키(지도 좌표)
        if k['key'] != fk:
            k.update(key=fk, stage='start', state='', handle=None, marker=d.get('marker_id', -1), lat0=None, creep_t=None, still_t=None,
                     trim_t=None,  # [수정 2026-11-20] trim 시작 시각
                     aligned=False,  # [수정 2026-11-20] T-44: 정렬 재판정 1회
                     front_stop=False)  # [수정 2026-11-20] T-46: 앞 정지
            self.det = None
            if self.drive == 'nav2':
                self.pub_dock_target.publish(Int32(data=k['marker']))
        # [수정 2026-11-26] 후진 도킹: 다가가는 방향은 로봇이 향하는 방향(yaw)의
        # 반대. along·lat 는 다가가는 방향 기준(전진 도킹은 예전과 같음)
        back = self.dock_backwards
        a_yaw = d['yaw'] + (math.pi if back else 0.0)
        c, s_ = math.cos(a_yaw), math.sin(a_yaw)  # 다가가는 방향 단위벡터
        along = (d['x'] - self.x) * c + (d['y'] - self.y) * s_          # distance still to go along the dock heading
        lat = -(d['x'] - self.x) * s_ + (d['y'] - self.y) * c  # 옆 어긋남(m)
        if k['stage'] == 'start':  # 앞 노드에 맞추고 방법 결정
            # Nav2 ends a segment up to 1.5 cm before the node; for a dock entered from the side that is a sideways
            # offset the short approach cannot remove. Creep onto the node before the dock first.
            if self._creep(prev.x, prev.y, k):
                return False
            # 도킹 서버 조건: 도크까지 3~30 cm, 옆 3 cm 안, 서버 준비됨
            ok = (self.drive == 'nav2' and self.use_docking and 0.03 <= along <= 0.30 and abs(lat) <= 0.03
                  and self.dock_cli.server_is_ready())
            # [수정 2026-11-20] T-44: 조건 미달이면 한 번만 도크 방향으로
            # 제자리 정렬(앞 노드는 통로 쪽이라 회전 여유 있음) 뒤 다시 판정
            if (not ok and self.drive == 'nav2' and self.measured_map
                    and self.use_docking and not k.get('aligned')
                    and abs(wrap(d['yaw'] - self.yaw)) > 0.08):
                k['stage'] = 'align'
            else:
                k['stage'] = 'turn' if ok else 'drive'
        if k['stage'] == 'align':  # 제자리 정렬(T-44)
            self.nav_state = 'TURN'
            if self._rotate(wrap(d['yaw'] - self.yaw), 0.08, dt, 0.4):
                k['still_t'] = None
                return False
            if k.get('still_t') is None:          # 멈춘 뒤 위치 추정이 따라오게
                k['still_t'] = time.time()
            if time.time() - k['still_t'] < 0.5:
                return False
            k.update(stage='start', aligned=True, still_t=None, creep_t=None)
            return False
        if k['stage'] == 'turn':  # 회전 뒤 도킹 목표 전송
            self.nav_state = 'TURN'
            # [수정 2026-11-20] T-46: 도킹 전에 앞쪽 스캔 평가를 미리 켬
            # [수정 2026-11-26] 후진 도킹이면 뒤쪽 스캔 평가를 켬
            if back:
                self._rear_clear()
            else:
                self._front_clear()
            if self._rotate(wrap(d['yaw'] - self.yaw), 0.08, dt, 0.4):
                return False
            if not self.measured_map and self.clear_local.service_is_ready():
                self.clear_local.call_async(ClearEntireCostmap.Request())
            g = DockRobot.Goal()  # 지도 좌표 도크 자세로
            g.use_dock_id, g.navigate_to_staging_pose = False, False
            g.dock_type = 'marker_dock' if d['kind'] == 'marker' else 'pose_dock'
            g.dock_pose.header.frame_id, g.dock_pose.header.stamp = 'map', self.get_clock().now().to_msg()
            g.dock_pose.pose.position.x, g.dock_pose.pose.position.y = float(d['x']), float(d['y'])
            # [수정 2026-11-27] T-64: 후진 도킹이면 도킹 서버에 넘기는 도크
            # 자세 방향을 180도 돌림. opennav_docking 1.3.13 approachDock 은
            # 목표를 도크 자세 방향으로 0.25 m 밀고(backward_projection)
            # 후진이면 그 방향을 다시 180도 돌림 -> 서버는 도크 자세 방향이
            # 진행 방향(도킹한 로봇이 보는 방향의 반대)이라고 봄. roadmap 의
            # yaw_deg(도킹한 로봇이 보는 방향)를 그대로 넘기면 목표가 도크
            # 앞 0.25 m 가 되어 D1_STOP 은 돌아서 도크 반대로 후진, H2 는 목표
            # 근처에서 제자리 회전 뒤 시간 초과(실기기 11-27).
            # 전진 도킹은 그대로
            g_yaw = d['yaw'] + (math.pi if self.dock_backwards else 0.0)
            g.dock_pose.pose.orientation.z = math.sin(g_yaw / 2)
            g.dock_pose.pose.orientation.w = math.cos(g_yaw / 2)
            k.update(stage='docking', state='ACTIVE', handle=None, lat0=lat)
            self.dock_cli.send_goal_async(g).add_done_callback(lambda f, fk=fk: self._dock_accepted(f, fk))
            return False
        if k['stage'] == 'docking':  # 도킹 서버 주행 감시
            self.nav_state = 'DOCKING'
            # [수정 2026-11-20] T-46: 앞 라이다로 벽이 front_stop_dist 안이면
            # (또는 1초 넘게 새 스캔이 없으면) 도킹을 취소하고 그 자리를 도착
            # 으로 침. 음식 받는 곳이라 벽에 닿지 않는 것이 우선이고, 실패로
            # 돌려주어도 로봇은 같은 자리에 서 있으므로 얻는 것이 없음.
            # 제자리 회전(trim)도 하지 않음(모서리가 벽 쪽으로 나감)
            # [수정 2026-11-26] 후진 도킹: 뒤 라이다(rear_stop_dist)로 같은 판정
            if back:
                front = self._rear_clear()
                since, side = self.rear_since, 'rear'
                dist, stop_d = self.rear, self.rear_stop
            else:
                front = self._front_clear()
                since, side = self.front_since, 'front'
                dist, stop_d = self.front, self.front_stop
            if k['state'] == 'ACTIVE' and (
                    front is False or front is None
                    and time.time() - since > 1.0):
                if k['handle'] is not None:
                    k['handle'].cancel_goal_async()
                self.pub_cmd.publish(Twist())
                self.get_logger().warn(
                    f'{self.rid}: docking at {d["name"]} stopped by the '
                    f'{side} lidar (' + (
                        f'{dist * 1000:.0f} mm < '
                        f'{stop_d * 1000:.0f} mm' if front is False
                        else 'no fresh scan for 1 s') + '), '
                    f'{along * 1000:+.0f} mm short of the dock pose')
                k.update(stage='trim', state='', handle=None,
                         front_stop=True)
            elif k['state'] == 'SUCCEEDED':
                k['stage'] = 'trim'
            elif k['state'] == 'ACTIVE' and k['handle'] is not None and along <= 0.006 and abs(lat) < 0.03:
                # Level with the dock pose. The server only stops within docking_threshold of the pose itself, which
                # a robot a few mm to the side never reaches: it would drive on into the wall.
                k['handle'].cancel_goal_async()
                self.pub_cmd.publish(Twist())
                k.update(stage='trim', state='', handle=None)
            elif k['state'] == 'FAILED' or along < -0.02:               # failed, or drove past the dock pose
                self.get_logger().warn(f'{self.rid}: docking at {d["name"]} did not finish '
                                       f'({k["state"] or "overshoot"}), finishing the segment with Nav2')
                if k['handle'] is not None and k['state'] == 'ACTIVE':
                    k['handle'].cancel_goal_async()
                self.pub_cmd.publish(Twist())
                k.update(stage='drive', state='', handle=None)
            return False
        if k['stage'] == 'drive':  # 일반 구간으로 도크까지
            if self.drive == 'nav2':
                done = self._nav2_segment(key, d['x'], d['y'], reverse)
            else:
                done = self._step_toward(d['x'], d['y'], reverse, dt)
            if not done:
                return False
            k.update(stage='settle', creep_t=None)
        if k['stage'] == 'settle':                                      # same creep, onto the dock node itself
            if self._creep(d['x'], d['y'], k):
                return False
            k['stage'] = 'trim'
        # trim: turn in place to the dock heading. With a marker in view the error comes from the marker (dock heading
        # and robot heading both in the odometry frame), otherwise from the localisation.
        self.nav_state = 'DOCKING'
        err = wrap(d['yaw'] - self.yaw)
        if d['kind'] == 'marker' and self.det is not None and time.time() - self.det[1] < 1.0:
            err = wrap(self.det[0] - self.odom[2])
        # [수정 2026-11-20] trim 시간 제한: 넘으면 세우고 남은 오차를 남긴 뒤
        # 도킹 완료로 처리(허용 오차는 그대로)
        if k.get('trim_t') is None:
            k['trim_t'] = time.time()
        # [수정 2026-11-20] T-46: 앞 라이다로 멈춘 도킹은 회전하지 않음
        if k.get('front_stop'):
            self.pub_cmd.publish(Twist())
        elif self.trim_timeout > 0 and \
                time.time() - k['trim_t'] > self.trim_timeout:
            self.pub_cmd.publish(Twist())
            self.get_logger().warn(
                f'{self.rid}: heading trim at {d["name"]} did not get within '
                f'{math.degrees(self.yaw_tol):.1f} deg in '
                f'{self.trim_timeout:.1f} s, stopping with '
                f'{math.degrees(err):+.1f} deg left')
        else:
            if self._rotate(err, self.yaw_tol, dt, self.trim_w):
                k['still_t'] = None
                return False
            # stand still for a moment and check again (coasting, a fresh
            # marker reading taken at rest)
            if k.get('still_t') is None:
                k['still_t'] = time.time()
            if time.time() - k['still_t'] < 0.5:
                return False
        note = ''  # 도착 로그 덧붙임
        if d['kind'] == 'marker':
            note = (', marker not seen' if self.det is None else
                    f', marker puts the dock {(self.det[2] - d["x"]) * 1000:+.0f} / {(self.det[3] - d["y"]) * 1000:+.0f} mm '
                    f'(x / y) from its map position')
        # [수정 2026-11-20] T-46: 앞 라이다 거리도 남김(front_stop_dist 조정용)
        if self.front is not None and time.time() - self.front_t < 1.0:
            note += f', front lidar {self.front * 1000:.0f} mm'
        # [수정 2026-11-26] 후진 도킹: 뒤 라이다 거리(rear_stop_dist 조정용)
        if back and self.rear is not None and time.time() - self.rear_t < 1.0:
            note += f', rear lidar {self.rear * 1000:.0f} mm, backwards'
        self.get_logger().info(f'{self.rid}: docked at {d["name"]} ({self.x:.3f}, {self.y:.3f}, '
                               f'{math.degrees(self.yaw):.1f} deg): {along * 1000:+.0f} mm short, {lat * 1000:+.0f} mm '
                               f'sideways, heading error {math.degrees(wrap(d["yaw"] - self.yaw)):.1f} deg' + note +
                               (f', approach started {k["lat0"] * 1000:+.0f} mm sideways' if k.get('lat0') is not None else ''))
        k.update(key=None, stage='', state='', handle=None, marker=-1, lat0=None,
                 trim_t=None)  # [수정 2026-11-20] trim 시간 제한
        if self.drive == 'nav2':
            self.pub_dock_target.publish(Int32(data=-1))
        return True

    def _creep(self, tx, ty, k):
        """Drive straight (no turning) until the point (tx, ty) is level with the robot; only for the last 3 cm that
        the Nav2 goal tolerance leaves. Returns True while moving."""
        if self.drive == 'kinematic':
            return False
        # 목표점까지 로봇 진행 방향 성분(m, 음수면 지나침)
        f = (tx - self.x) * math.cos(self.yaw) + (ty - self.y) * math.sin(self.yaw)
        if k.get('creep_t') is None:
            k['creep_t'] = time.time()
        # [수정 2026-11-20] T-46: 앞으로 기어갈 때 앞이 막혔거나 새 스캔이
        # 없으면 더 가지 않음(도크 노드 바로 앞은 벽이 가까움)
        if f > 0 and self.drive == 'nav2' and \
                self._front_clear() is not True:
            f = 0.0
        # [수정 2026-11-26] 후진 도킹: 뒤로 기어갈 때는 뒤 라이다로 같은 확인
        if f < 0 and self.drive == 'nav2' and self.dock_backwards and \
                self._rear_clear() is not True:
            f = 0.0
        # 3 mm~3 cm 남았고 4초 안이면 0.02 m/s 로 앞뒤 이동
        if 0.003 < abs(f) <= 0.03 and time.time() - k['creep_t'] < 4.0:
            self.nav_state = 'DOCKING'
            cmd = Twist()
            cmd.linear.x = math.copysign(0.02, f)
            self.pub_cmd.publish(cmd)
            return True
        self.pub_cmd.publish(Twist())
        k['creep_t'] = None
        return False

    def _rotate(self, err, tol, dt, w_min):
        """Turn in place by `err`. Returns True while still turning, False (and stops) once within `tol`."""
        if abs(err) <= tol:
            if self.drive != 'kinematic':
                self.pub_cmd.publish(Twist())
            return False
        if self.drive == 'kinematic':
            self.yaw = wrap(self.yaw + max(-self.turn_rate * dt, min(self.turn_rate * dt, err)))
        else:
            cmd = Twist()
            cmd.angular.z = max(-1.5, min(1.5, 2.5 * err))
            if abs(cmd.angular.z) < w_min:  # 모터 불감대 위로
                cmd.angular.z = math.copysign(w_min, err)
            self.pub_cmd.publish(cmd)
        return True

    def _dock_accepted(self, fut, fk):
        """도킹 목표 수락 결과: 다른 단계면 취소, 거절이면 FAILED."""
        gh, k = fut.result(), self.dk
        if k['key'] != fk or k['stage'] != 'docking':
            if gh.accepted:
                gh.cancel_goal_async()
            return
        if not gh.accepted:
            k['state'] = 'FAILED'
            return
        k['handle'] = gh
        gh.get_result_async().add_done_callback(lambda f, fk=fk: self._dock_result(f, fk))

    def _dock_result(self, fut, fk):
        """도킹 결과를 dk['state'] 에 적는다(상태 4 = SUCCEEDED)."""
        k = self.dk
        if k['key'] == fk and k['stage'] == 'docking':
            r = fut.result()
            k['state'] = 'SUCCEEDED' if r.status == 4 and r.result.success else 'FAILED'

    def _dock_cancel(self):
        """진행 중인 도킹을 취소하고 도킹 상태를 비운다."""
        k = self.dk
        if k['key'] is None:
            return
        if k['stage'] == 'docking' and k['handle'] is not None:
            k['handle'].cancel_goal_async()
        if k['stage'] in ('turn', 'docking', 'trim') and self.drive != 'kinematic':
            self.pub_cmd.publish(Twist())
        k.update(key=None, stage='', state='', handle=None, marker=-1)

    # ------------------------------------------------------------ Nav2 segment driving
    def _set_speed_limit(self, v):
        """Guiding is slower than normal driving: cap the Nav2 controller through its speed-limit topic."""
        if v != self._limit:
            self._limit = v
            m = SpeedLimit()
            m.header.stamp = self.get_clock().now().to_msg()
            m.percentage, m.speed_limit = False, float(v or 0.0)      # 0 = no limit
            self.pub_limit.publish(m)

    def _nav2_segment(self, key, tx, ty, reverse=False):
        """Drive to one granted roadmap node with Nav2. Returns True once the node is reached.
        reverse=True: turn the rear toward the node, then let the controller (allow_reversing) back up to it."""
        n = self.n2
        # Progress watch per target node (not per plan version: the Task Manager may re-send the same segment under
        # a new version every few seconds, which used to reset the failure count so the fallback never triggered).
        fk, now = (round(tx, 3), round(ty, 3)), time.time()
        if n.get('try_fk') != fk or math.hypot(self.x - n['try_pos'][0], self.y - n['try_pos'][1]) > 0.02:
            if n.get('try_fk') != fk and n.get('direct') != fk:
                n['direct'] = None
            n.update(try_fk=fk, try_t0=now, try_pos=(self.x, self.y))
        # 15초 동안 2 cm 못 나감: 실측 지도는 FAILED, 가상 매장은 직접 주행
        elif now - n['try_t0'] > 15.0 and n.get('direct') != fk:
            if self.measured_map:
                self._nav2_cancel()
                n['state'] = 'FAILED'
                return False
            self.get_logger().warn(f'{self.rid}: no progress toward {fk} for 15 s under Nav2, driving it directly')
            self._nav2_cancel()
            n.update(direct=fk, fails=0)
        if n.get('direct') == fk:                                   # Nav2 gave up on this segment: drive it directly
            v = self.guide_speed if self._limit else self.speed
            if self._step_toward(tx, ty, reverse, 0.05, v):
                self.pub_cmd.publish(Twist())
                n.update(key=None, state='', fails=0, direct=None, try_fk=None)
                return True
            return False
        if self.measured_map and n['state'] == 'FAILED':  # _navigate 가 처리
            return False
        if n['key'] != key:  # 새 구간: 회전 후 목표
            # Turn toward the node before handing the segment to Nav2. Turning in place inside the controller makes
            # the footprint corners sweep cells marked by the lidar (aisle walls, a robot on the neighbouring node),
            # so RPP reports "collision ahead" and never finishes a U-turn after a replan sends the robot back.
            d = math.hypot(tx - self.x, ty - self.y)
            err = wrap(math.atan2(ty - self.y, tx - self.x) + (math.pi if reverse else 0.0) - self.yaw)
            # [수정 2026-11-17] UR-03: 실측 지도의 후진 구간도 여기서 뒤를
            # 목표로 돌림 (후진용 제어기에는 제자리 회전이 없음)
            if (not self.measured_map or reverse) and d > 0.05 \
                    and abs(err) > (0.15 if n.get('turning') == key else 0.5):
                n['turning'] = key
                self.nav_state = 'TURN'
                cmd = Twist()
                cmd.angular.z = max(-1.5, min(1.5, 2.5 * err))
                if abs(cmd.angular.z) < 0.4:
                    cmd.angular.z = math.copysign(0.4, err)
                self.pub_cmd.publish(cmd)
                return False
            if n.get('turning') == key:
                n['turning'] = None
                self.pub_cmd.publish(Twist())
            if not self.measured_map and n['fails'] >= 3 and n.get('fail_key') == fk:
                self.get_logger().warn(f'{self.rid}: Nav2 failed segment to {fk} {n["fails"]} times, driving it directly')
                n.update(direct=fk, state='', fails=0)
                return False
            if not self.nav2.server_is_ready():  # Nav2 미기동
                self.nav_state = 'WAIT_NAV2'
                return False
            # 실패 직후 1초는 다시 보내지 않음
            if n['state'] == 'FAILED' and time.time() - n['t_fail'] < 1.0:
                return False
            # [수정 2026-11-17] UR-03: 이 구간에 쓸 제어기를 먼저 알림. 바뀌었을
            # 때는 한 주기 뒤에 목표를 보내 선택이 먼저 도착하게 함
            want = 'FollowPathReverse' if reverse else 'FollowPath'
            if want != self._controller:
                self._controller = want
                self.pub_controller.publish(String(data=want))
                return False
            # The simulated lidar sometimes returns only invalid ranges; marks from earlier scans would then never
            # be ray-traced away. Start every segment from an empty local costmap that the next scans refill.
            if self.clear_local.service_is_ready():
                self.clear_local.call_async(ClearEntireCostmap.Request())
            g = NavigateToPose.Goal()  # 목표: 노드 좌표
            g.pose.header.frame_id = 'map'
            g.pose.header.stamp = self.get_clock().now().to_msg()
            g.pose.pose.position.x, g.pose.pose.position.y = float(tx), float(ty)
            yaw = math.atan2(ty - self.y, tx - self.x) + (math.pi if reverse else 0.0)
            g.pose.pose.orientation.z, g.pose.pose.orientation.w = math.sin(yaw / 2), math.cos(yaw / 2)
            n.update(key=key, state='ACTIVE', handle=None, goal_fk=fk)
            self.nav2.send_goal_async(g).add_done_callback(lambda f, key=key: self._nav2_accepted(f, key))
            return False
        if n['state'] == 'SUCCEEDED':
            n.update(key=None, state='', fails=0, fail_key=None, try_fk=None)
            return True
        if n['state'] == 'FAILED':  # 가까우면 도착, 아니면 재시도
            if math.hypot(tx - self.x, ty - self.y) < 0.03:       # close enough: count the node as reached
                n.update(key=None, state='', fails=0, fail_key=None, try_fk=None)
                return True
            n['fail_key'] = fk
            n['key'] = None                                         # blocked (obstacle in the costmap): try again
            self.nav_state = 'NAV2_RETRY'
        return False

    def _refresh_costmap(self):
        """While driving, rebuild the local costmap from the newest scan once a second (see _nav2_segment)."""
        if not self.measured_map and self.n2['key'] is not None and self.clear_local.service_is_ready():
            self.clear_local.call_async(ClearEntireCostmap.Request())

    def _nav2_accepted(self, fut, key):
        """Nav2 목표 수락 결과: 옛 구간이면 취소, 거절이면 FAILED."""
        gh, n = fut.result(), self.n2
        if n['key'] != key:
            if gh.accepted:
                gh.cancel_goal_async()
            return
        if not gh.accepted:
            n.update(state='FAILED', t_fail=time.time())
            return
        n['handle'] = gh
        gh.get_result_async().add_done_callback(lambda f, key=key: self._nav2_result(f, key))

    def _nav2_result(self, fut, key):
        """Nav2 결과를 n2 에 적는다. 같은 노드의 연속 실패를 센다."""
        n = self.n2
        if n['key'] != key:
            return
        if fut.result().status == 4:                                # GoalStatus.STATUS_SUCCEEDED
            n['state'] = 'SUCCEEDED'
        else:
            fails = n['fails'] + 1 if n.get('fail_key') in (None, n.get('goal_fk')) else 1
            n.update(state='FAILED', t_fail=time.time(), fails=fails)

    def _nav2_cancel(self):
        """회전·직접 주행을 세우고 진행 중인 Nav2 목표를 취소한다."""
        n = self.n2
        if n.get('turning') is not None or n.get('direct') is not None:
            self.pub_cmd.publish(Twist())
            n['turning'] = None            # 'direct' stays: it belongs to the target node, not to this plan version
        if n['key'] is not None:
            if n['handle'] is not None:
                n['handle'].cancel_goal_async()
            n.update(key=None, state='', handle=None)

    # ------------------------------------------------------------ Arm Controller (serving arm on the AMR)
    def _arm_job(self, gh):
        """팔 작업 실행. 대역은 duration 동안 관절 애니메이션 뒤 성공."""
        g = gh.request
        self.arm_state, self.arm_task = g.job, g.task_id
        # [수정 2026-11-20] serving_arm:=real 이면 실물 구동부로 넘김
        if self.arm_cli is not None:
            return self._arm_forward(gh)
        t0, dur = time.time(), max(0.2, g.duration)  # 최소 0.2초
        while rclpy.ok():
            if gh.is_cancel_requested or self.estop:      # canceled by the Task Manager, or emergency stop
                self.arm_q, self.arm_state = list(REST), 'IDLE'
                if gh.is_cancel_requested:
                    gh.canceled()
                else:
                    gh.abort()
                return ArmJob.Result(success=False, reason='CANCELED' if gh.is_cancel_requested else 'E_STOP')
            pr = (time.time() - t0) / dur  # 진행률(0~1)
            if pr >= 1.0:
                break
            self.arm_q = arm_pose(g.job, pr)
            gh.publish_feedback(ArmJob.Feedback(phase=g.job, progress=float(pr)))
            time.sleep(0.05)
        self.arm_q, self.arm_state = list(REST), 'IDLE'
        gh.succeed()
        return ArmJob.Result(success=True, reason='OK')

    # [수정 2026-11-20] 신규: 팔 작업을 서빙 팔의 실물 구동부로 넘김
    # (frybot_arm/master_controller 와 같은 방식)
    def _arm_forward(self, gh) -> ArmJob.Result:
        """팔 작업을 /<robot>/serving_arm/arm_job 으로 넘기고 결과를 돌려준다.

        피드백과 팔의 결과(사유 포함)는 그대로 전달한다. 상태 보고
        (arm_state, /fleet/arm_status)는 전달하는 동안에도 작업 중으로 나간다.

        Args:
            gh: 관제가 보낸 목표의 핸들.

        Returns:
            팔의 결과. 구동부가 없거나 끊기면 ARM_OFFLINE, 목표를 받지
            않으면 REJECTED, 관제가 취소하면 CANCELED, 비상 정지면 E_STOP.
        """
        # [수정 2026-11-26] 서빙 팔 자세 연동: 펴기(HOME)가 돌고 있으면 끊고,
        # 팔 구동부를 혼자 씀. 작업 결과로 arm_pose 를 갱신(성공: HOME 작업은
        # HOME, 그 밖은 REST. 실패·취소: UNKNOWN 이라 다음 주행 전에 접음)
        self.arm_preempt = True
        with self.arm_lock:
            self.arm_preempt = False
            self.arm_pose = 'UNKNOWN'
            result = self._arm_relay(gh)
            if result.success:
                self.arm_pose = ('HOME' if gh.request.job == ARM_HOME_JOB
                                 else 'REST')
        self.arm_q, self.arm_state = list(REST), 'IDLE'
        if gh.is_cancel_requested:
            gh.canceled()
        elif result.success:
            gh.succeed()
        else:
            gh.abort()
        if not result.success:
            self.get_logger().warn(
                f'{self.rid}: arm job {gh.request.job} '
                f'({gh.request.task_id}): {result.reason}')
        return result

    def _arm_relay(self, gh) -> ArmJob.Result:
        """_arm_forward 의 본체: 팔 쪽 목표를 보내고 끝날 때까지 지켜본다.

        Args:
            gh: 관제가 보낸 목표의 핸들.

        Returns:
            돌려줄 결과(성공 여부와 사유).
        """
        def fail(reason: str) -> ArmJob.Result:
            """실패 결과를 만든다."""
            return ArmJob.Result(success=False, reason=reason)

        def feedback(fb) -> None:
            """팔 쪽 피드백을 관제 목표로 그대로 넘긴다."""
            if gh.is_active:
                gh.publish_feedback(fb.feedback)

        # 구동부가 arm_wait 안에 보이지 않으면 ARM_OFFLINE
        if not self.arm_cli.wait_for_server(timeout_sec=self.arm_wait):
            return fail('ARM_OFFLINE')
        sent = self.arm_cli.send_goal_async(gh.request,
                                            feedback_callback=feedback)
        t0 = time.time()
        while not sent.done():
            if time.time() - t0 > self.arm_wait:
                return fail('ARM_OFFLINE')     # 보낸 목표에 답이 없음
            time.sleep(ARM_POLL_SEC)
        child = sent.result()
        if not child.accepted:
            return fail('REJECTED')
        done = child.get_result_async()
        stop, t_stop, lost = '', 0.0, None  # 정지 사유, 취소 시각, 끊김
        while not done.done():
            # 관제의 취소나 비상 정지(생존 신호의 정지 목록): 팔도 세움
            if not stop and (gh.is_cancel_requested or self.estop):
                stop = 'CANCELED' if gh.is_cancel_requested else 'E_STOP'
                child.cancel_goal_async()
                t_stop = time.time()
                self.get_logger().warn(
                    f'{self.rid}: arm job {gh.request.job}: {stop}, '
                    'canceling the arm goal')
            # 구동부가 보이지 않은 시간을 잼
            if self.arm_cli.server_is_ready():
                lost = None
            elif lost is None:
                lost = time.time()
            if lost is not None and time.time() - lost > self.arm_wait:
                return fail(stop or 'ARM_OFFLINE')   # 작업 중 구동부가 사라짐
            if stop and time.time() - t_stop > ARM_CANCEL_WAIT_SEC:
                self.get_logger().error(
                    f'{self.rid}: the arm did not confirm the cancel in '
                    f'{ARM_CANCEL_WAIT_SEC:.0f} s')
                return fail(stop)
            time.sleep(ARM_POLL_SEC)
        if stop:
            return fail(stop)
        wrapped = done.result()
        result = wrapped.result
        # 팔이 사유 없이 실패하면 결과 상태로 사유를 채움
        if not result.success and not result.reason:
            result.reason = ('CANCELED'
                             if wrapped.status == GoalStatus.STATUS_CANCELED
                             else 'ARM_FAIL')
        return result

    # [수정 2026-11-26] 신규: 서빙 팔 자세 연동. 관제 목표 없이 로봇 제어기가
    # 실물 팔 구동부에 접기(REST)·펴기(HOME)를 보냄
    def _arm_call(self, job: str, stop_if) -> str:
        """실물 팔 구동부에 작업 하나를 보내고 끝날 때까지 기다린다.

        arm_lock 을 잡고 보냄(다른 팔 목표가 끝날 때까지 기다림). 결과로
        arm_pose 를 갱신한다.

        Args:
            job: ARM_REST_JOB 또는 ARM_HOME_JOB.
            stop_if: 인자 없는 함수. True 가 되면 팔 목표를 취소하고 끝냄.

        Returns:
            'OK', 'STOPPED'(stop_if 로 끊음), 'ARM_OFFLINE'(구동부 없음·응답
            없음·작업 중 끊김), 'REJECTED', 또는 구동부의 실패 사유
            (ARM_TIMEOUT 등).
        """
        while not self.arm_lock.acquire(timeout=ARM_POLL_SEC):
            if stop_if():
                return 'STOPPED'
        try:
            if stop_if():
                return 'STOPPED'
            if not self.arm_cli.wait_for_server(timeout_sec=self.arm_wait):
                return 'ARM_OFFLINE'
            goal = ArmJob.Goal(task_id=f'{self.rid}_{job.lower()}',
                               arm_id=self.rid, job=job, duration=0.0,
                               params_json='{}')
            self.arm_pose = 'UNKNOWN'        # 보낸 뒤로는 팔이 움직일 수 있음
            sent = self.arm_cli.send_goal_async(goal)
            t0 = time.time()
            while not sent.done():
                if time.time() - t0 > self.arm_wait:
                    return 'ARM_OFFLINE'
                time.sleep(ARM_POLL_SEC)
            child = sent.result()
            if not child.accepted:
                return 'REJECTED'
            done = child.get_result_async()
            t_stop, lost = None, None        # 취소 시각, 구동부 끊긴 시각
            while not done.done():
                if t_stop is None and stop_if():
                    child.cancel_goal_async()
                    t_stop = time.time()
                if (t_stop is not None
                        and time.time() - t_stop > ARM_CANCEL_WAIT_SEC):
                    return 'STOPPED'
                if self.arm_cli.server_is_ready():
                    lost = None
                elif lost is None:
                    lost = time.time()
                if lost is not None and time.time() - lost > self.arm_wait:
                    return 'ARM_OFFLINE'
                time.sleep(ARM_POLL_SEC)
            if t_stop is not None:
                return 'STOPPED'
            r = done.result().result
            if r.success:
                self.arm_pose = 'HOME' if job == ARM_HOME_JOB else 'REST'
                return 'OK'
            return r.reason or 'ARM_FAIL'
        finally:
            self.arm_lock.release()

    def _arm_home_later(self, gh) -> None:
        """홈에서 끝난 경로 gh 뒤 arm_home_delay 만큼 서 있으면 팔을 0도로 편다.

        그 사이에 새 경로(cur 이 바뀜)·비상 정지·관제 팔 작업이 오면 펴지
        않거나 펴던 것을 끊는다(다음 주행 전에 _navigate 가 다시 접음).

        Args:
            gh: 홈에서 성공으로 끝난 경로 목표 핸들.
        """
        def stop_if() -> bool:
            return (self.estop or self.cur is not gh or self.arm_preempt
                    or self.arm_state != 'IDLE')

        time.sleep(self.arm_home_delay)
        if stop_if() or self.arm_pose == 'HOME':
            return
        why = self._arm_call(ARM_HOME_JOB, stop_if)
        if why not in ('OK', 'STOPPED'):
            self.get_logger().warn(
                f'{self.rid}: could not unfold the arm at {self.home_node} '
                f'({why})')

    # ------------------------------------------------------------ status / TF
    def _publish(self):
        """로봇 상태를 /fleet/robot_status 로 보낸다(10 Hz).

        실측 지도에서 위치를 모르면 자동 위치 추정 상태만 보낸다. 상태는
        충전 > 팔 작업 > 주행 상태 순, 오류는 비상 정지 > 통신 > 센서 > 주행.
        """
        if self.measured_map and not self.have_truth:
            # [수정 2026-11-20] T-49: 자동 위치 추정 중·실패도 보고(위치 없이)
            st = self.locz.tick_state() if self.locz is not None else ''
            if st:
                self.pub_status.publish(RobotStatus(
                    stamp=self.get_clock().now().to_msg(), robot_id=self.rid,
                    state=st, battery=float(self.battery),
                    reached_index=-1, arm_state=self.arm_state,
                    error='SELF_CHECK_ERROR' if st == 'NOT_LOCALIZED'
                    else ''))
            return
        now = self.get_clock().now().to_msg()
        if self.battery_from_topic:
            # [수정 2026-11-17] UR-21: 실기기는 충전대 좌표가 아니라 측정한
            # 잔량의 변화로 충전 여부를 판단 (예전에는 홈 노드에 서 있기만
            # 해도 충전 중으로 보고)
            self.charging = self._charging_from_battery()
        # [수정 2026-11-18] P3: 가짜 배터리·충전대 좌표 판정은 sim_backend
        elif self.sim is not None:
            self.sim.update_battery()
        # 보고 상태: 충전 중 > 팔 작업 > 주행 상태
        state = 'CHARGING' if self.charging else (self.arm_state if self.arm_state != 'IDLE' else self.nav_state)
        error = ''
        if self.estop:
            state, error = 'E_STOP', 'EMERGENCY_STOP'
        elif self.nav_state == 'WAIT_FMS':
            error = 'COMMUNICATION_ERROR'
        # [수정 2026-11-17] D4: 위치 추정이 끊김(굳은 위치를 보고 중)
        elif self._loc_lost():
            error = 'SENSOR_ERROR'
        elif self.drive_error:
            error = 'DRIVE_ERROR'
        self.pub_status.publish(RobotStatus(stamp=now, robot_id=self.rid, state=state, x=self.x, y=self.y, yaw=self.yaw,
                                            battery=float(self.battery), charging=self.charging, task_id=self.task_id,
                                            plan_version=self.pv, reached_index=self.reached, node_id=self.node_id,
                                            arm_state=self.arm_state, error=error))
        # [수정 2026-11-18] P3(R1-4): map -> base TF(Nav2 없는 주행)와 가짜 바퀴
        # 관절값은 시뮬만 냄. 실기기의 바퀴 관절값은 pinky_driver 의 것만 남음.
        # With Nav2 the pose comes from map -> odom -> base: AMCL on the robot
        if self.sim is not None:
            self.sim.publish(now)
        # 팔 관절값 발행(RViz 모델)
        aj = JointState()
        aj.header.stamp, aj.name, aj.position = now, JOINTS, [float(v) for v in self.arm_q]
        self.pub_arm_js.publish(aj)


def main():
    """노드를 띄우고 6 스레드 실행기로 돈다. 끝날 때 마지막 자세 저장."""
    rclpy.init()
    n = MobileController()
    ex = MultiThreadedExecutor(num_threads=6)
    ex.add_node(n)
    try:
        ex.spin()
    except KeyboardInterrupt:
        pass
    # [수정 2026-11-20] T-49: 끝날 때 마지막 자세 저장
    if n.locz is not None:
        n.locz.save(force=True)
        # [수정 2026-11-20] T-52: 감시 요약 한 줄
        if n.locz.p['monitor']:
            n.locz.summary()


if __name__ == '__main__':
    main()
