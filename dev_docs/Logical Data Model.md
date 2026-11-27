# Logical Data Model

**검토용 초안 v0.3** · 작성  · 확정 목표  상세설계 · 스키마 v3

근거: [System Requirements](https://oneteam1.atlassian.net/wiki/spaces/1/pages/65685/System+Requirements) v6 · [State Diagram](https://oneteam1.atlassian.net/wiki/spaces/1/pages/9043988/State+Diagram+V0.04) v3 · [System Architecture](https://oneteam1.atlassian.net/wiki/spaces/1/pages/786434/System+Architecture) · 상위 모델: [Conceptual Data Model](https://oneteam1.atlassian.net/wiki/spaces/1/pages/10354702/Conceptual+Data+Model)

## 0. 작성 원칙

1. **상태값은 State Diagram 이름을 그대로** 쓴다. 상태를 바꾸는 주체는 그 상태가 놓인 레인이다.
2. State Diagram·SR에 근거가 없는 **DB 전용 항목은 SQL에서 주석 처리**(`-- [DB 제안]`)하고, 팀이 반영하면 해제한다. 지금 넣으면 DB가 거부한다.
3. 깨지면 안 되는 규칙(중복 배정, 로봇 이중 임무 등)은 **DB 제약으로 강제**한다.

색: WAITING 대기 · COMPLETED 완료 · E\_STOP 오류 · GUIDING 진행 · DB 제안 주석 처리 (State Diagram 범례와 같음)

## 1. 상태 정의

### 1.1 레인별 상태 (State Diagram 원본에서 추출)

| 레인 (주체) | 상태 | DB 저장 위치 |
| --- | --- | --- |
| 입구 접수 UI | CHECK\_IN | `visit.status` 초기값 |
| 테이블 주문 UI | SELECTINGEND\_OF\_USE | SELECTING은 화면 상태라 저장하지 않음 |
| 서버/고객·테이블·주문 관리 | WAITINGASSIGNEDIN\_USEEND\_OF\_USECLEANINGAVAILABLE | `visit.status`, `dining_table.status` |
| 〃 (3장 주문) | ORDEREDCOOKINGREADYSERVINGARRIVEDCOMPLETEDON\_HOLDCANCELED | `orders.status` |
| 서버/Service Workflow | GUIDE\_REQGUIDE\_PENDINGGUIDE\_EXCEPTIONCOOK\_TASKSERVE\_REQSERVE\_PENDINGON\_HOLDRECOVERY\_WAITCHECKRESUMECANCEL\_TASKREASSIGNCANCELED | `task.state` |
| AI Server | FOLLOW\_CHECKDONENESS | `vision_result.kind` |
| AMR × 3 | IDLETO\_ENTRANCEGUIDINGPAUSEDARRIVEDRETURNINGCHARGINGTO\_PICKUPQUEUEDDOCKEDSERVINGE\_STOP | `robot.state` |
| 로봇팔 Station | IDLEPICK\_CHICKENFRYINGWAIT\_TIMERLIFT\_AND\_DRAINPICK\_INGREDIENTSSTIR\_FRYINGPLATINGON\_HANDOFFRETRYLOADINGE\_STOP | `robot.state` |

### 1.2 테이블 dining\_table.status — 고객·테이블·주문 관리

| 전이 | 조건 | 근거 |
| --- | --- | --- |
| AVAILABLE → ASSIGNED | 손님 그룹에 배정 (중복 배정 불가) | 2장, SR-003·004 |
| ASSIGNED → IN\_USE | 안내 AMR 테이블 도착(착석) | 2장 |
| IN\_USE → CLEANING | 이용 종료 확정 (미전달 주문 없음) | 6장, SR-028 |
| CLEANING → AVAILABLE | 관리자 정리 완료 입력 | 6장, SR-029 |

관리자가 상태를 바꿀 수 있지만 중복 배정은 DB가 막는다 (SR-031).

### 1.3 손님 그룹 visit.status — 입구 접수 UI → 고객·테이블·주문 관리

| 전이 | 조건 | 근거 |
| --- | --- | --- |
| (생성) CHECK\_IN | 입구에서 인원 입력 | 2장, SR-001 |
| CHECK\_IN → WAITING | 빈 테이블 없음(만석) | 2장 |
| CHECK\_IN/WAITING → ASSIGNED | 빈 테이블 배정, 안내 임무 생성 | 2장 |
| ASSIGNED → IN\_USE | 테이블 도착(착석) | 2장 |
| IN\_USE → END\_OF\_USE | 이용 종료 확정 | 6장, SR-027 |
| CANCELED *DB 제안* | 대기 이탈·안내 포기 | State Diagram에 없음 → 주석 |

### 1.4 주문 orders.status — 고객·테이블·주문 관리

| 전이 | 조건 | 근거 |
| --- | --- | --- |
| (확정) ORDERED | 주문 확정·유효 → 주문 ID 발급 | 3장, SR-011·012 |
| ORDERED → COOKING | 조리 시작 보고 | 3장 |
| COOKING → READY | 조리 완료 보고 (픽업 대기) | 3장 |
| READY → SERVING | 적재 완료 보고 | 3장, SR-022 |
| SERVING → ARRIVED | 테이블 도착 보고 | 3장, SR-024·025 |
| ARRIVED → COMPLETED | 손님 수령 확인 또는 N초 후 자동 수령 (`received_by`) | 3·5장 |
| 진행 중 → ON\_HOLD | 장비 오류 (`hold_from_status`에 직전 상태 기록) | 3·7장 |
| ON\_HOLD → 멈춘 단계 / CANCELED | 관리자 재시도 / 취소 | 3·7장 |

### 1.5 임무 task.state — Service Workflow

| 상태 | 의미 | 근거 |
| --- | --- | --- |
| GUIDE\_REQCOOK\_TASKSERVE\_REQ | 임무 생성·전달. 로봇이 배정되면 진행은 `robot.state`로 본다 | 2·4·5장 |
| GUIDE\_PENDINGSERVE\_PENDING | 가용 AMR 없음 → 대기 (로봇 미배정) | SR-005, SR-019 |
| GUIDE\_EXCEPTION | 손님을 N초 이상 놓침 → 관리자 알림 | SR-008 |
| ON\_HOLD → RECOVERY\_WAIT → CHECK → RESUME | 오류 보류 → 복구 대기 → 관리자 재시도 → 조건 확인 → 멈춘 단계부터 재개 | 7장, SR-036 |
| CANCEL\_TASK → REASSIGN / CANCELED | 관리자 중단 → AMR 임무는 재배정, 조리 임무는 주문 취소 | 7장, SR-034 |
| DONE *DB 제안* | 완료 상태가 없어 지금은 `finished_at`으로 완료 표시 | State Diagram에 없음 → 주석 |

### 1.6 로봇 robot.state — AMR·로봇팔 보고 → Workflow 저장

AMR은 AMR 상태만, 로봇팔은 로봇팔 상태만 저장할 수 있다. OFFLINE(연결 끊김)은 DB 제안으로 주석, 지금은 `last_seen_at`으로 판단한다.

## 2. 논리 ERD

| 외래키 컬럼 | 참조 테이블 |
| --- | --- |
| `dining_table.location_id` | `location` |
| `incident.order_id` | `orders` |
| `incident.robot_id` | `robot` |
| `incident.task_id` | `task` |
| `order_item.menu_id` | `menu` |
| `order_item.order_id` | `orders` |
| `order_item.serve_task_id` | `task` |
| `orders.table_id` | `dining_table` |
| `orders.visit_id` | `visit` |
| `robot.home_location_id` | `location` |
| `task.order_id` | `orders` |
| `task.order_item_id` | `order_item` |
| `task.reassigned_from_task_id` | `task` |
| `task.robot_id` | `robot` |
| `task.visit_id` | `visit` |
| `vision_result.robot_id` | `robot` |
| `vision_result.task_id` | `task` |
| `visit.table_id` | `dining_table` |

```text
erDiagram
  location ||--o| dining_table : ""
  location ||--o{ robot : "home"
  dining_table ||--o{ visit : ""
  dining_table ||--o{ orders : ""
  visit ||--o{ orders : ""
  orders ||--|{ order_item : ""
  menu ||--o{ order_item : ""
  visit ||--o{ task : "GUIDE"
  order_item ||--o{ task : "COOK"
  orders ||--o{ task : "SERVE"
  task ||--o{ order_item : "serve_task_id"
  robot ||--o{ task : ""
  task ||--o| task : "reassigned_from"
  robot ||--o{ incident : ""
  task ||--o{ incident : ""
  orders ||--o{ incident : ""
  task ||--o{ vision_result : ""
  robot ||--o{ vision_result : ""
```

## 3. 테이블 정의서

실행 중인 DB(`information_schema`)에서 생성했다. 제약: PK 기본키 · FK 외래키 · UK 유일 · NN 필수 · 규칙용 생성 컬럼(직접 쓰지 않음)

### location — 로봇 이동 지점

*기준 정보 · 근거: SR-002, SR-020*

| 컬럼 | 타입 | 제약 | 설명 |
| --- | --- | --- | --- |
| `location_id` | `INT` | PK |  |
| `code` | `VARCHAR(20)` | UK NN | 사람이 읽는 코드 (ENT, T1, PICKUP, DOCK1) |
| `name` | `VARCHAR(50)` | NN | 표시 이름 |
| `type` | ENUM `ENTRANCE`, `TABLE`, `PICKUP`, `QUEUE`, `DOCK` | NN | PICKUP=받는 곳·인계대, QUEUE=대기 지점, DOCK=충전대 |
| `x` | `DOUBLE` |  | map 좌표(m), 실측 전 NULL |
| `y` | `DOUBLE` |  |  |
| `yaw` | `DOUBLE` |  |  |

### dining\_table — 테이블

*기준 정보 · 근거: SR-002\~004, SR-028\~031 · 2·6장*

| 컬럼 | 타입 | 제약 | 설명 |
| --- | --- | --- | --- |
| `table_id` | `INT` | PK |  |
| `code` | `VARCHAR(10)` | UK NN | 테이블 코드 (T1) |
| `seats` | `INT` | NN | 수용 인원 (SR-002) |
| `location_id` | `INT` | FK→location UK NN | 안내·서빙 위치 |
| `status` | ENUM `AVAILABLE`, `ASSIGNED`, `IN_USE`, `CLEANING` | NN | 이용 상태 (기본 AVAILABLE) |
| `updated_at` | `DATETIME(3)` | NN |  |

### visit — 손님 그룹

*서비스 · 근거: SR-001 · 2·6장*

| 컬럼 | 타입 | 제약 | 설명 |
| --- | --- | --- | --- |
| `visit_id` | `BIGINT` | PK |  |
| `party_size` | `INT` | NN | 인원 (SR-001) |
| `queue_no` | `INT` |  | 대기 순번(WAITING) |
| `table_id` | `INT` | FK→dining\_table | 배정 테이블, 대기 중 NULL |
| `status` | ENUM `CHECK_IN`, `WAITING`, `ASSIGNED`, `IN_USE`, `END_OF_USE` | NN | 손님 그룹 상태 (기본 CHECK\_IN) |
| `created_at` | `DATETIME(3)` | NN |  |
| `ended_at` | `DATETIME(3)` |  |  |
| `active_table_id` | `INT` | 규칙용 생성 컬럼 | 규칙용 생성 컬럼: 진행 중이면 table\_id → UNIQUE로 중복 배정 차단 |

### menu — 메뉴

*기준 정보 · 근거: SR-009, SR-016·017*

| 컬럼 | 타입 | 제약 | 설명 |
| --- | --- | --- | --- |
| `menu_id` | `INT` | PK |  |
| `name` | `VARCHAR(50)` | UK NN | 치킨, 볶음밥 |
| `cook_type` | ENUM `FRY`, `WOK` | NN | 조리할 로봇팔 선택 기준 |
| `is_available` | `TINYINT(1)` | NN | 품절이면 주문 오류(3장) (기본 1) |

### orders — 주문

*서비스 · 근거: SR-010\~013 · 3장*

| 컬럼 | 타입 | 제약 | 설명 |
| --- | --- | --- | --- |
| `order_id` | `BIGINT` | PK | 고유 주문 ID(SR-012) |
| `visit_id` | `BIGINT` | FK→visit NN | 주문한 손님 그룹 |
| `table_id` | `INT` | FK→dining\_table NN | 주문 화면의 테이블(SR-010) |
| `status` | ENUM `ORDERED`, `COOKING`, `READY`, `SERVING`, `ARRIVED`, `COMPLETED`, `ON_HOLD`, `CANCELED` | NN | 주문 진행 상태 (SR-013) (기본 ORDERED) |
| `hold_from_status` | ENUM `ORDERED`, `COOKING`, `READY`, `SERVING`, `ARRIVED` |  | ON\_HOLD 직전 상태. 재시도 시 여기로 복귀 |
| `received_by` | ENUM `CUSTOMER`, `AUTO` |  | 수령 확인 / N초 후 자동 수령 |
| `created_at` | `DATETIME(3)` | NN |  |
| `completed_at` | `DATETIME(3)` |  |  |

### order\_item — 주문 항목

*서비스 · 근거: SR-014·015*

| 컬럼 | 타입 | 제약 | 설명 |
| --- | --- | --- | --- |
| `order_item_id` | `BIGINT` | PK |  |
| `order_id` | `BIGINT` | FK→orders NN |  |
| `menu_id` | `INT` | FK→menu NN | 메뉴 |
| `qty` | `INT` | NN | 수량 (SR-009) (기본 1) |
| `ready_at` | `DATETIME(3)` |  | 서빙 준비 완료(인계대 ON\_HANDOFF) |
| `serve_task_id` | `BIGINT` | FK→task | 이 항목을 싣고 간 서빙 임무 |

### robot — 로봇

*기준 정보 · 근거: SR-033, SR-037 · AMR·로봇팔 레인*

| 컬럼 | 타입 | 제약 | 설명 |
| --- | --- | --- | --- |
| `robot_id` | `VARCHAR(20)` | PK | ROS2 네임스페이스와 같게 |
| `type` | ENUM `AMR`, `ARM` | NN | AMR / ARM |
| `cook_type` | ENUM `FRY`, `WOK` |  | 로봇팔만 |
| `state` | ENUM `IDLE`, `E_STOP`, `TO_ENTRANCE`, `GUIDING`, `PAUSED`, `ARRIVED`, `RETURNING`, `CHARGING`, `TO_PICKUP`, `QUEUED`, `DOCKED`, `SERVING`, `PICK_CHICKEN`, `FRYING`, `WAIT_TIMER`, `LIFT_AND_DRAIN`, `PICK_INGREDIENTS`, `STIR_FRYING`, `PLATING`, `ON_HANDOFF`, `RETRY`, `LOADING` | NN | 현재 장치 상태 (State Diagram 레인 상태) (기본 IDLE) |
| `home_location_id` | `INT` | FK→location | AMR 충전대 |
| `pose_x` | `DOUBLE` |  | 현재 위치 (SR-033) |
| `pose_y` | `DOUBLE` |  |  |
| `pose_yaw` | `DOUBLE` |  |  |
| `battery_pct` | `INT` |  | 배터리 % (SR-033) |
| `is_charging` | `TINYINT(1)` |  | SR-037: 복귀(RETURNING→도착)와 실제 충전을 구분 |
| `last_seen_at` | `DATETIME(3)` |  | 마지막 상태 보고 |

### task — 임무

*로봇 운영 · 근거: SR-005, 014, 018·019, 034 · 2·4·5·7장*

| 컬럼 | 타입 | 제약 | 설명 |
| --- | --- | --- | --- |
| `task_id` | `BIGINT` | PK |  |
| `task_type` | ENUM `GUIDE`, `COOK`, `SERVE` | NN | GUIDE 안내 / COOK 조리 / SERVE 서빙 |
| `state` | ENUM `GUIDE_REQ`, `GUIDE_PENDING`, `GUIDE_EXCEPTION`, `COOK_TASK`, `SERVE_REQ`, `SERVE_PENDING`, `ON_HOLD`, `RECOVERY_WAIT`, `CHECK`, `RESUME`, `CANCEL_TASK`, `REASSIGN`, `CANCELED` | NN | Service Workflow 레인 상태 |
| `hold_from_state` | ENUM `GUIDE_REQ`, `COOK_TASK`, `SERVE_REQ`, `RESUME` |  | ON\_HOLD 직전 상태 |
| `robot_id` | `VARCHAR(20)` | FK→robot | 배정 로봇, 대기 중 NULL |
| `visit_id` | `BIGINT` | FK→visit | GUIDE 대상 |
| `order_item_id` | `BIGINT` | FK→order\_item | COOK 대상 |
| `order_id` | `BIGINT` | FK→orders | SERVE 대상 |
| `reassigned_from_task_id` | `BIGINT` | FK→task | SR-034 재배정 전 임무 |
| `created_at` | `DATETIME(3)` | NN |  |
| `assigned_at` | `DATETIME(3)` |  | 로봇 배정 시각 |
| `finished_at` | `DATETIME(3)` |  | 완료 시각(완료 표시) |
| `active_robot_id` | `VARCHAR(20)` | 규칙용 생성 컬럼 | 규칙용 생성 컬럼: 진행 중이면 robot\_id → UNIQUE로 로봇당 1건 |

### incident — 오류·복구 기록

*로봇 운영 · 근거: SR-034, SR-036 · 7장*

| 컬럼 | 타입 | 제약 | 설명 |
| --- | --- | --- | --- |
| `incident_id` | `BIGINT` | PK |  |
| `source` | ENUM `DEVICE_ERROR`, `ADMIN_STOP` | NN | 오류 발생 / 관리자 중단 |
| `robot_id` | `VARCHAR(20)` | FK→robot NN | 장치 식별자 |
| `task_id` | `BIGINT` | FK→task | 관련 임무 |
| `order_id` | `BIGINT` | FK→orders | 관련 주문 |
| `error_code` | `VARCHAR(30)` |  | 오류 코드 (SR-036) |
| `error_message` | `VARCHAR(500)` |  | 오류 내용 |
| `failed_state` | `VARCHAR(30)` |  | 실패한 작업 단계(당시 robot.state) |
| `admin_choice` | ENUM `RETRY`, `STOP` |  | 관리자 선택 |
| `result` | ENUM `RESUME`, `REASSIGN`, `CANCELED` |  | 7장 처리 결과 |
| `occurred_at` | `DATETIME(3)` | NN | 발생 시각 |
| `resolved_at` | `DATETIME(3)` |  | 처리 완료 시각 |

### vision\_result — AI 판단 결과

*로봇 운영 · 근거: 2장 FOLLOW\_CHECK, 4장 DONENESS*

| 컬럼 | 타입 | 제약 | 설명 |
| --- | --- | --- | --- |
| `result_id` | `BIGINT` | PK |  |
| `task_id` | `BIGINT` | FK→task NN | 판단 대상 임무 |
| `robot_id` | `VARCHAR(20)` | FK→robot NN | 영상을 보낸 장치 |
| `kind` | ENUM `FOLLOW_CHECK`, `DONENESS` | NN |  |
| `decision` | `VARCHAR(20)` | NN | FOLLOW\_CHECK: NEAR/FAR/LOST, DONENESS: DONE/UNDERCOOKED |
| `confidence` | `DECIMAL(5,4)` |  | 신뢰도 0\~1 |
| `model_version` | `VARCHAR(50)` |  |  |
| `detail` | `JSON` |  | 원본 결과 JSON |
| `created_at` | `DATETIME(3)` | NN |  |

### system\_config — 기준값

*기준 정보 · 근거: State Diagram 확인 사항 4 (기준값 N)*

| 컬럼 | 타입 | 제약 | 설명 |
| --- | --- | --- | --- |
| `config_key` | `VARCHAR(50)` | PK | 기준값 이름 |
| `value` | `DECIMAL(10,3)` |  | 미정이면 NULL |
| `unit` | `VARCHAR(10)` | NN |  |
| `description` | `VARCHAR(200)` | NN |  |
| `updated_at` | `DATETIME(3)` | NN |  |

### event\_log — 운영 이력

*이력 · 근거: SR-038*

| 컬럼 | 타입 | 제약 | 설명 |
| --- | --- | --- | --- |
| `log_id` | `BIGINT` | PK |  |
| `entity` | ENUM `VISIT`, `TABLE`, `ORDER`, `TASK`, `ROBOT`, `INCIDENT` | NN | 대상 종류 |
| `entity_id` | `VARCHAR(30)` | NN | 대상 ID |
| `from_state` | `VARCHAR(30)` |  | 이전 상태 |
| `to_state` | `VARCHAR(30)` |  | 다음 상태 |
| `actor` | ENUM `ENTRANCE_UI`, `TABLE_UI`, `ADMIN_UI`, `ORDER_MANAGER`, `WORKFLOW`, `AI_SERVER`, `AMR`, `ARM` | NN | 주체 (State Diagram 레인) |
| `message` | `VARCHAR(500)` |  |  |
| `detail` | `JSON` |  |  |
| `created_at` | `DATETIME(3)` | NN |  |

### schema\_version — 스키마 버전

*이력 · 근거: 스키마 연동*

| 컬럼 | 타입 | 제약 | 설명 |
| --- | --- | --- | --- |
| `version` | `INT` | PK |  |
| `description` | `VARCHAR(200)` | NN |  |
| `applied_at` | `DATETIME` | NN |  |

### 관제용 뷰

| 뷰 | 내용 | 근거 |
| --- | --- | --- |
| `v_table_board` | 테이블별 상태, 현재 손님 그룹, 진행 중 주문 수 | SR-030, SR-032 |
| `v_order_progress` | 주문별 항목 수, 서빙 준비 수, 적재 수 | SR-013, SR-015 |
| `v_robot_board` | 로봇별 상태, 배터리, 충전 여부, 위치, 현재 임무 | SR-033, SR-037 |

## 4. DB 규칙

애플리케이션 코드가 아니라 DB 제약으로 걸려 있어 어긋난 데이터는 저장이 거부된다. `db/tests/run_tests.sh`가 State Diagram 2\~7장 정상 흐름 11건과 금지 규칙 15건을 검사한다(26/26 통과).

| 규칙 | DB 제약 이름 | 근거 |
| --- | --- | --- |
| 같은 테이블에 진행 중(ASSIGNED, IN\_USE) 손님 그룹은 1개 | `uk_visit_active_table` | SR-004, SR-031 |
| ASSIGNED·IN\_USE면 테이블이 있어야 함 | `chk_visit_table` | 2장 |
| ON\_HOLD면 복귀할 상태(hold\_from\_status)가 있어야 함 | `chk_orders_hold` | 3장 재시도 |
| COMPLETED면 수령 방식(손님 확인/자동)이 있어야 함 | `chk_orders_done` | 5장 |
| 로봇 1대에 진행 중 임무는 1건 | `uk_task_active_robot` | SR-005, SR-019 |
| 임무 유형별 대상: GUIDE→손님 그룹, COOK→주문 항목, SERVE→주문 | `chk_task_target` | SR-014, SR-018 |
| 유형에 맞는 상태만 (조리 임무가 SERVE\_REQ 불가) | `chk_task_type_state` | State Diagram |
| \*\_PENDING(가용 AMR 없음) 임무에는 로봇 없음 | `chk_task_pending_robot` | SR-005, SR-019 |
| ON\_HOLD면 복귀할 상태가 있어야 함 | `chk_task_hold` | 7장 |
| 재배정은 AMR 임무(GUIDE, SERVE)만. 조리는 주문 취소 | `chk_task_reassign` | 7장, SR-034 |
| AMR은 AMR 상태만, 로봇팔은 로봇팔 상태만 | `chk_robot_type_state` | State Diagram 레인 |
| 로봇팔만 조리 방식(FRY/WOK)을 가짐 | `chk_robot_cook_type` | SR-016·017 |
| 장치 오류면 오류 코드 필수 | `chk_incident_error` | SR-036 |
| 처리 결과와 처리 시각은 함께 기록 | `chk_incident_resolved` | 7장 |
| 판단 값 범위: 손님 거리 NEAR/FAR/LOST, 익힘 DONE/UNDERCOOKED | `chk_vision_decision` | 2·4장 |

## 5. DB 제안 (주석 처리)

| 항목 | 필요한 이유 | 지금 대체 방법 | 해제 조건 |
| --- | --- | --- | --- |
| CANCELED visit | 대기 이탈·안내 포기 손님을 끝낼 상태가 없음 | 없음 (대기 목록에 남음) | State Diagram 2장에 추가 |
| DONE task | 임무 완료 상태가 없음 | `finished_at` 기록 | State Diagram에 완료 상태 추가 |
| OFFLINE robot | 연결 끊긴 로봇 표시 | `last_seen_at`으로 판단 | 7장 등에 추가 |
| `menu.price` | 가격 표시 | — | 결제를 범위에 포함 |
| `menu.cook_sec` | 표준 조리 시간 (ETA) | — | ETA를 범위에 포함 |
| `eta_prediction` 테이블 | Colab ETA 예측 저장 | — | ETA 학습을 SR에 추가 |

## 6. 접속·변경 방법

| 항목 | 값 |
| --- | --- |
| 호스트 | `192.168.0.8` (서버 PC IP, 바뀔 수 있음) · 포트 `3306` · DB `frybot` |
| 계정 | `team_dev` 읽기·쓰기 / `team_ro` 조회 전용 / `frybot` 스키마 담당 |
| 비밀번호 | 담당자에게 개별로 받는다. 단톡방에 올리지 않는다. |

```bash
# 권장: 비밀번호를 .env에 넣어 두고 스크립트로 접속
./db/connect.sh team_dev 192.168.0.8
# 직접 칠 때 (마지막 frybot은 DB 이름, 비밀번호는 Enter 후 입력)
mysql -h 192.168.0.8 -u team_dev -p frybot
# 내 PC에 똑같이 띄우기
cp .env.example .env && docker compose up -d && ./db/tests/run_tests.sh
```

- 스키마 기준은 `db/init/*.sql`. DB 파일이 아니라 이 파일을 git으로 공유한다.
- 변경은 `04_xxx.sql`처럼 번호를 붙인 새 파일로, `schema_version`에 한 줄 추가한다. 구조 변경은 스키마 담당만 하고 PR 리뷰를 거친다.
- 버전 확인: `SELECT MAX(version) FROM schema_version;` → 지금 **3**
