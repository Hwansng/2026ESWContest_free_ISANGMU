from setuptools import setup

package_name = 'sensor_bridge'

setup(
    name=package_name,
    version='0.0.1',
    packages=[package_name],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='pi',
    maintainer_email='pi@todo.todo',
    description='ENV Board TCP Bridge',
    license='MIT',
    entry_points={
        'console_scripts': [
            'sensor_bridge_node = sensor_bridge.sensor_bridge_node:main',
        ],
    },
)
