"""FrybotNavigator: builds the Nav2 stack of one FrybotMobile (shared by navigator.launch.py, robot.launch.py and the
simulation bring-up)."""
import os
import tempfile

from ament_index_python.packages import get_package_share_directory
from launch_ros.actions import Node

NAV_NODES = ['controller_server', 'planner_server', 'bt_navigator']
LOC_NODES = ['map_server', 'amcl']


def params_file(rid, real, map_yaml=''):
    """Fill the placeholders of nav2_store.yaml for one robot and return the path of the result."""
    share = get_package_share_directory('frybot_mobile')
    body = open(os.path.join(share, 'config', 'nav2_store.yaml')).read()
    for k, v in (('__NS__', rid), ('__FP__', '' if real else rid + '/'), ('__SIM__', 'false' if real else 'true'),
                 ('__BT__', os.path.join(share, 'config', 'segment_bt.xml')), ('__MAPTOPIC__', f'/{rid}/map' if real else '/map'), ('__MAP__', map_yaml)):
        body = body.replace(k, v)
    path = os.path.join(tempfile.mkdtemp(prefix='frybot_nav2_'), rid + '_nav2.yaml')
    # the nodes run in the robot's namespace, so the parameter file needs the namespace as its root key
    open(path, 'w').write(rid + ':\n' + ''.join('  ' + ln if ln.strip() else ln for ln in body.splitlines(True)))
    return path


def navigator_nodes(rid, real=False, map_yaml=''):
    """Launch actions of one robot's Nav2 stack (also used by the simulation bring-up)."""
    pfile = params_file(rid, real, map_yaml)
    # on the robot every node of the namespace shares the robot's own TF topics
    remap = [('/tf', 'tf'), ('/tf_static', 'tf_static')] if real else []
    common = dict(namespace=rid, output='screen', parameters=[pfile], remappings=remap)
    nodes = [
        Node(package='nav2_controller', executable='controller_server', **common),
        Node(package='nav2_planner', executable='planner_server', **common),
        Node(package='nav2_bt_navigator', executable='bt_navigator', **common),
        Node(package='nav2_lifecycle_manager', executable='lifecycle_manager', name='lifecycle_manager', namespace=rid,
             output='screen', parameters=[{'use_sim_time': not real, 'autostart': True, 'bond_timeout': 0.0,
                                           'node_names': NAV_NODES}]),
    ]
    if real:
        nodes = [
            Node(package='nav2_map_server', executable='map_server', **common),
            Node(package='nav2_amcl', executable='amcl', **common),
            Node(package='nav2_lifecycle_manager', executable='lifecycle_manager', name='lifecycle_manager_localization',
                 namespace=rid, output='screen', parameters=[{'use_sim_time': False, 'autostart': True,
                                                              'bond_timeout': 0.0, 'node_names': LOC_NODES}]),
        ] + nodes
    return nodes
