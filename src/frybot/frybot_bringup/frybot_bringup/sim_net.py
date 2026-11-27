"""시뮬레이션 런치의 통신 범위 설정 (sim.launch.py, gazebo.launch.py 공용)."""
import os


# [수정 2026-11-17] 신규 (A2): 시뮬을 실기기와 다른 ROS 도메인에서 돌림
def apply_sim_network(net: str, sim_domain: str) -> None:
    """런치가 띄울 프로세스의 통신 환경 변수를 정한다.

    Args:
        net: 'sim'(기본) 이면 시뮬 전용 도메인을 씀. 실기기(Pinky)와 관제
            PC 는 다른 도메인이라 시뮬의 /pinky1..N 과 서로 보이지 않음.
            'local' 은 탐색을 이 PC 로 제한(LOCALHOST). 이 PC 에서는 Gazebo
            (프로세스 52개)를 이렇게 띄우면 노드가 33개만 서로 보여 Nav2 가
            TF 를 받지 못했음(T-13, 관측 결과). 'lan' 은 아무것도 바꾸지
            않음(실기기와 같은 도메인: 로봇이 켜져 있으면 쓰지 않음).
        sim_domain: net 이 'sim' 일 때 쓸 ROS_DOMAIN_ID (0~101).

    Raises:
        ValueError: net 이 셋 중 하나가 아니거나 sim_domain 이 범위 밖일 때.
    """
    if net not in ('sim', 'local', 'lan'):
        raise ValueError(f'net:={net} 는 sim | local | lan 중 하나여야 합니다.')
    if net == 'lan':  # 환경 변수를 그대로 둠
        return
    if net == 'sim' and not (sim_domain.isdigit()
                             and 0 <= int(sim_domain) <= 101):
        raise ValueError(
            f'sim_domain:={sim_domain} 는 0~101 의 정수여야 합니다.')
    # Gazebo 통신은 두 경우 모두 이 PC 안에 묶음(T-13: 유선 랜이 끊기자
    # 시뮬 전체가 멈췄음)
    os.environ['GZ_IP'] = '127.0.0.1'
    if net == 'sim':
        os.environ['ROS_DOMAIN_ID'] = str(int(sim_domain))
        # 터미널에 LOCALHOST 가 남아 있어도 위 증상이 나지 않게 함
        os.environ['ROS_AUTOMATIC_DISCOVERY_RANGE'] = 'SUBNET'
    else:
        os.environ['ROS_AUTOMATIC_DISCOVERY_RANGE'] = 'LOCALHOST'
