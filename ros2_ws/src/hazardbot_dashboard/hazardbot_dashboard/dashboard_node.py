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
    # ── ENV 보드 데이터 ──
    'env_gas': {'gas': 0},
    'env_temp': {'flame': 0},
    'env_battery': 0.0,
    'env_distance': {'distance_mm': None},
    'env_state': {'state': 'SAFE', 'action': 'NORMAL_MOTION', 'fault': 'OK'},
    # ── v11 GAS_CHECK 결과 (sensor_bridge_node의 /env/gas_result) ──
    'env_gas_result': {
        'zone': None, 'result': None,
        'baseline': None, 'minimum_raw': None, 'weak_percent': None,
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
        self.create_subscription(String, '/env/gas_result', self.env_gas_result_cb, 10)

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

    def env_gas_result_cb(self, msg: String):
        dashboard_data['env_gas_result'] = json.loads(msg.data)

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
