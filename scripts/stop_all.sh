#!/bin/bash
# Stop every FryBot simulation process (run this as its own command).
P=("[l]aunch frybot_bringup" "lib/[f]rybot" "[r]obot_state_publisher" "[s]tatic_transform_publisher" "[p]arameter_bridge"
   "[i]gn gazebo" "[g]z sim" "[r]viz2 -d" "[c]ontroller_server" "[p]lanner_server" "[b]t_navigator" "[l]ifecycle_manager" "[o]pennav_docking"
   "[n]av2_map_server" "[n]av2_costmap_2d")   # [수정 2026-11-17] 실측 지도 시뮬의 지도 서버
for p in "${P[@]}"; do pkill -INT -f "$p" 2>/dev/null; done
sleep 3
for p in "${P[@]}"; do pkill -9 -f "$p" 2>/dev/null; done
sleep 1; echo "stopped"
