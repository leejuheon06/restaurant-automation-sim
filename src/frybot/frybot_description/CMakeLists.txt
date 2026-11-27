# 로봇 모델 파일(URDF·xacro·메시·라이선스)을 share 에 설치만 하는
# ament_cmake 패키지. 빌드할 코드는 없다.
cmake_minimum_required(VERSION 3.8)
project(frybot_description)

find_package(ament_cmake REQUIRED)

# pinky: Pinky Pro xacro + meshes, jetcobot: myCobot 280 Pi URDF + meshes
install(DIRECTORY pinky jetcobot licenses DESTINATION share/${PROJECT_NAME})

ament_package()
