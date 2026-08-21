"""USB 카메라 인식·식별·동시 대역폭 검증.

lerobot-find-cameras 는 카메라를 열자마자 프레임을 잡는다. UVC 카메라는 자동노출이
안정되기까지 수십 프레임이 걸리므로 첫 프레임이 검게 나오는 것이 정상이다.
이 도구는 **워밍업 후** 캡처하고, 데이터 수집에서 실제로 문제가 되는
**2대 동시 캡처 대역폭**을 측정한다.

왜 대역폭이 중요한가 (카메라 문서 §3):
    데이터 수집 시 노트북 한 대에 USB 카메라 2대 + 서보 어댑터 2대가 동시에 물린다.
    UVC 카메라 2대를 같은 USB 컨트롤러에서 640x480/30fps 로 돌리면 대역폭이 모자랄 수 있다.
    수집 당일에 알면 대처가 늦다 (전원 공급 허브 구매 = 또 리드타임).

사용법:
    # 각 인덱스를 워밍업 후 캡처. 어느 인덱스가 어느 카메라인지 식별할 때
    python tools/check_cameras.py --list

    # 지원 해상도 탐색 (기종 구분용 — Innomaker 720P vs SO-ARM 2MP)
    python tools/check_cameras.py --probe

    # 두 카메라 동시 캡처하며 실측 FPS. 데이터 수집 전 필수
    python tools/check_cameras.py --bandwidth 1 2
"""

import argparse
import time
from pathlib import Path

import cv2

WARMUP_FRAMES = 40      # 자동노출·화이트밸런스가 안정될 때까지 버리는 프레임 수
MAX_INDEX = 5
OUT_DIR = Path(__file__).resolve().parent.parent / "outputs" / "camera_check"

# 데이터 수집에 쓸 캡처 설정 (카메라 문서 §3)
CAP_W, CAP_H, CAP_FPS = 640, 480, 30

# 기종 구분용. Innomaker U20CAM-720P 는 720p, SO-ARM 2MP 는 1080p 까지 지원한다.
PROBE_RESOLUTIONS = [(640, 480), (1280, 720), (1920, 1080)]


def _open(index: int) -> cv2.VideoCapture:
    # Windows 에서는 DSHOW 가 MSMF 보다 안정적이다 (MSMF 는 open 이 수 초 걸리는 경우가 있음).
    return cv2.VideoCapture(index, cv2.CAP_DSHOW)


def _save(path: Path, frame) -> bool:
    """🔴 cv2.imwrite 는 **비 ASCII 경로에서 조용히 실패한다** (반환값 False, 예외 없음).

    이 저장소 경로에 「바탕 화면」이 들어 있어 실제로 한 장도 저장되지 않고 있었다
    (2026-08-14 발견). imencode 로 메모리에 인코딩한 뒤 파이썬으로 쓰면 경로 인코딩과 무관하다.
    """
    ok, buf = cv2.imencode(path.suffix, frame)
    if not ok:
        return False
    path.write_bytes(buf.tobytes())
    return True


def list_cameras() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"인덱스 0~{MAX_INDEX - 1} 를 워밍업({WARMUP_FRAMES}프레임) 후 캡처한다.\n")
    print(f"{'idx':<5}{'상태':<10}{'해상도':<12}{'평균밝기':>10}{'표준편차':>10}   판정")
    print("-" * 70)

    found = 0
    for idx in range(MAX_INDEX):
        cap = _open(idx)
        if not cap.isOpened():
            cap.release()
            continue
        found += 1

        frame = None
        for _ in range(WARMUP_FRAMES):
            ok, f = cap.read()
            if ok:
                frame = f
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()

        if frame is None:
            print(f"{idx:<5}{'열림':<10}{f'{w}x{h}':<12}{'-':>10}{'-':>10}   🔴 프레임 없음")
            continue

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        mean, std = float(gray.mean()), float(gray.std())

        # 표준편차가 거의 0 이면 균일한 화면이다 = 신호 없음.
        # 어둡기만 한 것(렌즈 가림)은 노이즈 때문에 std 가 살아 있다.
        if std < 1.0:
            verdict = "🔴 균일 화면 — 신호 없음"
        elif mean < 12:
            verdict = "⚠ 매우 어두움 — 렌즈 가림/조명 확인"
        elif mean > 240:
            verdict = "⚠ 포화 — 조명 과다"
        else:
            verdict = "✅ 정상"

        path = OUT_DIR / f"cam{idx}.png"
        if not _save(path, frame):
            verdict += "  (⚠ 저장 실패)"
        print(f"{idx:<5}{'열림':<10}{f'{w}x{h}':<12}{mean:>10.1f}{std:>10.1f}   {verdict}")

    print(f"\n{found}개 열림. 이미지: {OUT_DIR}")
    print("→ 이미지를 열어 어느 인덱스가 손목/프론트/내장인지 확인할 것.")
    print("   손목  = 물체에 바짝 붙은 근접 화면. 팔을 움직이면 같이 움직인다")
    print("   프론트 = 작업대 전체가 보이는 넓은 화면 (유일하게 720p 까지만 지원)")
    print("   내장  = 노트북 앞쪽 장면. 셔터로 막혀 있으면 **까만 화면에 카메라 금지 아이콘**")
    return 0 if found else 1


def probe() -> int:
    print("각 인덱스가 지원하는 해상도를 탐색한다 (기종 구분용).\n")
    for idx in range(MAX_INDEX):
        cap = _open(idx)
        if not cap.isOpened():
            cap.release()
            continue
        supported = []
        for w, h in PROBE_RESOLUTIONS:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
            aw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            ah = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            if (aw, ah) == (w, h):
                supported.append(f"{w}x{h}")
        cap.release()
        print(f"  인덱스 {idx}: {', '.join(supported) if supported else '없음'}")

    print("\n참고: Innomaker U20CAM-720P → 1280x720 까지 / SO-ARM 2MP → 1920x1080 까지")
    print("🔴 해상도만으로는 손목과 내장을 못 가른다 — **노트북 내장도 1080p** 다.")
    print("   720p 인 것이 프론트라는 것만 확실하고, 나머지 둘은 --list 의 이미지를 봐야 한다.")
    return 0


def bandwidth(indices: list[int], seconds: float) -> int:
    print(f"인덱스 {indices} 를 {CAP_W}x{CAP_H}/{CAP_FPS}fps 로 **동시** 캡처한다.")
    print(f"{seconds:.0f}초간 측정.\n")

    caps = {}
    for idx in indices:
        cap = _open(idx)
        if not cap.isOpened():
            print(f"🔴 인덱스 {idx} 를 열 수 없다.")
            for c in caps.values():
                c.release()
            return 1
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAP_W)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAP_H)
        cap.set(cv2.CAP_PROP_FPS, CAP_FPS)
        caps[idx] = cap

    for idx, cap in caps.items():
        aw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        ah = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f"  인덱스 {idx}: 설정 결과 {aw}x{ah}")
        if (aw, ah) != (CAP_W, CAP_H):
            print(f"    ⚠ 요청한 {CAP_W}x{CAP_H} 가 아니다. 대역폭 제약일 수 있다.")

    # 워밍업
    for _ in range(WARMUP_FRAMES):
        for cap in caps.values():
            cap.read()

    counts = {idx: 0 for idx in indices}
    fails = {idx: 0 for idx in indices}
    start = time.perf_counter()
    while (elapsed := time.perf_counter() - start) < seconds:
        for idx, cap in caps.items():
            ok, _ = cap.read()
            if ok:
                counts[idx] += 1
            else:
                fails[idx] += 1

    for cap in caps.values():
        cap.release()

    print(f"\n{elapsed:.1f}초 측정 결과")
    print(f"{'idx':<6}{'프레임':>9}{'실측 FPS':>11}{'실패':>8}   판정")
    print("-" * 52)
    ok_all = True
    for idx in indices:
        fps = counts[idx] / elapsed
        if fails[idx] > 0:
            verdict = "🔴 읽기 실패 발생"
            ok_all = False
        elif fps < CAP_FPS * 0.8:
            verdict = f"🔴 목표 {CAP_FPS}fps 의 80% 미만"
            ok_all = False
        elif fps < CAP_FPS * 0.95:
            verdict = "⚠ 약간 미달"
        else:
            verdict = "✅"
        print(f"{idx:<6}{counts[idx]:>9}{fps:>11.1f}{fails[idx]:>8}   {verdict}")

    print()
    if ok_all:
        print(f"✅ {len(indices)}대 동시 캡처에 대역폭 여유가 있다. 데이터 수집을 진행해도 된다.")
        return 0

    print("🔴 대역폭 부족. 대처 순서:")
    print("   1. 두 카메라를 **서로 다른 USB 컨트롤러**에 꽂는다 (노트북 좌/우 포트를 나눠 쓴다)")
    print("   2. 그래도 안 되면 **전원 공급 USB 허브** (조달 필요 — 리드타임 고려)")
    print("   3. 최후에 캡처 해상도 하향 — 단 정책 입력 해상도를 먼저 조정할 것 (카메라 문서 §3)")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true", help="워밍업 후 각 인덱스 캡처")
    parser.add_argument("--probe", action="store_true", help="지원 해상도 탐색")
    parser.add_argument("--bandwidth", nargs="+", type=int, metavar="IDX",
                        help="인덱스 1개 이상 동시 캡처 FPS 측정")
    parser.add_argument("--seconds", type=float, default=15.0)
    args = parser.parse_args()

    if args.probe:
        return probe()
    if args.bandwidth:
        return bandwidth(args.bandwidth, args.seconds)
    return list_cameras()


if __name__ == "__main__":
    raise SystemExit(main())
