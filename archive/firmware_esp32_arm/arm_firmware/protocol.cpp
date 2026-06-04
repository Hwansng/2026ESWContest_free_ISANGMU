/*
 * protocol.cpp - <CMD,VALUE,CS> 프로토콜 구현
 */
#include "protocol.h"

// payload 문자열의 각 문자를 누적 XOR -> 1바이트 체크섬
uint8_t xorChecksum(const char* payload) {
  uint8_t cs = 0;
  for (const char* p = payload; *p; ++p) {
    cs ^= (uint8_t)(*p);
  }
  return cs;
}

// "CMD" + "," + "VALUE" 를 만들고 체크섬을 붙여 한 줄 메시지로 반환
String buildMessage(const char* cmd, const char* value) {
  String payload = String(cmd) + "," + value;        // "CMD,VALUE"
  uint8_t cs = xorChecksum(payload.c_str());
  char hex[3];
  snprintf(hex, sizeof(hex), "%02X", cs);            // 2자리 대문자 HEX
  return String("<") + payload + "," + hex + ">\n";  // "<CMD,VALUE,CS>\n"
}

// CMD/VALUE 문자열을 내부 CommandType으로 매핑
static CommandType mapCommand(const String& cmd, const String& val, int& outValue) {
  outValue = 0;
  if (cmd == "POSE") {
    if (val == "HOME")  return CMD_POSE_HOME;
    if (val == "READY") return CMD_POSE_READY;
    if (val == "DROP")  return CMD_POSE_DROP;
  } else if (cmd == "WRIST") {
    outValue = val.toInt();   // 방위각 0~180
    return CMD_WRIST;
  } else if (cmd == "GRIP") {
    if (val == "SOFT") return CMD_GRIP_SOFT;
    if (val == "HARD") return CMD_GRIP_HARD;
    if (val == "OPEN") return CMD_GRIP_OPEN;
  } else if (cmd == "STOP") {
    return CMD_STOP;
  }
  return CMD_UNKNOWN;
}

// "<CMD,VALUE,CS>" 한 줄을 파싱. 프레임/콤마/체크섬을 모두 검증한다.
bool parseMessage(const String& line, ArmCommand& out) {
  int lt = line.indexOf('<');
  int gt = line.indexOf('>');
  if (lt < 0 || gt < 0 || gt <= lt) return false;     // 프레임(<...>) 검증
  String body = line.substring(lt + 1, gt);           // "CMD,VALUE,CS"

  int c1 = body.indexOf(',');       // 첫 콤마 (CMD 끝)
  int c2 = body.lastIndexOf(',');   // 마지막 콤마 (CS 앞)
  if (c1 < 0 || c2 <= c1) return false;               // 콤마 2개 필요

  String cmd   = body.substring(0, c1);
  String val   = body.substring(c1 + 1, c2);
  String csStr = body.substring(c2 + 1);

  // 체크섬 재계산 후 비교
  String payload = cmd + "," + val;
  uint8_t expect = xorChecksum(payload.c_str());
  uint8_t got = (uint8_t)strtol(csStr.c_str(), nullptr, 16);
  if (expect != got) return false;                    // 체크섬 불일치 -> 폐기

  out.type = mapCommand(cmd, val, out.value);
  return out.type != CMD_UNKNOWN;
}

const char* armStateName(ArmState s) {
  switch (s) {
    case ARM_IDLE:    return "IDLE";
    case ARM_MOVING:  return "MOVING";
    case ARM_GRIPPED: return "GRIPPED";
    default:          return "ERROR";
  }
}
