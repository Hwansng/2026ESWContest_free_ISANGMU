# 🔴 긴급 — `amr_bridge_node.py` 파일 손상 복구

| | |
|---|---|
| 작성 | 2026-08-29 · 승환 |
| 대상 | `jinu-rpi5-restore` 브랜치, `ros2_ws/src/amr_bridge/amr_bridge/amr_bridge_node.py` |
| 성격 | 🔴 **최우선.** DRIVE와의 TCP 통신 자체가 지금 브랜치에 없다 |

---

## 0. 무슨 일이 있었나

지금 HEAD(`2a643f8`, "신호 수정")의 `amr_bridge_node.py`를 열어보면 **`mission_orchestrator_node.py`의 내용이 그대로 들어가 있다**(`class AmrBridge` 자리에 `class MissionOrchestrator`가 있음). 커밋 이력으로 확인함:

- 직전 커밋 `b7e1f84`("amr_bridge/arm_bridge 타임아웃 감지 수정")에서는 `amr_bridge_node.py`가 **정상**이었고, `last_recv_time` 타임아웃 버그도 정확히 고쳐져 있었다
- 바로 다음 커밋 `2a643f8`에서 mission_orchestrator를 고치다가 **그 내용이 amr_bridge_node.py 파일에 실수로 덮어써진 것**으로 보임 (아마 저장할 때 파일을 잘못 지정했거나, 복사-붙여넣기 실수)

**영향**: DRIVE(포트 5000) TCP 서버 자체가 없다. MOVE/STOP/HB 전달, `/amr/object_near`, `/amr/connected` 전부 안 되고, 새로 추가한 RETURN 흐름(`/amr/return_request`↔DRIVE)도 당연히 안 된다.

## 1. 복구 방법 — `b7e1f84` 기준 + RETURN 릴레이 추가

`b7e1f84`의 정상 버전을 그대로 되살리고, 거기에 지금 `mission_orchestrator`가 새로 요구하는 두 가지만 얹었다:

- `/amr/return_request` 구독 → 받으면 DRIVE로 `<RETURN,CS>` 전송
- DRIVE의 `<RETDONE,CS>` 수신 → `/amr/return_complete` 발행 (mission_orchestrator의 `return_complete_cb`가 이걸 기다림)
- 겸사겸사 DRIVE의 `<DETECT,CS>`(정지 마커 도달, 8/28 승환이 펌웨어에 추가한 것)도 `/amr/object_near`로 연결해뒀다 — 이전엔 dist 임계값으로만 판정하고 있었는데, 마커 도달 시점에도 한 번 더 트리거되는 것뿐이라 무해하다

**`b7e1f84` 이후 다른 의도된 변경은 없다** — 순수 복구 + RETURN 릴레이 추가만이다.

```python
"""
AMR ESP32 #1(DRIVE)과 TCP로 통신하며 이동 명령을 ROS2 토픽과 연결하는 브릿지 노드.
하트비트를 DRIVE로 전달하는 heartbeat_cb 포함.
가스/화염/거리 등 ENV 데이터는 sensor_bridge(포트 8765)가 담당함.
DRIVE가 보내는 SENS 프레임 자체는 살아있고, 이 노드는 그중 battCv/dist만 실제로 씀.

2026-08-29 복구 + RETURN 릴레이 추가 — 커밋 2a643f8("신호 수정")에서 이 파일이
mission_orchestrator_node.py 내용으로 통째로 덮어써졌던 것을 b7e1f84(직전 정상
커밋) 기준으로 복구하고, 그 위에 mission_orchestrator의 새 RETURN 흐름이 요구하는
릴레이만 추가함. b7e1f84 이후의 다른 의도된 변경은 없음.
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
        # 2026-08-29 추가 — mission_orchestrator 가 RETURN 상태에서 DRIVE 의
        # 후진 완료(<RETDONE,CS>)를 기다린다. 이걸로 알려준다.
        self.pub_return_complete = self.create_publisher(String, '/amr/return_complete', 10)

        self.conn = None
        self.conn_lock = threading.Lock()
        self.last_recv_time = time.time()
        self.create_timer(0.5, self.check_timeout)

        self.create_subscription(
            Twist, '/amr/cmd_vel', self.cmd_vel_cb, 10
        )
        self.create_subscription(String, '/mission/heartbeat', self.heartbeat_cb, 10)
        self.create_subscription(String, '/amr/emergency', self.emergency_cb, 10)
        # 2026-08-29 추가 — mission_orchestrator 가 RETURN 상태 진입 시 여기로
        # 'BACKUP' 을 보낸다(페이로드 내용은 안 본다, 신호로만 씀). DRIVE 의
        # esp32_drive_tcp.ino 는 <RETURN,CS> 수신만으로 개루프 후진을 시작한다.
        self.create_subscription(String, '/amr/return_request', self.return_request_cb, 10)

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
    #              <DETECT,CS> · <RETDONE,CS>  (2026-08-28, esp32_drive_tcp.ino 추가분)
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

        # 2026-08-29 추가 — DRIVE 의 정지 마커 도달 신호. 지금은 그대로 object_near
        # 로 흘려보낸다(vision_node 가 그걸로 캡처 트리거를 건다). dist 기반 판정과
        # 겹쳐도 무해함 — 둘 다 True 를 보낼 뿐이라 vision_node 쪽은 한 번 더 도는 것뿐.
        elif cmd == 'DETECT':
            self.pub_near.publish(Bool(data=True))
            self.get_logger().info('DETECT 수신 — /amr/object_near=True 발행')

        # 2026-08-29 추가 — RETURN(후진) 완료. mission_orchestrator.return_complete_cb 가
        # 이걸 받아 RETURN → IDLE 로 전이한다. 페이로드 내용은 안 본다, 신호로만 씀.
        elif cmd == 'RETDONE':
            self.pub_return_complete.publish(String(data='done'))
            self.get_logger().info('RETDONE 수신 — /amr/return_complete 발행')

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

    # 2026-08-29 추가
    def return_request_cb(self, msg: String):
        self.get_logger().warn(f'/amr/return_request 수신: {msg.data} — <RETURN> 전송')
        self.build_and_send('RETURN')

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
```

`py_compile`로 문법 검증만 했고, rclpy·실물 DRIVE 연결로는 검증 못 했다.

---

## 2. 확인 요청 — `/amr/return_request` 페이로드

`mission_orchestrator.py`의 `RETURN` 상태 진입 시 `pub_return_request.publish(String(data='BACKUP'))`로 고정 문자열을 보내고 있다. 위 복구본의 `return_request_cb`는 페이로드 내용을 안 보고 그냥 `<RETURN>`을 보내는데, 혹시 나중에 "왜 후진하는지"(화염 위치, 세기 등)를 DRIVE에 같이 넘길 계획이 있으면 지금 미리 말해달라 — 지금 구조로는 신호 하나뿐이라 그 정보가 안 넘어간다.

## 3. 남은 것

- `arm_act_node.py` ACT 패치는 어제 보낸 `ACT_ROS2통합_진우_2026-08-29.md` 그대로 유효함 — 아직 미반영
- 이 파일 복구되면 실물로 DRIVE 붙여서 `<RETURN>`/`<RETDONE>`/`<DETECT>` 왕복부터 확인하는 게 순서
