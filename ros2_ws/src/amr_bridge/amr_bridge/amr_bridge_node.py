"""
AMR ESP32 #1과 TCP로 통신하며 이동 명령을 ROS2 토픽과 연결하는 브릿지 노드.
하트비트를 DRIVE로 전달하는 heartbeat_cb 포함.
센서 데이터(가스/화염/거리)는 sensor_bridge(포트 8765)가 담당함, 이 노드는 죽은 SENS 파싱이 남아있음.
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
    def __init__(self):
        super().__init__('amr_bridge')

        self.pub_sensors = self.create_publisher(String,  '/amr/sensors',     10)
        self.pub_gas     = self.create_publisher(String,  '/amr/gas',         10)
        self.pub_temp    = self.create_publisher(String,  '/amr/temp',        10)
        self.pub_battery = self.create_publisher(Float32, '/amr/battery',     10)
        self.pub_near    = self.create_publisher(Bool,    '/amr/object_near', 10)
        # 수정: 연결 상태 발행 추가함, 대시보드가 amr_connected로 구독함
        self.pub_connected = self.create_publisher(String, '/amr/connected', 10)

        self.conn = None
        self.conn_lock = threading.Lock()
        self.last_recv_time = time.time()
        self.create_timer(0.5, self.check_timeout)

        self.create_subscription(
            Twist, '/amr/cmd_vel', self.cmd_vel_cb, 10
        )
        self.create_subscription(String, '/mission/heartbeat', self.heartbeat_cb, 10)
        # 수정: mission_orchestrator가 /amr/emergency로 보내는 STOP을 받는 구독 추가함
        # 이전엔 emergency_stop 메서드가 아무도 안 부르는 죽은 코드였음
        self.create_subscription(String, '/amr/emergency', self.emergency_cb, 10)

        threading.Thread(target=self.tcp_server, daemon=True).start()

        self.create_timer(0.5, self.heartbeat)
        # 수정: 연결 상태를 1초마다 발행하는 타이머 추가함
        self.create_timer(1.0, self.publish_connected)

        self.get_logger().info('AMR Bridge 노드 시작함')

    def tcp_server(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((HOST, AMR_PORT))
            server.listen(1)
            self.get_logger().info(f'포트 {AMR_PORT} 에서 ESP32 #1 대기중')

            while rclpy.ok():
                try:
                    conn, addr = server.accept()
                    self.get_logger().info(f'ESP32 #1 연결됨 IP: {addr[0]}')
                    with self.conn_lock:
                        self.conn = conn
                    threading.Thread(
                        target=self.recv_loop,
                        args=(conn,),
                        daemon=True
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

            except ConnectionResetError:
                self.get_logger().warn('ESP32 #1 연결 끊김')
                break
            except Exception as e:
                self.get_logger().warn(f'수신 오류: {e}')
                break

        with self.conn_lock:
            self.conn = None
        self.get_logger().warn('ESP32 #1 연결 종료됨, 재접속 대기중')

    STATE_NAMES  = ['SAFE', 'WARNING', 'DANGER', 'STOP', 'SENSOR_ERROR']
    ACTION_NAMES = ['NORMAL_MOTION', 'LIMITED_MOTION', 'STOP_MOTION']
    FAULT_NAMES  = ['OK', 'ESTOP', 'LIPO', 'SENSOR', 'RPI_TIMEOUT', 'HAZARD']

    def parse_msg(self, line: str):
        # 참고: 이 SENS 블록은 sensor_bridge 분리 이전 구조가 남아있는 죽은 코드로 보임
        # ESP32가 실제로 이 필드 조합을 이 포트로 보내는지 확인 후 정리 필요함
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

            gas_msg = String()
            gas_msg.data = json.dumps({'gas': gas, 'flag': data['state']})
            self.pub_gas.publish(gas_msg)

            temp_msg = String()
            temp_msg.data = json.dumps({'temp': 0.0, 'flame': int(flame)})
            self.pub_temp.publish(temp_msg)

            batt_msg = Float32()
            batt_msg.data = data['battery_v']
            self.pub_battery.publish(batt_msg)

            self.get_logger().info(
                f'SENS 수신: gas={gas} flame={flame} '
                f'batt={data["battery_v"]}V state={data["state"]} '
                f'action={data["action"]} fault={data["fault"]}'
            )

        else:
            self.get_logger().debug(f'알 수 없는 CMD: {cmd}')

    def verify_checksum(self, parts: list) -> bool:
        try:
            received_cs = int(parts[-1])
            data_str = ','.join(parts[:-1])
            calculated = sum(ord(c) for c in data_str) % 256
            return received_cs == calculated
        except (ValueError, IndexError):
            return False

    def calc_checksum(self, *fields) -> int:
        data_str = ','.join(str(f) for f in fields)
        return sum(ord(c) for c in data_str) % 256

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
                self.get_logger().warn('ESP32 #1 미연결 상태, 명령 전송 불가')

    def cmd_vel_cb(self, msg: Twist):
        linear  = msg.linear.x
        angular = msg.angular.z

        left  = int((linear - angular) * 150)
        right = int((linear + angular) * 150)
        left  = max(-255, min(255, left))
        right = max(-255, min(255, right))

        self.build_and_send('MOVE', left, right)

    def emergency_stop(self):
        self.get_logger().error('AMR 비상 정지함')
        self.build_and_send('STOP')

    def emergency_cb(self, msg: String):
        self.get_logger().error(f'/amr/emergency 수신: {msg.data}, 비상 정지 실행함')
        self.emergency_stop()

    def heartbeat_cb(self, msg: String):
        self.build_and_send('HB')

    def heartbeat(self):
        with self.conn_lock:
            status = '연결됨' if self.conn else '미연결'
        self.get_logger().debug(f'ESP32 #1 상태: {status}')

    def check_timeout(self):
        elapsed = time.time() - self.last_recv_time
        if self.conn and elapsed > 2.0:
            self.get_logger().error('ESP32 #1 응답 없음, 연결 끊김 판정함')
            with self.conn_lock:
                self.conn = None

    # 수정: 연결 상태를 문자열 true/false로 발행함, dashboard_node의 amr_connected_cb와 짝맞춤
    def publish_connected(self):
        with self.conn_lock:
            connected = self.conn is not None
        msg = String()
        msg.data = 'true' if connected else 'false'
        self.pub_connected.publish(msg)


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