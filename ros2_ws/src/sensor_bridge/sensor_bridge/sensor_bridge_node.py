"""
ENV 보드와 TCP로 통신하며 가스/화염/배터리/상태 데이터를 ROS2 토픽과 연결하는 브릿지 노드.
"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Float32
import socket, threading, json, time

HOST = '0.0.0.0'
ENV_PORT = 5002

STATE_NAMES  = ['SAFE', 'WARNING', 'DANGER', 'STOP', 'SENSOR_ERROR']
ACTION_NAMES = ['NORMAL_MOTION', 'LIMITED_MOTION', 'STOP_MOTION']
FAULT_NAMES  = ['OK', 'ESTOP', 'LIPO', 'SENSOR', 'RPI_TIMEOUT', 'HAZARD']

class SensorBridge(Node):
    # 노드 초기화: 토픽 구독/발행 설정
    def __init__(self):
        super().__init__('sensor_bridge')
        self.pub_gas     = self.create_publisher(String,  '/env/gas',     10)
        self.pub_temp    = self.create_publisher(String,  '/env/temp',    10)
        self.pub_battery = self.create_publisher(Float32, '/env/battery', 10)
        self.pub_state   = self.create_publisher(String,  '/env/state',   10)

        self.conn = None
        self.conn_lock = threading.Lock()
        self.last_recv_time = time.time()

        threading.Thread(target=self.tcp_server, daemon=True).start()
        self.create_timer(0.5, self.check_timeout)
        self.create_timer(0.5, self.heartbeat)
        self.get_logger().info('Sensor Bridge(ENV) 노드 시작!')

    # TCP 서버 소켓을 열고 클라이언트(ESP32) 접속을 계속 대기
    def tcp_server(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((HOST, ENV_PORT))
            server.listen(1)
            self.get_logger().info(f'포트 {ENV_PORT} 에서 ENV 보드 기다리는 중...')
            while rclpy.ok():
                try:
                    conn, addr = server.accept()
                    self.get_logger().info(f'ENV 보드 연결됨! IP: {addr[0]}')
                    with self.conn_lock:
                        self.conn = conn
                        self.last_recv_time = time.time()
                    threading.Thread(target=self.recv_loop, args=(conn,), daemon=True).start()
                except Exception as e:
                    self.get_logger().error(f'서버 오류: {e}')
                    time.sleep(1)

    # 연결된 소켓에서 개행 단위로 메시지를 읽어 파싱으로 넘김
    def recv_loop(self, conn):
        buf = ''
        while rclpy.ok():
            try:
                raw = conn.recv(256)
                if not raw:
                    break
                buf += raw.decode('utf-8', errors='ignore')
                while '\n' in buf:
                    line, buf = buf.split('\n', 1)
                    line = line.strip()
                    if line:
                        self.parse_msg(line)
            except Exception as e:
                self.get_logger().warn(f'수신 오류: {e}')
                break
        with self.conn_lock:
            self.conn = None
        self.get_logger().warn('ENV 보드 연결 종료. 재접속 대기 중...')

    # <CMD,...> 형식 메시지를 검증하고 필드별로 파싱해 토픽 발행
    def parse_msg(self, line: str):
        self.last_recv_time = time.time()
        if not (line.startswith('<') and line.endswith('>')):
            return
        parts = line[1:-1].split(',')
        if len(parts) < 2 or not self.verify_checksum(parts):
            return
        if parts[0] == 'SENS' and len(parts) >= 8:
            gas, flame, batt_cv = int(parts[1]), int(parts[2]), int(parts[3])
            state_code, action_code, fault_code = int(parts[4]), int(parts[5]), int(parts[6])

            self.pub_gas.publish(String(data=json.dumps({'gas': gas})))
            self.pub_temp.publish(String(data=json.dumps({'flame': int(flame)})))
            self.pub_battery.publish(Float32(data=batt_cv / 100.0))
            self.pub_state.publish(String(data=json.dumps({
                'state': STATE_NAMES[state_code] if state_code < len(STATE_NAMES) else f'UNKNOWN({state_code})',
                'action': ACTION_NAMES[action_code] if action_code < len(ACTION_NAMES) else f'UNKNOWN({action_code})',
                'fault': FAULT_NAMES[fault_code] if fault_code < len(FAULT_NAMES) else f'UNKNOWN({fault_code})',
            })))
            self.get_logger().info(f'ENV SENS 수신: gas={gas} flame={flame} batt={batt_cv/100.0}V')

    # 메시지 끝의 체크섬이 payload와 일치하는지 검증
    def verify_checksum(self, parts):
        try:
            received_cs = int(parts[-1])
            return sum(ord(c) for c in ','.join(parts[:-1])) % 256 == received_cs
        except (ValueError, IndexError):
            return False

    # check_timeout 처리
    def check_timeout(self):
        elapsed = time.time() - self.last_recv_time
        if self.conn and elapsed > 2.0:
            self.get_logger().error('ENV 보드 응답 없음! 연결 끊김 판정')
            with self.conn_lock:
                self.conn = None

    # 연결 상태를 주기적으로 디버그 로그로 출력
    def heartbeat(self):
        with self.conn_lock:
            status = '연결됨' if self.conn else '미연결'
        self.get_logger().debug(f'ENV 보드 상태: {status}')


# 노드 초기화 후 스핀 시작, 종료 시 안전하게 정리
def main(args=None):
    rclpy.init(args=args)
    node = SensorBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
