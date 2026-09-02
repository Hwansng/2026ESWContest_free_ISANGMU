// Target: ESP32 #1 (AMR)
// MQ-135 + KY-026 + 3-level decision with moving average

#include <Arduino.h>

const int MQ135_PIN = 34;
const int FLAME_PIN = 27;

const int GAS_WARNING = 50;
const int GAS_DANGER = 100;

const int SAMPLE_COUNT = 10;
const int READ_DELAY_MS = 300;

int gasSamples[SAMPLE_COUNT];
int sampleIndex = 0;
long gasSum = 0;

void setup() {
  Serial.begin(115200);
  delay(1000);

  pinMode(FLAME_PIN, INPUT);

  for (int i = 0; i < SAMPLE_COUNT; i++) {
    gasSamples[i] = 0;
  }

  Serial.println("3-level decision with moving average start");
}

void loop() {
  int gasRaw = analogRead(MQ135_PIN);
  int flameValue = digitalRead(FLAME_PIN);

  gasSum -= gasSamples[sampleIndex];
  gasSamples[sampleIndex] = gasRaw;
  gasSum += gasRaw;

  sampleIndex = (sampleIndex + 1) % SAMPLE_COUNT;

  int gasAverage = gasSum / SAMPLE_COUNT;

  String state = "SAFE";

  if (flameValue == 0) {
    state = "DANGER";
  } else if (gasAverage > GAS_DANGER) {
    state = "DANGER";
  } else if (gasAverage > GAS_WARNING) {
    state = "WARNING";
  }

  Serial.print("Gas raw: ");
  Serial.print(gasRaw);
  Serial.print(" | Gas avg: ");
  Serial.print(gasAverage);
  Serial.print(" | Flame: ");
  Serial.print(flameValue);
  Serial.print(" | State: ");
  Serial.println(state);

  delay(READ_DELAY_MS);
}