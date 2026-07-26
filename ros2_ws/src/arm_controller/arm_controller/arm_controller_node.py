"""
포즈 테이블 기반으로 '놓기' 동작만 담당하는 축소판 로봇팔 제어 노드. 파지는 arm_act_node가 담당한다.
"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import String

class ArmController(Node):
    # 노드 초기화: 토픽 구독/발행 설정
    def __init__(self):
        super().__init__('arm_controller')

        self.create_subscription(String, '/arm/place_request', self.place_request_cb, 10)
        self.create_subscription(String, '/arm/servo_feedback', self.feedback_cb, 10)

        self.pub_arm_cmd = self.create_publisher(String, '/arm/command', 10)

        self.joint_limits = {
            1: (0, 4095, 2048), 2: (170, 1877, 1024), 3: (0, 2048, 1024),
            4: (0, 2048, 1024), 5: (0, 2048, 1024), 6: (340, 1365, 340),
        }

        # 파지(GRIP)는 arm_act_node가 담당, 여기는 "놓기" 목적지만 남김
        self.poses = {
            'HOME':            [2048, 1024, 1024, 1024, 1024, 340],
            'OVERPACK_DRUM':   [2048, 1200, 800, 1024, 1024, 900],
            'HAZMAT_STORAGE':  [2048, 700,  1300, 900, 1024, 900],
        }

        self.get_logger().info('Arm Controller(축소판) 노드 시작!')

    # /arm/place_request 콜백: 목적지 이름으로 포즈 이동
    def place_request_cb(self, msg: String):
        self.move_to_pose(msg.data.strip())

    # /arm/servo_feedback 콜백: 과열/과부하 경고 또는 파지 판정
    def feedback_cb(self, msg: String):
        pass

    # 포즈 테이블에서 이름으로 조회해 관절 한계값 검증 후 이동
    def move_to_pose(self, pose_name: str):
        if pose_name not in self.poses:
            self.get_logger().warn(f'알 수 없는 포즈: {pose_name}')
            return
        positions = self.poses[pose_name]
        validated = []
        for i, pos in enumerate(positions):
            min_p, max_p, _ = self.joint_limits[i + 1]
            validated.append(max(min_p, min(max_p, pos)))
        msg = String(); msg.data = ','.join(str(p) for p in validated)
        self.pub_arm_cmd.publish(msg)
        self.get_logger().info(f'포즈 이동: {pose_name} → {validated}')


# 노드 초기화 후 스핀 시작, 종료 시 안전하게 정리
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
