"""🔴 사용 중단 (2026-07-29) — `widen_wrist_roll.py` 를 쓸 것.

이 스크립트는 위치 한계를 **원시 엔코더 기준**이라 가정하고, 창이 원시 0 을
가로지르면 거부한다 (`--recenter` 의 래핑 가드). **그 가정이 틀렸다.**

팔로워 6축을 직접 읽어보면 shoulder_pan·shoulder_lift·elbow_flex·wrist_flex·gripper
**5축 모두** 원시 0 을 가로지르는 창으로 정상 동작 중이고, 서보 Min/Max_Position_Limit 이
JSON range_min/max(= Present 기준 측정값)와 정확히 일치한다.
→ 한계는 **보고 좌표(Present = 원시 − Homing_Offset) 기준**이다.

그 잘못된 가드 때문에 손목 창이 ±35°(70°) 로 묶였다. 자세한 경위는 구축기록 §5-8.
아래 원문은 기록으로만 남긴다.

---

팔로워 wrist_roll 의 안전 가동 범위를 측정하고 서보 위치 한계로 굳힌다.

## 왜 필요한가 (2026-07-28 실측)

팔로워 6축의 레지스터를 비교하면 wrist_roll 만 다음이 다르다.

    다른 5축   Min/Max_Position_Limit = 캘리브레이션된 기계 범위 (예: 1151~3856)
    wrist_roll Min/Max_Position_Limit = 0~4095   ← 아무것도 막지 않음

연속 회전축이라 LeRobot 이 범위를 0~4095 로 고정하기 때문이다.
그리고 `Goal_Position` 은 RAM 이라 **전원을 뺐다 넣으면 0 으로 초기화**된다.

    전원 재투입 → Goal = 0 → 토크 인가 → 전 축이 위치 0 으로 이동 시도
      다른 5축   : Min_Position_Limit 이 막아 기계 범위 안에서만 움직임
      wrist_roll : 막는 것이 없어 355도 회전 시도 → 배선이 버티지 못함 → 과부하

다른 축이 멀쩡한 것은 서보가 튼튼해서가 아니라 **한계가 걸려 있기 때문**이다.

## 무엇을 하는가

1. `--measure` : 토크를 끄고 손으로 돌리는 동안 실제 가동 범위를 기록한다.
                 보고값이 0/4095 를 넘나들어도 **언랩(unwrap)** 해서 참 범위를 구한다.
2. `--apply`   : 측정 결과로 아래를 함께 갱신한다.
                 - `Homing_Offset`  → 가동 범위 중심이 2048 을 가리키도록 (경계 회피)
                 - `Min/Max_Position_Limit` → 안전 범위로 제한
                 - 캘리브레이션 JSON 2곳 (`is_calibrated()` 가 서보와 대조하므로 필수)
                 - `follower_home.json` 의 wrist_roll (좌표계가 바뀌므로)

사용법:
    python tools/limit_wrist_roll.py --port COM3 --measure --seconds 60
    python tools/limit_wrist_roll.py --port COM3 --apply
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

# 측정된 양 끝에서 이만큼 안쪽으로 한계를 잡는다. 배선이 팽팽해지기 시작한 지점이
# 측정 끝이므로, 거기에 딱 붙이지 않고 여유를 둔다. (100 카운트 ≈ 8.8도)
INWARD_MARGIN = 100
MIN_USABLE_SPAN = 400  # 이보다 좁으면 측정이 부실한 것으로 본다

BASE = Path(__file__).resolve().parent.parent
MEASURE_PATH = Path(__file__).resolve().parent / ".wrist_roll_measured.json"
HOME_PATH = BASE / "calibration" / "follower_home.json"
BACKUP_CALIB = BASE / "calibration" / "follower_arm.json"
CACHE_CALIB = (
    Path.home() / ".cache" / "huggingface" / "lerobot" / "calibration"
    / "robots" / "so_follower" / "follower_arm.json"
)

# 팔로워는 robot, 리더는 teleoperator 로 분류되어 캐시 경로가 갈린다.
CACHE_BASE = Path.home() / ".cache" / "huggingface" / "lerobot" / "calibration"
ARMS = {
    "follower": {
        "cache": CACHE_BASE / "robots" / "so_follower" / "follower_arm.json",
        "backup": BASE / "calibration" / "follower_arm.json",
        "home": BASE / "calibration" / "follower_home.json",
    },
    "leader": {
        "cache": CACHE_BASE / "teleoperators" / "so_leader" / "leader_arm.json",
        "backup": BASE / "calibration" / "leader_arm.json",
        "home": None,  # 리더는 토크가 항상 꺼져 있어 기준 자세 파일을 쓰지 않는다
    },
}


def _bus(port: str) -> FeetechMotorsBus:
    bus = FeetechMotorsBus(
        port=port, motors={MOTOR: Motor(MOTOR_ID, "sts3215", MotorNormMode.RANGE_M100_100)}
    )
    bus.connect(handshake=False)
    return bus


def _unwrap(trace: list[int]) -> list[int]:
    """보고 위치가 0/4095 를 넘나들며 감기는 것을 펴서 연속값으로 만든다.

    한 샘플 만에 반 바퀴(2048) 이상 변했다면 물리적 이동이 아니라 감김이다.
    """
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
    """Homing_Offset 은 부호+크기 12비트라 ±2047 이 한계.

    서보가 4096 모듈로로 계산하므로 offset 과 offset±4096 은 등가다.
    """
    v = ((v + 2048) % RESOLUTION) - 2048
    return -2047 if v == -2048 else v


def measure(port: str, seconds: float) -> int:
    bus = _bus(port)
    try:
        bus.disable_torque()
        homing = bus.read("Homing_Offset", MOTOR, normalize=False)
        print("⚠ 토크를 껐다.")
        print(f"{seconds:.0f}초 동안 팔로워 손목을 **손으로 좌우 끝까지 천천히** 돌릴 것.")
        print("  배선이 팽팽해지기 시작하는 지점까지만. 무리하게 밀지 말 것.\n")

        trace = []
        start = time.perf_counter()
        while (elapsed := time.perf_counter() - start) < seconds:
            trace.append(bus.read("Present_Position", MOTOR, normalize=False))
            time.sleep(0.05)
    finally:
        bus.disconnect(disable_torque=False)

    uw = _unwrap(trace)
    lo, hi = min(uw), max(uw)
    span = hi - lo
    print(f"기록 종료 — {elapsed:.0f}초, {len(trace)} 샘플")
    print(f"보고값 범위(언랩 전) : {min(trace)} ~ {max(trace)}")
    print(f"참 가동 범위(언랩 후) : {lo} ~ {hi}   span {span}  ({span * 360 / RESOLUTION:.0f}°)\n")

    if span < MIN_USABLE_SPAN:
        print(f"🔴 범위가 너무 좁다 ({span}). 손목을 양쪽 끝까지 돌렸는지 확인하고 다시 측정할 것.")
        return 1

    # 언랩된 좌표의 중심이 실제 엔코더로 어디인지 구한다.
    mid_reported = (lo + hi) // 2
    actual_mid = (mid_reported + homing) % RESOLUTION

    new_homing = _wrap_offset(actual_mid - CENTER)
    half = span // 2 - INWARD_MARGIN
    if half <= 0:
        print(f"🔴 여유({INWARD_MARGIN})를 빼면 남는 범위가 없다. 더 넓게 측정할 것.")
        return 1
    new_min, new_max = CENTER - half, CENTER + half

    result = {
        "measured_lo": lo, "measured_hi": hi, "span": span,
        "old_homing_offset": homing, "new_homing_offset": new_homing,
        "new_range_min": new_min, "new_range_max": new_max,
    }
    MEASURE_PATH.write_text(json.dumps(result, indent=4), encoding="utf-8")

    print("=== 적용 예정값 ===")
    print(f"  Homing_Offset        {homing}  →  {new_homing}")
    print(f"  Min_Position_Limit   0     →  {new_min}")
    print(f"  Max_Position_Limit   4095  →  {new_max}")
    print(f"  → 중심 {CENTER}, 가동 폭 {2 * half} ({2 * half * 360 / RESOLUTION:.0f}°)")
    print(f"  → 측정 끝단에서 {INWARD_MARGIN} 카운트({INWARD_MARGIN * 360 / RESOLUTION:.0f}°) 안쪽에 한계를 둔다")
    print(f"\n저장: {MEASURE_PATH}")
    print("\n적용하려면 --apply 를 실행할 것.")
    return 0


def apply(port: str) -> int:
    if not MEASURE_PATH.is_file():
        print(f"❌ 측정값이 없다. 먼저 --measure 를 실행할 것. ({MEASURE_PATH})")
        return 1
    r = json.loads(MEASURE_PATH.read_text(encoding="utf-8"))

    bus = _bus(port)
    try:
        bus.disable_torque()
        bus.write("Homing_Offset", MOTOR, r["new_homing_offset"], normalize=False)
        bus.write("Min_Position_Limit", MOTOR, r["new_range_min"], normalize=False)
        bus.write("Max_Position_Limit", MOTOR, r["new_range_max"], normalize=False)

        got = {
            "Homing_Offset": bus.read("Homing_Offset", MOTOR, normalize=False),
            "Min_Position_Limit": bus.read("Min_Position_Limit", MOTOR, normalize=False),
            "Max_Position_Limit": bus.read("Max_Position_Limit", MOTOR, normalize=False),
        }
        pos = bus.read("Present_Position", MOTOR, normalize=False)
        # 이 스크립트는 위치를 움직이지 않는다. 토크가 켜져 있지 않은지 확인한다.
        bus.disable_torque()
        torque = bus.read("Torque_Enable", MOTOR, normalize=False)
    finally:
        bus.disconnect(disable_torque=False)

    expect = {
        "Homing_Offset": r["new_homing_offset"],
        "Min_Position_Limit": r["new_range_min"],
        "Max_Position_Limit": r["new_range_max"],
    }
    print("서보 기록 결과")
    ok = True
    for k, v in expect.items():
        mark = "✅" if got[k] == v else f"🔴 기대 {v}"
        if got[k] != v:
            ok = False
        print(f"  {k:<22}{got[k]:>8}   {mark}")
    print(f"  {'Present_Position':<22}{pos:>8}")
    print(f"  {'Torque_Enable':<22}{torque:>8}   " + ("✅ 꺼짐" if not torque else "🔴 켜짐 — 전원 차단할 것"))
    if not ok or torque:
        return 1

    # is_calibrated() 가 JSON 과 서보를 대조하므로 양쪽을 반드시 함께 갱신한다.
    for path in (CACHE_CALIB, BACKUP_CALIB):
        if not path.is_file():
            print(f"\n🔴 캘리브레이션 파일 없음: {path}")
            return 1
        calib = json.loads(path.read_text(encoding="utf-8"))
        calib[MOTOR]["homing_offset"] = r["new_homing_offset"]
        calib[MOTOR]["range_min"] = r["new_range_min"]
        calib[MOTOR]["range_max"] = r["new_range_max"]
        path.write_text(json.dumps(calib, indent=4), encoding="utf-8")
        print(f"\n✅ 갱신: {path}")

    # 좌표계가 바뀌었으므로 기준 자세의 wrist_roll 값도 새 프레임으로 옮긴다.
    if HOME_PATH.is_file():
        home = json.loads(HOME_PATH.read_text(encoding="utf-8"))
        old = home.get(MOTOR)
        home[MOTOR] = pos
        HOME_PATH.write_text(json.dumps(home, indent=4), encoding="utf-8")
        print(f"✅ 기준 자세 갱신: {MOTOR} {old} → {pos}")

    print("\n🎉 적용 완료. 이제 Goal 이 0 으로 초기화돼도 서보는 "
          f"{r['new_range_min']} 아래로 내려가지 못한다.")
    print("   확인: python tools/check_goal.py --port " + port)
    return 0


def zero_homing(port: str, half: int, arm: str = "follower") -> int:
    """`Homing_Offset` 을 0 으로 두고 **현재 위치 둘레**에 한계를 건다.

    ## 왜 이 방식인가 (2026-07-28 무접촉 실험으로 확정)

    아무도 건드리지 않은 15초 텔레옵에서 wrist_roll 이 혼자 127도 돌았다.

        Homing_Offset  -1454
        명령 Goal      보고 2044  ->  의도한 실제 위치  590
        실제 도달      보고 3499  ->  실제 위치        2045   (= 명령값과 거의 같음)

    서보가 `Goal_Position` 을 **실제 엔코더 값으로 해석**했다.
    `Homing_Offset` 이 `Present_Position` 에는 적용되는데 `Goal_Position` 에는 적용되지 않는다.
    → 오프셋 크기만큼 엉뚱한 곳으로 간다.

    실제로 오늘 유일하게 정상 동작한 설정은 `Homing_Offset = 4` 였다. 프레임이 일치해서다.

    ## 해결

    오프셋을 **0** 으로 두면 보고값 = 실제 엔코더가 되어 불일치가 원천적으로 사라진다.
    정규화는 `range_min~range_max` 기준이므로 **중심이 2048 일 필요가 없다.**
    현재 위치를 중심으로 창만 잡으면 된다.
    """
    bus = _bus(port)
    try:
        bus.disable_torque()
        cur = bus.read("Present_Position", MOTOR, normalize=False)
        homing = bus.read("Homing_Offset", MOTOR, normalize=False)
        actual = (cur + homing) % RESOLUTION

        new_min, new_max = actual - half, actual + half
        if new_min < 0 or new_max > RESOLUTION - 1:
            print(f"🔴 창 [{new_min}, {new_max}] 이 0~4095 를 벗어난다.")
            print(f"   현재 실제 엔코더 {actual} 가 끝에 너무 가깝다.")
            print(f"   손목을 손으로 돌려 실제 엔코더가 {half}~{RESOLUTION - 1 - half} 안에 오게 할 것.")
            return 1

        print(f"Homing_Offset 을 0 으로 두고 현재 위치를 중심으로 한계를 건다.\n")
        print(f"  현재 실제 엔코더     {actual}")
        print(f"  Homing_Offset        {homing}  →  0   (보고값 = 실제 엔코더)")
        print(f"  Min_Position_Limit   →  {new_min}")
        print(f"  Max_Position_Limit   →  {new_max}")
        print(f"  → 가동 폭 ±{half} ({half * 360 / RESOLUTION:.0f}°)\n")

        bus.write("Homing_Offset", MOTOR, 0, normalize=False)
        bus.write("Min_Position_Limit", MOTOR, new_min, normalize=False)
        bus.write("Max_Position_Limit", MOTOR, new_max, normalize=False)

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

    expect = {"Homing_Offset": 0, "Min_Position_Limit": new_min, "Max_Position_Limit": new_max}
    ok = True
    for k, v in expect.items():
        mark = "✅" if got[k] == v else f"🔴 기대 {v}"
        if got[k] != v:
            ok = False
        print(f"  {k:<22}{got[k]:>8}   {mark}")
    print(f"  {'Present_Position':<22}{pos:>8}   " + ("✅ = 실제 엔코더" if abs(pos - actual) <= 5 else "⚠"))
    print(f"  {'Torque_Enable':<22}{torque:>8}   " + ("✅ 꺼짐" if not torque else "🔴 켜짐 — 전원 차단"))
    if not ok or torque:
        return 1

    paths = ARMS[arm]
    for path in (paths["cache"], paths["backup"]):
        if not path.is_file():
            print(f"\n🔴 캘리브레이션 파일 없음: {path}")
            return 1
        calib = json.loads(path.read_text(encoding="utf-8"))
        calib[MOTOR]["homing_offset"] = 0
        calib[MOTOR]["range_min"] = new_min
        calib[MOTOR]["range_max"] = new_max
        path.write_text(json.dumps(calib, indent=4), encoding="utf-8")
        print(f"\n✅ 갱신: {path}")

    home_path = paths["home"]
    if home_path and home_path.is_file():
        home = json.loads(home_path.read_text(encoding="utf-8"))
        old = home.get(MOTOR)
        home[MOTOR] = pos
        home_path.write_text(json.dumps(home, indent=4), encoding="utf-8")
        print(f"✅ 기준 자세 갱신: {MOTOR} {old} → {pos}")

    print(f"\n🎉 {arm} 완료. 보고값과 실제 엔코더가 일치하므로 Goal 해석 불일치가 사라진다.")
    return 0


def recenter(port: str, half: int, arm: str = "follower") -> int:
    """**현재 손목 방향**을 중심(2048)으로 재정의하고 그 둘레로 한계를 건다.

    왜 중심이 중요한가:
        위치 한계만 걸어도 폭주는 막힌다. 그러나 **작동 지점이 한쪽 끝에 치우쳐 있으면**
        서보가 늘 배선을 당긴 상태로 일하게 되어 과부하가 계속 난다.
        (2026-07-28: 기준 자세가 상한에서 335카운트 거리에 있어 과부하가 반복됐다)
        → 배선이 가장 느슨한 지점을 중심으로 삼고, 거기서 대칭으로 움직인다.

    폭을 좁게 잡아도 손실이 거의 없다:
        하이브리드 데모에서 ACT 가 담당하는 **종이컵은 회전 대칭**이라 손목 회전이
        사실상 불필요하다. 블록은 프리셋 경로이고 정밀 IK 가 아닌 포즈테이블을 쓴다 (v5 5.5).

        ⚠ 위 두 문장은 **2026-07-28 당시의 기록**이다. 둘 다 지금은 사실이 아니다 —
          창은 7/29 에 ±157°(총 314°)로 넓혀졌고(구축기록 5-8), 블록도 ACT 로 바뀌었다
          (v5 5.2). 이 파일은 사용 중단이므로 여기서 현행 설계를 읽지 말 것.
    """
    bus = _bus(port)
    try:
        bus.disable_torque()
        cur = bus.read("Present_Position", MOTOR, normalize=False)
        homing = bus.read("Homing_Offset", MOTOR, normalize=False)

        actual = (cur + homing) % RESOLUTION
        new_homing = _wrap_offset(actual - CENTER)
        new_min, new_max = CENTER - half, CENTER + half

        # 🔴 한계는 서보 내부에서 **원시 엔코더 기준**으로 다뤄진다.
        #    보고 좌표로 만든 창이 원시 0 을 가로지르면 min > max 인 뒤집힌 범위가 되어
        #    서보가 제대로 처리하지 못한다 — 한계가 통째로 무의미해진다.
        #    (2026-07-28: 실제 중심이 126 이라 창이 3622~726 이 되었고, 손목이 180도 돌았다)
        a_min = (new_min + new_homing) % RESOLUTION
        a_max = (new_max + new_homing) % RESOLUTION
        if a_min > a_max:
            print(f"🔴 한계 창이 원시 엔코더 0 을 가로지른다 (실제 {a_min} ~ {a_max}).")
            print(f"   현재 손목의 실제 엔코더 위치가 {actual} 로 감김 지점에 너무 가깝다.")
            print(f"   → 손목을 **손으로 돌려** 실제 엔코더가 {CENTER} 부근이 되게 한 뒤 다시 실행할 것.")
            print(f"     지금 필요한 회전량: 약 {abs(actual - CENTER) * 360 / RESOLUTION:.0f}°")
            print("   그리퍼는 평행 2조라 180도 회전이 대칭이므로 방향을 바꿔도 기능 손실이 없다.")
            return 1

        print(f"현재 위치 {cur} 를 중심({CENTER})으로 재정의한다.")
        print(f"  실제 엔코더 {actual} → 한계 창 실제 {a_min} ~ {a_max} (가로지름 없음 ✅)\n")
        print(f"  Homing_Offset        {homing}  →  {new_homing}")
        print(f"  Min_Position_Limit   →  {new_min}")
        print(f"  Max_Position_Limit   →  {new_max}")
        print(f"  → 가동 폭 ±{half} ({half * 360 / RESOLUTION:.0f}°)\n")

        bus.write("Homing_Offset", MOTOR, new_homing, normalize=False)
        bus.write("Min_Position_Limit", MOTOR, new_min, normalize=False)
        bus.write("Max_Position_Limit", MOTOR, new_max, normalize=False)

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

    expect = {"Homing_Offset": new_homing,
              "Min_Position_Limit": new_min, "Max_Position_Limit": new_max}
    ok = True
    for k, v in expect.items():
        mark = "✅" if got[k] == v else f"🔴 기대 {v}"
        if got[k] != v:
            ok = False
        print(f"  {k:<22}{got[k]:>8}   {mark}")
    print(f"  {'Present_Position':<22}{pos:>8}   " + ("✅ 중심" if abs(pos - CENTER) <= 5 else "⚠"))
    print(f"  {'Torque_Enable':<22}{torque:>8}   " + ("✅ 꺼짐" if not torque else "🔴 켜짐 — 전원 차단"))
    if not ok or torque:
        return 1

    paths = ARMS[arm]
    for path in (paths["cache"], paths["backup"]):
        if not path.is_file():
            print(f"\n🔴 캘리브레이션 파일 없음: {path}")
            return 1
        calib = json.loads(path.read_text(encoding="utf-8"))
        calib[MOTOR]["homing_offset"] = new_homing
        calib[MOTOR]["range_min"] = new_min
        calib[MOTOR]["range_max"] = new_max
        path.write_text(json.dumps(calib, indent=4), encoding="utf-8")
        print(f"\n✅ 갱신: {path}")

    home_path = paths["home"]
    if home_path and home_path.is_file():
        home = json.loads(home_path.read_text(encoding="utf-8"))
        old = home.get(MOTOR)
        home[MOTOR] = pos
        home_path.write_text(json.dumps(home, indent=4), encoding="utf-8")
        print(f"✅ 기준 자세 갱신: {MOTOR} {old} → {pos}")

    print(f"\n🎉 {arm} 재중심 완료. 이 방향이 중심이고, 여기서 대칭으로만 움직인다.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True, help="팔로워 COM 포트 (예: COM3)")
    parser.add_argument("--measure", action="store_true", help="가동 범위 측정")
    parser.add_argument("--apply", action="store_true", help="측정 결과를 서보·JSON 에 반영")
    parser.add_argument("--recenter", action="store_true",
                        help="현재 위치를 2048 로 재정의하고 한계를 건다 (Homing_Offset 을 씀 — 권장하지 않음)")
    parser.add_argument("--zero-homing", action="store_true",
                        help="Homing_Offset=0 으로 두고 현재 위치 둘레에 한계를 건다 (권장)")
    parser.add_argument("--half-range", type=int, default=600,
                        help="--recenter 시 중심에서 좌우 허용 카운트 (기본 600 ≈ 53°)")
    parser.add_argument("--arm", choices=list(ARMS), default="follower",
                        help="--recenter 대상 팔. 리더·팔로워를 같은 폭으로 맞추면 1:1 대응이 된다")
    parser.add_argument("--seconds", type=float, default=60.0)
    args = parser.parse_args()

    if args.zero_homing:
        return zero_homing(args.port, args.half_range, args.arm)
    if args.recenter:
        return recenter(args.port, args.half_range, args.arm)
    if args.apply:
        return apply(args.port)
    if args.measure:
        return measure(args.port, args.seconds)
    parser.error("--measure / --apply / --recenter 중 하나가 필요하다")


if __name__ == "__main__":
    raise SystemExit(main())
