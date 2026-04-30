# SO-ARM101 STL 다운로드 스크립트 (Windows PowerShell)
#
# 사용법: .\download_stl.ps1
#
# 주의: LeRobot 저장소 구조 변경 시 $SourceRepo / $SourcePath를 수정해야 한다.

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ScriptDir

$SourceRepo = "huggingface/lerobot"
# TODO: 실제 STL 경로 확인 후 수정
$SourcePath = "docs/source/_static/img/so100"

Write-Host "[*] Cloning sparse checkout from $SourceRepo ..."
$TmpDir = Join-Path $env:TEMP ("lerobot_stl_" + [System.Guid]::NewGuid().ToString("N").Substring(0, 8))
New-Item -ItemType Directory -Path $TmpDir | Out-Null

try {
    git clone --depth 1 --filter=blob:none --sparse "https://github.com/$SourceRepo.git" $TmpDir
    Push-Location $TmpDir
    try {
        git sparse-checkout set $SourcePath
    } finally {
        Pop-Location
    }

    Write-Host "[*] Copying STL files ..."
    $StlFiles = Get-ChildItem -Path (Join-Path $TmpDir $SourcePath) -Filter *.stl -Recurse -ErrorAction SilentlyContinue
    if (-not $StlFiles) {
        Write-Warning "STL 파일을 찾지 못함. README.md의 수동 다운로드 절차를 따르라."
        exit 1
    }
    foreach ($f in $StlFiles) {
        Copy-Item $f.FullName -Destination $ScriptDir -Force
    }

    Write-Host "[✓] Done. 다운로드된 파일:"
    Get-ChildItem -Path $ScriptDir -Filter *.stl | Select-Object Name, Length
} finally {
    if (Test-Path $TmpDir) {
        Remove-Item -Recurse -Force $TmpDir
    }
}
