/*
 * servo_control.cpp - STS3215 제어 구현 (SCServo SMS_STS)
 *
 * set_servo_id.ino 단계에서 ID 2~6이 부여된 6축(ID1~6)을 제어한다.
 * 관절 매핑(SO-ARM101): ID1 shoulder_pan / ID2 shoulder_lift /
 *   ID3 elbow_flex / ID4 wrist_flex / ID5 wrist_roll / ID6 gripper
 */
#include <SCServo.h>
#include "servo_control.h"
#include "config.h"

static SMS_STS st;  // Feetech SMS_STS 드라이버 인스턴스

// 프리셋 자세 [deg] : 열 = 관절(ID1~6)
// ※ 실제 기구학에 맞게 캘리브레이션 필요(시작값)
static const float POSE_HOME[SERVO_COUNT]  = { 180,  90,  90,  90,  90, GRIPPER_OPEN_DEG };
static const float POSE_READY[SERVO_COUNT] = { 180, 120, 120,  90,  90, GRIPPER_OPEN_DEG };
static const float POSE_DROP[SERVO_COUNT]  = {  90, 120, 120,  90,  90, GRIPPER_OPEN_DEG };

void servoInitBus() {
  // STS3215 직렬 버스를 UART2로 개통 (set_servo_id.ino와 동일 설정)
  Serial1.begin(SERVO_BAUD, SERIAL_8N1, PIN_SERVO_RX, PIN_SERVO_TX);
  st.pSerial = &Serial1;
  delay(100);
  for (uint8_t id = JOINT_FIRST_ID; id <= SERVO_COUNT; ++id) {
    st.EnableTorque(id, 1);  // 전 축 토크 ON
  }
}

int angleToPos(float angleDeg) {
  int pos = (int)(angleDeg * STEPS_PER_DEG + 0.5f);  // 각도 -> step (반올림)
  if (pos < 0) pos = 0;                              // 하한 clamp
  if (pos > SERVO_POS_MAX) pos = SERVO_POS_MAX;      // 상한 clamp
  return pos;
}

void moveJoint(uint8_t id, float angleDeg) {
  uint8_t idx = id - 1;  // 0-based 인덱스
  // 소프트웨어 한계값 clamp (기구 충돌/손상 방지)
  if (angleDeg < JOINT_MIN_DEG[idx]) angleDeg = JOINT_MIN_DEG[idx];
  if (angleDeg > JOINT_MAX_DEG[idx]) angleDeg = JOINT_MAX_DEG[idx];
  st.WritePosEx(id, angleToPos(angleDeg), SERVO_SPEED, SERVO_ACC);
}

void presetPose(CommandType pose) {
  const float* target = POSE_HOME;
  if (pose == CMD_POSE_READY)     target = POSE_READY;
  else if (pose == CMD_POSE_DROP) target = POSE_DROP;
  // 베이스(ID1) -> 그리퍼(ID6) 순차 구동
  // (동시 기동 시 6서보 피크전류가 커지므로 순차로 분산)
  for (uint8_t id = JOINT_FIRST_ID; id <= SERVO_COUNT; ++id) {
    moveJoint(id, target[id - 1]);
    delay(250);  // 관절 간 이동 간격
  }
}

void setWristRoll(int azimuthDeg) {
  // 비전 방위각 0~180deg -> Wrist Roll(ID5) 0~360 매핑
  if (azimuthDeg < 0)   azimuthDeg = 0;
  if (azimuthDeg > 180) azimuthDeg = 180;
  float angle = (float)azimuthDeg * 2.0f;  // 0~180 -> 0~360
  moveJoint(5, angle);
}

void gripperOpen() {
  moveJoint(GRIPPER_ID, GRIPPER_OPEN_DEG);
}

int readLoadPercent(uint8_t id) {
  int raw = st.ReadLoad(id);  // 0~1000 (방향 부호가 섞일 수 있음)
  if (raw < 0) raw = -raw;    // 부하 크기만 사용
  return raw / 10;            // 0.1% 단위 -> percent
}

bool complianceGrip(bool hard, int& finalLoad) {
  int target = hard ? HARD_LOAD_PERCENT : SOFT_LOAD_PERCENT;  // 목표 부하
  float angle = GRIPPER_OPEN_DEG;  // 개방 상태에서 시작
  finalLoad = 0;
  // 목표 부하 도달 또는 완전 폐쇄까지 조금씩 닫으며 Load를 감시
  while (angle > GRIPPER_CLOSE_DEG) {
    angle -= GRIP_STEP_DEG;
    moveJoint(GRIPPER_ID, angle);
    delay(GRIP_STEP_DELAY);  // 부하 안정화 대기
    int load = readLoadPercent(GRIPPER_ID);
    finalLoad = load;
    if (load >= OVERLOAD_PERCENT) return true;  // 과부하 -> 즉시 정지(잡힘)
    if (load >= target)           return true;  // 목표 부하 도달 -> 파지 성공
  }
  return false;  // 완전히 닫혔는데 목표 미달 -> 물체 없음/파지 실패
}

void torqueOffAll() {
  for (uint8_t id = JOINT_FIRST_ID; id <= SERVO_COUNT; ++id) {
    st.EnableTorque(id, 0);  // 토크 해제 -> 즉시 정지(전역 STOP)
  }
}
