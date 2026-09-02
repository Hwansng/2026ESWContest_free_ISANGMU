// HazardBot 라인센서 단독 확인 — 독립 1채널 IR 반사센서 ×2 (좌/우) (2026-08-21)
//
// 기존 5채널 보드가 흑/백 구분 불가로 판단되어 독립 1채널 센서 2개(좌/우)로 교체.
// 이 단계에서는 모터를 연결하지 않는다. USB 전원만으로 동작한다.
//
// 배선:
//     각 센서 + → ESP32 **3V3**   🔴 5V 금지. ESP32 는 5V 를 못 견딘다.
//     각 센서 GND → ESP32 GND
//     좌 센서 OUT → G13   우 센서 OUT → G32
//
// 장착: 두 센서를 **라인 폭보다 넓게** 벌려서, 평소(직진 중)엔 라인이 두 센서
//       "사이"에 있어 둘 다 흰 바닥(0)을 보게 한다 — esp32_line_pid 의 마커 검출이
//       "둘 다 검정"을 마커 신호로 쓰기 때문에, 평상시에도 둘 다 검정이면 구분이 안 된다.
//
// 확인할 것 3가지:
//   1) 손을 대었다 떼면 값이 변하는가         → 안 변하면 배선/전원 문제
//   2) 검정 라인 위에서 '#' 이 뜨는가          → 반대면 'p' 로 극성 뒤집기
//   3) 왼쪽 센서를 가리면 '#' 이 왼쪽에 뜨는가 → 반대면 'o' 로 좌우 뒤집기
//
// 2·3 은 시리얼에서 즉석으로 바꿀 수 있다. 확정되면 그 값을 esp32_line_pid 로 옮긴다
// (LINE_ACTIVE_LOW, 필요하면 PIN_LINE_L/PIN_LINE_R 순서).

#include <WiFi.h>
#include <ArduinoOTA.h>

const char* WIFI_SSID = "여기에-AP-SSID";
const char* WIFI_PW   = "여기에-AP-비밀번호";  // 🔴 공개 저장소라 실제 값을 적지 않는다. 업로드 전에 여기만 채울 것.

#define PIN_LINE_L 13
#define PIN_LINE_R 32

// 이 모듈은 검정에서 HIGH 로 가정한다 (기존 5채널 보드와 동일 가정). 'p' 로 되돌릴 수 있다.
bool activeLow = false;
// 좌 센서가 실제로는 오른쪽에 달려 있으면 'o' 로 뒤집는다.
bool reversed  = false;

unsigned long lastMs = 0;
bool paused = false;

int pinL() { return reversed ? PIN_LINE_R : PIN_LINE_L; }
int pinR() { return reversed ? PIN_LINE_L : PIN_LINE_R; }

void printHelp() {
  Serial.println(F(
    "\n── 명령 ──────────────────────────────\n"
    "  p : 극성 반전 (검정에서 감지 ↔ 흰색에서 감지)\n"
    "  o : 좌우 반전 (좌 센서가 실제로 오른쪽에 달렸을 때)\n"
    "  space : 출력 일시정지/재개\n"
    "  ? : 이 목록\n"
    "──────────────────────────────────────\n"
    "raw 는 핀의 실제 전압(1=HIGH). #  = 검정 감지.\n"));
}

void setup() {
  Serial.begin(115200);
  delay(300);
  pinMode(PIN_LINE_L, INPUT);
  pinMode(PIN_LINE_R, INPUT);

  // WiFi 는 기다리지 않는다 — 붙으면 OTA 가 열리고, 안 붙어도 센서 확인에는 지장 없다
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PW);
  ArduinoOTA.setHostname("hazardbot-drive");
  ArduinoOTA.begin();

  Serial.println(F("\n=== 라인센서 확인 (2채널) ==="));
  printHelp();
}

void loop() {
  ArduinoOTA.handle();

  if (Serial.available()) {
    char c = Serial.read();
    if (c == 'p') {
      activeLow = !activeLow;
      Serial.printf(">> 극성: %s 에서 감지\n", activeLow ? "LOW" : "HIGH");
    } else if (c == 'o') {
      reversed = !reversed;
      Serial.printf(">> 좌우: %s\n", reversed ? "반전됨" : "정방향");
    } else if (c == ' ') {
      paused = !paused;
      Serial.println(paused ? ">> 일시정지" : ">> 재개");
    } else if (c == '?') {
      printHelp();
    }
  }

  if (paused || millis() - lastMs < 200) return;
  lastMs = millis();

  int rawL = digitalRead(pinL());
  int rawR = digitalRead(pinR());
  bool l = activeLow ? (rawL == LOW) : (rawL == HIGH);
  bool r = activeLow ? (rawR == LOW) : (rawR == HIGH);

  Serial.printf("raw=[L=%d R=%d]  라인[%c %c]  ",
                rawL, rawR, l ? '#' : '.', r ? '#' : '.');

  if (l && r)       Serial.println("상태=마커 후보(둘 다 검정)");
  else if (l && !r) Serial.println("상태=좌회전 필요(좌만 검정)");
  else if (!l && r) Serial.println("상태=우회전 필요(우만 검정)");
  else              Serial.println("상태=중앙(둘 다 흰 바닥) — 또는 완전 이탈, 구분 불가");
}
