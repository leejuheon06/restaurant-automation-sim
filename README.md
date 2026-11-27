# frybot_ws

다중 로봇 협업 스마트 레스토랑(FryBot)의 ROS 2 Jazzy 작업 공간입니다. 실제 Pinky 로봇 주행과 시뮬레이션(경량 시뮬, Gazebo Harmonic)을 함께 다룹니다.
사용법과 구조는 [src/frybot/README.md](src/frybot/README.md)에 있습니다.

## 받기

```bash
git clone <이 저장소> ~/frybot_ws && cd ~/frybot_ws
colcon build --symlink-install --packages-up-to frybot_bringup
source install/setup.bash
ros2 launch frybot_bringup sim.launch.py                          # 경량 시뮬
ros2 launch frybot_bringup real.launch.py map_id:=test_map_v001  # 실제 Pinky
```

알고리즘 조합 비교 자료(1차 비교, 선정 보고서, `bench_*.csv`, Gazebo 검증 로그)는 2026-11-17에 `archive/algorithm_comparison_2026-11.tar.gz`로 묶어 보관했습니다. 2026-11-14 맵 변경 이전의 시뮬레이션·오프라인 수치입니다.
