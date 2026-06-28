"""
camera_ros가 카메라를 점유하므로 /camera/image_raw 토픽을 구독하는 방식으로 전환된 비전 노드.
"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Bool
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
import json, cv2, numpy as np, threading

class VisionNode(Node):
    # 노드 초기화: 토픽 구독/발행 설정
    def __init__(self):
        super().__init__('vision_node')

        self.bridge = CvBridge()
        self.latest_frame = None
        self.frame_lock = threading.Lock()

        self.create_subscription(Image, '/camera/image_raw', self.image_cb, 10)
        self.create_subscription(Bool, '/amr/object_near', self.trigger_cb, 10)
        self.pub_vision = self.create_publisher(String, '/vision/detected', 10)

        self.hsv_ranges = {
            'red': [(np.array([0,120,70]), np.array([10,255,255])),
                    (np.array([170,120,70]), np.array([180,255,255]))],
            'yellow': [(np.array([20,100,100]), np.array([35,255,255]))],
        }
        self.get_logger().info('Vision Node 시작! (/camera/image_raw 구독 중)')

    # /camera/image_raw 콜백: ROS Image를 OpenCV 배열로 변환해 저장
    def image_cb(self, msg: Image):
        try:
            frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
            with self.frame_lock:
                self.latest_frame = frame
        except Exception as e:
            self.get_logger().warn(f'이미지 변환 실패: {e}')

    # /amr/object_near 콜백: 물체 근접 시 프레임 분석 스레드 시작
    def trigger_cb(self, msg: Bool):
        if msg.data:
            with self.frame_lock:
                frame = self.latest_frame.copy() if self.latest_frame is not None else None
            if frame is not None:
                threading.Thread(target=self.analyze_frame, args=(frame,), daemon=True).start()

    # HSV 마스크+컨투어로 색상/방위각/형상 특징 추출 후 발행
    def analyze_frame(self, frame):
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        best_result, best_area = None, 0
        for color_name, ranges in self.hsv_ranges.items():
            mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
            for lower, upper in ranges:
                mask |= cv2.inRange(hsv, lower, upper)
            kernel = np.ones((5,5), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not contours:
                continue
            largest = max(contours, key=cv2.contourArea)
            area = cv2.contourArea(largest)
            if area < 1000 or area <= best_area:
                continue
            best_area = area
            rect = cv2.minAreaRect(largest)
            center, size, angle = rect
            w, h = size
            if w < h:
                angle += 90
            angle = abs(angle)
            aspect_ratio = round(max(w,h)/min(w,h), 2) if min(w,h) > 0 else 1.0
            best_result = {'color': color_name, 'angle': round(angle,1),
                            'aspect_ratio': aspect_ratio, 'area': int(area)}
        if best_result:
            msg = String(); msg.data = json.dumps(best_result)
            self.pub_vision.publish(msg)
            self.get_logger().info(f'감지: {best_result["color"]} 각도={best_result["angle"]}°')


# 노드 초기화 후 스핀 시작, 종료 시 안전하게 정리
def main(args=None):
    rclpy.init(args=args)
    node = VisionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
