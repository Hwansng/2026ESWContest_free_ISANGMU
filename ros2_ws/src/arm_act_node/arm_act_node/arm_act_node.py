"""
ACT 정책으로 파지 동작을 추론하는 노드. 정책 미탑재 시 더미 시퀀스로 폴백한다.
"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
import json, threading

class ObjectClass:
    CONTAINMENT_BREACH = "CONTAINMENT_BREACH"
    HANDLE_CARE = "HANDLE_CARE"

COLOR_TO_CLASS = {'red': ObjectClass.CONTAINMENT_BREACH, 'yellow': ObjectClass.HANDLE_CARE}

POLICY_PATHS = {ObjectClass.CONTAINMENT_BREACH: None, ObjectClass.HANDLE_CARE: None}

class ArmActNode(Node):
    # 노드 초기화: 토픽 구독/발행 설정
    def __init__(self):
        super().__init__('arm_act_node')
        self.bridge = CvBridge()
        self.latest_front_frame = None
        self.frame_lock = threading.Lock()

        self.create_subscription(Image, '/camera/image_raw', self.front_image_cb, 10)
        self.create_subscription(String, '/hazard/detected', self.hazard_cb, 10)
        self.create_subscription(String, '/vision/detected', self.vision_cb, 10)
        self.create_subscription(String, '/arm/servo_feedback', self.feedback_cb, 10)
        self.create_subscription(String, '/arm/grip_request', self.grip_request_cb, 10)

        self.pub_arm_cmd = self.create_publisher(String, '/arm/command', 10)
        self.pub_grip_cmd = self.create_publisher(String, '/arm/grip_cmd', 10)

        self.policies = {}
        self.load_policies()
        self.warmup_all()

        self.current_target_class = None
        self.get_logger().info('Arm ACT Node 시작!')

    # /camera/image_raw 콜백: 최신 프레임을 버퍼에 저장
    def front_image_cb(self, msg):
        try:
            frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
            with self.frame_lock:
                self.latest_front_frame = frame
        except Exception as e:
            self.get_logger().warn(f'프론트 이미지 변환 실패: {e}')

    # 물체 분류별 정책 체크포인트를 로드 (없으면 더미 모드)
    def load_policies(self):
        for obj_class, path in POLICY_PATHS.items():
            if path is None:
                self.get_logger().warn(f'{obj_class} 정책 체크포인트 미지정 — 더미 모드로 동작')
                self.policies[obj_class] = None

    # 정책 워밍업 (더미 모드에서는 스킵)
    def warmup_all(self):
        self.get_logger().info('정책 워밍업 단계 (더미 모드 - 스킵)')

    # /hazard/detected 콜백: 위험 등급에 따라 접근 동작 트리거
    def hazard_cb(self, msg: String):
        pass

    # /vision/detected 콜백: 감지 색상/방위각 로그 또는 상태 갱신
    def vision_cb(self, msg: String):
        data = json.loads(msg.data)
        self.current_target_class = COLOR_TO_CLASS.get(data.get('color'))
        self.get_logger().info(f'비전 감지 → 대상 분류: {self.current_target_class}')

    # /arm/grip_request 콜백: 분류 결과에 따라 정책 추론 또는 더미 파지 실행
    def grip_request_cb(self, msg: String):
        obj_class = self.current_target_class
        if obj_class is None:
            self.get_logger().warn('분류 안 된 상태에서 파지 요청 — 스킵')
            return
        policy = self.policies.get(obj_class)
        if policy is None:
            self.get_logger().warn(f'{obj_class} 정책 없음 — 더미 접근/파지 시퀀스로 대체')
            self.run_dummy_grip_sequence(obj_class)

    # /arm/servo_feedback 콜백: 과열/과부하 경고 또는 파지 판정
    def feedback_cb(self, msg: String):
        pass

    # 정책이 없을 때 임시로 GRIP 명령만 전송 (통신 검증용)
    def run_dummy_grip_sequence(self, obj_class):
        threshold = 40 if obj_class == ObjectClass.HANDLE_CARE else 80
        self.pub_grip_cmd.publish(String(data=f'CLOSE,{threshold}'))
        self.get_logger().info(f'[더미] GRIP 명령 전송: threshold={threshold}%')


# 노드 초기화 후 스핀 시작, 종료 시 안전하게 정리
def main(args=None):
    rclpy.init(args=args)
    node = ArmActNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
