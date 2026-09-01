"""텔레옵 시작 전에 리더·팔로워의 자세 차이를 확인한다 (읽기 전용).

lerobot-teleoperate 는 시작하는 순간 팔로워 토크를 켜고 리더 자세로 추종시킨다.
두 팔의 자세가 크게 다르면 그 순간 팔로워가 급격히 움직여
3D 프린팅 파츠나 서보 기어에 충격이 간다.

**두 팔을 비슷한 자세로 맞춘 뒤 텔레옵을 시작할 것.**

각 축을 캘리브레이션 범위 기준으로 -100~+100 (그리퍼는 0~100) 으로 정규화해
같은 척도에서 비교한다. 원시 엔코더 값은 두 팔의 오프셋이 달라 직접 비교할 수 없다.

🔴 정규화 값을 [0,1] 로 **잘라내지 않는다.** 2026-07-28 사건: 리더 손목이 창 밖
   (raw 977, 창 3201~4001)에 있었는데 잘린 값(-100)으로 비교해 "35° 회전 ✅" 로
   통과시켰고, 텔레옵이 그대로 시작돼 팔로워 손목이 129° 폭주해 배선을 감았다.
   창 밖에 있는 축은 차이 크기와 무관하게 무조건 차단한다.

사용법:
    python tools/check_align.py --leader COM5 --follower COM3
"""

import argparse
import json
from pathlib import Path

from lerobot.motors import Motor, MotorNormMode
from lerobot.motors.feetech import FeetechMotorsBus

MOTOR_IDS = {
    "shoulder_pan": 1, "shoulder_lift": 2, "elbow_flex": 3,
    "wrist_flex": 4, "wrist_roll": 5, "gripper": 6,
}
FULL_TURN_MOTOR = "wrist_roll"

CALIB_BASE = Path.home() / ".cache" / "huggingface" / "lerobot" / "calibration"
LEADER_CALIB = CALIB_BASE / "teleoperators" / "so_leader" / "leader_arm.json"
FOLLOWER_CALIB = CALIB_BASE / "robots" / "so_follower" / "follower_arm.json"

WARN = 15.0           # 정규화 척도(-100~100)에서 이 이상 차이나면 경고
ROLL_WARN_DEG = 45.0  # wrist_roll 은 실제 각도로 판정한다 (배선 꼬임 위험)
OUTSIDE_MARGIN = 0.02  # 창 밖 판정 여유 (2% ≈ 손목 기준 16카운트)


def read_raw(port: str) -> dict[str, int]:
    motors = {
        name: Motor(mid, "sts3215",
                    MotorNormMode.RANGE_0_100 if name == "gripper" else MotorNormMode.RANGE_M100_100)
        for name, mid in MOTOR_IDS.items()
    }
    bus = FeetechMotorsBus(port=port, motors=motors)
    bus.connect(handshake=False)
    try:
        return bus.sync_read("Present_Position", normalize=False)
    finally:
        bus.disconnect(disable_torque=False)


def load_calib(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"캘리브레이션 파일이 없다: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def normalize(name: str, raw: int, calib: dict) -> tuple[float, bool]:
    """잘라내지 않은 정규화 값과 창 밖 여부를 돌려준다."""
    c = calib[name]
    lo, hi = c["range_min"], c["range_max"]
    frac = (raw - lo) / (hi - lo) if hi > lo else 0.0
    outside = frac < -OUTSIDE_MARGIN or frac > 1.0 + OUTSIDE_MARGIN
    val = frac * 100 if name == "gripper" else frac * 200 - 100
    # drive_mode 는 서보가 아니라 JSON 에만 있는 호스트측 반전 플래그다.
    # LeRobot 의 _normalize 와 같은 규칙으로 여기서도 적용해야 값이 일치한다.
    if c.get("drive_mode"):
        val = (100 - val) if name == "gripper" else -val
    return val, outside


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--leader", required=True, help="리더 COM 포트")
    parser.add_argument("--follower", required=True, help="팔로워 COM 포트")
    args = parser.parse_args()

    leader_raw = read_raw(args.leader)
    follower_raw = read_raw(args.follower)
    lcal = load_calib(LEADER_CALIB)
    fcal = load_calib(FOLLOWER_CALIB)

    print(f"{'축':<14}{'리더':>9}{'팔로워':>10}{'차이':>9}   판정")
    print("-" * 62)
    blocked = False
    outside_notes = []
    for name in MOTOR_IDS:
        lval, l_out = normalize(name, leader_raw[name], lcal)
        fval, f_out = normalize(name, follower_raw[name], fcal)
        diff = lval - fval

        if l_out or f_out:
            # 창 밖 = 캘리브레이션이 가정하는 범위를 벗어난 상태.
            # 텔레옵(RANGE 모드)은 창 경계로 잘라 명령하므로 시작 즉시 경계까지 튄다.
            blocked = True
            verdict = "🔴 창 밖 — 아래 안내 참조"
            for side, out, raw, cal in (("리더", l_out, leader_raw[name], lcal),
                                        ("팔로워", f_out, follower_raw[name], fcal)):
                if out:
                    c = cal[name]
                    outside_notes.append(
                        f"{name}({side}): raw {raw}, 창 {c['range_min']}~{c['range_max']}"
                        f" — **손으로** 창 안까지 돌려놓을 것")
        elif name == FULL_TURN_MOTOR:
            # 손목 카메라·그리퍼 배선이 지나는 축이라 꼬임 위험을 실제 각도로 본다.
            # 양쪽 창 폭이 같으므로(800카운트) 정규화 차이를 그대로 각도로 환산할 수 있다.
            span = fcal[name]["range_max"] - fcal[name]["range_min"]
            deg = abs(diff) / 200 * span * 360 / 4096
            if deg > ROLL_WARN_DEG:
                verdict = f"🔴 약 {deg:.0f}° 회전 — 배선 꼬임 주의"
                blocked = True
            else:
                verdict = f"✅ 약 {deg:.0f}° 회전"
        elif abs(diff) > WARN:
            verdict = f"🔴 팔로워가 {'+' if diff > 0 else '-'} 방향으로 크게 움직인다"
            blocked = True
        else:
            verdict = "✅"
        print(f"{name:<14}{lval:>+9.1f}{fval:>+10.1f}{diff:>+9.1f}   {verdict}")

    print()
    if not blocked:
        print("✅ 두 팔의 자세가 충분히 가깝다. 텔레옵을 시작해도 안전하다.")
        return 0

    if outside_notes:
        print("🔴 캘리브레이션 창 밖에 있는 축:")
        for note in outside_notes:
            print(f"   - {note}")
        print("   손목이 크게 벗어나 있으면 한 바퀴(360°) 감겨 있을 수 있다 — 배선을 먼저 볼 것.")
        print()
    print("🔴 텔레옵 시작 즉시 팔로워가 위 차이만큼 급격히 움직인다.")
    print("   **리더를 팔로워와 비슷한 자세로 맞춘 뒤** 다시 확인할 것.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
