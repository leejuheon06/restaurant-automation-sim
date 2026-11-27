"""frybot_control 패키지 설치 설정(ament_python)."""
from setuptools import setup, find_packages
package_name = 'frybot_control'
setup(
    name=package_name, version='0.1.0', packages=find_packages(),
    data_files=[('share/ament_index/resource_index/packages', ['resource/' + package_name]),
                ('share/' + package_name, ['package.xml'])],
    # 지도 폴더(maps/<map_id>/ 의 roadmap.json, yaml, pgm, png)를 함께 설치
    package_data={package_name: ['maps/*/*.json', 'maps/*/*.yaml', 'maps/*/*.pgm', 'maps/*/*.png']},
    install_requires=['setuptools'], zip_safe=True,
    maintainer='OneTeam', maintainer_email='oneteam@example.com',
    description='FryBot Central Control + Task Manager', license='Apache-2.0',
    # ros2 run frybot_control <이름> 으로 실행하는 명령 -> 모듈:함수
    entry_points={'console_scripts': [
        'central_control = frybot_control.central_control_node:main',
        'task_manager = frybot_control.task_manager_node:main',
        'analyze_run = frybot_control.analyze:main',
        'fleet_bench = frybot_control.offline_bench:main',
        'export_map = frybot_control.store_map:main',
        # [수정 2026-11-17] T-23: 실기기 로그 재현 도구
        'replay_run = frybot_control.replay_run:main',
        # [수정 2026-11-23] 작업 지시 18: 천장 카메라 초기 위치 판정
        'ceiling_locator = frybot_control.ceiling_locator_node:main',
        'ceiling_tool = frybot_control.ceiling_tool:main',
    ]},
)
