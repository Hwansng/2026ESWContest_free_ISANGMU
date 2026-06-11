from setuptools import setup

package_name = 'mission_orchestrator'

setup(
    name=package_name,
    version='0.0.1',
    packages=[package_name],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='pi',
    maintainer_email='pi@todo.todo',
    description='Mission Orchestrator FSM Node',
    license='MIT',
    entry_points={
        'console_scripts': [
            'mission_orchestrator_node = mission_orchestrator.mission_orchestrator_node:main',
        ],
    },
)
