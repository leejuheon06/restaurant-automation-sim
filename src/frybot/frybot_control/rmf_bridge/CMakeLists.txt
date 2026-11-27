# Open-RMF 도우미(rmf_plan_server) 빌드. colcon 패키지가 아니라 따로 빌드:
#   source /opt/ros/jazzy/setup.bash
#   cmake -S src/frybot/frybot_control/rmf_bridge -B build/rmf_bridge
#   cmake --build build/rmf_bridge
# 결과 파일 경로는 planners/rmf.py 의 SERVER 기본값과 같아야 함
cmake_minimum_required(VERSION 3.16)
project(frybot_rmf_bridge CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_BUILD_TYPE Release)
# 경로 계획·협상(rmf_traffic), 배터리 모델(rmf_battery), 임무 배정(rmf_task)
find_package(rmf_traffic REQUIRED)
find_package(rmf_battery REQUIRED)
find_package(rmf_task REQUIRED)
add_executable(rmf_plan_server rmf_plan_server.cpp)
target_link_libraries(rmf_plan_server PRIVATE rmf_traffic::rmf_traffic rmf_battery::rmf_battery rmf_task::rmf_task)
