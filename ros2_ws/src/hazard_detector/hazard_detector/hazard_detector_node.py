# 물체 분류 (색상 기반 파지 대상)
class ObjectClass:
    CONTAINMENT_BREACH = "CONTAINMENT_BREACH"  # 적색 강체 - 개방·파손, 격리 실패 원인
    HANDLE_CARE = "HANDLE_CARE"                # 황색 변형체 - 취급주의, 정상 업무

# 구역 식별자 (코드용, 절대 안 바뀜) — 표시 이름만 별도
class ZoneId:
    ZONE1 = 1       # 표시 이름: 일반구역
    ZONE2 = 2       # 표시 이름: 취급구역
    ZONE3 = 3       # 표시 이름: 위험구역
    JUNCTION = 4    # 분기점 (모듈로 4 순환, 정차 안 함)

ZONE_DISPLAY_NAMES = {1: "일반구역", 2: "취급구역", 3: "위험구역", 4: "분기점"}

import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Int8
import json

class HazardDetector(Node):
    def __init__(self):
        super().__init__('hazard_detector')

        # Subscribers
        self.create_subscription(String, '/amr/gas',     self.gas_cb,    10)
        self.create_subscription(String, '/amr/temp',    self.temp_cb,   10)
        self.create_subscription(String, '/amr/sensors', self.sensor_cb, 10)
        self.create_subscription(String, '/vision/detected', self.vision_cb, 10)
        self.create_subscription(Int8,   '/mission/zone', self.zone_cb,  10)

        # Publishers
        self.pub_hazard = self.create_publisher(String, '/hazard/detected', 10)

        # 상태 저장
        self.current_zone = 1
        self.gas_data  = None
        self.temp_data = None

        # 구역별 가스 임계값 (구역 컨텍스트)
        self.zone_thresholds = {
            1: {'gas': 300, 'temp': 60},   # ZONE 1 임계값
            2: {'gas': 200, 'temp': 50},   # ZONE 2 임계값
            3: {'gas': 150, 'temp': 45},   # ZONE 3 임계값
        }

        self.get_logger().info('Hazard Detector 노드 시작!')

    # ════════════════════════════════════════════
    # 구역 업데이트
    # ════════════════════════════════════════════
    def zone_cb(self, msg: Int8):
        self.current_zone = msg.data
        self.get_logger().info(f'현재 구역: ZONE {self.current_zone}')

    # ════════════════════════════════════════════
    # 가스 데이터 수신
    # ════════════════════════════════════════════
    def gas_cb(self, msg: String):
        self.gas_data = json.loads(msg.data)
        self.evaluate_hazard()

    # ════════════════════════════════════════════
    # 온도 데이터 수신
    # ════════════════════════════════════════════
    def temp_cb(self, msg: String):
        self.temp_data = json.loads(msg.data)

        # 화염 감지시 즉시 L3
        if self.temp_data.get('flame') == 1:
            self.publish_hazard(3, 'FLAME', 'KY-026 화염 감지')
            return

        self.evaluate_hazard()

    # ════════════════════════════════════════════
    # 센서 데이터 수신
    # ════════════════════════════════════════════
    def sensor_cb(self, msg: String):
        pass  # amr_bridge에서 이미 분리해서 옴

    # ════════════════════════════════════════════
    # 비전 데이터 수신
    # ════════════════════════════════════════════
    def vision_cb(self, msg: String):
        data = json.loads(msg.data)
        self.get_logger().info(
            f'비전 감지: 색상={data.get("color")} '
            f'방위각={data.get("angle")} '
            f'종횡비={data.get("aspect_ratio")}'
        )

    # ════════════════════════════════════════════
    # 위험 등급 판단 (핵심 로직)
    # ════════════════════════════════════════════
    def evaluate_hazard(self):
        if not self.gas_data or not self.temp_data:
            return

        zone     = self.current_zone
        mq2      = self.gas_data.get('mq2', 0)
        mq135    = self.gas_data.get('mq135', 0)
        temp     = self.temp_data.get('temp', 0)
        flag     = self.gas_data.get('flag', 'NORMAL')

        # 구역별 임계값 가져오기
        threshold = self.zone_thresholds.get(zone, self.zone_thresholds[1])
        gas_limit  = threshold['gas']
        temp_limit = threshold['temp']

        # MQ 비율 분석
        ratio = mq2 / mq135 if mq135 > 0 else 0

        # ── 등급 판단 ──────────────────────────
        level = 0
        reason = 'NORMAL'

        # L3: 즉시 위험
        if flag == 'HIGH' and temp > temp_limit:
            level = 3
            reason = '가스+고온 복합 위험'

        # L2: 경고
        elif mq2 > gas_limit or mq135 > gas_limit:
            level = 2
            reason = f'가스 초과 (ZONE {zone} 임계값 {gas_limit})'

        elif temp > temp_limit:
            level = 2
            reason = f'온도 초과 ({temp}°C)'

        # L1: 주의
        elif mq2 > gas_limit * 0.7 or temp > temp_limit * 0.8:
            level = 1
            reason = '주의 수준'

        # L0: 정상
        else:
            level = 0
            reason = 'NORMAL'

        self.publish_hazard(level, reason, f'MQ2={mq2} MQ135={mq135} TEMP={temp}°C ZONE={zone}')

    # ════════════════════════════════════════════
    # 위험 정보 발행
    # ════════════════════════════════════════════
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
