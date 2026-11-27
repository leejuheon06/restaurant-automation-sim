# 코드 리뷰와 수정 기록 — 2026-11-17

> 2026-11-19: 11월 16~18일 실행 폴더(`runs/run_2026111[6-8]_*` 등)는 `archive/runs_2026-11-16_18/`로 옮겼습니다. 이 문서의 실행 이름은 그 폴더 아래에 있습니다.

17일 발견 사항과 17~18일 후속 조치를 통합한 기록입니다. 수정 전 증상·제안과 적용된 조치를 함께 보존합니다. **수정 완료는 실기기 검증 완료를 뜻하지 않습니다.** 현재 실행 명령은 [COMMANDS.md](COMMANDS.md), 이후 실측은 [18일](2026-11-18_REAL_TEST.md)·[19일](2026-11-19_REAL_TEST.md) 기록을 참고하세요.

- 정리: 2026-11-17. 아래 "출처"의 네 문서에서 뽑았고, 요약 표의 "재확인" 칸에 ○가 있는 항목은 같은 날 현재 코드에서 그대로임을 다시 확인함
- 파일별 검토 완료 여부와 R0~R7의 원래 발견·조치는 [체크리스트](CODE_REVIEW_CHECKLIST.md)에 보존합니다. 본문에 남은 행 번호와 “지금”은 해당 리뷰 시점 기준이며 현재 코드 재검증 결과가 아닙니다.
- 쓰는 법: 고친 항목은 "조치:" 줄에 날짜와 내용을 적고, 버그 수정이면 [TROUBLESHOOTING.md](TROUBLESHOOTING.md)에 T-번호로 기록
- 경로는 `src/frybot/` 기준. 줄 번호는 2026-11-17 값이라 수정이 진행되면 어긋남
- "확신"은 코드 경로를 따라가 본 정도(확실 = 경로 확인, 추정 = 실기기 확인 필요)
- 2026-11-17 추가: `dev_docs/`의 설계 자료와 대조한 검토(Claude + Codex GPT-6.1-Sol 교차 검토)에서 나온 G, N, H 항목을 더하고, 기존 항목 일부를 정정함(각 항목의 "정정:" 줄). G 항목의 `P n`은 레스토랑 AMR 우선순위(권장 순서 참고). 정적 검토이며 실기기에서 확인한 것은 없음
- 2026-11-18 추가: 권장 순서 1번(사람 안전·정지)에서 9건을 고침. 아래 "수정 완료" 표와 각 항목의 "조치:" 줄 참고. 완료 항목도 근거와 검증 한계를 보존하며 요약 표에는 **[수정 완료]**로 표시

| 출처 | 번호 |
|---|---|
| 17일 원본 리뷰(이 문서에 통합) | A1~A5, B1~B6, C1~C5, D1~D11, E |
| [CODE_REVIEW_CHECKLIST.md](CODE_REVIEW_CHECKLIST.md) | R0~R7 |
| [2026-11-16_CHANGES.md](2026-11-16_CHANGES.md), [2026-11-17_CHANGES_MAPS.md](2026-11-17_CHANGES_MAPS.md) | "남은 일"의 항목 |
| `dev_docs/` 설계 적합성 검토 (2026-11-17, UR·SR v2, State Diagram V0.04, Sequence V0.09, 기기별 상태 흐름 V0.10, 데이터 모델) | G1~G17, N1~N3, H1~H7 |


## 후속 기록과 상태 대조 (2026-11-19 정리)

| 항목 | 이후 문서에서 확인한 변경 | 남겨 둘 한계 |
| --- | --- | --- |
| B1 / R5-4 시간 모델 | 16일 실측은 구간당 약 2.27초 + 거리÷0.135m/s, 실제/ETA 약 1.76배. 18일 W6/W10에서 plan_overhead 추가, 모의 ETA 비율 1.00~1.10 | 기본 plan_overhead는 0.0. 보정 후보의 실기기 검증 완료로 처리하지 않음 |
| D7 / R7-2 등록부 | 18일 T-30에서 ~/.config/frybot/robots.yaml로 이동 | 아래 원래 발견 설명은 변경 전 상태 |
| B6 / R1-4 시뮬 출력 | 18일 T-36에서 sim_backend.py로 분리 | 실제 센서·모델 동작 검증과 별개 |
| E: fleet_rviz 두 대 고정 | 19일 T-40에서 robots 인자 추가, C6-B에서 세 대 모델·지역 코스트맵 표시 사용자 확인 | RViz 연결 직후 끊김 문제는 별도 실측 기록 참고 |
| D4 TF 신선도 | 18일 실측에서 정지 중 SENSOR_ERROR가 보고됨 | 1.0초 임계값의 오탐 여부 확인 필요. 수정 구현만으로 해결 판정하지 않음 |
| F: R0-8 상태 주석 | 17일 재확인에서 이미 YIELD·YIELD_BLOCKED 기재 | 수정할 결함으로 다시 집계하지 않음 |

근거: [체크리스트](CODE_REVIEW_CHECKLIST.md), [18일 개선 기획안](2026-11-18_IMPROVEMENT_PLAN.md), 날짜별 실기기 기록. 이번 작업은 문서 대조이며 코드 리뷰나 실기기 시험을 새로 수행한 것이 아닙니다.

## 수정 완료 (2026-11-17~18)

수정 전 계획과 수정 후 코드를 Codex(GPT-6.1-Sol)가 교차 검토했고, 빌드·모의 시험·시뮬 실행(경량 시뮬 demo, 실측 지도 시뮬, Gazebo + Nav2)으로 확인했습니다. 실기기에서는 확인하지 않았습니다. 상세는 [TROUBLESHOOTING.md](TROUBLESHOOTING.md) T-29.

| 번호 | 고친 내용 | 확인한 방법 | 남은 확인 |
|---|---|---|---|
| A1 | `cmd_vel`이 0.5초 끊기면 드라이버가 모터를 세움 | 가짜 모터 드라이버 6건 | 실기기 확인 필요, 로봇에 배포 필요 |
| A2 | 시뮬 기본값을 시뮬 전용 도메인(74)으로 | 도메인 73에서 시뮬 토픽 0개, 경량 시뮬·Gazebo 시나리오 완료 | Pinky를 켠 상태의 확인 |
| A3 | 끊긴 로봇에 허가·재계획·배정 중단, 10초 뒤 임무 보류 | 모의 22건, 실측 지도 시뮬에서 제어기 강제 종료 | 실기기 재연결 뒤 동작 |
| B3 | 로봇 제어기 기본값을 실기기 값으로 | 경량 시뮬, Gazebo 주행 | 없음 |
| B4 | `real.launch.py`가 실측 지도 없이는 뜨지 않음 | 런치 실행 4가지 | 없음 |
| D4 | 위치 추정이 1초 넘게 굳으면 정지하고 `SENSOR_ERROR` 보고 | 가짜 TF 7건 | 실기기 확인 필요(오탐 여부), 로봇에 배포 필요 |
| D6 | CORS 삭제, 관리자 명령은 관제 PC 또는 토큰 | `curl` 응답 코드, 관리자 화면 렌더링 | 토큰 입력 창 조작, AI 포트(8100) |
| G2 | 오류를 보고 중인 로봇에 임무를 배정하지 않음 | 모의 | 운용 제외 상태 |
| G4 | 실기기는 손님 추적 없이 안내를 출발하지 않음 | 런치 인자 전달 | 실기기 확인 필요(안내 임무가 생긴 뒤) |

권장 순서 1번에서 남은 것: G5(충돌 감시 노드), G3(정지 확인 뒤 확정), A4·A5의 감시 시간.

## 요약

| 번호 | 항목 | 심각도 | 주 파일 | 재확인 |
|---|---|---|---|---|
| A1 | **[수정 완료]** 속도 명령이 끊겨도 모터가 멈추지 않음 | 높음 | `pinky_driver.py` | ○ |
| A2 | **[수정 완료]** 시뮬레이션 기본값이 실기기와 같은 네트워크·도메인 | 높음 | `sim.launch.py`, `gazebo.launch.py` | ○ |
| A3 | **[수정 완료]** 끊긴 로봇의 경로·락·임무를 그대로 둠 (R5-1) | 높음 | `fleet_core.py` | ○ |
| A4 | 경로 전송과 진행에 감시 시간 없음 | 높음 | `task_manager_node.py`, `fleet_core.py` | |
| A5 | Nav2가 죽었을 때 감지·실패 전파 (설명 정정) | 중간 | `mobile_controller.py`, `navigator.py` | ○ |
| B1 | 계획 시간 모델이 시뮬 값 (R5-4, T-23). 방향 미결정 | 높음 | `sipp.py`, `fleet_core.py` | ○ |
| B2 | 구간 시작 때마다 지역 코스트맵을 지움 | 중간 | `mobile_controller.py` | ○ |
| B3 | **[수정 완료]** 로봇 제어기 기본값이 시뮬 값 | 중간 | `mobile_controller.py` | ○ |
| B4 | **[수정 완료]** `map_id`를 빠뜨리면 가상 매장으로 뜸 | 중간 | `real.launch.py` | ○ |
| B5 | 실기기 분기를 도는 시뮬이 없음 | 중간 | `mobile_controller.py` | |
| B6 | 실기기가 시뮬 전용 토픽을 구독 (R1-3) | 낮음 | `mobile_controller.py` | ○ |
| C1 | 복귀를 포기한 로봇이 다시 물러남 (T-26) | 중간 | `fleet_core.py` | ○ |
| C2 | 거절된 이동 명령이 복귀 예약을 지움 (T-26) | 중간 | `fleet_core.py` | ○ |
| C3 | 지도 불일치 시 화면이 3초마다 초기화 (T-27) | 중간 | `admin.html`, `web_service_node.py` | |
| C4 | 실측 지도 시뮬에 `drive:=nav2`를 주면 조용히 안 움직임 | 낮음 | `sim.launch.py` | ○ |
| C5 | 복귀를 기다리는 로봇이 대기 상태로 보임 (T-26) | 낮음 | `fleet_core.py` | ○ |
| D1 | `remote:=false`이면 관제가 pinky1만 앎 | 높음 | `real.launch.py` | ○ |
| D2 | 구간 중 취소된 로봇이 비켜 주기 대상에서 빠짐 | 중간 | `fleet_core.py` | ○ |
| D3 | 보류된 로봇을 4초 뒤 비킨다고 계산 | 중간 | `fleet_core.py` | ○ |
| D4 | **[수정 완료]** AMCL이 죽어도 굳은 위치를 계속 보고 (R1-2) | 높음 | `mobile_controller.py` | ○ |
| D5 | `stop_all.sh`가 PC의 다른 ROS 작업도 끔 | 중간 | `scripts/stop_all.sh` | ○ |
| D6 | **[수정 완료]** 관리자 API 인증 없음 (R7-1) | 높음 | `httpd.py` | ○ |
| D7 | SSH 비밀번호가 패키지 안에 있음 (R7-2) | 중간 | `config/robots.yaml` | ○ |
| D8 | 배포가 실행 중인 로봇 위에 덮어씀 | 중간 | `robot_remote.py` | ○ |
| D9 | 실측 지도에서 접수·주문이 "만석"처럼 거절됨 | 중간 | `restaurant.py` | |
| D10 | 실행 기록에 관제 설정과 로드맵 버전이 없음 | 중간 | `central_control_node.py`, `replay_run.py` | |
| D11 | 코드 머리말과 README의 옛 실행 예시 | 낮음 | `README.md`, 런치 파일 | ○ |
| E | 낮음 묶음 16건 | 낮음 | 여러 파일 | 일부 |
| F | 앞선 리뷰·수정 기록의 남은 항목 | 낮음~중간 | 여러 파일 | 일부 |
| G1 | 실측 지도에서 식당 업무(접수·주문·조리·서빙·회수)가 막힘 | 높음 | `restaurant.py`, `fleet_core.py` | ○ |
| G2 | **[수정 완료]** 가용 판정이 로봇 오류를 보지 않음 | 높음 | `fleet_core.py` | ○ |
| G3 | 중단·재배정·취소·재개가 실제 정지 확인 전에 확정됨 | 높음 | `fleet_core.py`, `task_manager_node.py` | ○ |
| G4 | **[수정 완료]** 실기기 안내에서 동행 관측이 없어도 출발함 | 높음 | `mobile_controller.py`, `robot.launch.py` | ○ |
| G5 | 직접 속도 명령을 공통으로 검사하는 충돌 감시가 없음 | 높음 | `mobile_controller.py`, `nav2_store.yaml` | ○ |
| G6 | 적재 상태별 속도·가속도 제한이 없음 | 중간 | `mobile_controller.py`, `NavigateRoute.action` | ○ |
| G7 | 익힘 판정이 없거나 미달이어도 조리를 진행함 | 중간 | `fleet_core.py` | ○ |
| G8 | QR 이용 종료 판정이 등록 정보와 관측 신선도를 보지 않음 | 중간 | `restaurant.py`, `central_control_node.py` | ○ |
| G9 | 음식 항목에 `LOADED` 상태가 없음 | 중간 | `restaurant.py`, `fleet_core.py` | ○ |
| G10 | 회수 중인 테이블을 확인 없이 이용 가능으로 바꿀 수 있음 | 중간 | `restaurant.py` | ○ |
| G11 | 주문 요청에 식별자가 없어 중복 접수를 가릴 수 없음 | 중간 | `PlaceOrder.srv`, `restaurant.py` | ○ |
| G12 | 임무 후 복귀·충전·재가용 절차가 축약됨 | 중간 | `fleet_core.py`, `mobile_controller.py` | ○ |
| G13 | 조리 팔 상태를 보고가 아닌 명령으로 추정함 | 중간 | `fleet_core.py` | ○ |
| G14 | 보류·복구 기록이 저장되지 않고 재시작 복원이 없음 | 중간 | `restaurant.py`, `db.py` | ○ |
| G15 | 테이블 화면이 전달 실패를 "전달 완료"로 표시할 수 있음 | 낮음 | `table.html` | ○ |
| G16 | `device_state.py` 주석이 옛 설계 버전 기준 | 낮음 | `device_state.py` | ○ |
| G17 | `frybot_mobile/package.xml`에 직접 쓰는 의존성이 빠져 있음 | 낮음 | `package.xml`, `mobile_controller.py` | ○ |
| N1 | 실기기 구성에서 대역 팔의 성공이 물리 완료로 쓰임 | 높음 | `real.launch.py`, `mobile_controller.py` | ○ |
| N2 | 충전 판정이 배터리 기록의 신선도를 보지 않음 | 중간 | `mobile_controller.py` | ○ |
| N3 | `fleet_core.py`와 `mobile_controller.py`에 책임이 몰려 있음 | 낮음 | `fleet_core.py`, `mobile_controller.py` | ○ |
| H | 설계 쪽 결정이 필요한 것 7건 | 결정 필요 | `dev_docs/` | |

## 권장 순서

2026-11-17 교차 검토에서 "고치기 쉬운 것부터"가 아니라 위험 순으로 다시 정했습니다. 번호는 레스토랑 AMR 우선순위(1 사람 안전·정지, 2 혼잡 주행, 3 위치 추정, 4 쏟지 않는 운동 제어, 5 교통 관리, 6 배차·상태 관리, 7 통신·고장 대응, 8 운영 화면)입니다.

1. 사람 안전·정지: A1 → G5, A2, B4·B3(오기동), D6, G3, G4. A3·A4·D4 중 "끊기면 정지·허가 차단" 부분
   - 2026-11-18: A1, A2, B3, B4, D6, G4, A3, D4와 6번의 G2를 수정 완료. 남은 것은 G5, G3, A4
2. 혼잡 주행: B2, C1·C2·D2, C5(예고 없는 재출발), F의 R1-6과 `_rotate` 시간 제한, B5
3. 위치 추정: D4의 TF 신선도와 복구
4. 쏟지 않는 운동 제어: G6 (실제 적재 주행 시험 전까지)
5. 교통 관리: B1(방향 결정 뒤) → D3, R5-5
6. 배차·상태 관리: G2 → H1·H3·H4 결정 → G1+D9 → N1 → G9, G8, G10, G11, G12 → G14+H2
7. 통신·고장 대응: A3·A4·A5의 나머지, G13, N2, G17, D8. 실제 팔을 연결하기 전에 R0-7과 G7
8. 운영 화면·정리: G15, C3, D10, D11, H6, N3, E의 나머지

G1(실측 지도에 식당 업무 연결)은 실기기 기준으로 가장 큰 기능 공백이지만, 실기기에서 켜기 전에 1~4번이 먼저입니다.

## A. 실기기 안전

### A1. 속도 명령이 끊겨도 모터가 멈추지 않음 (높음, 확실)
- 위치: `frybot_mobile/frybot_mobile/pinky_driver.py:106-127` `twist_callback`
- 지금: `cmd_vel`을 받을 때만 `set_double_rpm`을 보냄. 명령 시간 초과가 없고, 다이나믹셀은 속도 모드라 마지막 RPM을 유지함. 0 속도 전송이 실패해도 경고만 찍음
- 문제: `mobile_controller`(직접 후진 중), `controller_server`, 네트워크 중 하나만 죽어도 로봇이 그 속도로 계속 감. T-22의 정지 명령과 R1-5는 보내는 쪽이 살아 있어야만 동작함. R1-1에 "확인 필요"로 남아 있던 "드라이버 자체의 명령 시간 초과"의 답이 이것임
- 제안: 마지막 수신 시각을 저장하고, `update_and_publish`(30 Hz)에서 0.5초 넘게 명령이 없으면 0 RPM을 보냄(실패하면 다음 주기에 다시)
- 조치(2026-11-17~18): **수정 완료(실기기 확인 필요).** `cmd_vel_timeout`(0.5초) 넘게 명령이 없으면 30 Hz 주기에서 0 RPM을 보내고, 0 RPM 전송이 실패하면 다음 주기에 다시 보냄. 가짜 모터 드라이버로 6건 통과. 실기기에서 주행 중 제어기를 죽였을 때 서는지와 정상 주행 중 오탐 여부는 확인하지 못함. 로봇에 배포(`robot_remote --all --deploy`)해야 적용됨. 검증은 [TROUBLESHOOTING.md](TROUBLESHOOTING.md) T-29

### A2. 시뮬레이션이 기본으로 실기기와 같은 네트워크·도메인을 씀 (높음, 코드 확실 / 발생 추정)
- 위치: `frybot_bringup/launch/sim.launch.py`의 `('net', 'lan')`
- 지금: 이 PC와 Pinky 3대의 `ROS_DOMAIN_ID`가 모두 73. 시뮬의 Task Manager와 `/pinky1..3` 이름이 실기기와 겹침. `gazebo.launch.py`의 기본값도 `lan`
- 문제: Pinky 쪽 프로그램이 살아 있으면(원격 정지가 실패했거나 수동으로 띄운 경우) 시뮬의 생존 신호를 새 세션으로 받아 시뮬의 경로를 주행할 수 있음. 문서는 `net:=local`을 붙이라고만 안내함
- 제안: 기본값을 `local`로 바꾸거나 시뮬을 다른 도메인에서 돌림
- 조치(2026-11-17~18): **수정 완료.** `net` 기본값을 `lan` → `sim`(시뮬 전용 도메인 74, `frybot_bringup/sim_net.py`)으로 바꿈. 제안의 `local`을 먼저 기본으로 했으나 Gazebo(프로세스 52개)에서 노드가 서로를 다 찾지 못해 Nav2가 주행하지 못했고(T-13의 원인), 제안의 두 번째 안(다른 도메인)으로 바꿈. 시뮬 실행 중 도메인 73에서 시뮬 토픽 0개, 경량 시뮬 demo와 Gazebo single 완료. 실제 Pinky를 켠 상태의 확인은 하지 않음. 검증은 [TROUBLESHOOTING.md](TROUBLESHOOTING.md) T-29

### A3. 로봇이 끊겨도 경로·락·임무를 그대로 둠 (높음, 확실, 기존 R5-1)
- 위치: `frybot_control/frybot_control/fleet_core.py` `tick`(오프라인 판정), `_drive`
- 지금: 상태 보고가 2초 넘게 없으면 `online=False`만 함. `_drive`는 `online`을 보지 않아 허가를 계속 냄. 오프라인 판정 자체가 `if self.graph.map_id:` 안에만 있어 가상 매장(시뮬)에서는 끊겨도 영원히 온라인
- 문제: 끊긴 로봇이 잡은 락에 다른 로봇이 막힘. 시뮬로는 이 경로를 검증할 수 없음
- 제안: 판정을 지도와 무관하게 하고, `_drive` 첫 줄에서 오프라인이면 반환. 일정 시간 넘으면 임무를 `OFFLINE`으로 보류
- 정정(2026-11-17): 끊긴 로봇에는 신규 허가·배정을 막되, 물리 점유가 불명인 락을 시간만으로 풀지 않음(락은 보고된 진행에 따라 해제됨, `fleet_core.py:1213`)
- 조치(2026-11-17~18): **수정 완료(실기기 확인 필요).** 끊김 판정을 지도와 무관하게 하고, 끊긴 로봇에는 허가·재계획·재배정을 하지 않음(락 유지). 10초를 넘기면 임무를 `SUSPENDED(OFFLINE)`로 두고 `RETRY_TASK`로 재개. `ROBOT_OFFLINE`·`ROBOT_ONLINE` 이벤트 추가. 모의 22건과 실측 지도 시뮬(주행 중 제어기 강제 종료)에서 확인. 끊긴 사이 취소가 닿지 않은 실제 로봇의 재연결 뒤 동작은 확인하지 못함. 검증은 [TROUBLESHOOTING.md](TROUBLESHOOTING.md) T-29

### A4. 경로 전송과 진행에 감시 시간이 없음 (높음, 감시 없음은 확실 / 유실 방식은 추정)
- 위치: `frybot_control/frybot_control/task_manager_node.py` `send_route`, `_nav_accepted`; `fleet_core.py` `_drive`
- 지금: `send_goal_async`가 끝나지 않거나 결과가 유실되면 관제의 경로가 남고, 다음 노드 락을 잡은 채 진행 보고를 기다림
- 문제: 화면은 이동 중인데 로봇은 서 있고, 다른 로봇이 그 락에 막힘. 결과가 오지 않으므로 자동 재시도도 없음
- 제안: 수락 뒤 일정 시간(예: 2 × (2.27초 + 구간 ÷ 0.135)) 안에 진행이 없으면 경로를 취소하고 기존 재시도 경로(`on_route_result`)를 탐
- 조치:

### A5. Nav2가 죽었을 때 감지와 실패 전파가 부족함 (중간, 설명 정정)
- 위치: `frybot_mobile/frybot_mobile/mobile_controller.py:681-683`, `navigator.py:48,62`
- 지금: `if not self.nav2.server_is_ready(): self.nav_state = 'WAIT_NAV2'; return False`. 시간 제한과 오류 보고가 없음. `bond_timeout: 0.0`이라 lifecycle manager도 알아채지 못함
- 문제: 경로를 끝내지도 실패를 알리지도 않고 `WAIT_NAV2`에 머묾. 관제는 그 로봇의 락을 계속 잡음
- 제안: `WAIT_NAV2`가 10초를 넘으면 `NAV2_FAILED`로 끝냄. `bond_timeout`은 기본값(4초)으로
- 정정(2026-11-17): 구간마다 15초 무진행 감시가 있고 실측 지도에서는 이때 0 속도를 보냄(`mobile_controller.py:775-777`). "끝없이 기다림"은 현재 코드와 다름. 남은 문제는 `bond_timeout: 0.0`(`navigator.py:50, 64`)과, 감시 뒤 `WAIT_NAV2`에서 실패가 관제로 전달되는지(`:817-819`, 확인 필요)
- 조치:

## B. 실기기 기준이 아닌 것

### B1. 계획 시간 모델이 시뮬 값 (높음, 코드 확실 / 효과 크기 추정, 기존 R5-4·T-23)
- 위치: `planners/sipp.py:44`, `fleet_core.py`(`speed`, `plan_speed_factor`, `stall_timeout`, `_retreat`, `_cost_fn`), `task_manager_node.py:25-30`, `frybot_bringup/launch/real.launch.py`의 `('speed', '0.08')`
- 지금: 계획 시간 = 거리 ÷ 0.072 m/s, 구간 지연 0. 실측은 2.27초 + 거리 ÷ 0.135 m/s. 예: 0.06 m 구간은 계획 0.8초, 실제 약 2.7초
- 같은 모델에 기대는 값: `stall_timeout` 3초(상대가 다음 구간을 출발하는 데만 2.27초라 보통의 대기가 정체로 판정됨), `_retreat`의 소요 추정(실제 후진은 0.05 m/s), `yield_max_wait` 25초, `yield_until` 30초, `YIELD_BACK_WAIT` 60초, 배정 비용. `FLIP_HOLD` 8초만 실측에 맞춰져 있음
- 그 밖: `plan_speed_factor`는 ROS 파라미터가 아님. `speed`/`guide_speed`가 원격 기동(`remote.py`)으로 로봇에 전달되지 않음. 실측 지도 경량 시뮬도 0.08 m/s, 지연 0으로 움직여 실제 타이밍을 검증하지 못함
- 제안: `PlanRequest`에 구간 지연을 추가해 `dt = 지연 + 거리 ÷ 속도`로 계산. Task Manager에 `speed`, 구간 지연, `plan_speed_factor` 파라미터를 두고 실기기 런치 기본값을 실측값으로. `_retreat`와 `_cost_fn`도 같은 함수를 쓰게 함. 경량 시뮬의 로봇에도 같은 지연을 넣음
- 주의: 주행 순서가 달라지는 큰 변경. 사용자가 "미결정"으로 남겨 둔 항목
- 조치:

### B2. 구간을 시작할 때마다 지역 코스트맵을 지움 (중간, 코드 확실 / 영향 크기 추정)
- 위치: `mobile_controller.py:686-689`, `:376-377`
- 지금: 주석 근거는 "The simulated lidar sometimes returns only invalid ranges". 1초 주기 지우기(`_refresh_costmap`)는 실측 지도에서 막혀 있지만, 구간 시작과 재시도 때의 지우기는 실기기에서도 실행됨
- 문제: 출발 직후 다음 스캔이 채우기 전까지 사람이나 다른 로봇이 지역 코스트맵에서 지워짐. 장애물 때문에 실패했는데 장애물을 지우고 다시 출발하게 됨
- 제안: 시뮬 전용 파라미터 뒤로 옮기거나, 실측 경로에서는 지운 뒤 스캔 한 번을 기다림
- 조치:

### B3. 로봇 제어기의 기본값이 시뮬 값 (중간, 확실)
- 위치: `mobile_controller.py:58-59`
- 지금: `drive` 기본 `kinematic`, `pose_source` 기본 `gz`. 정상 실기기 경로는 `robot.launch.py`가 `nav2`/`tf`를 넘겨 영향 없음
- 문제: 로봇에서 파라미터 없이 `ros2 run frybot_mobile mobile_controller`를 실행하면 실제로는 움직이지 않고 경로를 "성공"으로 끝냄. T-25 이후에는 AMCL 없이 홈 좌표를 참값으로 보고함
- 제안: 기본값을 `nav2`/`tf`로 바꾸고 시뮬 런치가 값을 명시
- 조치(2026-11-17~18): **수정 완료.** 기본값을 `nav2`/`tf`로 바꾸고 `sim.launch.py`가 `pose_source: gz`를 명시. 경량 시뮬과 Gazebo에서 주행 확인. 단독 실행에는 `base_frame:=base_footprint`와 `/tf` 리맵도 필요함을 머리말에 적음. 검증은 [TROUBLESHOOTING.md](TROUBLESHOOTING.md) T-29

### B4. 실기기 런치에 `map_id`를 빠뜨리면 가상 매장으로 뜸 (중간, 확실)
- 위치: `real.launch.py:33-38, 50, 68`
- 지금: `map_id` 기본값이 `''`. 비어 있으면 PC는 가상 매장 그래프와 조리 팔·AI 대역으로 뜨고, 로봇은 지도 인자가 없어 늦게 실패함. `map_id:=proto`를 주면 대역은 뜨지 않는데 관제는 주문을 받아 조리가 끝나지 않음
- 제안: `map_id`가 비었거나 `proto`이거나 지도 목록에 없으면 오류. `sim_cooking` 기본값을 `false`로 하거나 proto 전용임을 명시
- 조치(2026-11-17~18): **수정 완료.** `map_id`가 없거나 `proto`이거나 없는 지도면 런치를 멈춤(남는 프로세스 없음 확인). 도달할 수 없게 된 조리 팔·AI 대역 분기와 `sim_cooking` 인자 삭제. 정상 지도에서 관제 3개 노드 기동 확인(`remote:=false`). 검증은 [TROUBLESHOOTING.md](TROUBLESHOOTING.md) T-29

### B5. 실기기 경로를 도는 시뮬이 없음 (중간, 확실)
- 위치: `mobile_controller.py`의 `not self.measured_map` 분기(366, 491, 643, 665, 677, 713행)
- 지금: Gazebo는 가상 매장 전용이고, 실측 지도 시뮬은 Nav2를 거치지 않는 직접 이동뿐. 재시도 뒤 `NAV2_FAILED`, 직접 후진의 라이다 검사 같은 실기기 분기는 어느 시뮬에서도 실행되지 않음
- 제안: 분기 기준을 지도 종류가 아닌 명시 파라미터로 바꾸고 Gazebo가 실측 지도로 뜰 수 있게 함. 최소한 경량 시뮬에 실측 구간 지연과 속도 옵션을 둠(B1과 함께)
- 조치:

### B6. 실기기가 시뮬 전용 토픽을 구독함 (낮음, 확실, 기존 R1-3)
- 위치: `mobile_controller.py:99, 300-316`
- 지금: `/sim/world_state`를 항상 구독. 실기기의 손님 안내는 이탈 검사 없이 진행함
- 문제: 같은 도메인에서 시뮬의 매장 노드가 돌면 가상 손님 때문에 실기기가 멈추거나 `GUEST_LOST`가 될 수 있음(A2와 연결)
- 제안: 손님 위치 토픽을 파라미터로 받고 실기기는 기본 비활성
- 정정(2026-11-17): 이탈 검사는 T-28에서 `/frybot/guest_track` 기준으로 바뀜. "실기기에서 동행 확인 없이 진행" 문제는 G4로 옮기고, 여기에는 시뮬 토픽 구독만 남김(현재 구독 위치 `mobile_controller.py:122`)
- 조치:

## C. 2026-11-17에 고친 코드의 문제

### C1. 복귀를 포기한 로봇이 다시 물러났다가 복귀를 시도함 (중간, 확실, T-26)
- 위치: `fleet_core.py:975` `_resolve_stall`의 마지막 `if mutual or o.estop: self._retreat(r, o)`
- 지금: 복귀 중인 로봇이 정체되면 `_start_move`가 `YIELD_STAY`를 남기고 포기하는데, 바로 뒤에서 일반 물러서기가 실행되어 복귀 예약을 다시 걺
- 문제: T-26이 막으려던 자리 바꾸기가 이 경로로 남음. `tick` 쪽에는 조건이 있는데 여기에는 없음
- 제안: 조건을 `(mutual or o.estop) and (r.task or not self.graph.map_id)`로
- 조치:

### C2. 거절된 이동 명령이 복귀 예약을 지움 (중간, 경로 확실 / 발생 창은 좁음, T-26)
- 위치: `fleet_core.py:1251-1254`, `:527-533`
- 지금: `_move_to_vertex`가 명령 수락 여부를 확인하기 전에 `pending_goal`을 지움. 또 복귀 경로를 자를 때 관제 쪽만 자르고 로봇에는 알리지 않음
- 문제: 명령이 거절되면 복귀만 사라짐. 드물게 로봇 쪽 목표가 취소되지 않아 대기 상태로 돌아오지 못하고, 이후 명령이 모두 거절됨(비상 정지 → 재개로만 풀림)
- 제안: 예약 해제를 수락이 확정된 뒤로 옮기고, 자른 경로는 로봇에 취소를 보냄
- 조치:

### C3. 지도 불일치가 계속되면 화면이 3초마다 초기화됨 (중간, 논리 확실 / 원인 추정, T-27)
- 위치: `frybot_web/static/admin.html` `checkCatalog`, `frybot_web/frybot_web/web_service_node.py` `_maps`
- 지금: 화면의 `active`는 웹 서비스의 환경 변수에서, `fleet.map_id`는 Task Manager에서 옴. 둘이 다르면 3초마다 지도를 다시 받음
- 문제: 옛 웹 서비스가 8080 포트를 쥐고 있으면 불일치가 풀리지 않아 지도와 선택이 계속 초기화됨. 새로고침 버튼으로도 풀리지 않음. 이 상황이 T-27 증상의 원인일 가능성도 있음
- 제안: `_maps`가 관제에서 받은 `map_id`를 우선 보고. 2~3회 불일치면 자동 다시 받기를 멈추고 안내 문구 표시. 다시 받을 때 사용자의 미리보기 선택 유지
- 조치:

### C4. 실측 지도 시뮬에 `drive:=nav2`를 주면 조용히 움직이지 않음 (낮음, 확실)
- 위치: `sim.launch.py` `measured_nodes`
- 지금: `drive`를 그대로 넘기지만 Nav2·AMCL·라이다를 띄우지 않음. 코스트맵 노드는 `sim_time:=true`일 때 시계가 맞지 않음
- 제안: `kinematic`이 아니면 오류. 코스트맵에도 `use_sim_time`을 같이 넘김
- 조치:

### C5. 복귀를 기다리는 로봇이 대기 상태로 보임 (낮음, 확실, T-26)
- 위치: `fleet_core.py` `robot_state`
- 지금: 옆 자리에서 복귀를 기다리는 로봇이 `IDLE`/`STANDBY`로 표시되다가 최대 60초 안에 스스로 출발
- 문제: 실기기 옆에 있는 사람에게는 예고 없는 출발
- 제안: `pending_goal`이 있으면 `YIELDING`으로 표시
- 조치:

## D. 그 밖의 중간 항목

### D1. `remote:=false`이면 관제가 pinky1만 앎 (높음, 확실)
- 위치: `real.launch.py:31-32`
- 지금: `remote:=false`일 때 등록 파일을 읽지 않아, `robots:=`가 없으면 로봇 목록이 `['pinky1']`이 됨
- 문제: 로봇을 손으로 띄우는 절차(REAL_ROBOT_GUIDE 3장)에서 pinky2·pinky3이 나타나지 않고 아무 안내도 없음
- 제안: 로봇 목록은 항상 등록 파일에서 만들고, `remote`는 SSH 기동 여부만 결정
- 조치:

### D2. 구간 중 취소된 로봇이 "비켜 주기" 대상에서 빠짐 (중간, 확실)
- 위치: `fleet_core.py:1132-1137` `_claim_vertex` (2026-11-17 재확인: `heading`을 지우는 곳은 `_move_to_vertex` 1270행뿐)
- 지금: 로봇이 대기 상태로 노드를 다시 잡을 때 `heading`을 지우지 않음. `_make_way`와 `_clear_exit`는 `heading`이 있는 로봇을 제외함
- 제안: `_claim_vertex`에서 `robot.heading = ''`
- 조치:

### D3. 임무가 보류된 로봇을 4초 뒤 비킨다고 계산 (중간, 확실)
- 위치: `fleet_core.py:455-469` `_hold_estimate`
- 지금: 임무가 `SUSPENDED`인 채 서 있는 로봇(예: `NAV2_FAILED` 뒤)에 4.0초를 돌려줌
- 문제: 다른 로봇이 4초 뒤 통과하는 계획을 세우고, 실제로는 락에 막혀 정체와 재계획을 반복
- 제안: 임무가 보류됐거나 오프라인이면 무한대
- 조치:

### D4. AMCL이 죽어도 굳은 위치를 계속 보고 (높음, 확실, 기존 R1-2)
- 위치: `mobile_controller.py:199-208` `_tf_pose`
- 지금: 최신 TF를 시각 확인 없이 씀. `have_truth`는 한 번 참이 되면 내려가지 않음
- 제안: 0.5초 넘은 변환은 쓰지 않고 `LOCALIZATION_STALE`을 보고, 직접 주행은 정지. `except`는 `tf2_ros.TransformException`으로
- 정정(2026-11-17): 중간 → 높음. 굳은 위치가 새 상태 보고로 나가 관제의 정지·통행 판단에도 쓰임
- 조치(2026-11-17~18): **수정 완료(실기기 확인 필요).** 최신 TF가 `tf_stale_sec`(1.0초, 제안의 0.5초보다 느슨하게 둠)보다 오래되면 주행을 세우고(`WAIT_LOC`) `SENSOR_ERROR`를 보고(`LOCALIZATION_STALE`은 오류 코드표에 없어 기존 코드 사용). 갱신이 돌아오면 이어서 감. `except`를 `TransformException`으로 좁힘. 가짜 TF로 7건 통과. Pinky의 AMCL 갱신 주기에서 오탐이 없는지는 확인하지 못함. 복구 절차(재위치 추정)는 넣지 않음. 검증은 [TROUBLESHOOTING.md](TROUBLESHOOTING.md) T-29

### D5. `stop_all.sh`가 PC의 다른 ROS 작업도 끔 (중간, 패턴 확실 / 로봇 잔류는 추정)
- 위치: `scripts/stop_all.sh`
- 지금: `robot_state_publisher`, `lifecycle_manager`, `controller_server`, `nav2_map_server`, `nav2_costmap_2d`, `rviz2 -d` 같은 이름으로 PC 전체에서 종료. `lib/frybot`은 `robot_remote`도 맞히는데, 로봇 정지에는 5초쯤 걸리고 강제 종료는 3초 뒤
- 문제: Open-RMF 작업 공간(`~/rmf_jazzy_ws`)의 노드도 같이 꺼짐. 로봇 정지가 끝나기 전에 원격 프로세스가 죽을 수 있음
- 제안: frybot 프로세스만 대상으로(런치 프로세스 그룹, 또는 `frybot_` 경로·네임스페이스로 한정). `robot_remote`는 강제 종료 대상에서 빼거나 끝에 `robot_remote --all --stop`을 명시적으로 호출
- 조치:

### D6. 관리자 API에 인증이 없고 다른 웹 페이지에서도 호출 가능 (높음, 확실, 기존 R7-1)
- 위치: `frybot_web/frybot_web/httpd.py:21, 26-30`, `/api/admin`
- 지금: `Access-Control-Allow-Origin: *`이고 OPTIONS가 `Content-Type`을 허용. `0.0.0.0`에 열림
- 문제: 같은 Wi-Fi의 기기뿐 아니라 운영자 브라우저에 열린 다른 웹 페이지도 `RESUME`(비상 정지 해제)이나 `MOVE_TO_VERTEX`를 보낼 수 있음
- 제안: CORS 헤더와 OPTIONS 처리를 없앰(화면은 같은 출처에서 제공됨). 관리자 명령에 런치 인자로 정한 토큰을 요구
- 정정(2026-11-17): 중간 → 높음. 비상 정지 해제와 이동 명령의 접근 통제 문제
- 조치(2026-11-17~18): **수정 완료.** CORS 헤더와 OPTIONS 응답을 삭제하고, POST는 `application/json`과 같은 출처만 받음. `/api/admin`은 관제 PC(localhost)는 그대로, 다른 주소는 `admin_token`(런치 인자)이 맞을 때만 받음. 실기기 런치는 토큰이 없으면 관제 PC에서만 받음. 시뮬은 전과 같음. `curl`로 응답 코드 확인, 관리자 화면 렌더링 확인(토큰 입력 창은 눌러 보지 못함). AI 결과 수신 포트(8100)는 그대로임. 검증은 [TROUBLESHOOTING.md](TROUBLESHOOTING.md) T-29

### D7. SSH 비밀번호가 패키지 안에 있음 (중간, 확실, 기존 R7-2)
- 위치: `frybot_bringup/config/robots.yaml:8`, `frybot_bringup/setup.py:9`
- 지금: 비밀번호가 든 파일이 설치되고(`install/.../share`), 아직 git에 없는 파일이라 그대로 커밋하면 저장소에 들어감
- 제안: 패키지에는 비밀번호 없는 예시 파일만 두고 실제 값은 `~/.config/frybot/robots.yaml`에서만 읽음(이미 그 경로를 우선 읽음)
- 조치:

### D8. 배포가 실행 중인 로봇 위에 덮어씀 (중간, 확실)
- 위치: `frybot_bringup/frybot_bringup/robot_remote.py:303, 310-328`
- 지금: `rsync -az --delete`로 네 패키지를 덮어씀. 로봇 프로그램을 멈추지 않음. 빌드가 실패하면 새 소스와 옛 빌드가 섞임. `--check`는 `FleetHeartbeat` 존재만 확인
- 문제: 로봇에만 있는 파일(보정값, 로봇에서 고친 설정)이 경고 없이 지워짐. 실행 중인 노드의 코드가 바뀜
- 제안: 배포 전에 정지. 로봇 전용 파일 보호 규칙 추가. 빌드 실패를 분명히 표시
- 조치:

### D9. 실측 지도에서 접수·주문이 "만석"처럼 거절됨 (중간, 확실)
- 위치: `frybot_control/frybot_control/restaurant.py:26, 41-47, 60`, `frybot_web/static/index.html`, `reception.html`, `table.html`
- 지금: 실측 지도에서는 테이블 목록이 비어 있어 접수가 "지금은 맞는 빈 테이블이 없습니다"로 거절됨. 첫 화면은 테이블 6개와 손님 시뮬레이터(8090) 링크를 항상 보여 줌
- 제안: 실측 지도에서는 "테이블·작업 지점이 정의되지 않음"을 돌려주고, 첫 화면의 테이블 버튼과 8090 링크를 숨김
- 정정(2026-11-17): 원인(실측 지도에 식당 업무가 연결되지 않음)은 G1. 이 항목은 G1의 하위 작업
- 조치:

### D10. 실행 기록에 관제 설정과 로드맵 버전이 없음 (중간, 확실)
- 위치: `central_control_node.py:33-35`, `frybot_control/frybot_control/replay_run.py:296, 464-471`
- 지금: 기록에는 시나리오, 지도 이름, 로봇, 시뮬 여부만 있음. `replay_run`은 기본 설정으로 재현하고 `simulation` 값을 읽지 않음. `--find-yield`의 기본 모델은 시뮬 값(0.08 m/s, 지연 0)
- 문제: 실기기 실행의 설정이 달랐거나 같은 이름의 지도가 편집됐어도(v002는 편집 중) 알 수 없음
- 제안: 기록에 관제 파라미터와 `roadmap.json` 해시를 넣고, 재현할 때 다르면 경고. `--find-yield` 기본 모델을 실측값으로
- 조치:

### D11. 코드 머리말과 README에 옛 실행 예시가 남아 있음 (낮음, 확실)
- 위치: `src/frybot/README.md:243`, `frybot_bringup/launch/real.launch.py:10`, `frybot_mobile/launch/robot.launch.py:4,6`
- 지금: `poses:=pinky1:A2,pinky3:W3` 예시(pinky1의 홈은 2026-11-17부터 W1). `robot.launch.py` 머리말은 `map:=$HOME/frybot_map/store.yaml`과 "충전대에서 출발"을 안내
- 문제: 예시대로 띄우면 로봇을 놓은 자리와 초기 자세가 어긋남
- 제안: 현재 절차(`map_id:=test_map_v001`, `poses:=pinky1:W1,...`)로 수정
- 참고: `docs/REAL_ROBOT_GUIDE.md`와 `docs/COMMANDS.md`는 2026-11-17에 새로 써서 해당 없음
- 조치:

## E. 낮음 (묶음)

| 위치 | 지금 | 제안 |
|---|---|---|
| `pinky_driver.py:58-84, 218-221` | 모터 초기화가 실패해도 프로세스가 살아 있어 런치가 정상처럼 보임 | 실패하면 프로세스 종료 |
| `mobile_controller.py:83, 134-136` | 배터리 값의 수신 시각을 보지 않아 드라이버가 죽으면 100%로 남음. 단위(0~100)는 미확인(R2-3) | 15초 넘게 끊기면 오류 보고 |
| `nav2_store.yaml:47, 59` | 속도 0.08 m/s인데 실측 기울기는 0.135. 충돌 예측 0.3초 | 실기기에서 속도·이동량을 먼저 측정 |
| `nav2_store.yaml:43, 115` (R2-2) | 도착 허용 오차 1.5 cm, 지도 해상도 5 cm | 측정 뒤 0.03, 0.05로 |
| `mobile_controller.py:103`, `navigator.py:41`, `layout.py:131` | 실측 지도에는 도크가 없는데 도킹 서버와 아루코 검출이 Pinky에서 계속 뜸. `roadmap.json`의 `docking_candidates`는 아무 코드도 읽지 않음 | 도크가 없으면 띄우지 않거나 문서에 명시 |
| `mobile_controller.py:812-820` (R1-5) | 노드 종료 시 정지 명령이 없음 | 종료 처리에서 0 속도 |
| `mobile_controller.py:802-806` (R1-4) | 실기기에서 가짜 바퀴 관절값을 발행 | `kinematic`이 아니면 발행하지 않음 |
| `robot.launch.py:107` | `ai_host` 기본값이 `127.0.0.1`이라 실기기 카메라 UDP가 로봇 자신에게 감 | 기본값을 비움 |
| `fleet_core.py:1321-1326` (R5-2) | 전체 비상 정지 명령이 없음. 비상 정지를 풀면 옛 목적지로 바로 출발 | `ESTOP_ALL` 추가, 재개와 재출발 분리 |
| `central_control_node.py:111-114` | 관리자 명령의 서비스 호출에 시간 제한이 없음 | 시간 제한 추가 |
| `runlog.py:31-37` | 여러 스레드가 락 없이 같은 기록 파일에 씀(줄이 섞일 수 있음, 추정) | 락 추가 |
| `fleet_core.py:1127-1130` | 대기 상태 보고마다 거리 확인 없이 가장 가까운 노드를 점유(추정) | 노드 근처일 때만 |
| `robot_remote.py:100-107` | PC에 도메인 값이 없으면 로봇이 자기 설정을 그대로 씀(지금은 PC와 로봇 모두 73이라 해당 없음) | PC의 실제 값을 명시적으로 전달 |
| `robot_remote.py:214-216` | 로봇 런치가 죽으면 남은 프로세스를 정리하지 않음 | 한 번 정지 스크립트 실행 |
| `scripts/relocalize.py:13` | 지도가 `test_map_v001`로 고정 | `--map-id` 인자로 |
| `launch/fleet_rviz.launch.py` | pinky1·pinky2만 표시 | `robots:=` 인자와 `fleet_rviz_config` 사용 |

## F. 앞선 리뷰와 수정 기록의 남은 항목

A~E에 들어 있지 않은 것만 적습니다.

| 번호 | 위치 | 지금 | 제안 | 조치 |
|---|---|---|---|---|
| R0-8 | `frybot_interfaces/msg/RobotStatus.msg` | 로봇이 `YIELD`, `YIELD_BLOCKED` 상태를 보내는데 주석의 상태 목록에 없음 | 주석에 추가 | 해당 없음(2026-11-17 확인): 주석에 이미 있음(`RobotStatus.msg:4`) |
| R1-6 | `mobile_controller.py` `_navigate` | 경로의 첫 노드(`route[0]`)까지는 허가 없이, 거리 제한 없이 이동. 관제가 1 m 이내 노드만 주지만 로봇 쪽 방어는 없음 | 로봇에서도 거리 상한 확인 | |
| R1 | `mobile_controller.py:577` `_rotate` | 도킹 회전·트림에 시간 제한이 없음(`_creep`은 4초) | 시간 제한 추가 | |
| R2-1 | `frybot_mobile/config/nav2_store.yaml` | `amcl.set_initial_pose` 주석("제어기가 초기 자세를 보냄")과 머리말("시뮬과 실기기에서 그대로 사용")이 실측 지도의 실제 동작과 다름 | 주석을 실제에 맞춤 | |
| R2 | `navigator.py:21` | 임시 파라미터 폴더(`mkdtemp`)를 지우지 않음 | 종료 때 삭제하거나 고정 경로 사용 | |
| R5-5 | `fleet_core.py` | 양보 기준(1.4배, 0.4 m)이 실측 지도에서 검증되지 않음. 서 있는 로봇이 길을 막는 조합의 41%가 기준 미만으로 우회 | 실기기 결과를 본 뒤 기준 조정 | |
| R0-7 | `frybot_arm/arm_controller.py` | 조리 팔 대역이 취소를 받지 않아 비상 정지가 조리 팔 작업을 멈추지 못함 | 취소 지원 | |
| 규칙 | 10곳: `mobile_controller.py`, `aruco_dock_detector.py`, `dynamixel_driver.py`, `task_manager_node.py`, `central_control_node.py`, `httpd.py`(2), `runlog.py`, `ai_server.py`, `planners/rmf.py` | 이유 없는 `except Exception` | 구체적인 예외 타입으로 | |
| 규칙 | `schedulers/rmf_task.py:60` | 루프 변수 `t`를 묶지 않은 함수(B023). 버그 여부 확인 필요 | 기본 인자로 묶음 | |
| 11-16 | `scripts/relocalize.py` | 손으로 옮긴 로봇의 위치 재설정이 임시 스크립트뿐. 관제 웹에서 초기 자세를 지정할 수 없음 | 패키지 명령으로 넣고 웹에서도 지정 | |

## G. 설계 자료와 대조해 나온 항목 (2026-11-17)

`dev_docs/`의 설계 자료와 코드를 대조한 결과입니다. Claude와 Codex(GPT-6.1-Sol)가 따로 검토한 뒤 서로의 결과를 맞춰 보았습니다. "재현"이라고 적은 것은 Codex가 파일을 만들지 않고 메모리 안에서 실행해 본 것이며, 실기기에서 확인한 항목은 없습니다.

### G1. 실측 지도에서 식당 업무(접수·주문·조리·서빙·회수)가 막힘 (높음, P6)
- 위치: `frybot_control/frybot_control/restaurant.py:25-26`, `fleet_core.py:220-222` `submit_task`
- 지금: 실측 지도(`map_id` 지정)에서는 테이블 목록이 비고, Task Manager가 `GUIDE`·`SERVE`·`COLLECT`·`COOK` 제출을 예외로 거부함. 조리 대역도 `map_id`가 없을 때만 뜸(`real.launch.py:53`)
- 문제: 실기기에서는 노드 간 이동(`MOVE_TO_VERTEX`)만 됨. SR-001~005, 014, 018~019, 040~042가 실기기 경로에서 동작하지 않음
- 제안: `roadmap.json`에 입구, 테이블 안내·서빙 지점, 픽업, 퇴식구, 충전 위치를 등록하고 가상 매장과 같은 업무 프로그램(`_program`)을 쓰게 함. D9(거절 문구)는 이 항목의 하위 작업. 실기기에서 켜기 전에 A·G2~G5가 먼저
- 조치:

### G2. 가용 판정이 로봇 오류를 보지 않음 (높음, P1, P7)
- 위치: `fleet_core.py:282-283` `_available`, `:1305`
- 지금: 온라인, 비상 정지, 임무, 팔 작업, 배터리만 봄. `RobotStatus.error`(예: `DRIVE_ERROR`)가 있어도 새 임무를 배정함(Codex가 메모리 안 실행으로 재현)
- 문제: 주행 오류가 난 로봇에 손님 안내나 서빙이 배정됨. 기기별 상태 흐름의 자체 점검·복구 점검·운용 제외 전이(`INITIALIZING`, `RECOVERY_CHECK`, `OUT_OF_SERVICE`)도 코드표만 있고 배정을 막는 데 쓰이지 않음
- 제안: 오류 보고, 부착 팔 오류, 보고 신선도(A3), 운용 제외를 배정 조건에 넣음. 미관측은 `UNKNOWN`으로 둠
- 조치(2026-11-17~18): **수정 완료.** 로봇 오류나 서빙 팔 오류(정상 보고가 와야 풀림)가 있으면 배정하지 않고, 화면의 불가 사유에 `ERROR`를 추가. 관리자의 이동·홈 복귀는 `DRIVE_ERROR`만 허용해 복구 통로를 남김. 끊긴 로봇과 오류 로봇의 임무는 재배정 비교에서도 제외. 모의로 확인. 운용 제외(`OUT_OF_SERVICE`) 전이와 `UNKNOWN` 처리는 남음. 검증은 [TROUBLESHOOTING.md](TROUBLESHOOTING.md) T-29

### G3. 중단·재배정·취소·재개가 실제 정지 확인 전에 확정됨 (높음, P1, P6)
- 위치: `fleet_core.py:1518-1602` `command`, `task_manager_node.py:98-109`
- 지금: `PAUSE`는 취소 요청만 보내고 바로 성공을 돌려줌. `REASSIGN`은 `carrying`만 보고 `pi=0`으로 되돌림. `CANCEL_TASK`는 `CANCELED`를 먼저 발행하고 로봇을 뗌. `RESUME`·`RETRY_TASK`는 제한을 풀고 바로 재시도(Codex가 취소 응답 전 재배정 수락을 재현)
- 문제: 이전 로봇이 아직 움직이는 중에 같은 임무가 다른 로봇에 배정될 수 있음. SR-034, Sequence 12와 다름
- 제안: 요청, 정지 확인 중, 정지 확인, 취소 확정을 나누고 액션 결과를 받은 뒤에만 재배정·취소를 확정. 정지 해제와 재출발도 분리(E의 R5-2와 함께). 조리 팔 취소(F의 R0-7)와 묶음
- 조치:

### G4. 실기기 안내에서 동행 관측이 없어도 출발함 (높음, P1)
- 위치: `frybot_mobile/frybot_mobile/mobile_controller.py:72, 254-279`, `frybot_mobile/launch/robot.launch.py:97`
- 지금: `guest_track_required` 기본값이 `False`이고 실기기 런치가 켜지 않음. 추적 값이 한 번도 오지 않으면 확인 없이 후진 안내
- 문제: SR-006~008, Sequence 03과 다름. 사람 옆에서 뒤로 가는 동작인데 손님 위치를 모르는 채 진행. 실기기 추적 입력(카메라·AI)도 아직 없음
- 제안: 실기기 런치에서 `true`로 두고 관측이 없으면 안내를 보류. B6의 "이탈 검사 없이 진행" 부분은 이 항목으로 옮김
- 조치(2026-11-17~18): **수정 완료(실기기 확인 필요).** `robot.launch.py`의 `guest_track_required` 기본값을 `true`로 함(`false`로 끌 수 있음). 추적 값이 없으면 `PAUSED_GUEST`로 기다리다 `GUEST_LOST`. 런치 인자 전달만 확인했고, 실측 지도에는 아직 안내 임무가 없어(G1) 실기기 동작은 확인하지 못함. 실기기 추적 입력은 여전히 없음(H7). 검증은 [TROUBLESHOOTING.md](TROUBLESHOOTING.md) T-29

### G5. 직접 속도 명령을 공통으로 검사하는 충돌 감시가 없음 (높음, P1)
- 위치: `mobile_controller.py:692-725`(직접 주행), `:800` 부근, `frybot_mobile/config/nav2_store.yaml:59`, `navigator.py:39`
- 지금: Nav2 주행 구간에는 RPP의 충돌 예측이 있음. `mobile_controller`가 `cmd_vel`을 직접 내는 회전, 양보 후진, 도킹 미세 이동은 뒤쪽 라이다 검사(양보 후진)뿐이고 Nav2 Collision Monitor 같은 독립 감시 노드가 없음
- 문제: 관제나 계획 계층과 무관하게 로봇 자체에서 감속·정지하는 마지막 방어가 없음. A1(드라이버 시간 초과)과는 별개의 방어
- 제안: `cmd_vel` 경로 끝에 Collision Monitor를 두어 Nav2와 직접 주행 명령을 모두 지나가게 함. 소프트웨어만으로 안전 인증이 되지는 않음(확인 필요: 실기기 정지 거리)
- 조치:

### G6. 적재 상태별 속도·가속도 제한이 없음 (중간, P4)
- 위치: `mobile_controller.py:493, 558, 755` `_set_speed_limit`, `frybot_interfaces/action/NavigateRoute.action`
- 지금: `mode`는 `NORMAL`/`GUIDE`/`YIELD`뿐이고 속도 제한은 안내 구간에만 걸림. Nav2에 기본 속도·각가속도 제한은 있으나 직접 속도 발행은 이를 거치지 않음. `velocity_smoother`도 없음
- 문제: 음식이나 식기를 실은 채 빈 로봇과 같은 속도·가감속으로 움직임
- 제안: 적재 여부를 경로에 실어 보내고 직진·회전·가감속 상한을 따로 둠. 실제 적재 주행 시험 전에 필요
- 조치:

### G7. 익힘 판정이 없거나 미달이어도 조리를 진행함 (중간, P6)
- 위치: `fleet_core.py:1672-1695` `_cook_tick`
- 지금: AI 결과가 5초 안에 없으면 `DONE`으로 대체. `UNDERCOOKED`도 두 번 재시도한 뒤에는 다음 공정으로 넘어감
- 문제: State Diagram(음식 `COOKING → READY` 조건), Sequence 05p와 다름. 지금은 조리 팔이 대역이라 실물 영향 없음. 실제 조리 팔을 연결하기 전에는 높음
- 제안: 미수신과 미달은 보류(`SUSPENDED`)로 두고 관리자 확인. 기준값과 승인 주체는 설계에서 미정
- 조치:

### G8. QR 이용 종료 판정이 등록 정보와 관측 신선도를 보지 않음 (중간, P6)
- 위치: `restaurant.py:230-247` `on_seat_qr`·`tick`, `central_control_node.py:182-185`
- 지금: 등록된 좌석 수가 아니라 AI 요청의 `seats` 값과 비교. 빈 좌석 관측이 한 번 오면 새 관측이 없어도 8초 뒤 이용 종료를 시도(Codex가 재현)
- 문제: SR-039, Sequence 07과 다름. 카메라가 가려지거나 끊겨도 손님이 있는 테이블이 종료될 수 있음
- 제안: 등록 좌석 수와 대조. 관측이 끊기면 종료 타이머를 무효화하고 확인 보류(공석이나 점유로 확정하지 않음)
- 조치:

### G9. 음식 항목에 `LOADED` 상태가 없음 (중간, P6)
- 위치: `restaurant.py:196-197`, `fleet_core.py:370`
- 지금: 임무의 `LOADED` 이벤트를 받으면 음식 상태를 바로 `SERVING`으로 저장. 임무에는 `carrying`이 있으나 음식 상태·DB에는 대응이 없음
- 문제: State Diagram V0.04("이번 보강")와 다름. 적재 후 출발 전 대기와 이동 중을 구분하지 못함
- 제안: `LOADED`를 저장하고 테이블 이동을 시작할 때 `SERVING`으로 바꿈
- 조치(2026-11-18): **수정 완료.** 작업 지시서 W2. 음식 상태 `LOADED`를 저장하고, 관제가 적재 뒤 테이블행 경로의 첫 구간을 지날 때 `SERVING` 임무 이벤트를 한 번 발행(`Task.serving_sent`). 주문 상태는 `LOADED`를 `SERVING`으로 묶어 바뀌는 시점이 전과 같음. 보류 후 재개는 `LOADED`로 돌아옴. 경량 시뮬 demo에서 음식 4개 모두 `EVT_LOADED → EVT_SERVING → EVT_DELIVERED`, `fleet_bench` rush·bottleneck 수치 변화 없음(`run_20261118_114055`)

### G10. 회수 중인 테이블을 확인 없이 이용 가능으로 바꿀 수 있음 (중간, P6)
- 위치: `restaurant.py:113-120, 255-257`
- 지금: 관리자 `SET_TABLE AVAILABLE`이 `COLLECTING` 테이블을 진행 중인 회수 임무 확인 없이 해제. 전달 이력이 없는 이용 종료는 회수 대기 없이 바로 해제
- 문제: 회수 로봇이 가고 있는 테이블에 새 손님이 배정될 수 있음. SR-029, SR-031
- 제안: 진행 중인 `COLLECT` 임무가 있으면 거부하거나, G3의 정지 확인을 거친 뒤에만 해제
- 조치:

### G11. 주문 요청에 식별자가 없어 중복 접수를 가릴 수 없음 (중간, P6)
- 위치: `frybot_interfaces/srv/PlaceOrder.srv`, `restaurant.py:58-82`, `frybot_web/frybot_web/web_service_node.py:166-175`, `frybot_web/static/table.html:79-87`
- 지금: 호출마다 새 주문과 조리 임무를 만듦. 웹 요청이 시간 초과하면 화면은 다시 주문할 수 있는 상태로 돌아감
- 문제: 응답만 유실되고 첫 주문이 접수된 경우 재주문으로 중복 조리. Sequence 10과 다름
- 제안: 요청 키와 접수 결과 조회를 두고, 통신 실패를 미접수로 취급하지 않음. 키 방식은 설계에서 미정
- 조치:

### G12. 임무 후 복귀·충전·재가용 절차가 축약됨 (중간, P6, P7)
- 위치: `fleet_core.py:359-366, 477-479` `_go_home`, `mobile_controller.py:282-306` `_real_charging`
- 지금: 임무가 끝나면 바로 `r.task=None`이라 복귀 도중에도 가용. 실측 지도에서는 `_go_home`이 바로 반환(자동 복귀 없음). 실제 충전은 배터리 상승 추정이고, 마지막 배터리 기록의 신선도를 보지 않음(N2)
- 문제: Sequence R1(복귀·도킹·실제 충전·재가용을 각각 확인)과 다름. SR-042
- 제안: 자동 복귀 구현, 충전 확인, 복귀 중 재배정 허용 조건을 나누어 다룸. 복귀 중 재배정을 허용할지는 정책 결정. E의 배터리 수신 시각 항목과 함께
- 조치:

### G13. 조리 팔 상태를 보고가 아닌 명령으로 추정함 (중간, P7)
- 위치: `fleet_core.py:1330-1357` `_cook_arm_device`
- 지금: 보고를 한 번도 받지 못해도 `IDLE`/`COOKING`과 `NO_ERROR`로 표시. 보고가 있어도 오류가 없으면 보고된 `state` 대신 명령으로 상태를 다시 만듦
- 문제: 기기별 상태 흐름("미관측을 오류 없음으로 채우지 않는다")과 다름
- 제안: 무보고는 `UNKNOWN`, 유효한 보고는 그대로 씀. 배정 차단은 G2에서
- 조치:

### G14. 보류·복구 기록이 저장되지 않고 재시작 복원이 없음 (중간, P6)
- 위치: `restaurant.py:25-29, 145-148, 285-288`, `frybot_control/frybot_control/db.py:26-30`
- 지금: incident의 해결 결과와 음식의 `hold_from`은 메모리에만 있음. 재시작하면 상태와 ID가 0부터 다시 시작하고 DB에서 읽어 오지 않음
- 문제: 재시작 뒤 진행 중이던 주문·임무·적재 상태를 알 수 없음. Logical Data Model의 `hold_from_status`, `incident.result`와 다름
- 제안: 변경 시점에 저장하고, 재시작 때 상태·ID·임무 소유를 복원. 복원했다고 자동 재개하지는 않음. H2와 연결
- 조치:

### G15. 테이블 화면이 전달 실패를 "전달 완료"로 표시할 수 있음 (낮음, P8)
- 위치: `frybot_web/static/table.html:107-122` `renderArrival`
- 지금: 서빙 임무가 `IN_PROGRESS`·`UNLOADING` 조건에서 빠지면 실제 `DELIVERED` 여부와 무관하게 완료 표시. 임무가 `SUSPENDED`가 되어도 같음
- 문제: Sequence 06("실패·불명을 성공으로 표시하지 않음")과 다름
- 제안: 음식 항목의 `DELIVERED` 상태로 판정
- 조치:

### G16. `device_state.py` 주석이 옛 설계 버전 기준 (낮음)
- 위치: `frybot_control/frybot_control/device_state.py:1`
- 지금: 주석은 "기기별 상태 흐름 V0.07", 설계 자료는 V0.10
- 문제: 코드표(STA 14개, ERR 11개)는 V0.10과 같음. 전이가 없는 문제는 G2·G3에서 다룸
- 제안: 주석의 버전을 고침
- 조치:

### G17. `frybot_mobile/package.xml`에 직접 쓰는 의존성이 빠져 있음 (낮음, P7)
- 위치: `frybot_mobile/package.xml:10-30`, `mobile_controller.py:20-44`
- 지금: `geometry_msgs`, `nav_msgs`, `sensor_msgs`, `std_msgs`, `tf2_msgs` 등을 import하지만 선언이 없음
- 문제: 지금 로봇에는 이미 설치되어 있어 동작함. 새 로봇에 배포할 때 실패할 수 있음(확인 필요)
- 제안: 선언을 추가하고 깨끗한 환경에서 배포를 한 번 확인(D8과 함께)
- 조치:

## N. 교차 검토에서 Codex가 더한 항목

### N1. 실기기 구성에서 대역 팔의 성공이 물리 완료로 쓰임 (높음, P6)
- 위치: `frybot_bringup/launch/real.launch.py:18-19, 53-57, 69-71`, `mobile_controller.py:892-912` `_arm_job`, `frybot_arm/frybot_arm/arm_controller.py:59-84`
- 지금: 서빙 팔과 조리 팔은 정한 시간이 지나면 성공을 돌려주는 대역. `sim_cooking` 기본값이 `true`. 카메라는 영상 대신 JSON 값을 보냄
- 문제: 적재·전달·반납 "성공"이 실제 물건 이동의 근거가 아님. SR-016~017, 021, 026, 040~041
- 제안: 실기기 구성에서는 대역 결과를 완료 근거로 쓰지 못하게 막고, 실제 적재·전달·반납 확인을 따로 구현. 실제 장치 연결 방식은 H7. B4와 함께
- 조치:

### N2. 충전 판정이 배터리 기록의 신선도를 보지 않음 (중간, P7)
- 위치: `mobile_controller.py:282-306`
- 지금: 배터리 기록 정리는 새 메시지가 올 때만 하고, 충전 판정은 마지막 기록이 지금도 유효한지 보지 않음
- 문제: 배터리 노드가 죽으면 옛 값으로 충전 중·가용을 판단
- 제안: 수신 시각을 확인하고 끊기면 불명으로 보고. G12와 E의 배터리 항목에 묶음
- 조치:

### N3. `fleet_core.py`와 `mobile_controller.py`에 책임이 몰려 있음 (낮음)
- 위치: `fleet_core.py`(1,786줄: 배정·경로·통행·조리), `mobile_controller.py`(970줄: 주행·도킹·추적·팔·카메라 대역)
- 지금: 설계의 제어 역할(Controller, Navigator, Arm Controller)이 한 클래스에 있음
- 문제: 한 기능을 고칠 때 다른 기능에 영향이 가기 쉬움
- 제안: 따로 리팩터링하지 않고, 관련 기능을 고칠 때 그 부분만 나눔
- 조치:

## H. 설계 쪽 결정이 먼저 필요한 것

코드를 고치기 전에 팀이 정해야 하는 항목입니다. 안전 항목(A, G2~G5)은 이 결정을 기다리지 않습니다.

| 번호 | 결정할 것 | 지금 | 걸리는 항목 |
|---|---|---|---|
| H1 | 기준 문서 | Conceptual/Logical Data Model은 State Diagram v3 기준이라 State Diagram V0.04·Sequence V0.09와 어긋남(주문 `ARRIVED`·고객 수령·관리자 정리 대 음식 `LOADED`·임무 `DONE`·자동 회수). 코드는 상태도 쪽에 가까움 | G9, G14, H2 |
| H2 | DB | 설계는 서버 PC의 MySQL 8.4. 코드는 실행 폴더의 SQLite이고 `location`, `menu`, `robot`, `vision_result`, `system_config`, `schema_version` 테이블과 외래키·상태 제약·로봇당 진행 임무 유일성이 없음(`db.py:8-17`). 어느 쪽으로 가든 누락 엔터티와 제약은 수정 대상 | G14 |
| H3 | Master Controller 책임 | 설계는 Master가 A/B 인계·간섭을 조율. 코드는 Task Manager가 조율하고 Master는 `arm_id`로 나누는 중계(`master_controller.py:6`). 팔 상태도 Master를 거치지 않고 `/fleet/arm_status`로 감 | G13 |
| H4 | 양념치킨·볶음밥의 최종 조리대 배치 팔 | 설계는 A(Sequence 05b·05c), 코드는 B(`fleet_core.py:1615-1623`) | G7 |
| H5 | 영업 준비(Sequence 01)·영업 마감(14) | 해당 코드 없음. 접수에 영업 상태 검사가 없음(`restaurant.py:35`). 범위와 별개로, 준비가 확인되지 않은 상태의 자동 접수 차단은 작업으로 남김 | G1 |
| H6 | 만석 대기(`WAITING`, 대기 순번) | 코드는 `REJECTED`로 끝냄(`restaurant.py:38-47`). 데이터 모델에서도 팀 확인 사항(Q4)이라 누락으로 단정하지 않음 | — |
| H7 | 실제 서빙 팔·조리 팔·카메라·AI 추론의 연결 방식 | 전부 대역. AI 서버는 임계값 모의이고 추론·학습 경로가 없음 | N1, G4 |

## 원본 리뷰에서만 남아 있던 기록

중복 본문은 위 항목에 통합했습니다. 다음은 원본의 고유 내용이며, 후속 정정과 다른 옛 판단은 당시 이력으로만 읽습니다. 원문 전체는 `archive/docs_cleanup_2026-11-19/reviews_16_17/`에 보존합니다.

### 당시 기록: FryBot 코드 검토 결과 (실기기 기준)

- 작성: 2026-11-17
- 대상: `src/frybot`의 8개 패키지, `scripts/`, 실행 문서. 외부 저장소(`src/pinky_pro`, `src/mycobot_ros2`)는 제외
- 기준: 패키지는 실기기(`real.launch.py` → SSH → Pinky의 `robot.launch.py`, 실측 지도, `drive=nav2`, AMCL) 위에서 구성되어야 하고, 시뮬레이션은 같은 코드를 타는 사전 검증용이어야 함
- 방법: 로봇 쪽, 관제, 런치·웹 세 영역을 나눠 읽기 전용으로 검토. 높음·중간 항목 대부분은 해당 줄을 다시 확인함
- **이 문서는 검토 결과만 적은 것이며, 여기 적힌 수정은 하나도 적용하지 않았음.** 고칠 항목을 고른 뒤 수정함
- 실기기에서 실제로 일어나는지는 확인하지 못함. "확신"은 코드 경로를 따라가 본 정도를 뜻함(확실 = 경로 확인, 추정 = 실기기 확인 필요)
- 실측 근거: 2026-11-16 실기기 실행에서 구간 하나의 소요 시간은 약 2.27초 + 거리 ÷ 0.135 m/s (T-23)
- 경로는 `src/frybot/` 기준, 줄 번호는 작성 시점 값. 앞선 리뷰 번호(R0~R7)는 [CODE_REVIEW_CHECKLIST.md](CODE_REVIEW_CHECKLIST.md), T-번호는 [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
수정이 필요해 보이는 곳은 A 5건, B 6건, C 5건, D 11건과 낮음 항목입니다. "조치" 칸은 결정한 뒤 채웁니다.

### 당시 기록: A2. 시뮬레이션이 기본으로 실기기와 같은 네트워크·도메인을 씀 (높음, 코드 확실 / 발생 추정)

- 지금: 이 PC는 `ROS_DOMAIN_ID=73`으로 Pinky와 같은 도메인. 시뮬의 Task Manager와 `/pinky1..3` 이름이 실기기와 겹침

### 당시 기록: D2. 구간 중 취소된 로봇이 "비켜 주기" 대상에서 빠짐 (중간, 확실)

- 위치: `fleet_core.py:1132-1137` `_claim_vertex`

### 당시 기록: D11. 실기기 가이드에 옛 절차가 남아 있음 (낮음, 확실)

- 위치: `docs/REAL_ROBOT_GUIDE.md` 49, 55, 57, 60행과 3장(110-128행), `docs/COMMANDS.md:82`
- 지금: `map_id` 없이 띄우는 절차, 가상 매장 충전대 출발 위치, "관제 PC에는 RViz가 없다", "Nav2 3회 실패 후 직접 주행"(가상 매장에서만 해당) 등이 남아 있음
- 문제: 3장을 그대로 따라 하면 B4·D1대로 잘못 뜸
- 제안: 현재 절차로 수정

### 당시 기록: 낮음 (묶음)

| `robot_remote.py:100-107` | PC에 도메인 값이 없으면 로봇이 자기 설정을 그대로 씀(지금은 73이라 해당 없음) | PC의 실제 값을 명시적으로 전달 |

### 당시 기록: 앞선 리뷰의 미해결 항목 현재 상태

| 항목 | 상태 |
| R1-2 TF 시각 미확인 | 그대로 (D4) |
| R1-3 손님 이탈 검사가 시뮬 토픽 의존 | 그대로 (B6) |
| R1-4 가짜 바퀴 관절값 | 그대로 |
| R1-5 종료 시 정지 명령 없음 | 그대로 |
| R1-6 첫 노드까지 허가·거리 제한 없이 이동 | 그대로 |
| R2-2 도착 허용 오차와 지도 해상도 | 그대로 |
| R2-3 배터리 단위 | 미확인 |
| R5-1 오프라인 로봇의 경로·락 | 그대로 (A3) |
| R5-2 전체 비상 정지 없음 | 그대로 |
| R5-4 시간 모델 | 그대로 (B1) |
| R5-5 양보 기준(1.4배, 0.4 m) | 기본값 그대로 |
| R7-1 관리자 API 인증 | 그대로, 기록보다 범위가 넓음 (D6) |
| R7-2 비밀번호 | 그대로 (D7) |

### 당시 기록: 문제없다고 확인한 것

- T-25 수정(경량 시뮬의 자기 자세를 참값으로)은 `drive=nav2`에 영향 없음
- T-22의 정지 명령, 비상 정지와 관제 단절 시 0 속도 발행
- 허가 재발행, 옛 경로 번호와 역행 진행 무시, 수락 전 취소 처리
- T-24 수정(`FLIP_HOLD`, 상대가 양보 중이면 대기, `_clear_exit`)
- T-26 수정 중 `_yield_done`의 상대 목적지 확인과 시간 초과, `_retreat`의 `back` 조건, `tick` 경로의 물러서기 차단
- 지도 이름 `proto` 처리는 관제·웹·시뮬 런치에서 일관됨(B4 제외)
- `robot.launch.py`의 네임스페이스와 TF 분리, 내장 드라이버 구성은 원본(`pinky_bringup`)과 같음
- 양보 후진의 뒤쪽 라이다 검사(라이다 방향, 1초 넘은 스캔은 막힌 것으로 판정)
- AMCL 범위 설정이 지도 크기(41×22칸)에 맞음
- RViz가 뜨지 못해도 실기기 런치의 나머지는 계속 돎. `fleet_rviz_config`는 임의의 로봇 목록을 처리함
- SSH 비밀번호는 명령줄에 나오지 않음(askpass 사용). 한 로봇의 배포 실패가 다른 로봇을 막지 않음
- 웹: 정적 파일 경로 차단, 서비스 호출 4초 제한, 지도 선택 중복 요청 방지

### 당시 기록: 권장 순서

1. A1 (드라이버 시간 초과): 다른 안전 항목이 모두 여기에 기댐
2. A2 (시뮬 기본 네트워크)
3. C1, C2, D2: 한두 줄짜리이고 오늘 수정의 빈틈
4. B4, D1: 실기기 런치를 잘못 띄우는 경로
5. A3, A4, A5: 로봇이 끊기거나 Nav2가 죽었을 때의 처리
6. B1: 시간 모델. 주행 순서가 달라지므로 따로 다룸
