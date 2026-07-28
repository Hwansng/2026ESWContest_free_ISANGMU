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
