/*
 * File: AMR_state_v9_ino.ino
 * Target Board: ESP32 sensor-only bench
 *
 * Purpose:
 * - Read MQ-135, MQ-2, and KY-026 sensors together.
 * - Calibrate each MQ channel against its own clean-air baseline.
 * - Evaluate a fail-safe AMR hazard state.
 * - Send compact SENS telemetry to Raspberry Pi 5.
 *
 * Scope:
 * - Sensor-only ESP32 bench validation.
 * - No motor, TB6612, line tracing, ARM, servo, or gripper logic.
 * - No VL53L1X distance sensor code or telemetry.
 * - Battery voltage is a test injection until a divider is connected.
 *
 * RPi Message Format:
 *   <SENS,mq135,mq2,flame,battCv,stateCode,actionCode,faultCode,checksum>
 *
 * checksum is the decimal ASCII sum of the payload modulo 256.
 */

#include <Arduino.h>

// ======================================================
// Pin Settings
// ======================================================

const int MQ135_PIN = 34;
const int MQ2_PIN = 35;
const int FLAME_PIN = 27;
const int EMERGENCY_STOP_PIN = 26;

// ======================================================
// Sensor and Calibration Settings
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

// Bench test injection only. This is not a measured battery voltage.
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
// MQ Channel Definition
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

MqChannel mq135Channel;
MqChannel mq2Channel;

// ======================================================
// Global Variables
// ======================================================

int dangerCount = 0;

AmrState previousState = STATE_SENSOR_ERROR;
AmrState currentState = STATE_SENSOR_ERROR;

unsigned long lastReadTime = 0;
unsigned long lastHeartbeatTime = 0;
unsigned long lastRpiMessageTime = 0;

String rpiRxBuffer = "";

// ======================================================
// Function Declarations
// ======================================================

void initializeMqChannel(MqChannel& channel, int pin);
void updateMqChannel(MqChannel& channel, unsigned long now);
bool isMqChannelReady(const MqChannel& channel);
int calculateRisePercent(const MqChannel& channel);
bool isFlameDetected();
bool isEmergencyStopActive();

void updateRpiCommunication();
bool isValidRpiMessage(const String& message);
bool isDecimalChecksum(const String& text);
bool isRpiTimeoutActive(unsigned long now);

AmrState evaluateAmrState(
  int mq135RisePercent,
  int mq2RisePercent,
  bool flameDetected,
  bool mq135Ready,
  bool mq2Ready,
  float batteryVoltage,
  bool emergencyStopActive,
  bool rpiTimeoutActive,
  AmrState lastState
);

AmrAction determineAmrAction(AmrState state);

SafetyFault determineSafetyFault(
  AmrState state,
  bool flameDetected,
  bool mq135Ready,
  bool mq2Ready,
  float batteryVoltage,
  bool emergencyStopActive,
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
  int mq135Average,
  int mq2Average,
  int mq135RisePercent,
  int mq2RisePercent,
  bool flameDetected,
  bool mq135Ready,
  bool mq2Ready,
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
  pinMode(MQ2_PIN, INPUT);
  pinMode(FLAME_PIN, INPUT);
  pinMode(EMERGENCY_STOP_PIN, INPUT_PULLUP);

  initializeMqChannel(mq135Channel, MQ135_PIN);
  initializeMqChannel(mq2Channel, MQ2_PIN);

  Serial.println("AMR_state_v9 start");
  Serial.println("Target: ESP32 sensor-only bench");
  Serial.println("Active sensors: MQ-135, MQ-2, KY-026");
  Serial.println("Battery: TEST VALUE ONLY (not measured)");
  Serial.println("Protocol: <SENS,mq135,mq2,flame,battCv,stateCode,actionCode,faultCode,checksum>");

  lastRpiMessageTime = millis();
  sendSensorMessage(
    STATE_SENSOR_ERROR,
    ACTION_STOP_MOTION,
    FAULT_SENSOR,
    0,
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

  if (now - lastReadTime < READ_INTERVAL_MS) {
    return;
  }

  lastReadTime = now;

  updateMqChannel(mq135Channel, now);
  updateMqChannel(mq2Channel, now);

  int mq135Average = mq135Channel.average;
  int mq2Average = mq2Channel.average;
  int mq135RisePercent = calculateRisePercent(mq135Channel);
  int mq2RisePercent = calculateRisePercent(mq2Channel);
  bool mq135Ready = isMqChannelReady(mq135Channel);
  bool mq2Ready = isMqChannelReady(mq2Channel);
  bool flameDetected = isFlameDetected();
  bool emergencyStopActive = isEmergencyStopActive();
  bool rpiTimeoutActive = isRpiTimeoutActive(now);

  currentState = evaluateAmrState(
    mq135RisePercent,
    mq2RisePercent,
    flameDetected,
    mq135Ready,
    mq2Ready,
    currentBatteryVoltage,
    emergencyStopActive,
    rpiTimeoutActive,
    previousState
  );

  AmrAction currentAction = determineAmrAction(currentState);
  SafetyFault currentFault = determineSafetyFault(
    currentState,
    flameDetected,
    mq135Ready,
    mq2Ready,
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
      mq135Average,
      mq2Average,
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
      mq135Average,
      mq2Average,
      flameDetected,
      currentBatteryVoltage
    );

    lastHeartbeatTime = now;
  }

  printDebugInfo(
    mq135Average,
    mq2Average,
    mq135RisePercent,
    mq2RisePercent,
    flameDetected,
    mq135Ready,
    mq2Ready,
    currentState,
    currentAction,
    currentFault
  );
}

// ======================================================
// Sensor Reading and Calibration
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

  return (
    (channel.average - channel.baseline) * 100 /
    channel.baseline
  );
}

bool isFlameDetected() {
  return digitalRead(FLAME_PIN) == LOW;
}

bool isEmergencyStopActive() {
  return digitalRead(EMERGENCY_STOP_PIN) == LOW;
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
// State Evaluation
// ======================================================

AmrState evaluateAmrState(
  int mq135RisePercent,
  int mq2RisePercent,
  bool flameDetected,
  bool mq135Ready,
  bool mq2Ready,
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

  if (!mq135Ready || !mq2Ready) {
    return STATE_SENSOR_ERROR;
  }

  if (rpiTimeoutActive) {
    return STATE_STOP;
  }

  if (flameDetected) {
    dangerCount = 0;
    return STATE_DANGER;
  }

  bool dangerEnterCondition = (
    mq135RisePercent >= DANGER_ENTER_PERCENT ||
    mq2RisePercent >= DANGER_ENTER_PERCENT
  );

  bool dangerStayCondition = (
    mq135RisePercent >= DANGER_EXIT_PERCENT ||
    mq2RisePercent >= DANGER_EXIT_PERCENT
  );

  bool warningEnterCondition = (
    mq135RisePercent >= WARNING_ENTER_PERCENT ||
    mq2RisePercent >= WARNING_ENTER_PERCENT
  );

  bool warningStayCondition = (
    mq135RisePercent >= WARNING_EXIT_PERCENT ||
    mq2RisePercent >= WARNING_EXIT_PERCENT
  );

  if (lastState == STATE_DANGER && dangerStayCondition) {
    return STATE_DANGER;
  }

  if (lastState == STATE_DANGER) {
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

  if (lastState == STATE_WARNING && warningStayCondition) {
    return STATE_WARNING;
  }

  if (warningEnterCondition) {
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
  bool mq135Ready,
  bool mq2Ready,
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

  if (!mq135Ready || !mq2Ready) {
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
  // Sensor-only bench: retain the safe state-to-action hook without motors.
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

  Serial.print("<");
  Serial.print(payload);
  Serial.print(",");
  Serial.print(calculateChecksum(payload));
  Serial.println(">");
}

// ======================================================
// Debug Output
// ======================================================

void printDebugInfo(
  int mq135Average,
  int mq2Average,
  int mq135RisePercent,
  int mq2RisePercent,
  bool flameDetected,
  bool mq135Ready,
  bool mq2Ready,
  AmrState state,
  AmrAction action,
  SafetyFault fault
) {
  Serial.print("[DEBUG] MQ135=");
  Serial.print(mq135Average);
  Serial.print(" | MQ135_BASE=");
  Serial.print(mq135Channel.baseline);
  Serial.print(" | MQ135_RISE=");
  Serial.print(mq135RisePercent);
  Serial.print("% | MQ135_SENSOR=");
  Serial.print(mq135Ready ? "OK" : "ERROR");
  Serial.print(" | MQ135_ERROR_COUNT=");
  Serial.print(mq135Channel.errorCount);

  Serial.print(" | MQ2=");
  Serial.print(mq2Average);
  Serial.print(" | MQ2_BASE=");
  Serial.print(mq2Channel.baseline);
  Serial.print(" | MQ2_RISE=");
  Serial.print(mq2RisePercent);
  Serial.print("% | MQ2_SENSOR=");
  Serial.print(mq2Ready ? "OK" : "ERROR");
  Serial.print(" | MQ2_ERROR_COUNT=");
  Serial.print(mq2Channel.errorCount);

  Serial.print(" | FLAME=");
  Serial.print(flameDetected ? "YES" : "NO");
  Serial.print(" | CALIBRATION=");
  if (millis() < CALIBRATION_SETTLE_MS) {
    Serial.print("SETTLING");
  } else if (!mq135Channel.calibrated || !mq2Channel.calibrated) {
    Serial.print("CALIBRATING");
  } else {
    Serial.print("READY");
  }
  Serial.print(" | BAT_TEST_VALUE=");
  Serial.print(currentBatteryVoltage, 2);
  Serial.print("V | STATE=");
  Serial.print(stateToString(state));
  Serial.print(" | ACTION=");
  Serial.print(actionToString(action));
  Serial.print(" | FAULT=");
  Serial.println(faultToCode(fault));
}
