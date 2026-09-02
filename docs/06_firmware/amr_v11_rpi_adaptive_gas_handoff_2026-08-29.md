# HazardBot V11 적응형 가스 검사 — RPi 담당자 인계

## 변경 요약

ESP32는 이제 MQ-2 D0를 상시 위험 판정하지 않는다. 로봇이 P1 또는 P2에 도착해 정지한 뒤 RPi가 `GAS_CHECK` 명령을 보낼 때만 3초간 검사하고, 구역이 포함된 `GAS_RESULT`를 한 번 반환한다.

기존 TCP 구조는 그대로다.

- ESP32: TCP 클라이언트
- RPi: `0.0.0.0:8765` TCP 서버
- 기존 `CMD,PING` 및 `SENS` 프레임 유지
- 모든 프레임: `<payload,checksum>\n`
- checksum: payload ASCII 바이트 합계 modulo 256의 10진수

## RPi가 보내야 하는 프레임

```text
PING:     <CMD,PING,46>\n
P1 검사: <CMD,GAS_CHECK,P1,69>\n
P2 검사: <CMD,GAS_CHECK,P2,70>\n
```

검사 중에도 1초마다 PING을 계속 보내야 한다. ESP32의 RPi timeout은 마지막 유효 메시지 이후 3초이므로, `GAS_CHECK`만 보내고 기다리면 검사 종료 시점에 timeout 정지가 겹칠 수 있다.

## ESP32가 반환하는 GAS_RESULT

형식:

```text
<GAS_RESULT,zone,result,baseline,minimumRaw,weakPercent,checksum>\n
```

예시:

```text
<GAS_RESULT,P1,CLEAR,1775,1700,0,169>\n
<GAS_RESULT,P2,DETECTED,1775,400,5,86>\n
<GAS_RESULT,P2,ERROR,0,4095,0,51>\n
```

| 필드 | 의미 |
|---|---|
| `zone` | 요청한 `P1` 또는 `P2` |
| `result` | `CLEAR`, `DETECTED`, `ERROR` |
| `baseline` | 검사 시작 때 고정한 정상 기준값 |
| `minimumRaw` | 3초 동안 관찰한 최솟값 |
| `weakPercent` | 기준값의 70% 아래로 내려간 샘플 비율(정수 %) |
| `checksum` | 앞 payload의 ASCII 합 mod 256 |

RPi 동작 결정에는 `zone`과 `result`를 사용하고, 나머지 세 값은 현장 민감도 조정 로그로 저장한다. 요청 구역과 결과 구역이 다르면 해당 결과를 사용하지 않는다.

## 시나리오 처리 순서

### P1

1. P1 도착 및 완전 정지
2. `<CMD,GAS_CHECK,P1,69>\n` 전송
3. PING을 계속 보내며 최대 5초간 P1 결과 대기
4. `CLEAR`: 파지하지 않고 다음 구역으로 이동
5. `DETECTED`: 같은 명령으로 한 번만 재검사
6. 재검사도 `DETECTED`, `ERROR`, 또는 timeout: 안전 정지 및 운영자 확인

### P2

1. P2 도착 및 완전 정지
2. `<CMD,GAS_CHECK,P2,70>\n` 전송
3. PING을 계속 보내며 최대 5초간 P2 결과 대기
4. `DETECTED`: 위험물 파지 절차 진행
5. `CLEAR`: 같은 명령으로 한 번만 재검사
6. 재검사도 `CLEAR`, `ERROR`, 또는 timeout: 안전 정지 및 운영자 확인

P3에서는 `GAS_CHECK`를 보내지 않는다. P4 화염 감지는 가스 검사와 별개이며, 기존 SENS의 `flame=1`, `stateCode=2`, `faultCode=5`를 이용해 후진 대피를 수행한다.

## TCP 수신 주의사항

TCP의 한 번의 `recv()`가 한 프레임과 일치한다고 가정하면 안 된다. 수신 바이트를 버퍼에 누적하고 `<`부터 `>`까지 프레임을 분리한 후 checksum을 검증한다. `SENS`와 `GAS_RESULT`가 연속해서 들어올 수 있으므로 첫 필드로 두 형식을 구분한다.

검사 중 같은 명령을 반복 전송해도 ESP32는 진행 중인 3초 타이머를 재시작하지 않는다. 첫 명령 후 결과 또는 5초 timeout을 기다린 다음 재검사 명령을 보낸다.

## 통합 확인 체크리스트

- [ ] RPi가 `0.0.0.0:8765`에서 listen한다.
- [ ] ESP32 Serial에 `[TCP] CONNECTED`가 표시된다.
- [ ] PING을 1초 주기로 계속 보낸다.
- [ ] P1 명령 후 약 3초 뒤 `GAS_RESULT,P1,...`을 받는다.
- [ ] P2 명령 후 약 3초 뒤 `GAS_RESULT,P2,...`을 받는다.
- [ ] 검사 중에도 SENS 프레임을 정상 수신한다.
- [ ] P3에는 가스 검사 명령을 보내지 않는다.
- [ ] P4 화염 처리와 부저가 가스 결과와 독립적으로 동작한다.
