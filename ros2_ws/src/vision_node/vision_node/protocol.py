"""
[레거시 — 현재 사용 안 함]
초기 개발 단계 <CMD,VALUE,CS> XOR 체크섬 프로토콜 헬퍼임. 이건 아두이노
펌웨어 시리얼 통신 프로토타입 시절 규약이고, 지금 vision_node.py는
/vision/detected를 JSON 문자열로 발행함(json.dumps). 이 프로토콜은 안 씀.
dummy_subscriber.py가 이걸 참조하는데, dummy_subscriber도 같이 레거시임.
"""
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
    body = line[1:-1]
    parts = body.rsplit(",", 1)
    if len(parts) != 2:
        return None
    payload, cs_str = parts
    try:
        got = int(cs_str, 16)
    except ValueError:
        return None
    if got != xor_checksum(payload):
        return None
    cmd, _, value = payload.partition(",")
    return cmd, value