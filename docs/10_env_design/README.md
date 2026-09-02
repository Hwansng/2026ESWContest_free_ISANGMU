# ENV 보드 · 전력 · 구동부 설계 기록 (윤강희)

ENV 보드 펌웨어와 전력·모터 계통을 정하면서 남긴 **설계 근거** 문서다.
결론만 필요하면 정본을 보면 된다 — 여기는 "왜 그렇게 정했나"가 남아 있는 쪽이다.

| 문서 | 내용 |
| --- | --- |
| [`power_requirements.md`](power_requirements.md) | 부하별 소비전류 산정 → 레귤레이터 용량 결정 |
| [`lipo_voltage_measurement_plan.md`](lipo_voltage_measurement_plan.md) | 3S LiPo 전압 분압 측정 계획 |
| [`motor_driver_selection_guide.md`](motor_driver_selection_guide.md) | L298N 대신 TB6612FNG 를 고른 근거 |
| [`motor_encoder_wiring_plan.md`](motor_encoder_wiring_plan.md) | JGA25-371 엔코더 배선 |
| [`amr_v7_safety_flow.md`](amr_v7_safety_flow.md) | v7 안전 상태 전이 |
| [`rpi5_state_response_policy.md`](rpi5_state_response_policy.md) | RPi 가 ENV 상태코드에 어떻게 반응하는지 |
| [`rpi5_amr_v7_checklist.md`](rpi5_amr_v7_checklist.md) | RPi ↔ ENV 연동 점검 목록 |

## specs / plans

설계(spec) → 구현계획(plan) 순으로 짝지어 남긴 기록이다.

| 주제 | 설계 | 구현계획 |
| --- | --- | --- |
| 만능기판 배선 | [`specs/2026-07-28-amr-perfboard-wiring-design.md`](specs/2026-07-28-amr-perfboard-wiring-design.md) | — |
| VL53L1X 통합 | [`specs/2026-07-31-vl53l1x-code-first-design.md`](specs/2026-07-31-vl53l1x-code-first-design.md) | [`plans/2026-07-31-vl53l1x-code-first-implementation.md`](plans/2026-07-31-vl53l1x-code-first-implementation.md) |
| v9 3센서 | [`specs/2026-08-03-amr-v9-three-sensor-design.md`](specs/2026-08-03-amr-v9-three-sensor-design.md) | [`plans/2026-08-03-amr-v9-three-sensor-implementation.md`](plans/2026-08-03-amr-v9-three-sensor-implementation.md) |
| v10 VL53L1X | [`specs/2026-08-03-amr-v10-vl53l1x-design.md`](specs/2026-08-03-amr-v10-vl53l1x-design.md) | [`plans/2026-08-03-amr-v10-vl53l1x-implementation.md`](plans/2026-08-03-amr-v10-vl53l1x-implementation.md) |
| 납땜 설명서 | [`specs/2026-08-07-hazardbot-perfboard-soldering-manual-design.md`](specs/2026-08-07-hazardbot-perfboard-soldering-manual-design.md) | [`plans/2026-08-07-hazardbot-perfboard-soldering-manual-implementation.md`](plans/2026-08-07-hazardbot-perfboard-soldering-manual-implementation.md) |

> **VL53L1X(v10)는 최종 구성에서 빠졌다.** 설계·구현계획까지 갔다가 납땜 단계에서
> 접었다. 미채택 근거는 [`../06_firmware/센서_지도.md`](../06_firmware/센서_지도.md) 를,
> 실제 올라간 판본은 [`../../firmware/esp32_env/`](../../firmware/esp32_env/) 를 본다.

## 정본은 어디에

- 핀 배정·배선 확정값 → [`../06_firmware/README.md`](../06_firmware/README.md)
- 전력 계통 실배선 → [`../06_firmware/전력계통_실배선_2026-08-28.md`](../06_firmware/전력계통_실배선_2026-08-28.md)
- 납땜 설명서(완성본 PDF) → [`../08_reference/HazardBot_만능기판_납땜_설명서.pdf`](../08_reference/HazardBot_만능기판_납땜_설명서.pdf)
