"""Robot descriptions for the simulation: Pinky Pro (xacro) and JetCobot 280 (= myCobot 280 Pi URDF)."""
import os
import subprocess
import xml.etree.ElementTree as ET

from ament_index_python.packages import get_package_share_directory


def pinky_urdf(namespace='', is_sim=False):
    path = os.path.join(get_package_share_directory('pinky_description'), 'urdf', 'robot.urdf.xacro')
    return subprocess.check_output(['xacro', path, f'namespace:={namespace}', f'is_sim:={"true" if is_sim else "false"}']).decode()


def jetcobot_urdf(scale=1.0):
    """scale < 1 shrinks the arm. The team's scenario mounts an arm on every AMR, which the real hardware cannot
    carry (11 x 12 cm base), so the mounted serving arm is shown at reduced scale; cooking arms are full size."""
    path = os.path.join(get_package_share_directory('mycobot_description'), 'urdf', 'mycobot_280_pi', 'mycobot_280_pi.urdf')
    root = ET.parse(path).getroot()
    if scale != 1.0:
        for o in root.iter('origin'):
            if 'xyz' in o.attrib:
                o.set('xyz', ' '.join(str(float(v) * scale) for v in o.attrib['xyz'].split()))
        for mesh in root.iter('mesh'):
            mesh.set('scale', f'{scale} {scale} {scale}')
    return ET.tostring(root, encoding='unicode')


def pinky_gz_urdf(rid, fortress=True):
    """Pinky model for Gazebo with every topic / frame under the robot name."""
    urdf = pinky_urdf(namespace=rid + '/', is_sim=True)
    # the upstream xacro prefixes the <gazebo reference> link names, but the links themselves are not prefixed
    urdf = urdf.replace(f'reference="{rid}/', 'reference="')
    if fortress:                       # Fortress (ROS 2 Humble) still uses the ignition names
        urdf = urdf.replace('gz-sim-', 'ignition-gazebo-').replace('gz::sim::systems', 'ignition::gazebo::systems')
        urdf = urdf.replace('gz_frame_id', 'ignition_frame_id')
    return urdf
