# frybot_interfaces: FryBot 의 msg·srv·action 정의를 코드로 만드는 패키지
# (rosidl). 정의를 바꾸면 이 패키지와 쓰는 패키지를 다시 빌드해야 함
cmake_minimum_required(VERSION 3.8)
project(frybot_interfaces)

# 빌드 도구, 인터페이스 생성기, 메시지의 stamp 가 쓰는 Time 타입
find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(builtin_interfaces REQUIRED)

# 아래 목록의 정의에서 Python·C++ 타입을 만듦. 새 정의 파일은 여기에
# 추가해야 생성됨
rosidl_generate_interfaces(
  ${PROJECT_NAME}
  # [수정 2026-11-25] I/F 정의서 v0.2 이름: TaskEvent -> TaskProgress,
  # CheckIn·PlaceOrder·EndUse·AdminCommand·FleetCommand -> RegisterVisit·
  # SubmitOrder·EndVisit·RequestAdminOperation·ControlTask
  # [수정 2026-11-26] I/F v0.3 최종 판 이름: TaskProgress -> TaskEvent
  "msg/Waypoint.msg" "msg/RobotStatus.msg" "msg/TaskEvent.msg" "msg/TrafficGrant.msg" "msg/FleetHeartbeat.msg"
  "msg/GuestTrack.msg" "msg/ArmStatus.msg"
  # [수정 2026-11-26] I/F v0.3 최종 판 이름: RegisterVisit -> CheckIn,
  # SubmitOrder -> PlaceOrder, EndVisit -> EndUse,
  # RequestAdminOperation -> AdminCommand, ControlTask -> FleetCommand
  "srv/CheckIn.srv" "srv/PlaceOrder.srv" "srv/EndUse.srv" "srv/AdminCommand.srv"
  "srv/SubmitTask.srv" "srv/FleetCommand.srv"
  # [수정 2026-11-23] 작업 지시 18: 천장 카메라 후보 자리 판정
  "srv/SpotCheck.srv"
  "action/NavigateRoute.action" "action/ArmJob.action"
  DEPENDENCIES builtin_interfaces
)

# 이 패키지를 쓰는 쪽이 실행할 때 필요한 rosidl 런타임을 함께 알림
ament_export_dependencies(rosidl_default_runtime)

ament_package()
