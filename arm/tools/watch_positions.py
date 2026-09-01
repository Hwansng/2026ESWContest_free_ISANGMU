"""팔로워 6축의 위치를 실시간으로 표시한다 (읽기 전용).

캘리브레이션 전에 각 관절을 손으로 움직여 보며:
  - 어느 ID 가 어느 물리 축에 대응하는지 확인
  - 위치값이 0/4095 경계를 넘어 래핑(wrap)하는지 확인
  - 통신 글리치로 값이 튀는지 확인

토크는 건드리지 않는다. 서보에 전원이 들어가 있으면 토크가 켜져 있어 뻑뻑할 수 있으므로,
--free 를 주면 토크를 꺼서 손으로 움직일 수 있게 한다 (팔이 중력에 무너지니 받칠 것).

사용법:
    python tools/watch_positions.py --port COM3
    python tools/watch_positions.py --port COM3 --free
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--free", action="store_true", help="토크를 꺼서 손으로 움직일 수 있게 한다")
    args = parser.parse_args()

    bus = FeetechMotorsBus(port=args.port, motors=MOTORS)
    bus.connect(handshake=False)

    if args.free:
        bus.disable_torque()
        print("⚠ 토크를 껐다. 팔이 중력에 무너진다 — 손으로 받칠 것.\n")

    lo = {name: 4095 for name in MOTORS}
    hi = {name: 0 for name in MOTORS}

    print("관절을 하나씩 천천히 움직여 볼 것. Ctrl+C 로 종료.")
    print("MIN/MAX 가 0 이나 4095 에 닿으면 래핑(wrap)이 일어난 것이다.\n")

    try:
        while True:
            pos = bus.sync_read("Present_Position", normalize=False)

            lines = []
            for name in MOTORS:
                p = pos[name]
                lo[name] = min(lo[name], p)
                hi[name] = max(hi[name], p)

                # 0/4095 경계에 닿았으면 표시
                warn = ""
                if lo[name] <= 10 or hi[name] >= 4085:
                    warn = "  ← 경계 도달 (래핑 의심)"

                lines.append(f"{name:<14} {p:>5}   [{lo[name]:>4} ~ {hi[name]:>4}]{warn}")

            print("\033[H\033[J", end="")  # 화면 지우기
            print("축              현재    [최소 ~ 최대]")
            print("-" * 55)
            print("\n".join(lines))
            print("\nCtrl+C 로 종료")

            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n\n=== 관측된 범위 ===")
        for name in MOTORS:
            span = hi[name] - lo[name]
            deg = span * 360 / 4096
            print(f"{name:<14} {lo[name]:>4} ~ {hi[name]:>4}   (범위 {span:>4} ≈ {deg:>5.1f}°)")
    finally:
        bus.disconnect(disable_torque=False)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
