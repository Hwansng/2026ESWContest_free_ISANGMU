"""
전체 ROS2 노드를 한 번에 실행하는 launch 설정.
"""
from launch import LaunchDescription
from launch_ros.actions import Node

# 전체 노드를 한 번에 실행하는 launch 구성 반환
def generate_launch_description():
    return LaunchDescription([
        Node(package='amr_bridge',          executable='amr_bridge_node'),
        Node(package='arm_bridge',          executable='arm_bridge_node'),
        Node(package='hazard_detector',     executable='hazard_detector_node'),
        Node(package='arm_controller',      executable='arm_controller_node'),
        Node(package='mission_orchestrator',executable='mission_orchestrator_node'),
        Node(package='hazardbot_dashboard', executable='dashboard_node'),
    ])
