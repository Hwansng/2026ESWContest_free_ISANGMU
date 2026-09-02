import argparse


REQUIRED_FIELDS = ("STATE", "GAS", "FLAME", "BAT")


def calculate_checksum(payload):
    checksum = 0
    for char in payload:
        checksum ^= ord(char)
    return checksum


def calculate_sum_checksum(payload):
    return sum(ord(char) for char in payload) % 256


def parse_fields(payload):
    parts = payload.split(",")
    if not parts or parts[0] != "CMD":
        raise ValueError("message command must be CMD")

    fields = {"command": parts[0]}
    for part in parts[1:]:
        if "=" not in part:
            raise ValueError(f"field is missing '=': {part}")
        key, value = part.split("=", 1)
        fields[key] = value

    for key in REQUIRED_FIELDS:
        if key not in fields:
            raise ValueError(f"required field is missing: {key}")

    return fields


def parse_sens_payload(payload):
    parts = payload.split(",")
    if len(parts) != 8 or parts[0] != "SENS":
        raise ValueError("v9 SENS payload must contain exactly 8 fields")

    try:
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
    except ValueError as exc:
        raise ValueError("v9 SENS fields must be decimal integers") from exc


def parse_amr_message(message):
    text = message.strip()
    if not text.startswith("<") or not text.endswith(">"):
        raise ValueError("message must start with '<' and end with '>'")

    body = text[1:-1]
    if "," not in body:
        raise ValueError("message is missing checksum separator")

    payload, checksum_text = body.rsplit(",", 1)

    command = payload.split(",", 1)[0]

    if command == "SENS":
        if not checksum_text.isdecimal() or len(checksum_text) > 3:
            raise ValueError("v9 checksum must be one to three decimal digits")

        received_checksum = int(checksum_text)
        if received_checksum < 0 or received_checksum > 255:
            raise ValueError("v9 checksum must be in range 0..255")

        expected_checksum = calculate_sum_checksum(payload)
        if received_checksum != expected_checksum:
            raise ValueError(
                f"checksum mismatch: received {checksum_text}, expected {expected_checksum}"
            )

        return parse_sens_payload(payload)

    if command != "CMD":
        raise ValueError(f"unsupported message command: {command}")

    if len(checksum_text) != 2:
        raise ValueError("checksum must be 2 hex characters")

    try:
        received_checksum = int(checksum_text, 16)
    except ValueError as exc:
        raise ValueError("checksum must be hexadecimal") from exc

    expected_checksum = calculate_checksum(payload)
    if received_checksum != expected_checksum:
        raise ValueError(
            f"checksum mismatch: received {checksum_text}, expected {expected_checksum:02X}"
        )

    fields = parse_fields(payload)
    return {
        "command": fields["command"],
        "state": fields["STATE"],
        "gas": int(fields["GAS"]),
        "flame": int(fields["FLAME"]),
        "battery": float(fields["BAT"]),
    }


def parse_args():
    parser = argparse.ArgumentParser(
        description="Parse a HazardBot ESP32 #1 AMR status message."
    )
    parser.add_argument(
        "message",
        help=(
            "Legacy CMD or v9 SENS message, including frame and checksum"
        ),
    )
    return parser.parse_args()


def main():
    args = parse_args()
    parsed = parse_amr_message(args.message)
    for key, value in parsed.items():
        print(f"{key}={value}")


if __name__ == "__main__":
    main()
