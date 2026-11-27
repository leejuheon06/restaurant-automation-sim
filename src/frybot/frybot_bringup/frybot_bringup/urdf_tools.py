"""Robot descriptions for the simulation: Pinky Pro (xacro) and JetCobot 280 (= myCobot 280 Pi URDF)."""
import os
import re
import subprocess
import xml.etree.ElementTree as ET

from ament_index_python.packages import get_package_share_directory


# [수정 2026-11-17] 외부 pinky_description, mycobot_description 대신
# frybot_description 안의 사본을 씀 (pinky_pro, mycobot_ros2 의존 제거)
def pinky_urdf(namespace='', is_sim=False):
    """Pinky Pro 의 URDF 문자열을 xacro 로 만든다.

    Args:
        namespace: 링크·조인트 이름 앞에 붙일 접두사(예: 'pinky1/').
        is_sim: True 면 Gazebo 용 정의(pinky_gz.urdf.xacro)를 넣음.

    Returns:
        URDF XML 문자열.

    Raises:
        subprocess.CalledProcessError: xacro 가 실패할 때.
    """
    path = os.path.join(get_package_share_directory('frybot_description'),
                        'pinky', 'urdf', 'robot.urdf.xacro')
    return subprocess.check_output(['xacro', path, f'namespace:={namespace}', f'is_sim:={"true" if is_sim else "false"}']).decode()


def jetcobot_urdf(scale=1.0):
    """scale < 1 shrinks the arm. The team's scenario mounts an arm on every AMR, which the real hardware cannot
    carry (11 x 12 cm base), so the mounted serving arm is shown at reduced scale; cooking arms are full size."""
    path = os.path.join(get_package_share_directory('frybot_description'),
                        'jetcobot', 'mycobot_280_pi.urdf')
    root = ET.parse(path).getroot()
    # 관절 위치(origin xyz)와 메시 크기를 같은 배율로 줄임
    if scale != 1.0:
        for o in root.iter('origin'):
            if 'xyz' in o.attrib:
                o.set('xyz', ' '.join(str(float(v) * scale) for v in o.attrib['xyz'].split()))
        for mesh in root.iter('mesh'):
            mesh.set('scale', f'{scale} {scale} {scale}')
    return ET.tostring(root, encoding='unicode')


def pinky_gz_urdf(rid, fortress=False):
    """Pinky model for Gazebo with every topic / frame under the robot name."""
    urdf = pinky_urdf(namespace=rid + '/', is_sim=True)
    # the upstream xacro prefixes the <gazebo reference> link names, but the links themselves are not prefixed
    urdf = urdf.replace(f'reference="{rid}/', 'reference="')
    # Front camera (ArUco docking): a smaller, slower image than upstream keeps three robots renderable, and the near
    # clip goes down because the robot stops 9-14 cm in front of the marker wall
    head, cam = urdf.split('type="camera">', 1)
    cam, tail = cam.split('</sensor>', 1)
    # 카메라 640x360, near 0.02 m, 10 Hz, 센서 시각화 끔
    for pat, new in ((r'<width>\d+</width>', '<width>640</width>'), (r'<height>\d+</height>', '<height>360</height>'),
                     (r'<near>[\d.]+</near>', '<near>0.02</near>'), (r'<update_rate>\d+</update_rate>', '<update_rate>10</update_rate>'),
                     (r'<visualize>true</visualize>', '<visualize>false</visualize>')):
        cam = re.sub(pat, new, cam)
    urdf = head + 'type="camera">' + cam + '</sensor>' + tail
    if fortress:                       # Fortress (ROS 2 Humble) still uses the ignition names
        urdf = urdf.replace('gz-sim-', 'ignition-gazebo-').replace('gz::sim::systems', 'ignition::gazebo::systems')
        urdf = urdf.replace('gz_frame_id', 'ignition_frame_id')
    else:
        # Harmonic's bridge no longer copies the pose name of /world/<w>/dynamic_pose/info into child_frame_id, so
        # each robot publishes its own world pose (header child_frame_id = model name) on /model/<rid>/pose
        urdf = urdf.replace('</robot>', '''  <gazebo>
    <plugin filename="gz-sim-pose-publisher-system" name="gz::sim::systems::PosePublisher">
      <publish_model_pose>true</publish_model_pose><publish_link_pose>false</publish_link_pose>
      <publish_collision_pose>false</publish_collision_pose><publish_visual_pose>false</publish_visual_pose>
      <publish_sensor_pose>false</publish_sensor_pose><publish_nested_model_pose>false</publish_nested_model_pose>
      <use_pose_vector_msg>true</use_pose_vector_msg><update_frequency>50</update_frequency>
    </plugin>
  </gazebo>
</robot>''', 1)
    return urdf
