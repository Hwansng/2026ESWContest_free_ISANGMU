"""
AMR ESP32 #1(DRIVE)과 TCP로 통신하며 이동 명령을 ROS2 토픽과 연결하는 브릿지 노드.
하트비트를 DRIVE로 전달하는 heartbeat_cb 포함.
가스/화염/거리 등 ENV 데이터는 sensor_bridge(포트 8765)가 담당함.
DRIVE가 보내는 SENS 프레임 자체는 살아있고, 이 노드는 그중 battCv/dist만 실제로 씀.
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

# 수정: dist 기준 근접 판정 임계값, 잠정값임, 강희 실측 후 조정 필요
OBJECT_NEAR_THRESHOLD_MM = 100


class AmrBridge(Node):
    def __init__(self):
        super().__init__('amr_bridge')

        # 수정: /amr/gas, /amr/temp 죽은 퍼블리셔 삭제함
        # hazard_detector, dashboard가 전부 /env/*로 옮겨가서 받는 곳이 없었음
        self.pub_battery  = self.create_publisher(Float32, '/amr/battery',     10)
        self.pub_near     = self.create_publisher(Bool,    '/amr/object_near', 10)
        self.pub_connected = self.create_publisher(String, '/amr/connected', 10)

        self.conn = None
        self.conn_lock = threading.Lock()
        self.last_recv_time = time.time()
        self.create_timer(0.5, self.check_timeout)

        self.create_subscription(
            Twist, '/amr/cmd_vel', self.cmd_vel_cb, 10
        )
        self.create_subscription(String, '/mission/heartbeat', self.heartbeat_cb, 10)
        self.create_subscription(String, '/amr/emergency', self.emergency_cb, 10)

        threading.Thread(target=self.tcp_server, daemon=True).start()

        self.create_timer(0.5, self.heartbeat)
        self.create_timer(1.0, self.publish_connected)

        self.get_logger().info('AMR Bridge 노드 시작함')

    def tcp_server(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((HOST, AMR_PORT))
            server.listen(1)
            self.get_logger().info(f'포트 {AMR_PORT} 에서 DRIVE 대기중')

            while rclpy.ok():
                try:
                    conn, addr = server.accept()
                    self.get_logger().info(f'DRIVE 연결됨 IP: {addr[0]}')
                    with self.conn_lock:
                        self.conn = conn
                        # 수정: 접속 시점에도 last_recv_time 갱신함, parse_msg 진입 전
                        # 공백 구간 없이 타임아웃 판정이 바로 정상 동작하게 함
                        self.last_recv_time = time.time()
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
                self.get_logger().warn('DRIVE 연결 끊김')
                break
            except Exception as e:
                self.get_logger().warn(f'수신 오류: {e}')
                break

        with self.conn_lock:
            self.conn = None
        self.get_logger().warn('DRIVE 연결 종료됨, 재접속 대기중')

    STATE_NAMES  = ['SAFE', 'WARNING', 'DANGER', 'STOP', 'SENSOR_ERROR']
    ACTION_NAMES = ['NORMAL_MOTION', 'LIMITED_MOTION', 'STOP_MOTION']
    FAULT_NAMES  = ['OK', 'ESTOP', 'LIPO', 'SENSOR', 'RPI_TIMEOUT', 'HAZARD']

    # DRIVE 프레임: <SENS,gas,flame,battCv,state,action,fault,dist,stopIdx,CS>
    def parse_msg(self, line: str):
        # 수정: 이 줄이 핵심임. 매 수신마다 갱신 안 해서 접속 2초 뒤부터
        # 무조건 연결 끊김 판정 나던 버그. sensor_bridge에 넣었던 패턴을 그대로 옮김
        self.last_recv_time = time.time()

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

        # 수정: 필드 개수 조건은 건드리지 않음, DRIVE 프레임 포맷 자체는 그대로임
        if cmd == 'SENS' and len(parts) >= 8:
            batt_cv     = int(parts[3])
            fault_code  = int(parts[6])

            # 수정: dist, stopIdx는 있을 때만 파싱함, 아직 없는 구버전 프레임도 방어적으로 허용
            dist = int(parts[7]) if len(parts) >= 8 + 1 else None
            fault_name = self.FAULT_NAMES[fault_code] if fault_code < len(self.FAULT_NAMES) else f'UNKNOWN({fault_code})'

            batt_msg = Float32()
            batt_msg.data = batt_cv / 100.0
            self.pub_battery.publish(batt_msg)

            # 수정: pub_near가 선언만 되고 한 번도 publish 안 되던 문제.
            # dist가 임계값 이하이거나 fault가 HAZARD면 근접으로 판정해서 실제로 publish함
            if dist is not None:
                is_near = (dist != -1 and dist <= OBJECT_NEAR_THRESHOLD_MM) or (fault_name == 'HAZARD')
                self.pub_near.publish(Bool(data=is_near))

            dist_str = 'N/A' if dist is None else ('측정실패' if dist == -1 else f'{dist}mm')
            self.get_logger().info(
                f'DRIVE SENS 수신: batt={batt_cv/100.0}V dist={dist_str} fault={fault_name}'
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
                self.get_logger().warn('DRIVE 미연결 상태, 명령 전송 불가')

    def cmd_vel_cb(self, msg: Twist):
        linear  = msg.linear.x
        angular = msg.angular.z

        left  = int((linear - angular) * 150)
        right = int((linear + angular) * 150)
        left  = max(-255, min(255, left))
        right = max(-255, min(255, right))

        self.build_and_send('MOVE', left, right)

    def emergency_stop(self):
        self.get_logger().error('DRIVE 비상 정지함')
        self.build_and_send('STOP')

    def emergency_cb(self, msg: String):
        self.get_logger().error(f'/amr/emergency 수신: {msg.data}, 비상 정지 실행함')
        self.emergency_stop()

    def heartbeat_cb(self, msg: String):
        self.build_and_send('HB')

    def heartbeat(self):
        with self.conn_lock:
            status = '연결됨' if self.conn else '미연결'
        self.get_logger().debug(f'DRIVE 상태: {status}')

    def check_timeout(self):
        elapsed = time.time() - self.last_recv_time
        if self.conn and elapsed > 2.0:
            self.get_logger().error('DRIVE 응답 없음, 연결 끊김 판정함')
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
    node = AmrBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            node.build_and_send('STOP')
        except Exception:
            pass
        node.destroy_node()
        rclpy.shutdown()