# [수정 2026-11-24] 새 파일: guest_tracker 의 순수 함수 시험(YOLO 없이)
"""guest_tracker 의 손님 선택·거리 추정·스트림 분리 시험."""

import importlib.util
import math
import pathlib

from frybot_ai import guest_tracker as gt
import pytest


def test_parse_camera_default_and_port() -> None:
    """포트를 생략하면 8554, 주면 그 값."""
    cam = gt.parse_camera('pinky1=192.168.0.9')
    assert (cam.robot_id, cam.host, cam.port) == ('pinky1', '192.168.0.9',
                                                  8554)
    assert gt.parse_camera('pinky2=10.0.0.2:9000').port == 9000


# [수정 2026-11-24] 로봇별 회전
def test_parse_camera_rotate_suffix() -> None:
    """'@회전'이 있으면 그 로봇만 그 회전, 없으면 None(전체 기본값)."""
    cam = gt.parse_camera('pinky2=192.168.0.29:8554@cw')
    assert (cam.host, cam.port, cam.rotate) == ('192.168.0.29', 8554, 'cw')
    assert gt.parse_camera('pinky3=192.168.0.28').rotate is None


@pytest.mark.parametrize('spec', ['pinky1', '=1.2.3.4', 'pinky1=',
                                  'pinky1=1.2.3.4@90'])
def test_parse_camera_rejects_bad_spec(spec: str) -> None:
    """robot=host 형식이 아니면 ValueError."""
    with pytest.raises(ValueError):
        gt.parse_camera(spec)


def test_focal_and_distance() -> None:
    """화각 90도면 f = 폭/2, 거리는 상자 높이에 반비례."""
    f = gt.focal_px(640, 90.0)
    assert f == pytest.approx(320.0)
    assert gt.estimate_distance(320.0, 0.17, f) == pytest.approx(0.17)
    assert gt.estimate_distance(160.0, 0.17, f) == pytest.approx(0.34)
    assert math.isinf(gt.estimate_distance(0.0, 0.17, f))


def test_pick_guest_is_tallest_box() -> None:
    """상자 높이가 가장 큰(가장 가까운) 사람을 손님으로 고른다."""
    far = {'xyxy': [0, 100, 50, 200], 'conf': 0.9}
    near = {'xyxy': [100, 50, 200, 400], 'conf': 0.5}
    assert gt.pick_guest([far, near]) is near
    assert gt.pick_guest([]) is None


# [수정 2026-11-24] guest_result 가 손님을 인자로 받도록 바뀜, 고정 정보 확인
def test_guest_result_visible_and_truncated() -> None:
    """손님이 있으면 거리·잘림, 없으면 visible False."""
    f = gt.focal_px(640, 90.0)
    p = {'xyxy': [10, 0, 60, 320], 'conf': 0.8, 'id': 4}
    out = gt.guest_result('pinky1', [p], p, 480, 0.17, f)
    assert out['kind'] == 'GUEST_TRACK' and out['visible']
    assert out['distance'] == pytest.approx(0.17)
    assert out['truncated'] and out['count'] == 1
    assert 'visit_id' not in out and not out['locked']  # 관제가 채움
    assert out['track_id'] == 4
    locked = gt.guest_result('pinky1', [p], None, 480, 0.17, f, 7)
    assert locked['visit_id'] == 7 and locked['locked']
    assert not locked['visible'] and locked['distance'] == 0.0


# [수정 2026-11-24] 손님 고정: 안내 시작 때 가장 앞 사람, 끝날 때까지 유지
def test_select_guest_locks_front_person_and_keeps_it() -> None:
    """고정 뒤에는 더 가까운 사람이 끼어들어도 고정한 사람만 손님."""
    guest = {'xyxy': [100, 50, 200, 400], 'conf': 0.8, 'id': 3}
    other = {'xyxy': [300, 100, 350, 250], 'conf': 0.9, 'id': 5}
    # 고정 안 함: 가장 앞 사람, 고정 번호 없음
    assert gt.select_guest([guest, other], 0, None) == (guest, None)
    # 안내 시작(고정 전): 가장 앞 사람 3번으로 고정
    assert gt.select_guest([other, guest], 9, None) == (guest, 3)
    # 다른 사람이 더 가까이 끼어듦: 그래도 3번
    intruder = {'xyxy': [0, 0, 300, 470], 'conf': 0.95, 'id': 8}
    assert gt.select_guest([intruder, guest], 9, 3) == (guest, 3)
    # 3번이 가려짐: 손님 없음, 고정은 유지(다른 사람으로 넘어가지 않음)
    assert gt.select_guest([intruder, other], 9, 3) == (None, 3)


def test_select_guest_waits_for_tracked_person() -> None:
    """고정 전인데 추적 번호가 없으면 고정하지 않고 기다린다."""
    p = {'xyxy': [0, 0, 10, 100], 'conf': 0.9, 'id': None}
    assert gt.select_guest([p], 9, None) == (None, None)
    assert gt.select_guest([], 9, None) == (None, None)


def test_tracker_config_writes_yaml(tmp_path) -> None:
    """추적기 설정 파일: ReID 켜짐/꺼짐, ByteTrack."""
    reid = gt.tracker_config('botsort_reid', 90, tmp_path)
    text = pathlib.Path(reid).read_text(encoding='utf-8')
    assert 'tracker_type: botsort' in text and 'with_reid: True' in text
    assert 'track_buffer: 90' in text
    bt = pathlib.Path(gt.tracker_config('bytetrack', 30, tmp_path)
                      ).read_text(encoding='utf-8')
    assert 'tracker_type: bytetrack' in bt and 'with_reid' not in bt


def test_split_jpegs_keeps_latest_and_rest() -> None:
    """마지막 완성 JPEG 하나를 꺼내고 뒤에 남은 바이트는 남긴다."""
    a = b'\xff\xd8A\xff\xd9'
    b = b'\xff\xd8B\xff\xd9'
    jpg, rest = gt.split_jpegs(a + b + b'\xff\xd8C')
    assert jpg == b and rest == b'\xff\xd8C'
    assert gt.split_jpegs(b'\xff\xd8C') == (None, b'\xff\xd8C')


# [수정 2026-11-24] 런치의 카메라 기본값: 등록부의 모든 로봇
def test_launch_cameras_from_registry(tmp_path) -> None:
    """등록부에서 host 가 있고 꺼지지 않은 로봇을 모두 카메라로 넣는다."""
    launch = (pathlib.Path(__file__).resolve().parents[1] / 'launch'
              / 'guest_tracker.launch.py')
    spec = importlib.util.spec_from_file_location('gt_launch', launch)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    reg = tmp_path / 'robots.yaml'
    reg.write_text(
        'robots:\n'
        '  pinky1: {host: 192.168.0.9}\n'
        '  pinky2: {host: 192.168.0.29, camera_rotate: cw}\n'
        '  pinky3: {host: 192.168.0.28, enabled: false}\n'
        '  pinky4: {}\n', encoding='utf-8')
    assert mod.cameras_from_registry(str(reg)) == [
        'pinky1=192.168.0.9:8554', 'pinky2=192.168.0.29:8554@cw']
    assert mod.cameras_from_registry(str(tmp_path / 'none.yaml')) == []
