"""
ACT 정책으로 파지 동작을 추론하는 노드. 정책 미탑재 시 더미 시퀀스로 폴백한다.
"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
import json
import threading

# ══════════════════════════════════════════════
# 물체 분류 (색상 기반) — 문서 §2-6 개명 규칙
# ══════════════════════════════════════════════
class ObjectClass:
    CONTAINMENT_BREACH = "CONTAINMENT_BREACH"  # 적색 강체
    HANDLE_CARE = "HANDLE_CARE"                # 황색 변형체


COLOR_TO_CLASS = {
    'red': ObjectClass.CONTAINMENT_BREACH,
    'yellow': ObjectClass.HANDLE_CARE,
}

# 정책 파일 경로 (학습 완료 후 채워질 자리)
POLICY_PATHS = {
    ObjectClass.CONTAINMENT_BREACH: None,  # TODO: 적색용 체크포인트 경로
    ObjectClass.HANDLE_CARE: None,         # TODO: 황색용 체크포인트 경로
}


class ArmActNode(Node):
    def __init__(self):
        super().__init__('arm_act_node')
        self.bridge = CvBridge()

        # ── 카메라 구독 (손목 카메라는 아직 미장착 — 프론트만 우선 연결) ──
        self.latest_front_frame = None
        self.latest_wrist_frame = None
        self.frame_lock = threading.Lock()

        self.create_subscription(Image, '/camera/image_raw', self.front_image_cb, 10)
        # TODO: 손목 카메라 장착 후 아래 구독 추가
        # self.create_subscription(Image, '/camera/wrist/image_raw', self.wrist_image_cb, 10)

        # ── 미션 신호 구독 ──
        self.create_subscription(String, '/hazard/detected', self.hazard_cb, 10)
        self.create_subscription(String, '/vision/detected', self.vision_cb, 10)
        self.create_subscription(String, '/arm/servo_feedback', self.feedback_cb, 10)
        self.create_subscription(String, '/arm/grip_request', self.grip_request_cb, 10)

        # ── arm_bridge로 명령 발행 (기존 arm_controller와 동일 채널 재사용) ──
        self.pub_arm_cmd = self.create_publisher(String, '/arm/command', 10)
        self.pub_grip_cmd = self.create_publisher(String, '/arm/grip_cmd', 10)

        # ── 정책 2개 로드 (문서: 미션 시작 전 워밍업 필수) ──
        self.policies = {}
        self.load_policies()
        self.warmup_all()

        self.current_target_class = None
        self.get_logger().info('Arm ACT Node 시작!')

    # ════════════════════════════════════════════
    # 카메라 콜백
    # ════════════════════════════════════════════
    def front_image_cb(self, msg):
        try:
            frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
            with self.frame_lock:
                self.latest_front_frame = frame
        except Exception as e:
            self.get_logger().warn(f'프론트 이미지 변환 실패: {e}')

    def wrist_image_cb(self, msg):
        try:
            frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
            with self.frame_lock:
                self.latest_wrist_frame = frame
        except Exception as e:
            self.get_logger().warn(f'손목 이미지 변환 실패: {e}')

    # ════════════════════════════════════════════
    # 정책 로드 / 워밍업
    # ════════════════════════════════════════════
    def load_policies(self):
        for obj_class, path in POLICY_PATHS.items():
            if path is None:
                self.get_logger().warn(
                    f'{obj_class} 정책 체크포인트 미지정 — 더미 모드로 동작'
                )
                self.policies[obj_class] = None
                continue
            # TODO: 실제 체크포인트 준비되면 여기서 ACTPolicy.from_pretrained(path) 로드
            self.policies[obj_class] = None

    def warmup_all(self):
        # TODO: 실제 정책 로드 후, 각 정책에 대해 더미 입력으로 1회 추론해 워밍업
        # (문서 §5: 미션 시작 전 워밍업 안 하면 첫 파지에서만 지연이 튄다)
        self.get_logger().info('정책 워밍업 단계 (더미 모드 - 스킵)')

    # ════════════════════════════════════════════
    # 미션 신호 콜백
    # ════════════════════════════════════════════
    def hazard_cb(self, msg: String):
        pass  # 필요 시 위험등급에 따른 추가 로직

    def vision_cb(self, msg: String):
        data = json.loads(msg.data)
        color = data.get('color')
        self.current_target_class = COLOR_TO_CLASS.get(color)
        self.get_logger().info(
            f'비전 감지 → 대상 분류: {self.current_target_class}'
        )

    def grip_request_cb(self, msg: String):
        # mission_orchestrator가 GRIP 상태 진입 시 호출
        obj_class = self.current_target_class
        if obj_class is None:
            self.get_logger().warn('분류 안 된 상태에서 파지 요청 — 스킵')
            return

        policy = self.policies.get(obj_class)
        if policy is None:
            self.get_logger().warn(
                f'{obj_class} 정책 없음 — 더미 접근/파지 시퀀스로 대체'
            )
            self.run_dummy_grip_sequence(obj_class)
            return

        # TODO: 실제 정책 추론 루프
        # obs = self.build_observation()
        # action_chunk = policy.select_action(obs)
        # self.publish_action(action_chunk)

    def feedback_cb(self, msg: String):
        pass  # 파지 성공/실패 판정은 mission_orchestrator가 계속 담당

    # ════════════════════════════════════════════
    # 더미 폴백 (정책 없을 때 임시 동작 — 실제 파지는 안 됨, 통신 검증용)
    # ════════════════════════════════════════════
    def run_dummy_grip_sequence(self, obj_class):
        threshold = 40 if obj_class == ObjectClass.HANDLE_CARE else 80
        grip_msg = String()
        grip_msg.data = f'CLOSE,{threshold}'
        self.pub_grip_cmd.publish(grip_msg)
        self.get_logger().info(f'[더미] GRIP 명령 전송: threshold={threshold}%')


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
