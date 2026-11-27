"""frybot_ai 패키지 설치 설정(ament_python).

[수정 2026-11-24] 새 파일: AI 서버(guest_tracker)와 런치를 설치한다.
"""

from glob import glob

from setuptools import setup

package_name = 'frybot_ai'
setup(
    name=package_name, version='0.1.0', packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',
         ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', glob('launch/*.py')),
    ],
    install_requires=['setuptools'], zip_safe=True,
    maintainer='OneTeam', maintainer_email='oneteam@example.com',
    description='FryBot AI server (YOLO guest tracking)',
    license='Apache-2.0',
    entry_points={'console_scripts': [
        # 손님 추적(YOLO). 보통은 런치가 가상 환경 Python 으로 띄움
        'guest_tracker = frybot_ai.guest_tracker:main',
    ]},
)
