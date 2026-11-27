# FryBot 실기기 기준 정리 기획안 (2026-11-18)

2026-11-18 재검토에서 "시뮬 기준으로 남은 것"으로 찾은 항목을 모두 실기기(Pinky) 기준으로 바꾸고 오타를 고치는 계획입니다. 이 문서는 계획만 담으며, 코드는 아직 바꾸지 않았습니다. 작업 공간 규칙(CLAUDE.local.md)은 그대로 적용됩니다. 경로는 `src/frybot/` 기준이고 줄 번호는 작성 시점 값입니다.

## 0. 원칙

1. **노드 기본값은 실기기 값**으로 둡니다. 시뮬 값은 시뮬 런치(`sim.launch.py`, `gazebo.launch.py`)가 명시합니다. 2026-11-17 B3(`drive`, `pose_source`)와 같은 방식입니다.
2. **이름은 실기기 구성 요소 이름**을 씁니다. 실기기에서 쓰는 코드·노드·필드에 `sim`, `gz`, `proto`가 들어가지 않게 합니다.
3. **시뮬 전용 동작은 실기기 경로 밖**으로 모읍니다. 실기기 코드가 "시뮬이 아니면"으로 갈라지지 않고, 시뮬 쪽이 끼워 넣는 형태로 바꿉니다.
4. **동작은 바꾸지 않습니다.** 기본값을 뒤집을 때마다 시뮬 런치에 예전 값을 명시해 시뮬 결과가 그대로인지 확인합니다. 관제 판단(`fleet_core.py`의 스케줄·계획·양보)은 손대지 않습니다.
5. 단계마다 따로 검증하고, 앞 단계가 통과해야 다음 단계로 갑니다.

## 1. 단계 요약

| 단계 | 내용 | 바뀌는 패키지 | 위험 | 실기기 확인 |
| --- | --- | --- | --- | --- |
| P1 | 노드·런치 기본값을 실기기 값으로 | web, mobile, control, bringup | 낮음 | 필요(단독 실행) |
| P2 | 오타와 이름 정리 | mobile, arm, control, bringup | 낮음 | 필요(노드 이름) |
| P3 | 시뮬 전용 입력·출력을 실기기 경로에서 분리 | mobile, web, bringup | 중간 | 필요(관절값, RViz) |
| P4 | "실측 지도" 분기를 지도 기능 기준으로 | control, mobile, web | 높음 | 필요 |
| P5 | 공용 지도 패키지 분리 | 전체 | 중간 | 필요(배포) |
| P6 | 문서 갱신 | docs, README | 낮음 | 없음 |

P1~P3은 바로 진행할 수 있습니다. P4·P5는 2장의 결정이 필요합니다.

### 진행 상태 (2026-11-18)

| 단계 | 상태 |
| --- | --- |
| P1 | 완료(부장 세션). 모의·시뮬 확인, 실기기 확인 필요 |
| P2 | 완료. 모의·시뮬 확인, 실기기 확인 필요 |
| P3 | 완료(입출력 분리만). 주행 안의 `kinematic` 분기는 보류(D8) |
| `map:=` 삭제(D9) | 완료. 실기기 확인 필요 |
| P4 | **보류(사용자 결정).** 분류표만 작성. 실제 매장 지도가 정해질 때 다시 봄 |
| P5 | **보류.** P4 뒤에 함 |
| P6 | 각 단계에서 바뀐 만큼 갱신함 |

기준 자료는 `archive/real_first_2026-11-18/baseline/`에 있습니다. 변경은 커밋하지 않은 상태입니다.

## 2. 결정이 필요한 것 (권장안 포함)

| # | 질문 | 권장 |
| --- | --- | --- |
| D1 | `FRYBOT_MAP_ID`가 없을 때 가상 매장(`proto`)으로 뜨는 기본을 없앨지 | ROS 노드는 지도 이름이 없으면 오류로 멈춤. 오프라인 도구(`fleet_bench`, `replay_run`, `export_map`, pytest)는 `--map-id` 기본 `proto`를 명시적으로 유지 |
| D2 | `mobile_controller` 노드 이름 `amr`을 무엇으로 통일할지 | 실행 파일과 같은 `mobile_controller` |
| D3 | 원본 사본인 `pinky_driver.py`, `pinky_battery.py`의 노드 이름을 바꿀지 | 바꿈(`pinky_driver`, `pinky_battery`). "동작은 바꾸지 않음" 머리말에 이름만 바꿨다고 적음 |
| D4 | P4에서 매장 정보(테이블, 충전대, 도크)를 `roadmap.json`으로 옮길지 | 옮김. 다만 실제 매장 지도가 정해지기 전이므로 형식만 만들고 `proto`로 검증 |
| D5 | P5 공용 지도 패키지를 만들지, 이름은 무엇으로 할지 | 만듦. 이름 `frybot_map` |
| D7 | `robot.launch.py`에서 `map_id`를 필수로 할지 (부장 세션이 찾은 D1 불일치에서 나옴) | **확정(2026-11-18, 사용자): 필수.** 비어 있으면 런치를 멈추고 지도 이름을 안내. `navigator.launch.py`는 `map_id` 값으로 `FRYBOT_MAP_ID`를 넣고, 없으면 `proto` + 안내 로그 |
| D8 | 주행·비상 정지 안의 `drive == 'kinematic'` 분기도 백엔드로 옮길지 | **확정(2026-11-18, 사용자): 보류.** 실기기에서 T-22·양보 후진·비상 정지를 확인한 뒤 수정을 검토 |
| D9 | 쓸 수 없게 된 `map:=` 인자(`real.launch.py`, `robots.launch.py`, `robot.launch.py`, `remote.py`, `robot_remote.py`)를 지울지 | **확정(2026-11-18, 사용자): 삭제.** 다른 지도는 `maps/`에 새 `map_id`로 추가. `navigator.launch.py`의 `map`은 유지 |
| D6 | 시뮬 전용 코드를 `frybot_mobile` 안의 별도 모듈로 둘지 `frybot_sim`으로 옮길지 | `frybot_mobile/sim_backend.py`로 분리. `frybot_sim`으로 옮기면 `frybot_mobile`이 `frybot_sim`에 의존하게 되어 로봇 배포 목록이 늘어남 |

## 3. P1: 기본값을 실기기 값으로

### 수정

| 위치 | 지금 | 바꿀 값 | 시뮬 런치에 명시할 것 |
| --- | --- | --- | --- |
| `frybot_web/web_service_node.py:65` `admin_local_only` | `False` | `True` | `sim.launch.py:220, 289`의 `web_service`에 `admin_local_only: False` |
| `frybot_mobile/launch/navigator.launch.py:32` `mode` | `sim` | `real` | 해당 없음(시뮬은 `navigator_nodes`를 직접 부름). 머리말 예시 수정 |
| `frybot_mobile/navigator.py:16, 30` `real` 인자 | 기본 `False` | 기본값을 없애고 필수 인자로 | `gazebo.launch.py:95`의 `navigator_nodes(rid)`를 `navigator_nodes(rid, real=False)`로 |
| `frybot_mobile/mobile_controller.py:73` `base_frame` | `{rid}/base_footprint` | `base_footprint` | `sim.launch.py:240, 298`의 `mobile_controller`에 `base_frame: {rid}/base_footprint` |
| `frybot_mobile/aruco_dock_detector.py:55-57` 프레임 3개 | `{rid}/...` | 접두어 없음(`base_footprint`, `front_camera_link`, `odom`) | `navigator.py:45-48`의 조건을 뒤집어 시뮬일 때만 `{rid}/...`를 넘김 |
| `frybot_control/task_manager_node.py:24` `robot_ids` | 3대 | `['pinky1']` (`real.launch.py`의 "등록 없음" 기본과 같음) | 시뮬 런치는 이미 넘김 |
| `task_manager_node.py:29` `use_standby` | `True` | `False` | 시뮬 런치는 이미 넘김 |
| `task_manager_node.py:33` `auto_home` | `False` | `True` | 실측 지도 시뮬(`sim.launch.py:217`)은 이미 넘김. 가상 매장 쪽 `task_manager`는 넘기지 않으므로 `auto_home: False`를 명시 |
| `frybot_control/central_control_node.py:34` `scenario` | `interactive` | `real` | 시뮬 런치는 `scenario_name`을 이미 넘김 |
| `central_control_node.py:37` `robot_ids` | 3대 | `['pinky1']` | 시뮬 런치는 이미 넘김 |
| `frybot_control/map_catalog.py:25` 지도 이름 없음 | `proto` | D1 권장안: 노드 시작 시 오류 | `sim.launch.py`는 이미 `FRYBOT_MAP_ID`를 넣음 |

- `FleetCore` 생성자의 기본값은 바꾸지 않습니다. `fleet_bench`, `replay_run`, pytest가 그 기본값을 쓰므로 결과가 달라지지 않아야 합니다.
- `base_frame`을 바꿔도 로봇에서 단독 실행하려면 `/tf` 리맵은 여전히 필요합니다(파라미터로 줄 수 없음). 머리말(10행)의 안내를 그에 맞게 고칩니다.
- `mobile_controller.py:65-67`의 B3 주석, `nav2_store.yaml` 머리말의 "Used unchanged"(R2-1)도 실제에 맞춥니다.

### 완료 확인

- 빌드: `colcon build --symlink-install --packages-select frybot_control frybot_web frybot_mobile frybot_bringup`
- `fleet_bench --scenario rush`, `--scenario bottleneck` 평균이 작업 전 결과와 같음(plan_ms 제외), pytest 전체 통과
- `sim.launch.py` + `scenario --scenario demo` 후 `analyze_run` 지표가 작업 전과 같은 수준, `manifest`의 `simulation`이 true
- `sim.launch.py map_id:=test_map_v001`에서 이동 명령 1건 완료
- `gazebo.launch.py`에서 Nav2가 활성화되고 구간 1개 이상 주행
- 노드 단독 실행: `ros2 run frybot_web web_service` 후 다른 기기 주소로 `POST /api/admin`이 거절됨
- 실기기 확인 필요: `real.launch.py` 기동, 로봇에서 `mobile_controller` 단독 실행 시 TF 수신

## 4. P2: 오타와 이름 정리

### 오타·낡은 문구

| 위치 | 지금 | 수정 |
| --- | --- | --- |
| `frybot_mobile/pinky_battery.py:10` | 노드 이름 `battery_publihser` | `pinky_battery` |
| `frybot_arm/launch/cooking.launch.py:6` | `real.launch.py(sim_cooking:=true)` (B4에서 삭제된 인자) | `sim.launch.py`만 언급 |
| `frybot_bringup/remote.py:1`, `robot_remote.py:9` | `config/robots.yaml` | `~/.config/frybot/robots.yaml` |
| `frybot_bringup/robot_remote.py:47` | 패키지의 `config/robots.yaml`을 대체 경로로 돌려줌(T-30 뒤로 없는 파일) | `USER_FILE`을 돌려줌 |
| `frybot_bringup/package.xml:5` | "lightweight simulation + RViz, and Gazebo variant" | 실기기 런치를 앞에 둔 설명 |
| `frybot_mobile/config/nav2_store.yaml:2` | "Used unchanged in the simulation and on the real robot" | `navigator.py`가 덮어쓰는 항목을 적음(R2-1) |
| `frybot_mobile/mobile_controller.py:990` | 주석 "Gazebo odometry" | 실기기(AMCL) 기준으로 |

오타 검색(`publihser`, `recieve`, `seperat`, `occured`, `lenght`, `paramter`, `contoller` 등)에서 걸린 것은 `battery_publihser` 하나였습니다. 한국어 문서의 맞춤법은 이 검색으로 확인하지 못했습니다.

### 이름

| 대상 | 지금 | 바꿀 이름 | 함께 고칠 곳 |
| --- | --- | --- | --- |
| `mobile_controller` 노드 | `amr`, 클래스 `Amr` | `mobile_controller`, `MobileController` | `mobile_controller.py:56-58`, `robot.launch.py:98`, `sim.launch.py:240, 298` |
| `pinky_driver` 노드 | `pinky_bringup` | `pinky_driver` | `pinky_driver.py:40` |
| `master_controller` 노드 | `arm_master_controller` | `master_controller` | `master_controller.py:34`, `cooking.py:21` |
| `fleet_core.Robot.sim_state` | 실기기 `RobotStatus.state`를 담음 | `reported_state` | `fleet_core.py:96, 1338, 1616` |
| RViz 설정 | `frybot.rviz`(시뮬), `fleet_real.rviz`(실기기) | `sim_store.rviz`, `fleet.rviz` | `sim.launch.py:150, 183`, `fleet_rviz.launch.py:9`, `remote.py:47, 52` |
| `mobile_controller.real_battery`, `_real_charging` | 실기기 쪽에 `real_` 접두어 | `_charging_from_battery` 등 접두어 없는 이름. 가짜 쪽에 `sim_`을 붙임(P3) | `mobile_controller.py:75, 179, 302, 962-966` |

- `mobile_controller.py:195`의 `self.cam.send('amr', ...)`는 AI 서버 대역이 받는 프레임 종류라 노드 이름과 별개입니다. `ai_server.py`와 함께 봐야 하므로 그대로 둡니다.
- 노드 이름이 바뀌면 `ros2 node list`, 로그 이름, 파라미터 파일의 루트 키가 달라집니다. `scripts/stop_all.sh`는 실행 파일 경로(`lib/frybot`)로 프로세스를 찾으므로 영향이 없습니다. `robot_remote --stop`의 `STACK` 목록(`robot_remote.py:31-33`)도 실행 파일 경로(`lib/frybot_mobile`)와 런치 이름으로 찾으므로 영향이 없습니다.

### 완료 확인

- 빌드 후 `sim.launch.py`에서 `ros2 node list`에 새 이름만 보임
- `fleet_bench --scenario rush` 결과 동일, pytest 통과
- RViz가 시뮬과 `fleet_rviz.launch.py`에서 모두 설정을 읽음
- `rg "battery_publihser|sim_state|fleet_real\.rviz|sim_cooking|name='amr'" src/frybot scripts docs` 결과 0건(기록 문서의 과거 서술은 제외)
- 실기기 확인 필요: `robot_remote --all --check`, `--stop`이 새 이름에서도 동작

## 5. P3: 시뮬 전용 입력·출력을 실기기 경로에서 분리

### 지금

`mobile_controller.py`(1,014줄) 한 클래스 안에 시뮬 전용 동작이 섞여 있습니다.

- `drive == 'kinematic'` 분기 13곳(자세 직접 이동, 허용 오차, 0 속도 발행 생략 등)
- `/gz/model_poses` 구독과 `_gz_pose`(178, 383), map → base TF 발행(990)
- 가짜 배터리 증감(968-971), 충전대 좌표로 충전 판정(959-960)
- 가짜 바퀴 관절값 `l_wheel_joint`를 실기기에서도 발행(992-995). `pinky_driver.py:29`는 같은 토픽에 `left_wheel_joint`를 냄(R1-4)
- `/sim/world_state` 구독(133)과 그 값에 의존하는 `_guide_frame`(246-262)
- `frybot_web/web_service_node.py:74`도 실기기에서 `/sim/world_state`를 구독

### 수정

1. `frybot_mobile/sim_backend.py`를 만들고 위 동작 가운데 **입출력**(`/gz/model_poses`와 map → odom 보정, map → base TF, 가짜 배터리와 충전 판정, 가짜 바퀴 관절값, `/sim/world_state`와 `_guide_frame`)을 옮깁니다(D6). `mobile_controller`는 지금과 같은 조건일 때만 이 모듈을 붙입니다.
   - [수정 2026-11-18] 부장 세션 지적: 주행·비상 정지 안의 `drive == 'kinematic'` 분기(`_navigate`, `_step_toward`, `_stop`, `_rotate`, `_creep`, 도킹, `_heartbeat`)는 이번에 옮기지 않습니다. T-22, 양보 후진, 비상 정지 경로를 건드리게 되기 때문입니다. 옮길지는 따로 정합니다(D8).
2. 바퀴 관절값은 시뮬 백엔드만 냅니다. 실기기는 `pinky_driver`의 값만 남습니다.
3. `/sim/world_state` 구독은 시뮬 백엔드(로봇)와 `sim_world:=true` 파라미터(`web_service`, 기본 false, 시뮬 런치가 켬)로 옮깁니다.
4. `_guide_frame`은 시뮬 백엔드로 옮깁니다. 실기기 카메라 영상 송신은 아직 구현이 없으므로 "없음"으로 남기고 `REAL_ROBOT_GUIDE.md`의 "아직 없는 것"에 적습니다.
5. 서빙 팔(`arm_common.py`, `_arm_job`)은 실물이 없어 대역으로 남깁니다. 이름과 주석에 대역임을 분명히 하고, 실기기에서 팔 관절값(`/{pinky}/arm/joint_states`)을 내지 않을지는 RViz 표시를 보고 정합니다(확인 필요).

`CLAUDE.local.md`의 "시뮬에서만 동작하는 분기를 넣지 말 것"과 방향이 같습니다. 주행·허가·비상 정지 로직은 옮기지 않고 그대로 둡니다.

### 완료 확인

- `sim.launch.py` demo, `sim.launch.py map_id:=test_map_v001`, `gazebo.launch.py` 세 가지에서 작업 전과 같은 동작(`analyze_run` 비교)
- `drive=nav2`, `pose_source=tf`로 띄운 노드가 `/sim/world_state`, `/gz/model_poses`를 구독하지 않음(`ros2 node info`)
- `mobile_controller.py`에서 입출력 쪽 `gz`·`world_state`·가짜 배터리·바퀴 관절이 0건이고, `kinematic`은 주행 분기만 남음
- 실기기 확인 필요: RViz 로봇 모델의 바퀴 표시, 양보 후진·비상 정지 동작이 전과 같은지(T-22, T-28 항목 재확인)

## 6. P4: "실측 지도" 분기를 지도 기능 기준으로

### 지금

- 실기기 여부를 `graph.map_id`가 비었는지로 판정합니다. `fleet_core.py`에 13곳, `mobile_controller.py`의 `measured_map`, `layout.Graph`(190-213)에 있습니다.
- 실제 뜻은 "테이블·충전대·도크가 없는 지도"입니다. 매장 정보(`TABLES`, `CHARGERS`, `BAY_NODES`, `STANDBY_NODES`, `docks()`)는 `layout.py`에 `proto`용으로만 있습니다.
- `roadmap.json`의 키는 실측 지도가 `label, map_yaml, homes, nodes, edges, waiting, docking_candidates`, `proto`가 `label, map_yaml, homes, nodes, edges, waiting, alias`입니다.

### 수정

1. 분기 13곳을 먼저 분류합니다. 각각 무엇을 묻는지(테이블이 있는가, 충전대가 있는가, 도크가 있는가, 유휴 로봇을 조용히 둘 것인가, 이동 명령을 받을 것인가)를 표로 만들고 사용자 확인을 받습니다. 이 표가 P4의 첫 결과물입니다.
2. `roadmap.json`에 선택 키 `tables`, `chargers`, `bays`, `docks`, `stations`를 정의합니다. `export_map --proto`가 `layout.py`의 값을 이 키로 내보냅니다.
3. `Graph`는 모든 지도를 `roadmap.json`에서 읽습니다. `map_id == ''` 특수 처리를 없애고 `has_tables`, `has_chargers`, `has_docks` 같은 속성을 둡니다.
4. `fleet_core.py`와 `mobile_controller.py`의 분기를 1의 분류대로 그 속성으로 바꿉니다. 판단 내용은 바꾸지 않습니다.
5. `active_map_id()`가 `proto`를 빈 문자열로 돌려주는 규칙을 없앱니다. 웹(`web_service_node.py:91-101`)의 "빈 id = 가상 매장" 약속도 함께 고칩니다.

실제 매장 지도가 생기면 `roadmap.json`에 테이블 위치만 채워 접수·서빙을 쓸 수 있게 되는 것이 목표입니다. 이번 범위는 구조까지이고, 실측 지도에 테이블을 넣는 일은 포함하지 않습니다.

### 완료 확인

- `fleet_bench` rush·bottleneck·`--scenario moves --map-id test_map_v001 --robots 2`가 작업 전과 같은 결과(씨앗별 원본 CSV 비교), pytest 통과
- `export_map --proto`로 다시 만든 `roadmap.json`의 `nodes`, `edges`, `homes`가 전과 같음
- `sim.launch.py` demo와 실측 지도 시뮬에서 `analyze_run` 비교
- `rg "graph\.map_id|measured_map" src/frybot`에 지도 이름을 기록·표시하는 용도만 남음
- 실기기 확인 필요: `real.launch.py` 이동 명령, 양보, 자동 홈 이동

### 분류표 (2026-11-18 작성)

부장 세션이 만든 분기 분류표는 [2026-11-18_REAL_FIRST_P4_BRANCHES.md](2026-11-18_REAL_FIRST_P4_BRANCHES.md)에 있습니다. 판정 자리 34곳을 묻는 것 8가지(A~H)로 나눴고, 사용자 확인 뒤에 수정 2~5를 진행합니다.

### 위험

관제 핵심 코드를 건드리므로 위험이 가장 큽니다. 분기 하나를 잘못 분류하면 실기기에서 대기 위치·양보 동작이 달라집니다. 분류표 확인 → 구조 변경(2, 3) → 분기 교체(4)를 따로 검증합니다.

## 7. P5: 공용 지도 패키지 분리

### 지금

`frybot_mobile`이 `layout.Graph`, `docks()`, `map_catalog.profile` 때문에 `frybot_control` 전체에 의존합니다(`mobile_controller.py:42`, `aruco_dock_detector.py:34`, `robot.launch.py:23-24`). 로봇 배포 목록(`robot_remote.py:36`)에도 `frybot_control`이 들어가 스케줄러·플래너·`fleet_core`가 Pinky Pi에 올라갑니다.

### 수정

- 새 패키지 `frybot_map`(D5)으로 `layout.py`, `map_catalog.py`, `store_map.py`, `maps/`를 옮깁니다. `export_map` 실행 파일도 옮깁니다.
- 가져오는 쪽(`frybot_control`, `frybot_mobile`, `frybot_web`, `frybot_sim`, `frybot_bringup`)의 import와 `package.xml`을 고칩니다.
- 배포 목록을 `frybot_interfaces, frybot_map, frybot_description, frybot_mobile`로 바꾸고 `robot_remote --check`의 점검 목록(270행)도 맞춥니다.
- P4 뒤에 합니다. P4가 같은 파일을 크게 고치므로 순서를 바꾸면 변경이 겹칩니다.

### 완료 확인

- `colcon build --symlink-install --packages-up-to frybot_bringup` 성공, P1~P4의 확인 항목 재실행
- `frybot_mobile/package.xml`에 `frybot_control`이 없음
- 실기기 확인 필요: `robot_remote --all --deploy` 후 로봇에서 빌드와 기동

## 8. P6: 문서

- `src/frybot/README.md`: 폴더·패키지 표, 노드 이름, 지도 추가 순서의 경로, 런치 인자 기본값
- `docs/REAL_ROBOT_GUIDE.md`: 단독 실행 방법, 노드 이름, "아직 없는 것"(카메라 영상, 서빙 팔)
- `docs/COMMANDS.md`: 바뀐 이름과 경로
- `docs/CODE_REVIEW_CHECKLIST.md`: R1-4, R2-1에 `- 조치(날짜):` 추가
- `docs/TROUBLESHOOTING.md`: 버그 성격인 항목을 T-번호로 기록(관리자 API 기본 개방, `base_frame` 기본값, 실기기 가짜 바퀴 관절값)하고 상단 표와 갱신 날짜를 고침

## 9. 범위 밖

- `src/pinky_pro/`, `src/mycobot_ros2/`는 수정하지 않습니다.
- `frybot_sim`, `mock_fleet.py`, `offline_bench.py`, `replay_run.py`의 시뮬·모의 이름은 시험 도구이므로 그대로 둡니다.
- `frybot_arm`의 조리 팔과 `frybot_sim/ai_server.py`는 실물·실제 서버가 정해지지 않아 대역으로 남깁니다. 실물이 정해지면 따로 계획합니다.
- 토픽 `/sim/world_state`, `/sim/customer_cmd`, `/gz/model_poses`의 이름은 시뮬 전용이므로 바꾸지 않고, 실기기 노드가 구독하지 않게만 합니다(P3).
- 전체 파일 재포맷, 요청받지 않은 리팩터링은 하지 않습니다.

## 10. 작업 전 기준 자료

단계마다 "작업 전과 같음"을 비교하므로 P1 시작 전에 한 번 남깁니다.

- `ros2 run frybot_control fleet_bench --scenario rush --csv <기준>`, `--scenario bottleneck`, `--scenario moves --map-id test_map_v001 --robots 2`
- pytest 결과(`frybot_control/test`)
- `sim.launch.py` + `scenario --scenario demo`의 `analyze_run` 출력
- `ros2 node list`, `ros2 topic list` (시뮬 기동 상태)

## 11. 보고 형식

단계가 끝날 때마다 바뀐 파일 목록, 실행한 확인 명령과 통과·실패, 남은 "실기기 확인 필요" 항목, 커밋 메시지 초안을 보고합니다. 커밋과 푸시는 사용자가 합니다.
