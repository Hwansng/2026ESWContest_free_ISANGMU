"""리더·팔로워의 wrist_roll 영점 차이를 없앤다.

왜 이 축만 문제가 되는가:
    나머지 5축은 캘리브레이션이 `range_min~range_max` 를 물리적 가동 한계로 기록하므로
    정규화 기준이 팔의 실제 구조에 묶인다. 두 팔이 같은 구조면 자동으로 일치한다.

    그런데 wrist_roll 은 연속 회전축이라 LeRobot 이 range 를 0~4095 로 고정한다.
    → 정규화 기준점이 오직 `homing_offset` 하나로 정해지고,
      그 값은 `set_half_turn_homings()` 를 실행한 순간의 손목 각도로 결정된다.
    → 두 팔의 손목이 그때 다른 방향을 보고 있었으면 그 차이가 상수 오프셋으로 남는다.

증상: 회전 **방향**은 같은데 **위치**가 일정하게 어긋난다 (예: 180도 차이).

사용법:
    # 1) 두 팔의 손목을 눈으로 같은 방향에 맞춘다 (집게가 같은 쪽을 향하게)
    # 2) 측정만
    python tools/sync_wrist_roll.py --leader COM5 --follower COM3
    # 3) 적용 (리더 서보 EPROM + JSON 2곳)
    python tools/sync_wrist_roll.py --leader COM5 --follower COM3 --apply
"""

import argparse
import json
from pathlib import Path

from lerobot.motors import Motor, MotorNormMode
from lerobot.motors.feetech import FeetechMotorsBus

MOTOR = "wrist_roll"
MOTOR_ID = 5
RESOLUTION = 4096

CALIB_BASE = Path.home() / ".cache" / "huggingface" / "lerobot" / "calibration"
LEADER_CALIB = CALIB_BASE / "teleoperators" / "so_leader" / "leader_arm.json"
FOLLOWER_CALIB = CALIB_BASE / "robots" / "so_follower" / "follower_arm.json"
LEADER_BACKUP = Path(__file__).resolve().parent.parent / "calibration" / "leader_arm.json"


def _bus(port: str) -> FeetechMotorsBus:
    bus = FeetechMotorsBus(
        port=port, motors={MOTOR: Motor(MOTOR_ID, "sts3215", MotorNormMode.RANGE_M100_100)}
    )
    bus.connect(handshake=False)
    return bus


def _norm(pos: int, calib: dict) -> float:
    lo, hi = calib[MOTOR]["range_min"], calib[MOTOR]["range_max"]
    frac = min(max((pos - lo) / (hi - lo), 0.0), 1.0)
    val = frac * 200 - 100
    return -val if calib[MOTOR].get("drive_mode") else val


def wrap_offset(v: int) -> int:
    """Homing_Offset 은 부호+크기 12비트라 ±2047 이 한계다.

    다만 Present_Position = Actual - Offset 을 서보가 4096 모듈로로 계산하므로
    offset 과 offset±4096 은 등가다. 범위 안으로 접어 넣으면 된다.
    """
    v = ((v + 2048) % RESOLUTION) - 2048
    return -2047 if v == -2048 else v


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--leader", required=True)
    parser.add_argument("--follower", required=True)
    parser.add_argument("--apply", action="store_true", help="리더 서보와 JSON 에 실제로 기록한다")
    args = parser.parse_args()

    leader_calib = json.loads(LEADER_CALIB.read_text(encoding="utf-8"))
    follower_calib = json.loads(FOLLOWER_CALIB.read_text(encoding="utf-8"))

    lb, fb = _bus(args.leader), _bus(args.follower)
    try:
        lpos = lb.read("Present_Position", MOTOR, normalize=False)
        fpos = fb.read("Present_Position", MOTOR, normalize=False)
        cur_offset = lb.read("Homing_Offset", MOTOR, normalize=False)
    finally:
        fb.disconnect(disable_torque=False)
        lb.disconnect(disable_torque=False)

    lnorm, fnorm = _norm(lpos, leader_calib), _norm(fpos, follower_calib)
    diff = lnorm - fnorm
    # Present = Actual - Offset 이므로 offset 을 키우면 보고값(=정규화값)이 내려간다.
    counts = round(diff / 200 * (RESOLUTION - 1))
    new_offset = wrap_offset(cur_offset + counts)

    print(f"{'':16}{'원시':>8}{'정규화':>10}")
    print("-" * 36)
    print(f"{'리더':16}{lpos:>8}{lnorm:>+10.1f}")
    print(f"{'팔로워':16}{fpos:>8}{fnorm:>+10.1f}")
    print(f"{'차이':16}{'':>8}{diff:>+10.1f}   ≈ {abs(diff) / 200 * 360:.0f}°")
    print()
    print(f"리더 Homing_Offset : {cur_offset}  →  {new_offset}   (보정 {counts:+})")

    if abs(diff) < 3:
        print("\n✅ 이미 일치한다. 보정할 것이 없다.")
        return 0

    if not args.apply:
        print("\n측정만 했다. 적용하려면 --apply 를 붙일 것.")
        print("⚠ 적용 전에 두 팔의 손목이 **눈으로 같은 방향**인지 반드시 확인할 것.")
        print("  어긋난 상태에서 적용하면 그 어긋남이 그대로 새 영점이 된다.")
        return 0

    lb = _bus(args.leader)
    try:
        lb.disable_torque()
        lb.write("Homing_Offset", MOTOR, new_offset, normalize=False)
        readback = lb.read("Homing_Offset", MOTOR, normalize=False)
        after = lb.read("Present_Position", MOTOR, normalize=False)
    finally:
        lb.disconnect(disable_torque=False)

    if readback != new_offset:
        print(f"\n❌ 기록 실패: 읽기 확인값이 {readback} 이다.")
        return 1

    # homing_offset 은 is_calibrated() 가 서보와 대조하는 값이므로 JSON 도 함께 갱신해야 한다.
    # 어긋나면 다음 연결 때 재캘리브레이션 프롬프트가 뜬다.
    leader_calib[MOTOR]["homing_offset"] = new_offset
    payload = json.dumps(leader_calib, indent=4)
    for path in (LEADER_CALIB, LEADER_BACKUP):
        path.write_text(payload, encoding="utf-8")
        print(f"✅ 갱신: {path}")

    print(f"\n✅ 서보 기록 완료. 위치 {lpos} → {after}")
    print("   확인: python tools/check_align.py --leader <리더> --follower <팔로워>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
