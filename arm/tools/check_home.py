"""팔로워를 **저장된 기준 자세**와 비교한다 (읽기 전용 — 서보를 움직이지 않는다).

왜 필요한가:
    `check_align.py` 는 리더와 팔로워를 서로 맞추지만, **어느 위치에서 맞출지**는 정하지 않는다.
    그래서 매 세션 손목이 제각각인 방향에서 시작하게 되고, 때로는 배선이 팽팽한
    위치에서 시작해 `wrist_roll` 과부하로 이어졌다 (구축기록 §5-5).

    특히 `wrist_roll` 은 연속 회전축이라 **중력으로 돌아갈 자연스러운 쉬는 자세가 없다.**
    토크를 끄면 마지막 위치에 그대로 남으므로, 세션마다 방향이 누적해서 어긋난다.
    `wrist_flex` 는 손목 카메라 장착(2026-07-29) 이후 시작 각도가 카메라 케이블 여유를
    좌우하므로 함께 엄격히 본다.

    → **알려진 안전한 방향 하나를 기준으로 정해 두고 매번 거기서 시작한다.**
      데이터 수집의 일관성에도 도움이 된다 (에피소드마다 손목 시작 방향이 같아진다).

이 도구는 **아무것도 움직이지 않는다.** 얼마나 어긋났는지만 알려준다.
손으로 맞춘 뒤 다시 실행해 확인할 것.

사용법:
    python tools/check_home.py --port COM3            # 기준과 비교
    python tools/check_home.py --port COM3 --save     # 현재 자세를 기준으로 저장
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

HOME_PATH = Path(__file__).resolve().parent.parent / "calibration" / "follower_home.json"

# wrist_roll(쉬는 자세 없음)과 wrist_flex(카메라 케이블 여유)만 엄격히 본다.
# 나머지 축은 중력으로 쉬는 자세에 수렴하므로 check_align.py 의 리더-팔로워
# 비교로 충분하고, 여기서는 참고로만 표시한다.
STRICT_MOTORS = ("wrist_flex", "wrist_roll")
TOLERANCE = 120  # 카운트. 4096 = 360도 이므로 약 10.5도


def _read(port: str) -> dict[str, int]:
    motors = {
        n: Motor(i, "sts3215",
                 MotorNormMode.RANGE_0_100 if n == "gripper" else MotorNormMode.RANGE_M100_100)
        for n, i in MOTOR_IDS.items()
    }
    bus = FeetechMotorsBus(port=port, motors=motors)
    bus.connect(handshake=False)
    try:
        return bus.sync_read("Present_Position", normalize=False)
    finally:
        bus.disconnect(disable_torque=False)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True, help="팔로워 COM 포트 (예: COM3)")
    parser.add_argument("--save", action="store_true",
                        help="현재 자세를 기준으로 저장한다 (정렬이 맞은 상태에서만 할 것)")
    args = parser.parse_args()

    pos = _read(args.port)

    if args.save:
        HOME_PATH.parent.mkdir(parents=True, exist_ok=True)
        HOME_PATH.write_text(json.dumps(pos, indent=4), encoding="utf-8")
        print("현재 자세를 기준으로 저장했다.\n")
        for n in MOTOR_IDS:
            mark = "   ← 기준 판정 대상" if n in STRICT_MOTORS else ""
            print(f"   {n:<14}{pos[n]:>6}{mark}")
        print(f"\n✅ 저장: {HOME_PATH}")
        print("\n⚠ 이 값은 **두 팔이 정렬되고 배선이 편안한 상태**에서 저장해야 의미가 있다.")
        return 0

    if not HOME_PATH.is_file():
        print(f"❌ 기준 자세가 없다: {HOME_PATH}")
        print("   두 팔을 정렬한 상태에서 --save 로 먼저 저장할 것.")
        return 1

    home = json.loads(HOME_PATH.read_text(encoding="utf-8"))

    header = f"{'축':<14}{'현재':>8}{'기준':>8}{'차이':>9}{'각도':>9}   판정"
    print(header)
    print("-" * (len(header) + 12))

    ok = True
    for n in MOTOR_IDS:
        if n not in home:
            continue
        diff = pos[n] - home[n]
        deg = abs(diff) * 360 / 4096

        if n not in STRICT_MOTORS:
            verdict = "(참고 — check_align 이 담당)"
        elif abs(diff) <= TOLERANCE:
            verdict = "✅ 기준 위치"
        else:
            ok = False
            way = "줄이는" if diff > 0 else "늘리는"
            verdict = f"🔴 {way} 방향으로 {deg:.0f}° 돌릴 것"
        print(f"{n:<14}{pos[n]:>8}{home[n]:>8}{diff:>+9}{deg:>8.0f}°   {verdict}")

    print()
    if ok:
        print("✅ wrist_flex·wrist_roll 이 기준 위치에 있다. 이 자세에서 시작하면 된다.")
        print("   다음: check_align.py 로 리더를 팔로워에 맞출 것.")
        return 0

    print("🔴 기준에서 벗어난 축이 있다.")
    print("   **손으로** 돌려 맞춘 뒤 다시 실행할 것. 이 도구는 서보를 움직이지 않는다.")
    print("   기준에서 시작해야 배선이 편안한 방향에서 텔레옵이 시작된다 (구축기록 §5-5).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
