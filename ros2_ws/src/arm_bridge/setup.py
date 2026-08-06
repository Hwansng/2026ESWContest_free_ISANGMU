from setuptools import setup

package_name = 'arm_bridge'

setup(
    name=package_name,
    version='0.0.1',
    packages=[package_name],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='pi',
    maintainer_email='pi@todo.todo',
    description='ARM ESP32 #2 TCP Bridge',
    license='MIT',
    entry_points={
        'console_scripts': [
            'arm_bridge_node = arm_bridge.arm_bridge_node:main',
        ],
    },
)
