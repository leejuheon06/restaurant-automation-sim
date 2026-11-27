"""FryBot with REAL AMRs, started from the central PC with one command:

  ros2 launch frybot_bringup real.launch.py map_id:=test_map_v001

Starts the central side (Web Service, Central Control, Task Manager) AND, over SSH, the robot side
(`ros2 launch frybot_mobile robot.launch.py`) on every robot registered in
~/.config/frybot/robots.yaml (address, user and password per robot).
Ctrl-C stops both sides.
[수정 2026-11-18] T-30: 등록부는 저장소 밖(~/.config/frybot/robots.yaml)에 둠.
없으면 관제만 뜨고 그 사실을 로그로 알림. 형식은 config/robots.example.yaml.
  robots:=N        pinky1..pinkyN (default: every registered robot; pinky1
                   when nothing is registered or with remote:=false)
  robots:=pinky1,pinky3   exactly these robots
  poses:=pinky1:A2,pinky3:W3   where each robot stands at start (roadmap node, optional :heading in degrees,
                   0 = +x): given to AMCL as the initial pose, so no RViz "2D Pose Estimate" is needed
  remote:=false    do not touch the robots: start robot.launch.py on each Pinky by hand, as before
  rviz:=false      do not open the fleet RViz view. [수정 2026-11-17] 기본값을 true 로 바꿈: 실행할 때마다
                   런치에 든 모든 로봇의 전역·지역 코스트맵이 켜진 RViz 가 함께 뜸
  auto_home:=true  [수정 2026-11-20] T-48: 기본 false(이전 기본 true). 연결된
      로봇은 지금 자리에서 대기(사용자 요청). true 면 예전처럼 아래 동작
  (예전 설명) [수정 2026-11-17] 위치가 잡힌 로봇이 자기 출발
      노드(roadmap.json 의 homes,
                   대기 위치)로 스스로 이동함. false 면 놓인 자리에 그대로 서 있음
  prefer_yield:=false   let robots drive round each other as before instead of waiting / stepping aside
[수정 2026-11-17] B4: map_id 는 필수이며 실측 지도여야 함(비었거나 proto 이거나 없는 지도면 런치를 멈춤).
전에는 map_id 를 빠뜨리면 관제가 가상 매장 도면과 조리 팔·AI 대역으로 떴음. 그 분기와 sim_cooking 인자는
도달할 수 없게 되어 삭제함(조리 팔·AI 서버는 실물이 아직 없음).
  plan_overhead:=2.27  [수정 2026-11-18] W6: 계획의 구간 지연(초), 기본 0.0.
                   speed:=0.135 와 함께 쓰는 보정값은 실기기 확인 필요
  discovery:=subnet  [수정 2026-11-18] T-38: 기본 peers.
      peers: 로봇은 자기 안과 관제 PC 만 탐색하고, 관제 PC 는 로봇들을
      탐색 상대로 지정함(로봇끼리는 서로 탐색하지 않음).
      subnet: 예전처럼 같은 대역 전체를 탐색(로봇이 늘면 기동이 느려짐)
  rviz_wait:=true  [수정 2026-11-19] T-40: 기본 false(예전처럼 곧바로 띄움).
      true: 런치에 든 로봇이 모두 상태를 보고한 뒤(또는 rviz_wait_sec 초,
      기본 120 뒤)에 RViz 를 띄움. poses:= 가 없는 로봇이 있으면 초기
      자세를 RViz 에서 찍어야 하므로 기다리지 않음.
      실기기 시험(C4)에서 RViz 가 뜬 직후 상태 보고가 4~8초 끊겼고 그때
      로봇이 자동 홈 이동 중이었음. 그래서 기본으로 켜지 않음
  rviz_displays:=false  [수정 2026-11-19] 기본 true. false 면 RViz 왼쪽의
      Displays 창 없이 띄움(화면 녹화용). RViz 메뉴 Panels > Add New
      Panel > Displays 로 다시 열 수 있음
  serving_robots:=pinky1  [수정 2026-11-20] T-47: SERVE·COLLECT 를 맡길
      로봇(쉼표). 비우면(기본) 등록부 arms 에서 켜진 서빙 팔의 mount,
      all 이면 모든 로봇. 팔 있는 로봇이 런치에 없으면 SERVE 를 거절
  ceiling_camera:=false  [수정 2026-11-23] T-55: 기본 true. 관제 PC 의 천장
      카메라 노드(ceiling_locator)를 띄움. 로봇 자동 위치 추정이 모호하면
      후보 자리를 물어 봄(답하지 못하면 예전 규칙). 빈 바닥 기준 화면이
      있어야 답함(ceiling_tool reference). ceiling_device:=/dev/video0
      [수정 2026-11-23] T-57: false 면 로봇에도 localize_camera:=false 를
      넘겨, 모호할 때 카메라를 기다리지 않음(robot_remote 직접 기동은 켬)
  admin_token:=<값>  [수정 2026-11-17] D6: 관제 PC 가 아닌 기기에서 관리자 명령을 보낼 때 쓰는 토큰.
                   비워 두면(기본) 관리자 명령은 관제 PC(localhost)에서만 받음
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction, SetEnvironmentVariable
# [수정 2026-11-19] T-40: 로봇 온라인 뒤 RViz 시작에 씀
from launch.actions import LogInfo, RegisterEventHandler
from launch.event_handlers import OnProcessExit
from launch.substitutions import LaunchConfiguration as LC
from launch_ros.actions import Node

# [수정 2026-11-18] T-30: registry_notice 추가. T-38: static_peers 추가
# [수정 2026-11-20] T-47: serving_robots 추가
from frybot_bringup.remote import (fleet_rviz_config, pick_robots, registered,
                                   registry_notice, remote_bringup,
                                   serving_robots, start_poses, static_peers)
from frybot_control.layout import Graph
from frybot_control.map_catalog import PROTO_MAP_ID, map_ids


def setup(context):
    """런치 인자로 관제 PC 노드, 로봇 원격 기동, RViz 를 만든다.

    Args:
        context: 런치 컨텍스트.

    Returns:
        런치 액션 목록.

    Raises:
        ValueError: map_id 가 실측 지도가 아니거나, discovery 값이 틀리거나,
            로봇의 출발 노드(homes)가 지도에 없을 때.
    """
    g = lambda k: LC(k).perform(context)  # 런치 인자 값(문자열)
    # remote:=false 면 등록부를 보지 않음: 원격 기동 없음, robots 가
    # 비면 pinky1
    reg = registered(g('robots_file')) if g('remote') != 'false' else {}
    robots = pick_robots(g('robots'), reg)
    map_id = g('map_id')
    # [수정 2026-11-17] B4: 실측 지도가 아니면 아무것도 띄우지 않고 멈춤
    if not map_id or map_id == PROTO_MAP_ID or map_id not in map_ids():
        raise ValueError(
            'real.launch.py 에는 실측 지도가 필요합니다: '
            f'map_id:={map_id or "(없음)"} -> 쓸 수 있는 값: {map_ids()}')
    # [수정 2026-11-18] T-38: DDS 탐색 범위. peers 면 로봇끼리 탐색하지 않음
    discovery = g('discovery')
    if discovery not in ('peers', 'subnet'):
        raise ValueError(
            f'discovery:={discovery} 는 peers | subnet 중 하나여야 합니다.')
    for rid in robots:                         # every robot needs a start vertex on the map (raises if not)
        Graph(map_id).home_of(rid)
    # [수정 2026-11-20] T-47: SERVE·COLLECT 를 받을 로봇. 인자가 비면
    # 등록부 arms 의 mount(remote:=false 여도 등록부가 있으면 읽음),
    # 'all' 이면 제한 없음
    serving = g('serving_robots')
    serving = ('' if serving == 'all' else serving) if serving else \
        ','.join(serving_robots(g('robots_file')))
    # 관제 PC 노드: 지도 환경 변수, central_control, task_manager, web_service
    nodes = [
        SetEnvironmentVariable('FRYBOT_MAP_ID', map_id),
        Node(package='frybot_control', executable='central_control', output='screen',
             parameters=[{'run_id': g('run_id'), 'scenario': 'real', 'robot_ids': robots,
                          'ai_http_port': int(g('ai_http_port'))}]),
        Node(package='frybot_control', executable='task_manager', output='screen',
             parameters=[{'scheduler': g('scheduler'), 'planner': g('planner'), 'speed': float(g('speed')),
                          'guide_speed': float(g('guide_speed')), 'cook_time_scale': float(g('cook_time_scale')),
                          'robot_ids': robots, 'use_standby': g('standby') == 'true',
                          'prefer_yield': g('prefer_yield') == 'true',
                          'auto_home': g('auto_home') == 'true',
                          # [수정 2026-11-18] W6: 계획 구간 지연(초)
                          'plan_overhead': float(g('plan_overhead')),
                          # [수정 2026-11-20] T-47: 서빙 팔을 올린 로봇
                          'serving_robots': serving}]),
        # [수정 2026-11-17] D6: 실기기에서는 관리자 명령을 관제 PC 에서만,
        # 다른 기기는 admin_token 이 맞을 때만 받음
        Node(package='frybot_web', executable='web_service', output='screen',
             parameters=[{'port': int(g('web_port')), 'admin_local_only': True,
                          'admin_token': g('admin_token')}]),
    ]
    # [수정 2026-11-23] T-55: 천장 카메라 후보 판정(실측 지도에서만, 이
    # 런치는 실측 지도 전용). 기준 화면이 없거나 카메라가 없으면 노드는
    # ok=false 로 답하고 로봇은 예전 규칙으로 감
    if g('ceiling_camera') == 'true':
        nodes.append(Node(
            package='frybot_control', executable='ceiling_locator',
            output='screen',
            parameters=[{'device': g('ceiling_device'),
                         'robot_ids': robots}]))
    # [수정 2026-11-18] T-30: remote 인데 등록부가 없으면 안내 로그
    if g('remote') != 'false':
        nodes += registry_notice(g('robots_file'))
    # [수정 2026-11-19] T-40: 출발 위치를 한 번만 계산해 아래 두 곳에서 씀
    poses = start_poses(g('poses'), map_id)
    if reg:                                    # robot side of every registered robot, over SSH
        # [수정 2026-11-18] map:= 인자를 지움(사용자 결정). 다른 yaml 을
        # 끼우면 roadmap.json 과 지도 이미지가 어긋남. 필요하면 maps/ 에
        # 새 map_id 로 추가
        # [수정 2026-11-23] T-57: 천장 카메라를 끄면 로봇도 묻지 않게 함
        # (켜 두면 모호할 때마다 노드 생성 뒤 최대 35 s 를 기다림)
        extra = ([] if g('ceiling_camera') == 'true'
                 else ['localize_camera:=false'])
        nodes += remote_bringup(robots, map_id, robots_file=g('robots_file'),
                                poses=poses,
                                discovery=discovery, extra_args=extra)
        # [수정 2026-11-18] T-38: 관제 PC 노드가 로봇을 직접 찾도록 로봇
        # 주소를 탐색 상대로 지정(터미널에 있던 값은 앞에 유지). 노드보다
        # 먼저 적용되도록 FRYBOT_MAP_ID 바로 뒤에 넣음
        if discovery == 'peers':
            nodes.insert(1, SetEnvironmentVariable(
                'ROS_STATIC_PEERS', static_peers(robots, reg)))
    if g('rviz') == 'true':  # fleet_rviz 중계 + rviz2
        # [수정 2026-11-19] rviz_displays:=false 면 Displays 창 없이 띄움
        config = fleet_rviz_config(
            robots, hide_displays=g('rviz_displays') == 'false')
        # [수정 2026-11-19] map_id 를 넘겨 로드맵(노드·통로)도 그리게 함
        views = [Node(package='frybot_bringup', executable='fleet_rviz',
                      output='screen', parameters=[{'robot_ids': robots,
                                                    'map_id': map_id}]),
                 Node(package='rviz2', executable='rviz2', output='screen',
                      arguments=['-d', str(config)])]
        # [수정 2026-11-19] T-40: RViz 를 로봇 온라인 뒤에 띄움. 실측 지도의
        # 로봇은 위치가 잡혀야 상태를 보고하므로, poses 가 없는 로봇이
        # 있으면(RViz 에서 초기 자세를 찍어야 함) 기다리지 않음
        no_pose = [rid for rid in robots if rid not in poses]
        if g('rviz_wait') != 'true':
            nodes += views
        elif no_pose:
            nodes += [LogInfo(msg=f'poses 가 없는 로봇 {no_pose}: RViz 를 '
                                  '기다리지 않고 바로 띄웁니다.')] + views
        else:
            waiter = Node(package='frybot_bringup', executable='wait_online',
                          output='screen',
                          parameters=[{'robot_ids': robots, 'timeout_sec':
                                       float(g('rviz_wait_sec'))}])

            def start_views(event, context):
                # 런치를 내리는 중(Ctrl-C)에 끝난 것이면 띄우지 않음
                return None if context.is_shutdown else views

            nodes += [waiter, RegisterEventHandler(OnProcessExit(
                target_action=waiter, on_exit=start_views))]
    return nodes


def generate_launch_description():
    """실기기 런치 인자를 선언하고 setup 을 붙인다.

    Returns:
        LaunchDescription. 인자의 뜻은 모듈 docstring 과 README 참고.
    """
    # (인자 이름, 기본값) 목록
    args = [('robots', ''), ('scheduler', 'min_cost_eta_rh'), ('planner', 'sipp'), ('speed', '0.08'),
            ('guide_speed', '0.05'), ('cook_time_scale', '20.0'), ('standby', 'false'),
            ('run_id', ''), ('map_id', ''), ('web_port', '8080'), ('ai_http_port', '8100'),
            ('remote', 'true'), ('robots_file', ''), ('rviz', 'true'), ('prefer_yield', 'true'), ('poses', ''),
            # [수정 2026-11-20] T-48: auto_home 기본 false(이전 'true').
            # 연결된 로봇은 지금 자리에서 대기
            ('auto_home', 'false'), ('admin_token', ''),
            # [수정 2026-11-18] T-38: 로봇·관제의 DDS 탐색 범위
            ('discovery', 'peers'),
            # [수정 2026-11-19] T-40: RViz 를 로봇 온라인 뒤에 띄울지와
            # 기다리는 시간 제한(초). 실기기 시험(C4)에서 RViz 가 뜬 직후
            # 주행 중인 로봇의 상태 보고가 4~8초 끊겨 기본은 false
            ('rviz_wait', 'false'), ('rviz_wait_sec', '120'),
            # [수정 2026-11-19] false 면 RViz 의 Displays 창 없이 띄움(녹화용)
            ('rviz_displays', 'true'),
            # [수정 2026-11-18] W6: 계획의 구간 지연(초). 기본 0.0. 보정값
            # (plan_overhead:=2.27 speed:=0.135)은 실기기 확인 필요
            ('plan_overhead', '0.0'),
            # [수정 2026-11-20] T-47: SERVE·COLLECT 를 받을 로봇(쉼표).
            # 비우면 등록부 arms 의 mount, all 이면 모든 로봇
            ('serving_robots', ''),
            # [수정 2026-11-23] T-55: 천장 카메라 후보 판정 노드와 장치
            ('ceiling_camera', 'true'), ('ceiling_device', '/dev/video0')]
    return LaunchDescription([DeclareLaunchArgument(k, default_value=v) for k, v in args] +
                             [OpaqueFunction(function=setup)])
