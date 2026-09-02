# AMR v9 Three-Sensor Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and verify an ESP32 AMR v9 sketch that simultaneously reads MQ-135, MQ-2, and KY-026, fuses their relative hazard signals, fails safely, and emits checked v9 telemetry without any VL53L1X dependency.

**Architecture:** Preserve the existing single-sketch v8 structure in a new v9 folder. Model each MQ sensor as an independent channel with first-sample buffer priming, validity debounce, clean-air baseline calibration, normalized rise percentage, and fault isolation; keep KY-026 as an active-LOW digital hazard input. Mirror the decision and protocol behavior in a standalone Python harness, update the Raspberry Pi parser/keepalive utilities for the decimal sum protocol, then compile and validate on the real ESP32.

**Tech Stack:** ESP32 Arduino, C++17-compatible Arduino sketch, Python 3 standalone test harnesses, `unittest`, Arduino CLI, PowerShell, pyserial

## Global Constraints

- Work only on the sensor-only ESP32 bench configuration; do not add motor, TB6612, line tracing, ARM, servo, gripper, buzzer, or direct ESP32-to-ESP32 logic.
- Preserve `Arduino/AMR_state_v8_ino/AMR_state_v8_ino.ino` unchanged.
- Create the final sketch at `Arduino/AMR_state_v9_ino/AMR_state_v9_ino.ino` and use `AMR_state_v9` in its file banner and startup output.
- Use GPIO34 for MQ-135 AO, GPIO35 for MQ-2 AO, GPIO27 for KY-026 DO, and GPIO26 for the existing inactive `INPUT_PULLUP` E-Stop input.
- Do not include `Wire`, `Adafruit_VL53L1X`, VL53L1X initialization, distance evaluation, or `distanceMm` telemetry.
- Preserve Emergency Stop as highest priority, the LiPo cutoff at exactly `9.9V`, and the RPi timeout at exactly `3000ms`.
- Treat the bench `currentBatteryVoltage = 12.0` as a test injection, not a measured battery value.
- Use decimal ASCII-sum-modulo-256 checksums for v9 incoming keepalive and outgoing SENS telemetry.
- Use exact v9 payload order `SENS,mq135,mq2,flame,battCv,stateCode,actionCode,faultCode`.
- Treat MQ readings as relative demo signals, never certified ppm or gas identification.
- Require initial MQ aging of at least 48 hours and at least 20 minutes of warm-up before real baseline capture.
- Do not use actual flame, released butane, or sprayed flammable liquid during bench validation.

## File Map

- Create `tests/amr_v9/test_amr_v9_pure.py`: executable v9 pure-logic model, behavioral tests, protocol tests, and Arduino source-contract checks.
- Create `Arduino/AMR_state_v9_ino/AMR_state_v9_ino.ino`: final three-sensor firmware.
- Modify `tools/rpi_keepalive.py`: emit the decimal sum checksum accepted by v8/v9 firmware while retaining an explicitly named legacy-v7 helper.
- Modify `tests/amr_v7/test_rpi_keepalive_tool.py`: lock in the corrected default keepalive and legacy helper behavior.
- Modify `tools/rpi_amr_parser.py`: retain legacy named CMD parsing and add compact v9 SENS parsing.
- Modify `tests/amr_v7/test_rpi_amr_parser.py`: preserve legacy coverage and add v9 SENS cases.
- Read only `Arduino/AMR_state_v8_ino/AMR_state_v8_ino.ino`: stable implementation baseline.
- Read only `tests/amr_v8/test_amr_v8_pure.py`: stable regression baseline and report style.

---

### Task 1: Add failing v9 pure-logic and source-contract tests

**Files:**
- Create: `tests/amr_v9/test_amr_v9_pure.py`
- Read: `tests/amr_v8/test_amr_v8_pure.py`
- Expected later source: `Arduino/AMR_state_v9_ino/AMR_state_v9_ino.ino`

**Interfaces:**
- Consumes: v8 enum numeric codes, ASCII-sum checksum behavior, fail-safe priority, and standalone report pattern.
- Produces: `MqChannel`, `V9Context`, `update_mq_channel()`, `calculate_rise_percent()`, `evaluate_amr_state()`, `determine_safety_fault()`, and `build_sensor_message()` behavior that the Arduino sketch must mirror.

- [ ] **Step 1: Create the v9 model constants and contexts**

Create the file with these imports, enums copied verbatim from the v8 harness, and exact constants/context fields:

```python
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

SAMPLE_COUNT = 10
CALIBRATION_SAMPLE_COUNT = 10
CALIBRATION_SETTLE_MS = 180000
ADC_MIN_VALID_VALUE = 1
ADC_MAX_VALID_VALUE = 4094
MQ_BASELINE_MAX_VALUE = 2700
WARNING_ENTER_PERCENT = 20
WARNING_EXIT_PERCENT = 15
DANGER_ENTER_PERCENT = 50
DANGER_EXIT_PERCENT = 40
DANGER_COUNT_THRESHOLD = 3
SENSOR_ERROR_COUNT_THRESHOLD = 3
LIPO_CUTOFF_VOLTAGE = 9.9
RPI_TIMEOUT_MS = 3000


@dataclass
class MqChannel:
    samples: list[int] = field(default_factory=list)
    sample_index: int = 0
    sample_sum: int = 0
    average: int = 0
    error_count: int = 0
    baseline_sum: int = 0
    baseline_sample_count: int = 0
    baseline: int = 0
    calibration_window_started: bool = False
    calibrated: bool = False


@dataclass
class V9Context:
    mq135: MqChannel = field(default_factory=MqChannel)
    mq2: MqChannel = field(default_factory=MqChannel)
    danger_count: int = 0
```

Copy `AmrState`, `AmrAction`, `SafetyFault`, `TestResult`, `pass_if()`, and the report-printing shape from v8 without changing numeric codes.

- [ ] **Step 2: Add real first-sample priming, calibration, and fault-isolation functions**

Add these functions to the test-side model:

```python
def update_mq_channel(raw_value, channel, now_ms=CALIBRATION_SETTLE_MS):
    raw_valid = ADC_MIN_VALID_VALUE <= raw_value <= ADC_MAX_VALID_VALUE
    if not raw_valid:
        channel.error_count += 1
        return channel.average

    channel.error_count = 0
    if not channel.samples:
        channel.samples = [raw_value] * SAMPLE_COUNT
        channel.sample_sum = raw_value * SAMPLE_COUNT
        channel.average = raw_value
    else:
        channel.sample_sum -= channel.samples[channel.sample_index]
        channel.samples[channel.sample_index] = raw_value
        channel.sample_sum += raw_value
        channel.sample_index = (channel.sample_index + 1) % SAMPLE_COUNT
        channel.average = channel.sample_sum // SAMPLE_COUNT

    if not channel.calibrated and now_ms >= CALIBRATION_SETTLE_MS:
        if not channel.calibration_window_started:
            channel.samples = [raw_value] * SAMPLE_COUNT
            channel.sample_index = 0
            channel.sample_sum = raw_value * SAMPLE_COUNT
            channel.average = raw_value
            channel.calibration_window_started = True

        channel.baseline_sum += channel.average
        channel.baseline_sample_count += 1
        if channel.baseline_sample_count == CALIBRATION_SAMPLE_COUNT:
            channel.baseline = channel.baseline_sum // CALIBRATION_SAMPLE_COUNT
            channel.calibrated = (
                ADC_MIN_VALID_VALUE
                <= channel.baseline
                <= MQ_BASELINE_MAX_VALUE
            )

    return channel.average


def is_mq_channel_ready(channel):
    return (
        channel.error_count < SENSOR_ERROR_COUNT_THRESHOLD
        and channel.calibrated
    )


def calculate_rise_percent(average, baseline):
    if baseline <= 0 or average <= baseline:
        return 0
    return (average - baseline) * 100 // baseline
```

Add tests that prove:

```python
channel = MqChannel()
assert update_mq_channel(1200, channel) == 1200
assert channel.samples == [1200] * SAMPLE_COUNT

context = V9Context()
for _ in range(CALIBRATION_SAMPLE_COUNT):
    update_mq_channel(1000, context.mq135)
    update_mq_channel(600, context.mq2)
assert context.mq135.baseline == 1000
assert context.mq2.baseline == 600
assert is_mq_channel_ready(context.mq135)
assert is_mq_channel_ready(context.mq2)

update_mq_channel(0, context.mq135)
update_mq_channel(0, context.mq135)
assert is_mq_channel_ready(context.mq135)
assert is_mq_channel_ready(context.mq2)
update_mq_channel(0, context.mq135)
assert not is_mq_channel_ready(context.mq135)
assert is_mq_channel_ready(context.mq2)
```

- [ ] **Step 3: Add exact three-sensor state and fault logic**

Define `evaluate_amr_state()` with this signature:

```python
def evaluate_amr_state(
    mq135_rise_percent,
    mq2_rise_percent,
    flame_detected,
    mq135_ready,
    mq2_ready,
    battery_voltage,
    emergency_stop_active,
    rpi_timeout_active,
    last_state,
    context,
):
```

Implement this priority and behavior in the model:

```python
if emergency_stop_active:
    return AmrState.STOP
if battery_voltage <= LIPO_CUTOFF_VOLTAGE:
    return AmrState.STOP
if not mq135_ready or not mq2_ready:
    return AmrState.SENSOR_ERROR
if rpi_timeout_active:
    return AmrState.STOP
if flame_detected:
    context.danger_count = 0
    return AmrState.DANGER

danger_enter = (
    mq135_rise_percent >= DANGER_ENTER_PERCENT
    or mq2_rise_percent >= DANGER_ENTER_PERCENT
)
danger_stay = (
    mq135_rise_percent >= DANGER_EXIT_PERCENT
    or mq2_rise_percent >= DANGER_EXIT_PERCENT
)
warning_enter = (
    mq135_rise_percent >= WARNING_ENTER_PERCENT
    or mq2_rise_percent >= WARNING_ENTER_PERCENT
)
warning_stay = (
    mq135_rise_percent >= WARNING_EXIT_PERCENT
    or mq2_rise_percent >= WARNING_EXIT_PERCENT
)

if last_state == AmrState.DANGER and danger_stay:
    return AmrState.DANGER
if last_state == AmrState.DANGER:
    context.danger_count = 0

if danger_enter:
    context.danger_count += 1
else:
    context.danger_count = 0
if context.danger_count >= DANGER_COUNT_THRESHOLD:
    return AmrState.DANGER
if last_state == AmrState.WARNING and warning_stay:
    return AmrState.WARNING
if warning_enter:
    return AmrState.WARNING
return AmrState.SAFE
```

Define `determine_safety_fault()` using the same priority and return `SafetyFault.HAZARD` for DANGER/flame, then `SafetyFault.OK` otherwise. Keep `determine_amr_action()` identical to v8.

Add exact cases for:

```python
# Flame is immediate after both channels are ready.
assert evaluate_amr_state(
    0, 0, True, True, True, 12.0, False, False,
    AmrState.SAFE, V9Context()
) == AmrState.DANGER

# One MQ at 20% enters WARNING.
assert evaluate_amr_state(
    20, 0, False, True, True, 12.0, False, False,
    AmrState.SAFE, V9Context()
) == AmrState.WARNING

# WARNING stays at 15%, exits below 15%.
warning_context = V9Context()
assert evaluate_amr_state(
    15, 0, False, True, True, 12.0, False, False,
    AmrState.WARNING, warning_context
) == AmrState.WARNING
assert evaluate_amr_state(
    14, 0, False, True, True, 12.0, False, False,
    AmrState.WARNING, warning_context
) == AmrState.SAFE

# MQ DANGER requires three consecutive samples and stays at 40%.
danger_context = V9Context()
state = AmrState.SAFE
for _ in range(3):
    state = evaluate_amr_state(
        0, 50, False, True, True, 12.0, False, False,
        state, danger_context
    )
assert state == AmrState.DANGER
assert evaluate_amr_state(
    0, 40, False, True, True, 12.0, False, False,
    state, danger_context
) == AmrState.DANGER
```

Add a table proving exact priority:

```text
Emergency Stop > LiPo cutoff > either MQ error/unready > RPi timeout > hazard
```

- [ ] **Step 4: Add v9 telemetry and source-contract checks**

Use this exact payload builder:

```python
def build_sensor_payload(
    state, action, fault, mq135_average, mq2_average,
    flame_detected, battery_voltage,
):
    return (
        f"SENS,{mq135_average},{mq2_average},"
        f"{1 if flame_detected else 0},"
        f"{battery_to_centivolts(battery_voltage)},"
        f"{state.value},{action.value},{fault.value}"
    )
```

Build `<{payload},{decimal_checksum}>\n` using ASCII sum modulo 256. Verify this exact payload field list:

```python
fields == ["SENS", "120", "220", "1", "1200", "0", "0", "0"]
len(fields) == 8
```

Load the future v9 source path and require all of these strings:

```python
'File: AMR_state_v9_ino.ino'
'const int MQ135_PIN = 34;'
'const int MQ2_PIN = 35;'
'const int FLAME_PIN = 27;'
'const float LIPO_CUTOFF_VOLTAGE = 9.9;'
'const unsigned long RPI_TIMEOUT_MS = 3000;'
'payload += String(mq135Average);'
'payload += String(mq2Average);'
'Serial.println("AMR_state_v9 start");'
```

Reject the source if any of these strings are present:

```python
'Adafruit_VL53L1X'
'distanceMm'
'initializeDistanceSensor'
```

- [ ] **Step 5: Run the harness and verify the expected RED result**

Run:

```powershell
C:\Users\rkdgm\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe tests\amr_v9\test_amr_v9_pure.py
```

Expected: the pure model cases pass, then the run exits `1` because `Arduino/AMR_state_v9_ino/AMR_state_v9_ino.ino` does not exist.

- [ ] **Step 6: Commit the failing v9 harness**

```powershell
C:\Users\rkdgm\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\cmd\git.exe add -- tests\amr_v9\test_amr_v9_pure.py
C:\Users\rkdgm\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\cmd\git.exe commit -m "Add AMR v9 three-sensor tests"
```

---

### Task 2: Implement the v9 three-sensor Arduino sketch

**Files:**
- Create: `Arduino/AMR_state_v9_ino/AMR_state_v9_ino.ino`
- Read: `Arduino/AMR_state_v8_ino/AMR_state_v8_ino.ino`
- Test: `tests/amr_v9/test_amr_v9_pure.py`

**Interfaces:**
- Consumes: Task 1 constants, state semantics, telemetry order, and source contracts.
- Produces: `MqChannel`, `initializeMqChannel()`, `updateMqChannel()`, `isMqChannelReady()`, `calculateRisePercent()`, three-sensor `evaluateAmrState()`, `determineSafetyFault()`, and v9 SENS telemetry.

- [ ] **Step 1: Create v9 as a complete v8-derived sketch without distance code**

Copy the entire v8 sketch into the new v9 path. Change the file banner, purpose, startup line, and protocol banner to v9 and three sensors. Add MQ-2 but do not edit v8.

Use only:

```cpp
#include <Arduino.h>
```

Add these exact constants:

```cpp
const int MQ135_PIN = 34;
const int MQ2_PIN = 35;
const int FLAME_PIN = 27;
const int EMERGENCY_STOP_PIN = 26;

const int SAMPLE_COUNT = 10;
const int CALIBRATION_SAMPLE_COUNT = 10;
const unsigned long CALIBRATION_SETTLE_MS = 180000;
const int ADC_MIN_VALID_VALUE = 1;
const int ADC_MAX_VALID_VALUE = 4094;
const int MQ_BASELINE_MAX_VALUE = 2700;
const int WARNING_ENTER_PERCENT = 20;
const int WARNING_EXIT_PERCENT = 15;
const int DANGER_ENTER_PERCENT = 50;
const int DANGER_EXIT_PERCENT = 40;
const int DANGER_COUNT_THRESHOLD = 3;
const int SENSOR_ERROR_COUNT_THRESHOLD = 3;
```

Keep `READ_INTERVAL_MS = 300`, `RPI_TIMEOUT_MS = 3000`, and `LIPO_CUTOFF_VOLTAGE = 9.9` exactly.

- [ ] **Step 2: Add an independent MQ channel adapter**

Define:

```cpp
struct MqChannel {
  int pin;
  int samples[SAMPLE_COUNT];
  int sampleIndex;
  long sampleSum;
  int average;
  int errorCount;
  long baselineSum;
  int baselineSampleCount;
  int baseline;
  bool sampleBufferInitialized;
  bool calibrated;
};

MqChannel mq135Channel;
MqChannel mq2Channel;
```

Add and implement these functions with the same behavior as Task 1:

```cpp
void initializeMqChannel(MqChannel& channel, int pin);
void updateMqChannel(MqChannel& channel, unsigned long now);
bool isMqChannelReady(const MqChannel& channel);
int calculateRisePercent(const MqChannel& channel);
```

`updateMqChannel()` must:

1. Read `analogRead(channel.pin)` once.
2. Increment only that channel's `errorCount` for values outside `1..4094` and return without changing its average/baseline.
3. Reset that channel's error count on a valid raw value.
4. Fill all ten samples with the first valid value and set `sampleSum = raw * SAMPLE_COUNT`.
5. Use a circular moving average for subsequent values.
6. Add each valid average to baseline accumulation until ten values are collected.
7. Set `calibrated = true` only when baseline is in `1..2700`; otherwise leave the channel unready.

Initialize both channels in `setup()` and set both gas pins to `INPUT`.

- [ ] **Step 3: Pass both MQ channels through the 300ms evaluation flow**

Inside the existing read interval:

```cpp
updateMqChannel(mq135Channel, now);
updateMqChannel(mq2Channel, now);

int mq135Average = mq135Channel.average;
int mq2Average = mq2Channel.average;
int mq135RisePercent = calculateRisePercent(mq135Channel);
int mq2RisePercent = calculateRisePercent(mq2Channel);
bool mq135Ready = isMqChannelReady(mq135Channel);
bool mq2Ready = isMqChannelReady(mq2Channel);
bool flameDetected = isFlameDetected();
```

Extend the state, fault, telemetry, and debug functions to receive both averages, both rise percentages, and both ready flags. Do not share their buffers or error counters.

- [ ] **Step 4: Implement the exact safe state fusion**

Use this signature:

```cpp
AmrState evaluateAmrState(
  int mq135RisePercent,
  int mq2RisePercent,
  bool flameDetected,
  bool mq135Ready,
  bool mq2Ready,
  float batteryVoltage,
  bool emergencyStopActive,
  bool rpiTimeoutActive,
  AmrState lastState
);
```

Implement Task 1's priority exactly. Flame returns `STATE_DANGER` immediately after resetting `dangerCount`. MQ DANGER requires three consecutive readings at or above 50%, stays at or above 40%, and warning enters/stays at 20%/15% respectively. Either MQ unready returns `STATE_SENSOR_ERROR` before checking RPi timeout.

Extend `determineSafetyFault()` to return `FAULT_SENSOR` when either MQ channel is unready and `FAULT_HAZARD` for DANGER/flame.

- [ ] **Step 5: Emit v9 telemetry and complete debug output**

Implement payload order:

```cpp
String payload = "SENS";
payload += ",";
payload += String(mq135Average);
payload += ",";
payload += String(mq2Average);
payload += ",";
payload += String(flameDetected ? 1 : 0);
payload += ",";
payload += String(batteryToCentivolts(batteryVoltage));
payload += ",";
payload += String(stateToCode(state));
payload += ",";
payload += String(actionToCode(action));
payload += ",";
payload += String(faultToCode(fault));
```

Keep the decimal ASCII sum modulo 256 and frame output `<payload,checksum>\n`.

Print at least these labels on every 300ms debug line:

```text
MQ135, MQ135_BASE, MQ135_RISE, MQ135_SENSOR, MQ135_ERROR_COUNT,
MQ2, MQ2_BASE, MQ2_RISE, MQ2_SENSOR, MQ2_ERROR_COUNT,
FLAME, CALIBRATION, BAT_TEST_VALUE, STATE, ACTION, FAULT
```

Use `CALIBRATING` while either baseline is unavailable and explicitly label the battery field as `BAT_TEST_VALUE`.

- [ ] **Step 6: Run v9 and v8 harnesses for GREEN**

Run:

```powershell
C:\Users\rkdgm\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe tests\amr_v9\test_amr_v9_pure.py
C:\Users\rkdgm\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe tests\amr_v8\test_amr_v8_pure.py
```

Expected: both exit `0`; the v9 report has no `FAIL`, and the v8 report remains unchanged.

- [ ] **Step 7: Commit the v9 firmware**

```powershell
C:\Users\rkdgm\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\cmd\git.exe add -- Arduino\AMR_state_v9_ino\AMR_state_v9_ino.ino
C:\Users\rkdgm\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\cmd\git.exe commit -m "Add AMR v9 three-sensor firmware"
```

---

### Task 3: Align Raspberry Pi parser and keepalive tools with v9

**Files:**
- Modify: `tools/rpi_keepalive.py`
- Modify: `tests/amr_v7/test_rpi_keepalive_tool.py`
- Modify: `tools/rpi_amr_parser.py`
- Modify: `tests/amr_v7/test_rpi_amr_parser.py`

**Interfaces:**
- Consumes: legacy v7 `<CMD,STATE=...,CS_HEX>` and new v9 `<SENS,...,checksum_decimal>` frames.
- Produces: default v9 `build_message()`, explicit `build_legacy_v7_message()`, live response echo in `run_keepalive()`, and protocol-detecting `parse_amr_message()`.

- [ ] **Step 1: Add failing keepalive expectations**

Change/add tests to require:

```python
self.assertEqual(self.tool.calculate_checksum("CMD,PING"), 46)
self.assertEqual(self.tool.build_message("CMD,PING"), "<CMD,PING,46>\n")
self.assertEqual(
    self.tool.build_legacy_v7_message("CMD,PING"),
    "<CMD,PING,76>\n",
)

class FakeSerialInput:
    def __init__(self, lines):
        self.lines = [line.encode("utf-8") for line in lines]

    @property
    def in_waiting(self):
        return len(self.lines)

    def readline(self):
        return self.lines.pop(0)


fake = FakeSerialInput(["AMR_state_v9 start\n", "<SENS,1,2,0,1200,0,0,0,1>\n"])
self.assertEqual(
    self.tool.read_available_lines(fake),
    ["AMR_state_v9 start", "<SENS,1,2,0,1200,0,0,0,1>"],
)
```

Run:

```powershell
C:\Users\rkdgm\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m unittest tests.amr_v7.test_rpi_keepalive_tool -v
```

Expected: FAIL because the current default uses XOR/hex and no legacy helper exists.

- [ ] **Step 2: Implement default v9 and explicit legacy checksums**

In `tools/rpi_keepalive.py`, use:

```python
def calculate_checksum(payload):
    return sum(ord(char) for char in payload) % 256


def calculate_legacy_v7_checksum(payload):
    checksum = 0
    for char in payload:
        checksum ^= ord(char)
    return checksum


def build_message(payload=DEFAULT_PAYLOAD):
    return f"<{payload},{calculate_checksum(payload)}>\n"


def build_legacy_v7_message(payload=DEFAULT_PAYLOAD):
    return f"<{payload},{calculate_legacy_v7_checksum(payload):02X}>\n"
```

Keep `run_keepalive()` using `build_message()` so live v9 traffic is accepted by the firmware.

Add a separately testable response decoder:

```python
def read_available_lines(serial_port):
    lines = []
    while serial_port.in_waiting > 0:
        raw_line = serial_port.readline()
        lines.append(raw_line.decode("utf-8", errors="replace").rstrip())
    return lines
```

Extend `run_keepalive()` with `echo_responses=False` and `output_func=print`.
When enabled, call `read_available_lines()` after each interval sleep and pass every
returned line to `output_func`. This preserves one-second send spacing and captures
the firmware lines produced during that interval, including after the final send.
Add the CLI flag `--echo-responses` and forward it from `main()`.

- [ ] **Step 3: Add failing v9 parser tests while preserving v7 tests**

Add:

```python
def test_parses_v9_three_sensor_message(self):
    payload = "SENS,120,220,1,1200,0,0,0"
    checksum = sum(ord(char) for char in payload) % 256
    parsed = self.parser.parse_amr_message(f"<{payload},{checksum}>")
    self.assertEqual(parsed["command"], "SENS")
    self.assertEqual(parsed["mq135"], 120)
    self.assertEqual(parsed["mq2"], 220)
    self.assertEqual(parsed["flame"], 1)
    self.assertEqual(parsed["battery_centivolts"], 1200)
    self.assertEqual(parsed["state_code"], 0)
    self.assertEqual(parsed["action_code"], 0)
    self.assertEqual(parsed["fault_code"], 0)

def test_rejects_v9_wrong_field_count(self):
    payload = "SENS,120,220,1,1200,0,0"
    checksum = sum(ord(char) for char in payload) % 256
    with self.assertRaises(ValueError):
        self.parser.parse_amr_message(f"<{payload},{checksum}>")
```

Run the parser suite and expect the new SENS case to fail while legacy CMD cases still pass.

- [ ] **Step 4: Implement protocol detection and exact SENS parsing**

Keep the existing legacy CMD parser and XOR checksum path. Add:

```python
def calculate_sum_checksum(payload):
    return sum(ord(char) for char in payload) % 256


def parse_sens_payload(payload):
    parts = payload.split(",")
    if len(parts) != 8 or parts[0] != "SENS":
        raise ValueError("v9 SENS payload must contain exactly 8 fields")
    return {
        "command": "SENS",
        "mq135": int(parts[1]),
        "mq2": int(parts[2]),
        "flame": int(parts[3]),
        "battery_centivolts": int(parts[4]),
        "state_code": int(parts[5]),
        "action_code": int(parts[6]),
        "fault_code": int(parts[7]),
    }
```

In `parse_amr_message()`, inspect the payload command. For `SENS`, accept a one-to-three digit decimal checksum in `0..255`, verify `calculate_sum_checksum()`, and call `parse_sens_payload()`. For `CMD`, keep the two-character hex XOR behavior and existing return fields. Reject unknown commands.

- [ ] **Step 5: Run all tool tests**

```powershell
C:\Users\rkdgm\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m unittest tests.amr_v7.test_rpi_keepalive_tool tests.amr_v7.test_rpi_amr_parser -v
```

Expected: all tests pass with zero errors/failures.

- [ ] **Step 6: Commit the protocol tool changes**

```powershell
C:\Users\rkdgm\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\cmd\git.exe add -- tools\rpi_keepalive.py tools\rpi_amr_parser.py tests\amr_v7\test_rpi_keepalive_tool.py tests\amr_v7\test_rpi_amr_parser.py
C:\Users\rkdgm\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\cmd\git.exe commit -m "Align AMR tools with v9 protocol"
```

---

### Task 4: Compile and perform hardware-free final verification

**Files:**
- Verify: `Arduino/AMR_state_v9_ino/AMR_state_v9_ino.ino`
- Verify: `tests/amr_v9/test_amr_v9_pure.py`
- Verify: `tools/rpi_keepalive.py`
- Verify: `tools/rpi_amr_parser.py`
- Verify unchanged: `Arduino/AMR_state_v8_ino/AMR_state_v8_ino.ino`

**Interfaces:**
- Consumes: finished v9 firmware and matching host tools.
- Produces: fresh build/test evidence before hardware upload.

- [ ] **Step 1: Run all relevant Python tests**

```powershell
C:\Users\rkdgm\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe tests\amr_v9\test_amr_v9_pure.py
C:\Users\rkdgm\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe tests\amr_v8\test_amr_v8_pure.py
C:\Users\rkdgm\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m unittest tests.amr_v7.test_rpi_keepalive_tool tests.amr_v7.test_rpi_amr_parser -v
```

Expected: every command exits `0`, with no FAIL or unittest failure/error.

- [ ] **Step 2: Compile the exact v9 sketch**

Use the installed Arduino CLI and repository libraries:

```powershell
& 'C:\Program Files\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe' compile --fqbn esp32:esp32:esp32 --libraries 'Arduino\libraries' --build-path 'tmp\arduino-v9-three-sensor-build' 'Arduino\AMR_state_v9_ino'
```

Expected: exit `0`, sketch name/path reports v9, and no VL53L1X dependency appears in the library list.

- [ ] **Step 3: Check source and repository invariants**

```powershell
rg -n "AMR_state_v9|MQ135_PIN|MQ2_PIN|FLAME_PIN|SENS" Arduino\AMR_state_v9_ino tests\amr_v9
rg -n "Adafruit_VL53L1X|distanceMm|initializeDistanceSensor" Arduino\AMR_state_v9_ino tests\amr_v9
git diff --check
git status --short
```

Expected: first search shows v9/three-sensor contracts; second search returns no matches; `git diff --check` reports no whitespace errors. Existing unrelated user changes may remain untracked/modified, but only planned files belong to this feature.

- [ ] **Step 4: Record firmware identity evidence**

Capture the compiled source path and startup strings:

```text
File: Arduino/AMR_state_v9_ino/AMR_state_v9_ino.ino
Startup: AMR_state_v9 start
Protocol: <SENS,mq135,mq2,flame,battCv,stateCode,actionCode,faultCode,checksum>
Active sensors: MQ-135, MQ-2, KY-026
Excluded sensor: VL53L1X
```

---

### Task 5: Upload and validate all three physical sensors together

**Files:**
- Upload: `Arduino/AMR_state_v9_ino/AMR_state_v9_ino.ino`
- Use: `tools/rpi_keepalive.py`
- Use: `tools/rpi_amr_parser.py`

**Interfaces:**
- Consumes: compiled v9 firmware, exact approved wiring, warmed sensor hardware, and a detected serial port.
- Produces: live evidence that all three sensors update together, calibrate, respond, and fail independently.

- [ ] **Step 1: Perform the unpowered wiring inspection**

Confirm all of these before applying power:

```text
MQ-135: VCC -> external 5V, GND -> common GND,
        AO -> 10k -> GPIO34 midpoint, midpoint -> 20k -> GND, DO open
MQ-2:   VCC -> external 5V, GND -> common GND,
        AO -> 10k -> GPIO35 midpoint, midpoint -> 20k -> GND, DO open
KY-026: VCC -> ESP32 3V3, GND -> common GND, DO -> GPIO27, AO open
External 5V -> MQ VCC only; never ESP32 VIN/5V while USB is connected
All grounds common
```

Use a multimeter continuity/resistance check to confirm each ADC midpoint has its own 20kΩ path to GND and no direct 5V-to-ESP32 VIN/5V connection exists.

- [ ] **Step 2: Detect the ESP32 serial port**

```powershell
Get-CimInstance Win32_SerialPort | Select-Object DeviceID,Name,Description
```

Expected: DOIT/CP210x/CH340 ESP32 serial device, historically `COM4`. Use the detected port rather than assuming COM4.

- [ ] **Step 3: Upload the compiled v9 firmware**

Resolve the detected device into a PowerShell variable and fail if none exists:

```powershell
$serialPort = Get-CimInstance Win32_SerialPort | Select-Object -First 1 -ExpandProperty DeviceID
if (-not $serialPort) { throw 'No ESP32 serial port detected' }
& 'C:\Program Files\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe' upload --fqbn esp32:esp32:esp32 --port $serialPort --input-dir 'tmp\arduino-v9-three-sensor-build' 'Arduino\AMR_state_v9_ino'
```

Expected: exit `0`. If connection stalls, hold BOOT only during the connection phase and retry.

- [ ] **Step 4: Warm and calibrate safely**

Power the MQ heaters for at least 20 minutes. Then press ESP32 RESET without interrupting heater power. Observe 180 seconds of `SETTLING`, ten 300ms `CALIBRATING` samples, and then both channels reporting `READY`. Do not accept calibration if either baseline is `0`, above `2700`, or the value drifts more than 20% in clean air.

- [ ] **Step 5: Run v9 keepalive and capture live serial**

Use the corrected decimal checksum keepalive at one-second intervals:

```powershell
C:\Users\rkdgm\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe tools\rpi_keepalive.py --port $serialPort --interval 1.0 --count 30 --echo-responses
```

Because one process owns a Windows serial port at a time, do not open Arduino Serial
Monitor while the Python keepalive/response echo owns the port.

Expected live evidence:

```text
AMR_state_v9 start
MQ135=<1..4094> | MQ2=<1..4094> | FLAME=NO
MQ135_BASE=<1..2700> | MQ2_BASE=<1..2700>
MQ135_SENSOR=OK | MQ2_SENSOR=OK | CALIBRATION=READY
```

- [ ] **Step 6: Verify KY-026 and independent MQ fault isolation**

Use an IR remote to trigger KY-026 and confirm `FLAME=YES`, `STATE=DANGER`, `FAULT=5` without an actual flame.

Then, one at a time:

1. Disconnect only MQ-135 AO after power is stable; after three invalid cycles verify MQ-135 ERROR while MQ-2 continues updating and the system reports SENSOR_ERROR/STOP_MOTION.
2. Restore MQ-135 and verify recovery.
3. Disconnect only MQ-2 AO; verify the symmetric result while MQ-135 continues updating.
4. Restore MQ-2 and verify recovery.

If a floating disconnected ADC happens to remain in `1..4094`, temporarily connect that ADC input to GND through 10kΩ to produce a deterministic invalid value of 0; never connect an ESP32 ADC directly to 5V.

- [ ] **Step 7: Parse a captured v9 telemetry frame**

Pass one real `<SENS,...>` line to:

```powershell
$sensFrame = Read-Host 'Paste one complete SENS frame from the live output'
C:\Users\rkdgm\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe tools\rpi_amr_parser.py $sensFrame
```

Expected: command, MQ-135, MQ-2, flame, battery centivolts, state, action, and fault print with no checksum error.

- [ ] **Step 8: Run fresh final verification and prepare handoff**

Re-run Task 4's complete Python suite, Arduino compile, `git diff --check`, and `git status --short`. Report exact test totals, compile exit code, detected port, observed baselines/ranges, KY-026 response, both MQ fault-isolation results, and any hardware item not verified.

Do not claim ppm accuracy, real battery measurement, gas-type identification, or VL53L1X validation.
