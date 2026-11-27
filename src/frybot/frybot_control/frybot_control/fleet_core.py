"""Task Manager core (ROS-independent so it can also run in the offline benchmark).

Responsibilities
  * task queue + scheduler plug-in   -> which AMR takes which GUIDE / SERVE / COLLECT task
  * path planner plug-in             -> timed route on the single-lane roadmap
  * traffic layer                    -> node locks: request / grant / enter / exit, stall detection, replanning
  * cooking cell coordinator         -> cook arms A/B, fryer, wok, hand-off slots (acquire-all-at-once, no deadlock)

All side effects go through a FleetIO object; all inputs arrive via on_* methods and tick(now).
관제(Task Manager) 핵심. ROS 와 무관해 task_manager_node(ROS)와
mock_fleet·offline_bench(모의)가 같은 코드를 씀.
"""
import math
import random
import time
from dataclasses import dataclass, field

# 프로젝트 내부: 기기 상태 코드, 지도, 경로 계획기·배정기 플러그인
from . import device_state
from .layout import Graph, MENU, SAFE_DIST
from .planners import make_planner, PLANNERS, PlanRequest, ReservationTable, Step, INF, DEFAULT_PLANNER
from .schedulers import make_scheduler, SCHEDULERS, DEFAULT_SCHEDULER

AMR_TASKS = ('GUIDE', 'SERVE', 'COLLECT')  # AMR 이 맡는 임무(배정 대상)
# [수정 2026-11-20] T-52: 같은 노드로 다시 세우는 이동 명령을 받는 최소 거리(m)
# (Nav2 xy_goal_tolerance 1.5 cm 보다 크게 벗어났을 때)
RESETTLE_MIN = 0.015
# [수정 2026-11-20] T-49: 위치를 아직 모르는 로봇의 상태(위치를 쓰지 않음)
UNLOCALIZED = ('LOCALIZING', 'NOT_LOCALIZED')
# [수정 2026-11-20] T-47: 서빙 팔이 있어야 하는 임무(serving_robots 로 제한)
ARM_TASKS = ('SERVE', 'COLLECT')
# [수정 2026-11-20] T-47: 팔 없는 로봇에 매기는 배정 비용(초). 배정은 하지
# 않으며, 최소 비용 배정이 다른 쌍을 고르도록 크게 둠
NO_ARM_COST = 1.0e6
# 임무 종류별 기본 우선순위(클수록 급함). submit_task 의 priority 가 0
# 이면 이 값. 배정기와 정체 판단(_rank)이 씀
PRIORITY = {'GUIDE': 3, 'SERVE': 3, 'COLLECT': 1}
# [수정 2026-11-17] T-24: 우선순위를 뒤집힌 로봇이 되뒤집지 못하는 시간(초).
# 뒤집은 로봇이 두 구간쯤 갈 시간(실기기 구간당 약 3.5초)
FLIP_HOLD = 8.0
# [수정 2026-11-17] T-26: 비켜 준 유휴 로봇이 원래 노드로 돌아가려고 상대가
# 지나가기를 기다리는 최대 시간(초). 넘으면 비킨 자리에 남음
YIELD_BACK_WAIT = 60.0
# [수정 2026-11-18] W8-3: 같은 목적지 계획 실패가 이 시간(초)을 넘으면 임무를
# 보류하고 알림(임무가 없으면 알림만). mock_fleet 의 지표도 이 값을 씀
PLAN_FAIL_SUSPEND_SEC = 20.0


class FleetIO:
    """Outputs of the core. The ROS node and the offline simulator both implement this.

    관제 코어의 출력. task_manager_node 와 mock_fleet 이 구현함.
    """

    # 로봇에 경로(NavigateRoute)를 보냄. mode: NORMAL/GUIDE/YIELD,
    # steps: list[Step]. task_id 는 임무가 없으면 'RETURN'
    def send_route(self, robot_id, task_id, plan_version, mode, visit_id, steps): ...
    # 통행 허가(TrafficGrant): 경로의 index 번째 노드까지 가도 됨
    def grant(self, robot_id, task_id, plan_version, index): ...
    # 로봇의 경로 실행을 취소
    def cancel_route(self, robot_id): ...
    # 팔 작업 취소(일시 중단·비상 정지 때 서빙 팔)
    def cancel_arm(self, arm_id): ...
    # 팔 작업 요청. arm_id: 로봇 id(서빙 팔) 또는 cook_arm_a/b,
    # duration: 예상 시간(초), params: params_json 으로 갈 dict
    def arm_job(self, arm_id, task_id, job, duration, params): ...
    # [수정 2026-11-25] I/F 정의서 v0.2 이름: TaskEvent -> TaskProgress
    # [수정 2026-11-26] I/F v0.3 최종 판 이름: TaskProgress -> TaskEvent
    # 임무 상태 변화(TaskEvent)를 central_control 로
    def task_event(self, ev: dict): ...
    # 실행 로그 한 줄(/frybot/event_log)
    def log(self, event, **fields): ...


@dataclass
class Task:
    """AMR 또는 조리 셀이 수행하는 임무 하나(관제 내부 기록)."""

    id: str  # 종류 첫 글자 + 일련번호(G0001, M0002 등)
    type: str  # GUIDE, SERVE, COLLECT, COOK, MOVE
    visit_id: int = 0  # 방문(손님 일행) id
    order_id: int = 0  # 주문 id
    item_id: int = 0  # 주문 항목 id
    table_id: int = 0  # 테이블 번호
    menu: str = ''  # MENU 의 키(SERVE·COOK)
    priority: int = 1  # 클수록 급함
    created: float = 0.0  # 접수 시각(관제 시계, 초)
    state: str = 'PENDING'          # PENDING IN_PROGRESS DONE SUSPENDED CANCELED
    robot_id: str = ''  # 맡은 로봇('' = 미배정)
    # 단계 목록: ('move', 지점, 모드), ('arm', 작업, 초), ('event', 이름)
    phases: list = field(default_factory=list)
    pi: int = 0  # 지금 수행할 phases 번호
    carrying: bool = False  # 음식·식기를 싣고 있음
    assigned_at: float = 0.0  # 마지막 배정 시각
    finished_at: float = 0.0  # 완료 시각
    reason: str = ''  # 보류·취소 이유
    start_node: str = ''  # 첫 이동 지점 노드(배정 비용 기준)
    rebalanced: int = 0             # times the rolling-horizon scheduler moved it to another robot
    # [수정 2026-11-18] W2: State Diagram v4 의 LOADED -> SERVING. 적재 뒤
    # 테이블행 구간을 처음 나아갔을 때 SERVING 을 한 번만 내기 위한 표시
    serving_sent: bool = False


@dataclass
class Robot:
    """관제가 보는 AMR 한 대의 상태(보고 값 + 경로·락·양보 상태)."""

    id: str  # pinky1..N
    home: str  # 출발 노드(충전대, roadmap.json homes)
    node: str  # 마지막으로 도착한(서 있는) 노드
    # 가고 있는(락 잡은) 노드. '' 면 node 위에 서 있음, == node 면 그
    # 노드로 복귀(REJOIN) 중
    heading: str = ''
    route: list = None              # list[Step]
    idx: int = 0  # 마지막 도착 route 칸(-1: route[0] 으로 가는 중)
    granted: int = 0  # 허가한 route 칸 번호
    plan_version: int = 0  # 경로 번호(옛 피드백·허가 구분)
    mode: str = 'NORMAL'  # 지금 경로의 모드(NORMAL/GUIDE/YIELD)
    goal: str = ''  # 지금 경로의 목적 노드
    pending_goal: tuple = None      # (goal, mode, next_try)
    task: Task = None  # 수행 중인 임무
    returning: bool = False  # 임무 없이 park 로 가는 중
    arm_busy: str = ''  # 진행 중인 서빙 팔 작업('' = 없음)
    arm_until: float = 0.0  # 팔 작업이 끝날 예상 시각
    estop: bool = False  # 비상 정지 또는 일시 중단 중
    battery: float = 100.0  # 보고된 배터리(0~100 으로 다룸)
    charging: bool = False  # 충전 중 보고
    x: float = 0.0  # 보고 위치(지도 좌표, m)
    y: float = 0.0
    yaw: float = 0.0  # 보고 방향(rad)
    # [수정 2026-11-18] P2: 실기기 RobotStatus.state 를 담으므로 이름을 고침
    # (예전 sim_state)
    reported_state: str = ''
    wait_since: float = None  # 허가를 기다리기 시작한 시각
    blocked_by: str = ''  # 다음 노드를 막은 로봇
    last_replan: float = 0.0  # 마지막 정체 처리 시각
    held: set = field(default_factory=set)  # 락을 잡은 노드들
    dist: float = 0.0  # 누적 주행 거리(m, 지표)
    online: bool = False  # 상태 보고가 2초 안에 옴
    last_status: float = 0.0  # 마지막 상태 보고 시각
    needs_replan: bool = False  # 다음 tick 에서 다시 계획
    park: str = ''                  # where this robot waits when idle (charger or standby spot)
    yield_to: str = ''              # robot we stepped aside for; we resume only once it has passed
    yield_from: str = ''            # node we vacated for it
    yield_until: float = 0.0        # give up waiting for it after this time
    yield_note: str = ''            # robot we wait for on our own (short) path instead of driving a long way round
    last_yield: float = -1e9        # last time we stepped aside by choice (not twice within 10 s)
    error: str = ''                 # error the robot reports itself (device_state.ERROR name, '' = none)
    fail_count: int = 0             # failed routes in a row (reset by the next reached node)
    avoid_node: str = ''            # node the robot could not reach: plan round it until avoid_until
    avoid_until: float = 0.0
    # [수정 2026-11-17] T-23: 같은 판단을 다시 기록하지 않기 위한 표시
    wait_note: tuple = None  # 마지막 PLAN_WAIT 기록 키
    skip_note: tuple = None  # 마지막 YIELD_SKIP 기록 키
    # [수정 2026-11-17] T-24: 이 시각까지는 우선순위를 뒤집지 못함
    # (방금 뒤집은 상대를 되뒤집어 서로 계획을 무효화하는 것 방지)
    no_flip_until: float = 0.0
    # [수정 2026-11-17] 기동 후 출발 노드 자동 이동(auto_home)용 상태.
    # homed: 이번 관제 실행에서 자동 이동을 이미 처리함(성공·생략 모두)
    homed: bool = False
    still_pos: tuple = None         # 서 있다고 본 기준 위치
    still_since: float = 0.0        # 그 위치에 머문 시작 시각
    home_retry: float = 0.0         # 이 시각 전에는 다시 시도하지 않음
    # [수정 2026-11-20] T-45: 임무 뒤 홈 복귀를 이 시각 전에는 다시 시도 안 함
    return_retry: float = 0.0
    # [수정 2026-11-20] T-49: 위치를 모를 때 로봇이 보고한 상태('' = 아님)
    localizing: str = ''
    home_note: str = ''             # 마지막으로 기록한 보류 이유
    # [수정 2026-11-17] UR-18: 관리자의 일시 중단(PAUSE). estop 과 함께 켜져
    # 로봇을 세우되, 화면에는 비상 정지가 아닌 "일시 중단"으로 표시
    paused: bool = False
    # [수정 2026-11-17] UR-19: 이상 종류 -> 시작 시각 (알람의 발생 시각)
    fault_since: dict = field(default_factory=dict)
    # [수정 2026-11-17] A3: 상태 보고가 끊긴 시각 (None = 연결됨)
    offline_since: float = None
    # [수정 2026-11-18] W8-3: 같은 목적지 계획 실패 묶음 [목적지, 첫 실패 시각,
    # 알림을 냈는지]. 계획이 성공하거나 목적지가 바뀌면 지움
    plan_fail: list = None


class CookJob:
    """조리 작업 하나의 진행 상태(레시피 공정을 차례로 수행).

    Args:
        task: COOK 임무.
        ops: _recipe 가 만든 공정 목록.
    """

    def __init__(self, task, ops):
        self.task, self.ops, self.pc = task, ops, 0  # pc: 지금 할 ops 번호
        self.busy = False            # an arm job / timer is running
        self.until = 0.0  # 타이머 끝 시각(0 = 없음)
        self.retries = 0  # 덜 익어 다시 튀긴 횟수
        self.wait_doneness_since = None  # 익힘 판정 대기 시작
        self.label = 'QUEUED'  # 화면용 공정 단계 이름


# [수정 2026-11-18] W2: 공정 단계 이름을 State Diagram v4 의 조리 작업 상태로
def _cook_state(job: CookJob) -> str:
    """조리 작업의 v4 상태를 돌려준다.

    Args:
        job: 조리 작업.

    Returns:
        WAIT_ARM(팔을 아직 잡지 못함), PROCESS(공정 수행 중),
        HANDOFF(인계대 배치 중), DONE, CANCELED 중 하나.
    """
    if job.task.state == 'CANCELED':
        return 'CANCELED'
    if job.task.state == 'DONE' or job.label == 'READY':
        return 'DONE'
    if job.label == 'QUEUED':
        return 'WAIT_ARM'
    if job.label == 'PLACE_HANDOFF':
        return 'HANDOFF'
    return 'PROCESS'


class FleetCore:
    """관제 코어: 임무 배정, 경로 계획, 통행 허가(교통 계층), 조리 셀 조율.

    입력은 on_* 메서드와 tick(now), 출력은 io(FleetIO)로만 나감.

    Args:
        io: 출력 구현(FleetIO).
        robot_ids: 관제할 AMR id 목록.
        scheduler: 배정기 이름(SCHEDULERS).
        planner: 경로 계획기 이름(PLANNERS).
        speed: 일반 주행 속도(m/s).
        guide_speed: 손님 안내 속도(m/s).
        cook_time_scale: 조리 시간 축소 배율(시간 / 이 값).
        stall_timeout: 허가를 이 시간(초) 넘게 못 받으면 정체 처리.
        min_battery: 이보다 낮으면(%) 새 임무를 주지 않음.
        handoff_slots: 음식 받는 곳 한 곳에 둘 수 있는 접시 수.
        use_doneness: 튀긴 뒤 AI 익힘 판정을 기다림.
        plan_speed_factor: 계획 속도 = 주행 속도 x 이 값.
        use_standby: 임무 없는 로봇을 대기 위치에도 세움(가상 매장).
        standby_min_battery: 이보다 낮으면(%) 대기 대신 충전대로.
        prefer_yield: 먼 우회 대신 기다리거나 비켜 섬.
        yield_detour_ratio: 먼 우회 기준(최단 거리의 배수).
        yield_detour_min: 먼 우회 기준(최단 거리 + 이 값, m).
        yield_max_wait: 기다리는 계획이 우회보다 늦어도 되는 시간(초).
        route_retries: 주행 실패 뒤 자동 재계획 횟수.
        off_node_dist: 노드에서 이 거리(m) 넘게 벗어나면 노드 밖.
        rejoin_max_dist: 노드 복귀로 고를 노드의 최대 거리(m).
        pv_base: 경로 번호 시작값(None 이면 시각 기반).
        auto_home: 기동 후 출발 노드로 한 번 이동(실측 지도).
        auto_home_settle: 자동 이동 전에 서 있어야 하는 시간(초).
        offline_hold: 끊긴 로봇의 임무를 보류하기까지의 시간(초).
        plan_overhead: 계획의 구간 지연(초).
        rng_seed: 관제 난수 씨앗(None 이면 매번 다름).
        serving_robots: 서빙 팔을 올린 로봇(비면 모든 로봇).
        pos_block_dist: 서 있는 로봇 보고 위치의 점유 거리(m).
    """

    def __init__(self, io: FleetIO, robot_ids=('pinky1', 'pinky2', 'pinky3'), scheduler=DEFAULT_SCHEDULER,
                 planner=DEFAULT_PLANNER, speed=0.08, guide_speed=0.05, cook_time_scale=20.0,
                 stall_timeout=3.0, min_battery=25.0, handoff_slots=3, use_doneness=True,
                 plan_speed_factor=0.9, use_standby=True, standby_min_battery=40.0, prefer_yield=True,
                 yield_detour_ratio=1.4, yield_detour_min=0.4, yield_max_wait=25.0, route_retries=2,
                 off_node_dist=0.06, rejoin_max_dist=1.0, pv_base=None,
                 auto_home=False, auto_home_settle=3.0, offline_hold=10.0,
                 plan_overhead=0.0, rng_seed=None, serving_robots=(),
                 pos_block_dist=0.12):
        self.io = io  # 출력: 경로·허가·팔 작업·로그
        # [수정 2026-11-20] T-52: 서 있는 다른 로봇의 보고 위치에서 이 거리(m)
        # 안의 노드는 허가·계획하지 않음. SAFE_DIST 0.155 에서 서 있을 때의
        # 위치 추정 흔들림 여유 0.035(실기기 AMCL 흔들림 +-2~3 cm)를 뺀 값.
        # W1-B1 15.7 cm 처럼 가까운 노드도 노드 위 +-3 cm 흔들림(12.7 cm)은
        # 막지 않고, 09 의 5.9 cm 벗어남(B1 까지 9.9 cm)은 막음
        self.pos_block_dist = pos_block_dist
        # [수정 2026-11-20] T-47: 서빙 팔을 올린 로봇. 비면 모든 로봇이
        # SERVE·COLLECT 를 받음(예전 동작, 시뮬·벤치)
        self.serving_robots = set(serving_robots)
        # [수정 2026-11-17] A3: 로봇이 이 시간(초) 넘게 끊겨 있으면 진행 중인
        # 임무를 OFFLINE 으로 보류(관리자가 RETRY_TASK 로 재개)
        self.offline_hold = offline_hold
        self.graph = Graph()  # 지도(map_id 는 FRYBOT_MAP_ID)
        # 아래 값들은 생성자 인자 그대로(뜻은 클래스 docstring)
        self.speed, self.guide_speed = speed, guide_speed
        self.cook_scale = cook_time_scale
        self.stall_timeout = stall_timeout
        self.min_battery = min_battery
        self.use_doneness = use_doneness
        self.plan_speed_factor = plan_speed_factor
        # [수정 2026-11-18] W6(E1, R5-4): 계획의 구간 지연(초). 구간 시간 =
        # 지연 + 거리 / (속도 x plan_speed_factor). 손님 안내 구간의 실측
        # 지연은 없어 같은 값을 씀(가정). 기본 0.0 = 예전과 같음
        self.plan_overhead = plan_overhead
        # [수정 2026-11-18] W8-1: 물러난 뒤 다시 시도하는 시각을 흩는 난수.
        # 전역 random 대신 관제 코어의 생성기(rng_seed=None 이면 매번 다름)
        self.rng = random.Random(rng_seed)
        # 대기 위치 사용과 그 배터리 하한(가상 매장 _park_goal)
        self.use_standby, self.standby_min_battery = use_standby, standby_min_battery
        # Yielding: when the planner's answer to another robot on our path is a long way round (longer than
        # ratio x shortest and shortest + min metres), wait for it on the short path (at most yield_max_wait seconds
        # later than the detour), or back into a side spot until it has passed.
        self.prefer_yield, self.yield_detour_ratio = prefer_yield, yield_detour_ratio
        self.yield_detour_min, self.yield_max_wait = yield_detour_min, yield_max_wait
        self.route_retries = route_retries           # automatic re-plans after a route the robot could not drive
        self.off_node_dist, self.rejoin_max_dist = off_node_dist, rejoin_max_dist
        # [수정 2026-11-17] 실기기는 정확한 출발 위치에 놓고 시작할 수 없음.
        # auto_home 이면 위치가 잡힌 로봇을 출발 노드(homes)로 한 번 보냄.
        # auto_home_settle: 위치 보고가 이 시간(초) 동안 3 cm 안에 머문 뒤
        # 출발(AMCL 초기 자세가 들어온 직후의 위치 변동을 피함)
        self.auto_home, self.auto_home_settle = auto_home, auto_home_settle
        # Plan versions never repeat across restarts of the Task Manager (a robot may still hold permissions of the
        # previous session): start from the clock, 1024 versions per second of wall time, below 2^30.
        self.pv_base = ((int(time.time()) & 0xFFFFF) << 10) if pv_base is None else pv_base
        self.scheduler = make_scheduler(scheduler)  # 배정기(SCHEDULERS)
        self.scheduler.core = self  # rmf_task 배정기가 코어를 봄
        self.planner = make_planner(planner)  # 경로 계획기(PLANNERS)
        self.robots = {}  # 로봇 id -> Robot
        self.locks = {}                      # node -> robot id
        for rid in robot_ids:                 # any number of AMRs: the home spots come from the layout
            home = self.graph.home_of(rid)
            r = Robot(rid, home, home, plan_version=self.pv_base)
            r.x, r.y = self.graph.nodes[home]
            r.park = home
            # 가상 매장: 홈 노드에서 시작한다고 보고 락을 잡음. 실측 지도는
            # 첫 IDLE 상태 보고 때 가까운 노드를 잡음(on_robot_status)
            if not self.graph.map_id:
                r.held = {home}
                self.locks[home] = rid
            self.robots[rid] = r
        self.tasks = {}  # 임무 id -> Task
        self.seq = 0  # 임무 id 일련번호
        # cooking cell
        self.cook_jobs = []  # 진행 중인 CookJob
        # 조리 자원 -> 잡은 COOK 임무 id(None = 비어 있음)
        self.res_owner = {'ARM_A': None, 'ARM_B': None, 'FRYER': None, 'WOK': None}
        # 음식 받는 곳 -> 놓인 접시 수(SERVE 의 LOADED 때 줄어듦)
        self.slots = {'FRY_PICKUP': 0, 'WOK_PICKUP': 0}
        self.slot_cap = handoff_slots  # 받는 곳 한 곳의 최대 접시 수
        self.doneness = {}                   # cook task id -> (decision, stamp)
        # [수정 2026-11-17] UR-17, 19: 팔이 스스로 보고한 상태
        # (/fleet/arm_status). arm id -> dict(state, job, task_id, error, t)
        self.arm_reports = {}
        self.arm_fault_since = {}            # 조리 팔 id -> 이상 시작 시각
        # 지표(벤치·화면 metrics): 허가 수, 락 대기·계획 대기 시간(초),
        # 재계획·물러남·계획 실패·양보·재배정 횟수, 계획 시간(ms) 등
        self.m = dict(grants=0, blocked_wait=0.0, planned_wait=0.0, replans=0, retreats=0, plan_fail=0,
                      plan_calls=0, plan_ms=0.0, tasks_done=0, stalls=0, flips=0, joint_plans=0, joint_fail=0,
                      reassign=0, yields=0, rejoins=0, route_retries=0)
        self.now = 0.0  # 관제 시계(마지막 tick 의 now)
        # [수정 2026-11-17] T-23: 양보하지 않은 이유(기록용, 판단에는 쓰지 않음)
        self._yield_why = ''
        self._last_tick = None  # 지난 tick 시각(dt 계산)
        self._last_rebalance = 0.0  # 마지막 재배정 비교 시각

    # ------------------------------------------------------------------ algorithms (hot swap)
    def set_scheduler(self, name):
        """배정기를 실행 중에 바꾼다(관리자 SET_SCHEDULER).

        Args:
            name: SCHEDULERS 의 이름(옛 이름 hungarian* 도 받음).

        Raises:
            KeyError: 등록되지 않은 이름(make_scheduler).
        """
        self.scheduler = make_scheduler(name)
        self.scheduler.core = self
        self.io.log('SET_SCHEDULER', result=name)

    def set_planner(self, name):
        """경로 계획기를 바꾸고 진행 중인 경로를 새 계획기로 다시 계획한다.

        Args:
            name: PLANNERS 의 이름.

        Raises:
            KeyError: 등록되지 않은 이름(make_planner).
        """
        self.planner = make_planner(name)
        self.io.log('SET_PLANNER', result=name)
        for r in self.robots.values():        # re-plan running routes with the new algorithm
            if r.route and not r.estop:
                self._start_move(r, r.goal, r.mode, replan=True)

    # ------------------------------------------------------------------ task intake
    # [수정 2026-11-25] I/F 정의서 v0.2 이름: /fms/submit_task ->
    # /frybot/tasks/submit
    # [수정 2026-11-26] I/F v0.3 최종 판 이름(docstring):
    # /frybot/tasks/submit -> /fms/submit_task
    def submit_task(self, type, visit_id=0, order_id=0, item_id=0, table_id=0, menu='', priority=0):
        """새 임무를 접수한다(central_control 의 /fms/submit_task).

        COOK 은 바로 조리 셀에 넣고, 나머지는 PENDING 으로 두어 tick 의
        _schedule 이 배정한다.

        Args:
            type: GUIDE, SERVE, COLLECT, COOK.
            visit_id: 방문 id.
            order_id: 주문 id.
            item_id: 주문 항목 id.
            table_id: 테이블 번호.
            menu: 메뉴 이름(SERVE·COOK).
            priority: 우선순위. 0 이면 PRIORITY 의 기본값.

        Returns:
            새 임무 id.

        Raises:
            ValueError: 서빙 팔 로봇이 없거나, 지도에 필요한 지점이 없거나,
                모르는 임무 종류·COOK 메뉴일 때.
            KeyError: 가상 매장에서 모르는 메뉴의 SERVE.
        """
        # [수정 2026-11-20] 실측 지도에서 무조건 거절하던 것을, 그 임무에
        # 필요한 지점이 지도(roadmap.json 의 stations)에 있으면 받도록 바꿈
        # [수정 2026-11-20] T-47: 서빙 팔이 있는 로봇이 이 관제에 하나도
        # 없으면 SERVE·COLLECT 를 받지 않음(있으면 그 로봇이 빌 때까지 대기)
        if (type in ARM_TASKS and self.serving_robots
                and not self.serving_robots & set(self.robots)):
            raise ValueError(
                f'no robot with a serving arm for {type}: serving_robots='
                f'{sorted(self.serving_robots)}, robots={sorted(self.robots)}')
        if self.graph.map_id:
            missing = self._missing_stations(type, table_id, menu)
            if missing:
                raise ValueError('Restaurant stations are not defined on '
                                 f'this map: {", ".join(missing)}')
        self.seq += 1
        t = Task(f'{type[0]}{self.seq:04d}', type, visit_id, order_id, item_id, table_id, menu,
                 priority or PRIORITY.get(type, 1), self.now)
        self.tasks[t.id] = t
        if type == 'COOK':
            t.state = 'IN_PROGRESS'
            self.cook_jobs.append(CookJob(t, self._recipe(menu)))
        else:
            t.phases = self._program(t)
            t.start_node = self.graph.resolve(t.phases[0][1])
        self.io.log('TASK_SUBMIT', task_id=t.id, visit_id=visit_id, order_id=order_id, result=type, reason=menu)
        return t.id

    # [수정 2026-11-20] 신규: 실측 지도에서 임무를 받을 수 있는지 확인
    def _missing_stations(self, type: str, table_id: int,
                          menu: str) -> list[str]:
        """이 지도에서 임무를 수행하는 데 빠진 것을 돌려준다.

        Args:
            type: 임무 종류(GUIDE, SERVE, COLLECT, COOK).
            table_id: 테이블 번호.
            menu: 메뉴 이름(SERVE 의 음식 받는 곳을 정함).

        Returns:
            지도에 없는 지점 이름의 목록. 모두 있으면 빈 목록. 조리 팔이
            없는 실측 지도의 COOK, 모르는 메뉴의 SERVE 도 빠진 것으로 침.
        """
        if type == 'COOK':
            return ['COOK']
        if type == 'SERVE' and menu not in MENU:
            return [f'menu {menu!r}']
        probe = Task('', type, table_id=table_id, menu=menu)
        return [ph[1] for ph in self._program(probe) if ph[0] == 'move'
                and self.graph.resolve(ph[1]) not in self.graph.nodes]

    def _program(self, t):
        """임무 종류별 단계 목록(phases)을 만든다(지점 이름 사용)."""
        tbl = f'T{t.table_id}:serve'                 # serving / collecting point(s) of the table
        if t.type == 'GUIDE':
            return [('move', 'ENTRANCE', 'NORMAL'), ('event', 'AT_START'), ('move', f'T{t.table_id}:guide', 'GUIDE'),
                    ('event', 'ARRIVED')]
        if t.type == 'SERVE':
            pickup = MENU[t.menu]['pickup']
            return [('move', pickup, 'NORMAL'), ('arm', 'LOAD', 3.0), ('event', 'LOADED'),
                    ('move', tbl, 'NORMAL'), ('arm', 'UNLOAD', 3.0), ('event', 'DELIVERED')]
        if t.type == 'COLLECT':
            return [('move', tbl, 'NORMAL'), ('arm', 'COLLECT_DISHES', 4.0), ('event', 'COLLECTED'),
                    ('move', 'DISH_RETURN', 'NORMAL'), ('arm', 'RETURN_DISHES', 3.0), ('event', 'RETURNED')]
        raise ValueError(t.type)

    # ------------------------------------------------------------------ main loop
    def tick(self, now):
        """관제 한 주기(task_manager_node 는 0.1초마다 부름).

        끊김 판정, 배정, 재계획, 통행 허가, 홈 복귀, 조리 셀을 처리한다.

        Args:
            now: 지금 시각(초). ROS 노드는 time.time(), 모의는 모의 시각.
        """
        dt = 0.0 if self._last_tick is None else now - self._last_tick
        self._last_tick = self.now = now
        # [수정 2026-11-17] A3: 끊김 판정을 지도와 무관하게 함(전에는 실측
        # 지도에서만 해서 가상 매장 시뮬로는 이 경로를 볼 수 없었음). 끊긴
        # 로봇에는 새 허가·재계획·배정을 하지 않고, 오래 끊기면 임무를 보류.
        # 락은 시간으로 풀지 않음(로봇이 어디 있는지 모름)
        for robot in self.robots.values():
            # [수정 2026-11-24] 끊김 판정 2.0 → 1.0 s: 로봇의 fms_timeout
            # (1.0 s)과 같은 기준으로 맞춤. 실기기 확인 필요
            if robot.online and now - robot.last_status > 1.0:
                robot.online, robot.offline_since = False, now
                self.io.log('ROBOT_OFFLINE', robot_id=robot.id,
                            zone_id=robot.node, result='FAIL',
                            task_id=robot.task.id if robot.task else '')
            task = robot.task
            if not robot.online and robot.offline_since is not None \
                    and now - robot.offline_since > self.offline_hold \
                    and task and task.state == 'IN_PROGRESS':
                self._suspend(task, 'OFFLINE')
        self._schedule()  # 대기 임무 배정·재배정
        for r in self.robots.values():
            # 재계획 요청: 보류 임무·양보 대기 중이 아니면 다시 계획하고,
            # 실패하면 서 있는 로봇은 물러섬
            held_task = bool(r.task and r.task.state == 'SUSPENDED')
            if r.needs_replan and r.online and not held_task \
                    and not (r.pending_goal and not r.route and not self._yield_done(r)):
                r.needs_replan = False
                if (r.route or r.pending_goal) and not r.estop:
                    g, mode = (r.pending_goal[0], r.pending_goal[1]) if r.pending_goal else (r.goal, r.mode)
                    standing = not r.heading
                    # [수정 2026-11-17] T-26: 돌아가기를 포기한 로봇은 물러서지 않음
                    if not self._start_move(r, g, mode, replan=True, allow_flip=False) and standing \
                            and (r.task or not self.graph.map_id):
                        self._retreat(r, None, goal=g, mode=mode)
            self._drive(r, dt)  # 통행 허가(교통 계층)
            # 가상 매장: 임무 없이 서 있는 로봇은 충전대·대기 위치로
            if not self.graph.map_id and r.online and r.task is None and not r.route and not r.pending_goal and not r.estop and not r.heading:
                if r.node != r.home and r.battery < self.standby_min_battery:
                    self._go_home(r, force_home=True)          # standby robot running low: go and charge
                elif r.node != r.park and not r.arm_busy:
                    self._go_home(r)                           # left somewhere (e.g. after stepping aside): go and park
            # [수정 2026-11-20] T-45: 실측 지도 홈 복귀가 막혔으면 다시 시도
            if (self.graph.map_id and r.returning and r.online
                    and r.task is None and not r.route
                    and not r.pending_goal and not r.estop and not r.heading
                    and r.node != r.park and now >= r.return_retry):
                r.return_retry = now + 3.0
                self._start_move(r, r.park, 'NORMAL')
            # [수정 2026-11-17] 실측 지도: 기동 후 출발 노드로 자동 이동
            self._auto_home(r)
            # [수정 2026-11-17] UR-19: 이상이 시작된 시각 기록
            self._note_faults(r)
        self._cook_tick()  # 조리 셀 진행

    # ------------------------------------------------------------------ scheduling
    # [수정 2026-11-17] G2: 로봇이나 서빙 팔이 오류를 보고 중이면 새 임무를
    # 주지 않음(전에는 DRIVE_ERROR 가 있어도 안내·서빙을 배정했음)
    def _available(self, r):
        """새 임무를 자동 배정할 수 있는 로봇인지."""
        return (r.online and not r.estop and r.task is None and not r.arm_busy and r.battery >= self.min_battery
                and not self._fault(r))

    # [수정 2026-11-17] 신규 (G2)
    def _fault(self, r: Robot) -> str:
        """로봇이 보고 중인 오류 이름을 돌려준다 ('' = 없음).

        로봇의 RobotStatus.error 를 먼저 보고, 없으면 서빙 팔의 마지막
        보고를 본다. 팔의 오류는 보고가 끊겨도 남고, 정상 보고가 와야
        풀린다.
        """
        if r.error:
            return r.error
        arm = self.arm_reports.get(r.id)
        return 'ARM_ERROR' if arm and arm['error'] else ''

    # [수정 2026-11-17] 신규 (G2): 관리자의 이동 명령은 자동 배정과 조건을
    # 나눔. 주행 실패(DRIVE_ERROR)는 다음 구간을 성공해야 풀리므로, 관리자가
    # 노드로 되돌리는 이동은 받음. 통신·위치·팔 오류는 받지 않음
    def _movable(self, r: Robot) -> bool:
        """관리자의 이동·홈 복귀 명령을 받을 수 있는 로봇인지."""
        arm = self.arm_reports.get(r.id)
        return (r.online and not r.estop and r.task is None
                and not r.arm_busy and r.battery >= self.min_battery
                and r.error in ('', 'DRIVE_ERROR')
                and not (arm and arm['error']))

    # [수정 2026-11-20] T-52: 신규. 이동 명령을 받을 수 없는 이유
    def _unmovable_reason(self, r: Robot) -> str:
        """관리자 이동 명령을 받을 수 없는 첫 번째 이유('' = 받을 수 있음).

        Args:
            r: 로봇.

        Returns:
            사람이 읽을 이유 문자열.
        """
        arm = self.arm_reports.get(r.id)
        checks = (
            (not r.online, '관제와 연결 끊김(상태 보고 2초 넘게 없음)'),
            (r.estop, '비상 정지 중(RESUME 필요)'),
            (r.task is not None,
             f'임무 {r.task.id if r.task else ""} 수행 중'),
            (bool(r.arm_busy), f'팔 작업 {r.arm_busy} 중'),
            (r.battery < self.min_battery,
             f'배터리 {r.battery:.0f}% < {self.min_battery:.0f}%'),
            (r.error not in ('', 'DRIVE_ERROR'), f'로봇 오류 {r.error}'),
            (bool(arm and arm['error']),
             f'서빙 팔 오류 {arm["error"] if arm else ""}'),
            (bool(r.route), '경로 실행 중'),
            (bool(r.pending_goal), '비켜 준 뒤 복귀 대기 중'),
            (r.reported_state != 'IDLE',
             f'로봇 보고 상태 {r.reported_state or "(없음)"}'))
        return next((text for bad, text in checks if bad), '')

    def _cost_fn(self):
        """Seconds until a robot can be at the task's first stop. ETA schedulers ask the path planner, so waiting for
        aisle reservations of other robots (and a busy pick-up point) is included."""
        cache = {}

        def static(r, t):
            """그래프 최단 거리 기준 이동 시간(초, 구간 지연 포함)."""
            src = r.heading or r.node
            cost = self.graph.shortest_dist(src, t.start_node) / self.speed
            # [수정 2026-11-18] W6: 최단 경로의 구간 수 x 구간 지연
            if self.plan_overhead:
                hops = len(self._shortest_path(src, t.start_node)) - 1
                cost += max(0, hops) * self.plan_overhead
            return cost

        def eta(r, t):
            """계획기의 도착 예상 시간(초). (로봇, 지점)별로 한 번만 계산.

            조율 계획기가 아니면 static, 계획에 실패하면 static 의 3배.
            """
            k = (r.id, t.start_node)
            if k not in cache:
                # [수정 2026-11-18] W6: 구간 지연(overhead) 추가
                req = PlanRequest(r.id, r.heading or r.node, t.start_node, self.now, self.speed * self.plan_speed_factor,
                                  goal_hold=4.0, overhead=self.plan_overhead)
                steps = self.planner.plan(self.graph, req, self._table(r)) if self.planner.coordinated else None
                cache[k] = (steps[-1].arrive - self.now) if steps else static(r, t) * (1.0 if steps is None and not
                                                                                     self.planner.coordinated else 3.0)
            return cache[k]
        fn = eta if self.scheduler.uses_eta else static  # ETA 배정기면 eta
        # [수정 2026-11-20] T-47: 팔 없는 로봇의 SERVE·COLLECT 는 큰 비용
        if not self.serving_robots:
            return fn
        return lambda r, t: fn(r, t) + (0.0 if self._can_take(r, t)
                                        else NO_ARM_COST)

    # [수정 2026-11-20] T-47: 신규
    def _can_take(self, r: Robot, t: Task) -> bool:
        """로봇 r 이 임무 t 를 맡을 수 있는지(서빙 팔 조건)를 돌려준다.

        Args:
            r: 로봇.
            t: 임무.

        Returns:
            serving_robots 가 비었거나, 팔이 필요 없는 임무이거나, r 이
            serving_robots 에 있으면 True.
        """
        return (not self.serving_robots or t.type not in ARM_TASKS
                or r.id in self.serving_robots)

    def _assign(self, t, r):
        """임무 t 를 로봇 r 에 배정하고 첫 단계를 시작한다."""
        t.robot_id, t.state, t.assigned_at, t.pi = r.id, 'IN_PROGRESS', self.now, 0
        r.task, r.returning = t, False
        self.io.log('TASK_ASSIGN', task_id=t.id, robot_id=r.id, visit_id=t.visit_id, order_id=t.order_id,
                    result=self.scheduler.name, reason=f'wait={self.now - t.created:.1f}')
        self._event(t, 'ASSIGNED')
        self._run_phase(r)

    def _schedule(self):
        """대기 임무를 빈 로봇에 배정한다.

        롤링 호라이즌 배정기(rebalance)면 아직 첫 지점에 닿지 않은 임무를
        주기마다 다시 비교해, 비용 합이 rebalance_gain 넘게 줄면 다른
        로봇으로 넘긴다.
        """
        pend = [t for t in self.tasks.values() if t.state == 'PENDING' and t.type in AMR_TASKS]
        free = [r for r in self.robots.values() if self._available(r)]
        cost = self._cost_fn()
        if self.scheduler.rebalance and self.now - self._last_rebalance >= self.scheduler.rebalance_period:
            self._last_rebalance = self.now
            # not started = still driving to the first stop (no guest picked up, nothing loaded)
            # A task may change hands at most twice, and not within 6 s of its last assignment: otherwise two robots
            # can keep handing the same task to each other (each turns round, which flips the ETA comparison again).
            open_ = [t for t in self.tasks.values() if t.state == 'IN_PROGRESS' and t.type in AMR_TASKS and t.pi == 0
                     and not t.carrying and not self.robots[t.robot_id].estop
                     # [수정 2026-11-17] A3, G2: 끊겼거나 오류를 보고 중인
                     # 로봇의 임무는 재배정 비교에 넣지 않음
                     and self.robots[t.robot_id].online
                     and not self._fault(self.robots[t.robot_id])
                     and t.rebalanced < 2 and self.now - t.assigned_at >= 6.0]
            if open_:
                robots = free + [self.robots[t.robot_id] for t in open_]
                # a robot that is released again plans from where it is now
                pairs = self.scheduler.assign(pend + open_, robots, cost, self.now)
                new = {t.id: r for t, r in pairs}
                # 비교한 임무가 모두 다시 짝지어졌을 때만 비용 감소(gain)를 봄
                if all(t.id in new for t in open_):
                    gain = sum(cost(self.robots[t.robot_id], t) - cost(new[t.id], t) for t in open_)
                    moved = [t for t in open_ if new[t.id].id != t.robot_id]
                    # [수정 2026-11-20] T-47: 팔 없는 로봇으로는 넘기지 않음
                    if (moved and gain > self.scheduler.rebalance_gain
                            and all(self._can_take(new[t.id], t)
                                    for t in moved)):
                        for t in moved:
                            old = self.robots[t.robot_id]
                            old.task = None
                            t.robot_id, t.state = '', 'PENDING'
                            t.rebalanced += 1
                            self.m['reassign'] += 1
                            self.io.log('TASK_REBALANCE', task_id=t.id, robot_id=old.id, result=new[t.id].id,
                                        reason=f'gain={gain:.1f}')
                        for t in moved:
                            self._assign(t, new[t.id])
                        for o in robots:                       # released robots without a new task go and park
                            if o.task is None and not o.estop and all(o is not new[t.id] for t in moved):
                                if o.route and not o.returning:
                                    self._go_home(o)
                        pend = [t for t in self.tasks.values() if t.state == 'PENDING' and t.type in AMR_TASKS]
                        free = [r for r in self.robots.values() if self._available(r)]
                        cost = self._cost_fn()
        # 남은 대기 임무를 빈 로봇에 배정
        if not pend or not free:
            return
        for t, r in self.scheduler.assign(pend, free, cost, self.now):
            # [수정 2026-11-20] T-47: 팔 없는 로봇과 짝지어진 임무는 대기
            if self._can_take(r, t):
                self._assign(t, r)

    # ------------------------------------------------------------------ task programs
    def _run_phase(self, r):
        """로봇 r 의 임무를 진행할 수 있는 데까지 진행한다.

        event 단계는 바로 처리하고, move 는 경로를 계획한 뒤, arm 은 팔
        작업을 보낸 뒤 돌아온다(끝나면 _arrived·on_arm_result 가 다시
        부름). 단계를 모두 마치면 임무를 DONE 으로 하고 복귀시킨다.
        """
        t = r.task
        while t and t.state == 'IN_PROGRESS':
            if t.pi >= len(t.phases):
                t.state, t.finished_at = 'DONE', self.now
                self.m['tasks_done'] += 1
                self._event(t, 'DONE')
                self.io.log('TASK_DONE', task_id=t.id, robot_id=r.id, visit_id=t.visit_id, order_id=t.order_id,
                            result='OK', reason=f'dur={t.finished_at - t.created:.1f}')
                r.task = None
                # [수정 2026-11-20] T-45: 실측 지도에서도 임무를 마치면 자기 홈
                # (roadmap.json homes)으로 돌아감. 관리자 이동 명령(MOVE)은 그
                # 자리에 남음. 가상 매장은 그대로 _go_home
                if self.graph.map_id and t.type != 'MOVE':
                    self._return_home(r, t.id)
                else:
                    self._go_home(r)
                return
            ph = t.phases[t.pi]
            if ph[0] == 'event':  # 상태 이벤트: 화물 표시 갱신
                if ph[1] == 'LOADED':
                    t.carrying = True
                    # 받는 곳에서 접시를 집음: 그곳의 접시 수를 줄임
                    self.slots[MENU[t.menu]['pickup']] = max(0, self.slots[MENU[t.menu]['pickup']] - 1)
                if ph[1] in ('DELIVERED', 'RETURNED'):
                    t.carrying = False
                if ph[1] == 'COLLECTED':
                    t.carrying = True
                self._event(t, ph[1])
                t.pi += 1
                continue
            if ph[0] == 'move':  # 이동: 목적 노드까지 계획
                if len(self.graph.table_nodes.get(ph[1], ())) > 1:      # table reachable from several sides
                    ph = t.phases[t.pi] = ('move', self._table_side(r, ph[1]), ph[2])
                goal = self.graph.resolve(ph[1])
                self._rejoin(r)                   # not standing on a node: drive back onto the roadmap first
                if r.node == goal and not r.heading:
                    # Already standing on the goal. A route may still be active (e.g. the robot was on its way home
                    # and got this task while passing the node): drop it instead of planning a one-node route, whose
                    # arrival is never reported (progress only counts indices above the current one).
                    if r.route:
                        self._stop_route(r)
                    r.returning, r.pending_goal = False, None
                    t.pi += 1
                    continue
                self._start_move(r, goal, ph[2])
                return
            if ph[0] == 'arm':                    # only after the stop at the node is confirmed (no route active)
                r.arm_busy, r.arm_until = ph[1], self.now + ph[2]
                self.io.arm_job(r.id, t.id, ph[1], ph[2], {'table_id': t.table_id, 'menu': t.menu})
                self.io.log('ARM_START', task_id=t.id, robot_id=r.id, zone_id=r.node, result=ph[1])
                return

    def _table_side(self, r, table):
        """Service node of a table that can be approached from several sides: the nearest one for this robot, with a
        penalty when another robot stands on it / is heading for it. The choice is kept for the rest of the move."""
        src = r.heading or r.node

        # 노드 n 의 비용: 최단 거리(m) + 다른 로봇이 서 있거나 향하면 0.6
        def cost(n):
            busy = any(o.id != r.id and (o.goal == n and (o.route or o.pending_goal) or o.node == n)
                       for o in self.robots.values())
            return self.graph.shortest_dist(src, n) + (0.6 if busy else 0.0)
        return min(self.graph.table_nodes[table], key=cost)

    def _park_goal(self, r, force_home=False):
        """Where an idle robot waits. Chargers sit next to the entrance (guiding); the standby spots sit next to the
        cook zone (serving). Keep one robot on the entrance side, send the others to a free standby spot."""
        others = [o for o in self.robots.values() if o.id != r.id and not o.estop]
        if r.battery < self.standby_min_battery and r.home not in self.graph.home_nodes:
            # an AMR without its own charger borrows a free one (nobody parked on it or heading for it)
            used = {o.park for o in others} | {o.node for o in others}
            # [수정 2026-11-18] W8-1: 거리가 같을 때 집합 순서로 고르지
            # 않게 정렬
            free = [n for n in sorted(self.graph.home_nodes)
                    if n not in used and self._blocker(n, r.id) is None]
            if free:
                return min(free, key=lambda n: self.graph.shortest_dist(r.heading or r.node, n))
        if force_home or not self.use_standby or r.battery < self.standby_min_battery:
            return r.home
        entrance_side = sum(1 for o in others if o.task is None and (o.park or o.node) in self.graph.home_nodes)
        if entrance_side < 1:
            return r.home
        taken = {o.park for o in others if o.task is None} | {o.node for o in others if o.task is None}
        free = [n for n in self.graph.standby_nodes if n not in taken and self._blocker(n, r.id) is None]
        if not free:
            return r.home
        return min(free, key=lambda n: self.graph.shortest_dist(r.heading or r.node, n))

    # [수정 2026-11-17] 신규: 기동 후 출발 노드(대기 위치) 자동 이동
    def _auto_home(self, r: Robot) -> None:
        """위치가 잡힌 로봇을 자기 출발 노드로 한 번 보냄(실측 지도).

        로봇을 정확한 노드 위에 놓고 시작할 수 없으므로, 처음 온라인이 된
        로봇이 서 있는 곳에서 출발 노드(roadmap.json 의 homes)까지 이동
        명령(MOVE_TO_VERTEX)과 같은 경로로 보냄. 노드 밖에 있으면 가장
        가까운 빈 노드로 먼저 들어감(_rejoin). 로봇마다 관제 실행당 한 번만
        하고, 그 전에 운영자가 임무를 주거나 비상 정지를 걸면 하지 않음.

        Args:
            r: 대상 로봇.
        """
        if r.homed or not self.auto_home or not self.graph.map_id \
                or not r.online:
            return
        if r.task or r.estop:
            r.homed = True                 # 운영자가 먼저 개입: 맡김
            self.io.log('AUTO_HOME', robot_id=r.id, zone_id=r.home,
                        result='SKIP',
                        reason='estop' if r.estop else 'operator task')
            return
        if r.route or r.pending_goal or self.now < r.home_retry \
                or self.now - r.still_since < self.auto_home_settle:
            return
        off = math.dist((r.x, r.y), self.graph.nodes[r.home])
        if off <= self.off_node_dist:
            r.homed = True
            self.io.log('AUTO_HOME', robot_id=r.id, zone_id=r.home,
                        result='AT_HOME', reason=f'off={off:.2f}m')
            return
        ok, message = self._move_to_vertex(r.id, r.home)
        if ok:
            r.homed = True
            self.io.log('AUTO_HOME', robot_id=r.id, zone_id=r.home,
                        result='OK', reason=message)
            return
        r.home_retry = self.now + 3.0      # 막혀 있으면 3초 뒤 다시 시도
        if message != r.home_note:
            r.home_note = message
            self.io.log('AUTO_HOME', robot_id=r.id, zone_id=r.home,
                        result='WAIT', reason=message)

    # [수정 2026-11-20] T-45: 신규
    def _return_home(self, r: Robot, task_id: str = '') -> None:
        """실측 지도: 임무를 마친 로봇을 자기 홈 노드로 보낸다.

        가상 매장의 _go_home 처럼 임무 없이 복귀(returning)하므로, 복귀 중에도
        새 임무를 받으면 그 임무로 바뀐다(_assign). 길이 막혀 계획이 안 되면
        tick 이 3초마다 다시 시도한다.

        Args:
            r: 임무를 마친 로봇.
            task_id: 방금 마친 임무(기록용).
        """
        if r.estop or (r.node == r.home and not r.heading):
            return
        r.park, r.returning = r.home, True
        r.return_retry = self.now + 3.0
        self.io.log('RETURN_HOME', robot_id=r.id, task_id=task_id,
                    zone_id=r.home)
        self._start_move(r, r.home, 'NORMAL')

    def _go_home(self, r, force_home=False):
        """가상 매장: 임무 없는 로봇을 대기 자리(_park_goal)로 보낸다.

        실측 지도에서는 아무것도 하지 않음(임무 뒤 복귀는 _return_home).

        Args:
            r: 로봇.
            force_home: 대기 위치 대신 자기 홈(충전대)으로.
        """
        if self.graph.map_id:
            return
        goal = self._park_goal(r, force_home)
        r.park = goal
        if r.node == goal and not r.heading:
            return
        r.returning = True
        self._start_move(r, goal, 'NORMAL')

    # [수정 2026-11-25] I/F 정의서 v0.2 이름: TaskEvent -> TaskProgress
    # [수정 2026-11-26] I/F v0.3 최종 판 이름(docstring):
    # TaskProgress -> TaskEvent
    def _event(self, t, state, reason=''):
        """임무 상태 이벤트(TaskEvent)를 낸다. reason 이 비면 t.reason."""
        self.io.task_event(dict(task_id=t.id, task_type=t.type, state=state, robot_id=t.robot_id, visit_id=t.visit_id,
                                order_id=t.order_id, item_id=t.item_id, table_id=t.table_id,
                                plan_version=self.robots[t.robot_id].plan_version if t.robot_id in self.robots else 0,
                                reason=reason or t.reason))

    # ------------------------------------------------------------------ planning
    def _table(self, me, optimistic=False, exclude=()):
        """Reservations of all other robots. optimistic=True ignores their future plans (only what they occupy now):
        used when `me` cannot find a plan, so that `me` goes first and the others re-plan around it."""
        tb = ReservationTable(conflict=self.graph.conflict)
        for o in self.robots.values():
            if o.id == me.id or o.id in exclude:
                continue
            # 낙관: 움직이는 로봇은 지금 잡은 노드만 5초 점유로 봄
            if optimistic and (o.route or o.pending_goal) and not o.estop:
                for n in o.held:
                    tb.add(n, self.now, self.now + 5.0, o.id)
                    tb.itineraries.append([(n, self.now), (n, self.now + 5.0)])
            # 시각이 있는 계획: 남은 계획 + 지금 점유(1.5초) + 이동 궤적
            # (itineraries, 궤적 기반 계획기용)
            elif o.route and self.planner.coordinated and o.route[0].arrive > 0:
                rem = o.route[max(o.idx, 0):]
                hold = self._hold_estimate(o, at_goal=True)
                tb.add_plan(o.id, rem, last_hold=hold)
                for n in o.held:                       # what it physically occupies right now
                    tb.add(n, self.now, self.now + 1.5, o.id)
                pts = [(rem[0].node, min(self.now, rem[0].depart))]
                for i, st in enumerate(rem):
                    if i:
                        pts.append((st.node, st.arrive))
                    pts.append((st.node, st.depart if i + 1 < len(rem) else st.arrive + hold))
                tb.itineraries.append(pts)
            # 그 밖: 잡은 노드를 머무는 예상 시간만큼 점유
            else:
                hold = self._hold_estimate(o)
                for n in o.held:
                    tb.add(n, self.now, self.now + hold, o.id)
                    tb.itineraries.append([(n, self.now), (n, self.now + hold)])
            # [수정 2026-11-20] T-48·T-52: 노드에서 벗어나 서 있는 로봇은 보고
            # 위치에서 pos_block_dist(기본 0.12 m) 안의 노드도 점유(서 있는
            # 동안). 계획이 그 노드를 지나게 세우면 허가 단계에서 막혀 정체가
            # 되므로 미리 피함
            if self._stray(o):
                hold = self._hold_estimate(o) if not o.route else 1.5
                for n, xy in self.graph.nodes.items():
                    # [수정 2026-11-20] T-52: 허가와 같은 거리 기준
                    if math.dist(xy, (o.x, o.y)) < self.pos_block_dist:
                        tb.add(n, self.now, self.now + hold, o.id)
        return tb

    def _hold_estimate(self, o, at_goal=False):
        """로봇 o 가 지금 자리(at_goal 이면 목적지 도착 뒤)에 머물 시간(초).

        INF 는 계속 머묾(비상 정지, 주차, 복귀, MOVE 의 마지막 이동).
        다음 단계가 팔 작업이면 그 시간 + 2초.
        """
        if o.estop:
            return INF
        if at_goal:
            if o.returning:
                return INF
            t = o.task
            if t and t.pi + 1 < len(t.phases) and t.phases[t.pi + 1][0] == 'arm':
                return t.phases[t.pi + 1][2] + 2.0
            # [수정 2026-11-18] W8-2: 이동 명령(MOVE)처럼 지금 이동이 임무의
            # 마지막 단계면 도착 뒤 그 자리에 계속 섬. 4초 뒤 빈다고 예약하면
            # 뒤 로봇이 막다른 자리까지 들어와 둘 다 멈췄음(W5)
            if t and t.type == 'MOVE' and t.pi + 1 >= len(t.phases):
                return INF
            return 4.0
        if o.arm_busy:
            return max(1.0, o.arm_until - self.now) + 2.0
        if o.task is None and not o.route and not o.pending_goal:
            return INF                               # parked
        return 4.0

    def _start_move(self, r, goal, mode, replan=False, blocked=frozenset(), allow_flip=True):
        """로봇 r 의 goal 까지 경로를 계획해 채택한다.

        순서: 함께 계획(CCBS) -> 방금 못 간 노드 피하기 -> 기본 계획 ->
        길을 막은 유휴 로봇 비키기 -> 우회 대신 양보 -> 우선순위 뒤집기.
        실패하면 pending_goal 로 1초 뒤 다시 시도한다.

        Args:
            r: 로봇.
            goal: 목적 지점(노드 또는 지점 이름).
            mode: NORMAL, GUIDE, YIELD.
            replan: 진행 중 경로의 재계획(기록 REPLAN, _adopt 참고).
            blocked: 계획에서 뺄 노드(조율하지 않는 재계획).
            allow_flip: 함께 계획·우선순위 뒤집기 허용.

        Returns:
            경로를 채택했거나 비켜 서기를 시작했으면 True.
        """
        goal = self.graph.resolve(goal)
        self._rejoin(r)
        r.yield_note = ''
        self._yield_why = ''
        start = r.heading or r.node
        # plan a little slower than the robots drive, so small execution delays do not flip the planned order
        speed = (self.guide_speed if mode == 'GUIDE' else self.speed) * self.plan_speed_factor
        # [수정 2026-11-18] W6: 구간 중간이면 남은 시간을 (지연 + 거리 / 속도)의
        # 절반으로, 노드로 돌아가는 길도 한 구간(지연 포함)으로 봄
        ov = self.plan_overhead
        t0 = self.now
        if r.heading:
            seg = ov + self.graph.dist(r.node, r.heading) / speed
            t0 += seg * 0.5
        if r.heading and r.heading == r.node:        # driving back onto the roadmap from somewhere off it
            back = math.dist((r.x, r.y), self.graph.nodes[r.node])
            t0 += ov + back / speed
        # 목적지 도착 뒤 점유: park 로 복귀면 계속, 아니면 5초
        hold = INF if (r.returning and goal == r.park) else 5.0
        req = PlanRequest(r.id, start, goal, t0, speed, goal_hold=hold,
                          blocked=blocked, overhead=ov)
        c0 = time.perf_counter()  # 계획 시간(plan_ms) 측정
        steps = None
        # 함께 계획하는 계획기(CCBS): 움직이는 다른 로봇과 함께 계획
        if self.planner.joint and allow_flip and not blocked:
            steps = self._plan_joint(r, req, goal, mode)
        if steps is None and not blocked and r.avoid_node and self.now < r.avoid_until \
                and r.avoid_node not in (goal, start):
            # the robot just failed to reach this node (obstacle, Nav2 gave up): look for a way round it first
            steps = self.planner.plan(self.graph, PlanRequest(r.id, start, goal, t0, speed, goal_hold=hold,
                                                              blocked=frozenset({r.avoid_node})), self._table(r))
        # 기본: 다른 로봇의 예약을 피해 계획
        if steps is None:
            steps = self.planner.plan(self.graph, req, self._table(r))
        # [수정 2026-11-17] T-26: 비켜 준 뒤 원래 노드로 돌아가는 로봇(실측
        # 지도에서 임무 없이 움직이는 로봇)은 다른 로봇을 비키게 하거나
        # 우선순위를 뒤집지 않음. 그러면 서로 끝없이 자리를 바꿈
        quiet = bool(self.graph.map_id) and r.task is None and mode != 'YIELD'
        # 먼 우회이거나 계획이 없으면 길을 막은 유휴 로봇을 비키고 다시 계획
        if self.prefer_yield and self.planner.coordinated and not blocked and mode != 'YIELD' and not quiet \
                and (steps is None or self._long_way(steps, start, goal)) and self._make_way(r, start, goal):
            # an idle robot stood in the way and is stepping aside now: plan again, the short way is opening up
            steps = self.planner.plan(self.graph, req, self._table(r)) or steps
        # 우회 대신 기다리거나 물러서기(_yield_instead)
        if steps is not None and self.prefer_yield and self.planner.coordinated and not self.planner.joint \
                and not blocked and not r.heading and mode != 'YIELD' and not quiet:
            alt = self._yield_instead(r, req, steps, goal, mode)
            if alt == 'RETREAT':                      # stepped aside; the move continues from the side spot
                self.m['plan_calls'] += 1
                self.m['plan_ms'] += (time.perf_counter() - c0) * 1000.0
                return True
            steps = alt or steps
        # [수정 2026-11-17] T-24: 마주 본 두 로봇이 1초마다 서로 뒤집어
        # 아무도 출발하지 못했음. 뒤집힌 쪽은 FLIP_HOLD 동안 되뒤집지 못함
        if steps is None and self.planner.coordinated and allow_flip \
                and not quiet and self.now >= r.no_flip_until:
            steps = self.planner.plan(
                self.graph, req, self._table(r, optimistic=True))
            # priority flip: the others must now plan around us
            if steps is not None:
                self.m['flips'] += 1
                for o in self.robots.values():
                    if o.id != r.id and (o.route or o.pending_goal) and not o.estop:
                        o.needs_replan = True
                        o.no_flip_until = self.now + FLIP_HOLD
        self.m['plan_calls'] += 1
        self.m['plan_ms'] += (time.perf_counter() - c0) * 1000.0
        r.goal, r.mode = goal, mode
        if steps is None and quiet:  # 임무 없는 복귀가 막힘
            if r.heading and r.route:
                # 구간을 달리는 중: 허가받은 노드까지만 가서 다시 판단함.
                # 구간 중간에 서면 다른 로봇이 비켜 달라고 할 수 없음
                r.route = r.route[:max(r.granted, r.idx) + 1]
                r.pending_goal = (goal, mode, self.now + 1.0)
                return False
            # 돌아갈 길이 막혀 있음: 다시 시도하지 않고 지금 노드에 남음
            r.pending_goal = None
            r.yield_to = r.yield_from = ''
            self.io.log('YIELD_STAY', robot_id=r.id, zone_id=goal,
                        reason=f'no_way_back at={r.node}')
            self._stop_route(r)
            return False
        if steps is None:  # 계획 실패: 1초 뒤 다시 시도
            self.m['plan_fail'] += 1
            r.pending_goal = (goal, mode, self.now + 1.0)
            self.io.log('PLAN_FAIL', robot_id=r.id, task_id=r.task.id if r.task else '', zone_id=goal,
                        result=self.planner.name)
            if r.route:                               # keep standing where we are
                self._stop_route(r)
            self._plan_fail_watch(r, goal)
            return False
        # [수정 2026-11-18] W8-3: 계획 성공이면 실패 묶음을 지움
        r.plan_fail = None
        # [수정 2026-11-17] T-23: 계획에 든 대기와 양보하지 않은 이유를 기록
        self._log_plan_notes(r, steps, start, goal, mode, blocked)
        self._adopt(r, steps, goal, mode, replan)
        return True

    # [수정 2026-11-17] T-23: 실기기에서 양보처럼 보인 동작(계획 대기,
    # 우회)이 로그에 남지 않았음. 기록만 추가하고 판단은 바꾸지 않음
    def _user_of(self, r: Robot, nodes) -> str:
        """다른 로봇 중 `nodes`(와 너무 가까운 노드)를 쓰는 첫 로봇의 id.

        Args:
            r: 기준 로봇.
            nodes: 확인할 노드들.

        Returns:
            로봇 id. 없으면 ''.
        """
        region = set(nodes)
        for n in list(region):
            region |= self.graph.conflict[n]
        for o in self.robots.values():
            if o.id == r.id:
                continue
            used = set(o.held)
            if o.route:
                used |= {st.node for st in o.route[max(o.idx, 0):]}
            if used & region:
                return o.id
        return ''

    def _log_plan_notes(self, r: Robot, steps: list, start: str, goal: str,
                        mode: str, blocked: frozenset) -> None:
        """채택한 계획의 대기(PLAN_WAIT)와 우회 이유(YIELD_SKIP)를 기록함.

        Args:
            r: 계획을 받은 로봇.
            steps: 채택한 계획.
            start: 출발 노드.
            goal: 목적 노드.
            mode: 주행 모드.
            blocked: 계획에서 뺀 노드(조율하지 않는 재계획).
        """
        if len(steps) < 2 or mode == 'YIELD':
            return
        task_id = r.task.id if r.task else ''
        if self.planner.coordinated and steps[0].arrive > 0:
            waits = [(i, s.depart - s.arrive) for i, s in enumerate(steps[:-1])
                     if s.depart - s.arrive > 1.0]
            if waits:
                i, wait = waits[0]
                who = self._user_of(r, [steps[i + 1].node])
                key = (goal, steps[i].node, who)
                if key != r.wait_note:
                    r.wait_note = key
                    self.io.log(
                        'PLAN_WAIT', robot_id=r.id, task_id=task_id,
                        zone_id=steps[i].node,
                        reason=f'wait={wait:.1f}s for={who or "?"} '
                               f'next={steps[i + 1].node} '
                               f'total={sum(w for _, w in waits):.1f}s')
        short = self.graph.shortest_dist(start, goal)
        # [수정 2026-11-20] D-05: 경로 길이 합을 _plan_length 하나로 모음
        length = self._plan_length(steps)
        if length <= short + 0.05:
            return
        limit = max(short * self.yield_detour_ratio,
                    short + self.yield_detour_min)
        if blocked:
            why = 'uncoordinated_replan'
        elif not self.prefer_yield:
            why = 'prefer_yield_off'
        elif not self.planner.coordinated or self.planner.joint:
            why = 'planner_without_yield'
        elif length <= limit:
            why = 'below_threshold'
        elif r.heading:
            why = 'robot_between_nodes'
        else:
            why = self._yield_why or 'no_side_spot'
        who = self._user_of(r, self._shortest_path(start, goal))
        key = (goal, why, who)
        if key != r.skip_note:
            r.skip_note = key
            self.io.log(
                'YIELD_SKIP', robot_id=r.id, task_id=task_id, zone_id=goal,
                reason=f'{why} by={who or "?"} detour={length:.2f}m '
                       f'short={short:.2f}m limit={limit:.2f}m')

    # ------------------------------------------------------------------ exception handling: robot off the roadmap
    def _rejoin(self, r, avoid=()):
        """A standing robot that is not on a roadmap node (Nav2 gave up between two nodes, somebody moved it, the
        localisation jumped) gets the nearest free node as the start of its next route: `heading` is set to that
        node, so the route starts there, the robot drives to it first and only then asks for permissions.
        `avoid`: nodes not to pick (the node it just failed to reach). Returns True when a node was chosen."""
        if not r.online or r.route:
            return False
        pos = (r.x, r.y)
        pool = None
        if r.heading:
            if r.heading == r.node and r.node not in avoid:
                return False                              # already on its way back onto the roadmap
            if not avoid:
                return False                              # between two nodes: carry on to the one ahead (as before)
            pool = [n for n in (r.node, r.heading) if n not in avoid]
        elif math.dist(pos, self.graph.nodes[r.node]) <= self.off_node_dist:
            return False

        # 피할 노드가 아니고 다른 로봇이 막지 않은 노드만 남김
        def free(nodes):
            return [n for n in nodes if n not in avoid and self._blocker(n, r.id) is None]
        cands = free(pool) if pool else []
        if not cands:
            cands = free(self.graph.nodes)
        if not cands:
            return False
        n = min(cands, key=lambda k: math.dist(pos, self.graph.nodes[k]))
        d = math.dist(pos, self.graph.nodes[n])
        if d > self.rejoin_max_dist:
            return False
        # keep the locks of nodes the body still overlaps; they are released when the robot reports the new node
        keep = {k for k in r.held if math.dist(pos, self.graph.nodes[k]) < SAFE_DIST}
        for k in r.held - keep - {n}:
            if self.locks.get(k) == r.id:
                del self.locks[k]
        r.held = keep | {n}
        self.locks[n] = r.id
        r.node = r.heading = n
        self.m['rejoins'] += 1
        self.io.log('REJOIN', robot_id=r.id, zone_id=n, task_id=r.task.id if r.task else '', reason=f'off_node={d:.2f}m')
        return True

    # ------------------------------------------------------------------ yielding instead of a long way round
    def _shortest_path(self, a, b):
        """빈 로드맵에서 a 부터 b 까지의 최단 경로 노드 목록(점유 무시)."""
        h = self.graph.sp_from(b)
        path = [a]
        while path[-1] != b and path[-1] in h and len(path) <= len(self.graph.nodes):
            path.append(min(self.graph.adj[path[-1]], key=lambda e: e[1] + h.get(e[0], 1e18))[0])
        return path

    # [수정 2026-11-20] D-05: 같은 계산이 세 곳에 있어 한 메서드로 모음
    def _plan_length(self, steps):
        """경로의 통로 길이 합(m). 같은 노드에 머무는 대기 스텝은 0."""
        return sum(self.graph.dist(a.node, b.node)
                   for a, b in zip(steps, steps[1:], strict=False)
                   if a.node != b.node)

    def _long_way(self, steps, start, goal):
        """True when the plan is a long way round compared with the shortest path on the empty roadmap."""
        short = self.graph.shortest_dist(start, goal)
        # [수정 2026-11-20] D-05: 경로 길이 합을 _plan_length 하나로 모음
        length = self._plan_length(steps)
        return length > max(short * self.yield_detour_ratio, short + self.yield_detour_min)

    def _make_way(self, r, start, goal):
        """Idle robots parked on the shortest path of `r` (or too close to its goal) step aside into a side spot
        instead of making `r` drive a long way round, or wait for ever. Returns True when one started to move."""
        path = self._shortest_path(start, goal)
        region = set(path)
        for n in path:
            region |= self.graph.conflict[n]
        moved = False
        for o in self.robots.values():
            if o.id == r.id or not o.online or o.estop or o.task or o.route or o.pending_goal or o.arm_busy \
                    or o.heading or o.node not in region or self.now - o.last_yield < 10.0:
                continue
            # [수정 2026-11-17] T-26: 실측 지도에서는 비켜 준 로봇이 상대가
            # 지나간 뒤 서 있던 노드로 돌아감(운영자가 세워 둔 자리 유지).
            # 상대의 목적지가 그 노드이거나 너무 가까우면 돌아가지 않음
            target = self.graph.resolve(goal)
            back = bool(self.graph.map_id) and o.node not in (
                {target} | self.graph.conflict[target])
            if self._retreat(o, r, strict=True, clear=region, stay=True,
                             back=back):
                o.last_yield = self.now
                self.m['yields'] += 1
                moved = True
            # [수정 2026-11-17] T-24: 비킬 자리가 다른 유휴 로봇에 막혀 있으면
            # 그 로봇부터 비키게 함 (전에는 포기해 PLAN_FAIL 이 반복됨)
            elif self._clear_exit(o, r, region):
                moved = True
        return moved

    def _clear_exit(self, o: Robot, r: Robot, region: set) -> bool:
        """`o`가 `region` 밖으로 나갈 길을 막고 선 유휴 로봇을 비키게 함.

        Args:
            o: 비켜야 하지만 비킬 자리가 없는 유휴 로봇.
            r: 지나가려는 로봇.
            region: `r`이 지나갈 노드와 그에 너무 가까운 노드.

        Returns:
            비키기 시작한 로봇이 있으면 True.
        """
        # 비킬 수 있는 유휴 로봇: 연결됨, 정지·임무·경로·팔 작업·주행 없음,
        # 마지막으로 비킨 뒤 10초 지남
        def idle(q: Robot) -> bool:
            return bool(q.online and not (
                q.estop or q.task or q.route or q.pending_goal or q.arm_busy
                or q.heading) and self.now - q.last_yield >= 10.0)

        # 유휴 로봇이 선 노드는 지나갈 수 있다고 보고 가장 가까운 출구를 찾음
        prev, order, exit_node = {o.node: None}, [o.node], None
        for u in order:
            for n, _ in self.graph.adj[u]:
                if n in prev:
                    continue
                owner = self._blocker(n, o.id)
                if owner is not None and (
                        owner == r.id or not idle(self.robots[owner])):
                    continue
                prev[n] = u
                order.append(n)
                if n not in region:
                    exit_node = n
                    break
            if exit_node:
                break
        if exit_node is None:
            return False
        # 출구까지의 길과 그에 너무 가까운 노드(비워야 할 곳)
        need, n = set(), exit_node
        while n is not None:
            need |= {n} | self.graph.conflict[n]
            n = prev[n]
        # 그 길 위 노드의 락을 잡은 유휴 로봇을 비키게 함
        moved = False
        for q in self.robots.values():
            if q.id in (o.id, r.id) or not idle(q) or not q.held & need:
                continue
            if self._retreat(q, o, strict=True, clear=region | need,
                             stay=True):
                q.last_yield = self.now
                self.m['yields'] += 1
                moved = True
        return moved

    def _in_the_way(self, r, path):
        """The moving robot whose route (or body) meets `path` first, or None. Parked and stopped robots do not
        count: they will not move away, so driving round them is right."""
        best, at = None, len(path)
        index = {n: i for i, n in reversed(list(enumerate(path)))}
        for o in self.robots.values():
            if o.id == r.id or o.estop or not o.route:
                continue
            nodes = set(o.held) | {st.node for st in o.route[max(o.idx, 0):]}
            for n in list(nodes):
                nodes |= self.graph.conflict[n]
            hit = min((index[n] for n in nodes if n in index), default=None)
            if hit is not None and hit < at:
                best, at = o, hit
        return best

    def _yield_instead(self, r, req, steps, goal, mode):
        """`steps` avoids another robot. If that costs a long way round, give way instead: a plan that waits on the
        short path, or 'RETREAT' after backing into a side spot (the move then continues from there), else None."""
        if not self._long_way(steps, req.start, goal):
            return None
        short = self.graph.shortest_dist(req.start, goal)
        # [수정 2026-11-20] D-05: 경로 길이 합을 _plan_length 하나로 모음
        length = self._plan_length(steps)
        path = self._shortest_path(req.start, goal)
        o = self._in_the_way(r, path)
        # [수정 2026-11-17] T-23: 양보하지 않는 이유를 남김(기록용)
        if o is None:
            self._yield_why = 'no_moving_robot_on_path'
            return None
        loaded = lambda x, md: md == 'GUIDE' or bool(x.task and x.task.carrying)
        if loaded(r, mode) and not loaded(o, o.mode):
            self._yield_why = 'carrying'
            return None                               # guests in tow / food on board: keep moving, do not wait
        on = set(path)
        if self._stay_region(o) & on:
            self._yield_why = 'other_stops_on_path'
            return None                               # it will stop ON our short path: waiting cannot help, go round
        wait = self.planner.plan(self.graph, PlanRequest(
            # [수정 2026-11-18] W6: 구간 지연을 그대로 넘김
            r.id, req.start, goal, req.t0, req.speed,
            goal_hold=req.goal_hold, overhead=req.overhead,
            blocked=frozenset(n for n in self.graph.nodes if n not in on)), self._table(r))
        if wait is not None and all(s.node in on for s in wait) \
                and wait[-1].arrive - steps[-1].arrive <= self.yield_max_wait:
            self.m['yields'] += 1
            r.yield_note = o.id
            self.io.log('YIELD_WAIT', robot_id=r.id, zone_id=goal, task_id=r.task.id if r.task else '',
                        reason=f'yield_to={o.id} wait={wait[-1].arrive - steps[-1].arrive:+.1f}s '
                               f'instead_of_detour={length - short:+.2f}m')
            return wait
        if self.now - r.last_yield > 10.0 and self._retreat(r, o, goal=goal, mode=mode, strict=True):
            r.last_yield = self.now
            self.m['yields'] += 1
            return 'RETREAT'
        self._yield_why = 'wait_too_long_no_side_spot'
        return None

    def _stay_region(self, o):
        """Nodes robot `o` will occupy once its current move is over (its goal and the nodes too close to it)."""
        g = o.pending_goal[0] if o.pending_goal else (o.route[-1].node if o.route else o.node)
        return {g} | self.graph.conflict[g]

    def _reachable(self, src, dst, closed):
        """closed 노드를 지나지 않고 src 에서 dst 로 갈 수 있는지."""
        seen, todo = {src}, [src]
        while todo:
            u = todo.pop()
            if u == dst:
                return True
            for n, _ in self.graph.adj[u]:
                if n not in seen and n not in closed:
                    seen.add(n)
                    todo.append(n)
        return False

    def _adopt(self, r, steps, goal, mode, replan=False):
        """계획 steps 를 로봇 r 의 경로로 채택하고 로봇에 보낸다.

        출발 = 목적지면 바로 도착 처리하고, 구간 중간 재계획에서 지나는
        노드가 같으면 경로를 다시 보내지 않고 시각만 고친다.
        """
        same_kind = r.goal == goal and r.mode == mode
        r.goal, r.mode, r.pending_goal = goal, mode, None
        if len(steps) == 1 and not r.heading and steps[0].node == r.node:
            # start == goal: nothing to drive, so no progress report would ever come. Treat it as arrived now.
            if r.route:
                self._stop_route(r)
            r.plan_version += 1
            self._arrived(r)
            return
        if replan and r.route and r.heading and same_kind and not r.yield_to and steps[0].arrive > 0:
            # The robot is between two nodes and the new plan visits the same nodes: only the timing changed. Keep the
            # route and its version and take over the new times. Re-sending it restarts the robot's current segment,
            # and a robot that is re-planned every few seconds (others keep changing plans) then never arrives.
            k = r.idx + 1
            if [s.node for s in r.route[k:]] == [s.node for s in steps]:
                for old, new in zip(r.route[k:], steps):
                    old.arrive, old.depart = new.arrive, new.depart
                return
        r.plan_version += 1
        r.route, r.idx, r.granted = steps, -1 if r.heading else 0, 0
        r.wait_since, r.blocked_by = None, ''
        self.io.send_route(r.id, r.task.id if r.task else 'RETURN', r.plan_version, mode,
                           r.task.visit_id if r.task else 0, steps)
        self.io.log('REPLAN' if replan else 'PLAN', robot_id=r.id, task_id=r.task.id if r.task else 'RETURN',
                    plan_version=r.plan_version, zone_id=goal, result=self.planner.name,
                    reason=f'len={len(steps)} eta={steps[-1].arrive - self.now:.1f}' if steps[-1].arrive else f'len={len(steps)}')

    def _request(self, o, goal, mode):
        """다른 로봇 o 의 계획 요청(함께 계획용, _start_move 와 같은 식)."""
        speed = (self.guide_speed if mode == 'GUIDE' else self.speed) * self.plan_speed_factor
        # [수정 2026-11-18] W6: 구간 지연 포함(_start_move 와 같은 식)
        ov = self.plan_overhead
        t0 = self.now
        if o.heading:
            t0 += (ov + self.graph.dist(o.node, o.heading) / speed) * 0.5
        hold = INF if (o.returning and goal == o.park) else self._hold_estimate(o, at_goal=True)
        return PlanRequest(o.id, o.heading or o.node, goal, t0, speed,
                           goal_hold=hold, overhead=ov)

    def _plan_joint(self, r, req, goal, mode):
        """Joint planners (CCBS): plan `r` together with every other robot that is on its way somewhere."""
        others = [o for o in self.robots.values() if o.id != r.id and not o.estop and (o.route or o.pending_goal)]
        if not others:
            return None
        reqs = [req] + [self._request(o, o.pending_goal[0] if o.pending_goal else o.goal,
                                      o.pending_goal[1] if o.pending_goal else o.mode) for o in others]
        plans = self.planner.plan_joint(self.graph, reqs, self._table(r, exclude={o.id for o in others}))
        if plans is None:
            self.m['joint_fail'] += 1
            return None
        self.m['joint_plans'] += 1
        for o in others:
            g, md = (o.pending_goal[0], o.pending_goal[1]) if o.pending_goal else (o.goal, o.mode)
            old = [s.node for s in o.route[max(o.idx, 0):]] if o.route else None
            new = plans[o.id]
            if old == [s.node for s in new] and o.route and abs(new[-1].arrive - o.route[-1].arrive) < 1.0:
                continue                                   # unchanged: do not disturb the robot
            self._adopt(o, new, g, md, replan=True)
        return plans[r.id]

    def _stop_route(self, r):
        """로봇의 경로를 취소하고 관제 쪽 경로를 지운다(락은 그대로)."""
        self.io.cancel_route(r.id)
        r.route = None

    # ------------------------------------------------------------------ traffic layer
    def _drive(self, r, dt):
        """교통 계층: 로봇 r 의 다음 노드 허가를 판단한다(tick 마다).

        계획의 출발 시각 전이면 기다리고, 늦었으면 남은 계획을 미룬다. 다음
        노드(와 너무 가까운 노드)가 비면 락을 잡고 허가를 내고, 막혀서
        stall_timeout 넘게 기다리면 _resolve_stall 로 넘긴다.

        Args:
            r: 로봇.
            dt: 지난 tick 부터의 시간(초, 대기 지표용).
        """
        # [수정 2026-11-17] A3: 끊긴 로봇과 보류된 임무의 로봇에는 새 허가를
        # 내지 않고 보류한 이동도 시작하지 않음. 이미 낸 허가와 락은 그대로
        if r.estop or not r.online or (r.task and r.task.state == 'SUSPENDED'):
            return
        # 다시 시도할 시각이 됐고 양보 상대가 지나갔으면 원래 목적지로
        if r.pending_goal and self.now >= r.pending_goal[2] and self._yield_done(r):
            g, mode, _ = r.pending_goal
            self._start_move(r, g, mode, replan=True)
        # 경로 없음, route[0] 으로 가는 중, 허가한 구간을 주행 중이면 할 일 없음
        if not r.route or r.idx < 0 or r.idx != r.granted:
            return
        if r.idx >= len(r.route) - 1:  # 마지막 노드: 허가할 구간 없음
            return
        # 시각이 있는 계획: 출발 시각 전에는 허가하지 않음
        timed = self.planner.coordinated and r.route[0].arrive > 0
        cur = r.route[r.idx]
        if timed:
            if self.now < cur.depart - 0.05:
                self.m['planned_wait'] += dt
                return
            late = self.now - cur.depart
            if late > 0.2:                                   # we are late: shift the rest of our plan
                for s in r.route[r.idx:]:
                    s.arrive += late if s is not cur else 0.0
                    s.depart += late
        # 다음 노드가 비었으면 락을 잡고 허가
        nxt = r.route[r.idx + 1].node
        owner = self._blocker(nxt, r.id)
        if owner is None:
            self.locks[nxt] = r.id
            r.held.add(nxt)
            r.heading = nxt
            r.granted = r.idx + 1
            r.wait_since, r.blocked_by = None, ''
            self.m['grants'] += 1
            self.io.grant(r.id, r.task.id if r.task else 'RETURN', r.plan_version, r.granted)
            self.io.log('ZONE_GRANT', robot_id=r.id, zone_id=nxt, plan_version=r.plan_version,
                        task_id=r.task.id if r.task else 'RETURN')
            return
        # blocked by another robot's lock
        if r.wait_since is None:
            r.wait_since, r.blocked_by = self.now, owner
            # [수정 2026-11-20] T-48: 보고 위치로 막혔으면 표시(off_node)
            why = f'held_by={owner}' + (
                ' off_node' if self.locks.get(nxt) != owner and not any(
                    self.locks.get(n) == owner
                    for n in self.graph.conflict[nxt]) else '')
            self.io.log('ZONE_REQUEST', robot_id=r.id, zone_id=nxt,
                        plan_version=r.plan_version, reason=why)
        self.m['blocked_wait'] += dt
        if self.now - r.wait_since > self.stall_timeout and self.now - r.last_replan > 2.0:
            self._resolve_stall(r, owner)

    def _blocker(self, node, rid):
        """Robot that prevents `rid` from entering `node` (holds it or a node too close to it), else None."""
        # [수정 2026-11-18] W8-1: 집합 순서(PYTHONHASHSEED)에 따라 막는 로봇이
        # 달라져 판단이 갈렸음. 정렬된 순서로 봄
        for n in (node, *sorted(self.graph.conflict[node])):
            o = self.locks.get(n)
            if o not in (None, rid):
                return o
        # [수정 2026-11-20] T-48: 노드에서 벗어나 서 있는 로봇은 보고 위치로도
        # 막음(락은 가장 가까운 노드에만 잡혀 있어 옆 노드가 비어 보였음)
        return self._pos_blocker(node, rid)

    # [수정 2026-11-20] T-48: 신규
    def _stray(self, o: Robot) -> bool:
        """노드에서 벗어나 서 있는(허가받은 구간을 주행 중이 아닌) 로봇인지.

        주행 중인 로봇(다음 구간 허가를 받고 아직 도착 보고 전)은 지나는
        두 노드의 락으로 덮이므로 제외함. 그래야 노드를 떠나는 정상 통과를
        막지 않음. 노드 위 흔들림은 여기서 거르지 않고 _pos_blocker·_table 이
        pos_block_dist(12 cm)로 거름(W1-B1 처럼 15.7 cm 떨어진 노드가 위치 추정
        흔들림만으로 잠기지 않게).

        Args:
            o: 로봇.

        Returns:
            보고 위치를 점유 판단에 써야 하면 True.
        """
        if o.still_pos is None:
            return False                                # 아직 위치 보고 없음
        if o.route and o.granted > o.idx >= 0:
            return False                                # 허가받은 구간 주행 중
        # [수정 2026-11-20] T-52: 6 cm(off_node_dist) 문턱을 없앰. 서 있는
        # 로봇은 모두 보고 위치로 봄. 노드 위 흔들림은 pos_block_dist 가
        # 거름(실기기 09: W1 에서 5.9 cm 벗어난 로봇 옆 B1 이 열려 있었음)
        return True

    # [수정 2026-11-20] T-48: 신규
    def _pos_blocker(self, node: str, rid: str) -> str | None:
        """보고 위치로 노드를 막는 로봇(노드에서 벗어나 서 있는 로봇).

        노드에서 벗어나 서 있는 다른 로봇의 보고 위치가 node 에서
        pos_block_dist(기본 0.12 m) 안이면 그 로봇.

        끊긴 로봇도 마지막 보고 위치로 봄(락과 같이, 어디 있는지 모르면
        움직이지 않았다고 봄).

        Args:
            node: 들어가려는 노드.
            rid: 들어가려는 로봇.

        Returns:
            막는 로봇 이름, 없으면 None.
        """
        xy = self.graph.nodes[node]
        for o in sorted(self.robots.values(), key=lambda b: b.id):
            # [수정 2026-11-20] T-52: SAFE_DIST 대신 pos_block_dist(12 cm)
            if o.id != rid and self._stray(o) \
                    and math.dist(xy, (o.x, o.y)) < self.pos_block_dist:
                return o.id
        return None

    def _resolve_stall(self, r, owner):
        """정체 처리: owner 가 다음 노드를 막아 오래 기다린 로봇 r.

        상대가 나에게 양보 중이면 기다리고, 서로 막혔으면 우선순위가 높은
        쪽이 조금 더 기다린다. 나머지는 다시 계획하고, 그래도 막히면
        (서로 막힘이거나 상대가 못 움직이면) 물러선다.
        """
        self.m['stalls'] += 1
        r.last_replan = self.now
        o = self.robots[owner]
        # [수정 2026-11-17] T-24: 상대가 이미 나에게 양보해 물러나는 중이면
        # 기다림. 전에는 나도 물러나 둘이 서로 30초씩 기다렸음
        # [수정 2026-11-17] A3: 단, 그 상대가 끊겼으면 기다리지 않음
        if o.yield_to == r.id and o.route and not o.estop and o.online:
            return
        # 서로 막힘: 상대가 나를 기다리거나, 다시 시도를 기다리거나,
        # 상대의 다음 노드를 내가 막음
        mutual = o.blocked_by == r.id or o.pending_goal is not None or \
            (o.route and 0 <= o.idx and o.idx + 1 < len(o.route) and self._blocker(o.route[o.idx + 1].node, o.id) == r.id)
        # in a mutual block the lower-priority robot yields first; the other one waits one more round
        # [수정 2026-11-17] A3: 끊긴 상대는 비상 정지된 로봇처럼 비켜 주지
        # 못하는 것으로 봄
        stuck = o.estop or not o.online
        if mutual and not stuck and self._rank(r) > self._rank(o) and \
                self.now - r.wait_since < 2.5 * self.stall_timeout:
            return
        # 비조율 계획기는 다른 로봇이 잡은 노드를 빼고 다시 계획
        blocked = frozenset(n for x in self.robots.values() if x.id != r.id for n in x.held)
        self.m['replans'] += 1
        ok = self._start_move(r, r.goal, r.mode, replan=True,
                              blocked=blocked if not self.planner.coordinated else frozenset())
        # 새 계획의 첫 구간이 비어 있으면 끝
        if ok and r.route and len(r.route) > 1 and self._blocker(r.route[1].node, r.id) is None:
            return
        if mutual or stuck:
            self._retreat(r, o)

    def _yield_done(self, r):
        """After stepping aside for robot `o`, stay out of the way until `o` has passed the node we vacated (or finished,
        or the wait ran out: 30 s, or YIELD_BACK_WAIT (60 s) when we went back
        the way we came). Resuming earlier puts us straight back in its way and
        the two keep swapping places.
        """
        if not r.yield_to:
            return True
        o = self.robots.get(r.yield_to)
        region = {r.yield_from} | self.graph.conflict.get(r.yield_from, set())
        ahead = {st.node for st in o.route[max(o.idx, 0):]} if o and o.route else set()
        passed = o is None or o.estop or (not o.route and not o.pending_goal) or \
            (o.route is not None and o.node not in region and o.heading not in region and not (ahead & region))
        # [수정 2026-11-17] T-26: 원래 노드로 돌아가려는 로봇(실측 지도, 임무
        # 없음)은 상대의 남은 길이 그 노드를 지나면 아직 지나간 것이 아님
        # (상대가 잠시 물러선 경우 포함). 기다리다 시간이 지나면 돌아가지
        # 않고 비킨 자리에 남음. 임무 중인 로봇 앞으로 되돌아가지 않기 위함
        if self.graph.map_id and r.task is None:
            if passed and o is not None and o.task and not o.estop:
                dest = o.pending_goal[0] if o.pending_goal else (
                    o.route[-1].node if o.route else '')
                if dest and set(self._shortest_path(
                        o.heading or o.node,
                        self.graph.resolve(dest))) & region:
                    passed = False
            if not passed and self.now > r.yield_until:
                self.io.log('YIELD_STAY', robot_id=r.id,
                            zone_id=r.yield_from,
                            reason=f'timeout wait_for={r.yield_to}')
                r.pending_goal = None
                r.yield_to = r.yield_from = ''
                return False
        if passed or self.now > r.yield_until:
            r.yield_to = r.yield_from = ''
            return True
        return False

    def _rank(self, r):
        """정체 판단의 우선순위(임무 우선순위 + 화물, 같으면 로봇 번호 작은 쪽).

        로봇 id 의 끝 한 자리 숫자만 봄(pinky10 은 0 으로 봄).
        """
        p = r.task.priority if r.task else 0
        return (p + (1 if r.task and r.task.carrying else 0), -int(r.id[-1]) if r.id[-1].isdigit() else 0)

    def _retreat(self, r, o, goal=None, mode=None, strict=False, clear=(), stay=False, back=False):
        """Step aside so the other robot(s) can pass, then continue to the goal. Searches the free nodes around us and
        prefers a lay-by (비켜 서는 곳), then any node that is not on another robot's route.
        stay: an idle robot makes way (it has no goal of its own). back: with stay, it drives back to the node
        it vacated once the other robot has passed, instead of staying on the side spot.
        o: 비켜 줄 상대(None 이면 계획 실패로 물러남). strict: 상대의 길을
        실제로 비우는 자리만 고름. clear: 더 피할 노드. 자리를 찾아 YIELD
        경로를 보냈으면 True.
        """
        # keep clear of the others' remaining routes AND of every node too close to them: a side spot next to the
        # aisle node the other robot needs (closer than SAFE_DIST) still blocks it, and the two would swap forever
        avoid = set()
        for x in self.robots.values():
            if x.id != r.id and x.route:
                for st in x.route[max(x.idx, 0):]:
                    avoid.add(st.node)
                    avoid |= self.graph.conflict[st.node]
        avoid |= set(clear)                               # nodes the other robot is about to plan through
        prev, order = {r.node: None}, [r.node]
        for u in order:                                   # BFS over nodes we could enter right now
            for n, _ in self.graph.adj[u]:
                if n not in prev and self._blocker(n, r.id) is None:
                    prev[n] = u
                    order.append(n)
        cands = order[1:]
        if strict:
            # By choice: only a spot that really clears the other's way, and from which our own goal can still be
            # reached once the other robot stands on ITS goal (a dead-end spur behind that goal would trap us).
            closed = self._stay_region(o) if o is not None and not stay else set()
            cands = [n for n in cands if n not in avoid and n not in closed
                     and (stay or self._reachable(n, self.graph.resolve(goal or r.goal), closed))]
            if not cands:
                return False
        if not cands:
            r.wait_since = self.now
            return False

        # 지금 노드에서 n 까지 몇 단계인지(탐색 트리 prev 를 거슬러 셈)
        def depth(n):
            d = 0
            while prev[n] is not None:
                n, d = prev[n], d + 1
            return d
        # The aisles are one robot wide, so the robot backs out of the way instead of turning round: prefer spots whose
        # first step lies behind it (away from the robot it yields to), then the nearest, counting a lay-by / standby spot as two nodes closer.
        pull_in = self.graph.bay_nodes | set(self.graph.standby_nodes)
        hx, hy = math.cos(r.yaw), math.sin(r.yaw)
        if o is not None:                                 # facing unknown / sideways: "behind" = away from the other robot
            ox, oy = o.x - r.x, o.y - r.y
            if ox * hx + oy * hy <= 0.0 and math.hypot(ox, oy) > 1e-6:
                d = math.hypot(ox, oy)
                hx, hy = ox / d, oy / d
        x0, y0 = self.graph.nodes[r.node]

        # n 으로 가는 첫 단계 노드가 로봇 뒤쪽(hx, hy 반대편)에 있는지
        def behind(n):
            first = n
            while prev[first] is not None and prev[first] != r.node:
                first = prev[first]
            fx, fy = self.graph.nodes[first]
            return (fx - x0) * hx + (fy - y0) * hy < 0.0
        # a lay-by / standby spot is worth two extra nodes of backing up, no more: long reverse runs block the aisle
        if strict:      # by choice: the nearest spot that clears the way (a side spot counts one node closer)
            cands.sort(key=lambda n: (depth(n) + (0 if n in pull_in else 1), not behind(n), depth(n)))
        else:
            cands.sort(key=lambda n: (n in avoid, not behind(n), depth(n) + (0 if n in pull_in else 2), depth(n)))
        side = cands[0]  # 고른 비켜 설 자리
        path = [side]
        while prev[path[-1]] is not None:
            path.append(prev[path[-1]])
        path.reverse()
        # 지금 경로를 취소하고 비켜 설 자리까지의 YIELD 경로를 보냄
        goal, mode = goal or r.goal, mode or r.mode
        if r.route:
            self.io.cancel_route(r.id)
        self.m['retreats'] += 1
        r.plan_version += 1
        timed = self.planner.coordinated
        t, steps = self.now, []
        for a, b in zip(path, path[1:] + [None]):
            # [수정 2026-11-18] W6: 물러나는 구간에도 구간 지연 포함
            dt = (self.plan_overhead + self.graph.dist(a, b) / self.speed
                  if b else 4.0)
            steps.append(Step(a, t if timed else 0.0, t if timed else 0.0))
            t += dt
        if timed:
            steps[-1].depart = t
        r.route, r.idx, r.granted = steps, 0, 0
        r.wait_since, r.blocked_by = None, ''
        # [수정 2026-11-17] T-26: 비켜 준 유휴 로봇이 원래 노드로 돌아감.
        # 임무 중 양보와 같은 방식(pending_goal, 상대가 지나갈 때까지 대기)
        if stay and back and o is not None:
            r.pending_goal = (path[0], 'NORMAL', t + self.rng.uniform(0.0, 3.0))
            r.returning, r.mode = False, 'YIELD'
            r.yield_to, r.yield_from = o.id, path[0]
            r.yield_until = t + YIELD_BACK_WAIT
            r.yield_note = o.id
        elif stay:                                        # idle robot making way: the side spot is where it stays
            r.pending_goal, r.returning, r.mode = None, False, 'YIELD'
            r.yield_to = r.yield_from = ''
            r.yield_note = o.id if o else ''
        else:
            r.pending_goal = (goal, mode, t + self.rng.uniform(0.0, 3.0))
            r.yield_to, r.yield_from, r.yield_until = (o.id if o else ''), r.node, t + 30.0
        r.goal = side
        self.io.send_route(r.id, r.task.id if r.task else 'RETURN', r.plan_version, 'YIELD', 0, r.route)
        self.io.log('RETREAT', robot_id=r.id, zone_id=side, plan_version=r.plan_version,
                    reason=f'yield_to={o.id if o else "plan"}' + (' idle_makes_way' if stay else ' by_choice' if strict else '')
                    + (f' back_to={path[0]}' if stay and back and o is not None else ''))
        return True

    # ------------------------------------------------------------------ inputs from robots
    def on_robot_status(self, rid, x, y, yaw, battery, charging, state, error=''):
        """로봇의 상태 보고(/fleet/robot_status, 10 Hz)를 반영한다.

        Args:
            rid: 로봇 id.
            x: 보고 위치 x(m, 지도 좌표).
            y: 보고 위치 y(m).
            yaw: 방향(rad).
            battery: 배터리(0~100 으로 다룸).
            charging: 충전 중.
            state: RobotStatus.state(IDLE, MOVING, LOCALIZING 등).
            error: device_state.ERROR 이름('' 또는 NO_ERROR = 없음).
        """
        r = self.robots.get(rid)
        if not r:
            return
        # [수정 2026-11-20] T-49: 로봇이 아직 위치를 모름(자동 위치 추정 중
        # 또는 실패). 상태·오류만 기록하고 위치는 쓰지 않음. last_status 를
        # 갱신하지 않아 이미 온라인이던 로봇은 상태 보고 시간 초과(tick 의
        # 1초) 뒤 오프라인이 되고 새 배정·허가가 없음. 전에 잡은 락(held)은
        # 남고, 전에 위치 보고가 있었으면(still_pos) _stray·_pos_blocker 가
        # 마지막 위치로 계속 막음(실제 운용에서의 영향은 확인 필요).
        # 위치가 잡히면 보통 보고가 옴
        if state in UNLOCALIZED:
            r.localizing = state
            r.error = '' if error == 'NO_ERROR' else error
            return
        r.localizing = ''
        # [수정 2026-11-17] G2: 'NO_ERROR' 도 오류 없음으로 봄
        r.last_status = self.now
        r.error = '' if error == 'NO_ERROR' else error
        # [수정 2026-11-17] A3: 다시 연결됨
        if not r.online and r.offline_since is not None:
            self.io.log('ROBOT_ONLINE', robot_id=rid, result='OK',
                        reason=f'offline={self.now - r.offline_since:.1f}s')
        r.offline_since = None
        # [수정 2026-11-17] auto_home: 3 cm 넘게 움직였거나 방금 연결됐으면
        # "서 있는 시간"을 다시 셈
        if not r.online or r.still_pos is None \
                or math.dist((x, y), r.still_pos) > 0.03:
            r.still_pos, r.still_since = (x, y), self.now
        if r.online:
            r.dist += math.hypot(x - r.x, y - r.y)
        r.x, r.y, r.yaw, r.battery, r.charging, r.reported_state, r.online = x, y, yaw, battery, charging, state, True
        # 실측 지도의 한가한 로봇: 보고 위치에서 가장 가까운 노드가 비었으면
        # 그 노드에 서 있다고 보고 락을 잡음
        if self.graph.map_id and state == 'IDLE' and not (r.route or r.pending_goal or r.task):
            vertex = self.graph.nearest_node(x, y)
            if self.locks.get(vertex) in (None, rid):
                self._claim_vertex(r, vertex)

    def _claim_vertex(self, robot, node):
        """로봇의 락을 모두 풀고 node 하나만 잡는다(그 노드에 서 있다고 봄)."""
        for previous in robot.held:
            if self.locks.get(previous) == robot.id:
                del self.locks[previous]
        robot.node, robot.held = node, {node}
        self.locks[node] = robot.id

    def on_route_progress(self, rid, plan_version, reached):
        """로봇이 경로의 reached 번째 노드에 도착했다는 피드백을 반영한다."""
        r = self.robots.get(rid)
        if not r or not r.route or plan_version != r.plan_version or reached <= r.idx:
            return
        reached = min(reached, len(r.route) - 1)
        if reached > 0:
            r.fail_count = 0                                  # a segment was driven: earlier failures are history
        r.idx = reached
        r.node = r.route[reached].node
        r.heading = ''
        # 지나온 노드의 락을 풂
        for n in list(r.held):
            if n != r.node:
                r.held.discard(n)
                if self.locks.get(n) == r.id:
                    del self.locks[n]
                self.io.log('ZONE_EXIT', robot_id=r.id, zone_id=n, plan_version=r.plan_version)
        r.held.add(r.node)
        self.locks[r.node] = r.id
        self.io.log('ZONE_ENTER', robot_id=r.id, zone_id=r.node, plan_version=r.plan_version)
        # [수정 2026-11-18] W2: 음식을 실은 서빙 임무가 테이블행 경로에서 한
        # 구간을 실제로 나아가면 SERVING(v4: 테이블 이동 시작). 비켜서기 중은 제외
        t = r.task
        if (t and t.type == 'SERVE' and t.carrying and not t.serving_sent
                and t.state == 'IN_PROGRESS' and not r.pending_goal):
            t.serving_sent = True
            self._event(t, 'SERVING')
        if reached == len(r.route) - 1:
            self._arrived(r)

    def on_route_result(self, rid, plan_version, success, reason, reached):
        """로봇의 경로 결과(NavigateRoute 결과)를 반영한다.

        정해진 실패(NAV2_FAILED 등)는 route_retries 번까지 노드로 돌아가 다시
        계획하고, 그 밖의 실패는 임무를 보류(SUSPENDED)한다.

        Args:
            rid: 로봇 id.
            plan_version: 결과가 속한 경로 번호(옛 번호는 무시).
            success: 성공 여부.
            reason: 실패 이유(NAV2_FAILED, NO_PROGRESS, PREEMPTED 등).
            reached: 마지막으로 도착한 경로 칸(쓰지 않음).
        """
        r = self.robots.get(rid)
        if not r or plan_version != r.plan_version:
            return                                            # late result of an old plan: ignore
        if success:
            if r.route:
                self.on_route_progress(rid, plan_version, len(r.route) - 1)
            return
        if reason in ('PREEMPTED', 'CANCELED'):  # 관제가 취소·선점
            return
        r.route = None
        if r.estop:
            return                                            # stopped by the operator: the task is already suspended
        if reason in ('NAV2_FAILED', 'REJECTED', 'FMS_RESTART', 'E_STOP') and r.fail_count < self.route_retries:
            # Exception handling: the robot stands somewhere between two nodes. Take it back onto the roadmap (the
            # node behind it first) and plan again, round the node it could not reach while there is another way.
            r.fail_count += 1
            self.m['route_retries'] += 1
            goal, mode = (r.pending_goal[0], r.pending_goal[1]) if r.pending_goal else (r.goal, r.mode)
            failed = r.heading if r.heading != r.node else ''
            if reason == 'NAV2_FAILED' and failed:
                r.avoid_node, r.avoid_until = failed, self.now + 60.0
                self._rejoin(r, avoid={failed})
            r.pending_goal = (goal, mode, self.now + 1.5)
            self.io.log('ROUTE_RETRY', robot_id=r.id, task_id=r.task.id if r.task else '', zone_id=goal,
                        plan_version=plan_version, reason=f'{reason} try={r.fail_count}/{self.route_retries}')
            return
        r.pending_goal = None
        # [수정 2026-11-20] T-44: 다시 시도하지 않는 경로 실패를 기록(임무가
        # 없는 이동도 로그에 남게). NO_PROGRESS(로봇의 무진행 감시) 등은
        # 아래에서 임무를 보류(SUSPENDED)하고, 보류는 관리자 알람이 됨
        self.io.log('ROUTE_FAIL', robot_id=r.id,
                    task_id=r.task.id if r.task else '', zone_id=r.goal,
                    plan_version=plan_version, result='FAIL', reason=reason)
        if r.task and r.task.state == 'IN_PROGRESS':
            self._suspend(r.task, reason)

    def _arrived(self, r):
        """경로 끝 도착: 비켜 서기면 대기, 복귀면 끝, 임무면 다음 단계."""
        r.route, r.yield_note = None, ''
        if r.pending_goal:                                    # we only stepped aside; continue later
            return
        if r.returning:
            r.returning = False
            self.io.log('HOME', robot_id=r.id, zone_id=r.node)
            return
        if r.task and r.task.state == 'IN_PROGRESS':
            ph = r.task.phases[r.task.pi]
            if ph[0] == 'move' and self.graph.resolve(ph[1]) == r.node:
                r.task.pi += 1
            self._run_phase(r)

    def on_arm_result(self, arm_id, task_id, success, reason=''):
        """팔 작업 결과(ArmJob 결과)를 반영한다.

        Args:
            arm_id: 서빙 팔이면 로봇 id, 조리 팔이면 cook_arm_a/b.
            task_id: 작업의 임무 id.
            success: 성공 여부.
            reason: 실패 이유(ARM_OFFLINE, REJECTED 등).
        """
        if arm_id in self.robots:
            r = self.robots[arm_id]
            self.io.log('ARM_DONE', task_id=task_id, robot_id=arm_id, zone_id=r.node, result='OK' if success else 'FAIL',
                        reason=reason)
            r.arm_busy = ''
            t = r.task
            if not t or t.id != task_id or t.state != 'IN_PROGRESS':
                return
            if not success:
                self._suspend(t, reason or 'ARM_FAIL')
                return
            t.pi += 1
            self._run_phase(r)
            return
        for j in self.cook_jobs:                              # cooking arms
            if j.task.id == task_id and j.busy:
                j.busy = False
                if not success:
                    j.task.state, j.task.reason = 'SUSPENDED', reason or 'ARM_FAIL'
                    self._event(j.task, 'SUSPENDED', j.task.reason)
                else:
                    j.pc += 1

    # [수정 2026-11-17] 신규 (UR-17, 19): 팔의 상태·오류 보고 수신
    def on_arm_status(self, arm_id: str, state: str, job: str = '',
                      task_id: str = '', error: str = '') -> None:
        """팔 한 대가 보고한 상태를 저장한다 (/fleet/arm_status).

        Args:
            arm_id: 조리 팔 id(cook_arm_a, cook_arm_b) 또는 서빙 팔이 붙은
                로봇 id.
            state: device_state.STATE 이름.
            job: 수행 중인 팔 작업 이름 ('' = 없음).
            task_id: 그 작업의 임무 id.
            error: device_state.ERROR 이름 ('' = 이상 없음).
        """
        if error and error not in device_state.ERROR:
            error = 'UNCLASSIFIED_ERROR'
        if error == 'NO_ERROR':
            error = ''
        self.arm_reports[arm_id] = dict(
            state=state if state in device_state.STATE else 'UNKNOWN',
            job=job, task_id=task_id, error=error, t=self.now)

    def _arm_report(self, arm_id: str) -> dict | None:
        """최근 3초 안에 받은 팔 보고. 없거나 끊겼으면 None."""
        rep = self.arm_reports.get(arm_id)
        return rep if rep and self.now - rep['t'] <= 3.0 else None

    def _cook_arm_device(self, arm_id: str, letter: str) -> dict:
        """조리 팔의 기기 상태(화면용). 팔이 보고한 오류가 있으면 그것을,
        보고가 끊겼으면 OFFLINE 을, 보고를 받은 적이 없으면 관제가 시킨
        작업으로 추정한 상태를 돌려준다."""
        if arm_id in self.arm_reports:
            rep = self._arm_report(arm_id)
            if rep is None:
                out = device_state.report('OFFLINE', 'COMMUNICATION_ERROR')
            elif rep['error']:
                out = device_state.report('FAULT_HANDLING', rep['error'])
            else:
                out = device_state.arm_state(self._arm_job_of(letter))
            if out['error'] not in ('', 'NO_ERROR'):
                out['since'] = self.arm_fault_since.setdefault(
                    arm_id, self.now)
            else:
                self.arm_fault_since.pop(arm_id, None)
            return out
        return device_state.arm_state(self._arm_job_of(letter))

    def _serving_arm(self, r: Robot) -> dict:
        """AMR 에 붙은 서빙 팔의 상태(화면용)."""
        rep = self._arm_report(r.id)
        if rep:
            return dict(state=rep['state'], job=rep['job'],
                        error=rep['error'], reported=True)
        return dict(state='ARM_OPERATING' if r.arm_busy else 'IDLE',
                    job=r.arm_busy, error='', reported=False)

    def _note_faults(self, r: Robot) -> None:
        """이상 종류별로 시작 시각을 적어 둔다 (알람의 발생 시각)."""
        arm = self._arm_report(r.id)
        active = {
            'OFFLINE': not r.online,
            'E_STOP': r.estop and not r.paused,
            'PAUSED': r.paused,
            'ERROR': bool(r.error) and not r.estop,
            'LOW_BATTERY': r.online and r.battery < 20 and not r.charging,
            'OFF_NODE': self._off_node(r),
            'ARM_ERROR': bool(arm and arm['error']),
        }
        for kind, on in active.items():
            if on:
                r.fault_since.setdefault(kind, self.now)
            else:
                r.fault_since.pop(kind, None)

    def _unavailable_reason(self, r: Robot) -> str:
        """새 임무를 줄 수 없는 이유 ('' = 줄 수 있음). _available 과 같은
        조건을 본다(순서는 다름: 오류를 임무보다 먼저 봄)."""
        if not r.online:
            return 'OFFLINE'
        if r.paused:
            return 'PAUSED'
        if r.estop:
            return 'E_STOP'
        # [수정 2026-11-17] G2
        if self._fault(r):
            return 'ERROR'
        if r.task is not None:
            return 'ON_TASK'
        if r.arm_busy:
            return 'ARM_BUSY'
        if r.battery < self.min_battery:
            return 'LOW_BATTERY'
        return ''

    def on_doneness(self, task_id, decision, stamp):
        """AI 익힘 판정을 저장한다(_cook_tick 이 읽음).

        Args:
            task_id: COOK 임무 id.
            decision: 판정(UNDERCOOKED 면 다시 튀김, 그 밖은 완료로 봄).
            stamp: 받은 시각(대기 시작 뒤에 온 판정만 씀).
        """
        self.doneness[task_id] = (decision, stamp)

    # [수정 2026-11-18] W8-3: 계획 실패가 끝없이 반복돼도 보류·알림이 없었음
    # (W5에서 1,380초 반복)
    def _plan_fail_watch(self, r: Robot, goal: str) -> None:
        """같은 목적지 계획 실패가 20초를 넘으면 임무를 보류하고 알림.

        보류는 로봇 끊김(A3)과 같이 다시 시도 예정과 락을 그대로 두고,
        RETRY_TASK 로 재개함. 임무가 없으면 묶음마다 알림만 한 번 남기고
        다시 시도를 계속함.

        Args:
            r: 계획에 실패한 로봇.
            goal: 실패한 목적지.
        """
        pf = r.plan_fail
        if pf is None or pf[0] != goal:
            r.plan_fail = [goal, self.now, False]
            return
        if pf[2] or self.now - pf[1] <= PLAN_FAIL_SUSPEND_SEC:
            return
        pf[2] = True
        waited = f'goal={goal} for={self.now - pf[1]:.0f}s'
        if r.task and r.task.state == 'IN_PROGRESS':
            self._suspend(r.task, 'PLAN_FAIL')
            self.io.log('PLAN_FAIL_SUSPEND', robot_id=r.id, task_id=r.task.id,
                        zone_id=goal, result='FAIL', reason=waited)
        else:
            self.io.log('PLAN_FAIL_ALERT', robot_id=r.id, zone_id=goal,
                        result='FAIL', reason=waited)

    def _suspend(self, t, reason):
        """임무를 보류(SUSPENDED)하고 기록·이벤트를 낸다(RETRY_TASK 로 재개)."""
        t.state, t.reason = 'SUSPENDED', reason
        self.io.log('TASK_SUSPEND', task_id=t.id, robot_id=t.robot_id, visit_id=t.visit_id, order_id=t.order_id,
                    result='FAIL', reason=reason)
        self._event(t, 'SUSPENDED', reason)

    def _move_to_vertex(self, robot_id, destination):
        """관리자 이동 명령(MOVE_TO_VERTEX, 실측 지도 전용).

        Args:
            robot_id: 로봇 id.
            destination: 목적 노드.

        Returns:
            (받았는지, 화면에 보여 줄 메시지).
        """
        if not self.graph.map_id or destination not in self.graph.nodes or robot_id not in self.robots:
            return False, '지도, 로봇 또는 주행 노드를 확인하세요.'
        robot = self.robots[robot_id]
        # [수정 2026-11-18] W8-2: 다른 로봇이 같은 목적지나 너무 가까운 노드로
        # 가는 중이면 거절(서 있는 임무 없는 로봇은 비켜 주기가 처리)
        other = self._heading_near(destination, robot_id)
        if other:
            return False, (f'{other}이(가) {destination} 또는 바로 옆 노드로 '
                           '가는 중입니다. 도착한 뒤 다시 명령하세요.')
        old = robot.task
        if old and old.type == 'MOVE' and old.state == 'SUSPENDED' and not robot.estop:
            old.state = 'CANCELED'                       # a new move order replaces the one that got stuck
            self._event(old, 'CANCELED', 'replaced')
            robot.task = None
        # [수정 2026-11-17] T-26: 비켜 준 뒤 원래 노드로 돌아가려고 기다리는
        # 로봇(임무 없이 pending_goal 만 있음)도 새 이동 명령을 받음. 새
        # 명령이 복귀를 대신함
        if robot.pending_goal and not robot.task and not robot.route \
                and robot.online and not robot.estop:
            robot.pending_goal = None
            robot.yield_to = robot.yield_from = ''
        if robot.mode == 'YIELD' and robot.route and not robot.task \
                and robot.online and not robot.estop:
            # the robot is stepping aside for another one right now: take the order and start it from the side spot
            # [수정 2026-11-20] D-05: MOVE 임무 만들기를 _new_move_task 로 모음
            task = self._new_move_task(destination)
            task.robot_id, task.state, task.assigned_at = robot.id, 'IN_PROGRESS', self.now
            robot.task = task
            self._event(task, 'ASSIGNED')
            robot.pending_goal = (destination, 'NORMAL', robot.route[-1].arrive or self.now + 2.0)
            robot.yield_to, robot.yield_from, robot.yield_until = robot.yield_note, robot.route[0].node, self.now + 30.0
            return True, f'{task.id}: {robot.yield_note or "다른 로봇"}에게 길을 비켜 준 뒤 {destination}(으)로 이동'
        # [수정 2026-11-17] G2: 자동 배정 조건(_available) 대신 _movable
        # [수정 2026-11-20] T-52: 어떤 조건에 걸렸는지 알려 줌(실기기 09 에서
        # 같은 문장으로 두 번 거절됐는데 원인을 알 수 없었음)
        why = self._unmovable_reason(robot)
        if why:
            self.io.log('MOVE_REJECT', robot_id=robot_id, zone_id=destination,
                        reason=why)
            return False, f'이동할 수 없는 상태입니다: {why}'
        robot.heading = ''  # a failed route may still retain its last granted target
        robot.fail_count, robot.avoid_node = 0, ''
        start = self.graph.nearest_node(robot.x, robot.y)
        off = math.dist((robot.x, robot.y), self.graph.nodes[start])
        if off <= self.off_node_dist:
            # [수정 2026-11-20] T-52: 노드에서 몇 cm 벗어난 로봇은 같은 노드로
            # 다시 세우는 명령을 받음. Nav2 도착 허용 오차(1.5 cm) 안이면 거절
            if start == destination and off <= RESETTLE_MIN:
                return False, (f'이미 해당 노드에 있습니다'
                               f'(노드에서 {off * 100:.1f} cm).')
            if self._blocker(start, robot_id):
                return False, '출발 노드를 다른 로봇이 점유 중입니다.'
            self._claim_vertex(robot, start)
            # [수정 2026-11-20] T-52: 같은 노드로 다시 세우기는 노드
            # 복귀(REJOIN)와 같이 heading 을 그 노드로 둬, 경로 첫 노드까지
            # 들어가게 함
            # (노드 하나짜리 경로를 건너뛰는 _run_phase 규칙을 피함)
            if start == destination:
                robot.heading = destination
        else:
            # not on a node: the route starts with the drive back to the nearest free node
            if self.locks.get(start) in (None, robot_id):
                self._claim_vertex(robot, start)
            if not self._rejoin(robot):
                return False, f'로봇이 주행 노드에서 {off * 100:.0f}cm 벗어나 있고, {self.rejoin_max_dist:.0f}m 안에 비어 있는 노드가 없습니다.'
            start = robot.node
        # [수정 2026-11-20] D-05: MOVE 임무 만들기를 _new_move_task 로 모음
        task = self._new_move_task(destination)
        self._assign(task, robot)
        return True, f'{task.id}: {start} → {destination}' + (f' (노드에서 {off * 100:.0f}cm 벗어나 있어 {start}로 복귀 후 이동)'
                                                              if off > self.off_node_dist else '')

    # [수정 2026-11-20] D-05: _move_to_vertex 두 곳의 같은 코드를 모음
    def _new_move_task(self, destination):
        """새 MOVE 임무를 만들어 임무 목록에 넣고 돌려준다(배정은 호출 쪽)."""
        self.seq += 1
        task = Task(f'M{self.seq:04d}', 'MOVE', created=self.now,
                    start_node=destination,
                    phases=[('move', destination, 'NORMAL')])
        self.tasks[task.id] = task
        return task

    # [수정 2026-11-18] W8-2: 이동 명령의 목적지 겹침 검사
    def _heading_near(self, destination: str, robot_id: str) -> str:
        """목적지나 그와 동시에 점유할 수 없는 노드로 가는 다른 로봇.

        Args:
            destination: 이동 명령의 목적지 노드.
            robot_id: 명령을 받을 로봇(제외).

        Returns:
            그런 로봇의 id. 없으면 ''. 비켜 서는 중인 자리(YIELD 경로의 끝)는
            잠시 머무는 곳이라 보지 않음.
        """
        region = {destination} | self.graph.conflict[destination]
        for o in self.robots.values():
            if o.id == robot_id or o.estop:
                continue
            goals = set()
            t = o.task
            if t and t.type == 'MOVE' and t.state == 'IN_PROGRESS':
                goals.add(self.graph.resolve(t.start_node))
            if o.pending_goal:
                goals.add(self.graph.resolve(o.pending_goal[0]))
            if o.route and o.mode != 'YIELD':
                goals.add(o.route[-1].node)
            if goals & region:
                return o.id
        return ''

    # [수정 2026-11-17] 신규: 관리자 화면의 홈 복귀 버튼(GO_HOME)
    def _send_home(self, target: str) -> tuple:
        """로봇 한 대 또는 연결된 모든 로봇을 홈으로 보냄.

        실측 지도에서는 출발 노드(homes)로 가는 이동 명령과 같고, 가상
        매장에서는 충전대로 복귀함. 임무 중이거나 비상 정지된 로봇은
        보내지 않음.

        Args:
            target: 로봇 이름. 'ALL' 이나 빈 값이면 연결된 모든 로봇.

        Returns:
            (성공 여부, 화면에 보여 줄 메시지). 전체 명령은 한 대라도
            출발했거나 모두 이미 홈이면 성공.

        Raises:
            KeyError: 없는 로봇 이름.
        """
        everyone = target in ('', 'ALL')
        robots = [r for r in self.robots.values() if r.online] \
            if everyone else [self.robots[target]]
        if not robots:
            return False, '연결된 로봇이 없습니다.'
        sent, notes = 0, []
        for r in robots:
            at_home = math.dist(
                (r.x, r.y), self.graph.nodes[r.home]) <= self.off_node_dist
            if at_home and not r.route and not r.task:
                sent += 1
                notes.append(f'{r.id}: 이미 홈({r.home})')
                continue
            if self.graph.map_id:
                ok, message = self._move_to_vertex(r.id, r.home)
            else:
                ok = self._movable(r) and not r.route
                message = f'{r.home}(으)로 복귀' if ok else \
                    '로봇이 이동 가능한 대기 상태인지 확인하세요.'
                if ok:
                    self._go_home(r, force_home=True)
            sent += bool(ok)
            notes.append(f'{r.id}: {message}')
            self.io.log('GO_HOME', robot_id=r.id, zone_id=r.home,
                        result='OK' if ok else 'FAIL', reason=message)
        return sent > 0, ' / '.join(notes)

    # ------------------------------------------------------------------ operator commands
    # [수정 2026-11-25] I/F 정의서 v0.2 이름: /fms/command ->
    # /frybot/tasks/control
    # [수정 2026-11-26] I/F v0.3 최종 판 이름(docstring):
    # /frybot/tasks/control -> /fms/command
    def command(self, cmd, target, arg=''):
        """관리자·관제 명령을 처리한다(/fms/command).

        Args:
            cmd: GO_HOME, MOVE_TO_VERTEX, SET_SCHEDULER, SET_PLANNER, PAUSE,
                ESTOP, SET_STANDBY, RESUME, RETRY_TASK, REASSIGN, CANCEL_TASK.
            target: 로봇 id, 임무 id 또는 알고리즘 이름(명령에 따라).
            arg: 목적 노드, on/off, 사유 등.

        Returns:
            (성공 여부, 메시지). 없는 대상은 False 로 돌려줌.
        """
        try:
            # [수정 2026-11-17] 홈 복귀 명령
            if cmd == 'GO_HOME':
                return self._send_home(target)
            if cmd == 'MOVE_TO_VERTEX':  # target 로봇을 arg 노드로
                return self._move_to_vertex(target, arg)
            if cmd == 'SET_SCHEDULER':  # 이름은 target 또는 arg
                self.set_scheduler(target or arg)
                return True, f'scheduler={self.scheduler.name}'
            if cmd == 'SET_PLANNER':
                self.set_planner(target or arg)
                return True, f'planner={self.planner.name}'
            # [수정 2026-11-17] UR-18: 일시 중단. 비상 정지와 같은 통로
            # (생존 신호의 정지 목록)로 세우고 임무는 SUSPENDED(PAUSED) 로 둠.
            # RESUME 이 임무를 중단된 단계부터 이어서 수행
            if cmd == 'PAUSE':
                r = self.robots[target]
                if r.estop:
                    return False, f'{target} is already stopped'
                r.estop = r.paused = True
                if r.route:
                    self._stop_route(r)
                if r.arm_busy:
                    self.io.cancel_arm(r.id)
                r.pending_goal = None
                self.io.log('PAUSE', robot_id=r.id, zone_id=r.node, reason=arg)
                if r.task and r.task.state == 'IN_PROGRESS':
                    self._suspend(r.task, 'PAUSED')
                return True, f'{target} paused'
            if cmd == 'ESTOP':  # 로봇 한 대 비상 정지
                r = self.robots[target]
                r.estop, r.paused = True, False
                if r.route:
                    self._stop_route(r)
                if r.arm_busy:
                    self.io.cancel_arm(r.id)
                r.pending_goal = None
                self.io.log('ESTOP', robot_id=r.id, zone_id=r.node, reason=arg)
                if r.task and r.task.state == 'IN_PROGRESS':
                    self._suspend(r.task, 'E_STOP')
                return True, f'{target} stopped'
            if cmd == 'SET_STANDBY':  # 1/true/on 이면 켬
                self.use_standby = (target or arg).lower() in ('1', 'true', 'on')
                return True, f'standby={self.use_standby}'
            if cmd == 'RESUME':  # 정지 해제, 보류 임무 재개
                r = self.robots[target]
                r.estop, r.paused, r.fail_count = False, False, 0
                self.io.log('RESUME', robot_id=r.id, zone_id=r.node)
                if r.task and r.task.state == 'SUSPENDED':
                    return self.command('RETRY_TASK', r.task.id)
                if r.task is None:
                    self._go_home(r)
                return True, f'{target} resumed'
            if cmd == 'RETRY_TASK':  # target: 보류된 임무 id
                t = self.tasks[target]
                if t.state != 'SUSPENDED':
                    return False, 'task is not suspended'
                if t.type == 'COOK':
                    t.state = 'IN_PROGRESS'
                    self._event(t, 'RESUMED')
                    return True, 'cook job resumed'
                r = self.robots[t.robot_id]
                if r.estop:
                    return False, 'robot is still in E-STOP; RESUME it first'
                t.state, t.reason = 'IN_PROGRESS', ''
                r.fail_count = 0
                # [수정 2026-11-18] W8-3: 재개하면 계획 실패 시간을 새로 셈
                r.plan_fail = None
                self._event(t, 'RESUMED')
                self._run_phase(r)
                return True, 'task resumed from the failed step'
            if cmd == 'REASSIGN':  # 보류 임무를 대기열로
                t = self.tasks[target]
                if t.state != 'SUSPENDED' or t.type not in AMR_TASKS:
                    return False, 'only a suspended AMR task can be reassigned'
                if t.carrying:
                    return False, 'food/dishes already loaded on the AMR: cannot hand over, remake required'
                old = self.robots.get(t.robot_id)
                if old:
                    old.task = None
                    if not old.estop:
                        self._go_home(old)
                t.robot_id, t.state, t.pi, t.reason = '', 'PENDING', 0, ''
                self._event(t, 'REASSIGNED')
                return True, 'task returned to the queue'
            if cmd == 'CANCEL_TASK':  # 임무 취소, 로봇은 복귀
                t = self.tasks[target]
                if t.state in ('DONE', 'CANCELED'):
                    return False, 'task already finished'
                r = self.robots.get(t.robot_id)
                t.state = 'CANCELED'
                self._event(t, 'CANCELED', arg)
                if r and r.task is t:
                    r.task = None
                    if not r.estop:
                        if r.route:
                            self._stop_route(r)
                        self._go_home(r)
                return True, 'task canceled'
        except KeyError as e:
            return False, f'unknown target {e}'
        return False, f'unknown command {cmd}'

    # ------------------------------------------------------------------ cooking cell
    def _recipe(self, menu):
        """메뉴의 조리 공정 목록을 만든다(시간은 cook_time_scale 로 나눔).

        공정: ('acq', 자원) 한꺼번에 잡기, ('rel', 자원) 놓기,
        ('arm', 'A'|'B', 작업, 초), ('timer', 초, 이름), ('doneness',) 익힘
        판정, ('ready', 받는 곳). 'SLOT:' 자원은 받는 곳 한 칸.
        """
        s = self.cook_scale
        fry = [('acq', {'ARM_A', 'FRYER'}), ('arm', 'A', 'LOAD_BASKET', 3.0), ('arm', 'A', 'DROP_IN_FRYER', 2.0),
               ('rel', {'ARM_A'}), ('timer', 600.0 / s, 'FRYING'), ('doneness',)]
        if menu == 'FRIED':
            return fry + [('acq', {'ARM_A', 'SLOT:FRY_PICKUP'}), ('arm', 'A', 'LIFT_DRAIN', 3.0), ('arm', 'A', 'PLATE', 3.0),
                          ('arm', 'A', 'PLACE_HANDOFF', 2.0), ('rel', {'ARM_A', 'FRYER'}), ('ready', 'FRY_PICKUP')]
        if menu == 'SEASONED':
            return fry + [('acq', {'ARM_A', 'ARM_B', 'WOK', 'SLOT:WOK_PICKUP'}), ('arm', 'A', 'LIFT_DRAIN', 3.0),
                          ('arm', 'A', 'TO_WOK', 3.0), ('rel', {'ARM_A', 'FRYER'}), ('arm', 'B', 'ADD_SAUCE', 2.0),
                          ('arm', 'B', 'STIR_FRY', 60.0 / s), ('arm', 'B', 'PLATE', 3.0), ('arm', 'B', 'PLACE_HANDOFF', 2.0),
                          ('rel', {'ARM_B', 'WOK'}), ('ready', 'WOK_PICKUP')]
        if menu == 'FRIED_RICE':
            return [('acq', {'ARM_A', 'ARM_B', 'WOK', 'SLOT:WOK_PICKUP'}), ('arm', 'A', 'ADD_INGREDIENTS', 3.0),
                    ('rel', {'ARM_A'}), ('arm', 'B', 'STIR_FRY', 300.0 / s), ('arm', 'B', 'PLATE', 3.0),
                    ('arm', 'B', 'PLACE_HANDOFF', 2.0), ('rel', {'ARM_B', 'WOK'}), ('ready', 'WOK_PICKUP')]
        raise ValueError(f'unknown menu {menu}')

    def _cook_tick(self):
        """조리 작업마다 공정을 진행한다(한 번에 즉시 끝나는 공정 최대 8개)."""
        for j in list(self.cook_jobs):
            t = j.task
            if t.state != 'IN_PROGRESS':
                if t.state in ('CANCELED', 'DONE'):
                    # 잡은 팔·조리기를 풂. 받는 곳 접시 수(slots)는 줄이지 않음
                    # (받는 곳을 잡은 뒤 취소되면 수가 남는지 확인 필요)
                    self._cook_release(j, set(self.res_owner))
                    self.cook_jobs.remove(j)
                continue
            for _ in range(8):                              # advance through instant ops
                if j.busy or j.pc >= len(j.ops):
                    break
                op = j.ops[j.pc]
                if op[0] == 'acq':                          # all-or-nothing: never wait while holding an arm
                    arms = {x for x in op[1] if not x.startswith('SLOT:')}
                    slots = [x[5:] for x in op[1] if x.startswith('SLOT:')]
                    if any(self.res_owner[a] not in (None, t.id) for a in arms) or \
                       any(self.slots[s] >= self.slot_cap for s in slots):
                        break
                    for a in arms:
                        self.res_owner[a] = t.id
                    for s in slots:
                        self.slots[s] += 1
                    if j.pc == 0:
                        j.label = 'COOKING'
                        self._event(t, 'COOKING')
                    j.pc += 1
                elif op[0] == 'rel':  # 자원 놓기
                    self._cook_release(j, op[1])
                    j.pc += 1
                elif op[0] == 'arm':  # 조리 팔 작업(끝나면 on_arm_result)
                    j.busy, j.label = True, op[2]
                    params = {'cook_task_id': t.id, 'menu': t.menu}
                    if op[2] == 'DROP_IN_FRYER':
                        params['fry_time'] = 600.0 / self.cook_scale
                    self.io.arm_job('cook_arm_a' if op[1] == 'A' else 'cook_arm_b', t.id, op[2], op[3], params)
                    self.io.log('COOK_STEP', task_id=t.id, order_id=t.order_id, robot_id='cook_arm_' + op[1].lower(),
                                result=op[2])
                elif op[0] == 'timer':  # 튀김 등 시간 대기
                    if j.until == 0.0:
                        j.until, j.label = self.now + op[1], op[2]
                        self.io.log('COOK_STEP', task_id=t.id, order_id=t.order_id, result=op[2], reason=f'{op[1]:.1f}s')
                        break
                    if self.now < j.until:
                        break
                    j.until = 0.0
                    j.pc += 1
                elif op[0] == 'doneness':  # 익힘 판정(5초 안에 없으면 완료)
                    if not self.use_doneness:
                        j.pc += 1
                        continue
                    if j.wait_doneness_since is None:
                        j.wait_doneness_since, j.label = self.now, 'DONENESS_CHECK'
                    d = self.doneness.get(t.id)
                    fresh = d and d[1] >= j.wait_doneness_since
                    if not fresh and self.now - j.wait_doneness_since < 5.0:
                        break
                    decision = d[0] if fresh else 'DONE'           # AI server silent: degrade to timer only
                    self.io.log('DONENESS', task_id=t.id, order_id=t.order_id, result=decision,
                                reason='ai' if fresh else 'timeout_fallback')
                    j.wait_doneness_since = None
                    if decision == 'UNDERCOOKED' and j.retries < 2:
                        j.retries += 1
                        j.ops.insert(j.pc, ('timer', 120.0 / self.cook_scale, f'REFRY_{j.retries}'))
                        continue
                    j.pc += 1
                elif op[0] == 'ready':  # 조리 완료: 받는 곳에 놓임
                    t.state, t.finished_at, j.label = 'DONE', self.now, 'READY'
                    self.io.log('COOK_READY', task_id=t.id, order_id=t.order_id, zone_id=op[1],
                                reason=f'dur={self.now - t.created:.1f}')
                    self._event(t, 'READY', op[1])
                    self.cook_jobs.remove(j)
                    break

    def _cook_release(self, j, names):
        """작업 j 가 잡은 자원 중 names 에 든 것을 놓는다(SLOT: 제외)."""
        for a in names:
            if not a.startswith('SLOT:') and self.res_owner.get(a) == j.task.id:
                self.res_owner[a] = None

    # ------------------------------------------------------------------ state for UI
    def robot_state(self, r):
        """화면에 보일 로봇 상태 이름(MOVING, SERVING, E_STOP 등).

        Args:
            r: 로봇.

        Returns:
            상태 이름 문자열.
        """
        # [수정 2026-11-20] T-49: 위치를 모르는 로봇(LOCALIZING 등)
        if r.localizing and not r.online:
            return r.localizing
        if r.estop:
            # [수정 2026-11-17] UR-18: 일시 중단은 따로 표시
            return 'PAUSED' if r.paused else 'E_STOP'
        t = r.task
        if t and t.state == 'SUSPENDED':
            return 'SUSPENDED'
        if r.arm_busy:
            return {'LOAD': 'LOADING', 'UNLOAD': 'UNLOADING', 'COLLECT_DISHES': 'COLLECTING',
                    'RETURN_DISHES': 'RETURNING_DISHES'}.get(r.arm_busy, r.arm_busy)
        if t:
            if t.type == 'MOVE':
                return 'MOVING'
            if t.type == 'GUIDE':
                return 'GUIDING' if t.pi >= 2 else 'TO_START'
            if t.type == 'SERVE':
                return 'SERVING' if t.carrying else 'TO_PICKUP'
            return 'TO_DISH_RETURN' if t.carrying else 'TO_TABLE'
        if r.returning or r.route:
            return 'RETURNING'
        if r.node in self.graph.standby_nodes:
            return 'STANDBY'
        return 'CHARGING' if r.charging else 'IDLE'

    def active_grants(self):
        """(robot, task id, plan version, granted index) of every route that holds a permission: the node repeats
        them so that a lost TrafficGrant message cannot leave a robot waiting for ever."""
        return [(r.id, r.task.id if r.task else 'RETURN', r.plan_version, r.granted)
                for r in self.robots.values() if r.route and r.granted > 0 and not r.estop]

    def estopped(self):
        """비상 정지·일시 중단 중인 로봇 id 목록(생존 신호의 정지 목록)."""
        return [r.id for r in self.robots.values() if r.estop]

    def _off_node(self, r):
        """서 있는 로봇이 노드에서 off_node_dist 넘게 벗어났는지(화면·알람)."""
        return bool(r.online and not r.route and not r.heading
                    and math.dist((r.x, r.y), self.graph.nodes[r.node]) > self.off_node_dist)

    def _arm_job_of(self, arm):
        """Arm job a cooking arm ('A' / 'B') is running right now, '' when it stands still."""
        for j in self.cook_jobs:
            if j.busy and j.pc < len(j.ops) and j.ops[j.pc][0] == 'arm' and j.ops[j.pc][1] == arm:
                return j.ops[j.pc][2]
        return ''

    # [수정 2026-11-20] T-53: 화면의 '남은 거리'. 누적 주행 거리(r.dist)가
    # 아니라 지금 경로의 남은 길이(보고 위치 → 다음 노드 → 경로 끝)
    def _remaining(self, r: Robot) -> float:
        """현재 경로의 남은 거리(m)를 돌려준다.

        Args:
            r: 관제가 보는 로봇.

        Returns:
            보고 위치에서 아직 도착하지 않은 다음 경로 노드까지의 직선 거리와
            그 노드부터 경로 마지막 노드까지의 통로 길이 합. 경로가 없거나
            마지막 노드에 도착했으면 0.
        """
        if not r.route:
            return 0.0
        # idx 는 마지막으로 도착한 경로 칸(-1 이면 route[0] 으로 가는 중)
        k = max(r.idx + 1, 0)
        if k >= len(r.route):
            return 0.0
        nodes = [s.node for s in r.route[k:]]
        rest = sum(self.graph.dist(a, b)
                   for a, b in zip(nodes, nodes[1:], strict=False) if a != b)
        return math.dist((r.x, r.y), self.graph.nodes[nodes[0]]) + rest

    def snapshot(self):
        """화면용 전체 상태(/fms/state 의 JSON).

        Returns:
            알고리즘, 로봇, 최근 임무 40건, 락, 조리 셀, 지표를 담은 dict.
        """
        return {
            'now': self.now,
            'map_id': self.graph.map_id,
            'algorithms': {'scheduler': self.scheduler.name, 'planner': self.planner.name,
                           'schedulers': {k: v.description for k, v in SCHEDULERS.items()},
                           'planners': {k: v.description for k, v in PLANNERS.items()}, 'standby': self.use_standby},
            # [수정 2026-11-17] UR-17~21: paused, fault_since, at_home,
            # available, unavailable_reason, arm 추가. 일시 중단 중에는 로봇이
            # 보고하는 EMERGENCY_STOP(정지 목록에 든 결과)을 오류로 보이지 않음
            'min_battery': self.min_battery,
            'robots': [{'id': r.id, 'state': self.robot_state(r), 'node': r.node, 'heading': r.heading,
                        'device': device_state.mobile_state(self.robot_state(r), r.online,
                                                            error='' if r.paused else r.error),
                        'error': '' if r.paused else r.error,
                        'paused': r.paused, 'fault_since': dict(r.fault_since),
                        'at_home': r.node == r.home and not r.heading and not r.route,
                        'available': self._available(r),
                        'unavailable_reason': self._unavailable_reason(r),
                        'arm': self._serving_arm(r), 'off_node': self._off_node(r), 'yield_to': r.yield_to or r.yield_note,
                        'x': r.x, 'y': r.y, 'yaw': r.yaw, 'battery': round(r.battery, 1), 'charging': r.charging,
                        'task': r.task.id if r.task else '', 'task_type': r.task.type if r.task else '',
                        'carrying': bool(r.task and r.task.carrying), 'plan_version': r.plan_version,
                        'blocked_by': r.blocked_by if r.wait_since is not None else '', 'online': r.online,
                        'route': [s.node for s in r.route[max(r.idx, 0):]] if r.route else [],
                        # [수정 2026-11-20] T-53: remaining = 현재
                        # 경로의 남은 거리(m). dist 는 누적 주행 거리
                        # (벤치 지표, 화면 '누적 주행 거리' 항목)
                        'remaining': round(self._remaining(r), 2),
                        'dist': round(r.dist, 2)} for r in self.robots.values()],
            'tasks': [{'id': t.id, 'type': t.type, 'state': t.state, 'robot': t.robot_id, 'table': t.table_id,
                       'menu': t.menu, 'visit': t.visit_id, 'order': t.order_id, 'item': t.item_id,
                       'reason': t.reason, 'age': round(self.now - t.created, 1), 'carrying': t.carrying}
                      for t in list(self.tasks.values())[-40:]],
            'locks': dict(self.locks),
            'cooking': {'resources': dict(self.res_owner), 'slots': dict(self.slots),
                        'arms': {f'cook_arm_{a.lower()}': self._cook_arm_device(f'cook_arm_{a.lower()}', a)
                                 for a in 'AB'},
                        # [수정 2026-11-18] W2: v4 조리 작업 상태 state 추가
                        # (step 은 화면이 쓰는 공정 단계 이름이라 그대로 둠)
                        'jobs': [{'task': j.task.id, 'menu': j.task.menu,
                                  'step': j.label, 'state': _cook_state(j),
                                  'order': j.task.order_id,
                                  'retries': j.retries}
                                 for j in self.cook_jobs]},
            'metrics': {k: (round(v, 2) if isinstance(v, float) else v) for k, v in self.m.items()},
        }
