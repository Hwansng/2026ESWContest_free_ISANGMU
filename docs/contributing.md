# HazardBot 2026 협업 가이드

본 문서는 3인 팀의 Git/GitHub 협업 방식을 정의한다.

## 1. 팀 구성 및 담당 영역

> 🔵 **2026-08-18 역할 재분담 반영.** 초기 분담(승환=암+비전 / 강희=AMR+전력)은 폐기됐다.
> **전력은 전 구간 승환 전담**이고, AMR 주행도 7/20 에 승환에게 이관됐다.
> 역할별 상세는 [`docs/handover/담당정리_*_2026-08-18.md`](02_schedule/) 참조.

| 팀원 | 주 담당 | 코드·문서 영역 |
|---|---|---|
| **승환** | 로봇암 · ACT · DRIVE 주행 · **전력 전 구간** · 시나리오 · 세트 | `arm/`, `firmware/esp32_drive/`, `firmware/sts3215/`, `firmware/docs/`, `hardware/`, `docs/scenario/`, `docs/schedule/`, `tools/` |
| **강희** | ENV 보드 (가스·화염 환경 감시) · 만능기판 납땜 · 임계값 | ENV 펌웨어(저장소 밖 · 로컬), `firmware/docs/amr_v9_4sensor_*` |
| **진우** | RPi 5 통합 · ROS2 노드 · FSM · 대시보드 | `ros2_ws/src/` (`mission_orchestrator`, `vision_node`, `hazard_detector`, `amr_bridge`, `arm_bridge`, `sensor_bridge`, `arm_controller`, `arm_act_node`, `hazardbot_dashboard`) |

각자 자기 영역에서 단독 개발/테스트하며, 통합은 합동 작업일에 세 플랫폼을 연결한다.
합동 회차 기록은 [`docs/schedule/작업일정_*.md`](02_schedule/) 에 있다.

## 2. 브랜치 전략

```
main ─────●────────●───────────●───────●─→  (배포 가능 상태만 유지, 보호 브랜치)
           \      /  \        /       /
            feat/A.. ─┘     feat/B..  /
                                     /
                          feat/C....┘
```

- **`main`**: 항상 빌드 가능 + 시연 가능 상태. 직접 push 금지, PR 머지만 허용
- **`feat/<영역>-<짧은_설명>`**: 새 기능
  - 예: `feat/arm-compliance-grip`, `feat/amr-line-pid`, `feat/mission-fsm`
- **`fix/<영역>-<짧은_설명>`**: 버그 수정
- **`docs/<주제>`**: 문서만 수정
- **`hotfix/<주제>`**: 시연 직전 긴급 수정

브랜치는 작업 완료 후 PR 머지되면 즉시 삭제한다 (origin/main만 유지).

## 3. 커밋 메시지 컨벤션

**한국어로 작성**. 형식:

```
<type>: <한 줄 요약 50자 이내>

<상세 설명 — 선택. 왜 이렇게 했는지 위주로 작성>
```

`<type>` 종류:
- `feat`: 새 기능
- `fix`: 버그 수정
- `refactor`: 동작 변경 없는 리팩터링
- `docs`: 문서만
- `chore`: 빌드/CI/설정
- `test`: 테스트 추가/수정
- `hw`: 하드웨어/회로/STL 변경

**예시:**
```
feat: STS3215 SYNC_READ로 6축 위치/부하 일괄 수신

기존 개별 READ는 6축 × 3ms = 18ms 소요로 10ms 폴링 주기 초과.
SYNC_READ 한 번에 6축 모두 읽어 약 5ms로 단축.
```

## 4. PR (Pull Request) 프로세스

1. `feat/...` 브랜치에서 작업 → 로컬에서 빌드/테스트
2. push 후 GitHub에서 PR 생성. **base: `main`**
3. PR 제목: 커밋 메시지 컨벤션 동일
4. PR 본문 템플릿:
   ```markdown
   ## 변경 사항
   - …

   ## 테스트
   - [ ] 로컬 빌드 통과
   - [ ] 단독 보드 테스트 (어떤 보드/시나리오)
   - [ ] CI 통과 (Arduino / ROS2)

   ## 관련 이슈
   #123
   ```
5. **리뷰어**: 자기 영역 외 1명 이상 (예: 팀원 A의 PR은 B 또는 C 리뷰)
6. **CI 통과 + 리뷰 승인 1+** 후 머지
7. 머지 방식: **Squash and merge** (히스토리 깔끔)

## 5. 충돌 회피 규칙

- 공유 파일(`README.md`, `docs/architecture.md`, `.gitignore`)은 변경 전 공지
- 핀맵·배선 변경은 **`firmware/docs/배선_확정_2026-08-14.md` 가 정본**이다. 이 문서부터 고치고, PR 본문에 변경 표를 포함한다 (DRIVE·ENV 양쪽 영향 검토)
- 통신 규격(포트 8765 · 명령 포맷 · 타임아웃) 변경은 **진우 동의 필수** — 합의 원문은 `docs/handover/회신_진우_2026-08-25.md`
- 🔴 **캘리브레이션·카메라 구성을 바꾸면 기존 ACT 데이터셋이 전량 무효**가 된다. 수집 이후에는 `arm/calibration/` 을 건드리기 전에 반드시 공지한다

## 6. CI 정책

- **Arduino 컴파일** (`.github/workflows/arduino.yml`): DRIVE · 서보 스케치 컴파일 통과 필수
- **ROS2 build** (`.github/workflows/ros2.yml`): `colcon build` + `colcon test` 통과 필수 (패키지가 있을 때)
- CI 실패 PR은 머지 금지

## 7. 비밀 정보 관리

- Wi-Fi SSID/PW, MQTT 자격증명, API 키 등은 **절대 커밋 금지**
- ESP32 펌웨어는 `secrets.h`(gitignored)로 분리:
  ```cpp
  // firmware/esp32_drive/<스케치>/secrets.h  (gitignored)
  #define WIFI_SSID "your_ssid"
  #define WIFI_PASS "your_pass"
  ```
- ROS2는 `config/secrets.yaml`(gitignored) + `config/secrets.example.yaml`(템플릿)
- 실수로 커밋 시 즉시 슬랙 공지 → 새 자격증명 발급 → `git filter-repo`로 히스토리 제거

## 8. 통합 테스트 일정

| 시점 | 항목 | 상태 |
|---|---|---|
| 07/16 | **★ 마일스톤 1 (텔레옵)** — 60Hz / 60초 무결, 관문 G2 Exit | ✅ 달성 |
| 08/14 | 시연 공간 확보 · 세트 제작 | ✅ 완료 |
| 08/26 | ACT 수집 100/100 에피소드 | ✅ 완료 |
| 08/27 | ACT 학습 100,000 스텝 | ✅ 완료 |
| 08/28 ~ 08/30 | 실물 롤아웃 검증 (판정 기준: 물체별 10회 중 8회) | 진행 |
| 08/31 | 산출물 정본 마감 (마감 09/04, 9/1~9/4 버퍼) | 예정 |

전체 13주 배치는 [`docs/schedule/작업일정_전체_2026-06-01_2026-08-31.md`](02_schedule/작업일정_전체_2026-06-01_2026-08-31.md) 참조.

## 9. 이슈 관리

- 버그/기능 요청은 GitHub Issues 사용
- 라벨: `bug`, `feature`, `arm`, `amr`, `vision`, `mission`, `hardware`, `docs`, `urgent`
- 시연 직전 발견된 이슈는 `urgent` 라벨 + 슬랙 즉시 공유

## 10. 로컬 환경 셋업

### Windows (펌웨어 개발)
- Arduino IDE 2.x + ESP32 보드 매니저 3.0.x
- VS Code + Arduino 확장 (선택)
- Git for Windows 2.40+

### Ubuntu 24.04 (ROS2 개발)
```bash
# ROS2 Jazzy 설치
sudo apt update && sudo apt install ros-jazzy-desktop python3-colcon-common-extensions
echo "source /opt/ros/jazzy/setup.bash" >> ~/.bashrc
```

### Raspberry Pi 5 (시연 환경)
- Ubuntu 24.04 LTS for RPi5 (공식 이미지)
- ROS2 Jazzy (소스 또는 deb)
- OpenCV 4.x (apt 또는 pip)
- 액티브 쿨러 팬 필수

---

질문이나 제안은 GitHub Issues에 등록.
