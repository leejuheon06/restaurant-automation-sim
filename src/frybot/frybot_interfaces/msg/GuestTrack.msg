# [수정 2026-11-17] 신규 (UR-03): 안내 중인 손님의 동행 상태.
# Central Control -> AMR, /frybot/guest_track. AI 서버가 AMR 카메라 영상에서
# 얻은 결과(HTTP /ai/result 의 kind = GUEST_TRACK)를 Central Control 이 옮겨 싣는다.
# [수정 2026-11-24] 실제 AI 서버(frybot_ai guest_tracker, YOLO)는 visit_id 를
# 보내지 않는다. Central Control 이 그 로봇이 맡은 안내 방문(ASSIGNED·GUIDING)
# 으로 채우고, 그런 방문이 없으면 이 메시지를 내지 않는다.
# AMR 은 robot_id 가 자기 것이고 visit_id 가 안내 중인 손님인 것만 쓴다.
# 안내 구간에서 visible = false 이거나 distance 가 follow_pause_dist 보다 크면
# 멈춰서 기다리고(PAUSED_GUEST), guest_timeout 을 넘으면 GUEST_LOST 로 끝낸다.
builtin_interfaces/Time stamp
# stamp: Central Control 이 AI 결과를 받아 다시 보낸 시각(ROS 시계)
# robot_id: 손님을 안내 중인 로봇(AI 결과의 robot_id)
string robot_id
# [수정 2026-11-25] I/F 정의서 v0.2 이름: CheckIn -> RegisterVisit
# [수정 2026-11-26] I/F v0.3 최종 판 이름: RegisterVisit -> CheckIn
# visit_id: 안내 중인 손님 그룹의 방문 번호(CheckIn 의 visit_id)
# [수정 2026-11-24] AI 결과에 없으면 Central Control 이 채움(위 설명)
int64 visit_id
# visible: AI 결과에 값이 없으면 Central Control 이 true 로 채움
bool visible          # 손님이 카메라에 보이는지
# distance: AI 결과에 값이 없으면 0.0 으로 채움
float32 distance      # 로봇에서 손님까지의 거리 (m). visible = false 면 쓰지 않음
