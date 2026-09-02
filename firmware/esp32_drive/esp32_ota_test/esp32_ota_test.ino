// HazardBot ESP32 OTA 연결 테스트 (2026-07-30)
//
// 목적: 주행 펌웨어를 올리기 전에 "무선 업로드 경로"부터 확보한다.
//       이 스케치를 USB 로 한 번 올리면, 이후 업로드는 WiFi 로 가능하다.
//
// 확인 방법:
//   1) 시리얼 모니터(115200)에 핫스팟 접속 + IP 가 찍히는지
//   2) Arduino IDE 포트 목록에 "hazardbot-drive at 172.20.10.x" 네트워크 포트가 뜨는지
//   3) FW_VERSION 을 2 로 바꿔 네트워크 포트로 재업로드 → 시리얼 대신 LED 점멸 속도로 확인
//      (v1 = 1초 점멸, v2 이상 = 0.2초 점멸)
//
// 🔴 iPhone 핫스팟: "호환성 최대화" ON (2.4GHz). ESP32 는 5GHz 를 못 본다.

#include <WiFi.h>
#include <ArduinoOTA.h>

// ── 여기 두 줄만 수정 ─────────────────────────────────────
const char* WIFI_SSID = "여기에-AP-SSID";
const char* WIFI_PW   = "여기에-AP-비밀번호";  // 🔴 공개 저장소라 실제 값을 적지 않는다. 업로드 전에 여기만 채울 것.
// ─────────────────────────────────────────────────────────

const int FW_VERSION = 1;          // OTA 성공 확인용 — 재업로드 때 2 로 올릴 것
const int LED_PIN    = 2;          // DevKit V1 내장 LED

unsigned long lastBlink = 0;
unsigned long lastWifiRetry = 0;
bool ledOn = false;

void setup() {
  Serial.begin(115200);
  pinMode(LED_PIN, OUTPUT);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PW);
  Serial.printf("\n[v%d] WiFi 접속 중: %s ", FW_VERSION, WIFI_SSID);
  // 최대 15초 대기 — 실패해도 loop 의 재접속 루프가 이어받는다
  for (int i = 0; i < 30 && WiFi.status() != WL_CONNECTED; i++) {
    delay(500);
    Serial.print(".");
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\n✅ 접속 성공  IP: %s  (이 주소가 네트워크 포트에 떠야 함)\n",
                  WiFi.localIP().toString().c_str());
  } else {
    Serial.println("\n🔴 접속 실패 — SSID/암호, 호환성 최대화(2.4GHz), 핫스팟 화면 열림 여부 확인");
  }

  ArduinoOTA.setHostname("hazardbot-drive");   // ESP32 #1 = 주행 보드. #2 는 hazardbot-env 로
  ArduinoOTA.onStart([]() {
    // 🔴 주행 펌웨어로 넘어가면 여기서 반드시 모터 정지 (TB6612 STBY LOW)
    Serial.println("OTA 수신 시작");
  });
  ArduinoOTA.onEnd([]()   { Serial.println("\nOTA 완료 — 재부팅"); });
  ArduinoOTA.onError([](ota_error_t e) { Serial.printf("OTA 오류 %u\n", e); });
  ArduinoOTA.begin();
}

void loop() {
  ArduinoOTA.handle();   // 🔴 매 루프 호출 — 빠지면 무선 업로드가 안 잡힌다

  // 끊기면 5초마다 재접속 (핫스팟이 유휴로 꺼졌다 켜져도 자동 복구)
  if (WiFi.status() != WL_CONNECTED && millis() - lastWifiRetry > 5000) {
    lastWifiRetry = millis();
    WiFi.disconnect();
    WiFi.begin(WIFI_SSID, WIFI_PW);
  }

  // LED 점멸 — v1: 1초 간격, v2 이상: 0.2초 간격 (OTA 성공을 눈으로 확인)
  unsigned long interval = (FW_VERSION >= 2) ? 200 : 1000;
  if (millis() - lastBlink > interval) {
    lastBlink = millis();
    ledOn = !ledOn;
    digitalWrite(LED_PIN, ledOn);
  }
}
