# Frybot 인터페이스 제안서와 코드 비교

**검토일** 2026-11-25  
**코드 범위** `src/frybot`, `jazzy-port`, HEAD `4ab5d33` 및 당시 미커밋 변경

웹 3개 경로와 ROS 2 8개 이름·주소가 v0.2 방향으로 반영됐다. 통행 허가·서빙·Nav2 주행 연결도 주요 계약이 맞는다. 남은 작업은 재요청 중복 방지, 방문 ID 검증, AI 관측 만료 처리, 정지·재가동 결과 확인이 우선이다. AMR 안내·퇴식·복귀에는 현재 공통 액션 구조를 유지하는 편이 좋다.

## 제안 기준과 구현 기준

| 문서 | 무엇을 담았나 | 이번 비교에서의 역할 |
| --- | --- | --- |
| [통합 인터페이스 정의서 v0.2](https://oneteam1.atlassian.net/wiki/spaces/1/pages/25690124) | 01~44번 상세 제안의 목차. 새 주소·필드, 요청 중복 방지, 오류·복구 등 목표 계약이 담겨 있다. 22번 통행 허가와 24번 서빙처럼 현행 구현에 맞춰 정정된 항목도 있다. | **변경 목표의 주 기준.** [11월 25일 로컬 작업 기록](../2026-11-25_IF_V02_CHECK.md)의 기준 선택을 따랐다. |
| [인터페이스 정의서 v0.3](https://oneteam1.atlassian.net/wiki/spaces/1/pages/28573701) | 01~44번을 한 페이지에 정리한 적용 기준. 웹은 설계 계약을 담고, ROS 2는 작성 당시 구현의 주소·IDL과 기존 연결에 통합된 항목을 정리한다. | **구현 이력과 통합 방식의 보조 근거.** 14~17·19·20·31·32번은 이전 ROS 2 이름·주소를 담고 있다. |
| 로컬 작업 트리 | 현재 등록된 경로·타입·필드와 콜백 동작 | **현재 동작을 판단하는 기준.** 실제 배포 상태는 실행 그래프와 실기기 확인이 필요하다. |

예를 들어 방문 등록 14번에서 v0.2는 `RegisterVisit`과 `/frybot/central/register_visit`를 정의하고, v0.3은 당시 구현인 `CheckIn`과 `/frybot/check_in`을 적고 있다. 현재 작업 트리는 v0.2의 이름·주소를 사용하지만, 요청·응답 필드는 여전히 구현 당시 형식이다. 반대로 고객 안내 23번은 v0.2 상세가 전용 `GuideGuest`를 제안하고, v0.3과 현재 코드는 공통 `NavigateRoute`에 통합한다. 두 문서가 각각 현행을 표기하므로 팀의 공식 적용 기준은 확인이 필요하다. [14번 상세](https://oneteam1.atlassian.net/wiki/spaces/1/pages/24445717) · [23번 상세](https://oneteam1.atlassian.net/wiki/spaces/1/pages/26017796) · [중앙 관제 코드](../../src/frybot/frybot_control/frybot_control/central_control_node.py#L94)

## 1. 제안서대로 반영된 부분

| I/F | 코드에서 확인한 내용 | 근거 |
| --- | --- | --- |
| **01·04·07 웹 경로** | `POST /api/visits`, `/api/orders`, `/api/admin/operations`가 서버와 화면 호출에 반영됐다. 이번 변경 범위는 경로다. | [웹 라우팅](../../src/frybot/frybot_web/frybot_web/web_service_node.py#L133) |
| **14~17·19·20 ROS 2 서비스** | `RegisterVisit`, `SubmitOrder`, `EndVisit`, `RequestAdminOperation`이 `/frybot/central/` 아래에 연결됐다. `SubmitTask`, `ControlTask`는 `/frybot/tasks/submit`, `/frybot/tasks/control`을 사용한다. | [중앙 관제](../../src/frybot/frybot_control/frybot_control/central_control_node.py#L94) · [Task Manager](../../src/frybot/frybot_control/frybot_control/task_manager_node.py#L98) |
| **31·32 ROS 2 토픽** | `/frybot/central/view_state` 주소와 `TaskProgress` 타입 및 `/frybot/tasks/progress` 주소가 반영됐다. 31번은 전체 스냅샷 JSON을 사용하며, 32번도 제안서와 필드 차이가 있다. | [상태 발행](../../src/frybot/frybot_control/frybot_control/central_control_node.py#L112) · [TaskProgress.msg](../../src/frybot/frybot_interfaces/msg/TaskProgress.msg) |
| **22·24·27 통행·서빙·주행** | `TrafficGrant`의 네 필드와 0.5초 재발행, `NavigateRoute`와 `ArmJob`을 사용한 이동 → LOAD → 이동 → UNLOAD, Nav2 `NavigateToPose` 연결이 맞는다. 22번 상세의 heartbeat 기본값은 2초이고 코드 기본값은 1초다. | [통행 허가](https://oneteam1.atlassian.net/wiki/spaces/1/pages/25788458) · [서빙 흐름](https://oneteam1.atlassian.net/wiki/spaces/1/pages/25755717) · [AMR 제어기](../../src/frybot/frybot_mobile/frybot_mobile/mobile_controller.py#L211) |

## 2. 코드 수정이 필요한 부분

| 우선순위 | I/F | 남은 작업 |
| --- | --- | --- |
| 높음 | **01·04·05·07, 14~17·19·20 요청 중복과 결과 구분** | 웹 `request_key`와 ROS 2 `request_id`를 실제 처리까지 전달한다. 현재 웹이 4초 후 응답 대기를 끝내도 ROS 요청은 계속 처리될 수 있다. 늦게 완료된 주문을 사용자가 다시 제출하면 중복 생성될 수 있으므로, 같은 키로 기존 결과를 반환하고 거절과 결과 미확인을 구분해야 한다. [웹 서비스 호출부](../../src/frybot/frybot_web/frybot_web/web_service_node.py#L272) |
| 높음 | **04·05·15·16 방문과 주문의 연결** | 현재 주문과 종료는 `table_id` 기준이다. 요청의 `visit_id`를 활성 방문과 대조하면 이전 방문의 늦은 요청이 같은 테이블의 새 방문에 적용되는 일을 막을 수 있다. `{menu, qty}`와 `{menu_id, quantity}` 변환 및 응답 ID 표현은 웹·DB 계약과 함께 정한다. [웹 주문·종료 처리](../../src/frybot/frybot_web/frybot_web/web_service_node.py#L294) |
| 높음 | **21·34~37·43·44 실행 복구와 장비 상태 확인** | 늦은 경로 결과는 `plan_version`으로 거른다. 실패 시 마지막 도달 위치 반영, `ArmStatus.error` 전파, 관제 단절 시 팔 정지 확인이 남았다. `RESUME` 이벤트에 승인자와 현장 확인 정보를 남기는 방안과 자체점검 범위를 정한다. [경로 결과](../../src/frybot/frybot_control/frybot_control/fleet_core.py#L1883) · [재가동](../../src/frybot/frybot_control/frybot_control/fleet_core.py#L2343) · [실물 팔 취소](../../src/frybot/frybot_mobile/frybot_mobile/mobile_controller.py#L1530) |
| 높음 | **38 AI 관측 유효성** | AI → 관제 `POST :8100/ai/result` 연결은 있다. 관제는 수신 시각을 기록하고 `GuestTrack`에 발행 시각을 찍는다. 원본 관측 시각과 유효기간을 전달해 지연된 프레임을 거르고, 미검출·수신 불가·만료를 구분한다. [AI 관측 정의](https://oneteam1.atlassian.net/wiki/spaces/1/pages/26148904) · [AI 수신부](../../src/frybot/frybot_control/frybot_control/central_control_node.py#L329) |
| 연동 계약 확정 후 | **02·03·06·08~11·13·31 웹 조회와 진단** | 화면은 `/api/state`를 주기 조회하고 관리 이력에 `/api/events`를 쓴다. 방문 상태·메뉴·관리자 현황·테이블·개별 주문 전용 조회, 조작 결과 조회, `/api/health`, WebSocket은 v0.2와 차이가 있다. 외부 웹이 소비할 경로를 정한 뒤 권한·응답 형식·스냅샷 버전과 기준 시각을 맞춘다. v0.3은 개별 주문 표시와 WebSocket을 기존 조회에 통합하는 안을 담고 있다. [웹 조회 라우팅](../../src/frybot/frybot_web/frybot_web/web_service_node.py#L133) · [v0.3 적용 기준](https://oneteam1.atlassian.net/wiki/spaces/1/pages/28573701) |

팀 결정이나 실측이 필요한 항목은 **01·14 대기 접수**, **29 조리 공정 소유권**, **33 상태 QoS·주기**, **39 UDP 영상**, **41 MySQL 전환**이다. 현재 코드는 빈 테이블이 없으면 거절하고, Task Manager가 조리 단계와 익힘 판정을 관리하며, DB는 SQLite를 쓴다. 실물 카메라는 TCP MJPEG이고 시뮬레이션의 UDP는 대역 JSON을 전송한다. 12번 음성 명령은 예정 항목이다. 40번 AI 내부 IPC와 42번 Colab 학습 연동은 운영 패키지의 필수 변경 범위 밖으로 보는 편이 타당하다. [방문 처리](../../src/frybot/frybot_control/frybot_control/restaurant.py#L61) · [조리 공정](../../src/frybot/frybot_control/frybot_control/fleet_core.py#L2402) · [영상 실측 기록](../2026-11-24_GUEST_TRACK_YOLO_PLAN.md) · [SQLite 저장소](../../src/frybot/frybot_control/frybot_control/db.py#L34)

## 3. 현재 코드의 구조를 유지할 부분

| I/F | 유지할 구조 | 판단 근거 |
| --- | --- | --- |
| **23·25·26 안내·퇴식·복귀** | 공통 `NavigateRoute`에 안내용 `GuestTrack`, 퇴식용 `ArmJob`, 마지막 도킹 구간의 Nav2 `DockRobot`을 연결한다. | 공통 경로에 `TrafficGrant`를 적용하므로 좁은 통로의 양보·재계획·구간 점유를 한 곳에서 관리할 수 있다. 업무별 완료 정보가 필요하면 공통 액션 결과를 보강한다. [AMR 액션 연결](../../src/frybot/frybot_mobile/frybot_mobile/mobile_controller.py#L279) · [기존 실기기 기록](../2026-11-20_REAL_TEST.md) |
| **28·30 서빙 팔과 조리 팔** | 서빙 팔과 조리 팔 A/B에 공통 `ArmJob`을 쓴다. | 목표·피드백·결과·취소를 재사용할 수 있다. v0.2 24번 상세도 실물 서빙 팔 경로에 `ArmJob`을 명시한다. 실물 전달과 조리 단계의 완료 확인 값은 센서나 확인 절차가 정해지면 추가한다. [ArmJob.action](../../src/frybot/frybot_interfaces/action/ArmJob.action) · [24번 상세](https://oneteam1.atlassian.net/wiki/spaces/1/pages/25755717) |
| **18·31·32·33 상태 조회와 실행 식별** | 최근 전체 스냅샷, `TaskProgress.plan_version`, 공용 `/fleet/robot_status`를 활용한다. | 자체 웹은 다음 스냅샷으로 화면을 복구하고 관제와 시각화는 전체 로봇을 한 토픽으로 볼 수 있다. 스냅샷 기준 시각·버전과 배터리 관측 시각을 보강한다. 상태 QoS는 실기기 Wi-Fi 측정 후 결정한다. [웹 상태 구독](../../src/frybot/frybot_web/frybot_web/web_service_node.py#L118) · [RobotStatus.msg](../../src/frybot/frybot_interfaces/msg/RobotStatus.msg) |
| **35~37 소프트웨어 정지 전달** | 5 Hz `/fms/heartbeat`에 정지 대상과 관제 세션을 반복 전달한다. | 한 번 유실되어도 다음 메시지에서 정지 상태를 받을 수 있고 AMR 주행은 heartbeat 단절과 관제 재시작에 대응한다. 이 전달 구조에 요청 접수, 장비 정지 확인, 재가동 승인 기록을 보강한다. [heartbeat 수신](../../src/frybot/frybot_mobile/frybot_mobile/mobile_controller.py#L451) · [재가동 제안](https://oneteam1.atlassian.net/wiki/spaces/1/pages/26116147) |

## 검증 범위

Confluence 조회와 현재 소스 대조를 기준으로 작성했다. 기존 기록에 이름 변경 후 빌드·pytest·경량 시뮬레이션 결과가 있다. 이번 검토에서 새 실행 그래프, 실기기, 별도 저장소의 OpenAPI·IDL 검증은 수행하지 않았다. [기존 검증 기록](../2026-11-25_IF_V02_CHECK.md#9-적용-결과)
