# ESP32 #2 (ARM) 펌웨어

담당: 팀원 A

STS3215 직렬 버스 서보 6축 제어 + 컴플라이언스 파지 + NeoPixel/부저.

## 핵심 태스크 (FreeRTOS)
- **Core 0**: Wi-Fi TCP (RPi 5 통신)
- **Core 1**: STS3215 UART2(GPIO 16/17) 서보 태스크 (10ms 폴링)

## 파지 임계값
- 소프트 한계: Load 40% (재시도)
- 하드 한계: Load 80% (즉시 정지)

> 구현 예정 (사전 준비기 4 ~ 6월).
