"""
카메라를 직접 열어(cv2.VideoCapture) HSV 색상 검출로 물체를 인식하는 비전 노드.
"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Bool
import json, cv2, numpy as np, threading

class VisionNode(Node):
    # 노드 초기화: 토픽 구독/발행 설정
    def __init__(self):
        super().__init__('vision_node')
        self.create_subscription(Bool, '/amr/object_near', self.trigger_cb, 10)
        self.pub_vision = self.create_publisher(String, '/vision/detected', 10)

        self.camera = None
        self.camera_active = False
        self.init_camera()

        self.hsv_ranges = {
            'red': [(np.array([0,120,70]), np.array([10,255,255])),
                    (np.array([170,120,70]), np.array([180,255,255]))],
            'yellow': [(np.array([20,100,100]), np.array([35,255,255]))],
        }
        self.get_logger().info('Vision Node 시작!')

    # cv2.VideoCapture로 카메라를 직접 열기 시도
    def init_camera(self):
        try:
            self.camera = cv2.VideoCapture(0)
            self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            if self.camera.isOpened():
                self.camera_active = True
                self.get_logger().info('카메라 연결 성공!')
            else:
                self.camera = None
                self.get_logger().warn('카메라 없음 - 나중에 연결하세요')
        except Exception as e:
            self.camera = None
            self.get_logger().warn(f'카메라 초기화 실패: {e}')

    # /amr/object_near 콜백: 물체 근접 시 프레임 분석 스레드 시작
    def trigger_cb(self, msg: Bool):
        if msg.data and self.camera_active:
            threading.Thread(target=self.analyze_frame, daemon=True).start()

    # HSV 마스크+컨투어로 색상/방위각/형상 특징 추출 후 발행
    def analyze_frame(self):
        if self.camera is None:
            return
        ret, frame = self.camera.read()
        if not ret:
            return
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
        if node.camera:
            node.camera.release()
        node.destroy_node()
        rclpy.shutdown()
