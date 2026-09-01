"""
형상 특징(원형도·채움률)과 ROI 제한, 색·형상 불일치 시 소프트 폴백을 추가한 비전 노드.
"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Bool
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
import json
import cv2
import numpy as np
import threading

# ══════════════════════════════════════════════
# 물체 분류 (색상 기반) — arm_act_node와 동일 규칙 공유
# ══════════════════════════════════════════════
class ObjectClass:
    CONTAINMENT_BREACH = "CONTAINMENT_BREACH"
    HANDLE_CARE = "HANDLE_CARE"

COLOR_TO_CLASS = {
    'red': ObjectClass.CONTAINMENT_BREACH,
    'yellow': ObjectClass.HANDLE_CARE,
}

# 형상 기대값, 실물 조달 후 재조정 필요, 지금은 임시값
EXPECTED_SHAPE = {
    'red':    {'circularity_min': 0.0, 'circularity_max': 1.0},
    'yellow': {'circularity_min': 0.0, 'circularity_max': 1.0},
}


class VisionNode(Node):
    def __init__(self):
        super().__init__('vision_node')

        self.bridge = CvBridge()
        self.latest_frame = None
        self.frame_lock = threading.Lock()

        self.create_subscription(Image, '/camera/image_raw', self.image_cb, 10)
        self.create_subscription(Bool, '/amr/object_near', self.trigger_cb, 10)

        self.pub_vision = self.create_publisher(String, '/vision/detected', 10)

        # 수정: hsv_separation_test.py로 실측한 값으로 교체함
        # NoIR 카메라는 IR 차단 필터가 없어서 색이 밀리는 현상이 실제로 나타남
        # 빨강이 일반적인 0-10/170-180 구간이 아니라 138-156(자주색 쪽)으로 완전히 이동함
        # 겹침 판정 결과 H 채널 겹침 0.00으로 완전 분리 확인됨, 여유 마진 살짝 넣어서 반영함
        self.hsv_ranges = {
            'red': [
                (np.array([133, 100, 60]), np.array([161, 255, 255])),
            ],
            'yellow': [
                (np.array([3, 30, 100]), np.array([31, 255, 255])),
            ],
        }

        # 프론트 카메라 ROI, 작업공간 높이로 제한해서 바닥 오검출 차단
        # 값은 실제 카메라 마운트 위치 확정 후 재조정 필요
        self.roi_y_start_ratio = 0.3
        self.roi_y_end_ratio = 0.8

        self.get_logger().info('Vision Node 시작함, /camera/image_raw 구독중')

    def image_cb(self, msg):
        try:
            frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
            with self.frame_lock:
                self.latest_frame = frame
        except Exception as e:
            self.get_logger().warn(f'이미지 변환 실패: {e}')

    def trigger_cb(self, msg: Bool):
        if msg.data:
            with self.frame_lock:
                frame = self.latest_frame.copy() if self.latest_frame is not None else None
            if frame is not None:
                threading.Thread(
                    target=self.analyze_frame, args=(frame,), daemon=True
                ).start()

    def apply_roi(self, frame):
        h, w = frame.shape[:2]
        y1 = int(h * self.roi_y_start_ratio)
        y2 = int(h * self.roi_y_end_ratio)
        return frame[y1:y2, :], y1

    def analyze_frame(self, frame):
        roi_frame, y_offset = self.apply_roi(frame)
        hsv = cv2.cvtColor(roi_frame, cv2.COLOR_BGR2HSV)

        best_result = None
        best_area = 0

        for color_name, ranges in self.hsv_ranges.items():
            mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
            for (lower, upper) in ranges:
                mask |= cv2.inRange(hsv, lower, upper)

            kernel = np.ones((5, 5), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

            contours, _ = cv2.findContours(
                mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            if not contours:
                continue

            largest = max(contours, key=cv2.contourArea)
            area = cv2.contourArea(largest)
            if area < 1000:
                continue

            if area > best_area:
                best_area = area
                rect = cv2.minAreaRect(largest)
                center = rect[0]
                size = rect[1]
                angle = rect[2]

                w_box, h_box = size
                if w_box < h_box:
                    angle = angle + 90
                angle = abs(angle)

                aspect_ratio = round(max(w_box, h_box) / min(w_box, h_box), 2) if min(w_box, h_box) > 0 else 1.0

                perimeter = cv2.arcLength(largest, True)
                fill_ratio = round(area / (w_box * h_box), 2) if (w_box * h_box) > 0 else 0.0
                circularity = round(
                    (4 * np.pi * area) / (perimeter ** 2), 2
                ) if perimeter > 0 else 0.0

                object_class = COLOR_TO_CLASS.get(color_name)

                shape_ok = self.check_shape_consistency(color_name, circularity)
                mode = 'NORMAL' if shape_ok else 'SOFT_FALLBACK'

                best_result = {
                    'color': color_name,
                    'object_class': object_class,
                    'angle': round(angle, 1),
                    'aspect_ratio': aspect_ratio,
                    'area': int(area),
                    'fill_ratio': fill_ratio,
                    'circularity': circularity,
                    'mode': mode,
                    'center_x': round(center[0], 1),
                    'center_y': round(center[1] + y_offset, 1),
                }

        if best_result:
            msg = String()
            msg.data = json.dumps(best_result)
            self.pub_vision.publish(msg)
            self.get_logger().info(
                f'감지: {best_result["color"]} ({best_result["object_class"]}) '
                f'각도={best_result["angle"]}도 원형도={best_result["circularity"]} '
                f'모드={best_result["mode"]}'
            )
        else:
            self.get_logger().debug('감지된 물체 없음')

    def check_shape_consistency(self, color_name, circularity):
        """색상 기대 형상과 실측 형상이 크게 어긋나면 소프트 모드로 폴백함
        임계값은 실물 조달 후 재조정 필요, 지금은 항상 통과하도록 관대하게 설정함"""
        expected = EXPECTED_SHAPE.get(color_name)
        if not expected:
            return True
        return expected['circularity_min'] <= circularity <= expected['circularity_max']


def main(args=None):
    rclpy.init(args=args)
    node = VisionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()