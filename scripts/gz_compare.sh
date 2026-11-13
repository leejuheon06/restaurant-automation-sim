#!/bin/bash
# Run the same Gazebo scenario several times per algorithm pair (headless) and keep each run's logs.
#   scripts/gz_compare.sh <out_dir> <runs> <scenario> "<scheduler> <planner>" ["<scheduler> <planner>" ...]
OUT=$1; RUNS=$2; SCEN=$3; shift 3
WS=$(cd "$(dirname "$0")/.." && pwd)
source "$WS/install/setup.bash"
mkdir -p "$OUT"
for k in $(seq "${FIRST:-1}" "$RUNS"); do
  for pair in "$@"; do
    read -r S P <<< "$pair"
    tag="${S}__${P}__run${k}"
    bash "$WS/scripts/stop_all.sh" > /dev/null 2>&1
    ros2 launch frybot_bringup gazebo.launch.py gui:=false rviz:=false scheduler:=$S planner:=$P > "$OUT/$tag.launch.log" 2>&1 &
    for i in $(seq 1 240); do [ "$(grep -c 'Nav2 active' "$OUT/$tag.launch.log")" -ge 3 ] && break; sleep 1; done
    echo "$tag nav2_active=$(grep -c 'Nav2 active' "$OUT/$tag.launch.log")" >> "$OUT/progress.txt"
    t0=$(date +%s)
    timeout 960 ros2 run frybot_sim scenario --scenario "$SCEN" --timeout 900 > "$OUT/$tag.scenario.log" 2>&1
    echo "elapsed=$(( $(date +%s) - t0 ))" >> "$OUT/$tag.scenario.log"
    curl -s http://127.0.0.1:8090/api/state > "$OUT/$tag.state.json" 2>/dev/null
    run=$(ls -td "$WS"/runs/*/ | head -1)
    cp "$run/events.csv" "$OUT/$tag.events.csv"
    echo "$tag done elapsed=$(( $(date +%s) - t0 ))" >> "$OUT/progress.txt"
  done
done
bash "$WS/scripts/stop_all.sh" > /dev/null 2>&1
echo ALL_DONE >> "$OUT/progress.txt"
