import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Int8, Int16, Float32
import json


# ══════════════════════════════════════════════
# 물체 분류 색상 기반 - vision_node/arm_act_node와 동일 규칙 공유
# ══════════════════════════════════════════════
class ObjectClass:
    CONTAINMENT_BREACH = "CONTAINMENT_BREACH"  # 적색 강체 - 격리 실패 원인
    HANDLE_CARE = "HANDLE_CARE"                # 황색 변형체 - 취급주의


COLOR_TO_CLASS_MISSION = {
    'red': ObjectClass.CONTAINMENT_BREACH,
    'yellow': ObjectClass.HANDLE_CARE,
}

# 담당정리_진우 문서 §4.2에서 삭제 대상으로 남아있는 항목
# 목적지는 색이 아니라 정지점 위치 기준 고정 오프셋으로 정해지는 게 맞는 설계라
# 지금 이 상수를 실제로 대체하는 작업은 VGR 소비 작업과 묶어서 별도로 진행 예정
# 지금 당장 지우면 TRANSPORT 목적지 결정 로직이 깨지므로 이번 커밋에서는 보류함
DESTINATION_BY_CLASS = {
    ObjectClass.CONTAINMENT_BREACH: "OVERPACK_DRUM",
    ObjectClass.HANDLE_CARE: "HAZMAT_STORAGE",
}

GRIP_THRESHOLD_BY_CLASS = {
    ObjectClass.CONTAINMENT_BREACH: 80,
    ObjectClass.HANDLE_CARE: 40,
}

# 수정: 판정은 구역을 몰라야 한다는 원칙에 따른 단일 기준값
# hazard_detector가 발행하는 level이 이 값 이상이면 가스 있음으로 판정함
GAS_PRESENT_LEVEL = 2


# ══════════════════════════════════════════════
# 구역 식별자 코드용 절대 안 바뀜 - 표시 이름만 별도
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
    # RETURN은 EMERGENCY와 하트비트 처리가 반대임
    # EMERGENCY는 하트비트 중단하고 DRIVE가 스스로 정지, 사람이 수동 해제해야 함
    # RETURN은 하트비트 유지한 채로 DRIVE에 후진 신호만 보내고 완료 응답 받으면 자동으로 IDLE 복귀함
    RETURN     = 'RETURN'
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
        # 출발 트리거, 지금은 점검 7항목 없이 바로 PATROL로 나가는 최소 버전임
        # 점검 7항목 붙이는 작업은 다음 순서로 별도 진행함
        self.create_subscription(String, '/mission/start',      self.mission_start_cb, 10)
        # DRIVE가 RETURN 후진 완료했다고 보고하면 amr_bridge를 거쳐 여기로 들어옴
        # 실제로 몇 mm를 얼마나 후진했는지는 관여하지 않고 완료 여부만 받음
        self.create_subscription(String, '/amr/return_complete', self.return_complete_cb, 10)

        # ── Publishers ──
        self.pub_state          = self.create_publisher(String, '/mission/state',    10)
        self.pub_zone            = self.create_publisher(Int8,   '/mission/zone',     10)
        self.pub_wrist            = self.create_publisher(Int16,  '/arm/wrist_preset', 10)
        self.pub_led              = self.create_publisher(String, '/arm/led_cmd',      10)
        self.pub_buzzer           = self.create_publisher(String, '/arm/buzzer_cmd',   10)

        # 파지 GRIP 요청 재시도 - arm_act_node가 구독
        self.pub_grip_request     = self.create_publisher(String, '/arm/grip_request', 10)
        self.pub_grip_retry       = self.create_publisher(String, '/arm/grip_retry',   10)
        # 놓기 place 요청 - arm_controller가 구독
        self.pub_place_request    = self.create_publisher(String, '/arm/place_request', 10)

        # 비상 정지
        self.pub_amr_stop         = self.create_publisher(String, '/amr/emergency',    10)
        self.pub_arm_stop         = self.create_publisher(String, '/arm/emergency',    10)

        # 하트비트
        self.pub_heartbeat        = self.create_publisher(String, '/mission/heartbeat', 10)

        # RETURN 후진 요청, 신호만 보냄, 얼마나 후진할지는 amr_bridge가 아니라 DRIVE 펌웨어가 알아서 함
        self.pub_return_request   = self.create_publisher(String, '/amr/return_request', 10)

        # ── FSM 상태 ──
        self.state        = MissionState.IDLE
        self.current_zone = ZoneId.ZONE1
        self.grip_retry    = 0
        self.MAX_RETRY     = 3

        self.detected_color = None
        self.detected_angle  = None

        # 최근 가스 판정 레벨 저장함, CLASSIFY 판정에서 적색 통과 여부를 가르는 기준값임
        self.last_gas_level = 0

        self.HEARTBEAT_INTERVAL = 0.3
        self.heartbeat_active = True
        self.create_timer(self.HEARTBEAT_INTERVAL, self.send_heartbeat)

        self.create_timer(1.0, self.publish_state)

        self.get_logger().info('Mission Orchestrator 노드 시작함')
        # 부팅 즉시 PATROL로 나가던 걸 폐지함, IDLE에서 /mission/start 대기함
        self.transition(MissionState.IDLE)

    # ════════════════════════════════════════════
    # FSM 상태 전이
    # ════════════════════════════════════════════
    def transition(self, new_state: str):
        self.get_logger().info(f'FSM: {self.state} → {new_state}')
        self.state = new_state
        self.publish_state()

        if new_state == MissionState.IDLE:
            self.set_led('0')
            self.set_buzzer('0')
            self.heartbeat_active = True

        elif new_state == MissionState.PATROL:
            self.set_led('0')
            self.set_buzzer('0')
            self.heartbeat_active = True

        elif new_state == MissionState.DETECTED:
            self.set_led('1')

        elif new_state == MissionState.APPROACH:
            if self.detected_angle is not None:
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

        elif new_state == MissionState.RETURN:
            # EMERGENCY와 달리 하트비트는 그대로 유지함, 주행 능력이 살아있어야 후진 가능함
            # 얼마나 후진할지는 신경 안 쓰고 신호만 보냄
            self.set_led('2')
            self.set_buzzer('1')
            self.get_logger().warn('RETURN 후진 요청 전송, DRIVE 완료 응답 대기')
            self.pub_return_request.publish(String(data='BACKUP'))

    # ════════════════════════════════════════════
    # 출발 트리거 콜백
    # ════════════════════════════════════════════
    def mission_start_cb(self, msg: String):
        # 지금은 점검 7항목 없이 IDLE 상태에서만 PATROL로 나가는 최소 버전임
        if self.state != MissionState.IDLE:
            self.get_logger().warn(f'IDLE 상태가 아니라 출발 요청 무시함, 현재 {self.state}')
            return
        self.get_logger().info('출발 트리거 수신함, PATROL 진입')
        self.transition(MissionState.PATROL)

    # ════════════════════════════════════════════
    # 위험물 감지 콜백
    # ════════════════════════════════════════════
    def hazard_cb(self, msg: String):
        try:
            data = json.loads(msg.data)
        except (json.JSONDecodeError, TypeError) as e:
            self.get_logger().warn(f'hazard_cb JSON 파싱 실패: {e}')
            return

        level = data.get('level', 0)
        haz_type = data.get('type', 'NORMAL')

        if haz_type == 'FLAME':
            # 화염 감지 시 EMERGENCY가 아니라 RETURN으로 전이함
            # 로봇 자신이 점화원 후보라서 정지가 아니라 이격 조치가 맞는 대응임
            if self.state != MissionState.RETURN:
                self.transition(MissionState.RETURN)
            return

        # 화염이 아닌 가스 판정은 상태와 무관하게 항상 최신값으로 저장해둠
        # CLASSIFY 단계에서 적색 물체 통과 여부를 가릴 때 이 값을 씀
        self.last_gas_level = level

        if level >= GAS_PRESENT_LEVEL and self.state == MissionState.PATROL:
            self.transition(MissionState.DETECTED)

    # ════════════════════════════════════════════
    # 비전 감지 콜백
    # ════════════════════════════════════════════
    def vision_cb(self, msg: String):
        try:
            data = json.loads(msg.data)
        except (json.JSONDecodeError, TypeError) as e:
            self.get_logger().warn(f'vision_cb JSON 파싱 실패: {e}')
            return

        self.detected_color = data.get('color')
        self.detected_angle  = data.get('angle')

        if self.state != MissionState.DETECTED:
            return

        self.transition(MissionState.CLASSIFY)

        # CLASSIFY 판정 로직, 담당정리 문서 §2.1 판정표 그대로 반영함
        # 적색 + 가스있음 -> 격리, 적색 + 가스없음 -> 통과, 황색은 가스 무관 항상 격리
        # 판정은 구역을 안 보는 게 원칙임, self.current_zone은 여기서 참조하지 않음
        if self.detected_color == 'red':
            if self.last_gas_level >= GAS_PRESENT_LEVEL:
                self.get_logger().info('적색 물체 가스 감지됨, 격리 절차 진행')
                self.transition(MissionState.APPROACH)
            else:
                # 통과 판정, 격납이 유지되고 있는 상태라 그대로 순찰 복귀함
                self.get_logger().info('적색 물체 가스 없음, 통과 판정, PATROL 복귀')
                self.detected_color = None
                self.detected_angle = None
                self.transition(MissionState.PATROL)
        elif self.detected_color == 'yellow':
            self.get_logger().info('황색 물체 감지됨, 가스 무관 항상 격리 절차 진행')
            self.transition(MissionState.APPROACH)
        else:
            self.get_logger().warn(f'알 수 없는 색상: {self.detected_color}, PATROL 복귀')
            self.transition(MissionState.PATROL)

    # ════════════════════════════════════════════
    # RETURN 완료 응답 콜백
    # ════════════════════════════════════════════
    def return_complete_cb(self, msg: String):
        # DRIVE가 후진 완료를 보고하면 그때 IDLE로 전이함
        # 실제 몇 mm를 얼마나 후진했는지는 DRIVE 펌웨어 소관, 여기서는 상태만 바꿈
        if self.state != MissionState.RETURN:
            return
        self.get_logger().warn('RETURN 완료 응답 수신, IDLE 복귀')
        self.detected_color = None
        self.detected_angle = None
        self.transition(MissionState.IDLE)

    # ════════════════════════════════════════════
    # 테스트용 강제로 GRIP 상태 진입
    # ════════════════════════════════════════════
    def force_grip_cb(self, msg: String):
        if self.state == MissionState.EMERGENCY:
            self.get_logger().warn('DEBUG EMERGENCY 상태 강제 GRIP 요청 무시')
            return

        self.get_logger().warn('DEBUG 강제로 GRIP 상태 진입')
        self.transition(MissionState.GRIP)

    # ════════════════════════════════════════════
    # EMERGENCY 수동 복귀 사람 개입 필수
    # ════════════════════════════════════════════
    def reset_cb(self, msg: String):
        if self.state != MissionState.EMERGENCY:
            self.get_logger().warn(
                f'EMERGENCY 상태가 아니라 리셋 무시됨, 현재 {self.state}'
            )
            return

        try:
            data = json.loads(msg.data)
        except (json.JSONDecodeError, TypeError):
            data = {}

        if data.get('confirm') != 'SAFE_TO_RESUME':
            self.get_logger().warn(
                '리셋 요청 거부, confirm 필드에 SAFE_TO_RESUME 필요함'
            )
            return

        self.get_logger().warn('사람 확인 완료, EMERGENCY 해제, PATROL 복귀')
        self.grip_retry = 0
        self.detected_color = None
        self.detected_angle = None
        self.transition(MissionState.PATROL)

    # ════════════════════════════════════════════
    # 서보 피드백 콜백 파지 판정 재시도 로직
    # ════════════════════════════════════════════
    def feedback_cb(self, msg: String):
        try:
            data = json.loads(msg.data)
        except (json.JSONDecodeError, TypeError) as e:
            self.get_logger().warn(f'feedback_cb JSON 파싱 실패: {e}')
            return

        servo_id = data.get('id')
        load = data.get('load', 0)

        if servo_id != 6 or self.state != MissionState.GRIP:
            return

        object_class = COLOR_TO_CLASS_MISSION.get(self.detected_color)
        threshold = GRIP_THRESHOLD_BY_CLASS.get(object_class, 80)

        if load >= threshold:
            self.get_logger().info(f'파지 성공, Load={load}%')
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
                self.get_logger().error('파지 재시도 초과, SKIP')
                self.grip_retry = 0
                self.transition(MissionState.PATROL)

    # ════════════════════════════════════════════
    # 배터리 콜백
    # ════════════════════════════════════════════
    def battery_cb(self, msg: Float32):
        voltage = msg.data
        if voltage > 0 and voltage < 9.9:
            if self.state != MissionState.EMERGENCY:
                self.get_logger().error(f'배터리 부족 {voltage}V, 비상 정지')
                self.transition(MissionState.EMERGENCY)

    # ════════════════════════════════════════════
    # 비상 정지 하트비트 방식
    # ════════════════════════════════════════════
    def emergency_stop_all(self):
        self.get_logger().error('EMERGENCY 하트비트 중단, DRIVE 자동 정지 유도')
        self.heartbeat_active = False

        stop_msg = String()
        stop_msg.data = 'STOP'

        self.pub_arm_stop.publish(stop_msg)
        self.pub_amr_stop.publish(stop_msg)

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
    # LED 부저 헬퍼
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