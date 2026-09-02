// Target: ESP32 #1 (AMR)
// Advanced decision logic (3-level state)

#include <Arduino.h>

const int MQ135_PIN = 34;
const int FLAME_PIN = 27;

const int GAS_WARNING = 50;
const int GAS_DANGER = 100;

void setup() {
  Serial.begin(115200);
  delay(1000);

  pinMode(FLAME_PIN, INPUT);

  Serial.println("Advanced decision system start");
}

void loop() {
  int gasValue = analogRead(MQ135_PIN);
  int flameValue = digitalRead(FLAME_PIN);

  String state = "SAFE";

  if (flameValue == 0) {
    state = "DANGER";
  } 
  else if (gasValue > GAS_DANGER) {
    state = "DANGER";
  } 
  else if (gasValue > GAS_WARNING) {
    state = "WARNING";
  }

  Serial.print("Gas: ");
  Serial.print(gasValue);
  Serial.print(" | Flame: ");
  Serial.print(flameValue);
  Serial.print(" | State: ");
  Serial.println(state);

  delay(500);
}