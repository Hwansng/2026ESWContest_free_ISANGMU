// HazardBot DRIVE — TCP 클라이언트 + VL53L1X ToF 통합 (2026-08-28)
//
// esp32_line_pid.ino(2026-08-21, 2채널 조향 + 정지점 마커)를 기반으로
// 8/25 에 확정된 통신 규격과 8/14 배선 정본의 ToF·배터리 분압을 얹은 것이다.
// 조향·마커 로직은 손대지 않았다 — 검증이 끝난 부분이라 그대로 옮겼다.
//
// ── 새로 들어온 것 ────────────────────────────────────────
//   1. TCP 클라이언트 — RPi 5 의 amr_bridge(포트 5000)에 붙는다.
//      🔴 서버는 RPi 다. ESP32 가 접속하러 간다 (amr_bridge_node.py:tcp_server).
//   2. <SENS> 주기 송신 + <MOVE>/<STOP>/<HB> 수신, 체크섬 검증
//   3. VL53L1X ToF — 🔴 논블로킹 읽기. 300mm 장애물 정지(안전 계층 1)
//   4. 배터리 분압 40k/10k = x5.0 → G39. 전압 피드포워드 + 과방전 감시
//   5. RPI_TIMEOUT 페일세이프 — 하트비트가 끊기면 스스로 선다
//   6. 🟠 <DETECT>/<RETURN>/<RETDONE> (2026-08-28 추가, 진우 제안 프로토콜)
//      정지 마커 도달마다 <DETECT> 1회 송신(비전 캡처 트리거) · <RETURN> 수신 시
//      개루프 후진 · 후진 끝나면 <RETDONE> 1회 송신. 🔴 RPi 쪽(mission_orchestrator·
//      amr_bridge)엔 이 프로토콜을 실제로 쓰는 코드가 아직 없다 — DRIVE 쪽만 먼저
//      준비해둔 것이다. RETURN_DURATION_MS·RETURN_SPEED 는 실측 전 잠정값이다(§10 참고)
//
// ── 🔴 통전 전에 반드시 ───────────────────────────────────
//   🔴 VCC 와 GND 는 직납땜이다. 핀소켓에 물리지 않는다.
//   지난 보드는 GND 를 핀소켓으로 물려뒀는데 그 접점이 **모터 진동으로 빠져** 죽었다.
//   3V3 에 매달린 주변부 전류(60~90mA) 전량이 신호선을 타고 GPIO 보호 다이오드로
//   귀환하면서 발열 → 사망. USB 는 자기 GND 를 들고 오므로 이 상태에서도
//   업로드는 계속 성공한다. 그래서 안 보인다.
//
//   🔴 도통 확인은 하되, 그것만으로는 부족하다 — 진동형 고장은 정지 상태에서
//   통해 있어도 주행 중에 빠진다. **모터를 돌린 뒤 한 번 더** 짚는다.
//   GND 핀 2개 이상(DevKit V1 은 3개) · TB6612 GND 3패드 전부 · 라인센서 GND.
//
//   🔴 직납땜의 대가로 OTA 가 필수가 된다 — 보드를 기판에서 뽑을 수 없으니
//   「주변 회로 분리 후 USB 업로드」가 안 된다. 그래서 이 스케치의 ArduinoOTA
//   (`hazardbot-drive`)는 편의가 아니라 전제다. 12V 인가 중 USB 업로드 금지.
//   🔴 뜨거우면 즉시 분리 — 발열은 진단 신호가 아니라 파괴가 진행 중이라는 뜻이다.

#include <WiFi.h>
#include <ArduinoOTA.h>
#include <ESPmDNS.h>

// ══════════════════════════════════════════════════════════
// 0. 🔲 현장에서 채워야 하는 값 — 업로드 전에 확인할 것
// ══════════════════════════════════════════════════════════
// 🔵 2026-08-29 — 아이폰 핫스팟(Hwan) 대신 RPi 자체 AP로 전환.
//    "핫스팟이 유휴 시 광고를 멈춰 ESP32가 재접속 못 함" 문제(firmware/README.md
//    트러블슈팅표)가 RPi AP로 가면서 없어진다 — RPi는 상시 켜져 있으니까.
const char* WIFI_SSID = "여기에-AP-SSID";
const char* WIFI_PW   = "여기에-AP-비밀번호";  // 🔴 공개 저장소라 실제 값을 적지 않는다. 업로드 전에 여기만 채울 것.

// 🔴 RPi 5 의 주소. 고정 IP 를 쓰면 여기에 적고, DHCP 면 빈 문자열로 두고
//    아래 RPI_MDNS 로 찾게 한다 (RPi 에서 `hostname -I` 로 확인).
// 🔵 2026-08-29 — RPi AP 모드의 고정 IP를 안 받아서 일단 mDNS로 간다.
//    비어있으면 tryConnect() 가 MDNS.queryHost(RPI_MDNS) 로 찾는다.
//    🟠 AP 환경에서 mDNS/멀티캐스트가 막혀 있으면 이 방식이 실패할 수 있다 —
//    "RPi 주소를 못 찾았다" 로그가 반복되면 RPi 의 AP 모드 IP(보통 192.168.4.1)를
//    알아내서 여기 직접 적는 걸로 바꿀 것.
const char* RPI_HOST  = "";
const char* RPI_MDNS  = "hazardbot";      // RPI_HOST 가 비었을 때만 사용 (hazardbot.local)
const uint16_t RPI_PORT = 5000;           // amr_bridge_node.py: AMR_PORT = 5000

// ToF(VL53L1X) — 장애물 정지 계층. 컴파일하려면 라이브러리가 하나 더 필요하다:
//    Arduino IDE > 라이브러리 매니저 > "Adafruit VL53L1X" (의존성 Adafruit BusIO 는 같이 깔린다)
//
// 🔵 2026-08-30 — 라인추종 단독 벤치 테스트 중 ToF 가 계속 정지를 걸어서 0 으로 껐다.
// 🔵 2026-09-03 — 다시 1 로 되돌린다. 장애물 정지는 안전 구조의 일부라 빼놓을 수 없다.
//
//    0 이면 장애물 정지 계층이 통째로 사라진다. obstacleNear 를 세팅하는 곳이
//    pollToF() 뿐인데 그 함수 본문이 HAS_TOF=0 이면 비기 때문이다. 이때
//    motionBlocked() 는 tofOk 를 안 보므로 주행은 그대로 되고 fault 만 SENSOR 로
//    뜬다 — 즉 "정지가 없어진 줄 모르고 도는" 상태가 된다.
//
//    🔴 벤치에서 오정지가 재현되더라도 여기를 0 으로 되돌리지 말 것.
//    먼저 OBSTACLE_STOP_MM(현재 300) 을 낮추거나 OBSTACLE_STREAK(현재 3) 을 올린다.
//    센서가 없거나 begin() 이 실패하면 tofOk=false 로 남아 주행을 막지 않고
//    dist 가 -1, fault 가 SENSOR 로 나간다 — 안전한 쪽으로 실패한다.
#define HAS_TOF 1

#if HAS_TOF
  #include <Wire.h>
  #include <Adafruit_VL53L1X.h>
  Adafruit_VL53L1X tof;
#endif

// ══════════════════════════════════════════════════════════
// 1. 핀 — firmware/README.md §1 · 전력계통_실배선_2026-08-28.md 2부 §1.5
// ══════════════════════════════════════════════════════════
#define PIN_PWMA   25
#define PIN_AIN1   26
#define PIN_AIN2   27
#define PIN_PWMB   14
#define PIN_BIN1   16      // 보드에 RX2 로 인쇄된 경우가 많다
#define PIN_BIN2   17      // 〃 TX2
#define PIN_STBY    4
#define PIN_LINE_L 13      // 2채널 교체분 (기존 S1 자리)
#define PIN_LINE_R 32      // 〃        (기존 S5 자리)
#define PIN_TOF_SDA 21
#define PIN_TOF_SCL 22
#define PIN_BATT   39      // 실크스크린 SN / VN — EN 버튼 옆. 입력 전용

const bool LINE_ACTIVE_LOW = false;   // 검정에서 HIGH — 실측으로 재확인할 것

// ══════════════════════════════════════════════════════════
// 2. 확정값
// ══════════════════════════════════════════════════════════
const int PWM_FREQ = 20000, PWM_BITS = 8, PWM_MAX = 255;

// ── 조향 (esp32_line_pid.ino 에서 그대로) ──
// 🔵 2026-08-30 — 감속 마커 폐기(정지 마커만 사용)로 마커 도달 시 감속 없이 바로
//    풀스피드→급정지가 된다. 마커 오버런을 줄이려고 baseSpeed를 낮췄다(120→95).
int turnDelta     = 40;
int baseSpeed     = 95;
int approachSpeed = 70;   // 🔴 감속 마커 폐기로 지금은 미사용(phase가 PH_APPROACH로 안 감) — 죽은 값은 아니고 부활 대비로 남겨둠
const int CONTROL_MS = 20;

// ── RETURN(후진) — 🟠 전부 잠정값, 실측 전 ──
// 오도메트리가 없어 개루프(시간×속도)로만 갈 수 있다. 목표는 "후진 800mm"(8/25 이월
// 목록)였는데 이 상수들로 실제로 몇 mm 가는지는 벤치에서 자로 재기 전엔 아무도 모른다.
// 촬영 전 반드시: 시리얼 'r' 키로 후진시켜보고 거리 재서 RETURN_DURATION_MS 조정할 것.
int RETURN_SPEED           = 80;    // 🔵 baseSpeed와 같이 낮췄다(100→80). baseSpeed보다 낮게 — 후진은 조향 보정이 없다
unsigned long RETURN_DURATION_MS = 1500;

// ── 통신 — 8/25 §0-B.G 확정 ──
const unsigned long SENS_PERIOD_MS = 300;    // <SENS> 송신 주기 (하트비트 주기와 동일)
// 🔵 2026-08-30 — 1000ms→3000ms. 실측해보니 모터 기동 직후 0.6~1초 사이에 WiFi가
// 순간 끊겨 RPI_TIMEOUT이 걸리는 패턴이 재현됨(ENV 보드는 그 구간에도 안 끊김 —
// RPi/AP 문제가 아니라 DRIVE 자신의 모터 기동 전류로 인한 순간 전압강하로 추정).
// 근본 원인(전원 디커플링)은 별도 점검 필요 — 이건 그 사이 임시 완화값이다.
const unsigned long RPI_TIMEOUT_MS = 3000;
                                             // 🔴 RPi 가 실제로 0.5s 주기로 쏘면 여유가 없다.
                                             //    복구일에 실측해서 확정한다 (8/25 §1 ③)
const unsigned long RECONNECT_MS   = 2000;   // TCP 재접속 간격

// ── ToF — 배선_확정 §3 · 구역_마커_설계 §6.1 ──
const uint16_t OBSTACLE_STOP_MM = 300;   // 🔵 300mm 단일 상수 (8/18 개정, 구간별 전환 폐기)
const uint16_t OBSTACLE_CLEAR_MM = 380;  // 히스테리시스 — 경계에서 덜덜거리지 않게
const uint8_t  OBSTACLE_STREAK   = 3;    // 연속 3회여야 인정 (단발 오검출 차단)

// ── 배터리 — 배선_확정 §2 ② ──
const float BATT_DIVIDER   = 5.0f;    // 40k/10k. 계수가 정확히 5.0 이라 코드가 깔끔하다
float       battCalib      = 1.0f;    // 🔲 멀티미터 실측 보정. 0.8~1.5 로 클램프
const float BATT_CUTOFF_V  = 9.9f;    // 3S 과방전 하한
const float BATT_WARN_V    = 10.5f;
const float BATT_NOMINAL_V = 12.0f;   // 전압 피드포워드 기준

// ── 마커 (esp32_line_pid.ino 에서 그대로) ──
const unsigned long MARKER_GUARD_MS = 1000;
const int SHORT_BRAKE_MS = 150;

// ══════════════════════════════════════════════════════════
// 3. 프로토콜 코드 — amr_bridge_node.py 의 이름 배열과 순서가 같아야 한다
// ══════════════════════════════════════════════════════════
enum StateCode  { ST_SAFE = 0, ST_WARNING, ST_DANGER, ST_STOP, ST_SENSOR_ERROR };
enum ActionCode { AC_NORMAL = 0, AC_LIMITED, AC_STOP };
enum FaultCode  { FT_OK = 0, FT_ESTOP, FT_LIPO, FT_SENSOR, FT_RPI_TIMEOUT, FT_HAZARD };

// ══════════════════════════════════════════════════════════
// 4. 상태
// ══════════════════════════════════════════════════════════
enum Phase { PH_CRUISE, PH_APPROACH };
enum DriveMode { DM_LINE, DM_REMOTE };   // 라인추종 자율 / RPi 의 <MOVE> 원격

Phase     phase      = PH_CRUISE;
DriveMode driveMode  = DM_LINE;

int   stopIndex   = 0;          // 🔵 0~3 순환 (8/25 §0-B.G ④). 이전 스케치는 1~4 였다
int   blackStreak = 0;
bool  markerLatch = false;
unsigned long lastMarkerMs = 0;

// 🔵 2026-08-30 — 소프트스타트. 정지 상태에서 목표 듀티로 바로 점프하면 모터 기동
// 인러시로 순간 전압강하가 생겨 WiFi가 끊기는 패턴이 실측으로 재현됨. 출발(pidRunning
// 이 true 되는 시점)마다 0→목표 듀티를 DRIVE_RAMP_MS에 걸쳐 올린다. RETURN/MOVE 는
// 아직 대상이 아니다 — 우선 재현됐던 라인추종 출발 구간만 다룬다.
const unsigned long DRIVE_RAMP_MS = 400;
unsigned long driveRampStartMs = 0;

bool  motorsEnabled = false;
bool  pidRunning    = false;
bool  useRealSensor = true;
bool  simL = false, simR = false;

// RETURN(후진) 진행 상태 — 🔵 controlStep() 맨 위에서 다른 구동 모드보다 먼저 본다
bool  returning      = false;
unsigned long returnStartMs = 0;

int   dutyL = 0, dutyR = 0;
int   remoteL = 0, remoteR = 0;   // <MOVE> 로 받은 목표 듀티

// 페일세이프 플래그
bool  estopLatched   = false;
bool  rpiTimeout     = false;
bool  obstacleNear   = false;
bool  battCritical   = false;
bool  tofOk          = false;
bool  everConnected  = false;   // 한 번이라도 amr_bridge 에 붙은 적이 있는가
uint8_t obstacleStreak = 0;

int32_t distanceMm = -1;    // -1 = 미측정
float   battVolts  = 0.0f;

WiFiClient rpi;
unsigned long lastHbMs = 0, lastSensMs = 0, lastCtrlMs = 0;
unsigned long lastTryConnMs = 0, lastTelemMs = 0;
char rxBuf[128];
uint8_t rxLen = 0;

// ══════════════════════════════════════════════════════════
// 5. 모터
// ══════════════════════════════════════════════════════════
void setMotor(int in1, int in2, int pwmPin, int duty) {
  if (duty >= 0) { digitalWrite(in1, HIGH); digitalWrite(in2, LOW); }
  else           { digitalWrite(in1, LOW);  digitalWrite(in2, HIGH); duty = -duty; }
  ledcWrite(pwmPin, min(duty, PWM_MAX));
}

void applyDrive(int l, int r) {
  dutyL = l; dutyR = r;
  setMotor(PIN_AIN1, PIN_AIN2, PIN_PWMA, l);
  setMotor(PIN_BIN1, PIN_BIN2, PIN_PWMB, r);
}

void stopMotors() {
  applyDrive(0, 0);
  pidRunning = false;
  phase = PH_CRUISE;
  blackStreak = 0; markerLatch = false;
  remoteL = remoteR = 0;
}

void doStop() {   // 숏브레이크 — 양쪽 HIGH 로 단락 제동
  digitalWrite(PIN_AIN1, HIGH); digitalWrite(PIN_AIN2, HIGH);
  digitalWrite(PIN_BIN1, HIGH); digitalWrite(PIN_BIN2, HIGH);
  ledcWrite(PIN_PWMA, PWM_MAX);
  ledcWrite(PIN_PWMB, PWM_MAX);
  delay(SHORT_BRAKE_MS);
  applyDrive(0, 0);
}

void setEnabled(bool on) {
  motorsEnabled = on;
  digitalWrite(PIN_STBY, on ? HIGH : LOW);
  if (!on) stopMotors();
}

// 🔴 하나라도 서면 바퀴가 돌면 안 되는 조건들
bool motionBlocked() {
  return estopLatched || rpiTimeout || obstacleNear || battCritical || !motorsEnabled;
}

// ══════════════════════════════════════════════════════════
// 6. 라인센서 · 마커 (esp32_line_pid.ino 에서 그대로)
// ══════════════════════════════════════════════════════════
bool readL() {
  if (!useRealSensor) return simL;
  int v = digitalRead(PIN_LINE_L);
  return LINE_ACTIVE_LOW ? (v == LOW) : (v == HIGH);
}
bool readR() {
  if (!useRealSensor) return simR;
  int v = digitalRead(PIN_LINE_R);
  return LINE_ACTIVE_LOW ? (v == LOW) : (v == HIGH);
}

void onMarker() {
  // 🔵 2026-08-30 — 감속 마커 폐기. 마커 하나(정지 마커)만 쓴다 — 두 마커를 기다리던
  // 2단계 로직(1번째: PH_APPROACH 진입 / 2번째: 정지)을 걷어내고 첫 마커에서 바로 선다.
  doStop();
  stopIndex = (stopIndex + 1) % 4;      // 🔵 0~3 순환
  pidRunning = false;
  phase = PH_CRUISE;
  blackStreak = 0; markerLatch = false;
  Serial.printf(">>> 정지 마커 — stopIndex=%d 도달. 정지 완료.\n", stopIndex);

  // 🟠 8/28 추가 — 정지점마다 무조건 1회 보낸다. 구역별로 가려 보내지 않는다
  // (stopIndex↔ZONE 매핑이 RPi 쪽에도 아직 없다). 물체 없는 정지점이면 vision_node 가
  // "감지된 물체 없음"으로 넘어갈 뿐이라 무해하다.
  sendFrame("DETECT");
  Serial.println(F(">>> DETECT 송신"));
}

void checkMarker() {
  if (!useRealSensor) return;
  bool allBlack = readL() && readR();
  if (allBlack) blackStreak++;
  else { blackStreak = 0; markerLatch = false; }

  if (blackStreak >= 2 && !markerLatch && (millis() - lastMarkerMs) > MARKER_GUARD_MS) {
    markerLatch = true;
    lastMarkerMs = millis();
    onMarker();
  }
}

// ══════════════════════════════════════════════════════════
// 7. 배터리 — 전압 피드포워드 + 과방전 감시
// ══════════════════════════════════════════════════════════
void readBattery() {
  // analogReadMilliVolts 는 eFuse 캘리브레이션을 쓴다 — 생 analogRead 보다 정확하다
  uint32_t mv = analogReadMilliVolts(PIN_BATT);
  battVolts = (mv / 1000.0f) * BATT_DIVIDER * battCalib;
  battCritical = (battVolts > 1.0f) && (battVolts < BATT_CUTOFF_V);
  // 1.0V 미만이면 분압이 아직 안 붙은 것으로 보고 판정하지 않는다 (벤치에서 오탐 방지)
}

// 배터리가 빠지면 같은 듀티로도 느려진다 — 12.0V 기준으로 되돌린다
int feedForward(int duty) {
  if (battVolts < 6.0f) return duty;      // 분압 미배선 상태면 보정하지 않는다
  float k = BATT_NOMINAL_V / battVolts;
  if (k < 0.8f) k = 0.8f;
  if (k > 1.5f) k = 1.5f;
  return constrain((int)(duty * k), -PWM_MAX, PWM_MAX);
}

// ══════════════════════════════════════════════════════════
// 8. ToF — 🔴 논블로킹. dataReady() 가 false 면 그냥 지나간다
// ══════════════════════════════════════════════════════════
void setupToF() {
#if HAS_TOF
  Wire.begin(PIN_TOF_SDA, PIN_TOF_SCL, 100000);   // 100kHz (배선_확정 §3)
  if (!tof.begin(0x29, &Wire)) {
    Serial.println(F("🔴 VL53L1X 초기화 실패 — 배선(G21/G22)·3V3 확인. ToF 없이 계속한다"));
    tofOk = false;
    return;
  }
  tof.startRanging();
  tof.setTimingBudget(50);
  tofOk = true;
  Serial.println(F("VL53L1X OK (논블로킹 모드)"));
#else
  Serial.println(F("ToF 비활성 (HAS_TOF=0)"));
  tofOk = false;
#endif
}

void pollToF() {
#if HAS_TOF
  if (!tofOk) return;
  if (!tof.dataReady()) return;        // 🔴 절대 기다리지 않는다
  int16_t d = tof.distance();
  tof.clearInterrupt();
  if (d < 0) return;                   // 측정 실패 프레임은 버린다
  distanceMm = d;

  if (!obstacleNear) {
    if (distanceMm <= OBSTACLE_STOP_MM) {
      if (++obstacleStreak >= OBSTACLE_STREAK) {
        obstacleNear = true;
        Serial.printf("🔴 장애물 %ldmm — 계층1 정지\n", (long)distanceMm);
        doStop();
        pidRunning = false;
      }
    } else obstacleStreak = 0;
  } else {
    if (distanceMm >= OBSTACLE_CLEAR_MM) {   // 히스테리시스로 해제
      obstacleNear = false;
      obstacleStreak = 0;
      Serial.printf("🔵 장애물 해제 %ldmm\n", (long)distanceMm);
    }
  }
#endif
}

// ══════════════════════════════════════════════════════════
// 9. 프로토콜 — amr_bridge_node.py 와 바이트 단위로 같아야 한다
//
//   프레이밍 : <payload,CS>\n
//   체크섬   : payload(쉼표 포함, CS 제외) 각 문자의 ASCII 합 % 256
//              → Python: sum(ord(c) for c in ','.join(parts[:-1])) % 256
//
//   올림 : <SENS,gas,flame,battCv,state,action,fault,dist,stopIdx,CS>
//   내림 : <MOVE,left,right,CS> · <STOP,CS> · <HB,CS>
//
//   🟠 2026-08-28 추가(진우 제안, RPi 쪽 구현 아직 없음) —
//   올림 : <DETECT,CS>   정지 마커 도달마다 1회 — RPi 는 이걸 비전 캡처 트리거로 쓴다
//   올림 : <RETDONE,CS>  RETURN 후진이 끝났을 때 1회
//   내림 : <RETURN,CS>   수신하면 즉시 개루프 후진 시작(§10 controlStep 참고)
// ══════════════════════════════════════════════════════════
uint8_t calcChecksum(const char* payload) {
  uint32_t s = 0;
  for (const char* p = payload; *p; ++p) s += (uint8_t)(*p);
  return (uint8_t)(s % 256);
}

void sendFrame(const char* payload) {
  if (!rpi.connected()) return;
  char out[160];
  snprintf(out, sizeof(out), "<%s,%u>\n", payload, (unsigned)calcChecksum(payload));
  rpi.print(out);
}

uint8_t currentState() {
  if (estopLatched || rpiTimeout)   return ST_STOP;
  if (obstacleNear || battCritical) return ST_DANGER;
  if (!tofOk)                       return ST_SENSOR_ERROR;
  if (phase == PH_APPROACH || battVolts < BATT_WARN_V) return ST_WARNING;
  return ST_SAFE;
}

uint8_t currentAction() {
  if (motionBlocked())         return AC_STOP;
  if (phase == PH_APPROACH)    return AC_LIMITED;
  return AC_NORMAL;
}

uint8_t currentFault() {
  if (estopLatched)  return FT_ESTOP;
  if (rpiTimeout)    return FT_RPI_TIMEOUT;
  if (battCritical)  return FT_LIPO;
  if (obstacleNear)  return FT_HAZARD;
  if (!tofOk)        return FT_SENSOR;
  return FT_OK;
}

void sendSens() {
  // 🔴 gas·flame 은 항상 0 이다 — 이 보드에는 가스·화염 센서가 없다.
  //    7/20 재분할로 MQ-135 · KY-026 은 전부 ENV(강희) 로 갔다.
  //    자리를 비우지 않고 0 으로 채우는 이유: amr_bridge 가 필드 위치로 파싱하므로
  //    빼는 순간 뒤 필드가 전부 한 칸씩 밀린다. 진우의 파서 정리와 같은 커밋으로만 뺀다.
  //
  //    🔴 그래서 지금 /amr/gas 는 항상 0 이다. hazard_detector 구독을 /env/* 로
  //    옮기기 전까지 가스 판정이 조용히 죽어 있다는 뜻이다 (8/25 §5.1-C).
  //
  // 🔵 dist·stopIdx 는 faultCode 뒤에 "덧붙였다" — 기존 파서와 호환된다.
  //    amr_bridge 는 len(parts) >= 8 과 parts[1..6] 만 보고, 체크섬은 parts[:-1]
  //    전체로 계산하므로 필드가 늘어도 깨지지 않는다.
  int battCv = (int)(battVolts * 100.0f + 0.5f);
  char payload[128];
  snprintf(payload, sizeof(payload), "SENS,0,0,%d,%u,%u,%u,%ld,%d",
           battCv, (unsigned)currentState(), (unsigned)currentAction(), (unsigned)currentFault(),
           (long)distanceMm, stopIndex);
  sendFrame(payload);
}

// 수신 한 줄 처리
void handleLine(char* line) {
  int n = strlen(line);
  if (n < 3 || line[0] != '<' || line[n - 1] != '>') return;

  line[n - 1] = '\0';           // '>' 제거
  char* inner = line + 1;       // '<' 건너뜀

  char* lastComma = strrchr(inner, ',');
  if (!lastComma) return;

  int rxCs = atoi(lastComma + 1);
  *lastComma = '\0';            // inner 는 이제 CS 를 뺀 payload
  if (calcChecksum(inner) != (uint8_t)rxCs) {
    Serial.printf("체크섬 불일치: %s (기대 %u, 수신 %d)\n",
                  inner, (unsigned)calcChecksum(inner), rxCs);
    return;
  }

  lastHbMs = millis();          // 🔴 유효 프레임은 전부 하트비트로 친다
  if (rpiTimeout) {
    rpiTimeout = false;
    Serial.println(F("🔵 RPi 하트비트 복구"));
  }

  char* cmd = strtok(inner, ",");
  if (!cmd) return;

  if (strcmp(cmd, "HB") == 0) {
    return;                                     // 위에서 이미 갱신했다

  } else if (strcmp(cmd, "STOP") == 0) {
    estopLatched = true;
    doStop();
    pidRunning = false;
    Serial.println(F("🔴 <STOP> 수신 — 비상 정지 래치"));

  } else if (strcmp(cmd, "MOVE") == 0) {
    char* sL = strtok(NULL, ",");
    char* sR = strtok(NULL, ",");
    if (!sL || !sR) return;
    remoteL = constrain(atoi(sL), -PWM_MAX, PWM_MAX);
    remoteR = constrain(atoi(sR), -PWM_MAX, PWM_MAX);
    driveMode = DM_REMOTE;
    pidRunning = false;                         // 원격 중엔 라인추종을 끈다

  } else if (strcmp(cmd, "GO") == 0) {
    // 🔵 2026-08-30 — RPi 원격 시작 지원. 시리얼 'g' 와 동일하게 동작한다
    // (amr_bridge_node.py 의 send_go() 가 이제 실제로 보낸다).
    setEnabled(true);
    estopLatched = false;
    driveMode = DM_LINE;
    pidRunning = true; phase = PH_CRUISE;
    blackStreak = 0; markerLatch = false;
    driveRampStartMs = millis();
    Serial.println(F("🔵 <GO> 수신 — 라인추종 시작 (CRUISE) · ESTOP 해제"));

  } else if (strcmp(cmd, "RETURN") == 0) {
    // 🟠 8/28 추가. ESTOP 은 건드리지 않는다 — 이미 래치돼 있으면 motionBlocked() 가
    //    controlStep() 에서 그대로 막는다. 이미 후진 중이면 타이머를 다시 시작하지 않는다.
    if (!returning) {
      returning = true;
      returnStartMs = millis();
      pidRunning = false;
      driveMode = DM_LINE;
      Serial.println(F("🔴 <RETURN> 수신 — 후진 시작"));
    }
  }
}

void pollRpi() {
  while (rpi.available()) {
    char c = rpi.read();
    if (c == '\n' || c == '\r') {
      if (rxLen > 0) { rxBuf[rxLen] = '\0'; handleLine(rxBuf); rxLen = 0; }
    } else if (rxLen < sizeof(rxBuf) - 1) {
      rxBuf[rxLen++] = c;
    } else {
      rxLen = 0;              // 넘치면 버린다
    }
  }
}

void tryConnect() {
  if (rpi.connected()) return;
  if (millis() - lastTryConnMs < RECONNECT_MS) return;
  if (WiFi.status() != WL_CONNECTED) return;

  // 🔴 바퀴가 도는 동안에는 접속을 시도하지 않는다.
  //    connect() 도 mDNS queryHost() 도 수백 ms 를 막는데, 20ms 조향 루프가
  //    그만큼 서면 라인에서 이탈한다. 연결이 끊기면 어차피 RPI_TIMEOUT 이
  //    먼저 로봇을 세우므로, 선 다음에 붙으면 된다.
  if (dutyL != 0 || dutyR != 0) return;

  lastTryConnMs = millis();

  IPAddress ip;
  bool have = false;
  if (RPI_HOST && RPI_HOST[0] && ip.fromString(RPI_HOST)) {
    have = true;
  } else {
    ip = MDNS.queryHost(RPI_MDNS);              // hazardbot.local · 🟠 최대 1초 블로킹
    have = (ip != IPAddress((uint32_t)0));
  }
  if (!have) { Serial.println(F("RPi 주소를 못 찾았다 — RPI_HOST 확인")); return; }

  Serial.printf("amr_bridge 접속 시도 %s:%u ... ", ip.toString().c_str(), RPI_PORT);
  if (rpi.connect(ip, RPI_PORT, 500)) {         // 🔵 타임아웃 500ms — 기본값은 훨씬 길다
    rpi.setNoDelay(true);
    rxLen = 0;
    lastHbMs = millis();                        // 접속 직후 타임아웃 오탐 방지
    rpiTimeout = false;
    everConnected = true;
    Serial.println(F("연결됨"));
  } else {
    Serial.println(F("실패"));
  }
}

void checkRpiTimeout() {
  bool stale = (millis() - lastHbMs) > RPI_TIMEOUT_MS;
  if (rpi.connected() && stale && !rpiTimeout) {
    rpiTimeout = true;
    doStop();
    pidRunning = false;
    Serial.println(F("🔴 RPI_TIMEOUT — 하트비트 끊김. 정지"));
  }
  // 🔴 한 번 붙었다가 끊긴 것은 즉시 정지 사유다.
  //    반대로 "한 번도 안 붙은" 상태는 벤치 단독 주행이므로 막지 않는다 —
  //    RPi 없이 조향·마커를 튜닝하는 것이 이 스케치의 다른 절반이다.
  if (!rpi.connected() && everConnected && !rpiTimeout) {
    rpiTimeout = true;
    doStop();
    pidRunning = false;
    Serial.println(F("🔴 TCP 끊김 — 정지 (한 번 붙었던 연결이다)"));
  }
}

// ══════════════════════════════════════════════════════════
// 10. 제어 루프
// ══════════════════════════════════════════════════════════

// RETURN 종료 — 정상 완료(completed=true)면 RETDONE 을 보낸다.
// motionBlocked() 로 인한 중단(completed=false)이면 안 보낸다 — STOP/EMERGENCY 가
// 이미 그 경로를 따로 처리하고 있고, "후진을 완료 못 했다"고 RPi 가 알 필요는 없다
// (RPi 는 하트비트/STOP 으로 이미 알고 있다).
void endReturn(bool completed) {
  returning = false;
  applyDrive(0, 0);
  pidRunning = false;
  phase = PH_CRUISE;
  if (completed) {
    Serial.println(F(">>> RETURN 완료 — RETDONE 송신"));
    sendFrame("RETDONE");
  } else {
    Serial.println(F("🔴 RETURN 중단(정지 사유 발생) — RETDONE 미송신"));
  }
}

void controlStep() {
  // 🔴 RETURN 도 다른 정지 사유(ESTOP·RPI_TIMEOUT·배터리 등) 앞에서는 그대로 선다.
  //    장애물(obstacleNear)도 포함된다 — 후진 중 전방 ToF 는 무관하지만, 판단 로직을
  //    분기하지 않고 보수적으로 기존 motionBlocked() 를 그대로 쓴다.
  if (motionBlocked()) {
    applyDrive(0, 0);
    if (returning) endReturn(false);
    return;
  }

  if (returning) {
    if (millis() - returnStartMs >= RETURN_DURATION_MS) {
      endReturn(true);
    } else {
      int rv = feedForward(RETURN_SPEED);
      applyDrive(-rv, -rv);   // 직진 후진 — 조향 보정 없음(개루프)
    }
    return;
  }

  if (driveMode == DM_REMOTE) {
    applyDrive(feedForward(remoteL), feedForward(remoteR));
    return;
  }

  if (!pidRunning) { applyDrive(0, 0); return; }

  bool l = readL(), r = readR();
  int bs = (phase == PH_APPROACH) ? approachSpeed : baseSpeed;

  int corr = 0;
  if (l && !r)      corr = -turnDelta;   // 왼쪽만 감지 → 라인이 왼쪽 → 좌회전
  else if (!l && r) corr = +turnDelta;
  // (0,0) 중앙(또는 완전 이탈 — 구분 불가) / (1,1) 마커 통과 중 — 둘 다 직진

  int targetL = feedForward(constrain(bs + corr, -PWM_MAX, PWM_MAX));
  int targetR = feedForward(constrain(bs - corr, -PWM_MAX, PWM_MAX));

  // 🔵 소프트스타트 램프 — 출발 후 DRIVE_RAMP_MS 동안 0→목표 듀티로 선형 증가
  unsigned long rampElapsed = millis() - driveRampStartMs;
  if (rampElapsed < DRIVE_RAMP_MS) {
    float rampFactor = (float)rampElapsed / (float)DRIVE_RAMP_MS;
    targetL = (int)(targetL * rampFactor);
    targetR = (int)(targetR * rampFactor);
  }

  applyDrive(targetL, targetR);
}

// ══════════════════════════════════════════════════════════
// 11. 시리얼 메뉴 — 벤치 작업용. 라인 스케치의 것을 유지했다
// ══════════════════════════════════════════════════════════
void printHelp() {
  Serial.println(F(
    "\n── DRIVE (TCP + ToF) ───────────────────────────\n"
    "  e : STBY 토글        g : 라인추종 시작/재출발 (ESTOP 도 해제)\n"
    "  s : 정지(수동)       v : 가상/실측 센서 전환\n"
    "  [ ] 0 b : 가상 좌우 입력 (좌만/우만/중앙/마커)\n"
    "  m : 마커 강제 트리거   x : stopIndex 리셋 → 0\n"
    "  r : RETURN(후진) 강제 트리거 — RPi 없이 거리 실측용, R : RETURN_DURATION_MS +200\n"
    "  t/T : turnDelta -/+10   +/- : CRUISE 속도   a/A : APPROACH 속도\n"
    "  c : 배터리 보정계수 조정 안내   i : 통신·센서 상태 한 줄\n"
    "  ? : 이 목록\n"
    "────────────────────────────────────────────────"));
}

void printStatus() {
  Serial.printf("[통신] %s  하트비트 %lums 전  |  [ToF] %s %ldmm %s  |  "
                "[배터리] %.2fV %s  |  stopIndex=%d  mode=%s%s\n",
                rpi.connected() ? "연결됨" : "미연결",
                millis() - lastHbMs,
                tofOk ? "OK" : "없음", (long)distanceMm,
                obstacleNear ? "🔴장애물" : "",
                battVolts, battCritical ? "🔴cutoff" : "",
                stopIndex,
                driveMode == DM_REMOTE ? "REMOTE" : "LINE",
                returning ? " 🔴RETURN 진행중" : "");
}

void handleSerial() {
  if (!Serial.available()) return;
  char c = Serial.read();
  switch (c) {
    case 'e': setEnabled(!motorsEnabled);
              Serial.printf("STBY %s\n", motorsEnabled ? "ON" : "OFF"); break;
    case 'g': if (!motorsEnabled) { Serial.println(F("먼저 'e' 로 STBY 를 켤 것")); break; }
              estopLatched = false;
              driveMode = DM_LINE;
              pidRunning = true; phase = PH_CRUISE;
              blackStreak = 0; markerLatch = false;
              driveRampStartMs = millis();
              Serial.println(F("라인추종 시작 (CRUISE) · ESTOP 해제")); break;
    case 's': stopMotors(); Serial.println(F("정지 (수동)")); break;
    case 'v': useRealSensor = !useRealSensor;
              Serial.printf("센서: %s\n", useRealSensor ? "실측 (2채널)" : "가상"); break;
    case '[': simL = true;  simR = false; Serial.println(F("가상 좌=1 우=0")); break;
    case ']': simL = false; simR = true;  Serial.println(F("가상 좌=0 우=1")); break;
    case '0': simL = false; simR = false; Serial.println(F("가상 좌=0 우=0 (중앙)")); break;
    case 'b': simL = true;  simR = true;  Serial.println(F("가상 좌=1 우=1 (마커)")); break;
    case 'm': onMarker(); break;
    case 'x': stopIndex = 0; Serial.println(F("stopIndex 리셋 → 0")); break;
    case 'r': if (!motorsEnabled) { Serial.println(F("먼저 'e' 로 STBY 를 켤 것")); break; }
              if (!returning) { returning = true; returnStartMs = millis();
                                 pidRunning = false; estopLatched = false;
                                 Serial.printf("RETURN 강제 시작 — %lums 뒤 자동 정지 (자로 거리 잴 것)\n", RETURN_DURATION_MS); }
              break;
    case 'R': RETURN_DURATION_MS += 200; Serial.printf("RETURN_DURATION_MS %lums\n", RETURN_DURATION_MS); break;
    case 't': turnDelta = max(0, turnDelta - 10); Serial.printf("turnDelta %d\n", turnDelta); break;
    case 'T': turnDelta = min(PWM_MAX, turnDelta + 10); Serial.printf("turnDelta %d\n", turnDelta); break;
    case '+': baseSpeed = min(PWM_MAX, baseSpeed + 20); Serial.printf("CRUISE %d\n", baseSpeed); break;
    case '-': baseSpeed = max(0, baseSpeed - 20); Serial.printf("CRUISE %d\n", baseSpeed); break;
    case 'a': approachSpeed = max(0, approachSpeed - 20); Serial.printf("APPROACH %d\n", approachSpeed); break;
    case 'A': approachSpeed = min(PWM_MAX, approachSpeed + 20); Serial.printf("APPROACH %d\n", approachSpeed); break;
    case 'c': Serial.printf("현재 battCalib=%.3f, 측정 %.2fV. 멀티미터 실측값 ÷ 이 값으로 "
                            "battCalib 을 고쳐 다시 업로드할 것 (0.8~1.5)\n", battCalib, battVolts); break;
    case 'i': printStatus(); break;
    case '?': printHelp(); break;
    default: break;
  }
}

// ══════════════════════════════════════════════════════════
// 12. setup / loop
// ══════════════════════════════════════════════════════════
void setup() {
  Serial.begin(115200);
  delay(300);

  // 🔴 모터를 가장 먼저 안전 상태로 — STBY LOW 는 TB6612 출력 차단
  pinMode(PIN_STBY, OUTPUT);
  digitalWrite(PIN_STBY, LOW);
  pinMode(PIN_AIN1, OUTPUT); pinMode(PIN_AIN2, OUTPUT);
  pinMode(PIN_BIN1, OUTPUT); pinMode(PIN_BIN2, OUTPUT);
  pinMode(PIN_LINE_L, INPUT);
  pinMode(PIN_LINE_R, INPUT);
  ledcAttach(PIN_PWMA, PWM_FREQ, PWM_BITS);
  ledcAttach(PIN_PWMB, PWM_FREQ, PWM_BITS);
  stopMotors();

  analogSetPinAttenuation(PIN_BATT, ADC_11db);   // 0~約3.3V. 사용 구간 1.98~2.52V

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PW);
  ArduinoOTA.setHostname("hazardbot-drive");
  ArduinoOTA.onStart([]() { setEnabled(false); Serial.println(F("\nOTA 수신 — 모터 차단")); });
  ArduinoOTA.begin();   // 🔵 내부에서 MDNS.begin() 을 호출한다 — 따로 부르지 않는다

  setupToF();
  readBattery();
  lastHbMs = millis();

  // 🔵 2026-08-30 — 부팅 시 STBY를 바로 켠다(RPi 원격 <GO> 로 시작하려면
  // 로컬에서 'e'를 눌러줄 사람이 없어도 돼야 한다). 듀티는 stopMotors()로 이미
  // 0이라 실제로 움직이진 않는다 — <GO>/'g' 전까진 그대로 정지 상태.
  // 🔴 이러면 통전 즉시 모터 드라이버가 살아있는 상태가 된다 — GND 직납땜
  // 도통 확인은 이제 부팅 전에(케이블 연결 전) 반드시 끝내둘 것.
  setEnabled(true);

  printHelp();
  Serial.println(F("🔵 STBY 부팅 시 자동 ON — 통전 전에 GND 도통을 확인해뒀을 것."));
}

void loop() {
  ArduinoOTA.handle();
  handleSerial();

  tryConnect();
  pollRpi();
  checkRpiTimeout();
  pollToF();

  if (millis() - lastCtrlMs >= CONTROL_MS) {
    lastCtrlMs = millis();
    readBattery();
    controlStep();
    if (driveMode == DM_LINE && pidRunning) checkMarker();
  }

  if (millis() - lastSensMs >= SENS_PERIOD_MS) {
    lastSensMs = millis();
    sendSens();
  }

  if (millis() - lastTelemMs >= 1000) {
    lastTelemMs = millis();
    printStatus();
  }
}
