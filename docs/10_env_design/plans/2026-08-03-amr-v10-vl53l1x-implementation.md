# AMR v10 VL53L1X Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create and hardware-free verify an AMR v10 sketch that preserves all v9 sensor behavior and adds fail-safe, non-blocking VL53L1X distance sensing plus compatible Raspberry Pi telemetry parsing.

**Architecture:** Copy the complete v9 sketch and pure-logic harness into separate v10 paths, then add one isolated distance channel whose readiness is passed into the existing safety evaluator. Extend the SENS payload by appending `distanceMm`, while the Raspberry Pi parser accepts both the unchanged v9 payload and the new v10 payload. Keep v9 uploaded on the board until the VL53L1X header is soldered.

**Tech Stack:** ESP32 Arduino, `Wire`, bundled `Adafruit_VL53L1X`, Python 3 pure-logic harness, Python `unittest`, PowerShell, Arduino CLI

## Global Constraints

- Preserve `Arduino/AMR_state_v9_ino/AMR_state_v9_ino.ino` and `tests/amr_v9/test_amr_v9_pure.py` unchanged.
- Create v10 only in `Arduino/AMR_state_v10_ino` and `tests/amr_v10`.
- Read MQ-135 on GPIO34, MQ-2 on GPIO35, and KY-026 digital output on GPIO27.
- Preserve the MQ calibration settle time at exactly `180000ms`.
- Use GPIO21 for VL53L1X SDA and GPIO22 for SCL.
- Use VL53L1X I2C address `0x29` and timing budget `50ms`.
- Treat `30..4000mm` as the only valid distance range.
- Use distance WARNING enter/exit thresholds `500/550mm`.
- Use distance DANGER enter/exit thresholds `200/250mm` with three consecutive danger evaluations.
- Treat distance initialization failure as immediate `SENSOR_ERROR`.
- Tolerate at most two consecutive runtime read failures only after at least one valid distance has been received; the third failure is `SENSOR_ERROR`.
- Preserve safety priority: E-Stop > 9.9V cutoff > any sensor error > 3000ms RPi timeout > hazard.
- Preserve flame LOW-active immediate DANGER and both MQ channels' independent relative calibration.
- Do not add motor, TB6612, line tracing, ARM, servo, gripper, buzzer, or other output-device code.
- Keep `currentBatteryVoltage = 12.0` labeled as a bench injection, not a measured battery voltage.
- Do not upload v10 before the VL53L1X header is soldered.

## File Map

- Create `tests/amr_v10/test_amr_v10_pure.py`: v9 logic regression plus distance channel, thresholds, fail-safe state, v10 payload, and v10 source contracts.
- Create `Arduino/AMR_state_v10_ino/AMR_state_v10_ino.ino`: full v9 sketch plus the VL53L1X adapter and v10 telemetry.
- Modify `tests/amr_v7/test_rpi_amr_parser.py`: add v10 parsing and rejection cases while retaining legacy and v9 tests.
- Modify `tools/rpi_amr_parser.py`: accept either eight-field v9 or nine-field v10 SENS payloads.
- Create `docs/amr_v10_vl53l1x_solder_test.md`: exact wiring and post-solder validation checklist.
- Read only `Arduino/libraries/Adafruit_VL53L1X`: bundled driver used for compilation.

---

### Task 1: Add the failing v10 pure-logic contract

**Files:**
- Create: `tests/amr_v10/test_amr_v10_pure.py`
- Read: `tests/amr_v9/test_amr_v9_pure.py`
- Expected later source: `Arduino/AMR_state_v10_ino/AMR_state_v10_ino.ino`

**Interfaces:**
- Consumes: v9 enums, `MqChannel`, `V9Context`, MQ calibration model, checksum helper, and executable test-report style.
- Produces: `DistanceChannel`, `update_distance_reading()`, distance-aware `evaluate_amr_state()`, distance-aware `determine_safety_fault()`, and v10 payload tests.

- [ ] **Step 1: Create the v10 test file from the v9 harness**

Copy the complete v9 harness to the v10 path, rename its title to
`HazardBot ESP32 AMR v10 Four-Sensor Pure Logic Harness`, and make source
contract checks target:

```python
V10_SOURCE = (
    Path(__file__).resolve().parents[2]
    / "Arduino"
    / "AMR_state_v10_ino"
    / "AMR_state_v10_ino.ino"
)
```

Do not remove the existing MQ calibration, state priority, checksum, or action
tests.

- [ ] **Step 2: Add the test-side distance channel model**

Add these exact constants and dataclass:

```python
DISTANCE_INVALID_MM = -1
DISTANCE_MIN_VALID_MM = 30
DISTANCE_MAX_VALID_MM = 4000
DISTANCE_WARNING_ENTER_MM = 500
DISTANCE_WARNING_EXIT_MM = 550
DISTANCE_DANGER_ENTER_MM = 200
DISTANCE_DANGER_EXIT_MM = 250


@dataclass
class DistanceChannel:
    initialized: bool = False
    last_valid_distance_mm: int = DISTANCE_INVALID_MM
    error_count: int = 0
```

Add this behavior model:

```python
def update_distance_reading(raw_distance_mm, channel):
    if not channel.initialized:
        return channel.last_valid_distance_mm, False

    raw_valid = DISTANCE_MIN_VALID_MM <= raw_distance_mm <= DISTANCE_MAX_VALID_MM
    if raw_valid:
        channel.last_valid_distance_mm = raw_distance_mm
        channel.error_count = 0
    else:
        channel.error_count += 1

    ready = (
        channel.last_valid_distance_mm != DISTANCE_INVALID_MM
        and channel.error_count < SENSOR_ERROR_COUNT_THRESHOLD
    )
    return channel.last_valid_distance_mm, ready


def is_distance_danger_enter(distance_mm):
    return DISTANCE_MIN_VALID_MM <= distance_mm <= DISTANCE_DANGER_ENTER_MM


def is_distance_danger_stay(distance_mm):
    return DISTANCE_MIN_VALID_MM <= distance_mm <= DISTANCE_DANGER_EXIT_MM


def is_distance_warning_enter(distance_mm):
    return DISTANCE_MIN_VALID_MM <= distance_mm <= DISTANCE_WARNING_ENTER_MM


def is_distance_warning_stay(distance_mm):
    return DISTANCE_MIN_VALID_MM <= distance_mm <= DISTANCE_WARNING_EXIT_MM
```

- [ ] **Step 3: Extend the wished-for safety interface**

Extend `evaluate_amr_state()` with `distance_mm` and `distance_ready` immediately
after the MQ readiness arguments. Change the sensor check to:

```python
if not mq135_ready or not mq2_ready or not distance_ready:
    return AmrState.SENSOR_ERROR
```

Keep flame as the immediate DANGER branch. Extend the combined conditions:

```python
danger_enter = (
    mq135_rise_percent >= DANGER_ENTER_PERCENT
    or mq2_rise_percent >= DANGER_ENTER_PERCENT
    or is_distance_danger_enter(distance_mm)
)
danger_stay = (
    mq135_rise_percent >= DANGER_EXIT_PERCENT
    or mq2_rise_percent >= DANGER_EXIT_PERCENT
    or is_distance_danger_stay(distance_mm)
)
warning_enter = (
    mq135_rise_percent >= WARNING_ENTER_PERCENT
    or mq2_rise_percent >= WARNING_ENTER_PERCENT
    or is_distance_warning_enter(distance_mm)
)
warning_stay = (
    mq135_rise_percent >= WARNING_EXIT_PERCENT
    or mq2_rise_percent >= WARNING_EXIT_PERCENT
    or is_distance_warning_stay(distance_mm)
)
```

Extend `determine_safety_fault()` with `distance_ready` and return
`SafetyFault.SENSOR` when any of the three sensor readiness flags is false.

- [ ] **Step 4: Extend the wished-for telemetry interface**

Add `distance_mm` as the last argument to `build_sensor_payload()` and
`build_sensor_message()`. Append it after `fault.value`:

```python
return (
    f"SENS,{mq135_average},{mq2_average},"
    f"{1 if flame_detected else 0},"
    f"{battery_to_centivolts(battery_voltage)},"
    f"{state.value},{action.value},{fault.value},{distance_mm}"
)
```

- [ ] **Step 5: Add concrete v10 behavior results**

Add separate results proving all of these cases:

```python
# Initialization failure is immediate fail-safe.
distance = DistanceChannel(initialized=False)
distance_mm, distance_ready = update_distance_reading(-1, distance)
assert distance_mm == -1 and not distance_ready

# A ready device is still fail-safe until its first valid measurement.
distance = DistanceChannel(initialized=True)
distance_mm, distance_ready = update_distance_reading(-1, distance)
assert distance_mm == -1 and not distance_ready

# First valid measurement enables the channel.
distance_mm, distance_ready = update_distance_reading(700, distance)
assert distance_mm == 700 and distance_ready

# Two transient failures retain the last value; the third invalidates it.
for _ in range(2):
    distance_mm, distance_ready = update_distance_reading(-1, distance)
assert distance_mm == 700 and distance_ready
distance_mm, distance_ready = update_distance_reading(-1, distance)
assert distance_mm == 700 and not distance_ready

# A normal reading recovers the channel.
distance_mm, distance_ready = update_distance_reading(650, distance)
assert distance_mm == 650 and distance_ready and distance.error_count == 0
```

Add state results for:

- `700mm -> SAFE`
- `350mm -> WARNING`
- `150mm` for evaluations 1 and 2 does not enter DANGER, evaluation 3 enters DANGER
- WARNING remains at `550mm` and exits at `551mm`
- DANGER remains at `250mm`; at `251mm`, with no MQ/flame hazard, it leaves DANGER
- distances `29`, `4001`, and `-1` are invalid
- flame remains immediate DANGER regardless of distance danger count
- E-Stop > 9.9V cutoff > distance error > RPi timeout > distance hazard

Add a telemetry result with exact fields:

```python
payload = build_sensor_payload(
    AmrState.WARNING,
    AmrAction.LIMITED_MOTION,
    SafetyFault.OK,
    120,
    220,
    False,
    12.0,
    350,
)
assert payload.split(",") == [
    "SENS", "120", "220", "0", "1200", "1", "1", "0", "350"
]
```

Verify its decimal ASCII-sum-modulo-256 checksum exactly as v9 does.

- [ ] **Step 6: Add future v10 source contracts**

Require these strings:

```python
required_source_contracts = [
    "File: AMR_state_v10_ino.ino",
    "#include <Wire.h>",
    "#include <Adafruit_VL53L1X.h>",
    "const int I2C_SDA_PIN = 21;",
    "const int I2C_SCL_PIN = 22;",
    "const uint8_t VL53L1X_I2C_ADDRESS = 0x29;",
    "const int VL53L1X_TIMING_BUDGET_MS = 50;",
    "const int DISTANCE_WARNING_ENTER_MM = 500;",
    "const int DISTANCE_WARNING_EXIT_MM = 550;",
    "const int DISTANCE_DANGER_ENTER_MM = 200;",
    "const int DISTANCE_DANGER_EXIT_MM = 250;",
    "distanceSensor.dataReady()",
    "distanceSensor.clearInterrupt()",
    "payload += String(distanceMm);",
    'Serial.println("AMR_state_v10 start");',
]
```

Forbid `ledcWrite`, `analogWrite`, `TB6612`, and motor pin declarations in the
v10 source contract.

- [ ] **Step 7: Run the v10 harness and verify RED**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
& 'C:\Users\rkdgm\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' tests\amr_v10\test_amr_v10_pure.py
```

Expected: the logic cases pass, but the source contract fails because
`Arduino/AMR_state_v10_ino/AMR_state_v10_ino.ino` does not exist.

- [ ] **Step 8: Commit the failing v10 contract**

Stage only `tests/amr_v10/test_amr_v10_pure.py` and commit:

```text
Add AMR v10 distance tests
```

---

### Task 2: Implement the v10 VL53L1X adapter and safety flow

**Files:**
- Create: `Arduino/AMR_state_v10_ino/AMR_state_v10_ino.ino`
- Read baseline: `Arduino/AMR_state_v9_ino/AMR_state_v9_ino.ino`
- Test: `tests/amr_v10/test_amr_v10_pure.py`

**Interfaces:**
- Consumes: every v9 function and global plus Task 1's exact distance constants and safety signatures.
- Produces: `DistanceChannel`, `initializeDistanceSensor()`, `readDistanceMm()`, `updateDistanceChannel()`, distance threshold helpers, distance-aware safety functions, and v10 telemetry.

- [ ] **Step 1: Create the v10 sketch from the complete v9 source**

Copy v9 into the new v10 path. Change only the file banner, purpose/scope
comments, protocol banner, and startup string before adding distance behavior:

```text
File: AMR_state_v10_ino.ino
AMR_state_v10 start
<SENS,mq135,mq2,flame,battCv,stateCode,actionCode,faultCode,distanceMm,checksum>
```

Remove the v9 comment that says VL53L1X is excluded. Do not edit v9.

- [ ] **Step 2: Add includes, pins, constants, and channel state**

Use:

```cpp
#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_VL53L1X.h>

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

Add:

```cpp
struct DistanceChannel {
  bool initialized;
  int lastValidDistanceMm;
  int errorCount;
};

Adafruit_VL53L1X distanceSensor;
DistanceChannel distanceChannel = {false, DISTANCE_INVALID_MM, 0};
```

- [ ] **Step 3: Declare and initialize the adapter**

Add declarations:

```cpp
void initializeDistanceSensor();
int readDistanceMm();
bool updateDistanceChannel(int rawDistanceMm);
bool isDistanceDangerEnter(int distanceMm);
bool isDistanceDangerStay(int distanceMm);
bool isDistanceWarningEnter(int distanceMm);
bool isDistanceWarningStay(int distanceMm);
```

Call `initializeDistanceSensor()` in `setup()` after the GPIO pin modes and
before initializing the MQ channels. Implement one attempt only:

```cpp
void initializeDistanceSensor() {
  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);

  if (!distanceSensor.begin(VL53L1X_I2C_ADDRESS, &Wire)) {
    distanceChannel.initialized = false;
    Serial.print("[VL53L1X] INIT_ERROR=");
    Serial.println(distanceSensor.vl_status);
    return;
  }

  if (!distanceSensor.startRanging()) {
    distanceChannel.initialized = false;
    Serial.print("[VL53L1X] RANGE_START_ERROR=");
    Serial.println(distanceSensor.vl_status);
    return;
  }

  if (!distanceSensor.setTimingBudget(VL53L1X_TIMING_BUDGET_MS)) {
    distanceChannel.initialized = false;
    Serial.print("[VL53L1X] TIMING_ERROR=");
    Serial.println(distanceSensor.vl_status);
    return;
  }

  distanceChannel.initialized = true;
  Serial.println("[VL53L1X] READY");
}
```

There is no infinite retry and no synthetic fallback distance.

- [ ] **Step 4: Implement non-blocking reads and debounced validity**

Use:

```cpp
int readDistanceMm() {
  if (!distanceChannel.initialized || !distanceSensor.dataReady()) {
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

bool updateDistanceChannel(int rawDistanceMm) {
  if (!distanceChannel.initialized) {
    return false;
  }

  bool rawValid = (
    rawDistanceMm >= DISTANCE_MIN_VALID_MM &&
    rawDistanceMm <= DISTANCE_MAX_VALID_MM
  );

  if (rawValid) {
    distanceChannel.lastValidDistanceMm = rawDistanceMm;
    distanceChannel.errorCount = 0;
  } else {
    distanceChannel.errorCount++;
  }

  return (
    distanceChannel.lastValidDistanceMm != DISTANCE_INVALID_MM &&
    distanceChannel.errorCount < SENSOR_ERROR_COUNT_THRESHOLD
  );
}
```

Implement the four inclusive threshold helpers exactly as their constants
state.

- [ ] **Step 5: Sample distance in the existing 300ms sensor block**

Immediately after updating both MQ channels, add:

```cpp
int rawDistanceMm = readDistanceMm();
bool distanceReady = updateDistanceChannel(rawDistanceMm);
int distanceMm = distanceChannel.lastValidDistanceMm;
```

Pass `distanceMm` and `distanceReady` through state evaluation, fault selection,
state-change telemetry, heartbeat telemetry, and debug output. Do not add a
second delay or a blocking wait.

- [ ] **Step 6: Extend safety evaluation**

Add `int distanceMm` and `bool distanceReady` to `evaluateAmrState()` and
`bool distanceReady` to `determineSafetyFault()`. Use:

```cpp
if (!mq135Ready || !mq2Ready || !distanceReady) {
  return STATE_SENSOR_ERROR;
}
```

Keep this check after LiPo and before RPi timeout. Keep the immediate flame
branch. Extend the existing danger and warning boolean expressions with the
four distance helpers exactly as in Task 1. In `determineSafetyFault()`, the
same three-sensor readiness check returns `FAULT_SENSOR`.

- [ ] **Step 7: Extend telemetry and debug output**

Add `int distanceMm` as the last sensor argument of `buildSensorPayload()`,
`sendSensorMessage()`, and `printDebugInfo()`. After `faultCode`, append:

```cpp
payload += ",";
payload += String(distanceMm);
```

Add debug output:

```cpp
Serial.print(" | DIST=");
if (distanceMm == DISTANCE_INVALID_MM) {
  Serial.print("INVALID");
} else {
  Serial.print(distanceMm);
  Serial.print("mm");
}
Serial.print(" | DIST_SENSOR=");
Serial.print(distanceReady ? "OK" : "ERROR");
Serial.print(" | DIST_ERROR_COUNT=");
Serial.print(distanceChannel.errorCount);
```

- [ ] **Step 8: Run v10 GREEN and v9 regression tests**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$py='C:\Users\rkdgm\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $py tests\amr_v10\test_amr_v10_pure.py
& $py tests\amr_v9\test_amr_v9_pure.py
```

Expected: both exit `0`; the v10 source contract and all v9 tests pass.

- [ ] **Step 9: Commit v10 firmware**

Stage only the v10 sketch and commit:

```text
Add VL53L1X AMR v10 firmware
```

---

### Task 3: Extend the Raspberry Pi parser for v10

**Files:**
- Modify: `tests/amr_v7/test_rpi_amr_parser.py`
- Modify: `tools/rpi_amr_parser.py`

**Interfaces:**
- Consumes: the existing `parse_amr_message(message)` API and decimal SENS checksum.
- Produces: unchanged legacy CMD parsing, unchanged v9 SENS parsing, and v10 SENS results with `distance_mm`.

- [ ] **Step 1: Add failing parser tests**

Add:

```python
def test_parses_v10_four_sensor_message(self):
    payload = "SENS,120,220,0,1200,1,1,0,350"
    checksum = sum(ord(char) for char in payload) % 256
    parsed = self.parser.parse_amr_message(f"<{payload},{checksum}>")

    self.assertEqual(parsed["command"], "SENS")
    self.assertEqual(parsed["mq135"], 120)
    self.assertEqual(parsed["mq2"], 220)
    self.assertEqual(parsed["distance_mm"], 350)


def test_rejects_v10_wrong_field_count(self):
    payload = "SENS,120,220,0,1200,1,1,0,350,999"
    checksum = sum(ord(char) for char in payload) % 256
    with self.assertRaises(ValueError):
        self.parser.parse_amr_message(f"<{payload},{checksum}>")


def test_rejects_v10_bad_decimal_checksum(self):
    with self.assertRaises(ValueError):
        self.parser.parse_amr_message(
            "<SENS,120,220,0,1200,1,1,0,350,0>"
        )
```

Keep `test_parses_v9_three_sensor_message()` unchanged and additionally assert
that `distance_mm` is not present in its result.

- [ ] **Step 2: Run parser tests and verify RED**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
& 'C:\Users\rkdgm\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.amr_v7.test_rpi_amr_parser
```

Expected: v10 parse test fails because `parse_sens_payload()` accepts only
eight fields.

- [ ] **Step 3: Implement dual v9/v10 parsing**

Change `parse_sens_payload()` to accept only lengths 8 and 9:

```python
def parse_sens_payload(payload):
    parts = payload.split(",")
    if len(parts) not in (8, 9) or parts[0] != "SENS":
        raise ValueError("SENS payload must contain 8 (v9) or 9 (v10) fields")

    try:
        parsed = {
            "command": "SENS",
            "mq135": int(parts[1]),
            "mq2": int(parts[2]),
            "flame": int(parts[3]),
            "battery_centivolts": int(parts[4]),
            "state_code": int(parts[5]),
            "action_code": int(parts[6]),
            "fault_code": int(parts[7]),
        }
        if len(parts) == 9:
            parsed["distance_mm"] = int(parts[8])
        return parsed
    except ValueError as exc:
        raise ValueError("SENS fields must be decimal integers") from exc
```

Update CLI help text from `v9 SENS` to `v9 or v10 SENS`. Do not change CMD
checksum behavior or SENS decimal checksum validation.

- [ ] **Step 4: Run parser GREEN and tool regression tests**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$py='C:\Users\rkdgm\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $py -m unittest discover -s tests\amr_v7 -p 'test_rpi_*.py'
```

Expected: all parser and keepalive tests pass.

- [ ] **Step 5: Commit parser compatibility**

Stage only the parser and parser test, then commit:

```text
Support AMR v10 distance telemetry
```

---

### Task 4: Add the soldering and hardware validation handoff

**Files:**
- Create: `docs/amr_v10_vl53l1x_solder_test.md`

**Interfaces:**
- Consumes: v10 pins, thresholds, serial field names, and fail-safe behavior.
- Produces: an exact text-only wiring and validation sequence for the later soldered sensor.

- [ ] **Step 1: Write the wiring section**

Include exactly:

```text
Power OFF before wiring.
VL53L1X VIN/VCC -> ESP32 3V3
VL53L1X GND     -> ESP32 GND
VL53L1X SDA     -> ESP32 GPIO21
VL53L1X SCL     -> ESP32 GPIO22
VL53L1X GPIO1/INT -> not connected
VL53L1X XSHUT     -> not connected
```

Warn not to connect VIN to both 3V3 and 5V, and to confirm the breakout's pin
labels before power-on.

- [ ] **Step 2: Write the post-solder checks**

List this order:

1. Continuity and short check with power off.
2. Upload the already compiled v10 sketch.
3. Confirm `[VL53L1X] READY` and address `0x29` behavior.
4. Keep RPi pings active during state checks.
5. Verify approximately 700mm SAFE, 350mm WARNING, and 150mm three-cycle DANGER.
6. Verify 500/550mm and 200/250mm hysteresis.
7. Disconnect SDA or SCL and confirm SENSOR_ERROR on the third failed cycle.
8. Reconnect with power off, reset, and confirm recovery.
9. Record measured values before changing only the four distance thresholds.

State explicitly that the current board remains on v9 until this checklist is
performed.

- [ ] **Step 3: Commit the handoff document**

Stage only the handoff document and commit:

```text
Document AMR v10 solder validation
```

---

### Task 5: Compile and verify the hardware-free v10 release candidate

**Files:**
- Verify: `Arduino/AMR_state_v10_ino/AMR_state_v10_ino.ino`
- Verify: `tests/amr_v10/test_amr_v10_pure.py`
- Verify unchanged: v7, v8, and v9 test/source paths
- Verify: `tools/rpi_amr_parser.py`

**Interfaces:**
- Consumes: completed v10 firmware, tests, parser, and handoff document.
- Produces: fresh automated evidence and a compiled binary awaiting soldered-hardware testing.

- [ ] **Step 1: Verify version and scope contracts**

Run:

```powershell
rg -n "AMR_state_v10|VL53L1X|distanceMm|I2C_SDA_PIN|I2C_SCL_PIN" Arduino\AMR_state_v10_ino tests\amr_v10 tools\rpi_amr_parser.py
rg -n "ledcWrite|analogWrite|TB6612|MOTOR" Arduino\AMR_state_v10_ino\AMR_state_v10_ino.ino
git diff --check
```

Expected: v10 contracts are present, the motor search has no executable motor
code, and `git diff --check` reports no errors.

- [ ] **Step 2: Run the complete Python verification**

Run with bytecode disabled:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$py='C:\Users\rkdgm\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $py tests\amr_v10\test_amr_v10_pure.py
if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
& $py tests\amr_v9\test_amr_v9_pure.py
if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
& $py tests\amr_v8\test_amr_v8_pure.py
if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
& $py tests\amr_v7\test_amr_v7_pure.py
if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
& $py -m unittest discover -s tests\amr_v7 -p 'test_rpi_*.py'
exit $LASTEXITCODE
```

Expected: every suite exits `0` with no failures.

- [ ] **Step 3: Compile v10 for ESP32**

Run:

```powershell
& 'C:\Program Files\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe' compile `
  --fqbn esp32:esp32:esp32 `
  --libraries 'Arduino\libraries' `
  --build-path 'tmp\arduino-v10-build' `
  'Arduino\AMR_state_v10_ino'
```

Expected: exit `0` with an ESP32 flash/RAM usage summary. Do not run `upload`.

- [ ] **Step 4: Verify v9 is still the board firmware**

Do not reset or upload. Record that the latest hardware upload performed before
this plan was the compiled v9 image and that v10 hardware verification remains
pending soldering. A passive serial read is optional and must not be described
as v10 evidence.

- [ ] **Step 5: Inspect final repository state**

Run:

```powershell
git log -6 --oneline
git status --short
git diff --check
```

Confirm only intended v10/parser/document commits were created. Preserve the
pre-existing deleted `AGENTS.md` and untracked v8, important-doc, test, and
temporary paths without staging them.

- [ ] **Step 6: Prepare the handoff**

Report:

- final code path and `AMR_state_v10` version evidence;
- v10 telemetry format;
- automated test counts and Arduino compile result;
- v9 remains uploaded on the board;
- v10 is code-complete but not hardware-confirmed until soldering;
- exact link to the solder-test checklist;
- the ESP32 5V dual-MQ supply remains suitable only for the current short bench test, not the long MQ aging/deployment power plan.
