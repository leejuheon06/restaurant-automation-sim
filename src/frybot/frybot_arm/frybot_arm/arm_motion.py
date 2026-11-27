"""조리 팔(JetCobot 280 = myCobot 280 Pi)의 관절 이름과 작업별 자세 (대역).

팔 구동 방식이 정해지면 이 파일의 관절 애니메이션을 실제 궤적으로 바꿉니다.
"""
import math

# 관절 이름(myCobot 280 URDF, 베이스 -> 끝 순서). joint_states 에 씀
JOINTS = ['joint2_to_joint1', 'joint3_to_joint2', 'joint4_to_joint3',
          'joint5_to_joint4', 'joint6_to_joint5', 'joint6output_to_joint6']
# 휴식 자세(rad, JOINTS 순서). 작업 전후와 대기 중 자세
REST = [0.0, 0.5, -1.9, 1.3, 0.0, 0.0]

# 작업 -> (베이스 yaw, 뻗은 자세). yaw 는 팔 베이스 기준.
POSES = {
    # 팔 A(튀김): 바구니 담기·튀김기에 넣기·건져 기름 빼기, 웍으로 옮기기,
    # 볶음밥 재료 넣기. 팔 B(웍): 소스·볶기. PLATE·PLACE_HANDOFF 는 둘 다
    # (fleet_core._recipe 기준)
    'LOAD_BASKET': (0.9, [0.0, -0.9, -0.9, 0.2, 0.0, 0.0]),
    'DROP_IN_FRYER': (-0.6, [0.0, -1.2, -0.4, 0.0, 0.0, 0.0]),
    'LIFT_DRAIN': (-0.6, [0.0, -0.7, -0.9, 0.0, 0.0, 0.6]),
    'PLATE': (0.3, [0.0, -1.0, -0.7, 0.1, 0.0, 1.2]),
    'PLACE_HANDOFF': (math.pi, [0.0, -1.2, -0.3, -0.1, 0.0, 0.0]),
    'TO_WOK': (-1.2, [0.0, -1.1, -0.5, 0.0, 0.0, 1.2]),
    'ADD_SAUCE': (0.5, [0.0, -1.0, -0.7, 0.1, 0.0, 1.0]),
    'ADD_INGREDIENTS': (-1.2, [0.0, -1.1, -0.5, 0.0, 0.0, 1.2]),
    'STIR_FRY': (0.0, [0.0, -1.0, -0.8, 0.2, 0.0, 0.0]),
}


def arm_pose(job: str, progress: float, t: float = 0.0) -> list[float]:
    """작업 진행률에 맞는 관절 각도를 돌려준다.

    휴식 -> 뻗음 -> 휴식 순으로 움직이고, STIR_FRY 는 웍을 흔든다.

    Args:
        job: ArmJob 의 작업 이름. 모르는 작업이면 휴식 자세.
        progress: 진행률 0..1.
        t: 현재 시각(초). 흔드는 동작의 위상에 씀.

    Returns:
        JOINTS 순서의 관절 각도(rad) 6개.
    """
    yaw, reach = POSES.get(job, (0.0, REST))
    k = math.sin(math.pi * min(max(progress, 0.0), 1.0))    # 0 -> 1 -> 0
    q = [REST[i] + (reach[i] - REST[i]) * k for i in range(6)]
    q[0] = yaw * min(1.0, k * 1.5)
    # 웍 흔들기: 진행률 10~90% 구간에서 베이스와 4번째 관절을 흔듦
    if job == 'STIR_FRY' and 0.1 < progress < 0.9:
        q[0] += 0.25 * math.sin(t * 6.0)
        q[3] += 0.2 * math.sin(t * 6.0 + 1.0)
    return q
