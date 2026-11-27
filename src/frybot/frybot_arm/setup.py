"""frybot_arm: Frybot Cooking Package (SW 아키텍처 v016)."""
from glob import glob

from setuptools import setup

package_name = 'frybot_arm'
setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    # 설치할 파일: ament 패키지 표시, package.xml, launch/*.py
    data_files=[
        ('share/ament_index/resource_index/packages',
         ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', glob('launch/*.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='OneTeam',
    maintainer_email='oneteam@example.com',
    description='Frybot Cooking Package: cooking arms A (chicken) / B (wok)',
    license='Apache-2.0',
    # ros2 run frybot_arm <이름> 으로 띄우는 실행 파일
    entry_points={'console_scripts': [
        'master_controller = frybot_arm.master_controller:main',
        'arm_controller = frybot_arm.arm_controller:main',
    ]},
)
