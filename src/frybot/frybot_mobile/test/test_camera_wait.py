"""auto_localize._ask_camera: 늦게 나타나는 서비스와 늦은 응답을 기다림.

[수정 2026-11-23] 신규: T-57. 19 1회차(세 대 동시 기동)에서 세 대 모두
3 s 안에 /frybot/spot_check 를 찾지 못했고(19-B 진단: 기동 중 생긴 참가자는
발견에 20~28 s), 찾은 뒤 첫 요청도 늦게 도착했음. ROS 실행기 없이 가짜
클라이언트로 시간 흐름만 흉내 냄(대기 상한은 짧게 줄여 씀).
"""
import threading
import time
import types

from frybot_mobile.auto_localize import AutoLocalizer


class _Log:
    """get_logger() 대역: 남긴 글을 모음."""

    def __init__(self) -> None:
        self.lines = []

    def info(self, msg):
        self.lines.append(msg)

    warn = error = info


class _Future:
    """rclpy Future 대역(결과·완료 콜백·취소)."""

    def __init__(self) -> None:
        self._res = None
        self._done = False
        self._cbs = []
        self.cancelled = False

    def add_done_callback(self, cb):
        self._cbs.append(cb)

    def set_result(self, res):
        self._res, self._done = res, True
        for cb in self._cbs:
            cb(self)

    def done(self):
        return self._done

    def result(self):
        return self._res

    def cancel(self):
        self.cancelled = True


class _Client:
    """SpotCheck 클라이언트 대역.

    appear: 만든 뒤 서비스가 보이기까지(s, None 이면 끝까지 안 보임).
    answer: 몇 번째 요청부터(0 부터) 답하는지(None 이면 답하지 않음).
    delay: 답하는 요청의 응답 지연(s).
    """

    def __init__(self, appear, answer=0, delay=0.05, scores=(0.5, 0.0)):
        self.t0 = time.monotonic()
        self.appear, self.answer, self.delay = appear, answer, delay
        self.scores = scores
        self.calls = []

    def wait_for_service(self, timeout_sec):
        if self.appear is None:
            time.sleep(timeout_sec)
            return False
        left = self.t0 + self.appear - time.monotonic()
        if left > timeout_sec:
            time.sleep(timeout_sec)
            return False
        time.sleep(max(left, 0.0))
        return True

    def call_async(self, req):
        fut = _Future()
        k = len(self.calls)
        self.calls.append(fut)
        if self.answer is not None and k >= self.answer:
            res = types.SimpleNamespace(ok=True, score=list(self.scores),
                                        reason='OK test')
            threading.Timer(self.delay, fut.set_result, (res,)).start()
        return fut


def _localizer(cli, wait=1.0, timeout=0.2):
    """가짜 클라이언트를 단 AutoLocalizer(카메라 문의 부분만)."""
    log = _Log()
    a = AutoLocalizer.__new__(AutoLocalizer)
    a.node = types.SimpleNamespace(rid='pinky1', get_logger=lambda: log)
    a.p = {'camera_timeout': timeout, 'camera_wait': wait,
           'camera_hi': 0.15, 'camera_lo': 0.05, 'camera_sep': 0.30}
    a.cli = cli
    a.cli_t = cli.t0
    return a, log


CANDS = [types.SimpleNamespace(x=0.09, y=-0.55),
         types.SimpleNamespace(x=1.64, y=0.16)]


def test_late_service_still_answers():
    """서비스가 0.5 s 뒤에 보여도(예전 0.2 s 대기로는 못 찾음) 고름."""
    a, log = _localizer(_Client(appear=0.5))
    k, why = a._ask_camera(CANDS)
    assert k == 0, why
    assert any('service found after' in s for s in log.lines)
    assert any('answer after' in s for s in log.lines)


def test_lost_first_request_is_resent():
    """첫 요청이 답을 못 받으면 남은 시간 안에서 다시 요청해 고름."""
    cli = _Client(appear=0.0, answer=1)
    a, _ = _localizer(cli)
    k, why = a._ask_camera(CANDS)
    assert k == 0, why
    assert len(cli.calls) >= 2 and cli.calls[0].cancelled


def test_late_first_answer_is_used():
    """첫 요청의 응답이 timeout 보다 늦게 와도 상한 안이면 씀."""
    cli = _Client(appear=0.0, answer=0, delay=0.5)
    a, _ = _localizer(cli)
    k, why = a._ask_camera(CANDS)
    assert k == 0, why


def test_no_service_gives_up_at_wait():
    """끝까지 서비스가 없으면 상한(생성 뒤 wait)에서 포기 -> 예전 규칙."""
    cli = _Client(appear=None)
    a, log = _localizer(cli, wait=0.6)
    t = time.monotonic()
    k, why = a._ask_camera(CANDS)
    took = time.monotonic() - t
    assert k is None and why.startswith('no /frybot/spot_check service')
    assert 0.5 <= took < 0.9
    assert any('waiting for /frybot/spot_check' in s for s in log.lines)


def test_no_answer_gives_up_at_wait():
    """서비스는 있으나 답이 없으면 상한에서 포기, 요청은 모두 취소."""
    cli = _Client(appear=0.0, answer=None)
    a, _ = _localizer(cli, wait=0.7)
    k, why = a._ask_camera(CANDS)
    assert k is None and why.startswith('no answer in')
    assert all(f.cancelled for f in cli.calls)


def test_past_wait_still_waits_timeout():
    """상한을 넘겨 불려도(탐색이 늦게 끝남) 최소 camera_timeout 은 기다림."""
    cli = _Client(appear=None)
    a, _ = _localizer(cli, wait=0.0, timeout=0.3)
    time.sleep(0.1)
    t = time.monotonic()
    a._ask_camera(CANDS)
    assert time.monotonic() - t >= 0.29
