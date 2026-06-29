"""서보 버스의 통신 안정성을 정량 측정한다 (읽기 전용).

왜 필요한가:
    LeRobot 의 `sync_read` / `write` 는 대부분 **재시도가 없다**(`after 1 tries`).
    시리얼 글리치 한 번에 텔레옵이나 녹화 세션 전체가 죽는다.
    50~100 에피소드를 수집하는 동안 이런 일이 나면 그때까지가 날아간다.

    간헐적 접촉 불량은 한 번 핑해서는 안 잡힌다. **반복 측정해서 성공률로 봐야 한다.**

읽는 법:
    - 특정 ID 만 성공률이 낮다  → 그 서보 또는 그 앞단 커넥터 접촉 불량
    - 뒤쪽 ID 일수록 낮다        → 데이지체인 신호 품질 (맨 끝이 경로가 가장 길다)
    - 전 ID 가 고르게 낮다       → 어댑터·USB 케이블·전원

사용법:
    python tools/check_bus.py --port COM3 --seconds 30
    python tools/check_bus.py --port COM3 --seconds 30 --shake   # 커넥터를 흔들며 측정
"""

import argparse
import time

from lerobot.motors import Motor, MotorNormMode
from lerobot.motors.feetech import FeetechMotorsBus

MOTOR_IDS = {
    "shoulder_pan": 1, "shoulder_lift": 2, "elbow_flex": 3,
    "wrist_flex": 4, "wrist_roll": 5, "gripper": 6,
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--seconds", type=float, default=30.0)
    parser.add_argument("--shake", action="store_true",
                        help="커넥터를 흔들며 측정하라는 안내를 출력한다")
    args = parser.parse_args()

    motors = {
        n: Motor(i, "sts3215",
                 MotorNormMode.RANGE_0_100 if n == "gripper" else MotorNormMode.RANGE_M100_100)
        for n, i in MOTOR_IDS.items()
    }
    bus = FeetechMotorsBus(port=args.port, motors=motors)
    bus.connect(handshake=False)

    if args.shake:
        print("⚠ 측정 중 3핀 커넥터를 하나씩 **가볍게 눌러보며** 성공률이 떨어지는지 볼 것.")
        print("  세게 흔들지 말 것 — 멀쩡한 접점을 망가뜨린다.\n")

    print(f"{args.seconds:.0f}초 동안 반복 측정한다...\n")

    seen = {i: 0 for i in MOTOR_IDS.values()}
    rounds = 0
    sync_fail = 0
    start = time.perf_counter()
    try:
        while (elapsed := time.perf_counter() - start) < args.seconds:
            rounds += 1
            present = bus.broadcast_ping() or {}
            for i in MOTOR_IDS.values():
                if i in present:
                    seen[i] += 1
            # 실사용 경로(sync_read)도 함께 본다. broadcast_ping 보다 부하가 크다.
            try:
                bus.sync_read("Present_Position", normalize=False)
            except Exception:
                sync_fail += 1
    finally:
        bus.disconnect(disable_torque=False)

    print(f"측정 종료 — {elapsed:.0f}초, {rounds}회\n")
    header = f"{'축':<14}{'ID':>3}{'성공':>8}{'성공률':>9}   판정"
    print(header)
    print("-" * (len(header) + 12))

    worst = 100.0
    for name, i in MOTOR_IDS.items():
        rate = seen[i] / rounds * 100 if rounds else 0.0
        worst = min(worst, rate)
        if rate >= 100.0:
            verdict = "✅"
        elif rate >= 99.0:
            verdict = "⚠ 간헐 실패"
        else:
            verdict = "🔴 접촉 불량 의심"
        print(f"{name:<14}{i:>3}{seen[i]:>8}{rate:>8.1f}%   {verdict}")

    sync_rate = (rounds - sync_fail) / rounds * 100 if rounds else 0.0
    print(f"\nsync_read 성공률 : {sync_rate:.1f}%  ({sync_fail}회 실패)")

    print()
    if worst >= 100.0 and sync_fail == 0:
        print("✅ 버스가 안정적이다. 통신 오류는 다른 원인을 볼 것.")
        return 0

    print("🔴 버스가 불안정하다. LeRobot 은 재시도가 없어 글리치 한 번에 세션이 죽는다.")
    print("   확인 순서:")
    print("   1. 성공률이 낮은 ID **앞단**의 3핀 커넥터를 다시 꽂아볼 것")
    print("      (뒤쪽 ID 가 낮으면 그 앞 어느 지점이든 원인일 수 있다)")
    print("   2. 커넥터가 헐겁거나 핀이 밀려 들어가 있는지 육안 확인")
    print("   3. 어댑터 쪽 3핀과 USB 케이블도 재체결")
    print("   4. 그래도 낮으면 --shake 로 어느 지점에서 떨어지는지 특정할 것")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
