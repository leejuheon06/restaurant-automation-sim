# frybot_ws

다중 로봇 협업 스마트 레스토랑(FryBot) 시뮬레이션용 ROS 2 Jazzy (Gazebo Harmonic) 작업 공간입니다.
사용법과 구조는 [src/frybot/README.md](src/frybot/README.md)에 있습니다.

## 받기

```bash
git clone <이 저장소> ~/frybot_ws && cd ~/frybot_ws
vcs import < deps.repos        # pinky_pro, mycobot_ros2 (python3-vcstool)
colcon build --symlink-install --packages-up-to frybot_bringup
source install/setup.bash
ros2 launch frybot_bringup sim.launch.py
```

`bench_*.csv`는 알고리즘 조합 비교(`fleet_bench`) 결과입니다.
