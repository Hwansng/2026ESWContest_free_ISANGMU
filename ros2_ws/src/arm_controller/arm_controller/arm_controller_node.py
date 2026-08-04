"""
포즈 테이블 기반으로 '놓기' 동작만 담당하는 축소판 로봇팔 제어 노드.
파지는 arm_act_node가 담당한다.
"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class ArmController(Node):
    def __init__(self):
        super().__init__('arm_controller')

        # ── 구독: mission_orchestrator의 "놓기" 요청만 처리 ──
        self.create_subscription(String, '/arm/place_request', self.place_request_cb, 10)
        self.create_subscription(String, '/arm/servo_feedback', self.feedback_cb, 10)

        self.pub_arm_cmd = self.create_publisher(String, '/arm/command', 10)

        # 관절 안전 한계값 (기존 유지)
        self.joint_limits = {
            1: (0,    4095, 2048),
            2: (170,  1877, 1024),
            3: (0,    2048, 1024),
            4: (0,    2048, 1024),
            5: (0,    2048, 1024),
            6: (340,  1365, 340),
        }

        # 프리셋 포즈 — 파지(GRIP)는 arm_act_node가 담당,
        # 여기는 "놓기" 목적지만 남김 (문서: 정밀 IK 불필요)
        self.poses = {
            'HOME':      [2048, 1024, 1024, 1024, 1024, 340],
            'OVERPACK_DRUM':    [2048, 1200, 800, 1024, 1024, 900],  # 적색 → 오버팩 회수 드럼
            'HAZMAT_STORAGE':   [2048, 700,  1300, 900, 1024, 900],  # 황색 → 위험물 보관함
        }

        self.get_logger().info('Arm Controller(축소판) 노드 시작!')

    def place_request_cb(self, msg: String):
        """mission_orchestrator가 목적지 이름을 보내면 해당 프리셋으로 이동"""
        destination = msg.data.strip()
        self.move_to_pose(destination)

    def feedback_cb(self, msg: String):
        pass  # 필요 시 과열/과부하 감시용으로 확장

    def move_to_pose(self, pose_name: str):
        if pose_name not in self.poses:
            self.get_logger().warn(f'알 수 없는 포즈: {pose_name}')
            return

        positions = self.poses[pose_name]
        validated = []
        for i, pos in enumerate(positions):
            joint = i + 1
            min_p, max_p, _ = self.joint_limits[joint]
            safe_pos = max(min_p, min(max_p, pos))
            validated.append(safe_pos)

        msg = String()
        msg.data = ','.join(str(p) for p in validated)
        self.pub_arm_cmd.publish(msg)
        self.get_logger().info(f'포즈 이동: {pose_name} → {validated}')


def main(args=None):
    rclpy.init(args=args)
    node = ArmController()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
