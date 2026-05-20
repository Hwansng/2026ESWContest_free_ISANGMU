/*
 * arm_firmware.ino - HazardBot ESP32 #2 (로봇 암) 메인 스케치
 *
 * 역할: STS3215 6축 + 그리퍼 제어, 컴플라이언스 파지, WiFi TCP 명령 수신.
 *
 * 구조 (FreeRTOS 듀얼코어):
 *   - Core 0: wifiTask   (WiFi TCP <CMD,VALUE,CS> 송수신)
 *   - Core 1: servoTask  (STS3215 제어 + 10ms Load 폴링)
 *   - 두 태스크는 큐로만 통신(전역변수 공유 금지).
 *
 * 통신: RPi가 중계.
 *   명령(RPi->ARM): <POSE,HOME|READY|DROP>, <WRIST,0~180>,
 *                   <GRIP,SOFT|HARD|OPEN>, <STOP,0>
 *   피드백(ARM->RPi): <ARM,IDLE|MOVING|GRIPPED|ERROR>, <LOAD,percent>
 *
 * 실보드 테스트 절차:
 *   1) set_servo_id.ino로 ID 2~6 부여(선행) 후 6축 Ping 확인
 *   2) <POSE,HOME,..>  -> 베이스부터 순차 구동 확인
 *   3) <GRIP,OPEN,..>  -> 그리퍼 개폐 확인
 *   4) <GRIP,SOFT,..>  -> <LOAD> 로그로 컴플라이언스 파지 확인
 *   5) <STOP,0,..>     -> 즉시 토크 오프(전역 정지) 확인
 */
#include <Arduino.h>
#include "protocol.h"
#include "config.h"
#include "servo_task.h"
#include "wifi_task.h"

// 태스크 간 큐 정의 (protocol.h에서 extern으로 선언됨)
QueueHandle_t xQueueCmdToServo    = nullptr;  // wifiTask -> servoTask
QueueHandle_t xQueueServoFeedback = nullptr;  // servoTask -> wifiTask

void setup() {
  Serial.begin(115200);
  delay(200);

  // 명령/피드백 큐 생성
  xQueueCmdToServo    = xQueueCreate(8,  sizeof(ArmCommand));
  xQueueServoFeedback = xQueueCreate(16, sizeof(ArmFeedback));

  // 코어 고정 생성: Core 0 = WiFi, Core 1 = 서보
  // (인자: 함수, 이름, 스택, 파라미터, 우선순위, 핸들, 코어번호)
  xTaskCreatePinnedToCore(wifiTask,  "wifiTask",  8192, nullptr, 1, nullptr, 0);
  xTaskCreatePinnedToCore(servoTask, "servoTask", 8192, nullptr, 2, nullptr, 1);
}

void loop() {
  // 모든 동작은 FreeRTOS 태스크에서 수행하므로 loop는 비워 둔다.
  vTaskDelay(pdMS_TO_TICKS(1000));
}
