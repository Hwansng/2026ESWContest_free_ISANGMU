/*
 * File: AMR_state_v5.ino
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
 *
 * 4. XOR Checksum
 *    - RPi가 수신 메시지의 무결성을 확인할 수 있도록 CS 값을 계산.
 *    - 메시지 본문("STATE,VALUE")을 문자 단위로 XOR하여 checksum 생성.
 *
 * Message Format:
 *   <CMD,VALUE,CS>
 *
 * Example:
 *   <STATE,DANGER,5A>
 *
 * Field Description:
 * 1. CMD
 *    - 메시지 종류
 *    - 현재는 "STATE" 사용
 *
 * 2. VALUE
 *    - SAFE    : 정상 상태
 *    - WARNING : 주의 상태
 *    - DANGER  : 위험 상태
 *
 * 3. CS
 *    - Checksum
 *    - "<"와 ">"는 제외하고, "STATE,VALUE" 문자열만 XOR 계산
 *    - 16진수 2자리로 출력
 *
 * System Flow:
 * Sensor Input → Filtering → State Decision → Event Detection → Checksum → Message Output




 /*
 * XOR Checksum Explanation
 *
 * 1. XOR 연산이란?
 *    - 두 비트를 비교해서 다르면 1, 같으면 0을 반환하는 연산
 *
 *    예:
 *      1 XOR 1 = 0
 *      0 XOR 0 = 0
 *      1 XOR 0 = 1
 *      0 XOR 1 = 1
 *
 * 2. 왜 XOR을 사용하는가?
 *    - 데이터 전송 중 오류(비트 변화)를 간단하게 검출하기 위해 사용
 *    - 계산이 매우 빠르고 구현이 쉬움 (임베디드에 적합)
 *
 * 3. 계산 방법
 *    - 문자열의 각 문자(ASCII 코드)를 하나씩 XOR
 *
 *    예:
 *      payload = "STATE,DANGER"
 *
 *      초기값: checksum = 0
 *
 *      checksum = 0 XOR 'S'
 *      checksum = 결과 XOR 'T'
 *      checksum = 결과 XOR 'A'
 *      ...
 *      checksum = 결과 XOR 'R'
 *
 *      → 최종 결과 = checksum
 *
 * 4. 실제 예시
 *
 *    payload: "STATE,DANGER"
 *
 *    ASCII 값:
 *      S = 83
 *      T = 84
 *      A = 65
 *      ...
 *
 *    XOR을 계속 누적하면:
 *
 *      checksum = 0 ^ 83 ^ 84 ^ 65 ^ ...
 *
 *    → 최종값 (예): 0x5A
 *
 *    최종 메시지:
 *
 *      <STATE,DANGER,5A>
 *
 * 5. 핵심 의미
 *
 *    - ESP32가 보낸 데이터와
 *      RPi가 받은 데이터를 같은 방식으로 XOR 계산했을 때
 *
 *    → 값이 같으면 정상
 *    → 다르면 데이터 손상 발생
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

byte calculateChecksum(String payload) {
  // payload 문자열의 각 문자를 XOR하여 checksum 계산
  byte checksum = 0;

  for (int i = 0; i < payload.length(); i++) {
    checksum ^= payload[i];
  }

  return checksum;
}

void printChecksum(byte checksum) {
  if (checksum < 0x10) {
    Serial.print("0");
  }
  Serial.print(checksum, HEX);
}

void sendStateMessage(String state) {
  String payload = "STATE," + state;
  byte checksum = calculateChecksum(payload);

  Serial.print("<");
  Serial.print(payload);
  Serial.print(",");
  printChecksum(checksum);
  Serial.println(">");
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

  Serial.println("AMR_state_v5 start");
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