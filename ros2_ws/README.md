# ROS2 워크스페이스 (Raspberry Pi 5)

ROS2 Jazzy (Ubuntu 24.04 LTS) 기반 미션 통합 레이어.
라인 추종 AMR + 6축 암으로 순찰 구역 내 위험물(적색/황색)을 색상·형상으로 감지하고, TCP로 연결된 ENV 보드에서 가스 재검사를 받아 등급을 판정한 뒤 파지·격리하고, Flask/SocketIO 웹 대시보드로 실시간 상태를 관제하는 시스템. AMR 구동보드(port 5000), ARM 서보보드(port 5001), ENV 센서보드(port 8765) 세 개의 ESP32가 각각 Wi-Fi TCP로 Pi와 통신.

## 패키지 구성

| 패키지 | 역할 | 
|---|---|
| `amr_bridge` | AMR 구동 ESP32 TCP 브릿지 — 센서/가스/온도/배터리/근접 감지 수신, 구동·하트비트·복귀 명령 송신 |
| `arm_bridge` | ARM 서보 ESP32 TCP 브릿지 — 서보 피드백 수신, 명령/LED/부저/그립/비상정지 송신 |
| `arm_controller` | 암 "놓기(place)" 동작 전용 — 프리셋 포즈 테이블 기반, IK·파지는 담당하지 않음(의도적으로 범위 축소) |
| `arm_act_node` | ACT(모방학습) 정책으로 파지 수행  | 
| `sensor_bridge` | ENV 센서보드 TCP 브릿지 — 가스/화염/배터리/상태 수신, 가스 재검사(GAS_CHECK) 요청·응답 처리 | 
| `hazard_detector` | 위험물 등급 판정 FSM — 비전 색상 + 가스 재검사 + 화염 값을 종합해 위험 등급 판정 |
| `mission_orchestrator` | 최상위 미션 FSM (IDLE→PATROL→DETECTED→CLASSIFY→APPROACH→GRIP→TRANSPORT→ISOLATE/REPORT, EMERGENCY/RETURN 분기) | 
| `vision_node` | OpenCV HSV 임계값 + 컨투어 형상 분석(각도/종횡비/원형도)으로 색상·형상 판정 | 
| `hazardbot_dashboard` | Flask + SocketIO 관제 UI — 전 토픽 집계, MJPEG 영상 스트림, RPi5 헬스체크(온도/스로틀링) | 
| `hazardbot_dashboard/launch/` | 통합 launch 파일, 파라미터 | 

## 빌드

```bash
cd ros2_ws
colcon build --symlink-install
source install/setup.bash
```

## 실행

통합 launch 파일은 `hazardbot_bringup` 대신 `hazardbot_dashboard/launch/`에 있음.

```bash
# 전체 스택 (10개 노드: 카메라, amr_bridge, arm_bridge, sensor_bridge,
# hazard_detector, arm_controller, arm_act_node, mission_orchestrator,
# vision_node, dashboard_node)
ros2 launch hazardbot_dashboard hazardbot.launch.py

# 순찰 데모 전용 (암 관련 3개 노드 + mission_orchestrator 제외, 6개 노드만 실행)
# amr_bridge_node가 자체 하트비트를 보내므로 mission_orchestrator 없이도
# DRIVE 펌웨어가 타임아웃되지 않음
ros2 launch hazardbot_dashboard hazardbot_patrol_demo.launch.py
```

## 토픽 (요약)

| 토픽 | 타입 | 발행 노드 | 설명 |
|---|---|---|---|
| `/amr/cmd_vel` | geometry_msgs/Twist | (구독만, 발행처 미포함) | AMR 이동 명령 |
| `/amr/gas` | std_msgs/String | amr_bridge | AMR 측 가스 센서 값 |
| `/amr/temp` | std_msgs/String | amr_bridge | AMR 측 온도 값 |
| `/amr/battery` | std_msgs/Float32 | amr_bridge | AMR 배터리 전압 실측치 |
| `/amr/object_near` | std_msgs/Bool | amr_bridge | 근접 물체 감지 트리거 (vision_node가 구독) |
| `/amr/stop_index` | std_msgs/Int8 | amr_bridge | 정지 구역 인덱스 |
| `/amr/return_done` | std_msgs/Bool | amr_bridge | 복귀 완료 알림 |
| `/amr/start_request`, `/mission/heartbeat`, `/hazard/return_request` | Bool/String | mission_orchestrator 등 | amr_bridge가 구독, 시작/하트비트/복귀 명령 |
| `/arm/command` | std_msgs/String | arm_act_node, arm_controller | 6축 명령 (그립/놓기 통합 채널) |
| `/arm/grip_cmd`, `/arm/led_cmd`, `/arm/buzzer_cmd`, `/arm/emergency` | std_msgs/String | arm_act_node, mission_orchestrator | 그립/LED/부저/비상정지 명령 (arm_bridge가 구독) |
| `/arm/servo_feedback` | std_msgs/String | arm_bridge | STS3215 서보 위치/부하/온도 피드백 |
| `/arm/connected` | std_msgs/String | arm_bridge | ARM 보드 연결 상태 |
| `/arm/place_request` | std_msgs/String | mission_orchestrator | 놓기 요청 (arm_controller가 구독) |
| `/arm/grip_request`, `/arm/grip_retry` | std_msgs/String | mission_orchestrator | 그립 요청/재시도 (arm_act_node가 구독) |
| `/env/gas` | std_msgs/String | sensor_bridge | ENV 보드 가스 원시값 (mq135, mq2) |
| `/env/temp` | std_msgs/String | sensor_bridge | ENV 보드 온도/화염 감지 |
| `/env/battery` | std_msgs/Float32 | sensor_bridge | ENV 보드 배터리 전압 실측치 |
| `/env/state` | std_msgs/String | sensor_bridge | ENV 보드 상태/폴트 |
| `/env/gas_result` | std_msgs/String | sensor_bridge | 가스 재검사(GAS_CHECK) 결과 (hazard_detector가 구독) |
| `/vision/detected` | std_msgs/String | vision_node | 색상/형상 판정 결과 (JSON: color, angle, aspect_ratio 등) |
| `/hazard/detected` | std_msgs/String | hazard_detector | 위험물 등급 판정 결과 (JSON: level/type/detail) |
| `/hazard/gas_check_request` | std_msgs/String | hazard_detector | 가스 재검사 요청 (sensor_bridge가 구독) |
| `/mission/state` | std_msgs/String | mission_orchestrator | FSM 상태 (JSON) |
| `/mission/zone` | std_msgs/Int8 | mission_orchestrator | 현재 구역 |
| `/mission/start`, `/mission/reset` | std_msgs/String | (외부 트리거) | 미션 시작/리셋 |
| `/debug/force_grip` | std_msgs/String | (테스트 전용) | 강제 그립 트리거 |

> 전체 토픽 목록은 위 표 기준 요약이며, 각 노드 소스의 정확한 타입/필드는 코드 주석 참고.

## 문서

- `docs/lerobot_verification.md` — LeRobot(ACT 정책 도구) 격리 venv 배포 검증 기록. 
- `vision_node/DEPENDENCY_NOTES.md` — RPi5/Ubuntu 24.04/ROS2 Jazzy 환경에서 겪은 libcamera 이름 불일치, cv_bridge 패키지 누락, numpy 2.x ABI 충돌(`numpy<2` 고정으로 해결), OpenCV headless의 GUI 캘리브레이션 대체(Flask 웹 스트림) 이슈 기록.
- `firmware_reference/AMR_state_v8_wifi.ino` — 실제 펌웨어가 아닌 참조용 안내 파일. AMR ESP32(MQ135 가스 + KY-026 화염)가 `<SENS,gas,flame,battCv,stateCode,actionCode,faultCode,checksum>` 프레임을 Wi-Fi TCP(port 5000)로 `amr_bridge`에 전송한다는 프로토콜 스펙만 기록되어 있고, 실제 구현은 별도 저장소에 있음.
