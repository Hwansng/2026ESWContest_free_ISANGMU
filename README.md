# HazardBot 2026

> **STS3215 직렬 버스 서보 기반 6DOF 적응형 파지 미션 기반 자율 위험물 탐지·격리 로봇 시스템**

임베디드 SW 경진대회 (자유공모) 출품작. 듀얼 ESP32 + Raspberry Pi 5 (8GB) + ROS2 Jazzy 기반 2계층 아키텍처.

---

## 시스템 개요

자율주행차(AMR)가 지정 영역을 순찰하며 5종 환경 센서와 엣지 AI 비전으로 위험물을 탐지·분류한다. 위험 등급 판별 후 6축 로봇 암(SO-ARM101 프레임 + Feetech STS3215 서보)이 컴플라이언스 토크 제어로 적응형 파지·운반하여 색상별 격리함에 안전 배치한다.

### 미션 흐름
```
IDLE → PATROL → DETECTED → CLASSIFY → APPROACH → GRIP → TRANSPORT → ISOLATE → REPORT
```

### 핵심 차별화 포인트
- **듀얼 ESP32 2계층 아키텍처**: ESP32 #1(AMR·센서) + ESP32 #2(6DOF Arm UART) + RPi 5 (Vision/ROS2). 역할 분리로 Fault Isolation 확보
- **6DOF STS3215 직렬 버스 서보**: 12-bit 엔코더 0.088° 피드백, 30kg·cm, 데이지 체인 3선
- **컴플라이언스 토크 제어**: 실시간 Load 센싱 기반 적응형 파지
- **엣지 AI 비전**: OpenCV HSV + minAreaRect 방위각 분류 (60fps)
- **5종 센서 퓨전**: MQ-2/MQ-135 비율 분석 가스 유형 추정

---

## 폴더 구조

```
HazardBot-2026/
├── firmware/
│   ├── esp32_amr/        # ESP32 #1 펌웨어 (AMR·센서·라인트레이싱)
│   └── esp32_arm/        # ESP32 #2 펌웨어 (STS3215 6DOF 제어)
├── ros2_ws/
│   └── src/              # ROS2 Jazzy 패키지 (RPi 5)
│       ├── hazardbot_bringup/
│       ├── hazardbot_arm/
│       ├── hazardbot_vision/
│       ├── hazardbot_mission/
│       └── hazardbot_dashboard/
├── hardware/
│   ├── stl/              # SO-ARM101 프레임 + 섀시 어댑터 STL
│   └── schematics/       # 회로도, 핀맵
├── docs/                 # 아키텍처, 통신 프로토콜, FSM 설계 문서
└── README.md
```

---

## 하드웨어 구성

| 분류 | 부품 | 용도 |
|---|---|---|
| MCU #1 | ESP32 DevKit V1 | AMR·5종 센서·DC모터·라인트레이싱 |
| MCU #2 | ESP32 DevKit V1 | STS3215 6축 UART 제어·NeoPixel·부저 |
| SBC | Raspberry Pi 5 (8GB) | ROS2 Jazzy + OpenCV + 대시보드 |
| 모터 드라이버 | TB6612FNG | DC 모터 (MOSFET, 효율 95%+) |
| 서보 | Feetech STS3215 × 6 | 6DOF 직렬 버스 데이지 체인 |
| 거리 | VL53L1X (ToF) | 정면 장애물·APPROACH 트리거 |
| 가스 | MQ-2, MQ-135 | 가스 유형 비율 추정 |
| 온도 | MLX90614 | 비접촉 IR 온도 |
| 화염 | KY-026 | 화염 감지 (즉시 정지) |
| 라인 | 5채널 IR 라인센서 | 라인트레이싱 PID + 이탈 감지 |
| 프레임 | SO-ARM101 (3D 출력) | LeRobot 오픈소스 STL 자체 제작 |
| 카메라 | RPi Camera v2 | OpenCV HSV + minAreaRect (60fps) |
| 전원 | 3S LiPo 11.1V | 듀얼 XL4015 (RPi 5 전용 + ESP32 공용) |

---

## 빌드 및 실행

### ESP32 펌웨어
Arduino IDE 또는 PlatformIO로 빌드:

```bash
# Arduino IDE
# Tools → Board → ESP32 Dev Module
# Tools → Port → 해당 COM 포트
firmware/esp32_amr/esp32_amr.ino  열어서 Upload
```

### ROS2 워크스페이스 (Raspberry Pi 5)

```bash
cd ros2_ws
colcon build --symlink-install
source install/setup.bash
ros2 launch hazardbot_bringup mission.launch.py
```

> ROS2 패키지는 현재 스켈레톤 단계이며 4월 ~ 6월 사전 준비기에 구현 예정.

---

## 통신 프로토콜

모든 RPi 5 ↔ ESP32 명령은 **Wi-Fi TCP 듀얼 채널**, `<CMD,VALUE,...,CS>\n` 포맷, XOR 체크섬 필수.

### AMR 채널 예시
```
RPi → ESP32 #1:  <MOVE,150,150,CS>     # 좌/우 모터 PWM
RPi → ESP32 #1:  <STOP,CS>             # 비상 정지 (최우선)
ESP32 #1 → RPi:  <STATE,DANGER,5A>     # 상태 변화 이벤트
ESP32 #1 → RPi:  <GAS,450,280,HIGH,CS> # MQ-2/MQ-135 비율 판정
```

자세한 프로토콜은 `docs/protocol.md` 참조.

---

## 팀 구성

| 팀원 | 담당 영역 |
|---|---|
| A | 6DOF 로봇 암 + ESP32 #2 펌웨어 + Vision 노드 |
| B | AMR + 센서 퓨전 + ESP32 #1 펌웨어 + 전력 설계 |
| C | RPi 5 통합 레이어 (ROS2 노드 + FSM + 대시보드) |

**3인 독립 개발 전략**: 각자 자기 플랫폼에 단독 플래싱·테스트, 통합 테스트는 주말에 세 플랫폼 연결.

---

## 일정

| 구간 | 기간 | 비고 |
|---|---|---|
| 사전 준비기 | 2026-04-01 ~ 2026-06-말 | 학습 + 부품 확보 + 단위 개발 + 1차 통합 |
| 집중 개발기 | 2026-07-01 ~ 2026-08-15 | 차별화 기능 + 안정화 |
| 마무리기 | 2026-08-16 ~ 2026-09-초 | 문서화 + 발표 준비 |

---

## 라이선스

본 저장소는 **비공개(Private)** 이며 경진대회 출품 전까지 외부 공개를 금지한다. 라이선스는 발표 후 결정 예정.

Hugging Face LeRobot SO-ARM101 STL은 [원 저장소](https://github.com/huggingface/lerobot) 라이선스를 따른다.
