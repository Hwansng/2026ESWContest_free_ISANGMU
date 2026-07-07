"""양팔 wrist_roll 의 가동 범위를 넓힌다 — 영점 정렬을 유지한 채 (2026-07-28).

## 왜 창이 70° 밖에 안 됐나

`limit_wrist_roll.py` 는 위치 한계를 **원시 엔코더 기준**이라 보고, 창이 원시 0 을
가로지르면 거부했다. 그 제약 때문에 손목 창이 ±35°(176~976) 로 묶였다.

**그 가정은 틀렸다.** 팔로워 6축을 직접 읽어 확인했다.

    축              homing   서보Min~Max   원시로 환산    상태
    shoulder_pan      1672    1151~3856    2823~1432    원시 0 가로지름 — 정상 동작
    shoulder_lift    -1563    1462~3746    3995~2183    원시 0 가로지름 — 정상 동작
    elbow_flex        1496     804~3021     2300~421    원시 0 가로지름 — 정상 동작
    wrist_flex        1999     919~3242    2918~1145    원시 0 가로지름 — 정상 동작
    gripper          -1510    1313~2793    3899~1283    원시 0 가로지름 — 정상 동작

5축 모두 원시 0 을 가로지르는 창으로 처음부터 멀쩡히 돌아갔다.
서보 Min/Max = JSON range_min/max 와 정확히 일치하므로, 한계는 **보고 좌표
(Present = 원시 − Homing_Offset) 기준**이다. 원시 0 가로지름은 무관하다.

## 방식

가동 범위가 영점 기준으로 크게 치우쳐 있다 (실측: 대략 −130° / +47°).
영점 대칭 창으로 잡으면 좁은 쪽에 묶여 손해가 크므로, **양팔 실측의 교집합을
그대로 창으로 쓰고 그 중점을 present 2048 에 놓는다.**

    창 = [영점+lo_off, 영점+hi_off]      (lo_off < 0 < hi_off, 비대칭)
    Homing_Offset = (영점 원시 + 중점오프셋) − 2048

양팔이 **같은 폭 · 영점의 같은 상대 위치**를 쓰므로 정규화가 1:1 로 대응하고
현재 맞춰진 그리퍼 방향 정렬이 그대로 유지된다.

중점을 2048 에 두면 보고 좌표의 불연속(present 0/4095)이 창에서 가장 멀어진다.

## 순서

    1. --measure --arm follower   토크 끄고 손으로 양끝까지
    2. --measure --arm leader     리더도 동일

    🔴 측정 기준을 정확히 전달할 것 — 결과가 크게 달라진다.
       "장력이 시작되는 곳" 으로 재면 174°, "뻣뻣한 저항이 분명한 곳" 으로 재면 227° 가
       같은 하드웨어에서 나왔다 (2026-07-29). 전자로 재고 "180° 는 물리적으로 불가능"
       이라 결론냈다가 뒤집혔다. **저항이 분명해지는 지점까지, 무리한 힘은 금물.**
    3. --plan                     교집합으로 창 결정 (쓰기 없음)
    4. --apply --arm follower  →  --apply --arm leader
    5. --profile                  각도별 정착 부하 (어디서 배선이 뻣뻣해지는지)
    6. --goal-test                창 끝단까지 추종하는지 확인 (움직임)
    7. teleop.ps1 로 최종 확인

🔴 --plan 에 --max-half 를 줬다면 --apply / --profile / --goal-test 에 **같은 값**을 줄 것.
   값이 다르면 계획이 달라져 양팔에 서로 다른 창이 적용되고 손목 방향이 어긋난다.

🔴 손목 카메라 장착 후에는 케이블이 추가되므로 1~5 를 **다시** 돌릴 것 (구축기록 §5-5).
"""

import argparse
import json
import time
from pathlib import Path

from lerobot.motors import Motor, MotorNormMode
from lerobot.motors.feetech import FeetechMotorsBus

MOTOR = "wrist_roll"
MOTOR_ID = 5
RESOLUTION = 4096
CENTER = 2048
DEFAULT_MARGIN = 100     # 측정 끝단에서 이만큼 안쪽에 한계 (≈ 8.8°)
MAX_HALF = 1024          # 기본 상한 ±90°. 그리퍼가 180° 대칭이라 파지 방향 도달에는 충분하다.
                         # 다만 중립 기준으로는 한쪽이 좁아질 수 있어 --max-half 로 넓힐 수 있다.
HARD_MAX_HALF = 1800     # 안전 천장 ±158°. 이보다 넓으면 창이 보고 좌표 불연속(0/4095)에
                         # 가까워진다. 물리 한계는 2047 이지만 여유를 둔다.
MIN_HALF = 400           # 이보다 좁으면 개선이 없는 것으로 본다 (현행 ±400)

BASE = Path(__file__).resolve().parent.parent
CACHE_BASE = Path.home() / ".cache" / "huggingface" / "lerobot" / "calibration"

# 🔴 정렬 영점은 **원시 엔코더 값**으로 따로 보관한다.
#    창을 영점 비대칭으로 잡은 뒤로는 "창 중점 = 영점" 이 성립하지 않는다.
#    한 번 적용한 뒤 다시 측정하면 기준이 창 중점으로 밀려 양팔 정렬이 깨졌다
#    (2026-07-29 실제 발생: 팔로워 기준이 raw 576 → 105 로 471 카운트 어긋남).
#    원시 영점은 서보 혼을 분해하지 않는 한 불변이므로 파일에 고정한다.
ZERO_PATH = BASE / "calibration" / "wrist_zero.json"
ARMS = {
    "follower": {
        "cache": CACHE_BASE / "robots" / "so_follower" / "follower_arm.json",
        "backup": BASE / "calibration" / "follower_arm.json",
        "home": BASE / "calibration" / "follower_home.json",
        "measure": Path(__file__).resolve().parent / ".wrist_widen_follower.json",
    },
    "leader": {
        "cache": CACHE_BASE / "teleoperators" / "so_leader" / "leader_arm.json",
        "backup": BASE / "calibration" / "leader_arm.json",
        "home": None,  # 리더는 토크가 항상 꺼져 있어 기준 자세 파일을 쓰지 않는다
        "measure": Path(__file__).resolve().parent / ".wrist_widen_leader.json",
    },
}
DEFAULT_PORTS = {"follower": "COM3", "leader": "COM5"}


def _bus(port: str) -> FeetechMotorsBus:
    bus = FeetechMotorsBus(
        port=port, motors={MOTOR: Motor(MOTOR_ID, "sts3215", MotorNormMode.RANGE_M100_100)}
    )
    bus.connect(handshake=False)
    return bus


def _unwrap(trace: list[int]) -> list[int]:
    """0/4095 를 넘나드는 보고값을 연속 좌표로 편다."""
    out, offset = [], 0
    for i, p in enumerate(trace):
        if i:
            d = p - trace[i - 1]
            if d > RESOLUTION // 2:
                offset -= RESOLUTION
            elif d < -(RESOLUTION // 2):
                offset += RESOLUTION
        out.append(p + offset)
    return out


def _wrap_offset(v: int) -> int:
    """Homing_Offset 은 부호+크기 12비트 → ±2047. offset±4096 은 등가."""
    v = ((v + 2048) % RESOLUTION) - 2048
    return -2047 if v == -2048 else v


def _deg(counts: float) -> float:
    return counts * 360 / RESOLUTION


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def zero_raw(arm: str) -> int:
    """정렬 영점의 원시 엔코더 값 (물리 상수)."""
    if not ZERO_PATH.is_file():
        raise FileNotFoundError(
            f"영점 파일이 없다: {ZERO_PATH}\n"
            "   양팔 그리퍼 방향을 맞춘 뒤 각 팔의 (Present + Homing_Offset) % 4096 을 기록할 것.")
    return int(_load(ZERO_PATH)[arm])


def home_present(default: int) -> int:
    """follower_home.json 에 저장된 wrist_roll 기본위치 (현재 프레임의 보고 좌표).

    프로파일·추종 시험이 끝난 뒤 팔을 세워 둘 자세다. 카메라 장착(2026-07-29) 후
    기본위치가 영점 −44° 로 정해졌으므로, 영점(2048)이 아니라 여기로 복귀해야
    check_home.py 기준과 일치한 상태로 끝난다."""
    path = ARMS["follower"]["home"]
    if path is not None and path.is_file():
        v = _load(path).get(MOTOR)
        if v is not None:
            return int(v)
    return default


def measure(arm: str, port: str, seconds: float) -> int:
    paths = ARMS[arm]
    calib = _load(paths["cache"])[MOTOR]

    bus = _bus(port)
    try:
        bus.disable_torque()
        homing = bus.read("Homing_Offset", MOTOR, normalize=False)
        if homing != calib["homing_offset"]:
            print(f"🔴 서보 Homing({homing}) 과 JSON({calib['homing_offset']}) 이 다르다.")
            print("   프레임이 어긋난 상태다. 먼저 원인을 확인할 것.")
            return 1
        # 영점은 원시 기준으로 보관하므로 현재 Homing 에 맞춰 보고 좌표로 환산한다.
        zero_present = (zero_raw(arm) - homing) % RESOLUTION
        print(f"⚠ [{arm}] 토크를 껐다. 영점(원시 {zero_raw(arm)} = present {zero_present}) 기준으로 측정한다.")
        print(f"{seconds:.0f}초 동안 손목을 **손으로 좌우 끝까지 천천히, 왕복** 돌릴 것.")
        print("  배선이 팽팽해지기 시작하는 지점까지만. 무리하게 밀지 말 것.\n")
        trace = []
        start = time.perf_counter()
        while (elapsed := time.perf_counter() - start) < seconds:
            trace.append(bus.read("Present_Position", MOTOR, normalize=False))
            time.sleep(0.05)
    finally:
        bus.disconnect(disable_torque=False)

    uw = _unwrap(trace)
    # 영점의 언랩 좌표 = 시작 샘플과 같은 바퀴에 있는 등가값
    zero_uw = zero_present + round((uw[0] - zero_present) / RESOLUTION) * RESOLUTION
    minus = zero_uw - min(uw)
    plus = max(uw) - zero_uw

    print(f"기록 종료 — {elapsed:.0f}초, {len(trace)} 샘플")
    print(f"영점 기준 가동: −{minus} ~ +{plus} 카운트 (−{_deg(minus):.0f}° ~ +{_deg(plus):.0f}°)")

    if minus <= 0 or plus <= 0:
        print("🔴 영점의 한쪽 방향이 측정되지 않았다. 양방향 모두 돌렸는지 확인할 것.")
        return 1

    paths["measure"].write_text(
        json.dumps({"minus": minus, "plus": plus}, indent=4), encoding="utf-8")
    print(f"저장: {paths['measure']}")
    other = "leader" if arm == "follower" else "follower"
    if ARMS[other]["measure"].is_file():
        print("\n양팔 측정 완료. 다음: --plan")
    else:
        print(f"\n다음: --measure --arm {other} --port {DEFAULT_PORTS[other]}")
    return 0


def compute_plan(margin: int, max_half: int = MAX_HALF) -> dict | None:
    for arm in ARMS:
        if not ARMS[arm]["measure"].is_file():
            print(f"❌ {arm} 측정값이 없다. 먼저 --measure --arm {arm} 을 실행할 것.")
            return None
    m = {arm: _load(ARMS[arm]["measure"]) for arm in ARMS}

    # 양팔 교집합 (영점 기준 오프셋). 좁은 쪽이 양팔 공통 한계다.
    lo_off = -min(v["minus"] for v in m.values()) + margin
    hi_off = min(v["plus"] for v in m.values()) - margin
    if hi_off <= lo_off:
        print("🔴 여유를 빼면 남는 범위가 없다. --margin 을 줄이거나 다시 측정할 것.")
        return None

    avail = (hi_off - lo_off) // 2
    half = min(avail, max_half)
    if half < MIN_HALF:
        print(f"🔴 반폭 {half}카운트 — 현행(±400)보다 넓지 않다. 측정을 다시 볼 것.")
        return None

    # 창 중점을 **중립(정렬 영점)에 최대한 가깝게** 둔다.
    #
    # 상한(max_half)에 걸려 교집합보다 좁은 창을 쓸 때, 중점을 교집합 중점에 두면
    # 중립이 창 한쪽에 몰린다. 2026-07-29 실측에서 중립 기준 −140°/+39° 로 갈렸다 —
    # 총 폭은 180° 인데 한쪽으로는 39° 밖에 못 도는 셈이라 조작이 답답해진다.
    # 중립을 창 안쪽으로 당기면 같은 폭으로 −119°/+61° 가 된다.
    #
    # 창은 반드시 교집합 안에 들어가야 하므로 중점의 허용 구간은 아래와 같다.
    c_lo, c_hi = lo_off + half, hi_off - half
    center_off = max(c_lo, min(c_hi, 0))   # 0(중립)을 허용 구간으로 클램프

    plan = {
        "margin": margin, "half": half, "center_off": center_off,
        "avail": avail, "max_half": max_half,
        "range_min": CENTER - half, "range_max": CENTER + half,
        "zero_present": CENTER - center_off,   # 정렬된 그리퍼 방향의 새 보고값
        "arms": {},
    }
    for arm, v in m.items():
        z = zero_raw(arm)
        plan["arms"][arm] = {
            "zero_actual": z, "homing": _wrap_offset((z + center_off) - CENTER),
            "minus": v["minus"], "plus": v["plus"]}
    return plan


def show_plan(margin: int, max_half: int = MAX_HALF) -> int:
    plan = compute_plan(margin, max_half)
    if plan is None:
        return 1
    half, span = plan["half"], plan["half"] * 2
    c = plan["center_off"]
    print(f"창 폭   ±{half}카운트 = ±{_deg(half):.0f}°  (총 {_deg(span):.0f}°)")
    print(f"한계    present {plan['range_min']} ~ {plan['range_max']}")
    print(f"영점    present {plan['zero_present']} (정렬된 그리퍼 방향)")
    # 조작 체감을 좌우하는 값이다 — 중립 자세에서 어느 쪽으로 얼마나 돌릴 수 있는가.
    print(f"중립에서 회전 가능: {_deg(c - half):+.0f}° ~ {_deg(c + half):+.0f}°"
          + ("  ✅ 대칭" if abs(c) < 60 else f"  ⚠ 한쪽으로 치우침 (중점 {_deg(c):+.0f}°)") + "\n")
    for arm, a in plan["arms"].items():
        print(f"[{arm:<8}] 영점 원시 {a['zero_actual']:>4} → Homing_Offset {a['homing']:>6}"
              f"   (실측 −{a['minus']}/+{a['plus']})")

    # 보고 좌표의 불연속은 present 0/4095 에 있다. 창이 거기서 얼마나 떨어져 있는지.
    print(f"\n불연속(present 0/4095)까지 여유: {plan['range_min']}카운트 "
          f"({_deg(plan['range_min']):.0f}°) — 창 안에 불연속 없음 ✅")
    if _deg(span) < 180:
        gap = 180 - _deg(span)
        print(f"\n⚠ 총 {_deg(span):.0f}° 로 180° 에 {gap:.0f}° 모자란다. 그리퍼가 180° 대칭이므로"
              f" 도달 불가한 방향이 {gap:.0f}° 폭으로 남는다.")
    elif plan["half"] >= plan["avail"]:
        print(f"\n실측이 창을 정한다 (상한 ±{_deg(plan['max_half']):.0f}° 에 닿지 않음).")
    else:
        print(f"\n상한 ±{_deg(plan['max_half']):.0f}° 이 창을 정한다."
              f" 실측만으로는 ±{_deg(plan['avail']):.0f}° 까지 가능하다"
              f" — 더 넓히려면 --max-half {min(plan['avail'], HARD_MAX_HALF)}")
    print("\n적용: --apply --arm follower  →  --apply --arm leader")
    return 0


def apply(arm: str, port: str, margin: int, max_half: int = MAX_HALF) -> int:
    plan = compute_plan(margin, max_half)
    if plan is None:
        return 1
    homing = plan["arms"][arm]["homing"]
    lo, hi = plan["range_min"], plan["range_max"]
    paths = ARMS[arm]
    # 기준 자세 재표현용 — JSON 을 갱신하기 전에 이전 프레임의 Homing 을 보관한다.
    old_homing = _load(paths["cache"])[MOTOR]["homing_offset"]

    bus = _bus(port)
    try:
        bus.disable_torque()
        bus.write("Homing_Offset", MOTOR, homing, normalize=False)
        bus.write("Min_Position_Limit", MOTOR, lo, normalize=False)
        bus.write("Max_Position_Limit", MOTOR, hi, normalize=False)
        got = {
            "Homing_Offset": bus.read("Homing_Offset", MOTOR, normalize=False),
            "Min_Position_Limit": bus.read("Min_Position_Limit", MOTOR, normalize=False),
            "Max_Position_Limit": bus.read("Max_Position_Limit", MOTOR, normalize=False),
        }
        pos = bus.read("Present_Position", MOTOR, normalize=False)
        bus.disable_torque()
        torque = bus.read("Torque_Enable", MOTOR, normalize=False)
    finally:
        bus.disconnect(disable_torque=False)

    ok = True
    print(f"[{arm}] 서보 기록 결과")
    for k, v in {"Homing_Offset": homing, "Min_Position_Limit": lo,
                 "Max_Position_Limit": hi}.items():
        mark = "✅" if got[k] == v else f"🔴 기대 {v}"
        ok = ok and got[k] == v
        print(f"  {k:<22}{got[k]:>8}   {mark}")
    print(f"  {'Present_Position':<22}{pos:>8}   (영점에 있다면 ≈ {plan['zero_present']})")
    print(f"  {'Torque_Enable':<22}{torque:>8}   "
          + ("✅ 꺼짐" if not torque else "🔴 켜짐 — 전원 차단할 것"))
    if not ok or torque:
        return 1

    # is_calibrated() 가 JSON 과 서보를 대조하므로 양쪽을 반드시 함께 갱신한다.
    for key in ("cache", "backup"):
        calib = _load(paths[key])
        calib[MOTOR].update(homing_offset=homing, range_min=lo, range_max=hi)
        paths[key].write_text(json.dumps(calib, indent=4), encoding="utf-8")
        print(f"✅ 갱신: {paths[key]}")

    # 좌표계가 바뀌어도 기준 자세의 **물리 방향**은 유지한다 (2026-07-29 변경).
    # 손목 카메라 장착 후 기본위치가 정렬 영점이 아니게 되었으므로(영점 −44°),
    # 예전처럼 영점으로 스냅하면 사용자가 정한 기본위치가 지워진다.
    # 원시값(present + homing)을 보존해 새 프레임으로 재표현한다.
    if paths["home"] is not None:
        home = _load(paths["home"])
        old = home.get(MOTOR)
        if old is None:
            new_home = plan["zero_present"]
        else:
            new_home = ((old + old_homing) - homing) % RESOLUTION
            if not (lo + 15 <= new_home <= hi - 15):
                print(f"⚠ 기준 자세(present {new_home})가 새 창 밖이다 — 영점으로 대체한다. "
                      "원하는 자세에서 check_home.py --save 로 다시 저장할 것.")
                new_home = plan["zero_present"]
        home[MOTOR] = new_home
        paths["home"].write_text(json.dumps(home, indent=4), encoding="utf-8")
        print(f"✅ 기준 자세 갱신: {MOTOR} {old} → {new_home}")

    other = "leader" if arm == "follower" else "follower"
    done = "적용됨" if arm == "follower" else ""
    print(f"\n다음: --apply --arm {other}" if not done or arm == "follower"
          else "\n다음: --goal-test")
    return 0


TEST_VELOCITY = 400   # 카운트/초 — 저속. 창 전체(2048카운트) 이동에 약 5초가 걸린다.
SETTLE_TIMEOUT = 8.0
SETTLE_TOL = 30       # 이 안에 들어오면 도착으로 본다 (≈ 2.6°)
LOAD_ABORT = 600      # 최대 1000. 이 이상이면 즉시 중단한다


def _settle(bus, goal: int) -> tuple[int, int, int, float, str]:
    """goal 을 쓰고 **멈출 때까지** 관찰한다 → (위치, 부하, 최대부하, 소요, 상태).

    고정 시간 대기는 쓰지 않는다. 저속 설정에서는 아직 이동 중인 것을
    '추종 실패' 로 오판하기 때문이다 (2026-07-29: 960카운트 이동을 1.5초에 판정해 오탐).
    """
    bus.write("Goal_Position", MOTOR, goal, normalize=False)  # 토크 자동 인가
    t0 = time.perf_counter()
    last, still, peak = None, 0, 0
    p = load = 0
    while (el := time.perf_counter() - t0) < SETTLE_TIMEOUT:
        time.sleep(0.2)
        p = bus.read("Present_Position", MOTOR, normalize=False)
        load = bus.read("Present_Load", MOTOR, normalize=False)
        peak = max(peak, abs(load))
        if abs(load) >= LOAD_ABORT:
            return p, load, peak, el, "overload"
        if abs(p - goal) <= SETTLE_TOL:
            return p, load, peak, el, "ok"
        # 목표에 못 미쳤는데 더 이상 움직이지 않으면 실제로 막힌 것이다.
        if last is not None and abs(p - last) <= 3:
            still += 1
            if still >= 3:
                return p, load, peak, el, "stalled"
        else:
            still = 0
        last = p
    return p, load, peak, el, "timeout"


def profile(port: str, margin: int, max_half: int, step: int = 200) -> int:
    """중립에서 바깥으로 조금씩 나가며 **어느 각도부터 배선이 뻣뻣해지는지** 잰다.

    왜 필요한가:
        창 끝까지 한 번에 이동하면 가속 성분과 배선 저항이 섞여 최대 부하만 보인다.
        작은 걸음으로 나가면 각 지점의 **정착 부하**를 볼 수 있고, 그것이 곧
        "그 각도를 유지하는 데 드는 힘" 이다. 데이터 수집은 이 자세를 수백 번 반복하므로
        순간 최대치보다 정착 부하가 중요하다.

    읽는 법:
        정착 부하가 완만하면 그 구간은 안전하다.
        급격히 꺾이는 지점 **안쪽**에 창을 두는 것이 좋다.
    """
    plan = compute_plan(margin, max_half)
    if plan is None:
        return 1
    half = plan["half"]

    print(f"⚠ 손목이 중립에서 ±{_deg(half):.0f}° 까지 {step}카운트({_deg(step):.0f}°)씩 나간다.")
    print("  주변에서 손을 치울 것.\n")

    bus = _bus(port)
    rows: list[tuple[int, int, int, str]] = []
    try:
        bus.write("Goal_Velocity", MOTOR, TEST_VELOCITY, normalize=False)
        bus.write("Acceleration", MOTOR, 30, normalize=False)
        print(f"  {'각도':>7}{'goal':>7}{'present':>9}{'정착부하':>10}{'최대부하':>10}   판정")
        print("  " + "-" * 56)
        for sign in (+1, -1):
            for k in range(1, half // step + 2):
                off = min(k * step, half)
                t = CENTER + sign * off
                p, load, peak, _, state = _settle(bus, t)
                mag = abs(load)
                mark = "✅" if mag < 200 else ("⚠ 뻣뻣" if mag < 400 else "🔴 과다")
                if state != "ok":
                    mark = f"🔴 {state}"
                print(f"  {_deg(sign * off):>+6.0f}°{t:>7}{p:>9}{load:>+10}{peak:>10}   {mark}")
                rows.append((sign * off, load, peak, state))
                if state != "ok" or mag >= 500:
                    break
                if off >= half:
                    break
            _settle(bus, CENTER)   # 다음 방향 전에 중립으로 복귀
        # 끝나면 영점이 아니라 **저장된 기본위치** 에 세워 둔다 (2026-07-30)
        home_p = max(CENTER - half + 15, min(CENTER + half - 15, home_present(CENTER)))
        _settle(bus, home_p)
        print(f"\n기본위치 복귀: present {home_p}")
    finally:
        try:
            bus.write("Goal_Velocity", MOTOR, 0, normalize=False)
            bus.write("Acceleration", MOTOR, 254, normalize=False)
            bus.write("Torque_Enable", MOTOR, 0, normalize=False)
            print("\n토크 해제 " + ("✅" if not bus.read("Torque_Enable", MOTOR, normalize=False)
                                   else "🔴 실패 — 전원 차단할 것"))
        except Exception as e:
            print(f"\n🔴 토크 해제 실패: {e} — 전원을 차단할 것.")
        bus.disconnect(disable_torque=False)

    safe = [off for off, load, _, state in rows if state == "ok" and abs(load) < 200]
    if safe:
        lo, hi = min(safe), max(safe)
        inner = min(abs(lo), abs(hi))
        print(f"\n정착 부하 200 미만 구간: {_deg(lo):+.0f}° ~ {_deg(hi):+.0f}°")
        print(f"→ 양방향 모두 안전한 대칭 폭: ±{_deg(inner):.0f}°  (--max-half {inner})")
    return 0


def goal_test(port: str, margin: int, max_half: int = MAX_HALF) -> int:
    """새 프레임에서 팔로워 손목이 창 전 구간을 추종하는지 저속 확인한다 (움직임 발생)."""
    plan = compute_plan(margin, max_half)
    if plan is None:
        return 1
    half = plan["half"]
    # 창 **끝단**까지 시험한다. 텔레옵이 실제로 명령할 수 있는 최대치가 거기이므로,
    # 안쪽만 확인하고 통과시키면 정작 위험한 구간을 못 본다.
    # 15카운트만 안쪽으로 들여 위치 한계 클램프와 판정 허용오차가 겹치지 않게 한다.
    reach = half - 15
    # 마지막은 영점이 아니라 **저장된 기본위치** 에 세워 둔다 (2026-07-30)
    home_p = max(plan["range_min"] + 15, min(plan["range_max"] - 15,
                                             home_present(plan["zero_present"])))
    targets = [CENTER, CENTER - reach, CENTER, CENTER + reach, CENTER, home_p]

    print(f"⚠ 손목이 저속으로 ±{reach}카운트(±{_deg(reach):.0f}°) 왕복한 뒤 기본위치로 돌아온다.")
    print("  주변에서 손을 치울 것. 이상 시 즉시 전원을 뺄 것.\n")

    bus = _bus(port)
    failed = False
    try:
        # 저속·저가속으로 부드럽게 (기본 254 는 §5-7 폭주 때처럼 급격하다)
        bus.write("Goal_Velocity", MOTOR, TEST_VELOCITY, normalize=False)
        bus.write("Acceleration", MOTOR, 30, normalize=False)
        print(f"  {'goal':>6}{'present':>9}{'오차':>7}{'부하':>7}{'최대부하':>9}{'소요':>7}   판정")
        print("  " + "-" * 60)
        for t in targets:
            p, load, peak, el, state = _settle(bus, t)
            err = p - t
            verdict = {
                "ok": "✅",
                "stalled": "🔴 막힘 — 배선 걸림",
                "overload": "🔴 부하 과다",
                "timeout": "🔴 시간 초과",
            }[state]
            print(f"  {t:>6}{p:>9}{err:>+7}{load:>+7}{peak:>9}{el:>6.1f}s   {verdict}")
            if state != "ok":
                failed = True
                break
    finally:
        try:
            # 시험용 저속 설정을 되돌린다 (Goal_Velocity 0 = 제한 없음, 가속 기본 254).
            bus.write("Goal_Velocity", MOTOR, 0, normalize=False)
            bus.write("Acceleration", MOTOR, 254, normalize=False)
            bus.write("Torque_Enable", MOTOR, 0, normalize=False)
            t_state = bus.read("Torque_Enable", MOTOR, normalize=False)
            print("\n토크 해제 " + ("✅" if not t_state else "🔴 실패 — 전원 차단할 것"))
        except Exception as e:
            print(f"\n🔴 토크 해제 실패: {e} — 전원을 차단할 것.")
        bus.disconnect(disable_torque=False)

    if failed:
        print("\n🔴 새 프레임에서 추종이 불안정하다. 텔레옵 금지. 결과를 보고 원인을 볼 것.")
        return 1
    print("\n✅ 창 전 구간 추종 정상. teleop.ps1 로 최종 확인할 것.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--measure", action="store_true")
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--goal-test", action="store_true")
    parser.add_argument("--profile", action="store_true",
                        help="중립에서 조금씩 나가며 각 각도의 정착 부하를 잰다 (움직임 발생)")
    parser.add_argument("--arm", choices=list(ARMS))
    parser.add_argument("--port")
    parser.add_argument("--seconds", type=float, default=45.0)
    parser.add_argument("--margin", type=int, default=DEFAULT_MARGIN,
                        help=f"측정 끝단에서 안쪽으로 둘 여유 카운트 (기본 {DEFAULT_MARGIN})")
    parser.add_argument("--max-half", type=int, default=MAX_HALF,
                        help=f"창 반폭 상한 카운트 (기본 {MAX_HALF} = ±90°, 최대 {HARD_MAX_HALF})")
    args = parser.parse_args()

    max_half = min(args.max_half, HARD_MAX_HALF)
    if args.max_half > HARD_MAX_HALF:
        print(f"⚠ --max-half 를 안전 천장 {HARD_MAX_HALF} 로 낮춘다 "
              f"(창이 보고 좌표 불연속에 너무 가까워진다).\n")

    if args.plan:
        return show_plan(args.margin, max_half)
    if args.profile:
        return profile(args.port or DEFAULT_PORTS["follower"], args.margin, max_half)
    if args.goal_test:
        return goal_test(args.port or DEFAULT_PORTS["follower"], args.margin, max_half)
    if args.measure or args.apply:
        if not args.arm:
            print("❌ --arm follower|leader 를 지정할 것.")
            return 1
        port = args.port or DEFAULT_PORTS[args.arm]
        if args.measure:
            return measure(args.arm, port, args.seconds)
        return apply(args.arm, port, args.margin, max_half)
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
