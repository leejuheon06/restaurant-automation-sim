# [수정 2026-11-24] 새 파일: Pinky 카메라(Camera Streamer)를 AI 서버가 직접
# 받는 MJPEG TCP 스트림으로 내보냄
"""Pinky Pi 에서 띄우는 것: Camera Streamer (rpicam-vid MJPEG TCP).

  ros2 launch frybot_mobile camera_streamer.launch.py

  width, height, fps   영상 크기·초당 프레임(기본 640x480, 15. 1296x972 는
                       Wi-Fi 지연이 커서 기본으로 두지 않음, 2026-11-24)
  port                 TCP 포트(기본 8554). AI 서버(frybot_ai guest_tracker)가
                       여기에 붙는다
  quality              MJPEG 품질(1~100, 기본 70)
                       [수정 2026-11-24] fps 30 -> 15, quality 93 -> 70. 세 대를
                       함께 보내자 pinky2 링크(약 2.7 Mbps)에 송신 대기가 약
                       667 KB(약 5 s 지연) 쌓였음. 15 fps·70 에서 1 프레임 수준

영상은 ROS 로 보내지 않는다(README '영상은 ROS로 보내지 않습니다').
rpicam-vid --listen 은 받는 쪽 연결이 끊기면 끝나므로, 다시 기다리도록
반복해서 띄운다. 한 번에 받는 쪽 하나만 붙을 수 있다. 다른 프로그램이
카메라를 쓰고 있으면 열리지 않는다.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.actions import ExecuteProcess
from launch.actions import OpaqueFunction
from launch.launch_context import LaunchContext
from launch.substitutions import LaunchConfiguration


def stream_command(width: str, height: str, fps: str, port: str,
                   quality: str) -> str:
    """카메라 스트림을 반복해서 띄우는 셸 명령을 만든다.

    Args:
        width: 영상 가로(px).
        height: 영상 세로(px).
        fps: 초당 프레임.
        port: TCP 포트.
        quality: MJPEG 품질.

    Returns:
        bash -c 로 실행할 명령 문자열.
    """
    for v in (width, height, fps, port, quality):
        int(v)  # 숫자가 아니면 ValueError 로 런치를 멈춤(셸 주입 방지)
    return (
        'while true; do rpicam-vid -t 0 -n'
        f' --width {width} --height {height} --framerate {fps}'
        f' --codec mjpeg --quality {quality} --listen'
        f' -o tcp://0.0.0.0:{port}; sleep 0.3; done')


def setup(context: LaunchContext) -> list:
    """런치 인자를 읽어 스트림 프로세스를 만든다.

    Args:
        context: 런치 문맥.

    Returns:
        ExecuteProcess 하나의 목록.
    """
    def g(key: str) -> str:
        return LaunchConfiguration(key).perform(context)

    cmd = stream_command(g('width'), g('height'), g('fps'), g('port'),
                         g('quality'))
    return [ExecuteProcess(cmd=['bash', '-c', cmd], output='screen',
                           name='camera_streamer')]


def generate_launch_description() -> LaunchDescription:
    """인자를 선언하고 setup 을 붙인다.

    Returns:
        LaunchDescription.
    """
    # [수정 2026-11-24] fps '30' -> '15', quality '93' -> '70' (위 머리말)
    args = [('width', '640'), ('height', '480'), ('fps', '15'),
            ('port', '8554'), ('quality', '70')]
    return LaunchDescription(
        [DeclareLaunchArgument(k, default_value=v) for k, v in args]
        + [OpaqueFunction(function=setup)])
