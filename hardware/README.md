# SO-ARM101 STL 파일

본 폴더에는 SO-ARM101 6DOF 로봇 암 프레임 STL 파일이 포함되어 있다.

## 포함된 파일

| 파일명 | 크기 | 용도 |
|---|---|---|
| `Base_SO101.stl` | 0.47 MB | 베이스 (섀시 마운팅 인터페이스) |
| `Prusa_Follower_SO101.stl` | 4.83 MB | Prusa 프린터용 통합 모델 (전체 암) |
| `Ender_Follower_SO101.stl` | 24.82 MB | Ender 프린터용 통합 모델 (전체 암) |
| `BRACKET.stl` · `PCB Support.stl` | — | 브래킷 · PCB 서포트 |
| `Waffle_Plate.stl` · `Waffle_Plate.3mf` | — | TB3 Waffle 플레이트 (3mf = 슬라이서 프로젝트) |
| `tb3_pi_camera_frame.stp` · `tb3_pcb_support-ibb-01.stp` | — | TB3 카메라 프레임 · PCB 서포트 STEP |
| `Hexagon Case.stl` | — | 육각 케이스 |
| `1.68g_tb3_pi_camera_frame_PLA_13m19s.gcode` | — | 카메라 프레임 출력 G-code (PLA · 13m19s · 1.68g) |

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

LeRobot 원본은 테이블 클램프 고정 설계다. **2WD 섀시 마운팅용 베이스 어댑터**는 자체 모델링했다.

- 위치: [`hardware/arm_base/`](../arm_base/)
- `Base_SO101_chassis_v1.{step,stl}` → `v2` 로 개정. **v2 를 쓴다.**
- `Base_SO101.step` 은 LeRobot 원본 베이스의 STEP 변환본이다 (수정 기준용)

## 라이선스

LeRobot 원본 STL은 [Hugging Face LeRobot 저장소](https://github.com/huggingface/lerobot)의 라이선스를 따른다. 재배포 시 원 라이선스 표기 필수.
