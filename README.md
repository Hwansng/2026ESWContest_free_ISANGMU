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
      - MQ-2 가스 센서 3초 게이트 판정 (5ms × 600 표본) + 화염·거리·라인 센서 퓨전
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
 | ESP32 DevKit V1 — **DRIVE** | Arduino-ESP32 3.0 | FreeRTOS (듀얼 코어) | TB6612FNG, VL53L1X, 5ch IR |
 | ESP32 DevKit V1 — **ENV** | Arduino-ESP32 3.0 | FreeRTOS (듀얼 코어) | MQ-2, KY-026, NeoPixel, Buzzer |
 | 학습·제어 PC (Windows 11) | — | LeRobot 0.4.4 | Feetech STS3215 × 12 (USB 반이중 어댑터), ACT |

 다음과 같은 개발환경에서 본 프로젝트를 진행한다. 모든 RPi 5 ↔ ESP32 통신은 Wi-Fi TCP 듀얼 채널이며, `<CMD,VALUE,...,CS>\n` 포맷에 XOR 8-bit 체크섬을 사용한다.

 > **설계 변경 이력.** 초기 구상은 ESP32 한 대가 STS3215 를 UART2 로 직접 구동하는 것이었으나,
 > STS3215 는 **1선 반이중** 버스라 마스터가 하나여야 한다. ESP32 를 서보 3핀 버스에 물리면
 > 충돌이 난다. 현재는 **USB 반이중 어댑터 하나**를 마스터로 두고 PC 의 LeRobot 이 양팔을 제어한다.
 > 보드 호칭도 `#1`·`#2` 번호가 문서마다 반대를 가리켜 **DRIVE / ENV** 로 통일했다.
 > 근거와 절차는 [`docs/06_firmware/센서_지도.md`](docs/06_firmware/센서_지도.md) 와
 > [`docs/05_arm/로봇암_구축기록.md`](docs/05_arm/로봇암_구축기록.md) 참조.

 ---
 # ➕ Hardware

 | 분류 | 부품 | 용도 |
 | --- | --- | --- |
 | MCU — DRIVE | ESP32 DevKit V1 | DC 모터 · 라인트레이싱 · VL53L1X · **모터 정지 단독 권한** |
 | MCU — ENV | ESP32 DevKit V1 | 가스·화염 환경 감시 · NeoPixel · 부저 |
 | SBC | Raspberry Pi 5 (8GB) | ROS2 Jazzy + OpenCV + 대시보드 |
 | 모터 드라이버 | TB6612FNG | DC 모터 (MOSFET, 효율 95%+) |
 | DC 모터 | JGA25-371 12V | 2WD 차동 구동 (334rpm) |
 | 서보 | Feetech STS3215 × 12 | 리더·팔로워 양팔 6DOF. 1선 반이중 버스, 마스터는 USB 어댑터 하나 (12-bit, 30kg·cm) |
 | 거리 센서 | VL53L1X (ToF) | 정면 장애물 **로컬 정지 반사**(300mm · 3회 연속) · APPROACH 트리거 |
 | 가스 센서 | MQ-2 | 3초 게이트 판정 — MQ-135 는 미채택(`docs/06_firmware/센서_지도.md` §2) |
 | ~~온도 센서~~ | ~~MLX90614~~ | **미채택** — 근거는 `docs/06_firmware/센서_지도.md` |
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

2. DRIVE 보드 펌웨어 업로드:
   Arduino IDE → firmware/esp32_drive/esp32_line_pid/esp32_line_pid.ino 열기
   Tools → Board: "ESP32 Dev Module" → Port 선택 → Upload

3. ENV 보드 펌웨어 업로드:
   먼저 firmware/esp32_env/libraries/AMRDemoScenarioLogic/ 를 Arduino/libraries/ 에 복사
   그리고 wifi_secrets.example.h 를 wifi_secrets.h 로 복사해 SSID/비밀번호를 채운다
   Arduino IDE → firmware/esp32_env/AMR_state_v11_ino/AMR_state_v11_ino.ino 열기
   Tools → Board: "ESP32 Dev Module" → Port 선택 → Upload
   ※ 자세한 절차는 firmware/esp32_env/README.md

   ※ 로봇암은 ESP32 가 아니라 PC 에서 제어한다 (1선 반이중, 마스터 하나):
      conda activate lerobot
      powershell arm/scripts/teleop.ps1 -LeaderPort COMx -FollowerPort COMy

4. RPi 5에서 ROS2 워크스페이스 빌드 및 실행:
   cd ros2_ws
   colcon build --symlink-install
   source install/setup.bash
   ros2 launch hazardbot_dashboard hazardbot.launch.py

5. 관제 대시보드 접속:
   브라우저에서 http://<RPi5_IP>:8080 접속
```
 </details>

 ---
 # ➕ Source code

 ## 📝 DRIVE Firmware
 스케치: [`firmware/esp32_drive/`](firmware/esp32_drive/) · 배선·확정값 정본: [`docs/06_firmware/README.md`](docs/06_firmware/README.md)
 <br>

 `라인 추종 PD · 전압 피드포워드 · ToF 논블로킹 · 모터 정지 단독 권한`

  <details>
  <summary>알고리즘 설명 (요약)</summary>

```
① 라인 추종 PD 루프 — 5채널 TCRT5000(검정 = HIGH), KP=60 · KD=25 · 주기 20ms.

② 전압 피드포워드 — 실제듀티 = 목표듀티 × (12.0 / 측정전압).
   배터리 전압이 내려가도 같은 속도를 낸다. 엔코더 속도 루프를 대체한 방식이다.

③ VL53L1X 는 논블로킹으로 읽는다. 블로킹으로 읽으면 라인 PID 주기(20ms)가 무너진다.
   정지 판정 임계는 300mm 단일 고정이다 (구간별 전환 · 마커 기반 전환은 폐기).

④ 후진은 개루프 직선이다. 라인센서가 전방에 있어 이 하드웨어로 후진 라인 추종은
   제어적으로 불가능하다.

⑤ 정지 권한 — 모터를 멈추는 것은 DRIVE 뿐이다. RPi·ENV 는 정지를 요청할 뿐 직접 끊지 않는다.
   STBY 10kΩ 풀다운으로 ESP32 가 죽거나 리셋되면 G4 가 하이임피던스가 되어 모터가 자동 정지한다.

⑥ 하트비트 — 정지는 STOP 명령이 아니라 생존 신호로 건다.
   RPi 사망 · WiFi 두절 · ENV 사망을 하나의 메커니즘으로 잡기 위해서다.

⑦ Message Format: <CMD,VALUE,CS>  예) <BUZZ,1>  — XOR 8-bit 체크섬, 16진수 2자리
```
  </details>

 ## 📝 ARM 제어 (PC · LeRobot) — 컴플라이언스 파지
 도구: [`arm/tools/`](arm/tools/) · 실행기: [`arm/scripts/teleop.ps1`](arm/scripts/teleop.ps1)
 <br>

 `STS3215 양팔 12축 반이중 버스 제어 · 실시간 Load 센싱 · 적응형 파지`

  <details>
  <summary>알고리즘 설명 (요약)</summary>

```
① USB 반이중 어댑터 하나를 마스터로 두고 Feetech STS3215 를 제어한다.
   STS3215 는 1선 반이중이라 마스터가 둘일 수 없다 — ESP32 를 서보 3핀 버스에 연결하지 않는다.
   12-bit 마그네틱 엔코더로 0.088° 절대 위치 피드백을 받는다.

② 리더·팔로워 텔레옵 (LeRobot 0.4.4 · Windows 11):
   - 리더 6축은 XL4015 7.4V 강압 레일, 팔로워 6축은 12V 직결
   - 60Hz / 60초 무결 (관문 G2 Exit 충족)
   - 정렬 확인을 선행하고, 실패하면 텔레옵을 시작하지 않는다

③ Compliance Grip: 실시간으로 그리퍼 서보의 Load 값을 모니터링한다.
   - 소프트 한계 (Load 40%): 재시도. 그리퍼 위치 +5mm offset 후 재폐쇄.
   - 하드 한계 (Load 80%): 즉시 토크 OFF + RPi 5에 GRIP_FAIL_HARD 보고.
   - 최대 3회 재시도 후 실패 시 SKIP → PATROL.

④ Servo Feedback Cycle: 6축을 라운드 로빈으로 매 10ms마다 1축씩 위치/부하/온도를 읽어 RPi 5로 퍼블리시한다. 평균 60Hz 텔레메트리.

⑤ Fault Isolation — 4계층 정지 체계. 모터를 멈추는 것은 DRIVE 뿐이다.
   하드웨어 풀다운(STBY 10kΩ) / DRIVE 로컬 / RPi / 사람 순으로 겹쳐 둔다.
   정지는 STOP 명령이 아니라 하트비트(생존 신호)로 건다 —
   RPi 사망 · WiFi 두절 · ENV 사망을 하나의 메커니즘으로 잡기 위해서다.
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
├── arm/                  # 로봇암 · ACT (PC 측)
│   ├── tools/            # STS3215 제어·진단 도구 17종
│   ├── act/              # ACT 수집·검수 도구 + dataset_meta/ (100 에피소드 메타)
│   ├── calibration/      # 캘리브레이션 정본 4개 + 백업·복원 절차
│   ├── scripts/          # teleop.ps1 · record_act.ps1 · rollout_act.ps1
│   └── tests/            # ACT 수집 테스트 3종
├── docs/
│   ├── architecture.md   # 시스템 아키텍처 · 통신 · 판정 로직
│   ├── contributing.md   # 협업 가이드 (브랜치 전략 · PR 프로세스)
│   ├── 01_plan/          # 계획 변경·개선안 · 시나리오 산업기준 재정의
│   ├── 02_schedule/      # 합동 작업일정 · 13주 공정표 · 역할별 담당정리 · 인계
│   ├── 03_scenario_demo/ # 시나리오 확정 · 시연장 배치 · 영상 구성
│   ├── 04_act/           # ACT 수집 설계 · 구현 계획 · 수집 작업기록
│   ├── 05_arm/           # 로봇암 구축기록 · 카메라 구성 · GPU 오프로드 기록
│   ├── 06_firmware/      # 핀 배정·배선 정본 · 센서 지도 · 구역 마커 · 전력 계통
│   ├── 07_ros2/          # lerobot 검증
│   ├── 08_reference/     # 납땜 설명서 · 시스템 구조 정리 (PDF)
│   └── 10_env_design/    # ENV·전력·구동부 설계 근거 (강희)
├── firmware/
│   ├── esp32_drive/      # DRIVE 주행 스케치 6종 (bringup · line · PID · OTA · TCP · motor)
│   ├── esp32_env/        # ENV 환경감시 스케치 (v11 정본 · v9 참고) + 자체 라이브러리
│   ├── sts3215/          # 서보 버스 점검 · ID 부여
│   ├── tools/            # ENV 프로토콜 파서 · keepalive (RPi 측)
│   └── tests/            # ENV 상태머신 로직 테스트 57건 (하드웨어 없이 실행)
├── hardware/             # 출력에 쓴 STL 3종 (리더암 · 팔로워암 · Waffle 플레이트)
├── ros2_ws/              # ROS2 패키지 (RPi 5)
├── report/               # 개발완료보고서 빌드 시스템 (python-pptx)
├── tools/                # rpi_check.py · ros2_ws_sync.ps1
├── archive/              # 폐기된 설계 · ENV v1~v8 · 초기 계획
└── README.md
```

 ---
 # ➕ 협업 / 라이선스

 - 협업 가이드 (브랜치 전략 · 커밋 컨벤션 · PR 프로세스): [docs/contributing.md](docs/contributing.md)
 - 시스템 아키텍처 상세: [docs/architecture.md](docs/architecture.md)
 - 본 저장소는 제24회 임베디드SW경진대회 제출물이다. 대회 규정 제10조③ 에 따라 **공개(Public)** 로 유지한다.
 - Hugging Face LeRobot SO-ARM101 STL은 [원 저장소](https://github.com/huggingface/lerobot) 라이선스를 따른다.

