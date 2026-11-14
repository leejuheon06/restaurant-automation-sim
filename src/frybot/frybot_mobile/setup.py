from glob import glob
from setuptools import setup
package_name = 'frybot_mobile'
setup(
    name=package_name, version='0.1.0', packages=[package_name],
    data_files=[('share/ament_index/resource_index/packages', ['resource/' + package_name]),
                ('share/' + package_name, ['package.xml']),
                ('share/' + package_name + '/launch', glob('launch/*.py')),
                ('share/' + package_name + '/config', glob('config/*'))],
    install_requires=['setuptools'], zip_safe=True,
    maintainer='OneTeam', maintainer_email='oneteam@example.com',
    description='FrybotMobile: software that runs on (or for) one AMR', license='Apache-2.0',
    entry_points={'console_scripts': ['mobile_controller = frybot_mobile.mobile_controller:main']},
)
