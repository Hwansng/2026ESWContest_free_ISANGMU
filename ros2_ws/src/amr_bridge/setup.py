from setuptools import setup

package_name = 'amr_bridge'

setup(
    name=package_name,
    version='0.0.1',
    packages=[package_name],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='pi',
    maintainer_email='pi@todo.todo',
    description='AMR ESP32 #1 TCP Bridge',
    license='MIT',
    entry_points={
        'console_scripts': [
            'amr_bridge_node = amr_bridge.amr_bridge_node:main',
        ],
    },
)
