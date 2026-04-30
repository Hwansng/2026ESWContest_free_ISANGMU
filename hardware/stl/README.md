# SO-ARM101 STL 파일

본 폴더에는 SO-ARM101 6DOF 로봇 암 프레임 STL 파일이 포함되어 있다.

## 포함된 파일

| 파일명 | 크기 | 용도 |
|---|---|---|
| `Base_SO101.stl` | 0.47 MB | 베이스 (섀시 마운팅 인터페이스) |
| `Prusa_Follower_SO101.stl` | 4.83 MB | Prusa 프린터용 통합 모델 (전체 암) |
| `Ender_Follower_SO101.stl` | 24.82 MB | Ender 프린터용 통합 모델 (전체 암) |

> 출처: [Hugging Face LeRobot SO-ARM101](https://github.com/huggingface/lerobot) 오픈소스 프레임. 사용한 프린터에 맞춰 `Prusa_*` 또는 `Ender_*` 중 하나를 슬라이싱한다.

## 출력 옵션

| 항목 | 값 |
|---|---|
| 재료 | PLA |
| 인필 | 20 ~ 30% |
| 레이어 두께 | 0.2 mm |
| 서보 피팅 공차 | 0.1 ~ 0.2 mm (출력 후 줄로 미세 다듬기) |
| 노즐 | 0.4 mm |

## 자체 제작 어댑터

LeRobot 원본은 테이블 클램프 고정 설계이므로, **2WD 섀시 마운팅용 베이스 어댑터 플레이트**는 별도 제작한다.

- 위치: `hardware/stl/custom/chassis_adapter.stl` (예정 — 자체 모델링)
- 섀시 나사 구멍에 맞춰 베이스 파트를 수정하여 출력

## 라이선스

LeRobot 원본 STL은 [Hugging Face LeRobot 저장소](https://github.com/huggingface/lerobot)의 라이선스를 따른다. 재배포 시 원 라이선스 표기 필수.
