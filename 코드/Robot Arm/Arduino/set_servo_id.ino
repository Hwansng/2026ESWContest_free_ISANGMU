#include <SCServo.h>

SMS_STS st;

#define S_RXD 17   // ESP32 UART2 RX
#define S_TXD 16   // ESP32 UART2 TX

const uint8_t CURRENT_ID = 1;   // 출하 기본값
const uint8_t NEW_ID     = 2;   // 부여할 ID — 서보 1개씩 교체하며 2,3,4,5,6 순으로 변경

void setup() {
  Serial.begin(115200);
  Serial1.begin(1000000, SERIAL_8N1, S_RXD, S_TXD);
  st.pSerial = &Serial1;
  delay(1000);

  // 1) 서보 응답 확인
  int id = st.Ping(CURRENT_ID);
  if (id == -1) {
    Serial.println("[FAIL] 서보 응답 없음 — 배선/전원/baud 확인");
    return;
  }
  Serial.printf("[OK] 검출된 ID: %d\n", id);

  // 2) EEPROM 잠금 해제
  st.unLockEprom(CURRENT_ID);
  delay(20);

  // 3) ID 레지스터(주소 5)에 새 ID 기록
  st.writeByte(CURRENT_ID, SMS_STS_ID, NEW_ID);
  delay(20);

  // 4) EEPROM 잠금 복원 (이때부터 새 ID로 호출)
  st.LockEprom(NEW_ID);
  delay(20);

  // 5) 검증 — 새 ID로 Ping
  int verify = st.Ping(NEW_ID);
  if (verify == NEW_ID) {
    Serial.printf("[SUCCESS] ID %d -> %d 변경 완료\n", CURRENT_ID, NEW_ID);
  } else {
    Serial.println("[FAIL] 변경 후 응답 없음");
  }
}

void loop() {}
