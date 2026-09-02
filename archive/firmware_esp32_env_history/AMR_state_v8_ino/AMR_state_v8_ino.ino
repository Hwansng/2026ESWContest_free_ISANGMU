/*
 * File: AMR_state_v8_ino.ino
 * Target Board: ESP32 #1 (AMR)
 *
 * Purpose:
 * - Read MQ-135 gas and KY-026 flame sensors.
 * - Evaluate AMR safety state.
 * - Send compact SENS telemetry to Raspberry Pi 5.
 *
 * Scope:
 * - ESP32 #1 AMR only.
 * - No ESP32 #2 ARM, servo, gripper, or output-device logic.
 * - No direct ESP32-to-ESP32 communication.
 *
 * RPi Message Format:
 *   <SENS,gas,flame,battCv,stateCode,actionCode,faultCode,checksum>
 *
 * Fields:
 * - gas: MQ-135 averaged ADC value.
 * - flame: 1 when flame is detected, otherwise 0.
 * - battCv: battery voltage in centivolts. 12.00V becomes 1200.
 * - stateCode: SAFE=0, WARNING=1, DANGER=2, STOP=3, SENSOR_ERROR=4.
 * - actionCode: NORMAL_MOTION=0, LIMITED_MOTION=1, STOP_MOTION=2.
 * - faultCode: OK=0, ESTOP=1, LIPO=2, SENSOR=3, RPI_TIMEOUT=4, HAZARD=5.
 * - checksum: ASCII sum of payload modulo 256, decimal.
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

const int GAS_WARNING_ENTER_THRESHOLD = 1400;
const int GAS_WARNING_EXIT_THRESHOLD = 1350;
const int GAS_DANGER_ENTER_THRESHOLD = 1500;
const int GAS_DANGER_EXIT_THRESHOLD = 1450;
const int GAS_MIN_VALID_VALUE = 1;
const int GAS_MAX_VALID_VALUE = 4094;

// ======================================================
// Filtering Settings
// ======================================================

const int SAMPLE_COUNT = 10;
const int READ_INTERVAL_MS = 300;
const int DANGER_COUNT_THRESHOLD = 3;
const int SENSOR_ERROR_COUNT_THRESHOLD = 3;

// ======================================================
// Communication Settings
// ======================================================

const unsigned long HEARTBEAT_INTERVAL_MS = 1000;
const unsigned long RPI_TIMEOUT_MS = 3000;
const int RPI_RX_BUFFER_MAX_LENGTH = 80;

// ======================================================
// Battery Safety Settings
// ======================================================

const float LIPO_CUTOFF_VOLTAGE = 9.9;
const int CENTIVOLTS_PER_VOLT = 100;

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

enum SafetyFault {
  FAULT_OK,
  FAULT_ESTOP,
  FAULT_LIPO,
  FAULT_SENSOR,
  FAULT_RPI_TIMEOUT,
  FAULT_HAZARD
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
bool isDecimalChecksum(const String& text);
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

SafetyFault determineSafetyFault(
  AmrState state,
  bool flameDetected,
  bool gasSensorValid,
  float batteryVoltage,
  bool emergencyStopActive,
  bool rpiTimeoutActive
);

String stateToString(AmrState state);
int stateToCode(AmrState state);
int actionToCode(AmrAction action);
int faultToCode(SafetyFault fault);
int batteryToCentivolts(float batteryVoltage);
int calculateChecksum(const String& payload);
String buildSensorPayload(
  AmrState state,
  AmrAction action,
  SafetyFault fault,
  int gasAverage,
  bool flameDetected,
  float batteryVoltage
);

void sendSensorMessage(
  AmrState state,
  AmrAction action,
  SafetyFault fault,
  int gasAverage,
  bool flameDetected,
  float batteryVoltage
);

void printDebugInfo(
  int gasAverage,
  bool flameDetected,
  bool gasSensorValid,
  AmrState state,
  AmrAction action,
  SafetyFault fault
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

  Serial.println("AMR_state_v8 start");
  Serial.println("Target: ESP32 #1 AMR");
  Serial.println("Protocol: <SENS,gas,flame,battCv,stateCode,actionCode,faultCode,checksum>");

  lastRpiMessageTime = millis();
  sendSensorMessage(
    STATE_SAFE,
    ACTION_NORMAL_MOTION,
    FAULT_OK,
    0,
    false,
    currentBatteryVoltage
  );
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
    SafetyFault currentFault = determineSafetyFault(
      currentState,
      flameDetected,
      gasSensorValid,
      currentBatteryVoltage,
      emergencyStopActive,
      rpiTimeoutActive
    );

    applyAmrAction(currentAction);

    if (currentState != previousState) {
      sendSensorMessage(
        currentState,
        currentAction,
        currentFault,
        gasAverage,
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
        gasAverage,
        flameDetected,
        currentBatteryVoltage
      );

      lastHeartbeatTime = now;
    }

    printDebugInfo(
      gasAverage,
      flameDetected,
      gasSensorValid,
      currentState,
      currentAction,
      currentFault
    );
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
  return flameValue == LOW;
}

bool isGasSensorValid(int gasAverage) {
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

  if (!isDecimalChecksum(checksumText)) {
    return false;
  }

  int expectedChecksum = checksumText.toInt();

  return calculateChecksum(payload) == expectedChecksum;
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

  if (batteryVoltage <= LIPO_CUTOFF_VOLTAGE) {
    return STATE_STOP;
  }

  if (!gasSensorValid) {
    return STATE_SENSOR_ERROR;
  }

  if (rpiTimeoutActive) {
    return STATE_STOP;
  }

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

SafetyFault determineSafetyFault(
  AmrState state,
  bool flameDetected,
  bool gasSensorValid,
  float batteryVoltage,
  bool emergencyStopActive,
  bool rpiTimeoutActive
) {
  if (emergencyStopActive) {
    return FAULT_ESTOP;
  }

  if (batteryVoltage <= LIPO_CUTOFF_VOLTAGE) {
    return FAULT_LIPO;
  }

  if (!gasSensorValid) {
    return FAULT_SENSOR;
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

    case FAULT_ESTOP:
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

String buildSensorPayload(
  AmrState state,
  AmrAction action,
  SafetyFault fault,
  int gasAverage,
  bool flameDetected,
  float batteryVoltage
) {
  String payload = "SENS";

  payload += ",";
  payload += String(gasAverage);

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
  int gasAverage,
  bool flameDetected,
  float batteryVoltage
) {
  String payload = buildSensorPayload(
    state,
    action,
    fault,
    gasAverage,
    flameDetected,
    batteryVoltage
  );

  int checksum = calculateChecksum(payload);

  Serial.print("<");
  Serial.print(payload);
  Serial.print(",");
  Serial.print(checksum);
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
  AmrAction action,
  SafetyFault fault
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
  Serial.print(actionToString(action));

  Serial.print(" | FAULT=");
  Serial.println(faultToCode(fault));
}
