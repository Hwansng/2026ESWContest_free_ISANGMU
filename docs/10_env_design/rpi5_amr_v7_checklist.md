# RPi 5 - ESP32 #1 AMR v7 검증 체크리스트

## 큰 목표

이 체크리스트의 목표는 Raspberry Pi 5와 ESP32 #1 AMR v7이 안전하게 통신하는지 확인하는 것이다. 핵심은 RPi 5가 중앙 제어자 역할을 유지하고, ESP32 #1이 센서 오류, Emergency Stop, LiPo cutoff, 통신 timeout 상황에서 안전 상태로 전환되는지 검증하는 것이다.

## 준비물

- ESP32 #1 AMR 보드
- Raspberry Pi 5 또는 테스트용 PC
- USB Serial 케이블
- Arduino IDE
- Python 3
- `pyserial`

## 1. ESP32 업로드

Arduino IDE에서 다음 파일을 연다.

```text
Arduino/AMR_state_v7_ino/AMR_state_v7_ino.ino
```

ESP32 보드와 포트를 선택한 뒤 업로드한다. 업로드 후 Serial Monitor를 `115200 baud`로 연다.

## 2. RPi 5 Serial 포트 확인

RPi 5에서 ESP32가 어떤 포트로 잡혔는지 확인한다.

```bash
ls /dev/ttyUSB*
ls /dev/ttyACM*
```

대표 예시는 다음과 같다.

```text
/dev/ttyUSB0
/dev/ttyACM0
```

Windows PC에서 테스트한다면 장치 관리자 또는 Arduino IDE의 포트 목록에서 `COM5` 같은 포트를 확인한다.

## 3. pyserial 설치

RPi 5에서 실제 Serial 전송을 하려면 `pyserial`이 필요하다.

```bash
python3 -m pip install pyserial
```

설치가 제한된 환경이면 가상환경을 사용한다.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install pyserial
```

## 4. keepalive 메시지 dry-run

실제 Serial을 쓰기 전에 메시지 형식만 확인한다.

```bash
python tools/rpi_keepalive.py --dry-run --count 2
```

예상 출력:

```text
<CMD,PING,76>
<CMD,PING,76>
```

`76`은 `CMD,PING` payload의 XOR checksum이다.

## 5. keepalive 실제 전송

RPi 5에서 ESP32 포트로 1초마다 keepalive를 보낸다.

```bash
python tools/rpi_keepalive.py --port /dev/ttyUSB0 --interval 1
```

Windows PC에서 테스트하면 포트 예시는 다음과 같다.

```powershell
python tools\rpi_keepalive.py --port COM5 --interval 1
```

## 6. 정상 통신 확인

ESP32 Serial Monitor에서 다음 형식의 메시지가 주기적으로 출력되는지 확인한다.

```text
<CMD,STATE=SAFE,GAS=...,FLAME=0,BAT=12.00,CS>
```

정상 기준:

- 메시지가 `<`로 시작하고 `>`로 끝난다.
- 첫 필드는 `CMD`다.
- `STATE=...`, `GAS=...`, `FLAME=...`, `BAT=...` 필드가 있다.
- 마지막 checksum 필드가 있다.

PC나 RPi 5에서 메시지 파싱만 먼저 확인하려면 다음 명령을 실행한다.

```bash
python tools/rpi_amr_parser.py "<CMD,STATE=SAFE,GAS=42,FLAME=0,BAT=12.00,56>"
```

예상 출력:

```text
command=CMD
state=SAFE
gas=42
flame=0
battery=12.0
```

## 7. timeout fallback 테스트

keepalive 실행을 중지한다. `RPI_TIMEOUT_MS = 3000`이므로 약 3초 뒤 ESP32 상태가 `STOP`으로 전환되어야 한다.

Pass 기준:

```text
STATE=STOP
```

Fail 기준:

- keepalive가 끊겼는데도 계속 `SAFE` 또는 `WARNING`을 유지한다.
- checksum이 틀린 메시지로 timeout이 해제된다.

## 8. Emergency Stop 테스트

E-Stop 입력은 현재 `EMERGENCY_STOP_PIN = 26`, `INPUT_PULLUP`, active-low 기준이다.

Pass 기준:

- GPIO 26이 LOW가 되면 즉시 `STATE=STOP`으로 전환된다.
- E-Stop은 gas, flame, timeout보다 우선한다.

주의:

- 실제 버튼 배선이 다르면 핀 번호 또는 active level을 조정해야 한다.

## 9. Sensor Error 테스트

MQ-135 입력이 유효 범위 밖으로 3회 연속 판단되면 `SENSOR_ERROR`로 전환되어야 한다.

Pass 기준:

```text
STATE=SENSOR_ERROR
```

## 10. 기록할 항목

검증 후 다음 값을 기록한다.

- ESP32 포트:
- RPi 5 포트:
- keepalive 주기:
- timeout 전환 시간:
- E-Stop 핀과 active level:
- MQ-135 정상 범위:
- Serial 출력 예시:

## 다음 개선 후보

- 실제 LiPo 전압 분배 회로 연결 및 ADC 변환 함수 구현
- `applyAmrAction()`에 실제 모터 드라이버 제어 연결
- RPi 5 keepalive를 systemd 서비스로 등록
- 발표용 상태 전환 다이어그램 작성
