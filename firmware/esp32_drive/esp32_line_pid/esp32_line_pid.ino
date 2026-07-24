// HazardBot 라인트레이싱 조향 + 정지점 마커 검출 — 2채널 버전 (2026-08-21)
//
// ── 왜 2채널인가 ──────────────────────────────────────────
//   기존 5채널 IR 라인센서 보드가 흑/백을 구분 못하는 고장으로 판단되어,
//   독립된 1채널 IR 반사센서 2개(좌/우)로 교체했다.
//
// ── 장착 방식 — 중요 ──────────────────────────────────────
//   두 센서를 **라인 폭보다 넓게** 벌려 장착한다. 평소(직진 중)에는
//   라인이 두 센서 "사이"에 있어 **둘 다 흰 바닥(0)** 을 본다.
//   이래야 "둘 다 검정(1,1)" 이 마커(전폭 가로선)에서만 뜨는 고유 신호가 된다.
//   센서를 라인 가장자리/위에 걸치게 달면 평상시에도 (1,1) 이 나와
//   마커와 구분이 안 된다.
//
// ── 5채널 대비 알려진 한계 (감수하기로 한 트레이드오프) ──────
//   1. 연속 위치값이 없다 — 왼쪽만 감지/오른쪽만 감지/둘 다/둘 다 아님, 4상태뿐.
//      부드러운 비례 제어가 아니라 **온-오프에 가까운 제어**라 더 덜컹거릴 수 있다.
//   2. **완전히 라인을 잃었을 때를 구분할 수 없다.** 두 센서가 모두 흰 바닥을
//      보는 상태는 "정상 중앙" 과 "너무 멀리 벗어나 아예 안 보임" 이 **같은 신호(0,0)** 다.
//      → 크게 벗어나면 그대로 직진하며 못 돌아올 수 있다. 별도 복구 로직이 없다.
//   3. 마커 오검출 여유가 줄었다 — 5개 중 5개 조건이 2개 중 2개가 되어
//      급커브에서 라인이 순간적으로 양쪽에 다 걸리면 마커로 오인될 수 있다.
//
// 두 가지 입력 모드:
//   가상 모드(기본) — 시리얼로 좌/우 감지 상태를 흉내 낸다. 바퀴 띄우고 방향 검증용.
//   실측 모드('v')  — 실제 센서 2개를 읽는다.
//
// ── 정지점 마커 (firmware/구역_마커_설계.md §4~6, 2채널로 축소 적용) ──
//   좌우 둘 다 검정(1,1) 2개 = 감속 마커 → 정지 마커.
//   CRUISE(baseSpeed) --감속마커--> APPROACH(approachSpeed) --정지마커--> 숏브레이크 정지.
//   정지 후 모터를 끄고 'g' 를 기다린다 — 그 사이 자로 x·y·θ 를 측정한다.
//
// 배선: + → ESP32 3V3, GND → ESP32 GND(로직 GND 레일), OUT → GPIO (아래 핀 참조)
// 극성: 검정에서 HIGH (기존 5채널과 동일 가정 — 실측으로 재확인할 것).

#include <WiFi.h>
#include <ArduinoOTA.h>

const char* WIFI_SSID = "Hwan";
const char* WIFI_PW   = "20241029";

// ── 핀 (README 기준 — 모터/STBY는 기존과 동일, 라인센서만 2채널로 교체) ──
#define PIN_PWMA   25
#define PIN_AIN1   26
#define PIN_AIN2   27
#define PIN_PWMB   14
#define PIN_BIN1   16
#define PIN_BIN2   17
#define PIN_STBY    4
#define PIN_LINE_L 13   // 기존 S1 자리 재사용
#define PIN_LINE_R 32   // 기존 S5 자리 재사용
const bool LINE_ACTIVE_LOW = false;   // 검정에서 HIGH — 실측으로 재확인할 것

const int PWM_FREQ = 20000, PWM_BITS = 8, PWM_MAX = 255;

// ── 조향 — 연속 PD 가 아니라 2상태 온-오프 보정 ──────────────
int turnDelta    = 40;    // 한쪽만 감지됐을 때 좌우 듀티 차이. 🔲 트랙에서 튜닝
int baseSpeed     = 120;  // CRUISE 기본 듀티
int approachSpeed = 70;   // APPROACH 감속 듀티 — 🔲 실측 튜닝 대상
const int CONTROL_MS = 20;

// ── 마커 검출 — "둘 다 검정" 이 5채널의 "5개 전부" 를 대체 ────
enum Phase { PH_CRUISE, PH_APPROACH };
Phase phase = PH_CRUISE;
int   stopIndex   = 0;
int   blackStreak = 0;
bool  markerLatch = false;
unsigned long lastMarkerMs = 0;
const unsigned long MARKER_GUARD_MS = 1000;
const int SHORT_BRAKE_MS = 150;

// ── 상태 ─────────────────────────────────────────────────
bool  motorsEnabled = false;
bool  pidRunning    = false;
bool  useRealSensor = true;    // 기본을 실측 모드로 (2026-08-21)
bool  simL = false, simR = false;   // 가상 모드 좌/우 감지 상태
unsigned long lastCtrlMs = 0, lastTelemMs = 0;

void setMotor(int in1, int in2, int pwmPin, int duty) {
  if (duty >= 0) { digitalWrite(in1, HIGH); digitalWrite(in2, LOW); }
  else           { digitalWrite(in1, LOW);  digitalWrite(in2, HIGH); duty = -duty; }
  ledcWrite(pwmPin, min(duty, PWM_MAX));
}

int dutyL = 0, dutyR = 0;
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
}

void doStop() {
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

// 감속 마커 → APPROACH 진입 / 정지 마커 → 숏브레이크 정지
void onMarker() {
  if (phase == PH_CRUISE) {
    phase = PH_APPROACH;
    Serial.printf(">>> 감속 마커 감지 — APPROACH 진입 (속도 %d)\n", approachSpeed);
    return;
  }
  doStop();
  stopIndex = (stopIndex % 4) + 1;
  pidRunning = false;
  phase = PH_CRUISE;
  blackStreak = 0; markerLatch = false;
  Serial.printf(">>> 정지 마커 감지 — stopIndex=%d 도달. 정지 완료.\n", stopIndex);
  Serial.println(F("    자·모눈종이로 x/y/theta 측정 후 'g' 로 재출발할 것."));
}

// 좌우 둘 다 검정 2주기 연속 + 가드타이머 — 5채널 "5개 전부" 조건의 2채널판
void checkMarker() {
  if (!useRealSensor) return;
  bool allBlack = readL() && readR();
  if (allBlack) {
    blackStreak++;
  } else {
    blackStreak = 0;
    markerLatch = false;
  }
  if (blackStreak >= 2 && !markerLatch && (millis() - lastMarkerMs) > MARKER_GUARD_MS) {
    markerLatch = true;
    lastMarkerMs = millis();
    onMarker();
  }
}

void controlStep() {
  bool l = readL(), r = readR();
  int bs = (phase == PH_APPROACH) ? approachSpeed : baseSpeed;

  int corr = 0;
  if (l && !r)      corr = -turnDelta;   // 왼쪽만 감지 → 라인이 왼쪽 → 좌회전
  else if (!l && r) corr = +turnDelta;   // 오른쪽만 감지 → 우회전
  // (0,0) 중앙(또는 완전 이탈 — 구분 불가) / (1,1) 마커 통과 중 — 둘 다 직진 유지

  int lDuty = constrain(bs + corr, -PWM_MAX, PWM_MAX);
  int rDuty = constrain(bs - corr, -PWM_MAX, PWM_MAX);
  applyDrive(lDuty, rDuty);
}

void printHelp() {
  Serial.println(F(
    "\n── 2채널 조향 + 정지점 마커 시험 ─────────────\n"
    "  e : STBY 토글        g : 시작/재출발    s : 정지(수동, 마커 카운트 무관)\n"
    "  v : 가상/실측 센서 전환 (현재 기본: 실측)\n"
    "  [ : 가상 좌=1,우=0 (좌회전 상황)   ] : 가상 좌=0,우=1 (우회전 상황)\n"
    "  0 : 가상 좌=0,우=0 (중앙)          b : 가상 좌=1,우=1 (마커 테스트)\n"
    "  m : (실측 모드) 마커 강제 트리거\n"
    "  x : stopIndex 리셋 → 0\n"
    "  t / T : turnDelta -10 / +10\n"
    "  + / - : CRUISE 속도 ±20   a / A : APPROACH 속도 ±20\n"
    "  ? : 이 목록\n"
    "───────────────────────────────────────────────\n"
    "검증: '[' → 좌 듀티 감소·우 증가 (좌회전) 이면 정상\n"
    "정지산포 측정: 'v' 로 실측 전환 → 'g' 로 CRUISE 시작 → 정지 마커에서 자동 정지\n"
    "              → 자로 x/y/theta 측정 → 'g' 로 재출발, 정지점당 10회 반복\n"
    "⚠ 두 센서 다 흰 바닥일 때가 '정상 중앙'과 '완전 이탈'을 구분 못한다 — 알려진 한계."));
}

void setup() {
  Serial.begin(115200);
  delay(300);
  pinMode(PIN_STBY, OUTPUT);
  digitalWrite(PIN_STBY, LOW);
  pinMode(PIN_AIN1, OUTPUT); pinMode(PIN_AIN2, OUTPUT);
  pinMode(PIN_BIN1, OUTPUT); pinMode(PIN_BIN2, OUTPUT);
  pinMode(PIN_LINE_L, INPUT);
  pinMode(PIN_LINE_R, INPUT);
  ledcAttach(PIN_PWMA, PWM_FREQ, PWM_BITS);
  ledcAttach(PIN_PWMB, PWM_FREQ, PWM_BITS);
  stopMotors();

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PW);
  ArduinoOTA.setHostname("hazardbot-drive");
  ArduinoOTA.onStart([]() { setEnabled(false); Serial.println("\nOTA 수신 — 모터 차단"); });
  ArduinoOTA.begin();

  printHelp();
  Serial.println(F("⚠ 실측 모드다. 실제 센서를 바로 읽는다. 가상 모드로 방향만 확인하려면 'v'."));
}

void loop() {
  ArduinoOTA.handle();

  if (Serial.available()) {
    char c = Serial.read();
    switch (c) {
      case 'e': setEnabled(!motorsEnabled);
                Serial.printf("STBY %s\n", motorsEnabled ? "ON" : "OFF"); break;
      case 'g': if (!motorsEnabled) { Serial.println("먼저 'e' 로 STBY 를 켤 것"); break; }
                pidRunning = true; phase = PH_CRUISE;
                blackStreak = 0; markerLatch = false;
                Serial.println("시작/재출발 (CRUISE)"); break;
      case 's': stopMotors(); Serial.println("정지 (수동 — stopIndex 변화 없음)"); break;
      case 'v': useRealSensor = !useRealSensor;
                Serial.printf("센서: %s\n", useRealSensor ? "실측 (2채널)" : "가상"); break;
      case '[': simL = true;  simR = false; Serial.println("가상 좌=1 우=0"); break;
      case ']': simL = false; simR = true;  Serial.println("가상 좌=0 우=1"); break;
      case '0': simL = false; simR = false; Serial.println("가상 좌=0 우=0 (중앙)"); break;
      case 'b': simL = true;  simR = true;  Serial.println("가상 좌=1 우=1 (마커 테스트)"); break;
      case 'm': if (!pidRunning) { Serial.println("먼저 'g' 로 주행을 시작할 것"); break; }
                Serial.println("(수동) 마커 강제 트리거"); onMarker(); break;
      case 'x': stopIndex = 0; Serial.println("stopIndex 리셋 → 0"); break;
      case 't': turnDelta = max(0, turnDelta - 10); Serial.printf("turnDelta %d\n", turnDelta); break;
      case 'T': turnDelta = min(PWM_MAX, turnDelta + 10); Serial.printf("turnDelta %d\n", turnDelta); break;
      case '+': baseSpeed = min(PWM_MAX, baseSpeed + 20);
                Serial.printf("CRUISE 속도 %d\n", baseSpeed); break;
      case '-': baseSpeed = max(0, baseSpeed - 20);
                Serial.printf("CRUISE 속도 %d\n", baseSpeed); break;
      case 'a': approachSpeed = max(0, approachSpeed - 20);
                Serial.printf("APPROACH 속도 %d\n", approachSpeed); break;
      case 'A': approachSpeed = min(PWM_MAX, approachSpeed + 20);
                Serial.printf("APPROACH 속도 %d\n", approachSpeed); break;
      case '?': printHelp(); break;
      default: break;
    }
  }

  if (pidRunning && millis() - lastCtrlMs >= CONTROL_MS) {
    lastCtrlMs = millis();
    controlStep();
    checkMarker();
  }

  if (millis() - lastTelemMs >= 500) {
    lastTelemMs = millis();
    bool l = readL(), r = readR();
    Serial.printf("[%s] L=%d R=%d  듀티 좌=%+4d 우=%+4d  turnDelta=%d 속도=%d/%d  %s  stopIndex=%d\n",
                  useRealSensor ? "실측" : "가상", l, r,
                  dutyL, dutyR, turnDelta, baseSpeed, approachSpeed,
                  pidRunning ? (phase == PH_APPROACH ? "APPROACH" : "CRUISE")
                             : (motorsEnabled ? "정지대기" : "STBY OFF"),
                  stopIndex);
  }
}
