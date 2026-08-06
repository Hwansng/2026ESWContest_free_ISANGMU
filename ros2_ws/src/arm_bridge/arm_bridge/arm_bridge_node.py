"""
ARM ESP32 #2와 TCP로 통신하며 서보 명령/피드백을 ROS2 토픽과 연결하는 브릿지 노드.
"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import socket, threading, json, time

ARM_PORT = 5001   # ESP32 #2가 접속할 포트

class ArmBridge(Node):
    def __init__(self):
        super().__init__('arm_bridge')

        # Publisher: ESP32 #2 서보 피드백 → ROS2
        self.pub_feedback = self.create_publisher(
            String, '/arm/servo_feedback', 10
        )

        # Subscribers: ROS2 명령 → ESP32 #2
        self.create_subscription(String, '/arm/command',    self.arm_cmd_cb,  10)
        self.create_subscription(String, '/arm/led_cmd',    self.led_cb,      10)
        self.create_subscription(String, '/arm/buzzer_cmd', self.buzzer_cb,   10)
        self.create_subscription(String, '/arm/grip_cmd',   self.grip_cb,     10)
        self.conn = None
        self.conn_lock = threading.Lock()

        threading.Thread(target=self.tcp_server, daemon=True).start()
        self.create_timer(0.5, self.heartbeat)
        self.get_logger().info('ARM Bridge 노드 시작!')

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
                    threading.Thread(
                        target=self.recv_loop, args=(conn,), daemon=True
                    ).start()
                except Exception as e:
                    self.get_logger().error(f'서버 오류: {e}')
                    time.sleep(1)

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
        self.get_logger().warn('ESP32 #2 연결 종료.')

    def parse_msg(self, line: str):
        if not (line.startswith('<') and line.endswith('>')):
            return
        parts = line[1:-1].split(',')
        if not self.verify_checksum(parts):
            return

        if parts[0] == 'SFBACK' and len(parts) >= 6:
            # <SFBACK,id,pos,load,temp,CS>
            data = {
                'id':   int(parts[1]),
                'pos':  int(parts[2]),
                'load': int(parts[3]),
                'temp': int(parts[4])
            }
            msg = String()
            msg.data = json.dumps(data)
            self.pub_feedback.publish(msg)

    def verify_checksum(self, parts):
        try:
            received = int(parts[-1])
            data_str = ','.join(parts[:-1])
            return sum(ord(c) for c in data_str) % 256 == received
        except:
            return False

    def calc_checksum(self, *fields):
        return sum(ord(c) for c in ','.join(str(f) for f in fields)) % 256

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

    def arm_cmd_cb(self, msg: String):
        # msg.data 예시: "90,45,120,80,135,30"
        angles = msg.data.strip().split(',')
        self.build_and_send('ARM', *angles)

    def led_cb(self, msg: String):
        # msg.data 예시: "2" (0=초록 1=주황 2=빨강 3=흰색)
        self.build_and_send('LED', msg.data.strip())

    def grip_cb(self, msg: String):
        # msg.data 예시: "CLOSE,80" 또는 "OPEN,0"
        parts = msg.data.strip().split(',')
        if len(parts) >= 2:
            direction, threshold = parts[0], parts[1]
            self.build_and_send('GRIP', direction, threshold)
            self.get_logger().info(f'GRIP 명령 전송: {direction} 임계값={threshold}%')

    def buzzer_cb(self, msg: String):
        # msg.data 예시: "1" (1=경보 0=정지)
        self.build_and_send('BUZZ', msg.data.strip())

    def emergency_stop(self):
        self.get_logger().error('!!! ARM 비상 정지 !!!')
        self.build_and_send('STOP')

    def heartbeat(self):
        with self.conn_lock:
            status = '연결됨' if self.conn else '미연결'
        self.get_logger().debug(f'ESP32 #2 상태: {status}')


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
