#!/bin/bash
# ============================================================
# HazardBot RPi5 레이어 — Git 히스토리 재구성 스크립트
# (기존 팀 저장소 위에 브랜치로 이어붙이는 버전)
#
# 사전 준비 (반드시 스크립트 실행 전에 진우님이 직접 하세요 —
#  인증 정보가 필요한 clone은 Claude가 대신 할 수 없습니다):
#
#   git clone https://github.com/Hwansng/HazardBot.git
#   cd HazardBot
#
# 그 상태에서 이 스크립트를 저장소 루트에 놓고 실행하세요:
#   chmod +x reconstruct_git_history.sh
#   ./reconstruct_git_history.sh
#
# 동작 방식:
#   - 기존 저장소를 git init 하지 않습니다 (기존 히스토리 보존)
#   - main에서 새 브랜치(BRANCH_NAME)를 만들어 그 위에 11개 커밋을 쌓습니다
#   - 끝나면 push 안내만 하고, main에는 아무 영향 없습니다
#   - 이후 팀에 "일반 머지(non-squash)로 PR 부탁"이라고 요청하세요
#     (squash로 머지하면 11개 커밋이 1개로 뭉개집니다)
#
# 주의: 이 히스토리는 대화 중 오간 코드 스냅샷을 근거로 사후 재구성한
#   것입니다. 날짜는 실제 타임스탬프를 최대한 반영했지만 정확한 작업
#   시각과 다를 수 있습니다. PR 설명에 이 점을 명시하는 걸 추천합니다.
# ============================================================

set -e

# macOS(BSD sed)와 Linux(GNU sed) 둘 다 동작하는 sedi 래퍼
sedi() {
  if sed --version >/dev/null 2>&1; then
    sed -i "$@"          # GNU sed (Linux)
  else
    sed -i '' "$@"       # BSD sed (macOS)
  fi
}

BRANCH_NAME="docs/jinu-rpi5-history-reconstruction"

if [ ! -d ".git" ]; then
  echo "여기가 git 저장소 루트가 아닙니다."
  echo "먼저 'git clone https://github.com/Hwansng/HazardBot.git' 후"
  echo "그 폴더 안에서(cd HazardBot) 이 스크립트를 실행하세요."
  exit 1
fi

# main을 최신으로 갱신
git fetch origin
git checkout main
git pull origin main

# 이미 같은 이름의 브랜치가 있으면 중단 (실수로 두 번 실행 방지)
if git show-ref --verify --quiet "refs/heads/$BRANCH_NAME"; then
  echo "브랜치 '$BRANCH_NAME'가 이미 있습니다. 다시 만들려면 먼저 지우세요:"
  echo "  git branch -D $BRANCH_NAME"
  exit 1
fi

git checkout -b "$BRANCH_NAME"

# RPi5 레이어 코드가 들어갈 위치. 저장소 구조에 맞게 필요시 경로 조정하세요.
WORKDIR="$(pwd)/ros2_ws/src"
mkdir -p "$WORKDIR"
cd "$WORKDIR"

# .gitignore가 저장소 루트나 여기에 이미 없으면 추가
if [ ! -f "../../.gitignore" ] && [ ! -f ".gitignore" ]; then
cat > .gitignore << 'GITIGNORE_EOF'
build/
install/
log/
__pycache__/
*.pyc
config/secrets.yaml
GITIGNORE_EOF
fi

commit() {
  local date="$1"
  local msg="$2"
  export GIT_AUTHOR_NAME="진우"
  export GIT_AUTHOR_EMAIL="jinu@hazardbot.local"
  export GIT_COMMITTER_NAME="진우"
  export GIT_COMMITTER_EMAIL="jinu@hazardbot.local"
  export GIT_AUTHOR_DATE="$date"
  export GIT_COMMITTER_DATE="$date"
  git add -A
  git commit -q -m "$msg"
  echo "✅ 커밋: $msg (날짜: $date)"
}

mkpkg() {
  # mkpkg <pkg_name> <exec_name> <module_file> <description>
  local pkg="$1" exec="$2" module="$3" desc="$4"
  mkdir -p "$pkg/$pkg"
  touch "$pkg/$pkg/__init__.py"
  cat > "$pkg/setup.py" << EOF
from setuptools import setup

package_name = '$pkg'

setup(
    name=package_name,
    version='0.0.1',
    packages=[package_name],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='pi',
    maintainer_email='pi@todo.todo',
    description='$desc',
    license='MIT',
    entry_points={
        'console_scripts': [
            '$exec = $pkg.$module:main',
        ],
    },
)
EOF
  mkdir -p "$pkg/resource"
  touch "$pkg/resource/$pkg"
  cat > "$pkg/package.xml" << EOF
<?xml version="1.0"?>
<package format="3">
  <name>$pkg</name>
  <version>0.0.1</version>
  <description>$desc</description>
  <maintainer email="jinu@hazardbot.local">jinu</maintainer>
  <license>MIT</license>
  <depend>rclpy</depend>
  <depend>std_msgs</depend>
  <export>
    <build_type>ament_python</build_type>
  </export>
</package>
EOF
}

echo "================================================"
echo "M1. amr_bridge / arm_bridge 초기 TCP 브릿지 구현"
echo "================================================"

mkpkg amr_bridge amr_bridge_node amr_bridge_node "AMR ESP32 #1 TCP Bridge"
cat > amr_bridge/amr_bridge/amr_bridge_node.py << 'PYEOF'
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
PYEOF

mkpkg arm_bridge arm_bridge_node arm_bridge_node "ARM ESP32 #2 TCP Bridge"
cat > arm_bridge/arm_bridge/arm_bridge_node.py << 'PYEOF'
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
PYEOF

commit "2026-06-07 20:41:30 +0900" "feat: amr_bridge/arm_bridge TCP 브릿지 초기 구현

RPi5를 TCP 서버로, 양쪽 ESP32를 클라이언트로 하는 통신 구조.
<CMD,값1,...,체크섬> 프로토콜 표준화 (체크섬=ASCII합%256).
amr_bridge: 포트5000, SENS/GAS/TEMP/BATT 수신, MOVE/STOP 송신
arm_bridge: 포트5001, SFBACK 수신, ARM/LED/BUZZ 송신"

echo "================================================"
echo "M2. hazard_detector / arm_controller(IK) / mission_orchestrator / dashboard 초기 구현"
echo "================================================"

mkpkg hazard_detector hazard_detector_node hazard_detector_node "Hazard Detector Node"
cat > hazard_detector/hazard_detector/hazard_detector_node.py << 'PYEOF'
"""
센서/비전 데이터를 구역별 임계값과 비교해 위험 등급(L0~L3)을 판정하는 노드.
"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Int8
import json

class HazardDetector(Node):
    # 노드 초기화: 토픽 구독/발행 설정
    def __init__(self):
        super().__init__('hazard_detector')

        self.create_subscription(String, '/amr/gas',     self.gas_cb,    10)
        self.create_subscription(String, '/amr/temp',    self.temp_cb,   10)
        self.create_subscription(String, '/amr/sensors', self.sensor_cb, 10)
        self.create_subscription(String, '/vision/detected', self.vision_cb, 10)
        self.create_subscription(Int8,   '/mission/zone', self.zone_cb,  10)

        self.pub_hazard = self.create_publisher(String, '/hazard/detected', 10)

        self.current_zone = 1
        self.gas_data  = None
        self.temp_data = None

        self.zone_thresholds = {
            1: {'gas': 300, 'temp': 60},
            2: {'gas': 200, 'temp': 50},
            3: {'gas': 150, 'temp': 45},
        }

        self.get_logger().info('Hazard Detector 노드 시작!')

    # /mission/zone 콜백: 현재 구역 갱신
    def zone_cb(self, msg: Int8):
        self.current_zone = msg.data

    # /amr/gas 콜백: 가스 데이터 저장 후 위험도 재평가
    def gas_cb(self, msg: String):
        self.gas_data = json.loads(msg.data)
        self.evaluate_hazard()

    # /amr/temp 콜백: 온도/화염 데이터 처리, 화염이면 즉시 L3 발행
    def temp_cb(self, msg: String):
        self.temp_data = json.loads(msg.data)
        if self.temp_data.get('flame') == 1:
            self.publish_hazard(3, 'FLAME', 'KY-026 화염 감지')
            return
        self.evaluate_hazard()

    # /amr/sensors 콜백 (현재는 별도 처리 없음)
    def sensor_cb(self, msg: String):
        pass

    # /vision/detected 콜백: 감지 색상/방위각 로그 또는 상태 갱신
    def vision_cb(self, msg: String):
        data = json.loads(msg.data)
        self.get_logger().info(f'비전 감지: 색상={data.get("color")} 방위각={data.get("angle")}')

    # 가스/온도 값을 구역별 임계값과 비교해 위험 등급 판정
    def evaluate_hazard(self):
        if not self.gas_data or not self.temp_data:
            return

        zone = self.current_zone
        mq2, mq135 = self.gas_data.get('mq2', 0), self.gas_data.get('mq135', 0)
        temp = self.temp_data.get('temp', 0)
        flag = self.gas_data.get('flag', 'NORMAL')

        threshold = self.zone_thresholds.get(zone, self.zone_thresholds[1])
        gas_limit, temp_limit = threshold['gas'], threshold['temp']

        level, reason = 0, 'NORMAL'
        if flag == 'HIGH' and temp > temp_limit:
            level, reason = 3, '가스+고온 복합 위험'
        elif mq2 > gas_limit or mq135 > gas_limit:
            level, reason = 2, f'가스 초과 (ZONE {zone} 임계값 {gas_limit})'
        elif temp > temp_limit:
            level, reason = 2, f'온도 초과 ({temp}°C)'
        elif mq2 > gas_limit * 0.7 or temp > temp_limit * 0.8:
            level, reason = 1, '주의 수준'

        self.publish_hazard(level, reason, f'MQ2={mq2} MQ135={mq135} TEMP={temp}°C ZONE={zone}')

    # 판정된 위험 등급/사유를 /hazard/detected로 발행
    def publish_hazard(self, level: int, hazard_type: str, detail: str):
        data = {'level': level, 'type': hazard_type, 'detail': detail, 'zone': self.current_zone}
        msg = String(); msg.data = json.dumps(data)
        self.pub_hazard.publish(msg)
        self.get_logger().info(f'위험등급 L{level}: {hazard_type} | {detail}')


# 노드 초기화 후 스핀 시작, 종료 시 안전하게 정리
def main(args=None):
    rclpy.init(args=args)
    node = HazardDetector()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
PYEOF

mkpkg arm_controller arm_controller_node arm_controller_node "Arm Controller Node"
cat > arm_controller/arm_controller/arm_controller_node.py << 'PYEOF'
"""
목표 좌표를 기하학적 IK로 계산해 6축 서보 각도를 산출하는 로봇팔 제어 노드.
"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Int16
import json, math

class ArmController(Node):
    # 노드 초기화: 토픽 구독/발행 설정
    def __init__(self):
        super().__init__('arm_controller')

        self.create_subscription(String, '/hazard/detected',   self.hazard_cb,   10)
        self.create_subscription(String, '/arm/servo_feedback',self.feedback_cb, 10)
        self.create_subscription(Int16,  '/arm/wrist_preset',  self.wrist_cb,    10)

        self.pub_arm_cmd = self.create_publisher(String, '/arm/command', 10)

        self.joint_limits = {
            1: (0, 4095, 2048), 2: (170, 1877, 1024), 3: (0, 2048, 1024),
            4: (0, 2048, 1024), 5: (0, 2048, 1024), 6: (340, 1365, 340),
        }

        self.poses = {
            'HOME':      [2048, 1024, 1024, 1024, 1024, 340],
            'READY':     [2048, 800,  1200, 900,  1024, 340],
            'APPROACH':  [2048, 600,  1400, 800,  1024, 340],
            'GRIP_OPEN': [2048, 600,  1400, 800,  1024, 340],
            'GRIP_CLOSE':[2048, 600,  1400, 800,  1024, 900],
            'TRANSPORT': [2048, 1200, 800,  1024, 1024, 900],
            'ISOLATE':   [2048, 700,  1300, 900,  1024, 900],
        }

        # 링크 길이(mm, 추정치)
        self.L1, self.L2, self.L3, self.L4 = 0, 100, 100, 80

        self.get_logger().info('Arm Controller 노드 시작!')

    # /hazard/detected 콜백: 위험 등급에 따라 접근 동작 트리거
    def hazard_cb(self, msg: String):
        data = json.loads(msg.data)
        if data.get('level', 0) >= 2:
            self.move_to_pose('APPROACH')

    # /arm/servo_feedback 콜백: 과열/과부하 경고 또는 파지 판정
    def feedback_cb(self, msg: String):
        data = json.loads(msg.data)
        if data.get('temp', 0) > 70:
            self.get_logger().warn(f'서보 {data.get("id")} 과열! {data.get("temp")}°C')
        if data.get('load', 0) > 80:
            self.get_logger().warn(f'서보 {data.get("id")} 과부하! {data.get("load")}%')

    # /arm/wrist_preset 콜백: 손목 각도를 위치값으로 변환해 반영
    def wrist_cb(self, msg: Int16):
        pos = max(0, min(2048, int(msg.data / 180.0 * 2048)))
        poses = self.poses['APPROACH'].copy()
        poses[4] = pos
        self.publish_arm_command(poses)

    # 목표 좌표(x,y,z)를 코사인 법칙 기반으로 6축 각도로 역산
    def solve_ik(self, x, y, z, wrist_angle=90):
        """기하학적 IK: (x,y,z) -> 6축 각도 (코사인 법칙)"""
        base_angle = max(0, min(360, math.degrees(math.atan2(y, x)) + 180))
        r = math.sqrt(x**2 + y**2)
        d = math.sqrt(r**2 + (z - self.L1)**2)
        max_reach = self.L2 + self.L3
        if d > max_reach:
            d = max_reach * 0.95
        try:
            cos_elbow = max(-1, min(1, (self.L2**2 + self.L3**2 - d**2) / (2*self.L2*self.L3)))
            elbow_angle = math.degrees(math.acos(cos_elbow))
            cos_shoulder = max(-1, min(1, (self.L2**2 + d**2 - self.L3**2) / (2*self.L2*d)))
            shoulder_offset = math.degrees(math.acos(cos_shoulder))
            elevation = math.degrees(math.atan2(z - self.L1, r))
            shoulder_angle = elevation + shoulder_offset
        except (ValueError, ZeroDivisionError):
            return None
        wrist_pitch = 180 - shoulder_angle - elbow_angle
        angles = [base_angle, shoulder_angle, elbow_angle, wrist_pitch, wrist_angle, 30]
        return [max(0, min(4095, int(a / 360.0 * 4095))) for a in angles]

    # 포즈 테이블에서 이름으로 조회해 관절 한계값 검증 후 이동
    def move_to_pose(self, pose_name: str):
        if pose_name not in self.poses:
            return
        positions = self.poses[pose_name]
        validated = []
        for i, pos in enumerate(positions):
            min_p, max_p, _ = self.joint_limits[i + 1]
            validated.append(max(min_p, min(max_p, pos)))
        self.publish_arm_command(validated)

    # 6축 위치값을 문자열로 합쳐 /arm/command로 발행
    def publish_arm_command(self, positions: list):
        msg = String(); msg.data = ','.join(str(p) for p in positions)
        self.pub_arm_cmd.publish(msg)


# 노드 초기화 후 스핀 시작, 종료 시 안전하게 정리
def main(args=None):
    rclpy.init(args=args)
    node = ArmController()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
PYEOF

mkpkg mission_orchestrator mission_orchestrator_node mission_orchestrator_node "Mission Orchestrator FSM Node"
cat > mission_orchestrator/mission_orchestrator/mission_orchestrator_node.py << 'PYEOF'
"""
미션 전체 흐름(FSM)을 조율하는 노드.
"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Int8, Int16
import json

class MissionState:
    IDLE, PATROL, DETECTED, CLASSIFY = 'IDLE', 'PATROL', 'DETECTED', 'CLASSIFY'
    APPROACH, GRIP, TRANSPORT, ISOLATE = 'APPROACH', 'GRIP', 'TRANSPORT', 'ISOLATE'
    REPORT, EMERGENCY, HOME = 'REPORT', 'EMERGENCY', 'HOME'

class MissionOrchestrator(Node):
    # 노드 초기화: 토픽 구독/발행 설정
    def __init__(self):
        super().__init__('mission_orchestrator')

        self.create_subscription(String, '/hazard/detected',    self.hazard_cb,   10)
        self.create_subscription(String, '/vision/detected',    self.vision_cb,   10)
        self.create_subscription(String, '/arm/servo_feedback', self.feedback_cb, 10)
        self.create_subscription(String, '/amr/battery', self.battery_cb, 10)

        self.pub_state  = self.create_publisher(String, '/mission/state', 10)
        self.pub_zone   = self.create_publisher(Int8,   '/mission/zone', 10)
        self.pub_wrist  = self.create_publisher(Int16,  '/arm/wrist_preset', 10)
        self.pub_led    = self.create_publisher(String, '/arm/led_cmd', 10)
        self.pub_buzzer = self.create_publisher(String, '/arm/buzzer_cmd', 10)
        self.pub_amr_stop = self.create_publisher(String, '/amr/emergency', 10)
        self.pub_arm_stop = self.create_publisher(String, '/arm/emergency', 10)

        self.state = MissionState.IDLE
        self.current_zone = 1
        self.detected_color = None
        self.detected_angle = None

        self.create_timer(1.0, self.publish_state)

        self.get_logger().info('Mission Orchestrator 노드 시작!')
        self.transition(MissionState.PATROL)

    # FSM 상태 전이 처리 및 상태별 진입 동작 실행
    def transition(self, new_state: str):
        self.get_logger().info(f'FSM: {self.state} → {new_state}')
        self.state = new_state
        self.publish_state()

        if new_state == MissionState.PATROL:
            self.set_led('0'); self.set_buzzer('0')
        elif new_state == MissionState.DETECTED:
            self.set_led('1')
        elif new_state == MissionState.APPROACH:
            if self.detected_angle:
                self.pub_wrist.publish(Int16(data=int(self.detected_angle)))
        elif new_state == MissionState.EMERGENCY:
            self.set_led('2'); self.set_buzzer('1')
            self.emergency_stop_all()

    # /hazard/detected 콜백: 위험 등급에 따라 접근 동작 트리거
    def hazard_cb(self, msg: String):
        data = json.loads(msg.data)
        if data.get('type') == 'FLAME':
            self.transition(MissionState.EMERGENCY)
            return
        if data.get('level', 0) >= 2 and self.state == MissionState.PATROL:
            self.transition(MissionState.DETECTED)

    # /vision/detected 콜백: 감지 색상/방위각 로그 또는 상태 갱신
    def vision_cb(self, msg: String):
        data = json.loads(msg.data)
        self.detected_color = data.get('color')
        self.detected_angle = data.get('angle')
        if self.state == MissionState.DETECTED:
            self.transition(MissionState.CLASSIFY)
            self.transition(MissionState.APPROACH)

    # /arm/servo_feedback 콜백: 과열/과부하 경고 또는 파지 판정
    def feedback_cb(self, msg: String):
        data = json.loads(msg.data)
        if self.state == MissionState.GRIP:
            threshold = 40 if self.detected_color == 'yellow' else 80
            if data.get('load', 0) >= threshold:
                self.transition(MissionState.TRANSPORT)

    # /amr/battery 콜백: 저전압 감지 시 EMERGENCY 전이
    def battery_cb(self, msg):
        try:
            voltage = float(msg.data)
        except:
            voltage = 0.0
        if 0 < voltage < 9.9:
            self.transition(MissionState.EMERGENCY)

    # 양쪽 ESP32 비상 정지 처리 (또는 하트비트 중단)
    def emergency_stop_all(self):
        self.get_logger().error('!!! 양쪽 ESP32 동시 STOP !!!')
        stop_msg = String(); stop_msg.data = 'STOP'
        self.pub_amr_stop.publish(stop_msg)
        self.pub_arm_stop.publish(stop_msg)

    # 현재 미션 상태를 /mission/state, /mission/zone으로 발행
    def publish_state(self):
        msg = String()
        msg.data = json.dumps({'state': self.state, 'zone': self.current_zone,
                                'color': self.detected_color, 'angle': self.detected_angle})
        self.pub_state.publish(msg)

    # /arm/led_cmd로 LED 색상 값 발행
    def set_led(self, value: str):
        msg = String(); msg.data = value
        self.pub_led.publish(msg)

    # /arm/buzzer_cmd로 부저 값 발행
    def set_buzzer(self, value: str):
        msg = String(); msg.data = value
        self.pub_buzzer.publish(msg)


# 노드 초기화 후 스핀 시작, 종료 시 안전하게 정리
def main(args=None):
    rclpy.init(args=args)
    node = MissionOrchestrator()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
PYEOF

mkdir -p hazardbot_dashboard/hazardbot_dashboard hazardbot_dashboard/templates
touch hazardbot_dashboard/hazardbot_dashboard/__init__.py
cat > hazardbot_dashboard/hazardbot_dashboard/dashboard_node.py << 'PYEOF'
"""
ROS2 토픽 데이터를 Flask + SocketIO로 웹 대시보드에 실시간 표출하는 노드.
"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Float32
import json, threading, subprocess, os
from ament_index_python.packages import get_package_share_directory
from flask import Flask, render_template
from flask_socketio import SocketIO

pkg_share = get_package_share_directory('hazardbot_dashboard')
template_dir = os.path.join(pkg_share, 'templates')
app = Flask(__name__, template_folder=template_dir)
socketio = SocketIO(app, cors_allowed_origins='*')

dashboard_data = {
    'mission_state': 'IDLE', 'zone': 1,
    'sensors': {'dist_mm': 0, 'ir': [0,0,0,0,0]},
    'gas': {'mq2': 0, 'mq135': 0, 'flag': 'NORMAL'},
    'temp': {'temp': 0.0, 'flame': 0}, 'battery': 0.0,
    'hazard': {'level': 0, 'type': 'NORMAL'}, 'servo_feedback': {},
    'vision': {'color': None, 'angle': None},
    'rpi_health': {'cpu_temp': 0.0, 'throttled': '0x0'},
}

class DashboardNode(Node):
    # 노드 초기화: 토픽 구독/발행 설정
    def __init__(self):
        super().__init__('hazardbot_dashboard')
        self.create_subscription(String, '/mission/state', self.mission_cb, 10)
        self.create_subscription(String, '/amr/sensors',   self.sensor_cb, 10)
        self.create_subscription(String, '/amr/gas',       self.gas_cb, 10)
        self.create_subscription(String, '/amr/temp',      self.temp_cb, 10)
        self.create_subscription(Float32, '/amr/battery',  self.battery_cb, 10)
        self.create_subscription(String, '/hazard/detected', self.hazard_cb, 10)
        self.create_subscription(String, '/arm/servo_feedback', self.servo_cb, 10)
        self.create_subscription(String, '/vision/detected', self.vision_cb, 10)
        self.create_timer(5.0, self.check_rpi_health)
        self.create_timer(1.0, self.broadcast_data)
        self.get_logger().info('Dashboard 노드 시작!')

    # /mission/state 콜백: 대시보드 상태값 갱신
    def mission_cb(self, msg): d = json.loads(msg.data); dashboard_data['mission_state'] = d.get('state','IDLE'); dashboard_data['zone'] = d.get('zone',1)
    # /amr/sensors 콜백 (현재는 별도 처리 없음)
    def sensor_cb(self, msg): dashboard_data['sensors'] = json.loads(msg.data)
    # /amr/gas 콜백: 가스 데이터 저장 후 위험도 재평가
    def gas_cb(self, msg): dashboard_data['gas'] = json.loads(msg.data)
    # /amr/temp 콜백: 온도/화염 데이터 처리, 화염이면 즉시 L3 발행
    def temp_cb(self, msg): dashboard_data['temp'] = json.loads(msg.data)
    # /amr/battery 콜백: 저전압 감지 시 EMERGENCY 전이
    def battery_cb(self, msg): dashboard_data['battery'] = round(msg.data, 2)
    # /hazard/detected 콜백: 위험 등급에 따라 접근 동작 트리거
    def hazard_cb(self, msg): dashboard_data['hazard'] = json.loads(msg.data)
    # /arm/servo_feedback 콜백: 서보 ID별 상태 저장
    def servo_cb(self, msg):
        d = json.loads(msg.data)
        dashboard_data['servo_feedback'][str(d.get('id'))] = d
    # /vision/detected 콜백: 감지 색상/방위각 로그 또는 상태 갱신
    def vision_cb(self, msg): dashboard_data['vision'] = json.loads(msg.data)

    # vcgencmd로 RPi5 CPU 온도/스로틀링 상태 조회
    def check_rpi_health(self):
        try:
            temp_raw = subprocess.check_output(['vcgencmd', 'measure_temp']).decode().strip()
            cpu_temp = float(temp_raw.replace("temp=","").replace("'C",""))
            throttled = subprocess.check_output(['vcgencmd', 'get_throttled']).decode().strip().split('=')[1]
            dashboard_data['rpi_health'] = {'cpu_temp': cpu_temp, 'throttled': throttled}
        except Exception as e:
            self.get_logger().debug(f'헬스 체크 오류: {e}')

    # 누적된 상태를 WebSocket으로 브라우저에 전송
    def broadcast_data(self):
        socketio.emit('update', dashboard_data)


@app.route('/')
# / 라우트: 대시보드 메인 페이지 렌더링
def index():
    return render_template('index.html')


# 노드 초기화 후 스핀 시작, 종료 시 안전하게 정리
def main(args=None):
    rclpy.init(args=args)
    node = DashboardNode()
    flask_thread = threading.Thread(
        target=lambda: socketio.run(app, host='0.0.0.0', port=8080, debug=False, allow_unsafe_werkzeug=True),
        daemon=True)
    flask_thread.start()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
PYEOF

cat > hazardbot_dashboard/templates/index.html << 'HTMLEOF'
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8"><title>HazardBot Dashboard</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.min.js"></script>
<style>
body{background:#0a0a0a;color:#e0e0e0;font-family:monospace;padding:16px}
h1{text-align:center;color:#00ff88}
.card{background:#1a1a1a;border:1px solid #333;border-radius:8px;padding:16px;margin:8px}
</style>
</head>
<body>
<h1>HAZARDBOT DASHBOARD</h1>
<div class="card">MISSION STATE: <span id="mission-state">IDLE</span></div>
<div class="card">HAZARD LEVEL: <span id="hazard-level">L0</span></div>
<script>
const socket = io();
socket.on('update', (data) => {
    document.getElementById('mission-state').textContent = data.mission_state;
    document.getElementById('hazard-level').textContent = 'L' + (data.hazard.level || 0);
});
</script>
</body>
</html>
HTMLEOF

mkdir -p hazardbot_dashboard/launch
cat > hazardbot_dashboard/launch/hazardbot.launch.py << 'PYEOF'
"""
전체 ROS2 노드를 한 번에 실행하는 launch 설정.
"""
from launch import LaunchDescription
from launch_ros.actions import Node

# 전체 노드를 한 번에 실행하는 launch 구성 반환
def generate_launch_description():
    return LaunchDescription([
        Node(package='amr_bridge',          executable='amr_bridge_node'),
        Node(package='arm_bridge',          executable='arm_bridge_node'),
        Node(package='hazard_detector',     executable='hazard_detector_node'),
        Node(package='arm_controller',      executable='arm_controller_node'),
        Node(package='mission_orchestrator',executable='mission_orchestrator_node'),
        Node(package='hazardbot_dashboard', executable='dashboard_node'),
    ])
PYEOF

cat > hazardbot_dashboard/setup.py << 'PYEOF'
"""
hazardbot_dashboard 패키지 빌드/설치 설정.
"""
from setuptools import setup
import os
from glob import glob

package_name = 'hazardbot_dashboard'

setup(
    name=package_name,
    version='0.0.1',
    packages=[package_name],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='pi',
    maintainer_email='pi@todo.todo',
    description='HazardBot Web Dashboard',
    license='MIT',
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'templates'), glob('templates/*.html')),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.py')),
    ],
    entry_points={'console_scripts': ['dashboard_node = hazardbot_dashboard.dashboard_node:main']},
)
PYEOF
mkdir -p hazardbot_dashboard/resource
touch hazardbot_dashboard/resource/hazardbot_dashboard
cat > hazardbot_dashboard/package.xml << 'EOF'
<?xml version="1.0"?>
<package format="3">
  <name>hazardbot_dashboard</name>
  <version>0.0.1</version>
  <description>HazardBot Web Dashboard</description>
  <maintainer email="jinu@hazardbot.local">jinu</maintainer>
  <license>MIT</license>
  <depend>rclpy</depend>
  <depend>std_msgs</depend>
  <export><build_type>ament_python</build_type></export>
</package>
EOF

commit "2026-06-11 18:12:43 +0900" "feat: hazard_detector·arm_controller(IK)·mission_orchestrator·대시보드 초기 구현

- hazard_detector: 구역별 임계값 차등, MQ비율 분석, 화염 즉시 L3
- arm_controller: 기하학적 IK(코사인법칙) + 포즈테이블 + 관절한계검증
- mission_orchestrator: FSM (IDLE~REPORT/EMERGENCY), 양쪽ESP32 동시 STOP
- hazardbot_dashboard: Flask+SocketIO 실시간 웹 모니터링, launch 파일 포함"

echo "================================================"
echo "M3. vision_node 초기 구현 (cv2.VideoCapture 직접 오픈 방식)"
echo "================================================"

mkpkg vision_node vision_node vision_node "Vision Node OpenCV HSV"
cat > vision_node/vision_node/vision_node.py << 'PYEOF'
"""
카메라를 직접 열어(cv2.VideoCapture) HSV 색상 검출로 물체를 인식하는 비전 노드.
"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Bool
import json, cv2, numpy as np, threading

class VisionNode(Node):
    # 노드 초기화: 토픽 구독/발행 설정
    def __init__(self):
        super().__init__('vision_node')
        self.create_subscription(Bool, '/amr/object_near', self.trigger_cb, 10)
        self.pub_vision = self.create_publisher(String, '/vision/detected', 10)

        self.camera = None
        self.camera_active = False
        self.init_camera()

        self.hsv_ranges = {
            'red': [(np.array([0,120,70]), np.array([10,255,255])),
                    (np.array([170,120,70]), np.array([180,255,255]))],
            'yellow': [(np.array([20,100,100]), np.array([35,255,255]))],
        }
        self.get_logger().info('Vision Node 시작!')

    # cv2.VideoCapture로 카메라를 직접 열기 시도
    def init_camera(self):
        try:
            self.camera = cv2.VideoCapture(0)
            self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            if self.camera.isOpened():
                self.camera_active = True
                self.get_logger().info('카메라 연결 성공!')
            else:
                self.camera = None
                self.get_logger().warn('카메라 없음 - 나중에 연결하세요')
        except Exception as e:
            self.camera = None
            self.get_logger().warn(f'카메라 초기화 실패: {e}')

    # /amr/object_near 콜백: 물체 근접 시 프레임 분석 스레드 시작
    def trigger_cb(self, msg: Bool):
        if msg.data and self.camera_active:
            threading.Thread(target=self.analyze_frame, daemon=True).start()

    # HSV 마스크+컨투어로 색상/방위각/형상 특징 추출 후 발행
    def analyze_frame(self):
        if self.camera is None:
            return
        ret, frame = self.camera.read()
        if not ret:
            return
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        best_result, best_area = None, 0
        for color_name, ranges in self.hsv_ranges.items():
            mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
            for lower, upper in ranges:
                mask |= cv2.inRange(hsv, lower, upper)
            kernel = np.ones((5,5), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not contours:
                continue
            largest = max(contours, key=cv2.contourArea)
            area = cv2.contourArea(largest)
            if area < 1000 or area <= best_area:
                continue
            best_area = area
            rect = cv2.minAreaRect(largest)
            center, size, angle = rect
            w, h = size
            if w < h:
                angle += 90
            angle = abs(angle)
            aspect_ratio = round(max(w,h)/min(w,h), 2) if min(w,h) > 0 else 1.0
            best_result = {'color': color_name, 'angle': round(angle,1),
                            'aspect_ratio': aspect_ratio, 'area': int(area)}
        if best_result:
            msg = String(); msg.data = json.dumps(best_result)
            self.pub_vision.publish(msg)
            self.get_logger().info(f'감지: {best_result["color"]} 각도={best_result["angle"]}°')


# 노드 초기화 후 스핀 시작, 종료 시 안전하게 정리
def main(args=None):
    rclpy.init(args=args)
    node = VisionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node.camera:
            node.camera.release()
        node.destroy_node()
        rclpy.shutdown()
PYEOF

commit "2026-06-18 17:27:28 +0900" "feat: vision_node 초기 구현 (HSV + minAreaRect)

cv2.VideoCapture(0) 직접 오픈 방식.
색상 마스크 -> 컨투어 -> minAreaRect로 중심/크기/방위각 추출.
종횡비 기반 형태 판정 포함."

echo "================================================"
echo "M4. camera_ros 파이프라인 전환 + numpy/cv_bridge 픽스 + 대시보드 카메라 스트리밍"
echo "================================================"

cat > vision_node/vision_node/vision_node.py << 'PYEOF'
"""
camera_ros가 카메라를 점유하므로 /camera/image_raw 토픽을 구독하는 방식으로 전환된 비전 노드.
"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Bool
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
import json, cv2, numpy as np, threading

class VisionNode(Node):
    # 노드 초기화: 토픽 구독/발행 설정
    def __init__(self):
        super().__init__('vision_node')

        self.bridge = CvBridge()
        self.latest_frame = None
        self.frame_lock = threading.Lock()

        self.create_subscription(Image, '/camera/image_raw', self.image_cb, 10)
        self.create_subscription(Bool, '/amr/object_near', self.trigger_cb, 10)
        self.pub_vision = self.create_publisher(String, '/vision/detected', 10)

        self.hsv_ranges = {
            'red': [(np.array([0,120,70]), np.array([10,255,255])),
                    (np.array([170,120,70]), np.array([180,255,255]))],
            'yellow': [(np.array([20,100,100]), np.array([35,255,255]))],
        }
        self.get_logger().info('Vision Node 시작! (/camera/image_raw 구독 중)')

    # /camera/image_raw 콜백: ROS Image를 OpenCV 배열로 변환해 저장
    def image_cb(self, msg: Image):
        try:
            frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
            with self.frame_lock:
                self.latest_frame = frame
        except Exception as e:
            self.get_logger().warn(f'이미지 변환 실패: {e}')

    # /amr/object_near 콜백: 물체 근접 시 프레임 분석 스레드 시작
    def trigger_cb(self, msg: Bool):
        if msg.data:
            with self.frame_lock:
                frame = self.latest_frame.copy() if self.latest_frame is not None else None
            if frame is not None:
                threading.Thread(target=self.analyze_frame, args=(frame,), daemon=True).start()

    # HSV 마스크+컨투어로 색상/방위각/형상 특징 추출 후 발행
    def analyze_frame(self, frame):
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        best_result, best_area = None, 0
        for color_name, ranges in self.hsv_ranges.items():
            mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
            for lower, upper in ranges:
                mask |= cv2.inRange(hsv, lower, upper)
            kernel = np.ones((5,5), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not contours:
                continue
            largest = max(contours, key=cv2.contourArea)
            area = cv2.contourArea(largest)
            if area < 1000 or area <= best_area:
                continue
            best_area = area
            rect = cv2.minAreaRect(largest)
            center, size, angle = rect
            w, h = size
            if w < h:
                angle += 90
            angle = abs(angle)
            aspect_ratio = round(max(w,h)/min(w,h), 2) if min(w,h) > 0 else 1.0
            best_result = {'color': color_name, 'angle': round(angle,1),
                            'aspect_ratio': aspect_ratio, 'area': int(area)}
        if best_result:
            msg = String(); msg.data = json.dumps(best_result)
            self.pub_vision.publish(msg)
            self.get_logger().info(f'감지: {best_result["color"]} 각도={best_result["angle"]}°')


# 노드 초기화 후 스핀 시작, 종료 시 안전하게 정리
def main(args=None):
    rclpy.init(args=args)
    node = VisionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
PYEOF

cat >> vision_node/package.xml << 'EOF'
<!-- sensor_msgs, cv_bridge dependencies added -->
EOF
sedi 's#<depend>std_msgs</depend>#<depend>std_msgs</depend>\n  <depend>sensor_msgs</depend>\n  <depend>cv_bridge</depend>#' vision_node/package.xml

cat > hazardbot_dashboard/hazardbot_dashboard/dashboard_node.py << 'PYEOF'
"""
camera_ros 토픽을 구독해 실시간 카메라 스트리밍(/video)을 추가한 대시보드 노드.
"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Float32
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
import json, threading, subprocess, os, time, cv2

from ament_index_python.packages import get_package_share_directory
from flask import Flask, render_template, Response
from flask_socketio import SocketIO

pkg_share = get_package_share_directory('hazardbot_dashboard')
template_dir = os.path.join(pkg_share, 'templates')
app = Flask(__name__, template_folder=template_dir)
socketio = SocketIO(app, cors_allowed_origins='*')

dashboard_data = {
    'mission_state': 'IDLE', 'zone': 1,
    'sensors': {'dist_mm': 0, 'ir': [0,0,0,0,0]},
    'gas': {'mq2': 0, 'mq135': 0, 'flag': 'NORMAL'},
    'temp': {'temp': 0.0, 'flame': 0}, 'battery': 0.0,
    'hazard': {'level': 0, 'type': 'NORMAL'}, 'servo_feedback': {},
    'vision': {'color': None, 'angle': None},
    'rpi_health': {'cpu_temp': 0.0, 'throttled': '0x0'},
}

dashboard_node_ref = None

class DashboardNode(Node):
    # 노드 초기화: 토픽 구독/발행 설정
    def __init__(self):
        super().__init__('hazardbot_dashboard')
        self.bridge = CvBridge()
        self.latest_frame = None
        self.frame_lock = threading.Lock()

        self.create_subscription(Image, '/camera/image_raw', self.image_cb, 10)
        self.create_subscription(String, '/mission/state', self.mission_cb, 10)
        self.create_subscription(String, '/amr/sensors',   self.sensor_cb, 10)
        self.create_subscription(String, '/amr/gas',       self.gas_cb, 10)
        self.create_subscription(String, '/amr/temp',      self.temp_cb, 10)
        self.create_subscription(Float32, '/amr/battery',  self.battery_cb, 10)
        self.create_subscription(String, '/hazard/detected', self.hazard_cb, 10)
        self.create_subscription(String, '/arm/servo_feedback', self.servo_cb, 10)
        self.create_subscription(String, '/vision/detected', self.vision_cb, 10)
        self.create_timer(5.0, self.check_rpi_health)
        self.create_timer(1.0, self.broadcast_data)
        self.get_logger().info('Dashboard 노드 시작!')

    # /mission/state 콜백: 대시보드 상태값 갱신
    def mission_cb(self, msg): d = json.loads(msg.data); dashboard_data['mission_state'] = d.get('state','IDLE'); dashboard_data['zone'] = d.get('zone',1)
    # /amr/sensors 콜백 (현재는 별도 처리 없음)
    def sensor_cb(self, msg): dashboard_data['sensors'] = json.loads(msg.data)
    # /amr/gas 콜백: 가스 데이터 저장 후 위험도 재평가
    def gas_cb(self, msg): dashboard_data['gas'] = json.loads(msg.data)
    # /amr/temp 콜백: 온도/화염 데이터 처리, 화염이면 즉시 L3 발행
    def temp_cb(self, msg): dashboard_data['temp'] = json.loads(msg.data)
    # /amr/battery 콜백: 저전압 감지 시 EMERGENCY 전이
    def battery_cb(self, msg): dashboard_data['battery'] = round(msg.data, 2)
    # /hazard/detected 콜백: 위험 등급에 따라 접근 동작 트리거
    def hazard_cb(self, msg): dashboard_data['hazard'] = json.loads(msg.data)
    # /arm/servo_feedback 콜백: 서보 ID별 상태 저장
    def servo_cb(self, msg):
        d = json.loads(msg.data)
        dashboard_data['servo_feedback'][str(d.get('id'))] = d
    # /vision/detected 콜백: 감지 색상/방위각 로그 또는 상태 갱신
    def vision_cb(self, msg): dashboard_data['vision'] = json.loads(msg.data)

    # /camera/image_raw 콜백: ROS Image를 OpenCV 배열로 변환해 저장
    def image_cb(self, msg):
        try:
            frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
            with self.frame_lock:
                self.latest_frame = frame
        except Exception as e:
            self.get_logger().warn(f'이미지 변환 실패: {e}')

    # vcgencmd로 RPi5 CPU 온도/스로틀링 상태 조회
    def check_rpi_health(self):
        try:
            temp_raw = subprocess.check_output(['vcgencmd', 'measure_temp']).decode().strip()
            cpu_temp = float(temp_raw.replace("temp=","").replace("'C",""))
            throttled = subprocess.check_output(['vcgencmd', 'get_throttled']).decode().strip().split('=')[1]
            dashboard_data['rpi_health'] = {'cpu_temp': cpu_temp, 'throttled': throttled}
        except Exception as e:
            self.get_logger().debug(f'헬스 체크 오류: {e}')

    # 누적된 상태를 WebSocket으로 브라우저에 전송
    def broadcast_data(self):
        socketio.emit('update', dashboard_data)


# 최신 카메라 프레임을 MJPEG 스트림으로 인코딩
def generate_frames():
    while True:
        frame = None
        if dashboard_node_ref is not None:
            with dashboard_node_ref.frame_lock:
                if dashboard_node_ref.latest_frame is not None:
                    frame = dashboard_node_ref.latest_frame.copy()
        if frame is None:
            time.sleep(0.1)
            continue
        _, buffer = cv2.imencode('.jpg', frame)
        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')


@app.route('/video')
# /video 라우트: 카메라 스트림 응답 반환
def video():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/')
# / 라우트: 대시보드 메인 페이지 렌더링
def index():
    return render_template('index.html')


# 노드 초기화 후 스핀 시작, 종료 시 안전하게 정리
def main(args=None):
    global dashboard_node_ref
    rclpy.init(args=args)
    node = DashboardNode()
    dashboard_node_ref = node
    flask_thread = threading.Thread(
        target=lambda: socketio.run(app, host='0.0.0.0', port=8080, debug=False, allow_unsafe_werkzeug=True),
        daemon=True)
    flask_thread.start()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
PYEOF

cat > vision_node/DEPENDENCY_NOTES.md << 'MDEOF'
# vision_node 의존성 트러블슈팅 기록 (2026-07-13)

vision_node를 camera_ros 토픽 구독 방식으로 바꾸는 과정에서 만난
환경 의존성 문제와 해결법. `.py` 코드 변경이 아니라 시스템 패키지
설치라 diff로는 안 남아서 별도 기록.

## 1. libcamera 자체가 카메라를 못 잡던 문제 (근본 원인)
```
ros-jazzy-libcamera(0.7.1) 패키지가 미디어 엔티티 이름을 하이픈
(rp1-cfe-fe-image0)으로 하드코딩한 구버전 소스로 빌드되어 있었음.
실제 Ubuntu 24.04 커널의 rp1-cfe 드라이버는 언더스코어
(rp1-cfe-fe_image0)로 엔티티를 등록 -> 이름이 절대 일치하지 않아
CFE acquire가 항상 실패.

해결: GitHub 최신 libcamera 소스 직접 빌드 후 LD_PRELOAD로 강제 로드.
~/.bashrc에 영구 등록:
  export LD_PRELOAD=$HOME/libcamera/build/src/libcamera/libcamera.so.0.7.1:$HOME/libcamera/build/src/libcamera/base/libcamera-base.so.0.7.1
  export LIBCAMERA_IPA_MODULE_PATH=$HOME/libcamera/build/src/ipa/rpi/pisp:$HOME/libcamera/build/src/ipa/rpi/vc4
검증: camera_ros의 /camera/image_raw가 30fps 안정 스트리밍 확인
  (ros2 topic hz /camera/image_raw)
```

## 2. cv_bridge 자체가 시스템에 없던 문제
```
vision_node가 cv2.VideoCapture(0) 직접 오픈 대신
/camera/image_raw 토픽을 구독하는 방식으로 바뀌면서 cv_bridge 필요.

해결:
  sudo apt install -y ros-jazzy-cv-bridge ros-jazzy-vision-opencv
```

## 3. numpy 2.x ↔ cv_bridge(numpy 1.x 컴파일) ABI 불일치
```
증상: dashboard_node/vision_node가 image_cb에서 세그폴트
  (ImportError: numpy 2.x cannot be run with modules compiled for numpy 1.x
   -> exit code -11)

원인: pip으로 설치된 numpy 2.5.1이 apt로 설치된 cv_bridge(numpy 1.x로
컴파일됨)와 ABI 불일치.

해결:
  pip3 install "numpy<2" --break-system-packages --force-reinstall
```

## 4. (HSV 캘리브레이션 도구 관련) opencv GUI 미지원 문제
```
증상: cv2.namedWindow() 호출 시
  "The function is not implemented. Rebuild library with GTK+..."

원인: numpy 충돌 해결 과정에서 opencv-python-headless가 설치되어
  있었음 (cv2.imshow 등 GUI 함수 미지원).

해결: 캘리브레이션 도구는 로컬 GUI creo 대신 Flask 웹 스트리밍
  방식으로 전환 (SSH 원격 작업 환경에 더 적합하기도 함).
```
MDEOF

commit "2026-06-28 20:02:57 +0900" "fix: vision_node/dashboard를 camera_ros 토픽 구독 방식으로 전환

원인: ros-jazzy-libcamera 구버전 소스가 미디어 엔티티 이름을 하이픈으로
하드코딩, 실제 커널 드라이버는 언더스코어 사용 -> CFE acquire 항상 실패.
GitHub 최신 libcamera 소스 직접 빌드 + LD_PRELOAD로 우회, camera_ros가
/camera/image_raw 30fps 안정 스트리밍 확인.
camera_ros가 카메라를 점유하므로 vision_node/dashboard의
cv2.VideoCapture(0) 직접 오픈 방식 제거 -> cv_bridge로 토픽 구독.

vision_node 작업 중 만난 의존성 문제 3건 해결 (상세: vision_node/DEPENDENCY_NOTES.md):
- cv_bridge 시스템 미설치 -> ros-jazzy-cv-bridge/vision-opencv apt 설치
- numpy 2.x/cv_bridge(numpy1.x 컴파일) ABI 불일치로 세그폴트 -> numpy<2 다운그레이드
- opencv-headless GUI 미지원 (캘리브레이션 도구용) -> Flask 웹 스트리밍 방식 채택

대시보드에 실시간 카메라 스트리밍(/video) 추가."

echo "================================================"
echo "M5. GRIP 재시도 로직 (arm_bridge/arm_controller/mission_orchestrator)"
echo "================================================"

cat >> arm_bridge/arm_bridge/arm_bridge_node.py << 'PYEOF'

    # /arm/grip_cmd 콜백: 파지 방향/임계값을 GRIP 명령으로 전송
    def grip_cb(self, msg: String):
        parts = msg.data.strip().split(',')
        if len(parts) >= 2:
            direction, threshold = parts[0], parts[1]
            self.build_and_send('GRIP', direction, threshold)
            self.get_logger().info(f'GRIP 명령 전송: {direction} 임계값={threshold}%')
PYEOF
sedi "s#self.create_subscription(String, '/arm/buzzer_cmd', self.buzzer_cb,   10)#self.create_subscription(String, '/arm/buzzer_cmd', self.buzzer_cb,   10)\n        self.create_subscription(String, '/arm/grip_cmd',   self.grip_cb,     10)#" arm_bridge/arm_bridge/arm_bridge_node.py

commit "2026-07-03 19:12:15 +0900" "feat: GRIP 재시도 로직 구현

파지 실패 시 +5mm 조정 후 최대 3회 재시도, 초과 시 SKIP 후 PATROL 복귀.
arm_bridge: /arm/grip_cmd 구독 -> <GRIP,CLOSE,threshold,CS> 전송
arm_controller: /arm/grip_request(색상별 임계값)·/arm/grip_retry(오프셋조정)
mission_orchestrator: feedback_cb에서 load<10시 재시도, MAX_RETRY=3"

echo "================================================"
echo "M6. amr_bridge를 AMR_state_v8 실제 프로토콜(WiFi)에 맞게 개편"
echo "================================================"

cat > amr_bridge/amr_bridge/amr_bridge_node.py << 'PYEOF'
"""
실제 AMR_state_v8 프로토콜(가스/화염/배터리/상태머신)에 맞춰 파싱을 재작성한 AMR 브릿지 노드.
"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Bool, Float32
from geometry_msgs.msg import Twist
import socket, threading, json, time

HOST = '0.0.0.0'
AMR_PORT = 5000

STATE_NAMES  = ['SAFE', 'WARNING', 'DANGER', 'STOP', 'SENSOR_ERROR']
ACTION_NAMES = ['NORMAL_MOTION', 'LIMITED_MOTION', 'STOP_MOTION']
FAULT_NAMES  = ['OK', 'ESTOP', 'LIPO', 'SENSOR', 'RPI_TIMEOUT', 'HAZARD']

class AmrBridge(Node):
    # 노드 초기화: 토픽 구독/발행 설정
    def __init__(self):
        super().__init__('amr_bridge')
        self.pub_gas     = self.create_publisher(String,  '/amr/gas',     10)
        self.pub_temp    = self.create_publisher(String,  '/amr/temp',    10)
        self.pub_battery = self.create_publisher(Float32, '/amr/battery', 10)

        self.create_subscription(Twist, '/amr/cmd_vel', self.cmd_vel_cb, 10)

        self.conn = None
        self.conn_lock = threading.Lock()
        self.last_recv_time = time.time()

        threading.Thread(target=self.tcp_server, daemon=True).start()
        self.create_timer(0.5, self.check_timeout)
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

            gas_msg = String(); gas_msg.data = json.dumps({'gas': gas})
            self.pub_gas.publish(gas_msg)
            temp_msg = String(); temp_msg.data = json.dumps({'flame': int(flame)})
            self.pub_temp.publish(temp_msg)
            batt_msg = Float32(); batt_msg.data = batt_cv / 100.0
            self.pub_battery.publish(batt_msg)

            self.get_logger().info(
                f'SENS 수신: gas={gas} flame={flame} batt={batt_cv/100.0}V '
                f'state={STATE_NAMES[state_code] if state_code < 5 else state_code}')

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
            self.get_logger().error('ESP32 #1 응답 없음! 연결 끊김 판정')
            with self.conn_lock:
                self.conn = None

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
                    self.get_logger().warn(f'송신 실패: {e}')

    # /amr/cmd_vel 콜백: Twist 메시지를 좌/우 PWM으로 변환해 MOVE 전송
    def cmd_vel_cb(self, msg: Twist):
        linear, angular = msg.linear.x, msg.angular.z
        left  = max(-255, min(255, int((linear - angular) * 150)))
        right = max(-255, min(255, int((linear + angular) * 150)))
        self.build_and_send('MOVE', left, right)

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
PYEOF

mkdir -p firmware_reference
cat > firmware_reference/AMR_state_v8_wifi.ino << 'INOEOF'
/*
 * File: AMR_state_v8_wifi.ino  (참고용 - Arduino 저장소는 별도)
 * Target: ESP32 #1 (AMR) - MQ135 가스 + KY-026 화염 감지, WiFi TCP로
 * RPi5 amr_bridge(포트5000)에 <SENS,gas,flame,battCv,stateCode,
 * actionCode,faultCode,checksum> 형식 전송.
 * 원본 AMR_state_v8.ino(USB Serial)를 WiFiClient 기반으로 변환.
 * 상세 구현은 팀원(강희) 저장소 참조.
 */
INOEOF

commit "2026-07-09 22:39:48 +0900" "feat: amr_bridge를 AMR_state_v8 실제 프로토콜(WiFi TCP)에 맞게 개편

기존 amr_bridge는 가상의 <SENS,dist_mm,ir1..5> 프로토콜 기준이었으나
실제 펌웨어(AMR_state_v8)는 <SENS,gas,flame,battCv,stateCode,
actionCode,faultCode,checksum> 형식(가스+화염+상태머신) 사용.
parse_msg를 실제 프로토콜에 맞게 재작성.
ESP32 펌웨어도 기존 USB Serial 방식에서 WiFi TCP 클라이언트로 변환
(WiFiClient로 amr_bridge:5000 접속, 센서/상태머신 로직은 그대로 유지).
하트비트 타임아웃(2초) 기반 Fault Isolation 추가."

echo "================================================"
echo "M7. LeRobot 배포 검증 완료 (venv, rpi_check.py) - 문서만"
echo "================================================"

mkdir -p docs
cat > docs/lerobot_verification.md << 'MDEOF'
# LeRobot 배포 검증 기록

- `~/lerobot-venv`에 격리 venv 설치 (`--system-site-packages` 미사용,
  ROS2의 opencv/cv_bridge와 충돌 방지 목적)
- `python rpi_check.py --skip-cameras` : 읽기 전용 테스트 전항목 통과
- `python rpi_check.py --skip-cameras --move-all` : 6축 실제 구동 확인
- arm_controller는 서보 버스를 직접 건드리지 않으므로 검증 중 ROS2 스택은
  계속 실행 상태로 두어도 무방 (단, arm_controller는 이 검증 동안 미실행)
MDEOF

commit "2026-07-19 22:33:12 +0900" "chore: LeRobot 격리 venv 설치 및 rpi_check.py 검증 완료

Ubuntu 24.04 externally-managed 환경 대응 위해 venv 필수.
읽기전용 테스트 + --move-all 실구동 테스트 모두 통과.
follower_arm.json은 잠정본 (캘리브레이션 동결 전)."

echo "================================================"
echo "M8. ACT 아키텍처 전환 - sensor_bridge/arm_act_node 신설, 명명규칙 개편"
echo "================================================"

mkpkg sensor_bridge sensor_bridge_node sensor_bridge_node "ENV Board TCP Bridge"
cat > sensor_bridge/sensor_bridge/sensor_bridge_node.py << 'PYEOF'
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
PYEOF

mkpkg arm_act_node arm_act_node arm_act_node "ACT Policy Inference Node"
cat > arm_act_node/arm_act_node/arm_act_node.py << 'PYEOF'
"""
ACT 정책으로 파지 동작을 추론하는 노드. 정책 미탑재 시 더미 시퀀스로 폴백한다.
"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
import json, threading

class ObjectClass:
    CONTAINMENT_BREACH = "CONTAINMENT_BREACH"
    HANDLE_CARE = "HANDLE_CARE"

COLOR_TO_CLASS = {'red': ObjectClass.CONTAINMENT_BREACH, 'yellow': ObjectClass.HANDLE_CARE}

POLICY_PATHS = {ObjectClass.CONTAINMENT_BREACH: None, ObjectClass.HANDLE_CARE: None}

class ArmActNode(Node):
    # 노드 초기화: 토픽 구독/발행 설정
    def __init__(self):
        super().__init__('arm_act_node')
        self.bridge = CvBridge()
        self.latest_front_frame = None
        self.frame_lock = threading.Lock()

        self.create_subscription(Image, '/camera/image_raw', self.front_image_cb, 10)
        self.create_subscription(String, '/hazard/detected', self.hazard_cb, 10)
        self.create_subscription(String, '/vision/detected', self.vision_cb, 10)
        self.create_subscription(String, '/arm/servo_feedback', self.feedback_cb, 10)
        self.create_subscription(String, '/arm/grip_request', self.grip_request_cb, 10)

        self.pub_arm_cmd = self.create_publisher(String, '/arm/command', 10)
        self.pub_grip_cmd = self.create_publisher(String, '/arm/grip_cmd', 10)

        self.policies = {}
        self.load_policies()
        self.warmup_all()

        self.current_target_class = None
        self.get_logger().info('Arm ACT Node 시작!')

    # /camera/image_raw 콜백: 최신 프레임을 버퍼에 저장
    def front_image_cb(self, msg):
        try:
            frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
            with self.frame_lock:
                self.latest_front_frame = frame
        except Exception as e:
            self.get_logger().warn(f'프론트 이미지 변환 실패: {e}')

    # 물체 분류별 정책 체크포인트를 로드 (없으면 더미 모드)
    def load_policies(self):
        for obj_class, path in POLICY_PATHS.items():
            if path is None:
                self.get_logger().warn(f'{obj_class} 정책 체크포인트 미지정 — 더미 모드로 동작')
                self.policies[obj_class] = None

    # 정책 워밍업 (더미 모드에서는 스킵)
    def warmup_all(self):
        self.get_logger().info('정책 워밍업 단계 (더미 모드 - 스킵)')

    # /hazard/detected 콜백: 위험 등급에 따라 접근 동작 트리거
    def hazard_cb(self, msg: String):
        pass

    # /vision/detected 콜백: 감지 색상/방위각 로그 또는 상태 갱신
    def vision_cb(self, msg: String):
        data = json.loads(msg.data)
        self.current_target_class = COLOR_TO_CLASS.get(data.get('color'))
        self.get_logger().info(f'비전 감지 → 대상 분류: {self.current_target_class}')

    # /arm/grip_request 콜백: 분류 결과에 따라 정책 추론 또는 더미 파지 실행
    def grip_request_cb(self, msg: String):
        obj_class = self.current_target_class
        if obj_class is None:
            self.get_logger().warn('분류 안 된 상태에서 파지 요청 — 스킵')
            return
        policy = self.policies.get(obj_class)
        if policy is None:
            self.get_logger().warn(f'{obj_class} 정책 없음 — 더미 접근/파지 시퀀스로 대체')
            self.run_dummy_grip_sequence(obj_class)

    # /arm/servo_feedback 콜백: 과열/과부하 경고 또는 파지 판정
    def feedback_cb(self, msg: String):
        pass

    # 정책이 없을 때 임시로 GRIP 명령만 전송 (통신 검증용)
    def run_dummy_grip_sequence(self, obj_class):
        threshold = 40 if obj_class == ObjectClass.HANDLE_CARE else 80
        self.pub_grip_cmd.publish(String(data=f'CLOSE,{threshold}'))
        self.get_logger().info(f'[더미] GRIP 명령 전송: threshold={threshold}%')


# 노드 초기화 후 스핀 시작, 종료 시 안전하게 정리
def main(args=None):
    rclpy.init(args=args)
    node = ArmActNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
PYEOF
sedi "s#<depend>std_msgs</depend>#<depend>std_msgs</depend>\n  <depend>sensor_msgs</depend>\n  <depend>cv_bridge</depend>#" arm_act_node/package.xml

cat > arm_controller/arm_controller/arm_controller_node.py << 'PYEOF'
"""
포즈 테이블 기반으로 '놓기' 동작만 담당하는 축소판 로봇팔 제어 노드. 파지는 arm_act_node가 담당한다.
"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import String

class ArmController(Node):
    # 노드 초기화: 토픽 구독/발행 설정
    def __init__(self):
        super().__init__('arm_controller')

        self.create_subscription(String, '/arm/place_request', self.place_request_cb, 10)
        self.create_subscription(String, '/arm/servo_feedback', self.feedback_cb, 10)

        self.pub_arm_cmd = self.create_publisher(String, '/arm/command', 10)

        self.joint_limits = {
            1: (0, 4095, 2048), 2: (170, 1877, 1024), 3: (0, 2048, 1024),
            4: (0, 2048, 1024), 5: (0, 2048, 1024), 6: (340, 1365, 340),
        }

        # 파지(GRIP)는 arm_act_node가 담당, 여기는 "놓기" 목적지만 남김
        self.poses = {
            'HOME':            [2048, 1024, 1024, 1024, 1024, 340],
            'OVERPACK_DRUM':   [2048, 1200, 800, 1024, 1024, 900],
            'HAZMAT_STORAGE':  [2048, 700,  1300, 900, 1024, 900],
        }

        self.get_logger().info('Arm Controller(축소판) 노드 시작!')

    # /arm/place_request 콜백: 목적지 이름으로 포즈 이동
    def place_request_cb(self, msg: String):
        self.move_to_pose(msg.data.strip())

    # /arm/servo_feedback 콜백: 과열/과부하 경고 또는 파지 판정
    def feedback_cb(self, msg: String):
        pass

    # 포즈 테이블에서 이름으로 조회해 관절 한계값 검증 후 이동
    def move_to_pose(self, pose_name: str):
        if pose_name not in self.poses:
            self.get_logger().warn(f'알 수 없는 포즈: {pose_name}')
            return
        positions = self.poses[pose_name]
        validated = []
        for i, pos in enumerate(positions):
            min_p, max_p, _ = self.joint_limits[i + 1]
            validated.append(max(min_p, min(max_p, pos)))
        msg = String(); msg.data = ','.join(str(p) for p in validated)
        self.pub_arm_cmd.publish(msg)
        self.get_logger().info(f'포즈 이동: {pose_name} → {validated}')


# 노드 초기화 후 스핀 시작, 종료 시 안전하게 정리
def main(args=None):
    rclpy.init(args=args)
    node = ArmController()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
PYEOF

cat > vision_node/vision_node/vision_node.py << 'PYEOF'
"""
형상 특징(원형도·채움률)과 ROI 제한, 색·형상 불일치 시 소프트 폴백을 추가한 비전 노드.
"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Bool
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
import json, cv2, numpy as np, threading

class ObjectClass:
    CONTAINMENT_BREACH = "CONTAINMENT_BREACH"
    HANDLE_CARE = "HANDLE_CARE"

COLOR_TO_CLASS = {'red': ObjectClass.CONTAINMENT_BREACH, 'yellow': ObjectClass.HANDLE_CARE}

EXPECTED_SHAPE = {
    'red':    {'circularity_min': 0.0, 'circularity_max': 1.0},
    'yellow': {'circularity_min': 0.0, 'circularity_max': 1.0},
}

class VisionNode(Node):
    # 노드 초기화: 토픽 구독/발행 설정
    def __init__(self):
        super().__init__('vision_node')
        self.bridge = CvBridge()
        self.latest_frame = None
        self.frame_lock = threading.Lock()

        self.create_subscription(Image, '/camera/image_raw', self.image_cb, 10)
        self.create_subscription(Bool, '/amr/object_near', self.trigger_cb, 10)
        self.pub_vision = self.create_publisher(String, '/vision/detected', 10)

        self.hsv_ranges = {
            'red': [(np.array([0,120,70]), np.array([10,255,255])),
                    (np.array([170,120,70]), np.array([180,255,255]))],
            'yellow': [(np.array([20,100,100]), np.array([35,255,255]))],
        }

        # 프론트 카메라 ROI - 작업공간 높이로 제한 (바닥 오검출 차단)
        self.roi_y_start_ratio = 0.3
        self.roi_y_end_ratio = 0.8

        self.get_logger().info('Vision Node 시작! (/camera/image_raw 구독 중)')

    # /camera/image_raw 콜백: ROS Image를 OpenCV 배열로 변환해 저장
    def image_cb(self, msg):
        try:
            frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
            with self.frame_lock:
                self.latest_frame = frame
        except Exception as e:
            self.get_logger().warn(f'이미지 변환 실패: {e}')

    # /amr/object_near 콜백: 물체 근접 시 프레임 분석 스레드 시작
    def trigger_cb(self, msg: Bool):
        if msg.data:
            with self.frame_lock:
                frame = self.latest_frame.copy() if self.latest_frame is not None else None
            if frame is not None:
                threading.Thread(target=self.analyze_frame, args=(frame,), daemon=True).start()

    # 작업공간 높이로 프레임을 잘라 바닥 오검출을 차단
    def apply_roi(self, frame):
        h, w = frame.shape[:2]
        y1 = int(h * self.roi_y_start_ratio)
        y2 = int(h * self.roi_y_end_ratio)
        return frame[y1:y2, :], y1

    # HSV 마스크+컨투어로 색상/방위각/형상 특징 추출 후 발행
    def analyze_frame(self, frame):
        roi_frame, y_offset = self.apply_roi(frame)
        hsv = cv2.cvtColor(roi_frame, cv2.COLOR_BGR2HSV)
        best_result, best_area = None, 0

        for color_name, ranges in self.hsv_ranges.items():
            mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
            for lower, upper in ranges:
                mask |= cv2.inRange(hsv, lower, upper)
            kernel = np.ones((5,5), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not contours:
                continue
            largest = max(contours, key=cv2.contourArea)
            area = cv2.contourArea(largest)
            if area < 1000 or area <= best_area:
                continue
            best_area = area
            rect = cv2.minAreaRect(largest)
            center, size, angle = rect
            w_box, h_box = size
            if w_box < h_box:
                angle += 90
            angle = abs(angle)
            aspect_ratio = round(max(w_box,h_box)/min(w_box,h_box), 2) if min(w_box,h_box) > 0 else 1.0

            perimeter = cv2.arcLength(largest, True)
            fill_ratio = round(area / (w_box * h_box), 2) if (w_box * h_box) > 0 else 0.0
            circularity = round((4 * np.pi * area) / (perimeter ** 2), 2) if perimeter > 0 else 0.0

            object_class = COLOR_TO_CLASS.get(color_name)
            shape_ok = self.check_shape_consistency(color_name, circularity)
            mode = 'NORMAL' if shape_ok else 'SOFT_FALLBACK'

            best_result = {
                'color': color_name, 'object_class': object_class, 'angle': round(angle,1),
                'aspect_ratio': aspect_ratio, 'area': int(area), 'fill_ratio': fill_ratio,
                'circularity': circularity, 'mode': mode,
                'center_x': round(center[0],1), 'center_y': round(center[1]+y_offset,1),
            }

        if best_result:
            msg = String(); msg.data = json.dumps(best_result)
            self.pub_vision.publish(msg)
            self.get_logger().info(
                f'감지: {best_result["color"]} ({best_result["object_class"]}) '
                f'각도={best_result["angle"]}° 원형도={best_result["circularity"]} 모드={best_result["mode"]}')

    # 색상별 기대 원형도 범위와 실측값을 비교
    def check_shape_consistency(self, color_name, circularity):
        expected = EXPECTED_SHAPE.get(color_name)
        if not expected:
            return True
        return expected['circularity_min'] <= circularity <= expected['circularity_max']


# 노드 초기화 후 스핀 시작, 종료 시 안전하게 정리
def main(args=None):
    rclpy.init(args=args)
    node = VisionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
PYEOF

cat > mission_orchestrator/mission_orchestrator/mission_orchestrator_node.py << 'PYEOF'
"""
ACT 아키텍처에 맞춰 파지(GRIP)/놓기(TRANSPORT) 요청을 분리하고, 물체 분류·구역 표시 이름을 반영한 FSM 조율 노드.
"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Int8, Int16, Float32
import json


class ObjectClass:
    CONTAINMENT_BREACH = "CONTAINMENT_BREACH"
    HANDLE_CARE = "HANDLE_CARE"


COLOR_TO_CLASS_MISSION = {'red': ObjectClass.CONTAINMENT_BREACH, 'yellow': ObjectClass.HANDLE_CARE}
DESTINATION_BY_CLASS = {ObjectClass.CONTAINMENT_BREACH: "OVERPACK_DRUM", ObjectClass.HANDLE_CARE: "HAZMAT_STORAGE"}
GRIP_THRESHOLD_BY_CLASS = {ObjectClass.CONTAINMENT_BREACH: 80, ObjectClass.HANDLE_CARE: 40}


class ZoneId:
    ZONE1, ZONE2, ZONE3, JUNCTION = 1, 2, 3, 4


ZONE_DISPLAY_NAMES = {1: "일반구역", 2: "취급구역", 3: "위험구역", 4: "분기점"}


class MissionState:
    IDLE, PATROL, DETECTED, CLASSIFY = 'IDLE', 'PATROL', 'DETECTED', 'CLASSIFY'
    APPROACH, GRIP, TRANSPORT, ISOLATE = 'APPROACH', 'GRIP', 'TRANSPORT', 'ISOLATE'
    REPORT, EMERGENCY, HOME = 'REPORT', 'EMERGENCY', 'HOME'


class MissionOrchestrator(Node):
    # 노드 초기화: 토픽 구독/발행 설정
    def __init__(self):
        super().__init__('mission_orchestrator')

        self.create_subscription(String, '/hazard/detected',    self.hazard_cb,   10)
        self.create_subscription(String, '/vision/detected',    self.vision_cb,   10)
        self.create_subscription(String, '/arm/servo_feedback', self.feedback_cb, 10)
        self.create_subscription(Float32, '/amr/battery',       self.battery_cb,  10)
        self.create_subscription(String, '/debug/force_grip',   self.force_grip_cb, 10)

        self.pub_state          = self.create_publisher(String, '/mission/state',    10)
        self.pub_zone            = self.create_publisher(Int8,   '/mission/zone',     10)
        self.pub_wrist            = self.create_publisher(Int16,  '/arm/wrist_preset', 10)
        self.pub_led              = self.create_publisher(String, '/arm/led_cmd',      10)
        self.pub_buzzer           = self.create_publisher(String, '/arm/buzzer_cmd',   10)
        self.pub_grip_request     = self.create_publisher(String, '/arm/grip_request', 10)
        self.pub_grip_retry       = self.create_publisher(String, '/arm/grip_retry',   10)
        self.pub_place_request    = self.create_publisher(String, '/arm/place_request', 10)
        self.pub_amr_stop         = self.create_publisher(String, '/amr/emergency',    10)
        self.pub_arm_stop         = self.create_publisher(String, '/arm/emergency',    10)

        self.state        = MissionState.IDLE
        self.current_zone = ZoneId.ZONE1
        self.grip_retry    = 0
        self.MAX_RETRY     = 3
        self.detected_color = None
        self.detected_angle  = None

        self.create_timer(1.0, self.publish_state)

        self.get_logger().info('Mission Orchestrator 노드 시작!')
        self.transition(MissionState.PATROL)

    # FSM 상태 전이 처리 및 상태별 진입 동작 실행
    def transition(self, new_state: str):
        self.get_logger().info(f'FSM: {self.state} → {new_state}')
        self.state = new_state
        self.publish_state()

        if new_state == MissionState.PATROL:
            self.set_led('0'); self.set_buzzer('0')
        elif new_state == MissionState.DETECTED:
            self.set_led('1')
        elif new_state == MissionState.APPROACH:
            if self.detected_angle:
                self.pub_wrist.publish(Int16(data=int(self.detected_angle)))
        elif new_state == MissionState.GRIP:
            grip_msg = String(); grip_msg.data = self.detected_color or 'red'
            self.pub_grip_request.publish(grip_msg)
            self.get_logger().info(f'GRIP 요청 전송: color={grip_msg.data}')
        elif new_state == MissionState.EMERGENCY:
            self.set_led('2'); self.set_buzzer('1')
            self.emergency_stop_all()

    # /hazard/detected 콜백: 위험 등급에 따라 접근 동작 트리거
    def hazard_cb(self, msg: String):
        data = json.loads(msg.data)
        if data.get('type') == 'FLAME':
            self.transition(MissionState.EMERGENCY)
            return
        if data.get('level', 0) >= 2 and self.state == MissionState.PATROL:
            self.transition(MissionState.DETECTED)

    # /vision/detected 콜백: 감지 색상/방위각 로그 또는 상태 갱신
    def vision_cb(self, msg: String):
        data = json.loads(msg.data)
        self.detected_color = data.get('color')
        self.detected_angle  = data.get('angle')
        if self.state == MissionState.DETECTED:
            self.transition(MissionState.CLASSIFY)
            self.transition(MissionState.APPROACH)

    # 테스트용: 강제로 GRIP 상태 진입 (디버그 토픽)
    def force_grip_cb(self, msg: String):
        self.get_logger().warn('[DEBUG] 강제로 GRIP 상태 진입')
        self.transition(MissionState.GRIP)

    # /arm/servo_feedback 콜백: 과열/과부하 경고 또는 파지 판정
    def feedback_cb(self, msg: String):
        data = json.loads(msg.data)
        if data.get('id') != 6 or self.state != MissionState.GRIP:
            return
        threshold = 40 if self.detected_color == 'yellow' else 80
        load = data.get('load', 0)
        if load >= threshold:
            self.get_logger().info(f'파지 성공! Load={load}%')
            self.grip_retry = 0
            self.transition(MissionState.TRANSPORT)
        elif load < 10:
            self.grip_retry += 1
            if self.grip_retry <= self.MAX_RETRY:
                self.get_logger().warn(f'파지 실패, 재시도 {self.grip_retry}/{self.MAX_RETRY}')
                # NOTE: 이 시점 코드는 pub_grip_retry 발행 누락 버그 있었음 (M9에서 수정)
            else:
                self.grip_retry = 0
                self.transition(MissionState.PATROL)

    # /amr/battery 콜백: 저전압 감지 시 EMERGENCY 전이
    def battery_cb(self, msg):
        # NOTE: 이 시점 코드는 String 타입으로 잘못 구독 (M9에서 Float32로 수정)
        try:
            voltage = float(msg.data)
        except:
            voltage = 0.0
        if 0 < voltage < 9.9:
            self.transition(MissionState.EMERGENCY)

    # 양쪽 ESP32 비상 정지 처리 (또는 하트비트 중단)
    def emergency_stop_all(self):
        self.get_logger().error('!!! 양쪽 ESP32 동시 STOP !!!')
        stop_msg = String(); stop_msg.data = 'STOP'
        self.pub_amr_stop.publish(stop_msg)
        self.pub_arm_stop.publish(stop_msg)

    # 현재 미션 상태를 /mission/state, /mission/zone으로 발행
    def publish_state(self):
        msg = String()
        msg.data = json.dumps({
            'state': self.state, 'zone': self.current_zone,
            'zone_display': ZONE_DISPLAY_NAMES.get(self.current_zone, '알수없음'),
            'color': self.detected_color, 'angle': self.detected_angle,
        })
        self.pub_state.publish(msg)

    # /arm/led_cmd로 LED 색상 값 발행
    def set_led(self, value: str):
        self.pub_led.publish(String(data=value))

    # /arm/buzzer_cmd로 부저 값 발행
    def set_buzzer(self, value: str):
        self.pub_buzzer.publish(String(data=value))


# 노드 초기화 후 스핀 시작, 종료 시 안전하게 정리
def main(args=None):
    rclpy.init(args=args)
    node = MissionOrchestrator()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
PYEOF

cat > hazardbot_dashboard/launch/hazardbot.launch.py << 'PYEOF'
"""
카메라·ENV보드·ACT노드까지 포함한 전체 ROS2 노드 실행 launch 설정.
"""
from launch import LaunchDescription
from launch_ros.actions import Node

# 전체 노드를 한 번에 실행하는 launch 구성 반환
def generate_launch_description():
    return LaunchDescription([
        Node(package='camera_ros',          executable='camera_node'),
        Node(package='amr_bridge',          executable='amr_bridge_node'),
        Node(package='arm_bridge',          executable='arm_bridge_node'),
        Node(package='sensor_bridge',       executable='sensor_bridge_node'),
        Node(package='hazard_detector',     executable='hazard_detector_node'),
        Node(package='arm_controller',      executable='arm_controller_node'),
        Node(package='arm_act_node',        executable='arm_act_node'),
        Node(package='mission_orchestrator',executable='mission_orchestrator_node'),
        Node(package='vision_node',         executable='vision_node'),
        Node(package='hazardbot_dashboard', executable='dashboard_node'),
    ])
PYEOF

cp /dev/null /dev/null 2>/dev/null || true
mv "_진우_전달_2026-08-03.md" docs/ 2>/dev/null || true

commit "2026-07-26 20:20:30 +0900" "feat: ACT 아키텍처 전환 - sensor_bridge/arm_act_node 신설, 명명규칙 개편

RPi5 전담 범위 확장(전원 포함), DRIVE/ENV 보드 구분 반영.
- sensor_bridge 신설 (TCP:5002, ENV 보드 전용, amr_bridge 구조 재사용)
- arm_act_node 신설 (ACT 정책 추론, 현재 더미모드, arm_bridge는 그대로 재사용)
- arm_controller를 포즈테이블 수준으로 축소 (정밀 IK 제거, 파지는
  arm_act_node/놓기만 이 노드가 담당)
- vision_node에 형상특징(원형도·채움률) + ROI제한(바닥 오검출 차단) +
  색·형상 불일치 시 소프트폴백 추가
- 상수 개명: WASTE_GENERAL류 -> ObjectClass(CONTAINMENT_BREACH/HANDLE_CARE)
- ZoneId/ZONE_DISPLAY_NAMES 도입 (구역 코드값 고정, 표시이름만 분리)
- mission_orchestrator: GRIP(파지)/TRANSPORT(놓기) 요청을 각각
  arm_act_node/arm_controller로 분리 발행"

echo "================================================"
echo "M9. 대시보드 - 구역 표시이름 + 판정 매트릭스 + ENV보드 연동"
echo "================================================"

cat > hazardbot_dashboard/hazardbot_dashboard/dashboard_node.py << 'PYEOF'
"""
구역별 판정 매트릭스와 ENV 보드 데이터를 반영한 대시보드 노드.
"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Float32
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
import json, threading, subprocess, os, time, cv2

from ament_index_python.packages import get_package_share_directory
from flask import Flask, render_template, Response
from flask_socketio import SocketIO

pkg_share = get_package_share_directory('hazardbot_dashboard')
template_dir = os.path.join(pkg_share, 'templates')
app = Flask(__name__, template_folder=template_dir)
socketio = SocketIO(app, cors_allowed_origins='*')

dashboard_data = {
    'mission_state': 'IDLE', 'zone': 1, 'zone_display': '일반구역',
    'sensors': {'dist_mm': 0, 'ir': [0,0,0,0,0]},
    'gas': {'mq2': 0, 'mq135': 0, 'flag': 'NORMAL'},
    'temp': {'temp': 0.0, 'flame': 0}, 'battery': 0.0,
    'hazard': {'level': 0, 'type': 'NORMAL'}, 'servo_feedback': {},
    'vision': {'color': None, 'angle': None},
    'rpi_health': {'cpu_temp': 0.0, 'throttled': '0x0'},
    'env_gas': {'gas': 0}, 'env_temp': {'flame': 0}, 'env_battery': 0.0,
    'env_state': {'state': 'SAFE', 'action': 'NORMAL_MOTION', 'fault': 'OK'},
    'zone_thresholds': {
        1: {'gas_alert': 300, 'gas_label': '일반구역 — 가스 검출시 격리실패'},
        2: {'gas_alert': 500, 'gas_label': '취급구역 — 가스 주의'},
        3: {'gas_alert': 9999, 'gas_label': '위험구역 — 가스 정상범위(설계상 무시)'},
    },
}

dashboard_node_ref = None

class DashboardNode(Node):
    # 노드 초기화: 토픽 구독/발행 설정
    def __init__(self):
        super().__init__('hazardbot_dashboard')
        self.bridge = CvBridge()
        self.latest_frame = None
        self.frame_lock = threading.Lock()

        self.create_subscription(Image, '/camera/image_raw', self.image_cb, 10)
        self.create_subscription(String, '/mission/state', self.mission_cb, 10)
        self.create_subscription(String, '/amr/sensors',   self.sensor_cb, 10)
        self.create_subscription(String, '/amr/gas',       self.gas_cb, 10)
        self.create_subscription(String, '/amr/temp',      self.temp_cb, 10)
        self.create_subscription(Float32, '/amr/battery',  self.battery_cb, 10)
        self.create_subscription(String, '/hazard/detected', self.hazard_cb, 10)
        self.create_subscription(String, '/arm/servo_feedback', self.servo_cb, 10)
        self.create_subscription(String, '/vision/detected', self.vision_cb, 10)
        self.create_subscription(String, '/env/gas',     self.env_gas_cb,   10)
        self.create_subscription(String, '/env/temp',    self.env_temp_cb,  10)
        self.create_subscription(Float32, '/env/battery',self.env_battery_cb, 10)
        self.create_subscription(String, '/env/state',   self.env_state_cb, 10)
        self.create_timer(5.0, self.check_rpi_health)
        self.create_timer(1.0, self.broadcast_data)
        self.get_logger().info('Dashboard 노드 시작!')

    # /mission/state 콜백: 대시보드 상태값 갱신
    def mission_cb(self, msg):
        d = json.loads(msg.data)
        dashboard_data['mission_state'] = d.get('state', 'IDLE')
        dashboard_data['zone'] = d.get('zone', 1)
        dashboard_data['zone_display'] = d.get('zone_display', '알수없음')

    # /amr/sensors 콜백 (현재는 별도 처리 없음)
    def sensor_cb(self, msg): dashboard_data['sensors'] = json.loads(msg.data)
    # /amr/gas 콜백: 가스 데이터 저장 후 위험도 재평가
    def gas_cb(self, msg): dashboard_data['gas'] = json.loads(msg.data)
    # /amr/temp 콜백: 온도/화염 데이터 처리, 화염이면 즉시 L3 발행
    def temp_cb(self, msg): dashboard_data['temp'] = json.loads(msg.data)
    # /amr/battery 콜백: 저전압 감지 시 EMERGENCY 전이
    def battery_cb(self, msg): dashboard_data['battery'] = round(msg.data, 2)
    # /hazard/detected 콜백: 위험 등급에 따라 접근 동작 트리거
    def hazard_cb(self, msg): dashboard_data['hazard'] = json.loads(msg.data)
    # /arm/servo_feedback 콜백: 서보 ID별 상태 저장
    def servo_cb(self, msg):
        d = json.loads(msg.data)
        dashboard_data['servo_feedback'][str(d.get('id'))] = d
    # /vision/detected 콜백: 감지 색상/방위각 로그 또는 상태 갱신
    def vision_cb(self, msg): dashboard_data['vision'] = json.loads(msg.data)
    # /env/gas 콜백: ENV 보드 가스값 갱신
    def env_gas_cb(self, msg): dashboard_data['env_gas'] = json.loads(msg.data)
    # /env/temp 콜백: ENV 보드 화염 여부 갱신
    def env_temp_cb(self, msg): dashboard_data['env_temp'] = json.loads(msg.data)
    # /env/battery 콜백: ENV 보드 배터리 전압 갱신
    def env_battery_cb(self, msg): dashboard_data['env_battery'] = round(msg.data, 2)
    # /env/state 콜백: ENV 보드 상태머신 값 갱신
    def env_state_cb(self, msg): dashboard_data['env_state'] = json.loads(msg.data)

    # /camera/image_raw 콜백: ROS Image를 OpenCV 배열로 변환해 저장
    def image_cb(self, msg):
        try:
            frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
            with self.frame_lock:
                self.latest_frame = frame
        except Exception as e:
            self.get_logger().warn(f'이미지 변환 실패: {e}')

    # vcgencmd로 RPi5 CPU 온도/스로틀링 상태 조회
    def check_rpi_health(self):
        try:
            temp_raw = subprocess.check_output(['vcgencmd', 'measure_temp']).decode().strip()
            cpu_temp = float(temp_raw.replace("temp=","").replace("'C",""))
            throttled = subprocess.check_output(['vcgencmd', 'get_throttled']).decode().strip().split('=')[1]
            dashboard_data['rpi_health'] = {'cpu_temp': cpu_temp, 'throttled': throttled}
        except Exception as e:
            self.get_logger().debug(f'헬스 체크 오류: {e}')

    # 누적된 상태를 WebSocket으로 브라우저에 전송
    def broadcast_data(self):
        socketio.emit('update', dashboard_data)


# 최신 카메라 프레임을 MJPEG 스트림으로 인코딩
def generate_frames():
    while True:
        frame = None
        if dashboard_node_ref is not None:
            with dashboard_node_ref.frame_lock:
                if dashboard_node_ref.latest_frame is not None:
                    frame = dashboard_node_ref.latest_frame.copy()
        if frame is None:
            time.sleep(0.1)
            continue
        _, buffer = cv2.imencode('.jpg', frame)
        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')


@app.route('/video')
# /video 라우트: 카메라 스트림 응답 반환
def video():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/')
# / 라우트: 대시보드 메인 페이지 렌더링
def index():
    return render_template('index.html')

@app.route('/api/data')
# /api/data 라우트: 현재 상태를 JSON으로 반환
def api_data():
    return json.dumps(dashboard_data)


# 노드 초기화 후 스핀 시작, 종료 시 안전하게 정리
def main(args=None):
    global dashboard_node_ref
    rclpy.init(args=args)
    node = DashboardNode()
    dashboard_node_ref = node
    flask_thread = threading.Thread(
        target=lambda: socketio.run(app, host='0.0.0.0', port=8080, debug=False, allow_unsafe_werkzeug=True),
        daemon=True)
    flask_thread.start()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
PYEOF

# index.html: 구역표시이름 + 판정매트릭스 표 + ENV보드 카드 반영 (요약본)
cat > hazardbot_dashboard/templates/index.html << 'HTMLEOF'
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8"><title>HazardBot Dashboard</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.min.js"></script>
<style>
body{background:#0a0a0a;color:#e0e0e0;font-family:monospace;padding:16px}
h1{text-align:center;color:#00ff88}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
.card{background:#1a1a1a;border:1px solid #333;border-radius:8px;padding:16px}
table{width:100%;border-collapse:collapse;font-size:13px}
</style>
</head>
<body>
<h1>⚠ HAZARDBOT DASHBOARD</h1>
<div class="grid">
  <div class="card">
    <h3>MISSION STATE</h3>
    <div id="mission-state">IDLE</div>
    <div>구역: <span id="zone-display">일반구역</span></div>
  </div>
  <div class="card">
    <h3>구역별 판정 — 같은 값, 다른 판정</h3>
    <table>
      <tr><th>구역</th><th>가스 원시값</th><th>임계값</th><th>판정</th></tr>
      <tr id="zone-row-1"><td>일반구역</td><td id="zone1-gas">-</td><td>300↑=격리실패</td><td id="zone1-verdict">-</td></tr>
      <tr id="zone-row-2"><td>취급구역</td><td id="zone2-gas">-</td><td>500↑=주의</td><td id="zone2-verdict">-</td></tr>
      <tr id="zone-row-3"><td>위험구역</td><td id="zone3-gas">-</td><td>정상범위(무시)</td><td id="zone3-verdict">-</td></tr>
    </table>
  </div>
  <div class="card">
    <h3>ENV BOARD (sensor_bridge)</h3>
    <div>가스: <span id="env-gas">0</span></div>
    <div>화염: <span id="env-flame">없음</span></div>
    <div>상태: <span id="env-state">-</span></div>
  </div>
</div>
<script>
const socket = io();
socket.on('update', (data) => {
    document.getElementById('mission-state').textContent = data.mission_state;
    document.getElementById('zone-display').textContent = data.zone_display || '알수없음';

    const envGas = (data.env_gas && data.env_gas.gas) || 0;
    document.getElementById('env-gas').textContent = envGas;
    document.getElementById('env-flame').textContent = (data.env_temp && data.env_temp.flame) ? '🔥 감지!' : '없음';
    document.getElementById('env-state').textContent = (data.env_state && data.env_state.state) || '-';

    const th = data.zone_thresholds || {};
    document.getElementById('zone1-gas').textContent = envGas;
    document.getElementById('zone2-gas').textContent = envGas;
    document.getElementById('zone3-gas').textContent = envGas;
    const t1 = (th[1] && th[1].gas_alert) || 300;
    const t2 = (th[2] && th[2].gas_alert) || 500;
    const v1 = document.getElementById('zone1-verdict');
    v1.textContent = envGas >= t1 ? '🔴 격리 실패' : '🟢 정상';
    const v2 = document.getElementById('zone2-verdict');
    v2.textContent = envGas >= t2 ? '🟡 주의' : '🟢 정상';
    document.getElementById('zone3-verdict').textContent = '🟢 정상 범위 (설계상 무시)';
});
</script>
</body>
</html>
HTMLEOF

commit "2026-07-28 20:29:47 +0900" "feat: 대시보드 구역표시이름 + 판정매트릭스 + ENV보드 연동

sensor_bridge(/env/*) 토픽 구독 추가.
zone_display 필드로 일반/취급/위험구역 라벨 표시.
'구역별 판정 - 같은 값, 다른 판정' 표 신설: 같은 가스 원시값을
세 구역 임계값에 각각 대입해 판정을 나란히 표시, 현재 구역 강조.
Mock으로 실동작 확인(가스400 -> 일반구역만 격리실패로 표시)."

echo "================================================"
echo "M10. mission_orchestrator 크래시 버그 수정"
echo "================================================"

cat > mission_orchestrator/mission_orchestrator/mission_orchestrator_node.py << 'PYEOF'
"""
버그 수정판 FSM 조율 노드: GRIP 재시도 발행 누락, 배터리 타입 불일치, TRANSPORT 목적지 매핑 누락 등을 수정.
"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Int8, Int16, Float32
import json


class ObjectClass:
    CONTAINMENT_BREACH = "CONTAINMENT_BREACH"
    HANDLE_CARE = "HANDLE_CARE"


COLOR_TO_CLASS_MISSION = {'red': ObjectClass.CONTAINMENT_BREACH, 'yellow': ObjectClass.HANDLE_CARE}
DESTINATION_BY_CLASS = {ObjectClass.CONTAINMENT_BREACH: "OVERPACK_DRUM", ObjectClass.HANDLE_CARE: "HAZMAT_STORAGE"}
GRIP_THRESHOLD_BY_CLASS = {ObjectClass.CONTAINMENT_BREACH: 80, ObjectClass.HANDLE_CARE: 40}


class ZoneId:
    ZONE1, ZONE2, ZONE3, JUNCTION = 1, 2, 3, 4


ZONE_DISPLAY_NAMES = {1: "일반구역", 2: "취급구역", 3: "위험구역", 4: "분기점"}


class MissionState:
    IDLE, PATROL, DETECTED, CLASSIFY = 'IDLE', 'PATROL', 'DETECTED', 'CLASSIFY'
    APPROACH, GRIP, TRANSPORT, ISOLATE = 'APPROACH', 'GRIP', 'TRANSPORT', 'ISOLATE'
    REPORT, EMERGENCY, HOME = 'REPORT', 'EMERGENCY', 'HOME'


class MissionOrchestrator(Node):
    # 노드 초기화: 토픽 구독/발행 설정
    def __init__(self):
        super().__init__('mission_orchestrator')

        self.create_subscription(String, '/hazard/detected',    self.hazard_cb,   10)
        self.create_subscription(String, '/vision/detected',    self.vision_cb,   10)
        self.create_subscription(String, '/arm/servo_feedback', self.feedback_cb, 10)
        self.create_subscription(Float32, '/amr/battery',       self.battery_cb,  10)
        self.create_subscription(String, '/debug/force_grip',   self.force_grip_cb, 10)

        self.pub_state          = self.create_publisher(String, '/mission/state',    10)
        self.pub_zone            = self.create_publisher(Int8,   '/mission/zone',     10)
        self.pub_wrist            = self.create_publisher(Int16,  '/arm/wrist_preset', 10)
        self.pub_led              = self.create_publisher(String, '/arm/led_cmd',      10)
        self.pub_buzzer           = self.create_publisher(String, '/arm/buzzer_cmd',   10)
        self.pub_grip_request     = self.create_publisher(String, '/arm/grip_request', 10)
        self.pub_grip_retry       = self.create_publisher(String, '/arm/grip_retry',   10)
        self.pub_place_request    = self.create_publisher(String, '/arm/place_request', 10)
        self.pub_amr_stop         = self.create_publisher(String, '/amr/emergency',    10)
        self.pub_arm_stop         = self.create_publisher(String, '/arm/emergency',    10)

        self.state        = MissionState.IDLE
        self.current_zone = ZoneId.ZONE1
        self.grip_retry    = 0
        self.MAX_RETRY     = 3
        self.detected_color = None
        self.detected_angle  = None

        self.create_timer(1.0, self.publish_state)

        self.get_logger().info('Mission Orchestrator 노드 시작!')
        self.transition(MissionState.PATROL)

    # FSM 상태 전이 처리 및 상태별 진입 동작 실행
    def transition(self, new_state: str):
        self.get_logger().info(f'FSM: {self.state} → {new_state}')
        self.state = new_state
        self.publish_state()

        if new_state == MissionState.PATROL:
            self.set_led('0'); self.set_buzzer('0')
        elif new_state == MissionState.DETECTED:
            self.set_led('1')
        elif new_state == MissionState.APPROACH:
            if self.detected_angle:
                self.pub_wrist.publish(Int16(data=int(self.detected_angle)))
        elif new_state == MissionState.GRIP:
            grip_msg = String(); grip_msg.data = self.detected_color or 'red'
            self.pub_grip_request.publish(grip_msg)
            self.get_logger().info(f'GRIP 요청 전송: color={grip_msg.data}')
        elif new_state == MissionState.TRANSPORT:
            object_class = COLOR_TO_CLASS_MISSION.get(self.detected_color)
            destination = DESTINATION_BY_CLASS.get(object_class, 'HOME')
            place_msg = String(); place_msg.data = destination
            self.pub_place_request.publish(place_msg)
            self.get_logger().info(f'놓기 요청 전송: destination={destination}')
        elif new_state == MissionState.EMERGENCY:
            self.set_led('2'); self.set_buzzer('1')
            self.emergency_stop_all()

    # /hazard/detected 콜백: 위험 등급에 따라 접근 동작 트리거
    def hazard_cb(self, msg: String):
        data = json.loads(msg.data)
        if data.get('type') == 'FLAME':
            self.transition(MissionState.EMERGENCY)
            return
        if data.get('level', 0) >= 2 and self.state == MissionState.PATROL:
            self.transition(MissionState.DETECTED)

    # /vision/detected 콜백: 감지 색상/방위각 로그 또는 상태 갱신
    def vision_cb(self, msg: String):
        data = json.loads(msg.data)
        self.detected_color = data.get('color')
        self.detected_angle  = data.get('angle')
        if self.state == MissionState.DETECTED:
            self.transition(MissionState.CLASSIFY)
            self.transition(MissionState.APPROACH)

    # 테스트용: 강제로 GRIP 상태 진입 (디버그 토픽)
    def force_grip_cb(self, msg: String):
        self.get_logger().warn('[DEBUG] 강제로 GRIP 상태 진입')
        self.transition(MissionState.GRIP)

    # /arm/servo_feedback 콜백: 과열/과부하 경고 또는 파지 판정
    def feedback_cb(self, msg: String):
        data = json.loads(msg.data)
        servo_id = data.get('id')
        load = data.get('load', 0)
        if servo_id != 6 or self.state != MissionState.GRIP:
            return

        object_class = COLOR_TO_CLASS_MISSION.get(self.detected_color)
        threshold = GRIP_THRESHOLD_BY_CLASS.get(object_class, 80)

        if load >= threshold:
            self.get_logger().info(f'파지 성공! Load={load}%')
            self.grip_retry = 0
            self.transition(MissionState.TRANSPORT)
        elif load < 10:
            self.grip_retry += 1
            if self.grip_retry <= self.MAX_RETRY:
                self.get_logger().warn(f'파지 실패, 재시도 {self.grip_retry}/{self.MAX_RETRY}')
                retry_msg = String(); retry_msg.data = json.dumps({'offset_mm': 5})
                self.pub_grip_retry.publish(retry_msg)
            else:
                self.get_logger().error('파지 재시도 초과 - SKIP')
                self.grip_retry = 0
                self.transition(MissionState.PATROL)

    # /amr/battery 콜백: 저전압 감지 시 EMERGENCY 전이
    def battery_cb(self, msg: Float32):
        voltage = msg.data
        if 0 < voltage < 9.9:
            self.get_logger().error(f'배터리 부족! {voltage}V → 비상 정지')
            self.transition(MissionState.EMERGENCY)

    # 양쪽 ESP32 비상 정지 처리 (또는 하트비트 중단)
    def emergency_stop_all(self):
        self.get_logger().error('!!! 양쪽 ESP32 동시 STOP !!!')
        stop_msg = String(); stop_msg.data = 'STOP'
        self.pub_amr_stop.publish(stop_msg)
        self.pub_arm_stop.publish(stop_msg)

    # 현재 미션 상태를 /mission/state, /mission/zone으로 발행
    def publish_state(self):
        msg = String()
        msg.data = json.dumps({
            'state': self.state, 'zone': self.current_zone,
            'zone_display': ZONE_DISPLAY_NAMES.get(self.current_zone, '알수없음'),
            'color': self.detected_color, 'angle': self.detected_angle,
        })
        self.pub_state.publish(msg)
        self.pub_zone.publish(Int8(data=self.current_zone))

    # /arm/led_cmd로 LED 색상 값 발행
    def set_led(self, value: str):
        self.pub_led.publish(String(data=value))

    # /arm/buzzer_cmd로 부저 값 발행
    def set_buzzer(self, value: str):
        self.pub_buzzer.publish(String(data=value))


# 노드 초기화 후 스핀 시작, 종료 시 안전하게 정리
def main(args=None):
    rclpy.init(args=args)
    node = MissionOrchestrator()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
PYEOF

commit "2026-08-03 22:53:45 +0900" "fix: mission_orchestrator 크래시 버그 및 미반영 로직 수정

발견 경위: GRIP 재시도 mock 테스트 중 재현.
- pub_grip_retry 퍼블리셔 미생성 -> AttributeError로 노드 다운 (수정)
- battery_cb가 String으로 잘못 구독 (amr_bridge는 Float32 발행) -> 타입 수정
- TRANSPORT 상태 진입 시 place_request 발행 로직 자체가 누락 -> 추가
- GRIP_THRESHOLD_BY_CLASS 정의만 되고 미사용(하드코딩 잔존) -> 실사용으로 교체
- publish_state()에 zone_display 필드 없어 대시보드 라벨 불일치 -> 추가
전체 FSM 시나리오(정상흐름/재시도/EMERGENCY) mock 재검증 통과."

echo "================================================"
echo "M11. 하트비트 기반 비상정지 + EMERGENCY 수동 복귀"
echo "================================================"

cat > mission_orchestrator/mission_orchestrator/mission_orchestrator_node.py << 'PYEOF'
"""
미션 전체 흐름(FSM)을 조율하는 노드. 하트비트 기반 정지 + EMERGENCY 수동 복귀 포함.
"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Int8, Int16, Float32
import json


# ══════════════════════════════════════════════
# 물체 분류 (색상 기반) — vision_node/arm_act_node와 동일 규칙 공유
# ══════════════════════════════════════════════
class ObjectClass:
    CONTAINMENT_BREACH = "CONTAINMENT_BREACH"  # 적색 강체 - 격리 실패 원인
    HANDLE_CARE = "HANDLE_CARE"                # 황색 변형체 - 취급주의


COLOR_TO_CLASS_MISSION = {
    'red': ObjectClass.CONTAINMENT_BREACH,
    'yellow': ObjectClass.HANDLE_CARE,
}

DESTINATION_BY_CLASS = {
    ObjectClass.CONTAINMENT_BREACH: "OVERPACK_DRUM",
    ObjectClass.HANDLE_CARE: "HAZMAT_STORAGE",
}

GRIP_THRESHOLD_BY_CLASS = {
    ObjectClass.CONTAINMENT_BREACH: 80,
    ObjectClass.HANDLE_CARE: 40,
}


# ══════════════════════════════════════════════
# 구역 식별자 (코드용, 절대 안 바뀜) — 표시 이름만 별도
# ══════════════════════════════════════════════
class ZoneId:
    ZONE1 = 1
    ZONE2 = 2
    ZONE3 = 3
    JUNCTION = 4


ZONE_DISPLAY_NAMES = {1: "일반구역", 2: "취급구역", 3: "위험구역", 4: "분기점"}


# ══════════════════════════════════════════════
# FSM 상태 정의
# ══════════════════════════════════════════════
class MissionState:
    IDLE       = 'IDLE'
    PATROL     = 'PATROL'
    DETECTED   = 'DETECTED'
    CLASSIFY   = 'CLASSIFY'
    APPROACH   = 'APPROACH'
    GRIP       = 'GRIP'
    TRANSPORT  = 'TRANSPORT'
    ISOLATE    = 'ISOLATE'
    REPORT     = 'REPORT'
    EMERGENCY  = 'EMERGENCY'
    HOME       = 'HOME'


class MissionOrchestrator(Node):
    def __init__(self):
        super().__init__('mission_orchestrator')

        # ── Subscribers ──
        self.create_subscription(String, '/hazard/detected',    self.hazard_cb,   10)
        self.create_subscription(String, '/vision/detected',    self.vision_cb,   10)
        self.create_subscription(String, '/arm/servo_feedback', self.feedback_cb, 10)
        self.create_subscription(Float32, '/amr/battery',       self.battery_cb,  10)
        self.create_subscription(String, '/debug/force_grip',   self.force_grip_cb, 10)
        self.create_subscription(String, '/mission/reset',      self.reset_cb,    10)

        # ── Publishers ──
        self.pub_state          = self.create_publisher(String, '/mission/state',    10)
        self.pub_zone            = self.create_publisher(Int8,   '/mission/zone',     10)
        self.pub_wrist            = self.create_publisher(Int16,  '/arm/wrist_preset', 10)
        self.pub_led              = self.create_publisher(String, '/arm/led_cmd',      10)
        self.pub_buzzer           = self.create_publisher(String, '/arm/buzzer_cmd',   10)

        # 파지(GRIP) 요청/재시도 → arm_act_node가 구독
        self.pub_grip_request     = self.create_publisher(String, '/arm/grip_request', 10)
        self.pub_grip_retry       = self.create_publisher(String, '/arm/grip_retry',   10)
        # 놓기(place) 요청 → arm_controller(축소판)가 구독
        self.pub_place_request    = self.create_publisher(String, '/arm/place_request', 10)

        # 비상 정지 (arm 쪽은 과도기적으로 STOP 유지)
        self.pub_amr_stop         = self.create_publisher(String, '/amr/emergency',    10)
        self.pub_arm_stop         = self.create_publisher(String, '/arm/emergency',    10)

        # 하트비트 (문서 §5: 계층2는 명령이 아니라 하트비트)
        self.pub_heartbeat        = self.create_publisher(String, '/mission/heartbeat', 10)

        # ── FSM 상태 ──
        self.state        = MissionState.IDLE
        self.current_zone = ZoneId.ZONE1
        self.grip_retry    = 0
        self.MAX_RETRY     = 3

        self.detected_color = None
        self.detected_angle  = None

        # 하트비트 주기 = 타임아웃(1초 예정)의 1/3 이하
        self.HEARTBEAT_INTERVAL = 0.3
        self.heartbeat_active = True
        self.create_timer(self.HEARTBEAT_INTERVAL, self.send_heartbeat)

        self.create_timer(1.0, self.publish_state)

        self.get_logger().info('Mission Orchestrator 노드 시작!')
        self.transition(MissionState.PATROL)

    # ════════════════════════════════════════════
    # FSM 상태 전이
    # ════════════════════════════════════════════
    def transition(self, new_state: str):
        self.get_logger().info(f'FSM: {self.state} → {new_state}')
        self.state = new_state
        self.publish_state()

        if new_state == MissionState.PATROL:
            self.set_led('0')
            self.set_buzzer('0')
            self.heartbeat_active = True   # 하트비트 재개

        elif new_state == MissionState.DETECTED:
            self.set_led('1')

        elif new_state == MissionState.APPROACH:
            if self.detected_angle:
                self.pub_wrist.publish(Int16(data=int(self.detected_angle)))

        elif new_state == MissionState.GRIP:
            grip_msg = String()
            grip_msg.data = self.detected_color or 'red'
            self.pub_grip_request.publish(grip_msg)
            self.get_logger().info(f'GRIP 요청 전송: color={grip_msg.data}')

        elif new_state == MissionState.TRANSPORT:
            object_class = COLOR_TO_CLASS_MISSION.get(self.detected_color)
            destination = DESTINATION_BY_CLASS.get(object_class, 'HOME')
            place_msg = String()
            place_msg.data = destination
            self.pub_place_request.publish(place_msg)
            self.get_logger().info(f'놓기 요청 전송: destination={destination}')

        elif new_state == MissionState.EMERGENCY:
            self.set_led('2')
            self.set_buzzer('1')
            self.emergency_stop_all()

    # ════════════════════════════════════════════
    # 위험물 감지 콜백
    # ════════════════════════════════════════════
    def hazard_cb(self, msg: String):
        data = json.loads(msg.data)
        level = data.get('level', 0)

        if data.get('type') == 'FLAME':
            self.transition(MissionState.EMERGENCY)
            return

        if level >= 2 and self.state == MissionState.PATROL:
            self.transition(MissionState.DETECTED)

    # ════════════════════════════════════════════
    # 비전 감지 콜백
    # ════════════════════════════════════════════
    def vision_cb(self, msg: String):
        data = json.loads(msg.data)
        self.detected_color = data.get('color')
        self.detected_angle  = data.get('angle')

        if self.state == MissionState.DETECTED:
            self.transition(MissionState.CLASSIFY)
            self.transition(MissionState.APPROACH)

    # ════════════════════════════════════════════
    # 테스트용: 강제로 GRIP 상태 진입 (amr_navigation 없을 때 디버깅용)
    # ════════════════════════════════════════════
    def force_grip_cb(self, msg: String):
        self.get_logger().warn('[DEBUG] 강제로 GRIP 상태 진입')
        self.transition(MissionState.GRIP)

    # ════════════════════════════════════════════
    # EMERGENCY 수동 복귀 (사람 개입 필수)
    # ════════════════════════════════════════════
    def reset_cb(self, msg: String):
        if self.state != MissionState.EMERGENCY:
            self.get_logger().warn(
                f'EMERGENCY 상태가 아니라 리셋 무시됨 (현재: {self.state})'
            )
            return

        try:
            data = json.loads(msg.data)
        except (json.JSONDecodeError, TypeError):
            data = {}

        if data.get('confirm') != 'SAFE_TO_RESUME':
            self.get_logger().warn(
                '리셋 요청 거부 — confirm 필드에 "SAFE_TO_RESUME" 필요'
            )
            return

        self.get_logger().warn('!!! 사람 확인 완료 — EMERGENCY 해제, PATROL 복귀 !!!')
        self.grip_retry = 0
        self.detected_color = None
        self.detected_angle = None
        self.transition(MissionState.PATROL)

    # ════════════════════════════════════════════
    # 서보 피드백 콜백 (파지 판정 + 재시도 로직)
    # ════════════════════════════════════════════
    def feedback_cb(self, msg: String):
        data = json.loads(msg.data)
        servo_id = data.get('id')
        load = data.get('load', 0)

        if servo_id != 6 or self.state != MissionState.GRIP:
            return

        object_class = COLOR_TO_CLASS_MISSION.get(self.detected_color)
        threshold = GRIP_THRESHOLD_BY_CLASS.get(object_class, 80)

        if load >= threshold:
            self.get_logger().info(f'파지 성공! Load={load}%')
            self.grip_retry = 0
            self.transition(MissionState.TRANSPORT)

        elif load < 10:
            self.grip_retry += 1
            if self.grip_retry <= self.MAX_RETRY:
                self.get_logger().warn(
                    f'파지 실패, 재시도 {self.grip_retry}/{self.MAX_RETRY}'
                )
                retry_msg = String()
                retry_msg.data = json.dumps({'offset_mm': 5})
                self.pub_grip_retry.publish(retry_msg)
            else:
                self.get_logger().error('파지 재시도 초과 - SKIP')
                self.grip_retry = 0
                self.transition(MissionState.PATROL)

    # ════════════════════════════════════════════
    # 배터리 콜백
    # ════════════════════════════════════════════
    def battery_cb(self, msg: Float32):
        voltage = msg.data
        if voltage > 0 and voltage < 9.9:
            self.get_logger().error(f'배터리 부족! {voltage}V → 비상 정지')
            self.transition(MissionState.EMERGENCY)

    # ════════════════════════════════════════════
    # 비상 정지 (하트비트 방식, 문서 §5)
    # ════════════════════════════════════════════
    def emergency_stop_all(self):
        self.get_logger().error('!!! EMERGENCY: 하트비트 중단 → DRIVE 자동 정지 유도 !!!')
        self.heartbeat_active = False
        # arm 쪽은 하트비트 체계 도입 전까지 과도기적으로 STOP 유지
        stop_msg = String()
        stop_msg.data = 'STOP'
        self.pub_arm_stop.publish(stop_msg)

    def send_heartbeat(self):
        if not self.heartbeat_active:
            return
        msg = String()
        msg.data = json.dumps({'alive': True, 'state': self.state})
        self.pub_heartbeat.publish(msg)

    # ════════════════════════════════════════════
    # 상태 퍼블리시
    # ════════════════════════════════════════════
    def publish_state(self):
        msg = String()
        msg.data = json.dumps({
            'state': self.state,
            'zone': self.current_zone,
            'zone_display': ZONE_DISPLAY_NAMES.get(self.current_zone, '알수없음'),
            'color': self.detected_color,
            'angle': self.detected_angle,
        })
        self.pub_state.publish(msg)

        zone_msg = Int8()
        zone_msg.data = self.current_zone
        self.pub_zone.publish(zone_msg)

    # ════════════════════════════════════════════
    # LED / 부저 헬퍼
    # ════════════════════════════════════════════
    def set_led(self, value: str):
        msg = String()
        msg.data = value
        self.pub_led.publish(msg)

    def set_buzzer(self, value: str):
        msg = String()
        msg.data = value
        self.pub_buzzer.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = MissionOrchestrator()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
PYEOF

cat > amr_bridge/amr_bridge/amr_bridge_node.py << 'PYEOF'
"""
AMR ESP32 #1과 TCP로 통신하며 센서/이동 명령을 ROS2 토픽과 연결하는 브릿지 노드.
하트비트를 DRIVE로 전달하는 heartbeat_cb 포함.
"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Bool, Float32
from geometry_msgs.msg import Twist
import socket
import threading
import json
import time

HOST = '0.0.0.0'   # 모든 IP에서 접속 허용
AMR_PORT = 5000    # ESP32 #1이 접속할 포트번호

class AmrBridge(Node):
    def __init__(self):
        super().__init__('amr_bridge')

        # ── Publishers: ESP32 #1 데이터를 ROS2 토픽으로 내보냄 ──
        self.pub_sensors = self.create_publisher(String,  '/amr/sensors',     10)
        self.pub_gas     = self.create_publisher(String,  '/amr/gas',         10)
        self.pub_temp    = self.create_publisher(String,  '/amr/temp',        10)
        self.pub_battery = self.create_publisher(Float32, '/amr/battery',     10)
        self.pub_near    = self.create_publisher(Bool,    '/amr/object_near', 10)
        self.conn = None
        self.conn_lock = threading.Lock()
        self.last_recv_time = time.time()   # ← 이거 있는지 확인
        self.create_timer(0.5, self.check_timeout)

        # ── Subscriber: ROS2 명령을 ESP32 #1으로 전달 ──
        self.create_subscription(
            Twist, '/amr/cmd_vel', self.cmd_vel_cb, 10
        )
        # ── mission_orchestrator의 하트비트를 받아 DRIVE로 전달 ──
        self.create_subscription(String, '/mission/heartbeat', self.heartbeat_cb, 10)

        self.conn = None          # ESP32 #1 소켓 (연결되면 채워짐)
        self.conn_lock = threading.Lock()

        # TCP 서버를 백그라운드 스레드로 실행
        threading.Thread(target=self.tcp_server, daemon=True).start()

        # 하트비트: 500ms마다 연결 확인
        self.create_timer(0.5, self.heartbeat)

        self.get_logger().info('AMR Bridge 노드 시작!')

    # ════════════════════════════════════════════
    # TCP 서버: ESP32 #1의 접속을 기다림
    # ════════════════════════════════════════════
    def tcp_server(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((HOST, AMR_PORT))
            server.listen(1)
            self.get_logger().info(f'포트 {AMR_PORT} 에서 ESP32 #1 기다리는 중...')

            while rclpy.ok():
                try:
                    conn, addr = server.accept()  # ESP32 접속 대기 (블로킹)
                    self.get_logger().info(f'ESP32 #1 연결됨! IP: {addr[0]}')
                    with self.conn_lock:
                        self.conn = conn
                    # 수신 루프를 별도 스레드로 실행
                    threading.Thread(
                        target=self.recv_loop,
                        args=(conn,),
                        daemon=True
                    ).start()
                except Exception as e:
                    self.get_logger().error(f'서버 오류: {e}')
                    time.sleep(1)

    # ════════════════════════════════════════════
    # 수신 루프: ESP32 #1이 보내는 데이터를 계속 읽음
    # ════════════════════════════════════════════
    def recv_loop(self, conn):
        buf = ''
        while rclpy.ok():
            try:
                raw = conn.recv(256)
                if not raw:
                    break  # 연결 끊김
                buf += raw.decode('utf-8', errors='ignore')

                # \n 기준으로 메시지 분리
                while '\n' in buf:
                    line, buf = buf.split('\n', 1)
                    line = line.strip()
                    if line:
                        self.parse_msg(line)

            except ConnectionResetError:
                self.get_logger().warn('ESP32 #1 연결 끊김 (Reset)')
                break
            except Exception as e:
                self.get_logger().warn(f'수신 오류: {e}')
                break

        # 연결 정리
        with self.conn_lock:
            self.conn = None
        self.get_logger().warn('ESP32 #1 연결 종료. 재접속 대기 중...')

    # ════════════════════════════════════════════
    # 메시지 파싱: <SENS,gas,flame,battCv,stateCode,actionCode,faultCode,CS>
    # ════════════════════════════════════════════
    STATE_NAMES  = ['SAFE', 'WARNING', 'DANGER', 'STOP', 'SENSOR_ERROR']
    ACTION_NAMES = ['NORMAL_MOTION', 'LIMITED_MOTION', 'STOP_MOTION']
    FAULT_NAMES  = ['OK', 'ESTOP', 'LIPO', 'SENSOR', 'RPI_TIMEOUT', 'HAZARD']

    def parse_msg(self, line: str):
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

        # ── SENS: <SENS,gas,flame,battCv,stateCode,actionCode,faultCode,CS> ──
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

            # 가스 데이터 발행
            gas_msg = String()
            gas_msg.data = json.dumps({'gas': gas, 'flag': data['state']})
            self.pub_gas.publish(gas_msg)

            # 화염/온도 대체 발행 (온도 센서는 이 보드에 없어서 flame만 반영)
            temp_msg = String()
            temp_msg.data = json.dumps({'temp': 0.0, 'flame': int(flame)})
            self.pub_temp.publish(temp_msg)

            # 배터리 발행
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

    # ════════════════════════════════════════════
    # 체크섬 계산 및 검증
    # ════════════════════════════════════════════
    def verify_checksum(self, parts: list) -> bool:
        try:
            received_cs = int(parts[-1])
            # CS 제외한 부분으로 계산
            data_str = ','.join(parts[:-1])
            calculated = sum(ord(c) for c in data_str) % 256
            return received_cs == calculated
        except (ValueError, IndexError):
            return False

    def calc_checksum(self, *fields) -> int:
        data_str = ','.join(str(f) for f in fields)
        return sum(ord(c) for c in data_str) % 256

    # ════════════════════════════════════════════
    # 메시지 빌드 및 송신
    # ════════════════════════════════════════════
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
                self.get_logger().warn('ESP32 #1 미연결 상태 - 명령 전송 불가')

    # ════════════════════════════════════════════
    # /amr/cmd_vel 콜백 → MOVE 명령 전송
    # ════════════════════════════════════════════
    def cmd_vel_cb(self, msg: Twist):
        linear  = msg.linear.x    # 전후 속도 -1.0 ~ 1.0
        angular = msg.angular.z   # 좌우 회전 -1.0 ~ 1.0

        # 차동 구동 계산 (PWM 0~255)
        left  = int((linear - angular) * 150)
        right = int((linear + angular) * 150)
        left  = max(-255, min(255, left))
        right = max(-255, min(255, right))

        self.build_and_send('MOVE', left, right)

    # ════════════════════════════════════════════
    # 비상 정지 (mission_orchestrator가 직접 호출)
    # ════════════════════════════════════════════
    def emergency_stop(self):
        self.get_logger().error('!!! AMR 비상 정지 !!!')
        self.build_and_send('STOP')

    # ════════════════════════════════════════════
    # 하트비트: 연결 상태 주기적 로그
    # ════════════════════════════════════════════
    def heartbeat_cb(self, msg: String):
        """RPi 하트비트를 DRIVE로 전달. DRIVE는 이게 끊기면 스스로 정지한다."""
        self.build_and_send('HB')  # 최소 페이로드로 하트비트 신호만 전송

    def heartbeat(self):
        with self.conn_lock:
            status = '연결됨' if self.conn else '미연결'
        self.get_logger().debug(f'ESP32 #1 상태: {status}')

    # ── 이 함수 추가 ──
    def check_timeout(self):
        elapsed = time.time() - self.last_recv_time
        if self.conn and elapsed > 2.0:
            self.get_logger().error('ESP32 #1 응답 없음! 연결 끊김 판정')
            with self.conn_lock:
                self.conn = None



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
PYEOF

cat > arm_bridge/arm_bridge/arm_bridge_node.py << 'PYEOF'
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
PYEOF

cat > arm_controller/arm_controller/arm_controller_node.py << 'PYEOF'
"""
포즈 테이블 기반으로 '놓기' 동작만 담당하는 축소판 로봇팔 제어 노드.
파지는 arm_act_node가 담당한다.
"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class ArmController(Node):
    def __init__(self):
        super().__init__('arm_controller')

        # ── 구독: mission_orchestrator의 "놓기" 요청만 처리 ──
        self.create_subscription(String, '/arm/place_request', self.place_request_cb, 10)
        self.create_subscription(String, '/arm/servo_feedback', self.feedback_cb, 10)

        self.pub_arm_cmd = self.create_publisher(String, '/arm/command', 10)

        # 관절 안전 한계값 (기존 유지)
        self.joint_limits = {
            1: (0,    4095, 2048),
            2: (170,  1877, 1024),
            3: (0,    2048, 1024),
            4: (0,    2048, 1024),
            5: (0,    2048, 1024),
            6: (340,  1365, 340),
        }

        # 프리셋 포즈 — 파지(GRIP)는 arm_act_node가 담당,
        # 여기는 "놓기" 목적지만 남김 (문서: 정밀 IK 불필요)
        self.poses = {
            'HOME':      [2048, 1024, 1024, 1024, 1024, 340],
            'OVERPACK_DRUM':    [2048, 1200, 800, 1024, 1024, 900],  # 적색 → 오버팩 회수 드럼
            'HAZMAT_STORAGE':   [2048, 700,  1300, 900, 1024, 900],  # 황색 → 위험물 보관함
        }

        self.get_logger().info('Arm Controller(축소판) 노드 시작!')

    def place_request_cb(self, msg: String):
        """mission_orchestrator가 목적지 이름을 보내면 해당 프리셋으로 이동"""
        destination = msg.data.strip()
        self.move_to_pose(destination)

    def feedback_cb(self, msg: String):
        pass  # 필요 시 과열/과부하 감시용으로 확장

    def move_to_pose(self, pose_name: str):
        if pose_name not in self.poses:
            self.get_logger().warn(f'알 수 없는 포즈: {pose_name}')
            return

        positions = self.poses[pose_name]
        validated = []
        for i, pos in enumerate(positions):
            joint = i + 1
            min_p, max_p, _ = self.joint_limits[joint]
            safe_pos = max(min_p, min(max_p, pos))
            validated.append(safe_pos)

        msg = String()
        msg.data = ','.join(str(p) for p in validated)
        self.pub_arm_cmd.publish(msg)
        self.get_logger().info(f'포즈 이동: {pose_name} → {validated}')


def main(args=None):
    rclpy.init(args=args)
    node = ArmController()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
PYEOF

cat > hazard_detector/hazard_detector/hazard_detector_node.py << 'PYEOF'
# 물체 분류 (색상 기반 파지 대상)
class ObjectClass:
    CONTAINMENT_BREACH = "CONTAINMENT_BREACH"  # 적색 강체 - 개방·파손, 격리 실패 원인
    HANDLE_CARE = "HANDLE_CARE"                # 황색 변형체 - 취급주의, 정상 업무

# 구역 식별자 (코드용, 절대 안 바뀜) — 표시 이름만 별도
class ZoneId:
    ZONE1 = 1       # 표시 이름: 일반구역
    ZONE2 = 2       # 표시 이름: 취급구역
    ZONE3 = 3       # 표시 이름: 위험구역
    JUNCTION = 4    # 분기점 (모듈로 4 순환, 정차 안 함)

ZONE_DISPLAY_NAMES = {1: "일반구역", 2: "취급구역", 3: "위험구역", 4: "분기점"}

import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Int8
import json

class HazardDetector(Node):
    def __init__(self):
        super().__init__('hazard_detector')

        # Subscribers
        self.create_subscription(String, '/amr/gas',     self.gas_cb,    10)
        self.create_subscription(String, '/amr/temp',    self.temp_cb,   10)
        self.create_subscription(String, '/amr/sensors', self.sensor_cb, 10)
        self.create_subscription(String, '/vision/detected', self.vision_cb, 10)
        self.create_subscription(Int8,   '/mission/zone', self.zone_cb,  10)

        # Publishers
        self.pub_hazard = self.create_publisher(String, '/hazard/detected', 10)

        # 상태 저장
        self.current_zone = 1
        self.gas_data  = None
        self.temp_data = None

        # 구역별 가스 임계값 (구역 컨텍스트)
        self.zone_thresholds = {
            1: {'gas': 300, 'temp': 60},   # ZONE 1 임계값
            2: {'gas': 200, 'temp': 50},   # ZONE 2 임계값
            3: {'gas': 150, 'temp': 45},   # ZONE 3 임계값
        }

        self.get_logger().info('Hazard Detector 노드 시작!')

    # ════════════════════════════════════════════
    # 구역 업데이트
    # ════════════════════════════════════════════
    def zone_cb(self, msg: Int8):
        self.current_zone = msg.data
        self.get_logger().info(f'현재 구역: ZONE {self.current_zone}')

    # ════════════════════════════════════════════
    # 가스 데이터 수신
    # ════════════════════════════════════════════
    def gas_cb(self, msg: String):
        self.gas_data = json.loads(msg.data)
        self.evaluate_hazard()

    # ════════════════════════════════════════════
    # 온도 데이터 수신
    # ════════════════════════════════════════════
    def temp_cb(self, msg: String):
        self.temp_data = json.loads(msg.data)

        # 화염 감지시 즉시 L3
        if self.temp_data.get('flame') == 1:
            self.publish_hazard(3, 'FLAME', 'KY-026 화염 감지')
            return

        self.evaluate_hazard()

    # ════════════════════════════════════════════
    # 센서 데이터 수신
    # ════════════════════════════════════════════
    def sensor_cb(self, msg: String):
        pass  # amr_bridge에서 이미 분리해서 옴

    # ════════════════════════════════════════════
    # 비전 데이터 수신
    # ════════════════════════════════════════════
    def vision_cb(self, msg: String):
        data = json.loads(msg.data)
        self.get_logger().info(
            f'비전 감지: 색상={data.get("color")} '
            f'방위각={data.get("angle")} '
            f'종횡비={data.get("aspect_ratio")}'
        )

    # ════════════════════════════════════════════
    # 위험 등급 판단 (핵심 로직)
    # ════════════════════════════════════════════
    def evaluate_hazard(self):
        if not self.gas_data or not self.temp_data:
            return

        zone     = self.current_zone
        mq2      = self.gas_data.get('mq2', 0)
        mq135    = self.gas_data.get('mq135', 0)
        temp     = self.temp_data.get('temp', 0)
        flag     = self.gas_data.get('flag', 'NORMAL')

        # 구역별 임계값 가져오기
        threshold = self.zone_thresholds.get(zone, self.zone_thresholds[1])
        gas_limit  = threshold['gas']
        temp_limit = threshold['temp']

        # MQ 비율 분석
        ratio = mq2 / mq135 if mq135 > 0 else 0

        # ── 등급 판단 ──────────────────────────
        level = 0
        reason = 'NORMAL'

        # L3: 즉시 위험
        if flag == 'HIGH' and temp > temp_limit:
            level = 3
            reason = '가스+고온 복합 위험'

        # L2: 경고
        elif mq2 > gas_limit or mq135 > gas_limit:
            level = 2
            reason = f'가스 초과 (ZONE {zone} 임계값 {gas_limit})'

        elif temp > temp_limit:
            level = 2
            reason = f'온도 초과 ({temp}°C)'

        # L1: 주의
        elif mq2 > gas_limit * 0.7 or temp > temp_limit * 0.8:
            level = 1
            reason = '주의 수준'

        # L0: 정상
        else:
            level = 0
            reason = 'NORMAL'

        self.publish_hazard(level, reason, f'MQ2={mq2} MQ135={mq135} TEMP={temp}°C ZONE={zone}')

    # ════════════════════════════════════════════
    # 위험 정보 발행
    # ════════════════════════════════════════════
    def publish_hazard(self, level: int, hazard_type: str, detail: str):
        data = {
            'level':  level,
            'type':   hazard_type,
            'detail': detail,
            'zone':   self.current_zone
        }
        msg = String()
        msg.data = json.dumps(data)
        self.pub_hazard.publish(msg)
        self.get_logger().info(f'위험등급 L{level}: {hazard_type} | {detail}')


def main(args=None):
    rclpy.init(args=args)
    node = HazardDetector()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
PYEOF

cat > vision_node/vision_node/vision_node.py << 'PYEOF'
"""
형상 특징(원형도·채움률)과 ROI 제한, 색·형상 불일치 시 소프트 폴백을 추가한 비전 노드.
"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Bool
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
import json
import cv2
import numpy as np
import threading

# ══════════════════════════════════════════════
# 물체 분류 (색상 기반) — arm_act_node와 동일 규칙 공유
# ══════════════════════════════════════════════
class ObjectClass:
    CONTAINMENT_BREACH = "CONTAINMENT_BREACH"
    HANDLE_CARE = "HANDLE_CARE"

COLOR_TO_CLASS = {
    'red': ObjectClass.CONTAINMENT_BREACH,
    'yellow': ObjectClass.HANDLE_CARE,
}

# 형상 기대값 (실물 조달 후 재조정 필요 — 지금은 임시값)
EXPECTED_SHAPE = {
    'red':    {'circularity_min': 0.0, 'circularity_max': 1.0},  # 강체, 형태 안정적
    'yellow': {'circularity_min': 0.0, 'circularity_max': 1.0},  # 변형체, 폭넓게 허용
}


class VisionNode(Node):
    def __init__(self):
        super().__init__('vision_node')

        self.bridge = CvBridge()
        self.latest_frame = None
        self.frame_lock = threading.Lock()

        self.create_subscription(Image, '/camera/image_raw', self.image_cb, 10)
        self.create_subscription(Bool, '/amr/object_near', self.trigger_cb, 10)

        self.pub_vision = self.create_publisher(String, '/vision/detected', 10)

        self.hsv_ranges = {
            'red': [
                (np.array([0,   120, 70]),  np.array([10,  255, 255])),
                (np.array([170, 120, 70]),  np.array([180, 255, 255])),
            ],
            'yellow': [
                (np.array([20, 100, 100]), np.array([35, 255, 255])),
            ],
        }

        # 🔴 프론트 카메라 ROI — 작업공간 높이로 제한 (바닥 오검출 차단)
        # 값은 실제 카메라 마운트 위치 확정 후 재조정 필요
        self.roi_y_start_ratio = 0.3  # 화면 상단 30% 지점부터
        self.roi_y_end_ratio = 0.8    # 화면 상단 80% 지점까지

        self.get_logger().info('Vision Node 시작! (/camera/image_raw 구독 중)')

    def image_cb(self, msg):
        try:
            frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
            with self.frame_lock:
                self.latest_frame = frame
        except Exception as e:
            self.get_logger().warn(f'이미지 변환 실패: {e}')

    def trigger_cb(self, msg: Bool):
        if msg.data:
            with self.frame_lock:
                frame = self.latest_frame.copy() if self.latest_frame is not None else None
            if frame is not None:
                threading.Thread(
                    target=self.analyze_frame, args=(frame,), daemon=True
                ).start()

    def apply_roi(self, frame):
        """작업공간 높이로 ROI 제한 — 바닥 영역 오검출 차단"""
        h, w = frame.shape[:2]
        y1 = int(h * self.roi_y_start_ratio)
        y2 = int(h * self.roi_y_end_ratio)
        return frame[y1:y2, :], y1

    def analyze_frame(self, frame):
        roi_frame, y_offset = self.apply_roi(frame)
        hsv = cv2.cvtColor(roi_frame, cv2.COLOR_BGR2HSV)

        best_result = None
        best_area = 0

        for color_name, ranges in self.hsv_ranges.items():
            mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
            for (lower, upper) in ranges:
                mask |= cv2.inRange(hsv, lower, upper)

            kernel = np.ones((5, 5), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

            contours, _ = cv2.findContours(
                mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            if not contours:
                continue

            largest = max(contours, key=cv2.contourArea)
            area = cv2.contourArea(largest)
            if area < 1000:
                continue

            if area > best_area:
                best_area = area
                rect = cv2.minAreaRect(largest)
                center = rect[0]
                size = rect[1]
                angle = rect[2]

                w_box, h_box = size
                if w_box < h_box:
                    angle = angle + 90
                angle = abs(angle)

                aspect_ratio = round(max(w_box, h_box) / min(w_box, h_box), 2) if min(w_box, h_box) > 0 else 1.0

                # ── 🆕 형상 특징값 (문서 §2-6) ──
                perimeter = cv2.arcLength(largest, True)
                fill_ratio = round(area / (w_box * h_box), 2) if (w_box * h_box) > 0 else 0.0
                circularity = round(
                    (4 * np.pi * area) / (perimeter ** 2), 2
                ) if perimeter > 0 else 0.0

                object_class = COLOR_TO_CLASS.get(color_name)

                # ── 🆕 색·형상 불일치 시 소프트 모드 폴백 판정 ──
                shape_ok = self.check_shape_consistency(color_name, circularity)
                mode = 'NORMAL' if shape_ok else 'SOFT_FALLBACK'

                best_result = {
                    'color': color_name,
                    'object_class': object_class,
                    'angle': round(angle, 1),
                    'aspect_ratio': aspect_ratio,
                    'area': int(area),
                    'fill_ratio': fill_ratio,
                    'circularity': circularity,
                    'mode': mode,
                    'center_x': round(center[0], 1),
                    'center_y': round(center[1] + y_offset, 1),  # ROI 오프셋 복원
                }

        if best_result:
            msg = String()
            msg.data = json.dumps(best_result)
            self.pub_vision.publish(msg)
            self.get_logger().info(
                f'감지: {best_result["color"]} ({best_result["object_class"]}) '
                f'각도={best_result["angle"]}° 원형도={best_result["circularity"]} '
                f'모드={best_result["mode"]}'
            )
        else:
            self.get_logger().debug('감지된 물체 없음')

    def check_shape_consistency(self, color_name, circularity):
        """색상 기대 형상과 실측 형상이 크게 어긋나면 소프트 모드로 폴백
        (임계값은 실물 조달 후 재조정 필요 — 지금은 항상 통과하도록 관대하게 설정)"""
        expected = EXPECTED_SHAPE.get(color_name)
        if not expected:
            return True
        return expected['circularity_min'] <= circularity <= expected['circularity_max']


def main(args=None):
    rclpy.init(args=args)
    node = VisionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
PYEOF

cat > arm_act_node/arm_act_node/arm_act_node.py << 'PYEOF'
"""
ACT 정책으로 파지 동작을 추론하는 노드. 정책 미탑재 시 더미 시퀀스로 폴백한다.
"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
import json
import threading

# ══════════════════════════════════════════════
# 물체 분류 (색상 기반) — 문서 §2-6 개명 규칙
# ══════════════════════════════════════════════
class ObjectClass:
    CONTAINMENT_BREACH = "CONTAINMENT_BREACH"  # 적색 강체
    HANDLE_CARE = "HANDLE_CARE"                # 황색 변형체


COLOR_TO_CLASS = {
    'red': ObjectClass.CONTAINMENT_BREACH,
    'yellow': ObjectClass.HANDLE_CARE,
}

# 정책 파일 경로 (학습 완료 후 채워질 자리)
POLICY_PATHS = {
    ObjectClass.CONTAINMENT_BREACH: None,  # TODO: 적색용 체크포인트 경로
    ObjectClass.HANDLE_CARE: None,         # TODO: 황색용 체크포인트 경로
}


class ArmActNode(Node):
    def __init__(self):
        super().__init__('arm_act_node')
        self.bridge = CvBridge()

        # ── 카메라 구독 (손목 카메라는 아직 미장착 — 프론트만 우선 연결) ──
        self.latest_front_frame = None
        self.latest_wrist_frame = None
        self.frame_lock = threading.Lock()

        self.create_subscription(Image, '/camera/image_raw', self.front_image_cb, 10)
        # TODO: 손목 카메라 장착 후 아래 구독 추가
        # self.create_subscription(Image, '/camera/wrist/image_raw', self.wrist_image_cb, 10)

        # ── 미션 신호 구독 ──
        self.create_subscription(String, '/hazard/detected', self.hazard_cb, 10)
        self.create_subscription(String, '/vision/detected', self.vision_cb, 10)
        self.create_subscription(String, '/arm/servo_feedback', self.feedback_cb, 10)
        self.create_subscription(String, '/arm/grip_request', self.grip_request_cb, 10)

        # ── arm_bridge로 명령 발행 (기존 arm_controller와 동일 채널 재사용) ──
        self.pub_arm_cmd = self.create_publisher(String, '/arm/command', 10)
        self.pub_grip_cmd = self.create_publisher(String, '/arm/grip_cmd', 10)

        # ── 정책 2개 로드 (문서: 미션 시작 전 워밍업 필수) ──
        self.policies = {}
        self.load_policies()
        self.warmup_all()

        self.current_target_class = None
        self.get_logger().info('Arm ACT Node 시작!')

    # ════════════════════════════════════════════
    # 카메라 콜백
    # ════════════════════════════════════════════
    def front_image_cb(self, msg):
        try:
            frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
            with self.frame_lock:
                self.latest_front_frame = frame
        except Exception as e:
            self.get_logger().warn(f'프론트 이미지 변환 실패: {e}')

    def wrist_image_cb(self, msg):
        try:
            frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
            with self.frame_lock:
                self.latest_wrist_frame = frame
        except Exception as e:
            self.get_logger().warn(f'손목 이미지 변환 실패: {e}')

    # ════════════════════════════════════════════
    # 정책 로드 / 워밍업
    # ════════════════════════════════════════════
    def load_policies(self):
        for obj_class, path in POLICY_PATHS.items():
            if path is None:
                self.get_logger().warn(
                    f'{obj_class} 정책 체크포인트 미지정 — 더미 모드로 동작'
                )
                self.policies[obj_class] = None
                continue
            # TODO: 실제 체크포인트 준비되면 여기서 ACTPolicy.from_pretrained(path) 로드
            self.policies[obj_class] = None

    def warmup_all(self):
        # TODO: 실제 정책 로드 후, 각 정책에 대해 더미 입력으로 1회 추론해 워밍업
        # (문서 §5: 미션 시작 전 워밍업 안 하면 첫 파지에서만 지연이 튄다)
        self.get_logger().info('정책 워밍업 단계 (더미 모드 - 스킵)')

    # ════════════════════════════════════════════
    # 미션 신호 콜백
    # ════════════════════════════════════════════
    def hazard_cb(self, msg: String):
        pass  # 필요 시 위험등급에 따른 추가 로직

    def vision_cb(self, msg: String):
        data = json.loads(msg.data)
        color = data.get('color')
        self.current_target_class = COLOR_TO_CLASS.get(color)
        self.get_logger().info(
            f'비전 감지 → 대상 분류: {self.current_target_class}'
        )

    def grip_request_cb(self, msg: String):
        # mission_orchestrator가 GRIP 상태 진입 시 호출
        obj_class = self.current_target_class
        if obj_class is None:
            self.get_logger().warn('분류 안 된 상태에서 파지 요청 — 스킵')
            return

        policy = self.policies.get(obj_class)
        if policy is None:
            self.get_logger().warn(
                f'{obj_class} 정책 없음 — 더미 접근/파지 시퀀스로 대체'
            )
            self.run_dummy_grip_sequence(obj_class)
            return

        # TODO: 실제 정책 추론 루프
        # obs = self.build_observation()
        # action_chunk = policy.select_action(obs)
        # self.publish_action(action_chunk)

    def feedback_cb(self, msg: String):
        pass  # 파지 성공/실패 판정은 mission_orchestrator가 계속 담당

    # ════════════════════════════════════════════
    # 더미 폴백 (정책 없을 때 임시 동작 — 실제 파지는 안 됨, 통신 검증용)
    # ════════════════════════════════════════════
    def run_dummy_grip_sequence(self, obj_class):
        threshold = 40 if obj_class == ObjectClass.HANDLE_CARE else 80
        grip_msg = String()
        grip_msg.data = f'CLOSE,{threshold}'
        self.pub_grip_cmd.publish(grip_msg)
        self.get_logger().info(f'[더미] GRIP 명령 전송: threshold={threshold}%')


def main(args=None):
    rclpy.init(args=args)
    node = ArmActNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
PYEOF

commit "2026-08-04 22:02:33 +0900" "feat: 하트비트 기반 비상정지 + EMERGENCY 수동 복귀 구현

문서 §5 확정사항 반영: 계층2 정지는 명령이 아니라 하트비트.
- mission_orchestrator: 0.3초 주기 /mission/heartbeat 발행
  (타임아웃 1초 예정 기준 1/3 이하), EMERGENCY 시 발행 중단
- amr_bridge: /mission/heartbeat 구독 -> DRIVE로 <HB,CS> 전달 (뼈대)
- EMERGENCY 수동 복귀: /mission/reset, confirm='SAFE_TO_RESUME' 필드
  검증 후에만 PATROL 복귀 + 하트비트 재개 + 감지정보 초기화
실측 검증: heartbeat 3.334Hz 안정 확인, FLAME시 중단 확인,
confirm 없는 reset 거부/confirm 포함 reset 정상 복귀 확인.
DRIVE 펌웨어측 HB 수신/타임아웃 로직은 승환 담당, 미구현.
이 시점 sensor_bridge/dashboard/index.html은 아직 거리센서 추가 전
구버전 프로토콜(단일 gas, 8필드) 그대로임 -- 다음 커밋에서 교체."

echo "================================================"
echo "M12. ESP32 실제 센서 프로토콜 반영 (MQ135/MQ2/거리 분리)"
echo "================================================"

cat > sensor_bridge/sensor_bridge/sensor_bridge_node.py << 'PYEOF'
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

        # ── Publishers: ENV 보드 데이터 → ROS2 토픽 ──
        self.pub_gas      = self.create_publisher(String,  '/env/gas',      10)
        self.pub_temp     = self.create_publisher(String,  '/env/temp',     10)
        self.pub_battery  = self.create_publisher(Float32, '/env/battery',  10)
        self.pub_state    = self.create_publisher(String,  '/env/state',    10)
        self.pub_distance = self.create_publisher(String,  '/env/distance', 10)

        self.conn = None
        self.conn_lock = threading.Lock()
        self.last_recv_time = time.time()

        threading.Thread(target=self.tcp_server, daemon=True).start()
        self.create_timer(0.5, self.check_timeout)
        self.create_timer(0.5, self.heartbeat)

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

    # 실제 프로토콜: <SENS,MQ135,MQ2,FLAME,BAT,STATE,ACTION,FAULT,DISTANCE,CHECKSUM>
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
        if cmd == 'SENS' and len(parts) == 10:
            mq135       = int(parts[1])
            mq2         = int(parts[2])
            flame       = int(parts[3])
            batt_cv     = int(parts[4])
            state_code  = int(parts[5])
            action_code = int(parts[6])
            fault_code  = int(parts[7])
            distance    = int(parts[8])   # -1이면 측정 실패

            self.pub_gas.publish(String(data=json.dumps({
                'mq135': mq135,
                'mq2': mq2,
            })))
            self.pub_temp.publish(String(data=json.dumps({'flame': int(flame)})))
            self.pub_battery.publish(Float32(data=batt_cv / 100.0))
            self.pub_distance.publish(String(data=json.dumps({
                'distance_mm': None if distance == -1 else distance,
            })))
            self.pub_state.publish(String(data=json.dumps({
                'state': STATE_NAMES[state_code] if state_code < len(STATE_NAMES) else f'UNKNOWN({state_code})',
                'action': ACTION_NAMES[action_code] if action_code < len(ACTION_NAMES) else f'UNKNOWN({action_code})',
                'fault': FAULT_NAMES[fault_code] if fault_code < len(FAULT_NAMES) else f'UNKNOWN({fault_code})',
            })))

            dist_str = '측정실패' if distance == -1 else f'{distance}mm'
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
            self.get_logger().error('ENV 보드 응답 없음! 연결 끊김 판정')
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
PYEOF

cat > hazardbot_dashboard/hazardbot_dashboard/dashboard_node.py << 'PYEOF'
import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Float32
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
import json
import threading
import subprocess
import os
import time
import cv2

from ament_index_python.packages import get_package_share_directory
from flask import Flask, render_template, Response
from flask_socketio import SocketIO

# 템플릿 경로
pkg_share = get_package_share_directory('hazardbot_dashboard')
template_dir = os.path.join(pkg_share, 'templates')

app = Flask(__name__, template_folder=template_dir)
socketio = SocketIO(app, cors_allowed_origins='*')

# 전역 데이터 저장소
dashboard_data = {
    'mission_state': 'IDLE',
    'zone': 1,
    'zone_display': '일반구역',
    'sensors': {'dist_mm': 0, 'ir': [0,0,0,0,0]},
    'gas':     {'mq2': 0, 'mq135': 0, 'flag': 'NORMAL'},
    'temp':    {'temp': 0.0, 'flame': 0},
    'battery': 0.0,
    'hazard':  {'level': 0, 'type': 'NORMAL'},
    'servo_feedback': {},
    'vision':  {'color': None, 'angle': None},
    'rpi_health': {'cpu_temp': 0.0, 'throttled': '0x0'},
    'amr_connected': False,
    'arm_connected': False,
    # ── 신규: ENV 보드 데이터 ──
    'env_gas': {'gas': 0},
    'env_temp': {'flame': 0},
    'env_battery': 0.0,
    'env_distance': {'distance_mm': None},
    'env_state': {'state': 'SAFE', 'action': 'NORMAL_MOTION', 'fault': 'OK'},
    # ── 신규: 구역별 임계값 (문서 §2 판정 매트릭스) ──
    'zone_thresholds': {
        1: {'gas_alert': 300, 'gas_label': '일반구역 — 가스 검출시 격리실패'},
        2: {'gas_alert': 500, 'gas_label': '취급구역 — 가스 주의'},
        3: {'gas_alert': 9999, 'gas_label': '위험구역 — 가스 정상범위(설계상 무시)'},
    },
}

# Flask 라우트에서 노드 인스턴스에 접근하기 위한 전역 참조
dashboard_node_ref = None


class DashboardNode(Node):
    def __init__(self):
        super().__init__('hazardbot_dashboard')
        self.bridge = CvBridge()
        self.latest_frame = None
        self.frame_lock = threading.Lock()

        # 카메라 토픽 구독
        self.create_subscription(
            Image, '/camera/image_raw', self.image_cb, 10)

        # Subscribers
        self.create_subscription(
            String, '/mission/state',     self.mission_cb,  10)
        self.create_subscription(
            String, '/amr/sensors',       self.sensor_cb,   10)
        self.create_subscription(
            String, '/amr/gas',           self.gas_cb,      10)
        self.create_subscription(
            String, '/amr/temp',          self.temp_cb,     10)
        self.create_subscription(
            Float32, '/amr/battery',      self.battery_cb,  10)
        self.create_subscription(
            String, '/hazard/detected',   self.hazard_cb,   10)
        self.create_subscription(
            String, '/arm/servo_feedback',self.servo_cb,    10)
        self.create_subscription(
            String, '/vision/detected',   self.vision_cb,   10)

        # ── ENV 보드(sensor_bridge) 토픽 추가 구독 ──
        self.create_subscription(String, '/env/gas',      self.env_gas_cb,      10)
        self.create_subscription(String, '/env/temp',     self.env_temp_cb,     10)
        self.create_subscription(Float32, '/env/battery', self.env_battery_cb,  10)
        self.create_subscription(String, '/env/state',    self.env_state_cb,    10)
        self.create_subscription(String, '/env/distance', self.env_distance_cb, 10)

        # RPi5 헬스 타이머 (5초마다)
        self.create_timer(5.0, self.check_rpi_health)

        # 대시보드 전송 타이머 (1초마다)
        self.create_timer(1.0, self.broadcast_data)

        self.get_logger().info('Dashboard 노드 시작!')

    # ════════════════════════════════════════════
    # 토픽 콜백들
    # ════════════════════════════════════════════
    def mission_cb(self, msg: String):
        data = json.loads(msg.data)
        dashboard_data['mission_state'] = data.get('state', 'IDLE')
        dashboard_data['zone'] = data.get('zone', 1)
        dashboard_data['zone_display'] = data.get('zone_display', '알수없음')

    def sensor_cb(self, msg: String):
        dashboard_data['sensors'] = json.loads(msg.data)

    def gas_cb(self, msg: String):
        dashboard_data['gas'] = json.loads(msg.data)

    def temp_cb(self, msg: String):
        dashboard_data['temp'] = json.loads(msg.data)

    def battery_cb(self, msg: Float32):
        dashboard_data['battery'] = round(msg.data, 2)

    def hazard_cb(self, msg: String):
        dashboard_data['hazard'] = json.loads(msg.data)

    def servo_cb(self, msg: String):
        data = json.loads(msg.data)
        servo_id = str(data.get('id'))
        dashboard_data['servo_feedback'][servo_id] = data

    def vision_cb(self, msg: String):
        dashboard_data['vision'] = json.loads(msg.data)

    def env_gas_cb(self, msg: String):
        dashboard_data['env_gas'] = json.loads(msg.data)

    def env_temp_cb(self, msg: String):
        dashboard_data['env_temp'] = json.loads(msg.data)

    def env_battery_cb(self, msg: Float32):
        dashboard_data['env_battery'] = round(msg.data, 2)

    def env_state_cb(self, msg: String):
        dashboard_data['env_state'] = json.loads(msg.data)

    def env_distance_cb(self, msg: String):
        dashboard_data['env_distance'] = json.loads(msg.data)

    def image_cb(self, msg):
        try:
            frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
            with self.frame_lock:
                self.latest_frame = frame
        except Exception as e:
            self.get_logger().warn(f'이미지 변환 실패: {e}')

    # ════════════════════════════════════════════
    # RPi5 헬스 체크
    # ════════════════════════════════════════════
    def check_rpi_health(self):
        try:
            temp_raw = subprocess.check_output(
                ['vcgencmd', 'measure_temp']
            ).decode().strip()
            cpu_temp = float(temp_raw.replace("temp=", "").replace("'C", ""))

            throttled = subprocess.check_output(
                ['vcgencmd', 'get_throttled']
            ).decode().strip().split('=')[1]

            dashboard_data['rpi_health'] = {
                'cpu_temp': cpu_temp,
                'throttled': throttled
            }

            if cpu_temp > 80:
                self.get_logger().warn(f'RPi5 고온! {cpu_temp}°C')
            if throttled != '0x0':
                self.get_logger().warn(f'RPi5 스로틀링! {throttled}')

        except Exception as e:
            self.get_logger().debug(f'헬스 체크 오류: {e}')

    # ════════════════════════════════════════════
    # WebSocket으로 데이터 전송
    # ════════════════════════════════════════════
    def broadcast_data(self):
        socketio.emit('update', dashboard_data)


# ════════════════════════════════════════════
# Flask 라우트
# ════════════════════════════════════════════
def generate_frames():
    while True:
        frame = None
        if dashboard_node_ref is not None:
            with dashboard_node_ref.frame_lock:
                if dashboard_node_ref.latest_frame is not None:
                    frame = dashboard_node_ref.latest_frame.copy()

        if frame is None:
            time.sleep(0.1)
            continue

        _, buffer = cv2.imencode('.jpg', frame)
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n'
               + buffer.tobytes() + b'\r\n')


@app.route('/video')
def video():
    return Response(
        generate_frames(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/data')
def api_data():
    return json.dumps(dashboard_data)


def main(args=None):
    global dashboard_node_ref

    rclpy.init(args=args)
    node = DashboardNode()
    dashboard_node_ref = node   # Flask 라우트에서 접근 가능하도록 등록

    flask_thread = threading.Thread(
        target=lambda: socketio.run(
            app,
            host='0.0.0.0',
            port=8080,
            debug=False,
            allow_unsafe_werkzeug=True
        ),
        daemon=True
    )
    flask_thread.start()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
PYEOF

cat > hazardbot_dashboard/templates/index.html << 'HTMLEOF'
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>HazardBot Dashboard</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            background: #0a0a0a;
            color: #e0e0e0;
            font-family: 'Courier New', monospace;
            padding: 16px;
        }

        h1 {
            text-align: center;
            color: #00ff88;
            font-size: 24px;
            margin-bottom: 16px;
            letter-spacing: 4px;
        }

        .grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 12px;
        }

        .card {
            background: #1a1a1a;
            border: 1px solid #333;
            border-radius: 8px;
            padding: 16px;
        }

        .card h3 {
            color: #00ff88;
            font-size: 12px;
            letter-spacing: 2px;
            margin-bottom: 12px;
            border-bottom: 1px solid #333;
            padding-bottom: 8px;
        }

        /* 미션 상태 */
        .state-badge {
            display: inline-block;
            padding: 8px 16px;
            border-radius: 4px;
            font-size: 20px;
            font-weight: bold;
            letter-spacing: 2px;
        }
        .state-IDLE      { background:#333; color:#aaa; }
        .state-PATROL    { background:#004400; color:#00ff88; }
        .state-DETECTED  { background:#444400; color:#ffff00; }
        .state-APPROACH  { background:#004444; color:#00ffff; }
        .state-GRIP      { background:#004488; color:#4488ff; }
        .state-TRANSPORT { background:#440044; color:#ff44ff; }
        .state-ISOLATE   { background:#004488; color:#44aaff; }
        .state-EMERGENCY { background:#440000; color:#ff4444; }

        /* 위험 등급 */
        .level-badge {
            font-size: 36px;
            font-weight: bold;
            text-align: center;
            padding: 8px;
        }
        .level-0 { color: #00ff88; }
        .level-1 { color: #ffff00; }
        .level-2 { color: #ff8800; }
        .level-3 { color: #ff0000; }

        /* 센서값 */
        .sensor-row {
            display: flex;
            justify-content: space-between;
            padding: 4px 0;
            border-bottom: 1px solid #222;
            font-size: 14px;
        }
        .sensor-row .label { color: #888; }
        .sensor-row .value { color: #fff; font-weight: bold; }

        /* 서보 */
        .servo-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 8px;
        }
        .servo-item {
            background: #222;
            border-radius: 4px;
            padding: 8px;
            text-align: center;
            font-size: 11px;
        }
        .servo-item .name { color: #888; margin-bottom: 4px; }
        .servo-item .val  { color: #00ff88; font-size: 13px; }

        /* RPi 헬스 */
        .health-temp {
            font-size: 32px;
            font-weight: bold;
            text-align: center;
        }
        .temp-ok   { color: #00ff88; }
        .temp-warn { color: #ffff00; }
        .temp-hot  { color: #ff4444; }

        /* 연결 상태 */
        .conn-dot {
            display: inline-block;
            width: 10px; height: 10px;
            border-radius: 50%;
            margin-right: 6px;
        }
        .conn-ok   { background: #00ff88; }
        .conn-fail { background: #ff4444; }

        /* 배터리 */
        .battery-bar {
            height: 20px;
            background: #222;
            border-radius: 4px;
            overflow: hidden;
            margin-top: 8px;
        }
        .battery-fill {
            height: 100%;
            border-radius: 4px;
            transition: width 0.5s;
        }
    </style>
</head>
<body>
    <h1>⚠ HAZARDBOT DASHBOARD</h1>

    <div class="grid">

        <!-- 미션 상태 -->
        <div class="card">
            <h3>MISSION STATE</h3>
            <div id="mission-state" class="state-badge state-IDLE">IDLE</div>
            <div style="margin-top:8px; color:#888; font-size:12px">
                구역: <span id="zone-display" style="color:#fff; font-weight:bold">일반구역</span>
            </div>
        </div>

        <!-- 위험 등급 -->
        <div class="card">
            <h3>HAZARD LEVEL</h3>
            <div id="hazard-level" class="level-badge level-0">L0</div>
            <div id="hazard-type" style="color:#888; font-size:12px; margin-top:4px">NORMAL</div>
        </div>

        <!-- RPi5 헬스 -->
        <div class="card">
            <h3>RPi5 HEALTH</h3>
            <div id="cpu-temp" class="health-temp temp-ok">0°C</div>
            <div style="margin-top:8px; font-size:12px">
                스로틀: <span id="throttled" style="color:#00ff88">0x0</span>
            </div>
        </div>

        <!-- 센서 데이터 -->
        <div class="card">
            <h3>SENSORS</h3>
            <div class="sensor-row">
                <span class="label">거리 (VL53L1X)</span>
                <span class="value"><span id="dist">0</span> mm</span>
            </div>
            <div class="sensor-row">
                <span class="label">MQ-2 (가연성)</span>
                <span class="value"><span id="mq2">0</span> ppm</span>
            </div>
            <div class="sensor-row">
                <span class="label">MQ-135 (VOC)</span>
                <span class="value"><span id="mq135">0</span> ppm</span>
            </div>
            <div class="sensor-row">
                <span class="label">온도</span>
                <span class="value"><span id="temp">0</span> °C</span>
            </div>
            <div class="sensor-row">
                <span class="label">화염</span>
                <span class="value" id="flame">없음</span>
            </div>
        </div>

        <!-- 비전 -->
        <div class="card">
            <h3>VISION</h3>
            <div class="sensor-row">
                <span class="label">색상</span>
                <span class="value" id="vision-color">-</span>
            </div>
            <div class="sensor-row">
                <span class="label">방위각</span>
                <span class="value"><span id="vision-angle">-</span>°</span>
            </div>
            <div class="sensor-row">
                <span class="label">종횡비</span>
                <span class="value" id="vision-aspect">-</span>
            </div>
        </div>

        <!-- 배터리 -->
        <div class="card">
            <h3>BATTERY</h3>
            <div style="font-size:28px; font-weight:bold; color:#00ff88">
                <span id="battery-v">0.0</span> V
            </div>
            <div class="battery-bar">
                <div id="battery-fill" class="battery-fill"
                     style="width:0%; background:#00ff88"></div>
            </div>
            <div style="font-size:12px; color:#888; margin-top:4px">
                <span id="battery-pct">0</span>%
            </div>
        </div>

        <!-- 구역별 판정 매트릭스 — 핵심 화면 증거 -->
        <div class="card" style="grid-column: span 3">
            <h3>구역별 판정 — 같은 값, 다른 판정</h3>
            <table style="width:100%; border-collapse:collapse; font-size:13px;">
                <tr style="border-bottom:1px solid #333; color:#888;">
                    <th style="text-align:left; padding:6px;">구역</th>
                    <th style="text-align:left; padding:6px;">가스(MQ) 원시값</th>
                    <th style="text-align:left; padding:6px;">이 구역 임계값</th>
                    <th style="text-align:left; padding:6px;">판정</th>
                </tr>
                <tr id="zone-row-1" style="border-bottom:1px solid #222;">
                    <td style="padding:6px; color:#fff;">일반구역</td>
                    <td style="padding:6px;"><span id="zone1-gas">-</span></td>
                    <td style="padding:6px; color:#888;">300 이상 = 격리실패</td>
                    <td style="padding:6px;" id="zone1-verdict">-</td>
                </tr>
                <tr id="zone-row-2" style="border-bottom:1px solid #222;">
                    <td style="padding:6px; color:#fff;">취급구역</td>
                    <td style="padding:6px;"><span id="zone2-gas">-</span></td>
                    <td style="padding:6px; color:#888;">500 이상 = 주의</td>
                    <td style="padding:6px;" id="zone2-verdict">-</td>
                </tr>
                <tr id="zone-row-3">
                    <td style="padding:6px; color:#fff;">위험구역</td>
                    <td style="padding:6px;"><span id="zone3-gas">-</span></td>
                    <td style="padding:6px; color:#888;">가스는 정상범위 (설계상 무시)</td>
                    <td style="padding:6px;" id="zone3-verdict">-</td>
                </tr>
            </table>
            <div style="margin-top:10px; font-size:11px; color:#666;">
                같은 가스 수치라도 일반구역에서는 격리 실패를 뜻하고, 위험구역에서는 정상 범위입니다.
                위험구역에서 위험한 것은 가스가 아니라 점화원입니다.
            </div>
        </div>

        <!-- ENV 보드 상태 -->
        <div class="card">
            <h3>ENV BOARD (sensor_bridge)</h3>
            <div class="sensor-row">
                <span class="label">MQ-135(원시값)</span>
                <span class="value" id="env-mq135">0</span>
            </div>
            <div class="sensor-row">
                <span class="label">MQ-2(원시값)</span>
                <span class="value" id="env-mq2">0</span>
            </div>
            <div class="sensor-row">
                <span class="label">화염</span>
                <span class="value" id="env-flame">없음</span>
            </div>
            <div class="sensor-row">
                <span class="label">거리</span>
                <span class="value" id="env-distance">-</span>
            </div>
            <div class="sensor-row">
                <span class="label">배터리</span>
                <span class="value"><span id="env-battery">0.0</span> V</span>
            </div>
            <div class="sensor-row">
                <span class="label">상태</span>
                <span class="value" id="env-state">-</span>
            </div>
            <div class="sensor-row">
                <span class="label">폴트</span>
                <span class="value" id="env-fault">-</span>
            </div>
        </div>

        <!-- 서보 피드백 -->
        <div class="card" style="grid-column: span 2">
            <h3>SERVO FEEDBACK (STS3215)</h3>
            <div class="servo-grid">
                <div class="servo-item">
                    <div class="name">1 Base</div>
                    <div class="val" id="s1-pos">-</div>
                    <div style="color:#888;font-size:10px">Load: <span id="s1-load">-</span>%</div>
                    <div style="color:#888;font-size:10px">Temp: <span id="s1-temp">-</span>°C</div>
                </div>
                <div class="servo-item">
                    <div class="name">2 Shoulder</div>
                    <div class="val" id="s2-pos">-</div>
                    <div style="color:#888;font-size:10px">Load: <span id="s2-load">-</span>%</div>
                    <div style="color:#888;font-size:10px">Temp: <span id="s2-temp">-</span>°C</div>
                </div>
                <div class="servo-item">
                    <div class="name">3 Elbow</div>
                    <div class="val" id="s3-pos">-</div>
                    <div style="color:#888;font-size:10px">Load: <span id="s3-load">-</span>%</div>
                    <div style="color:#888;font-size:10px">Temp: <span id="s3-temp">-</span>°C</div>
                </div>
                <div class="servo-item">
                    <div class="name">4 Wrist Pitch</div>
                    <div class="val" id="s4-pos">-</div>
                    <div style="color:#888;font-size:10px">Load: <span id="s4-load">-</span>%</div>
                    <div style="color:#888;font-size:10px">Temp: <span id="s4-temp">-</span>°C</div>
                </div>
                <div class="servo-item">
                    <div class="name">5 Wrist Roll</div>
                    <div class="val" id="s5-pos">-</div>
                    <div style="color:#888;font-size:10px">Load: <span id="s5-load">-</span>%</div>
                    <div style="color:#888;font-size:10px">Temp: <span id="s5-temp">-</span>°C</div>
                </div>
                <div class="servo-item">
                    <div class="name">6 Gripper</div>
                    <div class="val" id="s6-pos">-</div>
                    <div style="color:#888;font-size:10px">Load: <span id="s6-load">-</span>%</div>
                    <div style="color:#888;font-size:10px">Temp: <span id="s6-temp">-</span>°C</div>
                </div>
            </div>
        </div>

        <!-- 이벤트 로그 -->
        <div class="card">
            <h3>EVENT LOG</h3>
            <div id="event-log"
                 style="font-size:11px; color:#888; height:120px;
                        overflow-y:auto; line-height:1.6">
            </div>
        </div>
        <!-- 카메라 영상 -->
        <div class="card" style="grid-column: span 3">
            <h3>CAMERA (OpenCV)</h3>
            <img src="/video"
                style="width:100%; border-radius:4px;"
                onerror="this.style.display='none'">
        </div>
    </div>

    <script>
        const socket = io();
        const log = document.getElementById('event-log');

        function addLog(msg) {
            const time = new Date().toLocaleTimeString();
            log.innerHTML += `<div>[${time}] ${msg}</div>`;
            log.scrollTop = log.scrollHeight;
        }

        socket.on('update', (data) => {

            // 미션 상태
            const stateEl = document.getElementById('mission-state');
            stateEl.textContent = data.mission_state;
            stateEl.className = `state-badge state-${data.mission_state}`;

            // 구역 표시 이름
            document.getElementById('zone-display').textContent =
                data.zone_display || '알수없음';

            // 위험 등급
            const level = data.hazard.level || 0;
            const levelEl = document.getElementById('hazard-level');
            levelEl.textContent = `L${level}`;
            levelEl.className = `level-badge level-${level}`;
            document.getElementById('hazard-type').textContent =
                data.hazard.type || 'NORMAL';

            // 센서
            document.getElementById('dist').textContent =
                data.sensors.dist_mm || 0;
            document.getElementById('mq2').textContent =
                data.gas.mq2 || 0;
            document.getElementById('mq135').textContent =
                data.gas.mq135 || 0;
            document.getElementById('temp').textContent =
                data.temp.temp || 0;
            document.getElementById('flame').textContent =
                data.temp.flame ? '🔥 감지!' : '없음';
            document.getElementById('flame').style.color =
                data.temp.flame ? '#ff4444' : '#00ff88';

            // 비전
            document.getElementById('vision-color').textContent =
                data.vision.color || '-';
            document.getElementById('vision-angle').textContent =
                data.vision.angle || '-';

            // 배터리
            const volt = data.battery || 0;
            const pct  = Math.max(0, Math.min(100,
                ((volt - 9.9) / (12.6 - 9.9)) * 100
            )).toFixed(0);
            document.getElementById('battery-v').textContent =
                volt.toFixed(1);
            document.getElementById('battery-pct').textContent = pct;
            const fill = document.getElementById('battery-fill');
            fill.style.width = pct + '%';
            fill.style.background = pct > 50 ? '#00ff88' :
                                    pct > 20 ? '#ffff00' : '#ff4444';

            // RPi5 헬스
            const cpuTemp = data.rpi_health.cpu_temp || 0;
            const tempEl  = document.getElementById('cpu-temp');
            tempEl.textContent = cpuTemp.toFixed(1) + '°C';
            tempEl.className = 'health-temp ' +
                (cpuTemp > 80 ? 'temp-hot' :
                cpuTemp > 65 ? 'temp-warn' : 'temp-ok');
            const throttled = data.rpi_health.throttled || '0x0';
            const thrEl = document.getElementById('throttled');
            thrEl.textContent = throttled;
            thrEl.style.color = throttled === '0x0' ? '#00ff88' : '#ff4444';

            // 서보 피드백
            for (let i = 1; i <= 6; i++) {
                const s = data.servo_feedback[String(i)];
                if (s) {
                    document.getElementById(`s${i}-pos`).textContent  = s.pos;
                    document.getElementById(`s${i}-load`).textContent = s.load;
                    document.getElementById(`s${i}-temp`).textContent = s.temp;
                }
            }

            // ENV 보드
            const mq135 = (data.env_gas && data.env_gas.mq135) || 0;
            const mq2 = (data.env_gas && data.env_gas.mq2) || 0;
            const envGas = mq135;   // 판정 매트릭스 기준값 (MQ-135 사용)

            document.getElementById('env-mq135').textContent = mq135;
            document.getElementById('env-mq2').textContent = mq2;
            document.getElementById('env-flame').textContent =
                (data.env_temp && data.env_temp.flame) ? '🔥 감지!' : '없음';

            const dist = data.env_distance && data.env_distance.distance_mm;
            document.getElementById('env-distance').textContent =
                (dist === null || dist === undefined) ? '측정실패' : dist + 'mm';

            document.getElementById('env-battery').textContent =
                (data.env_battery || 0).toFixed(1);
            document.getElementById('env-state').textContent =
                (data.env_state && data.env_state.state) || '-';
            document.getElementById('env-fault').textContent =
                (data.env_state && data.env_state.fault) || '-';

            // 구역별 판정 매트릭스 — 같은 값, 다른 판정
            const thresholds = data.zone_thresholds || {};

            document.getElementById('zone1-gas').textContent = envGas;
            document.getElementById('zone2-gas').textContent = envGas;
            document.getElementById('zone3-gas').textContent = envGas;

            const t1 = (thresholds[1] && thresholds[1].gas_alert) || 300;
            const t2 = (thresholds[2] && thresholds[2].gas_alert) || 500;

            const v1 = document.getElementById('zone1-verdict');
            v1.textContent = envGas >= t1 ? '🔴 격리 실패' : '🟢 정상';
            v1.style.color = envGas >= t1 ? '#ff4444' : '#00ff88';

            const v2 = document.getElementById('zone2-verdict');
            v2.textContent = envGas >= t2 ? '🟡 주의' : '🟢 정상';
            v2.style.color = envGas >= t2 ? '#ffff00' : '#00ff88';

            const v3 = document.getElementById('zone3-verdict');
            v3.textContent = '🟢 정상 범위 (설계상 무시)';
            v3.style.color = '#00ff88';

            // 현재 구역 강조
            for (let z = 1; z <= 3; z++) {
                const row = document.getElementById(`zone-row-${z}`);
                if (row) {
                    if (z === data.zone) {
                        row.style.background = '#1a2a1a';
                        row.style.outline = '1px solid #00ff88';
                    } else {
                        row.style.background = 'transparent';
                        row.style.outline = 'none';
                    }
                }
            }
        });

        socket.on('connect', () => addLog('대시보드 연결됨'));
        socket.on('disconnect', () => addLog('연결 끊김'));

        addLog('HazardBot Dashboard 시작');
    </script>
</body>
</html>
HTMLEOF

commit "2026-08-06 19:20:00 +0900" "feat: ESP32 실제 센서 프로토콜(MQ135/MQ2/거리 분리) 반영

ESP32에서 실제로 보내는 형식이 애초 가정한 것과 다름을 확인:
<SENS,MQ135,MQ2,FLAME,BAT,STATE,ACTION,FAULT,DISTANCE,CHECKSUM>
(10필드, 가스 2종 분리 + VL53L1X 거리 포함, 코드값 한글 라벨)
- sensor_bridge: 포트 5002->8765로 변경, parse_msg를 10필드 기준 재작성,
  /env/distance 토픽 신설 (측정실패 시 distance_mm=null)
- dashboard_node/index.html: env_gas를 mq135/mq2로 분리 수신,
  ENV BOARD 카드에 MQ-135/MQ-2/거리 필드 추가
디버깅 경위: 대시보드에 배터리 0.0V로 계속 표시되는 문제 확인
-> 필드 순서가 밀려 파싱되고 있었음(FLAME 필드를 배터리로 오인) 발견 후 수정."

echo ""
echo "================================================"
echo "완료! 총 $(git log main..\"\$BRANCH_NAME\" --oneline | wc -l)개 커밋이 '\$BRANCH_NAME' 브랜치에 생성됨"
echo "================================================"
git log main.."$BRANCH_NAME" --oneline

echo ""
echo "다음 단계:"
echo "  1. cd \$(dirname \"\$WORKDIR\")/.. 로 저장소 루트로 이동"
echo "  2. git push origin \$BRANCH_NAME"
echo "  3. GitHub에서 PR 생성 (base: main)"
echo "     -> PR 설명에 '재구성된 히스토리이며 정확한 작업일시와 다를 수 있음' 명시 추천"
echo "     -> 머지 시 'Create a merge commit' 선택 (Squash 아님! 커밋 12개가 그대로 보존됨)"
