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
        self.declare_parameter("period_sec", 2.0)   # 트리거 발행 주기[s]
        period = float(self.get_parameter("period_sec").value)
        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)
        self._pub = self.create_publisher(Bool, "/amr/object_near", qos)
        self._timer = self.create_timer(period, self._tick)
        self.get_logger().info(f"mock 트리거 발행 시작 (주기 {period}s)")

    def _tick(self) -> None:
        msg = Bool()
        msg.data = True             # 물체 접근 가정
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
