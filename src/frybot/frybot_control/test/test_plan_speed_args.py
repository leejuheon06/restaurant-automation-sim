"""fleet_bench 계획 속도 인자 확인 (작업 지시서 4 W10).

--plan-speed 는 실기기 런치의 speed:= 처럼 일반 속도만 바꾸고, 손님 안내
구간의 계획 속도(안내 속도 x 배율)는 그대로여야 한다. 관제가 플래너에
넘긴 PlanRequest 의 속도를 모아 본다. ROS 없이 실행된다.

    cd ~/frybot_ws && source install/setup.bash
    python3 -m pytest src/frybot/frybot_control/test -q
"""
# [수정 2026-11-18] W10: 신규
import os

from frybot_control import offline_bench


def _plan_speeds(**plan) -> set[float]:
    """normal 작업 부하를 60초 돌리며 관제가 계획한 속도들을 모음.

    Args:
        **plan: OfflineWorld 의 계획 인자(plan_speed 등).

    Returns:
        PlanRequest.speed 값(소수 넷째 자리) 집합.
    """
    os.environ['FRYBOT_MAP_ID'] = ''           # 가상 매장 도면(proto)
    script = offline_bench.SCENARIOS['normal']
    w = offline_bench.OfflineWorld('min_cost_eta_rh', 'sipp', script, **plan)
    seen = set()
    plan_fn = w.core.planner.plan

    # 원래 plan 을 감싸 요청 속도를 기록한 뒤 그대로 계획함
    def spy(graph, req, table):
        seen.add(round(req.speed, 4))
        return plan_fn(graph, req, table)

    w.core.planner.plan = spy
    while w.t < 60.0:
        w.step()
    return seen


def test_default_plan_speeds():
    """인자가 없으면 일반 0.08 x 0.9, 안내 0.05 x 0.9."""
    assert _plan_speeds() == {0.072, 0.045}


def test_plan_speed_keeps_guide_speed():
    """--plan-speed 0.135 는 일반 속도만 바꾸고 안내는 0.045 m/s."""
    assert _plan_speeds(plan_speed=0.135) == {0.1215, 0.045}


def test_plan_speed_factor_and_guide_speed():
    """배율 1.0 과 안내 속도 인자는 그대로 곱해짐."""
    assert _plan_speeds(plan_speed=0.135, plan_speed_factor=1.0) == {
        0.135, 0.05}
    assert _plan_speeds(plan_speed=0.135, plan_guide_speed=0.04) == {
        0.1215, 0.036}
