# Confluence I/F 문서 검토 기록 (v0.3, 2026-11-26)

작성: 2026-11-26. Confluence의 FryBot 인터페이스 문서들이 서로 통일성 있게 정리됐는지 조회만으로 확인한 기록입니다. Confluence는 수정하지 않았습니다.

- 검토한 이유: 사용자가 "코드를 정의서에 맞춘다(정의서에 있는 것은 코드에 있어야 하고 달라서도 안 된다)"는 방향을 정했습니다. 기준이 되는 정의서가 문서끼리 어긋나 있으면 무엇에 맞출지 정할 수 없어, 먼저 문서 사이의 일치 여부를 확인했습니다.
- 이전 대조: [v0.2와 코드 대조(2026-11-25)](2026-11-25_IF_V02_CHECK.md). 그 문서가 기준으로 삼은 v0.2 페이지는 같은 주소에서 v0.3 본문으로 교체됐습니다(아래 1장).
- 확인 방법: Atlassian 조회 도구로 본문을 받아 번호·이름·주소·링크를 비교했습니다. 개별 v0.3 페이지 41개는 통합 정의서의 같은 번호 구간과 줄 단위로 비교했습니다.
- 확인하지 못한 것: 참조 페이지 6개(4.5절)는 이름·주소·머리말만 보았고 필드 단위로 대조하지 않았습니다. 화면에 렌더링된 모습(굵은 글씨, 링크 표시)은 보지 않고 본문 변환 결과로 판단했습니다(확인 필요). 통합 정의서가 근거로 드는 Google Drive의 "정정된 API 실무가이드"는 열어 보지 않았습니다.

## 1. 조회한 페이지

| 페이지 | id | 판 | 마지막 수정(UTC) | 수정 메모 |
| --- | --- | --- | --- | --- |
| [1) FryBot I/F 목록](https://oneteam1.atlassian.net/wiki/spaces/1/pages/24641549) | 24641549 | 18 | 2026-11-25 08:55 | 현행 I/F 목록을 이전된 통합 정의서 및 개별 v0.3 페이지로 연결 |
| [FryBot 통합 인터페이스 정의서 v0.3 — 01~44 현행 적용 기준](https://oneteam1.atlassian.net/wiki/spaces/1/pages/25690124) | 25690124 | 11 | 2026-11-25 08:54 | v0.3 통합 적용 기준 본문 반영 |
| [FryBot I/F 목록 정정 · 통행 허가와 서빙](https://oneteam1.atlassian.net/wiki/spaces/1/pages/28016712) | 28016712 | 1 | 2026-11-24 08:44 | 없음 |

통합 정의서(25690124) 아래의 하위 페이지는 51개입니다.

| 묶음 | 개수 | 페이지 | 마지막 수정(UTC) |
| --- | --- | --- | --- |
| 개별 v0.3 | 41 | `02)`~`21)`, `23)`, `25)`~`44)` `… v0.3` | 2026-11-25 08:48~08:50 |
| 개별 v0.2 | 3 | `01) WEB-01 방문 접수 v0.2`(25690148), `22) 통행 허가 TrafficGrant v0.2`(25788458), `24) 서빙 흐름 NavigateRoute + ArmJob v0.2`(25755717) | 2026-11-24 06:06, 08:39, 08:39 |
| 참조 | 6 | `01) ROS 2 Service 상세 정의`(26869761), `02) ROS 2 Action 상세 정의`(26771509), `03) ROS 2 Topic 상세 정의`(26771531), `04) ROS 2 안전 Service 후보`(26869783), `05) FryBot 시나리오·상태·시퀀스별 데이터 전송 정의`(27000833), `FryBot API 요약 · 2차 연동시험 ROS 2 계약`(26771458) | 2026-11-23 14:03~2026-11-24 08:39 |
| 사본 | 1 | `FryBot 인터페이스 정의서 v0.3 — 01~44 현행 적용 기준`(28573701) | 2026-11-24 14:21 |

## 2. 결론

- 현행 v0.3 본문끼리는 맞습니다: I/F 목록의 위쪽 표, 통합 정의서, 개별 v0.3 페이지 41개, 11-24 사본.
- 전체로는 통일되지 않았습니다. I/F 목록의 아래쪽 표, 정정 페이지, 개별 v0.2 페이지 3개, 참조 페이지 6개가 v0.2 설계안의 이름과 건수를 그대로 갖고 있고, "이전 내용"이라는 표시가 없거나 현행 문서에서 링크로 이어집니다.
- 통합 정의서 본문 안에도 서로 다른 표기와 빈 칸이 있습니다(4.7절, 4.8절).
- 코드를 맞출 기준은 통합 정의서 v0.3 본문 하나로 잡으면 됩니다. 다만 4.7절의 표기 차이는 작성자가 확정해야 웹 쪽을 구현할 수 있습니다.

## 3. 맞게 정리된 부분

| 비교 | 결과 |
| --- | --- |
| I/F 목록 위쪽 표(01~44) ↔ 통합 정의서의 번호별 제목 | 44건 모두 번호·이름 같음 |
| 개별 v0.3 페이지 41개 ↔ 통합 정의서의 같은 번호 구간 | 41건 모두 주소·타입·필드·수치 같음. 다른 것은 잘못 들어간 링크(4.6절)와 통합본에만 있는 "v0.2 상세 이력" 줄뿐 |
| 정정 페이지 22·24번 ↔ 통합 정의서 22·24번 | `/fms/traffic_grant`, 필드 타입(string·int32), 이동 → LOAD → 이동 → UNLOAD 순서 같음 |
| 11-24 사본(28573701) ↔ 통합 정의서 | 본문 같음. 다른 것은 통합본 쪽의 잘못 들어간 링크 3줄 |

## 4. 문제 목록

번호는 이 문서 안의 추적 번호(C-xx)입니다.

### 4.1 I/F 목록 아래쪽 표가 v0.2 그대로 (C-01)

- 위치: I/F 목록(24641549)의 `## I/F 목록` 절 전체(웹 연동, ROS 2 Service·Action·Topic, 안전 Service 후보, AI·영상·DB·학습 연동, 장비 운용 검토).
- 페이지 맨 위 제목은 "FryBot I/F v0.3 현행 목록"이고 위쪽 표는 v0.3입니다. 그 아래 `## 이전 목록과 담당자 기록` 절은 링크 두 줄뿐이고, 같은 수준의 제목 `## I/F 목록`이 이어져 아래쪽 표가 "이전 목록"인지 현행인지 알 수 없습니다.

| 항목 | I/F 목록 아래쪽 표 | 통합 정의서 v0.3 |
| --- | --- | --- |
| 건수·번호 | 49건, 링크 번호 `01)`~`49)` | 44건 |
| 집계 문구 | "HTTP 12개와 WebSocket 1채널", "기존 논리 연결 26개 · 공통 계약 21개", "Service 9개", "Action 9개", "Topic 8개", "안전 Service 후보 3개" | 해당 집계 없음. 11번은 06에 통합, 12번은 범위 제외, 13번은 WebSocket 0회, 18·21·36·37·43·44번은 별도 I/F 0회 |
| 웹 경로 | `POST /visits`, `GET /menu` 등 `/api` 없음. `GET /orders/{order_id}`, `POST /voice/command`, WebSocket 포함 | `/api/visits`, `/api/menu` 등. 11·12·13번은 경로 없음 |
| 14 | `RegisterVisit` `/frybot/central/register_visit` | `CheckIn` `/frybot/check_in` |
| 15 | `SubmitOrder` `/frybot/central/submit_order` | `PlaceOrder` `/frybot/place_order` |
| 16 | `EndVisit` `/frybot/central/end_visit` | `EndUse` `/frybot/end_use` |
| 17 | `RequestAdminOperation` `/frybot/central/request_admin_operation` | `AdminCommand` `/frybot/admin` |
| 18 | `GetViewState` `/frybot/central/get_view_state` | 31번에 통합, 별도 서비스 0회 |
| 19 | `SubmitTask` `/frybot/tasks/submit` | `SubmitTask` `/fms/submit_task` |
| 20 | `ControlTask` `/frybot/tasks/control` | `FleetCommand` `/fms/command` |
| 21 | `GetExecution` `/frybot/tasks/get_execution` | 22·24·32·33에 통합, 별도 서비스 0회 |
| 22 | `RequestPassage` 서비스 `/frybot/tasks/request_passage`(AMR → Task Manager) | `TrafficGrant` 토픽 `/fms/traffic_grant`(Task Manager → AMR) |
| 23 | `GuideGuest` `/{mobile_ns}/guide_guest` | 24번 `NavigateRoute` GUIDE에 통합, `/frybot/guest_track` |
| 24 | `ServeFood` `/{mobile_ns}/serve_food` | `NavigateRoute` `/{pinky}/navigate_route` + `ArmJob` `/{pinky}/arm_job` |
| 25 | `CollectDishes` `/{mobile_ns}/collect_dishes` | 24번에 통합 |
| 26 | `ReturnToCharge` `/{mobile_ns}/return_to_charge` | `DockRobot` `/{pinky}/dock_robot` |
| 27 | `NavigateToPose` `/{mobile_ns}/navigate_to_pose` | `/{pinky}/navigate_to_pose`(이름 표기만 다름) |
| 28 | `TransferObject` `/{mobile_ns}/arm/transfer_object` | `ArmJob` `/{pinky}/serving_arm/arm_job` |
| 29 | `ExecuteCookingJob` `/frybot/cooking/execute_job` | `ArmJob` `/frybot_arm/arm_job` |
| 30 | `CookStep` `/frybot/cooking/arm_a/cook_step`, `arm_b` | `ArmJob` `/cook_arm_a/arm_job`, `/cook_arm_b/arm_job` |
| 31 | `ViewState` `/frybot/central/view_state` | `std_msgs/String`(JSON) `/frybot/state` |
| 32 | `TaskProgress` `/frybot/tasks/progress` | `TaskEvent` `/fms/task_events` |
| 33 | `MobileStatus` `/{mobile_ns}/status` | `RobotStatus` `/fleet/robot_status` |
| 34 | `DeviceEvent` 주소 5개 | `ArmStatus` `/fleet/arm_status` |
| 35~37 | `RequestEmergencyStop`, `GetSafetyState`, `AuthorizeRestart` (`/{device_ns}/safety/...`) | `FleetHeartbeat` `/fms/heartbeat`, 33번에 통합, 20번에 통합 |
| 38 | "AI 관측 HTTP … 방향·경로 검토 중" | `POST :8100/ai/result`(AI 서버 → 중앙 관제)로 확정 서술 |
| 41 | "DB TCP" | SQLite 파일, 네트워크 DB 호출 0회 |
| 42 | "Colab REST" | 운영 중 REST 호출 0회 |

- 아래쪽 표의 번호 체계가 위쪽과 어긋납니다. 예: 아래쪽 링크 `32) ROS2-01-T01 ViewState`는 위쪽의 31번, `33) ROS2-02-T01 TaskProgress`는 32번, `34) ROS2-03-T01 MobileStatus`는 33번입니다.
- 아래쪽 표의 링크 49개 중 48개는 2026-11-20 판의 옛 페이지로 가고, `12) 음성 명령 접수 (예정)` 하나만 v0.3 페이지(25690214)로 갑니다.

### 4.2 정정 페이지가 지금 구조와 맞지 않음 (C-02)

- 위치: 정정 페이지(28016712) 전체.
- "기존 RequestPassage와 ServeFood 표기는 이전 설계 후보다"라고 적지만, I/F 목록 아래쪽 표에는 그 두 표기가 표시 없이 남아 있습니다.
- 22·24번만 정정 대상으로 적습니다. v0.3에서 바뀐 것은 4.1절 표의 14~42번 대부분이라, 이 페이지만 보면 나머지 옛 이름은 유효한 것처럼 읽힙니다.
- 22·24번 링크가 v0.2 개별 페이지(25788458, 25755717)로 갑니다. I/F 목록 위쪽 표는 같은 번호를 통합 정의서의 해당 절로 연결합니다.
- I/F 목록과 통합 정의서 어디에도 이 페이지로 가는 링크가 없습니다.
- 작성 시점(11-24)이 v0.3 반영(11-25)보다 앞이라, 내용이 I/F 목록 위쪽 표에 이미 들어가 있습니다.

### 4.3 01·22·24번만 개별 v0.3 페이지가 없음 (C-03)

- I/F 목록 위쪽 표에서 01·22·24번은 통합 정의서의 절로, 나머지 41개는 개별 v0.3 페이지로 연결됩니다.
- 하위에 있는 세 번호의 개별 페이지는 v0.2입니다.
- `01) WEB-01 방문 접수 v0.2`는 경로가 `POST /visits`이고 `RegisterVisit`·`GuideGuest`를 언급합니다. v0.3은 `POST /api/visits`, `CheckIn`입니다.
- `22) … v0.2`와 `24) … v0.2`의 본문은 v0.3과 같은 현행 이름(`/fms/traffic_grant`, `NavigateRoute`, `ArmJob`)이지만, 본문에 `RequestPassage`·`GuideGuest`·`ServeFood`·`ReturnToCharge`·`TransferObject`가 한 번씩 남아 있습니다.

### 4.4 "v0.2 상세 이력" 링크의 대상이 이력이 아님 (C-04)

- 위치: 통합 정의서의 각 번호 절 끝에 있는 `v0.2 상세 이력` 링크 44개.
- 41개(02~21, 23, 25~44번)가 개별 v0.3 페이지로 갑니다. 그 페이지들은 2026-11-25에 통합본과 같은 내용으로 고쳐져, 이력이 아니라 현행 본문의 복제입니다.
- v0.2 페이지로 가는 것은 01·22·24번 3개뿐입니다.
- 통합 정의서 머리말은 "이전 개별 페이지는 개정 전 설계와 식별자 이력을 확인할 때 사용합니다"라고 적어, 링크 대상과 설명이 맞지 않습니다.
- 같은 내용이 통합본과 개별 페이지 41개 두 곳에 있어, 한쪽만 고치면 다시 어긋납니다.

### 4.5 참조 페이지 6개가 v0.2 설계안 그대로 (C-05)

| 페이지 | 마지막 수정(UTC) | 남아 있는 옛 내용 |
| --- | --- | --- |
| `01) ROS 2 Service 상세 정의` | 2026-11-23 14:03 | `/frybot/central/*` 5곳, `/frybot/tasks/*` 4곳, `RegisterVisit`·`SubmitOrder`·`EndVisit`·`RequestAdminOperation`·`GetViewState`·`ControlTask`·`GetExecution`·`RequestPassage`, `request_id` 6곳 |
| `02) ROS 2 Action 상세 정의` | 2026-11-23 14:19 | `GuideGuest`·`ServeFood`·`CollectDishes`·`ReturnToCharge`·`TransferObject`·`ExecuteCookingJob`·`CookStep` |
| `03) ROS 2 Topic 상세 정의` | 2026-11-23 14:19 | `ViewState` `/frybot/central/view_state`, `MobileStatus`, `DeviceEvent`, `TaskProgress` |
| `04) ROS 2 안전 Service 후보` | 2026-11-23 14:03 | `RequestEmergencyStop`·`GetSafetyState`·`AuthorizeRestart`, `request_id` |
| `05) FryBot 시나리오·상태·시퀀스별 데이터 전송 정의` | 2026-11-24 08:39 | `RegisterVisit`·`GuideGuest` 등 옛 이름 15종과 `TrafficGrant`·`NavigateRoute`·`ArmJob`이 한 페이지에 섞여 있음 |
| `FryBot API 요약 · 2차 연동시험 ROS 2 계약` | 2026-11-24 06:06 | "논리 연결 29개, 계약 정의 24개", "ROS 2 24개 정의서" 등 v0.2 집계와 옛 이름 17종 |

- 네 페이지(`01)`~`04)`)의 머리말은 "형식 제안"이라고 적지만 "이전 설계안"이라는 표시는 없습니다.
- 통합 정의서 머리말("시나리오·상태·시퀀스 참고")과 I/F 목록 상단이 `05)` 페이지를 참고 자료로 연결합니다. 현행 문서에서 옛 이름으로 넘어가게 됩니다.
- `FryBot API 요약`의 첫 줄은 "현행 I/F 정의서 순번 01~44"로 통합 정의서를 가리키지만 본문은 v0.2 집계입니다.

### 4.6 본문에 잘못 들어간 링크와 깨진 서식 (C-06)

- 통합 정의서 첫 문장: 날짜 `2026-11-24`가 `2`, `0`, `2`, `6-11-`, `24`로 쪼개져 22·24번 v0.2 페이지 링크가 걸려 있고, "API 인터페이스 설계와 개발 실무가이드의" 사이사이에 `24) 서빙 흐름 …`, `2) 인터페이스 기본 양식` 링크 글자가 끼어 있습니다.
- 통합 정의서 02번 "사용 상황" 줄: 굵은 글씨가 `**사용 **[**상**]**황**`으로 깨져 있고 `05) 시나리오…` 링크가 끼어 있습니다.
- I/F 목록 첫 문단: "상세 계약과 … 검증 조건은 … 통합 v0.3 정의서에서 볼 수 있습니다" 문장의 단어마다 `05) FryBot 시나리오·상태·시퀀스별 데이터 전송 정의` 링크 글자가 6번 끼어 있습니다.
- 개별 v0.3 페이지 41개 중 30개에 같은 현상이 있습니다: 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12, 13, 18, 21, 23, 25, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44번. 문장 중간에 `05) 시나리오…`, `02) WEB-02 방문 상태 조회`, `33) ROS2-02-T01 TaskProgress`, `40) ROS2-09-S01 RequestEmergencyStop` 같은 옛 페이지 제목이 링크로 끼어 있습니다. 21·36·37번은 `**사용**` 뒤에 주소가 그대로 노출됩니다.
- 현상이 없는 개별 페이지는 11개입니다: 14, 15, 16, 17, 19, 20, 26, 27, 28, 29, 30번.
- 통합 정의서의 "번호별 찾아보기" 목차는 44줄 중 12·24·26·34번 4줄만 링크이고 대상이 비어 있습니다(`(#)`). 나머지 40줄은 링크가 없습니다.
- 내용이 바뀐 것은 아니고, 자동 편집이 남긴 흔적으로 보입니다(추정). 화면에서 어떻게 보이는지는 확인 필요입니다.

### 4.7 통합 정의서 안에서 서로 다른 표기 (C-07)

| 번호 | 한쪽 | 다른 쪽 |
| --- | --- | --- |
| 18 ↔ 31 | 18번이 "31 ViewState"로 참조 | 31번은 타입 이름 없이 `std_msgs/msg/String`의 `/frybot/state` |
| 31 | "데이터 구조는 31번 상세에서 지정한다" | 31번 자기 자신을 가리킴 |
| 07 ↔ 17·35 | 웹 `kind`: `E_STOP`, `SET_TABLE_STATUS`, `INCIDENT_RETRY`, `INCIDENT_STOP`, `ACK_ALARM` | 17번 예시 `SET_TABLE`, 20·35번 `ESTOP`·`RETRY_TASK`·`REASSIGN`·`CANCEL_TASK`. 웹 `kind`와 ROS `command` 사이의 대응 표 없음 |
| 01·02·04 ↔ 14·19·23 ↔ 38 | 웹 `visit_id`: string | ROS `visit_id`: int64, AI 결과 `visit_id`: integer ≥ 1 |
| 04 ↔ 15 | 웹 `order_id`: string | ROS `order_id`: int64 |
| 01 ↔ 14 | 웹 응답에 `WAITING`과 `queue_no`(대기 접수) | `CheckIn` 응답은 `accepted`, `visit_id`, `table_id`, `message`뿐이라 대기 순번을 실을 필드가 없음 |
| 01·04·05·07 ↔ 14~17, 19 | 웹 입력에 `request_key`(필수) | ROS 요청에 대응 필드 없음. 15번은 "ROS에는 멱등 키 필드가 없다", 19번은 "현재 Jazzy IDL에는 request_id가 없다"고 적음 |
| 10 ↔ 17 | 테이블 상태 `AVAILABLE`/`ASSIGNED`/`IN_USE`/`CLEANING` | 17번 예시는 `CLOSED` |
| 23 | 적용 상태 "통합"(별도 I/F 없음) | `GuestTrack` 메시지와 `/frybot/guest_track` 토픽을 이 번호에서만 정의 |
| 13 | "WebSocket 연결 0회" | I/F 목록 아래쪽 표는 WebSocket 1채널(4.1절) |

### 4.8 통합 정의서의 빈 칸과 미완성 표 (C-08)

- 02번, 05번 입력 표에 `| undefined | object | 선택 | 전달 위치: undefined |` 행이 있습니다. 경로의 `visit_id`가 들어갈 자리로 보입니다(추정).
- 05번 입력 표의 둘째 행은 필드 이름 자리에 "JSON 요청"이 적혀 있고 실제 필드(예: `request_key`)가 없습니다.
- 오류 응답 본문이 "없음"이고 처리 결과 칸이 빈 행: 02번 1개(404), 04번 3개(400, 409, 503), 05번 2개(409, 503). 01번은 같은 종류의 오류에 `Error` 본문과 코드 이름을 적고 있어 서술 수준이 다릅니다.
- 출력 표의 "의미·사용 규칙" 칸에 설명 대신 "HTTP 200", "HTTP 201", "JSON 요청"만 적힌 필드가 있습니다. 예: 01번 `queue_no`, 02번 `queue_no`·`guide`·`orders`, 06번 `server_time`·`robots`·`tables`·`version`, 07번 `kind`·`target_id`·`params`·`request_key`, 08번 `message`, 09번 `ok`.
- 02번의 `GuideProgress`, `Order`, 06번의 `RobotView`, `AdminTable`, `AdminOrder`, `AdminTask`, `Alarm`은 타입 이름만 있고 필드 정의가 없습니다.
- 26번 표의 일부 설명이 영어 원문 그대로입니다(`Whether to use the dock_id or dock_pose fields` 등).

### 4.9 정의서가 "코드 기준"이라고 적었지만 지금 코드와 다른 곳 (C-09)

통합 정의서 머리말은 "로컬 소스와 IDL을 대조했다"고 적습니다. 아래는 그 서술이 2026-11-26 현재 `jazzy-port` 작업 트리와 다른 곳입니다. 어느 쪽을 고칠지는 사용자 결정 사항이며, 여기서는 차이만 적습니다.

| 번호 | 정의서 | 지금 코드 | 비고 |
| --- | --- | --- | --- |
| 14 | `CheckIn` `/frybot/check_in` | `RegisterVisit` `/frybot/central/register_visit` | 2026-11-25에 코드를 v0.2 이름으로 바꿈. 필드는 같음 |
| 15 | `PlaceOrder` `/frybot/place_order` | `SubmitOrder` `/frybot/central/submit_order` | 위와 같음 |
| 16 | `EndUse` `/frybot/end_use` | `EndVisit` `/frybot/central/end_visit` | 위와 같음 |
| 17 | `AdminCommand` `/frybot/admin` | `RequestAdminOperation` `/frybot/central/request_admin_operation` | 위와 같음 |
| 19 | `/fms/submit_task` | `/frybot/tasks/submit` | 위와 같음 |
| 20 | `FleetCommand` `/fms/command` | `ControlTask` `/frybot/tasks/control` | 위와 같음 |
| 31 | `/frybot/state` | `/frybot/central/view_state` | 위와 같음 |
| 32 | `TaskEvent` `/fms/task_events` | `TaskProgress` `/frybot/tasks/progress` | 위와 같음 |
| 33 | "2초 넘게 미수신 시 신규 통행 허가를 내리지 않는다" | 1초(`fleet_core.py`, 2026-11-24에 2.0 → 1.0) | 정의서 값이 변경 전 값 |
| 35 | "코드의 AMR 통신 감시 기본값은 2초다" | `fms_timeout` 기본 1.0(`mobile_controller.py`) | 위와 같음. `22) … v0.2` 페이지에도 "코드 기본 2초" |
| 38 | `GUEST_TRACK`의 `visit_id` 필수 | `guest_tracker`는 보내지 않고 `central_control`이 채움 | |
| 39 | UDP :9100, 24 B 헤더, 분할 JPEG, 10 fps | 대역은 UDP :9100 JSON, 실물 Pinky는 TCP :8554 MJPEG 15 fps | 정의서도 "설계" 상태 |
| 01~10 | `/api/visits/{visit_id}/status`, `/api/menu`, `/api/visits/{visit_id}/end`, `/api/admin/overview`, `/api/admin/operations/{operation_id}`, `/api/health`, `/api/tables`, `request_key` | 없음(`GET /api/state` 하나, 종료는 `POST /api/end_use`) | 정의서도 "설계" 상태 |

- 사용자 방향(2026-11-26): 코드를 정의서에 맞춥니다. 다만 33·35번의 2초는 코드가 안전 쪽으로 줄인 값이라, 정의서를 1초로 고치는 쪽을 제안했습니다(미결).
- I/F 목록 아래쪽 표(C-01)는 14~17, 19, 20, 31, 32번에서 지금 코드와 같은 이름입니다. 통합 정의서와 반대입니다.

## 5. 작성자에게 전달할 정리 항목

| 번호 | 정리할 것 | 관련 |
| --- | --- | --- |
| 1 | I/F 목록 아래쪽 표를 "이전 목록"으로 명시하거나 v0.3 이름·건수로 바꾸기 | C-01 |
| 2 | 정정 페이지를 내리거나 "v0.3에 반영됨"으로 표시하기 | C-02 |
| 3 | 01·22·24번 개별 페이지를 v0.3으로 맞추거나 링크 방식을 나머지 41개와 통일하기 | C-03 |
| 4 | "v0.2 상세 이력" 링크 대상과 머리말 설명 맞추기, 통합본과 개별 페이지 중 원본 하나 정하기 | C-04 |
| 5 | 참조 페이지 6개에 "이전 설계안" 표시 넣기, 현행 문서의 `05)` 링크 재검토 | C-05 |
| 6 | 본문에 끼어든 링크와 깨진 굵은 글씨, 빈 목차 링크 정리 | C-06 |
| 7 | 웹 `kind` ↔ ROS `command` 대응, `visit_id`·`order_id` 타입, 대기 접수 전달 방법, `request_key` 처리 위치 확정 | C-07 |
| 8 | 02·05번 `undefined` 행, 오류 응답 본문, 이름만 있는 타입의 필드 채우기 | C-08 |
| 9 | 33·35번의 2초와 14~17, 19, 20, 31, 32번 이름을 코드와 어느 쪽에 맞출지 확정 | C-09 |

## 6. 최종 판 재확인 (2026-11-26 16:16 조회)

1~5장은 오전 판(I/F 목록 판 25 이전, 통합 정의서 판 11) 기준입니다. 같은 날 15:35에 I/F 목록이 판 26으로 바뀌었고, 사용자가 이 판과 그 아래 개별 v0.3 정의서를 **최종 기준**으로 정했습니다(2026-11-26). 아래는 그 판을 다시 읽은 결과입니다. Confluence는 조회만 했습니다.

### 6.1 바뀐 구조

- I/F 목록(24641549)은 "FryBot I/F v0.3 현행 목록" 표 하나(41행, 8열)만 있습니다. 아래쪽 v0.2 표는 없어졌습니다.
- 통합 정의서(25690124)는 조회되지 않습니다(404). 삭제인지 이동인지는 확인하지 못했습니다.
- 개별 v0.3 정의서 44개(01~44)가 I/F 목록 바로 아래에 있습니다. 01·22·24번도 v0.3 페이지가 있습니다(25690148, 25788458, 25755717).

### 6.2 1~5장 문제의 상태

| 번호 | 오전 판의 문제 | 최종 판 |
| --- | --- | --- |
| C-01 | I/F 목록 아래쪽 표가 v0.2 그대로 | 해소(표가 없어짐) |
| C-02 | 정정 페이지가 구조와 불일치 | 다시 보지 않음(확인 필요) |
| C-03 | 01·22·24번만 개별 v0.3 페이지 없음 | 페이지는 생김. 대신 I/F 목록 표에 01·22·24번 **행이 없음** |
| C-04 | "v0.2 상세 이력" 링크가 현행 복제본으로 감 | 해소(41행 모두 "v0.3 정의서" 링크 하나, 전부 열림) |
| C-05 | 참조 페이지 6개가 v0.2 설계안 | 다시 보지 않음(확인 필요). 26771458은 조회되지 않음(404) |
| C-06 | 본문에 끼어든 링크·깨진 굵은 글씨 | 44개 중 42개 해소. 01번(페이지 만들기 링크 9개)과 22번(주소가 링크 5개로 쪼개짐, "사용 상황" 문장에 옛 페이지 제목이 섞임)은 남음 |
| C-07 | 통합 정의서 내부 표기 차이 | 18번: 목록은 `31 ViewState`, 개별 페이지는 `31 업무 상태 발행 · /frybot/state`. 07번 `kind`(E_STOP·SET_TABLE_STATUS)와 17·20번(ESTOP·SET_TABLE)의 차이는 07번 본문에 대응 규칙으로 설명됨. 나머지는 필드 단위로 다시 대조하지 않음 |
| C-08 | 빈 칸 | 다시 대조하지 않음(확인 필요) |
| C-09 | 코드와 다른 곳 | 아래 6.3 |

그 밖에 I/F 목록의 "진행상태" 열은 41행 모두 "—"입니다.

### 6.3 최종 판과 코드의 차이

"구현" 표시 항목(14~17, 19, 20, 22, 24, 26~35) 가운데:

| 번호 | 최종 v0.3 | 코드 | 종류 |
| --- | --- | --- | --- |
| 14 | `CheckIn`, `/frybot/check_in` | `RegisterVisit`, `/frybot/central/register_visit` | 이름 |
| 15 | `PlaceOrder`, `/frybot/place_order` | `SubmitOrder`, `/frybot/central/submit_order` | 이름 |
| 16 | `EndUse`, `/frybot/end_use` | `EndVisit`, `/frybot/central/end_visit` | 이름 |
| 17 | `AdminCommand`, `/frybot/admin` | `RequestAdminOperation`, `/frybot/central/request_admin_operation` | 이름 |
| 19 | `/fms/submit_task` | `/frybot/tasks/submit` | 주소 |
| 20 | `FleetCommand`, `/fms/command` | `ControlTask`, `/frybot/tasks/control` | 이름 |
| 31 | `/frybot/state` | `/frybot/central/view_state` | 이름 |
| 32 | `TaskEvent`, `/fms/task_events` | `TaskProgress`, `/frybot/tasks/progress` | 이름 |
| 33 | 2초 넘게 끊기면 새 허가 없음 | 1초 | 값 |
| 35 | AMR 통신 감시 2초 | `fms_timeout` 1.0초 | 값 |

- 8건 모두 필드는 정의서와 같습니다(14·15·16·17·19·20·32번을 소스 정의와 대조).
- 22·24·27·28·34번은 이름·필드·주기가 같습니다. 26번은 타입이 같고 정의서 설명은 "마커 도크"만 다룹니다. 29·30번은 주소만 확인했습니다.
- 33·35번 본문은 "확인한 작업 트리의 기준은 2초다. 실제 배포 설정은 연동 시험에서 확인한다"고 적고 있습니다. 코드는 2026-11-24에 1초로 줄였습니다.
- "설계" 표시 항목(웹 01~10, 38, 39)과 코드의 차이는 1~5장의 C-09와 같으며 이번에 다시 대조하지 않았습니다.

### 6.4 조치

- 이름 8건: 코드를 최종 v0.3 이름으로 되돌리는 것이 기획 방향입니다. 실행은 하지 않았습니다(사용자 결정 2026-11-26: 지금은 기획만). 코드는 11-25 이름 그대로입니다.
- 33·35번의 2초: 코드의 1초를 유지하고 정의서 수정을 요청하기로 결정(사용자, 2026-11-26). 요청문은 7.5절.
- "설계" 항목: 사용자 결정 대기.

## 7. 최종 판 ↔ 지금 코드 전체 비교와 수정 영향 (2026-11-26 16:25 조회, 기획만)

개별 v0.3 정의서 44개를 모두 다시 읽고 지금 코드(소스 정의, 노드 코드)와 대조했습니다. 코드는 고치지 않았습니다. 판정 기준은 사용자 기준대로 "정의서에 있는 것이 코드에 없거나 다르면 차이, 코드에만 더 있는 것은 차이가 아님"입니다.

### 7.1 번호별 비교

| 번호 | 적용 상태 | 최종 v0.3 | 지금 코드 | 판정 |
| --- | --- | --- | --- | --- |
| 01 | 설계 | `POST /api/visits`, 입력 `party_size`·`request_key`, 출력 `visit_id`(string)·`status`·`table_id`·`queue_no`, 201/409/422/503 | 경로 같음. 입력 `party_size`만, 출력 `ok`·`visit_id`(정수)·`table_id`·`message`, 200 | 경로 일치, 필드·응답 코드 다름 |
| 02 | 설계 | `GET /api/visits/{visit_id}/status` | 없음(`GET /api/state`로 전체 상태) | 없음 |
| 03 | 설계 | `GET /api/menu` | 없음(메뉴는 `/api/state` 안) | 없음 |
| 04 | 설계 | `POST /api/orders`, 입력 `visit_id`·`table_id`·`items`·`request_key`, 출력 `order_id`(string)·`status` | 경로 같음. 입력 `table_id`·`items`, 출력 `ok`·`order_id`(정수)·`message` | 경로 일치, 필드 다름 |
| 05 | 설계 | `POST /api/visits/{visit_id}/end`, 입력 `request_key`, 출력 `result`·`collect_required` | `POST /api/end_use`, 입력 `table_id`·`source`, 출력 `ok`·`message` | 경로·필드 다름 |
| 06 | 설계 | `GET /api/admin/overview` | 없음(`/api/state`) | 없음 |
| 07 | 설계 | `POST /api/admin/operations`, 입력 `kind`·`target_id`·`params`·`request_key`, 출력 `operation_id`·`result`·`reason` | 경로 같음. 입력 `command`·`target`·`arg`, 출력 `ok`·`message` | 경로 일치, 필드 다름 |
| 08 | 설계 | `GET /api/admin/operations/{operation_id}` | 없음 | 없음 |
| 09 | 설계 | `GET /api/health` | 없음 | 없음 |
| 10 | 설계 | `GET /api/tables` | 없음(`/api/state`) | 없음 |
| 11 | 통합 | 06 응답 재사용, 추가 필드 없음 | — | 06에 따름 |
| 12 | 예정 | 범위 제외 | — | 해당 없음 |
| 13 | 통합 | 02·06·10 주기 조회 | 화면이 `/api/state`를 주기 조회 | 02·06·10에 따름 |
| 14 | 구현 | `CheckIn`, `/frybot/check_in` | `RegisterVisit`, `/frybot/central/register_visit` | **이름 다름**, 필드 같음 |
| 15 | 구현 | `PlaceOrder`, `/frybot/place_order` | `SubmitOrder`, `/frybot/central/submit_order` | **이름 다름**, 필드 같음 |
| 16 | 구현 | `EndUse`, `/frybot/end_use` | `EndVisit`, `/frybot/central/end_visit` | **이름 다름**, 필드 같음 |
| 17 | 구현 | `AdminCommand`, `/frybot/admin` | `RequestAdminOperation`, `/frybot/central/request_admin_operation` | **이름 다름**, 필드 같음 |
| 18 | 통합 | 31의 스냅샷 재사용 | web_service가 마지막 상태를 들고 있음 | 일치(31의 이름에 따름) |
| 19 | 구현 | `SubmitTask`, `/fms/submit_task` | `SubmitTask`, `/frybot/tasks/submit` | **주소 다름**, 필드 같음 |
| 20 | 구현 | `FleetCommand`, `/fms/command` | `ControlTask`, `/frybot/tasks/control` | **이름 다름**, 필드 같음 |
| 21 | 통합 | 22·24·32·33의 `task_id`·`plan_version` 대조 | 같은 필드로 대조 | 일치 |
| 22 | 구현 | `TrafficGrant`, `/fms/traffic_grant`, 0.5초 재발행, 깊이 100 | 같음 | 일치 |
| 23 | 통합 | 24의 GUIDE + `GuestTrack` `/frybot/guest_track`, 0.30 m·0.22 m·20초 | 같음 | 일치 |
| 24 | 구현 | `NavigateRoute` `/{pinky}/navigate_route`, `ArmJob` `/{pinky}/arm_job`, `Waypoint` | 같음 | 일치 |
| 25 | 통합 | 24 + `COLLECT_DISHES`·`RETURN_DISHES` | 같은 순서. 실물 서빙 팔 자세는 비어 있어 `NO_POSE` | 인터페이스 일치 |
| 26 | 구현 | `/{pinky}/dock_robot`, 마커 도크의 마지막 구간 | 같은 액션. 마커 없는 지도 좌표 도크에도 씀 | 일치(코드가 더 넓음) |
| 27 | 구현 | `/{pinky}/navigate_to_pose` | 같음 | 일치 |
| 28 | 구현 | `/{pinky}/serving_arm/arm_job`, 2초 뒤 `ARM_OFFLINE`, 거절 `REJECTED` | 같음 | 일치 |
| 29 | 구현 | `/frybot_arm/arm_job` | 같음 | 일치 |
| 30 | 구현 | `/cook_arm_a/arm_job`, `/cook_arm_b/arm_job` | 같음 | 일치 |
| 31 | 구현 | `/frybot/state`, 0.25초, JSON 키 `now`·`tables`·`visits`(30)·`orders`(30)·`incidents`(20)·`menu`·`run_id`·`run_dir`·`ai` | `/frybot/central/view_state`, 주기와 키 같음 | **이름 다름**, 내용 같음 |
| 32 | 구현 | `TaskEvent`, `/fms/task_events`, 깊이 100 | `TaskProgress`, `/frybot/tasks/progress` | **이름 다름**, 필드 같음 |
| 33 | 구현 | `RobotStatus` `/fleet/robot_status`, 0.1초, 깊이 50, **2초** 넘게 끊기면 새 허가 없음 | 이름·필드·주기 같음, 끊김 판정 **1초** | **값 다름** |
| 34 | 구현 | `ArmStatus` `/fleet/arm_status`, 0.5초, 깊이 20, 3초 넘으면 OFFLINE | 같음 | 일치 |
| 35 | 구현 | `FleetHeartbeat` `/fms/heartbeat`, 0.2초, AMR 통신 감시 **2초** | 이름·필드·주기 같음, `fms_timeout` **1.0초** | **값 다름** |
| 36 | 통합 | `state=E_STOP`, `error=EMERGENCY_STOP` | 같음 | 일치 |
| 37 | 통합 | `20 FleetCommand`의 RESUME | `ControlTask`의 RESUME | 20의 이름에 따름 |
| 38 | 설계 | `POST :8100/ai/result`, `kind` 세 가지, 200/400, `GUEST_TRACK`에 `visit_id` 필수, 운영 영상 필드(`stream_id`·`frame_id`·`capture_time_ms`) | 경로·`kind`·200/400 같음. `guest_tracker`는 `visit_id`를 보내지 않고 관제가 채움. 운영 영상 필드 없음 | 경로 일치, 필드 일부 다름 |
| 39 | 설계 | `UDP :9100`, 24 B 헤더(`FBY2`) + JPEG 조각 | UDP :9100에는 JSON 대역, 실제 영상은 TCP :8554 MJPEG | 방식 다름 |
| 40~42 | 내부 | 범위 제외 | — | 해당 없음 |
| 43 | 통합 | 33·34의 `LOCALIZING`·`SELF_CHECK_ERROR` | 같음 | 일치 |
| 44 | 통합 | 21 기준 재조회, 별도 호출 없음 | 같음 | 일치 |

묶으면 세 가지입니다.

| 묶음 | 번호 | 차이 |
| --- | --- | --- |
| 가. "구현" 항목의 이름 | 14, 15, 16, 17, 19, 20, 31, 32 (37은 20에 따름) | 이름만 다르고 필드·주기·QoS는 같음 |
| 나. "구현" 항목의 값 | 33, 35 | 통신 감시 2초 ↔ 1초 |
| 다. "설계" 항목 | 01~10, 38, 39 | 01·04·07은 경로만 같고 필드가 다름. 02·03·06·08·09·10은 코드에 없음. 05는 경로도 다름. 39는 방식이 다름 |

필드 대조는 14~17·19·20·22·24·28·32~35를 소스 정의와 한 줄씩, 31은 JSON 키와 주기까지 했습니다. 23·25~27·29·30·34·36·43·44는 이름·주소와 정의서에 적힌 수치만 대조했습니다.

### 7.2 Confluence 문서 재검토 (최종 판 자체의 문제)

| # | 문제 | 내용 |
| --- | --- | --- |
| R-1 | I/F 목록에 01·22·24번 행이 없음 | 개별 페이지는 있음. 21·23·25번 행이 22·24를 참조함 |
| R-2 | 01·22번 본문이 깨져 있음 | 01: 페이지 만들기 링크 9개가 "사용 상황" 문장 사이에 끼어 있음. 22: 주소 `/fms/traffic_grant`가 링크 5개로 쪼개지고 본문에 옛 페이지 제목(`23) ROS2-03-A01 GuideGuest` 등)이 섞임 |
| R-3 | 18번 표기 | 목록 `31 ViewState`, 개별 페이지 `31 업무 상태 발행 · /frybot/state`. `ViewState`라는 이름은 31번에 없음 |
| R-4 | 코드 설명이 11-25 이전 코드 기준 | 01번 "ROS 데모 `/api/checkin`", 07번 "현재 ROS 데모 `/api/admin`": 지금 코드는 `/api/visits`, `/api/admin/operations`(정의서의 01·07 경로와 같음). 33·35번 "확인한 reorganize/frybot-repository 작업 트리의 기준은 2초": 지금 코드는 1초 |
| R-5 | 테이블 상태 값이 번호마다 다름 | 10번 상태는 `AVAILABLE`·`ASSIGNED`·`IN_USE`·`CLEANING`. 07번은 "웹에서 허용하는 상태는 10을 따른다"고 하는데 17번 예시는 `SET_TABLE`의 `CLOSED`. 10번에 `CLOSED`가 없어 웹으로는 테이블 닫기를 표현할 수 없음 |
| R-6 | 뜻 칸에 설명 대신 "HTTP 200"·"JSON 요청" | 02(`queue_no`·`guide`·`orders`), 04(`request_key`), 06(`server_time`·`robots`·`tables`·`version`), 07(입력 네 개), 08(`message`), 09(두 개), 10(`seats`) |
| R-7 | 이름만 있고 정의가 없는 타입 | `GuideProgress`, `Order`, `RobotView`, `AdminTable`, `AdminOrder`, `AdminTask`, `Alarm`, `TableId`, `Error`, `Health` |
| R-8 | 23번은 "통합"인데 자기 토픽을 정의 | `/frybot/guest_track`과 `GuestTrack` 필드·QoS가 23번에 있고 I/F 목록에는 별도 행이 없음 |
| R-9 | 39번과 대역의 포트 | "UDP 포트는 실제 영상 프로파일 전용, JSON 대역은 별도 테스트 환경에서만"이라고 적었는데 대역도 같은 9100번을 씀 |
| R-10 | 28번 `job` 값 목록 없음 | "실행할 팔 동작"으로만 적혀 있어 `HOME`과 앞으로 넣을 값이 정의서에 근거가 없음 |
| R-11 | "진행상태" 열 | 41행 모두 "—" |

오전 판에서 문제였다가 설명이 붙어 해소된 것: 웹 `kind`와 ROS `command`의 대응(07번 본문), 웹 식별자 string과 ROS int64(02·04번의 변환 규칙), 대기 접수와 `queue_no`(01번: 웹 서비스가 관리하고 CheckIn 응답에서 유추하지 않음), `request_key` 소유(웹 서비스).

### 7.3 지금 코드를 고치면 생기는 문제

**가. 이름 8건을 되돌릴 때**

| # | 문제 | 근거 |
| --- | --- | --- |
| 1 | 11-25 변경을 통째로 되돌릴 수 없음 | 11-25에는 ROS 이름과 함께 HTTP 경로(`/api/checkin` → `/api/visits` 등)도 바꿨고, 이 HTTP 경로는 최종 v0.3과 같음. ROS 이름만 골라 되돌려야 함 |
| 2 | 되돌릴 기준 커밋이 없음 | 마지막 커밋 `4ab5d33` 뒤로 223개 파일이 미커밋. 실패했을 때 `git checkout`으로 돌아갈 수 없음(금지 명령이기도 함). 시작 전에 사용자가 커밋해 두는 것이 안전 |
| 3 | 고칠 곳이 넓음 | 코드 16개 파일 119곳(`web_service_node` 29, `central_control_node` 28, `task_manager_node` 13, `fleet_core` 8, `restaurant` 7, 인터페이스 정의 6개 파일 이름 변경과 CMakeLists). 문서 13개 파일 193곳(`INTERFACES.md` 36, `src/frybot/README.md` 14, `COMMANDS.md` 3) |
| 4 | 11-25 검증이 무효가 됨 | 빌드·pytest·경량 시뮬 임무 10건 완료·HTTP 확인(`archive/sim_runs_2026-11-25/`)을 새 이름으로 다시 해야 함 |
| 5 | 로봇 세 대와 팔 Pi 재배포 | `--deploy`는 `frybot_interfaces`와 `frybot_control`도 로봇에 복사·빌드함. 8건은 관제 PC 안의 통신이라 배포하지 않아도 통신은 되지만, 2차 시험의 "모든 기기 같은 빌드" 조건을 맞추려면 세 대 재빌드와 팔 Pi 수동 복사가 필요. `--check`는 `FleetHeartbeat`만 보므로 이 차이를 잡지 못함 |
| 6 | 다른 작업과 같은 파일을 건드림 | 2차 시험 준비(서빙 팔 OPEN·CLOSE, 새 지도)가 `src/frybot/README.md`·`COMMANDS.md`를, 다른 세션이 같은 작업 공간에서 작업 중. 한꺼번에 하면 실패 원인을 가르기 어려움 |
| 7 | 과거 문서와 어긋남 | `2026-11-25_IF_V02_*.md` 네 개와 `README`의 "v0.2를 따릅니다"가 틀린 말이 됨. 오늘 실기기 기록(HW 마무리 T3 등)은 11-25 이름으로 남아 있음 |

참고로 이로운 점: 팀 공유 저장소(`~/roscamp-repo-1`, GitHub `addinedu-roscamp-16th/roscamp-repo-1`)의 `frybot`은 지금도 v0.3 이름(`CheckIn`, `AdminCommand`, `TaskEvent`, `/fms/submit_task`)입니다. 되돌리면 그쪽과의 차이가 줄어듭니다. 실행 분석 도구(`analyze_run`, `runs/` 안의 스크립트)는 토픽 이름을 쓰지 않아 영향이 없습니다.

**나. 33·35번을 2초로 맞출 때**

- 관제가 끊긴 로봇에 허가를 계속 내는 시간과 로봇이 관제 없이 가는 시간이 1초 → 2초로 늘어납니다(0.08 m/s에서 8 cm → 16 cm). 안전 쪽으로는 후퇴입니다.
- 프로젝트 정량 목표 5번("1초 넘는 상태 보고 끊김 0건, 1초는 허가 중단·정지 기준")과 HW 검증 보고서의 전제가 1초입니다. 2초로 바꾸면 그 문서들도 고쳐야 합니다.
- 정의서 본문은 "확인한 작업 트리의 값"을 옮겨 적은 것이고 "실제 배포 설정은 연동 시험에서 확인한다"고 덧붙였습니다. 기획 의견은 코드 1초를 유지하고 정의서의 숫자를 고쳐 달라고 요청하는 것입니다.

**다. "설계" 항목(01~10, 38, 39)을 맞출 때**

- 지금 화면(`admin.html`, `reception.html`, `table.html`, 손님 시뮬레이터)은 `/api/state`와 `ok`·정수 ID 응답을 씁니다. 응답 모양을 정의서대로 바꾸면 화면이 함께 깨지므로 화면도 고치거나 옛 응답을 함께 유지해야 합니다.
- `request_key` 중복 처리, `operation_id` 발급과 결과 조회, 대기 순번(`queue_no`)은 web_service가 상태를 가져야 합니다. 지금 web_service는 업무 상태를 갖지 않는 구조입니다.
- 새 GET 여섯 개(02·03·06·08·09·10)와 05의 새 경로가 필요합니다. 타입 정의가 정의서에 없어(R-7) 그대로는 구현할 수 없습니다.
- 39번을 UDP로 바꾸면 실기기에서 확인한 손님 추적 영상 경로(TCP :8554)를 다시 만들고 다시 검증해야 합니다.
- 작업량과 검증 범위가 커서 2차 시험(일정표상 11-27) 전에 하면 시험 대상이 시험 직전에 크게 바뀝니다.

### 7.4 기획 의견 (결정 전)

1. 가 묶음(이름 8건)만 먼저 한다. 시작 전에 지금 상태를 커밋해 되돌릴 기준을 만든다.
2. 순서는 이름 8건 → 서빙 팔 OPEN·CLOSE → 새 지도 순으로 하나씩 끝내고, 배포는 세 가지가 끝난 뒤 한 번에 한다.
3. 나 묶음은 코드를 유지하고 정의서 수정을 요청한다.
4. 다 묶음은 2차 시험 뒤로 미루고, 그 전에 R-5·R-6·R-7을 정의서에서 채워 달라고 요청한다.

### 7.5 결정과 정의서 수정 요청 (2026-11-26)

**결정(사용자, 2026-11-26):** 33·35번의 통신 감시 시간은 코드의 1초를 유지하고, 정의서를 1초로 고쳐 달라고 요청한다. 7.4절 기획 의견 3번이 확정된 것이다. Confluence는 이쪽에서 고치지 않는다.

작성자에게 전달할 내용:

| 페이지 | 지금 문장 | 요청하는 문장 |
| --- | --- | --- |
| 33) AMR 운용 상태 v0.3 (25657554), "통신 경로와 호출 조건" | 2초 넘게 미수신 시 신규 통행 허가를 내리지 않는다. | 1초 넘게 미수신 시 신규 통행 허가를 내리지 않는다. |
| 같은 페이지, "실패·복구" | 2초 넘게 보고가 없으면 관제는 신규 통행 허가를 내지 않는다. | 1초 넘게 보고가 없으면 관제는 신규 통행 허가를 내지 않는다. |
| 같은 페이지, "시간 기준 확인" | 확인한 reorganize/frybot-repository 작업 트리의 Fleet 보고 단절 기준은 2초다. | 현행 코드의 Fleet 보고 단절 기준은 1초다(2026-11-24에 2초에서 변경, `fleet_core.py`). |
| 35) 정지 요청 전달 v0.3 (26017906), "통신 경로와 호출 조건" | 코드의 AMR 통신 감시 기본값은 2초다. | 코드의 AMR 통신 감시 기본값은 1초다. |
| 같은 페이지, "시간 기준 확인" | 확인한 reorganize/frybot-repository 작업 트리의 AMR fms_timeout 기본값은 2.0초다. | 현행 코드의 AMR `fms_timeout` 기본값은 1.0초다(2026-11-24에 2.0초에서 변경, `mobile_controller.py`). |

근거로 함께 전달할 것:

- 코드는 2026-11-24에 관제의 끊김 판정과 로봇의 `fms_timeout`을 같은 1초로 맞췄다.
- 프로젝트 정량 목표 5번(30분 운전 중 1초 넘는 상태 보고 끊김 0건)이 "1초는 허가 중단·정지 기준"을 근거로 한다.
- 2초로 두면 관제 신호가 끊긴 로봇이 0.08 m/s에서 약 16 cm(계산값)를 더 갈 수 있고, 이는 로봇 간 최소 중심 거리 기준 15.5 cm와 같은 크기다.

**반영 확인(2026-11-26 16:37 조회):** 33번(25657554)과 35번(26017906)이 모두 판 9로 바뀌었고, 위 표의 다섯 문장이 모두 1초(1.0초)로 고쳐져 있습니다. "시간 기준 확인" 문단은 "확인한 reorganize/frybot-repository 작업 트리의 … 기준은 1초다"로 숫자만 바뀌었습니다. 이로써 7.1절의 33·35번 "값 다름"은 해소되어 "구현" 항목의 차이는 이름 8건만 남습니다. I/F 목록(24641549)도 판 27이 되었는데, 무엇이 바뀌었는지는 확인하지 않았습니다.

### 7.6 I/F 목록에 01·22·24번 행 추가 (2026-11-26 16:46, 사용자 요청으로 Confluence 수정)

R-1(I/F 목록 표에 01·22·24번 행이 없음)을 사용자 요청에 따라 고쳤습니다. I/F 목록(24641549)이 판 27 → 28이 되었고, 변경 메모는 "I/F 목록에 빠진 01·22·24번 행 추가"입니다.

- 방법: 표 전체를 다시 쓰지 않고 행 세 개만 끼워 넣음(01은 02 앞, 22는 21 뒤, 24는 23 뒤). 기존 41행은 원본 그대로임을 게시 전 미리보기와 게시 뒤 재조회로 확인.
- 넣은 내용은 각 개별 v0.3 정의서의 통신 경로, 입력 필드, "결과 처리" 문장, 호출 조건에서 옮김.

| 번호 | 통신 방식 | I/F | 입력 | 빈도 | 작업자 |
| --- | --- | --- | --- | --- | --- |
| 01 | HTTP | 방문 접수 `POST /api/visits` | party_size, request_key | 사용자 제출 1회 · 자동 재호출 0회 | — (비워 둠) |
| 22 | ROS 2 Topic | 통행 허가 `/fms/traffic_grant` | robot_id, task_id, plan_version, granted_index | 허가 변경 때 1회 · 활성 경로마다 0.5초에 1회 재발행 | Juheon Lee |
| 24 | ROS 2 Action | AMR 경로·서빙 `/{pinky}/navigate_route · /{pinky}/arm_job` | NavigateRoute·ArmJob 목표 필드 | 경로 버전당 goal 1회 · 팔 동작당 goal 1회 | Juheon Lee |

- 재조회 결과: 표 44행, 번호 01~44가 순서대로 있고 빠진 번호 없음.
- 작업자: 22·24번은 다른 ROS 2 AMR 행과 같게 넣었고(기획 판단), 01번은 처음에 "—"로 두었다가 사용자 지시로 동욱황·남현우 멘션을 넣었습니다(16:53, 판 29, 02번 행과 같은 형식).
- 고치지 않은 것: 01·22번 개별 페이지의 깨진 본문(R-2), 18번 표기(R-3) 등 나머지 R 항목.

### 7.7 01·22번 개별 페이지의 깨진 본문 수정 (2026-11-26 16:54~16:55, 사용자 요청으로 Confluence 수정)

R-2를 사용자 요청에 따라 고쳤습니다. 문장 내용은 바꾸지 않고 끼어든 링크와 쪼개진 굵은 글씨만 걷어 냈습니다.

| 페이지 | 판 | 고친 문단 | 결과(재조회) |
| --- | --- | --- | --- |
| 01) 방문 접수 v0.3 (25690148) | 7 → 8 | "사용 상황" 한 문단 | 링크 0개. "손님이 입구 키오스크에서 인원수를 입력하고 접수 버튼을 누릅니다." 표 부분은 수정 전과 같음 |
| 22) 통행 허가 v0.3 (25788458) | 7 → 12 | "사용 상황", 주소 `/fms/traffic_grant`, 호출 조건 세 문단 | 세 문단은 깨끗해짐. 필드 표의 `robot_id` 칸에 링크 조각 2개(글자 "r", "t_"가 System Architecture 페이지로 연결)가 남음 |

22번에서 있었던 일(그대로 기록):

- 문단 단위 교체를 세 번 나눠 넣는 중 두 번째 교체가 어긋나게 적용되어, 판 9에서 "사용 상황"·"결과 처리" 문단과 "통신 경로와 호출 조건" 제목이 빠지고 필드 표 안에 링크가 끼어들었습니다(약 20초 동안).
- 수정 전에 받아 둔 판 7 원본에서 세 문단만 고친 본문으로 전체를 교체해 복구했습니다(판 10). 복구 뒤 본문은 링크를 빼고 비교하면 판 7과 표까지 같고, 세 문단만 의도대로 바뀌었습니다.
- `robot_id` 칸의 링크 조각 2개는 링크 없는 본문을 두 번 더 저장해도(판 11·12) 다시 붙었습니다. 저장할 때 Confluence 쪽에서 붙는 것으로 보이며 이 도구로는 지우지 못했습니다(원인 확인 필요). 편집 화면에서 그 칸의 링크를 직접 지워야 합니다.
- 이 때문에 22번의 판 번호가 다섯 번 올라갔습니다.

## 8. 재확인 (2026-11-27 02:04 조회, 전체 01~44)

7.5~7.7절의 Confluence 수정과 코드의 이름 되돌리기(2026-11-26, `src/frybot/README.md` 인터페이스 절)가 끝난 뒤 상태를 확인하려고 I/F 목록과 개별 v0.3 정의서 44개를 다시 조회해 지금 코드와 대조했습니다. Confluence는 조회만 했습니다. 코드는 소스(인터페이스 정의, 노드 코드)를 읽어 대조했고 실행으로 확인하지는 않았습니다(실행 확인은 사용자가 `ros2` 명령으로 직접 진행 예정).

### 8.1 조회한 판

| 페이지 | 판 | 마지막 수정(UTC) | 7장 뒤 바뀐 것 |
| --- | --- | --- | --- |
| I/F 목록(24641549) | 30 | 2026-11-26 07:58 | 44행(01~44)이 모두 있음(7.6절 반영) |
| 01) 방문 접수 (25690148) | 8 | 2026-11-26 07:54 | "사용 상황"의 끼어든 링크 없음(7.7절) |
| 22) 통행 허가 (25788458) | 12 | 2026-11-26 07:55 | 세 문단 정리됨. `robot_id` 칸의 링크 조각 2개는 남음(7.7절) |
| 33) AMR 운용 상태 (25657554) | 9 | 2026-11-26 07:36 | 보고 끊김 기준 1초(7.5절) |
| 35) 정지 요청 전달 (26017906) | 9 | 2026-11-26 07:36 | AMR 통신 감시 1.0초(7.5절) |
| 나머지 39개 | 6~10 | 2026-11-25 08:49 ~ 2026-11-26 06:39 | 없음 |

### 8.2 "구현"·"통합" 항목(14~37, 43, 44) ↔ 코드

정의서와 코드가 다른 곳은 없습니다. 7.1절의 "이름 다름" 8건(14·15·16·17·19·20·31·32)은 코드가 v0.3 이름으로 돌아와 해소됐고, "값 다름" 2건(33·35)은 정의서가 1초로 고쳐져 해소됐습니다.

| 번호 | 정의서 | 코드에서 확인한 곳 | 판정 |
| --- | --- | --- | --- |
| 14~17 | `CheckIn` `/frybot/check_in`, `PlaceOrder` `/frybot/place_order`, `EndUse` `/frybot/end_use`, `AdminCommand` `/frybot/admin` | `central_control_node.py` 서비스 4개, `web_service_node.py` 클라이언트 4개, srv 필드 | 일치 |
| 18 | 31의 스냅샷 재사용 | `web_service_node.py`가 `/frybot/state` 마지막 값을 보관 | 일치 |
| 19·20 | `SubmitTask` `/fms/submit_task`, `FleetCommand` `/fms/command` | `central_control_node.py` 클라이언트, srv 필드 | 일치 |
| 21 | 22·24·32·33의 `task_id`·`plan_version` | 네 정의 모두 두 필드가 있음 | 일치 |
| 22 | `TrafficGrant` `/fms/traffic_grant`, 0.5초 재발행, 깊이 100 | `task_manager_node.py`(`QOS` 깊이 100, `_regrant` 0.5초) | 일치 |
| 23 | `GuestTrack` `/frybot/guest_track`, 깊이 10, 0.30 m·0.22 m·20초 | `mobile_controller.py`(`follow_pause_dist` 0.30, `follow_resume_dist` 0.22, `guest_timeout` 20.0) | 일치 |
| 24·25 | `NavigateRoute`·`ArmJob`·`Waypoint` 필드, LOAD·UNLOAD, COLLECT_DISHES·RETURN_DISHES | action·msg 정의, `fleet_core.py`의 임무 단계 | 일치 |
| 26 | `/{pinky}/dock_robot`, 마커 도크 마지막 구간 | `mobile_controller.py`. 지도 좌표 도크(`pose_dock`)에도 씀 | 일치(코드가 더 넓음) |
| 27 | `/{pinky}/navigate_to_pose` | `mobile_controller.py`(`drive:=nav2`일 때) | 일치 |
| 28 | `/{pinky}/serving_arm/arm_job`, 2초 뒤 `ARM_OFFLINE` | `serving_arm_wait_sec` 2.0 | 일치 |
| 29·30 | `/frybot_arm/arm_job`, `/cook_arm_a/arm_job`·`/cook_arm_b/arm_job` | `frybot_arm`의 `MASTER_ACTION`, `arm_controller.py` | 일치 |
| 31 | `/frybot/state`, 0.25초, 깊이 10, 키 `now`·`tables`·`visits`(30)·`orders`(30)·`incidents`(20)·`menu`·`run_id`·`run_dir`·`ai` | `central_control_node.py`(0.25초 타이머), `restaurant.py` `snapshot` | 일치 |
| 32 | `TaskEvent` `/fms/task_events`, 깊이 100 | `task_manager_node.py`, msg 필드 | 일치 |
| 33 | `RobotStatus` `/fleet/robot_status`, 깊이 50, 1초 넘게 끊기면 새 허가 없음 | `mobile_controller.py`(깊이 50), `fleet_core.py`(`now - robot.last_status > 1.0`) | 일치 |
| 34 | `ArmStatus` `/fleet/arm_status`, 0.5초, 깊이 20, 3초 | `arm_controller.py`(0.5초), `fleet_core.py` `_arm_report`(3.0초) | 일치 |
| 35 | `FleetHeartbeat` `/fms/heartbeat`, 0.2초, 깊이 10, 감시 1.0초 | `task_manager_node.py`(0.2초), `mobile_controller.py`(`fms_timeout` 1.0) | 일치 |
| 36·37 | `state=E_STOP`·`error=EMERGENCY_STOP`, 20의 RESUME | `mobile_controller.py`, `fleet_core.py` `command` | 일치 |
| 43·44 | `LOCALIZING`·`SELF_CHECK_ERROR`, 21 기준 대조 | `auto_localize.py`, `mobile_controller.py` | 일치 |

### 8.3 "설계" 항목(01~10, 38, 39) ↔ 코드

7.1절과 같은 상태입니다. 어디까지 맞출지는 결정 대기입니다.

| 번호 | 판정 |
| --- | --- |
| 01·04·07 | 경로(`/api/visits`, `/api/orders`, `/api/admin/operations`)만 같고 필드·응답 코드가 다름 |
| 05 | 경로도 다름(정의서 `/api/visits/{visit_id}/end`, 코드 `/api/end_use`) |
| 02·03·06·08·09·10 | 코드에 없음(`GET /api/state`로 전체 상태) |
| 38 | 경로·`kind`·200/400 같음. `GUEST_TRACK`의 `visit_id` 필수, 운영 영상 필드 3개는 코드에 없음 |
| 39 | 방식 다름(정의서 UDP :9100 24 B 헤더 + JPEG 조각, 코드는 대역 UDP JSON·실물 TCP :8554 MJPEG) |

11·13은 06·02·10에 따르고, 12·40~42는 범위 제외입니다.

### 8.4 정의서 자체에 남은 문제

| # | 위치 | 내용 | 7.2절 번호 |
| --- | --- | --- | --- |
| 1 | 22번 필드 표 | `robot_id` 칸에 System Architecture 링크 조각 2개 | R-2의 남은 부분(7.7절) |
| 2 | I/F 목록 18번 행 | `31 ViewState` 표기. 개별 페이지에는 그 이름이 없음 | R-3 |
| 3 | 01·07번 본문 | "ROS 데모 `/api/checkin`", "현재 ROS 데모 `/api/admin`". 지금 코드는 `/api/visits`, `/api/admin/operations` | R-4 |
| 4 | 33·35번 "시간 기준 확인" | 숫자는 1초로 맞지만 출처가 "reorganize/frybot-repository 작업 트리"로 남음 | R-4 |
| 5 | 10번 ↔ 17번 | 10번 상태 값에 `CLOSED`가 없는데 17번 예시는 `SET_TABLE`의 `CLOSED` | R-5 |
| 6 | 02·04·06·07·08·09·10번 | 뜻 칸에 "HTTP 200"·"JSON 요청"만 적힌 필드 | R-6 |
| 7 | 01·02·06·09·10번 | 필드 정의 없는 타입: `TableId`, `Error`, `GuideProgress`, `Order`, `RobotView`, `AdminTable`, `AdminOrder`, `AdminTask`, `Alarm`, `Health` | R-7 |
| 8 | 23번 | "통합"인데 `GuestTrack` 토픽을 이 번호에서만 정의 | R-8 |
| 9 | 39번 | "UDP 포트는 실제 영상 전용"인데 JSON 대역도 9100번 | R-9 |
| 10 | 24·28번 | `job` 값 목록 없음 | R-10 |
| 11 | I/F 목록 | "진행상태" 열이 44행 모두 "—" | R-11 |
| 12 | 26번 | 설명 일부가 영어 원문, "마커 도크"만 다룸 | C-08 |

해소된 것: R-1(목록 행 44개), R-2의 01번과 22번 세 문단.

### 8.5 남은 일

- 14~37번의 실제 연결(이름·타입·발행·구독·주기)은 경량 시뮬에서 `ros2 service list -t`, `ros2 topic info -v`, `ros2 topic hz`, `ros2 action info`로 확인 예정입니다(사용자 직접 실행, 결과 미기록). 26·27번은 `drive:=nav2`(Gazebo 또는 실기기), 28번은 `serving_arm:=real`에서만 보입니다.
- "설계" 항목의 범위 결정, 8.4절 항목의 작성자 전달.
