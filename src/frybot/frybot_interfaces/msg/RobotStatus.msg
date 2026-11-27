# AMR 한 대의 상태 보고. mobile_controller -> Task Manager,
# /fleet/robot_status, 0.1초 타이머(10 Hz)
# stamp: 보고 시각(로봇 ROS 시계)
builtin_interfaces/Time stamp
# robot_id: 보고하는 로봇 이름(pinky1..N)
string robot_id
# state: IDLE MOVING TURN DOCKING WAIT_GRANT WAIT_NAV2 NAV2_RETRY PAUSED_GUEST CHARGING
#        YIELD YIELD_BLOCKED (양보 후진 / 뒤가 막힘)
# [수정 2026-11-20] T-46: FRONT_BLOCKED (막다른 곳에서 전진으로 나갈 때 앞 라이다에 막힘)
# [수정 2026-11-27] T-63: BACKOFF (Nav2 가 장애물 앞에서 구간을 포기한 뒤
#        NAV2_FAILED 를 돌려주기 전에 조금 물러나는 중)
#        WAIT_FMS (no heartbeat from the Task Manager)  E_STOP (held by the emergency-stop channel)
#        or, while the serving arm works, the arm job name (LOAD UNLOAD COLLECT_DISHES RETURN_DISHES)
string state
# x, y (m), yaw (rad): 지도(map) 좌표계의 로봇 자세.
#   LOCALIZING / NOT_LOCALIZED 보고에서는 채우지 않음(0)
float64 x
float64 y
float64 yaw
float32 battery       # 0..100 (percent)
# charging: 충전 중. 배터리 토픽이 있으면(실기기) 잔량 변화로,
#   시뮬은 sim_backend 가 판단
bool charging
# task_id: 마지막으로 받은 경로(NavigateRoute)의 task_id ('' = 없음)
string task_id
# plan_version: 마지막으로 받은 경로의 번호 (0 = 아직 없음)
int32 plan_version
int32 reached_index   # index of last reached waypoint of the active route (-1 none)
string node_id        # roadmap node the robot reached last ('' until it reached one)
string arm_state      # IDLE or current arm job
# error: '' when nothing is wrong, else a name from frybot_control/device_state.py ERROR:
#        COMMUNICATION_ERROR (no heartbeat)  EMERGENCY_STOP  DRIVE_ERROR (Nav2 could not drive the last segment)
#        SENSOR_ERROR (localisation TF older than tf_stale_sec: the robot stands still)
# [수정 2026-11-20] T-49: a robot that is not localised yet (measured map, no AMCL pose) sends only
#   state LOCALIZING (auto localisation from the lidar scan running, x/y meaningless) or
#   state NOT_LOCALIZED with error SELF_CHECK_ERROR (ambiguous / no match: set the pose in RViz);
#   without auto localisation (initial_pose given, auto_localize false) it sends nothing until AMCL has a pose.
#   SELF_CHECK_ERROR (localisation failed at start)
string error
