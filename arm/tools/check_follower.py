"""팔로워(SO-ARM101) USB 직결 통신 검증.

ESP32에서 검증했던 Ping / ReadPos / ReadLoad / ReadTemper 를
호스트 USB 직결 + LeRobot Feetech 드라이버 경로에서 재현한다.

읽기 전용이다. 토크를 켜거나 서보를 움직이지 않는다.

사용법:
    python tools/check_follower.py --port COM3
    python tools/check_follower.py --port COM3 --scan-only
"""

import argparse
import time

from lerobot.motors import Motor, MotorNormMode
from lerobot.motors.feetech import FeetechMotorsBus

# so101_follower 와 동일한 축 구성 (lerobot/robots/so_follower/so_follower.py)
MOTORS = {
    "shoulder_pan": Motor(1, "sts3215", MotorNormMode.RANGE_M100_100),   # Base
    "shoulder_lift": Motor(2, "sts3215", MotorNormMode.RANGE_M100_100),  # Shoulder
    "elbow_flex": Motor(3, "sts3215", MotorNormMode.RANGE_M100_100),     # Elbow
    "wrist_flex": Motor(4, "sts3215", MotorNormMode.RANGE_M100_100),     # Wrist Pitch
    "wrist_roll": Motor(5, "sts3215", MotorNormMode.RANGE_M100_100),     # Wrist Roll
    "gripper": Motor(6, "sts3215", MotorNormMode.RANGE_0_100),           # Gripper
}

EXPECTED_VOLTAGE = (10.0, 13.0)  # 팔로워 정격 12V


def scan(port: str) -> None:
    print(f"[scan] {port} 를 지원 보드레이트 전체로 탐색 중...")
    found = FeetechMotorsBus.scan_port(port)
    if not found:
        print("[scan] 응답한 서보가 없음. 전원 / 배선 / 포트를 확인할 것.")
        return
    for baudrate, ids in found.items():
        print(f"[scan] baudrate={baudrate:>8} → ID {sorted(ids)}")
        if baudrate != 1_000_000:
            print("       ⚠ ESP32 검증값(1 Mbps)과 다름. lerobot 기본값도 1 Mbps다.")


def check(port: str) -> int:
    bus = FeetechMotorsBus(port=port, motors=MOTORS)
    bus.connect(handshake=False)
    print(f"[connect] {port} 연결됨\n")

    # 브로드캐스트로 버스에 실제로 존재하는 ID 를 먼저 확정한다.
    present = bus.broadcast_ping() or {}
    print(f"[broadcast_ping] 응답한 ID: {sorted(present) if present else '없음'}\n")

    header = f"{'축':<14}{'ID':>3}  {'Ping':>5}  {'Pos':>6}  {'Load':>6}  {'Temp':>5}  {'Volt':>6}"
    print(header)
    print("-" * len(header))

    failed = []
    for name, motor in MOTORS.items():
        model = bus.ping(motor.id, num_retry=3)
        if model is None:
            print(f"{name:<14}{motor.id:>3}  {'FAIL':>5}  {'-':>6}  {'-':>6}  {'-':>5}  {'-':>6}")
            failed.append(name)
            continue

        pos = bus.read("Present_Position", name, normalize=False)
        load = bus.read("Present_Load", name, normalize=False)
        temp = bus.read("Present_Temperature", name, normalize=False)
        volt = bus.read("Present_Voltage", name, normalize=False) / 10.0

        print(f"{name:<14}{motor.id:>3}  {'OK':>5}  {pos:>6}  {load:>6}  {temp:>4}°C  {volt:>5.1f}V")

        if not EXPECTED_VOLTAGE[0] <= volt <= EXPECTED_VOLTAGE[1]:
            failed.append(f"{name}(전압 {volt:.1f}V — 12V 정격에서 벗어남)")
        if temp >= 55:
            failed.append(f"{name}(온도 {temp}°C — 과열)")

    # disable_torque=True 로 두면 응답 없는 서보에 토크 해제를 시도하다 예외가 난다.
    # 이 스크립트는 읽기 전용이므로 토크를 건드리지 않는다.
    bus.disconnect(disable_torque=False)
    print()

    if failed:
        print("❌ 문제 있음:")
        for f in failed:
            print(f"   - {f}")
        return 1

    print("✅ ID 1~6 전체 응답. USB 직결 경로에서 팔로워 통신 정상.")
    print("   → 다음: lerobot-calibrate --robot.type=so101_follower "
          f"--robot.port={port} --robot.id=follower_arm")
    return 0


def watch(port: str) -> int:
    """1초마다 버스를 브로드캐스트 핑하며 보이는 ID 를 계속 출력한다.

    커넥터를 흔들어보며 접촉 불량을 찾을 때 쓴다. Ctrl+C 로 종료.
    """
    bus = FeetechMotorsBus(port=port, motors=MOTORS)
    bus.connect(handshake=False)
    print(f"[watch] {port} — 1초마다 검사. 커넥터를 눌러보며 변화를 관찰할 것.")
    print("[watch] Ctrl+C 로 종료.\n")

    last = None
    try:
        while True:
            present = bus.broadcast_ping() or {}
            ids = sorted(present)
            mark = "  ← 변화" if ids != last else ""
            status = "전체 정상" if ids == [1, 2, 3, 4, 5, 6] else ""
            print(f"{time.strftime('%H:%M:%S')}  응답 ID: {ids if ids else '없음':<24}{status}{mark}")
            last = ids
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[watch] 종료.")
    finally:
        bus.disconnect(disable_torque=False)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True, help="팔로워 COM 포트 (예: COM3)")
    parser.add_argument("--scan-only", action="store_true", help="보드레이트/ID 탐색만 수행")
    parser.add_argument("--watch", action="store_true", help="1초마다 반복 검사 (접촉 불량 추적용)")
    args = parser.parse_args()

    try:
        if args.watch:
            return watch(args.port)
        scan(args.port)
        print()
        if args.scan_only:
            return 0
        return check(args.port)
    except ConnectionError:
        print(f"❌ 포트 '{args.port}' 를 열 수 없다.")
        print("   - 어댑터가 USB에 꽂혀 있는지 확인")
        print("   - `lerobot-find-port` 로 실제 포트 번호 확인")
        print("   - COM 포트가 아예 안 보이면 CH340 / CP210x 드라이버 설치")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
