# ENV 보드 펌웨어 (ESP32 DevKit V1)

가스·화염 환경 감시, NeoPixel 상태 표시, 부저, RPi 5 와의 TCP 핸드셰이크를 담당하는
ESP32 스케치다. 담당은 **윤강희**.

> 2026-09-03 이전까지 이 스케치는 저장소에 없었다(`강희 로컬`). 대회 제출을 앞두고
> 실물에 올라간 판본을 그대로 옮겼다.

## 무엇을 올리면 되나

| 스케치 | 상태 | 설명 |
| --- | --- | --- |
| [`AMR_state_v11_ino/`](AMR_state_v11_ino/) | ✅ **정본 — 시연에 올라간 판본** | RPi 적응형 가스 핸드셰이크(`GAS_CHECK`) 포함 |
| [`AMR_state_v9_ino/`](AMR_state_v9_ino/) | 참고 | 3센서 구성. 배선 가이드 `firmware/docs/amr_v9_4sensor_*.md` 가 이 판본 기준이다 |
| [`../../archive/firmware_esp32_env_history/`](../../archive/firmware_esp32_env_history/) | 폐기 | v1~v8 · 센서 실험 스케치. 개발 경과 기록용 |

## 빌드 전에 해야 하는 일

### 1. 라이브러리

`AMR_state_v11_ino.ino` 는 프로젝트 자체 헤더 라이브러리 하나를 쓴다.

```
firmware/esp32_env/libraries/AMRDemoScenarioLogic/   →  Arduino/libraries/ 에 복사
```

판정 임계값·상태 지속시간 상수(`GAS_INSPECTION_DURATION_MS` 등)가 전부 이 헤더
[`AMRDemoScenarioLogic.h`](libraries/AMRDemoScenarioLogic/src/AMRDemoScenarioLogic.h) 안에 있다.
시연 시나리오의 판정 규칙을 확인하려면 여기를 보면 된다.

외부 라이브러리는 **쓰지 않는다.** v11 이 `#include` 하는 것은 ESP32 코어
(`WiFi.h` · `ESPmDNS.h` · `WiFiClient.h`)와 위 헤더가 전부다. MQ-2·KY-026 은
아날로그/디지털 핀을 직접 읽고, 부저(TMB12A05)는 GPIO26 을 HIGH 로 두는
액티브 모듈이라 라이브러리가 필요 없다. 가스 채널은 **MQ-2 하나**(GPIO34)다.

> ENV 보드에서 빠진 것: **MLX90614**(온도, 미채택 확정) · **MQ-135**(2026-09-03
> 가스 센서를 MQ-2 하나로 확정). 근거는
> [`docs/06_firmware/센서_지도.md`](../../docs/06_firmware/센서_지도.md) §2.
>
> ToF(VL53L1X)는 ENV 가 아니라 **DRIVE 보드** 소관이고 최종 구성에 들어 있다 —
> [`../esp32_drive/esp32_drive_tcp/`](../esp32_drive/esp32_drive_tcp/) 의 장애물 정지 반사.

### 2. Wi-Fi 접속 정보

`AMR_state_v11_ino.ino` 는 `#include "wifi_secrets.h"` 로 접속 정보를 읽는다.
**이 파일은 저장소에 올리지 않는다** (`.gitignore`).

```
cp AMR_state_v11_ino/wifi_secrets.example.h AMR_state_v11_ino/wifi_secrets.h
# 그리고 SSID · 비밀번호를 실제 값으로 채운다
```

RPi 5 는 AP 모드로 동작하고 ENV 보드는 mDNS(`hazardbot.local`)로 RPi 를 찾는다.
포트는 **8765** 로, DRIVE 보드의 5000 번과 다르다.

## 관련 문서

- 핀 배정·배선 정본 — [`docs/06_firmware/README.md`](../../docs/06_firmware/README.md)
- 센서 선정 근거 — [`docs/06_firmware/센서_지도.md`](../../docs/06_firmware/센서_지도.md)
- v11 가스 핸드셰이크 프로토콜 — [`docs/06_firmware/amr_v11_rpi_adaptive_gas_handoff_2026-08-29.md`](../../docs/06_firmware/amr_v11_rpi_adaptive_gas_handoff_2026-08-29.md)
- 전력 계통 실배선 — [`docs/06_firmware/전력계통_실배선_2026-08-28.md`](../../docs/06_firmware/전력계통_실배선_2026-08-28.md)
