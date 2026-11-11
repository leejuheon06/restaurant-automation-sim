cmake_minimum_required(VERSION 3.8)
project(frybot_interfaces)
find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(builtin_interfaces REQUIRED)
rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/Waypoint.msg" "msg/RobotStatus.msg" "msg/TaskEvent.msg" "msg/TrafficGrant.msg"
  "srv/CheckIn.srv" "srv/PlaceOrder.srv" "srv/EndUse.srv" "srv/AdminCommand.srv"
  "srv/SubmitTask.srv" "srv/FleetCommand.srv"
  "action/NavigateRoute.action" "action/ArmJob.action"
  DEPENDENCIES builtin_interfaces)
ament_export_dependencies(rosidl_default_runtime)
ament_package()
