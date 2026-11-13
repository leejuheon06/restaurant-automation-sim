# FryBot — 다중 로봇 협업 스마트 레스토랑 (시뮬레이션)

OneTeam 기획안, Confluence 설계 문서(SR v2, 시나리오 v2, State Diagram v4), HW/SW 아키텍처 v007/v008, 매장 맵 치수(200×100 cm)를 기준으로 만든 ROS 2 Jazzy (Gazebo Harmonic) 작업 공간입니다.

## 실행

```bash
cd ~/frybot_ws && colcon build --symlink-install --packages-up-to frybot_bringup && source install/setup.bash
ros2 launch frybot_bringup sim.launch.py            # 경량 시뮬 + RViz
ros2 launch frybot_bringup gazebo.launch.py         # Gazebo + Nav2 (로봇마다 Nav2 스택, costmap 주행)
ros2 run frybot_sim scenario --scenario demo        # 자동 시나리오 (demo | normal | rush | single)
ros2 run frybot_control analyze_run                 # 마지막 실행의 지표 요약 (runs/<run_id>/events.csv)
ros2 run frybot_control fleet_bench --scenario rush # 알고리즘 조합 비교 (ROS 없이 고속 실행)
./scripts/stop_all.sh                               # 전체 종료
```

| 화면 | 주소 |
| --- | --- |
| 입구 접수 / 테이블 주문 / 관리자 | http://localhost:8080 |
| 손님 시뮬레이터 (아키텍처 밖 시험용 UI) | http://localhost:8090 |

AMR 대수는 `robots:=N`(기본 3, 최대 7)으로 정합니다. 이름은 `pinky1..N`이고 조리 팔 2대는 고정입니다. 4번째부터는 충전대가 없어 비켜 서는 곳을 홈으로 쓰고, 배터리가 낮으면 빈 충전대를 빌립니다. 더 늘리려면 `frybot_control/layout.py`의 `HOME_SPOTS`에 자리를 추가합니다. 오프라인 비교는 `fleet_bench --robots N`.

런치 인자: `scheduler:=min_cost|min_cost_eta|min_cost_eta_rh|priority_greedy|fifo_nearest`,
`planner:=sipp|ccbs|cooperative_astar|independent_astar`,
`rviz:=false`, `standby:=false`(대기 위치 미사용), `cook_time_scale:=20`(튀김 10분 → 30초), `undercooked_prob:=0.25`, `qr_vacant_sec:=8`.

## 패키지 (SW 아키텍처 v008 대응)

| 패키지 | 아키텍처 컴포넌트 | 내용 |
| --- | --- | --- |
| `frybot_interfaces` | — | `NavigateRoute`(mode=GUIDE가 GuideGuest), `ArmJob` 액션, 서비스, 메시지 |
| `frybot_control` | Central Control, Task Manager, DB | 식당 상태(State Diagram v4), 임무 배정, 경로 계획, 통행 허가, 조리 셀 조율, 실행 로그 |
| `frybot_web` | Web Service | HTTP ↔ ROS 2 다리. 상태를 갖지 않음 |
| `frybot_sim` | AMR Controller, OneTeamNavigator, Arm Controller, Camera Streamer, AI Server | Pinky Pro 3대, 서빙 팔, 조리 팔 A/B, AI 서버(UDP 입력 → HTTP 결과), 매장·손님 |
| `frybot_bringup` | — | 런치, RViz 설정, URDF 조합 |
| `pinky_pro`, `mycobot_ros2` | — | 외부 저장소. `pinky_description`, `mycobot_description`(JetCobot 280 = myCobot 280 Pi)만 사용 |

통신: 브라우저 —HTTP→ Web Service —ROS 2→ Central Control —ROS 2→ Task Manager —ROS 2 액션→ AMR/팔,
Camera Streamer —UDP→ AI Interface —HTTP→ Central Control.

문제 해결 기록은 [docs/TROUBLESHOOTING.md](../../docs/TROUBLESHOOTING.md), 각 알고리즘의 원리·출처·장단점은 [docs/ALGORITHMS.md](../../docs/ALGORITHMS.md), 조합 선정 보고서는 [docs/ALGORITHM_SELECTION_REPORT.md](../../docs/ALGORITHM_SELECTION_REPORT.md)에 있습니다.

## 알고리즘 교체

- 스케줄러: `frybot_control/schedulers/__init__.py`의 `Scheduler.assign(tasks, robots, cost, now)`
- 경로 계획: `frybot_control/planners/base.py`의 `PathPlanner.plan(graph, request, reservation_table)`
- 새 알고리즘은 클래스를 만들고 `SCHEDULERS` / `PLANNERS`에 등록하면 런치 인자, 관리자 화면, 벤치마크에 바로 나타납니다.
- 실행 중 교체: 관리자 화면의 선택 상자, 또는 `/frybot/admin` 서비스(`SET_SCHEDULER`, `SET_PLANNER`).

기본값은 `min_cost_eta_rh` + `sipp`입니다(20개 조합 비교 결과, docs/ALGORITHM_BENCHMARK.md). 통로가 로봇 한 대 폭(24 cm에 11 cm 로봇)이라 단선 로드맵 위에서
시간까지 계획해야 마주침이 없고, 로봇 3대에 임무 몇 건이면 최소 비용 배정이 즉시 풀리기 때문입니다.

Open-RMF 비교용 플래너 `rmf`(경로 계획), `rmf_nego`(경로 계획 + 협상)와 스케줄러 `rmf_task`(임무 배정)는 도우미를 빌드한 경우에만 목록에 나타납니다: `source /opt/ros/jazzy/setup.bash && cmake -S src/frybot/frybot_control/rmf_bridge -B build/rmf_bridge && cmake --build build/rmf_bridge`. 비교 결과는 docs/ALGORITHM_SELECTION_REPORT.md 10~11장.

### 알고리즘 목록

| 종류 | 이름 | 내용 |
| --- | --- | --- |
| 경로 | `sipp` | 우선순위 SIPP (Phillips & Likhachev 2011). 먼저 계획한 로봇의 예약을 피해 한 대씩 계획 |
| 경로 | `ccbs` | 충돌 기반 탐색 + SIPP 하위 탐색 (CCBS 계열, Andreychuk et al. 2022). 움직이는 로봇을 함께 계획하고, 충돌하면 어느 쪽이 양보할지 양쪽 다 탐색. 탐색 한도(노드 120개, 0.25초)를 넘으면 우선순위 SIPP로 대체 |
| 경로 | `cooperative_astar` | 0.5초 시간 격자 협조 A* (Silver 2005) |
| 경로 | `independent_astar` | 기준선: 각자 최단 경로 + 실행 중 점유 대기 |
| 배정 | `min_cost` | 최소 비용 배정. 비용 = 그래프 최단 거리 기준 이동 시간 |
| 배정 | `min_cost_eta` | 같은 배정, 비용 = 통로 예약 대기를 포함한 플래너의 도착 예상 시각 |
| 배정 | `min_cost_eta_rh` | ETA 배정 + 롤링 호라이즌: 첫 지점에 닿지 않은 임무를 2초마다 재평가해 5초 넘게 줄면 재배정. 손님 안내 중이거나 음식을 실은 임무는 유지 |
| 배정 | `priority_greedy`, `fifo_nearest` | 기준선 |

`min_cost*`는 2026-11-13 전까지 `hungarian*`이라고 불렀습니다. 배정 문제를 풀 뿐 헝가리안 방법을 구현한 것은 아니어서 이름을 바꿨습니다. 로봇 3대 규모에서는 가능한 배정이 수백 가지뿐이라 전수 탐색으로 최적해를 구하고, 로봇이 늘어 후보가 2만 가지를 넘으면 O(n³) 풀이인 SciPy `linear_sum_assignment`(Jonker-Volgenant 변형)로 전환합니다. 옛 이름도 런치 인자와 `fleet_bench`에서 그대로 받습니다.

비교: `ros2 run frybot_control fleet_bench --scenario bottleneck --seeds 3 --schedulers min_cost min_cost_eta_rh --planners sipp ccbs --csv out.csv`
(시나리오 `normal | rush | bottleneck`, `--seeds N`은 손님 도착 시각을 ±4초 흔든 N회 평균). 열: 접수→착석(`seat_avg`),
주문→전달(`deliver_avg`), 조리 완료→전달(`ready_to_deliver`), 점유 대기(`blocked_wait`), 재계획, 계획 시간, 최소 로봇 간격(`min_sep`), 재배정 수.

통행 규칙: 로봇(11×12 cm)이 노드 간격보다 커서, 중심 거리 15.5 cm 미만인 노드는 동시에 점유할 수 없습니다(예약과 실행 락 모두 적용).

## Gazebo + Nav2 구조

- 관제(Task Manager)가 경로와 공유 구간의 통과 순서를 정하고, AMR 노드는 허가받은 구간마다 Nav2 `NavigateToPose`를 보냅니다.
- 로봇마다 `planner_server`(NavFn, 전역 costmap = 매장 맵 + inflation), `controller_server`(Regulated Pure Pursuit, 지역 costmap = 라이다 + inflation, 충돌 예측 시 정지), `bt_navigator`(구간용 BT: 경로 계산 → 추종, 회복 동작 없음)를 네임스페이스로 띄웁니다. 설정은 `frybot_bringup/config/nav2_amr.yaml`.
- `drive:=cmd_vel`은 costmap 없는 예전 직선 주행입니다(비교용).
- 위치 추정은 AMCL 대신 Gazebo의 실제 모델 자세로 map→odom을 보정합니다. 바퀴 오도메트리만 쓰면 바퀴 미끄러짐으로 1 m 넘게 어긋났습니다. 실기에서는 AMCL 등으로 바꿔야 합니다.
- Gazebo 라이다가 주행 중 간헐적으로 무효값만 내보내, 지역 costmap을 1초마다 비우고 최신 스캔으로 다시 채웁니다.
- 손님 안내는 후진 주행입니다(로봇이 손님을 바라보며 안내 속도 0.05 m/s로 후진, Nav2에서는 `speed_limit` 토픽으로 제한).
- 통로가 로봇 한 대 폭이라 제자리 U턴 대신 후진합니다. 경로가 엇갈려 양보(`RETREAT`)할 때는 로봇 뒤쪽의 비켜 서는 곳·대기 위치를 우선 골라 `mode=YIELD`로 후진해 들어가고, 재계획된 경로가 왔던 길로 되돌아가면 처음 1~2구간을 후진합니다.
- 방향 전환은 AMR 노드가 Nav2에 목표를 보내기 전에 직접 합니다(제자리 회전 중 costmap 충돌 판정으로 멈추는 문제 방지). Nav2가 같은 구간을 3번 실패하면 그 구간만 직접 주행합니다.

## 가정한 것 (팀 확인 필요)

- 가운데 4인석(3·4번)은 치수표에서 시계 방향으로 90° 돌려 놓았습니다(긴 변이 세로, 의자는 좌우). 테이블마다 안내 지점(`guide`)과 서빙·회수 지점(`serve`)을 따로 두며 여러 개일 수 있습니다(`layout.py`의 `TABLES`). 3번: 안내 (86,24)·(86,76), 서빙 (70,24)·(70,76). 4번: 안내 (134,24)·(134,76), 서빙 (118,24)·(118,76). Task Manager가 로봇에게 더 빠른 쪽을 고릅니다. 3번 왼쪽에 노드 (50,37), (52,62)를 추가해 위·아래 통로를 이었습니다.

- 비켜 서는 곳(1·2번, 5·6번 사이)과 대기 위치(2·6번 오른쪽)는 경로 그림 기준으로 넣었고 치수는 추정입니다. 유휴 AMR 한 대는 충전대(입구 쪽)에, 나머지는 대기 위치(조리 구역 쪽)에 섭니다. 배터리 40% 미만이면 충전대로 갑니다.
- 퇴식구는 맵 치수표에 없어 조리 구역 가운데(183, 50)로 두었습니다.
- 음식 받는 곳: 후라이드 → 튀김 받는 곳, 양념치킨·볶음밥 → 볶음밥 받는 곳(웍 팔 B가 올림).
- AMR에 붙는 서빙 팔은 실제 크기로는 실을 수 없어 RViz에서 0.3배로 표시합니다.
- DB는 MySQL 대신 실행 폴더의 SQLite 파일입니다(테이블 이름은 논리 모델과 같음).
- AI 서버의 추론은 임계값 모의입니다(익힘: 황금색 비율 0.9 이상, 의자 QR: 보이는 개수).
- 조리 시간은 `cook_time_scale`로 줄였고, 조리팔 동작은 관절 애니메이션입니다(집기·물리 없음).
