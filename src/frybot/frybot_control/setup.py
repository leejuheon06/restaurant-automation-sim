from setuptools import setup, find_packages
package_name = 'frybot_control'
setup(
    name=package_name, version='0.1.0', packages=find_packages(),
    data_files=[('share/ament_index/resource_index/packages', ['resource/' + package_name]),
                ('share/' + package_name, ['package.xml'])],
    install_requires=['setuptools'], zip_safe=True,
    maintainer='OneTeam', maintainer_email='oneteam@example.com',
    description='FryBot Central Control + Task Manager', license='Apache-2.0',
    entry_points={'console_scripts': [
        'central_control = frybot_control.central_control_node:main',
        'task_manager = frybot_control.task_manager_node:main',
        'analyze_run = frybot_control.analyze:main',
        'fleet_bench = frybot_control.offline_bench:main',
        'export_map = frybot_control.store_map:main',
    ]},
)
