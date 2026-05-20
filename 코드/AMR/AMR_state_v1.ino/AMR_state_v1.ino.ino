/*
 * Target: ESP32 #1 (AMR)
 * File: HazardBot_AMR_sensor_decision_v2.ino
 *
 * Description:
 * MQ-135 (가스 센서) + KY-026 (불꽃 센서)를 이용한
 * 3단계 위험 판단 시스템 (SAFE / WARNING / DANGER)
 *
 * Key Features (핵심 차별점):
 * 1. Moving Average (이동 평균)
 *    → 센서 노이즈 제거, 값 안정화
 *
 * 2. Persistence Filter (지속 조건)
 * 목적:
 *  - 센서 값이 순간적으로 튀는 경우를 제거하기 위함
 *
 * 동작 방식:
 *  - 위험 조건(dangerNow)이 참일 때마다 dangerCount 증가
 *  - 조건이 거짓이면 dangerCount 초기화
 *
 * 판단 기준:
 *  - dangerCount가 일정 값(DANGER_COUNT_THRESHOLD) 이상이면
 *    → “지속적인 위험 상태”로 판단 → DANGER 상태 전환
 *
 * 핵심:
 *  - “한 번 튀는 건 무시, 여러 번 연속이면 진짜 위험”
 *
 *
 * 3. Multi-level Decision (3단계 판단)
 *    → SAFE / WARNING / DANGER
 *
 * System Flow:
 * Sensor Input → Filtering → Decision → Output (Serial)
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

void setup() {
  Serial.begin(115200);
  delay(1000);

  pinMode(FLAME_PIN, INPUT);

  for (int i = 0; i < SAMPLE_COUNT; i++) {
    gasSamples[i] = 0;
  }

  Serial.println("HazardBot Decision System Start");
}

void loop() {
  int gasRaw = analogRead(MQ135_PIN);
  int flameValue = digitalRead(FLAME_PIN);

  // Moving average update
  gasSum -= gasSamples[sampleIndex];
  gasSamples[sampleIndex] = gasRaw;
  gasSum += gasRaw;
  sampleIndex = (sampleIndex + 1) % SAMPLE_COUNT;

  int gasAverage = gasSum / SAMPLE_COUNT;

  // Danger condition (instant)
  bool dangerNow = (flameValue == 0) || (gasAverage > GAS_DANGER);

  // Persistence filter
  if (dangerNow) {
    dangerCount++;
  } else {
    dangerCount = 0;
  }

  // State decision
  String state = "SAFE";

  if (dangerCount >= DANGER_COUNT_THRESHOLD) {
    state = "DANGER";
  } else if (gasAverage > GAS_WARNING) {
    state = "WARNING";
  }

  // Output
  Serial.print("Gas avg: ");
  Serial.print(gasAverage);
  Serial.print(" | Flame: ");
  Serial.print(flameValue);
  Serial.print(" | Count: ");
  Serial.print(dangerCount);
  Serial.print(" | State: ");
  Serial.println(state);

  delay(READ_DELAY_MS);
}