"""
미션 전체 흐름(FSM)을 조율하는 노드.
"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Int8, Int16
import json

class MissionState:
    IDLE, PATROL, DETECTED, CLASSIFY = 'IDLE', 'PATROL', 'DETECTED', 'CLASSIFY'
    APPROACH, GRIP, TRANSPORT, ISOLATE = 'APPROACH', 'GRIP', 'TRANSPORT', 'ISOLATE'
    REPORT, EMERGENCY, HOME = 'REPORT', 'EMERGENCY', 'HOME'

class MissionOrchestrator(Node):
    # 노드 초기화: 토픽 구독/발행 설정
    def __init__(self):
        super().__init__('mission_orchestrator')

        self.create_subscription(String, '/hazard/detected',    self.hazard_cb,   10)
        self.create_subscription(String, '/vision/detected',    self.vision_cb,   10)
        self.create_subscription(String, '/arm/servo_feedback', self.feedback_cb, 10)
        self.create_subscription(String, '/amr/battery', self.battery_cb, 10)

        self.pub_state  = self.create_publisher(String, '/mission/state', 10)
        self.pub_zone   = self.create_publisher(Int8,   '/mission/zone', 10)
        self.pub_wrist  = self.create_publisher(Int16,  '/arm/wrist_preset', 10)
        self.pub_led    = self.create_publisher(String, '/arm/led_cmd', 10)
        self.pub_buzzer = self.create_publisher(String, '/arm/buzzer_cmd', 10)
        self.pub_amr_stop = self.create_publisher(String, '/amr/emergency', 10)
        self.pub_arm_stop = self.create_publisher(String, '/arm/emergency', 10)

        self.state = MissionState.IDLE
        self.current_zone = 1
        self.detected_color = None
        self.detected_angle = None

        self.create_timer(1.0, self.publish_state)

        self.get_logger().info('Mission Orchestrator 노드 시작!')
        self.transition(MissionState.PATROL)

    # FSM 상태 전이 처리 및 상태별 진입 동작 실행
    def transition(self, new_state: str):
        self.get_logger().info(f'FSM: {self.state} → {new_state}')
        self.state = new_state
        self.publish_state()

        if new_state == MissionState.PATROL:
            self.set_led('0'); self.set_buzzer('0')
        elif new_state == MissionState.DETECTED:
            self.set_led('1')
        elif new_state == MissionState.APPROACH:
            if self.detected_angle:
                self.pub_wrist.publish(Int16(data=int(self.detected_angle)))
        elif new_state == MissionState.EMERGENCY:
            self.set_led('2'); self.set_buzzer('1')
            self.emergency_stop_all()

    # /hazard/detected 콜백: 위험 등급에 따라 접근 동작 트리거
    def hazard_cb(self, msg: String):
        data = json.loads(msg.data)
        if data.get('type') == 'FLAME':
            self.transition(MissionState.EMERGENCY)
            return
        if data.get('level', 0) >= 2 and self.state == MissionState.PATROL:
            self.transition(MissionState.DETECTED)

    # /vision/detected 콜백: 감지 색상/방위각 로그 또는 상태 갱신
    def vision_cb(self, msg: String):
        data = json.loads(msg.data)
        self.detected_color = data.get('color')
        self.detected_angle = data.get('angle')
        if self.state == MissionState.DETECTED:
            self.transition(MissionState.CLASSIFY)
            self.transition(MissionState.APPROACH)

    # /arm/servo_feedback 콜백: 과열/과부하 경고 또는 파지 판정
    def feedback_cb(self, msg: String):
        data = json.loads(msg.data)
        if self.state == MissionState.GRIP:
            threshold = 40 if self.detected_color == 'yellow' else 80
            if data.get('load', 0) >= threshold:
                self.transition(MissionState.TRANSPORT)

    # /amr/battery 콜백: 저전압 감지 시 EMERGENCY 전이
    def battery_cb(self, msg):
        try:
            voltage = float(msg.data)
        except:
            voltage = 0.0
        if 0 < voltage < 9.9:
            self.transition(MissionState.EMERGENCY)

    # 양쪽 ESP32 비상 정지 처리 (또는 하트비트 중단)
    def emergency_stop_all(self):
        self.get_logger().error('!!! 양쪽 ESP32 동시 STOP !!!')
        stop_msg = String(); stop_msg.data = 'STOP'
        self.pub_amr_stop.publish(stop_msg)
        self.pub_arm_stop.publish(stop_msg)

    # 현재 미션 상태를 /mission/state, /mission/zone으로 발행
    def publish_state(self):
        msg = String()
        msg.data = json.dumps({'state': self.state, 'zone': self.current_zone,
                                'color': self.detected_color, 'angle': self.detected_angle})
        self.pub_state.publish(msg)

    # /arm/led_cmd로 LED 색상 값 발행
    def set_led(self, value: str):
        msg = String(); msg.data = value
        self.pub_led.publish(msg)

    # /arm/buzzer_cmd로 부저 값 발행
    def set_buzzer(self, value: str):
        msg = String(); msg.data = value
        self.pub_buzzer.publish(msg)


# 노드 초기화 후 스핀 시작, 종료 시 안전하게 정리
def main(args=None):
    rclpy.init(args=args)
    node = MissionOrchestrator()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
