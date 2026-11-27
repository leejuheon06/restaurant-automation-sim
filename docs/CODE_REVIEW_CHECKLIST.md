# FryBot 전체 코드 리뷰 체크리스트

작성: 2026-11-16. 대상은 `src/frybot`의 6개 패키지입니다. `frybot_sim`은 실기기 운영에서 쓰는 대역만 포함합니다.
순위 기준: ① 실물이 움직이거나 다칠 수 있는가 ② 실기기에서 검증되지 않았는가 ③ 다른 코드가 얼마나 기대는가.
경로는 `src/frybot/` 기준이고, 줄 수는 작성 시점 값입니다. 결과는 각 항목 아래에 `- 발견:` 줄로 적고, 수정한 내용은 `docs/TROUBLESHOOTING.md`에 기록합니다.

> 체크 표시는 파일을 검토했다는 뜻이며 결함 수정·실기기 검증 완료를 뜻하지 않습니다. A~H 항목별 정정·조치는 [17일 리뷰 통합](2026-11-17_CODE_REVIEW.md)을 참고합니다. 본문의 코드 줄 수와 위치는 당시 값입니다.

## 0순위: 통신 규격 (먼저 읽기, 약 140줄) — 리뷰 완료 2026-11-16

- [x] `frybot_interfaces/msg/Waypoint.msg` (5): `not_before`의 시간 기준(unix 초), 시뮬 시계와 벽시계가 섞이지 않는지
  - 발견(R0-5, 낮음): 로봇이 `not_before`를 읽지 않음. 출발 시각은 관제가 허가를 늦게 내는 방식으로만 지켜짐. 정의 주석과 실제가 다름
  - 조치(2026-11-16): 정의를 실제 동작에 맞춤(참고용 값, 출발 시각은 관제가 허가로 지킴)
- [x] `frybot_interfaces/msg/TrafficGrant.msg` (5): `granted_index`와 `plan_version`의 의미, 옛 버전 허가를 무시하는지
  - 발견(R0-1, 높음): 로봇은 허가를 `plan_version`별로만 저장하고(`mobile_controller._grant`) 지우지 않음. 관제의 `plan_version`은 0부터 다시 셈(`fleet_core.Robot.plan_version`). Task Manager만 재시작하면 새 경로 pv=1에 옛 pv=1의 큰 `granted_index`가 적용되어, 허가받지 않은 구간까지 전진할 수 있음
  - 조치(2026-11-16): 경로 번호를 시각 기반 값에서 시작, 로봇은 옛 허가를 버리고 관제 재시작을 감지
  - 발견(R0-2, 높음): 허가는 락을 잡을 때 한 번만 발행되고(`fleet_core._drive`) 다시 보내지 않음. 메시지가 유실되거나 로봇 구독자가 아직 연결되지 않았으면 로봇은 `WAIT_GRANT`로 계속 서 있음. 관제는 그 노드 락을 계속 잡고 있어 다른 로봇도 막힘. QoS가 RELIABLE이지만 TRANSIENT_LOCAL은 아님
  - 조치(2026-11-16): 진행 중인 경로의 허가를 0.5초마다 재발행
  - 발견(R0-7, 낮음): `task_id`는 로봇이 쓰지 않음
  - 조치(2026-11-16): 기록용임을 정의에 명시
- [x] `frybot_interfaces/msg/RobotStatus.msg` (14): 상태 문자열 목록이 `device_state.py`와 일치하는지, 배터리 단위(0~100)
  - 발견(R0-4, 중간): 실제 `state` 값은 IDLE/MOVING/WAIT_GRANT/PAUSED_GUEST/CHARGING과 팔 작업 이름(LOAD 등). 주석의 ARM_BUSY와 E_STOP은 보내지 않음. `node_id`, `error`는 채우지 않음 → 로봇 쪽 오류(Nav2·도킹 실패, 드라이버 이상)가 상태 보고에 나타나지 않고, 액션 결과로만 전달됨
  - 조치(2026-11-16): `node_id`, `error`를 채우고 주석의 상태 목록을 실제 값으로 수정
  - 실기기 배터리 토픽의 단위(0~1인지 0~100인지)는 2순위에서 `pinky_bringup`과 대조
- [x] `frybot_interfaces/msg/TaskEvent.msg` (11): 상태 문자열을 정리한 곳(주석의 "see docs")이 실제로 있는지
  - 발견(R0-6, 낮음): 참조할 문서가 없음. 실제로 발행되는 RETURNED, RESUMED, REASSIGNED, COOKING이 주석에 없음
  - 조치(2026-11-16): 상태 전체 목록을 메시지 정의에 기재
- [x] `frybot_interfaces/action/NavigateRoute.action` (16): mode 값(NORMAL/GUIDE/YIELD), 결과 reason 목록, 피드백 상태
  - 발견(R0-6, 낮음): mode 주석에 YIELD가 없음. reason에 NAV2_FAILED(로봇)와 REJECTED(관제가 만들어 냄)가 없고, E_STOP은 실제로 보내지 않음
  - 조치(2026-11-16): 주석 수정. `E_STOP`은 비상 정지 채널로 실제 전송됨
- [x] `frybot_interfaces/action/ArmJob.action` (11): job 목록, `params_json`의 형식
  - 발견(R0-7, 낮음): `params_json` 형식이 정해져 있지 않음(현재 `table_id`, `menu`). 서빙 팔 액션 서버는 취소를 받지 않아(cancel_callback 없음) 비상 정지가 팔 작업을 멈추지 못함. 실물 팔이 붙으면 중간 이상
  - 조치(2026-11-16): 키 정의, 서빙 팔 액션 취소 지원, 비상 정지 시 팔 작업 취소. 조리 팔 대역은 미지원
- [x] `frybot_interfaces/srv/*.srv` (6개, 41): `AdminCommand`와 `FleetCommand`의 역할 구분, 실패 응답 규칙
  - 발견(R0-6, 낮음): `AdminCommand` 주석의 CANCEL_VISIT는 구현이 없어 "unknown command"가 돌아옴. 구현된 END_USE, SET_STANDBY, MOVE_TO_VERTEX는 주석에 없음. `FleetCommand`에도 SET_STANDBY, MOVE_TO_VERTEX가 없음
  - 조치(2026-11-16): 두 서비스의 명령 목록을 구현대로 수정
- [x] `frybot_interfaces/CMakeLists.txt`, `package.xml`: 문제 없음
- 규격 밖 관찰(R0-3, 중간): 로봇에게 가는 비상 정지 전용 채널이나 관제 생존 신호가 없음. ESTOP은 액션 취소(`cancel_route`)로만 전달됨. 목표가 아직 수락되지 않은 순간에는 취소할 핸들이 없어 목표가 남음(허가가 없어 로봇은 서 있음). 관제나 네트워크가 끊기면 로봇은 이미 허가받은 구간까지는 계속 감. 1순위에서 로봇 쪽 처리를 이어서 확인
  - 조치(2026-11-16): `FleetHeartbeat`(`/fms/heartbeat`) 추가. 상세는 `docs/2026-11-16_CHANGES.md` 4장

## 1순위: AMR 제어기 (`mobile_controller.py`, 690줄) — 리뷰 2026-11-17 (도킹은 4순위에서)

- [x] 파라미터와 초기화(`__init__`): `drive`, `pose_source`, `battery_topic` 등 실기기용 기본값
  - 발견: 실기기 값은 `robot.launch.py`가 지정(`drive=nav2`, `pose_source=tf`, `battery_topic`). 문제 없음. 배터리 단위는 R2-3
- [x] 위치 입력(`_odom`, `_tf_pose`, `_initial_pose`, `_gz_pose`): TF를 못 받을 때 동작, AMCL 초기 자세 전송 시점
  - 발견(R1-2, 중간): `_tf_pose`가 최신 TF를 시각 확인 없이 씀. AMCL이 죽어도 옛 자세로 직접 주행(양보 후진)을 계속함. `navigator.py`의 `bond_timeout: 0.0`이라 lifecycle manager도 알아채지 못함. 한계는 뒤쪽 라이다 0.10 m 검사뿐. `except Exception`은 `tf2_ros.TransformException`으로 좁힐 수 있음
- [x] 경로 실행(`_navigate`): 허가 받은 구간까지만 전진하는지, 취소·선점 처리, `plan_version` 비교
  - 발견(R1-6, 낮음): `route[0]`까지는 허가 없이, 거리 제한 없이 이동(`reached = -1`일 때 `tgt = 0`). 관제가 1 m 이내 노드만 주므로(`rejoin_max_dist`) 실제로는 제한되지만 로봇 쪽 방어는 없음
  - 발견(낮음): 선점 시 옛 실행 스레드의 `_stop()`이 새 경로가 막 보낸 Nav2 목표를 취소할 수 있음(`self.n2` 공유). 새 루프가 다시 보내므로 스스로 회복
- [x] 허가 수신(`_grant`): 다른 로봇·옛 계획의 허가 무시
  - 발견: 문제 없음. 다른 로봇·옛 `plan_version` 허가를 버리고, 유실은 0.5초 재발행으로 메움
- [x] 직접 주행(`_step_toward`, `_rotate`, `_creep`): Nav2를 거치지 않는 경로. 장애물 검사가 없는 상태에서 속도와 거리 한계
  - 발견(R1-1, 높음): `drive=nav2`에서 `_stop()`이 Nav2 목표만 취소하고 0 속도를 보내지 않음. 실측 지도의 양보 후진(`_step_toward`로 `cmd_vel` 직접 발행) 중 경로가 취소·선점되면 마지막 속도가 남음. `pinky_bringup/bringup.py`의 `twist_callback`에 `cmd_vel` 시간 초과가 없어 허가받지 않은 구간으로 계속 후진할 수 있고, 이때 뒤쪽 라이다 검사도 돌지 않음. 도킹 `_creep`(start/settle 단계)도 같음(실측 지도에는 도크가 없어 시뮬에만 해당). 확인 필요: 모터 드라이버 자체의 명령 시간 초과
  - 조치(2026-11-17): `_stop()`이 `drive != kinematic`이면 항상 0 속도를 한 번 발행(T-22). 실기기 미확인
  - 발견(낮음): `_rotate`(도킹 회전·트림)에 시간 제한이 없음. `_creep`은 4초 제한 있음
- [x] Nav2 연동(`_nav2_segment`, `_nav2_accepted`, `_nav2_result`, `_nav2_cancel`, `_refresh_costmap`, `_set_speed_limit`): 3회 실패 후 직접 주행으로 바뀌는 조건
  - 발견: 실측 지도에서는 직접 주행으로 바꾸지 않고 구간 재시도(`nav2_retries`) 뒤 `NAV2_FAILED`를 돌려줌. "3회 실패 후 직접 주행"은 시뮬 지도에만 해당. 문제 없음
- [x] 도킹(`_dock_segment`, `_detected`, `_dock_accepted`, `_dock_result`, `_dock_cancel`): 4순위에서 다시 봄
  - 발견(2026-11-20): 4순위 항목에서 함께 봄(아래 4순위 참고)
- [x] 손님 안내(GUIDE): 후진 속도, 손님 이탈(`follow_pause_dist`, `guest_timeout`) 처리
  - 발견(R1-3, 낮음): 손님 이탈 검사가 `/sim/world_state`에 의존해 실기기에서는 검사 없이 후진 안내만 함. `REAL_ROBOT_GUIDE.md` "아직 없는 것"에 이미 적혀 있음
  - 조치(2026-11-17): 검사를 `/frybot/guest_track` 토픽 기준으로 바꾸고 실측 지도 안내 후진 추가(T-28). 실기기 추적 입력은 아직 없음
- [x] 비상 정지와 통신 끊김: 관제와 연결이 끊기거나 비상 정지가 오면 `_stop`이 반드시 불리는지
  - 발견: 비상 정지와 `WAIT_FMS`는 0 속도를 따로 보내 정상. 일반 취소·선점은 R1-1
  - 발견(R1-5, 낮음): 노드 종료(`main`) 때 0 속도를 보내지 않음. 직접 주행 중 노드가 죽으면 마지막 속도가 남음
  - 발견(2026-11-18, 낮음): `stop_all.sh`로 끝낼 때 경로 실행 중이던 제어기가 컨텍스트 종료 뒤 `_stop()`의 0 속도 발행에서 `RCLError`(publisher's context is invalid)를 냄. P1(실기기 정리) 전부터 있음(Gazebo 로그). 미수정
- [x] 팔 작업(`_arm_job`): 실기기 서빙 팔이 없을 때의 동작
  - 발견(낮음): 실기기에 서빙 팔이 없어도 시간만 지나면 성공을 돌려줌(대역). 취소와 비상 정지는 처리함
- [x] 상태 보고(`_publish`): 주기, 상태 코드, 오류 필드
  - 발견(R0-8, 낮음): `YIELD`, `YIELD_BLOCKED` 상태를 보내는데 `RobotStatus.msg` 주석의 상태 목록에 없음
  - 발견(R1-4, 낮음): 실기기에서도 가짜 바퀴 관절값(`l_wheel_joint` 등)을 `/pinkyN/joint_states`에 10 Hz로 발행. `pinky_bringup`도 같은 토픽에 `left_wheel_joint`를 냄. 확인 필요: RViz 모델 영향
  - 조치(2026-11-18): 가짜 바퀴 관절값, map → base TF, 가짜 배터리, `/gz/model_poses`, `/sim/world_state`를 `sim_backend.py`로 옮겨 시뮬 값일 때만 냄(T-36). 실기기 RViz 표시는 실기기 확인 필요

## 2순위: 로봇 기동과 Nav2 설정 (약 390줄)

- [x] `frybot_mobile/launch/robot.launch.py` (58): `pinky_bringup` 네임스페이스 씌우기, TF 토픽 분리, `drivers:=false`, 맵 경로
  - 발견: 문제 없음
- [x] `frybot_mobile/launch/navigator.launch.py` (31): `mode:=real`의 시계와 프레임 이름
  - 발견: 문제 없음
- [x] `frybot_mobile/frybot_mobile/navigator.py` (58): 노드 목록, lifecycle, 임시 파라미터 파일 생성
  - 발견(낮음): `bond_timeout: 0.0`으로 Nav2 노드가 죽어도 감지하지 않음(R1-2와 연결). 임시 파라미터 폴더(`mkdtemp`)를 지우지 않음
- [x] `frybot_mobile/config/nav2_store.yaml` (230): 속도·가속, footprint, 목표 허용 오차, costmap 레이어와 inflation, AMCL, 도킹 게인
  - 발견(R2-1, 낮음): 주석이 실제와 다름. `amcl.set_initial_pose`의 "제어기가 초기 자세를 보냄"은 실측 지도에서 해당 없음. 머리말의 "시뮬과 실기기에서 그대로 사용"과 달리 `navigator.py`가 실측 지도에서 `use_rotate_to_heading`, `allow_reversing`을 덮어씀
  - 조치(2026-11-18): 머리말과 `amcl.set_initial_pose` 주석을 실제 동작에 맞춤(실기기 정리 P1)
  - 발견(R2-2, 낮음): 지도 해상도 5 cm(`test_map_v001.yaml`)에 `xy_goal_tolerance` 1.5 cm. 전역 costmap `resolution: 0.01`은 static layer에서 무시됨. 확인 필요: 실기기 도착 판정 지연
- [x] `frybot_mobile/config/segment_bt.xml` (12): 회복 동작이 없는 설계가 실기기에서 안전한지
  - 발견: 회복 동작 없음은 설계대로. 실기기 안전성은 확인 필요
- [x] `frybot_mobile/package.xml` (27), `setup.py`: 로봇 설치 의존성
  - 발견(R16-30, 낮음): 기존 G17 여전함. `geometry_msgs`·`nav_msgs`·`sensor_msgs`·`std_msgs`·`tf2_msgs`·`launch`·`launch_ros`·`ament_index_python`·`python3-yaml` 미선언, test_depend `python3-pytest` 없음. setup.py 의 `config/*` 설치는 정상
- [ ] 대조: `pinky_pro/pinky_bringup`이 실제로 내는 토픽과 프레임 이름(수정하지 않고 확인만)
  - 발견(일부만 대조): `cmd_vel` 시간 초과 없음(R1-1), 바퀴 관절 이름 `left_wheel_joint`/`right_wheel_joint`(R1-4)
  - 발견(R2-3, 낮음): `battery/percent`가 0~100인지 확인하지 못함. 0순위의 메모가 그대로 남음
  - 발견(2026-11-20): 이번에도 대조하지 않음(외부 저장소, 실기기 확인 필요)

## 3순위: 공용 기하 정보 (약 560줄)

- [x] `frybot_control/frybot_control/layout.py` (294): 치수 변환 `m()`, `SAFE_DIST`, 로드맵 `build_roadmap()`, `docks()`, 마커 ID·크기·높이, `HOME_SPOTS`, `Graph`
  - 발견(R16-31, 낮음): `m()`·`SAFE_DIST`·`build_roadmap()`·`docks()`·마커·`HOME_SPOTS`·`Graph` 문제 없음. `ROBOT_W, ROBOT_L`(:12) 참조 0건(삭제 후보 D-08). 머리말 "single source of truth" 는 실측 지도 이후 맞지 않음(주석 오류 목록)
- [x] `frybot_control/frybot_control/map_catalog.py` (52): 활성 맵 선택, 맵별 좌표계
  - 발견(R16-32, 낮음): `selected_map_id()`(:19-25) 호출 0건(삭제 후보 D-09), 이를 쓴다는 주석(:30-31)이 틀림
- [x] `frybot_control/frybot_control/maps/test_map_v001/` (`roadmap.json` 151, `.yaml` 6, `.pgm`): 원점, 해상도, 로드맵과 맵의 일치
  - 발견(2026-11-20): 실측 지도 6개 모두 노드가 빈 칸 위(pgm 값 100 이상), homes·waiting 노드 존재. `docking_candidates` 키는 읽는 코드 0곳(README 형식 표에만 있음, 확인 필요)
- [x] `frybot_control/frybot_control/store_map.py` (52): `export_map` 출력이 실기기 map_server와 맞는지
  - 발견(2026-11-20): proto 출력과 maps/proto 의 키·크기 일치. 머리말 "the real robots load the exported file" 은 실측 지도를 쓰는 지금과 다름(주석 오류 목록)
- [x] `frybot_control/setup.py`: 맵 파일이 `package_data`로 설치되는지
  - 발견(2026-11-20): json·yaml·pgm 이 package_data 로 설치됨, entry point 6개 정상. test_depend `python3-pytest` 없음(낮음)

## 4순위: 정밀 도킹 (약 220줄 + 1순위의 도킹 부분)

- [x] `frybot_mobile/frybot_mobile/aruco_dock_detector.py` (216): 카메라 보정값 출처, 영상 시각과 오도메트리 맞추기, 마커를 놓쳤을 때 4초 유지, 잘못 인식한 경우
  - 발견(R16-20, 낮음): 보정값은 `camera_info` 가 없으면 hfov 이상 핀홀·왜곡 0. 실측 지도 도크에 마커가 없어 실기기에서는 뜨지 않음(시뮬 전용). 잘못 인식 방어는 id 일치 + 법선 방향뿐(재투영 오차·지도 위치 차이로 거르지 않음). 영상 시각 보간·4초 유지는 정상. 파라미터 `robot_id`(:58) 선언만 함
- [x] `mobile_controller.py`의 `_dock_segment` 이하: 도킹 실패와 시간 초과, 벽 쪽으로 계속 미는 경우
  - 발견(R16-21, 중간, [안전] 확인 필요): 도킹 단계에서 앞 라이다 스캔이 1초 넘게 없을 때(`front is None`)도 도킹을 취소하고 도착(성공)으로 침(:1009-1024, 1064-1065, 1100). 멈추는 방향이라 충돌은 없으나 관제는 OK 를 받고 다음 작업(LOAD)을 시작. 실패 사유로 돌려줄지 판단 필요
  - 발견(R16-22, 중간, [안전] 확인 필요): 도킹 실패·지나침 뒤 Nav2 대체 경로(`drive` 단계, :1033-1048)에는 T-46 앞 라이다 검사가 없음(costmap 충돌 검사만)
  - 발견(R16-23, 중간, 확인 필요): pose_dock(실기기 D1_STOP) 접근 종료 `along <= 0.006`, 지나침 `along < -0.02` 를 AMCL 자세로 판정. cm 단위 흔들림이 mm 판정을 좌우(실기기 정차 오차 측정 필요)
  - 발견(R16-24, 낮음): align/turn 회전(:976, 989)에 시간 제한 없음(trim 은 `dock_trim_timeout` 생김). 선점된 옛 스레드의 `_dock_cancel()` 이 새 도킹 상태 `self.dk` 를 지움(새 루프가 처음부터 다시 해 회복). `r.status == 4` 숫자 대신 `GoalStatus.STATUS_SUCCEEDED` 권장
- [x] `nav2_store.yaml`의 `docking_server` 부분
  - 발견(2026-11-20, 낮음): `max_retries 0`·`dock_approach_timeout 20`·`initial_perception_timeout 4` 는 제어기의 대체 흐름과 맞음. `wait_charge_timeout` 은 충전 도크가 아니라 무의미(무해). "server aims 0.25 m behind" 주석은 opennav_docking 소스와 대조 못 함(확인 필요)

## 5순위: 관제의 실기기 입력 처리 (약 1,200줄)

- [x] `frybot_control/frybot_control/task_manager_node.py` (141): QoS, 액션 수락 거부와 결과 유실, 서비스 콜백
  - 발견(낮음): `_submit`의 `except Exception`. 생존 신호 타이머가 `_tick`과 같은 단일 스레드라 계획이 2초 넘게 걸리면 로봇이 `WAIT_FMS`로 섬(멈추는 방향)
- [x] `fleet_core.py`의 `on_robot_status`, `on_route_progress`, `on_route_result`: 순서가 뒤바뀐 메시지, 옛 `plan_version`
  - 발견(R16-02, 중간): `on_route_result` 가 결과의 `reached` 를 쓰지 않음(:1600, 실패 분기). 진행 피드백이 유실되면 idx·node·락이 실제보다 뒤인 채로 재시도 계획(빈도 확인 필요)
  - 발견(R16-03, 낮음): 실패한 경로 뒤 `heading` 이 남음(실패 분기·`_claim_vertex` 가 지우지 않음). T-45 홈 복귀 재시도 조건 `not r.heading`(:394-397)이 다시 참이 되지 않아 복귀가 멈출 수 있음(`_move_to_vertex` 만 따로 지움 :1849)
- [x] `fleet_core.py`의 `_drive`, `_blocker`, `_resolve_stall`, `_retreat`, `_yield_done`: 정체 판정 시간, 양보 반복
  - 발견(R5-3, 중간): 계획에 든 대기와 "양보하지 않고 우회"한 판단이 로그에 남지 않음. 11/16 실기기 실행에서 겹침 6번이 모두 락 대기 → 정체 재계획으로 처리됐는데 양보 이벤트는 0건(T-23)
  - 조치(2026-11-17): `PLAN_WAIT`, `YIELD_SKIP` 이벤트 추가(판단은 그대로)
  - 발견(R5-6, 중간): 상대가 이미 양보해 물러나는 중인데 `_resolve_stall`이 나도 물러나게 함. 둘이 서로 30초씩 기다림(T-24)
  - 조치(2026-11-17): 상대가 나에게 양보 중이면 물러나지 않고 기다림
  - 발견(R5-7, 중간): `_make_way`가 비킬 자리가 없으면 포기함. 유휴 로봇 둘이 겹쳐 막으면 `PLAN_FAIL`이 끝없이 반복(T-24)
  - 조치(2026-11-17): `_clear_exit` 추가. 출구를 막고 선 유휴 로봇부터 비키게 함(한 단계)
  - 발견(2026-11-20): 기존 R5-3·R5-6·R5-8 해결 상태 유지, R5-7 한 단계 처리 그대로. 주석 오류: `_yield_done` "or 30 s"(되돌아가기는 `YIELD_BACK_WAIT` 60초), `_stray`·`_pos_blocker`·`_table` 의 6 cm/SAFE_DIST 표현이 T-52 의 `pos_block_dist` 와 다름(주석 오류 목록)
- [x] `fleet_core.py`의 `_start_move`, `_adopt`, `_plan_joint`, `_stop_route`: 재계획 중 허가 일관성
  - 발견(R5-4, 중간): 계획 시간 모델(거리 ÷ 0.072 m/s, 구간 지연 0)이 실기기(2.27초 + 거리 ÷ 0.135 m/s)와 달라 실제 소요가 ETA의 1.76배. 시간 예약이 실행과 어긋남. `fleet_bench`와 경량 시뮬의 시간 수치도 같은 모델이라 실기기 근거로 쓰기 어려움(T-23). 미수정
  - 조치(2026-11-18): 계획에 구간 지연(`plan_overhead`, 기본 0.0)을 추가. 보정값(0.135 m/s, 2.27초)으로 모의의 ETA 비율이 1.6배에서 1.00~1.10이 됨. 실기기 기본값은 0.0이고 실기기 확인 필요(T-23, IMPROVEMENT_PLAN 9.6)
  - 발견(R5-5, 낮음): 양보 기준(1.4배, 0.4 m)이 실측 지도에서 검증되지 않음. 서 있는 로봇이 길을 막는 조합의 41%가 기준 미만으로 우회(`replay_run --find-yield`)
  - 발견(R5-8, 중간): 우선순위 뒤집기에 순위 규칙·간격이 없어 마주 본 두 로봇이 1초마다 서로 계획을 취소시킴(T-24)
  - 조치(2026-11-17): 뒤집힌 로봇은 8초(`FLIP_HOLD`) 동안 되뒤집지 못함. 실기기 미확인
  - 발견(R16-06, 낮음): `_request`(:1213-1222) 출발 시각에 `_start_move` 의 "노드로 돌아가는 길" 항(:814-815)이 없어 공동 계획에서 다른 로봇 출발이 조금 이르게 잡힘. 기존 R5-12(`_adopt` 가 `yield_to` 를 남김)·R5-13 여전함
- [x] `fleet_core.py`의 `command`: ESTOP, RESUME, REASSIGN, CANCEL_TASK, MOVE_TO_VERTEX
  - 발견(R5-2, 낮음): 전체 비상 정지 명령이 없음. `ESTOP`은 로봇 한 대씩만
  - 발견(R16-01, 높음, [안전] 확인 필요): 실측 지도에서 임무를 떼어 내도 로봇이 옛 목적지로 계속 갈 수 있음. `_go_home` 이 `map_id` 면 바로 return(:721-723, 직접 확인)이라 정리가 안 됨. ① `CANCEL_TASK`(:2043-2055): 경로만 취소하고 `pending_goal` 을 남겨 다음 `_drive` 가 취소된 목적지로 다시 `_start_move` ② `REASSIGN`(:2029-2041): 경로·`pending_goal` 둘 다 남김 ③ 재배정 비교(`_schedule` :546-556)에서 넘겨준 로봇이 옛 첫 지점으로 계속 감. 코드 경로 추적만, 모의 재현 안 함
  - 발견(R16-04, 낮음): `RETRY_TASK`(:2015-2027)가 로봇 온라인 여부를 보지 않음. 기존 R5-2(전체 비상 정지 없음) 여전함. PAUSE·ESTOP 분기 중복(삭제 후보 D-04)
- [x] `fleet_core.py`의 오프라인·배터리 처리(`_available`, `_go_home`, `_park_goal`, `robot_state`)
  - 발견(R5-9, 중간): 같은 입력에도 판단이 실행마다 다름. `_blocker`가 문자열 집합 순서(PYTHONHASHSEED)로 막는 로봇을 고르고, 물러난 뒤 재시도 시각에 전역 random을 씀(W5, T-31)
  - 조치(2026-11-18): 정렬된 순서로 보고 FleetCore 자체 난수(rng_seed)를 씀. 모의 도구의 해시 씨앗 재실행 삭제(T-31)
  - 발견(R5-10, 중간): 이동 명령을 끝낸 로봇의 도착 뒤 점유를 4초로 예약해, 뒤 로봇이 막다른 자리까지 들어와 둘 다 멈춤. 같은 목적지 명령도 받음(W5, T-32)
  - 조치(2026-11-18): MOVE 임무의 마지막 이동은 도착 뒤 점유를 무한대로 예약하고, 같은 목적지(또는 너무 가까운 노드)로 가는 로봇이 있으면 이동 명령을 거절(T-32). 실기기 확인 필요
  - 발견(R5-11, 중간): 계획 실패가 끝없이 반복돼도 임무 보류·알림이 없음(W5에서 1,380초, T-33)
  - 조치(2026-11-18): 같은 목적지 계획 실패가 20초를 넘으면 SUSPENDED(PLAN_FAIL)로 보류하고 알림, RETRY_TASK로 재개(T-33). 실기기 확인 필요
  - 발견(R5-12, 중간): `_adopt`가 새 경로를 받을 때 `pending_goal`만 지우고 `yield_to`를 남김. 양보하러 물러나는 중 새 임무를 받은 로봇이 계속 "양보 중"으로 보여, `_resolve_stall`의 T-24 대기 규칙으로 두 로봇이 서로 기다림(모의 rush 41초, 기본 조합 1,200회 중 36회에서 서로 가리킴). 미수정, 기획안 9.10(W12 B)
  - 발견(R5-13, 낮음): 우선순위 뒤집기의 낙관적 예약표가 경로 없이 다시 시작을 기다리는 로봇을 5초 점유로 봐, 그 로봇을 지나는 계획을 세움. 세 대가 한 줄 통로에서 맞물려 20초 보류(기존 모델 + 보정 moves3 1회). 미수정, 기획안 9.10(W12 A)
  - 발견(R5-1, 중간): 경로 도중 로봇이 끊기면 `tick`이 `online=False`만 하고 경로·락·임무를 그대로 둠. `_drive`는 `online`을 보지 않아 허가도 계속 냄. 다른 로봇이 그 락에 막힘
  - 발견(2026-11-20): 기존 R5-1 해결(A3: 끊긴 로봇에 허가 안 냄, offline_hold 뒤 보류). `_go_home` 실측 지도 return 은 R16-01. 주석 오류: `_unavailable_reason` "같은 순서"(실제 순서 다름)
- [x] `fleet_core.py`의 나머지(`_schedule`, `_run_phase`, `_cook_tick`, `snapshot`)
  - 발견(R16-05, 낮음): `_rank` 가 로봇 id 마지막 한 자리만 봄(:1424, pinky1=pinky11). 시뮬 조리: 취소된 조리 작업의 인계대 칸(`slots`)을 돌려주지 않고 팔 작업도 취소 안 함(:2101, 2124-2127, 실측 지도는 COOK 거절이라 무관). `_cook_state`/snapshot `cooking.jobs[].state` 를 읽는 곳 0건(삭제 후보 D-03)
- [x] `frybot_control/frybot_control/device_state.py` (83): 상태·오류 코드 매핑
  - 발견: 문제 없음

## 6순위: 업무 상태와 기록 (약 620줄)

- [x] `frybot_control/frybot_control/central_control_node.py` (196): AI HTTP 수신(:8100) 입력 검증, 명령 전달, 스레드와 콜백 그룹
  - 발견(R16-10, 중간): 관제가 임무를 거절하면(`_submitted` :81-87) 오류 로그만 남고 Restaurant 에 알리지 않음. T-47·stations 부족 거절 때 음식 READY·테이블 COLLECTING/ASSIGNED 에 머묾
  - 발견(R16-11, 중간, 확인 필요): `rest.admin` 의 `int(target)`(restaurant.py:261, 278)에 숫자가 아닌 값이 오면 ValueError 가 서비스 콜백 밖으로 나가 노드가 죽을 수 있음(화면은 숫자만 보냄)
  - 발견(R16-12, 낮음): `_admin` 의 `cli_fleet.call`(:125) 시간 제한 없음. HTTP 스레드가 잠금 없이 `ai_latest` 에 쓰고 `_tick` 이 잠금 밖에서 dumps(:159-160, 191-201). `ai_latest`/`ai` 키를 읽는 곳 0건(삭제 후보 D-11). 기존 R7-1(:8100 인증 없음) 여전함
- [x] `frybot_control/frybot_control/restaurant.py` (301): 상태 기계 전이, 테이블 중복 배정 방지, 반납 확인 후 해제
  - 발견(2026-11-20): 중복 배정 방지·반납 확인 후 해제 문제 없음. 발견(R16-13, 낮음): 실측 지도에서 `tables = {}`(:29)라 접수·주문 항상 거절(의도인지 확인 필요). COLLECT 가 SUSPENDED/CANCELED 로 끝나면 테이블이 COLLECTING 에 남음(SET_TABLE 로 풀 수 있음)
- [x] `frybot_control/frybot_control/db.py` (39): 스키마, 유니크 인덱스
  - 발견(R16-14, 낮음): 모든 저장이 `INSERT OR REPLACE`(:29)라 부분 유니크 인덱스 위반 때 실패 대신 기존 방문 행을 지움. `Store.insert`(:32-33) 호출 0건(삭제 후보 D-10)
- [x] `frybot_control/frybot_control/runlog.py` (45): 파일 쓰기와 동시성
  - 발견(2026-11-20, 낮음): `_commit` 의 `except Exception` 여전함. central_control 의 서로 다른 콜백 그룹이 잠금 없이 같은 csv 에 씀(섞일 가능성 낮음, 보장 안 됨)
- [x] `frybot_control/frybot_control/analyze.py` (59)
  - 발견(R16-15, 낮음): :44 `f'알고리즘 변경: ' + ', '.join(...) or '-'` 는 `+` 가 먼저라 '-' 가 나오지 않음(F541 포함, 직접 확인). `open(path)` 미닫음(:20), runs 가 비면 IndexError(:55)

## 7순위: 운영 진입점 (약 530줄)

- [x] `frybot_bringup/launch/real.launch.py` (46): `sim_cooking`, `ROS_DOMAIN_ID`, 맵 프로필
  - 발견(R7-2, 중간): 함께 쓰는 `frybot_bringup/config/robots.yaml`에 SSH 비밀번호와 로봇 IP가 있음. 아직 git에 없는 파일이라 그대로 커밋하면 저장소에 들어감. `~/.config/frybot/robots.yaml`로 옮기는 편이 나음
  - 조치(2026-11-18): 등록부를 `~/.config/frybot/robots.yaml`로 옮기고 패키지에는 비밀번호 없는 `robots.example.yaml`만 둠. `.gitignore` 추가, 등록부가 없으면 안내(T-30)
- [x] `frybot_web/frybot_web/web_service_node.py` (101): 입력값 검증, 서비스 시간 초과, 관리자 명령 노출 범위
  - 발견(R7-1, 중간): 관리자 API가 인증 없이 `0.0.0.0`에 열림. 같은 Wi-Fi에서 `RESUME`(비상 정지 해제), `MOVE_TO_VERTEX`를 보낼 수 있음. `central_control_node.py`의 AI 수신(:8100)도 같음
  - 조치(2026-11-18): `web_service`의 `admin_local_only` 기본을 True로 바꿈. 런치 없이 띄워도 관리자 명령은 관제 PC(또는 `admin_token`)에서만 받음(T-34). AI 수신(:8100)은 그대로
- [x] `frybot_web/frybot_web/httpd.py` (64): 경로 처리, 예외 처리
  - 발견(낮음): CORS `*`, `except Exception` 2곳. 정적 파일 경로 처리(`/`와 `..` 차단)는 문제 없음
- [x] `frybot_web/static/` (`admin.html` 128, `map.js` 130, `table.html` 20, `reception.html` 10, `index.html` 7, `app.css` 25, `stations-test_map_v001.json` 8)
  - 발견(R16-40, 낮음, 확인 필요): admin.html 명령 버튼이 pointerdown·click 둘 다 보내고 800 ms 안의 click 만 버림. 길게 누르거나 `data-confirm` 대화상자로 800 ms 를 넘기면 같은 명령이 두 번 갈 수 있음(:176-187, GO_HOME ALL·CANCEL_TASK 등)
  - 발견(R16-41, 낮음): 이력 '통행' 필터의 `STALL` 접두어 이벤트 없음(:572). 서버 값 일부를 `esc()` 없이 innerHTML(:408, 437, 617). table.html 은 `?id=` 가 없으면 1번 테이블(:45). index.html 테이블 1~6·손님 시뮬 링크 고정. map.js `drawMap` 은 customer.html 만 쓰고 ui.js `drawStore` 와 중복. app.css `.big`·`.center` 안 씀. stations json 4개 문제 없음
- [x] `frybot_web/package.xml`, `frybot_bringup/package.xml`
  - 발견(R16-42, 낮음): frybot_web 에 `ament_index_python`, frybot_bringup 에 `launch`·`launch_ros`·`ament_index_python`·`ros_gz_bridge`·`ros_gz_sim` exec_depend 없음

## 8순위: 기본 알고리즘 (약 290줄)

- [x] `frybot_control/frybot_control/planners/base.py` (100): `ReservationTable`, 락 규칙, `pad`
  - 발견(2026-11-20): 문제 없음
- [x] `frybot_control/frybot_control/planners/sipp.py` (68)
  - 발견(R16-16, 낮음, 확인 필요): 출발 노드 안전 구간을 `[(t0, s_end)]` 하나로 고정(:22). 물러났다 출발 노드로 되돌아오는 계획을 못 세우거나 돌아감
- [x] `frybot_control/frybot_control/planners/__init__.py` (19)
  - 발견(2026-11-20): F401 5건은 기존 유지 결정 그대로(fleet_core.py:18 이 이 경로로 씀)
- [x] `frybot_control/frybot_control/schedulers/__init__.py` (125): `min_cost_eta_rh`, 재배정 조건
  - 발견(R16-17, 낮음, 확인 필요): 후보가 20000 을 넘으면 SciPy 사용, 비용에 inf 가 섞이면 `linear_sum_assignment` ValueError(:79, ImportError 만 잡음). 현재 규모에서는 해당 없음

## 9순위: 대역, 비교용, 시뮬 런치 (약 1,600줄)

- [x] `frybot_arm/frybot_arm/arm_controller.py` (2026-11-17 `frybot_sim/cook_arm_node.py`에서 옮김), `master_controller.py`, `frybot_sim/frybot_sim/ai_server.py` (76), `frybot_sim/package.xml`
  - 발견(R16-43, 낮음): arm_controller 는 ReentrantCallbackGroup 이라 같은 팔에 목표 두 개가 동시에 돌 수 있음(관제 자원 조율에 기댐). 기존 R0-7(조리 팔 취소 미지원) 여전함, master_controller 머리말 "취소 그대로 전달"은 실제와 다름(주석 오류). ai_server 는 `kind`·필수 키가 빠진 프레임 하나에 KeyError 로 수신 루프 전체가 죽음(:57-71). frybot_sim package.xml: `lifecycle_msgs`·`python3-opencv`·`ament_index_python` 없음, `sensor_msgs`·`tf2_ros` 는 쓰지 않음(D-14)
- [x] `frybot_mobile/frybot_mobile/arm_common.py` (50): 서빙 팔과 카메라 대역
  - 발견(2026-11-20, 낮음): `arm_pose` 의 `t` 인자 안 씀(D-07). `CameraStreamer`·`JOINTS`·`REST`·`arm_pose` 가 `frybot_arm/arm_motion.py`·`camera_streamer.py` 와 중복(D-16)
- [x] `frybot_control/frybot_control/planners/cbs.py` (90), `cooperative_astar.py` (84), `independent_astar.py` (37), `rmf.py` (191)
  - 발견(2026-11-20, 낮음): cbs `self.last_nodes`(:78) 쓰기만 함(D-12). cooperative_astar·independent_astar 문제 없음. rmf.py(확인 필요 범주): `safe_dist=0.155` 중복 기재(:40), `req.blocked` 무시, 도우미가 죽으면 ValueError 가 FleetCore 까지 올라감(:93, 비교용 경로만)
- [x] `frybot_control/frybot_control/schedulers/rmf_task.py` (73), `rmf_bridge/rmf_plan_server.cpp` (336), `rmf_bridge/CMakeLists.txt`
  - 발견(2026-11-20): 규칙 점검의 B023(지금 :63 `wait` lambda)은 같은 반복 안에서만 호출되어 버그 아님(해결로 정리 가능). 이동 시간에 `speed × plan_speed_factor` 대신 `c.speed` 를 써 비교 조건이 다름(낮음). rmf_bridge 프로토콜은 Python 쪽과 맞음
- [x] `frybot_control/frybot_control/offline_bench.py` (223)
  - 발견(R16-18, 낮음, 확인 필요): moves 가 아닌 시나리오는 `FRYBOT_MAP_ID` 를 비우지 않아 셸에 실측 지도 값이 남아 있으면 전부 CHECKIN_REJECT 로 끝남. `--map-id` 를 moves 없이 주면 조용히 무시(:814-817). replay_run `start_of` 의 `path[1]` IndexError 가능(:131), `fit_segments` 0 나눗셈(:97)
- [x] `frybot_bringup/launch/sim.launch.py` (182), `gazebo.launch.py` (120), `frybot_bringup/urdf_tools.py` (58), `rviz/sim_store.rviz`(2026-11-18 `frybot.rviz`에서 이름 바꿈)
  - 발견(R16-44, 중간, 확인 필요): gazebo.launch.py 가 sim.launch 에 `map_id` 를 넘기지 않아 셸의 `FRYBOT_MAP_ID` 가 실측 지도면 Gazebo 는 가상 매장, 관제는 실측 지도로 뜰 수 있음(:67, 106-113)
  - 발견(R16-45, 낮음): sim.launch 실측 지도 + `drive:=nav2` 는 Nav2 없이 RViz Nav2 표시만 넣음(확인 필요), 가상 매장은 `auto_home`·`serving_robots` 인자를 받고 안 씀, RViz 임시 폴더 미삭제(:185). 코스트맵 RViz 블록 두 벌 중복(D-17). urdf_tools·sim_store.rviz 문제 없음

## 규칙 준수 점검 (2026-11-17, `CLAUDE.local.md` 코딩 표준)

- ruff(`.claude/ruff.toml`) 1,978건: 80자 초과 1,599, docstring 약 260, import 순서 40. 요청 없이 전체를 다시 포맷하지 않으므로 고치는 부분만 맞춤
- 이유 없는 `except Exception` 9곳: `mobile_controller.py` `_tf_pose`, `aruco_dock_detector.py` `_camera_tf`, `task_manager_node.py` `_submit`, `central_control_node.py` `do_POST`, `httpd.py` 2곳, `runlog.py` `_commit`, `ai_server.py`, `planners/rmf.py`
- 버그 가능성(확인 필요): `schedulers/rmf_task.py:60` 루프 변수 `t`를 묶지 않은 함수(B023)
- 쓰지 않는 import·변수 11건: `planners/base.py`, `cbs.py`, `sipp.py`, `cooperative_astar.py`, `ai_server.py`
  - 조치(2026-11-17): 쓰지 않는 import·변수와 `device_state.APPLIES`, `cooperative_astar._path`의 버려지던 루프를 삭제. `planners/__init__.py`의 5건은 다른 모듈이 가져다 쓰는 다시 내보내기라 그대로 둠
- 가변 기본 인자와 `import *`는 없음
- 이번에 읽지 않은 것: `restaurant.py`, 8·9순위, `frybot_sim`, 웹 정적 파일, `store_map.py`, `analyze.py`, 시뮬 런치, 각 `package.xml`

## 리뷰 뒤 문서

- 현재 실행 명령은 [COMMANDS.md](COMMANDS.md)에 통합. `src/frybot/README.md`와의 일치 여부는 관련 코드 변경 시 확인. 삭제된 REAL_ROBOT_GUIDE.md는 새 작업 대상으로 두지 않음.

## 2026-11-20 전체 리뷰 (작업 지시 16 2단계)

위 [ ] 항목의 결과는 각 항목 아래 `발견(2026-11-20 / R16-xx)` 줄로 적었습니다. 아래는 기존 체크리스트에 없던 파일과 삭제 후보입니다. 이번 리뷰에서는 결함을 고치지 않았습니다. 고칠지는 기획 패널이 정합니다. `[안전]`은 실물이 움직이는 쪽의 결함입니다.

### 기존 목록에 없던 파일

- [x] `frybot_mobile/frybot_mobile/mobile_controller.py` 11-20 변경분(막다른 노드 출구, 앞 라이다, 무진행 감시, 서빙 팔 전달)
  - 발견(R16-25, 낮음): `_arm_job`이 동시에 들어온 두 작업을 막지 않아 `arm_state`·`arm_task`를 덮어씀(:1307-1309). 관제가 한 번에 하나만 보내면 해당 없음(확인 필요)
  - 발견(2026-11-20): 기존 R1-2 해결(`tf_stale_sec`). R1-5(종료 때 0 속도 없음)와 R1-6 여전함
- [x] `frybot_mobile/frybot_mobile/serving_arm_driver.py` (237)
  - 발견(R16-26, 낮음, [안전] 확인 필요): `/fms/heartbeat`를 보지 않음. 비상 정지는 mobile_controller가 목표를 취소하는 길로만 옴. mobile_controller가 죽거나 네트워크가 끊기면 팔은 경유 자세에 닿거나 `move_timeout` 20초가 지날 때까지 움직임(:87, 193)
  - 발견(낮음): `busy.locked()` 검사(:125)와 `with self.busy`(:139) 사이에 경쟁이 있어 거의 동시에 온 두 번째 목표가 대기로 받아짐
- [x] `frybot_mobile/frybot_mobile/auto_localize.py` (392)
  - 발견(R16-27, 낮음): `monitor=false`여도 `check_now`가 건너뛴 이유를 `'not localised'`로 셈(:288-289)
  - 발견(R16-28, 낮음, 확인 필요): 서 있을 때 보정 흐름(스캔 대기 1초 + 발행 0.6초) 사이에 경로가 시작되면 주행 중에 AMCL이 재설정될 수 있음(:296-301, 344-346)
  - 발견: `self.offset`(:74, 179)을 쓰기만 함(확인 필요 범주)
- [x] `frybot_mobile/frybot_mobile/scan_match.py` (364), `sim_backend.py` (149), `launch/navigator.launch.py`, `serving_arm.launch.py`, `config/segment_bt.xml`, `serving_arm.yaml`, `test/test_scan_match.py`: 발견: 문제 없음(주석 1건은 아래 표)
- [x] `frybot_mobile/frybot_mobile/pinky_driver.py` (276)
  - 발견(R16-29, 낮음): `Pinky()` 생성 중 예외가 나면 `main`의 `finally: node.driver.terminate()`(:272)에서 AttributeError가 남. 초기화 실패 경로에서 `terminate()`를 두 번 부름. 17일 E 표의 "초기화 실패 뒤에도 노드가 살아 있음"(:66-91)은 여전함. A1(`cmd_vel_timeout`)은 해결
- [x] `frybot_mobile/frybot_mobile/dynamixel_driver.py` (101)
  - 발견(낮음, 규칙): `from dynamixel_sdk import *`(F403 1 + F405 18 = 19건)는 import * 금지 위반. 쓰는 이름 9개(`PortHandler`, `PacketHandler`, `GroupSyncWrite`, `GroupBulkRead`, `COMM_SUCCESS`, `DXL_LOBYTE`, `DXL_HIBYTE`, `DXL_LOWORD`, `DXL_HIWORD`)를 명시 import로 바꾸는 수정 후보. 이유 없는 `except Exception`과 `print`가 있음(:52-53)
- [x] `frybot_mobile/frybot_mobile/navigator.py`: 기존 `mkdtemp` 미정리·`bond_timeout 0.0` 여전함. `open()` 두 곳에 with가 없음(낮음)
- [x] `frybot_mobile/launch/robot.launch.py`: 기존 E 표의 "`ai_host` 기본 127.0.0.1" 여전함. "실측 지도에 도크가 없는데 도킹 서버가 뜸"은 해결
- [x] `frybot_control/frybot_control/mock_fleet.py` (477)
  - 발견(낮음): 모의 로봇이 `on_route_result`를 보내지 않아 NAV2_FAILED·REJECTED·ROUTE_RETRY 처리가 오프라인 시험에서 빠짐
- [x] `frybot_control/frybot_control/replay_run.py` (395), `device_state.py`, `task_manager_node.py`, `rmf_bridge/*`, `test/*`: 위 항목과 5순위 기존 발견 외에는 문제 없음
- [x] `frybot_web/frybot_web/web_service_node.py` (266), `httpd.py` (96)
  - 발견(R16-46, 낮음): `_call`이 4초 시간 초과로 실패를 돌려줘도 보낸 요청은 취소되지 않음. 화면에 "응답 없음"이 떠도 관제가 나중에 처리할 수 있음(예: `RESUME`, :223-227)
  - 발견(낮음): 형식이 틀린 입력은 400이 아니라 500으로 돌아옴. `Content-Length`에 상한이 없음(httpd:84). httpd의 CORS `*`는 해결, `except Exception` 2곳은 여전함
- [x] `frybot_bringup/launch/real.launch.py`, `robots.launch.py`, `fleet_rviz.launch.py`, `frybot_bringup/*.py`(remote, robot_remote, fleet_rviz, wait_online, sim_net, urdf_tools), `rviz/fleet.rviz`, `config/robots.example.yaml`
  - 발견(R16-47, 낮음): `real.launch.py`는 `remote:=false`이면 등록부를 읽지 않아 로봇이 pinky1 하나가 되지만, `serving_robots`는 등록부를 읽음. 문서의 "every registered robot"과 다름(:11, 67-68, 85-87)
  - 발견(낮음): `robot_remote`에서 host 없는 로봇이 있으면 `load_registry`에서 traceback이 남(`load_arms`의 ValueError만 잡음, :563-570)
  - 그 밖에는 문제 없음. rviz가 구독하는 토픽은 모두 발행처가 있음
- [x] `frybot_sim/frybot_sim/world_node.py`, `customer_ui_node.py`, `scenario_runner.py`, `nav2_watchdog.py`, `gz_world_gen.py`, `static/customer.html`
  - 발견(낮음): world_node 마커 id가 `int(r['id'][-1])`이라 pinky1과 pinky11이 겹침(:252, 258). 나머지는 문제 없음
- [x] `frybot_interfaces/msg·srv·action` 필드별 사용처: 아래 삭제 후보 D-22. `RobotStatus.msg`의 error 목록에 실제로 보내는 `SENSOR_ERROR`가 없고, `SELF_CHECK_ERROR`는 두 번 적힘(주석 오류 표). 기존 R0-5(`not_before`는 참고용) 그대로
- [x] `frybot_description`: 메시 모두 URDF와 dae에서 참조됨. 문제 없음

### 삭제 후보 (승인 전, 아직 지우지 않음)

근거 범위는 src/frybot 전체, scripts/, docs/COMMANDS.md, README.md, src/frybot/README.md입니다. 누적 `Robot.dist`와 snapshot `dist` 키는 사용자 확정으로 제외했습니다.

| # | 파일:줄 | 무엇 | 근거(rg → 결과) | 줄 수 | 위험 |
|---|---|---|---|---|---|
| D-01 | fleet_core.py:87, 248 | `Robot.speed` 필드와 생성자의 `speed=speed`(쓰기만 함) | `rg -n 'r\.speed\|o\.speed\|robot\.speed' src/frybot` → Robot 필드를 읽는 곳 0건(rmf.py:183은 PlanRequest) | 2 | 낮음 |
| D-02 | fleet_core.py:1571 | `on_route_progress`의 `state=''` 인자(본문에서 안 씀) | 본문 `state` 0건. 호출 task_manager_node.py:94, mock_fleet.py:342, 349 | 1+호출 1 | 낮음 |
| D-03 | fleet_core.py:167-185, 2271 | `_cook_state`와 snapshot `cooking.jobs[].state`(읽는 곳 없음) | `rg -n -w _cook_state` → 2건(정의·사용). jobs를 읽는 화면(admin.html:327, 427, 513, map.js:41, 43, world_node:263)은 task·step·retries·menu만 읽음 | 약 20 | 중간: W2(v4 상태도)로 넣은 키라 확인 필요 |
| D-04 | fleet_core.py:1973-1998 | PAUSE·ESTOP 분기 중복(경로 취소, 팔 취소, 보류) | 읽어서 확인 | 약 10 감소 | 낮음 |
| D-05 | fleet_core.py:1832-1834·1876-1878, 948-950·1029·1133 | MOVE 임무 `Task(...)` 생성 중복, 계획 길이 합 계산 3곳 | 읽어서 확인 | 5 | 낮음 |
| D-06 | mobile_controller.py:629-630, 656-657, 926-927, 1165-1166 | `_stop()` 뒤 0 속도 Twist 중복 발행(T-22 뒤로 `_stop`이 이미 냄) | `_stop` 본문 :923-924, `rg -n "_dock_cancel\(" src/frybot` → 2건(정의, `_stop`) | 8 | 낮음. 정지 경로라 그대로 두어도 무방 |
| D-07 | arm_common.py:20, mobile_controller.py:1325 | `arm_pose`의 `t` 인자와 호출의 `time.time()` | `rg -n "arm_pose\(" src/frybot` → 4건, frybot_mobile 호출 1건. frybot_arm은 자기 `arm_motion.arm_pose`를 씀 | 2 | 낮음 |
| D-08 | layout.py:12 | `ROBOT_W, ROBOT_L` | `rg -n -w ROBOT_W src/frybot scripts docs/COMMANDS.md README.md` → 1건(정의) | 1 | 낮음 |
| D-09 | map_catalog.py:19-25 | `selected_map_id()` | `rg -n -w selected_map_id …` → 2건(정의, :30 주석) | 7 | 낮음(주석도 함께 정정) |
| D-10 | db.py:32-33 | `Store.insert`(upsert 별칭) | `rg -n "def insert\|\.insert\(" src/frybot/frybot_control src/frybot/frybot_web` → 정의 1건과 무관한 list.insert·cpp뿐 | 2 | 낮음 |
| D-11 | central_control_node.py:47, 159, 191, 199, 201 | `ai_latest`와 `/frybot/state`의 `ai` 키(쓰기만 함) | `rg -n -w ai_latest …` → 5건, 모두 이 파일. html·js에서 읽는 곳 0건 | 약 5 | 낮음. 토픽을 외부에서 echo로 보는지 확인 필요 |
| D-12 | planners/cbs.py:78 | `self.last_nodes`(쓰기만 함) | `rg -n -w last_nodes src/frybot` → 1건 | 1 | 낮음 |
| D-13 | frybot_sim/frybot_sim/gz_world_gen.py:98-102, setup.py:18 | `main()`과 `gz_world` 실행 파일 | `rg -n gz_world src/frybot scripts docs/COMMANDS.md README.md` → gazebo.launch.py:28(`world_sdf` import), setup.py 등록뿐 | 6 | 낮음 |
| D-14 | frybot_sim/package.xml:13, 15 | `sensor_msgs`, `tf2_ros` exec_depend(코드에서 안 씀) | `rg -n "sensor_msgs\|tf2_ros" src/frybot/frybot_sim` → package.xml 2건뿐 | 2 | 낮음 |
| D-15 | admin.html:572, app.css:13 | 이력 필터의 `STALL` 접두어(그런 이벤트 없음), `.big`·`.center` 클래스 | `rg -n "'STALL" src/frybot` → 0건. `class="…big/center…"` → 0건 | 줄 일부 | 낮음 |
| D-16 | frybot_arm/arm_motion.py:7-9·25-45, camera_streamer.py 전체 | `JOINTS`·`REST`·`arm_pose`·`CameraStreamer`가 frybot_mobile/arm_common.py:6-41과 중복 | `rg -n "class CameraStreamer" src/frybot` → 2건 | 약 40 | 낮음(합치기, 구조 제안 3과 함께) |
| D-17 | sim.launch.py:36-57, 107-139 | 코스트맵 RViz 표시 YAML 두 벌 | 읽어서 확인(들여쓰기만 다름) | 약 25 | 낮음 |
| D-18 | frybot_web/static/map.js:16-54 | `drawMap`(ui.js `drawStore`와 같은 일) | 호출은 frybot_sim/static/customer.html:26뿐 | 약 40 | 중간: 다른 포트(8090) 화면이 8080의 map.js를 불러씀 |
| D-19 | arm_controller.py:103-104, mobile_controller.py:319 | AI 서버로 보내는 `'idle'`·`'amr'` 프레임(대역 ai_server가 처리하지 않음) | `rg -n "'idle'\|'amr'" src/frybot -g '*.py'` → 송신 2곳. ai_server.py:57-71은 fryer·guide·ceiling만 처리 | 2+ | 확인 필요: 실제 AI 서버 형식 |
| D-20 | mobile_controller.py:295-296, 570-580 | `_initial_pose` 타이머(proto 지도 + `pose_source=tf`일 때만 돎) | 런치는 robot.launch.py:121(tf, 실측 지도 필수)과 sim.launch.py:258, 330(gz)뿐 | 13 | 중간: 런치 없이 proto로 단독 실행하는 경우 확인 필요 |
| D-21 | rmf_task.py:20-21 | `uses_eta = False`, `rebalance = False`(Scheduler 기본값과 같음) | `rg -n "uses_eta\|rebalance" schedulers` → 6건 | 2 | rmf 범주라 확인 필요 |
| D-22 | frybot_interfaces | 안 읽는 필드: `RobotStatus`의 `task_id`·`plan_version`·`reached_index`·`node_id`·`arm_state`, `NavigateRoute` Goal의 `robot_id`, `ArmJob` Feedback의 `phase`·`progress`, 각 msg의 `stamp` | 쓰는 곳 mobile_controller.py:1455-1458. 읽는 곳 task_manager_node.py:172 등은 id·x·y·yaw·battery·charging·state·error만 읽음 | 약 12 | 중간: 인터페이스가 바뀌면 로봇 재배포 필요. node_id는 R0-4 조치로 채운 것. `stamp`·`phase`·`progress`는 `ros2 topic/action` 확인용이라 유지 권장 |

삭제가 아닌 수정 후보: `dynamixel_driver.py` import * → 명시 import 9개(F403·F405 19건), `analyze.py:44` F541과 우선순위 버그(R16-15). 둘 다 동작 변경 없음 또는 출력 한 줄 정정.

### 문서 대조 보충 (2026-11-20)

- D-22에서 `SubmitTask.priority`는 삭제 후보에서 제외합니다. `task_manager_node.py`가 `req.priority`를 `FleetCore.submit_task`에 전달하고, 명시한 값은 `Task.priority`가 되어 스케줄러와 양보 우선순위에서 사용됩니다. 저장소의 기존 요청자가 값을 생략하는 것과 서비스 필드가 사용되지 않는 것은 다릅니다.
- D-01~D-22의 검색 결과는 기재된 저장소 범위의 근거입니다. 외부 ROS 클라이언트, CLI 실행 파일, 상태 메시지·snapshot 소비자의 사용 여부까지 입증하지 않으므로 삭제 승인을 뜻하지 않습니다. 특히 D-13 실행 파일과 D-22 인터페이스 필드는 내부 호출 검색만으로 제거를 확정하지 않습니다.
- 위 체크 표시는 해당 시점의 검토 완료이며, 발견 사항 수정 완료·실기기 검증 완료를 뜻하지 않습니다. 파일 줄 번호는 리뷰 당시 위치입니다.

### 확인 필요 후보 (삭제 금지 범주)

- `auto_localize.py:74, 179` `self.offset`(쓰기만 함), `pinky_driver.py:46, 121` `is_initialized`(쓰기만 함), `pinky_driver.py:255-256` 도달하지 않는 `current_voltage is None` 분기, `aruco_dock_detector.py:58` 파라미터 `robot_id`(navigator.py:70이 넘김)
- rmf 비교용: `rmf.py`·`rmf_task.py`·`rmf_bridge`. 코어의 `speed`·`guide_speed`·`arm_until`은 rmf_task가 읽으므로 유지
- `roadmap.json`의 `docking_candidates`(읽는 코드 0곳, README 형식 표에 있음), proto의 `alias`·`waiting`
- README·COMMANDS에 적힌 런치 인자와 관리자 명령은 모두 실제로 쓰임

### 틀린 기존 주석 (고치지 않음, 4단계 전 결정 필요)

| 파일:줄 | 주석 | 실제 |
|---|---|---|
| fleet_core.py:1316-1319 | `_stray`: off_node_dist(6 cm) 안의 흔들림 제외 | T-52에서 6 cm 문턱 제거, `pos_block_dist`로 거름 |
| fleet_core.py:1340-1341, 765-767 | `_pos_blocker`·`_table`: 보고 위치에서 SAFE_DIST 안 | `pos_block_dist`(0.12 m) 기준 |
| fleet_core.py:1389-1390 | `_yield_done`: "or 30 s went by" | 되돌아가는 경우는 `YIELD_BACK_WAIT` 60초 |
| fleet_core.py:1749-1750 | `_unavailable_reason`: `_available`과 같은 순서 | 조건은 같지만 순서가 다름 |
| fleet_core.py:1534-1537 | T-49: 노드 점유·배정·허가 없음 | 전에 잡은 락과 마지막 위치 점유는 남음(확인 필요) |
| fleet_core.py:88 | `heading`: '' when standing on node | 노드 복귀 중에는 `heading == node` |
| mobile_controller.py:8 | pose_source:=tf … sends AMCL the initial pose | proto 지도일 때만. 실측 지도는 `initial_pose`·auto_localize |
| mobile_controller.py:16 | serving arm은 아직 대역 | `serving_arm:=real`이면 실물로 넘김 |
| mobile_controller.py:267 | `self.det`: (yaw, wall time) | 값 4개: yaw, 시각, x, y |
| mobile_controller.py:943-945 | `_dock_segment` 단계 목록 | align·settle 단계가 빠짐, 앞 라이다로 서도 True |
| mobile_controller.py:391-392 | `_scan`: 후진할 때만 평가 | 앞쪽 구역도 평가(T-46) |
| serving_arm_driver.py:13-14 | 이 노드로 넘기는 연결은 아직 없음 | `_arm_forward`가 넘김 |
| pinky_driver.py:2-3 | bringup.py를 그대로 복사, 동작 안 바꿈 | `cmd_vel_timeout`·`serial_port`로 바뀜 |
| robot.launch.py:17 | `ai_host` default: none | 기본 '127.0.0.1' |
| robot.launch.py:13 | 홈 위에서 +x를 보고 시작 | T-49 뒤로 자세를 찾음(문서 의도 확인 필요) |
| auto_localize.py:57 | params: max_score, margin, budget, store_dir | monitor 관련 7개도 씀 |
| scan_match.py:47-48 | status 목록 | `'OK_HOME'`이 빠짐 |
| map_catalog.py:30-31 | 오프라인 도구가 `selected_map_id`를 씀 | 호출 0곳 |
| store_map.py:1-2 | 실기기가 export 파일을 씀 | 실기기는 실측 지도 |
| layout.py:1 | map, roadmap의 single source of truth | proto만 해당 |
| robot_remote.py:534 | `--robots-file`: 없으면 패키지 파일 | 11-18 P2에서 대체 없앰, 안내 후 종료 |
| web_service_node.py:1 | holds no state | 마지막 상태 메시지를 들고 있음(업무 상태는 없음) |
| master_controller.py:7-8 | 취소 그대로 전달 | arm_controller가 취소를 받지 않음 |
| RobotStatus.msg:19-25 | error 목록 | `SENSOR_ERROR`가 빠짐, `SELF_CHECK_ERROR` 중복 |
| real.launch.py:11 | default: every registered robot | `remote:=false`면 pinky1만 |

### 조치 (3단계 1차, 2026-11-20)

- 조치(2026-11-20): 승인된 삭제 D-01, D-02, D-07, D-08, D-09, D-10, D-12, D-13, D-14, D-15를 반영했습니다. 지운 자리마다 `# [수정 2026-11-20] 삭제: …` 주석을 남겼고, D-09는 관련 주석의 함수 이름도 함께 고쳤습니다.
- 조치(2026-11-20): `dynamixel_driver.py`의 import *를 명시 import 9개로 바꿨습니다(F403·F405 19건 해소).
- 조치(2026-11-20): `analyze.py:44` 우선순위 버그를 고쳤습니다(R16-15, T-54).
- 유지(기획 패널 결정): D-06, D-19, D-21, 확인 필요 범주 전부.
- 보류(사용자 결정 대기): D-03, D-04, D-05, D-11, D-16, D-17, D-18, D-20, D-22, R16-15를 뺀 R16-xx 전부, 틀린 기존 주석 25건, 패키지 구조 변경.
- ruff F: 25건에서 5건으로 줄었습니다. 남은 5건은 `planners/__init__.py`의 다시 내보내기로, 유지 결정에 따라 그대로 둡니다.

### 조치 (3단계 2차, 2026-11-20, 사용자 결정)

- 조치(2026-11-20): D-05를 처리했습니다. fleet_core의 경로 길이 합 계산 3곳을 `_plan_length`로, MOVE 임무를 만드는 코드 2곳을 `_new_move_task`로 모았습니다. pytest와 `fleet_bench rush --check` 결과가 기준선과 같습니다.
- 조치(2026-11-20): D-17을 처리했습니다. sim.launch.py의 코스트맵 RViz YAML 두 벌을 `_costmap_map` 하나로 합쳤습니다(380 → 369줄). `rviz_config`가 만드는 rviz 파일 내용이 예전과 바이트 단위로 같은 것을 5가지 조합에서 확인했습니다.
- 조치(2026-11-20): D-18을 처리했습니다. map.js의 `drawMap`을 지우고(140 → 103줄), 손님 시뮬레이터(customer.html)도 ui.js의 `drawStore`로 그리게 바꿨습니다. :8090 화면을 띄워 지도가 그려지는 것을 확인했습니다(headless Chrome 화면 캡처).
- 조치(2026-11-20): 틀린 기존 주석 25건을 모두 정정했습니다.
  - 일반 주석은 그 자리에서 고치고 바로 위에 `[수정 2026-11-20] 주석 정정: …` 한 줄을 달았습니다. 틀린 것이 기존 `[수정]` 주석이면 원문을 두고 바로 아래에 정정 줄을 덧붙였습니다.
  - docstring 안의 정정은 docstring 안에 정정 줄을 넣거나, def 위의 주석으로 달았습니다.
  - 코드 문자열이 바뀐 것은 robot_remote의 `--robots-file` 도움말 한 건뿐입니다. 나머지 정정은 docstring을 뺀 AST가 그대로입니다.
  - 확인 필요 2건(fleet_core T-49, robot.launch.py 머리말)은 코드로 확인한 범위만 적고, 나머지는 '확인 필요'로 남겼습니다.
- 유지·하지 않음(사용자 결정): D-03, D-04, D-11, D-16, D-20, D-22. 서빙 팔 코드는 frybot_mobile에 둡니다(아키텍처상 FrybotMobile Arm Controller). 구조 제안 3은 철회합니다.
- 보류: R16-xx 결함은 이번 작업이 끝난 뒤 사용자와 다시 논의합니다.

### 4단계(주석 보강) 중 발견 (2026-11-20, 고치지 않음, 다음 논의용)

주석 작업자들이 코드를 읽다가 찾은 것입니다. 지시대로 고치지 않고 목록만 남깁니다.

- 발견(R16-50, 중간, 확인 필요): `auto_localize.check_now`에서 Nav2 실패 때(`not standing`) `fix is None`이면 경고만 남기고 return 하지 않습니다. 그대로 `fix.yaw`로 내려가 AttributeError가 날 수 있습니다(auto_localize.py `check_now`). 예외가 나면 `mobile_controller._navigate`가 경로 액션을 빈 결과로 끝내 `nav2_retries`·`NAV2_FAILED` 처리를 건너뛸 수 있습니다. 실행으로는 확인하지 않았습니다.
  - 발견(2026-11-23): 실기기 runs/20261123_03(18-T 2회차)에서 실제로 일어남. B3→B2 구간 Nav2 실패 직후 이 예외로 경로 결과가 사라져 관제가 M0001 을 IN_PROGRESS 로 계속 잡았고, 관제까지 재기동해야 했음
  - 조치(2026-11-23): `check_now`의 그 분기 끝에 `return False`. `_navigate`의 호출을 `(AttributeError, TypeError, ValueError, IndexError)`로 감싸 위치 점검이 실패해도 재시도·NAV2_FAILED 반환으로 진행(T-56). 단위 시험은 수정 전 실패·수정 후 통과, 가짜 통합에서 NAV2_FAILED → 관제 보류(SUSPENDED) 확인. 실기기 확인 필요
- 발견(낮음): `robot_remote.check`의 원격 스크립트가 항상 0으로 끝나 패키지가 `MISSING`이어도 `OK`가 찍힐 수 있습니다. robots.example.yaml의 `baud`는 어디에서도 읽지 않습니다.
- 발견(낮음, 확인 필요): pinky_driver의 `joint_states` 바퀴 이름(`left_wheel_joint`)이 URDF(`l_wheel_joint`)와 다르고, 오른쪽 바퀴 부호도 오도메트리와 다릅니다.
- 발견(낮음): central_control 기동 로그는 `AI ingest http://127.0.0.1:port`라고 찍지만 실제로는 0.0.0.0에 열립니다.
- 발견(낮음): 홈페이지·손님 화면에서 리소스 404가 하나 납니다. favicon으로 보이지만 확인 필요입니다.
- 틀리거나 빠진 기존 주석(새로 찾은 것, 고치지 않음):

| 파일 | 주석 | 실제 |
|---|---|---|
| offline_bench.py 모듈 docstring | `--check` 통과 기준 목록 | 보류(suspended)도 실패로 침(`--help` 출력이라 안 고침) |
| task_manager_node.py `auto_home` 기본 | "실기기 값(켬)" | real.launch.py 기본은 T-48부터 false |
| restaurant.py 모듈 docstring | 테이블 상태 목록 | `CLOSED`가 빠짐 |
| test_off_node_block.py `5.9 cm(B1 까지 9.9 cm)` | 9.9 cm | 15.7 − 5.9 = 9.8 cm |
| scan_match.py `improve` | "넘게" | 코드는 `>=`(이상) |
| auto_localize.py 머리말 저장 조건 | 1 cm 또는 60 s | 방향이 0.02 rad 이상 바뀌어도 저장 |
| navigator.py:1 | 세 곳이 함께 씀 | robot.launch는 navigator.launch를 포함할 뿐임. 시뮬은 일부 함수만 씀 |
| gazebo.launch.py "localisation from the Controller" | 제어기 | T-36부터 sim_backend |
| world_node.py guests dict | 키 목록 | `party`, `table`이 빠짐 |
| mobile_controller.py `[수정 2026-11-17] UR-03` | 안내 경로면 카메라 프레임 전송 | 이 자리는 guide_goal만 둠. 프레임은 sim_backend가 시뮬에서만 보냄 |
| mobile_controller.py `_publish_arm` | "(대역: 오류 없음)" | serving_arm:=real 일 때도 같은 보고 |
| mobile_controller.py 앞 라이다 범위 | docking·creep | start 단계 creep과 turn 단계도 봄 |
| mobile_controller.py `_refresh_costmap` | 주행 중 1초마다 | 실측 지도에서는 하지 않음 |
| RobotStatus.msg state 목록 | | `WAIT_LOC`가 빠짐 |
| ArmJob.action reason 목록 | | `ARM_FAIL`이 빠짐 |

## 2026-11-27 경량화 검토와 이력 주석 정리

사용자 요청(필요 없는 코드·안 쓰는 기능·중복 삭제)으로 조회한 결과와 조치입니다. Confluence I/F v0.3 목록(24641549), SW 아키텍처 v016, 팀 저장소(roscamp-repo-1 main)의 ARCHITECTURE·SOURCE_GUIDE·REPOSITORY_REVIEW 를 함께 참고했습니다.

- 발견(2026-11-27): 참조 0건인 정의는 `ceiling_view.write_latest`(10줄)와 파라미터 `web_url`(customer_ui_node)·`grace_sec`(nav2_watchdog)뿐. ruff F 는 유지 결정한 `planners/__init__.py` 5건만 남음
- 발견(2026-11-27): 보류 중이던 D-11(`/frybot/state` 의 `ai` 키)과 D-22(`RobotStatus` 의 `task_id`·`plan_version`·`reached_index`·`node_id`·`arm_state`)는 I/F v0.3 의 31번·33번 필드 목록에 있어 삭제 대상이 아님(유지 결정과 일치)
- 발견(2026-11-27): 설계 문서에 없는 코드 묶음은 Open-RMF 비교(`planners/rmf.py`, `schedulers/rmf_task.py`, `rmf_bridge/`, 약 790줄, 도우미 빌드본 없음), 비교용 플래너(`cbs.py`, `cooperative_astar.py`), 옛 호환(`hungarian*` 이름, `drive:=cmd_vel`). 삭제 여부는 사용자 결정 대기(이번에는 지우지 않음)
- 발견(2026-11-27): `fleet_core.on_robot_status` 의 T-49 주석 정정 줄이 "2초 뒤 오프라인"이라고 적혀 있었으나 코드는 1초(`tick` 의 `now - last_status > 1.0`, 2026-11-24 변경)
- 조치(2026-11-27, 사용자 결정 "2번만 진행"): `[수정 날짜] … 삭제 …` 표기 27건과 `[수정 날짜] 주석 정정 …` 26건(합 53곳, 31개 파일)을 정리. 지운 코드의 자리 표시는 지우고, 지금 코드를 설명하는 내용은 날짜 표기 없이 남김. 주석 정정은 원문을 맞는 내용으로 고쳐 쓰고 정정 줄을 없앰(위 "2초"는 1초로 고침). 코드·문자열은 바꾸지 않음. 대상 파일 합계 12,501 → 12,442줄
  - 이번 정리는 "지운 자리에 이유를 주석으로 남김" 규칙의 예외(사용자 승인). 삭제 이유는 위 "조치 (3단계 1차·2차, 2026-11-20)"와 2026-11-17 규칙 준수 점검 절에 남아 있음
  - 확인: Python 26개 파일의 docstring 제외 AST 가 수정 전과 동일, 그 외 5개 파일(package.xml, admin.html, map.js, customer.html, RobotStatus.msg)은 주석 줄만 다름, `python3 -m pytest src/frybot` 129 passed(수정 전과 같음), `colcon build --packages-select frybot_interfaces frybot_sim` 성공, `fleet_bench --scenario rush --check` 기본 조합(min_cost_eta_rh + sipp) 통과
  - 확인하지 못한 것: map.js 문법 검사(PC 에 node 없음, diff 는 `//` 주석 줄뿐). `fleet_bench --check` 는 cooperative_astar 조합 2개가 "의도된 대기 20초 1"로 실패하는데 수정 전 결과를 떠 두지 않아 직접 비교는 못 함(AST 가 같아 이번 수정과 무관, 원인은 확인 필요)
  - 실기기: 로봇에 배포된 파일과 PC 파일의 md5 가 달라짐(mobile_controller.py, serving_arm_driver.py, pinky_driver.py, auto_localize.py, scan_match.py, arm_common.py, robot.launch.py, RobotStatus.msg). 동작 차이는 없으나 다음 배포 전까지 md5 대조는 불일치로 나옴
