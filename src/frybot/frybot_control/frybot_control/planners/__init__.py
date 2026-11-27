"""Planner registry. Add a new algorithm: subclass PathPlanner and register it here.

경로 계획기(플래너) 등록부. PLANNERS 의 키가 런치 인자 planner:=,
관리자 화면 선택 상자, fleet_bench 의 --planners 에 쓰는 이름이다.
"""
from .base import PathPlanner, PlanRequest, ReservationTable, Step, INF
from .sipp import SippPlanner
from .cooperative_astar import CooperativeAStarPlanner
from .independent_astar import IndependentAStarPlanner
from .cbs import CbsPlanner

# 이름 -> 플래너 클래스. 기본 제공 4종(sipp, ccbs, cooperative_astar,
# independent_astar). 새 플래너는 이 튜플에 클래스를 더해 등록함
PLANNERS = {c.name: c for c in (SippPlanner, CbsPlanner, CooperativeAStarPlanner, IndependentAStarPlanner)}
# Open-RMF 비교용 플래너(rmf, rmf_nego)는 도우미 실행 파일이 있을 때만 등록
from . import rmf as _rmf
if _rmf.available():          # Open-RMF back end: only when its helper has been built (see planners/rmf.py)
    PLANNERS[_rmf.RmfPlanner.name] = _rmf.RmfPlanner
    PLANNERS[_rmf.RmfNegotiationPlanner.name] = _rmf.RmfNegotiationPlanner
DEFAULT_PLANNER = 'sipp'  # 관제(FleetCore)가 쓰는 기본 플래너 이름


def make_planner(name):
    """이름으로 플래너 객체를 새로 만든다.

    Args:
        name: PLANNERS 에 등록된 플래너 이름(예: 'sipp').

    Returns:
        PathPlanner 하위 클래스의 새 인스턴스.

    Raises:
        KeyError: 등록되지 않은 이름일 때.
    """
    if name not in PLANNERS:
        raise KeyError(f'unknown planner {name!r}; available: {sorted(PLANNERS)}')
    return PLANNERS[name]()
