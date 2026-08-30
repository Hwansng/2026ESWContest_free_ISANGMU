"""
2026-08-30 — 파지 제외 순찰 시연용(라인추종+마커+색/가스 판정+화염 후진) 축소 launch.

hazardbot.launch.py에서 팔 관련 노드(arm_bridge/arm_controller/arm_act_node)와
mission_orchestrator(파지 FSM 전용, 하트비트 발행원 겸)를 뺐다.
mission_orchestrator가 없으면 하트비트를 아무도 안 보내 DRIVE가 RPI_TIMEOUT으로
서버리는데, amr_bridge_node.py가 2026-08-30부터 자체 HB도 같이 보내도록 바뀌어서
이 launch만으로 충분하다(추가 heartbeat 퍼블리셔 불필요).
"""
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        Node(package='camera_ros',          executable='camera_node'),
        Node(package='amr_bridge',          executable='amr_bridge_node'),
        Node(package='sensor_bridge',       executable='sensor_bridge_node'),
        Node(package='hazard_detector',     executable='hazard_detector_node'),
        Node(package='vision_node',         executable='vision_node'),
        Node(package='hazardbot_dashboard', executable='dashboard_node'),
    ])
