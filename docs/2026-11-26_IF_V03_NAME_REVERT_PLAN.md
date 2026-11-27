# 인터페이스 이름 8건을 Confluence I/F v0.3 최종 판에 맞추는 기획 (2026-11-26)

작성: 기획 패널. 코드 수정과 검증은 부장(Opus 5.5)이 맡습니다. **이 문서는 기획이며 실행하지 않았습니다.** 사용자가 실행을 지시하면 6장의 순서로 작업 지시를 보냅니다.

- 근거: [Confluence I/F v0.3 검토](2026-11-26_CONFLUENCE_IF_V03_REVIEW.md) 7장(최종 판 ↔ 코드 비교, 지금 고치면 생기는 문제)
- 11-25에 반대 방향으로 바꾼 기록: [v0.2 대조와 반영 현황](2026-11-25_IF_V02_CHECK.md) 9장

## 1. 왜 하는가

- 사용자 결정(2026-11-26): Confluence "1) FryBot I/F 목록"(24641549)과 그 아래 개별 v0.3 정의서가 최종 기준이다. 정의서에 있는 내용이 코드에 없거나 달라서는 안 된다.
- 코드는 2026-11-25에 v0.2 이름으로 바꿨는데, 최종 판은 그 전 이름이다. "구현" 표시 항목 가운데 코드와 다른 것은 이름 8건뿐이다(33·35번의 시간 값은 같은 날 정의서가 1초로 고쳐져 해소).
- 8건은 필드·주기·QoS가 이미 정의서와 같다. 이름만 바꾸면 "구현" 항목은 정의서와 모두 일치한다.
- 팀 공유 저장소(`~/roscamp-repo-1`의 `frybot`)도 v0.3 이름이라, 맞추면 그쪽과의 차이가 줄어든다.

## 2. 바꿀 것

| 번호 | 항목 | 지금 코드 | 바꿀 이름(최종 v0.3) | 구간 |
| --- | --- | --- | --- | --- |
| 14 | 방문 등록 | `RegisterVisit`, `/frybot/central/register_visit` | `CheckIn`, `/frybot/check_in` | web_service → central_control |
| 15 | 주문 등록 | `SubmitOrder`, `/frybot/central/submit_order` | `PlaceOrder`, `/frybot/place_order` | web_service → central_control |
| 16 | 방문 종료 처리 | `EndVisit`, `/frybot/central/end_visit` | `EndUse`, `/frybot/end_use` | web_service → central_control |
| 17 | 관리자 명령 전달 | `RequestAdminOperation`, `/frybot/central/request_admin_operation` | `AdminCommand`, `/frybot/admin` | web_service → central_control |
| 19 | 임무 접수 | `SubmitTask`, `/frybot/tasks/submit` | `SubmitTask`, `/fms/submit_task` | central_control → task_manager |
| 20 | 임무 조작 | `ControlTask`, `/frybot/tasks/control` | `FleetCommand`, `/fms/command` | central_control → task_manager |
| 31 | 업무 상태 발행 | `/frybot/central/view_state` | `/frybot/state` | central_control → web_service |
| 32 | 임무 상태 전이 | `TaskProgress`, `/frybot/tasks/progress` | `TaskEvent`, `/fms/task_events` | task_manager → central_control |

여덟 개 모두 관제 PC 안의 통신입니다. 로봇과 팔 Pi가 주고받는 인터페이스는 바뀌지 않습니다.

### 바꾸지 않는 것

| 대상 | 이유 |
| --- | --- |
| 필드, 주기, QoS, 동작 | 이미 정의서와 같음 |
| HTTP 경로 `/api/visits`, `/api/orders`, `/api/admin/operations` | 11-25에 함께 바꾼 것인데 최종 v0.3의 01·04·07번 경로와 같음. **11-25 변경을 통째로 되돌리면 안 되는 이유** |
| `POST /api/end_use`, `GET /api/state` 등 그 밖의 HTTP | "설계" 항목(01~10)은 이번 범위 밖 |
| 관리자 명령 문자열(`ESTOP`, `MOVE_TO_VERTEX` 등), 실행 로그의 이벤트 이름 | 정의서와 무관하거나 이미 같음 |
| 내부 파이썬 이름(`restaurant.check_in`, `_checkin` 등) | 11-25에도 바꾸지 않았음 |
| 33·35번 통신 감시 1초 | 코드 유지로 결정, 정의서가 1초로 고쳐짐 |
| `src/pinky_pro/`, `src/mycobot_ros2/` | 외부 저장소 |

## 3. 고칠 곳 (2026-11-26 `rg` 검색 기준)

코드 16개 파일 119곳입니다(수정 표기 주석 포함).

| 패키지 | 파일 | 할 일 |
| --- | --- | --- |
| `frybot_interfaces` | `srv/RegisterVisit.srv` → `CheckIn.srv`, `SubmitOrder.srv` → `PlaceOrder.srv`, `EndVisit.srv` → `EndUse.srv`, `RequestAdminOperation.srv` → `AdminCommand.srv`, `ControlTask.srv` → `FleetCommand.srv`, `msg/TaskProgress.msg` → `TaskEvent.msg` | 파일 이름 변경(6개), 머리 주석의 이름·주소 |
| | `srv/SubmitTask.srv`, `msg/GuestTrack.msg`, `CMakeLists.txt` | 주석의 주소·타입 이름, 생성 목록 |
| `frybot_control` | `central_control_node.py`(28곳) | import, 서비스 4개·클라이언트 2개·구독 1개·발행 1개의 타입과 주소, 주석 |
| | `task_manager_node.py`(13곳) | import, 발행 1개·서비스 2개의 타입과 주소, 주석 |
| | `fleet_core.py`(8곳), `restaurant.py`(7곳) | 주석과 docstring만 |
| `frybot_web` | `web_service_node.py`(29곳) | import, 클라이언트 4개와 구독 1개의 타입·주소, 요청 객체 생성 4곳, 주석 |
| | `static/ui.js`(2곳) | 주석만 |
| `frybot_sim` | `world_node.py`(2곳) | 구독 주소 |
| 시험 코드 | `frybot_control/test/test_guiding_visit.py`, `test_plan_fail_suspend.py` | 옛 이름을 쓰는지 확인(검색에는 타입 이름이 안 잡힘, 부장이 확인) |

`frybot_mobile`, `frybot_arm`, `frybot_ai`, `frybot_bringup`, `scripts/`에는 해당 이름이 없습니다.

문서:

| 파일 | 할 일 |
| --- | --- |
| `src/frybot/README.md`(14곳) | 연결 그림, 토픽·서비스 표, 관리자 명령 설명의 주소. "통합 I/F 정의서 v0.2를 따릅니다" 문단을 v0.3 최종 판 기준으로 고침 |
| `docs/INTERFACES.md`(36곳) | 이름·주소 |
| `docs/COMMANDS.md`(3곳) | 명령 예시의 주소·타입 |
| `docs/2026-11-25_IF_V02_*.md` 네 개, `docs/2026-11-23_IF_COMPARE_*.md` | 본문은 그날의 기록이라 그대로 두고, 머리에 "2026-11-26에 최종 기준이 v0.3으로 바뀌어 이름을 되돌림" 한 줄만 추가 |
| `docs/TROUBLESHOOTING.md`, 날짜별 실기기 기록 | 고치지 않음(기록 보존) |
| `docs/INTERFACES.pdf` | 옛 이름(= v0.3 이름)이 남아 있어 이름은 다시 맞게 됨. 다시 만들지는 별도 결정 |

수정 표기: 고친 자리에 `# [수정 2026-11-26] I/F v0.3 최종 판 이름: <지금> -> <바꿀 이름>`. 11-25 주석은 지우지 않고 그 아래에 덧붙입니다.

바뀌는 모습(예: `central_control_node.py`):

```python
# 지금
from frybot_interfaces.msg import GuestTrack, TaskProgress
from frybot_interfaces.srv import (ControlTask, EndVisit, RegisterVisit,
                                   RequestAdminOperation, SubmitOrder,
                                   SubmitTask)
        self.cli_submit = self.create_client(
            SubmitTask, '/frybot/tasks/submit', callback_group=g_cli)
        self.create_service(
            RegisterVisit, '/frybot/central/register_visit', self._check_in,
            callback_group=g_srv)
        self.pub_state = self.create_publisher(
            String, '/frybot/central/view_state', 10)

# 바꾼 뒤
from frybot_interfaces.msg import GuestTrack, TaskEvent
from frybot_interfaces.srv import (AdminCommand, CheckIn, EndUse,
                                   FleetCommand, PlaceOrder, SubmitTask)
        self.cli_submit = self.create_client(
            SubmitTask, '/fms/submit_task', callback_group=g_cli)
        self.create_service(
            CheckIn, '/frybot/check_in', self._check_in,
            callback_group=g_srv)
        self.pub_state = self.create_publisher(
            String, '/frybot/state', 10)
```

## 4. 시작 전 조건

| # | 조건 | 이유 |
| --- | --- | --- |
| 1 | 사용자가 지금 상태를 커밋 | 마지막 커밋 `4ab5d33` 뒤로 223개 파일이 미커밋. 실패했을 때 돌아갈 기준이 없음(`git checkout`은 금지 명령) |
| 2 | 관제 PC에 FryBot 프로세스가 없음 | 인터페이스를 다시 빌드하므로 실행 중인 노드가 있으면 안 됨 |
| 3 | 같은 작업 공간의 다른 세션이 같은 파일을 고치고 있지 않음 | `central_control_node.py`, `README.md`, `COMMANDS.md`가 겹칠 수 있음 |
| 4 | 서빙 팔 OPEN·CLOSE, 새 지도 작업과 섞지 않음 | 한 번에 하나씩 끝내야 실패 원인을 가를 수 있음 |

## 5. 완료 기준

| # | 확인 | 통과 기준 |
| --- | --- | --- |
| 1 | 빌드 | `frybot_interfaces`의 build·install을 지우고 `colcon build --symlink-install --packages-up-to frybot_bringup` 성공 |
| 2 | 옛 이름 검색 | `src/frybot`과 `scripts/` 코드에서 11-25 이름(`RegisterVisit`, `SubmitOrder`, `EndVisit`, `RequestAdminOperation`, `ControlTask`, `TaskProgress`, `/frybot/central/`, `/frybot/tasks/`) 사용 0건(수정 표기 주석 제외) |
| 3 | 타입 | `ros2 interface show`로 `CheckIn`, `PlaceOrder`, `EndUse`, `AdminCommand`, `FleetCommand`, `SubmitTask`, `TaskEvent`의 필드가 정의서와 같음 |
| 4 | pytest | `frybot_ai` 14, `frybot_control` 33, `frybot_mobile` 53 통과(11-25 기록과 같은 건수. 그 뒤 시험이 늘었으면 지금 건수를 먼저 재서 비교) |
| 5 | `fleet_bench` | `--scenario rush --check` 수치·판정이 수정 전과 같음 |
| 6 | 경량 시뮬 | 도메인 74에서 `sim.launch.py rviz:=false` + `scenario --scenario demo` → `analyze_run`: 임무 완료 10, 중단 0, 접수 거절 0(11-25와 같음) |
| 7 | 실행 중 이름 | `ros2 service list`·`ros2 topic list`에 v0.3 이름 서비스 6개·토픽 2개가 있고 11-25 이름은 0건 |
| 8 | 화면 | `:8080/admin`에서 관리자 명령 1건, `/reception`에서 접수 1건, `/table`에서 주문 1건이 처리됨(HTTP 경로는 그대로인데 뒤의 서비스가 바뀌므로 확인) |
| 9 | 문서 | README·INTERFACES.md·COMMANDS.md의 이름이 코드와 같고, 2차 연동테스트 기획 5.1절의 명령이 그대로 통함 |

시뮬 실행 폴더는 `archive/sim_runs_2026-11-26/`(또는 실행한 날짜)로 옮깁니다. 실기기 확인은 6장 3단계에서 합니다.

## 6. 순서

| 단계 | 내용 | 누가 | 조건 |
| --- | --- | --- | --- |
| 0 | 4장 조건 확인, 수정 전 기준선(pytest 건수, `fleet_bench` 결과) 저장 | 부장 | 사용자 실행 지시, 커밋 완료 |
| 1 | 인터페이스 정의 6개 이름 변경 → 노드 → 주석 → 문서 순으로 수정 | 부장 | — |
| 2 | 5장 1~9 확인, 보고 | 부장 → 기획 검토 | — |
| 3 | 로봇 세 대 `--deploy`와 팔 Pi 복사·빌드, `--check` | 부장 | 사용자 확인 뒤. 2차 시험 준비(OPEN·CLOSE, 새 지도)가 끝난 뒤 한 번에 |
| 4 | 실기기에서 관제 기동 → 이동 명령 1건 → 서빙 1건 | 2차 연동테스트 단계 0~4에서 겸함 | — |

3단계를 미루는 이유: 8건은 관제 PC 안의 통신이라 로봇에 배포하지 않아도 통신은 됩니다. 다만 `--deploy`는 `frybot_interfaces`와 `frybot_control`도 로봇에 복사·빌드하므로, 2차 시험의 "모든 기기 같은 빌드" 조건을 맞추려면 배포가 필요하고, 다른 변경과 묶어 한 번에 하는 편이 로봇 빌드 횟수를 줄입니다. `--check`는 `FleetHeartbeat`만 보므로 이 차이를 잡지 못합니다. 배포본 확인은 로봇의 정의 파일 목록으로 합니다.

## 7. 위험

| 위험 | 대응 |
| --- | --- |
| 11-25 변경을 통째로 되돌려 HTTP 경로까지 옛 것이 됨 | 2장 "바꾸지 않는 것"을 지시서에 명시. 완료 기준 8에서 화면 요청이 통하는지 확인 |
| 한 곳을 빠뜨려 실행 중에 서비스를 못 찾음 | 완료 기준 2(검색 0건)와 7(실행 중 이름), 6(시뮬 임무 10건) |
| 인터페이스 빌드 찌꺼기로 옛 타입이 남음 | 완료 기준 1에서 build·install을 지우고 빌드. 옛 타입 import가 ImportError인지 확인 |
| 로봇과 관제 PC의 빌드가 달라짐 | 6장 3단계. 그 전에는 "로봇 배포본은 11-25 이전 또는 11-25 이름"이라고 기록 |
| 오늘까지의 실기기 기록이 11-25 이름으로 남아 있음 | 기록은 고치지 않음. README에 "2026-11-25~26 사이의 실행은 v0.2 이름"이라고 한 줄 남김 |
| 실패했을 때 되돌리기 | 4장 조건 1(사전 커밋) |

## 8. 이 작업 뒤에도 남는 차이

- "설계" 항목: 웹 01~10, 38, 39번(검토 문서 7.1절 다 묶음). 2차 시험 뒤로 미루는 것이 기획 의견이며 결정 전입니다.
- 정의서 쪽 문제 R-1~R-11(검토 문서 7.2절). 01·22·24번 행 누락, 01·22번 본문 깨짐 등은 작성자에게 전달할 내용입니다.

## 9. 사용자 결정이 필요한 것

| # | 결정 | 기획 제안 |
| --- | --- | --- |
| 1 | 언제 실행하는가 | 2차 연동테스트 전, 준비 작업 중 가장 먼저 |
| 2 | 시작 전에 지금 상태를 커밋하는가 | 커밋 권장(직접 하심) |
| 3 | 로봇·팔 Pi 배포 시점 | OPEN·CLOSE와 새 지도가 끝난 뒤 한 번에 |
| 4 | `docs/INTERFACES.pdf`를 다시 만드는가 | 이번에는 만들지 않음(이름은 맞게 되고, 그 밖의 내용이 옛것인지는 따로 확인 필요) |

작업 지시서 초안은 기획 세션의 임시 폴더에 있으며(`WORK_ORDER_if_v03_names.md`), 실행 지시가 오면 이 문서의 5·6장에 맞춰 고쳐서 보냅니다.
