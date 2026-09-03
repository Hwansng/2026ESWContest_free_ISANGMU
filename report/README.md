# 개발완료보고서 — 빌드 시스템

제24회 임베디드SW경진대회 자유공모 부문 제출용 **개발완료보고서(PPT)** 를
python-pptx 로 생성한다. 슬라이드를 손으로 그리지 않고 코드로 만든다.

## 왜 코드로 만드나

수치가 바뀔 때마다 22장을 손으로 고치면 어딘가는 반드시 옛날 값이 남는다.
[`build_deck.py`](빌드/build_deck.py) 는 페이지마다 함수 하나라서, 값이 바뀌면
고칠 자리가 한 군데다. 빌드할 때 **글상자 넘침을 미리 계산**해 `[overflow]` /
`[wide]` 로 경고하므로, 글자가 상자 밖으로 삐져나온 채로 제출되는 일이 없다.

## 구성

| 파일 | 역할 |
| --- | --- |
| [`빌드/build_deck.py`](빌드/build_deck.py) | 22장 생성. 페이지당 함수 하나 (`s_cover` · `p01`~`p20` · `s_close`) |
| [`빌드/deck_lib.py`](빌드/deck_lib.py) | 도형·타이포 프리미티브, 넘침 추정기 |
| [`빌드/prep_images.py`](빌드/prep_images.py) | 시연 영상에서 슬라이드용 스틸을 뽑아 `img/` 에 저장 |
| [`빌드/build_review.py`](빌드/build_review.py) | 렌더 결과 검토용 시트 생성 |
| [`design.md`](design.md) | 디자인 시스템 (좌표·색·타입스케일). 영문 |
| [`PPT_구성안_2026-09-01.md`](PPT_구성안_2026-09-01.md) | 페이지별 구성안 + 대회 규정 정리 + 수치 정정 이력 |
| [`rollout_plan.csv`](rollout_plan.csv) | ACT 롤아웃 30회 원측정값 (cp949). 15p 86.7% 의 근거 |
| [`docs/03_scenario_demo/제출영상_스크립트_2026-09-01.md`](../docs/03_scenario_demo/제출영상_스크립트_2026-09-01.md) | 시연 영상 내레이션 (정본은 docs 쪽 하나뿐이다) |

## 빌드

```bash
pip install python-pptx pillow imageio-ffmpeg
python 빌드/build_deck.py        # → HazardBot_개발완료보고서_YYYY-MM-DD.pptx
```

경고 없이 끝나면 (`no layout warnings`) 넘친 글상자가 없다는 뜻이다.

## 저장소에 없는 것

용량 때문에 뺐다. 없어도 `build_deck.py` 는 돈다 — `img/` 의 스틸이 이미 있으니까.

- **`영상/`** (약 113MB) — 시연 원본 영상. `prep_images.py` 의 입력이다.
  제출본은 YouTube 링크로 갈음한다.
- **`폰트/`** — Pretendard OTF 9종. [원 저장소](https://github.com/orioncactus/pretendard)
  에서 받는다 (SIL OFL 1.1). **설치돼 있지 않으면 폰트가 대체되어 레이아웃이 깨진다.**
- **`양식/`** — 대회 주최 측 배포 양식·규정 PDF (재배포 대상 아님).

## 분량 산정

표지와 마무리 인사는 20p 산정에서 **빠진다**. 그래서 실물은 22장이고
쪽번호는 본문 20p 에만 붙는다. 근거는 `PPT_구성안_2026-09-01.md` §1-2.
