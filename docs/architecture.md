# HazardBot 아키텍처 개요

> 계획서 v4.4 요약. 상세는 별도 문서(Notion/Drive) 참조.

## 2계층 분산 아키텍처

```
                 ┌──────────────────────────────┐
                 │     Raspberry Pi 5 (8GB)     │
                 │     Ubuntu 24.04 + ROS2 Jazzy │
                 │                              │
                 │  ┌──────────────────────┐    │
                 │  │ vision_node (60fps)  │    │
                 │  │ hazard_detector      │    │
                 │  │ mission_orchestrator │    │
                 │  │ amr_bridge / arm_br. │    │
                 │  │ hazardbot_dashboard  │    │
                 │  └──────────────────────┘    │
                 └──────┬─────────────┬─────────┘
                  Wi-Fi │             │ Wi-Fi
                  TCP   │             │ TCP
                        ▼             ▼
              ┌─────────────────┐  ┌─────────────────┐
              │ ESP32 #1 (AMR)  │  │ ESP32 #2 (ARM)  │
              │ FreeRTOS dual   │  │ FreeRTOS dual   │
              │ - 5종 센서      │  │ - STS3215 UART2 │
              │ - 모터 PID      │  │ - 컴플라이언스  │
              │ - 라인트레이싱  │  │ - NeoPixel/부저 │
              └────────┬────────┘  └────────┬────────┘
                       │                    │
              ┌────────▼────────┐  ┌────────▼────────┐
              │ TB6612FNG +     │  │ STS3215 × 6     │
              │ 2WD JGA25-371   │  │ (데이지 체인)   │
              │ + 5ch IR + ToF  │  │ + 그리퍼        │
              │ + MQ/MLX/Flame  │  │                 │
              └─────────────────┘  └─────────────────┘
```

## Fault Isolation

- ESP32 #2(ARM) 크래시 → ESP32 #1이 모터 정지 + 안전 복귀
- ESP32 #1(AMR) 크래시 → ESP32 #2가 서보 토크 OFF (낙하 방지)
- 화염/LiPo 저전압 → RPi 5가 양쪽 ESP32 동시 STOP

## FSM 미션 흐름

```
IDLE → PATROL → DETECTED → CLASSIFY → APPROACH(WRIST 사전 정렬)
     → GRIP(컴플라이언스 파지)
     → [GRIP 실패: RETRY ×3 → SKIP → PATROL]
     → TRANSPORT → ISOLATE(색상별 격리함)
     → PATROL(계속) 또는 REPORT(완료)
```

## 통신 프로토콜

`<CMD,VALUE,...,CS>\n` (XOR 8-bit checksum, hex 2자리)

자세한 명령 카탈로그는 추후 `docs/protocol.md`에 정리 예정.

## 항법 방식

라인트레이싱(5채널 IR + PID) + ZONE 마커(M1~M4) + VL53L1X 정면 장애물 회피.

> SLAM/Nav2는 v5에서 LiDAR 도입 시 검토. 현 시점에는 결정론적 항법 + Fault Isolation 차별화가 우선.
