# frybot_sim 설치 설정(ament_python). 손님 시뮬레이터 화면
# (static/customer.html)을 share/frybot_sim/static 에 설치한다.
from setuptools import setup
package_name = 'frybot_sim'
setup(
    name=package_name, version='0.1.0', packages=[package_name],
    data_files=[('share/ament_index/resource_index/packages', ['resource/' + package_name]),
                ('share/' + package_name, ['package.xml']),
                ('share/' + package_name + '/static', ['static/customer.html'])],
    install_requires=['setuptools'], zip_safe=True,
    maintainer='OneTeam', maintainer_email='oneteam@example.com',
    description='FryBot simulation nodes', license='Apache-2.0',
    # 실행 파일(ros2 run frybot_sim <이름>)
    entry_points={'console_scripts': [
        # [수정 2026-11-17] cook_arm 은 frybot_arm 패키지의 arm_controller 로
        # 옮김 (SW 아키텍처의 Frybot Cooking Package)
        'world = frybot_sim.world_node:main',  # 매장 시뮬
        'ai_server = frybot_sim.ai_server:main',  # AI 서버 대역
        'customer_ui = frybot_sim.customer_ui_node:main',  # 손님 시뮬레이터 UI
        'scenario = frybot_sim.scenario_runner:main',  # 자동 시나리오
        'nav2_watchdog = frybot_sim.nav2_watchdog:main',  # Nav2 기동 감시
    ]},
)
