# AMR v9 3센서 실기 통합 설계

## 목표

ESP32 센서 전용 벤치 구성에서 MQ-135, MQ-2, KY-026 세 센서를 동시에
연결하고 읽는 `Arduino/AMR_state_v9_ino/AMR_state_v9_ino.ino`를 만든다.
기존 v8 파일은 보존한다. 납땜되지 않은 VL53L1X 거리 센서는 v9의 초기화,
판정, 오류 처리 및 메시지에서 모두 제외한다.

이번 v9의 완료 범위는 세 환경 센서의 동시 입력, 센서 융합 상태 판정,
안전한 오류 처리, Raspberry Pi용 telemetry 및 실제 ESP32 벤치 검증이다.
모터, TB6612, 라인트레이싱, 거리 센서와 실제 배터리 분압 측정은 포함하지
않는다.

## 하드웨어 전제

- 보드: DOIT ESP32 DEVKIT V1
- ESP32는 USB로 전원과 Serial 통신을 연결한다.
- MQ-135와 MQ-2 히터는 별도 안정화 5V 전원에서 공급한다.
- 외부 5V 전원은 1A 이상을 사용하고 MQ 모듈 VCC에만 연결한다.
- 외부 5V와 ESP32 USB를 동시에 ESP32 VIN 또는 5V 핀에 연결하지 않는다.
- 외부 전원 GND, ESP32 GND 및 세 센서 GND는 공통으로 연결한다.
- MQ 모듈은 `VCC`, `GND`, `AO`, `DO` 핀이 있는 일반 모듈을 기준으로 한다.

두 MQ 센서는 각각 최대 약 950mW의 히터 전력을 사용할 수 있으므로 ESP32
보드의 USB 5V 핀에서 두 히터를 함께 공급하지 않는다.

## 확정 배선

### MQ-135

| MQ-135 | 연결 |
|---|---|
| VCC | 외부 안정화 5V |
| GND | 공통 GND |
| AO | 10kΩ을 거쳐 GPIO34 쪽 분압 중점 |
| DO | 미연결 |

GPIO34 분압은 다음과 같이 연결한다.

```text
MQ-135 AO ── 10kΩ ──┬── GPIO34
                     └── 20kΩ ── GND
```

### MQ-2

| MQ-2 | 연결 |
|---|---|
| VCC | 외부 안정화 5V |
| GND | 공통 GND |
| AO | 10kΩ을 거쳐 GPIO35 쪽 분압 중점 |
| DO | 미연결 |

GPIO35 분압은 다음과 같이 연결한다.

```text
MQ-2 AO ── 10kΩ ──┬── GPIO35
                   └── 20kΩ ── GND
```

각 10kΩ/20kΩ 분압은 최대 5V AO를 약 3.33V로 낮춘다. GPIO34와 GPIO35는
Wi-Fi와 함께 사용할 수 있는 ADC1 입력 전용 핀이므로 이 용도에 적합하다.

### KY-026

| KY-026 | 연결 |
|---|---|
| VCC | ESP32 3V3 |
| GND | 공통 GND |
| DO | GPIO27 |
| AO | 미연결 |

KY-026을 3.3V로 구동해 DO의 HIGH 전압이 ESP32 입력 허용 범위를 넘지 않게
한다. 기존 동작과 같이 `LOW`를 불꽃 감지로 해석한다.

## 소프트웨어 구조

v9는 v8의 단일 스케치 구조와 안전 우선순위를 유지하되 세 센서별 입력과
고장 상태를 분리한다.

- `MQ135_PIN = 34`
- `MQ2_PIN = 35`
- `FLAME_PIN = 27`
- MQ-135와 MQ-2는 각각 별도의 이동평균 버퍼, 합계, 인덱스 및 오류
  카운터를 가진다.
- 시작 시 이동평균 버퍼를 0으로 채우지 않는다. 첫 실제 ADC 값을 버퍼
  전체에 채워 v8의 초기 저평균과 가짜 센서 오류를 방지한다.
- ADC 평균이 `1..4094` 범위를 연속 3회 벗어나면 해당 MQ 센서 오류로
  판정한다.
- 한 센서의 유효한 값이 다른 센서의 오류 카운터를 초기화하지 않는다.
- KY-026은 디지털 LOW active 입력으로 읽는다.

## MQ 예열과 기준값 보정

MQ 계열 센서는 절대 ADC 값만으로 가스 종류나 ppm을 확정하지 않는다. v9의
MQ 값은 시연용 상대 위험 신호이며 인증된 가스 농도 측정값이 아니다.

새 센서는 제조사 권장에 따라 최초 사용 전에 48시간 이상 에이징한다. 일반
실기 확인 때는 MQ 히터를 최소 20분 예열한 뒤 깨끗한 공기에서 ESP32 RESET을
눌러 기준값을 다시 잡는다.

RESET 후 180초 동안 ADC와 센서 출력이 안정되기를 기다린다. 이 구간에는
Serial에 `SETTLING`을 출력한다. 180초가 지나면 이동평균 버퍼를 그 시점의
실제 값으로 다시 채우고, 이후 각 MQ 센서의 유효한 10개 평균값을 기준값으로
사용한다. 기준값 수집이 끝나기 전에는 안전하게 `STATE_SENSOR_ERROR`와
`ACTION_STOP_MOTION`을 유지하고 Serial에 `CALIBRATING`을 출력한다.

180초 안정화는 실제 보드의 USB 전원 재인가 뒤 짧은 보정으로 MQ-2 기준이
155로 잡힌 뒤 실측값이 244까지 상승하고, 이후 MQ-135와 MQ-2가 각각 86과
121 부근까지 함께 안정된 현상을 반영한다. 마지막 58초 구간의 첫 20개와
마지막 20개 평균 차이는 MQ-135가 -4, MQ-2가 -1.4였다.

정규화 상승률은 다음 식으로 계산한다.

```text
risePercent = max(0, (average - baseline) * 100 / baseline)
```

초기 시연 기준은 두 센서 모두 다음과 같이 사용한다.

- WARNING 진입: 기준값보다 20% 이상 상승
- WARNING 해제: 기준값보다 15% 미만 상승
- DANGER 진입: 기준값보다 50% 이상 상승
- DANGER 해제: 기준값보다 40% 미만 상승

기준값이 유효 ADC 범위를 벗어나거나 위험 판정 여유가 없을 정도로 포화된
경우 정상 보정으로 인정하지 않고 센서 오류를 유지한다. 실측 로그에서 정상
공기 변동이 20%를 넘으면 하드웨어 전원·접지·예열 상태를 먼저 수정하며,
검증 근거 없이 임계값만 높이지 않는다.

## 상태 판정과 안전 우선순위

상태 판정 순서는 다음과 같이 고정한다.

1. Emergency Stop 활성
2. 3S LiPo 9.9V 이하
3. MQ-135 또는 MQ-2 센서 오류/미보정
4. Raspberry Pi 통신 3000ms timeout
5. KY-026 불꽃 감지 또는 MQ 위험 조건
6. MQ 경고 조건
7. SAFE

이번 벤치 구성에는 실제 E-Stop과 배터리 분압을 연결하지 않는다.
E-Stop 입력은 `INPUT_PULLUP`의 비활성 상태로 유지한다. 배터리 전압 입력은
v8의 테스트 주입값을 유지하므로 실제 LiPo 측정으로 표시하지 않는다.
9.9V cutoff 우선순위는 순수 로직 테스트로 검증한다.

판정 동작은 다음과 같다.

- KY-026 불꽃 감지는 즉시 DANGER 조건으로 취급한다.
- MQ-135 또는 MQ-2의 DANGER 조건은 3회 연속 확인 후 DANGER로 진입한다.
- 어느 한 MQ 센서라도 WARNING 조건이면 WARNING으로 진입한다.
- DANGER와 WARNING에는 별도의 해제 기준을 사용해 경계값 진동을 줄인다.
- 센서 오류, E-Stop, LiPo cutoff 및 RPi timeout은 가스·불꽃 상태보다
  우선한다.

## 메시지 형식

v9 telemetry는 다음 형식을 사용한다.

```text
<SENS,mq135,mq2,flame,battCv,stateCode,actionCode,faultCode,checksum>
```

- `mq135`: MQ-135 이동평균 ADC 값
- `mq2`: MQ-2 이동평균 ADC 값
- `flame`: KY-026 감지 시 1, 그 외 0
- `battCv`: 기존 v8 호환용 배터리 센티볼트 필드. 벤치에서는 테스트 주입값
- `stateCode`: SAFE=0, WARNING=1, DANGER=2, STOP=3, SENSOR_ERROR=4
- `actionCode`: NORMAL_MOTION=0, LIMITED_MOTION=1, STOP_MOTION=2
- `faultCode`: OK=0, ESTOP=1, LIPO=2, SENSOR=3, RPI_TIMEOUT=4, HAZARD=5
- `checksum`: `SENS`부터 `faultCode`까지 payload의 ASCII 합 modulo 256을
  10진수로 표현

VL53L1X와 `distanceMm` 필드는 포함하지 않는다. 기존 v8 parser에 필드가
추가되므로 Raspberry Pi parser와 테스트도 v9 형식에 맞게 갱신한다.

## 오류 처리

- MQ-135와 MQ-2의 오류 카운터를 독립적으로 유지한다.
- 어느 한 MQ 센서라도 연속 3회 유효 범위를 벗어나면
  `STATE_SENSOR_ERROR`, `FAULT_SENSOR`, `ACTION_STOP_MOTION`으로 전환한다.
- 이후 해당 센서가 연속으로 정상 값을 제공하면 오류 카운터를 초기화하고
  보정 상태가 유효할 때 정상 평가를 재개한다.
- Serial debug에는 두 ADC 평균, 두 기준값, 두 상승률, KY-026 상태, 각 센서
  유효성, 상태, 행동, fault를 모두 출력한다.
- 거리 센서 미연결은 오류가 아니다. v9에서 거리 센서를 초기화하거나 읽지
  않기 때문이다.

## 테스트와 실기 검증

### 자동 테스트

새 `tests/amr_v9/test_amr_v9_pure.py`에서 다음을 검증한다.

- 두 MQ 센서 이동평균의 독립성 및 첫 샘플 초기화
- 리셋 후 180초 동안 기준값을 확정하지 않고, 안정화 완료 시 이동평균을
  현재값으로 다시 채우는지 확인
- 개별 센서 오류 3회 누적과 회복
- 기준값 보정 전 fail-safe 상태
- 20%/15% WARNING hysteresis
- 50%/40% DANGER hysteresis와 3회 지속 조건
- KY-026 LOW active DANGER
- `E-Stop > 9.9V cutoff > sensor error > RPi timeout > hazard` 우선순위
- v9 메시지 필드 순서와 ASCII 합 modulo 256 checksum
- v8 회귀 테스트가 그대로 통과하는지 확인

### 컴파일 검증

저장소의 Arduino 라이브러리와 ESP32 보드 설정으로 v9 스케치를 컴파일한다.
거리 센서 라이브러리에 의존하지 않는지 소스와 컴파일 결과로 확인한다.

### 실제 보드 검증

1. 전원을 넣기 전에 각 AO 분압 중점과 GND 사이의 20kΩ 연결을 확인한다.
2. MQ 외부 5V와 ESP32 USB 5V/VIN이 직접 연결되지 않았는지 확인한다.
3. 세 센서 GND가 ESP32 GND와 공통인지 확인한다.
4. MQ 센서를 예열하고 RESET 후 두 기준값 보정 완료를 확인한다.
5. MQ-135와 MQ-2 값이 모두 `1..4094` 안에서 독립적으로 갱신되는지 확인한다.
6. KY-026에 실제 불꽃 대신 적외선 리모컨을 사용해 LOW active 변화를 먼저
   확인한다.
7. Raspberry Pi keepalive 도구로 timeout을 해제하고 SAFE, WARNING,
   DANGER 판정 및 v9 메시지를 확인한다.
8. MQ 센서 AO 한 선을 한 번에 하나씩 분리해 각 센서가 독립적으로
   SENSOR_ERROR를 만드는지 확인한다.
9. 테스트 중 실제 화염, 부탄 방출, 인화성 액체 분무는 사용하지 않는다.

## 완료 조건

- 파일명과 시작 배너가 모두 `AMR_state_v9`를 나타낸다.
- v9에는 MQ-135, MQ-2, KY-026만 활성 센서로 존재한다.
- 거리 센서 초기화, 판정, 메시지 필드가 없다.
- v9와 v8 순수 로직 테스트가 모두 통과한다.
- Arduino 컴파일이 경고 없이 성공한다.
- 실제 Serial에서 세 센서 값이 동시에 갱신된다.
- 실제 KY-026 입력 변화와 각 MQ 센서 연결 해제 오류가 독립적으로 확인된다.
- 실측하지 않은 배터리 값과 가스 ppm을 실제 측정값으로 주장하지 않는다.
