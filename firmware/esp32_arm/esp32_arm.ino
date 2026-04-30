/*
 * File: esp32_arm.ino
 * Target: ESP32 #2 (ARM)
 *
 * Description:
 * Feetech STS3215 직렬 버스 서보 6축 제어 펌웨어.
 * FreeRTOS 듀얼 코어:
 *   - Core 0: Wi-Fi TCP (RPi 5 ↔ <CMD,...,CS>\n 포맷)
 *   - Core 1: STS3215 UART2 서보 태스크 (10ms 폴링)
 *
 * Compliance Grip:
 *   - 소프트 한계 Load 40% → 재시도(최대 3회, +5mm)
 *   - 하드 한계 Load 80% → 즉시 토크 OFF + DANGER 보고
 *
 * Hardware:
 *   - UART2 TX/RX: GPIO 17 / 16 (STS3215 데이지 체인)
 *   - NeoPixel:    GPIO 4
 *   - Buzzer:      GPIO 25
 *
 * Message Format:
 *   <CMD,VALUE,...,CS>\n   (XOR 8-bit checksum, hex 2자리)
 *
 * NOTE: 본 파일은 사전 준비기(2026-04 ~ 06) 1차 통합용 스켈레톤이다.
 *       STS3215 패킷 송수신, IK 매핑, 컴플라이언스 알고리즘은 단계적으로 채운다.
 */

#include <Arduino.h>
#include <WiFi.h>
#include <HardwareSerial.h>

// ===== 핀 정의 =====
constexpr int STS_UART_TX = 17;
constexpr int STS_UART_RX = 16;
constexpr int STS_UART_BAUD = 1000000;
constexpr int NEOPIXEL_PIN = 4;
constexpr int BUZZER_PIN = 25;

// ===== 서보 구성 =====
constexpr uint8_t SERVO_COUNT = 6;
constexpr uint8_t SERVO_IDS[SERVO_COUNT] = {1, 2, 3, 4, 5, 6};  // BASE, SHOULDER, ELBOW, WRIST_PITCH, WRIST_ROLL, GRIPPER

// ===== 컴플라이언스 임계값 (Load 0~1023 스케일) =====
constexpr int LOAD_SOFT_LIMIT = 410;   // ≈ 40%
constexpr int LOAD_HARD_LIMIT = 820;   // ≈ 80%
constexpr int GRIP_RETRY_MAX  = 3;
constexpr int GRIP_RETRY_OFFSET_STEP = 22;  // 약 5mm 환산 (서보 step)

// ===== 통신 =====
constexpr uint16_t TCP_PORT = 5002;
constexpr unsigned long SERVO_TICK_MS = 10;

HardwareSerial StsSerial(2);
WiFiServer tcpServer(TCP_PORT);
WiFiClient tcpClient;

// ===== FreeRTOS =====
QueueHandle_t cmdQueue;       // RPi → 서보 태스크
QueueHandle_t feedbackQueue;  // 서보 태스크 → Wi-Fi 태스크

struct ArmCommand {
  enum Type : uint8_t { MOVE_JOINT, MOVE_POSE, GRIP, TORQUE_OFF, STOP } type;
  int16_t params[SERVO_COUNT];
};

struct ServoFeedback {
  uint8_t id;
  int16_t position;
  int16_t load;
  int8_t  temperature;
};

// ===== 체크섬 =====
byte calculateChecksum(const String& payload) {
  byte cs = 0;
  for (size_t i = 0; i < payload.length(); ++i) cs ^= (byte)payload[i];
  return cs;
}

void sendTcp(const String& payload) {
  if (!tcpClient || !tcpClient.connected()) return;
  byte cs = calculateChecksum(payload);
  char buf[8];
  snprintf(buf, sizeof(buf), ",%02X>\n", cs);
  tcpClient.print("<");
  tcpClient.print(payload);
  tcpClient.print(buf);
}

// ===== STS3215 통신 (TODO: 구현) =====
// SCS/STS 프로토콜: Header 0xFF 0xFF, ID, Length, Instruction, Params, Checksum
// 참고: https://www.feetechrc.com (STS 시리즈 메모리 맵)
bool stsWritePosition(uint8_t id, int16_t position, int16_t speed) {
  // TODO: 패킷 빌드 + UART2 송신 + 응답 검증
  return true;
}

bool stsReadFeedback(uint8_t id, ServoFeedback& fb) {
  // TODO: SYNC_READ 또는 개별 READ로 위치/부하/온도 수신
  fb.id = id;
  fb.position = 0;
  fb.load = 0;
  fb.temperature = 25;
  return true;
}

void stsTorqueOff(uint8_t id) {
  // TODO: 토크 디스에이블 (메모리 주소 0x28에 0)
}

// ===== 컴플라이언스 파지 =====
bool compliantGrip() {
  for (int retry = 0; retry < GRIP_RETRY_MAX; ++retry) {
    // TODO: 그리퍼 점진 폐쇄 + Load 모니터링
    ServoFeedback fb;
    stsReadFeedback(SERVO_IDS[5], fb);

    if (fb.load > LOAD_HARD_LIMIT) {
      stsTorqueOff(SERVO_IDS[5]);
      sendTcp("ARM,GRIP,FAIL_HARD");
      return false;
    }
    if (fb.load > LOAD_SOFT_LIMIT) {
      sendTcp("ARM,GRIP,RETRY");
      delay(100);
      continue;
    }
    sendTcp("ARM,GRIP,OK");
    return true;
  }
  sendTcp("ARM,GRIP,FAIL_RETRY");
  return false;
}

// ===== Core 1: 서보 태스크 =====
void servoTask(void* pvParameters) {
  TickType_t lastWake = xTaskGetTickCount();
  for (;;) {
    ArmCommand cmd;
    if (xQueueReceive(cmdQueue, &cmd, 0) == pdTRUE) {
      switch (cmd.type) {
        case ArmCommand::MOVE_JOINT:
          for (int i = 0; i < SERVO_COUNT; ++i) {
            stsWritePosition(SERVO_IDS[i], cmd.params[i], 1000);
          }
          break;
        case ArmCommand::GRIP:
          compliantGrip();
          break;
        case ArmCommand::TORQUE_OFF:
        case ArmCommand::STOP:
          for (int i = 0; i < SERVO_COUNT; ++i) stsTorqueOff(SERVO_IDS[i]);
          break;
        default:
          break;
      }
    }

    // 주기적 피드백 퍼블리시
    static uint8_t cycleId = 0;
    ServoFeedback fb;
    if (stsReadFeedback(SERVO_IDS[cycleId], fb)) {
      xQueueSend(feedbackQueue, &fb, 0);
    }
    cycleId = (cycleId + 1) % SERVO_COUNT;

    vTaskDelayUntil(&lastWake, pdMS_TO_TICKS(SERVO_TICK_MS));
  }
}

// ===== Core 0: Wi-Fi TCP 태스크 =====
void parseAndDispatch(const String& line) {
  // TODO: <CMD,VALUE,...,CS> 파싱 + 체크섬 검증 + cmdQueue 적재
  if (line.startsWith("<STOP")) {
    ArmCommand c{ArmCommand::STOP, {0}};
    xQueueSend(cmdQueue, &c, 0);
  }
  // ARM, WRIST, GRIP, LED, BEEP 등 분기 추가
}

void wifiTask(void* pvParameters) {
  // TODO: Wi-Fi 자격증명은 별도 헤더(secrets.h, gitignored)로 분리 권장
  // WiFi.begin(WIFI_SSID, WIFI_PASS);
  // while (WiFi.status() != WL_CONNECTED) delay(200);
  tcpServer.begin();

  for (;;) {
    if (!tcpClient || !tcpClient.connected()) {
      tcpClient = tcpServer.available();
      if (tcpClient) sendTcp("ARM,READY");
    }

    if (tcpClient && tcpClient.available()) {
      String line = tcpClient.readStringUntil('\n');
      line.trim();
      if (line.length()) parseAndDispatch(line);
    }

    ServoFeedback fb;
    if (xQueueReceive(feedbackQueue, &fb, 0) == pdTRUE) {
      String payload = "ARM,FB," + String(fb.id) + "," +
                       String(fb.position) + "," +
                       String(fb.load) + "," +
                       String(fb.temperature);
      sendTcp(payload);
    }

    vTaskDelay(pdMS_TO_TICKS(2));
  }
}

// ===== Setup =====
void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("esp32_arm boot");

  pinMode(BUZZER_PIN, OUTPUT);
  StsSerial.begin(STS_UART_BAUD, SERIAL_8N1, STS_UART_RX, STS_UART_TX);

  cmdQueue = xQueueCreate(8, sizeof(ArmCommand));
  feedbackQueue = xQueueCreate(32, sizeof(ServoFeedback));

  xTaskCreatePinnedToCore(servoTask, "servo", 4096, nullptr, 2, nullptr, 1);
  xTaskCreatePinnedToCore(wifiTask,  "wifi",  8192, nullptr, 1, nullptr, 0);
}

void loop() {
  // FreeRTOS 태스크가 모든 일을 처리. 본 함수는 사용하지 않음.
  vTaskDelay(pdMS_TO_TICKS(1000));
}
