# 작업 지시서 통합 — 2026-11-18

> 2026-11-19: 11월 16~18일 실행 폴더(`runs/run_2026111[6-8]_*` 등)는 `archive/runs_2026-11-16_18/`로 옮겼습니다. 이 문서의 실행 이름은 그 폴더 아래에 있습니다.

번호별 지시서는 서로 다른 단계이므로 본문을 생략하지 않고 날짜별로 통합했습니다. 아래 기록은 당시 지시와 판단이며, 실측 결과는 날짜별 `REAL_TEST` 문서가 기준입니다. 이후 단계의 변경 지시를 함께 확인하세요.

- [지시서 1: W0~W3](#order-1)
- [지시서 2: W4~W6](#order-2)
- [지시서 3: W7~W9](#order-3)
- [지시서 4: W10](#order-4)
- [지시서 5: W11~W12](#order-5)
- [지시서 6: 실기기 R0~R7](#order-6)
- [지시서 7: 기동 지연 B0~B4](#order-7)

---

<a id="order-1"></a>

## 지시서 1: W0~W3

<!-- 원본: WORK_ORDER_2026-11-18_1.md -->

# FryBot 작업 지시서 (2026-11-18)

기획안(docs/2026-11-18_IMPROVEMENT_PLAN.md) 8장의 결정 4건에 대한 사용자 확정과, 그에 따른 수정 방법입니다.
수정 방법은 기획 세션이 코드를 읽고 정했고, 실제 수정은 검토 세션(부장)이 합니다. 기획 세션은 코드를 고치지 않았습니다.

## 0. 사용자 확정 사항

1. 반복 횟수와 통과 기준은 검토 의견의 제안값으로 시작한다. 결과가 지나치게 좋거나, 너무 나빠 달성이 불가능해 보이면 그때 고친다.
   - 마주침·알고리즘 비교는 조건당 5회, 안전 정지는 고장 종류당 3회
   - 보정 후 구간 ETA 비율 중앙값 0.8~1.2
   - 정지 반응은 설계값 + 0.5초 이내, 이동 거리 0.155 m 미만
   - 마주침에서 PLAN_FAIL 연속 3회 이상 0건, 30초 넘는 정지 0건
     - [W7에서 변경, 2026-11-18] 30초 정지는 계획에 없는 정지만 셈(의도된 대기는 따로 보고, docs/2026-11-18_WORK_ORDER.md#order-3)
     - [W4에서 변경, 2026-11-18] PLAN_FAIL 기준은 "같은 목적지의 계획 실패가 20초 넘게 이어지는 경우 0건"으로 바뀜 (docs/2026-11-18_WORK_ORDER.md#order-2)
2. 기준선 조합은 실기기가 아니라 모의 비교를 먼저 한다. 비교 방법은 지금 것을 써도 되고, 더 나은 방법이 있으면 기존 구현을 지우고 새로 만들어도 된다.
3. 상태 이름은 State Diagram v4(dev_docs/State Diagram V0.04.md)에 맞춰 코드를 고친다.
4. 비밀번호는 실기기 연결에 문제가 없다면 저장소 밖으로 옮긴다.

작업 순서는 W0 → W1 → W2 → W3입니다. 작업 공간 규칙(CLAUDE.local.md)은 그대로 적용됩니다: git add·commit 금지, 수정 표기 주석, 고치는 부분만 코딩 표준 적용, 끝나면 바뀐 파일 목록과 커밋 메시지 초안 보고.

## W0. 기준 결과 저장 (수정 전에)

W2·W3이 관제 동작을 바꾸지 않았는지 확인하는 기준입니다. 아래는 기획 세션이 2026-11-18에 현재 작업 트리로 실행한 값입니다(시간 모델은 기존 그대로, 씨앗 5개 평균).

명령: ros2 run frybot_control fleet_bench --scenario <이름> --seeds 5 --schedulers min_cost_eta_rh fifo_nearest --planners sipp independent_astar

| 시나리오 | 스케줄러 | 플래너 | 완료 | 전체 소요(s) | 주문→전달 평균(s) | 점유 대기(s) | 정체 | 계획 실패 | 최소 간격(m) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rush | min_cost_eta_rh | sipp | 5/5 | 374.3 | 129.26 | 0.46 | 0.0 | 2.0 | 0.16 |
| rush | min_cost_eta_rh | independent_astar | 5/5 | 412.28 | 147.68 | 194.34 | 54.6 | 16.8 | 0.16 |
| rush | fifo_nearest | sipp | 5/5 | 370.34 | 125.4 | 0.42 | 0.0 | 1.8 | 0.16 |
| rush | fifo_nearest | independent_astar | 4/5 | 662.26 | 148.9 | 336.96 | 108.2 | 17.6 | 0.16 |
| bottleneck | min_cost_eta_rh | sipp | 5/5 | 423.78 | 156.74 | 3.18 | 0.6 | 4.8 | 0.16 |
| bottleneck | min_cost_eta_rh | independent_astar | 5/5 | 459.02 | 156.76 | 201.12 | 58.4 | 15.6 | 0.16 |
| bottleneck | fifo_nearest | sipp | 5/5 | 470.28 | 162.54 | 0.58 | 0.0 | 1.6 | 0.16 |
| bottleneck | fifo_nearest | independent_astar | 4/5 | 688.52 | 173.5 | 343.56 | 110.4 | 17.4 | 0.16 |

명령: ros2 run frybot_control replay_run archive/runs_2026-11-16_18/run_20261116_175751
- 실제 구간 147개에서 맞춘 모델: 2.27초 + 거리 ÷ 0.135 m/s
- 소요 시간 모의/실제 중앙값: 기존 모델 0.53, 실측 모델 1.01

할 일: 같은 두 명령을 --csv로 다시 실행해 원본을 archive/mock_compare_2026-11/baseline/에 저장하고, 위 표와 같은지 확인합니다. 다르면 수정을 시작하지 말고 알려 주세요.

## W1. SSH 비밀번호를 저장소 밖으로 (R7-2)

### 확인한 사실

- robot_remote.py의 registry_file()은 ~/.config/frybot/robots.yaml이 있으면 그것을 먼저 읽습니다(25행, 36~41행). real.launch.py, robots.launch.py, robot_remote 모두 이 함수를 거칩니다.
- 따라서 같은 내용을 그 경로로 옮기면 읽히는 값이 같고, SSH 접속 방식(키 먼저, 다음에 비밀번호)도 그대로입니다. 로봇에는 frybot_bringup이 배포되지 않아(DEPLOY 목록) 로봇 쪽 변경은 없습니다.
- src/frybot/frybot_bringup/config/robots.yaml은 미추적이고 git 이력에도 없습니다. .gitignore에는 없습니다.
- install/frybot_bringup/share/frybot_bringup/config/robots.yaml은 build/frybot_bringup/config/robots.yaml을 가리키는 심볼릭 링크입니다.
- ~/.config/frybot/는 아직 없습니다.

### 수정

1. ~/.config/frybot/을 만들고(권한 700) robots.yaml을 그리로 옮깁니다(권한 600). 내용은 바꾸지 않습니다.
2. 패키지에는 비밀번호가 없는 config/robots.example.yaml을 둡니다. 주소는 예시 값, password는 빈 값으로 하고 "~/.config/frybot/robots.yaml로 복사해 채운다"는 설명을 머리말에 적습니다.
3. .gitignore에 src/frybot/frybot_bringup/config/robots.yaml을 추가합니다.
4. 등록부가 없을 때의 안내를 넣습니다. 지금은 파일이 없으면 remote.registered()가 OSError를 삼켜 빈 목록을 돌려주므로, real.launch.py가 아무 말 없이 관제만 띄우고 로봇을 기동하지 않습니다. robot_remote는 traceback으로 끝납니다.
   - robot_remote.py: 등록부 파일이 없으면 찾은 경로와 예시 파일 위치를 한 줄로 알리고 종료 코드 1로 끝냄
   - real.launch.py, robots.launch.py: remote가 켜져 있는데 등록부가 없으면 같은 안내를 로그로 남김(동작은 지금처럼 관제만 기동)
5. 남은 사본을 지웁니다: build/frybot_bringup/config/robots.yaml과 install 쪽의 끊어진 링크. frybot_bringup을 다시 빌드합니다.
6. 문서를 맞춥니다.
   - src/frybot/README.md의 폴더 설명과 실기기 절(등록 위치를 ~/.config/frybot/robots.yaml로)
   - docs/REAL_ROBOT_GUIDE.md 77행, 88행 부근
   - robot_remote.py, real.launch.py, robots.launch.py의 머리말 주석
   - docs/CODE_REVIEW_CHECKLIST.md의 R7-2에 "- 조치(2026-11-18):" 줄
   - docs/TROUBLESHOOTING.md에 T-30 항목(증상 → 원인 → 수정 → 검증), 상단 표와 "마지막 갱신" 날짜
7. docs/에 비밀번호 값이 그대로 적힌 곳이 있는지 확인합니다. 기획 세션은 확인하지 못했습니다. docs/2026-11-16_CHANGES.md 66행·72행 주변이 후보입니다. 있으면 값만 지웁니다.

### 고치지 않는 것 (사용자 판단)

- docs/2026-11-16_CHANGES.md, 2026-11-17_CHANGES_MAPS.md, REAL_ROBOT_GUIDE.md에 로봇의 사설 IP가 적혀 있습니다. 공유기 안쪽 주소라 위험은 낮습니다. 지울지는 사용자에게 묻습니다.
- 각 로봇에 SSH 키를 등록(ssh-copy-id)하면 비밀번호 항목 자체를 지울 수 있습니다. 로봇의 설정을 바꾸는 일이라 사용자가 직접 합니다.

### 완료 확인

- git status --short에 robots.yaml이 나오지 않고, git check-ignore가 그 경로를 무시 대상으로 답함
- colcon build --symlink-install --packages-select frybot_bringup 성공
- 새 경로에서 load_registry()가 옮기기 전과 같은 로봇 이름·대수를 돌려줌(값은 출력하지 않음)
- ros2 run frybot_bringup robot_remote --all --check 가 로봇에 접속됨: 로봇이 켜져 있어야 하므로 못 하면 "실기기 확인 필요"로 보고

## W2. 상태 이름을 State Diagram v4에 맞춤

### 대조 결과

| 대상 | v4의 상태 | 코드 | 판정 |
| --- | --- | --- | --- |
| 주문 | ORDERED, COOKING, SERVING, COMPLETED, ON_HOLD, CANCELED | restaurant.py와 같음 | 변경 없음 |
| 음식 1개 | QUEUED, COOKING, READY, LOADED, SERVING, DELIVERED, ON_HOLD, CANCELED | LOADED가 없음. 적재 이벤트에서 바로 SERVING이 됨(restaurant.py 196~197행) | 수정 |
| AMR 임무 | PENDING, IN_PROGRESS, DONE, SUSPENDED, CANCELED | fleet_core.py Task.state와 같음 | 변경 없음 |
| 조리 작업 | WAIT_ARM, PROCESS, HANDOFF, DONE, CANCELED | CookJob.label은 공정 단계 이름(QUEUED, COOKING, 단계명, DONENESS_CHECK, READY)이고 v4 상태가 없음 | 상태 추가 |
| 방문·테이블 | v4가 정의하지 않음("매장·방문·테이블 전체 생명주기는 확정하지 않는다"고 명시) | GUIDING, SEATED, LEFT, COLLECTING, VACANT_CHECK 등 | 코드 변경 없음, 주석만 수정 |
| 기기 공통 코드 | 기기별 상태 흐름 V0.10의 STA 14개, ERR 11개 | device_state.py와 이름·번호가 같음 | 주석의 버전만 수정 |

### 수정 1: 음식 상태 LOADED

v4의 뜻: 적재가 확인된 뒤 테이블로 출발하기 전까지가 LOADED이고, 테이블 이동이 실제로 시작되면 SERVING입니다.

- fleet_core.py: 서빙 임무가 음식을 실은 뒤 테이블행 경로에서 처음으로 한 구간을 실제로 나아갔을 때(on_route_progress) TaskEvent 상태 SERVING을 한 번 발행합니다. Task에 발행 여부 표시를 둡니다. LOADED 이벤트 바로 뒤에 SERVING 이벤트 단계를 끼워 넣는 방식은 같은 주기에 둘 다 나가 LOADED가 보이지 않으므로 쓰지 않습니다.
- restaurant.py on_task_event: SERVE의 LOADED → 음식 LOADED, SERVE의 SERVING → 음식 SERVING.
- restaurant.py _recompute_order: LOADED를 SERVING·DELIVERED와 같은 묶음으로 봅니다. 주문에는 LOADED 상태가 없고, 이렇게 해야 주문 상태의 변화 시점이 지금과 같습니다.
- 보류 후 재개는 hold_from에 LOADED가 그대로 담기므로 따로 고칠 것이 없습니다(v4의 "재집기 금지"와 맞음). 확인만 합니다.
- frybot_interfaces/msg/TaskEvent.msg 7행 주석: SERVE의 상태 목록에 SERVING 추가. 필드는 바꾸지 않습니다.
- 이 상태를 읽는 곳을 함께 고칩니다.
  - frybot_web/static/ui.js 35행 ITEM_STAGE, map.js 10행 상태 이름표, table.html 52행 손님 화면 문구: LOADED 추가
  - frybot_web/static/admin.html 566행 이벤트 필터: EVT_SERVING 추가
  - central_control_node.py가 TaskEvent를 EVT_ 접두로 기록하는 부분에 새 상태가 그대로 기록되는지 확인
  - offline_bench.py와 frybot_sim/world_node.py는 DELIVERED만 봐서 영향 없음(확인만)

### 수정 2: 조리 작업 상태

- 공정 단계 이름(step)은 관리자 화면이 쓰므로 그대로 둡니다.
- fleet_core.py의 조리 작업 스냅샷(1849행 부근)에 v4 상태 state를 추가합니다: 팔을 아직 잡지 못함 → WAIT_ARM, 공정 수행 중 → PROCESS, PLACE_HANDOFF 수행 중 → HANDOFF, 끝남 → DONE.
- 관리자 화면 표시를 바꿀지는 선택입니다. 값만 내보내도 됩니다.

### 수정 3: 주석

- restaurant.py 머리말: "State names follow State Diagram v4"를 주문·음식에만 해당한다고 고치고, 방문·테이블은 v4에 정의가 없어 자체 이름을 쓴다고 적습니다.
- device_state.py 머리말: V0.07 → V0.10(코드 표는 같음).

### 팀 확인으로 넘기는 것 (코드 수정 없음)

논리 데이터 모델(State Diagram v3 기준)과 코드의 방문·테이블 상태가 다릅니다. v4가 이 둘을 정의하지 않아 어느 쪽이 맞는지 정할 근거가 없습니다.
- 방문: 모델은 CHECK_IN, WAITING, ASSIGNED, IN_USE, END_OF_USE / 코드는 ASSIGNED, GUIDING, SEATED, LEFT, REJECTED, GUIDE_FAILED, CANCELED
- 테이블: 모델은 AVAILABLE, ASSIGNED, IN_USE, CLEANING / 코드는 AVAILABLE, ASSIGNED, IN_USE, VACANT_CHECK, COLLECTING, CLOSED

### 완료 확인

- colcon build --symlink-install --packages-select frybot_interfaces frybot_control frybot_web 성공
- fleet_bench rush·bottleneck 결과가 W0의 표와 같음(상태 이름만 늘었으므로 수치가 달라지면 안 됨)
- sim.launch.py + ros2 run frybot_sim scenario --scenario demo 실행 후 events.csv에서 음식마다 EVT_LOADED → EVT_SERVING → EVT_DELIVERED 순서 확인, frybot.db의 order_item.status에 LOADED가 기록되는지 확인, analyze_run 결과 첨부
- 테이블 주문 화면과 관리자 화면에서 새 상태가 빈칸이나 undefined로 나오지 않는지 확인

## W3. 모의 비교

### 지금 도구로 알 수 있는 것 (W0 결과)

- 경로 계획의 효과는 뚜렷합니다. independent_astar는 점유 대기가 194~344초이고 sipp는 0.4~3.2초입니다. 기준선 조합(fifo_nearest + independent_astar)은 두 시나리오 모두 5번 중 1번을 끝내지 못했습니다.
- 배정의 효과는 시나리오에 따라 다릅니다. bottleneck에서는 기본 조합이 빠르지만(424초 대 470초), rush에서는 fifo_nearest + sipp가 오히려 조금 빠릅니다(370초 대 374초). 배정 쪽 장점은 지금 수치로는 주장하기 어렵습니다.
- 이 수치의 시간은 실기기의 절반 수준입니다(모의/실제 0.53).

### 지금 도구의 한계

1. fleet_bench의 모의 로봇은 계획 속도 그대로 지연 없이 움직입니다. 실기기는 구간마다 2.27초를 쓰고 속도도 다릅니다.
2. 실행 시간에 흔들림이 없어, 계획과 실행이 어긋날 때의 동작(11-16 실기기에서 드러난 문제)이 나오지 않습니다.
3. fleet_bench는 가상 매장 전용이고, 실측 지도를 다루는 replay_run은 기록된 로그 재생과 양보 조합 분류만 합니다. 실측 지도에서 조합을 비교하는 기능이 없습니다.
4. 평균만 내고, 씨앗별 차이와 통과·실패 판정이 없습니다.
5. 모의 로봇이 offline_bench.py(SimRobot, OfflineWorld)와 replay_run.py(Bot, ReplayWorld)에 따로 구현되어 있습니다.

### 방법 결정

실기기와 같은 관제 코어(FleetCore)에 모의 로봇을 붙이는 방식은 유지합니다. 비교하려는 대상이 그 코어이기 때문입니다. 모의 로봇과 비교 계층은 새로 만듭니다.

1. 새 모듈 frybot_control/mock_fleet.py
   - TimeModel(속도, 구간 지연, 흔들림 비율)과 MockFleet. replay_run.py의 ReplayWorld를 옮겨 와 기반으로 삼습니다(구간 지연이 이미 구현되어 있음).
   - 흔들림은 구간마다 소요 시간에 곱하는 난수이고, 씨앗으로 재현됩니다.
   - 로봇 간 최소 간격, 0.155 m 미만으로 있던 시간, 임무가 있는데 30초 넘게 움직이지 않은 횟수, 같은 로봇의 PLAN_FAIL 최대 연속 횟수를 MockFleet이 셉니다.
   - offline_bench.py와 replay_run.py는 이 모듈을 쓰고, SimRobot·Bot과 중복된 이동 코드는 지웁니다.
2. fleet_bench 확장
   - --time-model ideal|measured, --overhead, --exec-speed, --jitter, --plan-speed
   - --baseline "<스케줄러> <플래너>": 같은 씨앗끼리 짝지어 기준선과의 차이를 냄
   - 출력: 지표마다 중앙값·최소·최대, 주문→전달은 상위 5% 값, 기준선보다 나았던 씨앗 수. 원본은 씨앗당 한 줄로 --csv에 저장
   - --check: 0장의 통과 기준 중 모의로 볼 수 있는 것(전부 완료, 30초 넘는 정지 0건, PLAN_FAIL 연속 3회 미만, 최소 간격 0.155 m 이상)으로 통과·실패를 내고 종료 코드에 반영
   - scripts/bench_all.py가 offline_bench.run()을 쓰므로 그 함수의 인자와 반환 열은 호환되게 둡니다.
3. 실측 지도용 작업 부하 추가
   - --map-id test_map_v001 --scenario moves: 씨앗으로 정한 이동 명령을 로봇이 한가해질 때마다 MOVE_TO_VERTEX로 넣습니다. Restaurant는 쓰지 않습니다.
   - 지표: 명령별 소요 ÷ 막힘 없는 소요, 대기 시간, 위의 정지·실패·간격 지표
   - 이동 명령은 로봇을 지정하므로 배정 방식의 차이는 나오지 않고 경로 계획만 비교됩니다.
4. replay_run의 로그 재생과 --find-yield는 기능을 유지합니다.

### 실행할 비교

| 축 | 값 |
| --- | --- |
| 조합 | 기본(min_cost_eta_rh + sipp), fifo_nearest + sipp, min_cost_eta_rh + independent_astar, 기준선(fifo_nearest + independent_astar) |
| 작업 부하 | 가상 매장 normal·rush·bottleneck, 실측 지도 moves(로봇 2대, 3대) |
| 실행 시간 모델 | 기존(지연 0, 0.08 m/s), 실측(2.27초 + 거리 ÷ 0.135 m/s) |
| 흔들림 | 0, 0.2 |
| 계획 속도 | 지금 값(0.08 × 0.9), 속도만 보정한 값(실측 지도 구간 중앙값 13 cm 기준 약 0.04 m/s) |
| 씨앗 | 조건당 30개 |

- 계획이 구간 지연을 직접 모델링하게 하는 것은 플래너 수정이 필요한 별도 작업(기획안 E1)이라 이번에는 하지 않습니다. 이번에는 속도 값만 바꿔 보정 효과의 크기를 먼저 봅니다.
- 실측 시간 모델은 11-16 실기기 실행 한 건(로봇 2대, 구간 147개)에서 나왔고, 가상 매장에 그대로 적용하는 것은 가정입니다. 결과에 이 점을 적습니다.
- 흔들림 0.2는 임의로 고른 값입니다. 11-16 로그의 구간 시간에서 모델과의 차이 분포를 구할 수 있으면 그 값으로 바꿉니다.

### 완료 확인

- 리팩터링 뒤 기존 시간 모델·흔들림 0에서 W0의 표와 같은 수치가 나옴. replay_run 출력(0.53, 1.01)도 같음
- colcon build --symlink-install --packages-select frybot_control 성공
- 위 비교를 실행해 원본 CSV를 archive/mock_compare_2026-11/에 저장하고, 요약 표를 docs/2026-11-18_IMPROVEMENT_PLAN.md에 "모의 비교 결과" 절로 추가
- 결과가 기본 조합에 불리하게 나와도 그대로 적습니다. 통과 기준을 못 넘는 조건은 따로 표시합니다.

## 보고 형식

작업마다: 실행한 명령과 통과·실패, 확인하지 못한 것(실기기 확인 필요 포함), 바뀐 파일 목록, 커밋 메시지 초안.

---

<a id="order-2"></a>

## 지시서 2: W4~W6

<!-- 원본: WORK_ORDER_2026-11-18_2.md -->

# FryBot 작업 지시서 2 (2026-11-18): W4~W6

앞 지시서(docs/2026-11-18_WORK_ORDER.md)의 W0~W3 결과에 대한 사용자 결정과 그에 따른 수정 방법입니다.
수정 방법은 기획 세션이 코드를 읽고 정했고, 실제 수정은 검토 세션(부장)이 합니다. 작업 공간 규칙(CLAUDE.local.md)은 그대로 적용됩니다.

## 0. 사용자 결정

1. 통과 기준 "PLAN_FAIL 연속 3회 이상 0건"을 "같은 목적지의 계획 실패가 20초 넘게 이어지는 경우 0건"으로 바꾼다.
2. 기본 조합의 약점 두 가지의 원인을 먼저 조사하고, 그다음 구간 지연을 계획에 넣는다.

"30초 넘는 정지 0건"을 포함한 나머지 기준은 그대로입니다. 순서는 W4 → W5 → W6입니다.

## W4. 통과 기준 변경

### 지금 구현

- mock_fleet.py의 log()가 로봇별로 PLAN_FAIL을 세고 PLAN이 오면 0으로 되돌려 최대 연속 횟수(plan_fail_run)를 냅니다(173~186행).
- offline_bench.py의 _passes()가 plan_fail_run >= CHECK_FAIL_RUN이면 실패로 봅니다(523~534행).

### 수정

- 정의: 한 로봇이 같은 목적지로 낸 계획이 연속해서 실패하고, 그 묶음의 첫 실패부터 마지막 실패까지가 20초를 넘으면 1건입니다. 계획이 성공하거나 목적지가 바뀌면 묶음이 끝납니다. 실행이 끝날 때까지 이어진 묶음도 셉니다.
- mock_fleet.py: 위 건수를 새 지표(이름 예: plan_fail_long)로 세고, 기준 시간은 상수로 둡니다(20.0초). PLAN_FAIL 이벤트에 목적지가 어느 필드로 실리는지 먼저 확인하고, 없으면 fleet_core.py의 PLAN_FAIL 로그에 목적지를 넣습니다(기록만 추가, 판단은 바꾸지 않음).
- plan_fail_run은 참고 열로 남기고 판정에서는 뺍니다.
- offline_bench.py: _passes()와 원본 CSV 열, 머리말 설명(19행)을 새 기준으로 바꿉니다.
- 문서: src/frybot/README.md의 --check 설명, docs/2026-11-18_WORK_ORDER.md 0장의 기준 문구에 "W4에서 변경" 표시, docs/2026-11-18_IMPROVEMENT_PLAN.md 8장·9.3절.

### 완료 확인

- 기존 시간 모델·흔들림 0에서 fleet_bench rush·bottleneck 조합별 평균이 W0 표와 같음(--csv-mean)
- 앞 비교(128개 조건, 3,840회)를 다시 실행해 archive/mock_compare_2026-11/SUMMARY.md와 기획안 9장의 판정을 새 기준으로 갱신. 원본 CSV에는 시각이 없어 다시 실행해야 합니다.
- 새 기준으로 통과하는 조건 수와, 새 기준에 걸린 실행의 목록을 보고

## W5. 기본 조합의 약점 원인 조사

수정은 하지 않고 원인만 밝힙니다. 대상은 기본 조합(min_cost_eta_rh + sipp)입니다.

### 대상 실행 (archive/mock_compare_2026-11/의 원본에서 뽑음)

A. 끝내지 못한 실행

| 작업 부하 | 조건 | 씨앗 |
| --- | --- | --- |
| moves2 | 기존 모델, 흔들림 0, 계획 속도 기본 | 19 |
| moves2 | 기존 모델, 흔들림 0.2 / 실측 모델, 계획 속도 0.04 | 19 |
| moves3 | 실측 모델, 흔들림 0, 계획 속도 기본 | 19, 21 (씨앗 19는 30초 정지 63건) |
| moves3 | 실측 모델, 흔들림 0.2, 계획 속도 기본 | 11, 21 |
| moves3 | 실측 모델, 계획 속도 0.04 | 5, 11, 15 (흔들림 0), 5 (흔들림 0.2) |

moves2 씨앗 19는 흔들림이 없는 기존 모델에서도 나오므로 시간 모델과 무관한 원인일 가능성이 있습니다. 여기부터 봅니다.

B. 30초 넘는 정지

| 작업 부하 | 조건 | 걸린 씨앗 수 (건수) |
| --- | --- | --- |
| rush | 기존 모델, 흔들림 0 | 1 (1건, 씨앗 25) |
| rush | 실측 모델, 흔들림 0, 계획 속도 기본 | 16 (20건, 예: 0, 1, 4, 7, 12) |
| rush | 실측 모델, 흔들림 0.2, 계획 속도 기본 | 16 (23건) |
| rush | 실측 모델, 흔들림 0, 계획 속도 0.04 | 20 (35건) |

### 방법

1. 씨앗 하나만 골라 다시 실행할 수 있게 합니다. fleet_bench에 그런 인자가 없으면 추가합니다(예: --only-seed). 같은 씨앗은 같은 결과가 나와야 합니다.
2. 실행마다 문제 시점의 앞 60초를 뽑습니다: 어느 로봇이, 어느 노드에서, 어떤 임무·단계로 서 있었는지, 통행 허가를 기다렸다면 그 노드를 누가 잡고 있었는지, 그 사이의 관제 이벤트(PLAN, REPLAN, PLAN_WAIT, YIELD_WAIT, YIELD_SKIP, RETREAT, PLAN_FAIL, 우선순위 뒤집기).
3. 실행마다 원인을 한 가지로 분류하고 근거 이벤트를 붙입니다. 분류를 코드로 자동화할 수 있으면 걸린 실행 전체에 적용해 분류별 건수를 냅니다.

### 확인할 가설 (맞다고 가정하지 말고 근거로 가릴 것)

- 가설 1, 지표의 문제: 30초 정지 집계가 정상적인 대기까지 세고 있을 수 있습니다. mock_fleet.py는 임무가 IN_PROGRESS인데 움직이지 않으면 셉니다(249~256행). 팔 작업 중이거나 손님·음식을 기다리는 단계가 포함되는지 확인합니다.
- 가설 2, 계획과 실행의 어긋남: 관제는 지연 없이 0.072 m/s로 예약을 잡는데 실측 모델의 로봇은 구간마다 2.27초를 더 씁니다. 앞선 로봇이 예약보다 늦게 비켜 뒤 로봇이 허가를 오래 기다리는 경우입니다. 점유 대기가 0초 안팎에서 58초로 는 것과 맞는 방향입니다.
- 가설 3, 양보 대기: 대기 양보의 한도(yield_max_wait 25초)에 다른 대기가 더해져 30초를 넘는 경우입니다.
- 가설 4, 교착 또는 맴돌기: 끝내지 못한 실행에서 가장 오래 서 있던 시간이 12.8초였으므로 서 있는 것이 아니라 오가며 맴도는 경우일 수 있습니다. 우선순위 뒤집기 제한(FLIP_HOLD 8초)의 반복, 실측 지도에서 임무 없는 로봇은 다른 로봇을 비키게 하지 않는 규칙(T-26, fleet_core.py의 quiet)과의 관계를 봅니다.

### 결과물

- 분류표: 실행, 원인 분류, 근거 이벤트 발췌, 분류별 건수
- 분류마다 수정 제안(무엇을 왜 바꿀지 한두 줄). W5에서는 고치지 않습니다.
- 가설 1이 맞아 지표 정의가 틀렸다면, 정의를 어떻게 고칠지 제안만 하고 사용자 결정을 기다립니다. 통과 기준에 해당하기 때문입니다.
- 가설 2에 해당하는 것은 W6 뒤에 다시 실행해 사라지는지 봅니다.
- 시간 모델과 무관한 관제 버그가 나오면 W6와 섞지 말고 따로 보고합니다. 수정은 사용자 승인 뒤에 합니다.
- 기획안에 "9.5 약점 원인 조사" 절로 정리

## W6. 구간 지연을 계획에 반영 (기획안 E1, R5-4)

### 지금 구현

- PlanRequest에는 speed만 있습니다(planners/base.py 22~30행).
- sipp.py는 구간 시간을 dt = d / v로 계산합니다(41행). cooperative_astar.py는 n = ceil(d / v / dt)입니다(46행).
- fleet_core.py는 계획 속도를 speed × plan_speed_factor(0.9)로 넘깁니다(621행, 1017행). 속도를 직접 쓰는 곳이 더 있습니다: 배정 비용(361행, 366행), 구간 중간에서의 출발 시각(622~624행, 1018행), 물러날 때의 시간(1238행).
- 실기기에서 맞춘 구간 시간은 2.27초 + 거리 ÷ 0.135 m/s입니다. 앞 비교에서 계획 속도만 0.04 m/s로 낮추는 방식은 오히려 나빠졌습니다.

### 수정

1. planners/base.py: PlanRequest에 구간 지연(초) 필드를 기본값 0.0으로 추가합니다. 구간 시간은 "지연 + 거리 ÷ 속도"입니다. 지연은 구간을 출발할 때 쓰는 시간으로 봅니다(예약 규칙은 그대로: 앞 노드를 떠날 때부터 다음 노드에 닿을 때까지 점유).
2. 플래너
   - sipp.py, cooperative_astar.py, independent_astar.py: 구간 시간 계산에 지연을 더합니다. 휴리스틱(남은 거리 ÷ 속도)은 실제보다 작게 잡는 값이라 그대로 두어도 됩니다.
   - cbs.py: 하위 탐색이 요청을 그대로 넘기는지 확인하고, 직접 계산하는 곳이 있으면 같이 고칩니다.
   - rmf.py, schedulers/rmf_task.py: 외부 도우미가 속도만 받습니다. 지연을 지원하지 않는다고 설명에 적고 동작은 그대로 둡니다.
3. fleet_core.py: FleetCore에 계획 구간 지연 인자를 기본값 0.0으로 추가하고, 위 "지금 구현"에 적은 곳에 모두 반영합니다. 배정 비용의 거리 기준 계산(361행)은 최단 경로의 구간 수 × 지연을 더합니다. 손님 안내 구간의 실측 지연은 없으므로 같은 값을 쓰고 가정이라고 주석에 적습니다.
4. task_manager_node.py: plan_overhead 파라미터(기본 0.0)를 추가합니다.
5. 런치: sim.launch.py, gazebo.launch.py, real.launch.py에 plan_overhead 인자를 기본 0.0으로 추가합니다.
   - 경량 시뮬의 로봇은 지연 없이 움직이므로 0.0이 맞습니다.
   - 실기기 런치도 기본값은 0.0으로 둡니다. 실측값이 실기기 실행 한 건에서 나왔고 보정한 계획을 실기기에서 돌려 본 적이 없기 때문입니다. 권장값(plan_overhead:=2.27, speed:=0.135)과 "실기기 확인 필요"를 docs/REAL_ROBOT_GUIDE.md에 적습니다.
6. fleet_bench: --plan-overhead를 추가합니다. replay_run에도 보정한 계획으로 재생하는 인자를 추가합니다.
7. 기록
   - docs/TROUBLESHOOTING.md의 T-23: "시간 모델은 미수정"을 수정 내용과 검증 결과로 갱신(실기기 확인 대기), 상단 표와 "마지막 갱신" 날짜
   - docs/CODE_REVIEW_CHECKLIST.md의 R5-4에 "- 조치(2026-11-18):" 줄
   - src/frybot/README.md의 런치 인자 표, docs/COMMANDS.md에 해당 명령이 있으면 함께

### 완료 확인

1. 지연 0.0에서 동작이 같음: fleet_bench rush·bottleneck 조합별 평균이 W0 표와 같고, replay_run 출력(0.53, 1.01)도 같음
2. 계획 시각 확인: 다른 로봇이 없는 지도에서 sipp·cooperative_astar·independent_astar가 낸 경로의 도착 시각이 구간별 "지연 + 거리 ÷ 속도"의 합과 맞는지 확인하는 pytest를 frybot_control/test/에 추가하고 실행
3. colcon build --symlink-install --packages-select frybot_control frybot_bringup 성공
4. 보정 효과 비교: 실측 실행 모델에서 계획을 세 가지(지금 값, 속도만 0.04, 보정값 = 지연 2.27초 + 0.135 m/s)로 바꿔 가며, 앞 비교와 같은 작업 부하·조합·흔들림(0, 0.2)·씨앗 30개로 실행
   - 지표: 전체 소요, 점유 대기, 30초 정지, 20초 넘는 계획 실패, 미완료 수, 그리고 명령별 실제 소요 ÷ 계획 ETA의 중앙값(통과 기준 0.8~1.2)
   - 기존 실행 모델에 보정값을 쓰는 조건도 하나 넣어, 시뮬 기본값을 0.0으로 두는 근거를 확인
   - plan_speed_factor(0.9)를 보정값과 함께 쓸지, 지연에도 여유를 둘지는 결과를 보고 제안
5. W5에서 가설 2로 분류된 실행을 보정값으로 다시 돌려 사라지는지 확인
6. replay_run으로 11-16 실기기 로그를 보정한 계획으로 재생해, 이벤트 건수(REPLAN, ZONE_REQUEST, PLAN_WAIT)가 실제와 가까워지는지 확인
7. sim.launch.py + ros2 run frybot_sim scenario --scenario demo(기본값)로 노드 간 동작이 그대로인지 확인하고 analyze_run 결과 첨부
8. 원본은 archive/mock_compare_2026-11/에, 요약은 기획안 "9.6 구간 지연 보정 결과" 절에 저장

결과가 보정에 불리하게 나와도 그대로 적습니다. 실기기에서 확인하지 못한 것은 "실기기 확인 필요"로 남깁니다.

## 보고 형식

작업마다: 실행한 명령과 통과·실패, 확인하지 못한 것, 바뀐 파일 목록, 커밋 메시지 초안. W5의 분류표는 W6을 시작하기 전에 먼저 보내 주세요.

---

<a id="order-3"></a>

## 지시서 3: W7~W9

<!-- 원본: WORK_ORDER_2026-11-18_3.md -->

# FryBot 작업 지시서 3 (2026-11-18): W7~W9

작업 지시서 2의 W4~W6 결과에 대한 사용자 결정과 그에 따른 수정 방법입니다.
수정 방법은 기획 세션이 코드를 읽고 정했고, 실제 수정은 검토 세션(부장)이 합니다. 작업 공간 규칙(CLAUDE.local.md)은 그대로 적용됩니다.

## 0. 사용자 결정

1. "30초 넘는 정지"는 계획에 없이 선 경우만 세고, 의도된 대기는 따로 보고한다.
2. W5에서 나온 관제 문제 3건을 모두 고친다.
3. 보정 뒤 bottleneck에서 대기가 늘어난 원인을 조사한다.

순서는 W7 → W8 → W9입니다. W8은 실기기에서 도는 관제 코드를 바꾸므로 항목마다 전후를 따로 비교합니다. 작업이 끝날 때마다 보고하되, 다음 작업은 기다리지 말고 이어서 진행합니다. 단, W8-1 뒤 기준 표에서 기본 조합이 뚜렷이 나빠지면 멈추고 알려 주세요.

## W7. 30초 정지의 정의 변경

### 지금 구현

- mock_fleet.py의 move_robots()가 임무가 IN_PROGRESS인데 움직이지 않은 시간이 30초에 닿으면 stall30을 1 올립니다(249~256행). 이유는 구분하지 않습니다.
- W5의 w5_trace.py는 관제의 로봇 상태를 읽어 이유를 나눴습니다(계획 대기, 양보 대기, 락 대기 등).

### 수정

- 서 있는 이유를 mock_fleet.py에서 매 단계 나눕니다. 구분은 w5_trace.py의 방식을 옮겨 옵니다.
  - 의도된 대기: 계획상 출발 시각 전(fleet_core.py _drive의 planned_wait 분기와 같은 조건), 비켜 선 뒤 상대 통과를 기다림(pending_goal과 yield_to가 있음), 팔 작업 중
  - 계획에 없는 정지: 그 밖의 전부(다음 노드를 다른 로봇이 잡고 있어 허가를 기다림, 경로도 예정도 없음, 계획 실패 뒤 다시 시도하기를 기다림)
- 새 지표
  - unplanned30: 계획에 없는 정지가 30초 넘게 이어진 횟수. 통과 기준은 이 값이 0입니다.
  - intended_wait_max: 한 실행에서 가장 길게 이어진 의도된 대기(초)
  - intended30: 의도된 대기가 30초를 넘은 횟수. 참고 열이며 판정에는 쓰지 않습니다.
- 이유가 바뀌어도 서 있는 상태가 이어지면 시간은 종류별로 따로 잽니다. 예를 들어 계획 대기 20초 뒤 락 대기 15초는 계획에 없는 정지 15초입니다.
- stall30은 앞 결과와 비교할 수 있게 참고 열로 남깁니다.
- offline_bench.py의 _passes(), 출력, 원본 CSV 열, 머리말 설명을 고칩니다.
- 문서: src/frybot/README.md의 --check 설명, 기획안 8장과 9.3절, docs/2026-11-18_WORK_ORDER.md 0장에 "W7에서 변경" 표시.

### 완료 확인

- 기존 시간 모델·흔들림 0에서 fleet_bench rush·bottleneck 조합별 평균이 W0 표와 같음(plan_ms 제외)
- W5의 분류와 맞는지 확인: w5_classified.csv에서 "임무 없는 로봇에 막힘"과 "다시 계획할 때를 기다림"으로 분류된 묶음은 unplanned30에, 계획 대기와 양보 대기는 intended30에 들어가야 합니다. 어긋나는 건수를 보고합니다.
- 앞 비교(W3의 128개 조건, W6의 10개 조건)를 다시 실행해 요약과 기획안의 판정을 갱신하고, 새 기준으로 통과하는 조건 수를 보고
- 조건별 intended_wait_max의 중앙값과 최대값을 표로 냅니다. 의도된 대기에 상한을 둘지 정하는 근거로 씁니다.

## W8. 관제 문제 3건 수정

세 항목 모두 frybot_control의 변경이고 실기기 동작에 영향을 줍니다. 항목마다 따로 고치고 따로 확인합니다. 순서는 W8-1(판단 순서 고정) → W8-2(도착 뒤 점유) → W8-3(계획 실패 보류)입니다. 판단 순서를 먼저 고정해야 뒤 두 항목의 전후 비교가 흔들리지 않습니다.

### W8-1. 같은 입력에 같은 판단 (T-번호 새로 부여)

지금 구현
- 관제 코어가 문자열 집합을 도는 순서가 PYTHONHASHSEED에 따라 달라져 동점 처리가 바뀝니다. 모의 도구는 해시 씨앗을 0으로 두고 자신을 다시 실행해 가리고 있습니다(mock_fleet.py 39~45행).
- 후보가 되는 곳: fleet_core.py에서 held, graph.conflict, 대기 위치·비켜 서는 곳 집합, region·avoid·closed 같은 지역 집합을 도는 부분(515, 588~605, 730, 821, 833, 1121, 1217, 1323, 1339행 부근). layout.py, planners, schedulers에도 같은 종류가 있는지 봅니다.
- 물러난 뒤 다시 시도하는 시각에 전역 random.uniform을 씁니다(1277행).

수정
- 실제로 갈라지는 지점을 먼저 찾습니다. 같은 씨앗을 해시 씨앗 두 가지로 돌려 이벤트가 처음 달라지는 곳을 찾으면 됩니다. 추측으로 전부 바꾸지 않습니다.
- 그 지점과, 순서가 선택에 영향을 주는 순회(첫 번째로 맞는 것을 고르거나 동점에서 먼저 나온 것을 고르는 곳)를 정렬된 순서로 바꿉니다. 순서가 결과에 영향을 주지 않는 순회(예약 추가, 락 해제)는 그대로 둡니다.
- 전역 random 대신 FleetCore가 가진 난수 생성기를 쓰게 하고, 씨앗을 인자로 줄 수 있게 합니다(기본은 지금처럼 매번 다름). 다시 시도하는 시각을 흩는 동작 자체는 유지합니다.
- 고친 뒤 모의 도구의 해시 씨앗 재실행을 없앱니다. 남겨 두면 같은 문제가 다시 생겨도 가려지기 때문입니다.

완료 확인
- 해시 씨앗 재실행을 끈 상태에서 PYTHONHASHSEED 1·2·3으로 moves2·moves3·rush 각 씨앗 20개를 돌려 plan_ms를 뺀 결과가 같음
- 이 확인을 하는 pytest를 frybot_control/test/에 추가(하위 프로세스로 해시 씨앗을 바꿔 가며 몇 개 씨앗 비교)
- 기준 표 다시 저장: 정렬 순서는 해시 씨앗 0의 순서와 다르므로 W0 표의 수치가 달라질 수 있습니다. 달라지면 새 기준 표를 archive/mock_compare_2026-11/baseline_w8/에 저장하고, W0 표와의 차이를 조합별로 보고합니다. 이후 확인은 새 기준 표와 비교합니다.
- replay_run archive/runs_2026-11-16_18/run_20261116_175751과 --find-yield 출력의 변화도 함께 보고

### W8-2. 다음 일이 없는 로봇의 도착 뒤 점유 (T-번호 새로 부여)

지금 구현
- _hold_estimate(at_goal=True)(fleet_core.py 598~607행)는 이동 중인 로봇이 목적지에 닿고 4초 뒤 떠난다고 예약합니다.
- 이동 명령(MOVE)은 단계가 이동 하나뿐이라(_move_to_vertex, 1549~1550행) 도착하면 그 자리에 계속 섭니다. 뒤 로봇의 계획은 4초 뒤 그 자리가 빈다고 보고 길목까지 들어옵니다.
- _move_to_vertex는 출발 노드의 점유만 검사하고 목적지는 검사하지 않습니다(1566~1570행).

수정
- _hold_estimate: 지금 이동이 임무의 마지막 단계이고 그 뒤 할 일이 없으면(MOVE 임무) 도착 뒤 점유를 무한대로 돌려줍니다.
- _move_to_vertex: 다른 로봇이 같은 목적지로, 또는 그 목적지와 동시에 점유할 수 없는 노드(graph.conflict)로 가는 중이면 명령을 거절하고 이유를 알립니다. 목적지에 임무 없는 로봇이 서 있는 경우는 지금처럼 받습니다(비켜 주기 기능이 처리).
- 가상 매장에는 MOVE 임무가 없어(_move_to_vertex가 실측 지도에서만 동작) 가상 매장 결과는 바뀌지 않아야 합니다.

완료 확인
- 가상 매장 normal·rush·bottleneck 결과가 W8-1 기준 표와 같음
- W5에서 "막다른 대기 위치 W3" 유형으로 분류된 미완료 8회를 다시 실행해 결과를 보고(끝남, 거절됨, 그대로 중 어느 것인지)
- moves2·moves3 전체 조건을 다시 실행해 미완료 수, 거절된 명령 수, 전체 소요의 전후 비교
- 모의 작업 부하에서 거절된 명령은 "미완료"와 구분해 셉니다(거절은 관제가 이유를 알려 준 정상 응답).

### W8-3. 계획 실패가 이어지면 임무 보류와 알림 (T-번호 새로 부여)

지금 구현
- 계획이 실패하면 PLAN_FAIL을 남기고 1초 뒤 다시 시도합니다(pending_goal, 695·706행). 횟수나 시간 제한이 없어 W5에서 1,380초 동안 반복됐습니다.
- 임무 보류는 _suspend(1523~1527행)가 하고, TASK_SUSPEND 로그와 SUSPENDED 이벤트를 냅니다. Restaurant는 이를 받아 ALERT와 incident를 남깁니다. 보류된 임무의 로봇에는 새 허가를 내지 않습니다(_drive 1078행). 재개는 RETRY_TASK입니다.

수정
- 로봇별로 같은 목적지의 계획 실패가 시작된 시각을 기억합니다. 계획이 성공하거나 목적지가 바뀌면 지웁니다. W4의 묶음 정의와 같게 합니다.
- 그 시간이 20초를 넘으면
  - 임무가 있으면 _suspend(임무, 'PLAN_FAIL')로 보류합니다. 다시 시도하던 예정(pending_goal)과 락의 처리는 로봇 끊김으로 보류할 때(A3)와 같은 방식을 따르고, RETRY_TASK로 재개되는지 확인합니다.
  - 임무가 없으면(복귀·비켜 준 뒤 돌아가는 중) 보류할 임무가 없으므로, 묶음마다 한 번 알림 로그만 남기고 다시 시도는 계속합니다.
- 20초 값은 fleet_core.py의 상수 하나로 두고 mock_fleet.py가 그것을 가져다 씁니다.
- 손님 안내 중이거나 음식을 실은 임무도 같은 규칙을 적용합니다. 20초 넘게 길이 없으면 관리자가 알아야 하기 때문입니다.
- 인터페이스: TaskEvent.msg의 reason 설명에 PLAN_FAIL을 추가합니다(필드 변경 없음). FleetCommand.srv·AdminCommand.srv 주석에 영향이 있는지 확인합니다.
- Restaurant는 E_STOP·PAUSED가 아닌 보류를 모두 incident의 DEVICE_ERROR로 기록합니다(restaurant.py on_task_event). 길 막힘은 기기 고장이 아니므로, 논리 데이터 모델의 incident 출처 값에 맞는 것이 있는지 확인해 있으면 그 값을 쓰고, 없으면 그대로 두고 팀 확인 항목으로 보고합니다.
- 관리자 화면의 알람 목록에 새 사유가 빈칸 없이 나오는지 확인합니다.
- 모의 작업 부하: 보류된 임무가 있으면 그 실행은 시간 한도까지 기다리지 말고 끝내고, 보류 수(suspended)를 따로 셉니다.

완료 확인
- 가상 매장 결과가 W8-2 뒤와 같음(가상 매장에서는 20초 넘는 계획 실패가 0건이었으므로 바뀌지 않아야 함). 바뀌면 어느 실행에서 보류가 났는지 보고
- W5의 미완료 13회를 다시 실행: 끝남, 보류와 알림으로 끝남, 그대로 중 어느 것인지와, 보류까지 걸린 시간
- Restaurant에 SUSPENDED(PLAN_FAIL)를 넣어 ALERT와 incident가 남는지, RETRY_TASK로 재개되는지 확인
- 경량 시뮬 실측 지도(sim.launch.py map_id:=test_map_v001)에서 두 로봇을 같은 막다른 자리로 보내, 둘째 명령이 거절되는지(W8-2)와 길이 막힌 이동이 20초 뒤 보류·알림되는지 화면과 events.csv로 확인

### W8 공통

- 빌드: colcon build --symlink-install --packages-select frybot_interfaces frybot_control frybot_web
- pytest 전체 통과
- sim.launch.py + ros2 run frybot_sim scenario --scenario demo 후 analyze_run 결과 첨부
- 세 항목을 모두 넣은 뒤 W3·W6의 비교를 다시 실행해 요약과 기획안 표를 갱신
- 기록
  - docs/TROUBLESHOOTING.md에 항목마다 T-번호(증상 → 원인 → 수정 → 검증), 상단 표와 "마지막 갱신" 날짜
  - docs/CODE_REVIEW_CHECKLIST.md 5순위에 "- 발견:" / "- 조치(2026-11-18):" 줄
  - src/frybot/README.md "연결" 절에 계획 실패 보류 규칙 한 줄, docs/REAL_ROBOT_GUIDE.md에 실기기에서 달라지는 점(같은 목적지 이동 명령 거절, 20초 뒤 보류와 RETRY_TASK)
- 실기기에서 확인하지 못한 것은 "실기기 확인 필요"로 남깁니다.

## W9. 보정 뒤 bottleneck에서 대기가 늘어난 원인 조사

수정은 하지 않고 원인만 밝힙니다. W7의 지표와 W8의 수정이 들어간 코드로 합니다.

### 대상

- 기본 조합, 실측 실행 모델, bottleneck: 계획이 지금 값일 때 전체 소요 624초, 보정값일 때 660초(W6, 씨앗 30개 중앙값). 30초 정지는 6건에서 44건으로 늘었습니다.
- 같은 씨앗끼리 짝지어 비교합니다. 차이가 큰 씨앗 5개를 골라 실행을 열어 봅니다.
- W8 뒤에는 수치가 달라질 수 있으므로 먼저 두 조건을 다시 실행해 차이가 그대로인지 확인합니다. 차이가 없어졌으면 그 사실을 보고하고 끝냅니다.

### 방법

- 씨앗마다 두 조건의 차이를 시간 항목으로 나눕니다: 의도된 대기(계획 대기, 양보 대기), 계획에 없는 정지, 주행 시간, 조리·팔 작업 대기.
- 의도된 대기가 어디서(노드), 어떤 임무·단계에서, 누구를 기다리며 생겼는지 봅니다.
- 배정이 달라졌는지 봅니다: 임무별 배정 로봇, 재배정 횟수.

### 확인할 가설 (근거로 가릴 것)

- 가설 1, 다른 로봇의 점유 예상이 시간 모델과 맞지 않음: _hold_estimate의 고정값(4초, 팔 작업 + 2초)과 예약 여유(pad 0.4초)는 보정하지 않았습니다. 구간 시간만 길어져 예약이 서로 길게 겹칠 수 있습니다.
- 가설 2, 양보 판단의 시간 기준: 양보 대기 상한(yield_until +30초)과 yield_max_wait(25초)는 고정값이고, 보정 뒤 예상 시간이 길어져 기다리는 쪽을 더 자주 고를 수 있습니다.
- 가설 3, 배정의 변화: 도착 예상 시각이 달라져 min_cost_eta_rh의 배정·재배정이 바뀌었을 수 있습니다. 재평가 기준(5초 넘게 줄면 재배정)도 고정값입니다.
- 가설 4, 계획이 정확해져 일찍 서는 것: 보정 전에는 통로 앞에서 락을 기다리던 시간이 보정 뒤에는 출발 전에 서 있는 시간으로 옮겨 갔을 뿐이고, 전체 소요 차이는 다른 원인일 수 있습니다.

### 결과물

- 씨앗별 시간 항목 표와 원인 분류, 근거 발췌
- 원인마다 수정 제안. 양보 대기 상한을 상대 경로의 남은 예상 시간에 맞추는 안(W5 제안)도 여기서 근거와 함께 평가합니다. W9에서는 고치지 않습니다.
- W5에서 "세 대가 맞물림(원인 추가 확인 필요)"으로 남은 2회가 W8 뒤에 어떻게 됐는지 함께 보고
- 기획안에 "9.8 보정 뒤 bottleneck 조사" 절로 정리(9.7은 W7·W8 결과)

## 보고 형식

작업마다: 실행한 명령과 통과·실패, 확인하지 못한 것(실기기 확인 필요 포함), 바뀐 파일 목록, 커밋 메시지 초안.

---

<a id="order-4"></a>

## 지시서 4: W10

<!-- 원본: WORK_ORDER_2026-11-18_4.md -->

# FryBot 작업 지시서 4 (2026-11-18): W10

W9에서 찾은 모의 도구 문제를 고치고, 영향을 받은 비교를 다시 실행합니다. 관제 코드(fleet_core.py, planners)는 바꾸지 않습니다. 도구 수정이므로 기획 세션이 바로 지시하고, 사용자에게는 결과 정정으로 보고합니다.

## 확인한 사실

- offline_bench.py는 --plan-speed를 plan_speed_factor = plan_speed / speed로 넘깁니다(102행, 400행). replay_run.py도 같습니다(375행).
- fleet_core.py는 이 배율을 일반 속도와 안내 속도 모두에 곱합니다(650행, 1059행).
- 따라서 가상 매장 작업 부하에서 --plan-speed를 쓴 조건은 모두 안내 계획 속도가 함께 바뀌었습니다.
  - 보정값(0.135): 안내 계획 0.084 m/s (실행 0.05 m/s의 1.7배)
  - 속도만 낮춘 조건(0.04): 배율 0.5라 안내 계획 0.025 m/s (실행의 절반). W9 보고에는 없지만 이 조건도 같은 영향을 받습니다. 기획안 9.2의 "계획 속도만 낮추는 보정은 득이 없음"과 9.5의 계획 대기 건수(계획 속도 0.04에서 220건)는 가상 매장에 한해 다시 확인해야 합니다.
- 이동 명령 작업 부하(moves)는 안내가 없어 영향이 없습니다.
- 실기기 런치는 task_manager의 speed 파라미터를 바꾸는 방식이라 안내 속도에 영향이 없습니다.

## 수정

1. --plan-speed가 실기기 런치와 같은 방식으로 동작하게 합니다.
   - --plan-speed X는 FleetCore의 speed를 X로 넘깁니다(real.launch.py의 speed:=X와 같음). 안내 속도는 건드리지 않습니다.
   - --plan-guide-speed를 추가합니다(FleetCore의 guide_speed, 기본 0.05).
   - --plan-speed-factor를 추가합니다(기본은 관제 기본값 0.9). "보정" 조건은 배율 1.0, "보정×0.9" 조건은 기본값입니다.
   - 지금 값 조건(인자 없음)의 동작은 그대로여야 합니다.
   - replay_run.py의 --plan-speed도 같은 방식으로 고칩니다.
2. 서 있는 이유 분류에 "구간 출발 지연"을 추가합니다. 실측 실행 모델이 구간마다 출발 전에 쓰는 시간은 계획에 없는 정지도 의도된 대기도 아닙니다. unplanned30 판정에서 빼고, 합계 시간을 참고 열로 냅니다.
3. 문서: src/frybot/README.md의 fleet_bench 설명, docs/REAL_ROBOT_GUIDE.md에 --plan-speed 예시가 있으면 함께.

## 다시 실행할 것

- W3 비교 중 가상 매장의 계획 속도 0.04 조건(normal·rush·bottleneck × 실행 모델 2 × 흔들림 2)
- W6 비교 중 가상 매장의 보정·보정×0.9·속도만 0.04·"기존 모델 + 보정" 조건
- 지금 값 조건과 moves는 수치가 그대로인지만 확인합니다(같아야 함).

## 완료 확인

- 인자 없는 fleet_bench rush·bottleneck 평균이 baseline_w8 기준 표와 같음, replay_run 출력(0.53, 1.01)도 같음
- --plan-speed 0.135에서 안내 구간의 계획 속도가 0.045 m/s인지 확인하는 pytest 추가(PLAN 이벤트의 eta 또는 PlanRequest 값으로)
- pytest 전체 통과, colcon build --symlink-install --packages-select frybot_control 성공
- 갱신할 곳: archive/mock_compare_2026-11/의 요약, 기획안 9.1(표), 9.2(계획 속도 0.04에 대한 결론), 9.5(계획 대기 건수 중 가상 매장분), 9.6(보정 결과 표와 "기존 모델 + 보정 10~35% 증가"), 9.7(통과 수, 의도된 대기 최장 시간 표). 바뀐 수치에는 "W10에서 정정"이라고 표시하고, 앞 수치가 왜 틀렸는지 한 줄로 적습니다.
- 보고에 포함할 것
  - 보정 전후의 전체 소요·점유 대기·ETA 비율(기본 조합, 실측 실행 모델, 시나리오 3개)
  - 계획 속도 0.04 조건의 결론이 바뀌는지
  - 수정 뒤에도 보정값이 지금 값보다 느린 씨앗이 bottleneck에서 몇 개인지(W9 시험에서는 11/30)
  - 수정 뒤 의도된 대기 최장 시간의 분포(상한을 정할 근거)

## 이번에 하지 않는 것

- 양보 대기 상한을 남은 예상 시간에 맞추는 안, _hold_estimate 고정값 조정: W10 결과를 보고 사용자와 정합니다.

## 보고 형식

실행한 명령과 통과·실패, 확인하지 못한 것, 바뀐 파일 목록, 커밋 메시지 초안.

---

<a id="order-5"></a>

## 지시서 5: W11~W12

<!-- 원본: WORK_ORDER_2026-11-18_5.md -->

# FryBot 작업 지시서 5 (2026-11-18): W11~W12

W10 결과에 대한 사용자 결정과 그에 따른 작업입니다. 관제 코드(fleet_core.py, planners)는 바꾸지 않습니다. 작업 공간 규칙(CLAUDE.local.md)은 그대로 적용됩니다.

## 0. 사용자 결정

1. 의도된 대기도 30초는 길다. 20초를 기준으로 한다.
2. W10에서 새로 나온 문제 2건의 원인을 확인한다.
3. 실기기 실험(E1)은 대기한다. 이번 지시에 실기기 작업은 없습니다.

## W11. 의도된 대기 기준 추가 (모의 도구만)

### 정의

- 통과 기준에 "의도된 대기가 20초 넘게 이어진 경우 0건"을 추가합니다.
- 의도된 대기의 분류(계획상 출발 시각 전, 비켜 선 뒤 상대 통과 대기, 팔 작업)와 시간을 재는 방식은 W7 그대로입니다.
- "계획에 없는 정지 30초" 기준은 사용자가 바꾸라고 하지 않았으므로 그대로 둡니다. 다만 20초로 맞출지 정할 수 있게, 계획에 없는 정지가 20초를 넘은 횟수를 참고 열로 함께 냅니다.

### 수정

- mock_fleet.py: intended20(판정), unplanned20(참고)을 추가합니다. 기준 시간은 상수로 둡니다. intended30, intended_wait_max, stall30은 참고 열로 남깁니다.
- 의도된 대기가 20초를 넘은 묶음마다 종류(계획 대기, 양보 대기, 팔 작업)를 함께 셉니다(예: intended20_plan, intended20_yield).
- offline_bench.py의 _passes(), 출력, 원본 CSV 열, 머리말 설명
- 문서: src/frybot/README.md의 --check 설명, 기획안 8장과 9장의 판정 설명

### 완료 확인

- 인자 없는 fleet_bench rush·bottleneck 평균이 baseline_w8 기준 표와 같음(plan_ms 제외), pytest 전체 통과
- W3·W6 비교를 다시 실행해 새 기준의 통과 수를 보고
- 이 기준은 지금 관제로는 많이 걸릴 것입니다. W10에서 기본 조합의 가장 긴 의도된 대기가 중앙값 18.1초, 상위 10% 36.8초, 최대 68.7초였습니다. 그래서 다음을 함께 보고합니다.
  - 기본 조합에서 20초를 넘은 의도된 대기의 건수를 종류별, 작업 부하별, 계획 조건별(지금 값, 보정, 보정×0.9)로 나눈 표
  - 어디서 생기는지: 노드(받는 곳 앞, 테이블 옆, 통로 등), 임무 종류와 단계, 누구를 기다렸는지. 건수가 많은 상위 유형 몇 개와 근거 발췌
  - 유형마다 20초 안으로 줄이려면 관제에서 무엇을 바꿔야 하는지 제안(예: 비켜 선 뒤 대기 상한 yield_until +30초, 계획 대기가 길 때 다른 경로나 대기 자리 선택). 이번에는 고치지 않습니다.
  - 계획에 없는 정지를 20초로 맞추면 통과 수가 어떻게 달라지는지

## W12. 새 문제 2건의 원인 조사 (수정 없음)

### 대상

A. 세 대 맞물림: 실측 지도 이동 명령 moves3, 씨앗 25, 기본 조합, 기존 실행 모델 + 보정(--plan-speed 0.135 --plan-speed-factor 1.0 --plan-overhead 2.27). pinky1의 A4행 계획이 20초 실패해 보류됐고, 배율 0.9에서는 끝납니다. archive/mock_compare_2026-11/w10/s25.py가 있습니다.

B. 계획에 없는 30초 정지 1건: 가상 매장 rush, 기본 조합, 실측 실행 모델, 흔들림 0, 보정×0.9(--plan-speed 0.135 --plan-overhead 2.27). 실기기 권장값과 같은 조건입니다. 기획 세션이 씨앗 30개로 다시 돌려 1건이 재현되는 것을 확인했습니다. 씨앗 번호는 원본에서 찾아야 합니다.

B가 더 중요합니다. 실기기에서 쓸 설정에서 나왔기 때문입니다.

### 방법

- W5와 같습니다. 문제 시점의 앞 60초를 뽑아 어느 로봇이 어느 노드에서 어떤 임무·단계로 서 있었는지, 누가 그 노드를 잡고 있었는지, 그 사이의 관제 이벤트를 봅니다.
- A는 세 로봇의 위치·목적지·잡은 노드를 맞물린 시점 기준으로 그림처럼 적고, 어느 판단에서 빠져나갈 길이 없어졌는지 찾습니다. 배율 1.0과 0.9의 실행이 처음 갈라지는 지점도 봅니다.
- B는 그 정지가 락 대기, 경로·예정 없음, 재시도 대기 중 어느 것인지와, 30초 동안 정체 해소(_resolve_stall, 3초 뒤 재계획)가 왜 풀지 못했는지 봅니다.
- 같은 유형이 다른 실행에도 있는지 확인합니다: W10 원본에서 기본 조합의 unplanned30 > 0인 실행과 보류된 실행 전부를 같은 방식으로 분류합니다.

### 확인할 가설 (근거로 가릴 것)

- A-1: 세 대 이상이 얽힌 경우를 풀 규칙이 없음. 비켜 주기(_make_way, _clear_exit)는 한 단계만 봅니다(T-24의 "한 단계").
- A-2: W8-2에서 넣은 도착 뒤 무한 점유 예약이, 지연 없는 실행에 보정된 계획을 쓸 때 다른 로봇의 길을 지나치게 막음
- B-1: 보정된 계획에서 로봇이 계획보다 일찍 도착해, 예약 순서와 실제 락 순서가 뒤집힘(plan_speed_factor 0.9의 영향)
- B-2: 받는 곳·테이블 옆에서 팔 작업 중인 로봇의 점유 예상(_hold_estimate의 팔 작업 + 2초)이 실제보다 짧아 뒤 로봇이 락 앞에 섬
- B-3: 정체 해소가 재계획을 반복하지만 같은 경로가 다시 나옴

### 결과물

- 실행별 원인 분류와 근거 발췌, 유형별 건수
- 원인마다 수정 제안(무엇을 왜 바꿀지 한두 줄)과, 그 수정이 실기기 동작에 주는 영향. 고치지는 않습니다.
- 실기기 권장값(보정×0.9)을 그대로 권해도 되는지에 대한 의견
- 기획안에 "9.10 W11·W12" 절로 정리

## 보고 형식

실행한 명령과 통과·실패, 확인하지 못한 것, 바뀐 파일 목록, 커밋 메시지 초안.

---

<a id="order-6"></a>

## 지시서 6: 실기기 R0~R7

<!-- 원본: WORK_ORDER_2026-11-18_6.md -->

# FryBot 작업 지시서 6 (2026-11-18): 실기기 실험 R0~R7

기획 세션이 쓴 실기기 실험 지시서입니다. 실험과 기록은 검토 세션(부장)이 합니다. 작업 공간 규칙(CLAUDE.local.md)은 그대로 적용됩니다.

## 0. 사용자 결정과 현재 상태

1. 배터리 문제로 **pinky1, pinky2 두 대만** 씁니다. pinky3은 꺼져 있습니다.
2. 두 로봇은 `test_map_v001`의 대기 위치(pinky1 = W1, pinky2 = W2) **근처**에 놓여 있습니다. 정확히 노드 위는 아닙니다. 기동하면 출발 노드로 스스로 가는 로직(`auto_home`)이 실제로 동작하는지 봅니다.
3. 11-16 첫 실험에서 노드 사이를 이동하던 로봇이 **좌우로 계속 방향을 찾는 동작**을 많이 했습니다. 원인이 costmap인지 노드 수인지 가리기 위해 `test_map_v001`과 `test_map_v002`를 비교합니다.
4. **무엇을 시험했고 결과가 어땠는지를 빠짐없이 기록**합니다(4장). 측정하지 못한 항목은 비워 두지 말고 이유를 적습니다.

## 1. 원칙

- **코드와 설정 파일을 고치지 않습니다.** 예외는 측정 스크립트(3장)뿐입니다. 실험 중 버그를 찾으면 고치지 말고 증상·로그 발췌·재현 방법을 기록한 뒤 다음 단계로 갈 수 있는지 판단합니다. 주행 안전에 관계된 문제면 멈추고 보고합니다.
- **로봇을 움직이는 명령 전에 사용자에게 알립니다.** 단계(R1~R7)를 시작할 때마다 무엇이 움직이는지 한 줄로 알리고, 사용자가 손으로 해야 하는 일(로봇 옮기기, 상자 놓기)은 요청한 뒤 기다립니다.
- **멈추는 조건:** 로봇끼리 또는 벽과 접촉, 허가받지 않은 구간으로 진행, 비상 정지가 듣지 않음, 런치 Ctrl-C 뒤 2초 넘게 움직임. 이 가운데 하나라도 나오면 런치를 내리고(`robot_remote pinky1 pinky2 --stop`) 실험을 중단한 뒤 보고합니다.
- **배터리:** 단계가 끝날 때마다 두 로봇의 `/pinkyN/battery/percent`를 기록합니다. 어느 한 대가 20 아래(단위는 R1에서 확인)로 내려가면 남은 단계를 건너뛰고 보고합니다. 그래서 단계는 중요한 순서로 놓았습니다.
- 실기기 터미널은 `ROS_DOMAIN_ID=73`입니다. 시뮬용 74가 남은 터미널을 쓰지 않습니다. 시뮬과 실기기를 함께 띄우지 않습니다.
- `git commit`, `git push`, 작업 상태를 바꾸는 git 명령은 하지 않습니다.

## 2. 단계 요약

| 단계 | 내용 | 로봇 | 지도 | 꼭 필요한가 |
| --- | --- | --- | --- | --- |
| R0 | 빌드, 배포, 점검, 기준 기록 | 없음 | - | 필수 |
| R1 | 한 대 기동, 자동 홈 이동, 센서·이름 확인 | pinky1 | v001 | 필수 |
| R2 | 한 대 이동과 정지(비상 정지, 취소, 관제 중단) | pinky1 | v001 | 필수 |
| R3 | 흔들림 측정 v001 | pinky1 | v001 | 필수 |
| R4 | 흔들림 측정 v002 | pinky1 | v002 | 필수 |
| R5 | 두 대: 자동 홈 이동, 동시 이동, 양보, 이동 명령 거절 | pinky1, pinky2 | v001 | 필수 |
| R6 | 계획 보정값(`plan_overhead:=2.27 speed:=0.135`) | pinky1, pinky2 | v001 | 배터리가 남으면 |
| R7 | 사용자 손이 필요한 항목(노드 이탈 복귀, 구간 막기, 길 막힘 보류) | pinky1, pinky2 | v001 | 배터리가 남으면 |

R3·R4가 사용자가 가장 궁금해하는 항목입니다. R5보다 앞에 둔 이유는 한 대로 끝나고 배터리가 가장 많을 때 같은 조건으로 재야 하기 때문입니다.

## 3. 측정 준비 (R0에서 함)

### 3.1 기록할 토픽

런치마다 관제 PC에서 따로 bag을 남깁니다. 이름은 `runs/<run_id>/bag` 아래에 둡니다. 토픽 이름은 기동 뒤 `ros2 topic list`로 실제 이름을 확인하고, 다르면 실제 이름을 기록에 적습니다.

```bash
ros2 bag record -o runs/<run_id>/bag /pinky1/cmd_vel /pinky1/odom /pinky1/plan /pinky1/amcl_pose /pinky2/cmd_vel /pinky2/odom /pinky2/plan /pinky2/amcl_pose /fleet/robot_status /fms/traffic_grant /fms/task_events
```

- `/pinkyN/plan`(Nav2 전역 경로)과 `/pinkyN/amcl_pose`가 관제 PC에서 보이지 않으면(로봇 안에서만 도는 토픽일 수 있음) 그 사실을 기록하고, RViz 화면 관찰로 대신합니다.
- 로봇의 TF는 `/pinkyN/tf`입니다. 필요하면 추가합니다.

### 3.2 측정 스크립트 (새로 만듦, 유일한 코드 추가)

`scripts/wobble_metrics.py`를 만듭니다. bag과 `events.csv`, 지도의 `roadmap.json`을 읽어 로봇·이동 명령별로 다음을 냅니다. 관제·로봇 코드는 건드리지 않습니다.

| 값 | 정의 |
| --- | --- |
| `seg_n`, `dist_m`, `time_s` | 구간 수, 경로 길이, 소요 시간(`ZONE_ENTER`/`ZONE_EXIT` 또는 `EVT_ASSIGNED`→`EVT_DONE`) |
| `seg_time_med` | 구간당 소요 시간 중앙값 |
| `flip_per_m` | `cmd_vel.angular.z`의 부호가 바뀐 횟수 ÷ 이동 거리. 절댓값 0.1 rad/s 미만은 0으로 봄 |
| `spin_ratio` | 제자리 회전 시간 비율: `|linear.x| < 0.005`이고 `|angular.z| > 0.3`인 시간 ÷ 전체 |
| `stop_ratio` | 정지 시간 비율: 선속도·각속도 모두 0에 가까운 시간 ÷ 전체 |
| `flip_near_node`, `flip_mid` | 부호 바뀜이 일어난 위치가 가장 가까운 노드에서 5 cm 안인지 밖인지로 나눈 횟수(`odom` 또는 `robot_status` 위치 기준) |
| `amcl_jump` | `amcl_pose`가 연속 두 값 사이에 3 cm 또는 0.1 rad 넘게 바뀐 횟수(토픽이 있을 때) |
| `plan_shift` | 같은 구간 안에서 연속한 `/pinkyN/plan`의 가로 방향 최대 차이(cm)의 중앙값(토픽이 있을 때) |

- 임계값(0.1, 0.005, 0.3, 5 cm, 3 cm)은 기획 세션이 임의로 정한 값입니다. 실제 신호를 보고 맞지 않으면 바꾸되, 바꾼 값과 이유를 기록합니다.
- 스크립트는 ROS 없이 돌 필요는 없습니다(`rosbag2_py` 사용 가능). Google Python Style, 수정 표기 주석 규칙을 따릅니다.
- 완료 확인: R1의 bag으로 한 번 돌려 값이 나오는지 봅니다.

## 4. 기록 방식

결과 문서 `docs/2026-11-18_REAL_TEST.md`를 새로 만듭니다. 구성은 다음과 같습니다.

1. **머리말:** 날짜, 사용한 로봇, 코드 상태(`git log -1 --oneline`, 커밋하지 않은 변경이 있음, `git diff | sha1sum`), 로봇에 배포한 시각
2. **요약 표:** 아래 형식으로 시험 한 건당 한 줄

| ID | 시험 | 방법(명령) | 통과 기준 | 결과 | 측정값 | 근거 |
| --- | --- | --- | --- | --- | --- | --- |
| R1-3 | 자동 홈 이동 | ... | ... | 통과 / 실패 / 못 함 | off=0.09 m, 도착 14.2 s | `runs/<run_id>/events.csv`의 줄 발췌 |

3. **단계별 상세:** 실행한 명령 그대로, `run_id`, 시작·끝 시각, 배터리, `events.csv`·런치 로그 발췌, 관찰한 것(사용자가 눈으로 본 내용은 "사용자 관찰"이라고 표시)
4. **흔들림 비교(R3·R4):** 6장의 표
5. **찾은 문제:** 증상, 재현 방법, 로그. 고치지 않았음을 명시
6. **확인하지 못한 것과 이유**

결과에 "통과"를 쓰는 기준: 통과 기준을 로그나 측정값으로 실제 확인한 경우만입니다. 사용자의 눈 관찰만 있으면 "통과(사용자 관찰)"로 구분합니다.

실험이 끝나면 다음 문서도 맞춥니다.

- `docs/REAL_ROBOT_GUIDE.md` 9장: "실기기에서 확인한 것"에 오늘 결과를 추가하고, "그 뒤에 바뀌어 다시 봐야 하는 것" 표와 점검표의 pinky3 조합을 실제로 쓴 pinky2 조합으로 갱신
- `docs/TROUBLESHOOTING.md`: 해당 T-번호(T-22, T-24, T-28 중 해당분, T-30, T-32, T-33, T-23)의 검증 줄에 "실기기 확인(2026-11-18): 결과"를 추가. "마지막 갱신" 날짜 갱신
- `docs/CODE_REVIEW_CHECKLIST.md`: 확인된 항목(R1-1, R1-4, R2-3, R5-4 등)에 `- 조치(2026-11-18):` 또는 확인 결과 줄 추가
- `docs/2026-11-18_REAL_FIRST_PLAN.md` 진행 상태 표의 "실기기 확인 필요"

## 5. 단계별 절차

경로는 관제 PC의 `~/frybot_ws` 기준입니다. 관리자 명령은 화면(`http://localhost:8080/admin`) 대신 아래 형식으로 보내면 시각이 로그에 남아 측정이 쉽습니다.

```bash
curl -s -X POST -H 'Content-Type: application/json' -d '{"command":"MOVE_TO_VERTEX","target":"pinky1","arg":"B5"}' http://localhost:8080/api/admin
```

### R0. 빌드, 배포, 점검

| ID | 할 일 | 통과 기준 |
| --- | --- | --- |
| R0-1 | `colcon build --symlink-install --packages-up-to frybot_bringup`, `source install/setup.bash` | 빌드 성공 |
| R0-2 | `fleet_bench --scenario moves --map-id test_map_v001 --robots 2 --seeds 3 --check`와 같은 명령의 `test_map_v002` | 기본 조합(`min_cost_eta_rh` + `sipp`) 통과. 기획 세션이 15:5x에 v002를 돌렸을 때 통과, 최소 간격 0.156 m |
| R0-3 | `ros2 run frybot_bringup robot_remote pinky1 pinky2 --deploy` | 두 대 모두 로봇에서 빌드 성공. 배포 시각 기록 |
| R0-4 | `ros2 run frybot_bringup robot_remote pinky1 pinky2 --check` | 두 대 `OK`. pinky2는 실기기 첫 접속(T-30의 남은 항목). 로봇에 `test_map_v002`가 있는지도 확인 |
| R0-5 | `scripts/wobble_metrics.py` 작성(3.2) | R1 뒤에 실제 bag으로 확인 |

- `--all`은 꺼져 있는 pinky3 때문에 실패가 섞이므로 로봇 이름을 적습니다.
- 배포 목록(`robot_remote.py`의 `DEPLOY`)에 `frybot_control`이 들어 있어 `maps/`의 두 지도가 함께 갑니다. 로봇에서 실제로 보이는지는 R0-4에서 확인합니다.

### R1. 한 대 기동과 자동 홈 이동 (pinky1, v001)

런치 전에 사용자에게 **pinky1의 방향**을 묻습니다. `poses:=`의 방향 기본은 지도의 +x이고, 다르면 `pinky1:W1:<도>`로 줍니다. pinky2는 켜 둔 채 런치에 넣지 않습니다(W2 근처에 서 있는 장애물이 됨).

```bash
ros2 launch frybot_bringup real.launch.py map_id:=test_map_v001 robots:=pinky1 poses:=pinky1:W1
```

| ID | 확인할 것 | 방법 | 통과 기준 | 관련 |
| --- | --- | --- | --- | --- |
| R1-1 | 기동 | 런치 로그 | `[pinky1]` 로그가 이어지고 `robot launch ended` 없음. 기동~Nav2 active까지 걸린 시간 기록 | 점검표 2 |
| R1-2 | 내장 드라이버 | `ros2 node list`, `ros2 topic hz /pinky1/scan /pinky1/odom` | `pinky_driver`, `pinky_battery`, `mobile_controller` 이름으로 뜸. 스캔·오도메트리 주기 기록. 실패하면 `drivers:=pinky_pro`로 다시 띄우고 그 사실 기록 | 11-17 드라이버 교체, P2 |
| R1-3 | **자동 홈 이동** | `grep AUTO_HOME runs/<run_id>/events.csv`, `/fleet/robot_status` | 위치가 잡히고 약 3초 뒤 `AUTO_HOME pinky1 W1 OK`가 남고 W1에 도착. 6 cm 안에 놓였으면 `AT_HOME`(이동 없음)이 정상. 기록: 시작 시 W1과의 거리(`off`), `REJOIN` 유무, 온라인→명령까지 시간, 명령→도착까지 시간, 도착 뒤 W1과의 거리 | 점검표 16, 11-17 `auto_home` |
| R1-4 | 위치 추정 | RViz | 라이다 점이 지도 벽과 겹침(사용자 관찰 + 화면 캡처) | 점검표 4 |
| R1-5 | Nav2 | `ros2 lifecycle get /pinky1/bt_navigator` | `active` | 점검표 5 |
| R1-6 | 배터리 단위 | `ros2 topic echo /pinky1/battery/percent --once` | 값을 기록. 0~100인지 0~1인지 판정 | R2-3 |
| R1-7 | 바퀴 관절값 | `ros2 topic echo /pinky1/joint_states --once`, `ros2 topic info -v` | 발행자가 `pinky_driver` 하나이고 이름이 `left_wheel_joint`·`right_wheel_joint`. RViz 로봇 모델 바퀴가 정상 | R1-4, P3 |
| R1-8 | 시뮬 토픽 없음 | `ros2 node info /pinky1/mobile_controller` | `/sim/world_state`, `/gz/model_poses` 구독 없음 | P3 |
| R1-9 | 측정 스크립트 | R1의 bag으로 `wobble_metrics.py` 실행 | 값이 나옴 | R0-5 |

- **`AT_HOME`으로 끝나 이동이 없었다면** 자동 홈 이동을 본 것이 아닙니다. R5에서 pinky2로 보거나, 사용자에게 pinky1을 다른 노드(예: B1에서 10 cm쯤 벗어난 곳) 근처로 옮겨 달라고 한 뒤 `poses:=pinky1:B1`로 다시 띄워 확인합니다.
- 자동 홈 이동은 로봇마다 관제 실행당 한 번만 합니다. 그 전에 이동 명령이나 비상 정지를 주면 `SKIP`이 되므로, R1-3이 끝나기 전에는 명령을 보내지 않습니다.

### R2. 한 대 이동과 정지 (pinky1, v001, R1의 런치 그대로)

| ID | 확인할 것 | 방법 | 통과 기준 | 관련 |
| --- | --- | --- | --- | --- |
| R2-1 | 한 대 이동 | W1 → B1 → A1 → W1 순서로 이동 명령 | 매번 `EVT_DONE`. 구간 수·소요 시간 기록 | 점검표 6 |
| R2-2 | 비상 정지와 재개 | W1 → B5 주행 중 `ESTOP`, 5초 뒤 `RESUME` | 명령 뒤 `cmd_vel`이 0이 되기까지의 시간(bag), `E_STOP` 보고, 재개 뒤 B5 도착 | 점검표 13, R0-3 |
| R2-3 | 주행 중 취소 | B5 → W1 주행 중 `CANCEL_TASK` | 로봇이 서고 `cmd_vel`이 0으로 끝남(마지막 속도가 남지 않음). 멈춘 뒤 이동 거리 기록 | T-22, R1-1 |
| R2-4 | 취소 뒤 복귀 | 이어서 W1 이동 명령 | 도착. 노드 밖에 섰다면 `REJOIN` 뒤 도착 | 점검표 11 일부 |
| R2-5 | 관제 중단 | W1 → B5 주행 중 런치 Ctrl-C | 2초 안에 정지(bag의 `cmd_vel`/`odom`은 런치와 함께 끝나므로 사용자 관찰 + 로봇 쪽 로그). 로봇 쪽 프로세스도 내려감 | 점검표 14, `FleetHeartbeat` |

- 명령 인자 형식(`ESTOP`, `RESUME`, `CANCEL_TASK`의 `target`·`arg`)은 `frybot_interfaces/srv/AdminCommand.srv`와 `docs/COMMANDS.md`에서 확인합니다.
- R2-5 뒤에는 로봇이 통로 중간에 서 있습니다. R3의 런치는 `poses:=`를 그 위치에 가장 가까운 노드로 주거나, 사용자에게 W1 근처로 옮겨 달라고 합니다.

### R3. 흔들림 측정 v001 (pinky1)

```bash
ros2 launch frybot_bringup real.launch.py map_id:=test_map_v001 robots:=pinky1 poses:=pinky1:W1
```

자동 홈 이동이 끝난 뒤 다음 두 경로를 **각각 3회 왕복**합니다. 한 번의 이동 명령이 끝난 뒤 다음 명령을 보냅니다.

| 경로 | 명령 | v001 예상 경유 | v002 예상 경유 |
| --- | --- | --- | --- |
| P1 직선 | W1 → B7, B7 → W1 | W1, B1, B1_B2, B2, B2_B3, B3, B3_B4, B4, B4_B5, B5, B6, B7 (11구간, 약 1.66 m) | W1, B1, B3, B4, B5, B7 (5구간) |
| P2 꺾임 | W1 → C2, C2 → W1 | W1, B1, …, B4, C2_B4, C2 (9구간, 약 1.14 m) | W1, B1, B3, B4, C2 (4구간) |

- 경유 노드는 예상입니다. 실제 경로는 `events.csv`의 `PLAN`·`ZONE_ENTER`에서 읽어 기록합니다.
- 두 지도에서 이름은 같아도 좌표가 다른 노드가 있습니다(A6, B5, D2_IN). P1의 B5는 v001 (1.763, -0.419), v002 (1.863, -0.419)입니다. 끝점(W1, B7, C2)과 B1·B3·B4는 좌표가 같습니다.
- pinky2는 W2 근처에 서 있습니다. B행에서 pinky1의 라이다에 잡히므로 R3와 R4에서 **같은 자리**에 두고 움직이지 않습니다.
- 사용자에게 흔들림이 눈에 띄는 위치(어느 노드 사이, 노드 앞인지 중간인지)를 말해 달라고 하고 "사용자 관찰"로 적습니다. RViz에서 전역 경로가 매초 바뀌는지, 로봇 자세가 튀는지도 봅니다.

**R3-c (조건부):** R3 결과에서 `flip_mid`가 `flip_near_node`보다 많으면(구간 중간에서도 흔들림) 같은 런치에서 추종 거리만 바꿔 P1을 2회 왕복합니다.

```bash
ros2 param set /pinky1/controller_server FollowPath.lookahead_dist 0.10
```

- 이전 값은 0.06입니다. `ros2 param get`으로 적용됐는지 확인하고, 적용되지 않으면 "못 함"으로 기록합니다. 파일은 고치지 않으므로 재기동하면 0.06으로 돌아갑니다.
- 지역 costmap(라이다 장애물 층)을 끄는 실험은 하지 않습니다. 충돌 예측 정지가 사라집니다.

### R4. 흔들림 측정 v002 (pinky1)

R3의 런치를 내리고, pinky1이 W1에 있는 상태에서 지도만 바꿔 띄웁니다. 관제 PC와 로봇이 같은 `map_id`를 쓰는지 로그로 확인합니다.

```bash
ros2 launch frybot_bringup real.launch.py map_id:=test_map_v002 robots:=pinky1 poses:=pinky1:W1
```

- R3와 같은 경로 P1·P2를 각각 3회 왕복하고 같은 값을 냅니다.
- `test_map_v002`는 README에 "편집 중"으로 적혀 있고 실기기 주행은 처음입니다. 첫 왕복은 사용자가 지켜보는 상태에서 하고, 벽에 가까이 붙는 구간이 있으면 기록합니다.
- v002에는 0.5 m 구간이 있습니다(최대). 긴 구간에서 도착 판정이나 `NAV2_FAILED`가 달라지는지 봅니다.

### R5. 두 대 (pinky1, pinky2, v001)

런치 전에 사용자에게 pinky2의 방향을 묻습니다.

```bash
ros2 launch frybot_bringup real.launch.py map_id:=test_map_v001 robots:=pinky1,pinky2 poses:=pinky1:W1,pinky2:W2
```

| ID | 확인할 것 | 방법 | 통과 기준 | 관련 |
| --- | --- | --- | --- | --- |
| R5-1 | 두 대 기동, pinky2 첫 기동 | 런치 로그, R1-2·R1-5·R1-6을 pinky2에도 | 두 대 모두 Nav2 active, 상태 보고 10 Hz 안팎 | T-30, 점검표 2~5 |
| R5-2 | **두 대 자동 홈 이동** | `grep AUTO_HOME` | 두 대 모두 `OK` 또는 `AT_HOME`, 접촉 없음. R1-3과 같은 값을 로봇별로 기록. `WAIT`가 나오면 사유 기록 | 점검표 16 |
| R5-3 | 겹치지 않는 동시 이동 | pinky1 → A1, 바로 pinky2 → B5. 끝나면 둘 다 홈으로 | 둘 다 도착, 접촉 없음. 최소 간격(`robot_status`로 계산) 기록 | 점검표 7 |
| R5-4 | 비켜 주기 | pinky1을 B7, pinky2를 B6에 보낸 뒤 pinky1 → B5 | pinky2가 B4_B5로 비켰다가 B6로 돌아옴. `RETREAT pinky2 B4_B5 … back_to=B6`. 비킨 시간, 복귀 여부 기록 | 점검표 9, T-24 |
| R5-5 | 대기 양보 | pinky1을 A5로 보내고 pinky2는 W2. pinky1 → B2, 바로 이어 pinky2 → A4 | `YIELD_WAIT pinky2 … yield_to=pinky1`(모의에서 대기 +7.1초). 두 명령 간격과 실제 대기 시간 기록 | 점검표 10 |
| R5-6 | 같은 목적지 거절 | pinky1 → A5 주행 중 pinky2 → A5 | 응답이 "…가는 중입니다. 도착한 뒤 다시 명령하세요." 응답 원문 기록 | T-32 |
| R5-7 | 계획과 실제 | 런치를 내린 뒤 `replay_run runs/<run_id> -v`, `analyze_run` | ETA 대비 실제 소요 비율 기록(11-16은 1.76배). 판정 기준 없음, 기록만 | T-23, R5-4 |

- R5-4와 R5-5의 조합은 기획 세션이 오늘 `replay_run --find-yield --map-id test_map_v001`로 뽑은 것입니다. 모의 결과와 다르게 움직이면(우회, 다른 로봇이 양보) 실패가 아니라 "모의와 다름"으로 기록하고 `YIELD_SKIP`·`REPLAN`·`PLAN_WAIT` 줄을 발췌합니다.
- R5-4에서 pinky1이 B7로 가려면 B6를 지나야 하므로 pinky1을 먼저 B7에 보낸 뒤 pinky2를 B6에 보냅니다.
- R5-5는 두 명령의 간격이 벌어지면 결과가 달라집니다. 두 curl을 한 줄(`&&`)로 보냅니다.
- 양보 후진(`mode=YIELD`) 중에는 뒤쪽 라이다 검사에 기댑니다. 처음 볼 때는 사용자가 손을 댈 수 있는 거리에 있어야 합니다.

### R6. 계획 보정값 (배터리가 남으면)

```bash
ros2 launch frybot_bringup real.launch.py map_id:=test_map_v001 robots:=pinky1,pinky2 poses:=pinky1:W1,pinky2:W2 plan_overhead:=2.27 speed:=0.135
```

- R5-3, R5-4, R5-5와 같은 명령을 같은 순서로 다시 보냅니다.
- `replay_run runs/<run_id> -v --plan-overhead 2.27 --plan-speed 0.135`로 ETA 비율을 내고 R5-7과 나란히 적습니다. 락 대기(`ZONE_REQUEST`), `REPLAN` 횟수도 R5와 비교합니다.
- `speed:=`는 관제(`task_manager`)의 계획 속도만 바꿉니다. `remote.py`는 로봇 런치에 `speed`를 넘기지 않으므로(기획 세션이 코드로 확인) 로봇의 주행 속도는 0.08 그대로입니다. 기동 뒤 `ros2 param get /pinky1/mobile_controller speed`로 0.08인지 확인하고, 다르면 실행하지 말고 보고합니다.

### R7. 사용자 손이 필요한 항목 (배터리가 남으면)

| ID | 확인할 것 | 방법 | 통과 기준 | 관련 |
| --- | --- | --- | --- | --- |
| R7-1 | 노드 이탈 복귀 | 사용자가 pinky1을 노드에서 10 cm쯤 옮긴 뒤 이동 명령 | `REJOIN` 뒤 목적지 도착 | 점검표 11 |
| R7-2 | 주행 실패 복구 | 주행 중 구간 앞을 상자로 막음 | `retry 1/2`, `ROUTE_RETRY`. 계속 막으면 `SUSPENDED`. 상자를 치우고 `RETRY_TASK`로 재개 | 점검표 12 |
| R7-3 | 길 막힘 20초 보류 | pinky2를 B3에 세우고 `ESTOP`. pinky1 → W2(B3을 지나야만 닿음) | 20초 넘게 계획 실패 뒤 `SUSPENDED(PLAN_FAIL)`과 알람. pinky2 `RESUME` 뒤 홈으로 보내고 `RETRY_TASK`로 pinky1 도착 | T-33 |
| R7-4 | 위치 추정 끊김 | 하지 않음 | AMCL을 일부러 죽이는 시험은 이번 범위 밖 | R1-2 |

- R7-3은 기획 세션이 모의로 돌려 보지 않은 조합입니다. 관제가 다른 판단(거절, 다른 경로 없음 안내)을 하면 그대로 기록합니다.

## 6. 흔들림 비교 표와 판정 (R3·R4)

결과 문서에 다음 표를 채웁니다. 값은 왕복 3회의 중앙값과 범위입니다.

| 지도 | 경로 | 구간 수 | 소요(초) | 구간당(초) | `flip_per_m` | `spin_ratio` | `stop_ratio` | 노드 근처:중간 | `amcl_jump` | `plan_shift` | `ROUTE_RETRY` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| v001 | P1 | | | | | | | | | | |
| v001 | P2 | | | | | | | | | | |
| v002 | P1 | | | | | | | | | | |
| v002 | P2 | | | | | | | | | | |
| v001 + lookahead 0.10 | P1 | | | | | | | | | | |

가설과, 어떻게 나오면 그 가설을 지지하는지입니다. 기획 세션이 코드에서 읽은 근거도 함께 적습니다.

| 가설 | 지지하는 결과 | 코드 근거 |
| --- | --- | --- |
| H1 노드가 많음 | 흔들림이 노드 근처에 몰림. v002에서 `flip_per_m`·`spin_ratio`가 구간 수에 비례해 줄어듦 | v001은 구간 36개 중 31개가 20 cm 미만(중앙값 13.1 cm), v002는 중앙값 22.5 cm. 구간마다 Nav2 목표를 새로 보내고 도착 허용 오차가 1.5 cm(`xy_goal_tolerance`), 지도 해상도는 5 cm |
| H2 전역 경로 재계산 | 구간 중간에서도 흔들림. `plan_shift`가 큼. v002에서도 미터당 횟수가 그대로 | `segment_bt.xml`이 1초마다 NavFn으로 다시 계산. 추종 거리 6 cm |
| H3 위치 추정 튐 | `amcl_jump` 직후에 회전. 지도와 무관 | AMCL `update_min_d: 0.02`, 지도 해상도 5 cm |
| H4 제어기 값 | 경로와 자세가 안정적인데 흔들림. lookahead 0.10에서 줄어듦 | 실측 지도는 `use_rotate_to_heading: true`, 기준 0.4 rad. 추종점이 23°를 넘으면 멈춰서 돎 |

- 지역 costmap(라이다)은 이 설정에서 충돌 예측 정지에만 쓰입니다(`use_cost_regulated_linear_velocity_scaling: false`). 그래서 좌우 흔들림보다 `stop_ratio`와 `ROUTE_RETRY`에 나타날 것으로 봅니다. 맞는지 결과로 확인합니다.
- 가설은 서로 배타적이지 않습니다. 결과 문서에는 "어느 가설을 지지하고 어느 가설은 가릴 수 없었는지"를 적고, 표본이 왕복 3회뿐임을 함께 적습니다.
- 수정 제안(허용 오차, 추종 거리, 재계산 주기, 노드 정리)은 결과 뒤에 한두 줄씩 적되 이번에는 고치지 않습니다. `nav2_store.yaml`을 바꾸자는 제안에는 이유와 이전 값을 함께 적습니다.

## 7. 보고 형식

- 단계가 끝날 때마다: 시험 ID별 통과·실패·못 함, 핵심 측정값, 배터리, 다음 단계로 가도 되는지
- 전체가 끝나면: 결과 문서 경로, 요약 표, 흔들림 비교 표와 가설 판정, 찾은 문제, 확인하지 못한 것과 이유, 바뀐 파일 목록, 커밋 메시지 초안
- 측정하지 못한 값은 "못 함(이유)"로 적습니다. 추정값을 측정값처럼 쓰지 않습니다.

---

<a id="order-7"></a>

## 지시서 7: 기동 지연 B0~B4

<!-- 원본: WORK_ORDER_2026-11-18_7.md -->

# FryBot 작업 지시서 7 (2026-11-18): 기동 지연 수정(T-38) 실기기 확인

기획 세션이 쓴 실기기 실험 지시서입니다. 실험과 기록은 검토 세션(부장)이 합니다. 작업 공간 규칙(CLAUDE.local.md)은 그대로 적용됩니다.

## 0. 사용자 결정과 현재 상태

1. **pinky3도 함께 시험합니다.** 대상은 pinky1, pinky2, pinky3 세 대입니다.
2. 사용자가 "기동에 시간이 너무 오래 걸린다"고 했고, 기획 세션이 오늘 실험 로그(`archive/real_test_2026-11-18/r1*_launch.log`)에서 다음을 확인했습니다.

   | 실행 | 로봇 | Nav2 active까지 |
   | --- | --- | --- |
   | 16:14 `r1` | 1대(드라이버 죽음) | 구성 완료 약 23초 |
   | 16:37 `r1b` | 2대 | 151초에 구성 완료, active 기록 없음, pinky2 AMCL 구성 실패 |
   | 16:42 `r1c` | 2대 | 145~146초 |
   | 16:51 `r1d` | 3대 | 도달 못 함. 15초 뒤 세 대 모두 SSH 끊김 33~43회 |

3. 원인은 DDS 탐색 부하로 **추정**했고(확인되지 않음), 기획 세션이 두 가지를 고쳤습니다. 상세는 `docs/TROUBLESHOOTING.md` T-38.
   - `real.launch.py`에 `discovery` 인자(기본 `peers`): 로봇은 `ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST` + `ROS_STATIC_PEERS=<관제 PC 주소>`, 관제 PC는 `ROS_STATIC_PEERS=<로봇 주소들>`. `discovery:=subnet`이 예전 동작
   - 실측 지도에서는 `docking_server`, `aruco_dock_detector`를 띄우지 않음(`frybot_mobile/navigator.py`, 로봇당 프로세스 15 → 13)
4. 빌드와 오프라인 확인(`--dry-run`, 액션 목록)만 했습니다. **실기기에서는 한 번도 돌리지 않았습니다.** 탐색 설정이 틀리면 관제와 로봇이 서로 보이지 않을 수 있습니다.

## 1. 원칙

- **코드와 설정 파일을 고치지 않습니다.** 문제를 찾으면 증상·로그 발췌·재현 방법을 기록하고 보고합니다. 로봇 등록부(`~/.config/frybot/robots.yaml`)도 고치지 않습니다.
- **로봇을 움직이는 명령 전에 사용자에게 알립니다.** 단계를 시작할 때마다 무엇이 움직이는지 한 줄로 알리고, 사용자가 해야 하는 일(로봇 놓기, 방향 알려 주기)은 요청한 뒤 기다립니다.
- **멈추는 조건:** 로봇끼리 또는 벽과 접촉, 허가받지 않은 구간으로 진행, 비상 정지가 듣지 않음, 런치 Ctrl-C 뒤 2초 넘게 움직임. 하나라도 나오면 런치를 내리고 `robot_remote pinky1 pinky2 pinky3 --stop` 뒤 보고합니다.
- **이번에 새로 생긴 위험:** `discovery:=peers`에서 관제의 생존 신호(`/fms/heartbeat`)와 비상 정지가 로봇에 닿는지는 확인된 적이 없습니다. **B1-6(비상 정지)이 통과하기 전에는 두 대 이상을 동시에 움직이지 않습니다.**
- 실기기 터미널은 `ROS_DOMAIN_ID=73`입니다. 시뮬과 실기기를 함께 띄우지 않습니다.
- 단계가 끝날 때마다 배터리(`/pinkyN/battery/percent`)를 기록합니다.
- `git commit`, `git push`, 작업 상태를 바꾸는 git 명령은 하지 않습니다.

## 2. 단계 요약

| 단계 | 내용 | 로봇 | 꼭 필요한가 |
| --- | --- | --- | --- |
| B0 | 빌드, 세 대 배포, 점검, 관제 PC 주소 확인 | 없음 | 필수 |
| B1 | 한 대 기동(`peers`): 시간, 서로 보이는지, 이동, 비상 정지 | pinky1 | 필수 |
| B2 | 세 대 동시 기동(`peers`): 시간, SSH 끊김, 자동 홈 이동, 이동 | pinky1·2·3 | 필수 |
| B3 | 비교: 두 대 `discovery:=subnet`(도킹 노드 제외만 적용된 상태) | pinky1·2 | 배터리가 남으면 |
| B4 | B2가 기준을 못 넘을 때: 로봇의 CPU·Wi-Fi 사용량 측정 | 해당 로봇 | B2가 실패하면 |

지도는 모두 `test_map_v001`입니다.

## 3. 측정 방법

### 3.1 기동 시간

런치 출력을 파일로 남깁니다(`archive/real_test_2026-11-18/b<단계>_launch.log`). 로봇별로 다음 시각을 **런치 시작 기준 초**로 냅니다. 로봇 로그의 시각은 로봇 시계이므로, PC와 로봇의 시계 차이가 1초를 넘으면 그 사실을 적습니다.

| 값 | 로그에서 찾는 줄 |
| --- | --- |
| `t_launch` | `[pinkyN] [INFO] [launch]: All log files ...` (로봇 런치 시작) |
| `t_lidar` | `SLLidar health status : OK` |
| `t_motor` | `Pinky Bringup with Dynamixel has been started successfully` |
| `t_loc` | `lifecycle_manager_localization]: Managed nodes are active` |
| `t_nav` | `lifecycle_manager]: Managed nodes are active` |
| `t_ready` | `mobile_controller]: pinkyN ready at` |
| `t_online` | `runs/<run_id>/events.csv`의 첫 `ROBOT_ONLINE` 또는 `AUTO_HOME` |
| `ssh_lost` | `SSH connection lost` 횟수 |
| `no_output_max` | `no output from the robot for N s`의 최댓값 |

- 구간별로 어디서 오래 걸렸는지 보기 위해 `Configuring controller_server` → `Configuring planner_server` 사이 시간도 적습니다(오늘 2대 실행에서 약 120초였던 구간).
- 값을 뽑는 한 줄 스크립트나 `grep`은 써도 됩니다. 새 파일을 만들면 `archive/real_test_2026-11-18/`에 둡니다.

### 3.2 통과 기준

- 세 대 동시 기동에서 **세 대 모두 `t_nav` ≤ 60초, `ssh_lost` = 0**
- 관제 PC에서 세 로봇의 토픽이 보이고(`/fleet/robot_status`에 세 대), 이동 명령과 비상 정지가 전달됨
- 기준을 못 넘어도 2대 145초보다 얼마나 줄었는지를 그대로 적습니다. "통과"는 기준을 로그로 확인한 경우에만 씁니다.

## 4. 단계별 절차

경로는 관제 PC의 `~/frybot_ws` 기준입니다. 관리자 명령 형식은 지시서 6의 5장과 같습니다.

### B0. 빌드, 배포, 점검

| ID | 할 일 | 통과 기준 |
| --- | --- | --- |
| B0-1 | `colcon build --symlink-install --packages-up-to frybot_bringup`, `source install/setup.bash` | 빌드 성공 |
| B0-2 | `ros2 run frybot_bringup robot_remote pinky1 pinky2 pinky3 --deploy` | 세 대 모두 "deploy finished". 배포 시각 기록(로봇 쪽 `navigator.py`가 바뀌었으므로 필수) |
| B0-3 | `ros2 run frybot_bringup robot_remote pinky1 pinky2 pinky3 --check` | 세 대 `OK` |
| B0-4 | `ros2 run frybot_bringup robot_remote pinky1 --map-id test_map_v001 --dry-run`을 세 대 각각 | `export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST`, `export ROS_STATIC_PEERS=<주소>`가 나오고, 그 주소가 `ip -4 addr`의 관제 PC Wi-Fi/랜 주소와 같음. 기획 세션이 봤을 때는 `192.168.0.20` |
| B0-5 | 로봇의 `~/.bashrc`에 탐색 관련 변수가 있는지 조회(읽기만) | `ROS_AUTOMATIC_DISCOVERY_RANGE`, `ROS_STATIC_PEERS`, `ROS_LOCALHOST_ONLY`, `RMW_IMPLEMENTATION`, `FASTRTPS_DEFAULT_PROFILES_FILE` 유무를 기록. `ROS_LOCALHOST_ONLY=1`이 있으면 B1 전에 보고 |

- B0-4의 주소가 관제 PC 주소가 아니면(다른 인터페이스) 진행하지 말고 보고합니다.

### B1. 한 대 기동 (pinky1, `peers`)

런치 전에 사용자에게 pinky1의 위치와 방향을 묻습니다. 나머지 두 대는 켜 둔 채 런치에 넣지 않습니다.

```bash
ros2 launch frybot_bringup real.launch.py map_id:=test_map_v001 robots:=pinky1 poses:=pinky1:W1 2>&1 | tee archive/real_test_2026-11-18/b1_launch.log
```

| ID | 확인할 것 | 방법 | 통과 기준 |
| --- | --- | --- | --- |
| B1-1 | 기동 시간 | 3.1의 값 전부 | `t_nav` ≤ 60초. 드라이버가 살아 있는 한 대의 기준값이 처음 생김 |
| B1-2 | 도킹 노드 없음 | 런치 로그, `ros2 node list` | `/pinky1/docking_server`, `/pinky1/aruco_dock_detector` 없음. `lifecycle_manager`가 controller·planner·bt_navigator 세 개만 올림. 로봇 프로세스 수 기록 |
| B1-3 | 관제 PC → 로봇이 보임 | 런치와 **다른 터미널**(환경 변수 없이, `ROS_DOMAIN_ID=73`만)에서 `ros2 node list`, `ros2 topic hz /pinky1/scan /pinky1/odom /fleet/robot_status` | 로봇 노드와 토픽이 보이고 주기가 나옴. 안 보이면 같은 터미널에서 `export ROS_STATIC_PEERS=<pinky1 주소>` 뒤 다시 보고 차이를 기록 |
| B1-4 | 로봇 → 관제가 보임 | `runs/<run_id>/events.csv`의 `ROBOT_ONLINE`/`AUTO_HOME`, 로봇 로그에 `WAIT_FMS`가 없는지 | 로봇이 온라인이 되고 자동 홈 이동(`OK` 또는 `AT_HOME`) |
| B1-5 | 이동 | W1 → B1 → W1 이동 명령 | 매번 `EVT_DONE` |
| B1-6 | **비상 정지** | W1 → B5 주행 중 `ESTOP`, 5초 뒤 `RESUME` | 정지하고 `E_STOP` 보고, 재개 뒤 도착. 정지까지 걸린 시간 기록 |
| B1-7 | 관제 중단 | W1 → B5 주행 중 런치 Ctrl-C | 2초 안에 정지(사용자 관찰 + 로봇 로그), 로봇 쪽 프로세스도 내려감 |
| B1-8 | RViz | 화면 | 지도, 코스트맵, 로봇 모델이 보임(사용자 관찰). 바퀴 등 모델이 깨지면 기록 |

- **B1-3 또는 B1-4가 실패하면**(서로 안 보임) 런치를 내리고 `discovery:=subnet`으로 한 번 띄워 그때는 보이는지 확인한 뒤, 두 결과를 기록하고 **B2로 가지 말고 보고합니다.**
- B1-6이 실패하면 멈추고 보고합니다(1장).

### B2. 세 대 동시 기동 (`peers`)

런치 전에 사용자에게 세 대의 위치와 방향을 묻습니다. 아래 `poses:=`는 예시이고 실제 놓인 노드로 바꿉니다.

```bash
ros2 launch frybot_bringup real.launch.py map_id:=test_map_v001 robots:=pinky1,pinky2,pinky3 poses:=pinky1:W1,pinky2:W2,pinky3:W3 2>&1 | tee archive/real_test_2026-11-18/b2_launch.log
```

| ID | 확인할 것 | 방법 | 통과 기준 |
| --- | --- | --- | --- |
| B2-1 | **기동 시간** | 3.1의 값을 로봇별로 | 세 대 모두 `t_nav` ≤ 60초, `ssh_lost` = 0 |
| B2-2 | pinky3 첫 기동 | 런치 로그 | 라이다 `health status : OK`, 모터 `started successfully`(T-37의 포트가 pinky3에도 맞는지). 실패하면 `port_check`와 같은 조회로 포트를 확인해 기록 |
| B2-3 | 관제가 세 대를 봄 | `ros2 topic echo /fleet/robot_status`, 관리자 화면 | 세 대 모두 보고, 화면 지도에 세 대 |
| B2-4 | 로봇끼리 탐색하지 않음 | pinky1에서 `ros2 node list`(SSH 조회, 로봇 런치와 같은 환경 변수를 준 상태) | `/pinky2/...`, `/pinky3/...` 노드가 보이지 않고 관제 노드(`/task_manager` 등)는 보임. 조회 방법이 마땅치 않으면 "못 함(이유)" |
| B2-5 | 자동 홈 이동 | `grep AUTO_HOME runs/<run_id>/events.csv` | 세 대 모두 `OK` 또는 `AT_HOME`, 접촉 없음 |
| B2-6 | 이동 | 한 대씩 이동 명령(겹치지 않는 목적지) 뒤 홈으로 | 매번 `EVT_DONE`. 그 뒤 두 대 동시 이동 한 번 |
| B2-7 | 비상 정지 | 한 대 주행 중 그 로봇 `ESTOP` → `RESUME` | B1-6과 같음 |
| B2-8 | 종료 | 런치 Ctrl-C | 세 대 모두 `robot stack stopped`. 걸린 시간 기록 |
| B2-9 | 재기동 | 같은 명령으로 한 번 더 띄움 | 3.1의 값이 첫 기동과 비슷한지(두 번의 값을 나란히 기록) |

- 기동이 3분을 넘겨도 active가 안 되면 기다리지 말고 B4로 갑니다.
- 세 대가 한 줄 통로에서 맞물리는 조합(CHECKLIST R5-13)은 이번 범위가 아닙니다. 동시 이동은 서로 먼 목적지로 한 번만 합니다.

### B3. 비교: 두 대 `subnet` (배터리가 남으면)

수정 1번(탐색 범위)과 2번(도킹 노드 제외)의 효과를 나눠 보기 위한 실행입니다. 오늘 16:42 실행(`r1c`, 2대, 도킹 노드 있음, 145초)과 비교합니다.

```bash
ros2 launch frybot_bringup real.launch.py map_id:=test_map_v001 robots:=pinky1,pinky2 poses:=pinky1:W1,pinky2:W2 discovery:=subnet 2>&1 | tee archive/real_test_2026-11-18/b3_launch.log
```

- 3.1의 값만 내고 로봇은 움직이지 않습니다(자동 홈 이동은 일어날 수 있음: 사용자에게 알림). active가 되면 바로 내립니다.
- pinky3은 켜져 있어도 런치에 넣지 않습니다. 켜져 있는 사실은 기록합니다(탐색 대상이 아니므로 영향은 없을 것으로 보지만 확인되지 않음).

### B4. 로봇의 CPU·Wi-Fi 측정 (B2가 기준을 못 넘으면)

기동하는 동안 느린 로봇 한 대에서 2초 간격으로 다음을 60~120초 동안 남깁니다(SSH 조회, 읽기만). 출력은 `archive/real_test_2026-11-18/b4_<로봇>.txt`.

- `top -b -n 1 | head -25` (프로세스별 CPU), `cat /proc/loadavg`, `free -m`
- `cat /proc/net/dev`의 무선 인터페이스 수신·송신 바이트(두 시각의 차이로 초당 바이트)
- `vcgencmd get_throttled`(전압·온도 제한 여부, 명령이 없으면 "못 함")

판정: CPU가 계속 100%에 가깝고 네트워크가 한가하면 프로세스 수·파이썬 노드 쪽, 네트워크 바이트가 크면 탐색·토픽 트래픽 쪽입니다. 어느 프로세스가 CPU를 쓰는지 이름을 적습니다.

## 5. 기록

- `docs/2026-11-18_REAL_TEST.md`에 "B. 기동 지연 수정 확인(지시서 7)" 절을 추가합니다. 형식은 지시서 6의 4장과 같습니다(요약 표, 단계별 상세, 찾은 문제, 확인하지 못한 것).
- 기동 시간 표를 넣습니다.

  | 실행 | discovery | 로봇 | `t_launch` | `t_lidar` | `t_motor` | `t_loc` | `t_nav` | `t_online` | `ssh_lost` |
  | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
  | 16:42 `r1c`(수정 전) | subnet | pinky1 | 10 | 14 | 28 | 26 | 145 | | 1 |
  | 16:42 `r1c`(수정 전) | subnet | pinky2 | 8 | 12 | 20 | 27 | 146 | | 0 |
  | B1 | peers | pinky1 | | | | | | | |
  | B2 | peers | pinky1 | | | | | | | |
  | B2 | peers | pinky2 | | | | | | | |
  | B2 | peers | pinky3 | | | | | | | |

- `docs/TROUBLESHOOTING.md` T-38의 검증에 "실기기 확인(2026-11-18): 결과" 줄을 추가하고, 상단 표의 상태를 결과에 맞게 고칩니다. 원인 추정이 맞았는지(탐색 부하인지 CPU인지)도 결과에 따라 적습니다.
- `docs/REAL_ROBOT_GUIDE.md`: "기동 중에 보이는 것"의 "수십 초 동안 출력이 없을 수 있습니다"를 실제 측정값에 맞게 고치고, 본문의 "실기기 확인 필요"(T-38 관련 4곳)를 결과로 바꿉니다.
- pinky3의 포트·드라이버 결과는 T-37의 검증 줄에도 적습니다.

## 6. 보고 형식

- 단계가 끝날 때마다: 시험 ID별 통과·실패·못 함, 기동 시간 값, 배터리, 다음 단계로 가도 되는지
- 전체가 끝나면: 기동 시간 표, 통과 기준 판정, 찾은 문제, 확인하지 못한 것과 이유, 바뀐 파일 목록, 커밋 메시지 초안. 기획 세션(`frybot-ws-97`)에도 결과 요약을 보냅니다.
- 측정하지 못한 값은 "못 함(이유)"로 적습니다. 추정값을 측정값처럼 쓰지 않습니다.
