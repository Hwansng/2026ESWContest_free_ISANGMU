# -*- coding: utf-8 -*-
"""덱에 들어갈 이미지 자산을 PPT/영상·사진 원본에서 뽑아 img/ 에 정리한다.
슬라이드 표시 크기의 2배 내외로 저장해 투사·인쇄에서 뭉개지지 않게 한다."""
import os, subprocess
from PIL import Image
import imageio_ffmpeg

FF = imageio_ffmpeg.get_ffmpeg_exe()
ROOT = r"C:\Users\sehi5\OneDrive\바탕 화면\HazardBot\PPT"
VID = os.path.join(ROOT, "영상")
PHOTO = os.path.join(ROOT, "사진")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "img")
os.makedirs(OUT, exist_ok=True)


def grab(src, t, dst):
    subprocess.run([FF, "-y", "-hide_banner", "-loglevel", "error",
                    "-ss", str(t), "-i", src, "-frames:v", "1", dst], check=True)


def crop_ratio(im, ratio, anchor=(0.5, 0.5)):
    """가운데(또는 anchor) 기준으로 지정 비율만 남긴다."""
    w, h = im.size
    if w / h > ratio:
        nw, nh = int(h * ratio), h
    else:
        nw, nh = w, int(w / ratio)
    x = int((w - nw) * anchor[0])
    y = int((h - nh) * anchor[1])
    return im.crop((x, y, x + nw, y + nh))


tmp = os.path.join(OUT, "_tmp.png")

# ── P04 시연 공간 와이드 (표시 736x414) ────────────────────────────────────────
im = Image.open(os.path.join(PHOTO, "전체 시연장.jpg"))
crop_ratio(im, 16 / 9).resize((1472, 828), Image.LANCZOS).save(
    os.path.join(OUT, "demo_space.png"))

# ── (현재 덱 미사용) 롤아웃 구동 환경 와이드 ─────────────────────────────────
# 2026-09-02, 12p 사진이 ACT 수집 프레임(act_collect)으로 바뀌면서 자리를 잃었다.
# 같은 장비를 더 잘 보여주는 사진이 생겼으니 굳이 넣지 않는다. 되살릴 일이 있을까 해
# 추출은 그대로 둔다. t=5 — 에피소드 시작 전 홈 자세로 배치가 흐트러지지 않은 시점.
grab(os.path.join(VID, "rollout_성공률_측정.mp4"), 5, tmp)
Image.open(tmp).resize((1472, 828), Image.LANCZOS).save(
    os.path.join(OUT, "rollout_wide.png"))

# ── P11 단일 에피소드 4단계 (각 표시 362x204) ────────────────────────────────
# 영상에서 실제로 확인한 순서:
#   t=7  그리퍼가 적색 원통(위험물)을 문다        → 파지
#   t=9  집은 채로 들어 올려 옮긴다                → 이동
#   t=13 흰색 육각 통(격리함) 안으로 내려놓는다    → 격리함 투입
#   t=19 육각 뚜껑을 덮는다                        → 뚜껑 닫기
GRIP_BOX = (432, 218, 894, 478)                            # 462x260 ≈ 16:9
for t, name in ((7, "grip1"), (9, "grip2"), (13, "grip3"), (19, "grip4")):
    grab(os.path.join(VID, "rollout_성공률_측정.mp4"), t, tmp)
    Image.open(tmp).crop(GRIP_BOX).resize((724, 408), Image.LANCZOS).save(
        os.path.join(OUT, name + ".png"))

# ── P12 ACT 시연 데이터 수집 (표시 508x286) ──────────────────────────────────
# 리더암을 사람이 직접 잡고, 팔로워암이 그대로 따라 움직이며 황색 물체를 무는 순간.
# 왼쪽 노트북 화면에 손목 카메라 뷰가 떠 있어 수집 환경까지 한 장에 들어온다.
# 원본이 1280x720 16:9 라 크롭 없이 그대로 축소한다.
grab(os.path.join(VID, "ACT데이터_학습.mp4"), 7, tmp)
Image.open(tmp).resize((1016, 572), Image.LANCZOS).save(
    os.path.join(OUT, "act_collect.png"))

# ── P14 대시보드 전체 화면 1장 (표시 540x409) ────────────────────────────────
# t=150 프레임 하나에 세 판정이 다 들어 있다 — EVENT LOG 에 황색 위반 · 적색
# 가스없음(통과) · 적색 가스감지(격납 파손)가 함께 쌓여 있고, 그 시점의
# HAZARD LEVEL 은 L1 GAS_DETECTED, VISION 색상은 red 다. 케이스별로 세 장을
# 쪼개는 것보다 이 한 장이 근거로 강하고, 크게 실어야 글자가 읽힌다.
# 브라우저 크롬과 상하 여백을 잘라 카드 영역만 남긴다(546x414 ≈ 1.32:1).
BOX = (48, 138, 594, 552)
grab(os.path.join(VID, "HazardBot_대시보드.mp4"), 150, tmp)
Image.open(tmp).crop(BOX).resize((1092, 828), Image.LANCZOS).save(
    os.path.join(OUT, "dash_full.png"))

os.remove(tmp)
for f in sorted(os.listdir(OUT)):
    p = os.path.join(OUT, f)
    print(f"{f:20s} {Image.open(p).size}  {os.path.getsize(p)//1024} KB")
