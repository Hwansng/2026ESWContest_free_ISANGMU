"""RPi 5 배포 준비 상태 점검 — 로봇 암이 정상 동작하는지 확인한다.

배포 시점의 RPi 5 는 노트북을 대체하는 호스트다. 팔로워암과 카메라가 RPi 에 직결되고,
RPi 가 ACT 정책을 추론해 서보를 제어한다. 이 스크립트는 그 준비가 끝났는지 점검한다.

점검 항목
  1. 환경        — Python / lerobot / torch (RPi 는 CPU 빌드가 정상)
  2. 시리얼 포트  — USB 버스 서보 어댑터 자동 탐색
  3. 서보 버스    — ID 1~6 응답, 위치/부하/온도/전압
  4. 캘리브레이션 — JSON 존재 + 서보 EPROM 값과 일치 여부
  5. 카메라       — 검출, 해상도/FPS 실측, MJPEG 여부
  6. (--move)     — 그리퍼 개폐로 쓰기 경로 검증 (가장 안전한 축)

기본은 읽기 전용이다. --move 를 주지 않으면 팔이 움직이지 않는다.

사용법 (RPi 5)
    python tools/rpi_check.py
    python tools/rpi_check.py --port /dev/ttyACM0
    python tools/rpi_check.py --move            # 그리퍼 개폐 테스트 포함
    python tools/rpi_check.py --move-all        # 6축 소폭 구동 (--delta 로 이동량 조절)
    python tools/rpi_check.py --skip-cameras    # camera_ros/libcamera 가 CSI 점유 중일 때
"""

import argparse
import json
import platform
import sys
import time
from pathlib import Path

OK = "  [OK]  "
FAIL = " [FAIL] "
WARN = " [WARN] "

MOTOR_SPEC = [
    ("shoulder_pan", 1, "Base"),
    ("shoulder_lift", 2, "Shoulder"),
    ("elbow_flex", 3, "Elbow"),
    ("wrist_flex", 4, "Wrist Pitch"),
    ("wrist_roll", 5, "Wrist Roll"),
    ("gripper", 6, "Gripper"),
]

CALIB_PATH = (
    Path.home()
    / ".cache/huggingface/lerobot/calibration/robots/so_follower/follower_arm.json"
)

failures: list[str] = []
warnings: list[str] = []


def section(title: str) -> None:
    print(f"\n{'=' * 62}\n{title}\n{'=' * 62}")


def check_env() -> None:
    section("1. 환경")
    print(f"{OK}플랫폼      : {platform.system()} {platform.machine()}")
    print(f"{OK}Python      : {sys.version.split()[0]}")

    try:
        import lerobot

        print(f"{OK}lerobot     : {lerobot.__version__}")
    except ImportError:
        print(f"{FAIL}lerobot 미설치 → pip install 'lerobot[feetech]'")
        failures.append("lerobot 미설치")
        return

    try:
        import torch

        dev = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"{OK}torch       : {torch.__version__} ({dev})")
        # RPi 5 는 GPU 가 없다. CPU 빌드가 정상이다.
        if platform.machine().startswith("aarch64") and dev == "cpu":
            print(f"{OK}             RPi 는 CPU 추론이 정상이다.")
    except ImportError:
        print(f"{FAIL}torch 미설치")
        failures.append("torch 미설치")


def find_port(explicit: str | None) -> str | None:
    section("2. 시리얼 포트 (USB 버스 서보 어댑터)")

    if explicit:
        print(f"{OK}지정된 포트 : {explicit}")
        return explicit

    try:
        from serial.tools import list_ports
    except ImportError:
        print(f"{FAIL}pyserial 미설치")
        failures.append("pyserial 미설치")
        return None

    ports = list(list_ports.comports())
    if not ports:
        print(f"{FAIL}시리얼 포트가 하나도 없다. 어댑터가 USB 에 꽂혀 있는가?")
        failures.append("시리얼 포트 없음")
        return None

    for p in ports:
        print(f"{OK}{p.device:<16} {p.description}")

    # CH34x(어댑터) 우선. 없으면 첫 번째.
    for p in ports:
        if "CH34" in (p.description or "") or "1A86" in (p.hwid or "").upper():
            print(f"\n     → 어댑터로 추정: {p.device}")
            return p.device

    print(f"\n{WARN}어댑터를 특정하지 못했다. 첫 번째 포트를 사용한다: {ports[0].device}")
    print("     틀리면 --port 로 직접 지정할 것.")
    warnings.append("포트 자동 판별 실패")
    return ports[0].device


def check_servos(port: str) -> dict | None:
    section("3. 서보 버스 (ID 1~6)")

    from lerobot.motors import Motor, MotorNormMode
    from lerobot.motors.feetech import FeetechMotorsBus

    motors = {
        name: Motor(
            i,
            "sts3215",
            MotorNormMode.RANGE_0_100 if name == "gripper" else MotorNormMode.RANGE_M100_100,
        )
        for name, i, _ in MOTOR_SPEC
    }

    bus = FeetechMotorsBus(port=port, motors=motors)
    try:
        bus.connect(handshake=False)
    except (ConnectionError, PermissionError) as e:
        print(f"{FAIL}포트를 열 수 없다: {e}")
        if platform.system() == "Linux":
            # 리눅스에서 가장 흔한 원인. 모르면 몇 시간을 날린다.
            print("\n     리눅스에서 흔한 원인 — 시리얼 포트 접근 권한:")
            print("       sudo usermod -aG dialout $USER")
            print("     실행 후 로그아웃했다 다시 접속할 것 (재접속해야 그룹이 적용된다).")
            print("\n     그 외:")
            print("       - 서보 전원(12V)이 어댑터 VIN 에 인가되어 있는가")
            print("       - 어댑터가 RPi USB 에 꽂혀 있는가")
        failures.append("서보 버스 연결 실패")
        return None

    present = bus.broadcast_ping() or {}
    found = sorted(present)
    print(f"     broadcast_ping → ID {found if found else '없음'}\n")

    if found != [1, 2, 3, 4, 5, 6]:
        print(f"{FAIL}ID 1~6 이 모두 응답하지 않는다. (응답: {found})")
        print("     - 서보 전원(12V)이 어댑터 VIN 에 인가되어 있는가")
        print("     - ID 중복? 서보를 하나만 연결해 확인할 것 (공장 기본값은 전부 ID=1)")
        failures.append(f"서보 응답 불완전: {found}")

    print(f"{'축':<14}{'ID':>3}  {'Pos':>6}  {'Load':>6}  {'Temp':>6}  {'Volt':>7}")
    print("-" * 55)

    eprom = {}
    for name, mid, label in MOTOR_SPEC:
        if mid not in present:
            print(f"{name:<14}{mid:>3}  {'FAIL':>6}")
            continue

        pos = bus.read("Present_Position", name, normalize=False)
        load = bus.read("Present_Load", name, normalize=False)
        temp = bus.read("Present_Temperature", name, normalize=False)
        volt = bus.read("Present_Voltage", name, normalize=False) / 10.0

        eprom[name] = {
            "homing_offset": bus.read("Homing_Offset", name, normalize=False),
            "range_min": bus.read("Min_Position_Limit", name, normalize=False),
            "range_max": bus.read("Max_Position_Limit", name, normalize=False),
        }

        print(f"{name:<14}{mid:>3}  {pos:>6}  {load:>6}  {temp:>5}°C  {volt:>6.1f}V")

        if not 10.0 <= volt <= 13.0:
            print(f"       ⚠ 전압 {volt:.1f}V — 팔로워 12V 정격을 벗어남")
            warnings.append(f"{name} 전압 {volt:.1f}V")
        if temp >= 55:
            print(f"       ⚠ 온도 {temp}°C — 과열")
            warnings.append(f"{name} 과열 {temp}°C")

    bus.disconnect(disable_torque=False)
    return eprom


def check_calibration(eprom: dict | None) -> None:
    section("4. 캘리브레이션")

    if not CALIB_PATH.exists():
        print(f"{FAIL}캘리브레이션 파일 없음: {CALIB_PATH}")
        print("     노트북에서 복사할 것:")
        print("       HazardBot/calibration/follower_arm.json →")
        print(f"       {CALIB_PATH.parent}/")
        failures.append("캘리브레이션 파일 없음")
        return

    print(f"{OK}파일 존재   : {CALIB_PATH}")
    calib = json.loads(CALIB_PATH.read_text())

    if eprom is None:
        print(f"{WARN}서보를 읽지 못해 EPROM 대조를 건너뛴다.")
        return

    # 정책은 캘리브레이션된 좌표계에서 학습된다.
    # 서보 EPROM 과 JSON 이 어긋나면 같은 숫자가 다른 물리 자세를 가리킨다.
    print(f"\n{'축':<14}{'서보 EPROM':>26}   {'JSON':>26}  판정")
    print("-" * 78)

    mismatch = 0
    for name, _, _ in MOTOR_SPEC:
        if name not in eprom or name not in calib:
            continue
        e, c = eprom[name], calib[name]
        same = (
            e["homing_offset"] == c["homing_offset"]
            and e["range_min"] == c["range_min"]
            and e["range_max"] == c["range_max"]
        )
        es = f"ofs={e['homing_offset']:>6} {e['range_min']:>5}~{e['range_max']:<5}"
        cs = f"ofs={c['homing_offset']:>6} {c['range_min']:>5}~{c['range_max']:<5}"
        print(f"{name:<14}{es:>26}   {cs:>26}  {'일치' if same else '불일치'}")
        if not same:
            mismatch += 1

    if mismatch:
        print(f"\n{FAIL}{mismatch}개 축이 불일치한다.")
        print("     정책은 캘리브레이션된 좌표계에서 학습됐다.")
        print("     좌표계가 어긋나면 같은 숫자가 다른 물리 자세를 가리켜 팔이 엉뚱하게 움직인다.")
        print("     → 노트북의 follower_arm.json 을 다시 복사할 것.")
        failures.append(f"캘리브레이션 불일치 {mismatch}축")
    else:
        print(f"\n{OK}전 축 일치. 정책과 같은 좌표계다.")


def check_cameras() -> None:
    section("5. 카메라")

    try:
        import cv2
    except ImportError:
        print(f"{FAIL}opencv 미설치")
        failures.append("opencv 미설치")
        return

    found = 0
    for idx in range(6):
        cap = cv2.VideoCapture(idx)
        if not cap.isOpened():
            cap.release()
            continue

        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 30)

        ok, _ = cap.read()
        if not ok:
            cap.release()
            continue

        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fourcc_i = int(cap.get(cv2.CAP_PROP_FOURCC))
        fourcc = "".join(chr((fourcc_i >> (8 * i)) & 0xFF) for i in range(4))

        # 실측 FPS (설정값이 아니라 실제로 나오는 값)
        t0, n = time.perf_counter(), 0
        while time.perf_counter() - t0 < 2.0:
            if cap.read()[0]:
                n += 1
        fps = n / (time.perf_counter() - t0)

        print(f"{OK}index {idx}   {w}x{h}  fourcc={fourcc}  실측 {fps:.1f} fps")

        if "MJPG" not in fourcc:
            print(f"       ⚠ MJPEG 이 아니다 ({fourcc}). 비압축이면 카메라 2대 동시 구동 시")
            print("         USB 2.0 대역폭이 부족해 프레임이 드롭된다.")
            warnings.append(f"index {idx} MJPEG 아님")
        if fps < 20:
            print(f"       ⚠ 실측 {fps:.1f} fps — 30fps 에 못 미친다.")
            warnings.append(f"index {idx} 저프레임 {fps:.1f}")

        cap.release()
        found += 1

    if found == 0:
        print(f"{FAIL}카메라를 찾지 못했다.")
        failures.append("카메라 없음")
    elif found == 1:
        print(f"\n{WARN}카메라가 1대뿐이다. 손목 + 작업공간 2대 구성이 목표다.")
        warnings.append("카메라 1대")
    else:
        print(f"\n{OK}카메라 {found}대 검출.")
        print("     ⚠ 두 카메라가 서로 다르게 식별되는지 확인할 것 (동일 VID/PID 면 무작위로 뒤바뀐다).")


def test_gripper(port: str) -> None:
    section("6. 쓰기 경로 검증 — 그리퍼 개폐")

    from lerobot.motors import Motor, MotorNormMode
    from lerobot.motors.feetech import FeetechMotorsBus

    if not CALIB_PATH.exists():
        print(f"{FAIL}캘리브레이션이 없어 안전 범위를 알 수 없다. 건너뛴다.")
        return

    calib = json.loads(CALIB_PATH.read_text())
    g = calib["gripper"]
    lo, hi = g["range_min"], g["range_max"]

    motors = {"gripper": Motor(6, "sts3215", MotorNormMode.RANGE_0_100)}
    bus = FeetechMotorsBus(port=port, motors=motors)
    bus.connect(handshake=False)

    start = bus.read("Present_Position", "gripper", normalize=False)
    print(f"     현재 위치   : {start}")
    print(f"     캘리브 범위 : {lo} ~ {hi}")

    # 캘리브레이션 범위의 25% / 75% 지점만 오간다. 범위를 절대 벗어나지 않는다.
    span = hi - lo
    targets = [lo + int(span * 0.25), lo + int(span * 0.75), start]

    bus.write("Operating_Mode", "gripper", 0)  # POSITION
    bus.write("Acceleration", "gripper", 10)   # 완만하게
    bus.enable_torque("gripper")

    try:
        for t in targets:
            t = max(lo, min(hi, t))  # 범위 강제
            print(f"     → 목표 {t} 로 이동...")
            bus.write("Goal_Position", "gripper", t, normalize=False)

            # 고정 대기 대신 위치가 안정될 때까지 기다린다.
            # 이동 거리에 따라 소요 시간이 다르므로 고정 대기는 긴 이동에서 조기 측정이 된다.
            now = bus.read("Present_Position", "gripper", normalize=False)
            deadline = time.perf_counter() + 5.0
            stable = 0
            while time.perf_counter() < deadline:
                time.sleep(0.1)
                prev, now = now, bus.read("Present_Position", "gripper", normalize=False)
                if abs(now - prev) <= 2:
                    stable += 1
                    if stable >= 3:  # 0.3초간 정지 → 안정
                        break
                else:
                    stable = 0

            err = abs(now - t)
            mark = OK if err < 80 else WARN
            print(f"{mark}도달 {now} (오차 {err})")
            if err >= 80:
                print("       ⚠ 오차가 크다. 그리퍼가 물체나 기계적 한계에 걸렸을 수 있다.")
                warnings.append(f"그리퍼 위치 오차 {err}")
    finally:
        bus.disable_torque("gripper")
        bus.disconnect(disable_torque=False)

    print(f"\n{OK}쓰기 경로 정상. 서보가 명령대로 움직인다.")


def settle(bus, name: str, timeout: float = 5.0) -> int:
    """위치가 안정될 때까지 기다린 뒤 최종 위치를 반환한다.

    고정 대기는 이동 거리가 길 때 조기 측정이 되어 오차를 과대평가한다.
    """
    now = bus.read("Present_Position", name, normalize=False)
    deadline = time.perf_counter() + timeout
    stable = 0
    while time.perf_counter() < deadline:
        time.sleep(0.1)
        prev, now = now, bus.read("Present_Position", name, normalize=False)
        if abs(now - prev) <= 2:
            stable += 1
            if stable >= 3:
                break
        else:
            stable = 0
    return now


def test_all_axes(port: str, delta: int) -> None:
    section(f"7. 전 축 동작 검증 (±{delta} 카운트 ≈ ±{delta * 360 / 4096:.1f}°)")

    from lerobot.motors import Motor, MotorNormMode
    from lerobot.motors.feetech import FeetechMotorsBus

    if not CALIB_PATH.exists():
        print(f"{FAIL}캘리브레이션이 없어 안전 범위를 알 수 없다. 건너뛴다.")
        return

    calib = json.loads(CALIB_PATH.read_text())

    motors = {
        name: Motor(
            i,
            "sts3215",
            MotorNormMode.RANGE_0_100 if name == "gripper" else MotorNormMode.RANGE_M100_100,
        )
        for name, i, _ in MOTOR_SPEC
    }
    bus = FeetechMotorsBus(port=port, motors=motors)
    bus.connect(handshake=False)

    start = {n: bus.read("Present_Position", n, normalize=False) for n in motors}

    # ── 안전의 핵심 ──────────────────────────────────────────────────────
    # 서보의 Goal_Position 레지스터에는 이전 목표값이 남아 있다.
    # 그대로 토크를 켜면 서보가 그 옛 목표로 순간 이동해 팔이 튄다.
    # 토크를 켜기 전에 Goal_Position 을 현재 위치로 덮어써서 "제자리 유지"로 만든다.
    for n in motors:
        bus.write("Operating_Mode", n, 0)      # POSITION
        bus.write("Acceleration", n, 10)       # 완만하게
        bus.write("Goal_Position", n, start[n], normalize=False)
    bus.enable_torque()
    time.sleep(0.5)
    print(f"{OK}토크 ON — 현재 자세를 그대로 유지 중 (튐 없음)\n")

    try:
        for name, mid, label in MOTOR_SPEC:
            lo = calib[name]["range_min"]
            hi = calib[name]["range_max"]
            p0 = start[name]

            # wrist_roll 은 0~4095(연속 회전)라 마진 개념이 없다.
            margin = 0 if name == "wrist_roll" else 60

            up = min(p0 + delta, hi - margin)
            down = max(p0 - delta, lo + margin)
            # 여유가 있는 쪽으로 움직인다.
            target = up if (up - p0) >= (p0 - down) else down

            if abs(target - p0) < 20:
                print(f"{WARN}{name:<14} 가동 여유 부족 (범위 {lo}~{hi}, 현재 {p0}) — 건너뜀")
                warnings.append(f"{name} 가동 여유 부족")
                continue

            print(f"     {name:<14}({label}) {p0} → {target} ...", end=" ", flush=True)
            bus.write("Goal_Position", name, target, normalize=False)
            reached = settle(bus, name)
            err1 = abs(reached - target)

            bus.write("Goal_Position", name, p0, normalize=False)
            back = settle(bus, name)
            err2 = abs(back - p0)

            load = abs(bus.read("Present_Load", name, normalize=False))

            worst = max(err1, err2)
            if worst < 40:
                print(f"{OK.strip()} 도달 오차 {err1}, 복귀 오차 {err2}, 부하 {load}")
            else:
                print(f"{WARN.strip()} 도달 오차 {err1}, 복귀 오차 {err2}, 부하 {load}")
                print("           ⚠ 오차가 크다. 기계적 간섭이나 부하 과다를 의심할 것.")
                warnings.append(f"{name} 위치 오차 {worst}")
    finally:
        bus.disable_torque()
        bus.disconnect(disable_torque=False)
        print(f"\n{OK}토크 OFF. 모든 축이 원위치로 복귀했다.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", help="서보 어댑터 포트 (예: /dev/ttyACM0, COM3)")
    parser.add_argument("--move", action="store_true", help="그리퍼 개폐로 쓰기 경로 검증")
    parser.add_argument(
        "--move-all",
        action="store_true",
        help="전 축을 소폭(±delta) 움직여 검증. 팔을 받칠 것.",
    )
    parser.add_argument("--delta", type=int, default=100, help="전 축 테스트 이동량 (카운트, 기본 100 ≈ 8.8°)")
    parser.add_argument("--skip-cameras", action="store_true")
    args = parser.parse_args()

    print("\nHazardBot — RPi 5 배포 준비 점검")

    check_env()
    port = find_port(args.port)

    eprom = check_servos(port) if port else None
    check_calibration(eprom)

    if not args.skip_cameras:
        check_cameras()

    if args.move and port and eprom:
        test_gripper(port)
    elif args.move:
        print(f"\n{WARN}서보/캘리브 점검이 실패해 그리퍼 테스트를 건너뛴다.")

    if args.move_all and port and eprom:
        test_all_axes(port, args.delta)
    elif args.move_all:
        print(f"\n{WARN}서보/캘리브 점검이 실패해 전 축 테스트를 건너뛴다.")

    section("결과")
    if failures:
        print("❌ 실패:")
        for f in failures:
            print(f"   - {f}")
    if warnings:
        print("⚠ 경고:")
        for w in warnings:
            print(f"   - {w}")
    if not failures and not warnings:
        print("✅ 전 항목 통과. RPi 5 에서 로봇 암이 정상 동작한다.")
    elif not failures:
        print("✅ 치명적 문제 없음. 경고를 확인할 것.")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
