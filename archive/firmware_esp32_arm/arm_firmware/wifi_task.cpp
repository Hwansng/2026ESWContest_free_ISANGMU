/*
 * wifi_task.cpp - Core 0 전담 WiFi TCP 태스크
 *
 * RPi(중계)와 TCP로 <CMD,VALUE,CS> 메시지를 주고받는다.
 *  - 수신: 한 줄(\n) 단위로 모아 파싱/체크섬 검증 -> 명령 큐로 전달
 *  - 송신: 피드백 큐를 비워 <ARM,..> / <LOAD,..> 로 클라이언트에 전송
 *
 * ESP32 #1(AMR)과 직접 통신하지 않는다(반드시 RPi 중계).
 */
#include <WiFi.h>
#include "wifi_task.h"
#include "protocol.h"
#include "config.h"

static WiFiServer server(TCP_PORT);  // ESP32 #2는 TCP 서버, RPi가 접속
static WiFiClient client;
static String rxLine;                 // 수신 라인 버퍼

// 피드백 큐를 모두 비워 클라이언트로 전송
static void flushFeedback() {
  ArmFeedback fb;
  while (xQueueReceive(xQueueServoFeedback, &fb, 0) == pdTRUE) {
    String msg;
    if (fb.kind == FB_STATE) {
      msg = buildMessage("ARM", armStateName(fb.state));        // <ARM,STATE,CS>
    } else {  // FB_LOAD
      msg = buildMessage("LOAD", String(fb.loadPercent).c_str());// <LOAD,percent,CS>
    }
    if (client && client.connected()) client.print(msg);
  }
}

void wifiTask(void* pv) {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  // 연결될 때까지 대기 (서보 태스크는 Core1에서 독립적으로 동작)
  while (WiFi.status() != WL_CONNECTED) {
    vTaskDelay(pdMS_TO_TICKS(500));
  }
  server.begin();

  for (;;) {
    // 1) 클라이언트 연결 수락(끊겼으면 재수락)
    if (!client || !client.connected()) {
      client = server.available();
    }

    // 2) 수신 데이터를 한 줄(\n) 단위로 파싱
    while (client && client.available()) {
      char c = client.read();
      if (c == '\n') {
        ArmCommand cmd;
        if (parseMessage(rxLine, cmd)) {
          xQueueSend(xQueueCmdToServo, &cmd, 0);  // servoTask로 전달
        }
        rxLine = "";
      } else if (c != '\r') {
        rxLine += c;
        if (rxLine.length() > 64) rxLine = "";    // 비정상 과길이 방지
      }
    }

    // 3) 피드백 송신
    flushFeedback();

    vTaskDelay(pdMS_TO_TICKS(5));
  }
}
