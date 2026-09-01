import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
POWERSHELL = Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")

from tools.act_collection_plan import mark_recorded


class ActScriptTests(unittest.TestCase):
    def run_record(self, dataset_root, *arguments):
        return subprocess.run(
            [
                str(POWERSHELL),
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(ROOT / "record_act.ps1"),
                "-DatasetRoot",
                str(dataset_root),
                "-PythonPath",
                sys.executable,
                *arguments,
                "-DryRun",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    @staticmethod
    def make_existing_dataset(root, total_episodes):
        (root / "meta").mkdir(parents=True, exist_ok=True)
        (root / "meta" / "info.json").write_text(
            json.dumps({"fps": 30, "total_episodes": total_episodes, "features": {}}),
            encoding="utf-8",
        )
        remaining = total_episodes
        first_episode = 0
        for batch in range(1, 11):
            count = min(10, remaining)
            if count == 0:
                break
            mark_recorded(root, batch, count, first_episode, "2026-08-24T21:00:00+09:00")
            first_episode += count
            remaining -= count

    def test_lerobot_launcher_restores_env_scripts_for_child_module(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            probe_module = temporary_path / "path_probe.py"
            probe_output = temporary_path / "rerun_path.txt"
            probe_module.write_text(
                "import shutil\n"
                "import sys\n"
                "from pathlib import Path\n"
                "Path(sys.argv[1]).write_text(shutil.which('rerun') or '', encoding='utf-8')\n",
                encoding="utf-8",
            )

            environment = os.environ.copy()
            environment["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32")
            environment["PYTHONPATH"] = str(temporary_path)
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "run_lerobot_module.py"),
                    "path_probe",
                    str(probe_output),
                ],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                Path(probe_output.read_text(encoding="utf-8")).resolve(),
                (Path(sys.executable).parent / "Scripts" / "rerun.EXE").resolve(),
            )

    @unittest.skip(
        "이 노트북의 teleop.ps1은 8/21 하드웨어로 검증된 구버전(대화형 안전검사 4단계)이라 "
        "-DryRun/-PythonPath/JSON plan 출력 인터페이스가 없다. record_act.ps1은 teleop.ps1을 "
        "호출하지 않고 check_home/check_align/check_cameras/check_goal을 직접 호출하므로 "
        "이 기능 없이도 실제 수집에는 영향이 없다. teleop.ps1을 이 인터페이스로 다시 쓰기로 "
        "결정하면 이 테스트를 되살릴 것 (ACT_수집학습_통합계획_2026-08-25.md §3.2 참고)."
    )
    def test_teleop_dry_run_plans_all_safety_checks_before_motion(self):
        result = subprocess.run(
            [
                str(POWERSHELL),
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(ROOT / "teleop.ps1"),
                "-FollowerPort",
                "COM3",
                "-LeaderPort",
                "COM5",
                "-WristIndex",
                "2",
                "-Cameras",
                "-PythonPath",
                r"C:\ActTest\lerobot\python.exe",
                "-DryRun",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        self.assertEqual(
            plan.get("environment", {}).get("prepend_path"),
            r"C:\ActTest\lerobot\Scripts",
        )
        self.assertEqual(
            [step["name"] for step in plan["steps"]],
            ["check_home", "check_align", "check_goal", "teleoperate"],
        )
        teleop_args = plan["steps"][-1]["argv"]
        self.assertEqual(
            Path(teleop_args[1]).resolve(),
            (ROOT / "tools" / "run_lerobot_module.py").resolve(),
        )
        self.assertEqual(teleop_args[2], "lerobot.scripts.lerobot_teleoperate")
        self.assertIn("--robot.use_degrees=false", teleop_args)
        self.assertIn("--teleop.use_degrees=false", teleop_args)
        self.assertIn("--robot.cameras={wrist: {type: opencv, index_or_path: 2, width: 640, height: 480, fps: 30, backend: 700}}", teleop_args)

    def test_new_batch_uses_stable_repo_and_no_stamp(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            dataset_root = Path(temporary_directory) / "new_dataset"
            result = self.run_record(dataset_root, "-Batch", "1")

            self.assertEqual(result.returncode, 0, result.stderr)
            plan = json.loads(result.stdout)
            self.assertEqual(plan["mode"], "create")
            self.assertEqual(plan["remaining"], 10)
            self.assertEqual(plan["repo_id"], "local/hazardbot_red_yellow_act_v1")
            self.assertEqual(plan["devices"], {"leader_port": "COM5", "follower_port": "COM3", "wrist_index": 0})
            # lerobot 0.4.4에는 --dataset.no_stamp 플래그 자체가 없다 (0.6.1 전용). 신규 생성
            # 시에도 붙이지 않는다 — 붙이면 draccus가 인식 못 해 그 자리에서 죽는다.
            self.assertNotIn("--dataset.no_stamp=true", plan["argv"])
            self.assertNotIn("--resume=true", plan["argv"])
            self.assertIn("--dataset.num_episodes=10", plan["argv"])
            self.assertIn("--dataset.episode_time_s=35", plan["argv"])
            self.assertIn("--dataset.reset_time_s=60", plan["argv"])
            self.assertIn("--display_data=true", plan["argv"])
            self.assertNotIn("--dataset.display_data=true", plan["argv"])
            self.assertEqual(Path(plan["argv"][1]).resolve(), (ROOT / "tools" / "run_lerobot_module.py").resolve())
            self.assertEqual(plan["argv"][2], "lerobot.scripts.lerobot_record")

    def test_existing_valid_dataset_resumes_only_remaining_rows(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            dataset_root = Path(temporary_directory)
            self.make_existing_dataset(dataset_root, total_episodes=24)

            result = self.run_record(dataset_root, "-Batch", "3")

            self.assertEqual(result.returncode, 0, result.stderr)
            plan = json.loads(result.stdout)
            self.assertEqual(plan["mode"], "resume")
            self.assertEqual(plan["remaining"], 6)
            self.assertIn("--resume=true", plan["argv"])
            self.assertNotIn("--dataset.no_stamp=true", plan["argv"])
            self.assertIn("--dataset.num_episodes=6", plan["argv"])

    def test_nonempty_non_dataset_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            dataset_root = Path(temporary_directory)
            (dataset_root / "unrelated.txt").write_text("keep", encoding="utf-8")

            result = self.run_record(dataset_root, "-Batch", "1")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("덮어쓰지 않습니다", result.stderr)

    def test_pilot_is_one_episode_and_does_not_use_production_plan(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            pilot_root = Path(temporary_directory) / "pilot"
            result = self.run_record(pilot_root, "-Pilot")

            self.assertEqual(result.returncode, 0, result.stderr)
            plan = json.loads(result.stdout)
            self.assertEqual(plan["mode"], "pilot_create")
            self.assertEqual(plan["repo_id"], "local/hazardbot_red_yellow_act_v1_pilot")
            self.assertEqual(plan["remaining"], 1)
            self.assertIsNone(plan["batch"])
            self.assertIn("--dataset.num_episodes=1", plan["argv"])


if __name__ == "__main__":
    unittest.main()
