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


def pinky_gz_urdf(rid, fortress=False):
    """Pinky model for Gazebo with every topic / frame under the robot name."""
    urdf = pinky_urdf(namespace=rid + '/', is_sim=True)
    # the upstream xacro prefixes the <gazebo reference> link names, but the links themselves are not prefixed
    urdf = urdf.replace(f'reference="{rid}/', 'reference="')
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
