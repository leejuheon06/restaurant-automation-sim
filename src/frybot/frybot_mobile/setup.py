"""frybot_mobile 패키지 설치 설정(ament_python).

launch/*.py, config/* 를 share 에 설치하고 실행 파일 5개를 등록한다.
"""
from glob import glob
from setuptools import setup
package_name = 'frybot_mobile'
setup(
    name=package_name, version='0.1.0', packages=[package_name],
    # 설치 데이터: ament 색인, package.xml, launch/*.py, config/*
    data_files=[('share/ament_index/resource_index/packages', ['resource/' + package_name]),
                ('share/' + package_name, ['package.xml']),
                ('share/' + package_name + '/launch', glob('launch/*.py')),
                ('share/' + package_name + '/config', glob('config/*'))],
    install_requires=['setuptools'], zip_safe=True,
    maintainer='OneTeam', maintainer_email='oneteam@example.com',
    description='FrybotMobile: software that runs on (or for) one AMR', license='Apache-2.0',
    # [수정 2026-11-20] serving_arm_driver 추가(서빙 팔 JetCobot 280 실물
    # 구동 노드, 팔의 Pi 에서 실행). 목록을 한 줄에 하나씩으로 나눔
    entry_points={'console_scripts': [
        # 경로 실행·상태 보고(로봇, 시뮬 공용)
        'mobile_controller = frybot_mobile.mobile_controller:main',
        # 도킹용 ArUco 마커 검출(마커 도크가 있을 때만 뜸)
        'aruco_dock_detector = frybot_mobile.aruco_dock_detector:main',
        # 실기기 바퀴 구동·오도메트리, 배터리 발행(Pinky Pi)
        # [수정 2026-11-17] pinky_bringup 의 bringup, battery_publisher 사본
        'pinky_driver = frybot_mobile.pinky_driver:main',
        'pinky_battery = frybot_mobile.pinky_battery:main',
        # 서빙 팔 실물 구동(팔의 Pi)
        'serving_arm_driver = frybot_mobile.serving_arm_driver:main']},
)
