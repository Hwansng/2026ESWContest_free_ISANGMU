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
