# ACT Red/Yellow Collection Environment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 적색 물체와 황색 종이컵의 성공 궤적 100개를 하나의 LeRobot ACT 데이터셋으로 안전하게 누적하고, 검사·이력·전송까지 처리하는 수집 전용 환경을 구축한다.

**Architecture:** PowerShell 실행기가 실제 하드웨어 사전 검사와 LeRobot 녹화를 조정하고, 작은 Python 도구들이 결정론적 수집표, 읽기 전용 데이터셋 검사, 체크섬을 담당한다. 데이터셋은 `output/act_red_yellow_v1` 하나에 누적하며 신규 생성과 재개를 폴더 상태로 엄격히 구분한다. 모든 하드웨어 없는 로직을 먼저 단위·통합 테스트하고 실제 로봇 시험은 별도 pilot 데이터셋에서 1회만 수행한다.

**Tech Stack:** Windows PowerShell 5.1, Python 3.12, LeRobot 0.6.1, PyTorch CPU, Hugging Face Datasets/Parquet, unittest, SHA-256, robocopy

**Spec:** `docs/04_act/2026-08-24-act-red-yellow-collection-design.md`

## Global Constraints

- 현재 노트북은 데이터 수집, 검사, 이력 관리, 전송만 수행하고 ACT 학습·CUDA·GPU 패키지를 설치하지 않는다.
- 정본 시나리오는 2026년 8월 16일 버전이며 적색과 황색을 하나의 ACT 정책·하나의 데이터셋으로 수집한다.
- 데이터셋 식별자는 `local/hazardbot_red_yellow_act_v1`, 기본 경로는 `output/act_red_yellow_v1`이다.
- 작업 문장은 `Pick up the hazardous object, place it in the isolation bin, and close the lid.`로 고정한다.
- 데이터는 30 FPS, 640×480 `observation.images.wrist` 한 대, 총 100개 성공 에피소드다.
- 10개 배치 각각은 적색·황색과 5개 위치의 조합 10개를 정확히 한 번씩 포함한다.
- 녹화 시간은 최대 35초, 비기록 재설정 시간은 최대 60초다.
- 실패 궤적은 `R`/왼쪽 화살표로 폐기하고, 성공 궤적만 `N`/오른쪽 화살표로 저장한다.
- 기존 비정상 폴더를 덮어쓰거나 손상 데이터셋을 자동 복구하지 않는다.
- 기본 장치 프로필은 리더 COM6, 팔로워 COM7, 카메라 1이며 자동 포트 추측은 하지 않는다.
- Hugging Face Hub 업로드는 항상 비활성화한다.
- 실제 로봇 시험은 `output/act_red_yellow_v1_pilot` 별도 경로에서 1회만 수행한다.

---

## File Structure

- `tools/act_collection_plan.py`: 고정 시드 수집표 생성, 배치 조회, 저장된 에피소드 상태 반영, 균형 검증
- `tools/check_act_dataset.py`: LeRobot 메타데이터·에피소드·카메라 프레임·수집표를 읽기 전용으로 검사
- `tools/act_transfer.py`: 체크섬 목록 생성과 복사본 검증을 OS 독립적인 Python 로직으로 제공
- `record_act.ps1`: 하드웨어 사전 검사, 신규/재개 안전 가드, LeRobot 실행, 수집표 갱신, 사후 검사
- `prepare_act_transfer.ps1`: 최종 검사, SHA-256 생성, robocopy, 복사본 검증 조정
- `tests/act_collection/test_act_collection_plan.py`: 수집표 순서·균형·상태 전이 단위 테스트
- `tests/act_collection/test_check_act_dataset.py`: 검사 오류와 성공 보고서 단위 테스트
- `tests/act_collection/test_act_transfer.py`: 체크섬 생성·불일치 검출 테스트
- `tests/act_collection/test_act_scripts.py`: PowerShell DryRun과 안전 가드 통합 테스트 확장
- `.gitignore`: 실제 데이터와 pilot 데이터만 정확히 제외
- `docs/04_act/ACT_수집_다른컴퓨터_가이드.md`: 한글 수집·중단·재개·검사·전송 안내

---

### Task 1: Deterministic balanced collection plan

**Files:**
- Create: `tools/act_collection_plan.py`
- Create: `tests/act_collection/test_act_collection_plan.py`

**Interfaces:**
- Consumes: 데이터셋 루트 `Path`, 배치 번호 `1..10`, 저장된 에피소드 수
- Produces: `build_plan(seed: int = 20260816) -> list[dict[str, str]]`, `load_or_build_plan(dataset_root: Path) -> list[dict[str, str]]`, `get_batch_status(rows: list[dict[str, str]], batch: int) -> dict`, `verify_plan(rows: list[dict[str, str]], require_complete: bool = False) -> list[dict[str, str]]`, `mark_recorded(dataset_root: Path, batch: int, count: int, first_episode_index: int, recorded_at: str) -> list[dict[str, str]]`, CLI JSON 출력

- [ ] **Step 1: Write the failing balance and determinism tests**

```python
import unittest
from collections import Counter

from tools.act_collection_plan import build_plan


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
```

- [ ] **Step 2: Run the test and confirm the missing module failure**

Run:

```powershell
C:\Users\rkdgm\anaconda3\envs\lerobot\python.exe -m unittest tests.act_collection.test_act_collection_plan -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'tools.act_collection_plan'`.

- [ ] **Step 3: Implement deterministic row generation**

```python
COLORS = ("red", "yellow")
POSITIONS = ("center", "front_left", "front_right", "rear_left", "rear_right")


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
```

- [ ] **Step 4: Run the balance test and confirm it passes**

Run the Step 2 command. Expected: PASS.

- [ ] **Step 5: Write failing state transition tests**

```python
import tempfile
from pathlib import Path

from tools.act_collection_plan import get_batch_status, load_or_build_plan, mark_recorded


def test_mark_recorded_updates_only_next_pending_rows(self):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        mark_recorded(root, batch=3, count=4, first_episode_index=20, recorded_at="2026-08-24T21:00:00+09:00")
        rows = load_or_build_plan(root)
        batch_rows = [row for row in rows if row["batch"] == "3"]
        self.assertEqual([row["status"] for row in batch_rows], ["recorded"] * 4 + ["pending"] * 6)
        self.assertEqual([row["episode_index"] for row in batch_rows[:4]], ["20", "21", "22", "23"])
        self.assertEqual(get_batch_status(rows, 3)["remaining"], 6)
```

- [ ] **Step 6: Implement atomic CSV persistence and CLI commands**

Use `collection/plan.csv.tmp` followed by `Path.replace()` so interruption never leaves a half-written plan. Implement these CLI contracts:

```text
python tools/act_collection_plan.py status --dataset-root ROOT --batch 1
python tools/act_collection_plan.py mark-recorded --dataset-root ROOT --batch 1 --count 4 --first-episode-index 0 --recorded-at 2026-08-24T21:00:00+09:00
python tools/act_collection_plan.py verify --dataset-root ROOT --require-complete
```

Every successful command prints one JSON object to stdout. `status` must not write a plan when the dataset root has no `meta/info.json`; `mark-recorded` creates `collection/plan.csv` and `collection/protocol.json` only after a LeRobot dataset exists. The protocol JSON stores schema version 1, seed `20260816`, repo ID, fixed task, FPS 30, image key, total 100, episode limit 35, and reset limit 60. Reject negative counts, batch numbers outside `1..10`, episode index collisions, and marking past ten rows.

- [ ] **Step 7: Run all collection plan tests**

Run:

```powershell
C:\Users\rkdgm\anaconda3\envs\lerobot\python.exe -m unittest tests.act_collection.test_act_collection_plan -v
```

Expected: all tests PASS.

- [ ] **Step 8: Commit the collection plan component**

```powershell
git add tools/act_collection_plan.py tests/act_collection/test_act_collection_plan.py
git commit -m "Add balanced ACT collection plan"
```

---

### Task 2: Read-only LeRobot dataset validator

**Files:**
- Create: `tools/check_act_dataset.py`
- Create: `tests/act_collection/test_check_act_dataset.py`

**Interfaces:**
- Consumes: dataset root, expected repo ID, maximum duration, validation mode, completion requirement
- Produces: `validate_dataset(dataset_root: Path, repo_id: str, mode: str = "full", require_complete: bool = False) -> dict`, exit code 0/1, JSON report
- Depends on: `load_or_build_plan()` and `verify_plan()` from Task 1

- [ ] **Step 1: Write failing metadata validation tests**

Create fixtures with only the metadata needed for pure checks and assert exact error codes:

```python
def test_missing_info_is_rejected(self):
    report = validate_dataset(self.root, REPO_ID, mode="metadata")
    self.assertFalse(report["ok"])
    self.assertIn("missing_meta_info", [error["code"] for error in report["errors"]])

def test_wrong_fps_and_missing_features_are_rejected(self):
    write_info(self.root, fps=15, total_episodes=0, features={})
    report = validate_dataset(self.root, REPO_ID, mode="metadata")
    codes = {error["code"] for error in report["errors"]}
    self.assertIn("unexpected_fps", codes)
    self.assertIn("missing_wrist_camera", codes)
    self.assertIn("missing_action", codes)
    self.assertIn("missing_observation_state", codes)
```

- [ ] **Step 2: Run tests and confirm the missing validator failure**

Run:

```powershell
C:\Users\rkdgm\anaconda3\envs\lerobot\python.exe -m unittest tests.act_collection.test_check_act_dataset -v
```

Expected: FAIL because `tools.check_act_dataset` does not exist.

- [ ] **Step 3: Implement pure metadata and plan checks**

The report schema is fixed:

```python
report = {
    "ok": len(errors) == 0,
    "dataset_root": str(dataset_root.resolve()),
    "repo_id": repo_id,
    "fps": info.get("fps"),
    "total_episodes": info.get("total_episodes"),
    "errors": errors,
    "warnings": warnings,
    "decoded_episode_samples": 0,
}
```

Each error is `{"code": str, "message": str}`. Require exact FPS 30 and feature keys `observation.images.wrist`, `observation.state`, and `action`. When `collection/protocol.json` exists, require its repo ID, task, FPS, image key, and limits to match the command and fixed protocol. Verify every required data/video path from episode metadata exists and has a non-zero file size. If `require_complete=True`, require exactly 100 episodes and a complete balanced plan; otherwise require the number of `recorded` rows to equal `total_episodes` whenever `collection/plan.csv` exists.

- [ ] **Step 4: Write failing episode continuity and duration tests**

```python
def test_episode_gap_and_excess_duration_are_rejected(self):
    write_valid_fixture(self.root, episodes=[
        {"episode_index": 0, "dataset_from_index": 0, "dataset_to_index": 901},
        {"episode_index": 2, "dataset_from_index": 901, "dataset_to_index": 2101},
    ])
    report = validate_dataset(self.root, REPO_ID, mode="metadata")
    codes = {error["code"] for error in report["errors"]}
    self.assertIn("episode_index_gap", codes)
    self.assertIn("episode_too_long", codes)
```

At 30 FPS, duration is `length / 30`; reject values greater than 35.0 seconds and non-positive lengths. Require each `dataset_from_index` to equal the preceding `dataset_to_index`.

- [ ] **Step 5: Implement lazy full decoding**

Import `LeRobotDataset` only in full mode so metadata tests remain fast. Construct it offline:

```python
dataset = LeRobotDataset(repo_id, root=dataset_root, download_videos=False, token=False)
for episode_index in range(dataset.meta.total_episodes):
    start = int(dataset.meta.episodes["dataset_from_index"][episode_index])
    stop = int(dataset.meta.episodes["dataset_to_index"][episode_index])
    sample_indices = sorted({start, (start + stop - 1) // 2, stop - 1})
    for sample_index in sample_indices:
        frame = dataset[sample_index]["observation.images.wrist"]
        if frame.numel() == 0 or not torch.isfinite(frame).all():
            raise ValueError(f"invalid wrist frame at dataset index {sample_index}")
```

Loading the dataset also validates LeRobot timestamp tolerance. Convert any load/decode exception into `dataset_load_failed` or `frame_decode_failed`; do not modify any source file.

- [ ] **Step 6: Implement CLI and JSON report output**

Support:

```text
python tools/check_act_dataset.py --dataset-root ROOT --repo-id local/hazardbot_red_yellow_act_v1 --mode metadata --json-stdout
python tools/check_act_dataset.py --dataset-root ROOT --repo-id local/hazardbot_red_yellow_act_v1 --mode full --json-report ROOT/collection/validation.json
python tools/check_act_dataset.py --dataset-root ROOT --repo-id local/hazardbot_red_yellow_act_v1 --mode full --require-complete
```

Write reports atomically. Human-readable Korean summary goes to stderr when `--json-stdout` is used, preserving parseable stdout.

- [ ] **Step 7: Run validator tests and CLI help**

Run:

```powershell
C:\Users\rkdgm\anaconda3\envs\lerobot\python.exe -m unittest tests.act_collection.test_check_act_dataset -v
C:\Users\rkdgm\anaconda3\envs\lerobot\python.exe tools\check_act_dataset.py --help
```

Expected: tests PASS and help lists `metadata`, `full`, and `--require-complete`.

- [ ] **Step 8: Commit the validator**

```powershell
git add tools/check_act_dataset.py tests/act_collection/test_check_act_dataset.py
git commit -m "Add ACT dataset validation"
```

---

### Task 3: Safe create/resume recording orchestrator

**Files:**
- Modify: `record_act.ps1`
- Modify: `tests/act_collection/test_act_scripts.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `-Batch 1..10` or `-Pilot`, explicit device overrides, `-ConfirmHardwareReady`, `-DryRun`
- Produces: LeRobot invocation, plan status updates, post-run validator report
- Depends on: Task 1 CLI JSON and Task 2 validator CLI

- [ ] **Step 1: Replace the old dry-run expectation with failing create/resume tests**

Add subprocess helpers that invoke PowerShell and parse stdout JSON. Cover these exact cases:

```python
def test_new_batch_uses_stable_repo_and_no_stamp(self):
    plan = run_record_dry_run(dataset_root=self.temp / "new", batch=1)
    self.assertEqual(plan["mode"], "create")
    self.assertEqual(plan["remaining"], 10)
    self.assertIn("--dataset.no_stamp=true", plan["argv"])
    self.assertNotIn("--resume=true", plan["argv"])

def test_existing_valid_dataset_resumes_only_remaining_rows(self):
    make_existing_dataset(self.temp, total_episodes=24, recorded_rows=24)
    plan = run_record_dry_run(dataset_root=self.temp, batch=3)
    self.assertEqual(plan["mode"], "resume")
    self.assertEqual(plan["remaining"], 6)
    self.assertIn("--resume=true", plan["argv"])
    self.assertIn("--dataset.num_episodes=6", plan["argv"])

def test_nonempty_non_dataset_root_is_rejected(self):
    (self.temp / "unrelated.txt").write_text("keep", encoding="utf-8")
    result = run_record_process(dataset_root=self.temp, batch=1)
    self.assertNotEqual(result.returncode, 0)
    self.assertIn("덮어쓰지 않습니다", result.stderr)
```

- [ ] **Step 2: Run the PowerShell tests and confirm they fail**

Run:

```powershell
C:\Users\rkdgm\anaconda3\envs\lerobot\python.exe -m unittest tests.act_collection.test_act_scripts -v
```

Expected: FAIL because `record_act.ps1` has no `-Batch`, resume state, or stable no-stamp behavior.

- [ ] **Step 3: Implement parameters, constants, and root state classification**

Use these safe defaults and fixed recording values:

```powershell
param(
    [ValidateRange(1, 10)][int]$Batch,
    [switch]$Pilot,
    [string]$FollowerPort = "COM7",
    [string]$LeaderPort = "COM6",
    [ValidateRange(0, 20)][int]$WristIndex = 1,
    [string]$DatasetRoot = (Join-Path $PSScriptRoot "output\act_red_yellow_v1"),
    [string]$PythonPath = "$env:USERPROFILE\anaconda3\envs\lerobot\python.exe",
    [switch]$ConfirmHardwareReady,
    [switch]$DryRun
)

$RepoId = "local/hazardbot_red_yellow_act_v1"
$Task = "Pick up the hazardous object, place it in the isolation bin, and close the lid."
$EpisodeTimeSeconds = 35
$ResetTimeSeconds = 60
```

Require exactly one of `-Batch` and `-Pilot`. Resolve the absolute path. Classify as `create` only when missing or empty, `resume` only when `meta/info.json` exists, and throw for every other non-empty state. `-Pilot` changes root to `output/act_red_yellow_v1_pilot`, repo ID to `local/hazardbot_red_yellow_act_v1_pilot`, and episode count to one; it never touches the production plan.

- [ ] **Step 4: Build exact create/resume argv and DryRun JSON**

Common arguments must include:

```text
--dataset.push_to_hub=false
--dataset.streaming_encoding=false
--dataset.fps=30
--dataset.episode_time_s=35
--dataset.reset_time_s=60
--dataset.single_task=Pick up the hazardous object, place it in the isolation bin, and close the lid.
--robot.cameras={wrist: {type: opencv, index_or_path: 1, width: 640, height: 480, fps: 30, backend: 700}}
```

Create adds `--dataset.no_stamp=true`; resume adds `--resume=true`. Production episode count is the pending count returned by Task 1; pilot count is one. DryRun prints `mode`, `dataset_root`, `repo_id`, `batch`, `remaining`, `environment.prepend_path`, `preflight`, and `argv` as one JSON object without opening serial ports or cameras.

- [ ] **Step 5: Implement preflight and post-run flow**

For non-DryRun production resume, run Task 2 in full mode before hardware checks. Then run, in order:

```text
tools/check_home.py --port COM7
tools/check_align.py --leader COM6 --follower COM7
tools/check_cameras.py --bandwidth 1 --seconds 5
tools/check_goal.py --port COM7 --fix
```

Change `check_cameras.py --bandwidth` to accept one or more indices with `nargs="+"`; retain the existing two-camera behavior. Require at least 20 GiB free before a new production dataset and at least 5 GiB before resume or pilot. Print the pending batch order and `N/R/Q` controls before the READY gate.

Capture the episode count before and after LeRobot. If the command exits normally, compute `delta = after - before`, reject negative or larger-than-requested deltas, call Task 1 `mark-recorded` for production, then call Task 2 in full mode and write `collection/validation.json`. On non-zero LeRobot exit, do not mark the plan; print the recovery command and leave the dataset untouched.

- [ ] **Step 6: Add camera CLI and script flow tests**

Extend tests to assert the dry-run preflight order, default COM6/COM7/camera 1, pilot isolation, completed-batch refusal, and disk thresholds represented in the plan. Add a direct argparse test that `check_cameras.py --bandwidth 1 --seconds 0.1` accepts a single index by mocking `_open` so no physical camera is opened.

- [ ] **Step 7: Ignore only generated ACT data**

Append exact root-relative patterns:

```gitignore
/output/act_red_yellow_v1/
/output/act_red_yellow_v1_pilot/
```

Do not ignore all of `output/` because existing user artifacts may belong there.

- [ ] **Step 8: Run PowerShell and camera tests**

Run:

```powershell
C:\Users\rkdgm\anaconda3\envs\lerobot\python.exe -m unittest tests.act_collection.test_act_scripts -v
C:\Users\rkdgm\anaconda3\envs\lerobot\python.exe -m unittest discover -s tests\act_collection -p "test_*.py" -v
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\record_act.ps1 -Batch 1 -DryRun
```

Expected: all tests PASS; DryRun reports create mode, ten remaining episodes, and does not move hardware.

- [ ] **Step 9: Commit the recording orchestrator**

```powershell
git add record_act.ps1 tools/check_cameras.py tests/act_collection/test_act_scripts.py .gitignore
git commit -m "Add safe ACT batch recording"
```

---

### Task 4: Checksum-based transfer preparation

**Files:**
- Create: `tools/act_transfer.py`
- Create: `prepare_act_transfer.ps1`
- Create: `tests/act_collection/test_act_transfer.py`
- Modify: `tests/act_collection/test_act_scripts.py`

**Interfaces:**
- Consumes: completed source dataset and an explicitly named destination parent
- Produces: `collection/SHA256SUMS.csv`, verified destination folder, JSON result
- Depends on: Task 2 `--require-complete`

- [ ] **Step 1: Write failing manifest and corruption tests**

```python
def test_manifest_is_stable_and_excludes_itself(self):
    (self.root / "a.txt").write_text("alpha", encoding="utf-8")
    (self.root / "nested").mkdir()
    (self.root / "nested" / "b.bin").write_bytes(b"beta")
    manifest = write_manifest(self.root)
    rows = read_manifest(manifest)
    self.assertEqual([row["path"] for row in rows], ["a.txt", "nested/b.bin"])
    self.assertTrue(verify_manifest(self.root, manifest)["ok"])

def test_verify_detects_changed_and_missing_files(self):
    (self.root / "a.txt").write_text("alpha", encoding="utf-8")
    manifest = write_manifest(self.root)
    (self.root / "a.txt").write_text("changed", encoding="utf-8")
    result = verify_manifest(self.root, manifest)
    self.assertFalse(result["ok"])
    self.assertEqual(result["mismatches"][0]["reason"], "sha256_mismatch")
```

- [ ] **Step 2: Run tests and confirm the missing module failure**

Run:

```powershell
C:\Users\rkdgm\anaconda3\envs\lerobot\python.exe -m unittest tests.act_collection.test_act_transfer -v
```

Expected: FAIL because `tools.act_transfer` does not exist.

- [ ] **Step 3: Implement streaming SHA-256 and atomic CSV output**

Expose:

```python
def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str
def write_manifest(root: Path, output: Path | None = None) -> Path
def read_manifest(path: Path) -> list[dict[str, str]]
def verify_manifest(root: Path, manifest: Path) -> dict
```

Sort POSIX-style relative paths, reject paths escaping the root, exclude `collection/SHA256SUMS.csv` and its temporary file, stream in 1 MiB chunks, and replace the final CSV atomically. CLI commands are:

```text
python tools/act_transfer.py manifest --dataset-root ROOT
python tools/act_transfer.py verify --dataset-root ROOT --manifest ROOT/collection/SHA256SUMS.csv
```

- [ ] **Step 4: Implement safe PowerShell transfer orchestration**

Parameters:

```powershell
param(
    [string]$DatasetRoot = (Join-Path $PSScriptRoot "output\act_red_yellow_v1"),
    [Parameter(Mandatory = $true)][string]$DestinationParent,
    [string]$GuidePath = (Join-Path $PSScriptRoot "docs\04_act\ACT_수집_다른컴퓨터_가이드.md"),
    [string]$PythonPath = "$env:USERPROFILE\anaconda3\envs\lerobot\python.exe",
    [switch]$DryRun
)
```

Resolve all absolute paths and set destination to `DestinationParent\act_red_yellow_v1`. Refuse when source and destination overlap, the guide is missing, or destination exists and is non-empty. Sequence: full `--require-complete` validation with `collection/validation.json` output, copy the guide to `collection/HANDOFF_KO.md`, manifest generation, `robocopy SOURCE DEST /E /COPY:DAT /DCOPY:T /R:2 /W:2`, destination manifest verification. The guide and validation report are therefore included in the checksum. Treat robocopy exit codes 0–7 as success and 8 or higher as failure. DryRun prints the resolved operations as JSON and performs no writes. Tests pass a temporary `-GuidePath` fixture; the final task verifies the default guide path.

- [ ] **Step 5: Add PowerShell DryRun and overlap tests**

Assert that DryRun includes validation, manifest, robocopy, and verify operations in order; source-under-destination and destination-under-source both fail before any copy. Use temporary directories only.

- [ ] **Step 6: Run transfer tests**

Run:

```powershell
C:\Users\rkdgm\anaconda3\envs\lerobot\python.exe -m unittest tests.act_collection.test_act_transfer -v
C:\Users\rkdgm\anaconda3\envs\lerobot\python.exe -m unittest tests.act_collection.test_act_scripts -v
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\prepare_act_transfer.ps1 -DestinationParent D:\ -DryRun
```

Expected: unit tests PASS; DryRun prints commands only. If `D:` is absent, use an existing temporary directory for the DryRun path because DryRun still validates path resolution.

- [ ] **Step 7: Commit transfer tooling**

```powershell
git add tools/act_transfer.py prepare_act_transfer.ps1 tests/act_collection/test_act_transfer.py tests/act_collection/test_act_scripts.py
git commit -m "Add verified ACT dataset transfer"
```

---

### Task 5: Korean operating guide and end-to-end non-hardware verification

**Files:**
- Create: `docs/04_act/ACT_수집_다른컴퓨터_가이드.md`
- Modify: `docs/04_act/2026-08-24-act-red-yellow-collection-design.md`
- Test: `tests/act_collection/`

**Interfaces:**
- Consumes: all Task 1–4 commands
- Produces: one self-contained Korean runbook and verified collection environment
- Depends on: all prior tasks

- [ ] **Step 1: Clarify pilot isolation in the approved spec**

Change the final sentence so it explicitly states that the one hardware trial uses `output/act_red_yellow_v1_pilot` and never counts toward the production 100 episodes. This resolves an implementation ambiguity without changing the approved collection protocol.

- [ ] **Step 2: Write the Korean runbook with exact commands**

The guide must include these sections and commands:

```powershell
# 하드웨어를 움직이지 않는 확인
.\record_act.ps1 -Batch 1 -DryRun

# 별도 시험 데이터 1회
.\record_act.ps1 -Pilot

# 본 데이터 배치 1
.\record_act.ps1 -Batch 1

# 현재 데이터 검사
C:\Users\rkdgm\anaconda3\envs\lerobot\python.exe .\tools\check_act_dataset.py --dataset-root .\output\act_red_yellow_v1 --repo-id local/hazardbot_red_yellow_act_v1 --mode full

# 외장 드라이브로 최종 전송
.\prepare_act_transfer.ps1 -DestinationParent D:\
```

Document fixed setup, five floor marks, the batch table display, `N/R/Q` controls, success/failure rules, 60-second reset, normal interruption, unexpected interruption recovery, the 20-episode loader checkpoint, 100-episode completion, and checksum verification. State prominently that this laptop does not train ACT.

- [ ] **Step 3: Run the complete automated suite**

Run:

```powershell
C:\Users\rkdgm\anaconda3\envs\lerobot\python.exe -m unittest discover -s tests\act_collection -p "test_*.py" -v
```

Expected: all ACT collection tests PASS.

- [ ] **Step 4: Run syntax and dry-run verification**

Run:

```powershell
C:\Users\rkdgm\anaconda3\envs\lerobot\python.exe -m py_compile tools\act_collection_plan.py tools\check_act_dataset.py tools\act_transfer.py
powershell.exe -NoProfile -Command "[void][scriptblock]::Create((Get-Content -Raw -LiteralPath '.\record_act.ps1')); [void][scriptblock]::Create((Get-Content -Raw -LiteralPath '.\prepare_act_transfer.ps1'))"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\record_act.ps1 -Batch 1 -DryRun
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\prepare_act_transfer.ps1 -DestinationParent .\tmp\act-transfer-dry-run -DryRun
git diff --check
```

Expected: compilation and parsing succeed, both DryRuns output valid JSON without hardware access, and `git diff --check` reports nothing.

- [ ] **Step 5: Inspect working tree scope**

Run:

```powershell
git status --short
git diff -- .gitignore record_act.ps1 prepare_act_transfer.ps1 tools/act_collection_plan.py tools/check_act_dataset.py tools/act_transfer.py tools/check_cameras.py tests/act_collection docs/04_act/ACT_수집_다른컴퓨터_가이드.md docs/04_act/2026-08-24-act-red-yellow-collection-design.md
```

Confirm unrelated user files remain unchanged and are not staged.

- [ ] **Step 6: Commit the runbook and final verification changes**

```powershell
git add docs/04_act/ACT_수집_다른컴퓨터_가이드.md docs/04_act/2026-08-24-act-red-yellow-collection-design.md
git commit -m "Document ACT collection workflow"
```

- [ ] **Step 7: Stop before physical pilot recording**

Report the automated test output and give the exact `-Pilot` command. Do not run it until the user confirms that the leader arm, follower arm, camera, clear workspace, open empty isolation bin, and emergency power-off access are ready.
