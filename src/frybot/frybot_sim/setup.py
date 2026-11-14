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
    entry_points={'console_scripts': [
        'cook_arm = frybot_sim.cook_arm_node:main',
        'world = frybot_sim.world_node:main',
        'ai_server = frybot_sim.ai_server:main',
        'customer_ui = frybot_sim.customer_ui_node:main',
        'scenario = frybot_sim.scenario_runner:main',
        'gz_world = frybot_sim.gz_world_gen:main',
        'nav2_watchdog = frybot_sim.nav2_watchdog:main',
    ]},
)
