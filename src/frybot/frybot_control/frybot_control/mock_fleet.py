"""관제 코어(FleetCore)에 붙이는 모의 로봇 묶음 (ROS 없음).

fleet_bench(offline_bench.py)와 replay_run(replay_run.py)이 같이 씀.
관제 코어는 실기기와 같은 코드이고, 로봇만 모의로 바꿈.

모의 로봇의 시간 모델(TimeModel)
    구간 시간 = (구간 지연 + 거리 / 속도) x 흔들림
    흔들림은 구간마다 1 ± jitter 범위의 난수이고 씨앗으로 재현됨.
    jitter = 0 이면 난수를 뽑지 않아, 예전 모의 로봇과 같은 값이 나옴.

함께 세는 지표
    min_sep         로봇 중심 간 최소 거리(m)
    close_time      두 로봇이 SAFE_DIST 미만으로 있던 시간(초)
    stall30         임무가 있는데 30초 넘게 움직이지 않은 횟수(참고용)
    unplanned30     계획에 없는 정지가 30초 넘게 이어진 횟수
                    ([수정 2026-11-18] W7: 통과 기준. 락 대기, 경로·예정 없음,
                    계획 실패 뒤 재시도 대기)
    intended30      의도된 대기가 30초를 넘은 횟수(참고용. 계획상 출발 시각 전,
                    비켜 선 뒤 상대를 기다림, 팔 작업)
    intended_wait_max  가장 길게 이어진 의도된 대기(초)
    intended20      의도된 대기가 20초 넘게 이어진 횟수
                    ([수정 2026-11-18] W11: 통과 기준. 20초를 넘은 순간의
                    종류별로 intended20_plan(계획상 출발 시각 전),
                    intended20_yield(비켜 선 뒤 대기), intended20_arm(팔
                    작업)도 셈)
    unplanned20     계획에 없는 정지가 20초 넘게 이어진 횟수(참고용)
    start_delay_sum 구간 출발 지연으로 서 있던 시간 합계(초, 참고용)
                    ([수정 2026-11-18] W10: 실행 모델의 구간 지연. 계획에
                    없는 정지도 의도된 대기도 아니어서 30초 판정에서 뺌)
    plan_fail_run   같은 로봇의 PLAN_FAIL 최대 연속 횟수(참고용)
    plan_fail_long  같은 목적지 계획 실패가 20초 넘게 이어진 묶음 수
                    ([수정 2026-11-18] W4: 통과 기준. 계획이 성공하거나
                    목적지가 바뀌면 묶음이 끝나고, 실행 끝까지 이어진
                    묶음도 셈)
"""

# [수정 2026-11-18] W3: 신규. offline_bench.SimRobot·OfflineWorld 와
# replay_run.Bot·ReplayWorld 에 따로 있던 모의 로봇을 하나로 모음
import dataclasses
import itertools
import math
import random

from . import fleet_core as _fleet_core
from .fleet_core import FleetCore
from .fleet_core import FleetIO
from .layout import SAFE_DIST

# 임무 중 정지를 stall30·unplanned30·intended30 으로 세는 기준(초)
STALL_SEC = 30.0
# [수정 2026-11-18] W11: 의도된 대기 판정 기준(초)과 계획에 없는 정지 참고 기준
INTENDED_LIMIT_SEC = 20.0  # intended20(판정) 기준
UNPLANNED_REF_SEC = 20.0  # unplanned20(참고) 기준


# [수정 2026-11-18] W8-1: 해시 씨앗을 0으로 두고 다시 실행하던 fix_hash_seed 를
# 지움. 관제 코어가 정렬된 순서로 판단하게 고쳐 필요 없고, 남겨 두면 같은
# 문제가 다시 생겨도 가려짐
# [수정 2026-11-18] W4: 같은 목적지 계획 실패 묶음이 이 시간(초)을 넘으면 1건
# [수정 2026-11-18] W8-3: 관제의 보류 기준(fleet_core.PLAN_FAIL_SUSPEND_SEC)과
# 같은 값을 씀
PLAN_FAIL_LONG_SEC = _fleet_core.PLAN_FAIL_SUSPEND_SEC
# [수정 2026-11-18] W7: 서 있는 이유
INTENDED = 'intended'  # 의도된 대기(_stand_kind 반환값)
UNPLANNED = 'unplanned'  # 계획에 없는 정지
# [수정 2026-11-18] W10: 실행 모델이 구간마다 출발 전에 쓰는 시간
START_DELAY = 'start_delay'  # 구간 출발 지연(30초 판정 제외)


@dataclasses.dataclass
class TimeModel:
    """모의 로봇이 한 구간을 가는 데 걸리는 시간 모델.

    Attributes:
        name: 모델 이름.
        speed: 움직이는 동안의 속도(m/s).
        overhead: 구간을 시작하기 전의 고정 지연(초).
        jitter: 구간 시간에 곱하는 난수의 폭(0.2 이면 0.8~1.2배).
        guide_speed: 손님 안내(GUIDE) 구간의 속도. None 이면 speed.
    """

    name: str
    speed: float
    overhead: float = 0.0
    jitter: float = 0.0
    guide_speed: float | None = None

    def segment_time(self, dist: float, mode: str = 'NORMAL') -> float:
        """흔들림 없이 한 구간을 가는 데 걸리는 시간(초).

        Args:
            dist: 구간 거리(m).
            mode: 구간 방식(NORMAL·GUIDE·YIELD). GUIDE 만 안내 속도.

        Returns:
            overhead + dist / 속도(초).
        """
        return self.overhead + dist / self.speed_of(mode)

    def speed_of(self, mode: str) -> float:
        """구간 방식에 따른 속도(m/s).

        Args:
            mode: 구간 방식. 'GUIDE' 이고 guide_speed 가 있을 때만 안내
                속도, 나머지는 speed.

        Returns:
            속도(m/s).
        """
        if mode == 'GUIDE' and self.guide_speed is not None:
            return self.guide_speed
        return self.speed


# 11-16 실기기 실행(run_20261116_175751, 구간 147개)에서 맞춘 값
MEASURED_SPEED = 0.135  # 주행 속도(m/s)
MEASURED_OVERHEAD = 2.27  # 구간 지연(초)


@dataclasses.dataclass
class Bot:
    """모의 로봇 한 대의 상태."""

    id: str  # 로봇 이름(pinkyN)
    x: float = 0.0  # 지도 좌표(m)
    y: float = 0.0
    yaw: float = 0.0  # 방향(rad). 움직일 때만 갱신
    # 받은 경로 [(노드, x, y), ...]. None 이면 경로 없음(서 있음)
    route: list | None = None
    pv: int = 0  # 지금 경로의 번호(plan_version)
    granted: int = 0  # 허가받은 마지막 경로 인덱스
    reached: int = 0  # 도착한 마지막 경로 인덱스(-1: 첫 노드로 가는 중)
    mode: str = 'NORMAL'  # 구간 방식(NORMAL·GUIDE·YIELD)
    seg: tuple | None = None  # 지금 가는 구간 (pv, 목표 인덱스)
    hold: float = 0.0  # 이 구간 출발 전 남은 지연(초)
    factor: float = 1.0  # 이 구간의 흔들림 배율(시간에 곱함)
    # [수정 2026-11-18] W10: 이번 단계에 구간 출발 지연으로 서 있었는지
    delayed: bool = False


class MockFleet(FleetIO):
    """FleetCore 에 모의 로봇을 붙여 시간 순서대로 실행함.

    Attributes:
        core: 관제 코어.
        bots: 로봇 id -> Bot.
        events: 관제 로그(시각 t 와 event, robot_id 등).
        task_events: 관제가 낸 임무 이벤트.
    """

    def __init__(
        self,
        robot_ids: list[str],
        model: TimeModel,
        dt: float = 0.1,
        seed: int = 0,
        **core_args,
    ) -> None:
        """모의 함대를 만든다.

        Args:
            robot_ids: 로봇 이름 목록.
            model: 모의 로봇 시간 모델.
            dt: 한 단계의 시간(초).
            seed: 흔들림 난수 씨앗.
            **core_args: FleetCore 에 넘길 인자.
        """
        self.dt, self.t, self.model = dt, 0.0, model  # t: 모의 시각(초)
        # [수정 2026-11-18] W8-1: 관제 코어의 난수도 같은 씨앗으로 재현
        core_args.setdefault('rng_seed', seed)
        self.core = FleetCore(self, robot_ids=robot_ids, **core_args)
        self.bots = {rid: Bot(rid) for rid in robot_ids}
        # 관제 코어가 정한 출발 위치(홈 노드)에 모의 로봇을 놓음
        for rid, robot in self.core.robots.items():
            self.bots[rid].x, self.bots[rid].y = robot.x, robot.y
        # 다음 단계에 수락 알림(index 0)을 보낼 (로봇, 경로 번호)
        self.accepted: list[tuple[str, int]] = []
        # 진행 중인 팔 작업 (끝날 시각, 팔 id, 임무 id)
        self.arm: list[tuple[float, str, str]] = []
        self.events: list[dict] = []
        self.task_events: list[dict] = []
        self._rng = random.Random(seed)  # 구간 흔들림용 난수
        self.min_sep = 9.9  # 초기값은 충분히 큰 거리(m)
        self.close_time = 0.0
        self.stall30 = 0
        # [수정 2026-11-18] W7: 계획에 없는 정지 30초(판정), 의도된 대기 30초
        # (참고), 가장 길게 이어진 의도된 대기(초)
        self.unplanned30 = 0
        # [수정 2026-11-18] W8-3: 관제가 보류한 임무 수(TASK_SUSPEND)
        self.suspended = 0
        self.intended30 = 0
        self.intended_wait_max = 0.0
        # [수정 2026-11-18] W11: 의도된 대기 20초(판정)와 종류별 수, 계획에
        # 없는 정지 20초(참고), 20초를 넘은 의도된 대기의 위치 기록(분석용)
        self.intended20 = 0
        self.intended20_kind = {'plan': 0, 'yield': 0, 'arm': 0}
        self.unplanned20 = 0
        self.long_waits: list[dict] = []
        self._last_plan_wait: dict[str, str] = {}
        # [수정 2026-11-18] W10: 구간 출발 지연(실행 모델의 overhead)으로 서
        # 있던 시간 합계(초, 로봇 전체)
        self.start_delay_sum = 0.0
        # 로봇별 (서 있는 이유, 이어진 시간(초))
        self._stand: dict[str, tuple[str, float]] = {}
        self.plan_fail_run = 0
        self._fail_run: dict[str, int] = {}  # 로봇별 PLAN_FAIL 연속 횟수
        # [수정 2026-11-18] W4: 로봇별 진행 중인 실패 묶음 [목적지, 첫 시각,
        # 마지막 시각]과 20초를 넘은 묶음 목록 (로봇, 목적지, 첫, 마지막)
        self._fail_open: dict[str, list] = {}
        # [수정 2026-11-18] W6: 계획 ETA 대비 실제 소요. 로봇별로 처음 계획한
        # (목적지, 시각, ETA)를 두고, 그 목적지에 들어갈 때 비율을 남김
        self._eta_open: dict[str, tuple[str, float, float]] = {}
        self.eta_ratios: list[float] = []
        self.fail_long: list[tuple[str, str, float, float]] = []
        self._still: dict[str, float] = {}  # 로봇별 임무 중 정지 시간(초)

    def place(self, rid: str, node: str) -> None:
        """서 있는 로봇을 노드 위에 놓고 관제에 바로 알림.

        replay_run 이 실험 중 손으로 옮긴 로봇을 실제 출발 노드에 다시
        놓을 때 씀.

        Args:
            rid: 로봇 이름.
            node: 놓을 노드 이름.
        """
        bot = self.bots[rid]
        bot.x, bot.y = self.core.graph.nodes[node]
        self.core.on_robot_status(
            rid, bot.x, bot.y, bot.yaw, 100.0, False, 'IDLE'
        )

    # ---- FleetIO
    def send_route(
        self, robot_id, task_id, plan_version, mode, visit_id, steps
    ):
        """경로를 받음(NavigateRoute 목표에 해당).

        Args:
            robot_id: 로봇 이름.
            task_id: 임무 id(모의 로봇은 쓰지 않음).
            plan_version: 경로 번호. 허가는 이 번호가 같을 때만 받음.
            mode: 구간 방식(NORMAL·GUIDE·YIELD).
            visit_id: 방문 id(모의 로봇은 쓰지 않음).
            steps: 관제의 Step 목록(node 만 씀).
        """
        bot = self.bots[robot_id]
        nodes = self.core.graph.nodes
        bot.route = [(s.node,) + tuple(nodes[s.node]) for s in steps]
        bot.pv, bot.granted, bot.seg, bot.mode = plan_version, 0, None, mode
        # 이미 첫 노드에 서 있으면 첫 노드 도착(0)으로 치고, 아니면 -1 로
        # 두어 허가 없이 첫 노드까지 먼저 감(_move)
        first = bot.route[0]
        at_start = math.hypot(bot.x - first[1], bot.y - first[2]) < 1e-3
        bot.reached = 0 if at_start else -1
        if at_start:
            # 액션의 첫 피드백(ACCEPTED, index 0)에 해당
            self.accepted.append((robot_id, plan_version))

    def grant(self, robot_id, task_id, plan_version, index):
        """통행 허가를 받음.

        다른 경로 번호의 허가는 버림(옛 계획의 허가 무시).

        Args:
            robot_id: 로봇 이름.
            task_id: 임무 id(쓰지 않음).
            plan_version: 허가가 속한 경로 번호.
            index: 여기까지 가도 되는 경로 인덱스.
        """
        bot = self.bots[robot_id]
        if plan_version == bot.pv:
            bot.granted = index

    def cancel_route(self, robot_id):
        """경로 취소."""
        self.bots[robot_id].route = None

    def cancel_arm(self, arm_id):
        """팔 작업 취소(모의 팔은 시간만 재므로 할 일 없음)."""

    def arm_job(self, arm_id, task_id, job, duration, params):
        """팔 작업: duration 초 뒤에 성공으로 끝남.

        Args:
            arm_id: 팔 id(로봇 이름 또는 조리 팔).
            task_id: 임무 id.
            job: 작업 이름(모의에서는 쓰지 않음).
            duration: 작업 시간(초).
            params: 작업 인자(모의에서는 쓰지 않음).
        """
        self.arm.append((self.t + duration, arm_id, task_id))

    def task_event(self, ev):
        """임무 이벤트를 모아 둠."""
        self.task_events.append(ev)

    def log(self, event, **fields):
        """관제 로그를 시각과 함께 모으고 PLAN_FAIL 연속 횟수를 셈.

        Args:
            event: 이벤트 이름(PLAN, PLAN_FAIL, ZONE_ENTER 등).
            **fields: 로그 열. robot_id, task_id, zone_id, result, reason
                만 남김.
        """
        row = {
            k: fields.get(k, '')
            for k in ('robot_id', 'task_id', 'zone_id', 'result', 'reason')
        }
        row.update(t=self.t, event=event)  # 모의 시각(초)과 이벤트 이름
        self.events.append(row)
        rid = row['robot_id']
        self._track_eta(event, rid, row)
        if event == 'TASK_SUSPEND':
            self.suspended += 1
        # [수정 2026-11-18] W11: 계획 대기의 상대(분석용)
        if event == 'PLAN_WAIT' and rid:
            self._last_plan_wait[rid] = row['reason']
        # [수정 2026-11-18] W4: 같은 목적지 계획 실패 묶음(PLAN_FAIL 의
        # zone_id 가 목적지)
        if event == 'PLAN_FAIL' and rid:
            open_ = self._fail_open.get(rid)
            if open_ and open_[0] == row['zone_id']:
                open_[2] = self.t
            else:
                self._close_fail(rid)
                self._fail_open[rid] = [row['zone_id'], self.t, self.t]
            self._fail_run[rid] = self._fail_run.get(rid, 0) + 1
            self.plan_fail_run = max(self.plan_fail_run, self._fail_run[rid])
        elif event == 'PLAN' and rid:
            self._fail_run[rid] = 0
            self._close_fail(rid)
        elif event == 'REPLAN' and rid:
            # [수정 2026-11-18] W4: 재계획 성공도 실패 묶음을 끝냄
            self._close_fail(rid)

    def _track_eta(self, event: str, rid: str, row: dict) -> None:
        """PLAN 의 ETA 와 목적지 도착까지의 실제 시간을 맞춰 봄."""
        # 첫 PLAN 의 (목적지, 시각, ETA)를 열어 두고, 목적지가 바뀐
        # REPLAN 이면 버림. 그 목적지에 ZONE_ENTER 하면 비율을 남김
        # (ETA 1초 미만은 비율이 튀므로 뺌)
        if not rid:
            return
        if event == 'PLAN' and 'eta=' in row['reason']:
            eta = float(row['reason'].split('eta=')[1].split()[0])
            self._eta_open[rid] = (row['zone_id'], self.t, eta)
        elif event == 'REPLAN':
            open_ = self._eta_open.get(rid)
            if open_ and open_[0] != row['zone_id']:
                self._eta_open.pop(rid)
        elif event == 'ZONE_ENTER':
            open_ = self._eta_open.get(rid)
            if open_ and open_[0] == row['zone_id']:
                self._eta_open.pop(rid)
                if open_[2] >= 1.0:
                    self.eta_ratios.append((self.t - open_[1]) / open_[2])

    def _close_fail(self, rid: str) -> None:
        """로봇의 실패 묶음을 닫고 20초를 넘었으면 기록함."""
        open_ = self._fail_open.pop(rid, None)
        if open_ and open_[2] - open_[1] > PLAN_FAIL_LONG_SEC:
            self.fail_long.append((rid, open_[0], open_[1], open_[2]))

    def fail_long_all(self) -> list[tuple[str, str, float, float]]:
        """20초 넘은 실패 묶음 전체(아직 닫히지 않은 묶음 포함)."""
        out = list(self.fail_long)
        for rid, (dest, t0, t1) in self._fail_open.items():
            if t1 - t0 > PLAN_FAIL_LONG_SEC:
                out.append((rid, dest, t0, t1))
        return out

    # ---- 실행
    def report(self, bot: Bot) -> None:
        """로봇 상태 보고(RobotStatus 에 해당).

        배터리는 100, 충전 아님으로 고정함.

        Args:
            bot: 보고할 모의 로봇.
        """
        state = 'MOVING' if bot.route else 'IDLE'
        self.core.on_robot_status(
            bot.id, bot.x, bot.y, bot.yaw, 100.0, False, state
        )

    def _move(self, bot: Bot) -> None:
        """로봇을 한 단계(dt)만큼 다음 노드 쪽으로 움직임.

        허가받은 인덱스까지만 감. 첫 노드(reached == -1)는 허가 없이 감.
        구간을 새로 시작하면 흔들림 배율을 뽑고 출발 지연(hold)부터 씀.
        노드에 닿으면 관제에 진행(on_route_progress)을 알림.
        """
        tgt = bot.reached + 1
        if tgt >= len(bot.route):  # 경로 끝
            return
        if tgt > bot.granted and bot.reached != -1:  # 허가 대기
            return
        # 새 구간 시작: 흔들림 배율과 출발 지연을 정함
        if bot.seg != (bot.pv, tgt):
            jitter = self.model.jitter
            bot.factor = (
                1.0 + self._rng.uniform(-jitter, jitter)
                if jitter > 0.0
                else 1.0
            )
            bot.seg = (bot.pv, tgt)
            bot.hold = self.model.overhead * bot.factor
        # 출발 지연 중이면 이번 단계는 서 있음
        if bot.hold > 0.0:
            bot.hold -= self.dt
            bot.delayed = True
            return
        _, tx, ty = bot.route[tgt]
        dist = math.hypot(tx - bot.x, ty - bot.y)
        step = self.model.speed_of(bot.mode) / bot.factor * self.dt
        # 이번 단계에 닿지 못하면 목표 쪽으로 step 만큼만 감
        if dist > step:
            bot.yaw = math.atan2(ty - bot.y, tx - bot.x)
            bot.x += (tx - bot.x) / dist * step
            bot.y += (ty - bot.y) / dist * step
            return
        # 노드 도착. 진행 알림 중 관제가 새 경로를 보냈을 수 있어(pv
        # 바뀜), 같은 경로일 때만 경로를 끝냄
        bot.x, bot.y, bot.reached = tx, ty, tgt
        pv, last = bot.pv, tgt == len(bot.route) - 1
        self.core.on_route_progress(bot.id, pv, tgt)
        if last and bot.pv == pv:
            bot.route = None

    def move_robots(self) -> None:
        """수락 알림, 팔 결과, 로봇 이동·보고, 지표 갱신을 한 번 함."""
        # 경로 수락(첫 노드에 이미 있음) 알림
        for rid, pv in self.accepted:
            self.core.on_route_progress(rid, pv, 0)
        self.accepted = []
        # 시간이 다 된 팔 작업은 성공으로 알림
        for done in [x for x in self.arm if x[0] <= self.t]:
            self.arm.remove(done)
            self.core.on_arm_result(done[1], done[2], True)
        # 이동 전 위치(정지 판정용)
        before = {b.id: (b.x, b.y) for b in self.bots.values()}
        for bot in self.bots.values():
            bot.delayed = False
            if bot.route:
                self._move(bot)
            if bot.delayed:
                self.start_delay_sum += self.dt
            self.report(bot)
        # 로봇 간 최소 거리와 SAFE_DIST 미만으로 있던 시간
        closest = 9.9
        for a, b in itertools.combinations(self.bots.values(), 2):
            closest = min(closest, math.hypot(a.x - b.x, a.y - b.y))
        self.min_sep = min(self.min_sep, closest)
        if closest < SAFE_DIST - 1e-6:
            self.close_time += self.dt
        # 진행 중인 임무가 있는데 움직이지 않은 로봇의 정지 시간을 셈.
        # 움직였거나 임무가 없으면 0 으로 되돌림
        for bot in self.bots.values():
            task = self.core.robots[bot.id].task
            moved = math.dist(before[bot.id], (bot.x, bot.y)) > 1e-6
            if task is None or task.state != 'IN_PROGRESS' or moved:
                self._still[bot.id] = 0.0
                self._stand[bot.id] = ('', 0.0)
                continue
            old = self._still.get(bot.id, 0.0)
            self._still[bot.id] = old + self.dt
            if old < STALL_SEC <= old + self.dt:
                self.stall30 += 1
            # [수정 2026-11-18] W7: 서 있는 이유별로 이어진 시간을 따로 잼
            # [수정 2026-11-18] W10: 구간 출발 지연은 따로 둠(30초 판정 없음)
            kind = (START_DELAY if bot.delayed
                    else self._stand_kind(self.core.robots[bot.id]))
            prev_kind, held = self._stand.get(bot.id, ('', 0.0))
            held = held if prev_kind == kind else 0.0
            self._stand[bot.id] = (kind, held + self.dt)
            if kind == INTENDED:
                self.intended_wait_max = max(self.intended_wait_max,
                                             held + self.dt)
            if kind != START_DELAY and held < STALL_SEC <= held + self.dt:
                if kind == INTENDED:
                    self.intended30 += 1
                else:
                    self.unplanned30 += 1
            # [수정 2026-11-18] W11: 20초 기준(의도된 대기는 판정, 계획에 없는
            # 정지는 참고)
            if kind == INTENDED and (held < INTENDED_LIMIT_SEC
                                     <= held + self.dt):
                self._long_wait(self.core.robots[bot.id])
            if kind == UNPLANNED and (held < UNPLANNED_REF_SEC
                                      <= held + self.dt):
                self.unplanned20 += 1

    # [수정 2026-11-18] W7: 서 있는 이유(w5_trace.py 의 구분을 옮겨 옴)
    def _stand_kind(self, r) -> str:
        """임무 중 서 있는 로봇이 의도된 대기인지 계획에 없는 정지인지.

        Args:
            r: 관제 코어의 로봇.

        Returns:
            INTENDED(계획상 출발 시각 전, 비켜 선 뒤 상대를 기다림, 팔 작업)
            또는 UNPLANNED(락 대기, 경로·예정 없음, 계획 실패 뒤 재시도 대기).
        """
        if r.arm_busy:
            return INTENDED
        if r.pending_goal and r.yield_to:
            return INTENDED
        route = r.route
        if route and 0 <= r.idx < len(route) - 1 and r.idx == r.granted:
            timed = self.core.planner.coordinated and route[0].arrive > 0
            if timed and self.core.now < route[r.idx].depart - 0.05:
                return INTENDED
        return UNPLANNED

    # [수정 2026-11-18] W11: 의도된 대기의 종류와 위치 기록
    def _intended_kind(self, r) -> str:
        """의도된 대기의 종류. _stand_kind 와 같은 순서로 판단함.

        Args:
            r: 관제 코어의 로봇(의도된 대기 중).

        Returns:
            'arm'(팔 작업), 'yield'(비켜 선 뒤 대기) 또는 'plan'(계획상 출발
            시각 전).
        """
        if r.arm_busy:
            return 'arm'
        if r.pending_goal and r.yield_to:
            return 'yield'
        return 'plan'

    def _long_wait(self, r) -> None:
        """의도된 대기가 20초를 넘은 순간을 세고 위치를 남김.

        Args:
            r: 관제 코어의 로봇.
        """
        kind = self._intended_kind(r)
        self.intended20 += 1
        self.intended20_kind[kind] += 1
        task = r.task
        phase = ''
        if task and 0 <= task.pi < len(task.phases):
            phase = str(task.phases[task.pi])
        if kind == 'yield':
            whom = r.yield_to
        elif kind == 'plan':
            whom = self._last_plan_wait.get(r.id, '')
        else:
            whom = ''
        self.long_waits.append(dict(
            t=round(self.t, 1), robot=r.id, kind=kind, node=r.node,
            task=task.id if task else '', type=task.type if task else '',
            phase=phase, pi=task.pi if task else -1, whom=whom))

    def step(self) -> None:
        """한 단계(dt 초) 진행함."""
        self.t += self.dt
        self.move_robots()
        self.core.tick(self.t)

    def idle(self) -> bool:
        """모든 로봇이 할 일 없이 서 있는지."""
        return all(
            r.task is None and not r.route and not r.pending_goal
            for r in self.core.robots.values()
        )
