import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.check_act_dataset import _decode_episode_samples, validate_dataset
from tools.act_collection_plan import mark_recorded


REPO_ID = "local/hazardbot_red_yellow_act_v1"
VALID_FEATURES = {
    "observation.images.wrist": {"dtype": "video", "shape": [480, 640, 3]},
    "observation.state": {"dtype": "float32", "shape": [6]},
    "action": {"dtype": "float32", "shape": [6]},
}


class DatasetValidatorTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def write_info(self, fps=30, total_episodes=0, total_frames=0, features=None):
        info = {
            "codebase_version": "v3.0",
            "robot_type": "so101_follower",
            "fps": fps,
            "total_episodes": total_episodes,
            "total_frames": total_frames,
            "features": features if features is not None else {},
            "data_path": "data/chunk-{chunk_index:03d}/file-{file_index:03d}.parquet",
            "video_path": "videos/{video_key}/chunk-{chunk_index:03d}/file-{file_index:03d}.mp4",
        }
        (self.root / "meta").mkdir(parents=True, exist_ok=True)
        (self.root / "meta" / "info.json").write_text(
            json.dumps(info),
            encoding="utf-8",
        )

    def write_episodes(self, rows):
        from datasets import Dataset
        from lerobot.datasets.utils import write_episodes

        write_episodes(Dataset.from_list(rows), self.root)

    def write_valid_single_episode_dataset(self):
        self.write_info(total_episodes=1, total_frames=600, features=VALID_FEATURES)
        self.write_episodes([self.episode(0, 0, 600)])
        data_file = self.root / "data" / "chunk-000" / "file-000.parquet"
        video_file = self.root / "videos" / "observation.images.wrist" / "chunk-000" / "file-000.mp4"
        data_file.parent.mkdir(parents=True)
        video_file.parent.mkdir(parents=True)
        data_file.write_bytes(b"data")
        video_file.write_bytes(b"video")

    @staticmethod
    def episode(episode_index, start, stop):
        return {
            "episode_index": episode_index,
            "length": stop - start,
            "dataset_from_index": start,
            "dataset_to_index": stop,
            "data/chunk_index": 0,
            "data/file_index": 0,
            "videos/observation.images.wrist/chunk_index": 0,
            "videos/observation.images.wrist/file_index": 0,
        }

    def test_missing_info_is_rejected(self):
        report = validate_dataset(self.root, REPO_ID, mode="metadata")

        self.assertFalse(report["ok"])
        self.assertIn("missing_meta_info", [error["code"] for error in report["errors"]])

    def test_wrong_fps_and_missing_features_are_rejected(self):
        self.write_info(fps=15)

        report = validate_dataset(self.root, REPO_ID, mode="metadata")

        codes = {error["code"] for error in report["errors"]}
        self.assertIn("unexpected_fps", codes)
        self.assertIn("missing_wrist_camera", codes)
        self.assertIn("missing_action", codes)
        self.assertIn("missing_observation_state", codes)

    def test_episode_gap_and_excess_duration_are_rejected(self):
        episodes = [self.episode(0, 0, 901), self.episode(2, 901, 2101)]
        self.write_info(total_episodes=2, total_frames=2101, features=VALID_FEATURES)
        self.write_episodes(episodes)
        data_file = self.root / "data" / "chunk-000" / "file-000.parquet"
        video_file = self.root / "videos" / "observation.images.wrist" / "chunk-000" / "file-000.mp4"
        data_file.parent.mkdir(parents=True)
        video_file.parent.mkdir(parents=True)
        data_file.write_bytes(b"data")
        video_file.write_bytes(b"video")

        report = validate_dataset(self.root, REPO_ID, mode="metadata")

        codes = {error["code"] for error in report["errors"]}
        self.assertIn("episode_index_gap", codes)
        self.assertIn("episode_too_long", codes)

    def test_missing_episode_data_and_video_files_are_rejected(self):
        self.write_info(total_episodes=1, total_frames=600, features=VALID_FEATURES)
        self.write_episodes([self.episode(0, 0, 600)])

        report = validate_dataset(self.root, REPO_ID, mode="metadata")

        codes = {error["code"] for error in report["errors"]}
        self.assertIn("missing_data_file", codes)
        self.assertIn("missing_video_file", codes)

    def test_protocol_repo_id_mismatch_is_rejected(self):
        self.write_valid_single_episode_dataset()
        mark_recorded(self.root, 1, 1, 0, "2026-08-24T21:00:00+09:00")
        protocol_path = self.root / "collection" / "protocol.json"
        protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
        protocol["repo_id"] = "local/wrong_dataset"
        protocol_path.write_text(json.dumps(protocol), encoding="utf-8")

        report = validate_dataset(self.root, REPO_ID, mode="metadata")

        self.assertIn("unexpected_repo_id", {error["code"] for error in report["errors"]})

    def test_complete_mode_requires_one_hundred_episodes(self):
        self.write_valid_single_episode_dataset()
        mark_recorded(self.root, 1, 1, 0, "2026-08-24T21:00:00+09:00")

        report = validate_dataset(self.root, REPO_ID, mode="metadata", require_complete=True)

        codes = {error["code"] for error in report["errors"]}
        self.assertIn("dataset_incomplete", codes)
        self.assertIn("plan_incomplete", codes)

    def test_decode_samples_reads_first_middle_and_last_frame_of_each_episode(self):
        import torch

        class FakeMeta:
            total_episodes = 2
            episodes = {
                "dataset_from_index": [0, 10],
                "dataset_to_index": [10, 20],
            }

        class FakeDataset:
            meta = FakeMeta()

            def __init__(self):
                self.requested_indices = []

            def __getitem__(self, index):
                self.requested_indices.append(index)
                return {"observation.images.wrist": torch.ones((3, 2, 2))}

        dataset = FakeDataset()

        decoded = _decode_episode_samples(dataset)

        self.assertEqual(decoded, 6)
        self.assertEqual(dataset.requested_indices, [0, 4, 9, 10, 14, 19])

    def test_full_mode_reports_real_lerobot_load_failure(self):
        self.write_valid_single_episode_dataset()

        report = validate_dataset(self.root, REPO_ID, mode="full")

        self.assertFalse(report["ok"])
        self.assertIn("dataset_load_failed", {error["code"] for error in report["errors"]})

    def test_cli_prints_json_and_returns_failure_for_missing_dataset(self):
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools" / "check_act_dataset.py"),
                "--dataset-root",
                str(self.root),
                "--repo-id",
                REPO_ID,
                "--mode",
                "metadata",
                "--json-stdout",
            ],
            cwd=ROOT,
            capture_output=True,
        )

        stderr = result.stderr.decode("utf-8", errors="replace")
        self.assertNotIn("\ufffd", stderr)
        self.assertEqual(result.returncode, 1, stderr)
        report = json.loads(result.stdout.decode("utf-8"))
        self.assertEqual(report["errors"][0]["code"], "missing_meta_info")

    def test_cli_writes_json_report_atomically(self):
        report_path = self.root / "reports" / "validation.json"
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools" / "check_act_dataset.py"),
                "--dataset-root",
                str(self.root),
                "--repo-id",
                REPO_ID,
                "--mode",
                "metadata",
                "--json-report",
                str(report_path),
            ],
            cwd=ROOT,
            capture_output=True,
        )

        stderr = result.stderr.decode("utf-8", errors="replace")
        self.assertNotIn("\ufffd", stderr)
        self.assertEqual(result.returncode, 1, stderr)
        self.assertEqual(json.loads(report_path.read_text(encoding="utf-8"))["ok"], False)
        self.assertFalse(report_path.with_suffix(".json.tmp").exists())


if __name__ == "__main__":
    unittest.main()
