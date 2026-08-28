# 물체 분류 (색상 기반 파지 대상)
class ObjectClass:
    CONTAINMENT_BREACH = "CONTAINMENT_BREACH"  # 적색 강체, 개방 파손 격리 실패 원인
    HANDLE_CARE = "HANDLE_CARE"                # 황색 변형체, 취급주의 정상 업무

# 구역 식별자, 코드용이라 값은 절대 안 바뀜, 표시 이름만 별도 관리함
class ZoneId:
    ZONE1 = 1       # 표시 이름 일반구역
    ZONE2 = 2       # 표시 이름 취급구역
    ZONE3 = 3       # 표시 이름 위험구역
    JUNCTION = 4    # 분기점, 모듈로 4 순환, 정차 안 함

ZONE_DISPLAY_NAMES = {1: "일반구역", 2: "취급구역", 3: "위험구역", 4: "분기점"}

import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Int8
import json

# 수정: 구역별 임계값 딕셔너리를 완전히 제거하고 단일 임계값으로 대체함
# 판정 로직은 구역을 몰라야 한다는 방향에 맞춰 구역 무관하게 동일 기준 적용함
# 강희가 실측하는 값으로 나중에 교체 필요, 지금은 잠정값임
GAS_THRESHOLD = 300


class HazardDetector(Node):
    def __init__(self):
        super().__init__('hazard_detector')

        # 수정: 죽은 토픽이던 /amr/gas, /amr/temp, /amr/sensors 구독 제거함
        # sensor_bridge가 실제로 발행하는 /env/gas, /env/flame, /env/distance로 전환함
        self.create_subscription(String, '/env/gas',      self.gas_cb,    10)
        self.create_subscription(String, '/env/flame',    self.flame_cb,  10)
        self.create_subscription(String, '/env/distance', self.distance_cb, 10)
        self.create_subscription(String, '/vision/detected', self.vision_cb, 10)
        self.create_subscription(Int8,   '/mission/zone', self.zone_cb,  10)

        # Publishers
        self.pub_hazard = self.create_publisher(String, '/hazard/detected', 10)

        # 상태 저장, zone은 판정에는 안 쓰고 리포트용 컨텍스트로만 유지함
        self.current_zone = 1
        self.gas_data = None
        self.distance_data = None

        self.get_logger().info('Hazard Detector 노드 시작함')

    def zone_cb(self, msg: Int8):
        self.current_zone = msg.data
        self.get_logger().info(f'현재 구역: ZONE {self.current_zone}')

    def gas_cb(self, msg: String):
        # 수정: JSON 파싱 방어 추가함
        try:
            self.gas_data = json.loads(msg.data)
        except (json.JSONDecodeError, TypeError) as e:
            self.get_logger().warn(f'gas_cb 파싱 실패: {e}')
            return
        self.evaluate_hazard()

    def flame_cb(self, msg: String):
        # 수정: 토픽 자체가 /env/flame으로 분리됐으니 콜백명도 flame_cb로 변경함
        try:
            data = json.loads(msg.data)
        except (json.JSONDecodeError, TypeError) as e:
            self.get_logger().warn(f'flame_cb 파싱 실패: {e}')
            return

        if data.get('flame') == 1:
            self.publish_hazard(3, 'FLAME', 'KY-026 화염 감지')

    def distance_cb(self, msg: String):
        # 수정: 로깅만 하던 걸 상태 저장으로 바꿈, 판정에는 아직 미반영임
        # 근접 위험 판정에 쓸지는 §5.5-B 트리거 소스 확정 이후 진행 필요
        try:
            self.distance_data = json.loads(msg.data)
        except (json.JSONDecodeError, TypeError) as e:
            self.get_logger().warn(f'distance_cb 파싱 실패: {e}')

    def vision_cb(self, msg: String):
        try:
            data = json.loads(msg.data)
        except (json.JSONDecodeError, TypeError) as e:
            self.get_logger().warn(f'vision_cb 파싱 실패: {e}')
            return
        self.get_logger().info(
            f'비전 감지: 색상={data.get("color")} '
            f'방위각={data.get("angle")} '
            f'종횡비={data.get("aspect_ratio")}'
        )

    def evaluate_hazard(self):
        if not self.gas_data:
            return

        zone  = self.current_zone
        mq2   = self.gas_data.get('mq2', 0)
        mq135 = self.gas_data.get('mq135', 0)

        # 수정: 구역별 임계값 조회 제거함, 단일 GAS_THRESHOLD로 판정함
        level = 0
        reason = 'NORMAL'

        if mq2 > GAS_THRESHOLD or mq135 > GAS_THRESHOLD:
            level = 2
            reason = f'가스 초과 (임계값 {GAS_THRESHOLD})'
        elif mq2 > GAS_THRESHOLD * 0.7 or mq135 > GAS_THRESHOLD * 0.7:
            level = 1
            reason = '주의 수준'
        else:
            level = 0
            reason = 'NORMAL'

        self.publish_hazard(level, reason, f'MQ2={mq2} MQ135={mq135} ZONE={zone}')

    def publish_hazard(self, level: int, hazard_type: str, detail: str):
        data = {
            'level':  level,
            'type':   hazard_type,
            'detail': detail,
            'zone':   self.current_zone
        }
        msg = String()
        msg.data = json.dumps(data)
        self.pub_hazard.publish(msg)
        self.get_logger().info(f'위험등급 L{level}: {hazard_type} | {detail}')


def main(args=None):
    rclpy.init(args=args)
    node = HazardDetector()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()