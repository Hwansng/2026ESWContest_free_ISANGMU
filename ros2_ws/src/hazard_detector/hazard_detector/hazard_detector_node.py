# 판정 규칙 (아티팩트 "순찰 한 바퀴" 2026-08-16 확정 — 지점 번호는 판정에 안 들어간다)
#   본 것          가스           하는 일
#   ─────────────────────────────────────────
#   빨강            없음           통과 (안전)
#   빨강            있음           위험 — 격납 파손
#   노랑            잴 것이 없다    위험 — 산화성 고체는 가스를 안 낸다. 위치 자체가 위반
#   화염            —             위험 — 부저(ENV 자체 처리) + 후진(이 노드가 트리거)
#
# 🔴 판정은 순전히 "지금 눈앞에 보이는 것"으로 내린다. stopIndex는 GAS_CHECK 프레임에
#    필요한 zone 라벨(P1/P2 둘 중 하나)을 고르는 용도로만 쓴다 — AMRDemoScenarioLogic.h가
#    zone 별로 다른 임계값을 쓰는지 확인할 방법이 없어서, 짝수/홀수로 단순 교대한다.
#    실물 확인 후 필요하면 이 매핑만 바꾸면 된다.

import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Bool, Int8
import json
import time

GAS_CHECK_TIMEOUT_S = 5.0   # md 문서 "최대 5초간 결과 대기"와 동일


class HazardDetector(Node):
    def __init__(self):
        super().__init__('hazard_detector')

        # Subscribers
        self.create_subscription(String, '/vision/detected',  self.vision_cb,      10)
        self.create_subscription(String, '/env/gas_result',   self.gas_result_cb,  10)
        self.create_subscription(String, '/env/temp',         self.temp_cb,        10)
        self.create_subscription(Int8,   '/amr/stop_index',   self.stop_index_cb,  10)

        # Publishers
        self.pub_hazard            = self.create_publisher(String, '/hazard/detected',           10)
        self.pub_gas_check_request = self.create_publisher(String, '/hazard/gas_check_request',  10)
        self.pub_return_request    = self.create_publisher(Bool,   '/hazard/return_request',      10)

        # 상태
        self.current_stop_index = 0
        self.flame_active = False        # 화염 래치 — RETURN 중복 송신 방지
        self.gas_check_inflight = False  # GAS_CHECK 응답 대기 중인지
        self.gas_check_started_at = None

        # 🔴 GAS_RESULT 프레임을 못 받으면(ENV 연결 끊김 등) inflight가 영원히 안 풀려서
        #    이후의 모든 적색 감지가 조용히 무시된다 — 타임아웃으로 반드시 해제한다.
        self.create_timer(0.5, self.check_gas_check_timeout)

        self.get_logger().info('Hazard Detector 노드 시작! (v11 이벤트식 판정)')

    # ════════════════════════════════════════════
    # 정지 인덱스 갱신 (GAS_CHECK zone 라벨 선택용)
    # ════════════════════════════════════════════
    def stop_index_cb(self, msg: Int8):
        self.current_stop_index = msg.data

    # ════════════════════════════════════════════
    # 비전 감지 — 마커 정지마다 vision_node가 1회 발행
    # ════════════════════════════════════════════
    def vision_cb(self, msg: String):
        data = json.loads(msg.data)
        color = data.get('color')
        self.get_logger().info(
            f'비전 감지: 색상={color} 방위각={data.get("angle")} 종횡비={data.get("aspect_ratio")}'
        )

        if color == 'yellow':
            # 산화성 고체 — 가스를 내지 않으니 잴 것이 없다. 위치 자체가 위반.
            self.publish_hazard(3, 'YELLOW_OXIDIZER',
                                 '황색 산화성 고체 감지 — 취급구역 내 위치 자체가 위반', color='yellow')

        elif color == 'red':
            if self.gas_check_inflight:
                self.get_logger().debug('가스 검사 진행 중 — 새 적색 감지 무시')
                return
            zone = 'P1' if (self.current_stop_index % 2 == 0) else 'P2'
            self.gas_check_inflight = True
            self.gas_check_started_at = time.monotonic()
            req = String()
            req.data = zone
            self.pub_gas_check_request.publish(req)
            self.get_logger().info(f'적색 감지 — GAS_CHECK 요청 전송 (zone={zone})')

        else:
            self.get_logger().debug(f'판정 대상 아님(색상={color}) — 통과')

    # ════════════════════════════════════════════
    # 가스 검사 결과 — sensor_bridge가 GAS_RESULT 수신 후 발행
    # ════════════════════════════════════════════
    def gas_result_cb(self, msg: String):
        if not self.gas_check_inflight:
            return  # 요청하지 않은 결과(레이스) 무시

        data = msg.data
        data = json.loads(data)
        zone = data.get('zone')
        result = data.get('result')
        self.gas_check_inflight = False
        self.gas_check_started_at = None

        if result == 'DETECTED':
            self.publish_hazard(3, 'RED_LEAK',
                                 f'적색 물질 — 가스 감지(zone={zone}). 격납 파손', color='red')
        elif result == 'CLEAR':
            self.publish_hazard(0, 'RED_SEALED',
                                 f'적색 물질 — 가스 없음(zone={zone}). 격납 유지, 통과', color='red')
        else:
            self.get_logger().warn(f'GAS_CHECK 결과 ERROR(zone={zone}) — 판정 보류, 위험 주장 안 함')

    def check_gas_check_timeout(self):
        if not self.gas_check_inflight or self.gas_check_started_at is None:
            return
        if time.monotonic() - self.gas_check_started_at < GAS_CHECK_TIMEOUT_S:
            return
        self.get_logger().warn('GAS_CHECK 응답 timeout — 판정 보류, 다음 감지를 위해 대기 상태 해제')
        self.gas_check_inflight = False
        self.gas_check_started_at = None

    # ════════════════════════════════════════════
    # 화염 — ENV SENS의 flame 필드. 마커 정지와 무관하게 상시 감시
    # ════════════════════════════════════════════
    def temp_cb(self, msg: String):
        data = json.loads(msg.data)
        flame = bool(data.get('flame'))

        if flame and not self.flame_active:
            self.flame_active = True
            self.publish_hazard(3, 'FLAME', 'KY-026 화염 감지 — 점화원 이탈(후진) 트리거')
            self.pub_return_request.publish(Bool(data=True))
            self.get_logger().warn('🔴 화염 감지 — /hazard/return_request 발행')
        elif not flame and self.flame_active:
            self.flame_active = False  # 꺼지면 재무장 (다음 화염 이벤트를 다시 잡기 위해)

    # ════════════════════════════════════════════
    # 위험 정보 발행
    # ════════════════════════════════════════════
    def publish_hazard(self, level: int, hazard_type: str, detail: str, color: str = None):
        data = {
            'level': level,
            'type': hazard_type,
            'detail': detail,
        }
        if color:
            data['color'] = color
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
