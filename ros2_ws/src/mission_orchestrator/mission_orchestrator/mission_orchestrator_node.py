"""
미션 전체 흐름(FSM)을 조율하는 노드. 하트비트 기반 정지 + EMERGENCY 수동 복귀 포함.
"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Int8, Int16, Float32
import json


# ══════════════════════════════════════════════
# 물체 분류 (색상 기반) — vision_node/arm_act_node와 동일 규칙 공유
# ══════════════════════════════════════════════
class ObjectClass:
    CONTAINMENT_BREACH = "CONTAINMENT_BREACH"  # 적색 강체 - 격리 실패 원인
    HANDLE_CARE = "HANDLE_CARE"                # 황색 변형체 - 취급주의


COLOR_TO_CLASS_MISSION = {
    'red': ObjectClass.CONTAINMENT_BREACH,
    'yellow': ObjectClass.HANDLE_CARE,
}

DESTINATION_BY_CLASS = {
    ObjectClass.CONTAINMENT_BREACH: "OVERPACK_DRUM",
    ObjectClass.HANDLE_CARE: "HAZMAT_STORAGE",
}

GRIP_THRESHOLD_BY_CLASS = {
    ObjectClass.CONTAINMENT_BREACH: 80,
    ObjectClass.HANDLE_CARE: 40,
}


# ══════════════════════════════════════════════
# 구역 식별자 (코드용, 절대 안 바뀜) — 표시 이름만 별도
# ══════════════════════════════════════════════
class ZoneId:
    ZONE1 = 1
    ZONE2 = 2
    ZONE3 = 3
    JUNCTION = 4


ZONE_DISPLAY_NAMES = {1: "일반구역", 2: "취급구역", 3: "위험구역", 4: "분기점"}


# ══════════════════════════════════════════════
# FSM 상태 정의
# ══════════════════════════════════════════════
class MissionState:
    IDLE       = 'IDLE'
    PATROL     = 'PATROL'
    DETECTED   = 'DETECTED'
    CLASSIFY   = 'CLASSIFY'
    APPROACH   = 'APPROACH'
    GRIP       = 'GRIP'
    TRANSPORT  = 'TRANSPORT'
    ISOLATE    = 'ISOLATE'
    REPORT     = 'REPORT'
    EMERGENCY  = 'EMERGENCY'
    HOME       = 'HOME'


class MissionOrchestrator(Node):
    def __init__(self):
        super().__init__('mission_orchestrator')

        # ── Subscribers ──
        self.create_subscription(String, '/hazard/detected',    self.hazard_cb,   10)
        self.create_subscription(String, '/vision/detected',    self.vision_cb,   10)
        self.create_subscription(String, '/arm/servo_feedback', self.feedback_cb, 10)
        self.create_subscription(Float32, '/amr/battery',       self.battery_cb,  10)
        self.create_subscription(String, '/debug/force_grip',   self.force_grip_cb, 10)
        self.create_subscription(String, '/mission/reset',      self.reset_cb,    10)

        # ── Publishers ──
        self.pub_state          = self.create_publisher(String, '/mission/state',    10)
        self.pub_zone            = self.create_publisher(Int8,   '/mission/zone',     10)
        self.pub_wrist            = self.create_publisher(Int16,  '/arm/wrist_preset', 10)
        self.pub_led              = self.create_publisher(String, '/arm/led_cmd',      10)
        self.pub_buzzer           = self.create_publisher(String, '/arm/buzzer_cmd',   10)

        # 파지(GRIP) 요청/재시도 → arm_act_node가 구독
        self.pub_grip_request     = self.create_publisher(String, '/arm/grip_request', 10)
        self.pub_grip_retry       = self.create_publisher(String, '/arm/grip_retry',   10)
        # 놓기(place) 요청 → arm_controller(축소판)가 구독
        self.pub_place_request    = self.create_publisher(String, '/arm/place_request', 10)

        # 비상 정지 (arm 쪽은 과도기적으로 STOP 유지)
        self.pub_amr_stop         = self.create_publisher(String, '/amr/emergency',    10)
        self.pub_arm_stop         = self.create_publisher(String, '/arm/emergency',    10)

        # 하트비트 (문서 §5: 계층2는 명령이 아니라 하트비트)
        self.pub_heartbeat        = self.create_publisher(String, '/mission/heartbeat', 10)

        # ── FSM 상태 ──
        self.state        = MissionState.IDLE
        self.current_zone = ZoneId.ZONE1
        self.grip_retry    = 0
        self.MAX_RETRY     = 3

        self.detected_color = None
        self.detected_angle  = None

        # 하트비트 주기 = 타임아웃(1초 예정)의 1/3 이하
        self.HEARTBEAT_INTERVAL = 0.3
        self.heartbeat_active = True
        self.create_timer(self.HEARTBEAT_INTERVAL, self.send_heartbeat)

        self.create_timer(1.0, self.publish_state)

        self.get_logger().info('Mission Orchestrator 노드 시작!')
        self.transition(MissionState.PATROL)

    # ════════════════════════════════════════════
    # FSM 상태 전이
    # ════════════════════════════════════════════
    def transition(self, new_state: str):
        self.get_logger().info(f'FSM: {self.state} → {new_state}')
        self.state = new_state
        self.publish_state()

        if new_state == MissionState.PATROL:
            self.set_led('0')
            self.set_buzzer('0')
            self.heartbeat_active = True   # 하트비트 재개

        elif new_state == MissionState.DETECTED:
            self.set_led('1')

        elif new_state == MissionState.APPROACH:
            if self.detected_angle:
                self.pub_wrist.publish(Int16(data=int(self.detected_angle)))

        elif new_state == MissionState.GRIP:
            grip_msg = String()
            grip_msg.data = self.detected_color or 'red'
            self.pub_grip_request.publish(grip_msg)
            self.get_logger().info(f'GRIP 요청 전송: color={grip_msg.data}')

        elif new_state == MissionState.TRANSPORT:
            object_class = COLOR_TO_CLASS_MISSION.get(self.detected_color)
            destination = DESTINATION_BY_CLASS.get(object_class, 'HOME')
            place_msg = String()
            place_msg.data = destination
            self.pub_place_request.publish(place_msg)
            self.get_logger().info(f'놓기 요청 전송: destination={destination}')

        elif new_state == MissionState.EMERGENCY:
            self.set_led('2')
            self.set_buzzer('1')
            self.emergency_stop_all()

    # ════════════════════════════════════════════
    # 위험물 감지 콜백
    # ════════════════════════════════════════════
    def hazard_cb(self, msg: String):
        data = json.loads(msg.data)
        level = data.get('level', 0)

        if data.get('type') == 'FLAME':
            self.transition(MissionState.EMERGENCY)
            return

        if level >= 2 and self.state == MissionState.PATROL:
            self.transition(MissionState.DETECTED)

    # ════════════════════════════════════════════
    # 비전 감지 콜백
    # ════════════════════════════════════════════
    def vision_cb(self, msg: String):
        data = json.loads(msg.data)
        self.detected_color = data.get('color')
        self.detected_angle  = data.get('angle')

        if self.state == MissionState.DETECTED:
            self.transition(MissionState.CLASSIFY)
            self.transition(MissionState.APPROACH)

    # ════════════════════════════════════════════
    # 테스트용: 강제로 GRIP 상태 진입 (amr_navigation 없을 때 디버깅용)
    # ════════════════════════════════════════════
    def force_grip_cb(self, msg: String):
        self.get_logger().warn('[DEBUG] 강제로 GRIP 상태 진입')
        self.transition(MissionState.GRIP)

    # ════════════════════════════════════════════
    # EMERGENCY 수동 복귀 (사람 개입 필수)
    # ════════════════════════════════════════════
    def reset_cb(self, msg: String):
        if self.state != MissionState.EMERGENCY:
            self.get_logger().warn(
                f'EMERGENCY 상태가 아니라 리셋 무시됨 (현재: {self.state})'
            )
            return

        try:
            data = json.loads(msg.data)
        except (json.JSONDecodeError, TypeError):
            data = {}

        if data.get('confirm') != 'SAFE_TO_RESUME':
            self.get_logger().warn(
                '리셋 요청 거부 — confirm 필드에 "SAFE_TO_RESUME" 필요'
            )
            return

        self.get_logger().warn('!!! 사람 확인 완료 — EMERGENCY 해제, PATROL 복귀 !!!')
        self.grip_retry = 0
        self.detected_color = None
        self.detected_angle = None
        self.transition(MissionState.PATROL)

    # ════════════════════════════════════════════
    # 서보 피드백 콜백 (파지 판정 + 재시도 로직)
    # ════════════════════════════════════════════
    def feedback_cb(self, msg: String):
        data = json.loads(msg.data)
        servo_id = data.get('id')
        load = data.get('load', 0)

        if servo_id != 6 or self.state != MissionState.GRIP:
            return

        object_class = COLOR_TO_CLASS_MISSION.get(self.detected_color)
        threshold = GRIP_THRESHOLD_BY_CLASS.get(object_class, 80)

        if load >= threshold:
            self.get_logger().info(f'파지 성공! Load={load}%')
            self.grip_retry = 0
            self.transition(MissionState.TRANSPORT)

        elif load < 10:
            self.grip_retry += 1
            if self.grip_retry <= self.MAX_RETRY:
                self.get_logger().warn(
                    f'파지 실패, 재시도 {self.grip_retry}/{self.MAX_RETRY}'
                )
                retry_msg = String()
                retry_msg.data = json.dumps({'offset_mm': 5})
                self.pub_grip_retry.publish(retry_msg)
            else:
                self.get_logger().error('파지 재시도 초과 - SKIP')
                self.grip_retry = 0
                self.transition(MissionState.PATROL)

    # ════════════════════════════════════════════
    # 배터리 콜백
    # ════════════════════════════════════════════
    def battery_cb(self, msg: Float32):
        voltage = msg.data
        if voltage > 0 and voltage < 9.9:
            self.get_logger().error(f'배터리 부족! {voltage}V → 비상 정지')
            self.transition(MissionState.EMERGENCY)

    # ════════════════════════════════════════════
    # 비상 정지 (하트비트 방식, 문서 §5)
    # ════════════════════════════════════════════
    def emergency_stop_all(self):
        self.get_logger().error('!!! EMERGENCY: 하트비트 중단 → DRIVE 자동 정지 유도 !!!')
        self.heartbeat_active = False
        # arm 쪽은 하트비트 체계 도입 전까지 과도기적으로 STOP 유지
        stop_msg = String()
        stop_msg.data = 'STOP'
        self.pub_arm_stop.publish(stop_msg)

    def send_heartbeat(self):
        if not self.heartbeat_active:
            return
        msg = String()
        msg.data = json.dumps({'alive': True, 'state': self.state})
        self.pub_heartbeat.publish(msg)

    # ════════════════════════════════════════════
    # 상태 퍼블리시
    # ════════════════════════════════════════════
    def publish_state(self):
        msg = String()
        msg.data = json.dumps({
            'state': self.state,
            'zone': self.current_zone,
            'zone_display': ZONE_DISPLAY_NAMES.get(self.current_zone, '알수없음'),
            'color': self.detected_color,
            'angle': self.detected_angle,
        })
        self.pub_state.publish(msg)

        zone_msg = Int8()
        zone_msg.data = self.current_zone
        self.pub_zone.publish(zone_msg)

    # ════════════════════════════════════════════
    # LED / 부저 헬퍼
    # ════════════════════════════════════════════
    def set_led(self, value: str):
        msg = String()
        msg.data = value
        self.pub_led.publish(msg)

    def set_buzzer(self, value: str):
        msg = String()
        msg.data = value
        self.pub_buzzer.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = MissionOrchestrator()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
