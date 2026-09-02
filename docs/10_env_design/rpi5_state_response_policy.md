# RPi 5 AMR 상태 대응 정책

## 목적

이 문서는 Raspberry Pi 5가 ESP32 #1 AMR v7에서 받은 상태 메시지에 어떻게 대응해야 하는지 정리한다. ESP32 #1은 센서와 안전 조건을 바탕으로 AMR 상태를 판단하고, RPi 5는 그 결과를 중앙에서 해석해 전체 시스템 동작을 중재한다.

## 기본 원칙

- RPi 5는 ESP32 #1과 ESP32 #2를 각각 통신한다.
- ESP32 #1과 ESP32 #2가 직접 통신하는 구조를 만들지 않는다.
- ESP32 #1이 보내는 checksum이 맞는 메시지만 신뢰한다.
- `STOP`, `DANGER`, `SENSOR_ERROR`는 항상 안전 우선 상태로 처리한다.
- RPi 5는 ESP32 #1 AMR 상태를 ARM 동작 허용 여부 판단에도 반영할 수 있다.

## 입력 메시지

ESP32 #1 AMR v7은 다음 형식으로 상태를 전송한다.

```text
<CMD,STATE=SAFE,GAS=42,FLAME=0,BAT=12.00,56>
```

RPi 5는 먼저 다음을 확인한다.

1. `<`, `>` 프레임이 있는가?
2. checksum이 맞는가?
3. `STATE`, `GAS`, `FLAME`, `BAT` 필드가 있는가?
4. 숫자 필드가 정상 변환되는가?

파싱 테스트는 다음 명령으로 확인할 수 있다.

```bash
python tools/rpi_amr_parser.py "<CMD,STATE=SAFE,GAS=42,FLAME=0,BAT=12.00,56>"
```

## 상태별 대응 정책

| ESP32 #1 상태 | RPi 5 해석 | 권장 대응 |
|---|---|---|
| `SAFE` | 정상 감시 상태 | AMR 정상 운용 허용 |
| `WARNING` | 주의 상태 | 감속, 로그 기록, 사용자 표시 |
| `DANGER` | 위험 상태 | AMR 정지 유지, ARM 동작 제한 검토, 경고 표시 |
| `STOP` | 안전 정지 상태 | AMR 정지 유지, 원인 확인 전 재개 금지 |
| `SENSOR_ERROR` | 센서 fault 상태 | AMR 정지 유지, 센서/배선 점검 요구 |

## 상태별 세부 행동

### SAFE

RPi 5는 AMR이 정상 감시 상태라고 판단한다. 주행 명령, 경로 계획, ARM 협업 동작을 허용할 수 있다. 단, keepalive는 계속 보내야 한다.

### WARNING

가스 수치가 주의 기준에 들어온 상태다. RPi 5는 감속, 로그 기록, UI 표시 같은 완화 조치를 수행한다. 즉시 전체 정지를 요구하지는 않지만, 상태가 DANGER로 올라갈 가능성을 고려한다.

### DANGER

flame 감지 또는 gas danger 조건이 충족된 상태다. RPi 5는 AMR 정지를 유지하고, ARM 동작도 위험 환경에서 계속 수행해도 되는지 제한해야 한다. 사용자에게 경고를 표시하고 상태 회복 전 자동 재개를 피한다.

### STOP

Emergency Stop, LiPo cutoff, RPi timeout 같은 안전 정지 상태다. RPi 5는 AMR이 움직이지 않도록 유지해야 한다. STOP 원인이 해소되기 전에는 주행 명령을 보내지 않는다.

### SENSOR_ERROR

MQ-135 센서값이 유효 범위를 벗어난 상태다. RPi 5는 이 상태를 단순 정지가 아니라 fault로 기록한다. 센서 배선, 전원, ADC 입력 문제를 점검해야 한다.

## 통신 timeout 정책

RPi 5는 ESP32 #1로 주기적으로 keepalive를 보낸다.

```text
<CMD,PING,76>
```

ESP32 #1은 checksum이 맞는 framed 메시지를 받아야 timeout을 해제한다. RPi 5 쪽 권장 keepalive 주기는 `1초`다. ESP32 #1의 timeout 기준은 현재 `3초`다.

## 재개 조건

정지 상태에서 자동 재개할지 여부는 상태별로 다르게 본다.

| 상태 | 자동 재개 권장 여부 |
|---|---|
| `WARNING -> SAFE` | 가능 |
| `DANGER -> SAFE` | 신중. 사용자 확인 권장 |
| `STOP -> SAFE` | 원인 확인 후 재개 |
| `SENSOR_ERROR -> SAFE` | 센서 점검 후 재개 |

## 로그로 남길 항목

RPi 5는 상태 메시지를 받을 때 다음 값을 기록하는 것이 좋다.

- 수신 시간
- 상태 `STATE`
- 가스 값 `GAS`
- flame 값 `FLAME`
- 배터리 값 `BAT`
- checksum 검증 결과
- 상태 변화 여부

## 다음 구현 후보

- `tools/rpi_amr_parser.py`를 기반으로 Serial read loop 추가
- 상태 변화만 콘솔에 표시하는 RPi 모니터 도구 작성
- ROS2 Jazzy 노드로 확장
- `DANGER`, `STOP`, `SENSOR_ERROR` 수신 시 ARM 동작 제한 정책 연결
