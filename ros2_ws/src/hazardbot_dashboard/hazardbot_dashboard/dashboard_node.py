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
    'hazard':  {'level': 0, 'type': 'NORMAL'},
    'servo_feedback': {},
    'vision':  {'color': None, 'angle': None},
    'rpi_health': {'cpu_temp': 0.0, 'throttled': '0x0'},
    'amr_connected': False,
    'arm_connected': False,
    # ENV 보드 데이터, sensor_bridge가 발행하는 실제 토픽만 반영함
    'env_gas': {'mq135': 0, 'mq2': 0},
    'env_flame': {'flame': 0},
    'env_battery': 0.0,
    'env_distance': {'distance_mm': None},
    'env_state': {'state': 'SAFE', 'action': 'NORMAL_MOTION', 'fault': 'OK'},
    # 수정: zone_thresholds 하드코딩 완전 삭제함
    # 판정 기준값은 hazard_detector 한 곳에서만 관리하는 걸로 정리함
    # 대시보드는 판정 결과(hazard)만 표시하고 기준값 자체는 안 들고 있음
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
            String, '/hazard/detected',   self.hazard_cb,   10)
        self.create_subscription(
            String, '/arm/servo_feedback',self.servo_cb,    10)
        self.create_subscription(
            String, '/vision/detected',   self.vision_cb,   10)

        # 수정: 죽은 토픽이던 /amr/sensors, /amr/gas, /amr/temp, /amr/battery 구독 제거함
        # ENV 보드(sensor_bridge) 토픽만 구독함
        self.create_subscription(String, '/env/gas',      self.env_gas_cb,      10)
        self.create_subscription(String, '/env/flame',    self.env_flame_cb,    10)
        self.create_subscription(Float32, '/env/battery', self.env_battery_cb,  10)
        self.create_subscription(String, '/env/state',    self.env_state_cb,    10)
        self.create_subscription(String, '/env/distance', self.env_distance_cb, 10)

        # 수정: amr_bridge, arm_bridge 연결 상태를 받을 구독 추가함
        # amr_bridge/arm_bridge에 연결 상태 퍼블리셔가 아직 없으면 여기서 계속 False로 남으니
        # 그쪽 노드에도 /amr/connected, /arm/connected 퍼블리셔가 있는지 같이 확인 필요함
        self.create_subscription(String, '/amr/connected', self.amr_connected_cb, 10)
        self.create_subscription(String, '/arm/connected', self.arm_connected_cb, 10)

        # RPi5 헬스 타이머, 5초마다
        self.create_timer(5.0, self.check_rpi_health)

        # 대시보드 전송 타이머, 1초마다
        self.create_timer(1.0, self.broadcast_data)

        self.get_logger().info('Dashboard 노드 시작함')

    def mission_cb(self, msg: String):
        try:
            data = json.loads(msg.data)
        except (json.JSONDecodeError, TypeError) as e:
            self.get_logger().warn(f'mission_cb 파싱 실패: {e}')
            return
        dashboard_data['mission_state'] = data.get('state', 'IDLE')
        dashboard_data['zone'] = data.get('zone', 1)
        dashboard_data['zone_display'] = data.get('zone_display', '알수없음')

    def hazard_cb(self, msg: String):
        try:
            dashboard_data['hazard'] = json.loads(msg.data)
        except (json.JSONDecodeError, TypeError) as e:
            self.get_logger().warn(f'hazard_cb 파싱 실패: {e}')

    def servo_cb(self, msg: String):
        try:
            data = json.loads(msg.data)
        except (json.JSONDecodeError, TypeError) as e:
            self.get_logger().warn(f'servo_cb 파싱 실패: {e}')
            return
        servo_id = str(data.get('id'))
        dashboard_data['servo_feedback'][servo_id] = data

    def vision_cb(self, msg: String):
        try:
            dashboard_data['vision'] = json.loads(msg.data)
        except (json.JSONDecodeError, TypeError) as e:
            self.get_logger().warn(f'vision_cb 파싱 실패: {e}')

    def env_gas_cb(self, msg: String):
        try:
            dashboard_data['env_gas'] = json.loads(msg.data)
        except (json.JSONDecodeError, TypeError) as e:
            self.get_logger().warn(f'env_gas_cb 파싱 실패: {e}')

    def env_flame_cb(self, msg: String):
        # 수정: env_temp_cb에서 이름 변경함, 토픽 분리에 맞춤
        try:
            dashboard_data['env_flame'] = json.loads(msg.data)
        except (json.JSONDecodeError, TypeError) as e:
            self.get_logger().warn(f'env_flame_cb 파싱 실패: {e}')

    def env_battery_cb(self, msg: Float32):
        dashboard_data['env_battery'] = round(msg.data, 2)

    def env_state_cb(self, msg: String):
        try:
            dashboard_data['env_state'] = json.loads(msg.data)
        except (json.JSONDecodeError, TypeError) as e:
            self.get_logger().warn(f'env_state_cb 파싱 실패: {e}')

    def env_distance_cb(self, msg: String):
        try:
            dashboard_data['env_distance'] = json.loads(msg.data)
        except (json.JSONDecodeError, TypeError) as e:
            self.get_logger().warn(f'env_distance_cb 파싱 실패: {e}')

    def amr_connected_cb(self, msg: String):
        dashboard_data['amr_connected'] = (msg.data == 'true')

    def arm_connected_cb(self, msg: String):
        dashboard_data['arm_connected'] = (msg.data == 'true')

    def image_cb(self, msg):
        try:
            frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
            with self.frame_lock:
                self.latest_frame = frame
        except Exception as e:
            self.get_logger().warn(f'이미지 변환 실패: {e}')

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
                self.get_logger().warn(f'RPi5 고온: {cpu_temp}도')
            if throttled != '0x0':
                self.get_logger().warn(f'RPi5 스로틀링: {throttled}')

        except Exception as e:
            self.get_logger().debug(f'헬스 체크 오류: {e}')

    def broadcast_data(self):
        socketio.emit('update', dashboard_data)


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
    dashboard_node_ref = node

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