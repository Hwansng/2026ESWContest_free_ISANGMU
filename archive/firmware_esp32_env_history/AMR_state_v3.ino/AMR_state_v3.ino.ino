/*
 * File: AMR_state_v3.ino
 * Target: ESP32 #1 (AMR)
 *
 * Description:
 * MQ-135 가스 센서와 KY-026 불꽃 센서를 이용해
 * SAFE / WARNING / DANGER 상태를 판단하고,
 * 상태 변화가 발생할 때마다 상태별 행동 함수를 실행하는 코드.
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
 * 3. Event-based Action
 *    - 상태가 바뀌는 순간에만 handleSafe(), handleWarning(), handleDanger() 실행.
 *    - 나중에 LED, 부저, 모터 정지 명령을 이 함수 안에 추가하기 쉬움.
 *
 *
 * <정상 출력 예시>
 * STATE CHANGE: SAFE -> WARNING
 * [ACTION] WARNING: caution level detected
 *
 * STATE CHANGE: WARNING -> DANGER
 * [ACTION] DANGER: emergency condition detected
 *
 * STATE CHANGE: DANGER -> SAFE
 * [ACTION] SAFE: monitoring normally
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

void handleSafe() {
  Serial.println("[ACTION] SAFE: monitoring normally");
}

void handleWarning() {
  Serial.println("[ACTION] WARNING: caution level detected");
}

void handleDanger() {
  Serial.println("[ACTION] DANGER: emergency condition detected");
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  pinMode(FLAME_PIN, INPUT);

  for (int i = 0; i < SAMPLE_COUNT; i++) {
    gasSamples[i] = 0;
  }

  Serial.println("AMR_state_v3 start");
  Serial.println("[ACTION] SAFE: monitoring normally");
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

  Serial.print("Gas raw: ");
  Serial.print(gasRaw);
  Serial.print(" | Gas avg: ");
  Serial.print(gasAverage);
  Serial.print(" | Flame: ");
  Serial.print(flameValue);
  Serial.print(" | DangerCount: ");
  Serial.print(dangerCount);
  Serial.print(" | State: ");
  Serial.println(currentState);

  delay(READ_DELAY_MS);
}