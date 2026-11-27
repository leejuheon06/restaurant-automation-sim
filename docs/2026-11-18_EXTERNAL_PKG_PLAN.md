# 외부 패키지(pinky_pro, mycobot_ros2) 사용 구조 전환 기획안 (2026-11-18)

2026-11-17에 한 "외부 저장소 의존 제거"(로봇 모델과 Pinky 드라이버를 `src/frybot` 안에 복사)를 되돌려, `pinky_pro`와 `mycobot_ros2`의 패키지를 그대로 불러 쓰는 구조로 바꾸는 계획입니다. 이 문서는 계획만 담으며 코드는 바꾸지 않았습니다. 작업 공간 규칙(CLAUDE.local.md)은 그대로 적용됩니다. 경로는 `src/frybot/` 기준이고 줄 수는 작성 시점 값입니다.

## 0. 요약

- `frybot_description`(외부 모델의 사본 937줄 + 메시 30개)은 통째로 지우고 `pinky_description`, `mycobot_description`을 씁니다.
- `frybot_mobile` 안의 Pinky 드라이버 사본 3개(`pinky_driver.py`, `pinky_battery.py`, `dynamixel_driver.py`, 427줄)를 지우고 `pinky_bringup`의 `bringup_robot.launch.xml`을 불러 씁니다.
- FryBot에만 있는 코드(관제 경로·통행 허가를 받는 `mobile_controller`, 매장용 Nav2 설정, 조리 셀의 `master_controller`)는 외부 저장소에 대응하는 것이 없어 남깁니다. 남기는 형태(패키지를 유지할지 합칠지)는 2장 D1에서 정합니다.
- 가장 큰 쟁점은 **속도 명령 감시(T-29 A1)** 입니다. 지금은 사본 `pinky_driver.py`에만 있고 원본 `bringup.py`에는 없습니다. 외부 저장소는 고치지 않으므로, 감시를 FryBot 쪽 중계 노드로 옮겨야 사람 안전 기능이 유지됩니다(3장 E2).
- 조리 팔은 지금 대역이라 "mycobot_ros2로 실제 구동"은 구동 방식 결정(D4)이 있어야 합니다. 이번 범위에서는 모델만 `mycobot_description`으로 바꾸고, 구동 연결은 별도 단계(E5)로 둡니다.

## 1. 현재 상태 (확인한 것)

### 1.1 사본과 원본의 차이

| 사본 (`src/frybot`) | 원본 | 차이 |
| --- | --- | --- |
| `frybot_description/pinky/urdf/*.xacro` (4개), `pinky/meshes` | `pinky_pro/pinky_description/urdf`, `meshes` | 경로 치환(`pinky_description` → `frybot_description/pinky`)뿐. `pinky_gz.urdf.xacro`만 램프 플러그인(`pinky_gz_sim::LampControlPlugin`) 참조 4줄을 지움 |
| `frybot_description/jetcobot/mycobot_280_pi.urdf` + 메시 | `mycobot_ros2/mycobot_description/urdf/mycobot_280_pi/` | 메시 경로 치환뿐 |
| `frybot_mobile/pinky_driver.py` (270줄) | `pinky_bringup/bringup.py` | 노드 이름 `pinky_bringup` → `pinky_driver`, **`cmd_vel_timeout` 감시 추가(A1, 약 45줄)** |
| `frybot_mobile/pinky_battery.py` (56줄) | `pinky_bringup/battery_publisher.py` | 노드 이름 `battery_publihser` → `pinky_battery`뿐 |
| `frybot_mobile/dynamixel_driver.py` (101줄) | `pinky_bringup/dynamixel_driver.py` | 머리말 주석뿐 |
| `robot.launch.py`의 `driver_actions()` | `pinky_bringup/launch/bringup_robot.launch.xml` | 같은 구성을 Python으로 다시 쓴 것. `drivers:=pinky_pro`로 원본을 부르는 분기가 이미 있음 |

### 1.2 사본을 쓰는 곳

| 파일 | 내용 |
| --- | --- |
| `frybot_bringup/frybot_bringup/urdf_tools.py` | `pinky_urdf()`, `jetcobot_urdf()`가 `frybot_description`에서 읽음 |
| `frybot_bringup/launch/gazebo.launch.py:119` | `GZ_SIM_RESOURCE_PATH`를 `frybot_description` 기준으로 잡음 |
| `frybot_bringup/package.xml`, `frybot_mobile/package.xml` | `frybot_description` 의존 |
| `frybot_mobile/launch/robot.launch.py` | 기본값(`drivers:=true`)이 내장 드라이버 + `frybot_description` |
| `frybot_mobile/setup.py` | 실행 파일 `pinky_driver`, `pinky_battery` |
| `frybot_bringup/frybot_bringup/robot_remote.py` | 배포 목록 `DEPLOY`(37행), 점검 목록(271행)에 `frybot_description` |
| `deps.repos`, 루트 `.gitignore` | "빌드·실행에 필요 없음" 주석, `src/pinky_pro/`·`src/mycobot_ros2/` 제외 |
| 문서 | `src/frybot/README.md`, `docs/REAL_ROBOT_GUIDE.md`, `docs/COMMANDS.md`, `docs/TROUBLESHOOTING.md` 등 |

마지막 커밋(4ab5d33)의 `urdf_tools.py`, `gazebo.launch.py`, `frybot_bringup/package.xml`은 `pinky_description`·`mycobot_description`을 직접 쓰던 판이라, 되돌릴 내용은 `git diff HEAD -- <파일>`로 볼 수 있습니다(복구 명령은 쓰지 않고 손으로 고침).

### 1.3 외부 저장소가 주는 것

| 저장소 | 패키지 | FryBot에서 쓸 것 |
| --- | --- | --- |
| `pinky_pro` (014a09f) | `pinky_description` | Pinky xacro·메시, `upload_robot.launch.py`(robot_state_publisher + joint_state_publisher) |
| | `pinky_bringup` | `bringup`(모터·오도메트리), `battery_publisher`, `bringup_robot.launch.xml`(모델 + 라이다 + 두 노드) |
| | `pinky_navigation` | Nav2 런치(`bringup_launch.xml`: `namespace`, `map`, `params_file` 인자)와 기본 파라미터. 쓸지는 D3 |
| | `pinky_gz_sim` | 램프 플러그인, Gazebo 런치. C++ 빌드와 `gz_ros2_control` 필요 |
| `mycobot_ros2` (d42ff61) | `mycobot_description` | `urdf/mycobot_280_pi`, `urdf/mycobot_280_jn` 등 |
| | `mycobot_280pi`, `mycobot_280jn` | `listen_real`(실제 팔 관절값 → `joint_states`), `slider_control` 등. `pymycobot` 필요 |
| | `mycobot_communication`, `mycobot_interfaces` | 팔 구동 토픽·서비스(`MycobotSetAngles`, `SetCoords`, 그리퍼 등) |

### 1.4 전환 전에 알아 둘 문제

1. **속도 명령 감시가 원본에 없음.** 원본 `bringup.py`는 `cmd_vel`이 끊겨도 마지막 RPM을 유지합니다(T-22, T-29 A1의 원인). 사본을 지우면 이 보호가 사라집니다.
2. **`mycobot_ros2` 작업 사본이 고쳐져 있음.** `setup.cfg` 16개가 `script-dir` → `script_dir`로 바뀐 상태입니다(`git -C src/mycobot_ros2 status`). `deps.repos`로 새로 받으면 이 변경은 없습니다. `mycobot_description/setup.cfg`는 원본이 이미 밑줄 표기라 해당 없습니다.
3. **`mycobot_interfaces`가 설치되지 않음.** 이 PC의 `build/`에는 있고 `install/`에는 없으며 `mycobot_communication`은 빌드되지 않았습니다. 옵션 없는 `colcon build`가 실패하는 지점으로 보이나 원인은 **확인 필요**입니다(지금 빌드 로그에는 frybot 패키지만 남아 있음).
4. **`pinky_bringup`의 의존 사슬.** `pinky_bringup` → `pinky_mujoco` → `pinky_gz_sim`(`ros_gz`, `gz_ros2_control`)입니다. 관제 PC에는 이미 모두 빌드돼 있습니다. 로봇에서는 frybot 작업 공간이 아니라 로봇에 설치된 `pinky_pro`를 써야 합니다.
5. **로봇에 설치된 `pinky_pro`의 판.** 2026-11-17 전에는 로봇의 `pinky_bringup`으로 주행했으므로 설치는 돼 있습니다. PC의 014a09f와 같은 판인지, `robot_remote`가 source하는 경로(`ros_setup`, `~/frybot_robot_ws/install`)로 보이는지는 **실기기 확인 필요**입니다.
6. **노드 이름이 원본으로 돌아감.** `/pinkyN/pinky_driver` → `/pinkyN/pinky_bringup`, `/pinkyN/pinky_battery` → `/pinkyN/battery_publihser`(원본의 오타). 2026-11-18 P2(D3)의 이름 변경이 이 두 노드에 한해 무효가 됩니다.
7. **Gazebo 램프 플러그인.** 원본 xacro를 쓰면 `pinky_gz_sim`을 빌드·경로 등록하지 않는 한 T-09의 `Failed to load system plugin` 메시지가 다시 나옵니다(주행·센서와 무관).
8. **실기기 확인이 지금 막혀 있음.** 2026-11-18 조회에서 pinky1·pinky2에 `/dev/ttyAMA0`이 없고 모터 포트(UART4)가 장치 트리에서 꺼져 있었습니다(`docs/2026-11-18_REAL_TEST.md` "찾은 문제 1"). 원본과 사본 모두 라이다를 `/dev/ttyAMA0`으로 열므로, 이 문제가 풀리기 전에는 E2~E4의 실기기 확인을 할 수 없습니다.
9. **`frybot_description`과 드라이버 사본은 git에 올라간 적이 없음**(untracked). 지우면 git으로 되살릴 수 없지만, 내용은 외부 저장소에서 다시 만들 수 있고 감시 코드만 FryBot 고유입니다.

## 2. 결정이 필요한 것 (권장안 포함)

| 번호 | 결정 | 선택지 | 권장 |
| --- | --- | --- | --- |
| D1 | FryBot 고유 코드를 담는 패키지 | **가)** `frybot_mobile`, `frybot_arm`을 유지하되 사본을 빼고 외부 패키지에 의존하는 얇은 패키지로 둠. **나)** 두 패키지를 없애고 노드를 다른 패키지로 옮김(예: `mobile_controller`·Nav2 설정 → 새 `frybot_robot` 또는 `frybot_control`, 조리 셀 → `frybot_control`) | 가). `mobile_controller`(979줄)와 매장용 Nav2 설정은 `pinky_pro`에 대응물이 없어 어디엔가 있어야 하고, SW 아키텍처의 FrybotMobile·Frybot Cooking 구분과도 맞음. 나)는 파일 이동과 배포·문서 변경만 늘고 동작 이득이 없음 |
| D2 | 속도 명령 감시를 어디에 둘지 | **가)** FryBot의 중계 노드(`cmd_vel_guard`, 3장 E2). **나)** `pinky_pro`에 PR을 보내고 반영될 때까지 가). **다)** `pinky_pro`를 포크해 `deps.repos`를 포크로 고정. **라)** 감시 없이 원본 사용 | 나). 라)는 사람 안전 기능을 되돌리는 것이라 권장하지 않음 |
| D3 | Nav2 기동 | **가)** 지금처럼 `frybot_mobile/navigator.py`가 Nav2 노드를 직접 띄움(설정 `nav2_store.yaml`, `segment_bt.xml`). **나)** `pinky_navigation/bringup_launch.xml`에 FryBot 파라미터 파일을 넘겨 띄움 | 가). `pinky_navigation`은 `behavior_server`·`waypoint_follower`·`velocity_smoother`를 함께 띄워 `cmd_vel` 경로와 주행 값이 달라지고, 구간용 BT·후진 제어기 선택·도킹 서버·지도별 덮어쓰기(`navigator.py`)를 다시 검증해야 함. 설정 파일은 사본이 아니라 FryBot 조정값임 |
| D4 | 조리 팔 실제 구동 | **가)** 이번에는 모델만 교체, 구동은 대역 유지. **나)** `mycobot_communication` 토픽으로 실제 팔을 움직이는 구동부 추가 | 가) 먼저. 나)는 팔 구동 방식과 JetCobot의 탑재 보드가 정해진 뒤 E5로 진행 |
| D5 | 조리 팔 URDF | `mycobot_280_pi`(현재) / `mycobot_280_jn`(Jetson Nano 판) | 실물 JetCobot 280의 보드에 맞춤. **확인 필요**. 정해지기 전에는 현재와 같은 `mycobot_280_pi` |
| D6 | Gazebo 램프 플러그인 | **가)** `urdf_tools.pinky_gz_urdf()`가 xacro 결과에서 플러그인 요소를 뺌(이 함수는 이미 문자열 치환을 함). **나)** `pinky_gz_sim`을 의존에 넣고 플러그인 경로를 등록 | 가). 외부 파일은 그대로 두고 T-09 메시지도 없음 |
| D7 | `mycobot_ros2`의 로컬 변경 16건 | **가)** 되돌리고(`git -C src/mycobot_ros2 checkout .`은 사용자가 실행) 필요한 패키지만 빌드. **나)** 그대로 둠 | 가). `mycobot_description`만 쓰는 동안은 변경이 필요 없음. setuptools 68.1.2에서 `script-dir`이 경고인지 오류인지는 E0에서 확인 |
| D8 | 지우는 사본의 보관 | 지움 / `archive/internal_copies_2026-11-18/`로 옮김 | 옮김. `pinky_driver.py`의 감시 코드는 E2의 기준 구현이자 나)의 PR 재료 |

## 3. 단계

앞 단계가 통과해야 다음 단계로 갑니다. 단계마다 수정 표기 주석(`# [수정 2026-11-18] ...`)을 남깁니다.

| 단계 | 내용 | 바뀌는 곳 | 위험 | 실기기 확인 |
| --- | --- | --- | --- | --- |
| E0 | 외부 저장소 빌드 상태 정리와 기준 자료 | `deps.repos`, 문서 | 낮음 | 없음 |
| E1 | 로봇 모델을 외부 패키지로 | bringup, mobile | 낮음 | 필요(RViz 모델) |
| E2 | 속도 명령 감시를 중계 노드로 | mobile | **높음(사람 안전)** | 필요 |
| E3 | Pinky 드라이버를 `pinky_bringup`으로 | mobile, bringup | 중간 | 필요 |
| E4 | 사본 삭제, 배포·점검 목록 | description, mobile, bringup | 중간 | 필요(배포) |
| E5 | 조리 팔을 `mycobot_ros2`로 구동 (D4 나) | arm, bringup | 중간 | 필요 |
| E6 | 문서 갱신 | docs, README | 낮음 | 없음 |

### E0. 준비

- 기준 자료를 남깁니다: 현재 코드로 `fleet_bench --scenario rush --check`, 경량 시뮬 demo의 `analyze_run`, 사본 xacro의 출력(`xacro .../robot.urdf.xacro namespace:= is_sim:=false`, `is_sim:=true`)을 `archive/external_pkg_2026-11-18/baseline/`에 저장.
- `colcon build --symlink-install --packages-up-to pinky_bringup pinky_description mycobot_description`이 깨끗한 `deps.repos` 상태에서 되는지 확인(D7).
- `mycobot_interfaces` 설치 실패 원인 확인(E5에서만 필요).
- `deps.repos` 머리말을 "frybot 빌드·실행에 필요"로 고침. 고정 커밋(014a09f, d42ff61)은 그대로.

### E1. 로봇 모델

- `urdf_tools.py`: `pinky_urdf()`는 `pinky_description/urdf/robot.urdf.xacro`, `jetcobot_urdf()`는 `mycobot_description/urdf/<D5>/`에서 읽음. `cam_tilt_deg` 등 현재 넘기는 xacro 인자는 그대로.
- `pinky_gz_urdf()`: 램프 플러그인 요소 제거(D6 가).
- `gazebo.launch.py:119`: `GZ_SIM_RESOURCE_PATH`를 `pinky_description`의 share 상위로.
- `frybot_bringup/package.xml`: `frybot_description` → `pinky_description`, `mycobot_description`.
- 검증: 새 출력과 E0의 기준 URDF를 비교해 메시 경로(와 Gazebo 판의 램프 요소)만 다른지 확인. 경량 시뮬과 Gazebo에서 RViz 모델 표시.

### E2. 속도 명령 감시 (`cmd_vel_guard`)

원본 드라이버를 고치지 않고 감시를 유지하는 방법입니다.

```
Nav2 controller_server ─┐
mobile_controller ──────┴─ /pinkyN/cmd_vel ─▶ cmd_vel_guard ─ /pinkyN/cmd_vel_safe ─▶ pinky_bringup(bringup)
```

- `frybot_mobile`에 노드 `cmd_vel_guard`를 새로 만듭니다. `cmd_vel`을 받아 `cmd_vel_safe`로 그대로 넘기고, 0이 아닌 명령 뒤 `cmd_vel_timeout`(기본 0.5초, 지금과 같은 값) 넘게 입력이 없으면 0 속도를 보냅니다. 끊긴 동안에는 0 속도를 주기적으로 다시 보내, 사본의 "0 RPM 전송 실패 시 재전송"을 대신합니다.
- 드라이버 쪽은 런치에서 `cmd_vel` → `cmd_vel_safe`로 리맵해 붙입니다(`robot.launch.py`의 드라이버 `GroupAction`에 `SetRemap` 추가). `bringup.py`가 상대 이름 `cmd_vel`을 구독하는 것은 확인했고, XML 런치를 포함할 때 `SetRemap`이 적용되는지는 E2에서 확인합니다. 보내는 쪽(Nav2, `mobile_controller`)과 토픽 이름은 바꾸지 않습니다.
- 시뮬에서는 띄우지 않습니다(Gazebo는 자체 플러그인이 `cmd_vel`을 받음). `mobile_controller`에는 분기를 넣지 않습니다.
- 사본 대비 달라지는 점
  - 감시가 드라이버 프로세스 밖에 있어, 감시 노드가 죽으면 드라이버에는 명령이 아예 가지 않습니다(마지막 RPM 유지). 런치에서 `respawn`을 켜고, 죽은 뒤 다시 뜰 때 0 속도를 먼저 보내게 합니다. 드라이버 내부 감시보다 한 단계 약하므로 D2 나)의 PR을 함께 진행합니다.
  - 모터 전송 실패 여부를 직접 볼 수 없습니다(원본이 밖으로 알리지 않음). 주기적 0 속도 재전송으로 갈음합니다.
- `README.md`의 "`pinky_driver`는 `cmd_vel`이 0.5초 넘게 끊기면 모터를 세웁니다", `docs/REAL_ROBOT_GUIDE.md`, T-29 항목을 새 구조로 고칩니다.
- 검증: 가짜 구독자로 하는 노드 시험(명령 뒤 침묵 → 0.5초 안에 0 속도, 0 명령 뒤에는 추가 발행 없음, 재개 시 즉시 통과, 재기동 직후 0 속도). T-29 때의 "가짜 모터 드라이버 6건"과 같은 경우를 맞춥니다. 실기기에서 주행 중 `mobile_controller`·Nav2를 죽였을 때 서는지는 **실기기 확인 필요**.

### E3. Pinky 드라이버

- `robot.launch.py`의 `driver_actions()`: 기본을 `pinky_bringup/launch/bringup_robot.launch.xml` 포함으로 바꾸고(지금의 `drivers:=pinky_pro` 분기), 내장 드라이버 분기를 지웁니다. `drivers` 값은 `true`/`false`만 남깁니다.
- 네임스페이스와 TF 분리(`PushRosNamespace`, `/tf` → `tf`)는 지금 구조 그대로입니다.
- `frybot_mobile/setup.py`: 실행 파일 `pinky_driver`, `pinky_battery` 삭제, `cmd_vel_guard` 추가. `package.xml`: `frybot_description` 삭제, `pinky_bringup`·`pinky_description` 추가.
- 배터리 토픽 이름(`battery/percent`)과 단위는 원본과 사본이 같은 코드라 그대로입니다(R2-3의 단위 확인은 여전히 남음).
- 검증: 관제 PC에서 `ros2 launch frybot_mobile robot.launch.py ... --show-args`와 런치 구성 출력으로 노드 목록 확인(모터가 없어 PC에서는 드라이버가 뜨지 않음). 실제 기동은 **실기기 확인 필요**.

### E4. 사본 삭제와 배포

- `frybot_description/` 전체, `frybot_mobile/frybot_mobile/{pinky_driver,pinky_battery,dynamixel_driver}.py`를 D8에 따라 옮기거나 지웁니다. 되돌릴 수 없는 삭제이므로 실행 전에 한 번 더 확인받습니다.
- `robot_remote.py`: `DEPLOY`에서 `frybot_description`을 빼고, 점검 목록을 `pinky_bringup`, `pinky_description`, `sllidar_ros2`로 바꿉니다. 점검에 로봇의 `pinky_pro` 커밋 표시를 추가하면 1.4의 5번을 매번 볼 수 있습니다.
- 로봇에는 `pinky_pro`를 배포하지 않고 로봇에 설치된 것을 씁니다. 로봇 작업 공간에 남은 `frybot_description`의 `build/`·`install/`은 배포 스크립트의 `rsync --delete` 대상이 아니므로 정리 방법을 정합니다(**확인 필요**).
- 빌드 명령은 지금과 같습니다(`--packages-up-to frybot_bringup`). 의존을 선언했으므로 `pinky_description`, `pinky_bringup`, `mycobot_description`이 함께 빌드됩니다.
- 검증: `build/`·`install/`의 `frybot_description`을 지운 뒤 전체 빌드, 시뮬 3종(경량 demo, 실측 지도, Gazebo) 실행, `robot_remote --all --check`.

### E5. 조리 팔 구동 (D4 나를 고른 경우)

- `frybot_arm/arm_controller.py`의 관절 애니메이션 자리에 구동부를 둡니다: `mycobot_communication`의 토픽 노드(`mycobot_topics_pi` 또는 `_jsnn`)에 `MycobotSetAngles`를 보내고 `MycobotAngles`로 도착을 확인합니다. `arm_motion.py`의 자세표는 그대로 목표 각도로 씁니다.
- RViz 표시는 `mycobot_280pi`(또는 `280jn`)의 `listen_real`이 내는 `joint_states`를 씁니다.
- 필요한 것: `mycobot_interfaces` 빌드 문제 해결(E0), 팔 쪽 컴퓨터의 `pymycobot`(4.0.5 이상), 직렬 포트·속도, 작업별 자세의 실물 보정, 취소(비상 정지) 처리. `ArmJob.action`은 바꾸지 않습니다.
- AMR의 서빙 팔(`frybot_mobile/arm_common.py`)은 실물이 없어 대역으로 둡니다.
- 전부 **실기기 확인 필요**이며, 팔이 없는 동안은 대역이 기본값이어야 시뮬이 돕니다.

### E6. 문서

- `src/frybot/README.md`(폴더 표, 대응 표, "빠른 시작", 실기기 절), `docs/REAL_ROBOT_GUIDE.md`(구성 표, 배포 목록, `drivers` 인자, 노드 이름), `docs/COMMANDS.md`, 루트 `README.md`, `deps.repos` 머리말.
- `docs/TROUBLESHOOTING.md`: 변경 이력 표에 한 줄, T-09 후속, T-29에 감시 위치 변경. `docs/2026-11-18_REAL_FIRST_PLAN.md`의 D3(노드 이름)에 되돌림 표시.
- `docs/CODE_REVIEW_CHECKLIST.md` 2순위의 "`pinky_bringup` 대조" 항목이 다시 실제 대상이 됩니다.

## 4. 완료 기준

| 항목 | 확인 방법 | 기준 |
| --- | --- | --- |
| 빌드 | 깨끗한 `deps.repos` 상태에서 `colcon build --symlink-install --packages-up-to frybot_bringup` | 성공, `frybot_description` 없이 |
| 모델 | E0 기준 URDF와 비교 | 메시 경로와 램프 요소 외 차이 없음 |
| 관제 | `ros2 run frybot_control fleet_bench --scenario rush --check` | E0 기준과 같음(관제 코드는 건드리지 않으므로 수치 동일) |
| 경량 시뮬 | `sim.launch.py` + `scenario --scenario demo` → `analyze_run` | 전부 완료, 기준과 같은 수준 |
| Gazebo | `gazebo.launch.py` + demo | Nav2 주행 완료, 램프 플러그인 오류 없음 |
| 감시 | `cmd_vel_guard` 노드 시험 | 전부 통과 |
| 배포·점검 | `robot_remote --all --check` | 패키지 누락 없음 |
| 실기기 | 주행, 양보 후진, 비상 정지, 제어기 강제 종료 시 정지 | **실기기 확인 필요**(이 항목이 끝나기 전에는 "끝났다"고 하지 않음) |

## 5. 위험과 되돌리기

| 위험 | 대응 |
| --- | --- |
| 감시 중계가 빠지거나 리맵이 틀려 원본 드라이버가 `cmd_vel`을 직접 받음 | E2 시험에 "드라이버가 `cmd_vel_safe`만 구독" 확인을 넣고, `robot_remote --check`에 `cmd_vel_guard` 실행 여부 추가 |
| 로봇의 `pinky_pro`가 PC와 다른 판 | 점검에 커밋 표시. 다르면 로봇 쪽을 014a09f로 맞춤(사용자 작업) |
| 외부 저장소 갱신으로 동작이 바뀜 | `deps.repos`의 커밋 고정 유지, 올릴 때 E1의 URDF 비교와 시뮬 3종 재실행 |
| 관제 PC에 `pinky_gz_sim`·`pinky_mujoco` 빌드 의존이 생김 | 지금 PC에는 빌드돼 있음. 새 PC에서는 `ros_gz`, `gz_ros2_control` 설치가 필요(문서에 적음) |
| 실기기에서 문제 | D8의 보관본과 지금의 `drivers` 분기를 E4 전까지 남겨 두어, E3까지는 런치 인자로 내장 드라이버로 되돌릴 수 있게 함. E4(삭제)는 실기기 확인 뒤에 함 |

## 6. 범위 밖

- `src/pinky_pro/`, `src/mycobot_ros2/`의 수정(PR은 D2 나에 한해 별도로).
- 관제 판단(`fleet_core.py`), 인터페이스(`frybot_interfaces`), Nav2 조정값(`nav2_store.yaml`) 변경.
- `pinky_navigation` 런치로의 전환(D3 나를 고르면 별도 기획).
