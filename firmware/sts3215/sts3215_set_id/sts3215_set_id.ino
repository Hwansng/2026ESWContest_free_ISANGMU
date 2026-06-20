/*
 * sts3215_set_id — STS3215 서보 ID 부여 (한 번에 하나씩)
 *
 * ⚠ 서보를 반드시 하나만 연결한 상태에서 실행할 것.
 *   STS3215 는 공장 출하 시 전부 ID=1 이다. 6개를 모두 물린 채로 ID를 쓰면
 *   같은 ID가 동시에 응답해 버스가 충돌하고, 엉뚱한 서보에 기록될 수 있다.
 *
 * 사용법 (시리얼 모니터 115200, 줄바꿈: Newline)
 *   scan      → 버스에 있는 서보 탐색 (ID 1~20)
 *   id <n>    → 연결된 단 하나의 서보에 ID n (1~6) 부여
 *
 * 축 매핑 (LeRobot so101 과 동일)
 *   1 Base / 2 Shoulder / 3 Elbow / 4 Wrist Pitch / 5 Wrist Roll / 6 Gripper
 *
 * 배선
 *   ESP32 UART2 : RX = GPIO 17, TX = GPIO 16 @ 1 Mbps
 *   서보 전원   : 팔로워 12V / 리더 7.4V — 정격에 맞는 전원만 인가할 것
 *   GND        : ESP32 GND ↔ 서보 전원 GND 공통 연결 필수
 *
 * ⚠ 리더암 서보는 7.4V 정격이다. 12V를 인가하면 파손된다.
 */

#include <SCServo.h>

#define S_RXD 17
#define S_TXD 16
#define BAUDRATE 1000000

/*
 * SCServo 의 SCSerial::rFlushSCS() 는 타임아웃이 없어(while(pSerial->read()!=-1);)
 * RX 가 떠 있으면 무한 루프에 빠진다. Ping() 이 이를 먼저 호출하므로 스캔이 멈춘다.
 * 타임아웃을 넣어 덮어쓴다.
 */
class SafeSMS_STS : public SMS_STS {
protected:
  void rFlushSCS() override {
    unsigned long start = millis();
    while (pSerial->read() != -1) {
      if (millis() - start > 50) {
        break;
      }
    }
  }
};

SafeSMS_STS st;

#define SCAN_MIN 1
#define SCAN_MAX 20

// 스캔 결과를 담는다.
int foundIds[SCAN_MAX + 1];
int foundCount = 0;

void scanBus() {
  foundCount = 0;
  Serial.println("[scan] ID 1~20 탐색 중...");

  for (int id = SCAN_MIN; id <= SCAN_MAX; id++) {
    if (st.Ping(id) != -1) {
      foundIds[foundCount++] = id;
      Serial.print("[scan] ID ");
      Serial.print(id);
      Serial.print(" 응답  (전압 ");
      Serial.print(st.ReadVoltage(id) / 10.0, 1);
      Serial.println("V)");
    }
  }

  if (foundCount == 0) {
    Serial.println("[scan] 응답 없음. 전원 / 배선 / 보드레이트를 확인할 것.");
  } else {
    Serial.print("[scan] 총 ");
    Serial.print(foundCount);
    Serial.println("개 발견.");
  }
  Serial.println();
}

void setId(int newId) {
  if (newId < 1 || newId > 6) {
    Serial.println("[set] 실패 — ID는 1~6 범위여야 한다.");
    return;
  }

  scanBus();

  if (foundCount == 0) {
    Serial.println("[set] 중단 — 서보가 응답하지 않는다.");
    return;
  }
  if (foundCount > 1) {
    Serial.println("[set] 중단 — 버스에 서보가 2개 이상 있다.");
    Serial.println("      ID 부여는 반드시 하나만 연결한 상태에서 해야 한다.");
    return;
  }

  int oldId = foundIds[0];
  if (oldId == newId) {
    Serial.print("[set] ID ");
    Serial.print(newId);
    Serial.println(" — 이미 해당 ID다. 변경 없음.");
    return;
  }

  Serial.print("[set] ID ");
  Serial.print(oldId);
  Serial.print(" → ");
  Serial.print(newId);
  Serial.println(" 기록 중...");

  st.unLockEprom(oldId);                    // EPROM 잠금 해제
  st.writeByte(oldId, SMS_STS_ID, newId);   // ID 레지스터(주소 5) 기록
  st.LockEprom(newId);                      // 새 ID로 다시 잠금
  delay(100);

  // 검증: 새 ID로 응답하는지, 옛 ID는 사라졌는지
  bool newOk = (st.Ping(newId) != -1);
  bool oldGone = (st.Ping(oldId) == -1);

  if (newOk && oldGone) {
    Serial.print("[set] OK — ID ");
    Serial.print(newId);
    Serial.println(" 부여 완료. 서보를 분리하고 다음 서보를 연결할 것.");
  } else {
    Serial.println("[set] FAIL — 검증 실패. 전원을 껐다 켜고 scan 으로 재확인할 것.");
  }
  Serial.println();
}

void printHelp() {
  Serial.println();
  Serial.println("=== STS3215 ID 부여 ===");
  Serial.println("  scan    버스 탐색 (ID 1~20)");
  Serial.println("  id <n>  연결된 서보에 ID n (1~6) 부여");
  Serial.println();
  Serial.println("⚠ 서보는 반드시 하나만 연결한 상태에서 id 명령을 실행할 것.");
  Serial.println("  1 Base / 2 Shoulder / 3 Elbow / 4 Wrist Pitch / 5 Wrist Roll / 6 Gripper");
  Serial.println();
}

void setup() {
  Serial.begin(115200);
  Serial1.begin(BAUDRATE, SERIAL_8N1, S_RXD, S_TXD);
  st.pSerial = &Serial1;
  delay(1000);
  printHelp();
}

void loop() {
  if (!Serial.available()) {
    return;
  }

  String line = Serial.readStringUntil('\n');
  line.trim();

  if (line.length() == 0) {
    return;
  }

  if (line.equalsIgnoreCase("scan")) {
    scanBus();
  } else if (line.startsWith("id ")) {
    setId(line.substring(3).toInt());
  } else {
    Serial.print("[?] 알 수 없는 명령: ");
    Serial.println(line);
    printHelp();
  }
}
