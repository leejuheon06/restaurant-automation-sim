# Central traffic permission: the robot may advance up to waypoint index granted_index of plan_version.
# - plan_version never repeats: the Task Manager starts every session from a time-based number, so a permission of an
#   earlier session can not match a new route. The robot also drops permissions older than its current route.
# - The Task Manager repeats the current permission of every active route (about 2 Hz), so a lost message or a robot
#   that subscribed late only delays the robot by one period.
# - task_id is for logs only; the robot matches on robot_id + plan_version.
# robot_id: 허가받는 로봇. 다른 로봇의 허가는 무시함
string robot_id
string task_id
# plan_version: 허가가 속한 경로 번호(NavigateRoute.plan_version)
int32 plan_version
# granted_index: 이 경로 순번(route[i])까지 가도 됨. route[0]은 허가
#   없이 감. 로봇은 같은 경로에서 받은 가장 큰 값을 씀
int32 granted_index
