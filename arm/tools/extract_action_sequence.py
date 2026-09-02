"""검증된 에피소드에서 실제 서보에 보낸 액션 시퀀스를 뽑아 RPi 재생용 JSON으로 저장한다.

2026-08-29 — RPi 실물 추론이 청크 경계마다 ~1초씩 멎는 문제
(docs/02_schedule/RPi_ACT_ROS2통합_시도기록_2026-08-29.md 참고)를 우회하기 위해,
"노트북에서 검증된 성공 에피소드를 그대로 재생"하는 방식을 시도한다.

🔴 이건 더 이상 폐루프 정책이 아니라 개루프 재생이다. 물체 위치·각도가 녹화 당시와
   실질적으로 같아야만 성공한다 — 다르면 대응 없이 그대로 실패한다.

🔵 값 형식 — 실측 확인함(episode 5): action 값은 raw tick(0~4095)이 아니라
   LeRobot 정규화 공간(캘리브레이션 기준 대략 ±100, gripper는 0~100)이다.
   그래서 재생 쪽은 반드시 robot.send_action()(SO101Follower 의 자체 변환 로직)을
   거쳐야 한다 — 값을 직접 서보 틱으로 손대서 보내면 안 된다.

🔵 파일 구조 — 실측 확인함: 이 데이터셋(v3.0)은 에피소드 1개당 parquet 파일 1개다
   (data/chunk-000/file-{episode_index:03d}.parquet). LeRobotDataset 클래스를
   거치지 않고 pandas 로 직접 읽는다 — 비디오 디코딩 등 불필요한 의존성을 피한다.

사용법:
    python tools/extract_action_sequence.py --episode 5 --out C:\\ACT_data\\replay\\ep5_near_success.json

episode 5 = 30회 검증 trial 2(세트1) = yellow, rear_right(근거리), 성공 기록됨
(rollout_plan.csv 매핑 + 세트1 실패 목록에 없음으로 확인).
"""
import argparse
import json
from pathlib import Path

import pandas as pd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=r"C:\ACT_data\eval_hazardbot_act_v1")
    ap.add_argument("--episode", type=int, required=True, help="추출할 에피소드 인덱스")
    ap.add_argument("--out", required=True, help="저장할 JSON 경로")
    args = ap.parse_args()

    root = Path(args.root)
    info = json.loads((root / "meta" / "info.json").read_text(encoding="utf-8"))
    fps = info["fps"]
    motor_names = info["features"]["action"]["names"]

    data_file = root / "data" / "chunk-000" / f"file-{args.episode:03d}.parquet"
    if not data_file.exists():
        raise SystemExit(f"파일 없음: {data_file} — 에피소드 번호 확인할 것")

    df = pd.read_parquet(data_file)
    if not (df["episode_index"] == args.episode).all():
        raise SystemExit(
            f"파일명({data_file.name})과 실제 episode_index 불일치 — "
            f"파일-에피소드 1:1 매핑 가정이 이 데이터셋에서 깨졌을 수 있다. 직접 확인할 것."
        )
    df = df.sort_values("frame_index")

    sequence = [
        {name: float(v) for name, v in zip(motor_names, row)}
        for row in df["action"].tolist()
    ]

    out = {
        "fps": fps,
        "motor_names": motor_names,
        "num_frames": len(sequence),
        "source_episode": args.episode,
        "source_root": str(root),
        "note": "개루프 재생용. robot.send_action() 으로만 보낼 것 — 값이 raw tick 아님(정규화 공간).",
        "actions": sequence,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"저장 완료: {out_path} ({len(sequence)} 프레임, {fps}fps, {len(sequence)/fps:.1f}초)")


if __name__ == "__main__":
    main()
