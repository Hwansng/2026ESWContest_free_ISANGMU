"""
목표 좌표를 기하학적 IK로 계산해 6축 서보 각도를 산출하는 로봇팔 제어 노드.
"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Int16
import json, math

class ArmController(Node):
    # 노드 초기화: 토픽 구독/발행 설정
    def __init__(self):
        super().__init__('arm_controller')

        self.create_subscription(String, '/hazard/detected',   self.hazard_cb,   10)
        self.create_subscription(String, '/arm/servo_feedback',self.feedback_cb, 10)
        self.create_subscription(Int16,  '/arm/wrist_preset',  self.wrist_cb,    10)

        self.pub_arm_cmd = self.create_publisher(String, '/arm/command', 10)

        self.joint_limits = {
            1: (0, 4095, 2048), 2: (170, 1877, 1024), 3: (0, 2048, 1024),
            4: (0, 2048, 1024), 5: (0, 2048, 1024), 6: (340, 1365, 340),
        }

        self.poses = {
            'HOME':      [2048, 1024, 1024, 1024, 1024, 340],
            'READY':     [2048, 800,  1200, 900,  1024, 340],
            'APPROACH':  [2048, 600,  1400, 800,  1024, 340],
            'GRIP_OPEN': [2048, 600,  1400, 800,  1024, 340],
            'GRIP_CLOSE':[2048, 600,  1400, 800,  1024, 900],
            'TRANSPORT': [2048, 1200, 800,  1024, 1024, 900],
            'ISOLATE':   [2048, 700,  1300, 900,  1024, 900],
        }

        # 링크 길이(mm, 추정치)
        self.L1, self.L2, self.L3, self.L4 = 0, 100, 100, 80

        self.get_logger().info('Arm Controller 노드 시작!')

    # /hazard/detected 콜백: 위험 등급에 따라 접근 동작 트리거
    def hazard_cb(self, msg: String):
        data = json.loads(msg.data)
        if data.get('level', 0) >= 2:
            self.move_to_pose('APPROACH')

    # /arm/servo_feedback 콜백: 과열/과부하 경고 또는 파지 판정
    def feedback_cb(self, msg: String):
        data = json.loads(msg.data)
        if data.get('temp', 0) > 70:
            self.get_logger().warn(f'서보 {data.get("id")} 과열! {data.get("temp")}°C')
        if data.get('load', 0) > 80:
            self.get_logger().warn(f'서보 {data.get("id")} 과부하! {data.get("load")}%')

    # /arm/wrist_preset 콜백: 손목 각도를 위치값으로 변환해 반영
    def wrist_cb(self, msg: Int16):
        pos = max(0, min(2048, int(msg.data / 180.0 * 2048)))
        poses = self.poses['APPROACH'].copy()
        poses[4] = pos
        self.publish_arm_command(poses)

    # 목표 좌표(x,y,z)를 코사인 법칙 기반으로 6축 각도로 역산
    def solve_ik(self, x, y, z, wrist_angle=90):
        """기하학적 IK: (x,y,z) -> 6축 각도 (코사인 법칙)"""
        base_angle = max(0, min(360, math.degrees(math.atan2(y, x)) + 180))
        r = math.sqrt(x**2 + y**2)
        d = math.sqrt(r**2 + (z - self.L1)**2)
        max_reach = self.L2 + self.L3
        if d > max_reach:
            d = max_reach * 0.95
        try:
            cos_elbow = max(-1, min(1, (self.L2**2 + self.L3**2 - d**2) / (2*self.L2*self.L3)))
            elbow_angle = math.degrees(math.acos(cos_elbow))
            cos_shoulder = max(-1, min(1, (self.L2**2 + d**2 - self.L3**2) / (2*self.L2*d)))
            shoulder_offset = math.degrees(math.acos(cos_shoulder))
            elevation = math.degrees(math.atan2(z - self.L1, r))
            shoulder_angle = elevation + shoulder_offset
        except (ValueError, ZeroDivisionError):
            return None
        wrist_pitch = 180 - shoulder_angle - elbow_angle
        angles = [base_angle, shoulder_angle, elbow_angle, wrist_pitch, wrist_angle, 30]
        return [max(0, min(4095, int(a / 360.0 * 4095))) for a in angles]

    # 포즈 테이블에서 이름으로 조회해 관절 한계값 검증 후 이동
    def move_to_pose(self, pose_name: str):
        if pose_name not in self.poses:
            return
        positions = self.poses[pose_name]
        validated = []
        for i, pos in enumerate(positions):
            min_p, max_p, _ = self.joint_limits[i + 1]
            validated.append(max(min_p, min(max_p, pos)))
        self.publish_arm_command(validated)

    # 6축 위치값을 문자열로 합쳐 /arm/command로 발행
    def publish_arm_command(self, positions: list):
        msg = String(); msg.data = ','.join(str(p) for p in positions)
        self.pub_arm_cmd.publish(msg)


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
        rclpy.shutdown()
