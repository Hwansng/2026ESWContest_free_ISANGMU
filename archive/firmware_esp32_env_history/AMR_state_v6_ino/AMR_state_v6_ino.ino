/*
 * File: AMR_state_v6.ino
 * Target: ESP32 #1 (AMR)
 *
 * Role:
 * - MQ-135 가스 센서와 KY-026 불꽃 센서를 읽는다.
 * - 센서값을 기반으로 AMR 상태를 SAFE / WARNING / DANGER / STOP으로 판단한다.
 * - RPi 5가 읽을 수 있는 표준 메시지 형식으로 상태를 전송한다.
 *
 * Important:
 * - 이 코드는 ESP32 #1 AMR 전용 코드이다.
 * - ESP32 #2 ARM의 서보, 그리퍼, 출력장치 로직과 절대 섞지 않는다.
 * - RPi가 전체 시스템을 중재하므로 ESP32끼리 직접 통신하지 않는다.
 *
 * Message Format:
 *   <STATE,VALUE,CS>
 *
 * Example:
 *   <STATE,SAFE,1A>
 *   <STATE,WARNING,4F>
 *   <STATE,DANGER,5A>
 *   <STATE,STOP,3C>
 *
 * Checksum Rule:
 * - '<' 와 '>' 는 제외한다.
 * - "STATE,VALUE" 문자열만 XOR 계산한다.
 *
 * System Flow:
 * Sensor Input
 *   → Moving Average Filtering
 *   → Persistence Filter
 *   → Safety Check
 *   → State Decision
 *   → Checksum
 *   → Serial Message Output
 */

#include <Arduino.h>

// ======================================================
// Pin Settings
// ======================================================

// MQ-135 가스 센서 아날로그 입력 핀
const int MQ135_PIN = 34;

// KY-026 불꽃 센서 디지털 입력 핀
// 일반적으로 KY-026은 불꽃 감지 시 LOW(0)가 나오는 경우가 많다.
const int FLAME_PIN = 27;

// ======================================================
// Gas Sensor Threshold Settings
// ======================================================

// WARNING 기준값
// 실제 환경에서 MQ-135 값이 어느 정도 나오는지 보고 조정해야 한다.
const int GAS_WARNING_THRESHOLD = 50;

// DANGER 기준값
// 이 값 이상이 연속으로 감지되면 DANGER 후보가 된다.
const int GAS_DANGER_THRESHOLD = 100;

// ======================================================
// Filtering Settings
// ======================================================

// Moving Average에 사용할 샘플 개수
// 값이 클수록 안정적이지만 반응이 느려진다.
const int SAMPLE_COUNT = 10;

// 센서 읽기 주기
const int READ_DELAY_MS = 300;

// DANGER 조건이 몇 번 연속 감지되어야 실제 DANGER로 볼 것인지 결정
// 순간적인 노이즈 때문에 바로 DANGER가 되는 것을 방지한다.
const int DANGER_COUNT_THRESHOLD = 3;

// ======================================================
// Battery Safety Settings
// ======================================================

// 3S LiPo cutoff 기준
// 3S LiPo는 셀당 3.3V 기준으로 9.9V 이하가 되면 보호가 필요하다.
const float LIPO_CUTOFF_VOLTAGE = 9.9;

// 현재는 전압 측정 회로가 없을 수 있으므로 임시값을 사용한다.
// 나중에 전압 분배 회로를 연결하면 analogRead 기반으로 교체한다.
float currentBatteryVoltage = 12.0;

// ======================================================
// State Definition
// ======================================================

enum AmrState {
  STATE_SAFE,
  STATE_WARNING,
  STATE_DANGER,
  STATE_STOP
};

// ======================================================
// Global Variables for Moving Average
// ======================================================

int gasSamples[SAMPLE_COUNT];
int sampleIndex = 0;
long gasSum = 0;

// DANGER 조건이 연속으로 감지된 횟수
int dangerCount = 0;

// 이전 상태 저장
// 상태 변화가 있을 때만 RPi용 메시지를 보내기 위해 사용한다.
AmrState previousState = STATE_SAFE;

// ======================================================
// Function Declarations
// ======================================================

int readGasAverage();
bool isFlameDetected();
AmrState evaluateAmrState(int gasAverage, bool flameDetected, float batteryVoltage);

String stateToString(AmrState state);
byte calculateChecksum(const String& payload);
void printChecksum(byte checksum);
void sendStateMessage(AmrState state);

void printDebugInfo(int gasAverage, bool flameDetected, AmrState currentState);
void handleStateChange(AmrState currentState);

// ======================================================
// Setup
// ======================================================

void setup() {
  Serial.begin(115200);
  delay(1000);

  pinMode(MQ135_PIN, INPUT);
  pinMode(FLAME_PIN, INPUT);

  // Moving Average 배열 초기화
  for (int i = 0; i < SAMPLE_COUNT; i++) {
    gasSamples[i] = 0;
  }

  Serial.println("AMR_state_v6 start");
  Serial.println("Target: ESP32 #1 AMR");
  Serial.println("Sensors: MQ-135 + KY-026");

  // 시작 시 기본 상태를 RPi에 알린다.
  sendStateMessage(STATE_SAFE);
}

// ======================================================
// Main Loop
// ======================================================

void loop() {
  // 1. 센서값 읽기
  int gasAverage = readGasAverage();
  bool flameDetected = isFlameDetected();

  // 2. 센서값과 안전 조건을 기반으로 현재 상태 판단
  AmrState currentState = evaluateAmrState(
    gasAverage,
    flameDetected,
    currentBatteryVoltage
  );

  // 3. 상태가 바뀐 경우에만 RPi용 상태 메시지 송신
  if (currentState != previousState) {
    handleStateChange(currentState);
    previousState = currentState;
  }

  // 4. 사람이 확인하기 위한 디버그 출력
  printDebugInfo(gasAverage, flameDetected, currentState);

  delay(READ_DELAY_MS);
}

// ======================================================
// Sensor Reading Functions
// ======================================================

int readGasAverage() {
  int gasRaw = analogRead(MQ135_PIN);

  // 기존 샘플 제거
  gasSum -= gasSamples[sampleIndex];

  // 새 샘플 저장
  gasSamples[sampleIndex] = gasRaw;

  // 새 샘플 반영
  gasSum += gasRaw;

  // 다음 위치로 이동
  sampleIndex = (sampleIndex + 1) % SAMPLE_COUNT;

  // 평균값 반환
  return gasSum / SAMPLE_COUNT;
}

bool isFlameDetected() {
  int flameValue = digitalRead(FLAME_PIN);

  // KY-026은 모듈에 따라 불꽃 감지 시 LOW가 나오는 경우가 많다.
  // 현재 v5 코드 기준 flameValue == 0을 불꽃 감지로 유지한다.
  return flameValue == LOW;
}

// ======================================================
// State Evaluation
// ======================================================

AmrState evaluateAmrState(int gasAverage, bool flameDetected, float batteryVoltage) {
  // 최우선 안전 조건
  // 배터리 전압이 cutoff 이하라면 센서 상태와 관계없이 STOP으로 전환한다.
  if (batteryVoltage <= LIPO_CUTOFF_VOLTAGE) {
    return STATE_STOP;
  }

  // DANGER 후보 조건
  // 불꽃이 감지되거나 가스 평균값이 DANGER 기준을 넘으면 위험 후보로 본다.
  bool dangerNow = flameDetected || (gasAverage > GAS_DANGER_THRESHOLD);

  if (dangerNow) {
    dangerCount++;
  } else {
    dangerCount = 0;
  }

  // DANGER 조건이 연속으로 일정 횟수 이상 감지되어야 실제 DANGER로 판단한다.
  if (dangerCount >= DANGER_COUNT_THRESHOLD) {
    return STATE_DANGER;
  }

  // WARNING 조건
  // 가스값이 WARNING 이상이지만 DANGER 확정 전이면 WARNING으로 판단한다.
  if (gasAverage > GAS_WARNING_THRESHOLD) {
    return STATE_WARNING;
  }

  return STATE_SAFE;
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

    default:
      return "UNKNOWN";
  }
}

byte calculateChecksum(const String& payload) {
  byte checksum = 0;

  // payload의 각 문자를 ASCII 값 기준으로 XOR 누적한다.
  for (int i = 0; i < payload.length(); i++) {
    checksum ^= payload[i];
  }

  return checksum;
}

void printChecksum(byte checksum) {
  // checksum은 항상 16진수 2자리로 출력한다.
  // 예: A가 아니라 0A
  if (checksum < 0x10) {
    Serial.print("0");
  }

  Serial.print(checksum, HEX);
}

void sendStateMessage(AmrState state) {
  String stateText = stateToString(state);
  String payload = "STATE," + stateText;
  byte checksum = calculateChecksum(payload);

  Serial.print("<");
  Serial.print(payload);
  Serial.print(",");
  printChecksum(checksum);
  Serial.println(">");
}

// ======================================================
// State Change Handler
// ======================================================

void handleStateChange(AmrState currentState) {
  Serial.print("STATE CHANGE: ");
  Serial.print(stateToString(previousState));
  Serial.print(" -> ");
  Serial.println(stateToString(currentState));

  if (currentState == STATE_SAFE) {
    Serial.println("[ACTION] SAFE: monitoring normally");
  } else if (currentState == STATE_WARNING) {
    Serial.println("[ACTION] WARNING: caution level detected");
  } else if (currentState == STATE_DANGER) {
    Serial.println("[ACTION] DANGER: emergency condition detected");
  } else if (currentState == STATE_STOP) {
    Serial.println("[ACTION] STOP: safety cutoff activated");
  }

  sendStateMessage(currentState);
}

// ======================================================
// Debug Output
// ======================================================

void printDebugInfo(int gasAverage, bool flameDetected, AmrState currentState) {
  Serial.print("Gas avg: ");
  Serial.print(gasAverage);

  Serial.print(" | Flame detected: ");
  Serial.print(flameDetected ? "YES" : "NO");

  Serial.print(" | Danger count: ");
  Serial.print(dangerCount);

  Serial.print(" | Battery: ");
  Serial.print(currentBatteryVoltage);
  Serial.print("V");

  Serial.print(" | State: ");
  Serial.println(stateToString(currentState));
}