# ROS2 워크스페이스 (Raspberry Pi 5)

담당: 팀원 C

ROS2 Jazzy (Ubuntu 24.04 LTS) 기반 미션 통합 레이어.

## 패키지 구성 (예정)

| 패키지 | 역할 |
|---|---|
| `hazardbot_bringup` | 통합 launch 파일, 파라미터 |
| `hazardbot_arm` | arm_bridge + arm_controller (IK 매핑, MoveIt 검토 중) |
| `hazardbot_vision` | OpenCV HSV + minAreaRect (60fps), VL53L1X 트리거 |
| `hazardbot_mission` | FSM orchestrator, hazard_detector, amr_navigation |
| `hazardbot_dashboard` | Flask + WebSocket 관제 UI |

## 빌드

```bash
cd ros2_ws
colcon build --symlink-install
source install/setup.bash
```

## 토픽 (요약)

| 토픽 | 타입 | 설명 |
|---|---|---|
| `/amr/cmd_vel` | geometry_msgs/Twist | AMR 이동 명령 |
| `/amr/sensors` | std_msgs/String | 센서 데이터 (JSON) |
| `/hazard/detected` | std_msgs/String | 위험물 등급 판정 결과 |
| `/arm/command` | std_msgs/String | 6축 IK 명령 |
| `/arm/servo_feedback` | std_msgs/String | STS3215 위치/부하/온도 |
| `/mission/state` | std_msgs/String | FSM 상태 + 진행률 |

> 현재 스켈레톤 단계. 4월 ~ 6월 사전 준비기에 패키지 구현 예정.
