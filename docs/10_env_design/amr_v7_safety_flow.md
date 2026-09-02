# HazardBot AMR v7 안전 흐름 문서

## 목적

이 문서는 ESP32 #1 AMR v7 펌웨어의 안전 중심 구조를 설명한다. 공모전 발표와 개발 검증에서 Sensor -> Evaluation -> Action 흐름, 상태 전환 기준, RPi 5 메시지 포맷, 테스트 방법을 빠르게 확인하는 것을 목표로 한다.

## 시스템 범위

대상은 ESP32 #1 AMR 펌웨어다. ESP32 #2 ARM, STS3215 서보, 그리퍼, 출력 장치 로직은 포함하지 않는다. ESP32 #1과 ESP32 #2는 직접 통신하지 않으며, Raspberry Pi 5가 ROS2 Jazzy 기반 중앙 제어기로 각각의 ESP32와 통신한다.

## Sensor -> Evaluation -> Action 구조

### Sensor

- MQ-135: 가스 센서 입력을 읽고 이동 평균으로 안정화한다.
- KY-026: flame 감지 입력을 읽는다. 현재 기준은 LOW active다.
- Emergency Stop: `EMERGENCY_STOP_PIN` 입력을 `INPUT_PULLUP`으로 읽고 LOW일 때 활성으로 본다.
- RPi 5 통신: Serial 입력이 들어오면 마지막 수신 시간을 갱신한다.
- RPi 5 keepalive: `<CMD,PING,CS>`처럼 checksum이 맞는 framed 메시지만 통신 정상으로 인정한다.
- LiPo 전압: 현재는 `currentBatteryVoltage = 12.0` 임시값을 사용한다.

### Evaluation

`evaluateAmrState()`가 센서값과 안전 조건을 평가한다. 우선순위는 다음과 같다.

1. Emergency Stop 활성: `STOP`
2. LiPo 전압 `9.9V` 이하: `STOP`
3. MQ-135 센서 오류: `SENSOR_ERROR`
4. RPi 5 통신 timeout: `STOP`
5. flame 감지 또는 gas danger 조건: `DANGER`
6. gas warning 조건: `WARNING`
7. 그 외: `SAFE`

### Action

현재 Action은 상태 메시지를 RPi 5로 전송하고, 상태별 AMR action을 분류하는 것이다. 상태가 바뀌면 즉시 전송하고, 상태 변화가 없어도 heartbeat 주기마다 다시 전송한다. 실제 모터 핀 제어는 아직 수행하지 않으며, `applyAmrAction()`은 나중에 모터 제어를 붙일 안전한 hook 역할만 한다.

| 상태 | Action | 의미 |
|---|---|---|
| `SAFE` | `NORMAL_MOTION` | 정상 주행 허용 |
| `WARNING` | `LIMITED_MOTION` | 제한 주행 또는 감속 대상 |
| `DANGER` | `STOP_MOTION` | 정지 대상 |
| `STOP` | `STOP_MOTION` | 정지 대상 |
| `SENSOR_ERROR` | `STOP_MOTION` | 정지 대상 |

## 상태 정의

| 상태 | 의미 | 진입 조건 |
|---|---|---|
| `SAFE` | 정상 감시 상태 | 위험 조건 없음 |
| `WARNING` | 주의 상태 | gas가 warning 진입 기준 이상 |
| `DANGER` | 위험 상태 | flame 감지 또는 gas danger 조건이 연속 기준 충족 |
| `STOP` | 즉시 정지 상태 | Emergency Stop, LiPo cutoff, RPi timeout |
| `SENSOR_ERROR` | 센서 fault 상태 | MQ-135 값이 유효 범위를 연속 이탈 |

## 주요 안전 기준

- 3S LiPo cutoff: `LIPO_CUTOFF_VOLTAGE = 9.9`
- Emergency Stop 핀: `EMERGENCY_STOP_PIN = 26`
- RPi timeout: `RPI_TIMEOUT_MS = 3000`
- Sensor error 연속 기준: `SENSOR_ERROR_COUNT_THRESHOLD = 3`
- DANGER 연속 기준: `DANGER_COUNT_THRESHOLD = 3`

## 메시지 포맷

RPi 5로 전송되는 메시지는 다음 형식을 사용한다.

```text
<CMD,STATE=상태,GAS=가스값,FLAME=0또는1,BAT=전압,CS>
```

예시:

```text
<CMD,STATE=SAFE,GAS=42,FLAME=0,BAT=12.00,56>
```

checksum은 `<`, `>`, checksum 필드를 제외한 payload 문자열을 XOR 계산한다.

```text
CMD,STATE=SAFE,GAS=42,FLAME=0,BAT=12.00
```

RPi 5가 ESP32 #1 timeout을 해제하려면 checksum이 맞는 framed 메시지를 보내야 한다. 현재 keepalive 예시는 다음과 같다.

```text
<CMD,PING,76>
```

여기서 `76`은 `CMD,PING` payload의 XOR checksum이다. checksum이 틀린 메시지는 timeout 해제에 사용하지 않는다.

RPi 5 또는 PC에서 keepalive 메시지를 확인하려면 다음 dry-run 명령을 실행한다.

```powershell
C:\Users\rkdgm\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe tools\rpi_keepalive.py --dry-run --count 2
```

실제 Serial 포트로 보낼 때는 `pyserial`이 필요하며, 포트를 지정해서 실행한다.

```powershell
python tools\rpi_keepalive.py --port COM5 --interval 1
```

## 테스트 방법

하드웨어 없이 먼저 Python pure logic 하네스를 실행한다.

```powershell
C:\Users\rkdgm\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe tests\amr_v7\test_amr_v7_pure.py
```

현재 하네스는 상태 문자열, 메시지 포맷, checksum, LiPo cutoff, SENSOR_ERROR, Emergency Stop, RPi timeout fallback을 확인한다.

실제 ESP32 보드에서는 다음을 추가 확인한다.

- Serial Monitor에 `<CMD,...,CS>` 메시지가 출력되는가?
- E-Stop 버튼을 누르면 즉시 `STOP`으로 전환되는가?
- RPi 5 입력이 3초 이상 없으면 `STOP`으로 전환되는가?
- RPi 5가 주기적으로 keepalive를 보내면 timeout이 해제되는가?
- MQ-135 비정상 입력이 3회 누적되면 `SENSOR_ERROR`로 전환되는가?

## 남은 개선 과제

- 실제 LiPo 전압 분배 회로와 ADC 변환 함수 구현
- RPi 5 keepalive 메시지 주기와 payload 최종 확정
- `applyAmrAction()`에 실제 모터 드라이버 제어 연결
- 실제 RPi 5 환경에 `pyserial` 설치 및 keepalive 서비스 등록
- 실제 보드 업로드 후 핀 배선과 active level 확인
- 공모전 발표용 상태 전환 다이어그램 작성
