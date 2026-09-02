[CmdletBinding()]
param(
    [ValidateRange(1, 30)]
    [int]$Trials = 1,
    [int]$EpisodeTime = 20,
    [string]$FollowerPort = "COM3",
    [ValidateRange(0, 20)]
    [int]$WristIndex = 0,
    [ValidateSet(700, 1400)]
    [int]$CameraBackend = 700,
    [string]$Checkpoint = "100000",
    [double]$HomeSeconds = 3.0,
    # 정책의 액션이 이 시간만큼 거의 변하지 않으면 에피소드를 조기 종료한다.
    # 이 정지 감지 구간이 곧 "뚜껑 닫고 잠깐 정지"에 해당한다.
    [double]$StillSeconds = 0.5,
    # 이 시간 전에는 조기 종료하지 않는다 (정책이 느리게 시작하는 경우 보호).
    [double]$MinSeconds = 8.0,
    # 시행 후 홈 복귀를 생략한다. 팔이 최종 자세에 그대로 남으므로, 다음 시행 전에
    # 반드시 손으로 되돌리고 check_home.py 로 확인해야 한다.
    [switch]$NoHome,
    [string]$PythonPath = "$env:USERPROFILE\miniconda3\envs\lerobot\python.exe",
    [switch]$ConfirmHardwareReady,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8
# 🔴 콘솔에 직접 쓸 때는 위 OutputEncoding 으로 충분하지만, 파이프로 연결된 자식
# 프로세스(예: 아래 check_home.py | Out-Null)는 콘솔이 아니므로 파이썬이 로케일
# 기본 코드페이지(cp949)로 폴백해 한글 콘솔 출력(—, ✅ 등)에서 UnicodeEncodeError 로 죽는다.
# 이 환경변수가 그 폴백을 막는다 (2026-08-28 실측: 이게 없으면 check_home.py 가 죽어서
# "홈이 아니다"로 오판되고, 실제로는 홈에 있는데 30회 검증 루프가 통째로 멈췄다).
$env:PYTHONIOENCODING = "utf-8"

# 🔴 정책을 지정하면 lerobot 이 데이터셋 이름에 'eval_' 접두어를 강제한다
# (utils/control_utils.py sanity_check_dataset_name). 학습 데이터셋과 절대 섞이면 안 되므로
# 저장 위치도 완전히 분리한다.
$repoId = "local/eval_hazardbot_act_v1"
$datasetRoot = "C:\ACT_data\eval_hazardbot_act_v1"
$policyPath = "C:\ACT_data\training\hazardbot_red_yellow_act_v1\checkpoints\$Checkpoint\pretrained_model"
$task = "Pick up the hazardous object, place it in the isolation bin, and close the lid."
$recordPatchedPath = Join-Path $PSScriptRoot "tools\run_lerobot_record_patched.py"
$goHomePath = Join-Path $PSScriptRoot "tools\go_home.py"
$checkGoalPath = Join-Path $PSScriptRoot "tools\check_goal.py"
$pythonScriptsPath = Join-Path (Split-Path -Parent $PythonPath) "Scripts"

foreach ($requiredPath in @($PythonPath, $recordPatchedPath, $goHomePath, $checkGoalPath)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) { throw "필수 파일을 찾을 수 없습니다: $requiredPath" }
}
if (-not (Test-Path -LiteralPath $policyPath -PathType Container)) {
    throw "체크포인트를 찾을 수 없습니다: $policyPath"
}

function Get-EpisodeCount {
    $infoPath = Join-Path $datasetRoot "meta\info.json"
    if (-not (Test-Path -LiteralPath $infoPath -PathType Leaf)) { return 0 }
    return [int]((Get-Content -LiteralPath $infoPath -Raw -Encoding UTF8 | ConvertFrom-Json).total_episodes)
}

# 🔵 시행 1회 = run_lerobot_record_patched.py 프로세스 1회(에피소드 1개).
#    조기 종료와 홈 복귀가 **그 프로세스 안에서** 끝난다 — 별도 go_home 프로세스가 없다.
#
#    lerobot 의 다회 에피소드 모드를 쓰지 않는 이유: 에피소드 사이 'Reset the environment'
#    구간에서 팔을 홈으로 되돌리려면 리더암 텔레옵이 필요한데(그 구간의 record_loop 호출에는
#    policy 인자가 없다), 패치된 복귀가 그 역할을 대신하면 **리더암이 아예 필요 없어진다.**
#    매 시행이 동일한 홈 자세에서 시작하므로 학습 분포와도 더 잘 맞는다.
function New-RecordArgs {
    param([bool]$IsResume)
    $cameraConfig = "{wrist: {type: opencv, index_or_path: $WristIndex, width: 640, height: 480, fps: 30, backend: $CameraBackend}}"
    $a = @(
        $PythonPath,
        $recordPatchedPath,
        "--still-seconds=$StillSeconds",
        "--min-seconds=$MinSeconds",
        "--home-seconds=$HomeSeconds",
        "--robot.type=so101_follower",
        "--robot.port=$FollowerPort",
        "--robot.id=follower_arm",
        "--robot.use_degrees=false",
        "--robot.cameras=$cameraConfig",
        "--policy.path=$policyPath",
        "--dataset.repo_id=$repoId",
        "--dataset.root=$datasetRoot",
        "--dataset.push_to_hub=false",
        "--dataset.streaming_encoding=false",
        "--dataset.single_task=$task",
        "--dataset.num_episodes=1",
        "--dataset.episode_time_s=$EpisodeTime",
        "--dataset.reset_time_s=0",
        "--dataset.fps=30",
        "--display_data=true"
    )
    # 🔵 --robot.disable_torque_on_disconnect 는 건드리지 않는다(기본 true 유지).
    #    홈 복귀가 프로세스 안에서, robot.disconnect() 보다 **먼저** 끝나므로 팔이 처질
    #    구간 자체가 없다. 예전처럼 토크를 켠 채 프로세스를 넘길 필요가 없어졌다.
    if ($NoHome) { $a += "--no-home" }
    if ($IsResume) { $a += "--resume=true" }
    return $a
}

$goalArgs = @($PythonPath, $checkGoalPath, "--port", $FollowerPort, "--fix")
$homeArgs = @($PythonPath, $goHomePath, "--port", $FollowerPort, "--seconds", "1")
# 🔵 2026-08-30 — check_cameras 대역폭 테스트(고정 5초)는 preflight에서 뺐다. 이 스크립트는
# 카메라 1대(손목)만 쓰므로 원래 목적(2대 동시 대역폭 경합)이 애초에 해당 없고, 카메라가
# 이미 정상 동작 확인됐다면 매 실행마다 5초를 태울 이유가 없다. 필요하면 따로 돌릴 것:
#   python tools\check_cameras.py --bandwidth <index> --seconds 5
$preflight = @(
    [ordered]@{ name = "check_home"; argv = @($PythonPath, (Join-Path $PSScriptRoot "tools\check_home.py"), "--port", $FollowerPort) }
)

if ($DryRun) {
    [ordered]@{
        trials = $Trials
        dataset_root = $datasetRoot
        repo_id = $repoId
        policy_path = $policyPath
        episodes_before = (Get-EpisodeCount)
        home_after_each_trial = (-not $NoHome)
        home_runs_in_record_process = (-not $NoHome)
        leader_arm_required = $false
        constraints = [ordered]@{
            episode_time_s = $EpisodeTime
            fps = 30
            home_seconds = $HomeSeconds
            still_seconds = $StillSeconds
            min_seconds = $MinSeconds
        }
        environment = [ordered]@{ prepend_path = $pythonScriptsPath }
        preflight = $preflight
        per_trial = [ordered]@{
            # 🔵 2026-08-30 — 물체 배치 대기 중 토크가 꺼져 있어 wrist_roll(연속회전축,
            # 쉬는 자세 없음)이 조금씩 밀릴 수 있다. check_goal --fix는 드리프트된 현재
            # 위치를 그대로 인정해버리므로, 그 전에 실제 저장된 홈으로 능동 복귀시킨다.
            pre_trial_home = $(if ($NoHome) { $null } else { $homeArgs })
            check_goal = $goalArgs
            record = (New-RecordArgs -IsResume $true)
        }
    } | ConvertTo-Json -Depth 6
    exit 0
}

$env:PATH = "$pythonScriptsPath;$env:PATH"

foreach ($step in $preflight) {
    Write-Host "[$($step.name)]"
    & $step.argv[0] $step.argv[1..($step.argv.Count - 1)]
    if ($LASTEXITCODE -ne 0) { throw "$($step.name) 실패" }
}

Write-Host ""
Write-Host "정책이 팔을 자율 제어합니다. 파지에 실패해도 멈추지 않고 계속 진행합니다."
Write-Host "팔 반경을 비우고 전원 스위치에 손을 올려두십시오."
if (-not $NoHome) {
    Write-Host "각 시행이 끝나면 팔이 $HomeSeconds 초에 걸쳐 홈 자세로 자동 복귀합니다."
}
if (-not $ConfirmHardwareReady) {
    $answer = Read-Host "준비되면 READY 입력"
    if ($answer -cne "READY") { throw "사용자가 실행을 취소했습니다." }
}

$sessionStart = Get-EpisodeCount
for ($trial = 1; $trial -le $Trials; $trial++) {
    Write-Host ""
    Write-Host "===== 시행 $trial / $Trials ====="

    if ($trial -gt 1 -and -not $ConfirmHardwareReady) {
        Read-Host "물체를 다음 조합 위치에 배치한 뒤 Enter"
    }

    # 🔵 2026-08-30 — 물체 배치 대기 중 토크 해제 상태로 wrist_roll이 밀렸을 수 있으니,
    # check_goal(현재 위치를 그대로 인정)보다 먼저 실제 저장된 홈으로 능동 복귀시킨다.
    # 그래야 이번 시행이 "시작할 때의 홈 자세"와 실제로 같은 곳에서 출발한다.
    if (-not $NoHome) {
        & $homeArgs[0] $homeArgs[1..($homeArgs.Count - 1)]
        if ($LASTEXITCODE -ne 0) { throw "시행 $trial - 시행 전 홈 복귀 실패. 팔이 막혔는지 확인할 것." }
    }

    & $goalArgs[0] $goalArgs[1..($goalArgs.Count - 1)]
    if ($LASTEXITCODE -ne 0) { throw "시행 $trial - Goal_Position 동기화 실패" }

    # 조기 종료(동작 정지 감지)와 홈 복귀가 이 프로세스 안에서 끝난다.
    # 복귀는 record_loop 의 finally 에 걸려 있어 녹화가 예외로 죽어도 실행된다.
    $recordArgs = New-RecordArgs -IsResume ((Get-EpisodeCount) -gt 0)
    & $recordArgs[0] $recordArgs[1..($recordArgs.Count - 1)]
    if ($LASTEXITCODE -ne 0) { throw "시행 $trial - 롤아웃 실패 (종료 코드 $LASTEXITCODE). 팔 자세를 확인할 것." }

    # 프로세스 안에서 복귀했더라도, 실제로 홈에 있는지는 밖에서 한 번 더 확인한다.
    # 다음 시행이 홈에서 시작하지 않으면 학습 분포를 벗어나 결과가 오염된다.
    if (-not $NoHome) {
        & $PythonPath (Join-Path $PSScriptRoot "tools\check_home.py") "--port" $FollowerPort | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "시행 $trial - 복귀 후에도 홈 자세가 아니다. 손으로 맞추고 check_home.py 로 확인할 것." }
    }
}

$afterCount = Get-EpisodeCount
Write-Host ""
Write-Host "완료: 이번 세션 $($afterCount - $sessionStart) 회 / 누적 $afterCount 회"
Write-Host "영상: $datasetRoot\videos\observation.images.wrist\"
Write-Host "각 시행의 성공/실패와 실패 단계(파지·이동·격리·뚜껑)를 기록해 두십시오."



