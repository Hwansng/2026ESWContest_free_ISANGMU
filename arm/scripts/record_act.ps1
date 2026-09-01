[CmdletBinding()]
param(
    [ValidateRange(1, 10)]
    [Nullable[int]]$Batch = $null,
    [switch]$Pilot,
    [string]$FollowerPort = "COM3",
    [string]$LeaderPort = "COM5",
    [ValidateRange(0, 20)]
    [int]$WristIndex = 0,
    [ValidateSet(700, 1400)]
    [int]$CameraBackend = 700,
    [string]$DatasetRoot = "",
    [string]$PythonPath = "$env:USERPROFILE\miniconda3\envs\lerobot\python.exe",
    [switch]$ConfirmHardwareReady,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8

$hasBatch = $null -ne $Batch
if ($hasBatch -eq [bool]$Pilot) {
    throw "-Batch 1..10 또는 -Pilot 중 하나만 지정하십시오."
}

$productionRepo = "local/hazardbot_red_yellow_act_v1"
$pilotRepo = "local/hazardbot_red_yellow_act_v1_pilot"
$task = "Pick up the hazardous object, place it in the isolation bin, and close the lid."
$launcherPath = Join-Path $PSScriptRoot "tools\run_lerobot_module.py"
$planPath = Join-Path $PSScriptRoot "tools\act_collection_plan.py"
$validatorPath = Join-Path $PSScriptRoot "tools\check_act_dataset.py"
$pythonScriptsPath = Join-Path (Split-Path -Parent $PythonPath) "Scripts"

if ([string]::IsNullOrWhiteSpace($DatasetRoot)) {
    # 🔴 저장소 경로(OneDrive\바탕 화면\...)에 한글이 있으면 LeRobot의 비디오 청크
    # 병합(ffmpeg concat)이 실패한다 (2026-08-25 실제 발생, 에피소드 2번째부터 재현).
    # 그래서 기본 저장 위치를 한글 없는 C:\ACT_data 로 둔다. OneDrive 밖이라 동기화
    # 잠금 문제도 같이 피한다. 필요하면 -DatasetRoot 로 덮어쓸 것.
    $baseRoot = "C:\ACT_data"
    $relativeRoot = if ($Pilot) { "act_red_yellow_v1_pilot" } else { "act_red_yellow_v1" }
    $DatasetRoot = Join-Path $baseRoot $relativeRoot
}
if (-not [System.IO.Path]::IsPathRooted($DatasetRoot)) {
    $DatasetRoot = Join-Path $PSScriptRoot $DatasetRoot
}
$DatasetRoot = [System.IO.Path]::GetFullPath($DatasetRoot)

function Get-DatasetState([string]$Root) {
    if (-not (Test-Path -LiteralPath $Root)) { return "create" }
    if (-not (Test-Path -LiteralPath $Root -PathType Container)) {
        throw "데이터셋 경로가 폴더가 아닙니다: $Root"
    }
    $entries = @(Get-ChildItem -LiteralPath $Root -Force)
    if ($entries.Count -eq 0) { return "create" }
    if (Test-Path -LiteralPath (Join-Path $Root "meta\info.json") -PathType Leaf) { return "resume" }
    $doNotOverwrite = ([string][char]0xB36E + [char]0xC5B4 + [char]0xC4F0 + [char]0xC9C0 + " " + [char]0xC54A + [char]0xC2B5 + [char]0xB2C8 + [char]0xB2E4)
    throw "$doNotOverwrite`: $Root"
}

function Get-EpisodeCount([string]$Root) {
    $infoPath = Join-Path $Root "meta\info.json"
    if (-not (Test-Path -LiteralPath $infoPath -PathType Leaf)) { return 0 }
    $info = Get-Content -LiteralPath $infoPath -Raw -Encoding UTF8 | ConvertFrom-Json
    return [int]$info.total_episodes
}

$state = Get-DatasetState $DatasetRoot
$beforeCount = Get-EpisodeCount $DatasetRoot
$repoId = if ($Pilot) { $pilotRepo } else { $productionRepo }
$mode = if ($Pilot) { "pilot_$state" } else { $state }

if ($Pilot) {
    if ($beforeCount -ge 1) { throw "파일럿 데이터셋에는 이미 에피소드가 있습니다." }
    $remaining = 1
} elseif ($state -eq "create") {
    $remaining = 10
} else {
    $statusText = & $PythonPath $planPath "status" "--dataset-root" $DatasetRoot "--batch" ([string]$Batch)
    if ($LASTEXITCODE -ne 0) { throw "수집 계획을 읽지 못했습니다." }
    $status = $statusText | ConvertFrom-Json
    $remaining = [int]$status.remaining
    if ($remaining -eq 0) { throw "배치 $Batch 는 이미 완료되었습니다." }
}

$cameraConfig = "{wrist: {type: opencv, index_or_path: $WristIndex, width: 640, height: 480, fps: 30, backend: $CameraBackend}}"
$recordArgs = @(
    $PythonPath,
    $launcherPath,
    "lerobot.scripts.lerobot_record",
    "--robot.type=so101_follower",
    "--robot.port=$FollowerPort",
    "--robot.id=follower_arm",
    "--robot.use_degrees=false",
    "--teleop.type=so101_leader",
    "--teleop.port=$LeaderPort",
    "--teleop.id=leader_arm",
    "--teleop.use_degrees=false",
    "--robot.cameras=$cameraConfig",
    "--dataset.repo_id=$repoId",
    "--dataset.root=$DatasetRoot",
    "--dataset.push_to_hub=false",
    "--dataset.streaming_encoding=false",
    "--display_data=true",
    "--dataset.num_episodes=$remaining",
    "--dataset.episode_time_s=35",
    "--dataset.reset_time_s=60",
    "--dataset.fps=30",
    "--dataset.single_task=$task"
)
if ($state -ne "create") { $recordArgs += "--resume=true" }
# 🔴 이 노트북의 lerobot 0.4.4에는 --dataset.no_stamp 플래그가 없다 (0.6.1 전용 — 확인:
# `lerobot_record --help`에 미존재, 소스에도 "stamp" 개념 자체가 없음). 신규 생성 시
# dataset.root 를 그대로 쓰므로 추가 플래그가 필요 없다.

$preflight = @(
    [ordered]@{ name = "check_home"; argv = @($PythonPath, (Join-Path $PSScriptRoot "tools\check_home.py"), "--port", $FollowerPort) },
    [ordered]@{ name = "check_align"; argv = @($PythonPath, (Join-Path $PSScriptRoot "tools\check_align.py"), "--leader", $LeaderPort, "--follower", $FollowerPort) },
    [ordered]@{ name = "check_camera"; argv = @($PythonPath, (Join-Path $PSScriptRoot "tools\check_cameras.py"), "--bandwidth", ([string]$WristIndex), "--seconds", "5") },
    [ordered]@{ name = "check_goal"; argv = @($PythonPath, (Join-Path $PSScriptRoot "tools\check_goal.py"), "--port", $FollowerPort, "--fix") }
)

if ($DryRun) {
    [ordered]@{
        mode = $mode
        dataset_root = $DatasetRoot
        repo_id = $repoId
        batch = if ($Pilot) { $null } else { $Batch }
        remaining = $remaining
        devices = [ordered]@{ leader_port = $LeaderPort; follower_port = $FollowerPort; wrist_index = $WristIndex }
        constraints = [ordered]@{ episode_time_s = 35; reset_time_s = 60; fps = 30 }
        environment = [ordered]@{ prepend_path = $pythonScriptsPath }
        preflight = $preflight
        argv = $recordArgs
    } | ConvertTo-Json -Depth 6
    exit 0
}

foreach ($requiredPath in @($PythonPath, $launcherPath, $planPath, $validatorPath)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) { throw "필수 파일을 찾을 수 없습니다: $requiredPath" }
}
$env:PATH = "$pythonScriptsPath;$env:PATH"

if ($state -eq "resume") {
    & $PythonPath $validatorPath "--dataset-root" $DatasetRoot "--repo-id" $repoId "--mode" "full"
    if ($LASTEXITCODE -ne 0) { throw "기존 데이터셋 검증에 실패했습니다." }
}

foreach ($step in $preflight[0..2]) {
    Write-Host "[$($step.name)]"
    & $step.argv[0] $step.argv[1..($step.argv.Count - 1)]
    if ($LASTEXITCODE -ne 0) { throw "$($step.name) 실패" }
}

Write-Host "수집 순서: 화면의 배치표에 따라 적색/황색과 위치를 교체하십시오."
Write-Host "키: N 또는 오른쪽=저장/다음, R 또는 왼쪽=재촬영, Q/Esc=종료"
if (-not $ConfirmHardwareReady) {
    $answer = Read-Host "팔 주변을 비운 뒤 READY 입력"
    if ($answer -cne "READY") { throw "사용자가 실행을 취소했습니다." }
}

$goal = $preflight[3]
& $goal.argv[0] $goal.argv[1..($goal.argv.Count - 1)]
if ($LASTEXITCODE -ne 0) { throw "Goal_Position 동기화 실패" }

& $recordArgs[0] $recordArgs[1..($recordArgs.Count - 1)]
if ($LASTEXITCODE -ne 0) { throw "LeRobot 녹화 실패 (종료 코드 $LASTEXITCODE)" }

$afterCount = Get-EpisodeCount $DatasetRoot
$recordedCount = $afterCount - $beforeCount
if (-not $Pilot -and $recordedCount -gt 0) {
    & $PythonPath $planPath "mark-recorded" "--dataset-root" $DatasetRoot "--batch" ([string]$Batch) "--count" ([string]$recordedCount) "--first-episode-index" ([string]$beforeCount) "--recorded-at" ([DateTimeOffset]::Now.ToString("o"))
    if ($LASTEXITCODE -ne 0) { throw "수집 계획 갱신에 실패했습니다." }
}
& $PythonPath $validatorPath "--dataset-root" $DatasetRoot "--repo-id" $repoId "--mode" "full" "--json-report" (Join-Path $DatasetRoot "collection\validation_latest.json")
if ($LASTEXITCODE -ne 0) { throw "녹화 후 데이터셋 검증에 실패했습니다." }
