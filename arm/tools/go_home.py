"""팔로워를 저장된 기준 자세(홈)로 **천천히** 복귀시킨다.

왜 필요한가:
    ACT 정책은 "뚜껑 닫고 1초 유지 후 종료"로 학습됐기 때문에, 롤아웃이 끝나면
    팔이 **뚜껑 위 최종 자세에 그대로 멈춰 있다.** 다음 시행은 홈 자세에서
    시작해야 학습 분포와 맞으므로, 매번 사람이 손으로 되돌려야 했다.

    이 도구가 그 복귀를 대신한다. `check_home.py` 는 **읽기 전용**이라
    얼마나 어긋났는지만 알려줄 뿐 움직이지 못한다 — 그래서 이 도구가 따로 필요하다.

🔴 STS3215 는 `Goal_Position` 을 받으면 **토크를 자동으로 켠다.**
    쓰기만 하고 두면 서보가 그 위치를 유지하려 계속 힘을 쓰고, 배선 복원력이나
    외력으로 밀리면 되돌리려다 과부하로 버스에서 떨어진다.
    (2026-07-28 에 wrist_roll 이 실제로 이렇게 죽어 전원 재투입이 필요했다)
    → `home_arm()` 은 **어떤 경로로 끝나든** 전 축 토크를 끄고, 실제로 꺼졌는지 확인한다.

🔴 한 번에 목표로 점프시키지 않는다.
    `check_goal.py` 실측에서 축 하나가 194° 벌어진 적이 있다. 그 거리를 순간 이동으로
    명령하면 서보가 최대 속도로 튀어 팔·배선·주변 물체를 때린다.
    → 코사인 이징으로 시작·끝 속도가 0 이 되게 보간해 나눠 보낸다.

사용법 (CLI):
    python tools/go_home.py --port COM3                 # 3초에 걸쳐 홈으로 복귀
    python tools/go_home.py --port COM3 --seconds 5     # 더 천천히
    python tools/go_home.py --port COM3 --dry-run       # 움직이지 않고 계획만 출력

라이브러리로 쓸 때 (`run_lerobot_record_patched.py` 가 이렇게 쓴다):
    from tools.go_home import home_arm
    home_arm(robot.bus)     # 이미 연결된 버스를 그대로 재사용 — 프로세스 재시작이 없다
"""

import argparse
import json
import math
import time
from pathlib import Path

from lerobot.motors import Motor, MotorNormMode
from lerobot.motors.feetech import FeetechMotorsBus

MOTOR_IDS = {
    "shoulder_pan": 1, "shoulder_lift": 2, "elbow_flex": 3,
    "wrist_flex": 4, "wrist_roll": 5, "gripper": 6,
}

HOME_PATH = Path(__file__).resolve().parent.parent / "calibration" / "follower_home.json"

# 도착 판정. 4096 카운트 = 360도 이므로 40 카운트 ≈ 3.5도.
ARRIVAL_TOLERANCE = 40
# 이보다 가까우면 이미 홈으로 보고 움직이지 않는다 (불필요한 토크 인가를 피한다).
ALREADY_HOME = 25
# 홈 파일이 깨졌거나 팔 상태가 이상한 경우를 걸러내기 위한 상한. 넘으면 force 없이
# 움직이지 않는다. 3000 카운트 = 264도.
#
# 🔴 이 값을 2048(180도)로 낮추지 말 것. 2026-08-28 실측에서 **정상적인** 롤아웃 종료
#    자세(뚜껑 닫은 직후)가 shoulder_lift 1949 카운트(171도)였다. 2048 로 두면 시행마다
#    아슬아슬하게 걸려, 30회 검증 도중 가짜 거부로 루프 전체가 멈춘다.
#    거리 자체는 코사인 이징이 안전하게 처리하므로, 이 상한의 목적은 "먼 거리 차단"이
#    아니라 "말이 안 되는 값 차단"이다.
MAX_SAFE_DIFF = 3000


def _ease(t: float) -> float:
    """코사인 이징 — 시작과 끝에서 속도가 0 이 된다."""
    return 0.5 * (1.0 - math.cos(math.pi * t))


def home_arm(
    bus,
    seconds: float = 3.0,
    hz: int = 30,
    force: bool = False,
    disable_torque_after: bool = True,
    dry_run: bool = False,
    verbose: bool = True,
) -> bool:
    """이미 연결된 버스로 팔을 홈 자세로 복귀시킨다. 성공하면 True.

    `bus` 는 `MOTOR_IDS` 와 같은 이름의 모터를 가진 연결된 FeetechMotorsBus 여야 한다
    (`SOFollower.bus` 가 그렇다 — so_follower.py 의 모터 구성이 동일하다).
    """
    def say(*a):
        if verbose:
            print(*a)

    if not HOME_PATH.is_file():
        say(f"❌ 기준 자세가 없다: {HOME_PATH}")
        return False
    home_raw = json.loads(HOME_PATH.read_text(encoding="utf-8"))

    try:
        start = bus.sync_read("Present_Position", normalize=False)

        # 서보는 Goal 을 위치 한계로 자른 뒤 이동한다. 미리 잘라 두어야 "도착 못 함"을
        # 서보 한계 탓인지 막힘 탓인지 구분할 수 있다 (check_goal.py 와 같은 이유).
        target, plan = {}, []
        for name in MOTOR_IDS:
            if name not in home_raw or name not in start:
                continue
            lo = bus.read("Min_Position_Limit", name, normalize=False)
            hi = bus.read("Max_Position_Limit", name, normalize=False)
            goal = min(hi, max(lo, int(home_raw[name])))
            target[name] = goal
            plan.append((name, start[name], goal, goal - start[name]))

        if verbose:
            header = f"{'축':<14}{'현재':>8}{'홈':>8}{'이동량':>9}{'각도':>9}"
            say(header)
            say("-" * (len(header) + 6))
            for name, cur, goal, diff in plan:
                say(f"{name:<14}{cur:>8}{goal:>8}{diff:>+9}{abs(diff) * 360 / 4096:>8.0f}°")
            say("")

        largest = max((abs(d) for _, _, _, d in plan), default=0)

        if largest <= ALREADY_HOME:
            say("✅ 이미 홈 자세다. 움직이지 않는다.")
            return True

        if largest > MAX_SAFE_DIFF and not force:
            say(f"🔴 최대 이동량이 {largest} 카운트({largest * 360 / 4096:.0f}°)로 너무 크다.")
            say("   정상적인 롤아웃 종료 자세라면 이 정도로 벌어지지 않는다.")
            say("   팔 상태와 calibration/follower_home.json 을 확인할 것.")
            return False

        steps = max(2, int(seconds * hz))
        say(f"{seconds}초 / {steps}스텝에 걸쳐 복귀한다 (코사인 이징).")

        if dry_run:
            say("⚠ dry-run 이라 실제로는 움직이지 않았다.")
            return True

        # 🔴 여기서부터 서보가 움직인다. sync_write 가 토크를 자동으로 켠다.
        period = 1.0 / hz
        for i in range(1, steps + 1):
            f = _ease(i / steps)
            frame = {n: int(round(start[n] + (target[n] - start[n]) * f)) for n in target}
            bus.sync_write("Goal_Position", frame, normalize=False)
            time.sleep(period)

        # 서보가 마지막 명령을 따라잡을 시간을 준다.
        time.sleep(0.3)
        end = bus.sync_read("Present_Position", normalize=False)

        stuck = []
        for name in target:
            diff = end[name] - target[name]
            if abs(diff) <= ARRIVAL_TOLERANCE:
                say(f"   {name:<14}{end[name]:>8}   ✅")
            else:
                stuck.append(name)
                say(f"   {name:<14}{end[name]:>8}   🔴 홈에서 {abs(diff) * 360 / 4096:.0f}° 벗어남")

        say("")
        if stuck:
            say(f"🔴 도착하지 못한 축: {', '.join(stuck)}")
            say("   배선에 막혔거나 외력이 걸려 있다. **토크를 끈 뒤** 손으로 확인할 것.")
            return False
        say("✅ 홈 자세로 복귀했다.")
        return True

    finally:
        # 🔴 무슨 일이 있어도 토크를 되돌린다. 축 하나씩 개별로 — 루프 중간에 예외가 나도
        #    앞서 켜진 축이 토크를 문 채 남지 않게 한다 (2026-07-28 wrist_roll 사망 원인).
        if disable_torque_after:
            for n in MOTOR_IDS:
                try:
                    bus.write("Torque_Enable", n, 0, normalize=False)
                except Exception:
                    pass
            still_on, unreachable = [], []
            for n in MOTOR_IDS:
                try:
                    if bus.read("Torque_Enable", n, normalize=False):
                        still_on.append(n)
                except Exception:
                    unreachable.append(n)
            if unreachable:
                say(f"🔴 응답 없음: {', '.join(unreachable)} — 서보가 버스에서 떨어졌다. **전원 재투입할 것.**")
            if still_on:
                say(f"🔴 토크가 아직 켜져 있다: {', '.join(still_on)} — **전원을 차단할 것.**")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True, help="팔로워 COM 포트 (예: COM3)")
    parser.add_argument("--seconds", type=float, default=3.0, help="복귀에 걸릴 시간 (기본 3초)")
    parser.add_argument("--hz", type=int, default=30, help="명령 전송 주기 (기본 30Hz)")
    parser.add_argument("--dry-run", action="store_true", help="움직이지 않고 계획만 출력한다")
    parser.add_argument("--force", action="store_true",
                        help=f"{MAX_SAFE_DIFF} 카운트(264도) 이상 벌어져 있어도 진행한다")
    parser.add_argument("--keep-torque", action="store_true",
                        help="복귀 후 토크를 켜둔다 (기본은 끈다). 중력으로 처지면 안 될 때만 쓸 것")
    args = parser.parse_args()

    motors = {
        n: Motor(i, "sts3215",
                 MotorNormMode.RANGE_0_100 if n == "gripper" else MotorNormMode.RANGE_M100_100)
        for n, i in MOTOR_IDS.items()
    }
    bus = FeetechMotorsBus(port=args.port, motors=motors)
    bus.connect(handshake=False)
    try:
        ok = home_arm(
            bus,
            seconds=args.seconds,
            hz=args.hz,
            force=args.force,
            disable_torque_after=(not args.keep_torque),
            dry_run=args.dry_run,
        )
        if args.keep_torque:
            print("⚠ --keep-torque: 토크가 켜진 상태로 남았다. 서보가 계속 힘을 쓴다.")
        return 0 if ok else 1
    finally:
        bus.disconnect(disable_torque=False)


if __name__ == "__main__":
    raise SystemExit(main())
