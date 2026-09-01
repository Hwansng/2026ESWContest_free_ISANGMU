# 캘리브레이션 백업

LeRobot 캘리브레이션 파일의 백업본. **이 파일을 잃으면 재캘리브레이션이 필요하고,
데이터 수집 이후에 재캘리브레이션하면 기존 데이터셋이 무효가 된다.**

## 파일

| 파일 | 대상 | 생성일 |
|---|---|---|
| `follower_arm.json` | 팔로워암 (SO-ARM101, STS3215 ×6) | 2026-07-10 |
| `leader_arm.json` | 리더암 (SO-ARM101, STS3215 ×6, 7.4V) | 2026-07-11 |

## 원본 위치 — **리더와 팔로워의 경로가 다르다**

```
팔로워: %USERPROFILE%\.cache\huggingface\lerobot\calibration\robots\so_follower\follower_arm.json
리더:   %USERPROFILE%\.cache\huggingface\lerobot\calibration\teleoperators\so_leader\leader_arm.json
```

팔로워는 **robot**, 리더는 **teleoperator** 로 분류되어 `robots/` 와 `teleoperators/` 로 갈린다.
디렉터리 이름도 `so_follower` / `so_leader` 다 (`so101_*` 이 아니다 — 그건 등록된 별칭이고
실제 클래스 이름이 경로가 된다).

LeRobot 명령은 `--robot.id=follower_arm` / `--teleop.id=leader_arm` 으로 파일을 찾는다.
**id 이름이 곧 파일명이다.**

## 복원 방법

```powershell
$base = "$env:USERPROFILE\.cache\huggingface\lerobot\calibration"

$dst = "$base\robots\so_follower"
New-Item -ItemType Directory -Force -Path $dst | Out-Null
Copy-Item ".\follower_arm.json" -Destination $dst -Force

$dst = "$base\teleoperators\so_leader"
New-Item -ItemType Directory -Force -Path $dst | Out-Null
Copy-Item ".\leader_arm.json" -Destination $dst -Force
```

## 왜 백업하는가

캘리브레이션 값은 **두 곳에** 저장된다.

| 데이터 | 저장 위치 | 비고 |
|---|---|---|
| 서보 ID, homing_offset, min/max 한계 | **서보 내부 EPROM** | 비휘발성 — 전원을 빼도 유지됨 |
| 동일한 값의 사본 | **PC의 이 JSON 파일** | LeRobot이 실행 시 참조 |

서보에 값이 남아 있어도 **LeRobot은 PC의 JSON을 찾는다.** 파일이 없으면 재캘리브레이션해야 한다.

그리고 **ACT 정책은 캘리브레이션된 좌표계에서 학습된다.** 데이터 수집 후 영점이 바뀌면
같은 숫자가 다른 물리 자세를 가리키게 되어 **데이터셋을 통째로 버려야 한다.**

→ **수집 시점과 배포 시점의 캘리브레이션은 반드시 동일해야 한다.**

## ⚠️ 주의

- **`lerobot-setup-motors` 를 다시 실행하지 말 것.** ID 부여 과정에서 서보 EPROM 설정이
  초기화될 수 있다. 팔로워는 ID 부여가 이미 끝났으므로 재실행할 이유가 없다.
- 캘리브레이션을 다시 하면 **이 백업도 함께 갱신할 것.**

## 현재 값 (2026-07-10, follower_arm)

| 축 | ID | homing_offset | range_min | range_max |
|---|---|---|---|---|
| shoulder_pan | 1 | 1672 | 1151 | 3856 |
| shoulder_lift | 2 | -1563 | 1462 | 3746 |
| elbow_flex | 3 | 1496 | 804 | 3021 |
| wrist_flex | 4 | 1999 | 919 | 3242 |
| wrist_roll | 5 | **-1968** | **260** | **3836** | ← 2026-08-20 카메라 장착 후 재갱신 |
| gripper | 6 | -1510 | 1313 | 2793 |

나머지 축은 모두 `range_min < 2048 < range_max` 이고 0/4095 에 닿지 않는다 — 합격 기준을 만족한다.

`wrist_roll` 은 원래 0~4095(연속 회전축 기본값)였으나 배선 보호를 위해 창을 제한했다.
**손목 카메라 장착(2026-08-20) 후 재측정한 현재 창은 ±157°(총 314°)** 이고, 창 중심은
정렬 영점이 아니라 **기본위치(영점 −44°, `follower_home.json` = present 2048)** 다 —
시작 자세에서 양방향 대칭 ±157° 가 나오도록 잡았다. 정렬 영점은 present **2544**.
실측 한계는 영점 기준 팔로워 −210°/+126°, 리더 −214°/+122° 이고 여유 100카운트를 뺀
교집합 전체가 창이다. 전 구간 정착 부하 ≤48(한계의 5%), 창 끝단 추종 오차 ≤8카운트,
텔레옵 60초 무결 확인(2026-07-16). 자세한 경위는 구축기록 §5-8.

## 현재 값 (2026-07-11, leader_arm)

| 축 | ID | homing_offset | range_min | range_max | 범위 | 팔로워 대비 |
|---|---|---|---|---|---|---|
| shoulder_pan | 1 | -1402 | 776 | 3439 | 234.1° | 238° |
| shoulder_lift | 2 | **-1061** | 991 | 3219 | 195.8° | 201° |
| elbow_flex | 3 | 285 | 629 | 2816 | 192.2° | 195° |
| wrist_flex | 4 | 1167 | 762 | 3077 | 203.5° | 204° |
| wrist_roll | 5 | **1057** | **260** | **3836** | 314.3° | 314.3° (동일) | ← 2026-08-20 카메라 장착 후 재갱신 |
| gripper | 6 | 31 | 2037 | 3307 | 111.6° | 130° |

> `wrist_roll` 은 양팔이 **같은 창 폭·같은 영점 상대위치**를 써야 1:1 대응이 된다.
> 한쪽만 바꾸면 손목 방향이 어긋난다 — 반드시 `widen_wrist_roll.py` 로 양팔을 함께 갱신할 것.
>
> 🔴 정렬 영점은 `wrist_zero.json` 에 **원시 엔코더 값**으로 보관한다 (팔로워 576 / 리더 3601).
> 창이나 `Homing_Offset` 을 바꿔도 이 값은 건드리지 않는다 — 서보 혼을 분해했을 때만 갱신한다.

전 축이 팔로워 실측치와 일치한다. `gripper` 만 `range_min` 이 2047 에 10 카운트 차로 붙어 있는데,
정규화는 `range_min~range_max` 를 기준으로 하므로 동작에는 문제가 없다.

### 🔴 shoulder_lift 의 homing_offset 은 자동 계산값이 아니다

이 축은 **가동 범위가 원시 엔코더 0 을 가로질러** 훑는 도중 값이 감겼다(wrap).
`lerobot-calibrate` 의 `set_half_turn_homings()` 로는 해결되지 않는다.

Feetech 서보가 `Homing_Offset` 을 **감김 이전에** 적용한다는 점을 이용해,
감김 지점을 관절이 지나가지 않는 구간으로 밀어 해결했다. `Homing_Offset` 은
부호+크기 12비트라 **±2047 이 한계**이므로 필요한 값 3035 대신 **모듈로 등가인 -1061** 을 썼다.

→ **재캘리브레이션 시 `tools/calibrate_leader.py --step homing --skip shoulder_lift` 를 쓸 것.**
   `lerobot-calibrate` 를 그냥 돌리면 이 값이 덮어써져 래핑이 재발한다.

## 도구

| 파일 | 용도 |
|---|---|
| `tools/check_leader.py` | 리더 통신·전압 검증 (7.4V 기준. `check_follower.py` 는 12V 기준이라 오검출) |
| `tools/set_leader_id.py` | 서보 ID 를 한 번에 하나씩 부여 |
| `tools/calibrate_leader.py` | 캘리브레이션 단계 분리 (`raw`→`aim`→`homing`→`ranges`) |
| `tools/measure_leader_range.py` | 가동 범위만 측정 |
