# One roadmap node on a route.
# not_before = planned earliest departure toward the NEXT node (unix seconds, wall clock of the Task Manager, 0 = none).
# It is information only: the robot does NOT wait for it. The Task Manager enforces the timing by holding back the
# TrafficGrant of the next node until that moment (and shifts its own plan when a robot runs late).
# node_id: 로드맵 노드 이름(roadmap.json 의 nodes 키)
string node_id
# x, y: 그 노드의 지도(map) 좌표 (m)
float64 x
float64 y
float64 not_before
