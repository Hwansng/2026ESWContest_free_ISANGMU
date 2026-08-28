"""
[레거시 — 현재 사용 안 함]
초기 개발 단계 테스트 도구임. /amr/object_near를 주기적으로 True 발행함.
지금은 ros2 topic pub 직접 실행으로 같은 걸 하고 있어서 (mock_env_board.py 등),
이 노드는 굳이 따로 안 씀. 필요하면 재사용 가능하지만 현재 워크플로에는 없음.
"""
"""테스트용 가짜 트리거 노드.

실제 AMR(ESP32 #1)이 없어도 vision_node를 단독 검증할 수 있도록
/amr/object_near(Bool)에 주기적으로 True를 발행한다.
"""
from __future__ import annotations

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from std_msgs.msg import Bool


class MockAmrPublisher(Node):
    def __init__(self) -> None:
        super().__init__("mock_amr_publisher")
        self.declare_parameter("period_sec", 2.0)
        period = float(self.get_parameter("period_sec").value)
        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)
        self._pub = self.create_publisher(Bool, "/amr/object_near", qos)
        self._timer = self.create_timer(period, self._tick)
        self.get_logger().info(f"mock 트리거 발행 시작 (주기 {period}s)")

    def _tick(self) -> None:
        msg = Bool()
        msg.data = True
        self._pub.publish(msg)
        self.get_logger().info("/amr/object_near = True 발행")


def main(args=None) -> None:
    rclpy.init(args=args)
    node = MockAmrPublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()