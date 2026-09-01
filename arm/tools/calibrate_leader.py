"""리더암 캘리브레이션을 **단계별로 분리해서** 실행한다.

lerobot-calibrate 는 프롬프트 2개(중간 자세 → 전 축 훑기)가 한 프로세스에 묶여 있어
사람이 터미널 앞에 붙어 있어야 한다. 이 스크립트는 각 단계를 독립 실행으로 쪼갠다.
내부 동작은 SOLeader.calibrate() 와 동일하다.

단계:
    --step pose     현재 위치만 읽는다 (쓰기 없음).
    --step raw      Homing_Offset 을 0 으로 지우고 **원시 엔코더** 범위를 측정한다.
    --step aim      원시 목표값까지 얼마나 남았는지 알려준다 (중간 자세 조준).
    --step homing   현재 자세를 2047 로 재정의한다 (Homing_Offset 기록).
    --step ranges   가동 범위를 기록하고 캘리브레이션을 서보+JSON 에 저장한다.

권장 순서: raw → aim (반복) → homing → ranges

⚠️ 순서를 지킬 것. homing 을 다시 하면 ranges 도 다시 해야 한다.

원시 측정(raw)이 왜 필요한가:
    Present_Position 은 서보가 `원시 엔코더 - Homing_Offset` 으로 계산해 보고한다.
    원시값이 0/4095 를 넘어가면 그 지점에서 값이 통째로 감기는데(wrap),
    **오프셋은 감긴 뒤에 빼므로 어떤 오프셋으로도 이를 되돌릴 수 없다.**
    관절의 물리적 가동 범위가 원시 0 을 가로지르면 기구적으로 고쳐야 한다.
    → raw 로 이를 먼저 판별하고, 가로지르지 않으면 원시 중앙에 자세를 맞춘다.

왜 중간 자세가 중요한가 (실행계획 §5-2):
    팔이 쉬는 자세는 사실상 그 관절의 기계적 한계다. 거기서 영점을 잡으면
    반쪽만 기록되거나 엔코더 경계(0/4095)를 넘어 래핑한다.
    → 2026-07-13 팔로워 캘리브레이션 4회 실패의 원인.

사용법:
    python tools/calibrate_leader.py --port COM5 --step pose
    python tools/calibrate_leader.py --port COM5 --step homing
    python tools/calibrate_leader.py --port COM5 --step ranges --seconds 120
"""

import argparse
import json
import time
from pathlib import Path

from lerobot.motors import Motor, MotorCalibration, MotorNormMode
from lerobot.motors.feetech import FeetechMotorsBus, OperatingMode

MOTORS = {
    "shoulder_pan": Motor(1, "sts3215", MotorNormMode.RANGE_M100_100),
    "shoulder_lift": Motor(2, "sts3215", MotorNormMode.RANGE_M100_100),
    "elbow_flex": Motor(3, "sts3215", MotorNormMode.RANGE_M100_100),
    "wrist_flex": Motor(4, "sts3215", MotorNormMode.RANGE_M100_100),
    "wrist_roll": Motor(5, "sts3215", MotorNormMode.RANGE_M100_100),
    "gripper": Motor(6, "sts3215", MotorNormMode.RANGE_0_100),
}

# wrist_roll 은 연속 회전축이라 LeRobot 이 0~4095 를 자동 부여한다.
FULL_TURN_MOTOR = "wrist_roll"

CENTER = 2047
EDGE = 60        # 이 값 이내로 0/4095 에 접근하면 불합격
MIN_SPAN = 800   # 이보다 좁으면 축을 제대로 훑지 않은 것으로 본다

# Teleoperator 기반 클래스가 쓰는 경로와 동일해야 lerobot 이 찾는다.
#   HF_LEROBOT_CALIBRATION / TELEOPERATORS / "so_leader" / f"{id}.json"
CALIB_PATH = (
    Path.home() / ".cache" / "huggingface" / "lerobot" / "calibration"
    / "teleoperators" / "so_leader" / "leader_arm.json"
)
BACKUP_PATH = Path(__file__).resolve().parent.parent / "calibration" / "leader_arm.json"
# --step raw 가 계산한 원시 목표값. --step aim 이 읽는다.
TARGETS_PATH = Path(__file__).resolve().parent / ".leader_raw_targets.json"


def _connect(port: str) -> FeetechMotorsBus:
    bus = FeetechMotorsBus(port=port, motors=MOTORS)
    bus.connect(handshake=False)
    return bus


def step_pose(port: str) -> int:
    """읽기 전용. 중간 자세를 맞출 때 현재 값을 확인한다."""
    bus = _connect(port)
    try:
        pos = bus.sync_read("Present_Position", normalize=False)
        print(f"{'축':<14}{'현재 위치':>10}{'2047 과의 차':>14}")
        print("-" * 40)
        for name in MOTORS:
            mark = "  (연속 회전축)" if name == FULL_TURN_MOTOR else ""
            print(f"{name:<14}{pos[name]:>10}{pos[name] - CENTER:>+14}{mark}")
        print()
        print("※ 지금 값은 서보 EPROM 의 기존 Homing_Offset 이 반영된 좌표다.")
        print("  --step homing 이 이를 0 으로 초기화하고 현재 자세를 2047 로 재정의한다.")
        print("  따라서 지금 값 자체는 의미가 없고, **팔의 물리적 자세**만 맞추면 된다.")
        return 0
    finally:
        bus.disconnect(disable_torque=False)


def step_raw(port: str, seconds: float) -> int:
    """Homing_Offset 을 0 으로 지우고 원시 엔코더 가동 범위를 측정한다.

    원시값이 0 과 4095 **양쪽에 모두** 닿으면 관절 가동 범위가 엔코더 영점을
    가로지른다는 뜻이고, 이는 오프셋으로 해결되지 않는 기구적 문제다.
    """
    bus = _connect(port)
    try:
        bus.disable_torque()
        bus.reset_calibration()  # Homing_Offset = 0, 한계 0~4095
        print("Homing_Offset 을 0 으로 초기화했다. 이제 원시 엔코더 값을 직접 본다.")
        print(f"⚠ 토크 꺼짐 — 팔을 받칠 것.")
        print(f"기록 시작. {seconds:.0f}초 동안 wrist_roll 을 제외한 전 축을 양쪽 끝까지 움직일 것.\n")

        names = [n for n in MOTORS if n != FULL_TURN_MOTOR]
        start_pos = bus.sync_read("Present_Position", names, normalize=False)
        lo = {n: start_pos[n] for n in names}
        hi = {n: start_pos[n] for n in names}

        start = time.perf_counter()
        samples = 0
        while (elapsed := time.perf_counter() - start) < seconds:
            pos = bus.sync_read("Present_Position", names, normalize=False)
            for n in names:
                lo[n] = min(lo[n], pos[n])
                hi[n] = max(hi[n], pos[n])
            samples += 1
            time.sleep(0.05)
        print(f"기록 종료 — {elapsed:.0f}초, {samples} 샘플\n")
    finally:
        bus.disconnect(disable_torque=False)

    header = f"{'축':<14}{'원시MIN':>9}{'원시MAX':>9}{'범위':>7}{'각도':>8}{'목표 원시':>10}   판정"
    print(header)
    print("-" * (len(header) + 16))

    targets, blocked = {}, []
    for n in names:
        span = hi[n] - lo[n]
        deg = span * 360 / 4096
        mid = (lo[n] + hi[n]) // 2
        targets[n] = mid

        touches_zero = lo[n] <= EDGE
        touches_max = hi[n] >= 4095 - EDGE

        if span < MIN_SPAN:
            verdict = "🔴 덜 훑었다 — 재측정"
            blocked.append(f"{n}: 범위 {span} ({deg:.0f}°) — 이 축을 끝까지 안 움직였다")
        elif touches_zero and touches_max:
            verdict = "🔴 엔코더 영점을 가로지름 — 기구적 문제"
            blocked.append(f"{n}: 원시 0 과 4095 양쪽 도달 — 서보 혼 재장착 필요")
        else:
            verdict = "✅ 오프셋으로 해결 가능"
        print(f"{n:<14}{lo[n]:>9}{hi[n]:>9}{span:>7}{deg:>7.1f}°{mid:>10}   {verdict}")

    print()
    if blocked:
        print("🔴 문제:")
        for b in blocked:
            print(f"   - {b}")
        print()

    # 중앙값만이 아니라 관측 범위도 저장한다. aim 이 축별 허용 오차를 계산해야 하기 때문이다.
    TARGETS_PATH.write_text(
        json.dumps({n: {"lo": lo[n], "hi": hi[n]} for n in names}, indent=4), encoding="utf-8"
    )
    print(f"목표값 저장: {TARGETS_PATH}")
    print("\n다음: --step aim 으로 각 축을 위 '목표 원시' 값에 맞춘 뒤 --step homing.")
    return 1 if blocked else 0


def step_aim(port: str, skip: list[str]) -> int:
    """저장된 원시 목표값까지 각 축이 얼마나 남았는지 보여준다."""
    if not TARGETS_PATH.is_file():
        print(f"❌ 목표값이 없다. 먼저 --step raw 를 실행할 것. ({TARGETS_PATH})")
        return 1
    ranges = json.loads(TARGETS_PATH.read_text(encoding="utf-8"))
    for n in skip:
        ranges.pop(n, None)

    bus = _connect(port)
    try:
        pos = bus.sync_read("Present_Position", list(ranges), normalize=False)
    finally:
        bus.disconnect(disable_torque=False)

    # 영점 자세 P 를 잡으면 훑을 때 reported = 원시 - P + 2047 이 된다.
    # 양 끝이 EDGE 안쪽에 들어오려면 P 가 아래 폭 안에 있어야 한다:
    #     원시MAX - (4095 - EDGE - 2047)  <  P  <  원시MIN + (2047 - EDGE)
    # 즉 허용 폭은 (4095 - 2*EDGE) - span 이고, 가동 범위가 좁을수록 넉넉하다.
    print(f"{'축':<14}{'현재':>8}{'목표':>8}{'차이':>9}{'허용':>8}   방향")
    print("-" * 66)
    ok = True
    for n, r in ranges.items():
        span = r["hi"] - r["lo"]
        target = (r["lo"] + r["hi"]) // 2
        tol = ((4095 - 2 * EDGE) - span) // 2
        diff = pos[n] - target
        if tol <= 0:
            ok = False
            arrow = "🔴 가동 범위가 너무 넓다 — 영점을 잡을 여유가 없다"
        elif abs(diff) <= tol:
            arrow = "✅ 맞음"
        else:
            ok = False
            need = abs(diff) - tol
            arrow = f"{'줄이는' if diff > 0 else '늘리는'} 방향으로 최소 {need} 더"
        print(f"{n:<14}{pos[n]:>8}{target:>8}{diff:>+9}{tol:>+8}   {arrow}")

    print()
    print("✅ 전 축이 목표에 도달했다. --step homing 으로 진행할 것."
          if ok else "아직 맞지 않은 축이 있다. 조정 후 --step aim 을 다시 실행할 것.")
    return 0 if ok else 1


def step_offset(port: str, motor: str, value: int) -> int:
    """한 축의 Homing_Offset 을 직접 쓴다 (감김 지점 이동 시험용).

    서보가 오프셋을 감김 **이전에** 적용한다면 감김 지점이 함께 이동한다.
    관절이 지나가지 않는 구간으로 감김 지점을 옮기면 분해 없이 해결된다.
    """
    bus = _connect(port)
    try:
        bus.disable_torque()
        before = bus.read("Present_Position", motor, normalize=False)
        bus.write("Homing_Offset", motor, value, normalize=False)
        after = bus.read("Present_Position", motor, normalize=False)
        readback = bus.read("Homing_Offset", motor, normalize=False)
        print(f"{motor}: Homing_Offset {value} 기록 (읽기 확인 {readback})")
        print(f"   위치 {before} → {after}")
        print(f"\n다음: --step trace --motor {motor} 로 감김이 사라졌는지 확인할 것.")
        return 0
    finally:
        bus.disconnect(disable_torque=False)


def step_trace(port: str, motor: str, seconds: float) -> int:
    """한 축의 위치를 시계열로 기록하고 **불연속 점프**를 찾는다.

    엔코더가 0/4095 에서 감기면(wrap) 한 샘플 만에 ~4096 이 튄다.
    서보가 다회전을 연속 추적하면 값이 범위를 벗어나도 매끄럽게 이어진다.
    이 둘은 대처법이 정반대라 반드시 구분해야 한다.
    """
    bus = _connect(port)
    trace = []
    try:
        bus.disable_torque()
        print(f"⚠ 토크 꺼짐 — 팔을 받칠 것.")
        print(f"'{motor}' 를 {seconds:.0f}초 동안 **한 방향으로 천천히** 끝까지 움직일 것.")
        print("빠르게 움직이면 정상 변화도 점프로 오인된다.\n")

        start = time.perf_counter()
        while (elapsed := time.perf_counter() - start) < seconds:
            trace.append(bus.read("Present_Position", motor, normalize=False))
            time.sleep(0.02)
    finally:
        bus.disconnect(disable_torque=False)

    print(f"기록 종료 — {elapsed:.0f}초, {len(trace)} 샘플")
    print(f"관측 범위: {min(trace)} ~ {max(trace)}  (span {max(trace) - min(trace)})\n")

    jumps = [
        (i, trace[i - 1], trace[i], trace[i] - trace[i - 1])
        for i in range(1, len(trace))
        if abs(trace[i] - trace[i - 1]) > 500
    ]

    if not jumps:
        deltas = [abs(trace[i] - trace[i - 1]) for i in range(1, len(trace))]
        print(f"✅ 불연속 점프 없음 (최대 샘플 간 변화 {max(deltas) if deltas else 0})")
        print("   → 서보가 위치를 **연속 추적**한다. 값이 0~4095 를 벗어나도 감기지 않는다.")
        print(f"   → 따라서 관측된 span {max(trace) - min(trace)} 는 **실제 물리 회전량**이다.")
        return 0

    print(f"🔴 불연속 점프 {len(jumps)}회 발견 — 엔코더가 감긴다(wrap).\n")
    for i, prev, cur, d in jumps[:5]:
        print(f"   샘플 {i:>5}:  {prev:>6} → {cur:>6}   (변화 {d:+})")
    if len(jumps) > 5:
        print(f"   ... 외 {len(jumps) - 5}회")
    print("\n   → 이 축의 가동 범위가 엔코더 영점을 가로지른다.")
    print("     오프셋으로는 해결되지 않는다. 서보 혼을 재장착해야 한다.")
    return 1


def step_homing(port: str, skip: list[str]) -> int:
    """현재 자세를 각 축의 영점(2047)으로 기록한다.

    skip 에 지정한 축은 건드리지 않는다. 가동 범위가 엔코더 영점을 가로질러
    --step offset 으로 오프셋을 수동 지정한 축을 보존할 때 쓴다.
    """
    bus = _connect(port)
    targets = [n for n in MOTORS if n not in skip]
    try:
        bus.disable_torque()
        for motor in targets:
            bus.write("Operating_Mode", motor, OperatingMode.POSITION.value)

        if skip:
            print(f"제외: {', '.join(skip)} — 기존 Homing_Offset 을 유지한다.")
        print("현재 자세를 2047 로 재정의한다 (대상 축의 기존 오프셋은 0 으로 초기화)...\n")
        homing_offsets = bus.set_half_turn_homings(targets)

        pos = bus.sync_read("Present_Position", normalize=False)
        print(f"{'축':<14}{'homing_offset':>15}{'확인 위치':>12}")
        print("-" * 42)
        ok = True
        for name in MOTORS:
            if name in skip:
                kept = bus.read("Homing_Offset", name, normalize=False)
                print(f"{name:<14}{kept:>15}{pos[name]:>12}   (유지)")
                continue
            flag = "" if abs(pos[name] - CENTER) <= 2 else "   ⚠ 2047 이 아니다"
            if flag:
                ok = False
            print(f"{name:<14}{homing_offsets[name]:>15}{pos[name]:>12}{flag}")

        print()
        if not ok:
            print("⚠ 일부 축이 2047 로 맞지 않는다. 팔이 움직였을 수 있으니 재실행할 것.")
            return 1

        print("✅ 영점 설정 완료. 전 축이 2047 이다.")
        print("   다음: --step ranges 로 가동 범위를 기록할 것.")
        print("   ⚠ 이 단계 이후 팔을 움직여도 되지만, homing 을 다시 하면 처음부터다.")
        return 0
    finally:
        bus.disconnect(disable_torque=False)


def step_ranges(port: str, seconds: float) -> int:
    """가동 범위를 기록하고 캘리브레이션을 서보 EPROM 과 JSON 에 저장한다."""
    bus = _connect(port)
    recorded = {}
    try:
        bus.disable_torque()
        print("⚠ 토크를 껐다. 팔이 중력에 무너진다 — 손으로 받칠 것.")
        print(f"기록 시작. {seconds:.0f}초 동안 **wrist_roll 을 제외한 전 축**을 양쪽 끝까지 움직일 것.\n")

        names = [n for n in MOTORS if n != FULL_TURN_MOTOR]
        start_pos = bus.sync_read("Present_Position", normalize=False)
        lo = {n: start_pos[n] for n in names}
        hi = {n: start_pos[n] for n in names}

        start = time.perf_counter()
        samples = 0
        while (elapsed := time.perf_counter() - start) < seconds:
            pos = bus.sync_read("Present_Position", names, normalize=False)
            for n in names:
                lo[n] = min(lo[n], pos[n])
                hi[n] = max(hi[n], pos[n])
            samples += 1
            time.sleep(0.05)

        print(f"기록 종료 — {elapsed:.0f}초, {samples} 샘플\n")

        header = f"{'축':<14}{'MIN':>7}{'MAX':>7}{'범위':>7}{'각도':>8}   판정"
        print(header)
        print("-" * (len(header) + 12))

        problems = []
        for n in names:
            span = hi[n] - lo[n]
            deg = span * 360 / 4096
            if span < MIN_SPAN:
                verdict = "🔴 범위가 좁다 — 덜 훑었다"
                problems.append(f"{n}: 범위 {span} ({deg:.0f}°) — 다시 훑을 것")
            elif lo[n] <= EDGE or hi[n] >= 4095 - EDGE:
                verdict = "🔴 0/4095 경계 접촉"
                problems.append(f"{n}: {lo[n]}~{hi[n]} — 중간 자세가 치우쳤다. homing 부터 다시")
            elif not (lo[n] < CENTER < hi[n]):
                verdict = "🔴 2047 을 포함하지 않음"
                problems.append(f"{n}: {lo[n]}~{hi[n]} — 영점이 범위 밖이다")
            else:
                verdict = "✅"
            print(f"{n:<14}{lo[n]:>7}{hi[n]:>7}{span:>7}{deg:>7.1f}°   {verdict}")

        print(f"{FULL_TURN_MOTOR:<14}{0:>7}{4095:>7}{4095:>7}{360.0:>7.1f}°   (연속 회전축 — 자동)")
        print()

        if problems:
            print("🔴 저장하지 않았다. 문제:")
            for p in problems:
                print(f"   - {p}")
            print("\n   경계 접촉이면 --step homing 부터, 범위가 좁으면 --step ranges 만 다시 할 것.")
            return 1

        # 합격. 캘리브레이션을 구성해 서보 EPROM 과 JSON 양쪽에 기록한다.
        homing_offsets = bus.sync_read("Homing_Offset", normalize=False)
        for name, m in MOTORS.items():
            if name == FULL_TURN_MOTOR:
                rmin, rmax = 0, 4095
            else:
                rmin, rmax = lo[name], hi[name]
            recorded[name] = MotorCalibration(
                id=m.id, drive_mode=0,
                homing_offset=homing_offsets[name],
                range_min=rmin, range_max=rmax,
            )

        bus.write_calibration(recorded)
        print("✅ 서보 EPROM 에 기록 완료.")
    finally:
        bus.disconnect(disable_torque=False)

    if not recorded:
        return 1

    payload = {
        name: {
            "id": c.id, "drive_mode": c.drive_mode,
            "homing_offset": c.homing_offset,
            "range_min": c.range_min, "range_max": c.range_max,
        }
        for name, c in recorded.items()
    }
    for path in (CALIB_PATH, BACKUP_PATH):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=4), encoding="utf-8")
        print(f"✅ 저장: {path}")

    print("\n🎉 리더 캘리브레이션 완료. 다음은 텔레옵(마일스톤 1)이다.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--step", required=True,
                        choices=["pose", "raw", "trace", "offset", "aim", "homing", "ranges"])
    parser.add_argument("--value", type=int, default=2048, help="--step offset 으로 쓸 Homing_Offset")
    parser.add_argument("--skip", nargs="*", default=[], choices=list(MOTORS),
                        help="homing/aim 에서 제외할 축 (수동 오프셋을 보존할 때)")
    parser.add_argument("--seconds", type=float, default=120.0, help="raw/ranges/trace 기록 시간")
    parser.add_argument("--motor", choices=list(MOTORS), default="shoulder_lift",
                        help="--step trace 로 추적할 축")
    args = parser.parse_args()

    try:
        if args.step == "pose":
            return step_pose(args.port)
        if args.step == "raw":
            return step_raw(args.port, args.seconds)
        if args.step == "trace":
            return step_trace(args.port, args.motor, args.seconds)
        if args.step == "offset":
            return step_offset(args.port, args.motor, args.value)
        if args.step == "aim":
            return step_aim(args.port, args.skip)
        if args.step == "homing":
            return step_homing(args.port, args.skip)
        return step_ranges(args.port, args.seconds)
    except ConnectionError:
        print(f"❌ 포트 '{args.port}' 를 열 수 없다. 어댑터 USB 연결을 확인할 것.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
