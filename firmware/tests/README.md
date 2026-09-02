# ENV 보드 로직 테스트

`firmware/esp32_env/` 스케치의 상태 판정 로직을 **하드웨어 없이** 검증한다.
`.ino` 를 그대로 돌릴 수는 없으므로, 각 테스트는 스케치의 상태머신을 파이썬으로
재구현해 두고(`*_pure.py`) 두 가지를 함께 확인한다.

1. 재구현한 상태머신이 설계대로 동작하는가 (전이·임계·폴백)
2. **실제 `.ino` 원본이 그 계약을 여전히 지키고 있는가** — 소스를 읽어
   필수 상수·함수가 있는지, 폐기된 센서 계약이 남아 있지 않은지 대조한다

즉 스케치를 고치고 테스트를 안 고치면 `T_SRC_*` 항목이 깨진다.

## 실행

`amr_v8` · `amr_v9` 는 자체 러너를 쓰므로 파일을 직접 실행한다.

```bash
python -m unittest discover -s firmware/tests/amr_v7 -t firmware/tests/amr_v7   # 14건
python firmware/tests/amr_v8/test_amr_v8_pure.py                                # 22건
python firmware/tests/amr_v9/test_amr_v9_pure.py                                # 21건
```

2026-09-03 기준 57건 전부 통과한다.

## 무엇을 보는가

| 폴더 | 대상 | 핵심 검증 |
| --- | --- | --- |
| `amr_v7/` | 폐기된 v7 상태머신 + RPi 측 도구 2종 | 체크섬 계산 · keepalive 타임아웃 |
| `amr_v8/` | 폐기된 v8 | RPi 타임아웃 시 STOP 폴백 · DANGER 연속 검출 요건 |
| `amr_v9/` | `firmware/esp32_env/AMR_state_v9_ino/` | 3센서 계약 · **미납땜 거리센서가 빠졌는지** |

v7·v8 스케치 원본은 [`archive/firmware_esp32_env_history/`](../../archive/firmware_esp32_env_history/) 에 있다.
