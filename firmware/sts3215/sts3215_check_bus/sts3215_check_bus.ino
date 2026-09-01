/*
 * sts3215_check_bus — STS3215 데이지 체인 통신 검증 (읽기 전용)
 *
 * ESP32 #2 + SCServo(SMS_STS) 경로로 ID 1~6 전체를 Ping 하고
 * Pos / Load / Temp / Voltage 를 읽는다. 토크를 켜거나 서보를 움직이지 않는다.
 *
 * 배선 (기존 검증 설정 그대로)
 *   ESP32 UART2 : RX = GPIO 17, TX = GPIO 16
 *   보드레이트   : 1 Mbps
 *   서보 전원    : 팔로워 12V (외부 공급) — ESP32의 5V/3.3V로 구동하지 말 것
 *   GND         : ESP32 GND ↔ 서보 전원 GND 공통 연결 필수 (신호 기준 전위)
 *
 * ⚠ 리더암(7.4V 정격)에는 12V를 인가하지 말 것. 서보가 파손된다.
 */

#include <SCServo.h>

#define S_RXD 17
#define S_TXD 16
#define BAUDRATE 1000000

/*
 * SCServo 의 SCSerial::rFlushSCS() 는 타임아웃이 없다:
 *
 *     while(pSerial->read()!=-1);
 *
 * RX 핀이 떠 있거나(버스 미연결) 노이즈가 계속 들어오면 read() 가 -1 을
 * 반환하지 않아 영원히 빠져나오지 못한다. Ping() 이 이 함수를 먼저 호출하므로,
 * 증상은 "헤더까지 출력된 뒤 첫 서보에서 멈춤" 으로 나타난다.
 *
 * 타임아웃을 넣어 덮어쓴다. 그래야 배선이 빠져 있어도 멈추지 않고 FAIL 로 떨어진다.
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

#define ID_MIN 1
#define ID_MAX 6

// 팔로워 정격 12V. 이 범위를 벗어나면 배선/전원을 의심한다.
#define VOLT_MIN 10.0
#define VOLT_MAX 13.0

const char* axisName(int id) {
  switch (id) {
    case 1: return "Base        (shoulder_pan) ";
    case 2: return "Shoulder    (shoulder_lift)";
    case 3: return "Elbow       (elbow_flex)   ";
    case 4: return "Wrist Pitch (wrist_flex)   ";
    case 5: return "Wrist Roll  (wrist_roll)   ";
    case 6: return "Gripper     (gripper)      ";
    default: return "?";
  }
}

void checkBus() {
  Serial.println();
  Serial.println("=== STS3215 버스 검증 (읽기 전용) ===");
  Serial.print("UART2 RX=");
  Serial.print(S_RXD);
  Serial.print(" TX=");
  Serial.print(S_TXD);
  Serial.print(" @ ");
  Serial.print(BAUDRATE);
  Serial.println(" bps");
  Serial.println();

  Serial.println("ID  축                          Ping   Pos   Load  Temp   Volt");
  Serial.println("--------------------------------------------------------------");

  int okCount = 0;
  int warnCount = 0;

  for (int id = ID_MIN; id <= ID_MAX; id++) {
    Serial.print(" ");
    Serial.print(id);
    Serial.print("  ");
    Serial.print(axisName(id));

    if (st.Ping(id) == -1) {
      Serial.println("  FAIL   -     -     -      -");
      continue;
    }

    int pos = st.ReadPos(id);
    int load = st.ReadLoad(id);
    int temp = st.ReadTemper(id);
    float volt = st.ReadVoltage(id) / 10.0;

    Serial.print("  OK   ");
    Serial.print(pos);
    Serial.print("   ");
    Serial.print(load);
    Serial.print("   ");
    Serial.print(temp);
    Serial.print("C   ");
    Serial.print(volt, 1);
    Serial.println("V");

    okCount++;

    if (volt < VOLT_MIN || volt > VOLT_MAX) {
      Serial.print("     ⚠ ID ");
      Serial.print(id);
      Serial.print(" 전압 ");
      Serial.print(volt, 1);
      Serial.println("V — 팔로워 12V 정격을 벗어남. 전원/배선 확인.");
      warnCount++;
    }
    if (temp >= 55) {
      Serial.print("     ⚠ ID ");
      Serial.print(id);
      Serial.print(" 온도 ");
      Serial.print(temp);
      Serial.println("C — 과열.");
      warnCount++;
    }
  }

  Serial.println();
  Serial.print("응답: ");
  Serial.print(okCount);
  Serial.print(" / ");
  Serial.println(ID_MAX - ID_MIN + 1);

  if (okCount == (ID_MAX - ID_MIN + 1) && warnCount == 0) {
    Serial.println("OK — ID 1~6 전체 응답. 데이지 체인 통신 정상.");
  } else if (okCount == 0) {
    Serial.println("FAIL — 서보가 하나도 응답하지 않는다.");
    Serial.println("  이 메시지가 보인다는 것은 ESP32 시리얼은 정상이라는 뜻이다.");
    Serial.println("  즉 문제는 ESP32 ↔ 서보 사이에 있다:");
    Serial.println("  - 서보 전원 미인가 (팔로워 12V 외부 공급 필요. USB 전원으로는 안 된다)");
    Serial.println("  - ESP32 GND ↔ 서보 전원 GND 공통 연결 누락");
    Serial.println("  - UART2 배선 (RX=17 / TX=16) 반대로 연결");
  } else {
    Serial.println("FAIL — 일부 서보만 응답한다.");
    Serial.println("  - ID 중복 (공장 출하값은 전부 ID=1) → sts3215_set_id 로 재부여");
    Serial.println("  - 데이지 체인 커넥터 접촉 불량");
  }

  Serial.println();
  Serial.println("[엔터를 치면 다시 검사한다]");
}

void setup() {
  Serial.begin(115200);
  Serial1.begin(BAUDRATE, SERIAL_8N1, S_RXD, S_TXD);
  st.pSerial = &Serial1;
  delay(1000);

  checkBus();
}

// 부팅 시 1회 실행된다. 시리얼 모니터를 늦게 열어 출력을 놓쳤거나
// 배선을 고친 뒤 다시 보고 싶으면, 엔터만 치면 재실행된다.
void loop() {
  if (Serial.available()) {
    while (Serial.available()) {
      Serial.read();
    }
    checkBus();
  }
}
