/*
 * config.h - ESP32 #2 (로봇 암) 펌웨어 전역 설정 헤더
 *
 * 핀맵, 서보 구성, 소프트웨어 한계값, 컴플라이언스 파지 Load 임계값,
 * WiFi/TCP 설정 등 펌웨어 전반에서 쓰는 상수를 한곳에 모은다.
 * (팀 규칙: 매직넘버 금지 - 모든 수치는 여기서 UPPER_SNAKE 상수로 관리)
 */
#ifndef CONFIG_H
#define CONFIG_H

#include <Arduino.h>

// ===== STS3215 직렬 버스 (UART2) 핀/통신 설정 =====
// set_servo_id.ino(ID 부여 단계)와 동일한 핀/속도를 사용한다.
static const int  PIN_SERVO_RX = 17;       // ESP32 UART2 RX
static const int  PIN_SERVO_TX = 16;       // ESP32 UART2 TX
static const long SERVO_BAUD   = 1000000;  // STS3215 기본 통신 속도 1Mbps

// ===== 서보 구성 =====
static const uint8_t SERVO_COUNT    = 6;   // 6축 (ID 1~6)
static const uint8_t JOINT_FIRST_ID = 1;   // 첫 관절 ID
static const uint8_t GRIPPER_ID     = 6;   // 그리퍼 = ID 6

// STS3215 위치 분해능: 0~4095 step == 0~360deg (12bit)
static const int   SERVO_POS_MAX = 4095;
static const float STEPS_PER_DEG = 4096.0f / 360.0f;  // 약 11.38 step/deg

// 관절별 소프트웨어 한계값 [deg] (인덱스 0=ID1 ... 5=ID6=그리퍼)
// ※ SO-ARM101 실제 가동범위에 맞춰 캘리브레이션 필요(보수적 시작값)
static const float JOINT_MIN_DEG[SERVO_COUNT] = {   0,  10,  10,  10,   0,  30 };
static const float JOINT_MAX_DEG[SERVO_COUNT] = { 360, 200, 200, 200, 360, 120 };

// 그리퍼 개폐 각도 [deg]
static const float GRIPPER_OPEN_DEG  = 120;  // 완전 개방
static const float GRIPPER_CLOSE_DEG = 30;   // 완전 폐쇄

// 서보 구동 속도/가속 (WritePosEx 인자)
static const uint16_t SERVO_SPEED = 1500;  // step/s
static const uint8_t  SERVO_ACC   = 50;    // 가속도 단계

// ===== 컴플라이언스 파지 Load 임계값 [%] =====
// STS3215 ReadLoad 원시값 0~1000(0.1% 단위) -> percent = raw/10
static const int SOFT_LOAD_PERCENT = 40;   // 소프트 파지 목표 부하
static const int HARD_LOAD_PERCENT = 80;   // 하드 파지 목표 부하
static const int OVERLOAD_PERCENT  = 95;   // 과부하 경보(안전 정지 기준)

// Load 폴링 주기(Core1) 및 피드백 송신 throttle
static const int POLL_INTERVAL_MS  = 10;   // 10ms 주기 Load 폴링
static const int LOAD_REPORT_EVERY = 10;   // 10회마다(=100ms) <LOAD> 송신

// 그리퍼 점진 폐쇄 파라미터(컴플라이언스 파지)
static const float GRIP_STEP_DEG   = 1.5f; // 한 스텝당 닫는 각도
static const int   GRIP_STEP_DELAY = 15;   // 스텝 간 지연[ms] (부하 안정화)

// ===== WiFi / TCP =====
static const char*    WIFI_SSID = "HazardBot";  // TODO: 실제 AP SSID로 교체
static const char*    WIFI_PASS = "changeme";   // TODO: 실제 비밀번호로 교체
static const uint16_t TCP_PORT  = 5002;         // ESP32 #2 명령 수신 포트

#endif  // CONFIG_H
