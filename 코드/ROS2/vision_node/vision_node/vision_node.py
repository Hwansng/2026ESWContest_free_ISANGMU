"""HazardBot 비전 노드 (ROS2 Jazzy).

/amr/object_near(Bool) 트리거가 True일 때 카메라 프레임을 캡처하고,
detector로 위험물을 검출해 /vision/detected(String, <VISION,...,CS>)로 퍼블리시한다.
PC(웹캠) 단독 개발 후 RPi(picamera2)로 카메라 소스만 교체해 통합한다.
"""
from __future__ import annotations

import os

import rclpy
import yaml
from ament_index_python.packages import get_package_share_directory
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from std_msgs.msg import Bool, String

from vision_node import detector as det
from vision_node.camera_source import create_camera
from vision_node.protocol import build_message


class VisionNode(Node):
    def __init__(self) -> None:
        super().__init__("vision_node")

        # 파라미터: 카메라 소스(webcam/picamera2), HSV 설정 파일 경로
        self.declare_parameter("camera_source", "webcam")
        self.declare_parameter("config_path", "")
        source = self.get_parameter("camera_source").value
        cfg_path = self.get_parameter("config_path").value or self._default_cfg()
        self._cfg = self._load_cfg(cfg_path)

        # 카메라 캡처 소스 생성 (소스만 교체하면 PC/RPi 공용)
        self._camera = create_camera(source)

        # QoS 명시: 단발성 트리거이므로 신뢰성(RELIABLE) 사용
        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)
        self._pub = self.create_publisher(String, "/vision/detected", qos)
        self._sub = self.create_subscription(
            Bool, "/amr/object_near", self._on_trigger, qos)

        self.get_logger().info(f"vision_node 시작 (source={source})")

    def _default_cfg(self) -> str:
        """설치된 share 디렉터리의 기본 HSV 설정 경로."""
        share = get_package_share_directory("vision_node")
        return os.path.join(share, "config", "hsv_calibration.yaml")

    def _load_cfg(self, path: str) -> dict:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _on_trigger(self, msg: Bool) -> None:
        """object_near=True일 때만 1회 캡처 -> 검출 -> 퍼블리시."""
        if not msg.data:
            return
        frame = self._camera.read()
        if frame is None:
            self.get_logger().warn("프레임 캡처 실패")
            return
        detections = det.detect(frame, self._cfg)
        if not detections:
            return
        # 가장 큰(면적 기준) 물체 1건만 전송
        target = max(detections, key=lambda d: d.width * d.height)
        wrist = det.angle_to_wrist_roll(target.angle)
        # 페이로드: color:cx:cy:w:h:angle:asym
        value = (f"{target.color}:{target.cx}:{target.cy}:"
                 f"{target.width}:{target.height}:{wrist}:"
                 f"{int(target.asymmetric)}")
        out = String()
        out.data = build_message("VISION", value)  # <VISION,...,CS>
        self._pub.publish(out)
        self.get_logger().info(f"검출 발행: {out.data}")

    def destroy_node(self) -> bool:
        self._camera.release()
        return super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = VisionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
