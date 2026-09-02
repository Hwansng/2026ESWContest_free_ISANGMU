# VL53L1X 코드 우선 통합 설계

## 목표

현재 ESP32 #1 AMR의 안정 동작 버전인 v8을 보존하면서, 새
`Arduino/AMR_state_v9_ino/AMR_state_v9_ino.ino`에 Adafruit VL53L1X
거리 센서를 추가한다. 실제 센서 납땜 전에는 순수 로직 테스트로 거리 위험
판정, 오류 처리, 메시지와 체크섬을 검증하고, 납땜 후에는 실제 I2C 통신만
추가 확인한다.

이번 단계는 VL53L1X 통합만 포함한다. MQ-2는 보유 모듈의 핀 표기와 아날로그
출력 전압을 확인한 다음 별도 단계에서 같은 v9에 추가한다.

## 범위와 제약

- 작업 대상은 ESP32 #1 AMR뿐이다.
- ESP32 #2 ARM, 로봇팔, 그리퍼, 부저 및 다른 출력장치 로직은 추가하지 않는다.
- 기존 `Arduino/AMR_state_v8_ino/AMR_state_v8_ino.ino`는 수정하지 않는다.
- 기존 MQ-135, KY-026, Emergency Stop, 3S LiPo `9.9V` cutoff 및 RPi timeout
  안전 로직을 유지한다.
- Emergency Stop과 LiPo cutoff는 거리 위험보다 높은 우선순위를 유지한다.
- 메시지는 `<CMD,...,CS>\n` 외곽 형식과 ASCII 합 modulo 256 체크섬 방식을
  유지한다.
- 실제 하드웨어가 없는 상태를 정상 측정값으로 가장하지 않는다.

## 하드웨어 연결

Adafruit VL53L1X 브레이크아웃의 6핀 헤더를 납땜한 뒤 다음 네 선만 연결한다.

| VL53L1X | ESP32 #1 |
|---|---|
| VIN | 3V3 |
| GND | GND |
| SCL | GPIO22 |
| SDA | GPIO21 |
| GPIO | 연결하지 않음 |
| XSHUT | 연결하지 않음 |

Adafruit 브레이크아웃에 SDA와 SCL 풀업 저항이 있으므로 외부 I2C 풀업 저항은
추가하지 않는다. 센서의 기본 I2C 주소는 `0x29`를 사용한다.

## 소프트웨어 구조

v9는 v8의 단일 스케치 구조를 유지한다. 대규모 리팩터링이나 별도 태스크는
추가하지 않는다.

추가되는 책임은 다음과 같다.

- `Wire.begin(21, 22)`로 I2C 버스를 초기화한다.
- 저장소에 이미 포함된 `Adafruit_VL53L1X` 라이브러리로 주소 `0x29`의 센서를
  초기화한다.
- 센서 초기화 실패로 `setup()`을 무한 대기시키지 않는다.
- 새 거리값이 준비되면 mm 단위로 읽고, 읽기 실패 또는 준비 timeout이면
  무효 값으로 처리한다.
- 거리 센서 오류 횟수를 MQ-135 오류 횟수와 별도로 관리해 Fault Isolation을
  유지한다.
- 연속 3회 거리 읽기 실패 시 `STATE_SENSOR_ERROR`와
  `ACTION_STOP_MOTION`으로 전환한다.
- 센서가 미연결인 실제 펌웨어 실행에서는 오류 상태가 명시적으로 출력되며,
  가상값을 실제 측정값처럼 송신하지 않는다.

## 거리 위험 판정

실내 영상 시연에 적합하도록 다음 기준을 사용한다.

- `distanceMm > 500`: 거리 기준 SAFE
- `200 < distanceMm <= 500`: 거리 기준 WARNING
- `30 <= distanceMm <= 200`: 거리 기준 DANGER 후보
- `distanceMm < 30`, `distanceMm > 4000` 또는 읽기 실패: 무효 측정

경계값의 진동을 줄이기 위해 다음 이탈 기준을 사용한다.

- WARNING 해제: `distanceMm > 550`
- DANGER 해제: `distanceMm > 250`

DANGER 진입은 기존 정책과 동일하게 3회 연속 위험 조건을 요구한다. 불꽃
감지도 기존 v8과 동일하게 매 측정 주기의 위험 조건에 포함한다. 거리 센서 오류는 3회 연속 실패
전까지 마지막 유효 거리값을 유지하며, 3회째 실패부터 센서 오류 안전 상태로
전환한다.

## 상태 평가 우선순위

상태 평가는 다음 순서를 유지한다.

1. Emergency Stop
2. 3S LiPo `9.9V` cutoff
3. 센서 오류(MQ-135 또는 VL53L1X)
4. RPi 통신 timeout
5. 불꽃, 가스 또는 근거리 DANGER
6. 가스 또는 거리 WARNING
7. SAFE

거리 센서가 추가되어도 기존 상위 안전 조건은 약화되지 않는다.

## 메시지 형식

v9에서는 거리값을 기존 필드 뒤에 추가한다.

```text
<SENS,gas,flame,battCv,stateCode,actionCode,faultCode,distanceMm,checksum>
```

- `distanceMm`: 마지막 유효 VL53L1X 거리값
- 유효 거리값을 한 번도 얻지 못한 경우: `-1`
- `checksum`: 마지막 쉼표 앞 payload 전체의 ASCII 합 modulo 256

기존 7개 payload 필드의 순서는 유지하고 거리값만 뒤에 추가한다. 기존 RPi
파서는 v9 메시지에 맞춰 별도 갱신이 필요하지만, RPi 실물이 없는 현재
단계에서는 ESP32 송신 문자열과 순수 로직 테스트를 우선한다.

MQ-2를 추가하는 다음 단계에서는 `distanceMm` 뒤에 `mq2Raw`를 추가하고
체크섬을 다시 계산한다.

## 오류 처리

- I2C 초기화 실패: 거리 센서를 사용할 수 없는 상태로 기록하고 나머지 센서
  읽기와 Serial 출력은 계속한다.
- 거리 데이터 준비 timeout: 실패 횟수를 증가시키되 프로그램을 blocking하지
  않는다.
- 3회 연속 실패: `FAULT_SENSOR`, `STATE_SENSOR_ERROR`,
  `ACTION_STOP_MOTION`.
- 이후 유효 거리값을 얻으면 거리 오류 횟수를 초기화하고 정상 평가를 재개한다.
- RPi가 없는 실제 보드 테스트에서는 기존 정책에 따라 3초 뒤
  `FAULT_RPI_TIMEOUT` 정지가 발생한다. 이 경우에도 debug 출력으로 거리값은
  확인할 수 있다.

## 하드웨어 없는 검증

`tests/amr_v9/test_amr_v9_pure.py`에서 다음을 확인한다.

- 700mm에서 거리 기준 SAFE
- 350mm에서 WARNING
- 150mm가 3회 연속 입력되면 DANGER
- DANGER 상태가 250mm 이하에서 유지되고 250mm 초과에서 해제됨
- 3회 연속 무효 입력이면 SENSOR_ERROR와 정지
- Emergency Stop과 LiPo cutoff가 거리 판정보다 우선함
- 기존 MQ-135와 KY-026 판정이 유지됨
- `distanceMm`가 포함된 메시지 필드 순서와 체크섬
- 센서 미연결을 나타내는 `-1`이 정상 거리로 판정되지 않음

## 납땜 후 최소 검증

1. I2C 주소 `0x29`가 검출되는지 확인한다.
2. 약 700mm, 350mm, 150mm 거리에서 Serial debug 값을 확인한다.
3. 물체 제거, 센서 가림 또는 배선 분리 시 SENSOR_ERROR 안전 전환을 확인한다.
4. MQ-135와 KY-026 값이 기존처럼 계속 갱신되는지 확인한다.

투명, 검은색 또는 반사가 강한 물체보다 밝은 무광 골판지 상자를 시연
표적으로 사용한다.
