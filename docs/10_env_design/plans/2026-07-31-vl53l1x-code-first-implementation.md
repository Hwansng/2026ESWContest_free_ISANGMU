# VL53L1X Code-First Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve the uploaded ESP32 #1 AMR v8 sketch and create a v9 sketch that reads an Adafruit VL53L1X, evaluates distance hazards, fails safely when the sensor is unavailable, and emits distance in checked telemetry.

**Architecture:** Keep the existing single-sketch v8 structure and create a separate v9 sketch. Add a small non-blocking VL53L1X adapter inside that sketch, then pass its last valid millimetre reading and debounced validity into the existing evaluation flow. Mirror the Arduino decision logic in the existing standalone Python harness style so distance thresholds, safety priority, protocol fields, and checksum can be verified before hardware is soldered.

**Tech Stack:** ESP32 Arduino, `Wire`, bundled `Adafruit_VL53L1X`, Python 3 pure-logic harness, PowerShell

## Global Constraints

- Work only on ESP32 #1 AMR.
- Do not modify `Arduino/AMR_state_v8_ino/AMR_state_v8_ino.ino`.
- Do not add ESP32 #2 ARM, servo, gripper, buzzer, or output-device logic.
- Preserve Emergency Stop as the highest-priority condition.
- Preserve the 3S LiPo cutoff at exactly `9.9V`.
- Preserve RPi timeout fallback at `3000ms`.
- Preserve the outer protocol format `<CMD,...,CS>\n`.
- Preserve decimal ASCII-sum-modulo-256 checksum behavior.
- Use GPIO21 for SDA and GPIO22 for SCL.
- Use VL53L1X I2C address `0x29` and a `50ms` timing budget.
- Never transmit a simulated distance as a real hardware reading.
- Do not add MQ-2 in this plan; it follows after its module output voltage is confirmed.

## File Map

- Create `Arduino/AMR_state_v9_ino/AMR_state_v9_ino.ino`: v8 behavior plus VL53L1X initialization, reading, validation, distance risk evaluation, debug output, and v9 telemetry.
- Create `tests/amr_v9/test_amr_v9_pure.py`: executable pure-logic model and source-contract checks for v9.
- Read only `Arduino/AMR_state_v8_ino/AMR_state_v8_ino.ino`: stable source used as the v9 baseline.
- Read only `tests/amr_v8/test_amr_v8_pure.py`: existing test-harness style used as the v9 baseline.

---

### Task 1: Add failing v9 distance and protocol tests

**Files:**
- Create: `tests/amr_v9/test_amr_v9_pure.py`
- Read: `tests/amr_v8/test_amr_v8_pure.py`
- Expected later source: `Arduino/AMR_state_v9_ino/AMR_state_v9_ino.ino`

**Interfaces:**
- Consumes: v8 enums, threshold behavior, checksum algorithm, and test-report format.
- Produces: `V9Context`, `update_distance_reading()`, `evaluate_amr_state()`, `determine_safety_fault()`, `build_sensor_message()`, and executable regression checks.

- [ ] **Step 1: Create the v9 pure-logic model**

Start from the v8 test harness structure, rename the context to `V9Context`, separate the two sensor error counters, and add these exact constants and functions:

```python
DISTANCE_INVALID_MM = -1
DISTANCE_MIN_VALID_MM = 30
DISTANCE_MAX_VALID_MM = 4000
DISTANCE_WARNING_ENTER_MM = 500
DISTANCE_WARNING_EXIT_MM = 550
DISTANCE_DANGER_ENTER_MM = 200
DISTANCE_DANGER_EXIT_MM = 250


@dataclass
class V9Context:
    danger_count: int = 0
    gas_sensor_error_count: int = 0
    distance_sensor_error_count: int = 0
    last_valid_distance_mm: int = DISTANCE_INVALID_MM


def update_distance_reading(raw_distance_mm, context):
    raw_valid = DISTANCE_MIN_VALID_MM <= raw_distance_mm <= DISTANCE_MAX_VALID_MM
    if raw_valid:
        context.distance_sensor_error_count = 0
        context.last_valid_distance_mm = raw_distance_mm
    else:
        context.distance_sensor_error_count += 1

    sensor_valid = (
        context.distance_sensor_error_count < SENSOR_ERROR_COUNT_THRESHOLD
    )
    return context.last_valid_distance_mm, sensor_valid


def is_distance_danger_enter(distance_mm):
    return DISTANCE_MIN_VALID_MM <= distance_mm <= DISTANCE_DANGER_ENTER_MM


def is_distance_danger_stay(distance_mm):
    return DISTANCE_MIN_VALID_MM <= distance_mm <= DISTANCE_DANGER_EXIT_MM


def is_distance_warning_enter(distance_mm):
    return DISTANCE_MIN_VALID_MM <= distance_mm <= DISTANCE_WARNING_ENTER_MM


def is_distance_warning_stay(distance_mm):
    return DISTANCE_MIN_VALID_MM <= distance_mm <= DISTANCE_WARNING_EXIT_MM
```

Change `is_gas_sensor_valid()` to update
`context.gas_sensor_error_count`. Extend `evaluate_amr_state()` with
`distance_mm` and `distance_sensor_valid`. Reject either sensor fault before
RPi timeout and use these exact combined hazard conditions:

```python
if not gas_sensor_valid or not distance_sensor_valid:
    return AmrState.SENSOR_ERROR

danger_enter_condition = (
    flame_detected
    or gas_average >= GAS_DANGER_ENTER_THRESHOLD
    or is_distance_danger_enter(distance_mm)
)
danger_stay_condition = (
    flame_detected
    or gas_average >= GAS_DANGER_EXIT_THRESHOLD
    or is_distance_danger_stay(distance_mm)
)
warning_stay_condition = (
    gas_average >= GAS_WARNING_EXIT_THRESHOLD
    or is_distance_warning_stay(distance_mm)
)
warning_enter_condition = (
    gas_average >= GAS_WARNING_ENTER_THRESHOLD
    or is_distance_warning_enter(distance_mm)
)
```

Extend `determine_safety_fault()` with `distance_sensor_valid` and return
`SafetyFault.SENSOR` when either sensor is invalid.

- [ ] **Step 2: Add distance to the test-side telemetry builder**

Use this exact payload order:

```python
def build_sensor_payload(
    state,
    action,
    fault,
    gas_average,
    flame_detected,
    battery_voltage,
    distance_mm,
):
    return (
        f"SENS,{gas_average},{1 if flame_detected else 0},"
        f"{battery_to_centivolts(battery_voltage)},"
        f"{state.value},{action.value},{fault.value},{distance_mm}"
    )
```

`build_sensor_message()` must append the decimal checksum and `>\n` exactly as
v8 does.

- [ ] **Step 3: Add concrete behavioral test cases**

Add test results for all of these exact cases:

```python
distance_cases = [
    ("T_DISTANCE_SAFE", 700, AmrState.SAFE),
    ("T_DISTANCE_WARNING", 350, AmrState.WARNING),
]

context = V9Context()
state = AmrState.SAFE
for _ in range(3):
    distance_mm, distance_valid = update_distance_reading(150, context)
    state = evaluate_amr_state(
        gas_average=1200,
        flame_detected=False,
        gas_sensor_valid=True,
        distance_mm=distance_mm,
        distance_sensor_valid=distance_valid,
        battery_voltage=12.0,
        emergency_stop_active=False,
        rpi_timeout_active=False,
        last_state=state,
        context=context,
    )
assert state == AmrState.DANGER

context = V9Context()
for _ in range(3):
    distance_mm, distance_valid = update_distance_reading(-1, context)
assert distance_mm == -1
assert not distance_valid

context = V9Context()
distance_mm, distance_valid = update_distance_reading(150, context)
for _ in range(2):
    distance_mm, distance_valid = update_distance_reading(-1, context)
assert distance_mm == 150
assert distance_valid
distance_mm, distance_valid = update_distance_reading(-1, context)
assert distance_mm == 150
assert not distance_valid

distance_mm, distance_valid = update_distance_reading(700, context)
assert distance_mm == 700
assert distance_valid
assert context.distance_sensor_error_count == 0

context = V9Context()
state = AmrState.SAFE
for _ in range(3):
    distance_mm, distance_valid = update_distance_reading(150, context)
    state = evaluate_amr_state(
        gas_average=1200,
        flame_detected=False,
        gas_sensor_valid=True,
        distance_mm=distance_mm,
        distance_sensor_valid=distance_valid,
        battery_voltage=12.0,
        emergency_stop_active=False,
        rpi_timeout_active=False,
        last_state=state,
        context=context,
    )
assert state == AmrState.DANGER

distance_mm, distance_valid = update_distance_reading(240, context)
state = evaluate_amr_state(
    gas_average=1200,
    flame_detected=False,
    gas_sensor_valid=True,
    distance_mm=distance_mm,
    distance_sensor_valid=distance_valid,
    battery_voltage=12.0,
    emergency_stop_active=False,
    rpi_timeout_active=False,
    last_state=state,
    context=context,
)
assert state == AmrState.DANGER

distance_mm, distance_valid = update_distance_reading(260, context)
state = evaluate_amr_state(
    gas_average=1200,
    flame_detected=False,
    gas_sensor_valid=True,
    distance_mm=distance_mm,
    distance_sensor_valid=distance_valid,
    battery_voltage=12.0,
    emergency_stop_active=False,
    rpi_timeout_active=False,
    last_state=state,
    context=context,
)
assert state == AmrState.WARNING
```

Add explicit priority cases proving:

```python
Emergency Stop > LiPo cutoff > either sensor error > RPi timeout > hazard
```

Add a telemetry case that splits the payload and checks:

```python
fields == ["SENS", "120", "1", "1200", "0", "0", "0", "350"]
len(fields) == 8
```

Add source checks for these exact strings in the future v9 sketch:

```python
'#include <Adafruit_VL53L1X.h>'
'const int I2C_SDA_PIN = 21;'
'const int I2C_SCL_PIN = 22;'
'const uint8_t VL53L1X_I2C_ADDRESS = 0x29;'
'distanceSensor.startRanging()'
'distanceSensor.setTimingBudget(VL53L1X_TIMING_BUDGET_MS)'
'payload += String(distanceMm);'
```

- [ ] **Step 4: Run the new harness and verify the expected failure**

Run:

```powershell
C:\Users\rkdgm\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe tests\amr_v9\test_amr_v9_pure.py
```

Expected: FAIL because
`Arduino/AMR_state_v9_ino/AMR_state_v9_ino.ino` does not exist or because the
required VL53L1X source strings are absent.

- [ ] **Step 5: Commit the failing test harness**

```powershell
C:\Users\rkdgm\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\cmd\git.exe add -- tests/amr_v9/test_amr_v9_pure.py
C:\Users\rkdgm\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\cmd\git.exe commit -m "Add VL53L1X v9 logic tests"
```

---

### Task 2: Create the v9 Arduino sketch

**Files:**
- Create: `Arduino/AMR_state_v9_ino/AMR_state_v9_ino.ino`
- Read baseline: `Arduino/AMR_state_v8_ino/AMR_state_v8_ino.ino`
- Test: `tests/amr_v9/test_amr_v9_pure.py`

**Interfaces:**
- Consumes: v8 sensor/state/message functions and the thresholds established by Task 1.
- Produces: `initializeDistanceSensor()`, `readDistanceMm()`, `updateDistanceSensorValidity()`, distance-aware `evaluateAmrState()`, distance-aware `determineSafetyFault()`, and v9 telemetry.

- [ ] **Step 1: Create v9 from the complete v8 sketch**

Create `Arduino/AMR_state_v9_ino/AMR_state_v9_ino.ino` with the full v8 source
as its starting content. Change the file banner and startup strings from v8 to
v9. Do not edit the v8 file.

At the top of v9, use these includes:

```cpp
#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_VL53L1X.h>
```

- [ ] **Step 2: Add exact I2C, sensor, and threshold constants**

Place these constants beside the existing pin and sensor settings:

```cpp
const int I2C_SDA_PIN = 21;
const int I2C_SCL_PIN = 22;
const uint8_t VL53L1X_I2C_ADDRESS = 0x29;
const int VL53L1X_TIMING_BUDGET_MS = 50;

const int DISTANCE_INVALID_MM = -1;
const int DISTANCE_MIN_VALID_MM = 30;
const int DISTANCE_MAX_VALID_MM = 4000;
const int DISTANCE_WARNING_ENTER_MM = 500;
const int DISTANCE_WARNING_EXIT_MM = 550;
const int DISTANCE_DANGER_ENTER_MM = 200;
const int DISTANCE_DANGER_EXIT_MM = 250;
```

Add these globals without changing the v8 gas sample storage:

```cpp
Adafruit_VL53L1X distanceSensor;
bool distanceSensorInitialized = false;
int distanceSensorErrorCount = 0;
int lastValidDistanceMm = DISTANCE_INVALID_MM;
```

Rename the existing `sensorErrorCount` to `gasSensorErrorCount` everywhere so
the two sensor failures remain isolated.

- [ ] **Step 3: Implement non-blocking sensor initialization and reading**

Add these declarations:

```cpp
void initializeDistanceSensor();
int readDistanceMm();
bool updateDistanceSensorValidity(int rawDistanceMm);
bool isDistanceDangerEnter(int distanceMm);
bool isDistanceDangerStay(int distanceMm);
bool isDistanceWarningEnter(int distanceMm);
bool isDistanceWarningStay(int distanceMm);
```

Implement initialization without an infinite retry:

```cpp
void initializeDistanceSensor() {
  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);

  if (!distanceSensor.begin(VL53L1X_I2C_ADDRESS, &Wire)) {
    distanceSensorInitialized = false;
    Serial.print("[VL53L1X] INIT_ERROR=");
    Serial.println(distanceSensor.vl_status);
    return;
  }

  if (!distanceSensor.startRanging()) {
    distanceSensorInitialized = false;
    Serial.print("[VL53L1X] RANGE_START_ERROR=");
    Serial.println(distanceSensor.vl_status);
    return;
  }

  if (!distanceSensor.setTimingBudget(VL53L1X_TIMING_BUDGET_MS)) {
    distanceSensorInitialized = false;
    Serial.print("[VL53L1X] TIMING_ERROR=");
    Serial.println(distanceSensor.vl_status);
    return;
  }

  distanceSensorInitialized = true;
  Serial.println("[VL53L1X] READY");
}
```

Implement one non-blocking read:

```cpp
int readDistanceMm() {
  if (!distanceSensorInitialized || !distanceSensor.dataReady()) {
    return DISTANCE_INVALID_MM;
  }

  int distanceMm = distanceSensor.distance();
  bool interruptCleared = distanceSensor.clearInterrupt();

  if (
    !interruptCleared ||
    distanceMm < DISTANCE_MIN_VALID_MM ||
    distanceMm > DISTANCE_MAX_VALID_MM
  ) {
    return DISTANCE_INVALID_MM;
  }

  return distanceMm;
}

bool updateDistanceSensorValidity(int rawDistanceMm) {
  bool rawValid = (
    rawDistanceMm >= DISTANCE_MIN_VALID_MM &&
    rawDistanceMm <= DISTANCE_MAX_VALID_MM
  );

  if (rawValid) {
    lastValidDistanceMm = rawDistanceMm;
    distanceSensorErrorCount = 0;
  } else {
    distanceSensorErrorCount++;
  }

  return distanceSensorErrorCount < SENSOR_ERROR_COUNT_THRESHOLD;
}
```

Add the four threshold helpers as inclusive integer comparisons matching
Task 1.

- [ ] **Step 4: Initialize and sample VL53L1X in the existing flow**

Call `initializeDistanceSensor()` in `setup()` after the existing pin modes
and before the startup telemetry.

In the 300ms read block, add:

```cpp
int rawDistanceMm = readDistanceMm();
bool distanceSensorValid = updateDistanceSensorValidity(rawDistanceMm);
int distanceMm = lastValidDistanceMm;
```

Pass `distanceMm` and `distanceSensorValid` into state evaluation, fault
selection, heartbeat telemetry, state-change telemetry, and debug output.

- [ ] **Step 5: Extend safety evaluation without weakening v8 priorities**

Extend the relevant signatures with:

```cpp
int distanceMm,
bool distanceSensorValid
```

Immediately after the LiPo check, use:

```cpp
if (!gasSensorValid || !distanceSensorValid) {
  return STATE_SENSOR_ERROR;
}
```

Use these conditions:

```cpp
bool dangerEnterCondition = (
  flameDetected ||
  gasAverage >= GAS_DANGER_ENTER_THRESHOLD ||
  isDistanceDangerEnter(distanceMm)
);

bool dangerStayCondition = (
  flameDetected ||
  gasAverage >= GAS_DANGER_EXIT_THRESHOLD ||
  isDistanceDangerStay(distanceMm)
);

bool warningStayCondition = (
  gasAverage >= GAS_WARNING_EXIT_THRESHOLD ||
  isDistanceWarningStay(distanceMm)
);

bool warningEnterCondition = (
  gasAverage >= GAS_WARNING_ENTER_THRESHOLD ||
  isDistanceWarningEnter(distanceMm)
);
```

Replace the existing gas-only WARNING checks with
`warningStayCondition` and `warningEnterCondition`. In
`determineSafetyFault()`, return `FAULT_SENSOR` when either sensor validity
flag is false.

- [ ] **Step 6: Extend telemetry and debug output**

Extend `buildSensorPayload()` and `sendSensorMessage()` with `int distanceMm`.
After appending `faultCode`, append:

```cpp
payload += ",";
payload += String(distanceMm);
```

Update the protocol banner to:

```text
<SENS,gas,flame,battCv,stateCode,actionCode,faultCode,distanceMm,checksum>
```

Add these debug fields:

```cpp
Serial.print(" | DIST=");
if (distanceMm == DISTANCE_INVALID_MM) {
  Serial.print("INVALID");
} else {
  Serial.print(distanceMm);
  Serial.print("mm");
}

Serial.print(" | DIST_SENSOR=");
Serial.print(distanceSensorValid ? "OK" : "ERROR");

Serial.print(" | DIST_ERROR_COUNT=");
Serial.print(distanceSensorErrorCount);
```

- [ ] **Step 7: Run v9 and v8 pure-logic tests**

Run:

```powershell
C:\Users\rkdgm\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe tests\amr_v9\test_amr_v9_pure.py
C:\Users\rkdgm\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe tests\amr_v8\test_amr_v8_pure.py
```

Expected: both commands exit `0`; the v9 report contains no `FAIL`, and the
v8 regression report remains unchanged.

- [ ] **Step 8: Commit the v9 sketch**

```powershell
C:\Users\rkdgm\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\cmd\git.exe add -- Arduino/AMR_state_v9_ino/AMR_state_v9_ino.ino
C:\Users\rkdgm\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\cmd\git.exe commit -m "Add VL53L1X AMR v9 integration"
```

---

### Task 3: Verify the finished code-first integration

**Files:**
- Verify: `Arduino/AMR_state_v9_ino/AMR_state_v9_ino.ino`
- Verify: `tests/amr_v9/test_amr_v9_pure.py`
- Verify unchanged: `Arduino/AMR_state_v8_ino/AMR_state_v8_ino.ino`

**Interfaces:**
- Consumes: completed v9 sketch and v9 pure-logic harness.
- Produces: evidence that the code-only scope is complete and an exact later hardware checklist.

- [ ] **Step 1: Run whitespace and repository checks**

```powershell
C:\Users\rkdgm\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\cmd\git.exe diff --check
C:\Users\rkdgm\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\cmd\git.exe status --short
```

Expected: no whitespace errors. Existing unrelated untracked user files may
remain, but only the v9 sketch, v9 test, and plan-related files belong to this
feature.

- [ ] **Step 2: Run the complete hardware-free verification again**

```powershell
C:\Users\rkdgm\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe tests\amr_v9\test_amr_v9_pure.py
C:\Users\rkdgm\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe tests\amr_v8\test_amr_v8_pure.py
```

Expected: both commands exit `0`.

- [ ] **Step 3: Record the remaining Arduino IDE verification**

After the six-pin header is soldered, perform exactly these manual checks:

```text
Board: ESP32
VIN -> 3V3
GND -> GND
SCL -> GPIO22
SDA -> GPIO21
GPIO and XSHUT -> disconnected
Expected I2C address -> 0x29
Expected distances -> approximately 700mm, 350mm, 150mm
Expected state sequence with valid RPi heartbeat -> SAFE, WARNING, DANGER
Expected no-RPi behavior after 3000ms -> STOP with RPI_TIMEOUT
```

The Serial debug output must still show `DIST` while the no-RPi safety stop is
active. Disconnecting SDA or SCL for three read cycles must produce
`SENSOR_ERROR` and `STOP_MOTION`.

- [ ] **Step 4: Prepare the handoff summary**

Report:

```text
Purpose: add VL53L1X distance sensing without changing v8
Safety impact: distance danger and sensor-failure stop added; E-stop, 9.9V cutoff, and RPi timeout priority preserved
Automated tests: v9 and v8 pure-logic result counts and exit codes
Hardware status: I2C and physical-distance validation still required after soldering
Protocol: <SENS,gas,flame,battCv,stateCode,actionCode,faultCode,distanceMm,checksum>
```
