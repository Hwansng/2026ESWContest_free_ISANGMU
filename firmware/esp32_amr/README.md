# ESP32 #1 (AMR) 펌웨어

담당: 팀원 B

5종 센서(MQ-2/MQ-135/MLX90614/VL53L1X/KY-026) + DC 모터(TB6612FNG) + 5채널 IR 라인센서 + LiPo 감시(시연).

## 핵심 태스크 (FreeRTOS)
- **Core 0**: Wi-Fi TCP (RPi 5 통신)
- **Core 1**: 센서 읽기 + 모터 PID + 라인트레이싱

## 메시지 포맷
```
<CMD,VALUE,CS>\n
```
- `STATE`: SAFE / WARNING / DANGER
- 체크섬: `<`, `>` 제외 본문의 XOR 8-bit 16진수 2자리

## 핀맵 (요약)
| 기능 | 핀 |
|---|---|
| MQ-135 (가스) | GPIO 34 (ADC1) |
| KY-026 (화염) | GPIO 27 |
| 5ch IR 아날로그 | GPIO 35 |
| 5ch IR 디지털 통합 | GPIO 5 |
| VL53L1X SDA/SCL | I2C 기본 |

## 현재 구현 상태
- `esp32_amr.ino`: 가스/화염 기반 SAFE/WARNING/DANGER 상태 판정 + 이벤트 메시지 출력 (v5)
- TODO: 모터 제어, 라인트레이싱 PID, Wi-Fi TCP, LiPo 모니터링 통합
