# [수정 2026-11-25] I/F 정의서 v0.2 이름: TaskEvent, /fms/task_events -> TaskProgress,
# /frybot/tasks/progress
# [수정 2026-11-26] I/F v0.3 최종 판 이름: TaskProgress,
# /frybot/tasks/progress -> TaskEvent, /fms/task_events
# 임무 상태 변화 하나. Task Manager -> Central Control, /fms/task_events
# stamp: 발행 시각(Task Manager 의 ROS 시계)
builtin_interfaces/Time stamp
# task_id: 관제가 붙인 임무 번호(종류 첫 글자 + 4자리 순번, 예: G0001)
string task_id
string task_type      # GUIDE SERVE COLLECT COOK MOVE
# state, by task type (all of them are published by frybot_control/fleet_core.py):
#   any AMR task : ASSIGNED ... DONE | SUSPENDED (reason = cause) RESUMED REASSIGNED CANCELED
#                  [수정 2026-11-18] SUSPENDED 의 reason: OFFLINE, E_STOP, PAUSED, NAV2_FAILED 등과
#                  PLAN_FAIL(같은 목적지 계획 실패가 20초 넘게 이어짐, RETRY_TASK 로 재개)
#   GUIDE        : AT_START ARRIVED
#   SERVE        : LOADED SERVING DELIVERED
#                  [수정 2026-11-18] SERVING = 적재 뒤 테이블행 구간을 처음 나아갔을 때 한 번 (State Diagram v4)
#   COLLECT      : COLLECTED RETURNED
#   COOK         : COOKING READY (reason = pick-up place) | SUSPENDED RESUMED CANCELED
string state
# robot_id: 맡은 로봇 ('' = 미배정. COOK 은 로봇을 배정하지 않아 늘 '')
string robot_id
# visit_id, order_id, item_id, table_id: 임무를 접수할 때 받은 값
#   (SubmitTask 그대로, 없으면 0)
int64 visit_id
int64 order_id
int64 item_id
int32 table_id
# plan_version: 맡은 로봇의 현재 경로 번호 (로봇이 없으면 0)
int32 plan_version
# reason: 위 state 별 사유. 주지 않으면 임무에 남은 마지막 사유
string reason
