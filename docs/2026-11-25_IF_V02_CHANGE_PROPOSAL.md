# 통합 인터페이스 정의서 v0.2 수정 제안서: 코드 기준으로 고칠 ROS 2 항목 (2026-11-25)

> 2026-11-26에 최종 기준이 Confluence I/F v0.3 최종 판으로 바뀌어 이름 8건을 되돌림(`/frybot/check_in`, `/fms/submit_task` 등). 아래 본문은 그날의 기록입니다. 지금 이름은 [INTERFACES.md](2026-11-23_INTERFACES_OLD.md), [2026-11-26_IF_V03_NAME_REVERT_PLAN.md](2026-11-26_IF_V03_NAME_REVERT_PLAN.md) 참고.

작성: 2026-11-25, 기획 패널(Claude). [v0.2 대조와 반영 현황](2026-11-25_IF_V02_CHECK.md)과 [방향 비교](2026-11-25_IF_V02_DIRECTION.md)에서 "코드가 더 낫거나 이미 동작 중이라 Confluence를 코드에 맞추는 편이 낫다"고 본 항목만 모은 제안서입니다.

- 대상: Confluence `FryBot 통합 인터페이스 정의서 v0.2`와 그 아래 상세 정의서, `1) FryBot I/F 목록`.
- 범위: **ROS 2(서비스·액션·토픽·namespace) 항목만** 본문에 두었습니다. ROS 2 밖 항목(HTTP, 영상)은 처음 판에서 P12·P13 등으로 함께 있었으나 2026-11-25에 부록 A로 옮겼습니다. 번호는 그대로 두어 P12·P13이 본문에서 빠져 있습니다.
- 상태: **제안이며 아직 아무것도 수정하지 않았습니다.** Confluence 수정은 항목별로 사용자 승인을 받은 뒤에 합니다.
- 코드 기준: `src/frybot`(`jazzy-port`, 2026-11-25 이름 변경 반영 뒤). 아래 주소·타입·필드는 `frybot_interfaces`의 정의 파일과 각 노드의 생성 줄에서 옮긴 것입니다.
- 근거 범위: 코드 읽기와 기존 실기기·시뮬 기록입니다. 항목마다 실기기에서 확인된 범위를 적었습니다.
- 이 제안서에 없는 것: Confluence대로 코드를 고칠 항목(요청 키, 거절 구분, AI 관측 시각 등)과 보류 항목은 [방향 비교](2026-11-25_IF_V02_DIRECTION.md) 4장·5장에 있습니다.

## 1. 제안 목록

| # | 대상(현행 번호) | 제안 한 줄 | 코드 변경 |
| --- | --- | --- | --- |
| P1 | 23 고객 안내 | 전용 액션 `GuideGuest`를 빼고 `NavigateRoute`(`GUIDE`) + `GuestTrack`으로 적음 | 없음 |
| P2 | 25 퇴식 | 전용 액션 `CollectDishes`를 빼고 `NavigateRoute` + `ArmJob` 단계로 적음 | 없음 |
| P3 | 26 충전 복귀 | 전용 액션 `ReturnToCharge`를 빼고 홈 복귀 경로 + `DockRobot`으로 적음 | 없음 |
| P4 | 28 서빙 팔 | `TransferObject`를 `ArmJob` `/{pinky}/serving_arm/arm_job`으로 적음 | 없음 |
| P5 | 30 조리 팔 단계 | `CookStep`을 `ArmJob` `/cook_arm_a/arm_job`, `/cook_arm_b/arm_job`으로 적음 | 없음 |
| P6 | 33 AMR 상태 | 주소를 공용 토픽 `/fleet/robot_status`로, 필드를 코드대로 적음 | 없음 |
| P7 | 34 장치 이벤트 | 이벤트 토픽 5개 대신 주기 상태 보고(`RobotStatus.error`, `ArmStatus`)로 적음 | 팔 오류 채우기는 별도 코드 과제 |
| P8 | 35~37 안전 | 장비별 서비스 3개 대신 생존 신호 `FleetHeartbeat`의 정지 목록으로 적음 | 팔의 생존 신호 수신은 별도 코드 과제 |
| P9 | 18, 21 조회 서비스 | "별도 서비스 없음, 31번·22·24·32·33번으로 대조"로 적음 | 없음 |
| P10 | 20 임무 제어 | 받는 명령 범위(임무·로봇·설정)를 적음 | 없음 |
| P11 | 31, 32 | 31은 전체 스냅샷 JSON, 32는 `plan_version`이 시도 식별자라고 적음 | 없음 |
| P14 | 43 자체점검 | "기존 상태 보고 재사용"으로 확정 | 없음 |
| P15 | 7절 namespace | `pinky_1` → `pinky1` | 없음 |
| P16 | 번호 없는 연결 | 코드에만 있는 ROS 2 연결 8개를 추가 | 없음 |
| P17 | 문서 안 불일치 | v0.2와 I/F 목록 안에서 서로 다른 곳 6군데 정리 | 없음 |

본문은 15건(P1~P11, P14~P17)입니다. ROS 2 밖 항목은 부록 A에 있습니다.

## 2. 항목별 제안

### P1. 23 고객 안내

| | 지금 v0.2 | 제안 |
| --- | --- | --- |
| 계약 | Action `GuideGuest` `/{mobile_ns}/guide_guest` | Action `NavigateRoute` `/{pinky}/navigate_route`, `mode=GUIDE` (24번과 같은 계약) |
| Goal | `task_id`, `attempt_id`, `table_id`, `entrance_pose` | `task_id`, `robot_id`, `plan_version`, `mode`, `visit_id`, `route[]`(`node_id`, `x`, `y`, `not_before`) |
| Feedback | `phase`, `current_pose`, `guest_dist_m`, `observation_valid` | `plan_version`, `reached_index`, `state`(ACCEPTED·MOVING·PAUSED_GUEST) |
| Result | `outcome`, `reason`, `evidence_ref` | `success`, `plan_version`, `reached_index`, `reason`(OK·GUEST_LOST 등) |
| 동행 판단 | Feedback의 손님 거리 | 토픽 `/frybot/guest_track`(`GuestTrack`, Central Control → AMR). 보이지 않거나 멀어지면 대기, 시간 초과면 `GUEST_LOST` |

- 이유: 통로가 로봇 한 대 폭이라 관제가 경로를 계획하고 구간마다 통행 허가(22번)를 내야 양보·재계획·재배정을 할 수 있습니다. 안내만 로봇이 통째로 맡는 계약이면 22·24번과 구조가 갈립니다.
- 확인 범위: 경량 시뮬에서 안내 완료. 실기기 안내 주행은 확인 필요.

### P2. 25 퇴식

| | 지금 v0.2 | 제안 |
| --- | --- | --- |
| 계약 | Action `CollectDishes` `/{mobile_ns}/collect_dishes` | 24번의 두 계약을 순서대로: 테이블 경로(`NavigateRoute`) → `ArmJob` `COLLECT_DISHES` → 퇴식구 경로 → `ArmJob` `RETURN_DISHES` |
| 진행 보고 | Feedback `phase` | `TaskProgress`의 `COLLECTED`, `RETURNED` |
| 결과 | `returned_count`, `count_valid`, `evidence_ref` | 단계별 `success`, `reason`. 반납 개수는 없음 |

- 이유: P1과 같습니다. 반납 개수는 지금 셀 수단이 없어 뺐고, 수단이 생기면 `ArmJob` 결과에 더하는 후보로 남깁니다.
- 확인 범위: 경량 시뮬. 실기기 퇴식은 확인 필요.

### P3. 26 충전 복귀

| | 지금 v0.2 | 제안 |
| --- | --- | --- |
| 계약 | Action `ReturnToCharge` `/{mobile_ns}/return_to_charge` | 관제가 홈(또는 충전대) 노드까지 `NavigateRoute`를 보냄. 도크로 끝나는 마지막 구간은 AMR 안에서 `nav2_msgs/DockRobot` `/{pinky}/dock_robot` |
| 결과 | `docked_verified`, `evidence_ref` | 경로 결과 `success`. 충전 여부는 상태 보고의 `charging` |

- 이유: 복귀도 다른 로봇과 통로를 나눠 써야 해서 같은 경로·허가 계약을 씁니다.
- 확인 범위: 임무 뒤 홈 복귀는 실기기 확인(2026-11-20, T-45). 도킹은 단위 확인까지이고 실기기 확인 필요.

### P4. 28 서빙 팔 구동

| | 지금 v0.2 | 제안 |
| --- | --- | --- |
| 계약 | Action `TransferObject` `/{mobile_ns}/arm/transfer_object` | Action `ArmJob` `/{pinky}/serving_arm/arm_job`, Mobile Controller → 서빙 팔 구동부(`serving_arm_driver`) |
| Goal | `task_id`, `execution_id`, `operation`, `subject_ref` | `task_id`, `arm_id`, `job`(HOME·LOAD·UNLOAD·COLLECT_DISHES·RETURN_DISHES), `duration`, `params_json`(`table_id`, `menu`) |
| Feedback | `phase`, `holder_device_id`, `observation_ref` | `phase`, `progress` |
| Result | `outcome`, `physical_result_verified`, `reason`, `last_known_location` | `success`, `reason`(OK·CANCELED·E_STOP·ARM_OFFLINE·REJECTED·NO_POSE·ARM_TIMEOUT) |

- 이유: v0.2의 24번 상세가 이미 같은 연결을 `/{pinky}/serving_arm/arm_job`으로 "현행 구현 기준"이라고 적고 있어 28번과 서로 다릅니다. 팔은 정해 둔 자세를 순서대로 가므로 물체·위치 참조를 받지 않습니다.
- 남기는 것: `physical_result_verified`(실제로 놓였는지)는 좋은 항목입니다. 확인 수단이 정해지면 `ArmJob` 결과에 더하는 후보로 본문에 적어 둡니다.
- 확인 범위: 실물 팔은 직접 명령으로 시험했고, 이 액션을 거친 동작은 확인 필요.

### P5. 30 조리 팔 단계 실행

| | 지금 v0.2 | 제안 |
| --- | --- | --- |
| 계약 | Action `CookStep` `/frybot/cooking/arm_a/cook_step`, `arm_b` | Action `ArmJob` `/cook_arm_a/arm_job`, `/cook_arm_b/arm_job`, 조리 마스터 → 지정 팔 |
| Goal | `job_id`, `food_unit_id`, `execution_id`, `step` | `task_id`, `arm_id`, `job`(LOAD_BASKET·DROP_IN_FRYER·LIFT_DRAIN·PLATE·PLACE_HANDOFF·TO_WOK·ADD_SAUCE·ADD_INGREDIENTS·STIR_FRY), `duration`, `params_json`(`cook_task_id`, `menu`, `fry_time`) |
| Result | `outcome`, `step_verified`, `error_code`, `handoff_slot` | `success`, `reason` |

- 이유: 서빙 팔과 조리 팔이 한 타입을 쓰면 관제와 마스터의 처리 코드가 하나로 끝납니다.
- 함께 볼 것: 29번(`ExecuteCookingJob`, 작업 전체를 한 번에)은 조리 팔 구동 방식이 정해질 때까지 보류로 두고 이번 제안에 넣지 않았습니다. 29번이 지금처럼 단계 하나씩이면 주소는 `/frybot_arm/arm_job`입니다.
- 확인 범위: 조리 팔은 대역(관절 애니메이션)입니다.

### P6. 33 AMR 운용 상태

| | 지금 v0.2 | 제안 |
| --- | --- | --- |
| 주소 | 로봇마다 `/{mobile_ns}/status` | 공용 토픽 `/fleet/robot_status` 하나, `robot_id`로 구분 |
| 타입 | `MobileStatus` | `RobotStatus`(타입 이름은 v0.2대로 `MobileStatus`로 바꿀 수 있음. 로봇 재배포가 필요해 다음 배포 때로 제안) |
| 주기·QoS | 운용 5 Hz·대기 1 Hz, Best Effort / Keep Last 1 후보 | 10 Hz 고정, Reliable / Volatile / Keep Last 50. 1초 넘게 끊기면 관제가 새 통행 허가를 내지 않음 |
| 필드 | `device_id`, `state_code`, `state_valid`, `current_task_id`, `pose`, `battery_pct`, `battery_observed_at`, `battery_stale` | `stamp`, `robot_id`, `state`, `x`, `y`, `yaw`, `battery`(0~100), `charging`, `task_id`, `plan_version`, `reached_index`, `node_id`, `arm_state`, `error` |

- 이유: 구독자가 네 곳(관제, 천장 카메라 노드, RViz 표시, 기동 대기)이고 모두 전체 로봇을 보는 용도라 토픽 하나가 맞습니다. `error` 필드에 통신 끊김·비상 정지·주행 실패·위치 추정 실패가 실려 34·36·43번의 역할도 합니다.
- 남기는 것: 배터리 관측 시각과 오래됨 표시는 v0.2가 낫습니다(코드에 넣을 후보). QoS와 주기는 실기기 측정 뒤 다시 정하자는 메모를 본문에 남깁니다.
- 확인 범위: 실기기 세 대에서 써 온 토픽입니다.

### P7. 34 팔 상태·장애 보고

| | 지금 v0.2 | 제안 |
| --- | --- | --- |
| 계약 | `DeviceEvent` 공통 타입, 경로 5개(AMR → 관제, 서빙 팔 → AMR, 마스터 → 관제, 조리 팔 A·B → 마스터) | 이벤트 토픽 없음. AMR 장애는 33번의 `error`, 팔은 `ArmStatus` `/fleet/arm_status`(팔 → 관제, 2 Hz), 작업 실패는 액션 결과의 `reason` |
| 필드 | `event_id`, `device_id`, `task_id`, `attempt_id`, `execution_id`, `event_type`, `observed_at`, `error_code` | `ArmStatus`: `stamp`, `arm_id`, `state`, `job`, `task_id`, `error` |
| 조리 팔 경로 | 팔 → 마스터 → 관제 | 팔 → 관제 직접. 3초 넘게 끊기면 관제가 그 팔을 OFFLINE으로 표시 |

- 이유: 주기 보고는 한 번 유실돼도 다음 주기에 복구돼, 유실 뒤 대조 절차가 필요 없습니다. 조리 팔이 마스터를 거치지 않으면 마스터가 죽어도 팔 상태가 보입니다.
- 코드 쪽 숙제(이 제안과 별개): `ArmStatus.error`가 지금 항상 빈 값이고, 실물 서빙 팔의 끊김·오류는 작업 결과로만 전달됩니다. 본문에 "현재 한계"로 적습니다.

### P8. 35~37 정지 요청·정지 상태·재가동

| 번호 | 지금 v0.2 | 제안 |
| --- | --- | --- |
| 35 | Service `RequestEmergencyStop` `/{device_ns}/safety/request_stop` | 관리자 명령 `ESTOP`(17번 → 20번) → 토픽 `FleetHeartbeat` `/fms/heartbeat`(관제 → AMR, 5 Hz)의 `estop[]`에 로봇 이름을 유지 |
| 36 | Service `GetSafetyState` `/{device_ns}/safety/get_state` | 33번 상태 보고의 `state=E_STOP`, `error=EMERGENCY_STOP`으로 읽음. 물리 안전 회로의 확인은 범위 밖이라고 명시 |
| 37 | Service `AuthorizeRestart` `/{device_ns}/safety/authorize_restart` | 관리자 명령 `RESUME`(17번 → 20번) |

- `FleetHeartbeat` 필드: `stamp`, `session`(관제 기동마다 바뀜. 바뀌면 로봇이 옛 허가와 경로를 버림), `estop[]`.
- 이유: 생존 신호는 통신이 끊기면 로봇이 스스로 서고(기본 1초), 반복 발행이라 정지 명령이 한 번 유실돼도 0.2초 뒤 다시 갑니다. 요청·응답 서비스는 응답이 유실되면 정지됐는지 알 수 없습니다.
- 코드 쪽 숙제(별개): 서빙 팔 구동부와 조리 팔은 생존 신호를 직접 듣지 않습니다. `RESUME`에 승인자 기록이 없습니다. 본문에 "현재 한계"로 적습니다.
- 확인 범위: 비상 정지 채널과 생존 신호 끊김 정지는 PC·시뮬 확인이고 실기기 확인 필요.

### P9. 18 관제 상태 조회, 21 실행 상태 대조

| 번호 | 지금 v0.2 | 제안 |
| --- | --- | --- |
| 18 | Service `GetViewState` `/frybot/central/get_view_state` | "31번에 통합. 별도 서비스 없음. Web Service가 0.25초마다 오는 전체 스냅샷의 마지막 것을 보관" |
| 21 | Service `GetExecution` `/frybot/tasks/get_execution` | "별도 서비스 없음. 22·24·32·33번의 `task_id`와 `plan_version`, 35번의 `session`으로 현재 실행만 반영. 결과 미수신은 완료로 치지 않음" |

- 44번(장비 실행 재조회)도 21번과 같은 문장으로 적습니다.

### P10. 20 임무 조작의 범위

| | 지금 v0.2 | 제안 |
| --- | --- | --- |
| 범위 | 임무 중단·취소. `task_id` + `attempt_id` 기준 | `ControlTask` `/frybot/tasks/control`이 받는 명령을 모두 적음: 임무(`RETRY_TASK`, `REASSIGN`, `CANCEL_TASK`), 로봇(`PAUSE`, `ESTOP`, `RESUME`, `GO_HOME`, `MOVE_TO_VERTEX`), 설정(`SET_SCHEDULER`, `SET_PLANNER`, `SET_STANDBY`) |
| 필드 | `request_id`, `task_id`, `attempt_id`, `operation` / `status`, `tracking_id`, `reason` | `command`, `target`, `arg` / `ok`, `message` |

- 이유: 지금 코드는 이 서비스 하나로 관제에 가는 명령을 모두 받고, 나누면 서비스가 셋으로 늘 뿐 동작은 같습니다.
- 대안: 이름과 내용을 맞추려면 로봇 명령과 설정을 다른 서비스로 나누는 코드 수정이 필요합니다. 사용자 판단 대상입니다.

### P11. 31 업무 상태 발행, 32 임무 상태 전이

| 번호 | 지금 v0.2 | 제안 |
| --- | --- | --- |
| 31 | `ViewState` 메시지, 대상별 변경 발행(`entity_type`, `entity_id`, `state`, `version`, `observed_at`) | `std_msgs/String`의 JSON 전체 스냅샷, 0.25초마다, Reliable / Keep Last 10. 주소는 `/frybot/central/view_state` 그대로 |
| 32 | `attempt_id`, `execution_id`, `device_id`, `phase`, `outcome`, `observed_at` | `TaskProgress`: `stamp`, `task_id`(문자열), `task_type`, `state`, `robot_id`, `visit_id`, `order_id`, `item_id`, `table_id`, `plan_version`, `reason`. 상태 전이마다 1회 |

- 31의 이유: 전체 스냅샷은 누락·역순 복구가 필요 없습니다. 버전과 기준 시각 키는 코드에 더할 후보로 적습니다.
- 32의 이유: `plan_version`이 시도 식별자 역할을 하고, `stamp`가 관측 시각입니다.

### P14. 43 장비 자체점검

| | 지금 v0.2 | 제안 |
| --- | --- | --- |
| 계약 | "결과 계약 또는 기존 상태 보고 재사용 검토" | "기존 상태 보고 재사용"으로 확정. AMR이 기동 때 33번으로 `LOCALIZING`(위치 찾는 중), `NOT_LOCALIZED` + `SELF_CHECK_ERROR`(실패)를 보고. 그동안 관제는 그 로봇을 배정·허가에 쓰지 않음 |
| 범위 | 영업 전 점검 일반 | 위치 추정만. 팔·센서의 자체점검은 없음(현재 한계) |

### P15. 7절 namespace

| | 지금 v0.2 | 제안 |
| --- | --- | --- |
| AMR 이름 | `pinky_1`, `pinky_2`, `pinky_3` | `pinky1`, `pinky2`, `pinky3` |

- 이유: 로봇 등록부, 지도의 `homes` 순서, 로봇에 저장된 자세 파일 경로, 지금까지의 실행 로그가 모두 `pinky1`입니다. v0.2의 24번 상세도 `{pinky}`로 적고 있습니다.

### P16. 번호가 없는 연결 추가

코드에서 동작 중인데 v0.2 순번 표에 없는 것입니다. 새 번호를 주거나 관련 번호의 본문에 적는 것을 제안합니다.

| 연결 | 타입 | 방향·주기 | 넣을 곳(제안) |
| --- | --- | --- | --- |
| `/fms/heartbeat` | `FleetHeartbeat` | 관제 → AMR, 5 Hz, Reliable 깊이 10 | 35번(P8) |
| `/fleet/arm_status` | `ArmStatus` | 조리 팔·AMR 제어기 → 관제, 2 Hz, Reliable 깊이 20 | 34번(P7) |
| `/frybot/guest_track` | `GuestTrack`(`stamp`, `robot_id`, `visit_id`, `visible`, `distance`) | Central Control → AMR | 23번(P1) |
| `/frybot/spot_check` | `SpotCheck`(후보 자리 `x[]`, `y[]` → `score[]`) | AMR → 천장 카메라 노드, 기동 때 위치가 모호하면 | 새 번호 |
| `/{pinky}/dock_robot` | `nav2_msgs/DockRobot` | AMR 제어기 → Nav2 | 26번(P3) |
| `/fms/state` | `std_msgs/String`(JSON) | 관제 → Web Service, 0.25초 | 31번 옆 새 번호 |
| `/frybot/event_log` | `std_msgs/String` | 관제 → Central Control, 실행 로그용 | 32번 본문 |
| `/ai/results` | `std_msgs/String`(JSON) | Central Control → 관제, 익힘 판정 | 38번 본문(부록 A의 P12와 함께) |

### P17. 문서 안에서 서로 다른 곳

| 위치 | 지금 | 제안 |
| --- | --- | --- |
| `1) FryBot I/F 목록` Service 표, Action 표 | 22번 `RequestPassage`, 24번 `ServeFood` | 정정 페이지대로 `TrafficGrant` 토픽, `NavigateRoute` + `ArmJob`. 표 머리의 개수도 맞춤 |
| 통합 정의서 v0.2 7절 "ROS2 계약 목록" | 같은 두 이름이 남음 | 같은 정정 |
| `1) FryBot I/F 목록`의 정의서 링크 | 옛 49건 번호(예: ViewState 32번) | 현행 순번(31번)의 v0.2 페이지로 |
| 22번 상세 | "heartbeat 단절(코드 기본 2초)" | 1초(2026-11-24 변경) |
| 28번과 24번 | 같은 연결을 다른 이름으로 | P4로 정리 |
| v0.3 페이지 | 14~17, 19, 20, 31, 32번이 바꾸기 전 코드 이름(웹 01·04·07번 경로도 같음, 부록 A) | v0.2가 최종이므로 v0.3을 고치거나 "이전 판"으로 표시 |

## 3. 이 제안을 받아들였을 때

- 코드는 바뀌지 않습니다. 본문 15건과 부록 A는 모두 문서 수정입니다.
- v0.2의 ROS 2 항목 24건이 코드와 맞는 것이 지금 11건(일치 3, 이름 반영 8)에서, 29번(보류)을 뺀 23건으로 늘어납니다. 필드 차이가 남는 14~17·19·20번은 "이름과 연결은 일치, 필드는 코드 수정 예정"으로 남습니다.
- 본문에 "현재 한계"로 적자고 한 것(P4 물리 결과 확인, P6 배터리 관측 시각, P7 팔 오류, P8 팔의 생존 신호·재가동 기록, P11 스냅샷 버전)은 문서를 고친 뒤에도 코드 과제로 남습니다.

## 4. 진행 방법 제안

1. 이 제안서에서 받아들일 항목을 사용자가 고릅니다.
2. 고른 항목마다 대상 페이지의 최신 판을 다시 읽고, 바꿀 본문(전/후)을 보여 드린 뒤 승인받아 수정합니다. 페이지 수가 많아 번호 묶음(P1~P3, P4~P5, P6~P8, P9~P11, P14~P17)으로 나눠 진행하는 것을 권합니다.
3. 페이지 작성자가 따로 있으므로(통합 정의서 v0.2의 마지막 수정자는 사용자가 아님), 수정 전에 작성자와 공유할지는 사용자가 정합니다.

## 5. 확인하지 못한 것

- 필드와 주소는 코드에서 옮겼고, 실행 그래프로 다시 확인한 것은 이름 변경 8건의 서비스·토픽 목록뿐입니다.
- 항목마다 적은 "확인 범위" 밖은 실기기 확인 필요입니다.
- 정의서가 근거로 드는 GitHub 저장소(`roscamp-repo-1`)는 보지 못했습니다. 그쪽 코드가 v0.2의 후보 이름을 이미 쓰고 있다면 P1~P8의 판단이 달라질 수 있습니다(확인 필요).

## 부록 A. ROS 2 밖 항목 (본문에서 옮김)

HTTP와 영상 전송에 관한 제안입니다. ROS 2 항목과 따로 판단할 수 있게 여기에 모았습니다.

### P12. 38 AI 관측 결과 (HTTP)

| | 지금 v0.2 | 제안 |
| --- | --- | --- |
| 방향·경로 | "검토 중", 송수신 "확인 필요" | AI 서버 → Central Control, HTTP `POST :8100/ai/result`, JSON |
| 내용 | `observation_id`, `kind`, `target_ref`, `observed_at`, `validity` / 판정, `confidence`, `evidence_ref` | `kind`별: `SEAT_QR`(`table_id`, `visible`, `seats`), `DONENESS`(`cook_task_id`, `decision`, `confidence`, `changed`), `GUEST_TRACK`(`robot_id`, `visible`, `distance`, 그 밖 참고 값) |
| 후속 전달 | `GuestTrack`은 후속 경계 | `GUEST_TRACK` → 토픽 `/frybot/guest_track`, `DONENESS` → 토픽 `/ai/results`, `SEAT_QR` → 테이블 이용 종료 판단 |
| 추가 | 없음 | Central Control → AI 서버 `POST :8095/guides`: 안내 중인 (로봇 → 방문) 목록, 바뀔 때와 1초마다 |

- 이유: 방향과 경로가 코드에서 정해져 동작 중입니다.
- 남기는 것: 관측 시각과 유효성은 v0.2가 낫고 코드에 넣을 항목입니다(방향 비교 4.3절). 본문에 "현재 한계: 관측 시각 없음"으로 적습니다.
- 확인 범위: 손님 추적은 PC·녹화 영상 확인, 실기기 안내 주행은 확인 필요.
- ROS 2와 닿는 곳: 받은 결과를 Central Control이 토픽 `/frybot/guest_track`, `/ai/results`로 넘기는 뒷부분만 ROS 2이고, 그 토픽들은 본문 P1·P16에 있습니다.

### P13. 39 카메라 영상 (TCP·UDP)

| | 지금 v0.2 | 제안 |
| --- | --- | --- |
| 전송 | 압축 영상 UDP, `stream_id`·`frame_seq`·`capture_time` 머리 | 현행 두 가지를 적음. (1) Pinky 카메라 → AI 서버: TCP :8554 MJPEG, 640×480·15 fps·품질 70, 한 번에 받는 쪽 하나. (2) 대역: 조리 팔·AMR → AI 서버 대역, UDP :9100, 영상이 아닌 JSON 프레임 |
| UDP 압축 영상 | 기준 | "후보"로 남김 |

- 이유: 지금 동작하고 측정된 것이 TCP MJPEG입니다. 2026-11-24에 세 대를 함께 보낼 때 약 5초 밀린 일이 있어 15 fps·품질 70으로 낮췄습니다. 같은 문제가 다시 생기면 v0.2의 UDP로 가는 것이 맞으므로 후보로 둡니다.

### P16에서 옮긴 것: 번호가 없는 ROS 밖 연결

| 연결 | 방식 | 방향 | 넣을 곳(제안) |
| --- | --- | --- | --- |
| `GET /api/state`, `/api/layout`, `/api/maps`, `/api/map`, `/api/events` | HTTP | 화면 → Web Service | 06번 본문 |
| `POST :8095/guides` | HTTP | Central Control → AI 서버 | 38번(P12) |
| TCP :8554 MJPEG | 영상 | Pinky 카메라 → AI 서버 | 39번(P13) |

### P17에서 옮긴 것: v0.3의 웹 경로

v0.3 페이지의 웹 01·04·07번이 바꾸기 전 경로(`/api/checkin`, `/api/order`, `/api/admin`)를 적고 있습니다. 코드는 2026-11-25에 v0.2 경로(`/api/visits`, `/api/orders`, `/api/admin/operations`)로 바뀌었습니다.
