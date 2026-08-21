# ACT 데이터 수집 — 다른 컴퓨터로 이관 가이드

| | |
|---|---|
| 작성 | 2026-08-21 |
| 목적 | 오늘 DRIVE(ESP32) 쪽이 막혀서, **ACT 수집만 별도 컴�터에서 먼저 진행**하기 위한 이관 절차 |
| 전제 | **팔·카메라·세트·조명 등 물리적 환경은 그대로**다. 옮기는 건 **소프트웨어 환경뿐**이다 |
| 범위 | 이 문서는 **수집(`lerobot-record`)만** 다룬다. 학습(`lerobot-train`)은 GPU 검증이 끝난 원래 노트북(RTX 4060)에서 한다 |

> 🔴 **이 문서가 다루지 않는 것 — 물리적 체크리스트.**
> 조명 고정·그리퍼 골무·뚜껑 5조건·차체 통과 10/10·정지 산포는 컴퓨터와 무관한 하드웨어 준비다.
> 이미 확정됐으면 그대로 유효하고, 안 됐으면 컴퓨터를 옮기기 전에 먼저 끝낼 것 —
> 체크리스트는 `작업일정_2026-08-21.md`, 전체판은 `로봇암_카메라_구성정리.md` §11.
>
> 🔴 **수집 프로토콜 ①~⑦(에피소드 시작·종료 지점·물체 배치 범위·실패 처리·속도·길이·조작자)도
> 컴퓨터와 무관하게 먼저 정해져 있어야 한다** — `HazardBot_계획변경_및_개선안_v5.md` §6.
> 안 정해졌으면 수집 시작 전에 반드시 확정할 것. 중간에 바뀌면 앞뒤 에피소드 분포가 달라져
> 데이터셋이 오염된다.

---

## 1. 옮길 파일 목록

이 저장소(`HazardBot` 폴더)에서 **아래 파일들을 그대로 복사**한다. USB나 네트워크 공유 아무거나 상관없다.

| 파일 | 새 컴퓨터에서의 용도 |
|---|---|
| `calibration/follower_arm.json` | 팔로워 서보 캘리브레이션 (homing_offset·range) |
| `calibration/leader_arm.json` | 리더 서보 캘리브레이션 |
| `calibration/follower_home.json` | 팔로워 기본자세(기준 시작 위치) — 🔴 **오늘 재조정한 최신 값** |
| `calibration/wrist_zero.json` | wrist_roll 정렬 영점 (widen_wrist_roll.py 쓸 일 있을 때만 필요) |
| `teleop.ps1` | 텔레옵 실행 스크립트 (Windows 전용) |
| `tools/check_home.py` | 팔로워 기준 자세 확인 |
| `tools/check_align.py` | 리더-팔로워 정렬 확인 |
| `tools/check_goal.py` | Goal_Position 동기화 |
| `tools/check_cameras.py` | 카메라 인덱스 확인 |
| `tools/check_follower.py` | 팔로워 전압/통신 문제 진단 |
| `tools/check_leader.py` | 리더 전압(7.4V) 확인 |
| `tools/check_bus.py` | 버스 통신 문제 진단 |

🔵 통째로 옮기고 싶으면 `HazardBot` 폴더 전체를 복사해도 된다 — 위 목록은 **최소한**이다.

---

## 2. 새 컴퓨터 — 소프트웨어 설치

`로봇암_구축기록.md` §11과 같은 절차이되, **수집 전용이라 CUDA가 필요 없다.**

```powershell
# 1) Python 3.10 격리 환경 — Miniconda
winget install --id Anaconda.Miniconda3
conda create -n lerobot --override-channels -c conda-forge python=3.10 -y
conda activate lerobot

# 2) LeRobot + Feetech 드라이버
pip install "lerobot[feetech]"

# 3) ffmpeg
conda install -n lerobot --override-channels -c conda-forge ffmpeg -y
```

> 🔵 **`pip install lerobot[feetech]`가 기본으로 까는 CPU 빌드 torch를 그대로 둔다.**
> 원래 노트북 문서에서 이건 "함정"으로 적혀 있는데, 그건 **학습**에는 CUDA가 필수라서다.
> **수집은 서보 제어 + 카메라 캡처만 하고 신경망을 안 돌리므로 CPU 빌드로 충분**하다.
> `torch==2.10.0+cu128` 같은 CUDA 특정 버전을 굳이 맞출 필요 없다.

**🚦 Exit 조건**: `python -c "import lerobot; print('ok')"` 가 에러 없이 출력되면 준비 완료.

---

## 3. 캘리브레이션 복원

**리더와 팔로워의 저장 경로가 다르다** (`calibration/README.md`).

```powershell
$base = "$env:USERPROFILE\.cache\huggingface\lerobot\calibration"

New-Item -ItemType Directory -Force -Path "$base\robots\so_follower" | Out-Null
Copy-Item ".\calibration\follower_arm.json" -Destination "$base\robots\so_follower" -Force

New-Item -ItemType Directory -Force -Path "$base\teleoperators\so_leader" | Out-Null
Copy-Item ".\calibration\leader_arm.json" -Destination "$base\teleoperators\so_leader" -Force
```

🔴 **`follower_home.json`과 `wrist_zero.json`은 이 저장소의 `calibration\` 폴더 안에 그대로 두면 된다**
(별도 캐시 경로로 복사할 필요 없음 — `check_home.py`·`widen_wrist_roll.py`가 저장소 상대경로로 직접 읽는다).
단, **저장소 폴더 자체가 새 컴퓨터의 같은 상대 위치에 있어야** 한다 — `HazardBot` 폴더째로 옮길 것.

**확인**:
```powershell
python tools\check_home.py --port COM3
```
팔을 캘리브레이션된 그대로의 자세로 두고 실행했을 때 `wrist_flex`·`wrist_roll`이 **✅ 기준 위치**로 나오면 캘리브레이션 이관 성공.

---

## 4. 카메라 확인 — 반드시 다시 할 것

**인덱스는 컴퓨터마다 다르다.** 이전 컴퓨터의 인덱스(0)를 그대로 믿지 말 것.

```powershell
python tools\check_cameras.py --list
```

`outputs\camera_check\*.png`를 열어서 **화면으로** 손목 카메라 인덱스를 확인한다 (해상도로는 구분 안 됨 — 내장 카메라도 1080p).
손목 = 그리퍼 손가락·팔 브래킷이 보이는 근접 화면.

---

## 5. 텔레옵 검증

### Windows 인 경우

```powershell
powershell -ExecutionPolicy Bypass -File .\teleop.ps1 -Cameras -WristIndex <확인한 인덱스>
```
`[1/4]~[4/4]` 자동 검사(기준 자세 → 정렬 → Goal 동기화 → 시작)를 통과하면 정상.

### Windows 가 아닌 경우 — 수동으로 같은 순서를 밟을 것

```bash
python tools/check_home.py --port <팔로워포트>
python tools/check_align.py --leader <리더포트> --follower <팔로워포트>
python tools/check_goal.py --port <팔로워포트> --fix
python -m lerobot.scripts.lerobot_teleoperate \
  --robot.type=so101_follower --robot.port=<팔로워포트> --robot.id=follower_arm \
  --robot.use_degrees=false \
  --teleop.type=so101_leader --teleop.port=<리더포트> --teleop.id=leader_arm \
  --teleop.use_degrees=false
```

🔴 **`--robot.use_degrees=false --teleop.use_degrees=false`를 절대 빼지 말 것** — 손목 폭주 사고 이력 있음 (`로봇암_구축기록.md` §5-7).

⚠ 실행 중 `Press ENTER to use provided calibration file...` 프롬프트가 뜨면 **그냥 엔터**. `c`를 누르면 캘리브레이션이 날아간다.

---

## 6. 수집 실행

```powershell
$py = "<새 컴퓨터의 conda 환경 python.exe 경로>"

& $py -m lerobot.scripts.lerobot_record `
  --robot.type=so101_follower  --robot.port=<팔로워포트> --robot.id=follower_arm `
  --robot.use_degrees=false `
  --teleop.type=so101_leader   --teleop.port=<리더포트> --teleop.id=leader_arm `
  --teleop.use_degrees=false `
  --robot.cameras="{wrist: {type: opencv, index_or_path: <인덱스>, width: 640, height: 480, fps: 30, backend: 700}}" `
  --dataset.repo_id=local/hazardbot_grasp --dataset.root="<데이터 저장 경로>" `
  --dataset.push_to_hub=false `
  --dataset.num_episodes=10 --dataset.episode_time_s=<프로토콜 ⑥에서 정한 값>
```

> ⚠ `--dataset.*` 플래그 이름은 LeRobot 버전에 따라 달라질 수 있다. 첫 실행 전 `--help`로 확인할 것.
> 🔴 `draccus`가 `--robot.cameras`를 YAML로 읽는다 — **콜론 뒤 공백 필수** (`{type: opencv}`, `{type:opencv}` 아님).
> 🔴 `-m lerobot.scripts.lerobot_record`로 실행하는 이유는 `.exe` 직접 실행 시 Windows Smart App Control이
> 서명 없는 pip 런처를 차단하기 때문이다 (`로봇암_구축기록.md` §6-1). 새 컴퓨터에서도 같은 문제가 날 수 있다.

**체크리스트**:
- [ ] 🔴 `--dataset.push_to_hub=false` — 기본값이 HuggingFace 업로드
- [ ] 🔴 `--robot.use_degrees=false --teleop.use_degrees=false`
- [ ] `--robot.cameras`의 `wrist` 키 이름이 `teleop.ps1`에서 쓰던 것과 동일한지
- [ ] 🔴 **10 에피소드씩 나눠 녹화** — 한 번에 돌리다 끊기면 그때까지 날아간다 (`로봇암_구축기록.md` §10)
- [ ] `streaming_encoding` 켜지 말 것 — 4초 만에 세션 죽은 이력
- [ ] 두 파지 대상을 한 화면에 두지 않기
- [ ] 디스크 여유 확인

---

## 7. 수집 후 — 원래 노트북으로 데이터셋 이동

1. `--dataset.root`로 지정한 폴더 전체를 USB/네트워크로 원래 노트북(RTX 4060)에 복사
2. 원래 노트북에서 학습 벤치마크 재실행 (`data_s` 확인, `로봇암_구축기록.md` §10)
3. 학습 실행:
   ```powershell
   & "C:\Users\sehi5\miniconda3\envs\lerobot\Scripts\lerobot-train.exe" `
     --dataset.repo_id=local/hazardbot_grasp --dataset.root="<복사된 경로>" `
     --policy.type=act --policy.device=cuda --policy.push_to_hub=false `
     --output_dir="<출력경로>" --job_name=hazardbot_grasp `
     --steps=100000 --batch_size=8
   ```

---

## 부록 — 절대 하면 안 되는 것 (수집 컴퓨터 공통)

| | 결과 |
|---|---|
| **`push_to_hub` 기본값 방치** | HuggingFace 업로드 |
| **`use_degrees` 플래그 누락** | 손목 폭주 위험 |
| **캘리브레이션 프롬프트에서 `c`** | 캘리브레이션이 날아간다 |
| **수집 중 재캘리브레이션** | 데이터셋 통째로 무효 |
| **수집 후 카메라 2뷰로 변경** | 키가 `observation.images.wrist` 하나뿐 — 전량 재수집 |
| **리더암에 12V** | 서보 6개 전멸 (₩178,315, 복구 불가). 7.4V 전용 |

---

## 막히면 볼 문서 (같이 복사해두면 좋음)

| 찾는 것 | 위치 |
|---|---|
| 텔레옵 막혔던 지점 7건 | `로봇암_구축기록.md` §5 |
| 캘리브레이션 원리·복원 | `calibration/README.md` |
| 수집 착수 전 전체 체크리스트 | `로봇암_카메라_구성정리.md` §11 |
| 수집 전 순서 ⓪~⑦ | `시나리오_확정_보완_2026-08-16.md` §8.2 |
| 수집 프로토콜 ①~⑦ | `HazardBot_계획변경_및_개선안_v5.md` §6 |
| 학습 벤치마크·수집 함정 | `로봇암_구축기록.md` §10 |
