"""auto_localize.check_now: Nav2 실패 때 보정 후보가 없어도 예외 없이 끝남.

[수정 2026-11-23] 신규: T-56(R16-50). 실기기 runs/20261123_03 에서 Nav2 가
구간을 실패한 뒤 check_now 가 fix=None 에서 fix.yaw 로 AttributeError 를 내
경로 액션이 결과 없이 끝났음. ROS 실행기 없이 AutoLocalizer 를 직접 만듦.
"""
import math
import threading
import time
import types

from builtin_interfaces.msg import Time
import numpy as np

from frybot_mobile.auto_localize import AutoLocalizer


class _Log:
    """get_logger() 대역: 남긴 글을 모음."""

    def __init__(self) -> None:
        self.lines = []

    def warn(self, msg):
        self.lines.append(msg)

    info = error = warn


def _localizer(fix):
    """recheck 가 (점수, fix) 를 돌려주는 맞춤기를 단 AutoLocalizer."""
    log = _Log()
    node = types.SimpleNamespace(rid='pinky1', have_truth=True, x=0.582,
                                 y=-0.380, yaw=math.radians(177),
                                 get_logger=lambda: log)
    a = AutoLocalizer.__new__(AutoLocalizer)
    a.node, a.state, a.fix_t = node, '', -1e9
    a.p = {'monitor': True, 'fix_interval': 20.0, 'check_score': 0.012,
           'max_score': 0.04, 'improve': 0.005, 'warn_yaw_deg': 30.0}
    a.lock = threading.Lock()
    a.stats = {'checks': 0, 'fixes': 0, 'last_score': -1.0, 'last_t': 0.0,
               'skip': {}}
    now = time.time()
    stamp = Time(sec=int(now), nanosec=int((now % 1) * 1e9))
    a.scan = types.SimpleNamespace(header=types.SimpleNamespace(stamp=stamp),
                                   ranges=[0.12, 0.5, 0.8], angle_min=0.0,
                                   angle_increment=0.1)
    a.matcher = types.SimpleNamespace(
        points=lambda r, amin, inc: np.zeros((3, 2)),
        recheck=lambda *args, **kw: (0.0078, fix))
    a._ensure_matcher = lambda: True
    a.sent = []
    a._send = lambda x, y, yaw: a.sent.append((x, y, yaw))
    return a, log


def test_nav2_failure_without_fix_returns_false():
    """Nav2 실패 + 보정 후보 없음: 로그를 남기고 False(예외 없음)."""
    a, log = _localizer(None)
    assert a.check_now('Nav2 failed the segment to B2') is False
    assert any('no correction needed' in s for s in log.lines)
    assert a.sent == [] and not a.lock.locked()


def test_nav2_failure_with_fix_corrects():
    """보정 후보가 있으면 예전처럼 initialpose 를 보냄."""
    fix = types.SimpleNamespace(x=0.60, y=-0.38, yaw=math.radians(177),
                                score=0.003)
    a, _ = _localizer(fix)
    a.p['fix_interval'] = 0.0
    assert a.check_now('Nav2 failed the segment to B2') is True
    assert len(a.sent) == 2
