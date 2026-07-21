// HazardBot ESP32 #1 (주행 보드) 브링업 — TB6612FNG + JGA25-371 ×2 + 5채널 IR 라인센서
// 2026-07-30
//
// 목적: 라인트레이싱 PID 를 짜기 **전에** 하드웨어가 기대대로 붙었는지 확인한다.
//       - 모터가 지정한 방향으로 도는가 (배선 뒤집힘 확인)
//       - 라인센서가 검정 테이프에서 실제로 값이 변하는가 (임계값 결정용)
//       - 배터리 분압이 예상 전압을 읽는가
//
// 조작: 시리얼 모니터(115200)에서 한 글자 명령. '?' 로 목록 확인.
//       OTA 경로는 유지된다 — 무선 업로드 시 모터는 자동 정지한다.
//
// 🔴 벤치 규칙: 바퀴를 띄운 채로 먼저 돌릴 것. 책상에서 굴러떨어진다.

#include <WiFi.h>
#include <ArduinoOTA.h>

// ── WiFi ─────────────────────────────────────────────────
const char* WIFI_SSID = "Hwan";
const char* WIFI_PW   = "20241029";
const char* OTA_HOST  = "hazardbot-drive";

// ── 핀 배치 ───────────────────────────────────────────────
// 선정 근거:
//   · WiFi 사용 중에는 ADC2 를 못 쓴다 → 아날로그 입력은 전부 ADC1(32~39)
//   · GPIO 34~39 는 입력 전용이라 아날로그·디지털 입력에만 쓰고 출력 핀을 아낀다
//   · 스트래핑 핀(0, 2, 5, 12, 15) 은 출력으로 쓰지 않는다 — 부팅 모드가 바뀐다
//   · GPIO 6~11 은 내장 플래시 전용, 절대 사용 금지
#define PIN_PWMA   25   // TB6612 PWMA — 좌측 모터 속도
#define PIN_AIN1   26   // TB6612 AIN1  — 좌측 방향
#define PIN_AIN2   27   // TB6612 AIN2
#define PIN_PWMB   14   // TB6612 PWMB  — 우측 모터 속도
#define PIN_BIN1   16   // TB6612 BIN1  — 우측 방향
#define PIN_BIN2   17   // TB6612 BIN2
#define PIN_STBY    4   // TB6612 STBY  — LOW 면 출력 전면 차단 (주행부 0차 보호)

// 라인센서 (TCRT5000 5채널 + 장애물 + 범퍼) — **출력이 전부 디지털**이다.
// 🔴 모듈 VCC 는 **3V3 에 연결한다.** 5V 로 구동하면 출력도 5V 가 되어
//    5V 를 못 견디는 ESP32 GPIO 가 손상된다.
// S1 이 왼쪽인지 오른쪽인지는 보드마다 다르다 — 브링업에서 한쪽 끝을 가려 확인할 것.
const int PIN_LINE[5] = { 13, 18, 19, 23, 32 };   // S1 S2 S3 S4 S5
#define PIN_NEAR   34   // 장애물 감지 (선택) — 보드 표기 D34, 입력 전용
#define PIN_CLP    35   // 범퍼 스위치 (선택) — 보드 표기 D35, 입력 전용

// 🔴 39 는 보드에 숫자가 아니라 **VN**(또는 SN) 으로 인쇄돼 있다. EN 버튼 옆이다.
#define PIN_VBAT   39   // 배터리 분압 33k/10k — 보드 표기 **VN** (ADC1_CH3, 입력 전용)

// 🔴 이 모듈은 **검정에서 HIGH** 다 (2026-07-30 실측 확정).
const bool LINE_ACTIVE_LOW = false;

#define PIN_LED     2   // DevKit V1 내장 LED

// ── PWM ──────────────────────────────────────────────────
// 20kHz — 가청 대역(~16kHz) 위라 모터가 삐 소리를 내지 않는다.
// TB6612 는 100kHz 까지 받으므로 여유가 크다.
const int PWM_FREQ = 20000;
const int PWM_BITS = 8;      // 0~255
const int PWM_MAX  = 255;

// ── 안전 ──────────────────────────────────────────────────
// 명령 후 이 시간 동안 아무 입력이 없으면 모터를 세운다.
// 시리얼 연결이 끊기거나 자리를 비웠을 때 바퀴가 계속 도는 것을 막는다.
const unsigned long CMD_TIMEOUT_MS = 5000;

int  speedDuty = 120;        // 기본 듀티 (약 47%) — 벤치에서 낮게 시작
bool motorsEnabled = false;  // STBY 상태
unsigned long lastCmdMs = 0;
unsigned long lastTelemMs = 0;
bool moving = false;

// ── 모터 제어 ─────────────────────────────────────────────
// dir: +1 정방향, -1 역방향, 0 정지(브레이크 아님 — 자연 정지)
void setMotor(int in1, int in2, int pwmPin, int dir, int duty) {
  if (dir > 0)      { digitalWrite(in1, HIGH); digitalWrite(in2, LOW);  }
  else if (dir < 0) { digitalWrite(in1, LOW);  digitalWrite(in2, HIGH); }
  else              { digitalWrite(in1, LOW);  digitalWrite(in2, LOW);  }
  ledcWrite(pwmPin, dir == 0 ? 0 : duty);
}

void drive(int leftDir, int rightDir) {
  setMotor(PIN_AIN1, PIN_AIN2, PIN_PWMA, leftDir,  speedDuty);
  setMotor(PIN_BIN1, PIN_BIN2, PIN_PWMB, rightDir, speedDuty);
  moving = (leftDir != 0 || rightDir != 0);
  lastCmdMs = millis();
}

void stopMotors() {
  drive(0, 0);
  moving = false;
}

void setEnabled(bool on) {
  motorsEnabled = on;
  digitalWrite(PIN_STBY, on ? HIGH : LOW);
  if (!on) stopMotors();
}

// ── 텔레메트리 ────────────────────────────────────────────
// 분압 33k/10k → 배터리 전압 = ADC전압 × (33+10)/10 = ×4.3
// 🔴 이 계수는 실측 보정 전 이론값이다. 멀티미터와 대조해 맞출 것.
float readBatteryV() {
  int raw = analogRead(PIN_VBAT);          // 0~4095
  float vadc = raw * 3.3f / 4095.0f;       // 11dB 감쇠 기준 근사
  return vadc * 4.3f;
}

// 5채널을 읽어 라인 감지 여부 배열로 만든다
void readLine(bool* act) {
  for (int i = 0; i < 5; i++) {
    int v = digitalRead(PIN_LINE[i]);
    act[i] = LINE_ACTIVE_LOW ? (v == LOW) : (v == HIGH);
  }
}

// 라인 위치 = 감지된 채널의 가중 평균 (-2 ~ +2, 0 이 중앙).
// 아무것도 감지 못하면 NAN — PID 에서는 '라인 이탈' 로 처리해야 한다.
float linePosition(const bool* act) {
  float sum = 0; int n = 0;
  for (int i = 0; i < 5; i++) if (act[i]) { sum += (i - 2); n++; }
  return n ? sum / n : NAN;
}

void printTelemetry() {
  bool act[5];
  readLine(act);
  char pat[6];
  for (int i = 0; i < 5; i++) pat[i] = act[i] ? '#' : '.';
  pat[5] = '\0';

  float pos = linePosition(act);
  Serial.printf("라인 [%s] ", pat);
  if (isnan(pos)) Serial.print("위치=이탈  ");
  else            Serial.printf("위치=%+.1f  ", pos);
  Serial.printf("Near=%d CLP=%d  배터리=%.2fV  듀티=%3d  STBY=%s\n",
                digitalRead(PIN_NEAR), digitalRead(PIN_CLP),
                readBatteryV(), speedDuty, motorsEnabled ? "ON" : "OFF");
}

void printHelp() {
  Serial.println(F(
    "\n── 명령 ──────────────────────────────\n"
    "  e : STBY 토글 (모터 출력 허용/차단)\n"
    "  w : 전진      x : 후진      s : 정지\n"
    "  a : 좌회전    d : 우회전    (제자리 회전)\n"
    "  q : 좌측 모터만   r : 우측 모터만   ← 배선 확인용\n"
    "  + / - : 듀티 ±20\n"
    "  t : 현재 센서값 1회 출력\n"
    "  ? : 이 목록\n"
    "──────────────────────────────────────\n"
    "라인 표시 [.....] 는 S1~S5. '#' 가 라인 감지.\n"
    "검정 테이프 위에서 '.' 만 나오면 LINE_ACTIVE_LOW 를 false 로 바꿀 것."));
}

void setup() {
  Serial.begin(115200);
  delay(300);

  // 🔴 STBY 를 가장 먼저 LOW 로 — 나머지 핀이 정해지기 전에 모터가 돌면 안 된다
  pinMode(PIN_STBY, OUTPUT);
  digitalWrite(PIN_STBY, LOW);

  pinMode(PIN_AIN1, OUTPUT); pinMode(PIN_AIN2, OUTPUT);
  pinMode(PIN_BIN1, OUTPUT); pinMode(PIN_BIN2, OUTPUT);
  for (int i = 0; i < 5; i++) pinMode(PIN_LINE[i], INPUT);
  pinMode(PIN_NEAR, INPUT);
  pinMode(PIN_CLP, INPUT);
  pinMode(PIN_LED, OUTPUT);

  // ESP32 코어 3.x API — ledcSetup/ledcAttachPin 은 사라졌다
  ledcAttach(PIN_PWMA, PWM_FREQ, PWM_BITS);
  ledcAttach(PIN_PWMB, PWM_FREQ, PWM_BITS);
  stopMotors();

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PW);
  Serial.printf("\nWiFi 접속 중: %s ", WIFI_SSID);
  for (int i = 0; i < 30 && WiFi.status() != WL_CONNECTED; i++) { delay(500); Serial.print("."); }
  Serial.println(WiFi.status() == WL_CONNECTED
                 ? "\n✅ " + WiFi.localIP().toString()
                 : "\n🔴 접속 실패 (모터 시험은 그대로 가능)");

  ArduinoOTA.setHostname(OTA_HOST);
  ArduinoOTA.onStart([]() {          // 🔴 업로드 중 모터가 마지막 PWM 으로 계속 돌면 위험
    setEnabled(false);
    Serial.println("\nOTA 수신 — 모터 차단");
  });
  ArduinoOTA.begin();

  printHelp();
  Serial.println(F("\n⚠ STBY 가 OFF 다. 'e' 로 켠 뒤 주행 명령을 줄 것."));
}

void loop() {
  ArduinoOTA.handle();

  if (Serial.available()) {
    char c = Serial.read();
    switch (c) {
      case 'e': setEnabled(!motorsEnabled);
                Serial.printf("STBY %s\n", motorsEnabled ? "ON" : "OFF"); break;
      case 'w': drive(+1, +1); Serial.println("전진"); break;
      case 'x': drive(-1, -1); Serial.println("후진"); break;
      case 'a': drive(-1, +1); Serial.println("좌회전"); break;
      case 'd': drive(+1, -1); Serial.println("우회전"); break;
      case 'q': drive(+1,  0); Serial.println("좌측 모터만 — 왼쪽 바퀴가 전진해야 정상"); break;
      case 'r': drive( 0, +1); Serial.println("우측 모터만 — 오른쪽 바퀴가 전진해야 정상"); break;
      case 's': stopMotors();  Serial.println("정지"); break;
      case '+': speedDuty = min(PWM_MAX, speedDuty + 20);
                Serial.printf("듀티 %d\n", speedDuty); break;
      case '-': speedDuty = max(0, speedDuty - 20);
                Serial.printf("듀티 %d\n", speedDuty); break;
      case 't': printTelemetry(); break;
      case '?': printHelp(); break;
      default: break;
    }
  }

  // 명령이 끊긴 채 계속 도는 것을 막는다
  if (moving && millis() - lastCmdMs > CMD_TIMEOUT_MS) {
    stopMotors();
    Serial.println("⚠ 명령 없음 5초 — 자동 정지");
  }

  // 주행 중에는 센서를 빠르게, 정지 중에는 느리게 보고한다
  unsigned long period = moving ? 200 : 1000;
  if (millis() - lastTelemMs > period) {
    lastTelemMs = millis();
    printTelemetry();
    digitalWrite(PIN_LED, !digitalRead(PIN_LED));
  }
}
