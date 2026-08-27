from setuptools import setup

package_name = 'arm_act_node'

setup(
    name=package_name,
    version='0.0.1',
    packages=[package_name],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='pi',
    maintainer_email='pi@todo.todo',
    description='ACT Policy Inference Node',
    license='MIT',
    entry_points={
        'console_scripts': [
            'arm_act_node = arm_act_node.arm_act_node:main',
        ],
    },
)
