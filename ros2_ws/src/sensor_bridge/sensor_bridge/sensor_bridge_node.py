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

VALID_ZONES = ('P1', 'P2')
PING_PERIOD_S = 1.0   # ESP32 RPI_TIMEOUT_MS(3000) 대비 여유있게 1초 주기


class SensorBridge(Node):
    def __init__(self):
        super().__init__('sensor_bridge')

        # ── Publishers: ENV 보드 데이터 → ROS2 토픽 ──
        self.pub_gas        = self.create_publisher(String, '/env/gas',        10)
        self.pub_temp       = self.create_publisher(String, '/env/temp',       10)
        self.pub_battery    = self.create_publisher(Float32, '/env/battery',   10)
        self.pub_state      = self.create_publisher(String, '/env/state',      10)
        self.pub_gas_result = self.create_publisher(String, '/env/gas_result', 10)

        self.conn = None
        self.conn_lock = threading.Lock()
        self.last_recv_time = time.time()

        # ── Subscriber: hazard_detector가 요청하는 가스 검사 ──
        self.create_subscription(
            String, '/hazard/gas_check_request', self.gas_check_request_cb, 10
        )

        threading.Thread(target=self.tcp_server, daemon=True).start()
        self.create_timer(0.5, self.check_timeout)
        self.create_timer(0.5, self.heartbeat)
        self.create_timer(PING_PERIOD_S, self.send_ping)

        self.get_logger().info('Sensor Bridge(ENV) 노드 시작!')

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
        self.get_logger().warn('ENV 보드 연결 종료. 재접속 대기 중...')

    # 실제 프로토콜(v11, 2026-08-29):
    #   <SENS,mq135,mq2,flame,battCv,stateCode,actionCode,faultCode,checksum>  (9 필드)
    #   <GAS_RESULT,zone,result,baseline,minimumRaw,weakPercent,checksum>      (7 필드)
    # 🔴 구버전(거리 포함 10필드) 파서였던 걸 v11에 맞춰 교체함 — 예전엔 SENS가 전부
    #    조용히 버려지고 있었다.
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
        if cmd == 'SENS' and len(parts) == 9:
            self._handle_sens(parts)
        elif cmd == 'GAS_RESULT' and len(parts) == 7:
            self._handle_gas_result(parts)
        else:
            self.get_logger().debug(f'필드 개수 불일치({len(parts)}개) 또는 알 수 없는 CMD: {line}')

    def _handle_sens(self, parts):
        mq135       = int(parts[1])
        mq2         = int(parts[2])
        flame       = int(parts[3])
        batt_cv     = int(parts[4])
        state_code  = int(parts[5])
        action_code = int(parts[6])
        fault_code  = int(parts[7])

        self.pub_gas.publish(String(data=json.dumps({
            'mq135': mq135,
            'mq2': mq2,
        })))
        self.pub_temp.publish(String(data=json.dumps({'flame': int(flame)})))
        self.pub_battery.publish(Float32(data=batt_cv / 100.0))
        self.pub_state.publish(String(data=json.dumps({
            'state': STATE_NAMES[state_code] if state_code < len(STATE_NAMES) else f'UNKNOWN({state_code})',
            'action': ACTION_NAMES[action_code] if action_code < len(ACTION_NAMES) else f'UNKNOWN({action_code})',
            'fault': FAULT_NAMES[fault_code] if fault_code < len(FAULT_NAMES) else f'UNKNOWN({fault_code})',
        })))

        self.get_logger().info(
            f'ENV SENS 수신: MQ135={mq135} MQ2={mq2} flame={flame} batt={batt_cv/100.0}V'
        )

    def _handle_gas_result(self, parts):
        zone, result, baseline, minimum_raw, weak_percent = parts[1:6]
        payload = {
            'zone': zone,
            'result': result,
            'baseline': int(baseline),
            'minimum_raw': int(minimum_raw),
            'weak_percent': int(weak_percent),
        }
        self.pub_gas_result.publish(String(data=json.dumps(payload)))
        self.get_logger().info(f'GAS_RESULT 수신: {payload}')

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
            self.get_logger().error('ENV 보드 응답 없음! 연결 끊김 판정')
            with self.conn_lock:
                self.conn = None

    def heartbeat(self):
        with self.conn_lock:
            status = '연결됨' if self.conn else '미연결'
        self.get_logger().debug(f'ENV 보드 상태: {status}')

    # ════════════════════════════════════════════
    # RPi → ENV 송신
    # ════════════════════════════════════════════
    def build_and_send(self, *fields):
        payload = ','.join(str(f) for f in fields)
        checksum = sum(ord(c) for c in payload) % 256
        frame = f'<{payload},{checksum}>\n'
        with self.conn_lock:
            if not self.conn:
                return
            try:
                self.conn.sendall(frame.encode())
            except Exception as e:
                self.get_logger().warn(f'송신 실패: {e}')

    def send_ping(self):
        self.build_and_send('CMD', 'PING')

    def gas_check_request_cb(self, msg: String):
        zone = msg.data.strip().upper()
        if zone not in VALID_ZONES:
            self.get_logger().warn(f'잘못된 GAS_CHECK 구역 요청 무시: {msg.data!r}')
            return
        self.build_and_send('CMD', 'GAS_CHECK', zone)
        self.get_logger().info(f'GAS_CHECK 송신: zone={zone}')


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
