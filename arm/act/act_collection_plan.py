"""Balanced collection-plan management for the red/yellow ACT dataset."""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import Counter
from pathlib import Path


COLORS = ("red", "yellow")
POSITIONS = ("center", "front_left", "front_right", "rear_left", "rear_right")
PLAN_FIELDS = ("batch", "slot", "color", "position", "status", "episode_index", "recorded_at", "note")
REPO_ID = "local/hazardbot_red_yellow_act_v1"
TASK = "Pick up the hazardous object, place it in the isolation bin, and close the lid."


def build_plan(seed: int = 20260816) -> list[dict[str, str]]:
    rng = random.Random(seed)
    rows: list[dict[str, str]] = []
    for batch in range(1, 11):
        combinations = [(color, position) for color in COLORS for position in POSITIONS]
        rng.shuffle(combinations)
        for slot, (color, position) in enumerate(combinations, start=1):
            rows.append(
                {
                    "batch": str(batch),
                    "slot": str(slot),
                    "color": color,
                    "position": position,
                    "status": "pending",
                    "episode_index": "",
                    "recorded_at": "",
                    "note": "",
                }
            )
    return rows


def _plan_path(dataset_root: Path) -> Path:
    return dataset_root / "collection" / "plan.csv"


def _protocol() -> dict[str, object]:
    return {
        "schema_version": 1,
        "seed": 20260816,
        "repo_id": REPO_ID,
        "task": TASK,
        "fps": 30,
        "image_key": "observation.images.wrist",
        "total_episodes": 100,
        "episode_time_s": 35,
        "reset_time_s": 60,
    }


def load_or_build_plan(dataset_root: Path) -> list[dict[str, str]]:
    path = _plan_path(Path(dataset_root))
    if not path.is_file():
        return build_plan()
    with path.open("r", encoding="utf-8", newline="") as stream:
        return [dict(row) for row in csv.DictReader(stream)]


def get_batch_status(rows: list[dict[str, str]], batch: int) -> dict[str, object]:
    if batch not in range(1, 11):
        raise ValueError(f"batch must be between 1 and 10: {batch}")
    batch_rows = sorted(
        (row for row in rows if int(row["batch"]) == batch),
        key=lambda row: int(row["slot"]),
    )
    if len(batch_rows) != 10:
        raise ValueError(f"batch {batch} must contain exactly 10 rows")
    remaining = sum(row["status"] == "pending" for row in batch_rows)
    return {
        "batch": batch,
        "recorded": 10 - remaining,
        "remaining": remaining,
        "rows": batch_rows,
    }


def verify_plan(rows: list[dict[str, str]], require_complete: bool = False) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if len(rows) != 100:
        errors.append({"code": "plan_row_count", "message": f"expected 100 rows, found {len(rows)}"})
        return errors

    expected_combinations = Counter((color, position) for color in COLORS for position in POSITIONS)
    for batch in range(1, 11):
        batch_rows = [row for row in rows if row.get("batch") == str(batch)]
        combinations = Counter((row.get("color"), row.get("position")) for row in batch_rows)
        if combinations != expected_combinations:
            errors.append(
                {
                    "code": "batch_balance",
                    "message": f"batch {batch} does not contain each color-position combination once",
                }
            )

    recorded_indices: list[int] = []
    for row_number, row in enumerate(rows, start=1):
        if row.get("status") not in {"pending", "recorded"}:
            errors.append({"code": "invalid_status", "message": f"row {row_number} has invalid status"})
        if row.get("status") == "recorded":
            try:
                recorded_indices.append(int(row.get("episode_index", "")))
            except ValueError:
                errors.append(
                    {"code": "invalid_episode_index", "message": f"row {row_number} has no episode index"}
                )

    if sorted(recorded_indices) != list(range(len(recorded_indices))):
        errors.append(
            {
                "code": "episode_index_sequence",
                "message": "recorded episode indices must be unique and consecutive from zero",
            }
        )
    if require_complete and len(recorded_indices) != 100:
        errors.append(
            {
                "code": "plan_incomplete",
                "message": f"expected 100 recorded rows, found {len(recorded_indices)}",
            }
        )
    return errors


def _write_plan(dataset_root: Path, rows: list[dict[str, str]]) -> None:
    collection_dir = dataset_root / "collection"
    collection_dir.mkdir(parents=True, exist_ok=True)
    path = _plan_path(dataset_root)
    temporary_path = path.with_suffix(".csv.tmp")
    with temporary_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=PLAN_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    temporary_path.replace(path)


def _write_protocol(dataset_root: Path) -> None:
    path = dataset_root / "collection" / "protocol.json"
    temporary_path = path.with_suffix(".json.tmp")
    temporary_path.write_text(
        json.dumps(_protocol(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)


def mark_recorded(
    dataset_root: Path,
    batch: int,
    count: int,
    first_episode_index: int,
    recorded_at: str,
) -> list[dict[str, str]]:
    dataset_root = Path(dataset_root)
    if not (dataset_root / "meta" / "info.json").is_file():
        raise ValueError(f"LeRobot metadata is missing: {dataset_root / 'meta' / 'info.json'}")
    if count < 0:
        raise ValueError(f"count must not be negative: {count}")
    if first_episode_index < 0:
        raise ValueError(f"first episode index must not be negative: {first_episode_index}")

    rows = load_or_build_plan(dataset_root)
    status = get_batch_status(rows, batch)
    pending_rows = [row for row in status["rows"] if row["status"] == "pending"]
    if count > len(pending_rows):
        raise ValueError(f"batch {batch} has only {len(pending_rows)} pending rows")

    assigned_indices = {
        int(row["episode_index"])
        for row in rows
        if row["status"] == "recorded" and row["episode_index"]
    }
    new_indices = list(range(first_episode_index, first_episode_index + count))
    collision = next((index for index in new_indices if index in assigned_indices), None)
    if collision is not None:
        raise ValueError(f"episode index {collision} is already recorded")

    for row, episode_index in zip(pending_rows[:count], new_indices, strict=True):
        row["status"] = "recorded"
        row["episode_index"] = str(episode_index)
        row["recorded_at"] = recorded_at

    _write_plan(dataset_root, rows)
    _write_protocol(dataset_root)
    return rows


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    status_parser = subparsers.add_parser("status", help="show one batch without writing files")
    status_parser.add_argument("--dataset-root", type=Path, required=True)
    status_parser.add_argument("--batch", type=int, required=True)

    mark_parser = subparsers.add_parser("mark-recorded", help="mark the next pending rows as recorded")
    mark_parser.add_argument("--dataset-root", type=Path, required=True)
    mark_parser.add_argument("--batch", type=int, required=True)
    mark_parser.add_argument("--count", type=int, required=True)
    mark_parser.add_argument("--first-episode-index", type=int, required=True)
    mark_parser.add_argument("--recorded-at", required=True)

    verify_parser = subparsers.add_parser("verify", help="validate collection-plan structure")
    verify_parser.add_argument("--dataset-root", type=Path, required=True)
    verify_parser.add_argument("--require-complete", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        if args.command == "status":
            result = get_batch_status(load_or_build_plan(args.dataset_root), args.batch)
        elif args.command == "mark-recorded":
            rows = mark_recorded(
                args.dataset_root,
                args.batch,
                args.count,
                args.first_episode_index,
                args.recorded_at,
            )
            result = get_batch_status(rows, args.batch)
        else:
            errors = verify_plan(load_or_build_plan(args.dataset_root), args.require_complete)
            result = {"ok": not errors, "errors": errors}
            print(json.dumps(result, ensure_ascii=False))
            return 0 if result["ok"] else 1
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
