import unittest
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.act_collection_plan import build_plan, get_batch_status, load_or_build_plan, mark_recorded, verify_plan


class CollectionPlanTests(unittest.TestCase):
    def test_plan_is_deterministic_and_balanced(self):
        first = build_plan()
        second = build_plan()

        self.assertEqual(first, second)
        self.assertEqual(len(first), 100)
        self.assertEqual(Counter(row["color"] for row in first), {"red": 50, "yellow": 50})
        self.assertEqual(
            Counter((row["color"], row["position"]) for row in first),
            {
                (color, position): 10
                for color in ("red", "yellow")
                for position in ("center", "front_left", "front_right", "rear_left", "rear_right")
            },
        )
        for batch in range(1, 11):
            rows = [row for row in first if int(row["batch"]) == batch]
            self.assertEqual(len(rows), 10)
            self.assertEqual(len({(row["color"], row["position"]) for row in rows}), 10)

    def test_mark_recorded_updates_only_next_pending_rows(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "meta").mkdir()
            (root / "meta" / "info.json").write_text("{}", encoding="utf-8")

            mark_recorded(
                root,
                batch=3,
                count=4,
                first_episode_index=20,
                recorded_at="2026-08-24T21:00:00+09:00",
            )

            rows = load_or_build_plan(root)
            batch_rows = [row for row in rows if row["batch"] == "3"]
            self.assertEqual([row["status"] for row in batch_rows], ["recorded"] * 4 + ["pending"] * 6)
            self.assertEqual([row["episode_index"] for row in batch_rows[:4]], ["20", "21", "22", "23"])
            self.assertEqual(get_batch_status(rows, 3)["remaining"], 6)
            self.assertTrue((root / "collection" / "protocol.json").is_file())

    def test_mark_recorded_rejects_episode_index_collision(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "meta").mkdir()
            (root / "meta" / "info.json").write_text("{}", encoding="utf-8")
            mark_recorded(root, 1, 2, 0, "2026-08-24T21:00:00+09:00")

            with self.assertRaisesRegex(ValueError, "episode index 1"):
                mark_recorded(root, 2, 1, 1, "2026-08-24T21:01:00+09:00")

    def test_verify_plan_requires_all_rows_only_for_complete_mode(self):
        rows = build_plan()
        self.assertEqual(verify_plan(rows), [])
        self.assertEqual(verify_plan(rows, require_complete=True)[0]["code"], "plan_incomplete")

        for episode_index, row in enumerate(rows):
            row["status"] = "recorded"
            row["episode_index"] = str(episode_index)
            row["recorded_at"] = "2026-08-24T21:00:00+09:00"
        self.assertEqual(verify_plan(rows, require_complete=True), [])

    def test_status_cli_prints_json_without_creating_collection_files(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "act_collection_plan.py"),
                    "status",
                    "--dataset-root",
                    str(root),
                    "--batch",
                    "1",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(result.stdout.strip(), "status must print a JSON object")
            status = json.loads(result.stdout)
            self.assertEqual(status["remaining"], 10)
            self.assertFalse((root / "collection").exists())


if __name__ == "__main__":
    unittest.main()
