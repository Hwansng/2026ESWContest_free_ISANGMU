"""테스트용 더미 구독 노드.

/vision/detected(String)를 구독해 <VISION,...,CS> 메시지의 체크섬을 검증하고
필드를 파싱해 사람이 읽기 좋게 출력한다(vision_node 단독 검증용).
"""
from __future__ import annotations

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from std_msgs.msg import String

from vision_node.protocol import parse_message


class DummySubscriber(Node):
    def __init__(self) -> None:
        super().__init__("dummy_subscriber")
        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)
        self._sub = self.create_subscription(
            String, "/vision/detected", self._on_msg, qos)
        self.get_logger().info("dummy_subscriber 시작 - /vision/detected 대기")

    def _on_msg(self, msg: String) -> None:
        parsed = parse_message(msg.data)
        if parsed is None:
            self.get_logger().error(f"체크섬/형식 오류: {msg.data}")
            return
        cmd, value = parsed
        fields = value.split(":")           # color:cx:cy:w:h:angle:asym
        if cmd != "VISION" or len(fields) != 7:
            self.get_logger().warn(f"예상치 못한 메시지: {msg.data}")
            return
        color, cx, cy, w, h, angle, asym = fields
        self.get_logger().info(
            f"[검출] 색상={color} 중심=({cx},{cy}) 크기=({w}x{h}) "
            f"방위각={angle} 비대칭={'예' if asym == '1' else '아니오'}")


def main(args=None) -> None:
    rclpy.init(args=args)
    node = DummySubscriber()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
