from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class AmrState(Enum):
    SAFE = "SAFE"
    WARNING = "WARNING"
    DANGER = "DANGER"
    STOP = "STOP"
    SENSOR_ERROR = "SENSOR_ERROR"


class AmrAction(Enum):
    NORMAL_MOTION = "NORMAL_MOTION"
    LIMITED_MOTION = "LIMITED_MOTION"
    STOP_MOTION = "STOP_MOTION"


LIPO_CUTOFF_VOLTAGE = 9.9
GAS_WARNING_ENTER_THRESHOLD = 1400
GAS_WARNING_EXIT_THRESHOLD = 1350
GAS_DANGER_ENTER_THRESHOLD = 1500
GAS_DANGER_EXIT_THRESHOLD = 1450
DANGER_COUNT_THRESHOLD = 3
SENSOR_ERROR_COUNT_THRESHOLD = 3
RPI_TIMEOUT_MS = 3000


@dataclass
class V7Context:
    danger_count: int = 0
    sensor_error_count: int = 0


@dataclass
class TestResult:
    test_id: str
    name: str
    status: str
    detail: str


def state_to_string(state):
    if isinstance(state, AmrState):
        return state.value
    return "UNKNOWN"


def calculate_checksum(payload):
    checksum = 0
    for char in payload:
        checksum ^= ord(char)
    return checksum


def build_state_payload(state, gas_average, flame_detected, battery_voltage):
    return (
        f"CMD,STATE={state_to_string(state)},"
        f"GAS={gas_average},"
        f"FLAME={1 if flame_detected else 0},"
        f"BAT={battery_voltage:.2f}"
    )


def build_state_message(state, gas_average, flame_detected, battery_voltage):
    payload = build_state_payload(
        state,
        gas_average,
        flame_detected,
        battery_voltage,
    )
    checksum = calculate_checksum(payload)
    return f"<{payload},{checksum:02X}>\n"


def build_rpi_message(payload):
    return f"<{payload},{calculate_checksum(payload):02X}>"


def is_valid_rpi_message(message):
    if not message.startswith("<") or not message.endswith(">"):
        return False

    body = message[1:-1]
    if "," not in body:
        return False

    payload, checksum_text = body.rsplit(",", 1)
    if len(checksum_text) != 2:
        return False

    try:
        expected_checksum = int(checksum_text, 16)
    except ValueError:
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

    danger_enter_condition = (
        flame_detected or gas_average >= GAS_DANGER_ENTER_THRESHOLD
    )
    danger_stay_condition = (
        flame_detected or gas_average >= GAS_DANGER_EXIT_THRESHOLD
    )

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

    if last_state == AmrState.WARNING:
        if gas_average >= GAS_WARNING_EXIT_THRESHOLD:
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


def pass_if(test_id, name, condition, detail):
    return TestResult(test_id, name, "PASS" if condition else "FAIL", detail)


def known_gap(test_id, name, detail):
    return TestResult(test_id, name, "KNOWN_GAP", detail)


def load_v7_source():
    repo_root = Path(__file__).resolve().parents[3]
    source_path = (repo_root / "archive" / "firmware_esp32_env_history"
                   / "AMR_state_v7_ino" / "AMR_state_v7_ino.ino")
    return source_path.read_text(encoding="utf-8", errors="replace")


def run_tests():
    results = []
    v7_source = load_v7_source()

    for state in AmrState:
        results.append(
            pass_if(
                f"T_STATE_{state.value}",
                f"state string {state.value}",
                state_to_string(state) == state.value,
                f"{state.name} -> {state_to_string(state)}",
            )
        )

    results.extend(
        [
            pass_if(
                "T_SRC_SENSOR_ERROR_ENUM",
                "v7 source defines STATE_SENSOR_ERROR",
                "STATE_SENSOR_ERROR" in v7_source,
                "Arduino enum should expose a distinct sensor fault state.",
            ),
            pass_if(
                "T_SRC_SENSOR_ERROR_STRING",
                "v7 source prints SENSOR_ERROR",
                'return "SENSOR_ERROR";' in v7_source,
                "RPi 5 should receive SENSOR_ERROR as a state string.",
            ),
            pass_if(
                "T_SRC_SENSOR_ERROR_RETURN",
                "v7 source returns STATE_SENSOR_ERROR for invalid sensor",
                "return STATE_SENSOR_ERROR;" in v7_source,
                "Sensor fault should not be collapsed into generic STOP.",
            ),
            pass_if(
                "T_SRC_ESTOP_PIN",
                "v7 source defines EMERGENCY_STOP_PIN",
                "EMERGENCY_STOP_PIN" in v7_source,
                "Emergency Stop input should be named and isolated.",
            ),
            pass_if(
                "T_SRC_ESTOP_READER",
                "v7 source reads Emergency Stop input",
                "isEmergencyStopActive" in v7_source,
                "Emergency Stop should have a dedicated reader function.",
            ),
            pass_if(
                "T_SRC_ESTOP_PRIORITY",
                "v7 source evaluates Emergency Stop before LiPo and sensors",
                "if (emergencyStopActive)" in v7_source,
                "Emergency Stop should be first in evaluateAmrState().",
            ),
            pass_if(
                "T_SRC_CMD_PAYLOAD",
                "v7 source uses CMD as protocol command",
                'String payload = "CMD,STATE=";' in v7_source,
                "Serial payload should start with CMD and expose STATE as a field.",
            ),
            pass_if(
                "T_SRC_RPI_TIMEOUT_CONSTANT",
                "v7 source defines RPI_TIMEOUT_MS",
                "RPI_TIMEOUT_MS" in v7_source,
                "Timeout threshold should be a named constant.",
            ),
            pass_if(
                "T_SRC_RPI_COMM_UPDATE",
                "v7 source updates last RPi communication time",
                "updateRpiCommunication" in v7_source,
                "Serial input from RPi should refresh the timeout timer.",
            ),
            pass_if(
                "T_SRC_RPI_TIMEOUT_READER",
                "v7 source checks RPi timeout state",
                "isRpiTimeoutActive" in v7_source,
                "Timeout state should be isolated in a dedicated function.",
            ),
            pass_if(
                "T_SRC_RPI_RX_BUFFER",
                "v7 source buffers framed RPi input",
                "rpiRxBuffer" in v7_source,
                "RPi input should be parsed as complete framed messages.",
            ),
            pass_if(
                "T_SRC_RPI_CHECKSUM_VALIDATE",
                "v7 source validates RPi message checksum",
                "isValidRpiMessage" in v7_source,
                "Keepalive should refresh timeout only after checksum validation.",
            ),
            pass_if(
                "T_SRC_AMR_ACTION_ENUM",
                "v7 source defines AMR action enum",
                "enum AmrAction" in v7_source,
                "State-to-action mapping should exist before real motor control.",
            ),
            pass_if(
                "T_SRC_AMR_ACTION_MAPPING",
                "v7 source maps state to motor action",
                "determineAmrAction" in v7_source,
                "Action mapping should be isolated from state evaluation.",
            ),
            pass_if(
                "T_SRC_AMR_ACTION_APPLY",
                "v7 source has action application hook",
                "applyAmrAction" in v7_source,
                "The hook should exist without directly driving hardware yet.",
            ),
        ]
    )

    message = build_state_message(AmrState.SAFE, 42, False, 12.0)
    payload = message[1 : message.rfind(",")]
    checksum_text = message[message.rfind(",") + 1 : -2]
    fields = payload.split(",")

    results.extend(
        [
            pass_if("T_MSG_START", "message starts with <", message.startswith("<"), message),
            pass_if("T_MSG_END", "message has > before newline", message.endswith(">\n"), message),
            pass_if(
                "T_MSG_CMD_FORMAT",
                "message uses <CMD,...,CS> format",
                fields[0] == "CMD" and fields[1].startswith("STATE="),
                str(fields),
            ),
            pass_if("T_MSG_FIELDS", "message fields use commas", len(fields) == 5, str(fields)),
            pass_if(
                "T_MSG_CHECKSUM_EXISTS",
                "checksum exists as 2 hex chars",
                len(checksum_text) == 2 and all(c in "0123456789ABCDEF" for c in checksum_text),
                f"checksum={checksum_text}",
            ),
            pass_if(
                "T_MSG_CHECKSUM_VALUE",
                "checksum matches XOR payload",
                int(checksum_text, 16) == calculate_checksum(payload),
                f"payload={payload}, checksum={checksum_text}",
            ),
            pass_if(
                "T_RPI_KEEPALIVE_VALID",
                "valid RPi keepalive checksum is accepted",
                is_valid_rpi_message(build_rpi_message("CMD,PING")),
                build_rpi_message("CMD,PING"),
            ),
            pass_if(
                "T_RPI_KEEPALIVE_BAD_CHECKSUM",
                "bad RPi keepalive checksum is rejected",
                not is_valid_rpi_message("<CMD,PING,00>"),
                "<CMD,PING,00>",
            ),
        ]
    )

    lipo_context = V7Context()
    lipo_state = evaluate_amr_state(
        gas_average=1600,
        flame_detected=True,
        gas_sensor_valid=True,
        battery_voltage=9.9,
        emergency_stop_active=False,
        rpi_timeout_active=False,
        last_state=AmrState.SAFE,
        context=lipo_context,
    )
    results.append(
        pass_if(
            "T_SAFE_LIPO_PRIORITY",
            "LiPo cutoff overrides sensor state",
            lipo_state == AmrState.STOP,
            f"battery=9.9, gas=1600, flame=True -> {lipo_state.value}",
        )
    )

    sensor_context = V7Context()
    last_state = AmrState.SAFE
    sensor_state = AmrState.SAFE
    for _ in range(SENSOR_ERROR_COUNT_THRESHOLD):
        valid = is_gas_sensor_valid(0, sensor_context)
        sensor_state = evaluate_amr_state(
            gas_average=0,
            flame_detected=False,
            gas_sensor_valid=valid,
            battery_voltage=12.0,
            emergency_stop_active=False,
            rpi_timeout_active=False,
            last_state=last_state,
            context=sensor_context,
        )
        last_state = sensor_state
    results.append(
        pass_if(
            "T_SAFE_SENSOR_ERROR",
            "sensor error falls back to SENSOR_ERROR",
            sensor_state == AmrState.SENSOR_ERROR,
            f"invalid gas repeated 3 times -> {sensor_state.value}",
        )
    )

    danger_context = V7Context()
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
            "danger requires 3 consecutive detections",
            danger_state == AmrState.DANGER,
            f"gas=1500 repeated 3 times -> {danger_state.value}",
        )
    )

    warning_context = V7Context()
    warning_state = evaluate_amr_state(
        gas_average=1400,
        flame_detected=False,
        gas_sensor_valid=True,
        battery_voltage=12.0,
        emergency_stop_active=False,
        rpi_timeout_active=False,
        last_state=AmrState.SAFE,
        context=warning_context,
    )
    results.append(
        pass_if(
            "T_SAFE_WARNING_ENTER",
            "warning threshold enters WARNING",
            warning_state == AmrState.WARNING,
            f"gas=1400 -> {warning_state.value}",
        )
    )

    results.extend(
        [
            pass_if(
                "T_SAFE_ESTOP_PRIORITY",
                "Emergency Stop is highest priority",
                evaluate_amr_state(
                    gas_average=1200,
                    flame_detected=False,
                    gas_sensor_valid=True,
                    battery_voltage=12.0,
                    emergency_stop_active=True,
                    rpi_timeout_active=False,
                    last_state=AmrState.SAFE,
                    context=V7Context(),
                )
                == AmrState.STOP,
                "E-Stop active with otherwise SAFE inputs -> STOP",
            ),
            pass_if(
                "T_SAFE_TIMEOUT_FALLBACK",
                "timeout can enter safe fallback",
                evaluate_amr_state(
                    gas_average=1200,
                    flame_detected=False,
                    gas_sensor_valid=True,
                    battery_voltage=12.0,
                    emergency_stop_active=False,
                    rpi_timeout_active=True,
                    last_state=AmrState.SAFE,
                    context=V7Context(),
                )
                == AmrState.STOP,
                "RPi timeout with otherwise SAFE inputs -> STOP",
            ),
            pass_if(
                "T_ACTION_SAFE",
                "SAFE maps to normal motion",
                determine_amr_action(AmrState.SAFE) == AmrAction.NORMAL_MOTION,
                f"SAFE -> {determine_amr_action(AmrState.SAFE).value}",
            ),
            pass_if(
                "T_ACTION_WARNING",
                "WARNING maps to limited motion",
                determine_amr_action(AmrState.WARNING) == AmrAction.LIMITED_MOTION,
                f"WARNING -> {determine_amr_action(AmrState.WARNING).value}",
            ),
            pass_if(
                "T_ACTION_UNSAFE_STATES",
                "unsafe states map to stop motion",
                all(
                    determine_amr_action(state) == AmrAction.STOP_MOTION
                    for state in [AmrState.DANGER, AmrState.STOP, AmrState.SENSOR_ERROR]
                ),
                "DANGER/STOP/SENSOR_ERROR -> STOP_MOTION",
            ),
        ]
    )

    return results


def print_report(results):
    print("HazardBot ESP32 #1 AMR v7 Pure Logic Harness")
    print("=" * 52)
    print("Legend: PASS = v7 baseline verified, FAIL = regression, KNOWN_GAP = target not in v7 yet")
    print()

    for result in results:
        print(f"[{result.status:9}] {result.test_id:24} {result.name}")
        print(f"            {result.detail}")

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
