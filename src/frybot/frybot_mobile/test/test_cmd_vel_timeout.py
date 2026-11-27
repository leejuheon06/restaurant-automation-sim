"""cmd_vel_timeout 기본값과 감시 동작.

[수정 2026-11-25] 신규 (MT-7): 기본값 0.5 -> 0.3 s. 노드 기본값, 런치의
"(node default)" 로그 값, 런치 인자 검사(비우면 노드 기본값, 0.5 를 주면
예전 값), 0.3 s 를 넘을 때만 0 RPM 을 보내는지 확인한다. 하드웨어 없이
Pinky 를 직접 만들고 모터 쓰기를 대역으로 바꾼다.
"""
import importlib
import importlib.util
import os
import sys
import types

import pytest

# PC 의 tf_transformations 는 NumPy 2 에서 import 가 실패함(발행은 대역)
sys.modules.setdefault('tf_transformations', types.SimpleNamespace(
    quaternion_from_euler=lambda *a: (0.0, 0.0, 0.0, 1.0)))
pinky_driver = importlib.import_module('frybot_mobile.pinky_driver')

_LAUNCH = os.path.join(os.path.dirname(__file__), '..', 'launch',
                       'robot.launch.py')


def _robot_launch():
    """robot.launch.py 를 모듈로 읽는다(launch 실행 없음)."""
    spec = importlib.util.spec_from_file_location('robot_launch', _LAUNCH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Motor:
    """DynamixelDriver 대역: 보낸 RPM 을 모음."""

    def __init__(self) -> None:
        self.sent = []

    def set_double_rpm(self, rpm_l, rpm_r):
        self.sent.append((rpm_l, rpm_r))
        return True


class _Log:
    """get_logger() 대역: 경고를 모음."""

    def __init__(self) -> None:
        self.warns = []

    def warn(self, msg, **_):
        self.warns.append(msg)


def _driver():
    """감시에 필요한 값만 채운 Pinky(기본값 그대로)."""
    p = pinky_driver.Pinky.__new__(pinky_driver.Pinky)
    p.driver = _Motor()
    p.cmd_timeout = pinky_driver.CMD_VEL_TIMEOUT_DEFAULT
    p._stop_pending = True    # 0 이 아닌 명령을 보낸 뒤
    p._zero_failed = False
    log = _Log()
    p.get_logger = lambda: log
    return p, log


def test_default_is_0_3():
    """노드 기본값과 런치 로그의 기본값이 0.3 s 로 같다."""
    assert pinky_driver.CMD_VEL_TIMEOUT_DEFAULT == 0.3
    assert _robot_launch().CMD_VEL_TIMEOUT_DEFAULT == \
        pinky_driver.CMD_VEL_TIMEOUT_DEFAULT


def test_launch_arg_empty_uses_node_default_and_0_5_overrides():
    """인자를 비우면 파라미터를 넘기지 않고(노드 기본값), 0.5 는 그대로."""
    params = _robot_launch().cmd_timeout_params
    assert params('') == {}
    assert params('0.5') == {'cmd_vel_timeout': 0.5}


@pytest.mark.parametrize('silent, stops', [(0.29, False), (0.31, True),
                                           (0.45, True)])
def test_watchdog_stops_after_0_3(monkeypatch, silent, stops):
    """기본값에서 0.3 s 를 넘겨 끊겼을 때만 0 RPM 을 보낸다."""
    p, log = _driver()
    monkeypatch.setattr(pinky_driver.time, 'monotonic', lambda: 100.0)
    p._cmd_time = 100.0 - silent
    p._watch_cmd_vel()
    assert (p.driver.sent == [(0, 0)]) is stops
    assert bool(log.warns) is stops
