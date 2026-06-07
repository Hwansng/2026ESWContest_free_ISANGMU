"""
AMR ESP32 #1과 TCP로 통신하며 센서/이동 명령을 ROS2 토픽과 연결하는 브릿지 노드.
"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Bool, Float32
from geometry_msgs.msg import Twist
import socket
import threading
import json
import time

HOST = '0.0.0.0'
AMR_PORT = 5000

class AmrBridge(Node):
    # 노드 초기화: 토픽 구독/발행 설정
    def __init__(self):
        super().__init__('amr_bridge')

        self.pub_sensors = self.create_publisher(String,  '/amr/sensors',     10)
        self.pub_gas     = self.create_publisher(String,  '/amr/gas',         10)
        self.pub_temp    = self.create_publisher(String,  '/amr/temp',        10)
        self.pub_battery = self.create_publisher(Float32, '/amr/battery',     10)
        self.pub_near    = self.create_publisher(Bool,    '/amr/object_near', 10)

        self.create_subscription(Twist, '/amr/cmd_vel', self.cmd_vel_cb, 10)

        self.conn = None
        self.conn_lock = threading.Lock()

        threading.Thread(target=self.tcp_server, daemon=True).start()
        self.create_timer(0.5, self.heartbeat)

        self.get_logger().info('AMR Bridge 노드 시작!')

    # TCP 서버 소켓을 열고 클라이언트(ESP32) 접속을 계속 대기
    def tcp_server(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((HOST, AMR_PORT))
            server.listen(1)
            self.get_logger().info(f'포트 {AMR_PORT} 에서 ESP32 #1 기다리는 중...')
            while rclpy.ok():
                try:
                    conn, addr = server.accept()
                    self.get_logger().info(f'ESP32 #1 연결됨! IP: {addr[0]}')
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
        self.get_logger().warn('ESP32 #1 연결 종료. 재접속 대기 중...')

    # <CMD,...> 형식 메시지를 검증하고 필드별로 파싱해 토픽 발행
    def parse_msg(self, line: str):
        if not (line.startswith('<') and line.endswith('>')):
            return
        parts = line[1:-1].split(',')
        if len(parts) < 2:
            return
        if not self.verify_checksum(parts):
            self.get_logger().warn(f'체크섬 불일치: {line}')
            return

        cmd = parts[0]
        if cmd == 'SENS' and len(parts) >= 8:
            data = {'dist_mm': int(parts[1]), 'ir': [int(parts[i]) for i in range(2, 7)]}
            msg = String(); msg.data = json.dumps(data)
            self.pub_sensors.publish(msg)
            near = Bool(); near.data = (data['dist_mm'] < 150)
            self.pub_near.publish(near)
        elif cmd == 'GAS' and len(parts) >= 5:
            data = {'mq2': int(parts[1]), 'mq135': int(parts[2]), 'flag': parts[3]}
            msg = String(); msg.data = json.dumps(data)
            self.pub_gas.publish(msg)
        elif cmd == 'TEMP' and len(parts) >= 4:
            data = {'temp': float(parts[1]), 'flame': int(parts[2])}
            msg = String(); msg.data = json.dumps(data)
            self.pub_temp.publish(msg)
        elif cmd == 'BATT' and len(parts) >= 3:
            msg = Float32(); msg.data = float(parts[1])
            self.pub_battery.publish(msg)

    # 메시지 끝의 체크섬이 payload와 일치하는지 검증
    def verify_checksum(self, parts: list) -> bool:
        try:
            received_cs = int(parts[-1])
            data_str = ','.join(parts[:-1])
            return sum(ord(c) for c in data_str) % 256 == received_cs
        except (ValueError, IndexError):
            return False

    # 필드들을 합쳐 체크섬(ASCII 합 % 256) 계산
    def calc_checksum(self, *fields) -> int:
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
                    self.get_logger().warn(f'송신 실패: {e}')

    # /amr/cmd_vel 콜백: Twist 메시지를 좌/우 PWM으로 변환해 MOVE 전송
    def cmd_vel_cb(self, msg: Twist):
        linear, angular = msg.linear.x, msg.angular.z
        left  = max(-255, min(255, int((linear - angular) * 150)))
        right = max(-255, min(255, int((linear + angular) * 150)))
        self.build_and_send('MOVE', left, right)

    # STOP 명령 전송 (비상 정지)
    def emergency_stop(self):
        self.build_and_send('STOP')

    # 연결 상태를 주기적으로 디버그 로그로 출력
    def heartbeat(self):
        with self.conn_lock:
            status = '연결됨' if self.conn else '미연결'
        self.get_logger().debug(f'ESP32 #1 상태: {status}')


# 노드 초기화 후 스핀 시작, 종료 시 안전하게 정리
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
