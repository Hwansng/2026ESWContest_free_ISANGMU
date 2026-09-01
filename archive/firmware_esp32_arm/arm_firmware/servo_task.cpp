/*
 * servo_task.cpp - Core 1 전담 서보 태스크
 *
 * 역할 두 가지:
 *  1) 명령 큐(xQueueCmdToServo)에서 받은 명령을 실행
 *     (자세 이동 / 방위각 정렬 / 컴플라이언스 파지 / 그리퍼 개방 / 정지)
 *  2) 10ms 주기로 그리퍼 Load를 폴링해 과부하를 감시하고,
 *     100ms마다 <LOAD> 피드백을 wifiTask로 보낸다.
 *
 * 전역변수 공유 없이 큐로만 통신한다(팀 규칙).
 */
#include <Arduino.h>
#include "servo_task.h"
#include "servo_control.h"
#include "protocol.h"
#include "config.h"

// 상태 변경을 wifiTask로 보고
static void reportState(ArmState s) {
  ArmFeedback fb;
  fb.kind = FB_STATE;
  fb.state = s;
  fb.loadPercent = 0;
  xQueueSend(xQueueServoFeedback, &fb, 0);  // 큐가 차도 블로킹하지 않음
}

// 부하값을 wifiTask로 보고
static void reportLoad(int percent) {
  ArmFeedback fb;
  fb.kind = FB_LOAD;
  fb.state = ARM_IDLE;
  fb.loadPercent = percent;
  xQueueSend(xQueueServoFeedback, &fb, 0);
}

// 단일 명령 실행 (블로킹 동작 포함)
static void executeCommand(const ArmCommand& cmd) {
  switch (cmd.type) {
    case CMD_POSE_HOME:
    case CMD_POSE_READY:
    case CMD_POSE_DROP:
      reportState(ARM_MOVING);
      presetPose(cmd.type);     // 6축 순차 구동
      reportState(ARM_IDLE);
      break;

    case CMD_WRIST:
      reportState(ARM_MOVING);
      setWristRoll(cmd.value);  // 방위각 -> Wrist Roll 정렬
      reportState(ARM_IDLE);
      break;

    case CMD_GRIP_SOFT:
    case CMD_GRIP_HARD: {
      reportState(ARM_MOVING);
      int finalLoad = 0;
      bool ok = complianceGrip(cmd.type == CMD_GRIP_HARD, finalLoad);
      reportLoad(finalLoad);
      // 파지 성공 + 과부하 아님 -> GRIPPED, 그 외 -> ERROR
      reportState((ok && finalLoad < OVERLOAD_PERCENT) ? ARM_GRIPPED : ARM_ERROR);
      break;
    }

    case CMD_GRIP_OPEN:
      reportState(ARM_MOVING);
      gripperOpen();
      reportState(ARM_IDLE);
      break;

    case CMD_STOP:
      torqueOffAll();           // 최우선 안전: 즉시 토크 오프
      reportState(ARM_IDLE);
      break;

    default:
      break;
  }
}

void servoTask(void* pv) {
  servoInitBus();      // UART2 + 서보 초기화(토크 ON)
  reportState(ARM_IDLE);

  ArmCommand cmd;
  int pollCount = 0;

  for (;;) {
    // 1) 대기 중인 명령이 있으면 즉시 처리 (timeout 0 = 논블로킹)
    if (xQueueReceive(xQueueCmdToServo, &cmd, 0) == pdTRUE) {
      executeCommand(cmd);
    }

    // 2) 10ms Load 폴링 (그리퍼 부하 안전 감시)
    int load = readLoadPercent(GRIPPER_ID);
    if (load >= OVERLOAD_PERCENT) {
      reportState(ARM_ERROR);   // 과부하 경보
    }

    // 3) 100ms마다(=10회) <LOAD> 피드백 송신 (TCP 폭주 방지)
    if (++pollCount >= LOAD_REPORT_EVERY) {
      pollCount = 0;
      reportLoad(load);
    }

    vTaskDelay(pdMS_TO_TICKS(POLL_INTERVAL_MS));  // 10ms 주기 유지
  }
}
