"""
hazardbot_dashboard 패키지 빌드/설치 설정.
"""
from setuptools import setup
import os
from glob import glob

package_name = 'hazardbot_dashboard'

setup(
    name=package_name,
    version='0.0.1',
    packages=[package_name],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='pi',
    maintainer_email='pi@todo.todo',
    description='HazardBot Web Dashboard',
    license='MIT',
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'templates'), glob('templates/*.html')),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.py')),
    ],
    entry_points={'console_scripts': ['dashboard_node = hazardbot_dashboard.dashboard_node:main']},
)
