import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Bool, Float32
import socket
import threading
import json
import time

HOST = '0.0.0.0'
ENV_PORT = 8765   # ENV 보드 접속 포트

STATE_NAMES  = ['안전', '경고', '위험', '정지', '센서 오류']
ACTION_NAMES = ['정상 동작', '제한 동작', '정지']
FAULT_NAMES  = ['이상 없음', '비상정지', '배터리 저전압', '센서 오류', '라즈베리파이 통신 끊김', '가스·불꽃·근접 위험']


class SensorBridge(Node):
    def __init__(self):
        super().__init__('sensor_bridge')

        self.pub_gas      = self.create_publisher(String,  '/env/gas',      10)
        self.pub_flame    = self.create_publisher(String,  '/env/flame',    10)
        self.pub_battery  = self.create_publisher(Float32, '/env/battery',  10)
        self.pub_state    = self.create_publisher(String,  '/env/state',    10)
        self.pub_distance = self.create_publisher(String,  '/env/distance', 10)

        self.conn = None
        self.conn_lock = threading.Lock()
        self.last_recv_time = time.time()

        threading.Thread(target=self.tcp_server, daemon=True).start()
        self.create_timer(0.5, self.check_timeout)
        self.create_timer(0.5, self.heartbeat)

        self.get_logger().info('Sensor Bridge(ENV) 노드 시작함')

    def tcp_server(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((HOST, ENV_PORT))
            server.listen(1)
            self.get_logger().info(f'포트 {ENV_PORT} 에서 ENV 보드 대기중')

            while rclpy.ok():
                try:
                    conn, addr = server.accept()
                    self.get_logger().info(f'ENV 보드 연결됨 IP: {addr[0]}')
                    with self.conn_lock:
                        self.conn = conn
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
        self.get_logger().warn('ENV 보드 연결 종료됨, 재접속 대기중')

    # 수정: 실측 프로토콜은 10필드(DISTANCE 포함)이지만, 지금 붙은 firmware
    # (AMR_state_v11_ino.ino)는 DISTANCE 센서가 이 보드에 없어서 9필드(DISTANCE 없이)로 보냄
    # <SENS,MQ135,MQ2,FLAME,BAT,STATE,ACTION,FAULT,DISTANCE,CHECKSUM>  10필드, 거리센서 있는 보드용
    # <SENS,MQ135,MQ2,FLAME,BAT,STATE,ACTION,FAULT,CHECKSUM>           9필드,  지금 이 firmware
    # 둘 다 받아서, DISTANCE 없으면 None으로 처리함. 나중에 이 보드에 거리센서가
    # 추가돼서 firmware가 10필드로 바뀌어도 그대로 호환됨
    def parse_msg(self, line: str):
        self.last_recv_time = time.time()

        if not (line.startswith('<') and line.endswith('>')):
            return
        parts = line[1:-1].split(',')
        if len(parts) < 2 or not self.verify_checksum(parts):
            if len(parts) >= 2:
                self.get_logger().warn(f'체크섬 불일치: {line}')
            return

        cmd = parts[0]
        has_distance = len(parts) == 10
        has_no_distance = len(parts) == 9

        if cmd == 'SENS' and (has_distance or has_no_distance):
            mq135       = int(parts[1])
            mq2         = int(parts[2])
            flame       = int(parts[3])
            batt_cv     = int(parts[4])
            state_code  = int(parts[5])
            action_code = int(parts[6])
            fault_code  = int(parts[7])
            distance    = int(parts[8]) if has_distance else None   # -1이면 측정 실패, None이면 센서 자체가 없음

            self.pub_gas.publish(String(data=json.dumps({
                'mq135': mq135,
                'mq2': mq2,
            })))
            self.pub_flame.publish(String(data=json.dumps({'flame': int(flame)})))
            self.pub_battery.publish(Float32(data=batt_cv / 100.0))
            self.pub_distance.publish(String(data=json.dumps({
                'distance_mm': None if (distance is None or distance == -1) else distance,
            })))
            self.pub_state.publish(String(data=json.dumps({
                'state': STATE_NAMES[state_code] if state_code < len(STATE_NAMES) else f'UNKNOWN({state_code})',
                'action': ACTION_NAMES[action_code] if action_code < len(ACTION_NAMES) else f'UNKNOWN({action_code})',
                'fault': FAULT_NAMES[fault_code] if fault_code < len(FAULT_NAMES) else f'UNKNOWN({fault_code})',
            })))

            dist_str = '센서없음' if distance is None else ('측정실패' if distance == -1 else f'{distance}mm')
            self.get_logger().info(
                f'ENV SENS 수신: MQ135={mq135} MQ2={mq2} flame={flame} '
                f'batt={batt_cv/100.0}V distance={dist_str}'
            )
        else:
            self.get_logger().debug(f'필드 개수 불일치({len(parts)}개) 또는 알 수 없는 CMD: {line}')

    def verify_checksum(self, parts):
        try:
            received_cs = int(parts[-1])
            data_str = ','.join(parts[:-1])
            return sum(ord(c) for c in data_str) % 256 == received_cs
        except (ValueError, IndexError):
            return False

    def check_timeout(self):
        elapsed = time.time() - self.last_recv_time
        if self.conn and elapsed > 2.0:
            self.get_logger().error('ENV 보드 응답 없음, 연결 끊김 판정함')
            with self.conn_lock:
                self.conn = None

    def heartbeat(self):
        with self.conn_lock:
            status = '연결됨' if self.conn else '미연결'
        self.get_logger().debug(f'ENV 보드 상태: {status}')


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