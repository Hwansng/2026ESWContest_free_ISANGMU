"""<CMD,VALUE,CS> 프로토콜 헬퍼 (펌웨어 protocol.cpp와 동일 규약).

vision_node가 /vision/detected로 내보내는 문자열과 dummy_subscriber의 검증이
동일한 XOR 체크섬 규약을 공유하도록 한곳에 모은다.
"""
from __future__ import annotations


def xor_checksum(payload: str) -> int:
    """payload 문자열의 모든 문자를 XOR 한 1바이트(0~255) 체크섬."""
    cs = 0
    for ch in payload:
        cs ^= ord(ch)
    return cs & 0xFF


def build_message(cmd: str, value: str) -> str:
    """'<CMD,VALUE,CS>' 형식 문자열 생성 (CS = 2자리 대문자 HEX)."""
    payload = f"{cmd},{value}"
    return f"<{payload},{xor_checksum(payload):02X}>"


def parse_message(line: str) -> tuple[str, str] | None:
    """'<CMD,VALUE,CS>' 파싱 + 체크섬 검증.

    성공하면 (cmd, value)를, 형식/체크섬 오류면 None을 반환한다.
    """
    line = line.strip()
    if not line.startswith("<") or not line.endswith(">"):
        return None
    body = line[1:-1]               # "CMD,VALUE,CS"
    parts = body.rsplit(",", 1)     # 마지막 콤마 기준 분리 -> ["CMD,VALUE", "CS"]
    if len(parts) != 2:
        return None
    payload, cs_str = parts
    try:
        got = int(cs_str, 16)
    except ValueError:
        return None
    if got != xor_checksum(payload):  # 체크섬 불일치 -> 폐기
        return None
    cmd, _, value = payload.partition(",")
    return cmd, value
