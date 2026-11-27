# Task Manager -> all robots, about 5 Hz on /fms/heartbeat. Liveness of the central control and the emergency-stop
# channel (independent of the NavigateRoute action).
# A robot that drives a route and hears no heartbeat for fms_timeout seconds stops where it is until one arrives.
# 생존 신호 한 번(Task Manager 0.2초 타이머). 받는 쪽: mobile_controller
# stamp: 발행 시각(Task Manager 의 ROS 시계). 로봇은 이 값이 아니라
#   자기가 받은 시각(벽시계)으로 끊김을 판단함(fms_timeout 기본 1초,
#   2026-11-24 에 2초에서 줄임)
builtin_interfaces/Time stamp
# session: Task Manager 기동 시각(유닉스 초)의 16진수 문자열
string session        # changes every time the Task Manager starts: a robot then drops old permissions and its route
string[] estop        # robots that must stand still now (drive and serving arm) until they leave this list
