"""
ARM ESP32 #2와 TCP로 통신하며 서보 명령/피드백을 ROS2 토픽과 연결하는 브릿지 노드.
"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import socket, threading, json, time

ARM_PORT = 5001

class ArmBridge(Node):
    # 노드 초기화: 토픽 구독/발행 설정
    def __init__(self):
        super().__init__('arm_bridge')

        self.pub_feedback = self.create_publisher(String, '/arm/servo_feedback', 10)

        self.create_subscription(String, '/arm/command',    self.arm_cmd_cb,  10)
        self.create_subscription(String, '/arm/led_cmd',    self.led_cb,      10)
        self.create_subscription(String, '/arm/buzzer_cmd', self.buzzer_cb,   10)

        self.conn = None
        self.conn_lock = threading.Lock()

        threading.Thread(target=self.tcp_server, daemon=True).start()
        self.create_timer(0.5, self.heartbeat)
        self.get_logger().info('ARM Bridge 노드 시작!')

    # TCP 서버 소켓을 열고 클라이언트(ESP32) 접속을 계속 대기
    def tcp_server(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(('0.0.0.0', ARM_PORT))
            server.listen(1)
            self.get_logger().info(f'포트 {ARM_PORT} 에서 ESP32 #2 기다리는 중...')
            while rclpy.ok():
                try:
                    conn, addr = server.accept()
                    self.get_logger().info(f'ESP32 #2 연결됨! IP: {addr[0]}')
                    with self.conn_lock:
                        self.conn = conn
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

    # <CMD,...> 형식 메시지를 검증하고 필드별로 파싱해 토픽 발행
    def parse_msg(self, line: str):
        if not (line.startswith('<') and line.endswith('>')):
            return
        parts = line[1:-1].split(',')
        if not self.verify_checksum(parts):
            return
        if parts[0] == 'SFBACK' and len(parts) >= 6:
            data = {'id': int(parts[1]), 'pos': int(parts[2]), 'load': int(parts[3]), 'temp': int(parts[4])}
            msg = String(); msg.data = json.dumps(data)
            self.pub_feedback.publish(msg)

    # 메시지 끝의 체크섬이 payload와 일치하는지 검증
    def verify_checksum(self, parts):
        try:
            received = int(parts[-1])
            data_str = ','.join(parts[:-1])
            return sum(ord(c) for c in data_str) % 256 == received
        except:
            return False

    # 필드들을 합쳐 체크섬(ASCII 합 % 256) 계산
    def calc_checksum(self, *fields):
        return sum(ord(c) for c in ','.join(str(f) for f in fields)) % 256

    # 체크섬을 붙여 <CMD,...> 형식으로 조립 후 소켓 전송
    def build_and_send(self, *fields):
        cs = self.calc_checksum(*fields)
        msg = '<' + ','.join(str(f) for f in fields) + f',{cs}>\n'
        with self.conn_lock:
            if self.conn:
                try:
                    self.conn.sendall(msg.encode())
                except Exception as e:
                    self.get_logger().warn(f'ARM 송신 실패: {e}')
            else:
                self.get_logger().warn('ESP32 #2 미연결')

    # /arm/command 콜백: 6축 각도 문자열을 ARM 명령으로 전송
    def arm_cmd_cb(self, msg: String):
        angles = msg.data.strip().split(',')
        self.build_and_send('ARM', *angles)

    # /arm/led_cmd 콜백: LED 색상 명령 전송
    def led_cb(self, msg: String):
        self.build_and_send('LED', msg.data.strip())

    # /arm/buzzer_cmd 콜백: 부저 명령 전송
    def buzzer_cb(self, msg: String):
        self.build_and_send('BUZZ', msg.data.strip())

    # STOP 명령 전송 (비상 정지)
    def emergency_stop(self):
        self.build_and_send('STOP')

    # 연결 상태를 주기적으로 디버그 로그로 출력
    def heartbeat(self):
        with self.conn_lock:
            status = '연결됨' if self.conn else '미연결'
        self.get_logger().debug(f'ESP32 #2 상태: {status}')


# 노드 초기화 후 스핀 시작, 종료 시 안전하게 정리
def main(args=None):
    rclpy.init(args=args)
    node = ArmBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
