import argparse
import time


DEFAULT_PAYLOAD = "CMD,PING"


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
    checksum = calculate_legacy_v7_checksum(payload)
    return f"<{payload},{checksum:02X}>\n"


def validate_interval(interval_sec):
    if interval_sec <= 0:
        raise ValueError("interval_sec must be greater than 0")
    return interval_sec


def read_available_lines(serial_port):
    lines = []
    while serial_port.in_waiting > 0:
        raw_line = serial_port.readline()
        lines.append(raw_line.decode("utf-8", errors="replace").rstrip())
    return lines


def run_keepalive(
    port,
    interval_sec=1.0,
    count=None,
    dry_run=False,
    sleep_func=time.sleep,
    echo_responses=False,
    output_func=print,
):
    validate_interval(interval_sec)
    message = build_message()
    sent_messages = []

    if dry_run:
        iterations = count if count is not None else 1
        for _ in range(iterations):
            sent_messages.append(message)
            sleep_func(interval_sec)
        return sent_messages

    if not port:
        raise ValueError("port is required unless dry_run is enabled")

    try:
        import serial
    except ImportError as exc:
        raise RuntimeError("pyserial is required for real serial output") from exc

    with serial.Serial(port, 115200, timeout=1) as serial_port:
        iterations = 0
        while count is None or iterations < count:
            serial_port.write(message.encode("ascii"))
            serial_port.flush()
            sent_messages.append(message)
            iterations += 1
            sleep_func(interval_sec)

            if echo_responses:
                for line in read_available_lines(serial_port):
                    output_func(line)

    return sent_messages


def parse_args():
    parser = argparse.ArgumentParser(
        description="Send checksum-validated HazardBot RPi keepalive messages."
    )
    parser.add_argument("--port", help="Serial port, for example COM5 or /dev/ttyUSB0")
    parser.add_argument("--interval", type=float, default=1.0, help="Seconds between messages")
    parser.add_argument("--count", type=int, help="Number of messages to send")
    parser.add_argument("--dry-run", action="store_true", help="Print messages without serial output")
    parser.add_argument(
        "--echo-responses",
        action="store_true",
        help="Print serial lines received between v9 keepalive messages",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    messages = run_keepalive(
        port=args.port,
        interval_sec=args.interval,
        count=args.count,
        dry_run=args.dry_run,
        echo_responses=args.echo_responses,
    )

    for message in messages:
        print(message, end="")


if __name__ == "__main__":
    main()
