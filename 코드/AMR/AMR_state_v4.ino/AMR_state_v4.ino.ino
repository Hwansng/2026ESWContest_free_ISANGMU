/*
 * File: AMR_state_v4.ino
 * Target: ESP32 #1 (AMR)
 *
 * Description:
 * MQ-135 가스 센서와 KY-026 불꽃 센서를 이용해
 * SAFE / WARNING / DANGER 상태를 판단하고,
 * 상태 변화가 발생할 때마다 RPi가 읽을 수 있는 메시지 형식으로 출력하는 코드.
 *
 * Key Features:
 * 1. Moving Average
 *    - MQ-135 값의 순간 노이즈를 줄이기 위해 최근 SAMPLE_COUNT개의 평균 사용.
 *
 * 2. Persistence Filter
 *    - dangerCount는 위험 조건이 연속으로 감지된 횟수.
 *    - 한 번 튄 값은 바로 DANGER로 보지 않고,
 *      DANGER_COUNT_THRESHOLD 이상 연속 감지될 때 DANGER로 판단.
 *
 * 3. Event-based State Message
 *    - 상태가 바뀌는 순간에만 메시지 출력.
 *    - 불필요한 반복 전송을 줄이고, RPi가 상태 변화를 쉽게 감지할 수 있음.
 *
 * Message Format:
 *   <CMD,VALUE,CS>
 *
 * Example:
 *   <STATE,DANGER,00>
 *
 * Field Description:
 * 1. CMD
 *    - 메시지 종류
 *    - 현재는 "STATE" 사용
 *    - 의미: ESP32 #1이 판단한 현재 AMR 상태 전달
 *
 * 2. VALUE
 *    - 상태 값
 *    - SAFE    : 정상 상태
 *    - WARNING : 주의 상태
 *    - DANGER  : 위험 상태
 *
 * 3. CS
 *    - Checksum
 *    - 데이터 무결성 확인용 필드
 *    - 현재 v4에서는 테스트 단계이므로 "00" 고정값 사용
 *    - 추후 v5에서 XOR checksum으로 개선 가능
 *
 * Example Interpretation:
 *   <STATE,DANGER,00>
 *   → ESP32 #1이 현재 AMR 상태를 DANGER로 판단했음을 RPi에 전달
 *
 * System Flow:
 * Sensor Input → Filtering → State Decision → Event Detection → State Message Output
 */

#include <Arduino.h>

const int MQ135_PIN = 34;
const int FLAME_PIN = 27;

const int GAS_WARNING = 50;
const int GAS_DANGER = 100;

const int SAMPLE_COUNT = 10;
const int READ_DELAY_MS = 300;
const int DANGER_COUNT_THRESHOLD = 3;

int gasSamples[SAMPLE_COUNT];
int sampleIndex = 0;
long gasSum = 0;

int dangerCount = 0;
String previousState = "SAFE";

void sendStateMessage(String state) {
  // Send state message in <CMD,VALUE,CS> format.
  // Example: <STATE,WARNING,00>
  Serial.print("<STATE,");
  Serial.print(state);
  Serial.println(",00>");
}

void handleSafe() {
  Serial.println("[ACTION] SAFE: monitoring normally");
  sendStateMessage("SAFE");
}

void handleWarning() {
  Serial.println("[ACTION] WARNING: caution level detected");
  sendStateMessage("WARNING");
}

void handleDanger() {
  Serial.println("[ACTION] DANGER: emergency condition detected");
  sendStateMessage("DANGER");
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  pinMode(FLAME_PIN, INPUT);

  for (int i = 0; i < SAMPLE_COUNT; i++) {
    gasSamples[i] = 0;
  }

  Serial.println("AMR_state_v4 start");
  handleSafe();
}

void loop() {
  int gasRaw = analogRead(MQ135_PIN);
  int flameValue = digitalRead(FLAME_PIN);

  gasSum -= gasSamples[sampleIndex];
  gasSamples[sampleIndex] = gasRaw;
  gasSum += gasRaw;
  sampleIndex = (sampleIndex + 1) % SAMPLE_COUNT;

  int gasAverage = gasSum / SAMPLE_COUNT;

  bool dangerNow = (flameValue == 0) || (gasAverage > GAS_DANGER);

  if (dangerNow) {
    dangerCount++;
  } else {
    dangerCount = 0;
  }

  String currentState = "SAFE";

  if (dangerCount >= DANGER_COUNT_THRESHOLD) {
    currentState = "DANGER";
  } else if (gasAverage > GAS_WARNING) {
    currentState = "WARNING";
  }

  if (currentState != previousState) {
    Serial.print("STATE CHANGE: ");
    Serial.print(previousState);
    Serial.print(" -> ");
    Serial.println(currentState);

    if (currentState == "SAFE") {
      handleSafe();
    } else if (currentState == "WARNING") {
      handleWarning();
    } else if (currentState == "DANGER") {
      handleDanger();
    }

    previousState = currentState;
  }

  Serial.print("Gas avg: ");
  Serial.print(gasAverage);
  Serial.print(" | Flame: ");
  Serial.print(flameValue);
  Serial.print(" | Count: ");
  Serial.print(dangerCount);
  Serial.print(" | State: ");
  Serial.println(currentState);

  delay(READ_DELAY_MS);
}