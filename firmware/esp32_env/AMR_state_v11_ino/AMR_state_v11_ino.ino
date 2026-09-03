/*
 * File: AMR_state_v11_ino.ino
 * Target Board: ESP32 ENV sensor and alarm board
 *
 * Demonstration sensors:
 * - MQ-2 D0 through a 10k/10k divider on GPIO34
 * - KY-026 digital output on GPIO27
 * - TMB12A05 buzzer module on GPIO26 (active HIGH)
 *
 * Scope:
 * - Sensor state evaluation and continuous safety-alarm output.
 * - Battery voltage remains a test injection until a divider is connected.
 *
 * Gas sensing is MQ-2 only (final decision 2026-09-03). MQ-135 is not fitted.
 *
 * RPi Message Format:
 *   <SENS,mq135,mq2,flame,battCv,stateCode,actionCode,faultCode,checksum>
 *
 * The mq135 field is a constant 0. It is kept in place because
 * sensor_bridge_node.py parses this frame by field position -- removing the
 * field would shift every value after it. Do not renumber the frame here
 * without changing the parser in the same commit.
 *
 * checksum is the decimal ASCII sum of the payload modulo 256.
 */

#include <Arduino.h>
#include <WiFi.h>
#include <ESPmDNS.h>
#include <WiFiClient.h>
#include <AMRDemoScenarioLogic.h>
#include "wifi_secrets.h"

// ======================================================
// Pin Settings
// ======================================================

const int INCENSE_DO_PIN = 34;
const int FLAME_PIN = 27;
const int BUZZER_PIN = 26;
const int BUZZER_ACTIVE_LEVEL = HIGH;
const int BUZZER_INACTIVE_LEVEL = LOW;

// ======================================================
// MQ Sensor and Calibration Settings
// ======================================================

const int SAMPLE_COUNT = 10;
const int CALIBRATION_SAMPLE_COUNT = 10;
const unsigned long CALIBRATION_SETTLE_MS = 180000;
const int ADC_MIN_VALID_VALUE = 1;
const int ADC_MAX_VALID_VALUE = 4094;
const int MQ_BASELINE_MAX_VALUE = 2700;

const int WARNING_ENTER_PERCENT = 20;
const int WARNING_EXIT_PERCENT = 15;
const int DANGER_ENTER_PERCENT = 50;
const int DANGER_EXIT_PERCENT = 40;

// ======================================================
// Timing and Communication Settings
// ======================================================

const int READ_INTERVAL_MS = 50;
const int INCENSE_SAMPLE_INTERVAL_MS = 5;
const int FLAME_SAMPLE_INTERVAL_MS = 10;
const int SENSOR_ERROR_COUNT_THRESHOLD = 3;
const unsigned long HEARTBEAT_INTERVAL_MS = 1000;
const unsigned long RPI_TIMEOUT_MS = 3000;
const int RPI_RX_BUFFER_MAX_LENGTH = 80;

const int NETWORK_FRAME_MAX_LENGTH = 128;
const unsigned long WIFI_RETRY_MS = 5000;
const unsigned long MDNS_RETRY_MS = 5000;
const unsigned long TCP_RETRY_MS = 2000;
const int TCP_CONNECT_TIMEOUT_MS = 500;
const int NETWORK_TASK_STACK_SIZE = 8192;
const int NETWORK_TASK_PRIORITY = 1;
const int NETWORK_TASK_CORE = 0;
const int NETWORK_COMMAND_QUEUE_LENGTH = 4;
const int NETWORK_RESULT_QUEUE_LENGTH = 4;
const char* ESP32_MDNS_HOST = "hazardbot-amr";

// ======================================================
// Battery Safety Settings
// ======================================================

const float LIPO_CUTOFF_VOLTAGE = 9.9;
const int CENTIVOLTS_PER_VOLT = 100;

// Bench test injection only. This is not a measured battery voltage.
float currentBatteryVoltage = 12.0;

// ======================================================
// State Definitions
// ======================================================

enum AmrState {
  STATE_SAFE,
  STATE_WARNING,
  STATE_DANGER,
  STATE_STOP,
  STATE_SENSOR_ERROR
};

enum AmrAction {
  ACTION_NORMAL_MOTION,
  ACTION_LIMITED_MOTION,
  ACTION_STOP_MOTION
};

enum SafetyFault {
  FAULT_OK = 0,
  FAULT_ESTOP_RESERVED = 1,
  FAULT_LIPO = 2,
  FAULT_SENSOR = 3,
  FAULT_RPI_TIMEOUT = 4,
  FAULT_HAZARD = 5
};

// ======================================================
// Sensor Channel Definitions
// ======================================================

struct MqChannel {
  int pin;
  int samples[SAMPLE_COUNT];
  int sampleIndex;
  long sampleSum;
  int average;
  int errorCount;
  long baselineSum;
  int baselineSampleCount;
  int baseline;
  bool sampleBufferInitialized;
  bool calibrationWindowStarted;
  bool calibrated;
};

struct NetworkFrame {
  char text[NETWORK_FRAME_MAX_LENGTH];
};

WiFiClient networkClient;

QueueHandle_t networkTelemetryQueue = nullptr;
QueueHandle_t networkCommandQueue = nullptr;
QueueHandle_t networkResultQueue = nullptr;
TaskHandle_t networkTaskHandle = nullptr;

// ======================================================
// Global State
// ======================================================

AmrState previousState = STATE_SENSOR_ERROR;
AmrState currentState = STATE_SENSOR_ERROR;

unsigned long lastReadTime = 0;
unsigned long lastIncenseSampleTime = 0;
unsigned long lastFlameSampleTime = 0;
unsigned long lastHeartbeatTime = 0;
unsigned long lastRpiMessageTime = 0;
int incenseDoRaw = 4095;
GasInspectionState gasInspection{};
bool flameRawDetected = false;
FlameLatchState flameLatch{};

String rpiRxBuffer = "";

// ======================================================
// Function Declarations
// ======================================================

void initializeMqChannel(MqChannel& channel, int pin);
void updateMqChannel(MqChannel& channel, unsigned long now);
bool isMqChannelReady(const MqChannel& channel);
int calculateRisePercent(const MqChannel& channel);
bool isFlameDetected();
void initializeBuzzer();
void updateBuzzer(bool flameDetected);

void updateRpiCommunication();
bool processRpiMessage(const String& message, unsigned long now);
bool parseGasCheckCommand(const String& message, GasInspectionZone& zone);
bool isValidRpiMessage(const String& message);
bool isDecimalChecksum(const String& text);
bool isRpiTimeoutActive(unsigned long now);
void initializeNetworkTransport();
void networkTask(void* parameter);
void queueNetworkFrame(const String& frame);
void queueNetworkResultFrame(const String& frame);
void processNetworkEvents();
const char* gasZoneToString(GasInspectionZone zone);
const char* gasResultToString(GasInspectionResult result);

AmrState evaluateDemoState(
  bool gasEventActive,
  bool flameDetected,
  float batteryVoltage,
  bool rpiTimeoutActive
);

AmrAction determineAmrAction(AmrState state);

SafetyFault determineSafetyFault(
  AmrState state,
  bool flameDetected,
  float batteryVoltage,
  bool rpiTimeoutActive
);

void applyAmrAction(AmrAction action);
String stateToString(AmrState state);
String actionToString(AmrAction action);
int stateToCode(AmrState state);
int actionToCode(AmrAction action);
int faultToCode(SafetyFault fault);
int batteryToCentivolts(float batteryVoltage);
int calculateChecksum(const String& payload);

String buildSensorPayload(
  AmrState state,
  AmrAction action,
  SafetyFault fault,
  int mq135Average,
  int mq2Average,
  bool flameDetected,
  float batteryVoltage
);

String buildGasResultPayload(const GasInspectionState& state);
void sendGasResultMessage(const GasInspectionState& state);

void sendSensorMessage(
  AmrState state,
  AmrAction action,
  SafetyFault fault,
  int mq135Average,
  int mq2Average,
  bool flameDetected,
  float batteryVoltage
);

void printDebugInfo(
  int incenseRaw,
  bool flameDetected,
  AmrState state,
  AmrAction action,
  SafetyFault fault
);

// ======================================================
// Setup and Main Loop
// ======================================================

void setup() {
  initializeBuzzer();

  Serial.begin(115200);
  delay(1000);

  pinMode(INCENSE_DO_PIN, INPUT);
  pinMode(FLAME_PIN, INPUT_PULLUP);
  analogReadResolution(12);
  analogSetPinAttenuation(INCENSE_DO_PIN, ADC_11db);

  Serial.println("AMR_state_v11 start");
  Serial.println("Target: ESP32 ENV sensor and alarm board");
  Serial.println("Demo sensors: MQ-2 D0 on GPIO34, KY-026 D0 on GPIO27");
  Serial.println("Gas check: RPi-gated adaptive sampling for 3 seconds at P1/P2");
  Serial.println("Flame filter: 3 consecutive detections, held 5 seconds after last detection");
  Serial.println("Output: TMB12A05 buzzer sounds only for the filtered flame event");
  Serial.println("Battery: TEST VALUE ONLY (not measured)");
  Serial.println("Protocol: <SENS,mq135,mq2,flame,battCv,stateCode,actionCode,faultCode,checksum>");
  Serial.println("Gas command: <CMD,GAS_CHECK,P1|P2,checksum>");

  initializeNetworkTransport();

  lastRpiMessageTime = millis();
  sendSensorMessage(
    STATE_SAFE,
    ACTION_NORMAL_MOTION,
    FAULT_OK,
    0,
    incenseDoRaw,
    false,
    currentBatteryVoltage
  );
}

void loop() {
  unsigned long now = millis();
  updateRpiCommunication();
  processNetworkEvents();

  if (now - lastIncenseSampleTime >= INCENSE_SAMPLE_INTERVAL_MS) {
    lastIncenseSampleTime = now;
    incenseDoRaw = analogRead(INCENSE_DO_PIN);
    gasInspection = updateGasInspection(gasInspection, incenseDoRaw, now);
  }

  if (gasInspection.resultReady) {
    sendGasResultMessage(gasInspection);
    gasInspection = clearGasInspectionResult(gasInspection);
  }

  if (now - lastFlameSampleTime >= FLAME_SAMPLE_INTERVAL_MS) {
    lastFlameSampleTime = now;
    flameRawDetected = isFlameDetected();
    flameLatch = updateFlameLatch(flameLatch, flameRawDetected, now);
  }

  bool flameDetected = flameLatch.active;
  updateBuzzer(flameDetected);

  if (now - lastReadTime < READ_INTERVAL_MS) {
    return;
  }
  lastReadTime = now;

  bool rpiTimeoutActive = isRpiTimeoutActive(now);

  currentState = evaluateDemoState(
    gasInspection.gasEventActive,
    flameDetected,
    currentBatteryVoltage,
    rpiTimeoutActive
  );

  AmrAction currentAction = determineAmrAction(currentState);
  SafetyFault currentFault = determineSafetyFault(
    currentState,
    flameDetected,
    currentBatteryVoltage,
    rpiTimeoutActive
  );

  applyAmrAction(currentAction);

  if (currentState != previousState) {
    sendSensorMessage(
      currentState,
      currentAction,
      currentFault,
      0,
      incenseDoRaw,
      flameDetected,
      currentBatteryVoltage
    );
    previousState = currentState;
    lastHeartbeatTime = now;
  }

  if (now - lastHeartbeatTime >= HEARTBEAT_INTERVAL_MS) {
    sendSensorMessage(
      currentState,
      currentAction,
      currentFault,
      0,
      incenseDoRaw,
      flameDetected,
      currentBatteryVoltage
    );
    lastHeartbeatTime = now;
  }

  printDebugInfo(
    incenseDoRaw,
    flameDetected,
    currentState,
    currentAction,
    currentFault
  );
}

// ======================================================
// MQ Sensor Reading and Calibration
// ======================================================

void initializeMqChannel(MqChannel& channel, int pin) {
  channel.pin = pin;
  channel.sampleIndex = 0;
  channel.sampleSum = 0;
  channel.average = 0;
  channel.errorCount = 0;
  channel.baselineSum = 0;
  channel.baselineSampleCount = 0;
  channel.baseline = 0;
  channel.sampleBufferInitialized = false;
  channel.calibrationWindowStarted = false;
  channel.calibrated = false;

  for (int i = 0; i < SAMPLE_COUNT; i++) {
    channel.samples[i] = 0;
  }
}

void updateMqChannel(MqChannel& channel, unsigned long now) {
  int rawValue = analogRead(channel.pin);
  bool rawValid = (
    rawValue >= ADC_MIN_VALID_VALUE &&
    rawValue <= ADC_MAX_VALID_VALUE
  );

  if (!rawValid) {
    channel.errorCount++;
    return;
  }
  channel.errorCount = 0;

  if (!channel.sampleBufferInitialized) {
    channel.sampleSum = (long)rawValue * SAMPLE_COUNT;
    channel.average = rawValue;
    for (int i = 0; i < SAMPLE_COUNT; i++) {
      channel.samples[i] = rawValue;
    }
    channel.sampleBufferInitialized = true;
  } else {
    channel.sampleSum -= channel.samples[channel.sampleIndex];
    channel.samples[channel.sampleIndex] = rawValue;
    channel.sampleSum += rawValue;
    channel.sampleIndex = (channel.sampleIndex + 1) % SAMPLE_COUNT;
    channel.average = channel.sampleSum / SAMPLE_COUNT;
  }

  if (!channel.calibrated && now >= CALIBRATION_SETTLE_MS) {
    if (!channel.calibrationWindowStarted) {
      channel.sampleIndex = 0;
      channel.sampleSum = (long)rawValue * SAMPLE_COUNT;
      channel.average = rawValue;
      for (int i = 0; i < SAMPLE_COUNT; i++) {
        channel.samples[i] = rawValue;
      }
      channel.calibrationWindowStarted = true;
    }

    channel.baselineSum += channel.average;
    channel.baselineSampleCount++;
    if (channel.baselineSampleCount == CALIBRATION_SAMPLE_COUNT) {
      channel.baseline = channel.baselineSum / CALIBRATION_SAMPLE_COUNT;
      channel.calibrated = (
        channel.baseline >= ADC_MIN_VALID_VALUE &&
        channel.baseline <= MQ_BASELINE_MAX_VALUE
      );
    }
  }
}

bool isMqChannelReady(const MqChannel& channel) {
  return (
    channel.errorCount < SENSOR_ERROR_COUNT_THRESHOLD &&
    channel.calibrated
  );
}

int calculateRisePercent(const MqChannel& channel) {
  if (
    !channel.calibrated ||
    channel.baseline <= 0 ||
    channel.average <= channel.baseline
  ) {
    return 0;
  }
  return (channel.average - channel.baseline) * 100 / channel.baseline;
}

bool isFlameDetected() {
  return digitalRead(FLAME_PIN) == LOW;
}

void initializeBuzzer() {
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, BUZZER_INACTIVE_LEVEL);
}

void updateBuzzer(bool flameDetected) {
  bool shouldSound = demoBuzzerShouldSound(flameDetected);
  digitalWrite(
    BUZZER_PIN,
    shouldSound ? BUZZER_ACTIVE_LEVEL : BUZZER_INACTIVE_LEVEL
  );
}

// ======================================================
// Raspberry Pi Communication
// ======================================================

void updateRpiCommunication() {
  while (Serial.available() > 0) {
    char incoming = Serial.read();

    if (incoming == '<') {
      rpiRxBuffer = "<";
      continue;
    }
    if (rpiRxBuffer.length() == 0) {
      continue;
    }

    rpiRxBuffer += incoming;
    if (rpiRxBuffer.length() > RPI_RX_BUFFER_MAX_LENGTH) {
      rpiRxBuffer = "";
      continue;
    }

    if (incoming == '>') {
      processRpiMessage(rpiRxBuffer, millis());
      rpiRxBuffer = "";
    }
  }
}

bool processRpiMessage(const String& message, unsigned long now) {
  if (!isValidRpiMessage(message)) {
    return false;
  }

  lastRpiMessageTime = now;

  GasInspectionZone requestedZone = GAS_ZONE_NONE;
  if (!parseGasCheckCommand(message, requestedZone)) {
    return true;
  }

  if (gasInspection.sampling || gasInspection.resultReady) {
    Serial.print("[GAS] GAS_CHECK_BUSY ACTIVE=");
    Serial.print(gasZoneToString(gasInspection.activeZone));
    Serial.print(" REQUESTED=");
    Serial.println(gasZoneToString(requestedZone));
    return true;
  }

  gasInspection = startGasInspection(gasInspection, requestedZone, now);
  if (gasInspection.resultReady) {
    Serial.print("[GAS] START_ERROR ZONE=");
    Serial.print(gasZoneToString(requestedZone));
    Serial.print(" BASELINE=");
    Serial.println(gasInspection.frozenBaseline);
    return true;
  }

  Serial.print("[GAS] START ZONE=");
  Serial.print(gasZoneToString(requestedZone));
  Serial.print(" BASELINE=");
  Serial.println(gasInspection.frozenBaseline);
  return true;
}

bool parseGasCheckCommand(const String& message, GasInspectionZone& zone) {
  zone = GAS_ZONE_NONE;
  if (!message.startsWith("<") || !message.endsWith(">")) {
    return false;
  }

  String body = message.substring(1, message.length() - 1);
  int checksumSeparator = body.lastIndexOf(',');
  if (checksumSeparator <= 0) {
    return false;
  }

  String payload = body.substring(0, checksumSeparator);
  zone = gasInspectionZoneForPayload(payload.c_str());
  return zone != GAS_ZONE_NONE;
}

bool isValidRpiMessage(const String& message) {
  if (!message.startsWith("<") || !message.endsWith(">")) {
    return false;
  }

  String body = message.substring(1, message.length() - 1);
  int checksumSeparator = body.lastIndexOf(',');
  if (checksumSeparator <= 0) {
    return false;
  }

  String payload = body.substring(0, checksumSeparator);
  String checksumText = body.substring(checksumSeparator + 1);
  if (!isDecimalChecksum(checksumText)) {
    return false;
  }
  return calculateChecksum(payload) == checksumText.toInt();
}

bool isDecimalChecksum(const String& text) {
  if (text.length() == 0 || text.length() > 3) {
    return false;
  }
  for (int i = 0; i < text.length(); i++) {
    if (text[i] < '0' || text[i] > '9') {
      return false;
    }
  }
  int value = text.toInt();
  return value >= 0 && value <= 255;
}

bool isRpiTimeoutActive(unsigned long now) {
  return now - lastRpiMessageTime >= RPI_TIMEOUT_MS;
}

// ======================================================
// Wi-Fi and TCP Transport
// ======================================================

void initializeNetworkTransport() {
  networkTelemetryQueue = xQueueCreate(1, sizeof(NetworkFrame));
  networkCommandQueue = xQueueCreate(
    NETWORK_COMMAND_QUEUE_LENGTH,
    sizeof(NetworkFrame)
  );
  networkResultQueue = xQueueCreate(
    NETWORK_RESULT_QUEUE_LENGTH,
    sizeof(NetworkFrame)
  );

  if (
    networkTelemetryQueue == nullptr ||
    networkCommandQueue == nullptr ||
    networkResultQueue == nullptr
  ) {
    Serial.println("[TCP] QUEUE_INIT_FAILED");
    return;
  }

  BaseType_t taskCreated = xTaskCreatePinnedToCore(
    networkTask,
    "amr-network",
    NETWORK_TASK_STACK_SIZE,
    nullptr,
    NETWORK_TASK_PRIORITY,
    &networkTaskHandle,
    NETWORK_TASK_CORE
  );

  if (taskCreated != pdPASS) {
    networkTaskHandle = nullptr;
    Serial.println("[TCP] TASK_INIT_FAILED");
  }
}

void queueNetworkFrame(const String& frame) {
  if (networkTelemetryQueue == nullptr) {
    return;
  }

  NetworkFrame queuedFrame = {};
  frame.substring(0, NETWORK_FRAME_MAX_LENGTH - 1).toCharArray(
    queuedFrame.text,
    NETWORK_FRAME_MAX_LENGTH
  );
  xQueueOverwrite(networkTelemetryQueue, &queuedFrame);
}

void queueNetworkResultFrame(const String& frame) {
  if (networkResultQueue == nullptr) {
    return;
  }

  NetworkFrame queuedFrame = {};
  frame.substring(0, NETWORK_FRAME_MAX_LENGTH - 1).toCharArray(
    queuedFrame.text,
    NETWORK_FRAME_MAX_LENGTH
  );
  if (xQueueSend(networkResultQueue, &queuedFrame, 0) != pdTRUE) {
    Serial.println("[TCP] RESULT_QUEUE_FULL");
  }
}

void processNetworkEvents() {
  if (networkCommandQueue == nullptr) {
    return;
  }

  NetworkFrame commandFrame = {};
  while (xQueueReceive(networkCommandQueue, &commandFrame, 0) == pdTRUE) {
    processRpiMessage(String(commandFrame.text), millis());
  }
}

void networkTask(void* parameter) {
  (void)parameter;

  bool wifiWasConnected = false;
  bool mdnsStarted = false;
  bool serverResolved = false;
  bool tcpWasConnected = false;
  unsigned long lastWifiAttempt = millis() - WIFI_RETRY_MS;
  unsigned long lastMdnsAttempt = millis() - MDNS_RETRY_MS;
  unsigned long lastTcpAttempt = millis() - TCP_RETRY_MS;
  IPAddress serverIp;
  String tcpRxBuffer = "";

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);

  for (;;) {
    unsigned long now = millis();
    bool wifiConnected = WiFi.status() == WL_CONNECTED;

    if (!wifiConnected) {
      if (tcpWasConnected) {
        Serial.println("[TCP] DISCONNECTED");
      }
      networkClient.stop();
      tcpWasConnected = false;
      serverResolved = false;
      tcpRxBuffer = "";

      if (mdnsStarted) {
        MDNS.end();
        mdnsStarted = false;
      }

      if (wifiWasConnected) {
        Serial.println("[WIFI] DISCONNECTED");
        wifiWasConnected = false;
      }

      if (now - lastWifiAttempt >= WIFI_RETRY_MS) {
        lastWifiAttempt = now;
        Serial.println("[WIFI] CONNECTING");
        WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
      }

      vTaskDelay(pdMS_TO_TICKS(20));
      continue;
    }

    if (!wifiWasConnected) {
      wifiWasConnected = true;
      lastMdnsAttempt = now - MDNS_RETRY_MS;
      Serial.print("[WIFI] CONNECTED IP=");
      Serial.println(WiFi.localIP());
    }

    if (!mdnsStarted) {
      if (now - lastMdnsAttempt >= MDNS_RETRY_MS) {
        lastMdnsAttempt = now;
        if (MDNS.begin(ESP32_MDNS_HOST)) {
          mdnsStarted = true;
          Serial.println("[MDNS] READY");
        } else {
          Serial.println("[MDNS] START_FAILED");
        }
      }
      vTaskDelay(pdMS_TO_TICKS(20));
      continue;
    }

    if (!serverResolved) {
      if (now - lastMdnsAttempt >= MDNS_RETRY_MS) {
        lastMdnsAttempt = now;
        serverIp = MDNS.queryHost(RPI_MDNS_HOST);
        if (serverIp != IPAddress()) {
          serverResolved = true;
          lastTcpAttempt = now - TCP_RETRY_MS;
          Serial.print("[MDNS] RPI_IP=");
          Serial.println(serverIp);
        } else {
          Serial.println("[MDNS] RPI_NOT_FOUND");
        }
      }
      vTaskDelay(pdMS_TO_TICKS(20));
      continue;
    }

    if (!networkClient.connected()) {
      if (tcpWasConnected) {
        Serial.println("[TCP] DISCONNECTED");
        tcpWasConnected = false;
      }

      if (now - lastTcpAttempt >= TCP_RETRY_MS) {
        lastTcpAttempt = now;
        Serial.println("[TCP] CONNECTING");
        if (networkClient.connect(serverIp, RPI_TCP_PORT, TCP_CONNECT_TIMEOUT_MS)) {
          tcpWasConnected = true;
          tcpRxBuffer = "";
          Serial.println("[TCP] CONNECTED");
        } else {
          networkClient.stop();
          serverResolved = false;
          lastMdnsAttempt = now;
          Serial.println("[TCP] CONNECT_FAILED");
        }
      }

      vTaskDelay(pdMS_TO_TICKS(20));
      continue;
    }

    NetworkFrame resultFrame = {};
    if (xQueueReceive(networkResultQueue, &resultFrame, 0) == pdTRUE) {
      size_t frameLength = strnlen(resultFrame.text, NETWORK_FRAME_MAX_LENGTH);
      size_t bytesWritten = networkClient.write(
        reinterpret_cast<const uint8_t*>(resultFrame.text),
        frameLength
      );
      if (bytesWritten != frameLength) {
        xQueueSendToFront(networkResultQueue, &resultFrame, 0);
        networkClient.stop();
      }
    }

    NetworkFrame outgoingFrame = {};
    if (
      networkClient.connected() &&
      xQueueReceive(networkTelemetryQueue, &outgoingFrame, 0) == pdTRUE
    ) {
      size_t frameLength = strnlen(outgoingFrame.text, NETWORK_FRAME_MAX_LENGTH);
      size_t bytesWritten = networkClient.write(
        reinterpret_cast<const uint8_t*>(outgoingFrame.text),
        frameLength
      );
      if (bytesWritten != frameLength) {
        networkClient.stop();
      }
    }

    while (networkClient.connected() && networkClient.available() > 0) {
      char incoming = (char)networkClient.read();

      if (incoming == '<') {
        tcpRxBuffer = "<";
        continue;
      }
      if (tcpRxBuffer.length() == 0) {
        continue;
      }

      tcpRxBuffer += incoming;
      if (tcpRxBuffer.length() > RPI_RX_BUFFER_MAX_LENGTH) {
        tcpRxBuffer = "";
        continue;
      }

      if (incoming == '>') {
        NetworkFrame commandFrame = {};
        tcpRxBuffer.substring(0, NETWORK_FRAME_MAX_LENGTH - 1).toCharArray(
          commandFrame.text,
          NETWORK_FRAME_MAX_LENGTH
        );
        if (xQueueSend(networkCommandQueue, &commandFrame, 0) != pdTRUE) {
          Serial.println("[TCP] COMMAND_QUEUE_FULL");
        }
        tcpRxBuffer = "";
      }
    }

    vTaskDelay(pdMS_TO_TICKS(20));
  }
}

// ======================================================
// State Evaluation
// ======================================================

AmrState evaluateDemoState(
  bool gasEventActive,
  bool flameDetected,
  float batteryVoltage,
  bool rpiTimeoutActive
) {
  if (batteryVoltage <= LIPO_CUTOFF_VOLTAGE) {
    return STATE_STOP;
  }
  if (rpiTimeoutActive) {
    return STATE_STOP;
  }
  if (flameDetected || gasEventActive) {
    return STATE_DANGER;
  }
  return STATE_SAFE;
}

AmrAction determineAmrAction(AmrState state) {
  switch (state) {
    case STATE_SAFE:
      return ACTION_NORMAL_MOTION;
    case STATE_WARNING:
      return ACTION_LIMITED_MOTION;
    case STATE_DANGER:
    case STATE_STOP:
    case STATE_SENSOR_ERROR:
    default:
      return ACTION_STOP_MOTION;
  }
}

SafetyFault determineSafetyFault(
  AmrState state,
  bool flameDetected,
  float batteryVoltage,
  bool rpiTimeoutActive
) {
  if (batteryVoltage <= LIPO_CUTOFF_VOLTAGE) {
    return FAULT_LIPO;
  }
  if (rpiTimeoutActive) {
    return FAULT_RPI_TIMEOUT;
  }
  if (state == STATE_DANGER || flameDetected) {
    return FAULT_HAZARD;
  }
  return FAULT_OK;
}

void applyAmrAction(AmrAction action) {
  // Sensor-only bench: keep the state-to-action hook without outputs.
  switch (action) {
    case ACTION_NORMAL_MOTION:
    case ACTION_LIMITED_MOTION:
    case ACTION_STOP_MOTION:
    default:
      break;
  }
}

// ======================================================
// Message Functions
// ======================================================

String stateToString(AmrState state) {
  switch (state) {
    case STATE_SAFE:
      return "SAFE";
    case STATE_WARNING:
      return "WARNING";
    case STATE_DANGER:
      return "DANGER";
    case STATE_STOP:
      return "STOP";
    case STATE_SENSOR_ERROR:
      return "SENSOR_ERROR";
    default:
      return "UNKNOWN";
  }
}

String actionToString(AmrAction action) {
  switch (action) {
    case ACTION_NORMAL_MOTION:
      return "NORMAL_MOTION";
    case ACTION_LIMITED_MOTION:
      return "LIMITED_MOTION";
    case ACTION_STOP_MOTION:
      return "STOP_MOTION";
    default:
      return "UNKNOWN_ACTION";
  }
}

int stateToCode(AmrState state) {
  switch (state) {
    case STATE_SAFE:
      return 0;
    case STATE_WARNING:
      return 1;
    case STATE_DANGER:
      return 2;
    case STATE_STOP:
      return 3;
    case STATE_SENSOR_ERROR:
      return 4;
    default:
      return 9;
  }
}

int actionToCode(AmrAction action) {
  switch (action) {
    case ACTION_NORMAL_MOTION:
      return 0;
    case ACTION_LIMITED_MOTION:
      return 1;
    case ACTION_STOP_MOTION:
      return 2;
    default:
      return 9;
  }
}

int faultToCode(SafetyFault fault) {
  switch (fault) {
    case FAULT_OK:
      return 0;
    case FAULT_ESTOP_RESERVED:
      return 1;
    case FAULT_LIPO:
      return 2;
    case FAULT_SENSOR:
      return 3;
    case FAULT_RPI_TIMEOUT:
      return 4;
    case FAULT_HAZARD:
      return 5;
    default:
      return 9;
  }
}

int batteryToCentivolts(float batteryVoltage) {
  return (int)(batteryVoltage * CENTIVOLTS_PER_VOLT + 0.5);
}

int calculateChecksum(const String& payload) {
  int checksum = 0;
  for (int i = 0; i < payload.length(); i++) {
    checksum = (checksum + (byte)payload[i]) % 256;
  }
  return checksum;
}

const char* gasZoneToString(GasInspectionZone zone) {
  switch (zone) {
    case GAS_ZONE_P1:
      return "P1";
    case GAS_ZONE_P2:
      return "P2";
    case GAS_ZONE_NONE:
    default:
      return "NONE";
  }
}

const char* gasResultToString(GasInspectionResult result) {
  switch (result) {
    case GAS_RESULT_CLEAR:
      return "CLEAR";
    case GAS_RESULT_DETECTED:
      return "DETECTED";
    case GAS_RESULT_ERROR:
      return "ERROR";
    case GAS_RESULT_PENDING:
    default:
      return "PENDING";
  }
}

String buildGasResultPayload(const GasInspectionState& state) {
  int weakPercent = state.totalSamples == 0
    ? 0
    : (int)((uint32_t)state.weakSamples * 100UL / state.totalSamples);

  String payload = "GAS_RESULT";
  payload += ",";
  payload += gasZoneToString(state.resultZone);
  payload += ",";
  payload += gasResultToString(state.result);
  payload += ",";
  payload += String(state.frozenBaseline);
  payload += ",";
  payload += String(state.minimumRaw);
  payload += ",";
  payload += String(weakPercent);
  return payload;
}

void sendGasResultMessage(const GasInspectionState& state) {
  String payload = buildGasResultPayload(state);
  String frame = "<";
  frame += payload;
  frame += ",";
  frame += String(calculateChecksum(payload));
  frame += ">\n";

  Serial.print("[GAS] RESULT ZONE=");
  Serial.print(gasZoneToString(state.resultZone));
  Serial.print(" VALUE=");
  Serial.print(gasResultToString(state.result));
  Serial.print(" BASELINE=");
  Serial.print(state.frozenBaseline);
  Serial.print(" MIN=");
  Serial.print(state.minimumRaw);
  Serial.print(" STRONG=");
  Serial.print(state.strongSamples);
  Serial.print(" WEAK=");
  Serial.print(state.weakSamples);
  Serial.print(" TOTAL=");
  Serial.print(state.totalSamples);
  Serial.print(" WEAK_PERCENT=");
  Serial.println(
    state.totalSamples == 0
      ? 0
      : (int)((uint32_t)state.weakSamples * 100UL / state.totalSamples)
  );

  Serial.print(frame);
  queueNetworkResultFrame(frame);
}

String buildSensorPayload(
  AmrState state,
  AmrAction action,
  SafetyFault fault,
  int mq135Average,
  int mq2Average,
  bool flameDetected,
  float batteryVoltage
) {
  String payload = "SENS";
  payload += ",";
  payload += String(mq135Average);
  payload += ",";
  payload += String(mq2Average);
  payload += ",";
  payload += String(flameDetected ? 1 : 0);
  payload += ",";
  payload += String(batteryToCentivolts(batteryVoltage));
  payload += ",";
  payload += String(stateToCode(state));
  payload += ",";
  payload += String(actionToCode(action));
  payload += ",";
  payload += String(faultToCode(fault));
  return payload;
}

void sendSensorMessage(
  AmrState state,
  AmrAction action,
  SafetyFault fault,
  int mq135Average,
  int mq2Average,
  bool flameDetected,
  float batteryVoltage
) {
  String payload = buildSensorPayload(
    state,
    action,
    fault,
    mq135Average,
    mq2Average,
    flameDetected,
    batteryVoltage
  );
  String frame = "<";
  frame += payload;
  frame += ",";
  frame += String(calculateChecksum(payload));
  frame += ">\n";
  Serial.print(frame);
  queueNetworkFrame(frame);
}

// ======================================================
// Debug Output
// ======================================================

void printDebugInfo(
  int incenseRaw,
  bool flameDetected,
  AmrState state,
  AmrAction action,
  SafetyFault fault
) {
  Serial.print("[DEBUG] INCENSE_D0_RAW=");
  Serial.print(incenseRaw);
  Serial.print(" | GAS_EVENT=");
  Serial.print(gasInspection.gasEventActive ? "ACTIVE" : "OFF");
  Serial.print(" | GAS_CHECK=");
  Serial.print(gasInspection.sampling ? "SAMPLING" : "IDLE");
  Serial.print(" | GAS_ZONE=");
  Serial.print(gasZoneToString(gasInspection.activeZone));
  Serial.print(" | GAS_BASELINE=");
  Serial.print(gasInspection.baselineReady ? gasInspection.baseline : 0);
  Serial.print(" | FLAME_RAW=");
  Serial.print(flameRawDetected ? "YES" : "NO");
  Serial.print(" | FLAME_LATCH=");
  Serial.print(flameDetected ? "YES" : "NO");
  Serial.print(" | BUZZER=");
  Serial.print(digitalRead(BUZZER_PIN) == BUZZER_ACTIVE_LEVEL ? "ON" : "OFF");
  Serial.print(" | BAT_TEST_VALUE=");
  Serial.print(currentBatteryVoltage, 2);
  Serial.print("V | STATE=");
  Serial.print(stateToString(state));
  Serial.print(" | ACTION=");
  Serial.print(actionToString(action));
  Serial.print(" | FAULT=");
  Serial.println(faultToCode(fault));
}
