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

        self.pub_feedback = self.create_publisher(
            String, '/arm/servo_feedback', 10
        )
        self.pub_connected = self.create_publisher(String, '/arm/connected', 10)

        self.create_subscription(String, '/arm/command',    self.arm_cmd_cb,  10)
        self.create_subscription(String, '/arm/led_cmd',    self.led_cb,      10)
        self.create_subscription(String, '/arm/buzzer_cmd', self.buzzer_cb,   10)
        self.create_subscription(String, '/arm/grip_cmd',   self.grip_cb,     10)
        self.create_subscription(String, '/arm/emergency', self.emergency_cb, 10)

        self.conn = None
        self.conn_lock = threading.Lock()
        # 수정: amr_bridge와 동일한 타임아웃 감지 패턴을 여기도 추가함
        # 기존엔 이 메커니즘 자체가 없어서, 소켓이 안 끊긴 half-open 상태에서
        # ESP32 #2가 멈춰도 arm_bridge는 영원히 연결됨으로 착각했음
        self.last_recv_time = time.time()

        threading.Thread(target=self.tcp_server, daemon=True).start()
        self.create_timer(0.5, self.heartbeat)
        self.create_timer(1.0, self.publish_connected)
        # 수정: 응답 없음 감지 타이머 신규 추가
        self.create_timer(0.5, self.check_timeout)
        self.get_logger().info('ARM Bridge 노드 시작함')

    def tcp_server(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(('0.0.0.0', ARM_PORT))
            server.listen(1)
            self.get_logger().info(f'포트 {ARM_PORT} 에서 ESP32 #2 대기중')
            while rclpy.ok():
                try:
                    conn, addr = server.accept()
                    self.get_logger().info(f'ESP32 #2 연결됨 IP: {addr[0]}')
                    with self.conn_lock:
                        self.conn = conn
                        # 수정: 접속 시점에도 갱신, amr_bridge와 동일 패턴
                        self.last_recv_time = time.time()
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
        self.get_logger().warn('ESP32 #2 연결 종료됨')

    def parse_msg(self, line: str):
        # 수정: 매 수신마다 last_recv_time 갱신, amr_bridge/sensor_bridge와 동일 패턴
        self.last_recv_time = time.time()

        if not (line.startswith('<') and line.endswith('>')):
            return
        parts = line[1:-1].split(',')
        # 수정: verify_checksum 호출 전 최소 필드 개수 방어 추가
        # amr_bridge/sensor_bridge엔 있는데 여기만 빠져있었음
        if len(parts) < 2 or not self.verify_checksum(parts):
            return

        if parts[0] == 'SFBACK' and len(parts) >= 6:
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
        except (ValueError, IndexError):
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
        angles = msg.data.strip().split(',')
        self.build_and_send('ARM', *angles)

    def led_cb(self, msg: String):
        self.build_and_send('LED', msg.data.strip())

    def grip_cb(self, msg: String):
        parts = msg.data.strip().split(',')
        if len(parts) >= 2:
            direction, threshold = parts[0], parts[1]
            self.build_and_send('GRIP', direction, threshold)
            self.get_logger().info(f'GRIP 명령 전송: {direction} 임계값={threshold}%')

    def buzzer_cb(self, msg: String):
        self.build_and_send('BUZZ', msg.data.strip())

    def emergency_stop(self):
        self.get_logger().error('ARM 비상 정지함')
        self.build_and_send('STOP')

    def emergency_cb(self, msg: String):
        self.get_logger().error(f'/arm/emergency 수신: {msg.data}, 비상 정지 실행함')
        self.emergency_stop()

    def heartbeat(self):
        with self.conn_lock:
            status = '연결됨' if self.conn else '미연결'
        self.get_logger().debug(f'ESP32 #2 상태: {status}')

    # 수정: amr_bridge와 동일한 타임아웃 판정 신규 추가
    # 소켓이 안 끊겨도 2초 이상 데이터가 안 오면 연결 끊김으로 판정함
    def check_timeout(self):
        elapsed = time.time() - self.last_recv_time
        if self.conn and elapsed > 2.0:
            self.get_logger().error('ESP32 #2 응답 없음, 연결 끊김 판정함')
            with self.conn_lock:
                self.conn = None

    def publish_connected(self):
        with self.conn_lock:
            connected = self.conn is not None
        msg = String()
        msg.data = 'true' if connected else 'false'
        self.pub_connected.publish(msg)


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