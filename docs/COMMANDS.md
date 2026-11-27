# FryBot 명령어 모음

실행 이력: [2026-11-20 실기기 기록](2026-11-20_REAL_TEST.md)에 당시 입력 명령과 실행별 결과가 있습니다. 이 문서의 현재 사용법·시험 초안과 구분해 읽습니다.

상황별로 바로 복사해 쓰는 명령입니다. 전체 구조는 [패키지 README](../src/frybot/README.md), 날짜별 실측과 결정 기록은 [문서 안내](README.md)를 참고합니다.

- 작성: 2026-11-17
- 갱신: 2026-11-19 — 현재 런치·스크립트의 인자와 C6 실기기 결과 반영. 카메라 녹화(5장) 추가. 아래 명령은 소스와 대조했으며, 이번 문서 갱신 중 로봇 기동·이동 명령은 실행하지 않았습니다.
- 모든 명령은 관제 PC의 `~/frybot_ws`에서 실행합니다.
- `<run_id>`, `<관제 PC 주소>`처럼 꺾쇠로 적은 부분은 실제 값으로 바꿉니다.

## 0. 터미널을 열 때마다

```bash
cd ~/frybot_ws && source install/setup.bash
```

| 환경 | 값 |
|---|---|
| `ROS_DOMAIN_ID` | 73 (`~/.bashrc`). 관제 PC와 Pinky 3대가 같은 값 |
| `RMW_IMPLEMENTATION` | 설정하지 않음 (ROS 2 Jazzy 기본 미들웨어) |

시뮬레이션(`sim.launch.py`, `gazebo.launch.py`)은 기본으로 **시뮬 전용 도메인 74**에서 돕니다(`net:=sim`, 2026-11-17 변경). 실기기와 관제 PC는 73이라 Pinky가 켜져 있어도 시뮬의 `/pinky1..3`과 서로 보이지 않습니다. 시뮬에 다른 터미널에서 `ros2` 명령(`ros2 topic list` 등)을 쓸 때는 그 터미널에서 먼저 다음을 실행합니다. 시나리오 실행기(`ros2 run frybot_sim scenario`)와 화면은 HTTP만 쓰므로 필요 없습니다.

```bash
export ROS_DOMAIN_ID=74
```

이 값이 남아 있는 터미널에서는 실제 로봇의 토픽이 보이지 않습니다. 실기기로 돌아갈 때는 다음처럼 도메인을 명시합니다.

```bash
export ROS_DOMAIN_ID=73
```

실기기 등록부는 `~/.config/frybot/robots.yaml`입니다. `real.launch.py`가 설정한 `ROS_STATIC_PEERS`는 다른 터미널에 자동으로 전달되지 않습니다. 별도 터미널에서 로봇이 검색되지 않으면 등록부의 실제 주소를 확인해 `ROS_STATIC_PEERS`를 설정합니다.

| `net` | 동작 |
|---|---|
| `sim` (기본) | 시뮬 전용 도메인(`sim_domain:=74`). Gazebo 통신은 이 PC 안에 묶음 |
| `local` | 도메인은 그대로 두고 탐색을 이 PC로 제한(LOCALHOST). 이 PC에서 Gazebo를 이렇게 띄우면 노드가 서로를 다 찾지 못해 Nav2가 주행하지 못함(T-13, T-29) |
| `lan` | 예전 기본값. 실기기와 같은 도메인이므로 Pinky가 켜져 있으면 쓰지 않음 |

## 1. 빌드

| 하려는 것 | 명령 |
|---|---|
| 전체 빌드 | `colcon build --symlink-install --packages-up-to frybot_bringup` |
| 패키지 하나 | `colcon build --symlink-install --packages-select frybot_control` |
| 빌드 뒤 환경 다시 읽기 | `source install/setup.bash` |

옵션 없는 `colcon build`는 외부 저장소(`mycobot_ros2`)에서 실패합니다.

## 2. 실기기 (Pinky)

### 배포와 점검

| 하려는 것 | 명령 |
|---|---|
| 접속·설치 상태 점검 | `ros2 run frybot_bringup robot_remote --all --check` |
| 코드와 지도를 모든 로봇에 배포 | `ros2 run frybot_bringup robot_remote --all --deploy` |
| 일부 로봇만 배포 | `ros2 run frybot_bringup robot_remote pinky2 pinky3 --deploy` |
| 로봇에 남은 프로그램 정지 | `ros2 run frybot_bringup robot_remote --all --stop` |
| 실제로 실행될 내용만 출력 | `ros2 run frybot_bringup robot_remote pinky1 --deploy --dry-run` |

코드나 지도를 고쳤으면 빌드 → 배포 → 점검 순서로 합니다. 로봇 프로그램이 돌고 있을 때는 배포하지 않습니다.

### 기동

로봇 3대, W1·W2·W3에 놓고 -x 방향(180°)을 향한 경우:

```bash
ros2 launch frybot_bringup real.launch.py map_id:=test_map_v001 poses:=pinky1:W1:180,pinky2:W2:180,pinky3:W3:180
```

한 대만:

```bash
ros2 launch frybot_bringup real.launch.py map_id:=test_map_v001 robots:=pinky1 poses:=pinky1:W1:180
```

두 대를 골라서:

```bash
ros2 launch frybot_bringup real.launch.py map_id:=test_map_v001 robots:=pinky1,pinky3 poses:=pinky1:W1:180,pinky3:W3:180
```

`poses`는 실제 배치와 방향에 맞춰 바꿉니다. 0°는 +x, 180°는 -x입니다. 실측 지도·Nav2/AMCL에서 `poses`를 빼고 로봇 런치의 `auto_localize`가 켜져 있으면 라이다 스캔으로 자기 자세를 찾습니다(2026-11-20, T-49). 로그 `auto localisation OK`·`OK_SAVED`·`OK_HOME`이면 성공이고, `failed: AMBIGUOUS/NO_MATCH`이면 RViz 2D Pose Estimate로 정합니다. `auto_home` 기본은 2026-11-20부터 `false`(연결된 로봇은 제자리 대기)입니다.

| 인자 | 기본값 | 내용 |
|---|---|---|
| `map_id` | 없음 | 항상 적습니다 |
| `robots` | 등록된 로봇 전부 | `2` 또는 `pinky1,pinky3` |
| `poses` | 없음 | `로봇:노드[:방향(도)]`. 로봇이 실제로 서 있는 노드. 실측 지도·Nav2/AMCL에서 생략하면 기본 자동 스캔 위치 추정(T-49). 실패·비활성화 시 RViz의 2D Pose Estimate로 지정 |
| `rviz` | `true` | 전역·지역 코스트맵·로봇 모델 표시. `false`면 RViz와 `fleet_rviz` 중계 노드를 함께 끔 |
| `rviz_wait` | `false` | `true`면 모든 로봇의 첫 상태 보고 뒤 RViz 시작. Nav2 active 완료를 기다리는 것은 아님. 초기 자세가 빠진 로봇이 있으면 즉시 시작(T-40) |
| `rviz_wait_sec` | `120` | 지연 시작의 최대 대기 시간(초). 시간 초과 시에도 RViz 시작 |
| `auto_home` | `false` | 2026-11-20부터 기본 `false`(이전 `true`). `true`면 위치가 잡힌 로봇이 출발 노드로 한 번 이동 |
| `discovery` | `peers` | `peers` 또는 `subnet`. 기본은 관제–로봇 직접 탐색 |
| `robots_file` | 빈 값 | 기본 등록부 사용. 다른 등록부는 경로 지정 |
| `speed` | `0.08` | 관제 계획 속도(m/s) |
| `plan_overhead` | `0.0` | 계획의 구간 지연(초). 보정 후보 `2.27`은 기본값이 아님 |
| `prefer_yield` | `true` | `false`면 양보 없이 우회 |
| `remote` | `true` | `false`면 관제만 띄움. 이때 `robots:=`를 반드시 적음 |

종료는 런치 터미널에서 Ctrl-C입니다. 로봇 쪽도 함께 멈춥니다.

<!-- [수정 2026-11-23] T-55: 천장 카메라 위치 판정 준비 -->
<!-- [수정 2026-11-26] T-60: 바퀴 값을 줄자 기준으로 갱신 -->
### 로봇별 바퀴 치수 (2026-11-24 T-58, 2026-11-26 T-60 줄자 기준으로 갱신)

세 대의 바퀴 반지름·간격이 조금씩 달라 같은 명목값(0.027·0.0961 m)을 쓰면 오도메트리가 로봇마다 어긋납니다(pinky3 직진 2.4% 짧게, 회전 ±1%). 등록부 `~/.config/frybot/robots.yaml`의 로봇 항목에 실측값을 적습니다.

```yaml
robots:
  pinky3:
    host: ...
    wheel_radius: 0.02737      # m
    wheel_separation: 0.0983   # m
```

| 로봇 | `wheel_radius` | `wheel_separation` | 근거(2026-11-26, 1 m 직진 줄자÷odom 3회 평균, 360도 회전 ICP÷odom 좌/우) |
|---|---|---|---|
| pinky1 | 0.02743 | 0.0966 | 0.9990, 1.00029/0.99987 |
| pinky2 | 0.02735 | 0.0977 | 1.0015, 1.00079/1.00168 |
| pinky3 | 0.02737 | 0.0983 | 1.0011, 1.00015/1.00003 |

- 근거 자료: `runs/20261126_01_hwfinal_wheel_verify/report.md`. 이전 값(2026-11-24 MT-3, 정지 스캔 맞춤 기준) 0.02706·0.0953, 0.02685·0.0960, 0.02763·0.0992는 라이다로 잰 이동의 로봇별 치우침이 들어가 줄자와 어긋났습니다(1 m 줄자÷odom 1.0096·1.0108·0.9956, T-60).
- 계산: 직진은 반지름 = 지금 반지름 × (줄자÷odom). 간격도 같은 비율로 바꿔 회전 보정(간격÷반지름)을 유지합니다. 회전만 어긋나면 간격만 바꿉니다(간격 = 지금 간격 × (odom 회전÷실제 회전)).
- 확인: `ros2 run frybot_bringup robot_remote pinky3 --map-id test_map_v05 --dry-run` 출력에 `[pinky3] 바퀴 치수(등록부): ...`와 `wheel_radius:=0.02737 wheel_separation:=0.0983`이 보입니다. 로봇 기동 로그에는 `[pinky3] wheel_radius 0.02737 m, wheel_separation 0.0983 m (robot value)`, `pinky_driver`의 `Wheel radius: 0.02737`이 찍힙니다(2026-11-26 T3 에서 세 대 확인). 키가 없으면 `(nominal)`입니다.
- 손으로 띄울 때: `ros2 launch frybot_mobile robot.launch.py robot_id:=pinky3 map_id:=test_map_v05 wheel_radius:=0.02737 wheel_separation:=0.0983`. 한 번만 바꿔 볼 때는 `robot_remote ... --arg wheel_radius:=...`(등록부 값을 덮어씀).
- 명목값에서 10% 넘게 벗어나거나 숫자가 아니면 로봇 런치가 멈춥니다(cm·mm 단위 실수 방지). `drivers:=pinky_pro`이면 외부 드라이버를 쓰므로 이 값은 쓰이지 않습니다(로그에 ignored). `bringup.launch.py`(드라이버만, teleop용)는 아직 명목값입니다.
- 다시 재는 법(바퀴가 돌므로 배치·여유 확인 뒤): 직진은 바닥 줄자로 잽니다. 로봇을 줄자 옆에 놓고 1 m 를 0.08 m/s 로 3번 전진하며 매번 출발·도착 눈금을 mm 로 읽어 줄자÷odom 평균이 1±0.003 인지 봅니다(측정 스크립트 `runs/20261126_01_hwfinal_wheel_verify/scripts/hw_line.sh`, `--start-hold 15 --first-hold 30 --hold-all`, 바퀴 값을 인자로 넘김). 라이다(ICP·앞벽)로 잰 직진 거리는 로봇마다 0~1.3 % 짧게 나와 바퀴 값의 기준으로 쓰지 않습니다(T-60). 회전은 정지 스캔 ICP 로 잽니다(같은 폴더의 `scripts/mt6_v1.sh <robot> <prefix> <반지름> <간격> --reps 0 --turn-reps 1`, 목표 1±0.003).

### cmd_vel 감시 시간 (2026-11-24, 기본 0.3 s는 2026-11-25 MT-7)

`pinky_driver`는 `cmd_vel`이 `cmd_vel_timeout`(기본 0.3 s, 2026-11-25부터. 이전 0.5 s) 넘게 끊기면 0 RPM을 보냅니다. 판정은 30 Hz 타이머라 실제로는 0~33 ms 늦습니다. 끊긴 뒤 0.08 m/s에서 더 가는 거리는 0.3 s일 때 3.3~3.7 cm(MT-6 실측, 세 대), 0.5 s일 때 약 5 cm(MT-3 실측)입니다.

- 바꿔 띄우기(예: 예전 값 0.5 s): `ros2 run frybot_bringup robot_remote pinky1 --map-id test_map_v05 --arg cmd_vel_timeout:=0.5`, 또는 등록부 로봇 항목의 `launch_args: {cmd_vel_timeout: "0.5"}`. 손으로 띄울 때는 `robot.launch.py ... cmd_vel_timeout:=0.5`.
- `real.launch.py`는 이 인자를 넘기지 않습니다. 관제와 함께 바꾸려면 등록부 `launch_args`를 쓰거나, `real.launch.py remote:=false robots:=...`로 관제만 띄우고 로봇은 `robot_remote <로봇> --arg cmd_vel_timeout:=...`로 하나씩 띄웁니다.
- 확인: 로봇 기동 로그 `[pinky1] cmd_vel_timeout 0.5 s (launch arg)`(인자가 없으면 `0.3 s (node default)`). 0 이하는 감시를 끄므로 `WARNING ... watchdog is OFF`가 찍힙니다. 2 s를 넘거나 숫자가 아니면 런치가 멈춥니다.
- 시간 초과로 섰을 때 드라이버 로그: `cmd_vel silent for 0.32 s: motors stopped`(0.5 s 때는 0.53 s 정도).
- 기본값을 0.3 s로 정한 근거(2026-11-25, MT-6): 세 대 동시 20회 왕복을 0.5 s·0.3 s로 각각 돌려 로봇 안에서 기록한 `cmd_vel` 간격이 최대 67 ms, 0.3 s를 넘은 간격·`cmd_vel silent` 모두 0회(runs/20261125_02_mt6_v2_cmdvel_onboard_t05, runs/20261125_03_mt6_v3_cmdvel_t03 의 report.md).

### 천장 카메라 위치 판정 준비 (2026-11-23, 실기기 확인 필요)

로봇 자동 위치 추정이 모호할 때(대칭 자리) 관제 PC의 천장 카메라로 후보를 고릅니다(`ceiling_locator`, `real.launch.py`에서 기본으로 뜸). 카메라는 맵 전체가 보이는 지금 자리(`/dev/video0`)를 그대로 씁니다. 판정 근거와 한계는 TROUBLESHOOTING T-55에 있습니다.

| 하려는 것 | 명령 |
|---|---|
| 빈 바닥 기준 화면 저장(맵 안에 로봇·사람이 없을 때, 처음 한 번) | `ros2 run frybot_control ceiling_tool reference --map-id test_map_v05` |
| 지금 화면으로 후보 점수 확인 | `ros2 run frybot_control ceiling_tool check --map-id test_map_v05 --at 0.091,-0.552 1.641,0.192` |
| 바닥 마커 인쇄 파일(한 변 8 cm, 이미 만든 것: `archive/ceiling_markers_2026-11-23/`) | `ros2 run frybot_control ceiling_tool print-markers --out <폴더>` |
| 붙인 마커의 지도 좌표(roadmap.json 에 넣을 조각) | `ros2 run frybot_control ceiling_tool markers --map-id test_map_v05` |
| 천장 카메라 판정 없이 띄우기(로봇도 카메라를 기다리지 않음, T-57) | `ros2 launch frybot_bringup real.launch.py map_id:=test_map_v05 ceiling_camera:=false` |
| 로봇 한 대를 직접 띄울 때 카메라 문의 끄기 / 대기 상한 바꾸기 | `ros2 run frybot_bringup robot_remote pinky1 --map-id test_map_v05 --arg localize_camera:=false` / `--arg localize_camera_wait_sec:=45.0` |

- 기준 화면은 `~/.frybot/ceiling/<map_id>/reference.png`에 저장됩니다. 없으면 노드는 `NO_REFERENCE`로 답하고 로봇은 예전 규칙(저장 자세 → 홈)으로 갑니다.
- 가구(테이블·의자)를 옮겨도 기준 화면은 2분마다 자동으로 따라갑니다. 다만 관제가 띄운 로봇이 모두 위치가 잡힌 채 서 있고, 화면에 움직임이 없고, 각 로봇이 보고한 자리에 카메라로도 보일 때만입니다. 로봇 자리는 옛 화소를 둡니다. 꺼진 채 맵 안에 놓인 로봇은 관제가 모르므로, 그런 로봇이 있으면 `reference`로 다시 저장합니다.
- 마커 붙이기: DICT_4X4_50의 40~43을 바닥 네 모서리 근처에 붙입니다(로봇이 지나지 않는 곳, 평평하게). 오른쪽 위 바닥 모서리는 카메라 화면 밖이라, 41번은 오른쪽 벽에서 약 25 cm 안쪽에 둡니다. 붙인 뒤 `markers`의 출력 조각을 `frybot_control/frybot_control/maps/<map_id>/roadmap.json`에 넣고 다시 빌드합니다. 4개 이상 보이면 매번 마커로 대응을 구하고, 아니면 벽 바닥선 수동 대응을 씁니다(로그·`reason`의 `calib=`).
- 노드 로그: 요청마다 `spot check <로봇>: [후보] -> ok=... [점수] <이유>`. 로봇 로그는 `auto localisation OK_CAMERA ...` 한 줄에 `camera [...]`(점수와 이유)가 붙습니다.
- <!-- [수정 2026-11-23] T-57 --> 로봇은 모호할 때 노드가 뜬 뒤 35초(`localize_camera_wait_sec`)까지 서비스를 찾고 답을 기다리며, 응답이 3초 안에 없으면 다시 요청합니다. 세 대를 함께 띄우면 기동 중인 로봇이 서비스를 찾는 데 20~28초 걸렸습니다(T-57). 로봇 로그 `camera: waiting for ...`, `camera: service found after ...`, `camera: answer after ...` 세 줄로 걸린 시간을 봅니다. 기다리는 동안 관리자 화면 상태는 '기동·초기 점검 중'(`LOCALIZING`)입니다.

<!-- [수정 2026-11-20] 서빙 팔 시험 순서 초안 -->
### 서빙 팔 시험 (pinky1 + jetcobot1, `test_map_v04`) — 초안, 실기기 확인 필요

아직 실기기에서 돌려 보지 않은 순서입니다. 현재 `LOAD`·`UNLOAD`는 밑동을 좌우 30도로 움직이는 시험용 동작이며 실제 음식 전달 자세가 아닙니다.

<!-- [수정 2026-11-20] rest 를 주행용 접은 자세로 바꿈 -->
<!-- [수정 2026-11-20] rest J5 74 → 0(유지 발열), 속도 기본 10 → 70 -->
<!-- [수정 2026-11-20] 속도 기본 70 → 60(70 에서 육안 흔들림, 사용자 결정) -->
<!-- [수정 2026-11-26] 작업 이름 통일(HOME = 0도 home, REST = rest)과 자세 연동 -->
`rest`는 주행용 접은 자세 `[0, 122, -148, 143, 0, 60]`이고 그리퍼는 닫습니다(`rest_gripper: 0`). `home`은 0도 자세 `[0, 0, 0, 0, 0, 0]`(충전소 대기)입니다. 작업 이름은 2026-11-26에 `REST`(rest로 감, 예전 `HOME`)와 `HOME`(0도로 감)으로 바뀌었습니다. 자세가 있는 작업은 `home` → 작업 자세 → `rest`로 끝나고, 속도 기본은 60입니다. 측정 근거는 [2026-11-20_SERVING_ARM_REST_POSE.md](2026-11-20_SERVING_ARM_REST_POSE.md)에 있습니다.
실물 팔은 평평한 테이블 위에서 동작하며, 판단 기준은 유지 발열·재현성·왕복 시간·자기 간섭입니다(2026-11-21 전제 정정). AMR 탑재 주행 안정성·라이다 간섭은 검증 대상에서 제외합니다.
- 실물에서 확인한 것(`send_angles` 직접 호출): 0도 ↔ `rest` 왕복, 간섭 없음, J5 0도 유지 발열, 이전 J5 74도 자세에서 속도 20~70의 관측 가능한 구간의 목표 초과·발열. 새 J5 0도 자세에서는 속도 20 접기 한 번과 속도 70·60 왕복을 측정했고, 70에서 육안 흔들림이 있어 60으로 정했습니다(측정 문서 7.1절).
- 아직 확인하지 못한 것: 구동부 액션을 거친 `REST`·`HOME`·작업 앞 0도·작업 끝 접기, 속도 80 이상, 음식을 든 상태.
- 구동부는 기동할 때 자동으로 접지 않습니다. `serving_arm:=real`로 띄운 로봇은 주행 전에 `mobile_controller`가 `REST`를 보내 접고, 자기 충전소에 도착하면 1초 뒤 `HOME`으로 폅니다(2026-11-26, 경량 시뮬 확인, 실기기 확인 필요). 손으로 접을 때는 `REST` 작업을 보냅니다: `ros2 action send_goal /pinky1/arm_job frybot_interfaces/action/ArmJob "{task_id: 'a01', arm_id: 'pinky1', job: 'REST', duration: 3.0, params_json: '{}'}"`.
- 구동부가 없으면(팔 Pi 꺼짐) 주행 전 접기가 `ARM_OFFLINE`으로 실패해 로봇이 출발하지 않습니다. 팔 없이 주행 시험을 할 때는 `serving_arm`을 비워 띄웁니다.
- 액션의 `REST`·`HOME`·작업 성공 여부와 실물 관절 자세를 확인합니다. RViz의 AMR 팔 모델은 별도 대역 자세를 사용하므로 실제 접힘 완료 표시가 아닙니다.

1. 배포: `ros2 run frybot_bringup robot_remote pinky1 --deploy` (팔 Pi는 `frybot_interfaces`, `frybot_mobile`만 직접 복사·빌드, 배포 기능 없음)
2. 팔 Pi 명령 확인: `ros2 run frybot_bringup robot_remote jetcobot1 --arm-command --mount pinky1` → 출력된 한 줄을 `ssh jetcobot@<팔 주소>` 안에서 실행. 팔이 `rest` 자세에 있고 주변이 비어 있는지 먼저 확인
3. 관제 + pinky1 기동: `ros2 launch frybot_bringup real.launch.py map_id:=test_map_v04 robots:=pinky1 poses:=pinky1:W1:<방향>`. 등록부 `arms`에 `enabled`인 팔의 `mount`에 pinky1이 있으면 `serving_arm:=real`과 팔 주소가 자동으로 붙음(로그 `[pinky1] 서빙 팔 jetcobot1 ...`). jetcobot1은 `mount: [pinky1, pinky2, pinky3]`(팔 한 대를 옮겨 가며 씀)이라, 팔을 pinky2로 옮길 때는 기존 팔 구동부를 종료하고, 2단계에서 `--mount pinky2`로 생성한 명령으로 다시 실행합니다. 3단계의 `robots:=pinky2`와 `poses:=pinky2:<실제 노드>:<방향>`도 함께 바꾸고, 4단계 액션 이름은 `/pinky2/serving_arm/arm_job`으로 확인합니다. 관제는 등록부 `mount`에서 얻은 `serving_robots`에만 서빙을 배정합니다. `mount` 목록은 실제 장착 위치를 감지하지 않으므로, 팔 없는 로봇이 목록에 포함돼 있다면 `serving_robots:=pinky1`처럼 실제 장착 로봇을 명시해야 합니다(2026-11-20, T-47). 기동 로그 `serving robots (SERVE, COLLECT): ['pinky1']`로 확인
4. 연결 확인: `ros2 action list | grep serving_arm` 에 `/pinky1/serving_arm/arm_job`
5. 임무: `ros2 service call /fms/submit_task frybot_interfaces/srv/SubmitTask "{task_type: 'SERVE', table_id: 1, menu: 'FRIED'}"`
6. 결과: `grep -E "TASK_|ARM_" runs/<run_id>/events.csv`, pinky1 로그의 `docked at D1_STOP` 줄(남은 거리·옆 오차·방향 오차)
7. 비상 정지는 3장의 `ESTOP`. 구현상 팔 작업 중이면 팔 쪽 목표를 취소해 정지를 요청합니다. 실제 팔의 정지 여부·응답 시간은 실기기 시험에서 확인해야 합니다.

### 이동 없이 상태·부하를 관찰할 때

실제 위치와 방향을 맞춘 뒤 자동 홈 이동과 RViz를 끄고 기동합니다. 별도의 이동 명령은 보내지 않습니다.

```bash
ros2 launch frybot_bringup real.launch.py map_id:=test_map_v001 robots:=pinky1,pinky2,pinky3 poses:=pinky1:W1:180,pinky2:W2:180,pinky3:W3:180 auto_home:=false rviz:=false
```

필요할 때 다른 터미널에서 RViz를 붙입니다(0장의 실기기 도메인 설정 적용).

```bash
ros2 launch frybot_bringup fleet_rviz.launch.py robots:=pinky1,pinky2,pinky3
```

전역 코스트맵 **표시**는 현재 기본 켬입니다. C6-C에서 켬/끔 각 3회 비교 시 끊김은 20/17건, 2초 초과는 8/7건으로 뚜렷한 차이를 확인하지 못해 사용자 결정으로 다시 켰습니다. 기동 시간 비교는 배터리 때문에 하지 않았습니다. 표시를 끄는 것과 Nav2 코스트맵 계산을 끄는 것은 다릅니다. 자세한 조건은 [C6 실측 기록](2026-11-19_REAL_TEST.md)의 C6-C절을 참고합니다.

`rviz_wait`는 C4에서 RViz 시작 직후 최대 7.8초 끊김이 관찰돼 기본 `false`로 복귀했습니다. 지연 시작을 비교하려는 경우에만 기동 명령에 `rviz_wait:=true rviz_wait_sec:=120`을 붙입니다.


### 그 밖의 실기기 명령

| 하려는 것 | 명령 |
|---|---|
| 로봇 쪽만 SSH로 기동 (관제 없이) | `ros2 launch frybot_bringup robots.launch.py map_id:=test_map_v001` |
| 로봇 한 대만 SSH로 기동 | `ros2 run frybot_bringup robot_remote pinky1 --map-id test_map_v001` |
| 예전 드라이버(`pinky_pro`)로 기동 | `ros2 run frybot_bringup robot_remote pinky1 --map-id test_map_v001 --arg drivers:=pinky_pro` |
| RViz만 따로 띄우기 (`robots`를 비우면 등록된 로봇 전부) | `ros2 launch frybot_bringup fleet_rviz.launch.py robots:=pinky1,pinky2,pinky3` |
| 로봇을 노드에 놓고 자세 다시 맞추기 (임시 도구, `test_map_v001`만) | `python3 scripts/relocalize.py pinky1:B1 pinky3:A1 --send` |
| Pinky 안에서 직접 기동 | `ros2 launch frybot_mobile robot.launch.py robot_id:=pinky1 map_id:=test_map_v001` |
| Pinky 안에서 드라이버만 기동 (로봇 모델·라이다·모터·배터리, Nav2·제어기 없음. 수동 조종·센서 점검용, 2026-11-24) | `ros2 launch frybot_mobile bringup.launch.py robot_id:=pinky1` (`robot.launch.py`와 함께 띄우지 않음. 종료는 Ctrl-C) |
| 키보드 수동 조종 (관제 PC, 위 드라이버가 떠 있을 때) | `ros2 run teleop_twist_keyboard teleop_twist_keyboard --ros-args -r cmd_vel:=/pinky1/cmd_vel -p speed:=0.08 -p turn:=0.5` |

### 상태 확인

| 확인할 것 | 명령 |
|---|---|
| 로봇 상태 보고 | `ros2 topic echo /fleet/robot_status --once` |
| 라이다 주기 | `ros2 topic hz /pinky1/scan` |
| Nav2 기동 여부 (`active`면 정상) | `ros2 lifecycle get /pinky1/bt_navigator` |
| 관제 생존 신호 (5 Hz) | `ros2 topic hz /fms/heartbeat` |
| 통행 허가 | `ros2 topic echo /fms/traffic_grant` |
| 배터리 | `ros2 topic echo /pinky1/battery/percent --once` |
| 로봇의 런치 로그 (Pinky 안에서) | `tail -f ~/.frybot/robot_launch.log` |

### 손님 추적 AI 서버 (2026-11-24, 실기기 안내 주행 확인 필요)

Pinky 카메라 영상을 관제 PC(노트북)가 직접 받아 YOLO로 사람을 찾고 `GUEST_TRACK`을 `central_control`(:8100)로 보냅니다. 처음 한 번 `python3 -m venv ~/venv/yolo && ~/venv/yolo/bin/pip install ultralytics`로 가상 환경을 만듭니다(2026-11-24: ultralytics 8.4.218, torch 2.15 + CUDA). 가중치는 `~/.frybot/models/`에 처음 실행 때 내려받습니다.

| 상황 | 명령 |
| --- | --- |
| Pinky에서 카메라 송신 (로봇에 배포 뒤) | `ros2 launch frybot_mobile camera_streamer.launch.py` (기본 640×480 15 fps·품질 70, TCP 8554) |
| 관제 PC에서 손님 추적 (등록부의 모든 로봇) | `ros2 launch frybot_ai guest_tracker.launch.py` |
| 일부 로봇만 / 회전 지정 | `... cameras:=pinky1=192.168.0.9,pinky2=192.168.0.29@180` |
| 추적기 바꾸기 (시험 C) | `... tracker:=botsort` / `tracker:=bytetrack` (기본 `botsort_reid`) |
| 모델 바꾸기 | `... model:=yolo11s.pt` / `model:=yolo26s.pt` (기본 `yolov8s.pt`) |
| 관제 없이 화면만 | `... central_url:=none` |
| 모델 비교용 원본 프레임 녹화 | `... record:=<폴더>` (`<폴더>/pinky1/NNNNNN.jpg`, `frames.csv`) |

- 확인 화면: http://127.0.0.1:8095 (주황 상자가 손님, 거리 표시), 결과 JSON: http://127.0.0.1:8095/detections
- pinky1·2·3 카메라는 거꾸로 달려 있어 기본 `rotate:=180`입니다(2026-11-24 세 대 화면 확인). 로봇마다 다르면 등록부에 `camera_rotate: cw` 등을 적습니다.
- 손님 고정: 안내 시작 때 가장 앞 사람으로 고정, 자리 안내 완료 때 해제. `central_control`이 `ai_guides_url`(기본 `http://127.0.0.1:8095/guides`, `none`이면 끔)로 목록을 보냅니다.
- 세 대를 30 fps·품질 93으로 보내면 Wi-Fi가 약한 로봇에서 수 초 지연이 쌓였습니다(2026-11-24). 지연이 보이면 로봇에서 `ss -tni sport = :8554`의 Send-Q(송신 대기)를 봅니다.
- 카메라 스트림에는 한 번에 하나만 붙습니다. `guest_tracker`가 붙어 있으면 다른 뷰어는 연결되지 않습니다.

## 3. 관제 화면과 이동 명령

| 화면 | 주소 |
|---|---|
| 관리자 (통합 관제, 테이블·주문, 알람·이력, 설정) | http://localhost:8080/admin |
| 입구 접수 | http://localhost:8080/reception |
| 테이블 주문 | http://localhost:8080/table?id=1 |
| 손님 시뮬레이터 (가상 매장 시뮬에서만) | http://localhost:8090 |

다른 기기에서는 `localhost` 대신 관제 PC 주소를 씁니다. 실기기의 관리자 명령은 기본으로 관제 PC에서만 허용하며, 다른 기기의 명령에는 런치에서 설정한 `admin_token`을 `X-Admin-Token` 헤더로 전달해야 합니다. 접수와 테이블 주문은 가상 매장(`proto`)에서만 동작합니다.

이동 명령은 관리자 화면의 운영 지도에서 로봇과 목적 노드를 고르고 **이동 명령**을 누릅니다. 터미널에서는:

```bash
curl -s -X POST -H 'Content-Type: application/json' -d '{"command":"MOVE_TO_VERTEX","target":"pinky1","arg":"B5"}' http://localhost:8080/api/admin/operations
```

개별 로봇 비상 정지와 재개(관제 PC에서 실행):

```bash
# pinky2 비상 정지
curl -s -X POST -H 'Content-Type: application/json' -d '{"command":"ESTOP","target":"pinky2"}' http://localhost:8080/api/admin/operations
# 정지 원인을 확인하고 주행을 재개할 때
curl -s -X POST -H 'Content-Type: application/json' -d '{"command":"RESUME","target":"pinky2"}' http://localhost:8080/api/admin/operations
```

C6-B에서 개별 비상 정지 시 odom 정지까지 0.34~0.41초가 측정됐습니다. 이는 당시 조건의 실측이며 모든 조건의 정지 시간을 보장하는 값은 아닙니다.

| 확인할 것 | 명령 |
|---|---|
| 관제 상태(JSON) | `curl -s http://localhost:8080/api/state` |
| 지도 목록 | `curl -s http://localhost:8080/api/maps` |
| 최근 이벤트 | `curl -s http://localhost:8080/api/events` |

`test_map_v001`의 노드: `A1`~`A8`, `B1`~`B7`, `C1`~`C3`, `W1`~`W3`과 중간 노드(`B4_B5` 등). 출발 노드는 pinky1 `W1`, pinky2 `W2`, pinky3 `W3`입니다.

## 4. 시뮬레이션

### 가상 매장 (`proto`, 접수부터 서빙까지)

터미널 1:

```bash
ros2 launch frybot_bringup sim.launch.py
```

터미널 2:

```bash
ros2 run frybot_sim scenario --scenario demo
```

- 시나리오는 `demo`(약 4분), `normal`, `rush`, `single`입니다.
- `map_id`를 생략하면 `proto`입니다.

### 실측 지도 (노드 간 이동만)

```bash
ros2 launch frybot_bringup sim.launch.py map_id:=test_map_v001
```

- 관제와 가상 로봇 3대, 그 지도만 표시하는 RViz가 뜹니다. 매장·손님·조리 팔·AI 서버와 8090 화면은 뜨지 않습니다.
- 이동 명령은 3장과 같습니다.
- 자세를 직접 움직이는 방식이라 Nav2·라이다·AMCL을 거치지 않고, 소요 시간이 실기기와 다릅니다.
- 다른 지도: `map_id:=test_map_v002`

<!-- [수정 2026-11-20] 실측 지도 서빙 시험(test_map_v04) -->
### 실측 지도 서빙 시험 (`test_map_v04`, 2026-11-20)

`test_map_v04`는 `roadmap.json`에 `stations`(음식 받는 곳 = `D1_STOP`, 테이블 1 = `B4`)와 `docks`(`D1_STOP`, 마커 없음)가 있어 서빙 임무를 받습니다. 흐름: W1 → D1_STOP(도킹) → LOAD → B4 → UNLOAD.

```bash
# 터미널 1
ros2 launch frybot_bringup sim.launch.py map_id:=test_map_v04 robots:=1 rviz:=false
# 터미널 2 (export ROS_DOMAIN_ID=74 먼저)
ros2 service call /fms/submit_task frybot_interfaces/srv/SubmitTask "{task_type: 'SERVE', table_id: 1, menu: 'FRIED'}"
grep -E "TASK_|ARM_" runs/<run_id>/events.csv
```

- 서빙 팔 전달을 시험하려면 런치에 `serving_arm:=real`을 붙이고 `/pinky1/serving_arm/arm_job` 액션 서버(가짜 서버 또는 실물 `serving_arm_driver`)를 띄웁니다. 서버가 없으면 LOAD가 `ARM_OFFLINE`으로 끝나고 임무가 `SUSPENDED`가 됩니다.
- 팔 작업 중 비상 정지: `ros2 service call /fms/command frybot_interfaces/srv/FleetCommand "{command: 'ESTOP', target: 'pinky1', arg: ''}"`. 팔 쪽 목표가 취소됩니다.
- 경량 시뮬은 자세를 직접 움직여 도킹 단계를 실제로 거치지 않습니다. 실기기 도킹은 확인 필요입니다.

<!-- [수정 2026-11-20] test_map_v05 2대 시험(T-46, T-47) -->
### 실측 지도 2대 시험 (`test_map_v05`, pinky1 팔 있음 + pinky2 팔 없음, 2026-11-20)

`test_map_v05`는 v04에서 오른쪽 도크 쪽을 지우고 D1_STOP을 벽에서 4 cm 물린 지도입니다(README 지도 표). D1_STOP에 로봇이 서 있으면 교차점 D1_IN이 잠깁니다.

```bash
# 경량 시뮬: SERVE 는 pinky1 에만
ros2 launch frybot_bringup sim.launch.py map_id:=test_map_v05 robots:=2 rviz:=false serving_robots:=pinky1
# 실기기: 등록부 mount 로도 자동 지정되지만, 이 시험은 실제 장착 로봇 pinky1 을 명시
ros2 launch frybot_bringup real.launch.py map_id:=test_map_v05 robots:=pinky1,pinky2 poses:=pinky1:W1:<방향>,pinky2:W2:<방향> serving_robots:=pinky1
# 초기 자세 없이(로봇이 스캔으로 자세를 찾음, T-49). 연결된 로봇은 제자리 대기
ros2 launch frybot_bringup real.launch.py map_id:=test_map_v05 robots:=pinky1,pinky2 serving_robots:=pinky1
# 오프라인 비교
ros2 run frybot_control fleet_bench --scenario moves --map-id test_map_v05 --robots 2 --check
```

- 관제 로그 `serving robots (SERVE, COLLECT): ['pinky1']`, 이벤트의 `TASK_ASSIGN`이 모두 pinky1인지 확인합니다. pinky1이 바쁘면 다음 서빙은 pinky2가 놀고 있어도 기다립니다.
- 2026-11-20 `fleet_bench --scenario moves --map-id test_map_v05 --robots 2 --check`는 기본 조합(`sipp`)이 **실패**합니다(20초 넘는 의도된 대기 18건, 최대 39초, 전체 소요 641초. 같은 조건 v04는 164초로 통과). `independent_astar`만 통과합니다. 주행 시험 전에 확인이 필요합니다.
- 도킹·막다른 곳 전진 출발의 앞 라이다 정지(T-46)는 로봇 로그 `stopped by the front lidar`, `docked at D1_STOP (...) front lidar NN mm`로 봅니다.

### Gazebo + Nav2 (가상 매장 전용)

```bash
ros2 launch frybot_bringup gazebo.launch.py
```

화면 없이 돌리려면 `gui:=false rviz:=false`를 붙입니다.

### 조리 팔 대역만

```bash
ros2 launch frybot_arm cooking.launch.py
```

### 시뮬 런치 인자

| 인자 | 기본값 | 내용 |
|---|---|---|
| `map_id` | `proto` | 지도 이름 (`sim.launch.py`) |
| `net` | `sim` | 시뮬 전용 도메인 사용. `local`, `lan`의 차이는 0장 참고 |
| `sim_domain` | `74` | `net:=sim`일 때 시뮬 도메인 |
| `robots` | `3` | 로봇 대수. 실측 지도는 3대까지, 가상 매장은 7대까지 |
| `rviz` | `true` | RViz 표시 |
| `scheduler` | `min_cost_eta_rh` | `min_cost`, `min_cost_eta`, `priority_greedy`, `fifo_nearest` |
| `planner` | `sipp` | `ccbs`, `cooperative_astar`, `independent_astar` |
| `standby` | `true` | 유휴 로봇의 대기 위치 사용 |
| `cook_time_scale` | `20` | 조리 시간 축소 |
| `undercooked_prob` | `0.25` | 덜 익음 판정 확률 |
| `gui` | `true` | Gazebo 화면 (`gazebo.launch.py`) |
| `drive` | `nav2` | `cmd_vel`이면 코스트맵 없는 직선 주행 (`gazebo.launch.py`, 비교용) |
| `serving_arm` | 없음 | `real`이면 서빙 팔 작업을 `/<로봇>/serving_arm/arm_job`으로 넘김 (`sim.launch.py`, 2026-11-20) |
| `serving_robots` | 없음 | SERVE·COLLECT를 맡길 로봇(쉼표). 비우면 모든 로봇 (`sim.launch.py`, 2026-11-20, T-47) |

## 5. 결과 확인

| 하려는 것 | 명령 |
|---|---|
| 최근 실행 폴더 | `ls -t runs \| head -3` |
| 지표 요약 | `ros2 run frybot_control analyze_run runs/<run_id>` |
| 실기기 기록을 모의 실행과 비교 | `ros2 run frybot_control replay_run runs/<run_id> -v` |
| 실측 시간 모델로 비교 | `ros2 run frybot_control replay_run runs/<run_id> --model measured -v` |
| 양보가 일어나는 명령 조합 찾기 | `ros2 run frybot_control replay_run --find-yield --map-id test_map_v001` |
| 구간 지연을 넣은 계획으로 재생 (2026-11-18, W10에서 인자 의미 변경: `--plan-speed`는 런치의 `speed:=`와 같음) | `ros2 run frybot_control replay_run runs/<run_id> --model measured --plan-overhead 2.27 --plan-speed 0.135` |
| 양보·복귀·재시도 이벤트만 보기 | `grep -E "YIELD\|RETREAT\|PLAN_WAIT\|REJOIN\|ROUTE_RETRY" runs/<run_id>/events.csv` |

- `analyze_run`에는 폴더 경로를 반드시 넘깁니다. 인자 없이 실행하면 이름순 마지막 폴더를 고르고, `--help`는 지원하지 않습니다.
- 실행 기록은 `runs/<run_id>/events.csv`에 쌓입니다.

### 카메라 녹화 (2026-11-19 추가)

테스트나 주행 장면을 USB 카메라로 녹화해 실행 폴더에 함께 저장합니다. ROS 없이 단독으로 돌며, 런치와 다른 터미널에서 실행합니다.

| 하려는 것 | 명령 |
|---|---|
| 지금 도는 실행 폴더에 녹화 (런치를 띄운 뒤) | `python3 scripts/cam_record.py --run-id latest` |
| 실행 폴더 이름을 정해 녹화 | `python3 scripts/cam_record.py --run-id <run_id>` |
| 새 폴더(`runs/cam_YYYYMMDD_HHMMSS`)에 녹화 | `python3 scripts/cam_record.py` |
| 60초만, 미리보기 창 없이 | `python3 scripts/cam_record.py --run-id latest --duration 60 --no-preview` |

- 멈추기: 미리보기 창에서 `q`, 또는 터미널에서 Ctrl-C. 어느 쪽이든 파일을 정상으로 닫습니다.
- 저장 파일: `runs/<run_id>/camera_HHMMSS.mp4`(기본 1280×720, 30 fps, 영상 왼쪽 위에 시각 표시)와 `camera_HHMMSS_frames.csv`(프레임 번호, unix 초). 시각은 `events.csv`의 `timestamp`와 같은 기준이라 이벤트 시각으로 프레임을 찾을 수 있습니다.
- `latest`는 `runs/`에서 가장 최근에 바뀐 폴더입니다. 런치가 실행 폴더를 만든 뒤에 시작합니다.
- 기본 장치는 `/dev/video0`입니다(`--device`로 바꿈). 카메라 하나에 `/dev/video0`, `/dev/video1` 두 개가 잡히는데, `video1`은 메타데이터용이라 영상이 나오지 않습니다. 다른 프로그램이 카메라를 쓰고 있으면 열리지 않습니다.
- 그 밖의 인자: `--width`, `--height`, `--fps`, `--no-stamp`(시각 표시 안 함), `--runs-dir`.
- 720p 기준 1분에 약 80 MB입니다. `runs/`는 git에서 제외되어 있습니다.
<!-- [수정 2026-11-23] T-55: 천장 카메라 판정과 장치 공유 -->
- 녹화하는 동안 0.5초마다 원본 프레임을 `~/.frybot/ceiling/latest.jpg`에 남깁니다. 녹화가 카메라를 잡고 있어도 관제의 `ceiling_locator`가 이 파일(2초 안의 것)로 판정합니다. `--latest ''`로 끄면 녹화 중에는 `CAMERA_BUSY`로 답합니다.

## 6. 알고리즘 비교 (ROS 없이)

| 하려는 것 | 명령 |
|---|---|
| 한 시나리오의 모든 조합 | `ros2 run frybot_control fleet_bench --scenario rush` |
| 조합을 골라 3회 평균, CSV 저장 (2026-11-18부터 `--csv`는 씨앗당 한 줄, 평균은 `--csv-mean`) | `ros2 run frybot_control fleet_bench --scenario bottleneck --seeds 3 --schedulers min_cost min_cost_eta_rh --planners sipp ccbs --csv raw.csv --csv-mean mean.csv` |
| 실측 시간 모델 + 보정한 계획, 통과 판정 | `ros2 run frybot_control fleet_bench --scenario rush --seeds 30 --time-model measured --plan-speed 0.135 --plan-overhead 2.27 --check --jobs 8` (W10의 보정 후보를 사용한 모의 비교. 현재 실기기 런치 기본값과 다름) |
| 실측 지도 이동 명령 비교 | `ros2 run frybot_control fleet_bench --scenario moves --map-id test_map_v001 --robots 3 --seeds 30 --schedulers min_cost_eta_rh --planners sipp independent_astar --jobs 8` |
| 씨앗 하나만 다시 실행 | `ros2 run frybot_control fleet_bench --scenario rush --only-seed 7 --schedulers min_cost_eta_rh --planners sipp` |
| 로봇 대수 바꾸기 | `ros2 run frybot_control fleet_bench --scenario normal --robots 5` |
| 모든 조합을 시나리오마다 N회, 매 실행 기록 | `python3 scripts/bench_all.py --runs 3 --robots 3 --out bench_raw.csv` |

- 시나리오는 `normal`, `rush`, `bottleneck`입니다.
- 관제 로직이나 스케줄러·플래너를 고쳤으면 `fleet_bench --scenario rush` 결과를 고치기 전과 비교합니다.

## 7. 지도

| 하려는 것 | 명령 |
|---|---|
| 가상 매장 지도 파일 다시 만들기 (`layout.py`를 고친 뒤) | `ros2 run frybot_control export_map --proto` |
| 지도를 고친 뒤 PC에 반영 | `colcon build --symlink-install --packages-select frybot_control frybot_web` |
| 지도를 로봇에 반영 | `ros2 run frybot_bringup robot_remote --all --deploy` |

- 지도 폴더는 `src/frybot/frybot_control/frybot_control/maps/<map_id>/`입니다(`proto`, `test_map_v001`, `test_map_v002`, `test_map_v03`, `test_map_v04`, `test_map_v05`, `test_map_v06`).
<!-- [수정 2026-11-26] test_map_v06 과 roadmap.json 의 dock_backwards -->
- `test_map_v06`(2026-11-26): 바뀐 매장을 pinky1 SLAM 매핑으로 만든 지도. 조리대 도크 `D1_STOP`, 충전소 `H1`~`H3`(홈·대기), 테이블 1 정지 노드 `B2`. 도크는 모두 후진(`"dock_backwards": true`). 경량 시뮬: `ros2 launch frybot_bringup sim.launch.py map_id:=test_map_v06 robots:=2 serving_robots:=pinky1 rviz:=false`.
- `roadmap.json`의 `"dock_backwards"`: 그 지도의 도크에 뒤로 들어갈지. 키가 없으면 실측 지도는 `true`, `test_map_v04`·`test_map_v05`는 `false`(전진). 바꾼 뒤에는 PC 빌드와 로봇 `--deploy`가 필요합니다(로봇의 `mobile_controller`·`docking_server`가 기동 때 읽음).
- 서빙 팔 rest 연동 시뮬(가짜 팔 + 실제 `serving_arm_driver`, P1~P3 판정): `cd ~/frybot_ws && bash archive/sim_runs_2026-11-26/20261126_integ2_rest_sim/scripts/run.sh <run_id>`. 결과는 `runs/<run_id>/rest_report.md`, 끝나면 `archive/sim_runs_<날짜>/`로 옮깁니다.
- `export_map`은 `--help`를 지원하지 않습니다. `--proto` 외의 첫 인자는 출력 폴더 이름으로 받아들여 그 이름의 폴더를 만듭니다.

## 8. 종료

| 하려는 것 | 명령 |
|---|---|
| 실기기 런치 종료 | 런치 터미널에서 Ctrl-C |
| 로봇에 남은 프로그램 정지 | `ros2 run frybot_bringup robot_remote --all --stop` |
| PC의 FryBot 프로세스 전부 종료 | `./scripts/stop_all.sh` |

`stop_all.sh`는 주의해서 씁니다.

- 반드시 단독 명령으로 실행합니다. 다른 명령과 한 줄에 이어 쓰면 그 셸도 함께 꺼집니다.
- 프로세스를 이름으로 끄기 때문에 같은 PC에서 돌던 다른 Nav2, RViz, Gazebo 작업도 꺼집니다.
- 실기기 런치를 이것으로 끄면 로봇 쪽 정지가 끝나기 전에 원격 프로세스가 죽을 수 있습니다. 실기기는 Ctrl-C로 끄고, 로봇이 남았으면 `--stop`을 씁니다.

## 9. 하지 말 것

| 하지 말 것 | 이유 |
|---|---|
| 옵션 없는 `colcon build` | 외부 저장소에서 실패하고 설치 방식이 섞임 |
| `map_id` 없이 `real.launch.py` | 런치가 오류로 멈춤(2026-11-17부터. 실측 지도 이름이 필요하고 `proto`도 받지 않음) |
| Pinky가 켜진 상태에서 `net:=lan`으로 시뮬레이션 | 같은 도메인에서 `/pinky1..3` 이름이 겹쳐 실제 로봇이 시뮬 관제의 경로를 주행할 수 있음. 기본값(`net:=sim`)은 도메인이 달라 해당 없음 |
| 실기기와 함께 `pinky_rmf_bringup sim.launch.py` | 같은 이유 (Open-RMF 시뮬도 `/pinky1`, `/pinky2`를 씀) |
| 로봇 프로그램이 도는 중에 `--deploy` | 실행 중인 코드가 바뀜 |
| `export_map --help`, `analyze_run --help` | 도움말이 아니라 `--help`를 경로로 받아들임 |
