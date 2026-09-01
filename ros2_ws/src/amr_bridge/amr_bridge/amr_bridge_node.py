"""
AMR ESP32 #1과 TCP로 통신하며 센서/이동 명령을 ROS2 토픽과 연결하는 브릿지 노드.
하트비트를 DRIVE로 전달하는 heartbeat_cb 포함.
"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Bool, Float32, Int8
from geometry_msgs.msg import Twist
import socket
import threading
import json
import time

HOST = '0.0.0.0'   # 모든 IP에서 접속 허용
AMR_PORT = 5000    # ESP32 #1이 접속할 포트번호

class AmrBridge(Node):
    def __init__(self):
        super().__init__('amr_bridge')

        # ── Publishers: ESP32 #1 데이터를 ROS2 토픽으로 내보냄 ──
        self.pub_sensors = self.create_publisher(String,  '/amr/sensors',     10)
        self.pub_gas     = self.create_publisher(String,  '/amr/gas',         10)
        self.pub_temp    = self.create_publisher(String,  '/amr/temp',        10)
        self.pub_battery = self.create_publisher(Float32, '/amr/battery',     10)
        self.pub_near        = self.create_publisher(Bool, '/amr/object_near', 10)
        self.pub_stop_index  = self.create_publisher(Int8, '/amr/stop_index',  10)
        self.pub_return_done = self.create_publisher(Bool, '/amr/return_done', 10)
        self.conn = None
        self.conn_lock = threading.Lock()
        self.last_recv_time = time.time()   # ← 이거 있는지 확인
        self.create_timer(0.5, self.check_timeout)

        self.returning_active = False   # RETURN 송신 후 RETDONE 전까지 True — 중복 송신 방지

        # ── Subscriber: ROS2 명령을 ESP32 #1으로 전달 ──
        self.create_subscription(
            Twist, '/amr/cmd_vel', self.cmd_vel_cb, 10
        )
        # ── mission_orchestrator의 하트비트를 받아 DRIVE로 전달 ──
        self.create_subscription(String, '/mission/heartbeat', self.heartbeat_cb, 10)
        # ── hazard_detector가 화염 감지 시 후진을 요청 ──
        self.create_subscription(Bool, '/hazard/return_request', self.return_request_cb, 10)
        # ── 원격 출발 — DRIVE 시리얼에 로컬로 손댈 수 없을 때 RPi에서 대신 <GO> 송신 ──
        self.create_subscription(Bool, '/amr/start_request', self.start_request_cb, 10)

        self.conn = None          # ESP32 #1 소켓 (연결되면 채워짐)
        self.conn_lock = threading.Lock()

        # TCP 서버를 백그라운드 스레드로 실행
        threading.Thread(target=self.tcp_server, daemon=True).start()

        # 하트비트: 500ms마다 연결 확인
        self.create_timer(0.5, self.heartbeat)

        self.get_logger().info('AMR Bridge 노드 시작!')

    # ════════════════════════════════════════════
    # TCP 서버: ESP32 #1의 접속을 기다림
    # ════════════════════════════════════════════
    def tcp_server(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((HOST, AMR_PORT))
            server.listen(1)
            self.get_logger().info(f'포트 {AMR_PORT} 에서 ESP32 #1 기다리는 중...')

            while rclpy.ok():
                try:
                    conn, addr = server.accept()  # ESP32 접속 대기 (블로킹)
                    self.get_logger().info(f'ESP32 #1 연결됨! IP: {addr[0]}')
                    with self.conn_lock:
                        self.conn = conn
                    # 수신 루프를 별도 스레드로 실행
                    threading.Thread(
                        target=self.recv_loop,
                        args=(conn,),
                        daemon=True
                    ).start()
                except Exception as e:
                    self.get_logger().error(f'서버 오류: {e}')
                    time.sleep(1)

    # ════════════════════════════════════════════
    # 수신 루프: ESP32 #1이 보내는 데이터를 계속 읽음
    # ════════════════════════════════════════════
    def recv_loop(self, conn):
        buf = ''
        while rclpy.ok():
            try:
                raw = conn.recv(256)
                if not raw:
                    break  # 연결 끊김
                buf += raw.decode('utf-8', errors='ignore')

                # \n 기준으로 메시지 분리
                while '\n' in buf:
                    line, buf = buf.split('\n', 1)
                    line = line.strip()
                    if line:
                        self.parse_msg(line)

            except ConnectionResetError:
                self.get_logger().warn('ESP32 #1 연결 끊김 (Reset)')
                break
            except Exception as e:
                self.get_logger().warn(f'수신 오류: {e}')
                break

        # 연결 정리
        with self.conn_lock:
            self.conn = None
        self.get_logger().warn('ESP32 #1 연결 종료. 재접속 대기 중...')

    # ════════════════════════════════════════════
    # 메시지 파싱: <SENS,gas,flame,battCv,stateCode,actionCode,faultCode,CS>
    # ════════════════════════════════════════════
    STATE_NAMES  = ['SAFE', 'WARNING', 'DANGER', 'STOP', 'SENSOR_ERROR']
    ACTION_NAMES = ['NORMAL_MOTION', 'LIMITED_MOTION', 'STOP_MOTION']
    FAULT_NAMES  = ['OK', 'ESTOP', 'LIPO', 'SENSOR', 'RPI_TIMEOUT', 'HAZARD']

    def parse_msg(self, line: str):
        self.last_recv_time = time.time()   # 🔴 이게 빠져 있으면 check_timeout()이 2초마다 conn을 끊는다

        if not (line.startswith('<') and line.endswith('>')):
            self.get_logger().debug(f'무시된 메시지: {line}')
            return

        inner = line[1:-1]
        parts = inner.split(',')

        if len(parts) < 2:
            return

        if not self.verify_checksum(parts):
            self.get_logger().warn(f'체크섬 불일치: {line}')
            return

        cmd = parts[0]

        # ── SENS: <SENS,gas,flame,battCv,stateCode,actionCode,faultCode,CS> ──
        if cmd == 'SENS' and len(parts) >= 8:
            gas         = int(parts[1])
            flame       = int(parts[2])
            batt_cv     = int(parts[3])
            state_code  = int(parts[4])
            action_code = int(parts[5])
            fault_code  = int(parts[6])

            data = {
                'gas': gas,
                'flame': bool(flame),
                'battery_v': batt_cv / 100.0,
                'state': self.STATE_NAMES[state_code] if state_code < len(self.STATE_NAMES) else f'UNKNOWN({state_code})',
                'action': self.ACTION_NAMES[action_code] if action_code < len(self.ACTION_NAMES) else f'UNKNOWN({action_code})',
                'fault': self.FAULT_NAMES[fault_code] if fault_code < len(self.FAULT_NAMES) else f'UNKNOWN({fault_code})',
            }

            # 가스 데이터 발행
            gas_msg = String()
            gas_msg.data = json.dumps({'gas': gas, 'flag': data['state']})
            self.pub_gas.publish(gas_msg)

            # 화염/온도 대체 발행 (온도 센서는 이 보드에 없어서 flame만 반영)
            temp_msg = String()
            temp_msg.data = json.dumps({'temp': 0.0, 'flame': int(flame)})
            self.pub_temp.publish(temp_msg)

            # 배터리 발행
            batt_msg = Float32()
            batt_msg.data = data['battery_v']
            self.pub_battery.publish(batt_msg)

            self.get_logger().info(
                f'SENS 수신: gas={gas} flame={flame} '
                f'batt={data["battery_v"]}V state={data["state"]} '
                f'action={data["action"]} fault={data["fault"]}'
            )

            # 🔵 2026-08-28 스케치부터 fault 뒤에 dist·stopIndex 가 덧붙는다
            #    (esp32_drive_tcp.ino §9). 옛 8필드 프레임과도 호환되도록 있을 때만 읽는다.
            if len(parts) >= 10:
                stop_index = int(parts[8])
                self.pub_stop_index.publish(Int8(data=stop_index))

        # ── DETECT: 정지 마커 도달 — 비전 캡처 트리거 ──
        elif cmd == 'DETECT':
            self.pub_near.publish(Bool(data=True))
            self.get_logger().info('DETECT 수신 — /amr/object_near 발행 (비전 캡처 트리거)')

        # ── RETDONE: RETURN(후진) 완료 ──
        elif cmd == 'RETDONE':
            self.returning_active = False
            self.pub_return_done.publish(Bool(data=True))
            self.get_logger().info('RETDONE 수신 — 후진 완료')

        else:
            self.get_logger().debug(f'알 수 없는 CMD: {cmd}')

    # ════════════════════════════════════════════
    # 체크섬 계산 및 검증
    # ════════════════════════════════════════════
    def verify_checksum(self, parts: list) -> bool:
        try:
            received_cs = int(parts[-1])
            # CS 제외한 부분으로 계산
            data_str = ','.join(parts[:-1])
            calculated = sum(ord(c) for c in data_str) % 256
            return received_cs == calculated
        except (ValueError, IndexError):
            return False

    def calc_checksum(self, *fields) -> int:
        data_str = ','.join(str(f) for f in fields)
        return sum(ord(c) for c in data_str) % 256

    # ════════════════════════════════════════════
    # 메시지 빌드 및 송신
    # ════════════════════════════════════════════
    def build_and_send(self, *fields):
        cs = self.calc_checksum(*fields)
        msg = '<' + ','.join(str(f) for f in fields) + f',{cs}>\n'
        with self.conn_lock:
            if self.conn:
                try:
                    self.conn.sendall(msg.encode())
                except Exception as e:
                    self.get_logger().warn(f'송신 실패: {e}')
            else:
                self.get_logger().warn('ESP32 #1 미연결 상태 - 명령 전송 불가')

    # ════════════════════════════════════════════
    # /amr/cmd_vel 콜백 → MOVE 명령 전송
    # ════════════════════════════════════════════
    def cmd_vel_cb(self, msg: Twist):
        linear  = msg.linear.x    # 전후 속도 -1.0 ~ 1.0
        angular = msg.angular.z   # 좌우 회전 -1.0 ~ 1.0

        # 차동 구동 계산 (PWM 0~255)
        left  = int((linear - angular) * 150)
        right = int((linear + angular) * 150)
        left  = max(-255, min(255, left))
        right = max(-255, min(255, right))

        self.build_and_send('MOVE', left, right)

    # ════════════════════════════════════════════
    # 비상 정지 (mission_orchestrator가 직접 호출)
    # ════════════════════════════════════════════
    def emergency_stop(self):
        self.get_logger().error('!!! AMR 비상 정지 !!!')
        self.build_and_send('STOP')

    # ════════════════════════════════════════════
    # 화염 감지 시 hazard_detector가 요청하는 후진(RETURN)
    # ════════════════════════════════════════════
    def return_request_cb(self, msg: Bool):
        if not msg.data:
            return
        if self.returning_active:
            self.get_logger().debug('RETURN 이미 진행 중 — 재요청 무시')
            return
        self.returning_active = True
        self.build_and_send('RETURN')
        self.get_logger().warn('🔴 RETURN 송신 — 화염 감지로 후진 시작')

    # ════════════════════════════════════════════
    # 원격 출발 — <GO> 송신 (2026-08-30, DRIVE esp32_drive_tcp.ino와 짝)
    # DRIVE가 시리얼 'g'와 동일하게 STBY ON + 라인추종 시작 + ESTOP 해제까지 처리한다.
    # ════════════════════════════════════════════
    def start_request_cb(self, msg: Bool):
        if not msg.data:
            return
        self.send_go()

    def send_go(self):
        self.build_and_send('GO')
        self.get_logger().info('GO 송신 — 원격 라인추종 시작 요청')

    # ════════════════════════════════════════════
    # 하트비트: 연결 상태 주기적 로그
    # ════════════════════════════════════════════
    def heartbeat_cb(self, msg: String):
        """RPi 하트비트를 DRIVE로 전달. DRIVE는 이게 끊기면 스스로 정지한다."""
        self.build_and_send('HB')  # 최소 페이로드로 하트비트 신호만 전송

    def heartbeat(self):
        # 🔵 2026-08-30 — mission_orchestrator 없이(파지 제외 시연) 이 노드 단독으로도
        # DRIVE 타임아웃(RPI_TIMEOUT_MS=1000ms)을 안 넘기도록 자체 HB도 같이 보낸다.
        # mission_orchestrator가 붙어있으면 heartbeat_cb의 HB와 중복되지만 무해하다
        # (DRIVE는 유효 프레임이면 뭐든 하트비트로 친다).
        self.build_and_send('HB')
        with self.conn_lock:
            status = '연결됨' if self.conn else '미연결'
        self.get_logger().debug(f'ESP32 #1 상태: {status}')

    # ── 이 함수 추가 ──
    def check_timeout(self):
        elapsed = time.time() - self.last_recv_time
        if self.conn and elapsed > 2.0:
            self.get_logger().error('ESP32 #1 응답 없음! 연결 끊김 판정')
            with self.conn_lock:
                self.conn = None



def main(args=None):
    rclpy.init(args=args)
    node = AmrBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
