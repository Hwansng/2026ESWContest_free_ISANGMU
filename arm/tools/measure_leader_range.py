"""리더암 각 축의 실제 가동 범위를 **정해진 시간 동안** 기록하고 중앙값을 계산한다.

watch_positions.py 는 Ctrl+C 까지 무한 대기라 원격/자동 실행에 맞지 않는다.
이 스크립트는 --seconds 동안만 기록하고 스스로 끝나면서 요약을 출력한다.

왜 필요한가 (실행계획 §5-2):
    팔이 쉬는 자세(어깨 처짐·팔꿈치 접힘)는 사실상 그 관절의 기계적 한계다.
    거기서 영점을 잡으면 한쪽으로 갈 데가 없어 반쪽만 기록되거나,
    반대로 훑을 때 엔코더 경계(0/4095)를 넘어 래핑한다.
    → 2026-07-13 팔로워 캘리브레이션 4회 실패의 원인이 전부 이것이었다.

    **먼저 실제 범위를 측정하고, 그 한가운데를 중간 자세로 삼는다.**

⚠️ 토크를 끄므로 팔이 중력에 무너진다. 받칠 것.

사용법:
    python tools/measure_leader_range.py --port COM5 --seconds 90
"""

import argparse
import time

from lerobot.motors import Motor, MotorNormMode
from lerobot.motors.feetech import FeetechMotorsBus

MOTORS = {
    "shoulder_pan": Motor(1, "sts3215", MotorNormMode.RANGE_M100_100),
    "shoulder_lift": Motor(2, "sts3215", MotorNormMode.RANGE_M100_100),
    "elbow_flex": Motor(3, "sts3215", MotorNormMode.RANGE_M100_100),
    "wrist_flex": Motor(4, "sts3215", MotorNormMode.RANGE_M100_100),
    "wrist_roll": Motor(5, "sts3215", MotorNormMode.RANGE_M100_100),
    "gripper": Motor(6, "sts3215", MotorNormMode.RANGE_0_100),
}

# wrist_roll 은 연속 회전축이라 LeRobot 이 0~4095 를 자동 부여한다. 판정에서 제외.
FULL_TURN_MOTOR = "wrist_roll"

EDGE = 60          # 이 값 이내로 경계에 접근하면 위험
MIN_SPAN = 400     # 이보다 좁으면 축을 제대로 훑지 않은 것으로 본다


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--seconds", type=float, default=90.0, help="기록 시간 (기본 90초)")
    args = parser.parse_args()

    bus = FeetechMotorsBus(port=args.port, motors=MOTORS)
    bus.connect(handshake=False)
    bus.disable_torque()
    print(f"⚠ 토크를 껐다. 팔이 중력에 무너진다 — 손으로 받칠 것.")
    print(f"기록 시작. {args.seconds:.0f}초 동안 **모든 관절을 양쪽 끝까지** 천천히 움직일 것.\n")

    lo = {name: 4095 for name in MOTORS}
    hi = {name: 0 for name in MOTORS}
    start = time.perf_counter()
    samples = 0

    try:
        while (elapsed := time.perf_counter() - start) < args.seconds:
            pos = bus.sync_read("Present_Position", normalize=False)
            for name in MOTORS:
                lo[name] = min(lo[name], pos[name])
                hi[name] = max(hi[name], pos[name])
            samples += 1
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("[중단] 지금까지 기록한 값으로 요약한다.\n")
    finally:
        bus.disconnect(disable_torque=False)

    print(f"기록 종료 — {elapsed:.0f}초, {samples} 샘플\n")

    header = f"{'축':<14}{'MIN':>6}{'MAX':>6}{'범위':>7}{'각도':>8}{'중앙값':>8}   판정"
    print(header)
    print("-" * (len(header) + 14))

    problems = []
    midpoints = {}
    for name in MOTORS:
        span = hi[name] - lo[name]
        mid = (lo[name] + hi[name]) // 2
        midpoints[name] = mid
        deg = span * 360 / 4096

        if name == FULL_TURN_MOTOR:
            verdict = "연속 회전축 — 판정 제외"
        elif span < MIN_SPAN:
            verdict = "🔴 범위가 너무 좁다 — 이 축을 안 움직였다"
            problems.append(f"{name}: 범위 {span} — 다시 측정할 것")
        elif lo[name] <= EDGE and hi[name] >= 4095 - EDGE:
            verdict = "🔴 양쪽 경계 도달 — 래핑"
            problems.append(f"{name}: 0/4095 양쪽 도달 — 래핑했다")
        elif lo[name] <= EDGE:
            verdict = "🔴 0 경계 도달"
            problems.append(f"{name}: MIN={lo[name]} — 0 경계에 붙었다")
        elif hi[name] >= 4095 - EDGE:
            verdict = "🔴 4095 경계 도달"
            problems.append(f"{name}: MAX={hi[name]} — 4095 경계에 붙었다")
        elif not (lo[name] < 2048 < hi[name]):
            verdict = "⚠ 2048 을 포함하지 않음"
        else:
            verdict = "✅"

        print(f"{name:<14}{lo[name]:>6}{hi[name]:>6}{span:>7}{deg:>7.1f}°{mid:>8}   {verdict}")

    print()
    if problems:
        print("🔴 문제:")
        for p in problems:
            print(f"   - {p}")
        print()

    print("=== 캘리브레이션 중간 자세 목표값 ===")
    print("아래 값에 각 축을 맞춘 뒤 그 자세를 **유지한 채** lerobot-calibrate 를 실행할 것.\n")
    for name in MOTORS:
        if name == FULL_TURN_MOTOR:
            print(f"   {name:<14} (연속 회전축 — 아무 위치나 무방)")
        else:
            print(f"   {name:<14} → {midpoints[name]}")

    print()
    print("합격 기준: 전 축 MIN < 2048 < MAX, 0/4095 미접촉 (wrist_roll 제외)")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
