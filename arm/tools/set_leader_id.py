"""리더암 서보 ID를 **한 번에 하나씩** 부여한다.

lerobot-setup-motors 는 6축을 한 프로세스 안에서 순차 프롬프트로 처리한다.
그 방식은 사람이 터미널 앞에 붙어 있어야 하므로, 축 하나만 처리하고 끝나는
형태로 분리했다. 내부 동작은 동일하다 (MotorsBus.setup_motor).

⚠️ 버스에 서보가 **정확히 1개**만 연결돼 있어야 한다.
   STS3215 는 3핀 포트가 2개라 체인이 물려 있으면 옆 서보도 같이 잡힌다.
   양쪽 이웃 케이블을 모두 분리할 것.

⚠️ **ID = 물리적 관절 위치**다. 엉뚱한 서보를 물린 채 실행하면 통신은 정상인데
   관절이 뒤바뀌어 움직이는, 찾기 어려운 고장이 된다.

사용법:
    python tools/set_leader_id.py --port COM5 --motor gripper
    python tools/set_leader_id.py --port COM5 --motor wrist_roll
    ...
    python tools/set_leader_id.py --port COM5 --list
"""

import argparse

from lerobot.motors import Motor, MotorNormMode
from lerobot.motors.feetech import FeetechMotorsBus

# so101_leader 와 동일한 축 구성 (lerobot/teleoperators/so_leader/so_leader.py)
MOTORS = {
    "shoulder_pan": Motor(1, "sts3215", MotorNormMode.RANGE_M100_100),
    "shoulder_lift": Motor(2, "sts3215", MotorNormMode.RANGE_M100_100),
    "elbow_flex": Motor(3, "sts3215", MotorNormMode.RANGE_M100_100),
    "wrist_flex": Motor(4, "sts3215", MotorNormMode.RANGE_M100_100),
    "wrist_roll": Motor(5, "sts3215", MotorNormMode.RANGE_M100_100),
    "gripper": Motor(6, "sts3215", MotorNormMode.RANGE_0_100),
}

# 물리적 분해 순서(끝단 → 베이스). lerobot-setup-motors 와 같은 순서다.
ORDER = ["gripper", "wrist_roll", "wrist_flex", "elbow_flex", "shoulder_lift", "shoulder_pan"]

JOINT_DESC = {
    "gripper": "집게 구동",
    "wrist_roll": "손목 회전",
    "wrist_flex": "손목 상하 굽힘",
    "elbow_flex": "팔꿈치",
    "shoulder_lift": "어깨 상하",
    "shoulder_pan": "베이스 회전 (맨 아래)",
}


def show_list() -> int:
    print(f"{'순서':<5}{'축 이름':<16}{'물리 위치':<24}{'ID'}")
    print("-" * 55)
    for i, name in enumerate(ORDER, 1):
        print(f"{i:<5}{name:<16}{JOINT_DESC[name]:<24}{MOTORS[name].id}")
    return 0


def set_id(port: str, motor: str) -> int:
    target_id = MOTORS[motor].id
    print(f"대상 축   : {motor}  ({JOINT_DESC[motor]})")
    print(f"부여할 ID : {target_id}")
    print("-" * 55)

    bus = FeetechMotorsBus(port=port, motors=MOTORS)
    bus.connect(handshake=False)

    try:
        try:
            bus.setup_motor(motor)
        except RuntimeError as e:
            print(f"\n❌ 실패: {e}\n")
            print("   가장 흔한 원인은 **버스에 서보가 2개 이상** 연결된 것이다.")
            print("   대상 서보 양쪽의 3핀 케이블을 모두 분리했는지 확인할 것.")
            print("   (STS3215 는 포트가 2개라 체인이 남아 있으면 옆 서보도 잡힌다)")
            return 1

        # 새 ID 로 실제 응답하는지 확인한다. 여기까지 통과해야 성공이다.
        model = bus.ping(target_id, num_retry=5)
        if model is None:
            print(f"\n❌ ID 를 쓴 뒤 ID={target_id} 가 응답하지 않는다. 재시도할 것.")
            return 1

        volt = bus.read("Present_Voltage", motor, normalize=False) / 10.0
        pos = bus.read("Present_Position", motor, normalize=False)

        print(f"\n✅ '{motor}' → ID {target_id} 부여 완료")
        print(f"   응답 확인: model={model}  pos={pos}  volt={volt:.1f}V")

        idx = ORDER.index(motor)
        if idx + 1 < len(ORDER):
            nxt = ORDER[idx + 1]
            print(f"\n   마스킹테이프에 '{target_id}' 를 적어 붙여둘 것.")
            print(f"   다음: {nxt} ({JOINT_DESC[nxt]}) → ID {MOTORS[nxt].id}")
        else:
            print("\n   🎉 6축 전부 완료. 체인을 전부 재연결하고 다음을 실행할 것:")
            print(f"      python tools/check_leader.py --port {port}")
        return 0
    finally:
        bus.disconnect(disable_torque=False)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", help="리더 COM 포트 (예: COM5)")
    parser.add_argument("--motor", choices=list(MOTORS), help="ID 를 부여할 축 이름")
    parser.add_argument("--list", action="store_true", help="축 이름과 순서만 출력")
    args = parser.parse_args()

    if args.list:
        return show_list()
    if not args.port or not args.motor:
        parser.error("--port 와 --motor 가 필요하다 (--list 로 축 이름 확인)")

    try:
        return set_id(args.port, args.motor)
    except ConnectionError:
        print(f"❌ 포트 '{args.port}' 를 열 수 없다. 어댑터 USB 연결을 확인할 것.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
