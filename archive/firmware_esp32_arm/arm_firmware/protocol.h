/*
 * protocol.h - <CMD,VALUE,CS> 통신 프로토콜 + 태스크 간 메시지 정의
 *
 * 팀 공통 통신 규약 <CMD,VALUE,CS> (CS=XOR 체크섬, 2자리 HEX)을
 * 빌드/파싱하는 함수와, wifiTask <-> servoTask 사이를 오가는
 * 큐 메시지 구조체를 정의한다.
 */
#ifndef PROTOCOL_H
#define PROTOCOL_H

#include <Arduino.h>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>

// 명령 종류 (RPi -> ARM)
enum CommandType {
  CMD_POSE_HOME,   // 기본 자세
  CMD_POSE_READY,  // 파지 대기 자세
  CMD_POSE_DROP,   // 격리함 투하 자세
  CMD_WRIST,       // value = 비전 방위각 0~180 (Wrist Roll 정렬)
  CMD_GRIP_SOFT,   // 컴플라이언스 소프트 파지
  CMD_GRIP_HARD,   // 컴플라이언스 하드 파지
  CMD_GRIP_OPEN,   // 그리퍼 개방(놓기)
  CMD_STOP,        // 전역 정지(토크 오프) - 최우선 안전
  CMD_UNKNOWN      // 파싱 실패/미지원
};

// 파싱된 명령 (wifiTask -> servoTask 큐)
struct ArmCommand {
  CommandType type;
  int value;       // CMD_WRIST일 때만 의미(방위각)
};

// 암 상태 (ARM -> RPi)
enum ArmState { ARM_IDLE, ARM_MOVING, ARM_GRIPPED, ARM_ERROR };

// 피드백 종류
enum FeedbackKind { FB_STATE, FB_LOAD };

// 서보 피드백 (servoTask -> wifiTask 큐)
struct ArmFeedback {
  FeedbackKind kind;
  ArmState     state;        // kind==FB_STATE일 때 유효
  int          loadPercent;  // kind==FB_LOAD일 때 유효
};

// 태스크 간 큐 핸들 (arm_firmware.ino에서 정의, 여기선 extern 선언)
extern QueueHandle_t xQueueCmdToServo;     // wifiTask -> servoTask
extern QueueHandle_t xQueueServoFeedback;  // servoTask -> wifiTask

// payload("CMD,VALUE")의 모든 문자를 XOR 한 체크섬
uint8_t xorChecksum(const char* payload);
// "<CMD,VALUE,CS>\n" 문자열 생성 (CS = 2자리 대문자 HEX)
String buildMessage(const char* cmd, const char* value);
// 수신 라인 파싱 + 체크섬 검증 -> ArmCommand. 성공 시 true
bool parseMessage(const String& line, ArmCommand& out);
// 상태 enum -> 문자열("IDLE"/"MOVING"/...)
const char* armStateName(ArmState s);

#endif  // PROTOCOL_H
