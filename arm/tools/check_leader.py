"""리더암(SO-ARM101) USB 직결 통신·전압 검증.

check_follower.py 의 리더 버전이다. 차이는 **기대 전압 하나뿐**이다.
팔로워는 12V 정격, 리더는 **7.4V 정격**이라 check_follower.py 를 그대로 쓰면
정상인데도 전압 FAIL 이 뜬다.

읽기 전용이다. 토크를 켜거나 서보를 움직이지 않는다.

사용법:
    # ID 부여 전 — 서보 1개만 연결한 상태에서 전압만 확인 (가장 먼저 할 것)
    python tools/check_leader.py --port COM4 --volt-only

    # 버스에 어떤 ID 가 응답하는지 탐색
    python tools/check_leader.py --port COM4 --scan-only

    # ID 부여 후 — 6축 전체 검증
    python tools/check_leader.py --port COM4
"""

import argparse

from lerobot.motors import Motor, MotorNormMode
from lerobot.motors.feetech import FeetechMotorsBus

# so101_leader 와 동일한 축 구성 (lerobot/teleoperators/so_leader/so_leader.py)
MOTORS = {
    "shoulder_pan": Motor(1, "sts3215", MotorNormMode.RANGE_M100_100),   # Base
    "shoulder_lift": Motor(2, "sts3215", MotorNormMode.RANGE_M100_100),  # Shoulder
    "elbow_flex": Motor(3, "sts3215", MotorNormMode.RANGE_M100_100),     # Elbow
    "wrist_flex": Motor(4, "sts3215", MotorNormMode.RANGE_M100_100),     # Wrist Pitch
    "wrist_roll": Motor(5, "sts3215", MotorNormMode.RANGE_M100_100),     # Wrist Roll
    "gripper": Motor(6, "sts3215", MotorNormMode.RANGE_0_100),           # Gripper
}

# 🔴 리더 서보는 7.4V 정격이다. 팔로워(12V)와 다르다.
#    2S LiPo 기준 만충 8.4V ~ 방전 6.0V 이므로 그 범위를 합격으로 본다.
EXPECTED_VOLTAGE = (6.5, 8.4)
NOMINAL_VOLTAGE = 7.4


def _verdict(volt: float) -> str:
    if volt > EXPECTED_VOLTAGE[1]:
        return "🔴 과전압 — 즉시 전원 차단"
    if volt < EXPECTED_VOLTAGE[0]:
        return "🔴 저전압 — CC 전류제한 또는 배선 확인"
    if abs(volt - NOMINAL_VOLTAGE) > 0.3:
        return "⚠ 정격에서 다소 벗어남 (동작은 가능)"
    return "✅ 정상"


def volt_only(port: str, servo_id: int) -> int:
    """ID 부여 전에 쓴다. 서보를 **1개만** 연결한 상태로 실행할 것.

    출고 기본값은 전부 ID=1 이므로 여러 개를 물린 채 실행하면 응답이 뭉개진다.
    """
    bus = FeetechMotorsBus(port=port, motors={"probe": Motor(servo_id, "sts3215", MotorNormMode.RANGE_M100_100)})
    bus.connect(handshake=False)
    print(f"[connect] {port} 연결됨. ID={servo_id} 를 핑한다.\n")

    try:
        model = bus.ping(servo_id, num_retry=5)
        if model is None:
            print(f"❌ ID={servo_id} 무응답.")
            print("   - 서보가 1개만 연결돼 있는지 확인 (출고 기본값이 전부 ID=1 이라 충돌한다)")
            print("   - 3핀 커넥터 방향·체결 확인")
            print("   - XL4015 출력이 실제로 서보까지 들어오는지 확인")
            return 1

        volt = bus.read("Present_Voltage", "probe", normalize=False) / 10.0
        temp = bus.read("Present_Temperature", "probe", normalize=False)

        print(f"서보 보고 전압 : {volt:.1f}V   {_verdict(volt)}")
        print(f"서보 온도      : {temp}°C" + ("   🔴 과열" if temp >= 55 else ""))
        print()

        if not EXPECTED_VOLTAGE[0] <= volt <= EXPECTED_VOLTAGE[1]:
            print("→ 전원을 차단하고 XL4015 출력을 다시 조정할 것.")
            return 1

        print("→ 7.4V 레일 확인 완료. 다음: lerobot-setup-motors 로 ID 부여")
        return 0
    finally:
        bus.disconnect(disable_torque=False)


def scan(port: str) -> None:
    print(f"[scan] {port} 를 지원 보드레이트 전체로 탐색 중...")
    found = FeetechMotorsBus.scan_port(port)
    if not found:
        print("[scan] 응답한 서보가 없음. 전원 / 배선 / 포트를 확인할 것.")
        return
    for baudrate, ids in found.items():
        print(f"[scan] baudrate={baudrate:>8} → ID {sorted(ids)}")
        if baudrate != 1_000_000:
            print("       ⚠ lerobot 기본값(1 Mbps)과 다름.")
        if sorted(ids) == [1]:
            print("       ℹ ID 1 만 보이는 것은 **ID 부여 전이면 정상**이다.")
            print("         출고 기본값이 전부 ID=1 이라 6개가 동시에 응답해 뭉개진 상태.")
            print("         → lerobot-setup-motors 로 ID 를 부여할 것.")


def check(port: str) -> int:
    """ID 부여 후 6축 전체 검증."""
    bus = FeetechMotorsBus(port=port, motors=MOTORS)
    bus.connect(handshake=False)
    print(f"[connect] {port} 연결됨\n")

    present = bus.broadcast_ping() or {}
    print(f"[broadcast_ping] 응답한 ID: {sorted(present) if present else '없음'}\n")

    header = f"{'축':<14}{'ID':>3}  {'Ping':>5}  {'Pos':>6}  {'Temp':>5}  {'Volt':>6}"
    print(header)
    print("-" * len(header))

    failed = []
    for name, motor in MOTORS.items():
        model = bus.ping(motor.id, num_retry=3)
        if model is None:
            print(f"{name:<14}{motor.id:>3}  {'FAIL':>5}  {'-':>6}  {'-':>5}  {'-':>6}")
            failed.append(name)
            continue

        pos = bus.read("Present_Position", name, normalize=False)
        temp = bus.read("Present_Temperature", name, normalize=False)
        volt = bus.read("Present_Voltage", name, normalize=False) / 10.0

        print(f"{name:<14}{motor.id:>3}  {'OK':>5}  {pos:>6}  {temp:>4}°C  {volt:>5.1f}V")

        if not EXPECTED_VOLTAGE[0] <= volt <= EXPECTED_VOLTAGE[1]:
            failed.append(f"{name}(전압 {volt:.1f}V — 7.4V 정격에서 벗어남)")
        if temp >= 55:
            failed.append(f"{name}(온도 {temp}°C — 과열)")

    bus.disconnect(disable_torque=False)
    print()

    if failed:
        print("❌ 문제 있음:")
        for f in failed:
            print(f"   - {f}")
        return 1

    print("✅ ID 1~6 전체 응답. 리더 통신·전압 정상.")
    print("   → 다음: python tools/watch_positions.py "
          f"--port {port} --free  로 가동 범위를 먼저 측정할 것 (실행계획 §5-2)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True, help="리더 COM 포트 (예: COM4)")
    parser.add_argument("--volt-only", action="store_true",
                        help="ID 부여 전 전압 확인. 서보를 1개만 연결하고 실행할 것")
    parser.add_argument("--id", type=int, default=1,
                        help="--volt-only 로 핑할 ID (기본 1 = 출고 기본값)")
    parser.add_argument("--scan-only", action="store_true", help="보드레이트/ID 탐색만 수행")
    args = parser.parse_args()

    try:
        if args.volt_only:
            return volt_only(args.port, args.id)
        scan(args.port)
        print()
        if args.scan_only:
            return 0
        return check(args.port)
    except ConnectionError:
        print(f"❌ 포트 '{args.port}' 를 열 수 없다.")
        print("   - 어댑터가 USB에 꽂혀 있는지 확인")
        print("   - USB-C **데이터** 케이블인지 확인 (충전 전용은 LED만 켜진다)")
        print("   - `lerobot-find-port` 로 실제 포트 번호 확인")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
