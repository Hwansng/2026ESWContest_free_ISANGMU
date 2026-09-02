# 3S LiPo 전압 측정 설계 메모

## 목적

ESP32 #1 AMR v7은 3S LiPo cutoff 기준을 `9.9V`로 유지해야 한다. 현재 펌웨어에는 `LIPO_CUTOFF_VOLTAGE = 9.9` 조건이 있지만, 실제 전압은 `currentBatteryVoltage = 12.0` 임시값으로 고정되어 있다. 따라서 실제 배터리 보호 기능을 완성하려면 ESP32 ADC로 LiPo 전압을 측정하는 회로와 변환식이 필요하다.

## 모터와의 관계

LiPo 전압 측정은 모터를 직접 제어하는 기능은 아니다. 하지만 AMR 안전에는 강하게 연결된다.

- 모터가 큰 전류를 쓰면 배터리 전압이 순간적으로 떨어질 수 있다.
- 배터리 전압이 낮은 상태에서 계속 주행하면 LiPo 과방전 위험이 있다.
- 전압이 낮아지면 ESP32, 센서, 모터 드라이버가 불안정해질 수 있다.
- 따라서 전압이 `9.9V` 이하이면 상태 평가에서 `STOP`으로 전환하고, action은 `STOP_MOTION`이 되어야 한다.

즉, LiPo 측정은 “모터를 움직이기 위한 기능”이 아니라 “모터를 멈춰야 할 때를 판단하는 안전 입력”이다.

## 왜 전압 분배가 필요한가

3S LiPo는 완충 시 약 `12.6V`까지 올라간다. ESP32 ADC 입력은 보통 3.3V 범위를 넘기면 안 된다. 그래서 배터리 전압을 저항 2개로 낮춰 ADC 핀에 넣어야 한다.

기본 회로:

```text
LiPo + ---- R1 ----+---- ADC_PIN
                  |
                  R2
                  |
LiPo - -----------+---- GND
```

계산식:

```text
Vadc = Vbat * R2 / (R1 + R2)
Vbat = Vadc * (R1 + R2) / R2
```

예를 들어 `R1 = 100kΩ`, `R2 = 33kΩ`이면:

```text
분배비 = 33 / (100 + 33) = 0.248
12.6V * 0.248 = 약 3.12V
```

이 값은 ESP32 ADC 입력 범위 안에 들어온다.

## 코드에 들어갈 구조

실제 구현 시에는 다음 상수를 둔다.

```cpp
const int LIPO_ADC_PIN = 35;
const float LIPO_R1_OHMS = 100000.0;
const float LIPO_R2_OHMS = 33000.0;
const float ADC_REFERENCE_VOLTAGE = 3.3;
const int ADC_MAX_VALUE = 4095;
```

그리고 다음 함수로 분리한다.

```cpp
float readBatteryVoltage();
```

이 함수는 ADC raw 값을 읽고, ADC 전압으로 바꾼 뒤, 전압 분배 역산으로 실제 LiPo 전압을 계산한다.

개념식:

```cpp
float adcVoltage = raw * ADC_REFERENCE_VOLTAGE / ADC_MAX_VALUE;
float batteryVoltage = adcVoltage * (LIPO_R1_OHMS + LIPO_R2_OHMS) / LIPO_R2_OHMS;
```

## v7 상태 평가와 연결

현재 v7의 상태 평가 우선순위는 다음 흐름을 유지한다.

1. Emergency Stop이면 `STOP`
2. LiPo 전압이 `9.9V` 이하이면 `STOP`
3. 센서 오류이면 `SENSOR_ERROR`
4. RPi timeout이면 `STOP`
5. DANGER/WARNING/SAFE 판단

LiPo 측정 구현 후에는 `currentBatteryVoltage = 12.0` 고정값 대신 `readBatteryVoltage()` 결과를 사용한다.

## 실제 구현 전 확인할 것

아직 바로 코드를 바꾸기 전에 다음 값을 확정해야 한다.

- LiPo 전압 측정에 사용할 ESP32 ADC 핀
- 전압 분배 저항값 `R1`, `R2`
- 사용하는 ESP32 보드의 ADC 입력 허용 범위
- GND가 LiPo, ESP32, 모터 드라이버 사이에서 공통으로 연결되는지
- 멀티미터로 측정한 실제 배터리 전압과 ADC 계산값의 오차

## 테스트 방법

하드웨어 없이 가능한 테스트:

- Python 하네스에서 raw ADC 값 -> 배터리 전압 변환식을 검증한다.
- `9.9V` 이하일 때 `STOP`으로 평가되는지 확인한다.

실제 보드에서 필요한 테스트:

- 멀티미터로 LiPo 전압을 측정한다.
- ESP32가 계산한 `BAT=` 값과 비교한다.
- 배터리 전압이 낮은 상황을 전원공급기나 안전한 테스트 회로로 재현한다.
- `BAT <= 9.9V`일 때 `STATE=STOP`으로 전환되는지 확인한다.

## 주의사항

- LiPo를 ESP32 ADC 핀에 직접 연결하면 안 된다.
- 전압 분배 회로 없이 12V대 전압을 ADC에 넣으면 보드가 손상될 수 있다.
- 모터 부하로 순간 전압 강하가 생길 수 있으므로, 나중에 평균 필터나 최소 지속 시간 조건을 검토할 수 있다.
- cutoff 기준 `9.9V`는 3S 기준 셀당 약 `3.3V`이다.

## 추천 다음 단계

1. 실제 사용할 ADC 핀을 정한다.
2. 전압 분배 저항값을 정한다. 시작안은 `R1 = 100kΩ`, `R2 = 33kΩ`이다.
3. Python 하네스에 ADC 변환식 테스트를 추가한다.
4. Arduino v7에 `readBatteryVoltage()`를 추가한다.
5. 실제 보드에서 멀티미터 값과 `BAT=` 출력값을 비교해 보정한다.
