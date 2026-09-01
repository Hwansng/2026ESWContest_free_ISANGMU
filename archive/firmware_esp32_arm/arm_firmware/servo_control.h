/*
 * servo_control.h - STS3215 6축/그리퍼 제어 래퍼
 *
 * SCServo(SMS_STS) 라이브러리를 감싸 각도 기반 제어, 소프트웨어 한계값,
 * 프리셋 자세, 방위각->Wrist Roll 매핑, 컴플라이언스 파지, 토크 오프를 제공.
 */
#ifndef SERVO_CONTROL_H
#define SERVO_CONTROL_H

#include <Arduino.h>
#include "protocol.h"

// UART2 + SMS_STS 초기화, 전 축 토크 ON
void servoInitBus();
// 각도[deg] -> step 변환 (0~SERVO_POS_MAX clamp)
int  angleToPos(float angleDeg);
// 소프트웨어 한계값 적용 후 해당 관절 이동
void moveJoint(uint8_t id, float angleDeg);
// 프리셋 자세(HOME/READY/DROP) 베이스->그리퍼 순차 구동
void presetPose(CommandType pose);
// 비전 방위각 0~180 -> Wrist Roll(ID5) 매핑 후 이동
void setWristRoll(int azimuthDeg);
// 그리퍼 개방
void gripperOpen();
// 컴플라이언스 파지: 목표 부하 도달까지 점진 폐쇄. finalLoad에 최종 부하[%].
// 반환 true=물체 파지, false=목표 미달(물체 없음)
bool complianceGrip(bool hard, int& finalLoad);
// 지정 서보 Load 원시값 -> percent
int  readLoadPercent(uint8_t id);
// 전 축 토크 오프 (전역 STOP, 안전)
void torqueOffAll();

#endif  // SERVO_CONTROL_H
