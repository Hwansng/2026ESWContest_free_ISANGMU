from setuptools import setup

package_name = 'arm_controller'

setup(
    name=package_name,
    version='0.0.1',
    packages=[package_name],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='pi',
    maintainer_email='pi@todo.todo',
    description='Arm Controller Node',
    license='MIT',
    entry_points={
        'console_scripts': [
            'arm_controller_node = arm_controller.arm_controller_node:main',
        ],
    },
)
