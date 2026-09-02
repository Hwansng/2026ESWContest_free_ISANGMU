# AMR 모터 드라이버 선정 기준

## 목적

이 문서는 HazardBot AMR의 DC 12V 구동 모터에 맞는 모터 드라이버 선정 기준을 정리한다. 현재 보유한 `keyestudio TB6612FNG Motor Driver for Arduino`는 모터 드라이버가 맞지만, 현재 모터 정격 전류 기준으로 최종 주행용으로는 전류 여유가 부족할 수 있다.

## 현재 모터 조건

ICBANQ 제품 정보 기준 모터 사양:

| 항목 | 값 |
|---|---|
| 모델 | CHR-GM25-370 / CHIHAI MOTOR |
| 구동 전압 | DC 12V |
| 정격 전류 | 1.5A |
| 속도 | 350rpm |
| 토크 | 3.5kg.cm |
| 타이어 직경 | 130mm |
| 타이어 폭 | 60mm |

좌우 구동을 위해 모터 2개를 사용하면 정격 전류만 합산해도 약 `3.0A`가 필요하다. 출발, 회전, 바퀴 걸림, stall 상황에서는 이보다 큰 순간 전류가 흐를 수 있다.

## TB6612FNG 판단

TB6612FNG는 소형 DC 모터용 드라이버로는 적합하지만, 현재 AMR 바퀴 구동 모터에는 여유가 작다.

| 항목 | 판단 |
|---|---|
| 전압 | 12V 모터와 대체로 호환 가능 |
| 정격 전류 | 모터 1개당 1.5A라 여유 부족 가능 |
| stall current | 미확인. TB6612FNG 한계를 넘을 수 있음 |
| 사용 권장 | 저부하 짧은 테스트까지만 권장 |
| 최종 주행 | 더 큰 전류 드라이버 검토 권장 |

## 새 드라이버 권장 조건

최종 AMR 주행용 드라이버는 최소 다음 조건을 만족하는 것이 좋다.

| 항목 | 권장 기준 |
|---|---|
| 모터 전압 | 12V 이상 지원 |
| 채널 수 | DC 모터 2개 이상 |
| 채널당 연속 전류 | 최소 2A 이상, 권장 3A 이상 |
| 채널당 피크 전류 | 최소 5A 이상 권장 |
| 제어 방식 | ESP32 PWM 제어 가능 |
| 로직 전압 | 3.3V 입력 호환 또는 level shifting 필요 |
| 보호 기능 | 과전류, 과열, 역전압 보호 권장 |
| 방열 | 방열판 또는 충분한 PCB 방열 면적 권장 |

정격 전류 `1.5A` 모터는 실제 주행 중 순간적으로 더 큰 전류를 요구할 수 있으므로, 드라이버를 정격값에 딱 맞춰 고르지 말고 여유를 둔다.

## 후보 드라이버를 볼 때 확인할 항목

제품 페이지나 데이터시트에서 다음 항목을 확인한다.

- `Motor supply voltage`
- `Continuous current per channel`
- `Peak current per channel`
- `Logic input voltage`
- `PWM frequency`
- `Control interface`
- `Thermal shutdown`
- `Overcurrent protection`
- `Number of motor channels`

## 제어 방식별 코드 영향

모터 드라이버 제어 방식에 따라 `applyAmrAction()`에 들어갈 코드 구조가 달라진다.

### PWM/DIR 방식

핀 예시:

```text
LEFT_PWM, LEFT_DIR
RIGHT_PWM, RIGHT_DIR
```

특징:

- 속도는 PWM으로 제어
- 방향은 DIR 핀으로 제어
- 코드가 비교적 단순함

### IN1/IN2 방식

핀 예시:

```text
LEFT_IN1, LEFT_IN2
RIGHT_IN1, RIGHT_IN2
```

특징:

- IN1/IN2 조합으로 방향과 정지를 제어
- PWM을 한쪽 입력에 걸거나 enable 핀에 걸 수 있음
- 드라이버별 동작표 확인 필요

## 상태별 action 연결 원칙

현재 v7의 action 분류는 유지한다.

| 상태 | Action | 모터 출력 원칙 |
|---|---|---|
| `SAFE` | `NORMAL_MOTION` | 정상 속도 허용 |
| `WARNING` | `LIMITED_MOTION` | 감속 또는 제한 출력 |
| `DANGER` | `STOP_MOTION` | 모터 정지 |
| `STOP` | `STOP_MOTION` | 모터 정지 |
| `SENSOR_ERROR` | `STOP_MOTION` | 모터 정지 |

실제 모터 제어를 추가할 때도 Emergency Stop, LiPo cutoff, timeout, sensor error 조건은 항상 모터 정지보다 우선해야 한다.

## 구매 전 체크리스트

새 모터 드라이버를 구매하기 전에 다음을 확인한다.

- 모터 2개를 동시에 구동할 수 있는가?
- 채널당 연속 전류가 최소 `2A`, 가능하면 `3A` 이상인가?
- 피크 전류가 stall 상황을 어느 정도 감당할 수 있는가?
- 12V 배터리와 호환되는가?
- ESP32 3.3V GPIO로 제어 가능한가?
- 방열 대책이 있는가?
- 제어 핀 수가 ESP32에서 확보 가능한가?
- 제품 문서에 truth table 또는 제어 예제가 있는가?

## 추천 결정

현재 TB6612FNG는 보유 부품이므로 회로 이해나 무부하 테스트에는 사용할 수 있다. 하지만 실제 130mm 타이어를 장착한 AMR 주행에서는 전류 여유가 부족할 수 있으므로, 최종 구동용으로는 더 높은 전류 등급의 드라이버를 선정하는 것이 안전하다.
