from dataclasses import dataclass
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


LIPO_CUTOFF_VOLTAGE = 9.9
GAS_WARNING_ENTER_THRESHOLD = 1400
GAS_WARNING_EXIT_THRESHOLD = 1350
GAS_DANGER_ENTER_THRESHOLD = 1500
GAS_DANGER_EXIT_THRESHOLD = 1450
DANGER_COUNT_THRESHOLD = 3
SENSOR_ERROR_COUNT_THRESHOLD = 3
RPI_TIMEOUT_MS = 3000


@dataclass
class V8Context:
    danger_count: int = 0
    sensor_error_count: int = 0


@dataclass
class TestResult:
    test_id: str
    name: str
    status: str
    detail: str


def state_to_string(state):
    return state.name


def calculate_checksum(payload):
    return sum(ord(char) for char in payload) % 256


def battery_to_centivolts(battery_voltage):
    return int(battery_voltage * 100 + 0.5)


def build_sensor_payload(state, action, fault, gas_average, flame_detected, battery_voltage):
    return (
        f"SENS,{gas_average},{1 if flame_detected else 0},"
        f"{battery_to_centivolts(battery_voltage)},"
        f"{state.value},{action.value},{fault.value}"
    )


def build_sensor_message(state, action, fault, gas_average, flame_detected, battery_voltage):
    payload = build_sensor_payload(
        state,
        action,
        fault,
        gas_average,
        flame_detected,
        battery_voltage,
    )
    return f"<{payload},{calculate_checksum(payload)}>\n"


def build_rpi_message(payload):
    return f"<{payload},{calculate_checksum(payload)}>"


def is_valid_rpi_message(message):
    if not message.startswith("<") or not message.endswith(">"):
        return False

    body = message[1:-1]
    if "," not in body:
        return False

    payload, checksum_text = body.rsplit(",", 1)
    if not checksum_text.isdecimal():
        return False

    expected_checksum = int(checksum_text)
    if expected_checksum < 0 or expected_checksum > 255:
        return False

    return calculate_checksum(payload) == expected_checksum


def is_gas_sensor_valid(gas_average, context):
    valid = 1 <= gas_average <= 4094
    if valid:
        context.sensor_error_count = 0
    else:
        context.sensor_error_count += 1
    return context.sensor_error_count < SENSOR_ERROR_COUNT_THRESHOLD


def evaluate_amr_state(
    gas_average,
    flame_detected,
    gas_sensor_valid,
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

    if not gas_sensor_valid:
        return AmrState.SENSOR_ERROR

    if rpi_timeout_active:
        return AmrState.STOP

    danger_enter_condition = flame_detected or gas_average >= GAS_DANGER_ENTER_THRESHOLD
    danger_stay_condition = flame_detected or gas_average >= GAS_DANGER_EXIT_THRESHOLD

    if last_state == AmrState.DANGER:
        if danger_stay_condition:
            return AmrState.DANGER
        context.danger_count = 0

    if danger_enter_condition:
        context.danger_count += 1
    else:
        context.danger_count = 0

    if context.danger_count >= DANGER_COUNT_THRESHOLD:
        return AmrState.DANGER

    if last_state == AmrState.WARNING and gas_average >= GAS_WARNING_EXIT_THRESHOLD:
        return AmrState.WARNING

    if gas_average >= GAS_WARNING_ENTER_THRESHOLD:
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
    gas_sensor_valid,
    battery_voltage,
    emergency_stop_active,
    rpi_timeout_active,
):
    if emergency_stop_active:
        return SafetyFault.ESTOP
    if battery_voltage <= LIPO_CUTOFF_VOLTAGE:
        return SafetyFault.LIPO
    if not gas_sensor_valid:
        return SafetyFault.SENSOR
    if rpi_timeout_active:
        return SafetyFault.RPI_TIMEOUT
    if state == AmrState.DANGER or flame_detected:
        return SafetyFault.HAZARD
    return SafetyFault.OK


def pass_if(test_id, name, condition, detail):
    return TestResult(test_id, name, "PASS" if condition else "FAIL", detail)


def load_v8_source():
    repo_root = Path(__file__).resolve().parents[3]
    source_path = (repo_root / "archive" / "firmware_esp32_env_history"
                   / "AMR_state_v8_ino" / "AMR_state_v8_ino.ino")
    return source_path.read_text(encoding="utf-8", errors="replace")


def run_tests():
    results = []
    v8_source = load_v8_source()

    for state in AmrState:
        results.append(
            pass_if(
                f"T_STATE_{state.name}",
                f"state string {state.name}",
                state_to_string(state) == state.name,
                f"{state.name} -> {state_to_string(state)}",
            )
        )

    message = build_sensor_message(
        AmrState.SAFE,
        AmrAction.NORMAL_MOTION,
        SafetyFault.OK,
        120,
        True,
        12.0,
    )
    body = message[1:-2]
    payload, checksum_text = body.rsplit(",", 1)
    fields = payload.split(",")

    results.extend(
        [
            pass_if("T_MSG_START", "message starts with <", message.startswith("<"), message),
            pass_if("T_MSG_END", "message has > before newline", message.endswith(">\n"), message),
            pass_if(
                "T_MSG_SENS_FORMAT",
                "message uses SENS compact telemetry",
                fields[0] == "SENS" and len(fields) == 7,
                str(fields),
            ),
            pass_if(
                "T_MSG_CHECKSUM_DECIMAL",
                "checksum is decimal ASCII sum modulo 256",
                checksum_text.isdecimal()
                and int(checksum_text) == calculate_checksum(payload),
                f"payload={payload}, checksum={checksum_text}",
            ),
            pass_if(
                "T_MSG_NO_NAMED_FIELDS",
                "message removes v7 named STATE/GAS/BAT fields",
                all("=" not in field for field in fields),
                str(fields),
            ),
            pass_if(
                "T_RPI_MOVE_VALID",
                "valid RPi MOVE checksum is accepted",
                is_valid_rpi_message(build_rpi_message("MOVE,150,150")),
                build_rpi_message("MOVE,150,150"),
            ),
            pass_if(
                "T_RPI_BAD_CHECKSUM",
                "bad RPi checksum is rejected",
                not is_valid_rpi_message("<MOVE,150,150,0>"),
                "<MOVE,150,150,0>",
            ),
        ]
    )

    source_checks = [
        (
            "T_SRC_V8_FOLDER",
            "v8 source exists separately from v7",
            "AMR_state_v8" in v8_source,
            "v7 should remain as a stable baseline.",
        ),
        (
            "T_SRC_SENS_PAYLOAD",
            "v8 source builds SENS payload",
            'String payload = "SENS";' in v8_source,
            "RPi amr_bridge should receive SENS telemetry.",
        ),
        (
            "T_SRC_SUM_CHECKSUM",
            "v8 source uses ASCII sum checksum",
            "checksum = (checksum + (byte)payload[i]) % 256;" in v8_source,
            "PDF protocol says ASCII sum modulo 256.",
        ),
        (
            "T_SRC_DECIMAL_CHECKSUM",
            "v8 source validates decimal checksum",
            "isDecimalChecksum" in v8_source,
            "Incoming RPi messages should use decimal checksum.",
        ),
    ]
    for test_id, name, condition, detail in source_checks:
        results.append(pass_if(test_id, name, condition, detail))

    priority_cases = [
        (
            "T_SAFE_ESTOP_PRIORITY",
            "Emergency Stop has highest priority",
            dict(
                gas_average=1200,
                flame_detected=False,
                gas_sensor_valid=True,
                battery_voltage=12.0,
                emergency_stop_active=True,
                rpi_timeout_active=False,
            ),
            AmrState.STOP,
            SafetyFault.ESTOP,
        ),
        (
            "T_SAFE_LIPO_PRIORITY",
            "LiPo cutoff overrides normal sensor state",
            dict(
                gas_average=1200,
                flame_detected=False,
                gas_sensor_valid=True,
                battery_voltage=9.9,
                emergency_stop_active=False,
                rpi_timeout_active=False,
            ),
            AmrState.STOP,
            SafetyFault.LIPO,
        ),
        (
            "T_SAFE_SENSOR_ERROR",
            "sensor error becomes SENSOR_ERROR",
            dict(
                gas_average=0,
                flame_detected=False,
                gas_sensor_valid=False,
                battery_voltage=12.0,
                emergency_stop_active=False,
                rpi_timeout_active=False,
            ),
            AmrState.SENSOR_ERROR,
            SafetyFault.SENSOR,
        ),
        (
            "T_SAFE_RPI_TIMEOUT",
            "RPi timeout falls back to STOP",
            dict(
                gas_average=1200,
                flame_detected=False,
                gas_sensor_valid=True,
                battery_voltage=12.0,
                emergency_stop_active=False,
                rpi_timeout_active=True,
            ),
            AmrState.STOP,
            SafetyFault.RPI_TIMEOUT,
        ),
    ]
    for test_id, name, kwargs, expected_state, expected_fault in priority_cases:
        state = evaluate_amr_state(
            last_state=AmrState.SAFE,
            context=V8Context(),
            **kwargs,
        )
        fault = determine_safety_fault(state=state, **{k: v for k, v in kwargs.items() if k != "gas_average"})
        results.append(
            pass_if(
                test_id,
                name,
                state == expected_state and fault == expected_fault,
                f"state={state.name}, fault={fault.name}",
            )
        )

    danger_context = V8Context()
    danger_state = AmrState.SAFE
    for _ in range(DANGER_COUNT_THRESHOLD):
        danger_state = evaluate_amr_state(
            gas_average=1500,
            flame_detected=False,
            gas_sensor_valid=True,
            battery_voltage=12.0,
            emergency_stop_active=False,
            rpi_timeout_active=False,
            last_state=danger_state,
            context=danger_context,
        )

    results.append(
        pass_if(
            "T_SAFE_DANGER_COUNT",
            "danger requires consecutive detections",
            danger_state == AmrState.DANGER,
            f"gas=1500 repeated 3 times -> {danger_state.name}",
        )
    )

    results.append(
        pass_if(
            "T_ACTION_UNSAFE_STOP",
            "unsafe states map to stop action",
            all(
                determine_amr_action(state) == AmrAction.STOP_MOTION
                for state in [AmrState.DANGER, AmrState.STOP, AmrState.SENSOR_ERROR]
            ),
            "DANGER/STOP/SENSOR_ERROR -> STOP_MOTION",
        )
    )

    return results


def print_report(results):
    print("HazardBot ESP32 #1 AMR v8 Pure Logic Harness")
    print("=" * 52)
    print("Legend: PASS = v8 behavior verified, FAIL = regression or protocol mismatch")
    print()

    for result in results:
        print(f"[{result.status:4}] {result.test_id:24} {result.name}")
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
