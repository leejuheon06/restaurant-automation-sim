# 실제 Pinky 연결 가이드

실제 Pinky Pro를 FryBot 관제에 연결해 시험하는 절차입니다. 2026-11-14 기준이며, **이 문서의 실기기 절차는 아직 실제 로봇에서 실행해 보지 않았습니다.** 시뮬레이션에서 확인한 것과 확인하지 못한 것을 1장에 구분해 두었습니다.

## 1. 구조 점검 결과

### 구성

```
중앙 PC                                        Pinky N대 (각 로봇 안에서 실행)
┌──────────────────────────────┐              ┌────────────────────────────────────────┐
│ web_service  (frybot_web)    │              │ /pinkyN 네임스페이스                    │
│ central_control              │   ROS 2      │  pinky_bringup   모터·라이다·배터리      │
│ task_manager (frybot_control)│ ───────────▶ │  mobile_controller (frybot_mobile)      │
│                              │ NavigateRoute│  Nav2 + AMCL       (frybot_mobile)      │
│ real.launch.py               │ TrafficGrant │  robot.launch.py                        │
└──────────────────────────────┘ ◀─────────── └────────────────────────────────────────┘
                                 RobotStatus
```

| System Architecture 블록 | 패키지 / 실행 파일 | 실행 위치 |
|---|---|---|
| Web Service | `frybot_web` / `web_service` | 중앙 PC |
| Frybot Central Control | `frybot_control` / `central_control` | 중앙 PC |
| Frybot Task Manager | `frybot_control` / `task_manager` | 중앙 PC |
| FrybotMobile Controller | `frybot_mobile` / `mobile_controller` | 로봇 |
| FrybotNavigator | `frybot_mobile` / `navigator.launch.py`, `config/nav2_store.yaml` | 로봇 |
| FrybotMobile Arm Controller | `mobile_controller` 안의 대역(시간만 흐름) | 로봇 |
| 로봇 드라이버 | `pinky_pro` / `pinky_bringup` (수정 없이 사용) | 로봇 |

관제는 "어느 노드를 어떤 순서로 지나가라"와 통행 허가만 보냅니다. 노드 사이의 경로 탐색, 코스트맵, 주행 제어는 로봇 안의 Nav2가 합니다. 주행 관련 값은 [nav2_store.yaml](../src/frybot/frybot_mobile/config/nav2_store.yaml) 한 파일을 고치면 시뮬레이션과 실기기에 똑같이 적용됩니다.

### 준비된 것

| 항목 | 상태 |
|---|---|
| 로봇별 네임스페이스(`/pinkyN`)와 액션 이름 | 시뮬레이션에서 확인 |
| 관제 ↔ 로봇 인터페이스(`NavigateRoute`, `TrafficGrant`, `RobotStatus`) | 시뮬레이션에서 확인 |
| 로봇 수 확장(`robots:=N`) | 시뮬레이션에서 확인 |
| 실기기용 Nav2 구성(지도 서버 + AMCL, 로봇별 TF) | 작성, 설정 파일 생성까지만 확인 |
| 로봇 쪽 런치 `robot.launch.py`, 중앙 PC 쪽 런치 `real.launch.py` | 작성, 인자 표시까지만 확인 |
| 매장 지도 파일 내보내기 `export_map` | 실행 확인 |
| 배터리 값 연결(`/pinkyN/battery/percent`) | 작성, 미확인 |

### 아직 없는 것

- **서빙 팔:** 로봇에 붙은 팔을 움직이는 코드가 없습니다. 적재·전달·회수는 정해진 시간만 기다린 뒤 완료로 보고합니다.
- **조리 팔과 AI 서버:** 실제 장비 연동이 없어 `real.launch.py`가 대역 노드를 띄웁니다(`sim_cooking:=true`).
- **손님 동행 확인:** 손님 위치를 받는 수단이 없어, 실기기에서는 뒤처짐 확인 없이 후진 안내만 합니다.
- **충전 판정:** 충전대 좌표 2 cm 안에 서 있으면 충전 중으로 봅니다. 실제 충전 여부는 확인하지 않습니다.
- **비상 정지:** 관제 화면의 비상 정지는 주행 명령을 끊을 뿐, 로봇의 하드웨어 정지와 연결되어 있지 않습니다.
- **중앙 PC의 RViz:** 실기기는 로봇마다 TF가 따로라서 시뮬레이션용 RViz 설정으로는 볼 수 없습니다. 위치는 관제 웹 화면에서 확인합니다.

### 미리 알아 둘 위험

- **직접 주행:** Nav2가 한 구간을 3번 실패하거나 15초간 진행이 없으면 제어기가 그 구간을 코스트맵 없이 직진합니다. 시뮬레이션 `rush` 1회에서 8번 일어났습니다. 실기기에서는 충돌로 이어질 수 있으니 처음에는 손이 닿는 거리에서 지켜보세요.
- **지도 정합:** 로봇은 `layout.py`에서 만든 지도를 씁니다. 실물 매장(목업)의 테이블·벽 위치가 지도와 다르면 AMCL 위치가 틀어집니다.
- **라이다 높이:** 테이블과 의자가 라이다 높이에서 보여야 합니다. 다리만 있는 테이블은 지도와 다르게 보입니다.
- **좁은 간격:** 정차 위치는 테이블에서 11 cm, 통로 폭은 32 cm입니다. 위치 오차가 2~3 cm만 나도 Nav2가 접근을 거부할 수 있습니다.

## 2. 사전 준비

### 네트워크

중앙 PC와 모든 Pinky에서 같은 값을 씁니다.

```bash
export ROS_DOMAIN_ID=181
```

```bash
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
```

- 같은 공유기, 같은 대역(서브넷)에 연결합니다. 공유기의 "AP 격리"나 멀티캐스트 차단이 켜져 있으면 서로 보이지 않습니다.
- 중앙 PC의 방화벽(`ufw`)이 UDP를 막지 않는지 확인합니다.
- 로봇과 PC의 시계를 맞춥니다(`chrony` 등). 실기기는 실제 시각을 쓰므로 시계가 1초 이상 어긋나면 TF 조회가 실패합니다.
- 다른 팀이 같은 `ROS_DOMAIN_ID`를 쓰면 로봇이 섞입니다. 팀 고유 번호를 정해 두세요.

### 로봇에 설치

Pinky의 작업 공간에 `pinky_pro`와 아래 세 패키지를 넣고 빌드합니다. 시뮬레이션 패키지(`frybot_sim`)는 필요 없습니다.

```bash
colcon build --symlink-install --packages-up-to frybot_mobile
```

`frybot_mobile`은 `frybot_interfaces`와 `frybot_control`(매장 지도 정의)에 의존하므로 함께 빌드됩니다.

### 지도 만들기

중앙 PC에서 지도 파일을 만든 뒤 각 로봇으로 복사합니다.

```bash
ros2 run frybot_control export_map ~/frybot_map
```

`~/frybot_map/store.pgm`과 `store.yaml`이 생깁니다. 원점은 충전대 쪽 아래 모서리가 (0, 0), x가 조리 구역 방향입니다. `layout.py`를 고치면 다시 내보내야 합니다.

## 3. 실행 순서

### 로봇 (각 Pinky에서)

로봇을 자기 충전대 위치에 놓고, 머리가 매장 안쪽(조리 구역 방향)을 보게 합니다. 제어기가 이 자세를 AMCL 초기 위치로 보냅니다.

| 로봇 | 시작 위치 (cm, 맵 구성도 기준) |
|---|---|
| pinky1 | 충전대 1 (6, 20) |
| pinky2 | 충전대 2 (6, 50) |
| pinky3 | 충전대 3 (6, 80) |

```bash
ros2 launch frybot_mobile robot.launch.py robot_id:=pinky1 map:=$HOME/frybot_map/store.yaml
```

Pinky 드라이버를 따로 띄워 둔 경우에는 `drivers:=false`를 붙입니다. 이때 드라이버도 `/pinky1` 네임스페이스와 `/tf → tf` 리매핑으로 떠 있어야 합니다.

### 중앙 PC

```bash
ros2 launch frybot_bringup real.launch.py robots:=1
```

관제 화면은 `http://<중앙 PC 주소>:8080`입니다. 접수·주문은 같은 주소의 접수 화면과 테이블 화면에서 입력합니다.

## 4. 단계별 검증

한 단계가 통과한 뒤 다음으로 넘어갑니다. 처음에는 로봇 1대, `robots:=1`로 시작하세요.

| 단계 | 확인할 것 | 방법 | 통과 기준 |
|---|---|---|---|
| 1 | 통신 | 중앙 PC에서 `ros2 topic list` | `/pinky1/scan`, `/pinky1/odom`, `/fleet/robot_status`가 보임 |
| 2 | 드라이버 | `ros2 topic hz /pinky1/scan` | 라이다가 일정한 주기로 들어옴 |
| 3 | 위치 추정 | 관제 화면의 로봇 위치 | 충전대 위에 표시되고, 손으로 10 cm 옮기면 따라 움직임 |
| 4 | Nav2 기동 | `ros2 lifecycle get /pinky1/bt_navigator` | `active` |
| 5 | 단일 구간 주행 | 아래 "Nav2 목표 직접 보내기" | 목표 1.5 cm 안에서 정지 |
| 6 | 관제 임무 1건 | 접수 화면에서 2명 입력 | 응대 위치로 이동, 후진 안내, 충전대 복귀 |
| 7 | 주문~서빙 | 테이블 화면에서 주문 | 픽업 위치 → 테이블 → 복귀 (팔 동작은 대기 시간으로 대체) |
| 8 | 2대 교행 | `robots:=2`, 임무 2건 동시 | 한 대가 비켜 서거나 기다렸다 통과, 접촉 없음 |
| 9 | 3대 | `robots:=3`, 손님 3팀 | 모든 임무 완료, 모든 로봇 복귀 |

### Nav2 목표 직접 보내기 (5단계)

충전대 1 앞 통로 지점 (0.22, 0.80)으로 보내는 예입니다. 맵 좌표는 m 단위이고 y는 위쪽이 큽니다(맵 구성도의 y cm를 100에서 뺀 값).

```bash
ros2 action send_goal /pinky1/navigate_to_pose nav2_msgs/action/NavigateToPose "{pose: {header: {frame_id: map}, pose: {position: {x: 0.22, y: 0.80}, orientation: {w: 1.0}}}}"
```

### 단계별 기록 항목

- 위치 오차: 정지 후 자로 잰 위치와 목표의 차이(cm).
- 구간 실패: 로봇 로그의 `driving it directly` 횟수.
- 코스트맵: 로봇에서 `rviz2`를 띄워 `/pinky1/local_costmap/costmap`을 확인(로봇 쪽에서는 `/tf`를 `/pinky1/tf`로 리매핑해야 함).

## 5. 주행 값 조정

모두 [nav2_store.yaml](../src/frybot/frybot_mobile/config/nav2_store.yaml)에 있습니다. 로봇에서 고친 뒤 `robot.launch.py`를 다시 실행하면 적용됩니다.

| 증상 | 조정 항목 |
|---|---|
| 목표 근처에서 멈추지 못하고 맴돎 | `goal_checker.xy_goal_tolerance`를 키움(현재 1.5 cm) |
| 테이블 앞에서 `detected collision ahead` | `local_costmap.inflation_radius`를 줄이거나 `layout.py`의 `STOP_GAP`을 키움 |
| 위치가 튀거나 틀어짐 | `amcl`의 `update_min_d`, `laser_likelihood_max_dist`, `max_particles` |
| 너무 빠르거나 느림 | `FollowPath.desired_linear_vel`과 런치 인자 `speed`를 같은 값으로 |
| 라이다가 자기 몸체를 장애물로 봄 | `obstacle_layer.scan.obstacle_min_range` |

## 6. 문제 발생 시

| 증상 | 확인할 곳 |
|---|---|
| 중앙 PC에서 로봇 토픽이 안 보임 | `ROS_DOMAIN_ID`, 같은 서브넷, 방화벽, 공유기 AP 격리 |
| 관제 화면에 로봇이 안 뜸 | 로봇의 `mobile_controller` 로그, `/fleet/robot_status` 수신 여부 |
| 로봇 위치가 (0,0) 근처에 고정 | AMCL이 초기 위치를 못 받음: 로봇을 충전대에 다시 놓고 재실행, `/pinky1/map` 발행 여부 확인 |
| `Timed out waiting for transform` | 시계 불일치, 또는 드라이버가 `/tf`를 로봇 네임스페이스로 리매핑하지 않음 |
| 임무를 받았는데 출발하지 않음 | `/pinky1/navigate_to_pose` 액션 서버 유무, Nav2 `active` 여부 |

문제를 고치면 [TROUBLESHOOTING.md](TROUBLESHOOTING.md)에 원인과 수정 내용을 추가합니다.
