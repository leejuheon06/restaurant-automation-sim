from glob import glob
from setuptools import setup
package_name = 'frybot_bringup'
setup(
    name=package_name, version='0.1.0', packages=[package_name],
    data_files=[('share/ament_index/resource_index/packages', ['resource/' + package_name]),
                ('share/' + package_name, ['package.xml']),
                ('share/' + package_name + '/launch', glob('launch/*.py')),
                ('share/' + package_name + '/rviz', glob('rviz/*.rviz'))],
    install_requires=['setuptools'], zip_safe=True,
    maintainer='OneTeam', maintainer_email='oneteam@example.com',
    description='FryBot bringup', license='Apache-2.0',
)
