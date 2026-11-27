# [수정 2026-11-24] 새 파일: AI 서버 손님 추적(guest_tracker)을 가상 환경
# Python 으로 띄움
"""AI 서버(관제 PC·노트북)에서 띄우는 것: guest_tracker (YOLO 손님 추적).

  ros2 launch frybot_ai guest_tracker.launch.py cameras:=pinky1=192.168.0.9

  cameras:=<로봇=주소[:포트][@회전],...>  받을 로봇 카메라(쉼표로 여럿).
                                   [수정 2026-11-24] 비우면(기본) 로봇 등록부
                                   (robots_file)의 모든 로봇. 등록부의
                                   camera_rotate 키가 있으면 그 회전
  robots_file:=<경로>              로봇 등록부
                                   (기본 ~/.config/frybot/robots.yaml)
  model:=yolov8s.pt                yolov8s.pt / yolo11s.pt / yolo26s.pt 등
  python:=<경로>                   ultralytics 가 설치된 가상 환경의 Python
                                   (기본 ~/venv/yolo/bin/python)
  rotate, conf, device, person_height, hfov_deg, central_url, view_port,
  record, tracker, track_buffer    guest_tracker 의 같은 이름 인자

ultralytics(torch)는 가상 환경에만 있어, ROS 설정을 불러온 셸에서 가상
환경의 Python 으로 모듈을 직접 실행한다(serving_arm.launch.py 와 같은 방식).
"""

import os

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.actions import ExecuteProcess
from launch.actions import OpaqueFunction
from launch.launch_context import LaunchContext
from launch.substitutions import LaunchConfiguration
import yaml

# (런치 인자, 기본값, guest_tracker 인자). cameras 는 따로 처리
_ARGS = [
    ('model', 'yolov8s.pt', '--model'),
    ('device', '0', '--device'),
    ('conf', '0.4', '--conf'),
    # [수정 2026-11-24] 손님 고정용 추적기(botsort_reid, botsort, bytetrack)
    ('tracker', 'botsort_reid', '--tracker'),
    ('track_buffer', '90', '--track-buffer'),
    ('rotate', '180', '--rotate'),
    ('hfov_deg', '53.5', '--hfov-deg'),
    ('person_height', '0.17', '--person-height'),
    ('central_url', 'http://127.0.0.1:8100/ai/result', '--central-url'),
    ('view_port', '8095', '--view-port'),
    ('record', '', '--record'),
]


# [수정 2026-11-24] pinky1~3 모두: 카메라 목록 기본값을 로봇 등록부에서 읽음
def cameras_from_registry(path: str) -> list[str]:
    """로봇 등록부에서 카메라 지정 목록을 만든다.

    Args:
        path: 등록부 경로(robots.yaml 형식: robots.<이름>.host,
            선택 enabled, camera_rotate, camera_port).

    Returns:
        'robot=host:port[@rotate]' 목록(등록부 순서). enabled 가 false 이거나
        host 가 없는 로봇은 뺀다. 파일이 없으면 빈 목록.
    """
    path = os.path.expanduser(path)
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as f:
        reg = yaml.safe_load(f) or {}
    out = []
    for name, info in (reg.get('robots') or {}).items():
        info = info or {}
        if not info.get('host') or info.get('enabled', True) is False:
            continue
        spec = f"{name}={info['host']}:{info.get('camera_port', 8554)}"
        if info.get('camera_rotate'):
            spec += f"@{info['camera_rotate']}"
        out.append(spec)
    return out


def setup(context: LaunchContext) -> list:
    """런치 인자를 읽어 guest_tracker 를 띄우는 액션을 만든다.

    Args:
        context: 런치 문맥.

    Returns:
        ExecuteProcess 하나의 목록.
    """
    def g(key: str) -> str:
        return LaunchConfiguration(key).perform(context)

    cmd = [os.path.expanduser(g('python')), '-m', 'frybot_ai.guest_tracker']
    specs = [s.strip() for s in g('cameras').split(',') if s.strip()]
    if not specs:
        specs = cameras_from_registry(g('robots_file'))
    if not specs:
        raise RuntimeError(
            'guest_tracker: no cameras (cameras:= is empty and the robot '
            f"registry {g('robots_file')} has no robots)")
    for spec in specs:
        cmd += ['--camera', spec]
    for key, _, flag in _ARGS:
        cmd += [flag, g(key)]
    return [ExecuteProcess(cmd=cmd, output='screen', name='guest_tracker')]


def generate_launch_description() -> LaunchDescription:
    """인자를 선언하고 setup 을 붙인다.

    Returns:
        LaunchDescription.
    """
    decl = [DeclareLaunchArgument('cameras', default_value=''),
            DeclareLaunchArgument('robots_file',
                                  default_value='~/.config/frybot/robots.yaml'),
            DeclareLaunchArgument('python',
                                  default_value='~/venv/yolo/bin/python')]
    decl += [DeclareLaunchArgument(k, default_value=v) for k, v, _ in _ARGS]
    return LaunchDescription(decl + [OpaqueFunction(function=setup)])
