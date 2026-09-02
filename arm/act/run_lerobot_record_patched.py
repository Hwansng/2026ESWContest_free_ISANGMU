"""ACT 롤아웃 전용 lerobot_record 래퍼 — 동작이 멎으면 조기 종료하고, 같은 프로세스에서 홈 복귀.

왜 필요한가 (2026-08-28 사용자 지적: "뚜껑 닫은 후 홈 복귀까지 시간이 좀 길어"):
    ACT 정책은 "뚜껑 닫고 1초 유지 후 종료"로 학습돼 있어서, 태스크를 마치면 최종 자세에
    수렴해 **더 이상 움직이지 않는다.** 그런데 lerobot 은 `episode_time_s` 를 다 채울
    때까지 계속 녹화하므로, 실측에서 15~16초에 끝난 뒤 4~5초를 정지 상태로 낭비했다.
    거기에 `go_home.py` 를 **별도 프로세스**로 띄우는 비용(파이썬 기동 + lerobot import +
    버스 연결)이 더해져, 뚜껑 닫기부터 복귀까지 10초 이상 걸렸다.

    이 래퍼가 둘 다 없앤다:
      1. **조기 종료** — 정책이 내놓는 액션이 `--still-seconds` 동안 거의 변하지 않으면
         `events["exit_early"]` 를 켜서 에피소드를 끝낸다. 이 정지 감지 구간이 곧
         사용자가 요청한 "0.5초 정지"다.
      2. **같은 프로세스 내 홈 복귀** — `record_loop` 이 반환한 직후, 아직 열려 있는
         `robot.bus` 로 바로 복귀시킨다. 프로세스 재시작이 없다.
         **영상 인코딩(save_episode) 보다 먼저** 실행되므로 팔이 즉시 움직인다.

구현 방식 — 왜 이렇게 우회했는가:
    `record_loop` 은 매 프레임 `events["exit_early"]` 를 읽는다. 그래서 루프 본문을
    복사해 고치는 대신(버전이 바뀌면 깨진다), 다음 두 개만 몽키패치한다:
      - `predict_action`  → 정책이 내놓은 액션을 정지 감지기에 흘려보낸다
      - `init_keyboard_listener` → `events` 를 dict 서브클래스로 바꿔서,
        `exit_early` 를 물어볼 때 정지 감지기 판정도 함께 반영한다
    설치된 lerobot 패키지 자체는 건드리지 않는다.

사용법:
    python tools/run_lerobot_record_patched.py --robot.type=... (lerobot_record 인자 그대로)
    추가 인자: --still-seconds 0.5 --still-threshold 0.4 --min-seconds 8
              --home-seconds 3.0 --no-home
"""

import argparse
import logging
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import lerobot.scripts.lerobot_record as rec

from tools.go_home import home_arm


class StillnessDetector:
    """정책이 내놓는 액션이 얼마나 안 변하는지 본다.

    임계값 근거 (2026-08-28 실측, 6축 정규화 단위의 프레임당 절대변화 합):
        - 동작 중: 초당 25~180 → 프레임당 약 0.8~6.0
        - 정지 중: 초당 0.3~6.1 → 프레임당 약 0.01~0.2
      그래서 0.4 가 두 분포 사이에 여유 있게 놓인다. 게다가 `still_frames` 만큼
      **연속으로** 밑돌아야 하므로, 중간에 잠깐 느려진 것만으로는 켜지지 않는다.
    """

    def __init__(self, fps: int, still_seconds: float, threshold: float, min_seconds: float):
        self.threshold = threshold
        self.still_frames = max(1, int(round(still_seconds * fps)))
        self.min_frames = max(0, int(round(min_seconds * fps)))
        self.reset()

    def reset(self):
        self._prev = None
        self._frames = 0
        self._still = 0
        self._fired = False

    def feed(self, action):
        try:
            values = [float(v) for v in action.flatten().tolist()]
        except Exception:
            return
        self._frames += 1
        if self._prev is not None:
            delta = sum(abs(a - b) for a, b in zip(values, self._prev))
            self._still = self._still + 1 if delta < self.threshold else 0
        self._prev = values

    @property
    def converged(self) -> bool:
        if self._fired or self._frames < self.min_frames:
            return False
        if self._still >= self.still_frames:
            self._fired = True
            logging.info(
                f"[patched] 동작 정지 감지 — {self._still}프레임 연속 변화 < {self.threshold}. "
                f"에피소드를 조기 종료한다 (총 {self._frames}프레임)."
            )
            return True
        return False


class EarlyStopEvents(dict):
    """`exit_early` 를 물어볼 때 정지 감지기 판정도 함께 반영하는 events dict."""

    detector: StillnessDetector | None = None

    def __getitem__(self, key):
        if key == "exit_early" and self.detector is not None and self.detector.converged:
            return True
        return super().__getitem__(key)

    def __setitem__(self, key, value):
        # record_loop 은 break 직후 exit_early 를 False 로 되돌린다. 감지기도 같이
        # 초기화해야 뒤따르는 리셋 구간이 즉시 종료되지 않는다.
        if key == "exit_early" and not value and self.detector is not None:
            self.detector.reset()
        super().__setitem__(key, value)


def install(args) -> None:
    detector_holder: dict[str, StillnessDetector | None] = {"d": None}

    orig_predict = rec.predict_action
    orig_listener = rec.init_keyboard_listener
    orig_loop = rec.record_loop

    def patched_predict(*a, **kw):
        action = orig_predict(*a, **kw)
        d = detector_holder["d"]
        if d is not None:
            d.feed(action)
        return action

    def patched_listener(*a, **kw):
        listener, events = orig_listener(*a, **kw)
        wrapped = EarlyStopEvents(events)
        wrapped.detector = detector_holder["d"]
        return listener, wrapped

    def patched_loop(*a, **kw):
        policy = kw.get("policy")
        robot = kw.get("robot")
        fps = kw.get("fps") or 30

        # 정책이 도는 구간에서만 조기 종료·복귀를 건다. 리셋 구간(policy=None)은 건드리지 않는다.
        if policy is not None:
            d = StillnessDetector(fps, args.still_seconds, args.still_threshold, args.min_seconds)
            detector_holder["d"] = d
            events = kw.get("events")
            if isinstance(events, EarlyStopEvents):
                events.detector = d
        else:
            detector_holder["d"] = None

        try:
            return orig_loop(*a, **kw)
        finally:
            if policy is not None and robot is not None and not args.no_home:
                # 🔵 여기는 save_episode(영상 인코딩) **이전**이다. 그래서 팔이 먼저 움직이고
                #    인코딩은 그 뒤에 돌아 사용자 체감 지연이 사라진다.
                #    finally 이므로 녹화가 예외로 끝나도 복귀·토크해제가 반드시 실행된다.
                logging.info("[patched] 홈 복귀 시작 (같은 프로세스, 버스 재사용)")
                try:
                    home_arm(robot.bus, seconds=args.home_seconds)
                except Exception as exception:
                    logging.error(f"[patched] 홈 복귀 실패: {type(exception).__name__}: {exception}")
                    logging.error("[patched] 팔 상태를 확인하고 손으로 복귀시킬 것.")

    rec.predict_action = patched_predict
    rec.init_keyboard_listener = patched_listener
    rec.record_loop = patched_loop


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--still-seconds", type=float, default=0.5,
                        help="이 시간만큼 액션이 안 변하면 조기 종료 (기본 0.5초)")
    parser.add_argument("--still-threshold", type=float, default=0.4,
                        help="프레임당 6축 절대변화 합이 이보다 작으면 '정지'로 본다 (기본 0.4)")
    parser.add_argument("--min-seconds", type=float, default=8.0,
                        help="이 시간 전에는 조기 종료하지 않는다 (기본 8초)")
    parser.add_argument("--home-seconds", type=float, default=3.0, help="홈 복귀에 걸릴 시간")
    parser.add_argument("--no-home", action="store_true", help="에피소드 후 홈 복귀를 하지 않는다")
    args, passthrough = parser.parse_known_args()

    install(args)

    # 남은 인자는 lerobot_record 가 draccus 로 직접 파싱한다.
    sys.argv = ["lerobot_record", *passthrough]
    rec.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
