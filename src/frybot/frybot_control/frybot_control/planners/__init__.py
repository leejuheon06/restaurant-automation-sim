"""Planner registry. Add a new algorithm: subclass PathPlanner and register it here."""
from .base import PathPlanner, PlanRequest, ReservationTable, Step, INF
from .sipp import SippPlanner
from .cooperative_astar import CooperativeAStarPlanner
from .independent_astar import IndependentAStarPlanner
from .cbs import CbsPlanner

PLANNERS = {c.name: c for c in (SippPlanner, CbsPlanner, CooperativeAStarPlanner, IndependentAStarPlanner)}
from . import rmf as _rmf
if _rmf.available():          # Open-RMF back end: only when its helper has been built (see planners/rmf.py)
    PLANNERS[_rmf.RmfPlanner.name] = _rmf.RmfPlanner
    PLANNERS[_rmf.RmfNegotiationPlanner.name] = _rmf.RmfNegotiationPlanner
DEFAULT_PLANNER = 'sipp'


def make_planner(name):
    if name not in PLANNERS:
        raise KeyError(f'unknown planner {name!r}; available: {sorted(PLANNERS)}')
    return PLANNERS[name]()
