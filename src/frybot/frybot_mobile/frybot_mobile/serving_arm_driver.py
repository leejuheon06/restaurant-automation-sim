"""FrybotMobile Arm Controller 의 실물 구동부: AMR 위의 서빙 팔(JetCobot 280).

팔에 달린 Raspberry Pi 에서 돕니다. ArmJob 액션
(/<robot_id>/serving_arm/arm_job)을 받아 pymycobot 으로 팔을 움직이고,
읽은 관절값을 /<robot_id>/serving_arm/joint_states 로 냅니다.

  ros2 launch frybot_mobile serving_arm.launch.py robot_id:=pinky1

작업별 자세는 config/serving_arm.yaml 에서 읽습니다. 자세가 비어 있는
작업은 팔을 움직이지 않고 NO_POSE 로 실패합니다. HOME 은 rest 자세로
갑니다. 취소가 오면 팔을 그 자리에 세웁니다(모터는 켠 채로 유지).
[수정 2026-11-26] 작업 이름 통일(사용자 결정): 위의 'HOME 은 rest' 는 바뀜.
REST 는 rest(주행용 접은 자세)로, HOME 은 0도 home 자세로 갑니다. 그 밖의
작업은 home -> 작업 자세들 -> rest 순서이고, 이미 닿아 있는 자세는 명령 없이
지나갑니다.

[수정 2026-11-20] 신규. mobile_controller 가 serving_arm:=real 일 때
/<robot>/arm_job 을 이 노드로 넘깁니다(_arm_forward). 기본은
mobile_controller 의 대역(_arm_job)입니다.
"""
import math
import os
import threading
import time

from ament_index_python.packages import get_package_share_directory
from pymycobot.mycobot280 import MyCobot280
import rclpy
from rclpy.action import ActionServer
from rclpy.action import CancelResponse
from rclpy.action import GoalResponse
from rclpy.action.server import ServerGoalHandle
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from sensor_msgs.msg import JointState
import yaml

from frybot_interfaces.action import ArmJob
from frybot_mobile.arm_common import JOINTS

# myCobot 280 의 관절 한계(도), J1~J6. pymycobot 3.9.2 의 검사 값과 같음
LIMITS_DEG = ((-168, 168), (-135, 135), (-150, 150), (-145, 145),
              (-165, 165), (-180, 180))
# [수정 2026-11-26] 작업 이름 통일(사용자 결정): 11-20 에 넣은 HOME(rest 로
# 감)의 동작은 REST 로 이름을 바꾸고, HOME 은 0도 home 자세로 가는 작업이 됨
# (HOME 의 뜻이 바뀜). home 은 충전소 대기 자세이자 LOAD·UNLOAD 등을
# 시작하기 전에 거치는 자세
REST_JOB = 'REST'  # rest(주행용 접은 자세)로 가는 작업 이름
HOME_JOB = 'HOME'  # home(0도) 자세로 가는 작업 이름
# [수정 2026-11-20] 그리퍼 값 범위(0 닫힘 ~ 100 열림, pymycobot)
GRIPPER_MIN, GRIPPER_MAX = 0, 100


# [수정 2026-11-20] rest_gripper(rest 로 갈 때의 그리퍼 값)도 읽어 돌려줌
def load_poses(path: str) -> tuple[list[float], int | None,
                                   dict[str, list[list[float]]]]:
    """자세 파일을 읽고 관절 한계를 검사한다.

    Args:
        path: config/serving_arm.yaml 형식의 파일 경로.

    Returns:
        (rest 자세, rest_gripper, 작업 이름 -> 경유 자세 목록). 각도는 도,
        J1~J6 순서. rest_gripper 는 0(닫힘)~100(열림), 키가 없으면 None.

    Raises:
        OSError: 파일을 읽지 못할 때.
        ValueError: 자세가 6개 값이 아니거나 관절 한계를 벗어날 때,
            rest_gripper 가 0~100 정수가 아닐 때.
    """
    with open(path, encoding='utf-8') as f:
        data = yaml.safe_load(f) or {}

    # 자세 하나 검사: 값 6개, 관절마다 LIMITS_DEG 안. 통과하면 float 목록
    def pose(name: str, values: list) -> list[float]:
        if not isinstance(values, list) or len(values) != 6:
            raise ValueError(f'{name}: 관절값 6개가 필요합니다: {values}')
        out = [float(v) for v in values]
        for i, (v, (lo, hi)) in enumerate(
                zip(out, LIMITS_DEG, strict=True)):
            if not lo <= v <= hi:
                raise ValueError(
                    f'{name}: J{i + 1}={v} 가 한계 {lo}~{hi} 밖입니다')
        return out

    # rest 가 없으면 0도 자세. jobs 의 값이 비면(None, []) 빈 경유 목록
    rest = pose('rest', data.get('rest', [0, 0, 0, 0, 0, 0]))
    # [수정 2026-11-20] rest_gripper: 없으면 None(그리퍼를 건드리지 않음)
    grip = data.get('rest_gripper')
    if grip is not None:
        if isinstance(grip, bool) or not isinstance(grip, int) \
                or not GRIPPER_MIN <= grip <= GRIPPER_MAX:
            raise ValueError(
                f'rest_gripper: {GRIPPER_MIN}~{GRIPPER_MAX} 정수가 필요합니다:'
                f' {grip}')
    jobs = {}
    for job, path_deg in (data.get('jobs') or {}).items():
        jobs[job] = [pose(f'{job}[{i}]', p)
                     for i, p in enumerate(path_deg or [])]
    return rest, grip, jobs


# [수정 2026-11-26] 서빙 팔 자세 연동: home 키(0도 자세) 읽기. load_poses 의
# 반환 형식은 그대로 두려고 따로 읽음
def load_home(path: str) -> list[float]:
    """자세 파일의 home(0도 자세)를 읽고 관절 한계를 검사한다.

    Args:
        path: config/serving_arm.yaml 형식의 파일 경로.

    Returns:
        home 자세(도, J1~J6). 키가 없으면 모두 0.

    Raises:
        OSError: 파일을 읽지 못할 때.
        ValueError: 값이 6개가 아니거나 관절 한계를 벗어날 때.
    """
    with open(path, encoding='utf-8') as f:
        data = yaml.safe_load(f) or {}
    values = data.get('home', [0, 0, 0, 0, 0, 0])
    if not isinstance(values, list) or len(values) != 6:
        raise ValueError(f'home: 관절값 6개가 필요합니다: {values}')
    out = [float(v) for v in values]
    for i, (v, (lo, hi)) in enumerate(zip(out, LIMITS_DEG, strict=True)):
        if not lo <= v <= hi:
            raise ValueError(f'home: J{i + 1}={v} 가 한계 {lo}~{hi} 밖입니다')
    return out


class ServingArmDriver(Node):
    """서빙 팔 한 대를 pymycobot 으로 움직이는 ArmJob 액션 서버."""

    def __init__(self) -> None:
        super().__init__('serving_arm_driver')
        p = self.declare_parameter
        # 팔을 올린 AMR 이름: 액션·토픽 이름의 /<robot_id>/serving_arm 접두어
        self.rid = p('robot_id', 'pinky1').value
        # [수정 2026-11-20] 기본 20 → 10: 사용자 요구(주행용 접기 등 큰 이동을
        # 천천히). 실물에서 0도 ↔ rest(최대 148도) 왕복이 각 약 10초
        # [수정 2026-11-20] 기본 10 → 70: 실물 측정에서 속도 20~70 의 목표
        # 초과·발열 차이가 없고 접기가 1.7초(10 은 너무 오래 걸림). 80 이상은
        # 미측정. docs/2026-11-20_SERVING_ARM_REST_POSE.md
        # [수정 2026-11-20] 기본 70 → 60: 새 rest 를 70 으로 왕복할 때 사용자가
        # 육안으로 흔들림을 봄(읽은 초과는 0.0도). 사용자 결정, 같은 문서 7.1절
        self.speed = int(p('speed', 60).value)            # pymycobot 1~100
        # tolerance_deg: 모든 관절 오차가 이 값(도) 미만이면 그 자세에 닿음
        # move_timeout: 경유 자세 하나에 닿기까지의 제한 시간(초)
        self.tol = float(p('tolerance_deg', 3.0).value)
        # [수정 2026-11-20] 기본 20 → 30 초: 속도 10 에서 148도 이동이 약
        # 10초(안정 대기 포함 11.7초)라 큰 이동의 여유를 둠
        self.move_timeout = float(p('move_timeout', 30.0).value)
        # 자세 파일. 비우면 설치된 config/serving_arm.yaml
        poses_file = p('poses_file', '').value or os.path.join(
            get_package_share_directory('frybot_mobile'), 'config',
            'serving_arm.yaml')
        # [수정 2026-11-20] rest 로 갈 때의 그리퍼 값(None 이면 건드리지 않음)
        self.rest, self.rest_gripper, self.jobs = load_poses(poses_file)
        # [수정 2026-11-26] 서빙 팔 자세 연동: 0도 home 자세(HOME 작업, 작업
        # 시작 전)
        self.home = load_home(poses_file)
        # 팔 직렬 포트(udev 별칭으로 보임, 확인 필요)와 통신 속도(bps)
        port = p('port', '/dev/ttyJETCOBOT').value
        self.mc = MyCobot280(port, int(p('baud', 1000000).value))
        # 직렬 포트는 한 번에 한 명령만: 관절값 읽기와 이동 명령이 섞이지
        # 않게 함
        self.lock = threading.Lock()
        self.busy = threading.Lock()         # 작업은 한 번에 하나만 받음
        self.q_deg = None                    # 마지막으로 읽은 관절값(도)
        self.q_t = 0.0                       # q_deg 를 읽은 시각(time.time())
        # 작업 실행(_job, 끝날 때까지 블로킹)과 관절값 타이머가 함께 돌도록
        # 재진입 콜백 그룹 + main 의 MultiThreadedExecutor 를 씀
        cb = ReentrantCallbackGroup()
        name = f'/{self.rid}/serving_arm'
        self.pub_js = self.create_publisher(
            JointState, f'{name}/joint_states', 10)
        # ArmJob 액션 서버. 취소 요청은 항상 받고 실제 정지는 _move 가 함
        ActionServer(self, ArmJob, f'{name}/arm_job',
                     execute_callback=self._job, goal_callback=self._goal,
                     cancel_callback=lambda _: CancelResponse.ACCEPT,
                     callback_group=cb)
        # 5 Hz 로 관절값 발행
        self.create_timer(0.2, self._publish, callback_group=cb)
        # 자세가 비어 있는 작업 이름(기동 로그용)
        empty = sorted(j for j, w in self.jobs.items() if not w)
        self.get_logger().info(
            f'{self.rid} serving arm on {port}, poses: {poses_file}'
            + (f', 자세 없는 작업: {empty}' if empty else ''))

    def _angles(self) -> list[float] | None:
        """팔에서 관절값(도)을 읽는다. 응답이 없으면 None."""
        with self.lock:
            a = self.mc.get_angles()
        if isinstance(a, list) and len(a) == 6:
            self.q_deg, self.q_t = [float(v) for v in a], time.time()
            return self.q_deg
        return None

    def _goal(self, goal: ArmJob.Goal) -> GoalResponse:
        """다른 작업을 하는 중이면 새 작업을 받지 않는다."""
        if self.busy.locked():
            self.get_logger().warn(f'{goal.job} 거절: 다른 작업 수행 중')
            return GoalResponse.REJECT
        return GoalResponse.ACCEPT

    def _waypoints(self, job: str) -> list[list[float]]:
        """작업의 경유 자세 목록. 자세가 정해지지 않았으면 빈 목록.

        [수정 2026-11-20] 모든 작업은 성공하면 rest 로 끝남: 마지막 경유
        자세가 rest 가 아니면 rest 를 덧붙임. HOME 은 rest 하나.
        [수정 2026-11-26] 작업 이름 통일: rest 하나로 가는 작업은 REST(예전
        HOME), HOME 은 0도 home 자세 하나. 그 밖의 작업은 home 에서 시작(맨
        앞이 home 이 아니면 덧붙임). 자세가 빈 작업은 예전처럼 빈 목록(NO_POSE).
        """
        if job == REST_JOB:
            return [self.rest]
        if job == HOME_JOB:
            return [self.home]
        path = self.jobs.get(job, [])
        if path and path[0] != self.home:
            path = [self.home] + path
        if path and path[-1] != self.rest:
            path = path + [self.rest]
        return path

    def _job(self, gh: ServerGoalHandle) -> ArmJob.Result:
        """작업 하나를 수행한다: 경유 자세를 차례로 지난다."""
        g = gh.request
        with self.busy:
            reason = self._run(gh, g.job)
        if reason == 'OK':
            gh.succeed()
        elif reason == 'CANCELED':
            gh.canceled()
        else:
            gh.abort()
        # rclpy 로거는 같은 호출 자리에서 등급을 바꾸지 못해 둘로 나눔
        if reason == 'OK':
            self.get_logger().info(f'{g.job} ({g.task_id}): OK')
        else:
            self.get_logger().warn(f'{g.job} ({g.task_id}): {reason}')
        return ArmJob.Result(success=reason == 'OK', reason=reason)

    def _run(self, gh: ServerGoalHandle, job: str) -> str:
        """작업을 실행하고 결과 사유를 돌려준다.

        Args:
            gh: 액션 목표 핸들(취소 확인과 진행률 보고에 씀).
            job: ArmJob 의 job 이름.

        Returns:
            'OK', 'CANCELED', 'NO_POSE'(자세 미정), 'ARM_OFFLINE'(팔 무응답),
            'ARM_TIMEOUT'(제시간에 자세에 닿지 못함) 중 하나.
        """
        path = self._waypoints(job)
        if not path:
            return 'NO_POSE'
        if self._angles() is None:
            return 'ARM_OFFLINE'
        # 이동 전에 서보 전원을 켬
        with self.lock:
            self.mc.power_on()
        for i, target in enumerate(path):
            # [수정 2026-11-26] 서빙 팔 자세 연동: 이미 그 자세면 명령(그리퍼
            # 포함)을 보내지 않음. 실물은 send_angles 한 번에 약 1.6 s 걸려
            # 이미 rest 일 때 HOME 이 바로 끝나야 함
            if self._at(target):
                gh.publish_feedback(ArmJob.Feedback(
                    phase=job, progress=float((i + 1) / len(path))))
                continue
            # [수정 2026-11-20] rest 로 갈 때는 그리퍼를 먼저 맞추고 접음
            # (닫은 채 접기는 실물에서 확인). 키가 없으면 그리퍼는 그대로
            if target == self.rest and self.rest_gripper is not None:
                with self.lock:
                    self.mc.set_gripper_value(self.rest_gripper, self.speed)
            reason = self._move(gh, target)
            if reason != 'OK':
                return reason
            gh.publish_feedback(ArmJob.Feedback(
                phase=job, progress=float((i + 1) / len(path))))
        return 'OK'

    # [수정 2026-11-26] 서빙 팔 자세 연동: 이미 그 자세인지(읽은 관절값 기준)
    def _at(self, target: list[float]) -> bool:
        """방금 읽은 관절값이 target 에서 모든 관절 tol 미만인지.

        Args:
            target: 자세(도, J1~J6).

        Returns:
            읽기에 실패하면 False(명령을 보내는 쪽으로).
        """
        a = self._angles()
        return bool(a) and max(abs(x - y) for x, y
                               in zip(a, target, strict=True)) < self.tol

    def _move(self, gh: ServerGoalHandle, target: list[float]) -> str:
        """자세 하나로 이동하고, 닿거나 취소·시간 초과가 될 때까지 기다린다."""
        with self.lock:
            self.mc.send_angles(target, self.speed)
        t0 = time.time()
        while rclpy.ok():
            if gh.is_cancel_requested:
                self._halt()
                return 'CANCELED'
            a = self._angles()
            if a and max(abs(x - y) for x, y
                         in zip(a, target, strict=True)) < self.tol:
                return 'OK'
            if time.time() - t0 > self.move_timeout:
                self._halt()
                return 'ARM_TIMEOUT'
            time.sleep(0.1)
        self._halt()
        return 'CANCELED'

    def _halt(self) -> None:
        """움직이던 팔을 그 자리에 세운다(모터 전원은 유지)."""
        with self.lock:
            self.mc.stop()

    def _publish(self) -> None:
        """읽은 관절값을 라디안으로 발행한다. 읽지 못했으면 내지 않는다."""
        if not self.busy.locked():           # 작업 중에는 _move 가 읽음
            self._angles()
        if self.q_deg is None or time.time() - self.q_t > 2.0:
            # 이동 중에는 관절값 읽기가 잠시 비는 일이 있어(2026-11-20 실물
            # 시험) 경고하지 않고 발행만 쉼
            if not self.busy.locked():
                self.get_logger().warn(
                    '팔이 응답하지 않습니다(전원·USB 확인)',
                    throttle_duration_sec=5.0)
            return
        js = JointState()
        js.header.stamp = self.get_clock().now().to_msg()
        js.name = JOINTS
        js.position = [math.radians(v) for v in self.q_deg]
        self.pub_js.publish(js)


def main() -> None:
    """serving_arm_driver 노드를 띄운다."""
    rclpy.init()
    node = ServingArmDriver()
    # 액션 실행과 타이머를 함께 돌리는 다중 스레드 실행기
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
