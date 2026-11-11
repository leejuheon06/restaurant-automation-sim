from glob import glob
from setuptools import setup
package_name = 'frybot_web'
setup(
    name=package_name, version='0.1.0', packages=[package_name],
    data_files=[('share/ament_index/resource_index/packages', ['resource/' + package_name]),
                ('share/' + package_name, ['package.xml']),
                ('share/' + package_name + '/static', glob('static/*'))],
    install_requires=['setuptools'], zip_safe=True,
    maintainer='OneTeam', maintainer_email='oneteam@example.com',
    description='FryBot web service', license='Apache-2.0',
    entry_points={'console_scripts': ['web_service = frybot_web.web_service_node:main']},
)
