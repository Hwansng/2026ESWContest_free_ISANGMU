# 🤖 HazardBot — 자율 위험물 탐지·격리 로봇 시스템

# ➕ 참가정보
 - 2026년 임베디드 소프트웨어 경진대회 (자유공모 부문)
 - 팀명: HazardBot
 - 작품명: HazardBot — STS3215 직렬 버스 서보 기반 6DOF 적응형 파지 미션 기반 자율 위험물 탐지·격리 로봇 시스템
 - 팀원: 박승환, 윤강희, 이진우
 <br>

 - 주제: 듀얼 ESP32 + Raspberry Pi 5 (8GB) + ROS2 Jazzy 기반 2계층 아키텍처를 활용한 자율 위험물 탐지·격리 로봇 제작
 - 개요: 자율주행차(AMR)가 지정 영역을 자율 순찰하며, 라즈베리파이 카메라의 엣지 AI(OpenCV HSV + minAreaRect 방위각 분류)와 5종 환경 센서의 퓨전 알고리즘으로 위험물을 탐지·분류한다. 위험 등급 판별 후, UART 직렬 버스로 제어되는 6축(6DOF) Feetech STS3215 로봇 암(SO-ARM101 프레임 3D 프린팅 자체 제작)이 비대칭 물체의 방위각을 인식하고 실시간 부하(Load) 센싱 기반 컴플라이언스 토크 제어로 적응형 파지·운반 후 격리 구역의 색상별 격리함에 안전하게 배치하는 완전 자동화 미션 수행 시스템을 구현한다.
 - 개발 목표:
      - 듀얼 ESP32 기반 Fault Isolation 아키텍처 구축
      - Feetech STS3215 직렬 버스 6축 서보 데이지 체인 제어
      - 실시간 Load 센싱 기반 컴플라이언스 토크 제어 (적응형 파지)
      - OpenCV HSV + minAreaRect 방위각 분류 (60fps 엣지 비전)
      - MQ-2 / MQ-135 비율 분석 가스 유형 추정 + 5종 센서 퓨전
      - ROS2 Jazzy 노드 통합 + Flask 실시간 관제 대시보드

 - 미션 시나리오:
   ```
   IDLE → PATROL → DETECTED → CLASSIFY → APPROACH → GRIP → TRANSPORT → ISOLATE → REPORT
   ```

 - 개발영상: _시연 후 업로드 예정_

 ---
 # ➕ Needed (architecture)

 | `Device` | `OS` | `Middleware` | `Else` |
 | --- | --- | --- | --- |
 | Raspberry Pi 5 (8GB) | Ubuntu 24.04 LTS | ROS2 Jazzy | OpenCV 4.x, Flask + WebSocket, rosbag |
 | ESP32 DevKit V1 #1 (AMR) | Arduino-ESP32 3.0 | FreeRTOS (듀얼 코어) | TB6612FNG, VL53L1X, MQ-2/135, MLX90614, KY-026, 5ch IR |
 | ESP32 DevKit V1 #2 (ARM) | Arduino-ESP32 3.0 | FreeRTOS (듀얼 코어) | Feetech STS3215 × 6 (UART2 1Mbps), NeoPixel, Buzzer |

 다음과 같은 개발환경에서 본 프로젝트를 진행한다. 모든 RPi 5 ↔ ESP32 통신은 Wi-Fi TCP 듀얼 채널이며, `<CMD,VALUE,...,CS>\n` 포맷에 XOR 8-bit 체크섬을 사용한다.

 ---
 # ➕ Hardware

 | 분류 | 부품 | 용도 |
 | --- | --- | --- |
 | MCU #1 | ESP32 DevKit V1 | AMR · 5종 센서 · DC 모터 · 라인트레이싱 |
 | MCU #2 | ESP32 DevKit V1 | STS3215 6축 UART 제어 · NeoPixel · 부저 |
 | SBC | Raspberry Pi 5 (8GB) | ROS2 Jazzy + OpenCV + 대시보드 |
 | 모터 드라이버 | TB6612FNG | DC 모터 (MOSFET, 효율 95%+) |
 | DC 모터 | JGA25-371 12V | 2WD 차동 구동 (334rpm) |
 | 서보 | Feetech STS3215 × 6 | 6DOF 직렬 버스 데이지 체인 (12-bit, 30kg·cm) |
 | 거리 센서 | VL53L1X (ToF) | 정면 장애물 · APPROACH 트리거 |
 | 가스 센서 | MQ-2, MQ-135 | 비율 분석 가스 유형 추정 |
 | 온도 센서 | MLX90614 | 비접촉 IR 온도 |
 | 화염 센서 | KY-026 | 화염 감지 (즉시 정지) |
 | 라인 센서 | 5채널 IR 라인센서 | 라인트레이싱 PID + 이탈 감지 |
 | 프레임 | SO-ARM101 (3D 출력) | LeRobot 오픈소스 STL 자체 제작 |
 | 카메라 | RPi Camera v2 | OpenCV HSV + minAreaRect (60fps) |
 | 전원 | 3S LiPo 11.1V | 듀얼 XL4015 (RPi 5 전용 + ESP32 공용) |

 ---
 # ➕ System Process

 다양한 보드와 개발환경을 함께 사용하므로, 코드를 한 번에 실행하지 않고 보드별로 분리하여 실행한다. 그에 따라 실행 순서를 정리해두었다.

 <details>
 <summary>✏️ 실행 명령어 (요약)</summary>

```
1. Wi-Fi 라우터 부팅 + 양쪽 ESP32 시리얼 포트(COMx) 확인

2. ESP32 #1 (AMR) 펌웨어 업로드:
   Arduino IDE → firmware/esp32_amr/esp32_amr.ino 열기
   Tools → Board: "ESP32 Dev Module" → Port 선택 → Upload

3. ESP32 #2 (ARM) 펌웨어 업로드:
   Arduino IDE → firmware/esp32_arm/arm_firmware/arm_firmware.ino 열기
   Tools → Board: "ESP32 Dev Module" → Port 선택 → Upload

4. RPi 5에서 ROS2 워크스페이스 빌드 및 실행:
   cd ros2_ws
   colcon build --symlink-install
   source install/setup.bash
   ros2 launch hazardbot_bringup mission.launch.py

5. 관제 대시보드 접속:
   브라우저에서 http://<RPi5_IP>:8080 접속
```
 </details>

 ---
 # ➕ Source code

 ## 📝 AMR Firmware (ESP32 #1)
 펌웨어: [firmware/esp32_amr/esp32_amr.ino](firmware/esp32_amr/esp32_amr.ino)
 <br>

 `5종 센서 수집 · 위험 상태 판정 · 모터 PID · 라인트레이싱 · LiPo 모니터링`

  <details>
  <summary>알고리즘 설명 (요약)</summary>

```
① MQ-135 가스 센서와 KY-026 불꽃 센서를 이용해 SAFE / WARNING / DANGER 상태를 판정한다.

② Moving Average: MQ-135 값의 순간 노이즈를 줄이기 위해 최근 SAMPLE_COUNT개 평균을 사용한다.

③ Persistence Filter: 위험 조건이 DANGER_COUNT_THRESHOLD 이상 연속 감지될 때만 DANGER로 판정한다. 한 번 튄 값은 즉시 DANGER로 보지 않는다.

④ Event-based State Message: 상태가 바뀌는 순간에만 RPi 5로 메시지를 송신한다.

⑤ XOR Checksum: 메시지 본문(CMD,VALUE)을 문자 단위로 XOR하여 체크섬을 생성한다. 수신 측이 데이터 무결성을 확인할 수 있도록 16진수 2자리로 부착한다.

⑥ Message Format: <CMD,VALUE,CS>  예) <STATE,DANGER,5A>

⑦ FreeRTOS 듀얼 코어:
   - Core 0: Wi-Fi TCP (RPi 5 통신)
   - Core 1: 센서 읽기 + 모터 PID + 라인트레이싱
```
  </details>

 ## 📝 ARM Firmware (ESP32 #2) — 컴플라이언스 파지
 펌웨어: [firmware/esp32_arm/arm_firmware/arm_firmware.ino](firmware/esp32_arm/arm_firmware/arm_firmware.ino)
 <br>

 `STS3215 6축 데이지 체인 제어 · 실시간 Load 센싱 · 적응형 파지`

  <details>
  <summary>알고리즘 설명 (요약)</summary>

```
① UART2(GPIO 16/17, 1Mbps)로 Feetech STS3215 서보 6개를 데이지 체인 제어한다. 12-bit 마그네틱 엔코더로 0.088° 절대 위치 피드백을 받는다.

② FreeRTOS 듀얼 코어 분리:
   - Core 0: Wi-Fi TCP (RPi 5와 명령/피드백 송수신)
   - Core 1: STS3215 서보 태스크 (10ms 폴링, vTaskDelayUntil로 지터 최소화)

③ Compliance Grip: 실시간으로 그리퍼 서보의 Load 값을 모니터링한다.
   - 소프트 한계 (Load 40%): 재시도. 그리퍼 위치 +5mm offset 후 재폐쇄.
   - 하드 한계 (Load 80%): 즉시 토크 OFF + RPi 5에 GRIP_FAIL_HARD 보고.
   - 최대 3회 재시도 후 실패 시 SKIP → PATROL.

④ Servo Feedback Cycle: 6축을 라운드 로빈으로 매 10ms마다 1축씩 위치/부하/온도를 읽어 RPi 5로 퍼블리시한다. 평균 60Hz 텔레메트리.

⑤ Fault Isolation: ESP32 #1(AMR) 장애 시 RPi 5의 STOP 명령으로 즉시 토크 OFF하여 암이 낙하하지 않도록 한다.
```
  </details>

 ## 📝 Vision Pipeline (RPi 5)
 위치: [`ros2_ws/src/vision_node/`](ros2_ws/src/vision_node/)
 <br>

 `OpenCV HSV + minAreaRect 방위각 분류 (60fps)`

  <details>
  <summary>알고리즘 설명 (요약)</summary>

```
① RPi Camera v2를 60fps 모드로 열어 BGR 프레임을 수신한다.

② VL53L1X ToF 센서가 위험물 근접 거리를 감지하면 vision_node에 트리거를 보낸다.

③ HSV 색공간 변환 후 격리 색상별 마스크를 생성한다 (적/청/녹 3구역).

④ Morphology(open/close)로 노이즈를 제거하고 cv2.findContours로 외곽선을 추출한다.

⑤ minAreaRect로 회전 사각형을 피팅하여 (cx, cy, width, height, angle)을 얻는다. 이 angle이 비대칭 물체의 방위각이며 6축 IK의 손목 회전 명령으로 매핑된다.

⑥ 결과를 /vision/detected 토픽으로 퍼블리시: {color, angle, depth_mm, confidence}.

⑦ Cortex-A76 2.4GHz 쿼드코어 + 8GB LPDDR4X로 60fps 처리에 여유가 있어 고속 주행 중에도 방위각 정밀도가 유지된다.
```
  </details>

 ---
 # ➕ 폴더 구조

```
HazardBot-2026/
├── .github/workflows/    # CI (Arduino 컴파일 · ROS2 colcon build)
├── docs/
│   ├── architecture.md   # 시스템 아키텍처 다이어그램
│   └── contributing.md   # 협업 가이드 (브랜치 전략 · PR 프로세스)
├── firmware/
│   ├── esp32_amr/        # ESP32 #1 펌웨어 (AMR · 센서 · 라인트레이싱)
│   └── esp32_arm/
│       └── arm_firmware/ # ESP32 #2 펌웨어 (STS3215 6DOF 제어)
├── hardware/
│   └── stl/              # SO-ARM101 프레임 STL
├── ros2_ws/
│   └── src/
│       └── vision_node/  # ROS2 비전 패키지 (RPi 5)
└── README.md
```

 ---
 # ➕ 협업 / 라이선스

 - 협업 가이드 (브랜치 전략 · 커밋 컨벤션 · PR 프로세스): [docs/contributing.md](docs/contributing.md)
 - 시스템 아키텍처 상세: [docs/architecture.md](docs/architecture.md)
 - 본 저장소는 **비공개(Private)** 이며 경진대회 출품 전까지 외부 공개를 금지한다.
 - Hugging Face LeRobot SO-ARM101 STL은 [원 저장소](https://github.com/huggingface/lerobot) 라이선스를 따른다.

