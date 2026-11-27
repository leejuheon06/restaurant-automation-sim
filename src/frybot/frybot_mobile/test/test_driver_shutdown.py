"""종료 때 토크 끄기가 신호·끊긴 통신에도 끝까지 도는지.

[수정 2026-11-25] 신규 (T-59): 실기기에서 (1) SIGINT 의 KeyboardInterrupt 가
다이나믹셀 통신 도중에 나면 포트가 '사용 중'으로 남아 terminate 의 쓰기가
모두 COMM_PORT_BUSY 로 실패했고 (2) 두 번째 SIGINT 가 terminate 를 끊었다.
하드웨어·ROS 없이 포트·패킷 처리기와 rclpy 를 대역으로 바꾼다.
"""
import importlib
import os
import signal
import sys
import time
import types

import pytest

sys.modules.setdefault('tf_transformations', types.SimpleNamespace(
    quaternion_from_euler=lambda *a: (0.0, 0.0, 0.0, 1.0)))
pinky_driver = importlib.import_module('frybot_mobile.pinky_driver')
# [수정 2026-11-26] T-62: 종료 중 publish 가 내는 예외 타입
# (rclpy 내부와 같은 가져오기 경로)
RCLError = importlib.import_module(
    'rclpy.impl.implementation_singleton').rclpy_implementation.RCLError
dyn = importlib.import_module('frybot_mobile.dynamixel_driver')

COMM_PORT_BUSY = -1000  # dynamixel_sdk 의 값


class _Port:
    """PortHandler 대역."""

    def __init__(self, busy: bool) -> None:
        self.is_using = busy
        self.closed = False

    def closePort(self):  # noqa: N802 - SDK 이름
        self.closed = True


class _Packets:
    """PacketHandler 대역: 실제 SDK 처럼 is_using 이면 보내지 않음."""

    def __init__(self, fail_first: int = 0) -> None:
        self.torque = {}
        self.fail_left = fail_first

    def write1ByteTxRx(self, port, dxl_id, addr, value):  # noqa: N802
        if port.is_using:
            return COMM_PORT_BUSY, 0
        if addr == 64 and self.fail_left > 0:
            self.fail_left -= 1
            return -3001, 0  # 응답 없음
        if addr == 64:
            self.torque[dxl_id] = value
        return dyn.COMM_SUCCESS, 0


def _driver(busy=False, fail_first=0):
    d = dyn.DynamixelDriver.__new__(dyn.DynamixelDriver)
    d.ADDR_TORQUE_ENABLE, d.ADDR_LED_RED = 64, 65
    d.DXL_IDS = [1, 2]
    d.portHandler = _Port(busy)
    d.packetHandler = _Packets(fail_first)
    d.rpm = []
    d.set_double_rpm = lambda left, right: d.rpm.append((left, right)) or True
    return d


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(dyn.time, 'sleep', lambda s: None)


def test_terminate_clears_busy_port():
    """끊긴 통신이 남긴 is_using 이 있어도 토크를 끈다."""
    d = _driver(busy=True)
    assert d.terminate() is True
    assert d.packetHandler.torque == {1: 0, 2: 0}
    assert d.portHandler.closed


def test_terminate_retries_failed_torque_write():
    """토크 쓰기가 한 번 실패해도 다시 써서 성공한다."""
    d = _driver(fail_first=1)
    assert d.terminate() is True
    assert d.packetHandler.torque == {1: 0, 2: 0}


def test_terminate_reports_failure():
    """계속 실패하면 False 를 돌려준다(main 이 오류 로그)."""
    d = _driver(fail_first=99)
    assert d.terminate(retries=3) is False


@pytest.fixture
def _signals():
    old = {s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM)}
    yield
    for s, h in old.items():
        signal.signal(s, h)


def test_main_terminate_survives_second_sigint(monkeypatch, _signals):
    """spin 이 끝난 뒤 terminate 도중 SIGINT 가 와도 끝까지 돈다."""
    seen = {}

    class _Drv:
        def terminate(self):
            os.kill(os.getpid(), signal.SIGINT)   # launch 가 다시 보낸 신호
            time.sleep(0.05)
            seen['done'] = True
            return True

    class _Node:
        driver = _Drv()

        def get_logger(self):
            return types.SimpleNamespace(error=lambda m: None)

        def destroy_node(self):
            seen['destroyed'] = True

    def _init(args=None):
        # rclpy 가 넘겨 부를 Python 처리기는 KeyboardInterrupt 를 내지 않아야 함
        seen['handler'] = signal.getsignal(signal.SIGINT)

    def _spin(node):
        raise pinky_driver.ExternalShutdownException()

    monkeypatch.setattr(pinky_driver, 'Pinky', _Node)
    monkeypatch.setattr(pinky_driver, 'rclpy', types.SimpleNamespace(
        init=_init, spin=_spin,
        try_shutdown=lambda: seen.setdefault('shutdown', True)))
    pinky_driver.main()
    assert seen['handler'] is pinky_driver._ignore_signal
    assert seen.get('done') and seen.get('destroyed') and seen.get('shutdown')


def test_main_without_node(monkeypatch, _signals):
    """Pinky() 생성 중 예외면 terminate 를 부르지 않고 예외를 그대로 낸다."""
    def _boom():
        raise RuntimeError('serial open failed')

    monkeypatch.setattr(pinky_driver, 'Pinky', _boom)
    monkeypatch.setattr(pinky_driver, 'rclpy', types.SimpleNamespace(
        init=lambda args=None: None, spin=lambda n: None,
        try_shutdown=lambda: None))
    with pytest.raises(RuntimeError):
        pinky_driver.main()


# [수정 2026-11-26] T-62: 스택 종료 때 컨텍스트가 내려간 뒤 30 Hz 타이머의
# publish 가 RCLError 를 내 종료 코드 1 이 되던 것. 종료 중의 RCLError 만
# 정상 종료로 받고, 컨텍스트가 살아 있을 때의 RCLError 는 다시 올리는지.
def _rcl_main(monkeypatch, ok: bool) -> dict:
    """spin 이 RCLError 를 내는 main 을 준비하고 기록 dict 를 돌려준다."""
    seen = {}

    class _Drv:
        def terminate(self):
            seen['terminate'] = True
            return True

    class _Node:
        driver = _Drv()

        def get_logger(self):
            return types.SimpleNamespace(error=lambda m: None)

        def destroy_node(self):
            seen['destroyed'] = True

    def _spin(node):
        raise RCLError(
            "Failed to publish: publisher's context is invalid")

    monkeypatch.setattr(pinky_driver, 'Pinky', _Node)
    monkeypatch.setattr(pinky_driver, 'rclpy', types.SimpleNamespace(
        init=lambda args=None: None, spin=_spin, ok=lambda: ok,
        try_shutdown=lambda: seen.setdefault('shutdown', True)))
    return seen


def test_main_rclerror_after_shutdown_is_clean(monkeypatch, _signals):
    """컨텍스트가 내려간 뒤의 RCLError 는 정상 반환, terminate 는 불림."""
    seen = _rcl_main(monkeypatch, ok=False)
    assert pinky_driver.main() is None
    assert seen.get('terminate') and seen.get('destroyed')
    assert seen.get('shutdown')


def test_main_rclerror_while_running_is_raised(monkeypatch, _signals):
    """컨텍스트가 살아 있을 때의 RCLError 는 숨기지 않고 다시 올린다."""
    seen = _rcl_main(monkeypatch, ok=True)
    with pytest.raises(RCLError):
        pinky_driver.main()
    assert seen.get('terminate') and seen.get('shutdown')
