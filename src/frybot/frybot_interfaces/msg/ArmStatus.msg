# [수정 2026-11-17] 신규 (UR-17, 19): 로봇팔 한 대의 상태·오류 보고.
# 팔 제어기 -> Task Manager, /fleet/arm_status, 약 2 Hz.
#   조리 팔: frybot_arm 의 arm_controller (arm_id = cook_arm_a | cook_arm_b)
#   서빙 팔: frybot_mobile 의 mobile_controller (arm_id = 로봇 id, 예: pinky1)
# 조리 팔의 보고가 3초 넘게 끊기면 관제는 그 팔을 OFFLINE 으로 표시한다.
# [수정 2026-11-20] 서빙 팔은 serving_arm:=real 이면 작업을 실물 구동부
# (serving_arm_driver)로 넘기지만, 이 보고는 그때도 mobile_controller 가 관제가
# 보낸 작업 기준으로 낸다. error 는 조리 팔 대역·서빙 팔 모두 항상 비어 있다
# (실물 팔의 끊김·오류는 아직 여기로 보고하지 않고 ArmJob 결과로만 전달).
builtin_interfaces/Time stamp
# stamp: 보내는 노드의 ROS 시계(get_clock) 기준 보고 시각
# arm_id: 보고하는 팔. cook_arm_a | cook_arm_b, 서빙 팔은 로봇 id
string arm_id
string state          # frybot_control/device_state.py STATE 이름: IDLE COOKING ARM_OPERATING FAULT_HANDLING ...
string job            # 수행 중인 ArmJob 의 job 이름 ('' = 없음)
string task_id        # 그 작업의 임무 id ('' = 없음)
string error          # '' = 이상 없음, 아니면 device_state.py ERROR 이름 (ARM_ERROR GRIPPER_ERROR ...)
