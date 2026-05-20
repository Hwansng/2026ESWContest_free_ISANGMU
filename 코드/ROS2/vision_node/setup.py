"""vision_node ament_python 패키지 설치 정의.

console_scripts로 3개 실행 노드(vision_node, mock_amr_publisher,
dummy_subscriber)를 등록하고, config의 HSV 설정 파일을 share에 설치한다.
"""
from setuptools import find_packages, setup

package_name = 'vision_node'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        # ament 패키지 인덱스 마커
        ('share/ament_index/resource_index/packages',
         ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        # HSV 캘리브레이션 파일을 share/vision_node/config에 설치
        ('share/' + package_name + '/config', ['config/hsv_calibration.yaml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='seunghwan',
    maintainer_email='snghwan68@gmail.com',
    description='HazardBot 비전 노드 (HSV 색상 분류 + minAreaRect 방위각)',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'vision_node = vision_node.vision_node:main',
            'mock_amr_publisher = vision_node.mock_amr_publisher:main',
            'dummy_subscriber = vision_node.dummy_subscriber:main',
        ],
    },
)
