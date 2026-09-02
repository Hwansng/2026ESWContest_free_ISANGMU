from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class AmrState(Enum):
    SAFE = 0
    WARNING = 1
    DANGER = 2
    STOP = 3
    SENSOR_ERROR = 4


class AmrAction(Enum):
    NORMAL_MOTION = 0
    LIMITED_MOTION = 1
    STOP_MOTION = 2


class SafetyFault(Enum):
    OK = 0
    ESTOP = 1
    LIPO = 2
    SENSOR = 3
    RPI_TIMEOUT = 4
    HAZARD = 5


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


@dataclass
class TestResult:
    test_id: str
    name: str
    status: str
    detail: str


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


def determine_amr_action(state):
    if state == AmrState.SAFE:
        return AmrAction.NORMAL_MOTION
    if state == AmrState.WARNING:
        return AmrAction.LIMITED_MOTION
    return AmrAction.STOP_MOTION


def determine_safety_fault(
    state,
    flame_detected,
    mq135_ready,
    mq2_ready,
    battery_voltage,
    emergency_stop_active,
    rpi_timeout_active,
):
    if emergency_stop_active:
        return SafetyFault.ESTOP
    if battery_voltage <= LIPO_CUTOFF_VOLTAGE:
        return SafetyFault.LIPO
    if not mq135_ready or not mq2_ready:
        return SafetyFault.SENSOR
    if rpi_timeout_active:
        return SafetyFault.RPI_TIMEOUT
    if state == AmrState.DANGER or flame_detected:
        return SafetyFault.HAZARD
    return SafetyFault.OK


def calculate_checksum(payload):
    return sum(ord(char) for char in payload) % 256


def battery_to_centivolts(battery_voltage):
    return int(battery_voltage * 100 + 0.5)


def build_sensor_payload(
    state,
    action,
    fault,
    mq135_average,
    mq2_average,
    flame_detected,
    battery_voltage,
):
    return (
        f"SENS,{mq135_average},{mq2_average},"
        f"{1 if flame_detected else 0},"
        f"{battery_to_centivolts(battery_voltage)},"
        f"{state.value},{action.value},{fault.value}"
    )


def build_sensor_message(
    state,
    action,
    fault,
    mq135_average,
    mq2_average,
    flame_detected,
    battery_voltage,
):
    payload = build_sensor_payload(
        state,
        action,
        fault,
        mq135_average,
        mq2_average,
        flame_detected,
        battery_voltage,
    )
    return f"<{payload},{calculate_checksum(payload)}>\n"


def pass_if(test_id, name, condition, detail):
    return TestResult(test_id, name, "PASS" if condition else "FAIL", detail)


def load_v9_source():
    repo_root = Path(__file__).resolve().parents[3]
    source_path = (repo_root / "firmware" / "esp32_env"
                   / "AMR_state_v9_ino" / "AMR_state_v9_ino.ino")
    if not source_path.exists():
        return ""
    return source_path.read_text(encoding="utf-8", errors="replace")


def ready_context(mq135_baseline=1000, mq2_baseline=600):
    context = V9Context()
    for _ in range(CALIBRATION_SAMPLE_COUNT):
        update_mq_channel(mq135_baseline, context.mq135)
        update_mq_channel(mq2_baseline, context.mq2)
    return context


def run_tests():
    results = []

    settling = MqChannel()
    for now_ms in range(0, CALIBRATION_SETTLE_MS, 300):
        update_mq_channel(600, settling, now_ms=now_ms)
    update_mq_channel(200, settling, now_ms=CALIBRATION_SETTLE_MS)
    for sample_index in range(1, CALIBRATION_SAMPLE_COUNT):
        update_mq_channel(
            200,
            settling,
            now_ms=CALIBRATION_SETTLE_MS + sample_index * 300,
        )
    results.append(
        pass_if(
            "T_CALIBRATION_SETTLE",
            "baseline waits 180 seconds and reprimes after MQ heater settling",
            settling.baseline == 200
            and settling.calibrated
            and settling.samples == [200] * SAMPLE_COUNT,
            (
                f"baseline={settling.baseline}, "
                f"window_started={settling.calibration_window_started}"
            ),
        )
    )

    primed = MqChannel()
    primed_average = update_mq_channel(1200, primed)
    results.append(
        pass_if(
            "T_MQ_FIRST_SAMPLE_PRIMES",
            "first real sample primes the complete moving average",
            primed_average == 1200
            and primed.samples == [1200] * SAMPLE_COUNT
            and primed.sample_sum == 12000,
            f"average={primed_average}, samples={primed.samples}",
        )
    )

    calibrated = ready_context()
    results.extend(
        [
            pass_if(
                "T_MQ135_CALIBRATION",
                "MQ-135 calibrates independently",
                calibrated.mq135.baseline == 1000
                and is_mq_channel_ready(calibrated.mq135),
                f"baseline={calibrated.mq135.baseline}",
            ),
            pass_if(
                "T_MQ2_CALIBRATION",
                "MQ-2 calibrates independently",
                calibrated.mq2.baseline == 600
                and is_mq_channel_ready(calibrated.mq2),
                f"baseline={calibrated.mq2.baseline}",
            ),
            pass_if(
                "T_MQ_RISE_PERCENT",
                "relative rise percent uses each clean-air baseline",
                calculate_rise_percent(1200, 1000) == 20
                and calculate_rise_percent(900, 1000) == 0,
                "1200/1000 -> 20%, below baseline -> 0%",
            ),
        ]
    )

    update_mq_channel(0, calibrated.mq135)
    update_mq_channel(0, calibrated.mq135)
    two_failures_still_ready = is_mq_channel_ready(calibrated.mq135)
    update_mq_channel(0, calibrated.mq135)
    results.extend(
        [
            pass_if(
                "T_MQ_ERROR_DEBOUNCE",
                "MQ error requires three consecutive invalid readings",
                two_failures_still_ready
                and not is_mq_channel_ready(calibrated.mq135),
                f"mq135_error_count={calibrated.mq135.error_count}",
            ),
            pass_if(
                "T_MQ_FAULT_ISOLATION",
                "MQ-135 failure does not invalidate MQ-2",
                is_mq_channel_ready(calibrated.mq2)
                and calibrated.mq2.error_count == 0,
                (
                    f"mq135_ready={is_mq_channel_ready(calibrated.mq135)}, "
                    f"mq2_ready={is_mq_channel_ready(calibrated.mq2)}"
                ),
            ),
        ]
    )
    update_mq_channel(1000, calibrated.mq135)
    results.append(
        pass_if(
            "T_MQ_RECOVERY",
            "valid MQ input clears its debounced error",
            is_mq_channel_ready(calibrated.mq135)
            and calibrated.mq135.error_count == 0,
            f"mq135_error_count={calibrated.mq135.error_count}",
        )
    )

    uncalibrated_state = evaluate_amr_state(
        mq135_rise_percent=0,
        mq2_rise_percent=0,
        flame_detected=False,
        mq135_ready=False,
        mq2_ready=True,
        battery_voltage=12.0,
        emergency_stop_active=False,
        rpi_timeout_active=False,
        last_state=AmrState.SAFE,
        context=V9Context(),
    )
    results.append(
        pass_if(
            "T_CALIBRATION_FAIL_SAFE",
            "uncalibrated MQ channel stays fail-safe",
            uncalibrated_state == AmrState.SENSOR_ERROR,
            f"state={uncalibrated_state.name}",
        )
    )

    priority_cases = [
        (
            "T_PRIORITY_ESTOP",
            dict(
                mq135_rise_percent=60,
                mq2_rise_percent=60,
                flame_detected=True,
                mq135_ready=False,
                mq2_ready=False,
                battery_voltage=9.0,
                emergency_stop_active=True,
                rpi_timeout_active=True,
            ),
            AmrState.STOP,
            SafetyFault.ESTOP,
        ),
        (
            "T_PRIORITY_LIPO",
            dict(
                mq135_rise_percent=60,
                mq2_rise_percent=60,
                flame_detected=True,
                mq135_ready=False,
                mq2_ready=False,
                battery_voltage=9.9,
                emergency_stop_active=False,
                rpi_timeout_active=True,
            ),
            AmrState.STOP,
            SafetyFault.LIPO,
        ),
        (
            "T_PRIORITY_SENSOR",
            dict(
                mq135_rise_percent=60,
                mq2_rise_percent=60,
                flame_detected=True,
                mq135_ready=False,
                mq2_ready=True,
                battery_voltage=12.0,
                emergency_stop_active=False,
                rpi_timeout_active=True,
            ),
            AmrState.SENSOR_ERROR,
            SafetyFault.SENSOR,
        ),
        (
            "T_PRIORITY_RPI_TIMEOUT",
            dict(
                mq135_rise_percent=60,
                mq2_rise_percent=60,
                flame_detected=True,
                mq135_ready=True,
                mq2_ready=True,
                battery_voltage=12.0,
                emergency_stop_active=False,
                rpi_timeout_active=True,
            ),
            AmrState.STOP,
            SafetyFault.RPI_TIMEOUT,
        ),
    ]
    for test_id, kwargs, expected_state, expected_fault in priority_cases:
        state = evaluate_amr_state(
            last_state=AmrState.SAFE,
            context=V9Context(),
            **kwargs,
        )
        fault = determine_safety_fault(
            state=state,
            flame_detected=kwargs["flame_detected"],
            mq135_ready=kwargs["mq135_ready"],
            mq2_ready=kwargs["mq2_ready"],
            battery_voltage=kwargs["battery_voltage"],
            emergency_stop_active=kwargs["emergency_stop_active"],
            rpi_timeout_active=kwargs["rpi_timeout_active"],
        )
        results.append(
            pass_if(
                test_id,
                "safety priority is preserved",
                state == expected_state and fault == expected_fault,
                f"state={state.name}, fault={fault.name}",
            )
        )

    flame_context = V9Context()
    flame_state = evaluate_amr_state(
        0,
        0,
        True,
        True,
        True,
        12.0,
        False,
        False,
        AmrState.SAFE,
        flame_context,
    )
    results.append(
        pass_if(
            "T_FLAME_IMMEDIATE_DANGER",
            "KY-026 active LOW input maps to immediate DANGER",
            flame_state == AmrState.DANGER,
            f"state={flame_state.name}",
        )
    )

    warning_context = V9Context()
    warning_enter_state = evaluate_amr_state(
        20,
        0,
        False,
        True,
        True,
        12.0,
        False,
        False,
        AmrState.SAFE,
        warning_context,
    )
    warning_stay_state = evaluate_amr_state(
        15,
        0,
        False,
        True,
        True,
        12.0,
        False,
        False,
        AmrState.WARNING,
        warning_context,
    )
    warning_exit_state = evaluate_amr_state(
        14,
        0,
        False,
        True,
        True,
        12.0,
        False,
        False,
        AmrState.WARNING,
        warning_context,
    )
    results.append(
        pass_if(
            "T_WARNING_HYSTERESIS",
            "warning enters at 20%, stays at 15%, exits below 15%",
            warning_enter_state == AmrState.WARNING
            and warning_stay_state == AmrState.WARNING
            and warning_exit_state == AmrState.SAFE,
            (
                f"enter={warning_enter_state.name}, "
                f"stay={warning_stay_state.name}, exit={warning_exit_state.name}"
            ),
        )
    )

    danger_context = V9Context()
    danger_state = AmrState.SAFE
    intermediate_states = []
    for _ in range(DANGER_COUNT_THRESHOLD):
        danger_state = evaluate_amr_state(
            0,
            50,
            False,
            True,
            True,
            12.0,
            False,
            False,
            danger_state,
            danger_context,
        )
        intermediate_states.append(danger_state)
    danger_stay_state = evaluate_amr_state(
        0,
        40,
        False,
        True,
        True,
        12.0,
        False,
        False,
        danger_state,
        danger_context,
    )
    results.append(
        pass_if(
            "T_DANGER_PERSISTENCE",
            "MQ danger requires three readings and stays at 40%",
            intermediate_states[:2] == [AmrState.WARNING, AmrState.WARNING]
            and intermediate_states[2] == AmrState.DANGER
            and danger_stay_state == AmrState.DANGER,
            f"states={[state.name for state in intermediate_states]}, stay={danger_stay_state.name}",
        )
    )

    results.append(
        pass_if(
            "T_UNSAFE_ACTION_STOP",
            "DANGER, STOP, and SENSOR_ERROR stop motion",
            all(
                determine_amr_action(state) == AmrAction.STOP_MOTION
                for state in [AmrState.DANGER, AmrState.STOP, AmrState.SENSOR_ERROR]
            ),
            "DANGER/STOP/SENSOR_ERROR -> STOP_MOTION",
        )
    )

    message = build_sensor_message(
        AmrState.SAFE,
        AmrAction.NORMAL_MOTION,
        SafetyFault.OK,
        120,
        220,
        True,
        12.0,
    )
    body = message[1:-2]
    payload, checksum_text = body.rsplit(",", 1)
    fields = payload.split(",")
    results.extend(
        [
            pass_if(
                "T_MSG_FIELDS",
                "v9 telemetry has exact three-sensor field order",
                fields == ["SENS", "120", "220", "1", "1200", "0", "0", "0"]
                and len(fields) == 8,
                str(fields),
            ),
            pass_if(
                "T_MSG_CHECKSUM",
                "v9 telemetry uses decimal ASCII sum modulo 256",
                checksum_text.isdecimal()
                and int(checksum_text) == calculate_checksum(payload),
                f"payload={payload}, checksum={checksum_text}",
            ),
        ]
    )

    v9_source = load_v9_source()
    required_source_contracts = [
        "File: AMR_state_v9_ino.ino",
        "const int MQ135_PIN = 34;",
        "const int MQ2_PIN = 35;",
        "const int FLAME_PIN = 27;",
        "const unsigned long CALIBRATION_SETTLE_MS = 180000;",
        "const float LIPO_CUTOFF_VOLTAGE = 9.9;",
        "const unsigned long RPI_TIMEOUT_MS = 3000;",
        "payload += String(mq135Average);",
        "payload += String(mq2Average);",
        "updateMqChannel(mq135Channel, now);",
        'Serial.println("AMR_state_v9 start");',
    ]
    forbidden_source_contracts = [
        "Adafruit_VL53L1X",
        "distanceMm",
        "initializeDistanceSensor",
    ]
    results.extend(
        [
            pass_if(
                "T_SRC_V9_CONTRACTS",
                "v9 source exposes the approved three-sensor contracts",
                bool(v9_source)
                and all(contract in v9_source for contract in required_source_contracts),
                "source missing" if not v9_source else "required contracts checked",
            ),
            pass_if(
                "T_SRC_DISTANCE_EXCLUDED",
                "v9 source excludes the unsoldered distance sensor",
                bool(v9_source)
                and all(contract not in v9_source for contract in forbidden_source_contracts),
                "source missing" if not v9_source else "forbidden contracts checked",
            ),
        ]
    )

    return results


def print_report(results):
    print("HazardBot ESP32 AMR v9 Three-Sensor Pure Logic Harness")
    print("=" * 58)
    print("Legend: PASS = v9 behavior verified, FAIL = missing behavior or regression")
    print()

    for result in results:
        print(f"[{result.status:4}] {result.test_id:28} {result.name}")
        print(f"       {result.detail}")

    print()
    totals = {}
    for result in results:
        totals[result.status] = totals.get(result.status, 0) + 1
    print(
        "Summary: "
        + ", ".join(f"{status}={count}" for status, count in sorted(totals.items()))
    )

    failures = [result for result in results if result.status == "FAIL"]
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    print_report(run_tests())
