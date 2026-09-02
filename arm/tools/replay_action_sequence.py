"""녹화된 액션 시퀀스를 개루프로 재생한다 — 정책 추론 없이, RPi CPU 부담 없는 파지.

2026-08-29 — RPi5 CPU 추론이 청크 경계마다 ~1초씩 멎는 문제
(docs/02_schedule/RPi_ACT_ROS2통합_시도기록_2026-08-29.md)를 우회하기 위해,
노트북에서 tools/extract_action_sequence.py로 뽑은 검증된 성공 에피소드의
실제 액션 시퀀스를 그대로 재생한다.

🔴 이건 더 이상 ACT 정책이 아니라 개루프 재생이다. 카메라도, 정책도, torch도
   필요 없다 — 그래서 가볍다. 대신 물체 위치·각도가 녹화 당시와 실질적으로
   같아야만 성공한다. 다르면 대응 없이 그대로 실패한다(또는 충돌 위험).

🔴 재생 전 반드시:
   ① 이 스크립트가 자동으로 check_goal.py --fix 를 돌려 194°급 순간이동 위험을 잡는다
   ② 물체를 녹화 당시와 같은 위치·각도에 둘 것
   ③ 팔이 홈 자세에서 시작해야 한다 — 시퀀스 자체가 홈에서 시작한다고 가정한다

🔴 use_degrees=False 로 고정한다 — 추출한 액션 값(예: -100.97, 101.46)이 실제
   degrees 범위가 아니라 학습·30회 검증 때 쓴 정규화 규약(그때 CLI 인자
   --robot.use_degrees=false)과 일치한다. 이걸 True(기본값)로 두면 단위 자체가
   달라져서 팔이 엉뚱하게 움직인다 — arm_act_node.py 의 lerobot-rollout 호출에도
   이 플래그가 빠져 있었던 게 발견돼서 같이 고쳤다(RPi 실물에서 "방향이 이상하다"
   고 느꼈던 원인 중 하나로 의심됨, 확정은 아님).

사용법 (RPi):
    python3 tools/replay_action_sequence.py \\
        --json ~/act_replay/ep5_near_success.json \\
        --port /dev/ttyACM0 \\
        --robot-id follower_arm
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.go_home import home_arm  # 검증된 홈 복귀 로직(코사인 이징 + 토크 안전) 재사용


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", required=True, help="extract_action_sequence.py 로 뽑은 JSON")
    ap.add_argument("--port", default="/dev/ttyACM0")
    ap.add_argument("--robot-id", default="follower_arm")
    ap.add_argument("--home-seconds", type=float, default=3.0)
    ap.add_argument("--no-precheck", action="store_true",
                     help="check_goal --fix 생략(디버그용, 실전에서는 쓰지 말 것)")
    args = ap.parse_args()

    data = json.loads(Path(args.json).read_text(encoding="utf-8"))
    fps = data["fps"]
    actions = data["actions"]
    print(f"[replay] {len(actions)}프레임 · {fps}fps · {len(actions) / fps:.1f}초 "
          f"· source episode {data.get('source_episode')}")

    # ① 안전점검 — rollout_act.ps1/arm_act_node.py 와 동일 순서
    if not args.no_precheck:
        r = subprocess.run([sys.executable, str(PROJECT_ROOT / "tools" / "check_goal.py"),
                             "--port", args.port, "--fix"])
        if r.returncode != 0:
            raise SystemExit("check_goal --fix 실패 — 팔 자세 확인 필요, 재생 중단")

    # ② 로봇 연결 — 카메라 없음(재생엔 관측이 필요 없다), use_degrees=False 고정
    from lerobot.robots.so_follower import SO101FollowerConfig, SOFollower

    config = SO101FollowerConfig(
        port=args.port,
        id=args.robot_id,
        cameras={},
        use_degrees=False,
    )
    robot = SOFollower(config)
    robot.connect()

    try:
        print("[replay] 재생 시작")
        period = 1.0 / fps
        start = time.perf_counter()
        for i, frame in enumerate(actions):
            robot.send_action(frame)
            target = start + (i + 1) * period
            sleep_s = target - time.perf_counter()
            if sleep_s > 0:
                time.sleep(sleep_s)
        elapsed = time.perf_counter() - start
        print(f"[replay] 재생 완료 ({elapsed:.1f}초, 목표 {len(actions) / fps:.1f}초)")
    finally:
        # 🔴 finally — 재생 중 예외가 나도 반드시 홈 복귀·토크 해제를 시도한다
        print("[replay] 홈 복귀")
        try:
            home_arm(robot.bus, seconds=args.home_seconds)
        except Exception as e:
            print(f"[replay] 홈 복귀 실패: {e} — 팔 상태를 직접 확인할 것")
        robot.disconnect()


if __name__ == "__main__":
    main()
