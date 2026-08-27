from setuptools import setup

package_name = 'hazard_detector'

setup(
    name=package_name,
    version='0.0.1',
    packages=[package_name],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='pi',
    maintainer_email='pi@todo.todo',
    description='Hazard Detector Node',
    license='MIT',
    entry_points={
        'console_scripts': [
            'hazard_detector_node = hazard_detector.hazard_detector_node:main',
        ],
    },
)
