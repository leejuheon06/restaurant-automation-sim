"""FrybotNavigator: builds the Nav2 stack of one FrybotMobile (shared by navigator.launch.py, robot.launch.py and the
simulation bring-up)."""
import os
import tempfile

from ament_index_python.packages import get_package_share_directory
from launch_ros.actions import Node

# [수정 2026-11-20] 실측 지도의 도크(roadmap.json 의 docks)를 읽음
from frybot_control.layout import map_docks
# [수정 2026-11-26] 2단계 보완: 지도 단위 후진 도킹 설정(roadmap.json)
from frybot_control.map_catalog import dock_backwards as map_dock_backwards

# 주행 스택(lifecycle_manager 가 이 순서로 켬). docking_server 는 도크가
# 있을 때만 띄움(navigator_nodes 참고)
NAV_NODES = ['controller_server', 'planner_server', 'bt_navigator', 'docking_server']
LOC_NODES = ['map_server', 'amcl']  # 실기기 위치 추정 스택(real 일 때만)


def params_file(rid, real, map_yaml='', measured=False):
    """Fill the placeholders of nav2_store.yaml for one robot and return the path of the result."""
    # 인자: rid 로봇 이름, real 실기기 여부(프레임 접두어·시계·지도 토픽),
    # map_yaml 지도 yaml(__MAP__), measured 실측 지도 여부(전역 inflation).
    # 돌려주는 값: 임시 폴더에 쓴 <rid>_nav2.yaml 경로(지우지 않음)
    share = get_package_share_directory('frybot_mobile')
    body = open(os.path.join(share, 'config', 'nav2_store.yaml')).read()
    # 자리표시자 뜻은 nav2_store.yaml 머리말. 전역 inflation 은 실기기 +
    # 실측 지도만 0.07, 그 밖(시뮬 등)은 0.08
    for k, v in (('__NS__', rid), ('__FP__', '' if real else rid + '/'), ('__SIM__', 'false' if real else 'true'),
                 ('__BT__', os.path.join(share, 'config', 'segment_bt.xml')), ('__MAPTOPIC__', f'/{rid}/map' if real else '/map'), ('__MAP__', map_yaml),
                 ('__GLOBAL_INFLATION__', '0.07' if real and measured else '0.08')):
        body = body.replace(k, v)
    path = os.path.join(tempfile.mkdtemp(prefix='frybot_nav2_'), rid + '_nav2.yaml')
    # the nodes run in the robot's namespace, so the parameter file needs the namespace as its root key
    open(path, 'w').write(rid + ':\n' + ''.join('  ' + ln if ln.strip() else ln for ln in body.splitlines(True)))
    return path


# [수정 2026-11-18] P1: real 의 기본값(False, 시뮬)을 없애 부르는 쪽이 실기기/
# 시뮬을 반드시 밝히게 함
# [수정 2026-11-18] T-38: 실측 지도에는 도크가 없어(layout.docks() 가 빈
# 값) docking_server 와 aruco_dock_detector 를 띄우지 않음(로봇당 프로세스
# 2개 감소). 가상 매장 도면은 그대로 띄움
# [수정 2026-11-20] map_id 인자 추가. 실측 지도라도 도크가 있으면
# docking_server 를, 마커 도크가 있으면 aruco_dock_detector 도 띄움(서빙 팔
# 시험의 D1_STOP 정밀 정차). 도크 없는 지도는 T-38 대로 띄우지 않음
def navigator_nodes(rid, real, map_yaml='', measured=False, initial_pose=(),
                    map_id=''):
    """Launch actions of one robot's Nav2 stack (also used by the simulation).

    map_id: 실측 지도 이름. measured 일 때 그 지도의 도크로 도킹 노드를
    띄울지 정함(환경 변수 FRYBOT_MAP_ID 를 보지 않음).

    Args:
        rid: 로봇 이름(네임스페이스, 예: pinky1).
        real: True 면 실기기(벽시계, 로봇 자체 /<rid>/tf, map_server +
            AMCL 추가), False 면 시뮬(시뮬 시계, 공유 /tf, '<rid>/' 프레임).
        map_yaml: Nav2 지도 yaml 경로(map_server 용).
        measured: 실측 지도 여부. True 면 FollowPath 를 전진 전용으로
            덮어쓰고, 도킹 노드는 map_id 의 도크로 정함. False 면 가상
            매장 도면으로 보고 도킹 노드를 모두 띄움.
        initial_pose: (x, y, yaw) 를 주면 AMCL 초기 자세로 넣음(real 만).
        map_id: 위 설명.

    Returns:
        launch_ros Node 액션 목록(real 이면 위치 추정 노드가 앞에 옴).
    """
    # 가상 매장 도면(measured=False)은 도킹 서버·마커 검출기를 모두 띄움
    docking, marker = not measured, not measured
    if measured and map_id:
        kinds = [d['kind'] for d in map_docks(map_id).values()]
        docking, marker = bool(kinds), 'marker' in kinds
    pfile = params_file(rid, real, map_yaml, measured=measured)
    # 모든 Nav2 노드가 같은 파라미터 파일, 같은 네임스페이스로 뜸
    # on the robot every node of the namespace shares the robot's own TF topics
    remap = [('/tf', 'tf'), ('/tf_static', 'tf_static')] if real else []
    common = dict(namespace=rid, output='screen', parameters=[pfile], remappings=remap)
    controller = dict(common)
    # [수정 2026-11-17] 실측 지도는 FollowPath 만 전진 전용으로 덮어씀.
    # 후진용 FollowPathReverse 는 nav2_store.yaml 값 그대로 (UR-03 안내 후진)
    if measured:
        controller['parameters'] = [pfile, {'FollowPath.use_rotate_to_heading': True,
                                              'FollowPath.allow_reversing': False}]
    # 주행 스택(제어기, 전역 경로, 구간용 BT)
    nodes = [
        Node(package='nav2_controller', executable='controller_server', **controller),
        Node(package='nav2_planner', executable='planner_server', **common),
        Node(package='nav2_bt_navigator', executable='bt_navigator', **common),
    ]
    # [수정 2026-11-26] 후진 도킹(사용자 결정 방안 다): 실측 지도의 도크는 모두
    # 뒤로 들어감. 도킹 서버 설정은 서버 전체에 하나(dock_backwards)라 실측
    # 지도에서만 true 로 덮어씀. 가상 매장(proto)의 마커 도크는 앞 카메라로
    # 마커를 보므로 nav2_store.yaml 값(false) 그대로
    dock_common = dict(common)
    # [수정 2026-11-26] 2단계 보완: 지도의 "dock_backwards"(없으면 true)가
    # true 일 때만 덮어씀. false 인 지도(v04·v05)는 예전처럼 전진
    if measured and (map_dock_backwards(map_id) if map_id else True):
        dock_common['parameters'] = [pfile, {'dock_backwards': True}]
    dock_nodes = [
        Node(package='opennav_docking', executable='opennav_docking',
             name='docking_server', **dock_common),
        # ArUco marker -> dock pose for the docking server (camera image only used while docking)
        Node(package='frybot_mobile', executable='aruco_dock_detector', namespace=rid, output='screen', remappings=remap,
             # [수정 2026-11-18] P1: 검출기 프레임 기본값이 실기기 이름이 되어
             # 시뮬(공유 /tf)일 때만 '<로봇>/...' 를 넘김
             parameters=[{'robot_id': rid}] +
                        ([] if real else [{'base_frame': f'{rid}/base_footprint',
                                           'camera_frame': f'{rid}/front_camera_link',
                                           'fixed_frame': f'{rid}/odom'}])),
    ]
    # lifecycle_manager 가 관리할 노드(도크가 없으면 docking_server 제외)
    nav_names = [n for n in NAV_NODES if docking or n != 'docking_server']
    # [수정 2026-11-20] 검출기는 마커 도크가 있을 때만(dock_nodes[1])
    nodes += (dock_nodes[:1 + marker] if docking else []) + [
        Node(package='nav2_lifecycle_manager', executable='lifecycle_manager', name='lifecycle_manager', namespace=rid,
             output='screen', parameters=[{'use_sim_time': not real, 'autostart': True, 'bond_timeout': 0.0,
                                           'node_names': nav_names}]),
    ]
    # 실기기: map_server + AMCL 과 그 lifecycle_manager 를 앞에 붙임.
    # bond_timeout 0.0 은 노드가 죽어도 감지하지 않음(리뷰 R1-2 참고)
    if real:
        amcl = dict(common)
        if initial_pose:
            x, y, yaw = initial_pose
            amcl['parameters'] = [pfile, {'set_initial_pose': True, 'initial_pose.x': x,
                                         'initial_pose.y': y, 'initial_pose.yaw': yaw}]
        nodes = [
            Node(package='nav2_map_server', executable='map_server', **common),
            Node(package='nav2_amcl', executable='amcl', **amcl),
            Node(package='nav2_lifecycle_manager', executable='lifecycle_manager', name='lifecycle_manager_localization',
                 namespace=rid, output='screen', parameters=[{'use_sim_time': False, 'autostart': True,
                                                              'bond_timeout': 0.0, 'node_names': LOC_NODES}]),
        ] + nodes
    return nodes
