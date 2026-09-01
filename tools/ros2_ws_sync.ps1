# 진우의 ROS2 워크스페이스 사본 갱신 (Hwansng/HazardBot → ros2_ws\)
#
#   .\ros2_ws_sync.ps1
#
# 로컬에는 ros2_ws\ 폴더 하나만 둔다. git 클론은 남기지 않는다 —
# 실행할 때마다 임시 폴더에 받아서 복사하고 지운다. 59개 파일이라 몇 초면 끝난다.
#
# 🔴 이 사본은 읽기·검토 전용이다. 여기서 고쳐도 GitHub 에 올라가지 않는다.
#    진우 코드를 고칠 일이 있으면 GitHub 에서 PR 로 처리한다.

$ErrorActionPreference = "Stop"
$RepoUrl = "https://github.com/Hwansng/HazardBot.git"
$dest    = Join-Path $PSScriptRoot "ros2_ws"
$tmp     = Join-Path $env:TEMP ("hazardbot_sync_" + [System.Guid]::NewGuid().ToString("N").Substring(0,8))

try {
    Write-Host "[1/3] 저장소에서 ros2_ws 받는 중..." -ForegroundColor Cyan
    git clone --filter=blob:none --sparse --quiet $RepoUrl $tmp
    if ($LASTEXITCODE -ne 0) { throw "clone 실패. 인증이 만료됐으면 'git ls-remote $RepoUrl' 을 먼저 실행할 것." }
    git -C $tmp sparse-checkout set ros2_ws
    if ($LASTEXITCODE -ne 0) { throw "sparse-checkout 실패" }

    $head = (git -C $tmp rev-parse --short HEAD)
    Write-Host "      HEAD $head" -ForegroundColor DarkGray
    Write-Host "      ros2_ws 최근 커밋:" -ForegroundColor DarkGray
    git -C $tmp log -5 --format='        %h  %ad  %s' --date=short -- ros2_ws

    Write-Host "[2/3] 사본 갱신 중..." -ForegroundColor Cyan
    $src = Join-Path $tmp "ros2_ws"
    robocopy $src $dest /E /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy 오류 (코드 $LASTEXITCODE)" }

    # 상류에서 삭제된 파일은 지우지 않는다 — 직접 만든 메모가 날아가지 않게 한다.
    Write-Host "[3/3] 사본에만 있는 파일 확인..." -ForegroundColor Cyan
    $srcFiles  = Get-ChildItem $src  -Recurse -File | ForEach-Object { $_.FullName.Substring($src.Length) }
    $destFiles = Get-ChildItem $dest -Recurse -File | ForEach-Object { $_.FullName.Substring($dest.Length) }
    $orphans = Compare-Object $srcFiles $destFiles | Where-Object { $_.SideIndicator -eq "=>" }

    if ($orphans) {
        Write-Host "      저장소에 없는 파일이 사본에 있다 (상류 삭제분이거나 직접 만든 것):" -ForegroundColor Yellow
        $orphans | ForEach-Object { Write-Host "        $($_.InputObject)" -ForegroundColor DarkGray }
        Write-Host "      필요 없으면 직접 지울 것. 이 스크립트는 지우지 않는다." -ForegroundColor DarkGray
    } else {
        Write-Host "      없음 - 저장소와 일치한다." -ForegroundColor DarkGray
    }

    Write-Host ""
    Write-Host "완료 ($head). $dest" -ForegroundColor Green
}
finally {
    if (Test-Path $tmp) {
        # .git 안에 읽기 전용 속성이 붙어 있어 그냥 지우면 실패할 수 있다
        Get-ChildItem $tmp -Recurse -Force | ForEach-Object { $_.Attributes = 'Normal' }
        Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
    }
}
