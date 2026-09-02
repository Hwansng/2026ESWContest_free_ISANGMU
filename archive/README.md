# 폐기된 설계

여기 있는 코드는 **더 이상 쓰지 않는다.** 기록으로만 남긴다.

## firmware_esp32_arm — ESP32 서보 직결 방식

ESP32 한 대가 UART2(GPIO 16/17, 1Mbps)로 STS3215 6축을 데이지 체인 제어하려던 초기 설계다.

**폐기 사유** — STS3215 는 1선 반이중 버스라 마스터가 하나여야 한다.
ESP32 를 서보 3핀 버스에 물리면 USB 어댑터와 충돌한다.
현재는 USB 반이중 어댑터 하나를 마스터로 두고 PC 의 LeRobot 이 양팔 12축을 제어한다.

근거: [`docs/06_firmware/센서_지도.md`](../docs/06_firmware/센서_지도.md) · [`docs/05_arm/로봇암_구축기록.md`](../docs/05_arm/로봇암_구축기록.md)

## firmware_esp32_env_history — ENV 보드 v1~v8

ENV 보드 스케치의 개발 경과다. 실물에 올라간 것은
[`firmware/esp32_env/AMR_state_v11_ino/`](../firmware/esp32_env/AMR_state_v11_ino/) 이고,
3센서 구성인 v9 도 참고용으로 `firmware/esp32_env/` 에 남겼다.

v7·v8 은 [`firmware/tests/`](../firmware/tests/) 의 로직 테스트가 여기 원본을 직접 읽어
대조하므로 지우면 테스트가 깨진다.

`HazardBot_AMR_*_test` 2종은 센서 평균·퓨전 방식을 실험하던 스케치다.

## 배선 가이드 (v9 4센서)

`amr_v9_4sensor_브레드보드_배선_가이드.md` · `amr_v9_4sensor_만능기판_배선_가이드.md` —
v9 3센서 + 거리센서 구성을 전제로 쓴 문서다. **거리센서(VL53L1X)는 최종 구성에서
빠졌으므로** 핀 배정 정본으로 쓰면 안 된다. 정본은
[`docs/06_firmware/README.md`](../docs/06_firmware/README.md).

## 그 밖의 문서

- `HazardBot_시연계획_공유본.md` — 시연 계획 초기본. 확정본은 `docs/03_scenario_demo/`
- `_진우_전달_2026-08-03.md` — ROS2 통합 착수 시점의 인계 문서
- `로봇암_초기계획_2026-07.md` — ESP32 직결 전제의 초기 계획
