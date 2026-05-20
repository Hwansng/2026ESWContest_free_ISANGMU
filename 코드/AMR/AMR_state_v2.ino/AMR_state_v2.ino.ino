/*
 * File: AMR_state_v2.ino
 *
 * Description:
 * 센서 상태 변화(Event) 감지 시스템
 *
 * Key Features:
 * 1. Moving Average → 노이즈 제거
 * 2. Persistence Filter → 지속 조건
 * 3. Event Trigger → 상태 변화 순간만 감지
 *
 * 핵심:
 * “상태가 바뀌는 순간만 출력”
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

String prevState = "SAFE";  // 이전 상태 저장

void setup() {
  Serial.begin(115200);
  delay(1000);

  pinMode(FLAME_PIN, INPUT);

  for (int i = 0; i < SAMPLE_COUNT; i++) {
    gasSamples[i] = 0;
  }

  Serial.println("AMR_state_v2 start");
}

void loop() {
  int gasRaw = analogRead(MQ135_PIN);
  int flameValue = digitalRead(FLAME_PIN);

  // Moving average
  gasSum -= gasSamples[sampleIndex];
  gasSamples[sampleIndex] = gasRaw;
  gasSum += gasRaw;
  sampleIndex = (sampleIndex + 1) % SAMPLE_COUNT;

  int gasAverage = gasSum / SAMPLE_COUNT;

  // Danger condition
  bool dangerNow = (flameValue == 0) || (gasAverage > GAS_DANGER);

  if (dangerNow) {
    dangerCount++;
  } else {
    dangerCount = 0;
  }

  // Current state
  String currentState = "SAFE";

  if (dangerCount >= DANGER_COUNT_THRESHOLD) {
    currentState = "DANGER";
  } else if (gasAverage > GAS_WARNING) {
    currentState = "WARNING";
  }

  // 🔥 핵심: 상태 변화 감지
  if (currentState != prevState) {
    Serial.print("STATE CHANGE: ");
    Serial.print(prevState);
    Serial.print(" → ");
    Serial.println(currentState);

    prevState = currentState;
  }

  delay(READ_DELAY_MS);
}