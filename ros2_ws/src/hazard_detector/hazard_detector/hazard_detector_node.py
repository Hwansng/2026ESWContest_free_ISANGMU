"""
센서/비전 데이터를 구역별 임계값과 비교해 위험 등급(L0~L3)을 판정하는 노드.
"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Int8
import json

class HazardDetector(Node):
    # 노드 초기화: 토픽 구독/발행 설정
    def __init__(self):
        super().__init__('hazard_detector')

        self.create_subscription(String, '/amr/gas',     self.gas_cb,    10)
        self.create_subscription(String, '/amr/temp',    self.temp_cb,   10)
        self.create_subscription(String, '/amr/sensors', self.sensor_cb, 10)
        self.create_subscription(String, '/vision/detected', self.vision_cb, 10)
        self.create_subscription(Int8,   '/mission/zone', self.zone_cb,  10)

        self.pub_hazard = self.create_publisher(String, '/hazard/detected', 10)

        self.current_zone = 1
        self.gas_data  = None
        self.temp_data = None

        self.zone_thresholds = {
            1: {'gas': 300, 'temp': 60},
            2: {'gas': 200, 'temp': 50},
            3: {'gas': 150, 'temp': 45},
        }

        self.get_logger().info('Hazard Detector 노드 시작!')

    # /mission/zone 콜백: 현재 구역 갱신
    def zone_cb(self, msg: Int8):
        self.current_zone = msg.data

    # /amr/gas 콜백: 가스 데이터 저장 후 위험도 재평가
    def gas_cb(self, msg: String):
        self.gas_data = json.loads(msg.data)
        self.evaluate_hazard()

    # /amr/temp 콜백: 온도/화염 데이터 처리, 화염이면 즉시 L3 발행
    def temp_cb(self, msg: String):
        self.temp_data = json.loads(msg.data)
        if self.temp_data.get('flame') == 1:
            self.publish_hazard(3, 'FLAME', 'KY-026 화염 감지')
            return
        self.evaluate_hazard()

    # /amr/sensors 콜백 (현재는 별도 처리 없음)
    def sensor_cb(self, msg: String):
        pass

    # /vision/detected 콜백: 감지 색상/방위각 로그 또는 상태 갱신
    def vision_cb(self, msg: String):
        data = json.loads(msg.data)
        self.get_logger().info(f'비전 감지: 색상={data.get("color")} 방위각={data.get("angle")}')

    # 가스/온도 값을 구역별 임계값과 비교해 위험 등급 판정
    def evaluate_hazard(self):
        if not self.gas_data or not self.temp_data:
            return

        zone = self.current_zone
        mq2, mq135 = self.gas_data.get('mq2', 0), self.gas_data.get('mq135', 0)
        temp = self.temp_data.get('temp', 0)
        flag = self.gas_data.get('flag', 'NORMAL')

        threshold = self.zone_thresholds.get(zone, self.zone_thresholds[1])
        gas_limit, temp_limit = threshold['gas'], threshold['temp']

        level, reason = 0, 'NORMAL'
        if flag == 'HIGH' and temp > temp_limit:
            level, reason = 3, '가스+고온 복합 위험'
        elif mq2 > gas_limit or mq135 > gas_limit:
            level, reason = 2, f'가스 초과 (ZONE {zone} 임계값 {gas_limit})'
        elif temp > temp_limit:
            level, reason = 2, f'온도 초과 ({temp}°C)'
        elif mq2 > gas_limit * 0.7 or temp > temp_limit * 0.8:
            level, reason = 1, '주의 수준'

        self.publish_hazard(level, reason, f'MQ2={mq2} MQ135={mq135} TEMP={temp}°C ZONE={zone}')

    # 판정된 위험 등급/사유를 /hazard/detected로 발행
    def publish_hazard(self, level: int, hazard_type: str, detail: str):
        data = {'level': level, 'type': hazard_type, 'detail': detail, 'zone': self.current_zone}
        msg = String(); msg.data = json.dumps(data)
        self.pub_hazard.publish(msg)
        self.get_logger().info(f'위험등급 L{level}: {hazard_type} | {detail}')


# 노드 초기화 후 스핀 시작, 종료 시 안전하게 정리
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
