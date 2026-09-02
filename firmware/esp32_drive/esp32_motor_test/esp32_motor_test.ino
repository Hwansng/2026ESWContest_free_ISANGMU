// HazardBot DRIVE — 모터만 확인하는 최소 스케치 (2026-08-28)
//
// esp32_drive_tcp.ino 를 올리기 전, 새 ESP_Drive 보드가 TB6612 를 제대로
// 돌리는지만 먼저 확인한다. WiFi·OTA·라인센서·ToF 전부 없음 — USB 만으로 동작.
//
// 🔴 통전 전 필수 — GND 도통부터. 지난 보드는 GND 핀소켓 접점이 진동으로
//   빠져서 죽었다(esp-drive-board-failure). 무전원 상태 부저 모드로
//   ① ESP32 GND ↔ 스타포인트  ② TB6612 GND 3패드 전부  ③ 12V(−) 한 점에서만
//   만나는지 확인한 뒤에 USB 를 꽂을 것.
// 🔴 벤치 규칙 — 바퀴를 띄운 채로 먼저 돌릴 것. 책상에서 굴러떨어진다.
// 🔴 12V(모터 전원) 인가 중 USB 업로드 금지 — 배선_확정 공통 규칙.

// ── 핀 — esp32_drive_tcp.ino 와 동일(배선_확정_2026-08-14.md §1.5) ──
#define PIN_PWMA   25
#define PIN_AIN1   26
#define PIN_AIN2   27
#define PIN_PWMB   14
#define PIN_BIN1   16      // 보드에 RX2 로 인쇄된 경우가 많다
#define PIN_BIN2   17      // 〃        TX2
#define PIN_STBY    4

const int PWM_FREQ = 20000;   // 가청 대역(~16kHz) 위 — 모터가 삐 소리 안 냄
const int PWM_BITS = 8;
const int PWM_MAX  = 255;

// 명령 후 이 시간 동안 입력이 없으면 자동 정지 — 자리를 비웠을 때 계속 도는 것 방지
const unsigned long CMD_TIMEOUT_MS = 5000;

int  speedDuty     = 100;   // 낮게 시작 — esp32_drive_tcp.ino 의 baseSpeed(120)보다 보수적
bool motorsEnabled = false;
bool moving        = false;
unsigned long lastCmdMs = 0;

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

void stopMotors() { drive(0, 0); moving = false; }

void setEnabled(bool on) {
  motorsEnabled = on;
  digitalWrite(PIN_STBY, on ? HIGH : LOW);
  if (!on) stopMotors();
}

void printHelp() {
  Serial.println(F(
    "\n── 모터 단독 확인 ─────────────────────\n"
    "  e : STBY 토글 (먼저 켤 것)\n"
    "  w : 전진   x : 후진   s : 정지\n"
    "  a : 좌회전  d : 우회전 (제자리 회전)\n"
    "  q : 좌측만  r : 우측만  ← 배선(방향) 뒤집힘 확인용\n"
    "  + / - : 듀티 ±20 (현재 값은 'i')\n"
    "  i : 상태 한 줄\n"
    "  ? : 이 목록\n"
    "───────────────────────────────────────\n"
    "'q' 눌렀을 때 왼쪽 바퀴만 전진해야 정상, 'r' 은 오른쪽만.\n"
    "반대로 돌면 그 채널의 AIN1/AIN2(또는 BIN1/BIN2) 배선이 뒤집힌 것."));
}

void printStatus() {
  Serial.printf("STBY=%s  듀티=%3d  %s\n",
                motorsEnabled ? "ON" : "OFF", speedDuty,
                moving ? "구동중" : "정지");
}

void setup() {
  Serial.begin(115200);
  delay(300);

  // 🔴 STBY 를 가장 먼저 LOW 로 — 나머지 핀이 정해지기 전에 모터가 돌면 안 된다
  pinMode(PIN_STBY, OUTPUT);
  digitalWrite(PIN_STBY, LOW);
  pinMode(PIN_AIN1, OUTPUT); pinMode(PIN_AIN2, OUTPUT);
  pinMode(PIN_BIN1, OUTPUT); pinMode(PIN_BIN2, OUTPUT);

  ledcAttach(PIN_PWMA, PWM_FREQ, PWM_BITS);
  ledcAttach(PIN_PWMB, PWM_FREQ, PWM_BITS);
  stopMotors();

  printHelp();
  Serial.println(F("\n🔴 GND 도통 확인 안 했으면 지금 뽑을 것. 했으면 'e' 로 STBY 켜고 시작."));
}

void loop() {
  if (Serial.available()) {
    switch (Serial.read()) {
      case 'e': setEnabled(!motorsEnabled);
                Serial.printf("STBY %s\n", motorsEnabled ? "ON" : "OFF"); break;
      case 'w': drive(+1, +1); Serial.println("전진"); break;
      case 'x': drive(-1, -1); Serial.println("후진"); break;
      case 'a': drive(-1, +1); Serial.println("좌회전"); break;
      case 'd': drive(+1, -1); Serial.println("우회전"); break;
      case 'q': drive(+1,  0); Serial.println("좌측만 — 왼쪽 바퀴가 전진해야 정상"); break;
      case 'r': drive( 0, +1); Serial.println("우측만 — 오른쪽 바퀴가 전진해야 정상"); break;
      case 's': stopMotors();  Serial.println("정지"); break;
      case '+': speedDuty = min(PWM_MAX, speedDuty + 20); Serial.printf("듀티 %d\n", speedDuty); break;
      case '-': speedDuty = max(0, speedDuty - 20);        Serial.printf("듀티 %d\n", speedDuty); break;
      case 'i': printStatus(); break;
      case '?': printHelp(); break;
      default: break;
    }
  }

  if (moving && millis() - lastCmdMs > CMD_TIMEOUT_MS) {
    stopMotors();
    Serial.println("⚠ 명령 없음 5초 — 자동 정지");
  }
}
