# P4 분기 분류표: "실측 지도" 판정이 실제로 묻는 것 (2026-11-18)

`docs/2026-11-18_REAL_FIRST_PLAN.md` 6장 "수정 1"의 결과물입니다. 코드는 바꾸지 않았습니다. 사용자 확인 뒤 2~4(구조 변경, 분기 교체)를 진행합니다.

- 줄 번호는 2026-11-18 P1~P3와 `map:=` 삭제 뒤의 작업 트리 기준입니다.
- 지금 판정 방법:
  - 관제(`fleet_core`, `layout.Graph`): `graph.map_id`가 비었는지(proto는 빈 문자열)
  - 로봇: `measured_map = bool(Graph().map_id)`
  - 관제 노드, 웹: `active_map_id()`
- 표의 "제안 속성"은 6장 수정 3의 `has_tables`, `has_chargers`, `has_docks`에 맞춘 이름입니다.
- 세 속성으로 나타낼 수 없는 것은 따로 이름을 붙였습니다. 이름과 분류는 확인을 받을 항목입니다.

## 1. 분류 요약

| 묻는 것 | 곳 수 | 제안 속성 | 비고 |
|---|---|---|---|
| A. 매장 정보(테이블·작업 지점)가 있는가 | 4 | `has_tables` | 접수·서빙·회수 임무를 받을지 |
| B. 홈이 충전대인가(대기 위치, 배터리 복귀, 홈 복귀 방식) | 5 | `has_chargers` | proto는 홈 = 충전대 + 대기 위치, 실측 지도는 홈 = 출발 노드 |
| C. 정밀 도킹 지점이 있는가 | 2 | `has_docks` | |
| D. 출발 위치를 믿을 수 있는가(위치 추정 전 자리 잠금, 보고 시작) | 6 | 새 이름 필요(예: `start_known`) | 지도가 아니라 위치 추정 방식(AMCL 여부)에 가까움 |
| E. 임무 없는 로봇을 운영자가 세운 자리에 둘 것인가(T-26 "조용히") | 4 | 새 이름 필요(예: `keep_idle_spot`) | 지도 기능이 아니라 운용 방식 |
| F. 노드 이동 명령·자동 홈 이동을 받는가 | 3 | 새 이름 필요(예: `free_moves`) 또는 "has_tables 가 아님" | |
| G. Nav2 설정이 실측 지도용인가(전진 전용, 후진 제어기, 실패 처리) | 7 | 지도 속성이 아님. 로봇의 Nav2 설정 또는 시뮬 여부 | 아래 3장 참고 |
| H. 표시·기록용 | 3 | 바꾸지 않음(지도 이름 그대로) | 6장 수정 5 대상 |

## 2. 분기별 표

| # | 위치 | 지금 조건 | 하는 일 | 실제로 묻는 것 | 분류 |
|---|---|---|---|---|---|
| 1 | `fleet_core.py:227` | `not map_id` | 시작할 때 홈 노드를 잠금 | 로봇이 정말 홈에 있다고 믿을 수 있는가(실측 지도는 위치 보고 뒤 `:1341`에서 잠금) | D |
| 2 | `fleet_core.py:267` | `map_id` | 임무 접수 거절("Restaurant stations are not defined") | 매장 정보가 있는가 | A |
| 3 | `fleet_core.py:326` | `r.task or not map_id` | 돌아가기에 실패한 로봇이 물러설지(T-26) | 임무 없는 로봇을 그 자리에 둘 것인가 | E |
| 4 | `fleet_core.py:329` | `not map_id` | 유휴 로봇 대기 위치 이동, 배터리 낮으면 충전대로 | 홈이 충전대이고 대기 위치를 쓰는가 | B |
| 5 | `fleet_core.py:547` | `not map_id`이면 안 함 | 기동 뒤 자동 홈 이동(`auto_home`) | 홈이 출발 노드이고 위치를 보고받은 뒤 옮겨야 하는가 | D(F와 겹침) |
| 6 | `fleet_core.py:578` | `map_id`이면 안 함 | `_go_home`(충전대·대기 위치로) | 홈이 충전대인가 | B |
| 7 | `fleet_core.py:680` | `map_id and task is None` | 유휴 로봇이 남을 비키게 하거나 우선순위를 뒤집지 않음 | 임무 없는 로봇을 조용히 둘 것인가 | E |
| 8 | `fleet_core.py:895` | `map_id` | 비켜 준 유휴 로봇이 원래 노드로 돌아감 | 운영자가 세운 자리를 유지할 것인가 | E |
| 9 | `fleet_core.py:1192` | `map_id and task is None` | 양보 뒤 복귀 판단(상대 남은 길이 그 노드를 지나는가) | 같음 | E |
| 10 | `fleet_core.py:1341` | `map_id` | 위치 보고가 오면 가장 가까운 노드를 잠금 | 출발 위치를 위치 보고로 정하는가 | D |
| 11 | `fleet_core.py:1583` | `not map_id`이면 거절 | 노드 이동 명령(`MOVE_TO_VERTEX`) | 임의 노드 이동을 허용하는가(proto에서는 막음) | F |
| 12 | `fleet_core.py:1704` | `map_id` | `GO_HOME`을 이동 명령으로 할지 `_go_home`으로 할지 | 홈이 충전대인가 | B(F와 겹침) |
| 13 | `fleet_core.py:1968` | 값 그대로 | 상태 JSON의 `map_id` | 표시용 | H |
| 14 | `restaurant.py:29` | `active_map_id()` | 테이블 목록(실측 지도는 빈 목록) | 매장 정보가 있는가 | A |
| 15 | `central_control_node.py:41` | `active_map_id() or 'frybot_200x100_v1'` | 실행 기록의 지도 이름 | 기록용 | H |
| 16 | `layout.py:131` | `active_map_id()` | `docks()`가 빈 목록 | 도크가 있는가 | C |
| 17 | `layout.py:192~196` | `'proto' -> ''` | proto는 `build_roadmap()`, 그 밖은 `roadmap.json` | 지도 읽는 곳(수정 3 대상) | 구조 |
| 18 | `layout.py:213~218` | `map_id` | 테이블·대기 위치·충전대 노드 채우기(실측 지도는 `waiting`만) | 매장 정보·충전대가 있는가 | A·B |
| 19 | `layout.py:229` | `map_id` | 홈을 `roadmap.json`의 `homes`에서 읽음 | 지도 읽는 곳 | 구조 |
| 20 | `web_service_node.py:108` | `active_map_id()` | 빈 id = 가상 매장 도면(화면 쪽 약속) | 표시용 | H(수정 5) |
| 21 | `web_service_node.py:118` | `active_map_id()` | 실측 지도 실행에서만 지도 그림 제공 | 그림이 있는 지도인가 | H |
| 22 | `mobile_controller.py:125` | `bool(Graph().map_id)` | `measured_map` 계산 | 아래 23~34의 근원 | - |
| 23 | `mobile_controller.py:176` | `kinematic and measured_map` | 경량 시뮬 실측 지도에서 자세를 참값으로 봄(T-25) | 시뮬 여부 + 출발 위치 | D |
| 24 | `mobile_controller.py:183` | `not measured_map` | AMCL에 홈 자세를 초기 자세로 보냄 | 출발 위치를 믿을 수 있는가 | D |
| 25 | `mobile_controller.py:315` | `measured_map and not have_truth` | 위치를 받기 전 팔 상태 보고 안 함 | 출발 위치를 모르는가 | D |
| 26 | `mobile_controller.py:931` | 같음 | 위치를 받기 전 상태 보고 안 함 | 같음 | D |
| 27 | `mobile_controller.py:489` | `nav2 and measured_map and 후진` | 양보 후진을 Nav2 대신 `cmd_vel`로 | Nav2 제어기가 전진 전용인가 | G |
| 28 | `mobile_controller.py:513` | `not measured_map or 안내 후진` | 후진 구간에 후진 제어기를 쓸지 | 같음 | G |
| 29 | `mobile_controller.py:515, 791, 805` | `measured_map` | Nav2 실패를 재시도 뒤 `NAV2_FAILED`로 돌려줌 | 실패 처리 방식(실기기 방식) | G |
| 30 | `mobile_controller.py:828` | `not measured_map` | Nav2가 3번 실패하면 그 구간을 직접 주행 | 시뮬(Gazebo)에서만 쓰는 대응 | G(시뮬) |
| 31 | `mobile_controller.py:639, 871` | `not measured_map` | 지역 costmap을 비움(Gazebo 라이다 무효값 대응) | 시뮬(Gazebo)에서만 쓰는 대응 | G(시뮬) |
| 32 | `mobile_controller.py:815` | `not measured_map or 후진` | Nav2 목표 전에 직접 회전 | Nav2 제어기가 제자리 회전을 하는가 | G |

(29·31은 같은 성격의 2~3곳을 한 줄로 묶었습니다. 줄 수로 32줄, 분기 자리로는 34곳입니다.)

## 3. 확인받을 것

1. **G(로봇의 Nav2 설정)는 지도 속성으로 바꾸지 않는 것을 권합니다.**
   - "실측 지도"는 사실상 "실기기 방식의 Nav2 설정"을 뜻합니다. `navigator.py`도 같은 조건(`measured`)으로 `FollowPath`를 전진 전용으로 덮어씁니다.
   - 지도에 테이블이 생겨도 이 동작은 그대로여야 합니다.
   - 따라서 로봇 파라미터(예: `nav2_profile:=real|sim`)로 두는 편이 맞다고 봅니다.
   - 30·31은 Gazebo 대응이라 D8(주행 분기)과 함께 시뮬 백엔드 쪽에서 볼 항목입니다.
2. **D(출발 위치)와 E(유휴 로봇을 세운 자리에 둠)는 지도 기능이 아니라 운용 방식입니다.**
   - 실제 매장 지도에 테이블을 넣으면 `has_tables`는 참이 됩니다.
   - 그래도 위치는 여전히 AMCL로 정하고, 로봇을 손으로 세워 두는 운용도 같습니다.
   - 따라서 `has_tables`에 묶지 말고 따로 두기를 권합니다. 예를 들면 관제 파라미터나 지도의 `start_known: false` 같은 키입니다.
3. **F(노드 이동 명령)**
   - 지금은 가상 매장(proto)에서만 막습니다.
   - 실제 매장 지도에서도 관리자 이동 명령은 쓸모가 있으므로, 지도와 무관하게 늘 받는 쪽을 제안합니다.
   - 다만 이것은 proto 동작이 바뀝니다. 바꾸지 않으려면 proto에만 `free_moves: false`를 둡니다.
4. **A·B·C는 기획안의 `has_tables`, `has_chargers`, `has_docks`로 그대로 바꿀 수 있습니다.**
   - 다만 4·6·12(B)는 "홈 = 충전대"와 "대기 위치를 쓴다"가 함께 묶여 있습니다.
   - `roadmap.json`에 `chargers`만 있고 대기 위치(`waiting`)는 이미 있는 실측 지도의 경우를 어떻게 볼지 정해야 합니다.
5. **H는 6장 수정 5(빈 id = proto 약속 삭제)와 함께 고칩니다.**
