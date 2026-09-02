# AMR v10 VL53L1X 통합 설계

## 목표

ESP32 센서 전용 v9를 보존하고, MQ-135·MQ-2·KY-026에 VL53L1X 거리
센서를 추가한 `AMR_state_v10`을 만든다. 납땜 전에는 코드, 자동 테스트,
Raspberry Pi parser 호환성, Arduino 컴파일까지 완료한다. 실제 I2C 통신과
거리 임계값 검증은 헤더 납땜 후 수행한다.

v10도 센서 상태 판단만 담당한다. 모터, TB6612, 라인 트레이싱, 서보,
그리퍼 코드는 추가하지 않는다. 배터리 전압은 실제 분압 회로가 연결될
때까지 기존 `12.0V` 벤치 주입값이며 실측값으로 표현하지 않는다.

## 기준 버전과 파일 경계

- 기준 펌웨어: `Arduino/AMR_state_v9_ino/AMR_state_v9_ino.ino`
- 새 펌웨어: `Arduino/AMR_state_v10_ino/AMR_state_v10_ino.ino`
- 새 논리 테스트: `tests/amr_v10/test_amr_v10_pure.py`
- 수정할 parser: `tools/rpi_amr_parser.py`
- 수정할 parser 테스트: `tests/amr_v7/test_rpi_amr_parser.py`
- 사용 라이브러리: `Arduino/libraries/Adafruit_VL53L1X`

v9 소스와 v9 테스트는 수정하지 않는다. v10은 v9의 두 MQ 센서 독립 보정,
180초 히터 안정화, KY-026 LOW active 판정, RPi keepalive, 상태와 fault
코드를 그대로 계승한다.

## 하드웨어 인터페이스

VL53L1X는 다음 네 선만 사용한다.

| VL53L1X | ESP32 |
|---|---|
| VIN/VCC | 3V3 |
| GND | GND |
| SDA | GPIO21 |
| SCL | GPIO22 |

GPIO1/INT와 XSHUT은 연결하지 않는다. 기본 I2C 주소는 `0x29`, 측정 timing
budget은 `50ms`다. ESP32에서 `Wire.begin(21, 22)`로 버스를 시작한다.

## 거리 센서 어댑터

펌웨어는 `Wire`와 `Adafruit_VL53L1X`를 사용한다. `setup()`에서 I2C와
센서를 한 번 초기화하고 ranging을 시작한다. 초기화, ranging 시작 또는
timing budget 설정 중 하나라도 실패하면 무한 재시도하거나 부팅을 막지
않고 거리 센서를 즉시 미준비 상태로 기록한다.

거리 읽기는 기존 300ms 센서 주기 안에서 비차단 방식으로 수행한다.
`dataReady()`가 참일 때만 `distance()`를 호출하고, 읽은 뒤
`clearInterrupt()`를 호출한다. 정상 거리 범위는 `30..4000mm`다.

거리 채널은 다음 상태를 별도로 가진다.

- `initialized`: 초기화와 ranging 준비 성공 여부
- `lastValidDistanceMm`: 마지막 정상 거리, 초기값 `-1`
- `errorCount`: 연속 읽기 실패 횟수
- `valid`: 현재 안전 평가에 사용할 수 있는지 여부

부팅 초기화 실패는 즉시 `valid=false`다. 정상 초기화 후 일시적인 읽기
실패 1~2회에는 마지막 정상 거리를 유지한다. 3회 연속 실패하면
`valid=false`로 전환한다. 다음 정상 측정이 들어오면 오류 횟수를 0으로
초기화하고 자동 복구한다.

## 거리 위험 판정

거리 임계값은 실제 장착 시험 후 쉽게 바꿀 수 있도록 이름 있는 상수로
분리한다.

| 조건 | 진입 | 유지/해제 경계 |
|---|---:|---:|
| WARNING | `distance <= 500mm` | `distance <= 550mm`이면 유지 |
| DANGER | `distance <= 200mm` | `distance <= 250mm`이면 유지 |

WARNING은 한 번의 정상 측정으로 진입한다. 거리 DANGER는 MQ 위험과 같은
`dangerCount` 지속 조건을 사용해 3회 연속 확인 후 진입한다. 불꽃 감지는
기존처럼 즉시 DANGER 조건이다. DANGER 상태에서 거리가 250mm를 넘고 다른
위험 조건도 없으면 WARNING 또는 SAFE로 내려간다.

## 통합 안전 우선순위

상태 평가는 다음 순서를 유지한다.

1. Emergency Stop
2. 3S LiPo `9.9V` cutoff
3. MQ-135, MQ-2 또는 VL53L1X 미준비/오류
4. Raspberry Pi 통신 `3000ms` timeout
5. KY-026, MQ 또는 거리 DANGER 조건
6. MQ 또는 거리 WARNING 조건
7. SAFE

센서 오류는 `STATE_SENSOR_ERROR`, `FAULT_SENSOR`,
`ACTION_STOP_MOTION`으로 매핑한다. v10에도 실제 모터 출력은 없고
`applyAmrAction()`은 상태별 동작 의도만 유지한다.

MQ 180초 안정화 중에는 기존처럼 MQ 미준비가 우선하여 SENSOR_ERROR다.
거리 센서가 정상이어도 이 fail-safe를 우회하지 않는다.

## v10 telemetry

v10 메시지는 v9 payload 끝에 거리 필드를 하나 추가한다.

```text
<SENS,mq135,mq2,flame,battCv,stateCode,actionCode,faultCode,distanceMm,checksum>
```

- `mq135`, `mq2`: 각 MQ 이동평균 ADC 값
- `flame`: KY-026 감지 시 1, 아니면 0
- `battCv`: 벤치 배터리 주입값의 centivolt 표현
- `stateCode`, `actionCode`, `faultCode`: 기존 v9 코드
- `distanceMm`: 마지막 정상 거리, 정상값이 없으면 `-1`
- `checksum`: checksum 앞 payload 전체 ASCII 합 modulo 256의 10진수

Raspberry Pi parser는 v9의 8개 payload 필드와 v10의 9개 payload 필드를
모두 허용한다. v9에서는 거리 결과를 제공하지 않고, v10에서는
`distance_mm`을 정수로 제공한다. 잘못된 필드 수와 checksum은 계속
거부한다.

## 자동 테스트

`tests/amr_v10/test_amr_v10_pure.py`는 v9 논리 모델을 복사해 v10 요구만
추가한다. 다음 동작을 검증한다.

- 700mm SAFE, 350mm WARNING
- 150mm 3회 연속 후 DANGER
- WARNING 500/550mm 및 DANGER 200/250mm 히스테리시스
- 초기화 실패 즉시 SENSOR_ERROR
- 읽기 실패 1~2회 마지막 정상값 유지, 3회째 SENSOR_ERROR
- 정상 거리 수신 후 오류 자동 복구
- `30..4000mm` 범위 검증
- E-Stop, LiPo, 센서 오류, RPi timeout, 위험 순서
- MQ·불꽃·거리 복합 위험과 기존 180초 MQ 보정
- v10 telemetry 필드 순서와 checksum
- v10 소스의 버전 표식, I2C 핀, 주소, timing budget, 비차단 API 사용
- v10에 모터 구동 코드가 없는지 확인

parser 테스트에는 v9와 v10 정상 프레임, v10 checksum 오류, v10 필드 수
오류를 추가한다. v7·v8·v9 테스트를 함께 실행해 이전 버전이 바뀌지 않았음을
확인한다.

## 납땜 전 완료 조건

- v10 소스와 테스트가 별도 폴더에 존재한다.
- v9 소스와 테스트는 변경되지 않는다.
- v10 및 전체 회귀 테스트가 통과한다.
- Raspberry Pi parser가 v9와 v10을 모두 처리한다.
- ESP32용 Adafruit VL53L1X 라이브러리를 포함해 Arduino 컴파일이 성공한다.
- 실제 보드에는 v10을 업로드하지 않는다. 미연결 거리 센서 때문에 의도된
  SENSOR_ERROR가 발생하므로, v9를 유지해 현재 3센서 시험 상태를 보존한다.

## 납땜 후 실물 검증

1. 전원을 끄고 3V3, GND, SDA21, SCL22를 연결한다.
2. I2C 주소 `0x29`와 `[VL53L1X] READY`를 확인한다.
3. keepalive를 보내면서 약 700mm에서 SAFE를 확인한다.
4. 약 350mm에서 WARNING을 확인한다.
5. 약 150mm를 3회 이상 유지해 DANGER를 확인한다.
6. 200/250mm 및 500/550mm 경계에서 진동하지 않는지 확인한다.
7. SDA 또는 SCL을 분리해 3회 뒤 SENSOR_ERROR가 되는지 확인한다.
8. 다시 연결하고 리셋해 정상 복구와 네 센서 동시 갱신을 확인한다.
9. 실측 오차와 장착 위치를 바탕으로 거리 상수만 조정한다.

라이터 불꽃이나 가연성 가스를 VL53L1X 시험에 사용하지 않는다. 거리 시험은
불연성 평판을 사용하고 MQ와 KY-026은 깨끗한 공기 상태를 유지한다.
