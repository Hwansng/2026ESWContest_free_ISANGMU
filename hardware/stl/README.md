# SO-ARM101 STL 파일

본 폴더에는 SO-ARM101 6DOF 로봇 암 프레임 STL 파일을 배치한다. **STL 자체는 git 추적에서 제외**(`.gitignore` `*.stl`)되며, 각자 아래 절차로 다운로드한다.

## 다운로드 (수동)

1. Hugging Face LeRobot 저장소 접속: https://github.com/huggingface/lerobot
2. SO-ARM 관련 디렉토리에서 STL 파일 확보 (저장소 구조는 변경될 수 있으므로 최신 docs 참고)
3. 본 디렉토리(`hardware/stl/`)에 배치

## 필요 파트 (예시)

| 파일명 | 용도 | 출력 옵션 |
|---|---|---|
| `base.stl` | 베이스 (섀시 마운팅) | PLA, 인필 30%, 0.2mm 레이어 |
| `shoulder.stl` | 1축 회전 (어깨) | PLA, 인필 25% |
| `upper_arm.stl` | 2축 (상완) | PLA, 인필 20% |
| `forearm.stl` | 3축 (전완) | PLA, 인필 20% |
| `wrist_pitch.stl` | 4축 (손목 피치) | PLA, 인필 25% |
| `wrist_roll.stl` | 5축 (손목 롤) | PLA, 인필 25% |
| `gripper_left.stl` | 그리퍼 좌측 | PLA, 인필 30% |
| `gripper_right.stl` | 그리퍼 우측 | PLA, 인필 30% |

## 자체 제작 어댑터

LeRobot 원본은 테이블 클램프 고정 설계이므로 **2WD 섀시 마운팅용 베이스 어댑터 플레이트**를 별도 제작한다.

- 위치: `hardware/stl/custom/chassis_adapter.stl` (자체 모델링)
- `.gitignore`에서 `custom/` 하위 STL은 추적 대상으로 예외 처리됨

## 출력 공차

서보 피팅: **0.1 ~ 0.2mm** (출력 후 줄로 미세 다듬기)

## 라이선스

LeRobot 원본 STL은 [Hugging Face LeRobot 저장소](https://github.com/huggingface/lerobot)의 라이선스를 따른다. 재배포 시 원 라이선스 표기 필수.
