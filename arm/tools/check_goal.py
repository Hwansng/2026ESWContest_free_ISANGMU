"""텔레옵 시작 시 팔로워가 혼자 움직이는 문제를 진단·해소한다 (읽기 기본, --fix 로 교정).

증상:
    정렬 확인(check_align.py)을 통과했는데도 텔레옵을 시작하는 순간
    팔로워의 특정 축이 명령 없이 혼자 움직인다.

원인:
    Feetech 서보의 `Goal_Position` 은 EPROM 이 아니라 RAM 이지만 **전원이 유지되는 한 남는다.**
    텔레옵이 시작되면 `configure()` 가 토크를 켜는데, 서보는 그 순간
    **가장 최근에 기록된 Goal_Position 으로 즉시 이동**한다.
    그 값이 이전 세션 종료 시점의 것이면, 리더 명령이 도착하기도 전에 팔이 움직인다.

    특히 `wrist_roll` 처럼 배선에 막혀 목표에 도달하지 못한 축은
    Goal 과 Present 가 크게 벌어진 채 남아 있어 증상이 심하다.

    정렬 확인은 `Present_Position` 만 비교하므로 이 문제를 잡지 못한다.

해소:
    토크를 켜기 전에 `Goal_Position = Present_Position` 으로 맞춰 두면
    토크가 켜져도 서보가 제자리를 유지한다.

🔴 중요 — STS3215 는 `Goal_Position` 을 받으면 **토크를 자동으로 켠다.**
    쓰기만 하고 두면 서보가 그 위치를 유지하려 계속 힘을 쓴다. 배선 복원력이나
    외력으로 밀리면 되돌리려다 과부하로 버스에서 떨어진다.
    (2026-07-28 에 wrist_roll 이 실제로 이렇게 죽어 전원 재투입이 필요했다)
    → 이 스크립트는 쓰기 직후 반드시 `disable_torque()` 로 되돌리고 확인한다.

사용법:
    python tools/check_goal.py --port COM3
    python tools/check_goal.py --port COM3 --fix
"""

import argparse

from lerobot.motors import Motor, MotorNormMode
from lerobot.motors.feetech import FeetechMotorsBus

MOTOR_IDS = {
    "shoulder_pan": 1, "shoulder_lift": 2, "elbow_flex": 3,
    "wrist_flex": 4, "wrist_roll": 5, "gripper": 6,
}

# 이 이상 벌어져 있으면 토크 인가 시 눈에 띄게 움직인다.
# 4096 카운트 = 360도 이므로 100 카운트 ≈ 8.8도.
THRESHOLD = 100


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True, help="팔로워 COM 포트 (예: COM3)")
    parser.add_argument("--fix", action="store_true",
                        help="Goal_Position 을 Present_Position 으로 맞춘다")
    args = parser.parse_args()

    motors = {
        n: Motor(i, "sts3215",
                 MotorNormMode.RANGE_0_100 if n == "gripper" else MotorNormMode.RANGE_M100_100)
        for n, i in MOTOR_IDS.items()
    }
    bus = FeetechMotorsBus(port=args.port, motors=motors)
    bus.connect(handshake=False)

    try:
        header = f"{'축':<14}{'현재':>8}{'목표':>8}{'차이':>9}{'토크':>6}{'모드':>6}   판정"
        print(header)
        print("-" * (len(header) + 10))

        offenders = []
        for name in MOTOR_IDS:
            cur = bus.read("Present_Position", name, normalize=False)
            goal = bus.read("Goal_Position", name, normalize=False)
            torque = bus.read("Torque_Enable", name, normalize=False)
            mode = bus.read("Operating_Mode", name, normalize=False)
            lo = bus.read("Min_Position_Limit", name, normalize=False)
            hi = bus.read("Max_Position_Limit", name, normalize=False)

            # 서보는 Goal 을 위치 한계로 자른 뒤 그리로 이동한다.
            # 한계를 무시하고 계산하면 실제보다 훨씬 큰 값이 나와 경고가 과장된다.
            # (전원 재투입 후 Goal=0 이면 한계 없는 축만 크게 돈다 — 그것이 핵심 위험이다)
            effective = min(hi, max(lo, goal))
            diff = effective - cur

            if abs(diff) > THRESHOLD:
                deg = abs(diff) * 360 / 4096
                verdict = f"🔴 토크 인가 시 약 {deg:.0f}° 튄다"
                offenders.append((name, cur, goal, diff))
            else:
                verdict = "✅"
            print(f"{name:<14}{cur:>8}{goal:>8}{diff:>+9}{torque:>6}{mode:>6}   {verdict}")

        print()
        if not offenders:
            print("✅ 전 축의 Goal 이 Present 와 일치한다. 시작 시 튀지 않는다.")
            return 0

        print(f"🔴 {len(offenders)}개 축에서 Goal 과 Present 가 벌어져 있다.")
        print("   토크가 켜지는 순간 서보가 저장된 Goal 로 즉시 이동한다.")
        print("   **정렬 확인(check_align.py)은 Present 만 비교하므로 이 문제를 못 잡는다.**")

        if not args.fix:
            print("\n   교정하려면 --fix 를 붙일 것 (Goal 을 현재 위치로 덮어쓴다).")
            return 1

        print("\n   교정 중 — Goal_Position 을 현재 위치로 맞춘다...")
        # 🔴 STS3215 는 Goal_Position 을 받으면 **토크를 자동으로 켠다.**
        #    서보가 그 위치를 유지하려 계속 힘을 쓰고, 배선 복원력이나 외력으로 밀리면
        #    되돌리려다 과부하로 버스에서 떨어진다.
        #
        #    ⚠ 축 하나씩 **쓴 직후 바로** 토크를 끈다. 루프를 다 돌고 나서 한 번에 끄면,
        #      중간에 통신 글리치로 예외가 나는 순간 앞서 켜진 축들이 토크를 문 채 남는다.
        #      (2026-07-28: gripper 쓰기 실패 → wrist_roll 이 토크를 유지하다 죽음)
        failed = []
        for name, cur, goal, _ in offenders:
            try:
                bus.write("Goal_Position", name, cur, normalize=False)
                after = bus.read("Goal_Position", name, normalize=False)
                mark = "✅" if abs(after - cur) <= 2 else f"🔴 확인값 {after}"
                print(f"   {name:<14} {goal} → {after}   {mark}")
            except Exception as e:
                failed.append(name)
                print(f"   {name:<14} 🔴 실패: {type(e).__name__}")
            finally:
                # 이 축의 토크는 무슨 일이 있어도 되돌린다.
                try:
                    bus.write("Torque_Enable", name, 0, normalize=False)
                except Exception:
                    failed.append(f"{name}(토크 해제 실패)")

        # 전 축 토크가 실제로 꺼졌는지 확인한다. 못 읽는 축은 이미 버스에서 떨어진 것이다.
        still_on, unreachable = [], []
        for n in MOTOR_IDS:
            try:
                if bus.read("Torque_Enable", n, normalize=False):
                    still_on.append(n)
            except Exception:
                unreachable.append(n)

        print()
        if unreachable:
            print(f"🔴 응답 없음: {', '.join(unreachable)}")
            print("   해당 서보가 버스에서 떨어졌다. **전원을 빼고 다시 넣을 것.**")
            return 1
        if still_on:
            print(f"🔴 토크가 아직 켜져 있다: {', '.join(still_on)}")
            print("   전원을 차단할 것. 이대로 두면 서보가 계속 힘을 쓴다.")
            return 1
        if failed:
            print(f"🔴 일부 축 교정 실패: {', '.join(failed)}")
            print("   토크는 모두 꺼진 상태다. 다시 실행할 것.")
            return 1

        print("✅ 교정 완료. 토크는 전 축 꺼진 상태로 되돌렸다.")
        print("   이제 텔레옵을 시작해도 제자리에서 출발한다.")
        return 0
    finally:
        bus.disconnect(disable_torque=False)


if __name__ == "__main__":
    raise SystemExit(main())
