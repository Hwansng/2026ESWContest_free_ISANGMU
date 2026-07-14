# 리더-팔로워 텔레오퍼레이션 실행 (SO-ARM101)
#
# 캘리브레이션은 이미 끝나 있다. **매번 다시 할 필요 없다.**
# 이력·근거는 로봇암_구축기록.md §6.
#
# ══════════════════════════════════════════════════════════════
#  실행 3단계
# ══════════════════════════════════════════════════════════════
#
#  ① 전원
#
#       팔로워 ──▶ 12V 어댑터 직결        [COM3]
#       리더   ──▶ XL4015 #A  7.4V        [COM5]
#
#     🔴 바꿔 꽂으면 리더 서보 6개가 즉시 파손된다 (₩178,315, 복구 불가).
#        리더 연결 전 **매번** 멀티미터로 7.4V 를 확인할 것.
#        XL4015 #A 는 리더 전용이다 — 트리머를 5V 로 돌려 쓰지 않는다.
#
#     두 어댑터의 USB 를 노트북에 연결한다.
#     COM 번호는 USB 포트를 바꿔 꽂으면 달라진다. 전압으로 구분하는 편이 확실하다.
#
#  ② 두 팔을 비슷한 자세로 맞춘다
#
#     눈으로 봐서 비슷하면 된다 — 텔레옵은 시작하는 순간 팔로워가 리더 자세로 튄다.
#     [1/4][2/4] 가 자동으로 검사하므로 대충 맞춰도 된다.
#     손목(wrist_roll)만 예외다. 연속 회전축이라 중력으로 돌아갈 쉬는 자세가 없어
#     저장된 기준 방향에서만 시작한다 (§5-5).
#
#  ③ 실행
#
#       cd "C:\Users\sehi5\OneDrive\바탕 화면\HazardBot"
#       powershell -ExecutionPolicy Bypass -File .\teleop.ps1
#
#     Ctrl+C 로 종료. 정렬 확인이 먼저 돌고, 실패하면 텔레옵을 시작하지 않는다.
#
# ══════════════════════════════════════════════════════════════
#  옵션
# ══════════════════════════════════════════════════════════════
#
#   .\teleop.ps1                       정렬 확인 후 실행, Ctrl+C 로 종료
#   .\teleop.ps1 -Seconds 180          180초 후 자동 종료   ← 촬영용. 손이 팔에 묶여 있어도 된다
#   .\teleop.ps1 -SkipCheck            정렬 확인 생략 (권장하지 않음)
#   .\teleop.ps1 -LeaderPort COM7 -FollowerPort COM8        COM 번호가 바뀌었을 때
#
#   .\teleop.ps1 -Cameras              🔵 손목 카메라를 rerun 뷰어에 띄운다 = **ACT 최종 구성**
#   .\teleop.ps1 -Cameras -WristIndex 1                     인덱스가 바뀌었을 때
#
#   ⚠ rerun 표시는 지연이 크게 느껴진다 — 매 루프 이미지를 인코딩해 별도 프로세스로 보내기 때문이다.
#     **수집·추론에는 이 경로가 없다.** 실측 캡처 지연은 33~67ms 로 작다 (2026-08-14).
#
#   🔴 아래 도구들은 **conda 환경의 python** 으로 실행해야 한다. 그냥 `python` 은
#      Python 3.14 를 가리켜 ModuleNotFoundError (lerobot / cv2) 로 죽는다 (2026-08-14 실측).
#      셸마다 한 번:  $py = "C:\Users\sehi5\miniconda3\envs\lerobot\python.exe"
#
#   정렬 확인만:  & $py tools\check_align.py --leader COM5 --follower COM3
#   카메라 인덱스: & $py tools\check_cameras.py --list    → 이미지를 열어 확인 (해상도로는 못 가른다)
#
# ══════════════════════════════════════════════════════════════
#  ⚠ 실행 중 이 프롬프트가 뜨면 — 그냥 엔터
# ══════════════════════════════════════════════════════════════
#
#     Press ENTER to use provided calibration file associated with the id ...,
#     or type 'c' and press ENTER to run calibration:
#
#   🔴 'c' 를 누르면 캘리브레이션이 날아가고
#      shoulder_lift 래핑(§5-1)과 영점 불일치(§5-2)가 **함께** 재발한다.
#
# ══════════════════════════════════════════════════════════════
#  이 스크립트가 하는 일 — 직접 실행하지 말아야 하는 이유
# ══════════════════════════════════════════════════════════════
#
#   [1/4] 손목 기준 위치 확인    배선이 팽팽한 위치에서 시작하는 것을 막는다   §5-5
#   [2/4] 자세 정렬 확인         리더 vs 팔로워 Present — 실패 시 시작 안 함
#   [3/4] Goal_Position 동기화   토크가 켜지는 순간 혼자 움직이는 것을 막는다   §5-6
#   [4/4] 텔레옵 시작            시작 실패 시 3회까지 자동 재시도
#
#   부득이 lerobot-teleoperate 를 직접 부를 때는 [3/4] 를 반드시 먼저 돌릴 것:
#       & $py tools\check_goal.py --port COM3 --fix
#   그리고 --robot.use_degrees=false --teleop.use_degrees=false 를 빼지 말 것 (아래 §5-7).
#
# ══════════════════════════════════════════════════════════════
#  문제 해결
# ══════════════════════════════════════════════════════════════
#
#   "이 시스템에서 스크립트를 실행할 수 없으므로"  → -ExecutionPolicy Bypass 를 붙인다
#   "포트를 열 수 없다"                            → 이전 텔레옵이 살아 있는지 확인
#   정렬 확인 실패                                 → 표에서 🔴 인 축을 손으로 맞춘다.
#                                                     손목은 기준 위치, **리더를** 팔로워에 맞춘다
#   팔로워가 안 움직임 (12V 미인가)                → & $py tools\check_follower.py --port COM3
#   Goal 동기화에 "응답 없음"                      → 팔로워 전원을 빼고 다시 넣는다
#   3회 모두 시작 실패                             → & $py tools\check_bus.py --port COM3 --seconds 30
#   COM 이 아예 안 보임                            → USB-C **데이터** 케이블인지 먼저 의심.
#                                                     충전 전용도 어댑터 LED 는 켜져 정상처럼 보인다
#   draccus ParsingError (cameras)                 → 콜론 뒤 공백이 빠진 것. `{type: opencv}` 가 맞고
#                                                     `{type:opencv}` 는 YAML 이 키 하나로 읽어 죽는다.
#                                                     🔴 재시도 3회가 도는데 인자 문제라 다 실패한다
#   스크립트 한글이 깨짐                           → 🔴 이 파일은 **UTF-8 with BOM** 으로 저장할 것 §5-4
#   "애플리케이션 제어 정책에서 이 파일을 차단"     → Smart App Control 이 pip 의 .exe 런처를 막은 것.
#                                                     이 스크립트는 python -m 으로 우회한다 (아래 주석).
#                                                     🔴 SAC 를 끄지 말 것 — 한 번 끄면 재설치 전엔 못 켠다
#
#   어느 쪽이 리더인지:  & $py tools\check_leader.py --port COM5 --volt-only   (7.4V = 리더)
#   COM 목록:            & $py -m lerobot.scripts.lerobot_find_port
#
# ══════════════════════════════════════════════════════════════

param(
    [double]$Seconds = 0,
    [switch]$SkipCheck,
    [switch]$Cameras,
    [int]$WristIndex = 0,
    [string]$FollowerPort = "COM3",
    [string]$LeaderPort = "COM5"
)

$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"

$py = "C:\Users\sehi5\miniconda3\envs\lerobot\python.exe"

# 🔴 Scripts\lerobot-teleoperate.exe 를 직접 부르지 않는다 (2026-08-06).
#    Windows 11 Smart App Control 이 Enforce(=1) 상태라 pip 이 생성한 서명 없는 .exe 런처를
#    "애플리케이션 제어 정책에서 이 파일을 차단했습니다" 로 막는다.
#    python.exe 는 서명돼 있어 통과하므로, 같은 진입점을 -m 으로 부른다.
#    (entry_points.txt: lerobot-teleoperate = lerobot.scripts.lerobot_teleoperate:main)
#
#    🔴 Smart App Control 을 끄지 말 것 — 한 번 끄면 Windows 재설치 전에는 다시 켤 수 없다.
#    lerobot-record / lerobot-train / lerobot-find-port 등 모든 lerobot 명령이 같은 제약을 받는다.
$teleopModule = "lerobot.scripts.lerobot_teleoperate"

Set-Location $PSScriptRoot

if (-not $SkipCheck) {
    # wrist_roll 은 연속 회전축이라 중력으로 돌아갈 쉬는 자세가 없다.
    # 매번 다른 방향에서 시작하면 배선이 팽팽한 위치에서 텔레옵이 시작될 수 있고,
    # 실제로 그것이 과부하로 이어졌다 (구축기록 5-5).
    # → 저장된 기준 방향에서만 시작한다. 이 검사는 서보를 움직이지 않는다.
    Write-Host "[1/4] 손목 기준 위치 확인..." -ForegroundColor Cyan
    & $py "tools\check_home.py" --port $FollowerPort
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "중단했다. 팔로워 손목을 **손으로** 기준 위치까지 돌린 뒤 다시 실행할 것." -ForegroundColor Yellow
        Write-Host "기준을 새로 잡으려면: $py tools\check_home.py --port $FollowerPort --save" -ForegroundColor DarkGray
        exit 1
    }
    Write-Host ""

    # 텔레옵은 시작하는 순간 팔로워 토크를 켜고 리더 자세로 추종시킨다.
    # 두 팔이 크게 어긋나 있으면 그 순간 급격히 움직여 파츠에 충격이 간다.
    Write-Host "[2/4] 자세 정렬 확인..." -ForegroundColor Cyan
    & $py "tools\check_align.py" --leader $LeaderPort --follower $FollowerPort
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "중단했다. 위 표에서 차이가 큰 축을 맞춘 뒤 다시 실행할 것." -ForegroundColor Yellow
        Write-Host "손목은 기준 위치에 두고 **리더를** 팔로워에 맞출 것." -ForegroundColor Yellow
        Write-Host "검사를 무시하려면: .\teleop.ps1 -SkipCheck" -ForegroundColor DarkGray
        exit 1
    }
    Write-Host ""
}

# 서보의 Goal_Position 은 토크가 꺼진 동안에도 마지막 명령값으로 남는다.
# 그 사이 팔이 중력으로 처지거나 손으로 옮겨지면 Goal 과 Present 가 벌어지고,
# 토크가 켜지는 순간 서보가 저장된 Goal 로 되돌아가며 혼자 움직인다.
# LeRobot 의 configure() 는 이를 동기화하지 않는다 ("arm is in a rest position" 가정).
#
# 정렬 확인(Present 비교)으로는 잡히지 않으므로 여기서 따로 처리한다.
# 반드시 정렬 조정이 끝난 **직후**에 실행해야 한다 — 이후 팔을 움직이면 다시 벌어진다.
Write-Host "[3/4] 팔로워 Goal_Position 동기화..." -ForegroundColor Cyan
& $py "tools\check_goal.py" --port $FollowerPort --fix
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "중단했다. Goal 동기화가 실패한 상태로 텔레옵을 시작하면" -ForegroundColor Yellow
    Write-Host "서보가 이전 위치로 튀거나 토크를 문 채 남을 수 있다." -ForegroundColor Yellow
    Write-Host "위 메시지에 '응답 없음'이 있으면 **팔로워 전원을 빼고 다시 넣을 것.**" -ForegroundColor Yellow
    exit 1
}
Write-Host ""

# 🔴 use_degrees=false 는 절대 빼면 안 된다.
#    기본값(DEGREES 모드)은 goal 을 어디에서도 잘라주지 않는다. 리더 손목이 캘리브레이션
#    창 밖에 있으면 음수 goal 이 계산되고, sign-magnitude 인코딩(0x8800)을 서보가
#    raw 2048 로 해석해 팔로워 손목이 배선을 감으며 129° 폭주한다 (2026-07-28 사건).
#    RANGE 모드는 리더 읽기와 팔로워 goal 을 모두 창 안으로 잘라 이 경로를 차단한다.
#    lerobot-record / eval 에서도 반드시 같은 플래그를 써야 한다 (액션 스케일이 달라진다).
$leaderArgs = @(
    "--robot.type=so101_follower", "--robot.port=$FollowerPort", "--robot.id=follower_arm",
    "--robot.use_degrees=false",
    "--teleop.type=so101_leader", "--teleop.port=$LeaderPort", "--teleop.id=leader_arm",
    "--teleop.use_degrees=false"
)
if ($Seconds -gt 0) { $leaderArgs += "--teleop_time_s=$Seconds" }

# 카메라 미리보기 — 마운트 위치를 정할 때 쓴다 (로봇암_카메라_구성정리.md §9).
#
# 🔵 ACT 카메라는 **손목 SO-ARM 2MP 한 대뿐**이다 (2026-08-14 확정).
#    프론트 Innomaker 는 로봇에서 제거했다 — 진우는 자기 카메라를 따로 쓴다.
#    노트북에 남은 것은 손목 카메라와 **노트북 내장 카메라** 둘뿐이다.
#
# 🔴 인덱스는 장치 이름이 아니라 **열거 순서**다. 앞 번호 장치가 사라지면 뒤 번호가 당겨진다.
#    2026-08-14 하루에만 세 번 바뀌었다 (덮개·탈착 때문). **매번 확인할 것.**
#
# 🔴 해상도로는 못 가른다 — **내장 카메라도 1080p** 라 SO-ARM 2MP 와 같다. 화면을 봐야 한다:
#        & $py tools\check_cameras.py --list     → outputs\camera_check\*.png 를 열어볼 것
#    손목  = **그리퍼 손가락과 팔 브래킷이 보인다.** 팔을 움직이면 같이 움직인다
#    내장  = 노트북 앞쪽 장면. 셔터로 막혀 있으면 까만 화면에 카메라 금지 아이콘 (정적 이미지)
#
# backend:700 = DSHOW. Windows 기본값(ANY→MSMF)은 open 이 수 초 걸리거나 실패하는 경우가 있다
# (tools\check_cameras.py 주석과 같은 이유).
#
# 캡처는 640x480/30fps 로 고정한다 — 데이터 수집과 같은 조건이어야 여기서 본 화각이 그대로 간다.
if ($Cameras) {
    # 🔴 draccus 는 이 값을 YAML 로 읽는다. **콜론 뒤 공백이 반드시 있어야 한다.**
    #    "{type:opencv}" 처럼 붙여 쓰면 YAML 이 `type:opencv` 를 키 하나로 보고
    #    ParsingError: Expected a dict with a 'type' key ... 로 죽는다 (2026-08-14 실측).
    #    큰따옴표는 쓰지 않는다 — PowerShell 5.1 이 네이티브 exe 로 넘길 때 망가뜨린다.
    #    공백은 있어도 된다. PowerShell 이 인자 전체를 알아서 한 덩어리로 묶어 넘긴다.
    # 🔵 ACT 입력은 **손목 1뷰**다 — 수집·학습·추론 전부 (2026-08-14 확정).
    #    프론트는 로봇에서 아예 제거했다. 지연·대역폭 때문이 아니다 —
    #    실측상 2대와 1대의 FPS 가 같았다 (26.5 vs 26.6).
    #
    # 🔴 아래 $camSpec 은 **lerobot-record 에도 글자 그대로 써야 한다.** 여기서 본 화각이
    #    곧 데이터셋에 들어가는 화각이다. 키 이름(wrist)이 달라지면 정책 입력이 안 맞는다.
    $camSpec = "{wrist: {type: opencv, index_or_path: $WristIndex, width: 640, height: 480, fps: 30, backend: 700}}"
    $leaderArgs += "--robot.cameras=$camSpec"
    $leaderArgs += "--display_data=true"

    # 🔴 --display_data 는 rerun **뷰어 실행 파일**을 PATH 에서 찾아 띄운다 (rr.spawn).
    #    이 스크립트는 conda 를 activate 하지 않고 python.exe 를 절대 경로로 부르므로
    #    환경의 실행 파일 경로가 PATH 에 없다 → "Failed to find Rerun Viewer executable in PATH"
    #    (2026-08-14 실측).
    #
    #    🔴 Scripts\rerun.exe (108KB) 를 PATH 에 넣지 말 것 — pip 이 만든 서명 없는 런처라
    #       Smart App Control 이 막는 바로 그 형태다. 진짜 뷰어는 아래 rerun_cli 쪽 143MB 바이너리이고
    #       미서명이지만 SAC 를 통과한다 (실행 확인함).
    $rerunDir = Join-Path (Split-Path $py -Parent) "Lib\site-packages\rerun_sdk\rerun_cli"
    if (Test-Path (Join-Path $rerunDir "rerun.exe")) {
        $env:PATH = "$rerunDir;$env:PATH"
    } else {
        Write-Host "⚠ rerun 뷰어를 찾지 못했다: $rerunDir" -ForegroundColor Yellow
        Write-Host "  카메라 영상이 안 보일 수 있다. 텔레옵 자체는 정상 동작한다." -ForegroundColor Yellow
    }
}

if ($Cameras) {
    Write-Host "      카메라: wrist=$WristIndex 단독 (ACT 구성)  640x480/30fps, DSHOW" -ForegroundColor DarkGray
    Write-Host "      rerun 뷰어가 별도 창으로 열린다. 첫 프레임은 자동노출 때문에 어둡다." -ForegroundColor DarkGray
    Write-Host "      그리퍼 손가락이 안 보이면 내장 카메라다 — -WristIndex 를 바꿀 것." -ForegroundColor DarkGray
    Write-Host ""
}
Write-Host "[4/4] 텔레옵 시작 — 팔로워 토크가 켜진다. 주변에서 손을 치울 것." -ForegroundColor Cyan
if ($Seconds -gt 0) {
    Write-Host "      $Seconds 초 후 자동 종료." -ForegroundColor DarkGray
} else {
    Write-Host "      Ctrl+C 로 종료." -ForegroundColor DarkGray
}
Write-Host ""
Write-Host '⚠ "Press ENTER to use provided calibration file..." 프롬프트가 뜨면 그냥 엔터를 칠 것.' -ForegroundColor Yellow
Write-Host "  'c' 를 누르면 캘리브레이션이 날아가고 shoulder_lift 래핑이 재발한다." -ForegroundColor Yellow
Write-Host ""

# LeRobot 은 connect() 에서 6축에 레지스터를 수십 개 연속으로 쓴다.
# 그 중 한 번이라도 응답을 놓치면(`after 1 tries` — 재시도 없음) 시작 자체가 실패한다.
# 2026-07-28 실측: 시작 시도 8회 중 4회가 이 구간에서 실패했다. 매번 다른 ID 였다.
# 원인 후보는 configure_motors() 가 쓰는 Return_Delay_Time=0 (응답까지 2µs) 이다.
# 반이중 버스에서 어댑터가 송신→수신 전환을 그 안에 못 끝내면 응답 앞부분이 잘린다.
#
# LeRobot 이 매 연결마다 0 으로 덮어쓰므로 값을 유지시킬 수 없다. 재시도로 대응한다.
$maxAttempts = 3
for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
    $started = Get-Date
    & $py "-m" $teleopModule @leaderArgs
    $code = $LASTEXITCODE
    $elapsed = ((Get-Date) - $started).TotalSeconds

    if ($code -eq 0) { break }

    # 오래 돌다 끝난 것은 시작 실패가 아니다 — 재시도하면 안 된다.
    if ($elapsed -gt 15) {
        Write-Host ""
        Write-Host "텔레옵이 $([int]$elapsed)초 실행 후 종료됐다 (코드 $code)." -ForegroundColor Yellow
        Write-Host "시작 실패가 아니므로 재시도하지 않는다. 위 오류를 확인할 것." -ForegroundColor Yellow
        break
    }

    if ($attempt -lt $maxAttempts) {
        Write-Host ""
        Write-Host "시작 실패 ($attempt/$maxAttempts) — 연결 시 통신 글리치. 3초 후 재시도." -ForegroundColor Yellow
        Start-Sleep -Seconds 3
    } else {
        Write-Host ""
        Write-Host "$maxAttempts 회 모두 실패했다." -ForegroundColor Red
        # 🔴 재시도는 **연결 시 통신 글리치**만을 위한 것이다. 위 오류가 아래에 해당하면
        #    버스와 무관하고, 3번 다시 해도 똑같이 실패한다 (인자가 바뀌지 않으므로).
        Write-Host "  · ParsingError / draccus  → 버스 문제가 아니라 **인자 문제**다." -ForegroundColor Yellow
        Write-Host "                              -Cameras 를 썼다면 콜론 뒤 공백을 확인할 것." -ForegroundColor DarkGray
        Write-Host "  · 카메라 open 실패        → 다른 프로그램이 카메라를 쥐고 있는지 확인." -ForegroundColor Yellow
        Write-Host "                              $py tools\check_cameras.py --probe" -ForegroundColor DarkGray
        Write-Host "  · 그 외 (연결 중 무응답)  → 버스 상태를 확인할 것:" -ForegroundColor Yellow
        Write-Host "                              $py tools\check_bus.py --port $FollowerPort --seconds 30" -ForegroundColor DarkGray
    }
}
