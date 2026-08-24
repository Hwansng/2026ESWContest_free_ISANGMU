"""Read-only validation for the HazardBot red/yellow LeRobot dataset."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.act_collection_plan import TASK, load_or_build_plan, verify_plan


WRIST_KEY = "observation.images.wrist"
STATE_KEY = "observation.state"
ACTION_KEY = "action"


def _error(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _check_nonempty_file(path: Path, code: str, errors: list[dict[str, str]]) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        errors.append(_error(code, f"missing or empty file: {path}"))


def _decode_episode_samples(dataset: object) -> int:
    import torch

    decoded = 0
    for episode_index in range(dataset.meta.total_episodes):
        start = int(dataset.meta.episodes["dataset_from_index"][episode_index])
        stop = int(dataset.meta.episodes["dataset_to_index"][episode_index])
        if stop <= start:
            raise ValueError(f"episode {episode_index} has no frames")
        sample_indices = sorted({start, (start + stop - 1) // 2, stop - 1})
        for sample_index in sample_indices:
            frame = dataset[sample_index][WRIST_KEY]
            if frame.numel() == 0 or not bool(torch.isfinite(frame).all()):
                raise ValueError(f"invalid wrist frame at dataset index {sample_index}")
            decoded += 1
    return decoded


def _validate_episodes(
    dataset_root: Path,
    info: dict[str, object],
    errors: list[dict[str, str]],
) -> None:
    total_episodes = info.get("total_episodes")
    if not isinstance(total_episodes, int) or total_episodes < 0:
        errors.append(_error("invalid_total_episodes", f"invalid total_episodes: {total_episodes}"))
        return
    if total_episodes == 0:
        return

    try:
        import pandas as pd

        episode_files = sorted((dataset_root / "meta" / "episodes").rglob("*.parquet"))
        if not episode_files:
            raise FileNotFoundError("no episode parquet files")
        episodes = pd.concat((pd.read_parquet(path) for path in episode_files), ignore_index=True).to_dict(
            orient="records"
        )
    except Exception as exception:
        errors.append(_error("missing_episode_metadata", f"cannot load episode metadata: {exception}"))
        return

    if len(episodes) != total_episodes:
        errors.append(
            _error(
                "episode_count_mismatch",
                f"info declares {total_episodes} episodes but metadata has {len(episodes)}",
            )
        )

    data_template = info.get("data_path")
    video_template = info.get("video_path")
    previous_stop = 0
    checked_files: set[Path] = set()
    fps = info.get("fps") if isinstance(info.get("fps"), int) else 30
    for expected_index, episode in enumerate(episodes):
        episode_index = int(episode["episode_index"])
        start = int(episode["dataset_from_index"])
        stop = int(episode["dataset_to_index"])
        length = int(episode.get("length", stop - start))
        if episode_index != expected_index:
            errors.append(
                _error(
                    "episode_index_gap",
                    f"expected episode index {expected_index}, found {episode_index}",
                )
            )
        if start != previous_stop:
            errors.append(
                _error(
                    "frame_index_gap",
                    f"episode {episode_index} starts at {start}, expected {previous_stop}",
                )
            )
        if length <= 0 or stop - start != length:
            errors.append(_error("invalid_episode_length", f"episode {episode_index} has invalid length"))
        elif length / fps > 35.0:
            errors.append(
                _error(
                    "episode_too_long",
                    f"episode {episode_index} is {length / fps:.2f}s; maximum is 35.00s",
                )
            )
        previous_stop = stop

        if isinstance(data_template, str):
            data_path = dataset_root / data_template.format(
                chunk_index=int(episode["data/chunk_index"]),
                file_index=int(episode["data/file_index"]),
            )
            if data_path not in checked_files:
                _check_nonempty_file(data_path, "missing_data_file", errors)
                checked_files.add(data_path)
        else:
            errors.append(_error("invalid_data_path", "info.json has no data_path template"))

        if isinstance(video_template, str):
            video_path = dataset_root / video_template.format(
                video_key=WRIST_KEY,
                chunk_index=int(episode[f"videos/{WRIST_KEY}/chunk_index"]),
                file_index=int(episode[f"videos/{WRIST_KEY}/file_index"]),
            )
            if video_path not in checked_files:
                _check_nonempty_file(video_path, "missing_video_file", errors)
                checked_files.add(video_path)
        else:
            errors.append(_error("invalid_video_path", "info.json has no video_path template"))

    total_frames = info.get("total_frames")
    if isinstance(total_frames, int) and previous_stop != total_frames:
        errors.append(
            _error(
                "total_frames_mismatch",
                f"last episode stops at {previous_stop}, info declares {total_frames}",
            )
        )

    _validate_raw_data_row_count(dataset_root, total_frames, errors)


def _validate_raw_data_row_count(
    dataset_root: Path,
    total_frames: object,
    errors: list[dict[str, str]],
) -> None:
    """Metadata surgery (dropping episodes) only edits meta/episodes + info.json and leaves the
    underlying data/*.parquet bytes untouched by design. If those leftover "ghost" rows are never
    physically removed, an unfiltered LeRobotDataset load concatenates them back in anyway (they
    carry a real, in-range episode_index), shifting every later row's position and desyncing
    row-position from the declared per-episode index ranges. check_act_dataset previously only
    checked meta/episodes bookkeeping, which stayed self-consistent even while this was silently
    broken (found 2026-08-26: 7634 leftover rows across 3 files after a same-day episode-drop
    surgery). Count actual rows on disk to catch this class of bug directly.
    """
    if not isinstance(total_frames, int):
        return
    try:
        import pandas as pd

        data_files = sorted((dataset_root / "data").rglob("*.parquet"))
        actual_rows = sum(pd.read_parquet(f, columns=["index"]).shape[0] for f in data_files)
    except Exception as exception:
        errors.append(_error("raw_data_scan_failed", f"cannot count raw data rows: {exception}"))
        return
    if actual_rows != total_frames:
        errors.append(
            _error(
                "raw_data_row_count_mismatch",
                f"data/*.parquet contains {actual_rows} rows but info declares {total_frames}; "
                "likely leftover ghost rows from a prior episode-drop surgery that only edited "
                "meta/episodes without removing the underlying data rows",
            )
        )


def _validate_collection_metadata(
    dataset_root: Path,
    repo_id: str,
    total_episodes: object,
    require_complete: bool,
    errors: list[dict[str, str]],
) -> None:
    collection_dir = dataset_root / "collection"
    protocol_path = collection_dir / "protocol.json"
    plan_path = collection_dir / "plan.csv"

    if protocol_path.is_file():
        try:
            protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exception:
            errors.append(_error("invalid_protocol", f"cannot read {protocol_path}: {exception}"))
        else:
            expected = {
                "repo_id": repo_id,
                "task": TASK,
                "fps": 30,
                "image_key": WRIST_KEY,
                "total_episodes": 100,
                "episode_time_s": 35,
                "reset_time_s": 60,
            }
            for key, expected_value in expected.items():
                if protocol.get(key) != expected_value:
                    code = "unexpected_repo_id" if key == "repo_id" else "protocol_mismatch"
                    errors.append(
                        _error(
                            code,
                            f"protocol {key} is {protocol.get(key)!r}; expected {expected_value!r}",
                        )
                    )
    elif plan_path.is_file() or require_complete:
        errors.append(_error("missing_protocol", f"missing collection protocol: {protocol_path}"))

    if plan_path.is_file():
        rows = load_or_build_plan(dataset_root)
        errors.extend(verify_plan(rows, require_complete=require_complete))
        recorded_rows = sum(row["status"] == "recorded" for row in rows)
        if isinstance(total_episodes, int) and recorded_rows != total_episodes:
            errors.append(
                _error(
                    "plan_episode_count_mismatch",
                    f"plan has {recorded_rows} recorded rows; dataset has {total_episodes} episodes",
                )
            )
    elif require_complete:
        errors.append(_error("missing_collection_plan", f"missing collection plan: {plan_path}"))

    if require_complete and total_episodes != 100:
        errors.append(
            _error(
                "dataset_incomplete",
                f"expected 100 episodes, found {total_episodes}",
            )
        )


def _load_dataset(repo_id: str, dataset_root: Path) -> object:
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    return LeRobotDataset(
        repo_id,
        root=dataset_root,
        download_videos=False,
    )


def validate_dataset(
    dataset_root: Path,
    repo_id: str,
    mode: str = "full",
    require_complete: bool = False,
) -> dict[str, object]:
    dataset_root = Path(dataset_root)
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    info_path = dataset_root / "meta" / "info.json"
    info: dict[str, object] = {}

    if mode not in {"metadata", "full"}:
        raise ValueError(f"mode must be 'metadata' or 'full': {mode}")

    if not info_path.is_file():
        errors.append(_error("missing_meta_info", f"missing LeRobot metadata: {info_path}"))
    else:
        try:
            info = json.loads(info_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exception:
            errors.append(_error("invalid_meta_info", f"cannot read {info_path}: {exception}"))

    if info:
        if info.get("fps") != 30:
            errors.append(_error("unexpected_fps", f"expected 30 FPS, found {info.get('fps')}"))
        features = info.get("features")
        if not isinstance(features, dict):
            features = {}
            errors.append(_error("invalid_features", "features must be a JSON object"))
        if WRIST_KEY not in features:
            errors.append(_error("missing_wrist_camera", f"missing feature: {WRIST_KEY}"))
        if STATE_KEY not in features:
            errors.append(_error("missing_observation_state", f"missing feature: {STATE_KEY}"))
        if ACTION_KEY not in features:
            errors.append(_error("missing_action", f"missing feature: {ACTION_KEY}"))
        _validate_episodes(dataset_root, info, errors)
        _validate_collection_metadata(
            dataset_root,
            repo_id,
            info.get("total_episodes"),
            require_complete,
            errors,
        )

    decoded_episode_samples = 0
    if mode == "full" and info and not errors:
        try:
            dataset = _load_dataset(repo_id, dataset_root)
        except Exception as exception:
            errors.append(_error("dataset_load_failed", f"LeRobot dataset load failed: {exception}"))
        else:
            try:
                decoded_episode_samples = _decode_episode_samples(dataset)
            except Exception as exception:
                errors.append(_error("frame_decode_failed", f"camera frame decode failed: {exception}"))

    return {
        "ok": not errors,
        "dataset_root": str(dataset_root.resolve()),
        "repo_id": repo_id,
        "fps": info.get("fps"),
        "total_episodes": info.get("total_episodes"),
        "errors": errors,
        "warnings": warnings,
        "decoded_episode_samples": decoded_episode_samples,
        "require_complete": require_complete,
    }


def _write_json_report(path: Path, report: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--repo-id", required=True)
    parser.add_argument("--mode", choices=("metadata", "full"), default="full")
    parser.add_argument("--require-complete", action="store_true")
    parser.add_argument("--json-stdout", action="store_true")
    parser.add_argument("--json-report", type=Path)
    return parser


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = _build_parser().parse_args()
    report = validate_dataset(
        args.dataset_root,
        args.repo_id,
        mode=args.mode,
        require_complete=args.require_complete,
    )
    if args.json_report is not None:
        _write_json_report(args.json_report, report)

    summary = (
        f"ACT 데이터셋 검사: {'통과' if report['ok'] else '실패'} "
        f"(에피소드 {report['total_episodes']}, 오류 {len(report['errors'])})"
    )
    if args.json_stdout:
        print(summary, file=sys.stderr)
        print(json.dumps(report, ensure_ascii=False))
    else:
        print(summary)
        for error in report["errors"]:
            print(f"- {error['code']}: {error['message']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
