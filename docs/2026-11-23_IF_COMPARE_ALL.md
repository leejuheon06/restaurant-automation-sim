# 정의서와 코드 전체 비교 (인터페이스 49건)

> 2026-11-26에 최종 기준이 Confluence I/F v0.3 최종 판으로 바뀌어 이름 8건을 되돌림(`/frybot/check_in`, `/fms/submit_task` 등). 아래 본문은 그날의 기록입니다. 지금 이름은 [INTERFACES.md](2026-11-23_INTERFACES_OLD.md), [2026-11-26_IF_V03_NAME_REVERT_PLAN.md](2026-11-26_IF_V03_NAME_REVERT_PLAN.md) 참고.

작성: 2026-11-23. AMR·관제·서빙 팔만 쉬운 말로 추린 것은 [쉬운 설명](2026-11-23_IF_COMPARE_AMR.md)에 있습니다. 코드의 실제 연결은 [인터페이스 연결 구조](2026-11-23_INTERFACES_OLD.md)를 참고합니다.

- 비교한 것(Confluence, 스페이스 "다중 로봇 협업 기반 스마트 레스토랑 자동화 시스템"):
  - `1) FryBot I/F 목록` (2026-11-20, 버전 4)
  - 개별 정의서 v0.2 49건 (`01) WEB-01 방문 접수 v0.2` ~ `49) 장비 실행 재조회 v0.2`, 2026-11-23)
  - `FryBot 통합 인터페이스 정의서 v0.2` (2026-11-23, 버전 1)
- 코드: `src/frybot` (`jazzy-port` 브랜치). `frybot_interfaces`의 msg 7·srv 7·action 2와 각 노드가 여는 토픽·서비스·액션·HTTP 경로.
- 확인 범위: 문서와 코드를 읽어서 비교했습니다. 실행 그래프·실기기와 대조하지 않았습니다. Confluence는 조회만 했고 수정하지 않았습니다.
- 한계:
  - 개별 정의서는 대부분 항목 이름만 있고 타입·크기·QoS가 "확인 필요"입니다. 타입까지 맞춰 본 것은 01번(WEB-01)뿐이고, 나머지는 "이 항목이 코드에 있는가" 수준입니다.
  - 정의서가 근거로 드는 GitHub OpenAPI(`addinedu-roscamp-16th/roscamp-repo-1`의 `api/openapi.yaml`)는 열어 보지 않았습니다(확인 필요).
  - "더 좋다", "추가", "줄임" 판단은 작성자(Claude)의 의견이며 팀 합의가 아닙니다.
- 번호는 정의서의 `NN)` 번호입니다.

## 1. 요약

- 49건 중 주소까지 같은 것은 27번(Nav2 `NavigateToPose`) 하나이고, 계약 이름이 같은 것은 19번(`SubmitTask`) 하나입니다.
- 구조가 다른 곳은 네 군데입니다.
  1. **통행 허가(22)**: 정의서는 로봇이 묻는 서비스, 코드는 관제가 0.5초마다 내려보내는 토픽입니다.
  2. **AMR 임무(23~26)**: 정의서는 임무별 액션 4개, 코드는 `NavigateRoute` + `ArmJob` 두 개로 관제가 임무를 쪼개 보냅니다.
  3. **이벤트(35~39)**: 정의서의 `DeviceEvent` 5개에 대응하는 토픽이 코드에 없고, 상태 보고의 `error`와 액션 결과로 전달합니다.
  4. **안전(40~42)**: 정의서는 장비별 서비스 3개, 코드는 `/fms/heartbeat`의 `estop` 목록 하나입니다.
- 통합 문서 4절은 코드의 타입(`NavigateRoute`, `TrafficGrant`, `FleetHeartbeat`, `ArmJob`, `ArmStatus`, `TaskEvent`, `RobotStatus` 등)을 "팀 공유본·Git 스냅샷" 열에 싣고, 안내·경로는 "현재 스냅샷의 경로 실행과 통행 허가를 기준선으로 기록한다"고 적었습니다. 즉 22~26번은 "도입 여부를 정할 후보"이고, 번호 붙은 개별 정의서에만 코드 타입이 빠져 있습니다.

### 집계

| 구분 | 건수 | 번호 |
| --- | --- | --- |
| 주소까지 일치 | 1 | 27 |
| 대응물이 있고 항목이 모두 있음 | 2 | 33, 34 |
| 대응물은 있으나 이름·항목이 다름 | 21 | 01, 04~07, 14~17, 19, 20, 28~32, 40~44 |
| 구조가 다름(방향·단위) | 5 | 22, 23~26 |
| 부분 대응 또는 다른 방식 | 2 | 46, 48 |
| 코드에 없음 | 18 | 02, 03, 08~13, 18, 21, 35~39, 45, 47, 49 |

## 2. 번호별 대조

### 웹 (01~13)

코드의 웹은 `web_service`(:8080)입니다.

| 번호 | 정의서 | 코드 | 차이 |
| --- | --- | --- | --- |
| 01 | WEB-01 방문 접수 `POST /visits` | `POST /api/checkin` | 요청 키·대기 번호·오류 코드 없음. `visit_id`가 문자열이 아니라 정수 |
| 02 | WEB-02 방문 상태 조회 `GET /visits/{visit_id}/status` | 없음 | `/api/state` 전체 스냅샷으로 대신 |
| 03 | WEB-03 메뉴 조회 `GET /menu` | 없음 | 메뉴는 `/api/state`의 `rest.menu` |
| 04 | WEB-04 주문 접수 `POST /orders` | `POST /api/order` | 방문 ID·요청 키 없음. 메뉴 ID가 아니라 코드(`FRIED` 등) |
| 05 | WEB-06 방문 종료 `POST /visits/{visit_id}/end` | `POST /api/end_use` | 방문이 아니라 `table_id` 기준. 회수 필요 여부를 응답하지 않음 |
| 06 | WEB-07 관리자 현황 조회 `GET /admin/overview` | `GET /api/state`, `/api/events` | 필터는 이력에만 있음 |
| 07 | WEB-08 관리자 조작 요청 `POST /admin/operations` | `POST /api/admin` | 조작 ID·요청 키 없이 `ok`, `message`를 바로 응답 |
| 08 | WEB-09 관리자 조작 결과 조회 | 없음 | |
| 09 | 진단 상태 조회 `GET /health` | 없음 | |
| 10 | 테이블 현황 조회 `GET /tables` | 없음 | `/api/state` 안에 있음 |
| 11 | 개별 주문 조회 `GET /orders/{order_id}` | 없음 | `/api/state` 안에 있음 |
| 12 | 음성 명령 접수 `POST /voice/command` | 없음 | 기능 자체가 없음 |
| 13 | 상태 변경 구독 (WebSocket) | 없음 | 화면이 `/api/state`를 주기 조회 |

코드에만 있는 경로: `/api/layout`, `/api/maps`, `/api/map`, `/api/events`.

### ROS 2 서비스 (14~22)

| 번호 | 정의서 | 코드 | 차이 |
| --- | --- | --- | --- |
| 14 | ROS2-01-S01 RegisterVisit `/frybot/central/register_visit` | `CheckIn` `/frybot/check_in` | 요청 키·대기 없음 |
| 15 | ROS2-01-S02 SubmitOrder `/frybot/central/submit_order` | `PlaceOrder` `/frybot/place_order` | 방문 ID·요청 키 없음 |
| 16 | ROS2-01-S03 EndVisit `/frybot/central/end_visit` | `EndUse` `/frybot/end_use` | 테이블 기준. `source`가 종료 근거에 해당 |
| 17 | ROS2-01-S04 RequestAdminOperation | `AdminCommand` `/frybot/admin` | 조작 ID·요청 키 없음 |
| 18 | ROS2-01-S05 GetViewState | 없음 | 토픽 `/frybot/state`만 있음 |
| 19 | ROS2-02-S01 SubmitTask `/frybot/tasks/submit` | `SubmitTask` `/fms/submit_task` | 대상 위치·상관 ID 없음. `priority`는 코드에만 있음. `task_id`가 문자열 |
| 20 | ROS2-02-S02 ControlTask `/frybot/tasks/control` | `FleetCommand` `/fms/command` | 임무 명령(`RETRY_TASK` 등)만 대응. 로봇·스케줄러 명령은 정의서 범위 밖 |
| 21 | ROS2-02-S03 GetExecution | 없음 | `attempt_id`, `execution_id` 개념이 없음. `plan_version`·`session`으로 옛 실행을 거름 |
| 22 | ROS2-03-S01 RequestPassage (로봇 → 관제) | `TrafficGrant` 토픽 `/fms/traffic_grant` (관제 → 로봇) | 방향이 반대. 거절·만료 표현 없음 |

### ROS 2 액션 (23~31)

| 번호 | 정의서 | 코드 | 차이 |
| --- | --- | --- | --- |
| 23 | ROS2-03-A01 GuideGuest | `NavigateRoute`(`mode=GUIDE`) | 목표 위치 대신 노드 경로 전체를 받음 |
| 24 | ROS2-03-A02 ServeFood | `NavigateRoute` + `ArmJob`(`LOAD`, `UNLOAD`) | 임무별 액션 없음. 로봇은 주문 참조를 받지 않음 |
| 25 | ROS2-03-A03 CollectDishes | `NavigateRoute` + `ArmJob`(`COLLECT_DISHES`, `RETURN_DISHES`) | 임무별 액션 없음 |
| 26 | ROS2-03-A04 ReturnToCharge | 홈 복귀 경로(`NavigateRoute`) + `RobotStatus.charging` | 전용 계약 없음 |
| 27 | ROS2-05-A01 NavigateToPose | `/{pinky}/navigate_to_pose` | 일치. 실행 참조 ID만 없음 |
| 28 | ROS2-06-A01 TransferObject | `ArmJob` `/{pinky}/serving_arm/arm_job` | 물체·위치를 받지 않고 고정 자세를 씀 |
| 29 | ROS2-04-A01 ExecuteCookingJob | `ArmJob` `/frybot_arm/arm_job` | 작업 전체가 아니라 단계 하나씩 보냄 |
| 30 | ROS2-07-A01 CookStep (A) | `ArmJob` `/cook_arm_a/arm_job` | 결과에 물건 위치 없음 |
| 31 | ROS2-08-A01 CookStep (B) | `ArmJob` `/cook_arm_b/arm_job` | 결과에 물건 위치 없음 |

### ROS 2 토픽 (32~39)

| 번호 | 정의서 | 코드 | 차이 |
| --- | --- | --- | --- |
| 32 | ROS2-01-T01 ViewState | `/frybot/state` (`std_msgs/String` JSON) | 관측 버전·시각 키를 찾지 못함(검색 기준) |
| 33 | ROS2-02-T01 TaskProgress | `TaskEvent` `/fms/task_events` | 항목 모두 있음 |
| 34 | ROS2-03-T01 MobileStatus `/{mobile_ns}/status` | `RobotStatus` `/fleet/robot_status` | 항목 모두 있음. 로봇별이 아니라 공용 토픽 하나 |
| 35 | ROS2-03-T02 DeviceEvent (AMR) | 없음 | `RobotStatus.error`로 전달 |
| 36 | ROS2-06-T02 DeviceEvent (서빙 팔) | 없음 | `ArmJob` 결과로 전달 |
| 37 | ROS2-04-T02 DeviceEvent (조리 마스터) | 없음 | 조리 팔이 `/fleet/arm_status`로 관제에 직접 보고 |
| 38 | ROS2-07-T02 DeviceEvent (A) | 없음 | 마스터를 거치지 않음 |
| 39 | ROS2-08-T02 DeviceEvent (B) | 없음 | 마스터를 거치지 않음 |

### 안전 서비스 후보 (40~42)

| 번호 | 정의서 | 코드 | 차이 |
| --- | --- | --- | --- |
| 40 | ROS2-09-S01 RequestEmergencyStop | `ESTOP` 명령 → `FleetHeartbeat.estop[]` | 장비별 서비스 없음. 요청 참조·주체 없음 |
| 41 | ROS2-09-S02 GetSafetyState | `RobotStatus`의 `E_STOP`, `EMERGENCY_STOP` | 조회가 아니라 10 Hz 보고 |
| 42 | ROS2-09-S03 AuthorizeRestart | `RESUME` 명령 | 승인 주체·현장 해제 근거 없음 |

### AI·영상·DB·장비 운용 (43~49)

| 번호 | 정의서 | 코드 | 차이 |
| --- | --- | --- | --- |
| 43 | AI 관측 HTTP | `POST :8100/ai/result` (`SEAT_QR`, `DONENESS`, `GUEST_TRACK`) | `GuestTrack`에 신뢰도 없음. 관측 시각 필드는 확인하지 못함 |
| 44 | 카메라 UDP | UDP :9100 | 영상이 아니라 JSON 프레임(대역) |
| 45 | AI 내부 IPC | 없음 | AI 서버가 대역 |
| 46 | DB TCP (MySQL) | SQLite 파일(`db.py`) | TCP 접근 없음 |
| 47 | Colab REST | 없음 | |
| 48 | 장비 자체점검 | `RobotStatus`의 `LOCALIZING`, `SELF_CHECK_ERROR` | 위치 추정에만 해당 |
| 49 | 장비 실행 재조회 | 없음 | |

### 정의서 49건에 번호가 없고 코드에만 있는 것

| 계약 | 방향 | 통합 문서 4절 |
| --- | --- | --- |
| `NavigateRoute` `/{pinky}/navigate_route` | 관제 → AMR | 이름 있음 |
| `TrafficGrant` `/fms/traffic_grant` | 관제 → AMR | 이름 있음 |
| `FleetHeartbeat` `/fms/heartbeat` | 관제 → AMR | 이름 있음 |
| `ArmJob` `/{pinky}/arm_job` | 관제 → AMR(서빙 팔) | 이름 있음 |
| `ArmStatus` `/fleet/arm_status` | 팔 → 관제 | 이름 있음 |
| `GuestTrack` `/frybot/guest_track` | 중앙 관제 → AMR | 이름 있음 |
| `/fms/state`, `/frybot/event_log`, `/ai/results` | 관제 PC 내부 | 없음 |
| `SpotCheck` `/frybot/spot_check` | AMR → 천장 카메라 노드 | 없음 |
| `DockRobot` `/{pinky}/dock_robot` | AMR 내부 | 없음 |

## 3. 항목(필드) 대조

### 공통으로 빠진 것

- **요청 키(재전송 대조)**: 정의서는 웹 4건(01, 04, 05, 07)과 ROS 서비스 6건(14~17, 19, 20)에 요청 키·상관 ID를 둡니다. 코드에는 어느 계층에도 없습니다. `web_service`는 4초 뒤 실패를 돌려줘도 요청이 취소되지 않아(R16-46), 다시 보내면 두 번 처리될 수 있습니다.
- **방문 ID 기준**: 정의서의 주문·종료는 방문 ID가 기준입니다. 코드의 `PlaceOrder`, `EndUse`는 `table_id`만 받습니다.
- **"결과 불명" 상태**: 정의서는 수락·거절·불명(또는 대기·보류)을 구분합니다. 코드는 `bool accepted`/`ok` + `message`뿐입니다.
- **관측 버전·시각**: 정의서는 상태 스냅샷에 버전이나 시각을 둡니다. `/frybot/state`를 만드는 `central_control_node.py`, `restaurant.py`에서는 그런 키를 찾지 못했습니다(검색 기준).
- **ID 타입**: 01번은 `visit_id`가 문자열이고 코드는 `int64`입니다. `task_id`는 통합 문서가 "중앙 관제 DB 발급 `int32`"를 통합 후보로 두었고, 코드는 Task Manager가 `G0001` 같은 문자열을 붙입니다.

### 웹

| 번호 | 정의서 항목 | 코드 항목 |
| --- | --- | --- |
| 01 | 입력 `party_size`(integer), `request_key`(string) / 출력 `visit_id`(string), `status`(enum), `table_id`, `queue_no`, `error.code` | 입력 `party_size` / 출력 `ok`, `visit_id`(int), `table_id`, `message` |
| 04 | 방문 ID, 테이블 ID, 메뉴 ID, 수량, 요청 키 / 주문 ID, 상태 | `table_id`, `items[{menu, qty}]` / `ok`, `order_id`, `message` |
| 05 | 방문 ID, 요청 키 / 종료 상태, 회수 필요·보류 | `table_id`, `source` / `ok`, `message` |
| 07 | 조작 종류, 대상 ID, 요청 키 / 조작 ID, 수락·충돌·보류 | `command`, `target`, `arg` / `ok`, `message`. 인증은 관제 PC 한정 또는 `X-Admin-Token` |

### ROS 2 서비스

| 번호 | 정의서 항목 | 코드 필드 |
| --- | --- | --- |
| 14 | 인원수, 요청 키 / 방문 ID, 배정·대기 | `CheckIn`: `party_size` / `accepted`, `visit_id`, `table_id`, `message` |
| 15 | 방문 ID, 테이블 ID, 메뉴·수량, 요청 키 / 주문 ID, 결과 | `PlaceOrder`: `table_id`, `menu_codes[]`, `quantities[]` / `accepted`, `order_id`, `message` |
| 16 | 방문 ID, 요청 키, 종료 근거 / 결과, 회수 필요·보류 | `EndUse`: `table_id`, `source` / `accepted`, `message` |
| 17 | 조작 종류, 대상 ID, 요청 키 / 조작 ID, 결과 | `AdminCommand`: `command`, `target`, `arg` / `ok`, `message` |
| 19 | 임무 유형, 업무 참조 ID, 대상 위치, 상관 ID / task ID, 수락·대기·거절 | `SubmitTask`: `task_type`, `visit_id`, `order_id`, `item_id`, `table_id`, `menu`, `priority` / `accepted`, `task_id`, `message` |
| 20 | task ID, 조작 종류, 상관 ID / 수락·거절·보류 | `FleetCommand`: `command`, `target`, `arg` / `ok`, `message` |
| 22 | 로봇 ID, 임무 ID, 경로·구역 / 허용·대기·거절, 적용 구역 | `TrafficGrant`: `robot_id`, `task_id`, `plan_version`, `granted_index` |

### ROS 2 액션

| 번호 | 정의서 항목 | 코드 필드 |
| --- | --- | --- |
| 23 | 방문 ID, 임무 ID, 테이블·목표 위치 / 이동·동행 확인, 결과 | `NavigateRoute`: `visit_id`, `task_id`, `plan_version`, `mode`, `route[]` / 피드백 `state`(ACCEPTED·MOVING·PAUSED_GUEST) / 결과 `reason`(GUEST_LOST 등) |
| 24, 25 | 임무 ID, 주문 참조, 픽업·테이블·퇴식구 위치 / 적재·이동·전달 | `NavigateRoute` + `ArmJob`. 로봇은 `params_json`의 `table_id`, `menu`만 받음. 단계 진행은 `TaskEvent`(`LOADED`, `SERVING`, `DELIVERED`, `COLLECTED`, `RETURNED`) |
| 27 | 목표 pose, 좌표계, 실행 참조 ID | `nav2_msgs/NavigateToPose` (표준) |
| 28 | 임무 참조 ID, 물체 참조, 원점·목표 위치 / 파지·이동·배치 | `ArmJob`: `task_id`, `arm_id`, `job`, `duration`, `params_json` / `phase`, `progress` / `success`, `reason` |
| 29 | 조리 작업 ID, 메뉴 참조, 단계 정의 참조 / 공정 단계 | `ArmJob`(`/frybot_arm/arm_job`): `params_json`의 `cook_task_id`, `menu`, `fry_time`. 마스터는 `arm_id`로 팔을 고름 |
| 30, 31 | 작업·음식·공정 참조 ID, 단계 명령 / 동작과 물건 위치 | 같은 `ArmJob`. 결과는 `success`, `reason`만 |

### ROS 2 토픽

| 번호 | 정의서 항목 | 코드 필드 |
| --- | --- | --- |
| 33 | task ID, 단계·상태, 관측 시각 | `TaskEvent`: `stamp`, `task_id`, `task_type`, `state`, `robot_id`, `visit_id`, `order_id`, `item_id`, `table_id`, `plan_version`, `reason` |
| 34 | 로봇 ID, 위치, 배터리, 임무·운용 상태, 관측 시각 | `RobotStatus`: `stamp`, `robot_id`, `state`, `x`, `y`, `yaw`, `battery`, `charging`, `task_id`, `plan_version`, `reached_index`, `node_id`, `arm_state`, `error` |
| 35~39 | 장비 ID, 이벤트 ID·종류, 영향 임무, 관측 시각 | 없음. `RobotStatus.error`, `ArmStatus.error`(항상 빈 값), 액션 결과 `reason` |

### 안전·AI

| 번호 | 정의서 항목 | 코드 |
| --- | --- | --- |
| 40 | 장비 ID, 정지 요청 참조, 요청 주체 / 접수 결과, 추적 참조 | `FleetCommand` `ESTOP`(`target` = 로봇) → `FleetHeartbeat.estop[]` |
| 41 | 장비 ID / 안전 상태, 관측 시점 | `RobotStatus.state=E_STOP`, `error=EMERGENCY_STOP`. 팔은 해당 없음 |
| 42 | 장비 ID, 승인 주체, 현장 해제 근거 | `FleetCommand` `RESUME` |
| 43 | 관측 유형, 대상 참조, 관측 시각 / 결과, 신뢰도 | `kind`, `cook_task_id` 또는 `robot_id`·`visit_id`. `GuestTrack`: `stamp`, `robot_id`, `visit_id`, `visible`, `distance` |

## 4. 판단: 정의서를 따라갈 것과 정의서에 적을 것

### 정의서를 따라갈 것 (코드를 고침)

| 번호 | 정의서의 장점 | 코드의 현재 문제 | 고칠 곳 |
| --- | --- | --- | --- |
| 01, 04, 14, 15, 19, 20 | 요청 키로 재전송을 대조 | 다시 보내면 주문·임무가 두 번 들어갈 수 있음(R16-46) | `frybot_interfaces`와 이를 쓰는 노드, `web_service` |
| 07, 08, 17 | 조작 ID로 실제 적용 결과를 조회 | "응답 없음" 뒤에 명령이 처리될 수 있음(R16-46) | `web_service_node.py`, `central_control_node.py` |
| 19, 33 | 수락·대기·거절을 구분해 요청자가 앎 | 임무 거절이 업무 상태에 반영되지 않음(R16-10) | `central_control_node.py`, `restaurant.py` |
| 21, 49 | 정지·점유 해제가 실제로 됐는지 대조 | 경로 결과의 `reached`를 쓰지 않음(R16-02). 임무 취소 뒤 옛 목적지로 다시 갈 수 있음(R16-01, 안전) | `fleet_core.py` |
| 36~39 | 팔이 이상을 스스로 알림 | `ArmStatus.error`가 항상 비어 있음 | `mobile_controller.py`, `serving_arm_driver.py`, `arm_controller.py` |
| 40 | 정지 접수와 실제 정지 확인을 구분 | 서빙 팔 구동부가 생존 신호를 직접 듣지 않음(R16-26) | `serving_arm_driver.py` |
| 42 | 재가동 승인에 주체·근거를 남김 | `RESUME`에 기록이 없음 | `fleet_core.py`, `admin.html` |
| 02, 06, 32 | 상태 스냅샷에 버전·시각 | 화면이 오래된 상태를 구분할 방법이 없음 | `central_control_node.py` |
| 09 | `GET /health` | 없음(비용이 작음) | `web_service_node.py` |

이 표의 항목은 아직 고치지 않았습니다. 실기기 동작이 걸린 21·49, 36, 40은 실기기 확인 필요입니다.

### 정의서에 코드 내용을 적을 것

| 번호 | 코드의 장점 | 정의서에 적을 내용 |
| --- | --- | --- |
| 22 | 0.5초 재발행으로 유실에 강함. 허가가 없으면 로봇이 섬 | Service를 `TrafficGrant` 토픽(관제 → 로봇)으로 교체 |
| 23~26 | 통로가 한 대 폭이라 관제가 구간 단위로 보내야 양보·재계획·재배정을 할 수 있음 | 액션 목록에서 빼고 임무별 단계 표로 옮김. `NavigateRoute`, 관제 → AMR `ArmJob`을 새 번호로 추가 |
| 28 | `ArmJob` 한 타입으로 모든 팔을 다룸. 실물은 고정 자세만 씀 | `TransferObject`를 `ArmJob`으로 교체. 물체·위치는 확장 항목 후보 |
| 34, 35, 41, 48 | 상태·오류·위치 추정 결과가 한 보고에 10 Hz로 실려 유실돼도 복구됨 | 34번(`RobotStatus`)에 35·41·48번을 합침 |
| 40~42 | 생존 신호는 통신이 끊겨도 로봇이 스스로 섬 | `FleetHeartbeat`를 새 번호로 추가하고 40~42번은 그 위에 얹는 절차로 적음 |
| 없음 | — | `ArmStatus`, `SpotCheck`, `DockRobot`, `GuestTrack`을 새 번호로 추가 |

AMR·관제·서빙 팔 항목의 칸별 작성안은 [쉬운 설명 2절](2026-11-23_IF_COMPARE_AMR.md#2-코드가-더-좋은-것-정의서에-적어-넣습니다)에 있습니다.

### 정의서에서 줄이거나 합칠 만한 것

| 번호 | 판단 |
| --- | --- |
| 18, 32 | 같은 스냅샷의 조회와 발행입니다. 하나로 충분합니다. |
| 10, 11 | 06, 02와 내용이 겹치고 정의서도 "호환"·"확인 필요"로 적어 두었습니다. |
| 35~39 | 계약 하나에 인스턴스 5개로 적으면 됩니다. 38·39를 마스터가 받아 37로 다시 올리는 단계는 팔 2대 규모에서 이득이 작습니다. |
| 21, 49 | 둘 다 "실제로 실행됐는지 대조"입니다. 하나로 합칩니다. |
| 45, 46, 47 | 시스템 사이의 계약이 아닙니다. 45는 AI 서버 내부, 46은 표준 프로토콜, 47은 운영 중 호출이 아닌 학습 절차입니다. 참고 문서로 옮겨도 됩니다. |
| 12 | 범위에 넣을지부터 정해야 합니다. 정의서도 범위가 다르다고 적어 두었습니다. |

### 코드에 넣지 않아도 되는 것

- **13 WebSocket**: 화면 몇 개 규모에서는 주기 조회로 충분합니다. 다만 다른 팀원의 화면이 GitHub OpenAPI의 `/ws`를 기준으로 만들어지고 있다면 맞춰야 합니다(확인 필요).
- **21 `attempt_id`, `execution_id`**: 현재 `plan_version`으로 옛 실행을 걸러내고 있습니다.
- **16 방문 ID 기준 종료**: 테이블당 방문이 하나라 `table_id`로 동작합니다. 04·15번의 주문은 방문 ID를 함께 받는 편이 요청 키와 맞습니다.

## 5. 팀 합의가 필요한 것

| 항목 | 통합 문서 | 코드 |
| --- | --- | --- |
| 로봇 이름 | `pinky_1`, `pinky_2`, `pinky_3` | `pinky1..N` |
| 중앙 주소 | `/frybot/central/...`, `/frybot/tasks/...` | `/frybot/...`, `/fms/...`, `/fleet/...` |
| 임무 ID | 중앙 관제 DB 발급 `int32` 후보. `TASK_NONE=0`, `TASK_MANUAL=-1` 예약값 제안 | Task Manager 발급 문자열(`G0001`) |
| 상태 토픽 QoS | `MobileStatus` 후보 Best Effort, Keep Last 1 | `/fleet/robot_status` Reliable, 깊이 50 |
| 웹 경로 | GitHub OpenAPI(`/visits`, `/orders`, `/admin/...`, `/ws`) | `/api/checkin`, `/api/order`, `/api/end_use`, `/api/admin`, `/api/state` |
| 비상 정지 | 물리 정지는 현장 안전 회로, ROS는 요청·확인·승인 | 생존 신호 + `estop` 목록. Pinky·서빙 팔의 안전 회로 유무는 확인 필요 |

## 6. 층별 정리

| 층 | 번호 | 정의서에 맞추는 비용 | 판단 |
| --- | --- | --- | --- |
| 웹 (화면 ↔ `web_service`) | 01~13 | 중간. 로봇에 영향 없음 | 정의서를 따라감. 다른 팀원의 화면과 만나는 경계 |
| 웹 ↔ 중앙 관제 ↔ Task Manager | 14~21, 32, 33 | 중간. 관제 PC 안에서 끝남 | 요청 키·거절 통보는 정의서를 따라감. 이름은 팀 합의 |
| 관제 ↔ AMR | 22~26, 34, 35 | 큼. 실기기 재검증 필요 | 정의서에 코드 내용을 적음 |
| AMR ↔ 서빙 팔 | 28, 36 | 작음~중간 | 28은 정의서에 코드 내용을 적음, 36은 정의서를 따라감 |
| 조리 팔 | 29~31, 37~39 | 팔 구동 방식이 정해지지 않아 판단 보류 | 코드가 대역이라 정의서 확정 뒤 맞춤 |
| 안전 | 40~42 | 작음. 덧붙이는 방식 | 생존 신호를 정의서에 적고, 확인·승인 절차는 정의서를 따라감 |
