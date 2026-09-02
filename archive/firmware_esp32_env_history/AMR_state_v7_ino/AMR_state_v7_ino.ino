/*
 * File: AMR_state_v7.ino
 * Target Board: ESP32 #1 (AMR)
 *
 * Purpose:
 * - MQ-135 가스 센서와 KY-026 불꽃 센서를 읽는다.
 * - 센서값을 안정화한 뒤 SAFE / WARNING / DANGER / STOP 상태를 판단한다.
 * - RPi 5가 읽을 수 있도록 정해진 메시지 형식으로 상태와 센서값을 전송한다.
 *
 * v7 Features:
 * 1. 센서값 포함 메시지
 * 2. Heartbeat 주기 송신
 * 3. 센서 이상 감지
 * 4. 상태 흔들림 방지
 *
 * Important System Rule:
 * - 이 코드는 ESP32 #1 AMR 전용 코드이다.
 * - ESP32 #2 ARM의 서보, 그리퍼, 출력장치 로직과 섞지 않는다.
 * - ESP32끼리 직접 통신하지 않는다.
 * - RPi 5가 전체 시스템의 중재자 역할을 한다.
 *
 * Message Format:
 *   <STATE,STATE_VALUE,GAS=gasValue,FLAME=flameValue,BAT=batteryVoltage,CS>
 *
 * Example:
 *   <STATE,SAFE,GAS=42,FLAME=0,BAT=12.00,5A>
 *
 * Checksum Rule:
 * - '<' 와 '>' 는 제외한다.
 * - 마지막 checksum 필드도 제외한다.
 * - 즉, "STATE,SAFE,GAS=42,FLAME=0,BAT=12.00" 문자열만 XOR 계산한다.
 */

#include <Arduino.h>

// ======================================================
// Pin Settings
// ======================================================

const int MQ135_PIN = 34;
const int FLAME_PIN = 27;
const int EMERGENCY_STOP_PIN = 26;

// ======================================================
// Sensor Threshold Settings
// ======================================================

// MQ-135 WARNING 진입 기준
const int GAS_WARNING_ENTER_THRESHOLD = 1400;

// MQ-135 WARNING 해제 기준
// 진입 기준보다 낮게 설정해서 상태가 흔들리는 것을 방지한다.
const int GAS_WARNING_EXIT_THRESHOLD = 1350;

// MQ-135 DANGER 진입 기준
const int GAS_DANGER_ENTER_THRESHOLD = 1500;

// MQ-135 DANGER 해제 기준
const int GAS_DANGER_EXIT_THRESHOLD = 1450;

// MQ-135 센서값 정상 범위
// ESP32 analogRead는 보통 0~4095 범위이다.
const int GAS_MIN_VALID_VALUE = 1;
const int GAS_MAX_VALID_VALUE = 4094;

// ======================================================
// Filtering Settings
// ======================================================

const int SAMPLE_COUNT = 10;
const int READ_INTERVAL_MS = 300;

// DANGER 조건이 몇 번 연속 감지되어야 실제 DANGER로 인정할지 결정
const int DANGER_COUNT_THRESHOLD = 3;

// 센서 이상이 몇 번 연속 발생해야 STOP 처리할지 결정
const int SENSOR_ERROR_COUNT_THRESHOLD = 3;

// ======================================================
// Heartbeat Settings
// ======================================================

// 상태 변화가 없어도 이 주기마다 현재 상태를 RPi로 다시 전송한다.
const unsigned long HEARTBEAT_INTERVAL_MS = 1000;
const unsigned long RPI_TIMEOUT_MS = 3000;
const int RPI_RX_BUFFER_MAX_LENGTH = 80;

// ======================================================
// Battery Safety Settings
// ======================================================

// 3S LiPo cutoff 기준
const float LIPO_CUTOFF_VOLTAGE = 9.9;

// 현재는 전압 측정 회로가 없을 수 있으므로 임시값을 사용한다.
// 나중에 전압 분배 회로를 연결하면 analogRead 기반 함수로 교체하면 된다.
float currentBatteryVoltage = 12.0;

// ======================================================
// State Definition
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

// ======================================================
// Global Variables
// ======================================================

int gasSamples[SAMPLE_COUNT];
int sampleIndex = 0;
long gasSum = 0;

int dangerCount = 0;
int sensorErrorCount = 0;

AmrState previousState = STATE_SAFE;
AmrState currentState = STATE_SAFE;

unsigned long lastReadTime = 0;
unsigned long lastHeartbeatTime = 0;
unsigned long lastRpiMessageTime = 0;

String rpiRxBuffer = "";

// ======================================================
// Function Declarations
// ======================================================

int readGasAverage();
bool isFlameDetected();
bool isGasSensorValid(int gasAverage);
bool isEmergencyStopActive();
void updateRpiCommunication();
bool isValidRpiMessage(const String& message);
bool isHexPair(const String& text);
bool isRpiTimeoutActive(unsigned long now);
AmrAction determineAmrAction(AmrState state);
void applyAmrAction(AmrAction action);
String actionToString(AmrAction action);

AmrState evaluateAmrState(
  int gasAverage,
  bool flameDetected,
  bool gasSensorValid,
  float batteryVoltage,
  bool emergencyStopActive,
  bool rpiTimeoutActive,
  AmrState lastState
);

String stateToString(AmrState state);
byte calculateChecksum(const String& payload);
String buildStatePayload(
  AmrState state,
  int gasAverage,
  bool flameDetected,
  float batteryVoltage
);

void sendStateMessage(
  AmrState state,
  int gasAverage,
  bool flameDetected,
  float batteryVoltage
);

void printDebugInfo(
  int gasAverage,
  bool flameDetected,
  bool gasSensorValid,
  AmrState state,
  AmrAction action
);

// ======================================================
// Setup
// ======================================================

void setup() {
  Serial.begin(115200);
  delay(1000);

  pinMode(MQ135_PIN, INPUT);
  pinMode(FLAME_PIN, INPUT);
  pinMode(EMERGENCY_STOP_PIN, INPUT_PULLUP);

  for (int i = 0; i < SAMPLE_COUNT; i++) {
    gasSamples[i] = 0;
  }

  Serial.println("AMR_state_v7 start");
  Serial.println("Target: ESP32 #1 AMR");
  Serial.println("Features: sensor values, heartbeat, sensor error check, hysteresis");

  lastRpiMessageTime = millis();
  sendStateMessage(STATE_SAFE, 0, false, currentBatteryVoltage);
}

// ======================================================
// Main Loop
// ======================================================

void loop() {
  unsigned long now = millis();
  updateRpiCommunication();

  if (now - lastReadTime >= READ_INTERVAL_MS) {
    lastReadTime = now;

    int gasAverage = readGasAverage();
    bool flameDetected = isFlameDetected();
    bool gasSensorValid = isGasSensorValid(gasAverage);
    bool emergencyStopActive = isEmergencyStopActive();
    bool rpiTimeoutActive = isRpiTimeoutActive(now);

    currentState = evaluateAmrState(
      gasAverage,
      flameDetected,
      gasSensorValid,
      currentBatteryVoltage,
      emergencyStopActive,
      rpiTimeoutActive,
      previousState
    );

    AmrAction currentAction = determineAmrAction(currentState);
    applyAmrAction(currentAction);

    // 상태가 바뀌면 즉시 RPi로 전송한다.
    if (currentState != previousState) {
      sendStateMessage(
        currentState,
        gasAverage,
        flameDetected,
        currentBatteryVoltage
      );

      previousState = currentState;
      lastHeartbeatTime = now;
    }

    // 상태 변화가 없어도 heartbeat 주기마다 현재 상태를 재전송한다.
    if (now - lastHeartbeatTime >= HEARTBEAT_INTERVAL_MS) {
      sendStateMessage(
        currentState,
        gasAverage,
        flameDetected,
        currentBatteryVoltage
      );

      lastHeartbeatTime = now;
    }

    printDebugInfo(gasAverage, flameDetected, gasSensorValid, currentState, currentAction);
  }
}

// ======================================================
// Sensor Reading
// ======================================================

int readGasAverage() {
  int gasRaw = analogRead(MQ135_PIN);

  gasSum -= gasSamples[sampleIndex];
  gasSamples[sampleIndex] = gasRaw;
  gasSum += gasRaw;

  sampleIndex = (sampleIndex + 1) % SAMPLE_COUNT;

  return gasSum / SAMPLE_COUNT;
}

bool isFlameDetected() {
  int flameValue = digitalRead(FLAME_PIN);

  // KY-026은 보통 불꽃 감지 시 LOW가 출력된다.
  // 현재 v5/v6 흐름을 유지해서 LOW를 감지 상태로 본다.
  return flameValue == LOW;
}

bool isGasSensorValid(int gasAverage) {
  // MQ-135 값이 0이나 4095에 계속 붙어 있으면
  // 단선, 배선 문제, 센서 이상, ADC 입력 문제 가능성이 있다.
  bool valid = (
    gasAverage >= GAS_MIN_VALID_VALUE &&
    gasAverage <= GAS_MAX_VALID_VALUE
  );

  if (valid) {
    sensorErrorCount = 0;
  } else {
    sensorErrorCount++;
  }

  return sensorErrorCount < SENSOR_ERROR_COUNT_THRESHOLD;
}

bool isEmergencyStopActive() {
  return digitalRead(EMERGENCY_STOP_PIN) == LOW;
}

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
      if (isValidRpiMessage(rpiRxBuffer)) {
        lastRpiMessageTime = millis();
      }

      rpiRxBuffer = "";
    }
  }
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

  if (!isHexPair(checksumText)) {
    return false;
  }

  byte expectedChecksum = strtoul(checksumText.c_str(), nullptr, 16);

  return calculateChecksum(payload) == expectedChecksum;
}

bool isHexPair(const String& text) {
  if (text.length() != 2) {
    return false;
  }

  for (int i = 0; i < text.length(); i++) {
    char value = text[i];
    bool isDigit = value >= '0' && value <= '9';
    bool isUpperHex = value >= 'A' && value <= 'F';
    bool isLowerHex = value >= 'a' && value <= 'f';

    if (!isDigit && !isUpperHex && !isLowerHex) {
      return false;
    }
  }

  return true;
}

bool isRpiTimeoutActive(unsigned long now) {
  return now - lastRpiMessageTime >= RPI_TIMEOUT_MS;
}

// ======================================================
// State Evaluation
// ======================================================

AmrState evaluateAmrState(
  int gasAverage,
  bool flameDetected,
  bool gasSensorValid,
  float batteryVoltage,
  bool emergencyStopActive,
  bool rpiTimeoutActive,
  AmrState lastState
) {
  if (emergencyStopActive) {
    return STATE_STOP;
  }

  // 1. 배터리 cutoff는 최우선 안전 조건이다.
  if (batteryVoltage <= LIPO_CUTOFF_VOLTAGE) {
    return STATE_STOP;
  }

  // 2. 센서 이상도 안전상 STOP으로 보낸다.
  // 잘못된 센서값으로 주행 판단을 계속하는 것보다 정지가 안전하다.
  if (!gasSensorValid) {
    return STATE_SENSOR_ERROR;
  }

  if (rpiTimeoutActive) {
    return STATE_STOP;
  }

  // 3. DANGER 조건 판단
  bool dangerEnterCondition = (
    flameDetected ||
    gasAverage >= GAS_DANGER_ENTER_THRESHOLD
  );

  bool dangerStayCondition = (
    flameDetected ||
    gasAverage >= GAS_DANGER_EXIT_THRESHOLD
  );

  if (lastState == STATE_DANGER) {
    if (dangerStayCondition) {
      return STATE_DANGER;
    }

    dangerCount = 0;
  }

  if (dangerEnterCondition) {
    dangerCount++;
  } else {
    dangerCount = 0;
  }

  if (dangerCount >= DANGER_COUNT_THRESHOLD) {
    return STATE_DANGER;
  }

  // 4. WARNING 조건 판단
  // WARNING도 진입 기준과 해제 기준을 분리해 상태 흔들림을 줄인다.
  if (lastState == STATE_WARNING) {
    if (gasAverage >= GAS_WARNING_EXIT_THRESHOLD) {
      return STATE_WARNING;
    }
  }

  if (gasAverage >= GAS_WARNING_ENTER_THRESHOLD) {
    return STATE_WARNING;
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

void applyAmrAction(AmrAction action) {
  switch (action) {
    case ACTION_NORMAL_MOTION:
    case ACTION_LIMITED_MOTION:
    case ACTION_STOP_MOTION:
    default:
      break;
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

byte calculateChecksum(const String& payload) {
  byte checksum = 0;

  for (int i = 0; i < payload.length(); i++) {
    checksum ^= payload[i];
  }

  return checksum;
}

String buildStatePayload(
  AmrState state,
  int gasAverage,
  bool flameDetected,
  float batteryVoltage
) {
  String payload = "CMD,STATE=";
  payload += stateToString(state);

  payload += ",GAS=";
  payload += String(gasAverage);

  payload += ",FLAME=";
  payload += String(flameDetected ? 1 : 0);

  payload += ",BAT=";
  payload += String(batteryVoltage, 2);

  return payload;
}

void sendStateMessage(
  AmrState state,
  int gasAverage,
  bool flameDetected,
  float batteryVoltage
) {
  String payload = buildStatePayload(
    state,
    gasAverage,
    flameDetected,
    batteryVoltage
  );

  byte checksum = calculateChecksum(payload);

  char checksumText[3];
  snprintf(checksumText, sizeof(checksumText), "%02X", checksum);

  Serial.print("<");
  Serial.print(payload);
  Serial.print(",");
  Serial.print(checksumText);
  Serial.println(">");
}

// ======================================================
// Debug Output
// ======================================================

void printDebugInfo(
  int gasAverage,
  bool flameDetected,
  bool gasSensorValid,
  AmrState state,
  AmrAction action
) {
  Serial.print("[DEBUG] GAS=");
  Serial.print(gasAverage);

  Serial.print(" | FLAME=");
  Serial.print(flameDetected ? "YES" : "NO");

  Serial.print(" | GAS_SENSOR=");
  Serial.print(gasSensorValid ? "OK" : "ERROR");

  Serial.print(" | DANGER_COUNT=");
  Serial.print(dangerCount);

  Serial.print(" | SENSOR_ERROR_COUNT=");
  Serial.print(sensorErrorCount);

  Serial.print(" | BAT=");
  Serial.print(currentBatteryVoltage, 2);
  Serial.print("V");

  Serial.print(" | STATE=");
  Serial.print(stateToString(state));

  Serial.print(" | ACTION=");
  Serial.println(actionToString(action));
}
