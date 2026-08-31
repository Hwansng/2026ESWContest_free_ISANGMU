# -*- coding: utf-8 -*-
"""HazardBot 개발완료보고서 — 대회 필수항목 7개에 맞춘 덱.

내용은 PPT_구성안_2026-09-01.md, 형식은 design.md 를 따른다.
검증 수치는 rollout_plan.csv(30회 원본)에서 재확인했다.

분량 산정: 대회는 **표지와 인사 페이지를 20p 에서 제외**한다.
따라서 물리적 슬라이드는 표지(제외) + 본문 20p + 마무리(제외) = 22장이다.
쪽번호는 본문에만 붙는다.
"""
import os
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
import deck_lib as D
from deck_lib import (E, rect, textbox, line, oval, picture, mark, ground,
                      header, footer, field, card, rows, metric_strip,
                      evidence_rail, node, badge, chip, callout, image_mat,
                      arrow, elbow, label, new_slide, span, text_w,
                      GROUND, CANVAS, PEARL, TILE1, BLACK, INK, INK_DIM,
                      INK_FNT, ON_DARK, ON_DARK_M, RULE, RULE_SFT, RULE_DARK,
                      ACCENT, ACCENT_F, ACCENT_D, WASH, HAZARD, OXIDIZER,
                      CLEAR, BODY_X, BODY_Y, BODY_W, BODY_H, BODY_B, GAP)

HERE = os.path.dirname(os.path.abspath(__file__))
IMG = os.path.join(HERE, "img")
OUT = r"C:\Users\sehi5\OneDrive\바탕 화면\HazardBot\PPT\HazardBot_개발완료보고서_2026-09-01.pptx"

# §7 12칼럼 좌측 경계
COL = [64, 162, 260, 358, 456, 554, 652, 750, 848, 946, 1044, 1142]

# ══ 제출 직전에 채워 넣는 값 ══════════════════════════════════════════════════
# 팀명·팀번호가 정해지고 저장소·영상이 올라가면 이 세 줄만 고치고 다시 빌드한다.
# 비워 두면 슬라이드에 「확정 후 삽입」으로 찍힌다.
TEAM = ""            # "<팀번호>_<팀명>"  예: "A-12_HAZARDBOT"
GITHUB_URL = ""      # https://github.com/<사용자이름>/2026ESWContest_free_<팀명>
YOUTUBE_URL = ""     # https://youtu.be/…
PENDING = "확정 후 삽입"


def pend(v):
    return v if v else PENDING


def slide(rail, title, sub, page):
    new_slide()
    ground()
    header(rail, title, sub)
    footer(page)


# ══ 표지 (분량 제외) ══════════════════════════════════════════════════════════
def s_cover():
    """대회 가이드양식 3p 가 지정한 4줄 — 보고서명 / 부문 / 작품명 / 팀번호_팀명.

    §11 slide-cover — 본문 슬라이드와 같은 파치먼트 바탕. 어두운 표지판을 쓰지 않는다.
    """
    new_slide()
    ground()
    mark(96, 206, 132)
    textbox(260, 214, 760, 18,
            [("제24회 임베디드SW경진대회 개발완료보고서", 12, 600, ACCENT, 1.2, 0.08, 0)],
            wrap=False)
    textbox(260, 240, 760, 68,
            [("HazardBot", 60, 700, INK, 1.06, -0.025, 0)],
            anchor=MSO_ANCHOR.MIDDLE, wrap=False)
    textbox(262, 316, 760, 18,
            [("자유공모 부문", 13, 600, INK_FNT, 1.2, 0.06, 0)], wrap=False)
    textbox(96, 404, 1000, 30,
            [("위험물 취급구역을 순찰하며 감지·판정하고, 로봇팔로 직접 제거하는 "
              "AI 패트롤 로봇", 20, 400, INK_DIM, 1.5, -0.01, 0)],
            anchor=MSO_ANCHOR.MIDDLE, wrap=False, tag="cover.summary")
    rect(96, 464, 1088, 1, fill=RULE)
    textbox(96, 488, 700, 18, [(pend(TEAM), 12, 600, INK_FNT, 1.2, 0.08, 0)],
            anchor=MSO_ANCHOR.MIDDLE, wrap=False)
    textbox(484, 488, 700, 18, [("2026-09-03", 12, 600, INK_FNT, 1.2, 0.08, 0)],
            anchor=MSO_ANCHOR.MIDDLE, align=PP_ALIGN.RIGHT, wrap=False)


# ══ 01 · 목차 ═════════════════════════════════════════════════════════════════
CHAPTERS = [
    ("01", "개발 개요",
     "개발 배경·동기 · 목표·필요성 · 작품 개요와 제출 링크", "02 – 04"),
    ("02", "개발 환경",
     "시스템 개요 · 하드웨어와 전력 계통 · 개발 환경과 오픈소스 · "
     "소프트웨어 아키텍처 · 파일 구성", "05 – 09"),
    ("03", "개발 프로그램",
     "위험물 판정 로직 · GAS_CHECK · ACT 학습 · ACT 초동 조치 · "
     "통합 파이프라인과 대시보드 · 검증 결과", "10 – 15"),
    ("04", "장애요인과 해결", "개발 중 발생한 문제와 해결 방안", "16"),
    ("05", "결과와 일정",
     "작품의 차별성 · 기술적 우수성 · 파급력과 기대효과 · 개발 일정과 업무 분장",
     "17 – 20"),
]


def p01():
    slide("00 · 목차", "목차", "대회 필수항목 7개에 맞춘 5개 장 · 본문 20페이지", 1)
    field(BODY_X, BODY_Y, BODY_W, BODY_H)
    x, y, w = 96, 208, 1088
    rh = 424 / 5
    for i, (num, name, items, pages) in enumerate(CHAPTERS):
        top = y + i * rh
        if i:
            rect(x, top - 0.5, w, 1, fill=RULE_SFT)
        textbox(x, top, 52, rh, [(num, 26, 700, INK_FNT, 1.0, -0.02, 0)],
                anchor=MSO_ANCHOR.MIDDLE, wrap=False)
        textbox(x + 56, top, 852, rh,
                [(name, 19, 600, INK, 1.3, -0.015, 0),
                 (items, 13, 400, INK_DIM, 1.5, 0, 6)],
                anchor=MSO_ANCHOR.MIDDLE, tag=f"toc{i}")
        textbox(x + 928, top, 160, rh, [(pages, 13, 600, INK_FNT, 1.0, 0.02, 0)],
                anchor=MSO_ANCHOR.MIDDLE, align=PP_ALIGN.RIGHT, wrap=False)


# ══ 02 · 개발 배경 · 동기 ═════════════════════════════════════════════════════
def p02():
    slide("01 · 개발 개요", "사람이 계속 지킬 수 없는 구역이 있다",
          "24시간 가동하는 위험물 취급구역에서, 감시와 초동 조치는 여전히 사람의 몫으로 남아 있다", 2)
    field(BODY_X, BODY_Y, BODY_W, 240)
    fx, fw = 96, 1088
    nw, gap = 196, 27
    steps = ["24시간 가동 현장", "위험물 상시 취급", "사람의 지속 감시",
             "접근 · 조치 지연", "자동 감지 · 초동 조치"]
    for i, t in enumerate(steps):
        nx = fx + i * (nw + gap)
        node(nx, 256, nw, 80, t, active=(i == 4), size=14,
             align=PP_ALIGN.CENTER, pad=8, tag=f"p02.n{i}")
        if i < 4:
            arrow(nx + nw + 5, 296, nx + nw + gap - 5, 296)

    cards = [
        ("현장 조건", "지속 감시의 한계",
         "반도체 FAB·정유공장처럼 위험물을 다루면서도 멈추지 않는 현장이 있다. "
         "사람이 밤낮없이 모든 구간을 같은 집중으로 지키는 것은 현실적으로 어렵다."),
        ("작업자 위험", "근접이 곧 위험",
         "위험물을 치우려면 사람이 유해 물질에 직접 다가가야 한다. "
         "조치를 하는 행위 자체가 작업자에게 새로운 노출을 만든다."),
        ("개발 동기", "발견 다음이 비어 있다",
         "기존 순찰 로봇은 발견하고 알리는 데서 멈춘다. 치우는 일은 여전히 "
         "사람 몫으로 남아, 발견에서 조치까지의 간격이 사고 규모를 가른다."),
    ]
    for i, (eb, ti, bd) in enumerate(cards):
        card(COL[i * 4], 440, 368, 224, eyebrow=eb, title=ti, body=bd,
             tag=f"p02.c{i}")


# ══ 03 · 개발 목표 · 필요성 ═══════════════════════════════════════════════════
def p03():
    slide("01 · 개발 개요", "감지 · 판정 · 초동 조치를 하나의 흐름으로",
          "사람이 직접 접근하지 않고도 위험물을 감지·판정하고, 제거까지 수행하는 로봇을 만든다", 3)
    goals = [
        ("자동 감지", "순찰 중 정지 지점마다 카메라로 물체를 확인한다"),
        ("규칙 기반 판정", "색상으로 1차 분류하고, 필요한 경우에만 가스 센서로 정밀검사한다"),
        ("초동 조치", "위험으로 판정되면 로봇팔이 직접 집어 격리함에 넣는다"),
    ]
    for i, (t, d) in enumerate(goals):
        y = 176 + i * 154
        card(BODY_X, y, 368, 150, tag=f"p03.g{i}")
        textbox(88, y + 22, 320, 106,
                [(f"0{i + 1}", 12, 600, INK_FNT, 1.2, 0.08, 0),
                 (t, 19, 600, INK, 1.3, -0.015, 6),
                 (d, 12, 400, INK_DIM, 1.5, 0, 6)],
                anchor=MSO_ANCHOR.MIDDLE, tag=f"p03.g{i}.txt")
    label(BODY_X, 646, 368, "설계 근거 — 위험물안전관리법 유별 혼재 제한 · "
          "KS C IEC 60079-10-1", size=11, color=INK_FNT, tag="p03.std")
    image_mat(456, 176, 760, 488, os.path.join(IMG, "demo_space.png"), 736, 414,
              [("순찰 경로와 정지 지점을 구성한 시연 공간", 12, 600, INK, 1.4, 0, 0),
               ("바닥의 검은 선이 순찰 경로, 회색 패널이 각 정지 지점이다. "
                "지점마다 판정 대상 물체와 격리함을 배치했다.",
                12, 400, INK_DIM, 1.5, 0, 4)])


# ══ 04 · 작품 개요 · 제출 링크 ════════════════════════════════════════════════
def p04():
    slide("01 · 개발 개요", "작품 개요와 제출 링크",
          "대회 가이드양식의 개발 개요 표를 그대로 채웠다 — 소스코드와 시연동영상 링크는 필수 항목이다", 4)
    field(BODY_X, BODY_Y, 760, BODY_H)
    items = [
        ("작품명", "HazardBot"),
        ("개발 배경", "위험물을 다루면서도 24시간 멈추지 않는 산업현장에서, "
                   "감시와 초동 조치는 여전히 사람의 몫으로 남아 있다."),
        ("동기", "기존 순찰 로봇은 발견하고 알리는 데서 멈춘다. 발견 이후 치우는 "
               "일은 사람이 위험물에 직접 다가가야 한다."),
        ("목표", "위험물을 자동으로 감지·판정하고, 판정 결과에 따라 로봇팔로 "
               "초동 조치(제거)까지 수행하는 로봇을 개발한다."),
        ("필요성", "사람이 직접 접근하지 않고도 지속적인 감시·격리가 가능한 구조를 "
                "만들어, 유해물질에 근접하는 횟수 자체를 줄인다."),
    ]
    top = 200
    rh = 440 / 5
    for i, (k, v) in enumerate(items):
        if i:
            rect(96, top - 0.5, 696, 1, fill=RULE_SFT)
        textbox(96, top, 132, rh, [(k, 13, 600, INK, 1.5, 0, 0)],
                anchor=MSO_ANCHOR.MIDDLE, wrap=False)
        textbox(244, top, 548, rh, [(v, 12, 400, INK_DIM, 1.55, 0, 0)],
                anchor=MSO_ANCHOR.MIDDLE, tag=f"p04.v{i}")
        top += rh

    links = [("소스코드 링크", "GitHub", GITHUB_URL,
              "github.com/<사용자이름>/2026ESWContest_free_<팀명>"),
             ("시연 동영상 링크", "YouTube", YOUTUBE_URL,
              "2026ESWContest_자유공모_<팀명>_시연동영상 · 3분 이내 · 720p 이상")]
    for i, (title, host, url, note) in enumerate(links):
        y = 176 + i * 256
        card(848, y, 368, 232, accent_bar=(i == 0), tag=f"p04.l{i}")
        textbox(872, y + 26, 320, 16, [(title, 12, 600, ACCENT, 1.2, 0.08, 0)],
                wrap=False)
        chip(872, y + 52, host, size=12, fill=CANVAS if i == 0 else GROUND, h=22)
        textbox(872, y + 92, 320, 56,
                [(url if url else PENDING, 14 if url else 19, 600,
                  INK if url else INK_FNT, 1.5, 0, 0)], tag=f"p04.l{i}.url")
        rect(872, y + 156, 320, 1, fill=RULE_SFT)
        textbox(872, y + 168, 320, 44, [(note, 11, 400, INK_DIM, 1.45, 0, 0)],
                tag=f"p04.l{i}.note")


# ══ 05 · 시스템 개요 ══════════════════════════════════════════════════════════
def p05():
    slide("02 · 개발 환경", "HazardBot — 감지에서 초동 조치까지",
          "위험물 취급구역을 순찰하며 정지 지점마다 감지·판정하고, 로봇팔로 직접 제거한다", 5)
    field(BODY_X, BODY_Y, 760, 320)
    FX, FY = 96, 208

    def fl(x1, y1, x2, y2, ar=False):
        line(FX + x1, FY + y1, FX + x2, FY + y2, INK_FNT, 1.5, arrow=ar)

    fl(176, 144, 194, 144)
    fl(194, 84, 194, 204)
    fl(194, 84, 205, 84, True)
    fl(194, 204, 205, 204, True)
    fl(444, 84, 462, 84)
    fl(444, 204, 462, 204)
    fl(462, 84, 462, 204)
    fl(462, 84, 473, 84, True)
    fl(462, 204, 473, 204, True)

    for dx, w, num, name in [(0, 176, "01", " 감지"), (212, 232, "02", " 판정"),
                             (480, 216, "03", " 표시 · 조치")]:
        textbox(FX + dx, FY, w, 16, [(num + name, 12, 600, INK_DIM, 1.2, 0.08, 0)],
                wrap=False)

    NODES = [
        (0, 92, 176, 104, "카메라 인식", "정지 지점마다 물체 색 확인", [], None, False),
        (212, 32, 232, 104, "황색 — 산화성 고체", "취급구역 내 위치 자체가 위반",
         [("즉시 위험", "hazard")], OXIDIZER, False),
        (212, 152, 232, 104, "적색 — 인화성 액체", "MQ-2 가스 3초 정밀검사",
         [("검출 → 위험", "hazard"), ("없음 → 통과", "clear")], HAZARD, False),
        (480, 32, 216, 104, "대시보드 실시간 표시", "상태 · 센서 수치 · 판정 문장 로그",
         [], None, False),
        (480, 152, 216, 104, "로봇팔 초동 조치", "파지 → 이동 → 격리함 → 뚜껑 닫기",
         [], None, True),
    ]
    for dx, dy, w, h, title, desc, badges, swatch, active in NODES:
        nx, ny = FX + dx, FY + dy
        rect(nx, ny, w, h, fill=WASH if active else GROUND,
             line=ACCENT_F if active else RULE, lw=1.5 if active else 1, radius=6)
        pad_l = 30 if swatch else 12
        if swatch:
            oval(nx + 17, ny + 28, 5, swatch)
        body_h = h - 24 - (26 if badges else 0)
        textbox(nx + pad_l, ny + 12, w - pad_l - 12, body_h,
                [(title, 14, 600, INK, 1.6, 0, 0),
                 (desc, 12, 400, INK_DIM, 1.5, 0, 4)], tag=f"p05.{title[:6]}")
        bx = nx + pad_l
        for txt, kind in badges:
            bx += badge(bx, ny + h - 32, txt, kind, on_ground=True) + 6

    card(848, 176, 368, 320, eyebrow="하드웨어 구성", tag="p05.hw")
    rows(872, 224, 320, 248, [
        ("RPi 5", "ROS2 오케스트레이션 · 카메라 인식"),
        ("ESP_Drive", "TB6612FNG 모터 드라이버 · 안전 우선순위"),
        ("ESP_Env", "MQ-2 가스 · 화염 센서 3초 샘플링"),
        ("SO-101 로봇팔", "ACT 정책 · RTX 4060 GPU 추론"),
    ], tag="p05.hwrows")

    metric_strip(BODY_X, 520, BODY_W, [
        ("ACT 파지 성공률", "86.7%", "실물 30회 검증 · 근거리 100%"),
        ("가스 정밀검사", "3초", "MQ-2 샘플링 · 5초 워치독"),
        ("ACT 학습 데이터", "100회", "리더암 직접 시연 · 모방학습"),
        ("판정 로직 실물 확인", "7회", "3케이스 전부 정상 동작"),
    ])


# ══ 06 · 하드웨어 구성 · 전력 계통 ════════════════════════════════════════════
def p06():
    slide("02 · 개발 환경", "네 개의 하드웨어 단위와 세 개의 전력 레일",
          "RPi 5가 전체 흐름을 조율하고 두 개의 ESP32와 로봇팔이 주행·센싱·조치를 맡는다 — "
          "전원은 배터리 하나에서 세 갈래로 나뉜다", 6)
    units = [
        ("오케스트레이션", "RPi 5", [
            ("ROS2 노드 조율", "판정부터 조치까지 관리"),
            ("카메라 물체 인식", "색상 · 방위각 산출"),
            ("대시보드 웹서버", "hazardbot.local:8080"),
        ]),
        ("주행 · 안전 판단", "ESP_Drive", [
            ("TB6612FNG", "듀얼 H-브리지 모터 제어"),
            ("안전 우선순위 판단", "위험 순위대로 정지 처리"),
            ("라인 · 거리 센싱", "TCRT5000 · VL53L1X"),
        ]),
        ("가스 · 화염 센싱", "ESP_Env", [
            ("MQ-2 가스센서", "원시값 샘플링 · 화염 병행"),
            ("3초 정밀검사", "요청 시 집중 샘플링"),
            ("판정 결과 전달", "DETECTED · CLEAR · ERROR"),
        ]),
        ("초동 조치", "SO-101 로봇팔", [
            ("리더 - 팔로워 구조", "시연을 관절값으로 수집"),
            ("ACT 정책 제어", "학습된 정책으로 파지"),
            ("노트북 GPU 추론", "RTX 4060 · COM3 직결"),
        ]),
    ]
    for i, (eb, name, items) in enumerate(units):
        x = COL[i * 3]
        card(x, 176, 270, 252, eyebrow=eb, title=name, tag=f"p06.u{i}")
        rows(x + 24, 269, 222, 135, items, name_size=12, desc_size=11,
             tag=f"p06.u{i}.rows")

    field(BODY_X, 452, BODY_W, 212)
    label(96, 476, 700, "전력 계통 — 3S LiPo 11.1V · 2200mAh 에서 세 개 레일로",
          size=12, color=INK_DIM, weight=600, spc=0.08)
    node(96, 506, 168, 72, "3S LiPo 배터리", "11.1V · 2200mAh", size=13,
         align=PP_ALIGN.CENTER, pad=8, tag="p06.bat")
    arrow(264, 542, 286, 542)
    node(288, 522, 140, 40, "XT60 1to3", size=12, align=PP_ALIGN.CENTER, pad=6,
         tag="p06.xt60")
    line(428, 542, 448, 542, INK_FNT, 1.5)
    line(448, 516, 448, 608, INK_FNT, 1.5)

    rails = [(496, "12V — 팔로워", "로봇팔 서보 6개 전용",
              "SO-101 팔로워 암 · 6축", False),
             (542, "5V_RPi — XL4016 단독", "RPi 5 전용 레일",
              "RPi 5 · ROS2 · 카메라 · 대시보드", True),
             (588, "12V 주행 + 5V_ESP — XL4015", "주행 및 센서 계통",
              "TB6612 · ESP_Drive · ESP_Env", False)]
    for i, (y, t, d, loadtxt, act) in enumerate(rails):
        arrow(448, y + 20, 466, y + 20)
        node(468, y, 320, 40, t, None, active=act, size=12,
             align=PP_ALIGN.LEFT, pad=12, tag=f"p06.rail{i}")
        textbox(500, y, 280, 40, [(d, 11, 400, INK_DIM, 1.4, 0, 0)],
                anchor=MSO_ANCHOR.MIDDLE, align=PP_ALIGN.RIGHT, wrap=False,
                tag=f"p06.raild{i}")
        arrow(788, y + 20, 806, y + 20)
        rect(808, y, 376, 40, fill=GROUND, line=RULE, lw=1, radius=6)
        textbox(824, y, 344, 40, [(loadtxt, 12, 400, INK, 1.4, 0, 0)],
                anchor=MSO_ANCHOR.MIDDLE, wrap=False, tag=f"p06.load{i}")
    # 레일 스택이 628 에서 끝난다. 주석은 그 아래 여백에 앉힌다(겹침 방지).
    label(96, 638, 1088, "MQ-2 는 히터가 상시 330mA를 끌어 DRIVE 5V 를 흔들기 때문에 "
          "ESP_Env 5V/VIN 에서 따로 급전한다 · ESP 보드 전원선은 진동 이탈을 막으려 "
          "VCC/GND 직납땜 (16p)", size=11, color=INK_FNT, tag="p06.note")


# ══ 07 · 개발 환경 · 오픈소스 ═════════════════════════════════════════════════
def p07():
    slide("02 · 개발 환경", "개발 환경과 활용한 오픈소스",
          "규정 제10조 ③에 따라, 기존 소프트웨어의 출처와 우리가 바꾸거나 더한 것을 함께 밝힌다", 7)
    field(BODY_X, BODY_Y, BODY_W, 192)
    label(96, 200, 700, "개발 환경", size=12, color=INK_DIM, weight=600, spc=0.08)
    env = [
        ("중앙 제어기", "Raspberry Pi 5 · Ubuntu 24.04 LTS", "ROS 2 Jazzy · Python 3.12 (rclpy)"),
        ("학습 · 추론", "Windows 11 노트북 · RTX 4060 (8GB)", "miniconda 환경 lerobot · Python 3.10"),
        ("로봇팔 스택", "LeRobot 0.4.4 · PyTorch (CUDA)", "SCServo 라이브러리 · CP210x USB 시리얼"),
        ("임베디드", "ESP32 × 2 · Arduino 스케치(.ino)", "OTA 업로드 · TB6612FNG · MQ-2 · VL53L1X"),
        ("비전", "libcamera · OpenCV · cv_bridge", "정지 지점 색상 · 방위각 산출"),
        ("대시보드", "Flask · Flask-SocketIO", "RPi 호스팅 · hazardbot.local:8080"),
        ("형상관리 · CI", "GitHub · GitHub Actions 2종", "Arduino 컴파일 / colcon build (Jazzy)"),
        ("3D 제작", "STEP · STL · 3mf 자체 모델링", "PLA 출력 — 섀시 어댑터 · 카메라 프레임"),
    ]
    cw = (1088 - 24) / 2
    for i, (k, v1, v2) in enumerate(env):
        cx = 96 + (i % 2) * (cw + 24)
        cy = 218 + (i // 2) * 36
        if i >= 2:
            rect(cx, cy - 1, cw, 1, fill=RULE_SFT)
        textbox(cx, cy, 116, 36, [(k, 12, 600, INK, 1.4, 0, 0)],
                anchor=MSO_ANCHOR.MIDDLE, wrap=False)
        textbox(cx + 124, cy, cw - 124, 36,
                [(v1, 12, 400, INK, 1.4, 0, 0),
                 (v2, 11, 400, INK_FNT, 1.4, 0, 2)],
                anchor=MSO_ANCHOR.MIDDLE, wrap=False, tag=f"p07.e{i}")

    field(BODY_X, 392, BODY_W, 248)
    label(96, 416, 900, "활용한 오픈소스 — 출처 · 라이선스 · 우리가 바꾸거나 더한 것",
          size=12, color=INK_DIM, weight=600, spc=0.08)
    for cx, cw2, ht, al in ((96, 240, "오픈소스", PP_ALIGN.LEFT),
                            (348, 116, "라이선스", PP_ALIGN.LEFT),
                            (476, 708, "개선점 · 추가한 것", PP_ALIGN.LEFT)):
        textbox(cx, 444, cw2, 15, [(ht, 11, 600, INK_FNT, 1.2, 0.06, 0)],
                align=al, wrap=False)
    rect(96, 466, 1088, 1, fill=RULE)
    oss = [
        ("ROS 2 Jazzy", "Apache-2.0",
         "미션 통합 레이어로 자체 패키지 8종을 새로 작성했다."),
        ("LeRobot 0.4.4", "Apache-2.0",
         "표준 record 는 에피소드 사이 리더암 조작을 요구해 무인 롤아웃이 안 된다. "
         "「에피소드 1회 = 프로세스 1회」 패치 러너로 재구성하고, HuggingFace 자동 "
         "업로드 기본값을 차단했다."),
        ("ACT (Action Chunking Transformer)", "논문 구현",
         "파지 → 격리함 투입 → 뚜껑 닫기를 단일 에피소드 태스크로 재정의해 "
         "100 에피소드를 자체 수집·학습했다."),
        ("SO-ARM101 · lerobot-calibrate", "Apache-2.0",
         "원본이 테이블 클램프 설계라 2WD 섀시 어댑터를 v2까지 자체 모델링했고, "
         "표준 캘리브레이션이 못 잡는 축을 위해 전용 도구를 직접 만들었다."),
        ("Flask · Flask-SocketIO · OpenCV", "BSD · Apache-2.0",
         "실시간 판정 대시보드를 새로 구현했다."),
    ]
    top = 472
    rh = 168 / 5
    for i, (nm, lic, imp) in enumerate(oss):
        if i:
            rect(96, top - 0.5, 1088, 1, fill=RULE_SFT)
        textbox(96, top, 240, rh, [(nm, 12, 600, INK, 1.4, 0, 0)],
                anchor=MSO_ANCHOR.MIDDLE, tag=f"p07.o{i}n")
        textbox(348, top, 116, rh, [(lic, 11, 400, INK_FNT, 1.4, 0, 0)],
                anchor=MSO_ANCHOR.MIDDLE, wrap=False)
        textbox(476, top, 708, rh, [(imp, 11, 400, INK_DIM, 1.45, 0, 0)],
                anchor=MSO_ANCHOR.MIDDLE, tag=f"p07.o{i}i")
        top += rh
    label(96, 648, 1088, "본 보고서 서체는 Pretendard (SIL OFL 1.1), 이미지는 전부 "
          "자체 촬영·자체 제작이다.", size=11, color=INK_FNT)


# ══ 08 · 소프트웨어 아키텍처 ══════════════════════════════════════════════════
def p08():
    slide("02 · 개발 환경", "ROS2 노드가 판정과 조치를 이어 붙인다",
          "인식 · 센싱 · 주행 노드가 판정 노드로 모이고, 오케스트레이터가 표시와 조치로 내보낸다", 8)
    field(BODY_X, BODY_Y, 760, BODY_H)
    for name, desc, x, w in (("vision_node", "카메라 물체 인식", 96, 216),
                             ("sensor_bridge_node", "ENV 보드 중계", 336, 216),
                             ("amr_bridge_node", "DRIVE 보드 중계", 576, 216)):
        node(x, 208, w, 56, name, desc, size=13, align=PP_ALIGN.CENTER, pad=8,
             tag=f"p08.{name}")
    node(96, 328, 696, 56, "hazard_detector_node", "색상 1차 분류 + 가스 결과로 위험 판정",
         size=13, align=PP_ALIGN.CENTER, tag="p08.hazard")
    node(96, 448, 696, 56, "mission_orchestrator", "판정 결과에 따라 조치를 요청하고 상태를 관리",
         size=13, align=PP_ALIGN.CENTER, active=True, tag="p08.orch")
    node(96, 568, 336, 56, "dashboard_node", "실시간 판정 화면", size=13,
         align=PP_ALIGN.CENTER, pad=8, tag="p08.dash")
    node(456, 568, 336, 56, "arm_act_node", "ACT 정책 실행", size=13,
         align=PP_ALIGN.CENTER, pad=8, tag="p08.arm")

    for cx, topic in ((204, "/vision/detected"), (444, "/env/gas_result"),
                      (684, "/amr/object_near")):
        arrow(cx - 60, 264, cx - 60, 326)
        label(cx - 52, 286, 150, topic, size=11, color=INK_FNT)
    arrow(384, 384, 384, 446)
    label(392, 406, 160, "/hazard/detected", size=11, color=INK_FNT)
    arrow(264, 504, 264, 566)
    label(272, 526, 150, "판정 · 상태 갱신", size=11, color=INK_FNT)
    arrow(536, 504, 536, 566)
    label(544, 512, 160, "/arm/grip_request", size=11, color=INK_FNT)
    arrow(716, 566, 716, 506)
    label(548, 538, 160, "/arm/act_result", size=11, color=INK_FNT,
          align=PP_ALIGN.RIGHT)

    card(848, 176, 368, 232, eyebrow="판정 계통 토픽", tag="p08.t1")
    rows(872, 227, 320, 157, [
        ("/vision/detected", "인식한 물체의 색상 · 방위각"),
        ("/hazard/gas_check_request", "적색일 때 가스 정밀검사 요청"),
        ("/env/gas_result", "DETECTED · CLEAR · ERROR"),
        ("/hazard/detected", "최종 위험 판정과 판정 문장"),
    ], name_size=12, desc_size=11, tag="p08.t1.rows")

    card(848, 432, 368, 232, eyebrow="조치 · 상태 계통 토픽", tag="p08.t2")
    rows(872, 483, 320, 157, [
        ("/amr/object_near", "정지 지점에서 물체 근접 감지"),
        ("/amr/stop_index", "현재 정지 지점 번호"),
        ("/arm/grip_request", "로봇팔 초동 조치 요청"),
        ("/arm/act_result", "정책 실행 결과 회신"),
    ], name_size=12, desc_size=11, tag="p08.t2.rows")


# ══ 09 · 파일 구성 · 주요 함수 (소스코드 최종 커밋 후 작성) ═══════════════════
def p09():
    """🔴 보류 페이지.

    필수항목 3의 「파일 구성 · 함수별 기능」에 해당한다. 심사위원이 GitHub 저장소를
    열어 대조할 페이지라, 저장소 최종 커밋이 끝난 뒤에 실제 트리·함수로 채운다.
    지금 채워 두면 커밋 이후 실제 구조와 어긋날 수 있어 비워 둔다.
    쪽번호가 밀리지 않도록 페이지 자리는 유지한다.
    """
    slide("02 · 개발 환경", "파일 구성 · 주요 함수",
          "저장소 디렉터리 구조와 노드별 핵심 함수의 역할", 9)
    field(BODY_X, BODY_Y, 564, BODY_H)
    label(96, 200, 516, "저장소 구조", size=12, color=INK_DIM, weight=600, spc=0.08)
    field(652, BODY_Y, 564, BODY_H)
    label(684, 200, 516, "주요 함수 · 역할", size=12, color=INK_DIM, weight=600,
          spc=0.08)
    callout(184, 348, 912, 128,
            [("소스코드 최종 커밋 후 작성", 19, 600, ACCENT, 1.35, -0.015, 0),
             ("심사위원이 GitHub 저장소를 열어 대조하는 페이지다. "
              "커밋이 끝난 실제 트리와 함수로 채운다.",
              12, 400, INK_DIM, 1.5, 0, 6)])


# ══ 10 · 위험물 판정 로직 ═════════════════════════════════════════════════════
def p10():
    slide("03 · 개발 프로그램", "색으로 나누고, 필요할 때만 가스로 확인한다",
          "고체는 놓여 있는 것만으로 위반, 액체는 새어 나올 때만 위험 — 물질의 성질을 규칙으로 옮겼다", 10)
    field(BODY_X, BODY_Y, BODY_W, 200)
    steps = [("정지 지점 도착", "순찰 중 지정된 지점에 정지"),
             ("카메라 색상 확인", "물체의 색과 방위각을 산출"),
             ("색상별 규칙 적용", "황색은 즉시, 적색은 가스 검사"),
             ("판정 문장 출력", "대시보드에 결과를 그대로 표시")]
    nw, gap = 251, 28
    for i, (t, d) in enumerate(steps):
        nx = 96 + i * (nw + gap)
        node(nx, 236, nw, 80, t, d, size=14, tag=f"p10.n{i}")
        if i < 3:
            arrow(nx + nw + 5, 276, nx + nw + gap - 5, 276)

    cases = [
        ("황색 산화성 고체", "oxidizer", "즉시 위험",
         "황색 산화성 고체 감지 — 취급구역 내 위치 자체가 위반",
         "고체는 가스를 내뿜지 않는다. 그 자리에 있다는 사실만으로 규정 위반이므로 "
         "추가 검사 없이 곧바로 위험으로 판정한다."),
        ("적색 · 가스 검출", "hazard", "위험",
         "적색 물질 — 가스 감지. 격납 파손",
         "인화성 액체는 새어 나올 때 위험해진다. MQ-2가 가스를 검출하면 "
         "격납이 깨진 것으로 보고 위험으로 판정한다."),
        ("적색 · 가스 없음", "clear", "통과",
         "적색 물질 — 가스 없음. 격납 유지, 통과",
         "같은 적색이어도 가스가 없으면 격납이 유지된 상태다. "
         "정상으로 판정하고 순찰을 이어간다."),
    ]
    for i, (name, kind, verdict, quote, why) in enumerate(cases):
        x = COL[i * 4]
        card(x, 400, 368, 264, tag=f"p10.c{i}")
        badge(x + 24, 424, verdict, kind)
        textbox(x + 24, 460, 320, 26, [(name, 19, 600, INK, 1.35, -0.015, 0)],
                wrap=False, tag=f"p10.c{i}.name")
        rect(x + 24, 500, 2, 52, fill=D.STATUS[kind][0])
        textbox(x + 38, 500, 306, 52,
                [(quote, 14, 600, INK, 1.6, 0, 0)], anchor=MSO_ANCHOR.MIDDLE,
                tag=f"p10.c{i}.quote")
        textbox(x + 24, 568, 320, 72, [(why, 12, 400, INK_DIM, 1.5, 0, 0)],
                tag=f"p10.c{i}.why")


# ══ 11 · GAS_CHECK ════════════════════════════════════════════════════════════
def p11():
    slide("03 · 개발 프로그램", "적색 물질은 3초 정밀검사를 거친다",
          "판정 노드가 검사를 요청하면 ENV 보드가 MQ-2를 3초간 샘플링하고, "
          "5초 워치독이 응답 지연을 막는다", 11)
    field(BODY_X, BODY_Y, BODY_W, 320)
    flow = [("적색 판정", "카메라가 적색 물체를 확인"),
            ("검사 요청 발행", "/hazard/gas_check_request"),
            ("MQ-2 3초 샘플링", "GAS_INSPECTION_DURATION_MS = 3000"),
            ("결과 응답", "/env/gas_result 로 회신")]
    nw, gap = 257, 20
    for i, (t, d) in enumerate(flow):
        nx = 96 + i * (nw + gap)
        node(nx, 208, nw, 80, t, d, size=14, active=(i == 2), tag=f"p11.n{i}")
        if i < 3:
            arrow(nx + nw + 3, 248, nx + nw + gap - 3, 248)
    label(96, 302, 400, "결과 유형", size=12, color=INK_DIM, weight=600, spc=0.08)

    results = [
        ("DETECTED", "hazard", "가스 검출 — 위험",
         "격납이 깨진 것으로 보고 위험으로 판정한다. 초동 조치 대상이 된다."),
        ("CLEAR", "clear", "가스 없음 — 통과",
         "격납이 유지된 상태로 보고 정상 판정 후 순찰을 이어간다."),
        ("ERROR", None, "센서 오류 · 응답 없음",
         "5초 워치독(GAS_CHECK_TIMEOUT_S = 5.0)이 걸리면 오류로 처리한다. "
         "위험도 정상도 아닌 세 번째 결과다."),
    ]
    cw = (1088 - 48) / 3
    for i, (code, kind, title, desc) in enumerate(results):
        x = 96 + i * (cw + 24)
        rect(x, 328, cw, 136, fill=GROUND, line=RULE, lw=1, radius=6)
        if kind:
            badge(x + 20, 350, code, kind, on_ground=True)
        else:
            chip(x + 20, 350, code, size=12, fill=CANVAS, h=20)
        textbox(x + 20, 378, cw - 40, 70,
                [(title, 14, 600, INK, 1.5, 0, 0),
                 (desc, 12, 400, INK_DIM, 1.5, 0, 4)], tag=f"p11.r{i}")

    metric_strip(BODY_X, 520, BODY_W, [
        ("샘플링 시간", "3초", "GAS_INSPECTION_DURATION_MS = 3000 — "
         "액체가 새는지 확인하기에 필요한 최소 구간"),
        ("응답 워치독", "5초", "GAS_CHECK_TIMEOUT_S = 5.0 — 응답이 늦어도 "
         "판정 흐름이 멈추지 않는다"),
        ("결과 유형", "3가지", "DETECTED · CLEAR · ERROR — 오류도 판정 결과로 "
         "명시해 놓친 검사를 남기지 않는다"),
    ])


# ══ 12 · ACT 로봇팔 학습 ══════════════════════════════════════════════════════
def p12():
    slide("03 · 개발 프로그램", "사람의 시연 100회를 정책으로 학습했다",
          "리더암으로 직접 보여준 동작을 ACT(Action Chunking Transformer)로 모방학습했다", 12)

    # 수집 장면이 이 페이지의 유일한 실물 근거다. 매트 폭(564)보다 사진을 조금
    # 줄여 가운데 놓고, 남는 아래를 캡션에 준다.
    rect(BODY_X, BODY_Y, 564, 368, fill=CANVAS, line=RULE, lw=1, radius=6)
    picture(os.path.join(IMG, "act_collect.png"), 92, 188, 508, 286)
    textbox(92, 478, 508, 56,
            [("시연 데이터를 쌓는 중 — 리더암은 사람 손에 있다", 12, 600, INK,
              1.4, 0, 0),
             ("두 손으로 잡은 흰색 팔이 리더암, 섀시 위 팔이 팔로워암이다. 사람이 움직인 "
              "그대로 팔로워가 따라가고, 그때의 관절값이 학습 데이터가 된다. "
              "노트북 화면에 뜬 것은 학습에 쓰는 손목 카메라 뷰다.",
              11, 400, INK_DIM, 1.5, 0, 4)], tag="p12.caption")

    field(652, BODY_Y, 564, 368)
    label(684, 200, 516, "수집에서 롤아웃까지 3단계", size=12, color=INK_DIM,
          weight=600, spc=0.08)
    rows(684, 232, 516, 296, [
        ("01 · 시연 데이터 수집",
         "리더-팔로워 구조라 사람이 보여준 궤적이 그대로 관절값으로 남는다. "
         "적색 50 · 황색 50, 다섯 위치에 각 10회씩 배분해 100 에피소드를 모았다."),
        ("02 · ACT 정책 학습",
         "한 스텝씩이 아니라 여러 스텝을 한 덩어리(청크)로 예측하는 ACT 로 학습한다. "
         "중간에 멈추면 실패하는 파지 작업에 적합하다."),
        ("03 · 정책 롤아웃",
         "학습된 정책이 카메라 관측을 받아 다음 청크를 내놓고 팔로워가 실행한다. "
         "이 경로로 실물 30회를 측정했다."),
    ], name_size=14, desc_size=12, tag="p12.steps")

    metric_strip(BODY_X, 568, BODY_W, [
        ("시연 데이터", "100 에피소드"),
        ("색상 배분", "적 50 · 황 50"),
        ("학습량", "100,000 스텝"),
        ("학습 시간", "4시간 47분"),
    ], height=96)


# ══ 13 · ACT 로봇팔 초동 조치 ═════════════════════════════════════════════════
def p13():
    slide("03 · 개발 프로그램", "집어서 넣고 뚜껑까지, 한 번에 수행한다",
          "네 단계를 하나의 에피소드로 학습해 중간 개입 없이 이어서 실행한다", 13)
    card(BODY_X, BODY_Y, 368, BODY_H, eyebrow="단일 에피소드 태스크", tag="p13.card")
    rows(88, 227, 320, 413, [
        ("01 · 위험물 파지", "정지 지점에 놓인 물체를 집는다. 파지가 실패하면 "
         "이후 단계가 모두 무의미해지는 가장 어려운 구간이다."),
        ("02 · 이동", "집은 상태를 유지한 채 격리함 위치까지 팔을 옮긴다."),
        ("03 · 격리함 투입", "격리함 안으로 물체를 넣고 그리퍼를 연다."),
        ("04 · 뚜껑 닫기", "격리함 뚜껑을 덮어 취급구역에서 격리를 완료한다."),
        ("05 · 홈 복귀", "3초 선형 보간으로 부드럽게 홈 포지션으로 돌아가 "
         "다음 지점에 대비한다."),
    ], tag="p13.rows")

    # 실제 롤아웃 영상에서 네 단계를 그대로 뽑아 왼쪽 목록과 번호를 맞춘다.
    rect(456, 176, 760, 488, fill=CANVAS, line=RULE, lw=1, radius=6)
    shots = [("grip1.png", "01", "위험물 파지", "그리퍼가 적색 원통을 문다"),
             ("grip2.png", "02", "이동", "집은 채로 들어 올려 옮긴다"),
             ("grip3.png", "03", "격리함 투입", "격리함 안으로 내려놓는다"),
             ("grip4.png", "04", "뚜껑 닫기", "육각 뚜껑을 덮어 격리 완료")]
    # 매트 안쪽 188~652(464) = 2행 × 226 + 행간 12. 한 행 = 사진 204 + 6 + 캡션 16.
    # 캡션이 한 줄을 넘으면 아래 행 사진에 가려지므로 번호·이름·설명을 한 줄에 둔다.
    for i, (fn, num, name, desc) in enumerate(shots):
        cx = 468 + (i % 2) * 374
        cy = 188 + (i // 2) * 238
        picture(os.path.join(IMG, fn), cx, cy, 362, 204)
        textbox(cx, cy + 210, 362, 16,
                [([(num + "  ", ACCENT, None), (name, INK, None),
                   ("  —  " + desc, INK_DIM, 400)], 11, 600, INK, 1.45, 0, 0)],
                anchor=MSO_ANCHOR.MIDDLE, wrap=False, tag=f"p13.cap{i}")


# ══ 14 · 통합 파이프라인 · 대시보드 ═══════════════════════════════════════════
def p14():
    slide("03 · 개발 프로그램", "판정에서 조치까지, 그리고 화면에 남는 기록",
          "판정 노드가 위험을 알리면 오케스트레이터가 조치를 요청하고, "
          "그 과정이 대시보드에 실시간으로 쌓인다", 14)
    field(BODY_X, BODY_Y, 564, BODY_H)
    label(96, 200, 516, "ROS2 통합 파이프라인", size=12, color=INK_DIM,
          weight=600, spc=0.08)
    flow = [("hazard_detector_node", "색상과 가스 결과를 합쳐 최종 위험 판정",
             "/hazard/detected"),
            ("mission_orchestrator", "조치 필요 여부 판단 · 전체 상태 관리",
             "/arm/grip_request"),
            ("arm_act_node", "lerobot-rollout 으로 ACT 정책 실행",
             "/arm/act_result"),
            ("결과 회신", "성공 · 실패를 오케스트레이터로 되돌린다", None)]
    for i, (t, d, topic) in enumerate(flow):
        y = 236 + i * 104
        node(96, y, 516, 64, t, d, size=13, active=(i == 1), pad=14,
             tag=f"p14.n{i}")
        if topic:
            arrow(354, y + 64, 354, y + 88)
            label(362, y + 68, 220, topic, size=11, color=INK_FNT)

    # 캡션을 세 줄 쓰려고 사진을 매트 폭보다 줄여 가운데 놓는다(516x391).
    rect(652, 176, 564, 488, fill=CANVAS, line=RULE, lw=1, radius=6)
    picture(os.path.join(IMG, "dash_full.png"), 676, 188, 516, 391)
    textbox(676, 587, 516, 65,
            [("RPi 가 호스팅하는 실시간 대시보드 — hazardbot.local:8080", 12, 600,
              INK, 1.4, 0, 0),
             ("EVENT LOG 한 화면에 세 판정이 다 남아 있다 — 황색 위반, 적색·가스 "
              "없음(통과), 적색·가스 감지(격납 파손). HAZARD LEVEL 은 종합 판정이 "
              "아니라 가스 지표라 황색 판정 때도 L0 다.",
              11, 400, INK_DIM, 1.5, 0, 4)], tag="p14.dashcap")


# ══ 15 · 검증 결과 ════════════════════════════════════════════════════════════
def p15():
    slide("03 · 개발 프로그램", "파지 30회, 판정 3케이스를 실물로 확인했다",
          "ACT 파지는 성공률로, 규칙 기반 판정 로직은 케이스별 실물 시연으로 "
          "각각 검증했다", 15)
    field(BODY_X, BODY_Y, 564, 320)
    label(96, 208, 500, "정지 위치별 ACT 파지 성공률", size=12, color=INK_DIM,
          weight=600, spc=0.08)
    bars = [("근거리 (center · rear)", "18회 중 18회 성공", 1.0, "100%", ACCENT),
            ("원거리 (front)", "12회 중 8회 성공", 8 / 12, "66.7%", INK_FNT)]
    for i, (nm, sub, p, val, color) in enumerate(bars):
        y = 250 + i * 74
        textbox(96, y, 190, 44, [(nm, 13, 600, INK, 1.5, 0, 0),
                                 (sub, 11, 400, INK_FNT, 1.45, 0, 3)],
                tag=f"p15.bar{i}")
        rect(296, y + 6, 240, 22, fill=RULE_SFT)
        rect(296, y + 6, 240 * p, 22, fill=color)
        textbox(544, y, 52, 30, [(val, 19, 700, INK, 1.3, -0.02, 0)],
                anchor=MSO_ANCHOR.MIDDLE, align=PP_ALIGN.RIGHT, wrap=False)
    rect(96, 400, 500, 1, fill=RULE_SFT)
    textbox(96, 414, 300, 30, [("전체 30회 평균", 13, 600, INK, 1.5, 0, 0)],
            anchor=MSO_ANCHOR.MIDDLE, wrap=False)
    textbox(400, 412, 196, 34, [("86.7%", 26, 700, ACCENT, 1.0, -0.02, 0)],
            anchor=MSO_ANCHOR.MIDDLE, align=PP_ALIGN.RIGHT, wrap=False)
    label(96, 452, 500, "rollout_plan.csv — 3세트 × 10회, 위치와 색상을 섞어 측정",
          size=11, color=INK_FNT)

    field(652, BODY_Y, 564, 320)
    label(676, 208, 516, "판정 로직 실물 확인", size=12, color=INK_DIM,
          weight=600, spc=0.08)
    for cx, cw, ht in ((696, 204, "케이스"), (900, 80, "시연"), (996, 196, "결과")):
        textbox(cx, 240, cw, 16, [(ht, 12, 600, INK_DIM, 1.2, 0.08, 0)],
                align=PP_ALIGN.RIGHT if cw == 80 else PP_ALIGN.LEFT, wrap=False)
    rect(676, 264, 516, 1, fill=RULE)
    table = [("황색 — 산화성 고체", "3회", "즉시 위험 판정", "oxidizer"),
             ("적색 — 가스 검출", "3회", "위험 판정 · 격납 파손", "hazard"),
             ("적색 — 가스 없음", "1회", "통과 · 격납 유지", "clear")]
    for i, (c1, c2, c3, kind) in enumerate(table):
        y = 265 + i * 52
        if i:
            rect(676, y, 516, 1, fill=RULE_SFT)
        oval(683, y + 26, 5, D.STATUS[kind][0])
        textbox(696, y, 204, 52, [(c1, 13, 400, INK, 1.5, 0, 0)],
                anchor=MSO_ANCHOR.MIDDLE, wrap=False)
        textbox(900, y, 80, 52, [(c2, 13, 400, INK, 1.5, 0, 0)],
                anchor=MSO_ANCHOR.MIDDLE, align=PP_ALIGN.RIGHT, wrap=False)
        textbox(996, y, 196, 52, [(c3, 13, 400, INK_DIM, 1.5, 0, 0)],
                anchor=MSO_ANCHOR.MIDDLE, wrap=False)
    label(676, 436, 516, "규칙 기반 로직이라 확률적 정확도가 아니라, 케이스별로 "
          "실물에서 규칙대로 동작하는지를 확인했다.", size=11, color=INK_FNT,
          h=32, tag="p15.note")

    metric_strip(BODY_X, 520, BODY_W, [
        ("ACT 파지 평균", "86.7%", "실물 30회 · 3세트 × 10회"),
        ("근거리 위치", "100%", "center · rear 18회 전부 성공"),
        ("원거리 위치", "66.7%", "front 12회 중 8회 성공 — 개선 여지"),
        ("판정 로직 확인", "7회", "3케이스 전부 규칙대로 동작"),
    ])


# ══ 16 · 장애요인과 해결방안 ══════════════════════════════════════════════════
def p16():
    slide("04 · 장애요인과 해결", "막힌 지점마다 원인을 규명하고 우회했다",
          "실물에서 만난 네 건을 증상 · 원인 · 해결로 정리했다 — "
          "세 건은 원인까지 규명해 재발을 막았다", 16)
    field(BODY_X, BODY_Y, BODY_W, 336)
    cols = ((96, 240, "증상"), (360, 316, "원인"), (700, 484, "해결"))
    for cx, cw, ht in cols:
        textbox(cx, 200, cw, 15, [(ht, 11, 600, INK_FNT, 1.2, 0.06, 0)],
                wrap=False)
    rect(96, 228, 1088, 1, fill=RULE)
    cases = [
        ("리더암 서보 6개 동시 소손", "2026-06-16",
         "7.4V 정격 서보에 12V 오인가",
         "XL4015 두 대의 용도를 고정해(리더 7.4V / ESP32 5.0V) 레일을 물리적으로 "
         "분리하고, 되돌릴 수 없는 항목만 모은 통전 전 확인 5항목을 만들었다. "
         "이후 동일 사고 0건."),
        ("ESP_Drive 보드 발열 사망", "2026-08-25",
         "핀소켓 GND가 모터 진동으로 이탈",
         "전원선을 VCC/GND 직납땜으로 바꿨다. 이어서 전원 모듈(DFR0753)이 쇼트로 "
         "소손되자 XL4016 단독 레일로 계통을 우회 재구성했다."),
        ("표준 도구로 캘리브레이션 불가", "2026-06~07",
         "shoulder_lift 엔코더 래핑 · wrist_roll 연속 회전축 영점 불일치",
         "표준 lerobot-calibrate 로는 잡히지 않아 축마다 전용 도구를 직접 만들었다. "
         "정본 4종(leader_arm · follower_arm · wrist_zero · follower_home)을 "
         "확정하고 백업·복원 체계를 붙였다."),
        ("RPi 온보드 추론 중 정지", "2026-08-04 사전점검 → 08-29 실물",
         "수집 전 더미 가중치로 쟀을 때는 224×224 평균 0.509초로 합격이었다. "
         "실물도 평균은 23ms 였지만, 청크를 다시 계산하는 틱만 1023ms 로 튀어 "
         "20초에 4번 멈췄다.",
         "노트북 GPU 오프로드(gRPC)로 전환해 연결·제어까지 성공했으나 파지가 "
         "재현되지 않았다. 원인 미규명 상태로 조사를 종결하고, 노트북 단독 경로"
         "(rollout_act.ps1 · COM3 직결)로 제어 경로를 확정했다 — 15p 86.7%의 근거다."),
    ]
    top = 236
    rh = 276 / 4
    for i, (sym, when, cause, fix) in enumerate(cases):
        if i:
            rect(96, top - 0.5, 1088, 1, fill=RULE_SFT)
        textbox(96, top, 240, rh,
                [(sym, 13, 600, INK, 1.45, 0, 0),
                 (when, 11, 400, INK_FNT, 1.4, 0, 3)],
                anchor=MSO_ANCHOR.MIDDLE, tag=f"p16.s{i}")
        textbox(360, top, 316, rh, [(cause, 12, 400, INK_DIM, 1.5, 0, 0)],
                anchor=MSO_ANCHOR.MIDDLE, tag=f"p16.c{i}")
        textbox(700, top, 484, rh, [(fix, 12, 400, INK_DIM, 1.5, 0, 0)],
                anchor=MSO_ANCHOR.MIDDLE, tag=f"p16.f{i}")
        top += rh

    callout(BODY_X, 536, BODY_W, 128,
            [("남은 한계", 12, 600, ACCENT, 1.2, 0.08, 0),
             ("판정 → 초동 조치 자동 트리거는 코드 구현 후 실물 최종 검증이 남아 있다 · "
              "DRIVE 주행은 RPi/ESP 통합 이후 간헐적 오작동으로 이번 시연 범위에서 "
              "제외했다(안전 우선순위 판단 로직 자체는 구현되어 있다) · "
              "원거리 위치 파지 성공률 66.7% 는 개선 여지가 있다.",
              12, 400, INK, 1.55, 0, 6)])


# ══ 17 · 작품의 차별성 ════════════════════════════════════════════════════════
def p17():
    slide("05 · 결과와 일정", "발견에서 멈추지 않고 조치까지 간다",
          "기존 순찰·보안 로봇과의 차이는 조치 여부, 판정 근거, 그리고 조작 방식 세 곳에서 갈린다", 17)
    field(BODY_X, BODY_Y, 564, BODY_H)
    label(96, 200, 516, "① 기존 산업용 순찰·보안 로봇과의 기능 비교", size=12,
          color=INK_DIM, weight=600, spc=0.08)
    for cx, cw, ht, al in ((96, 220, "기능", PP_ALIGN.LEFT),
                           (340, 120, "기존 로봇", PP_ALIGN.CENTER),
                           (476, 136, "HazardBot", PP_ALIGN.CENTER)):
        textbox(cx, 236, cw, 15, [(ht, 11, 600, INK_FNT, 1.2, 0.06, 0)],
                align=al, wrap=False)
    rect(96, 264, 516, 1, fill=RULE)
    comp = [("순찰 · 감시", "○", "○", False),
            ("이상 감지 · 기록", "○", "○", False),
            ("관제 보고", "○", "○", False),
            ("물리적 초동 조치", "×", "○", True)]
    top = 272
    for i, (nm, a, b, hi) in enumerate(comp):
        if i:
            rect(96, top - 0.5, 516, 1, fill=RULE_SFT)
        if hi:
            rect(96, top, 516, 56, fill=WASH, radius=3)
        textbox(108, top, 208, 56, [(nm, 13, 600 if hi else 400, INK, 1.5, 0, 0)],
                anchor=MSO_ANCHOR.MIDDLE, wrap=False)
        textbox(340, top, 120, 56,
                [(a, 17, 400, HAZARD if hi else INK_FNT, 1.3, 0, 0)],
                anchor=MSO_ANCHOR.MIDDLE, align=PP_ALIGN.CENTER, wrap=False)
        textbox(476, top, 136, 56,
                [(b, 17, 600 if hi else 400, ACCENT if hi else INK_FNT, 1.3, 0, 0)],
                anchor=MSO_ANCHOR.MIDDLE, align=PP_ALIGN.CENTER, wrap=False)
        top += 56
    rect(96, 508, 516, 1, fill=RULE)
    textbox(96, 524, 516, 116,
            [("기존 로봇은 발견하고 알리는 데서 끝난다", 14, 600, INK, 1.5, 0, 0),
             ("결국 사람이 위험물에 다가가야 한다는 문제는 그대로 남는다. "
              "HazardBot 은 판정과 조치가 한 로봇 안에서 닫히므로, 사람이 현장에 "
              "들어가기 전에 격리라는 초동 조치가 이미 끝나 있다.",
              12, 400, INK_DIM, 1.55, 0, 8)], tag="p17.note")

    card(652, 176, 564, 232, eyebrow="② 판정 근거", title="색이 아니라 물성으로 나눈다",
         tag="p17.c1")
    rows(676, 269, 516, 115, [
        ("고체 — 황색", "가스를 내뿜지 않으므로 존재 자체가 위반이다. 즉시 판정한다."),
        ("액체 — 적색", "새어 나올 때만 위험해지므로 MQ-2 3초 검사로 2차 게이팅한다."),
    ], name_size=13, desc_size=11, tag="p17.c1.rows")

    card(652, 432, 564, 232, eyebrow="③ 조치 방식", title="고정 궤적이 아니라 학습된 정책",
         tag="p17.c2")
    rows(676, 525, 516, 115, [
        ("모방학습 정책", "좌표를 고정한 시퀀스가 아니라 사람 시연 100회를 학습한 "
                     "ACT 정책이라, 물체 위치가 달라져도 대응한다."),
        ("설계 근거", "판정 기준을 임의로 정하지 않고 위험물안전관리법 유별 혼재 제한과 "
                  "KS C IEC 60079-10-1 에서 가져왔다."),
    ], name_size=13, desc_size=11, tag="p17.c2.rows")


# ══ 18 · 기술적 우수성 · 완성도 ═══════════════════════════════════════════════
def p18():
    slide("05 · 결과와 일정", "임베디드 자원 제약을 구조로 풀었다",
          "센서를 주기별로 나누고, 정지 권한을 한 곳에 모으고, 없는 자원은 다른 방법으로 대체했다", 18)
    card(COL[0], BODY_Y, 368, BODY_H, eyebrow="① 구조",
         title="역할이 분리된 3계층", tag="p18.c0")
    textbox(88, 269, 320, 44,
            [("센서를 「누가 이 데이터로 행동하는가」를 기준으로 세 계층으로 "
              "재편했다.", 12, 400, INK_DIM, 1.5, 0, 0)], tag="p18.c0.lead")
    for cx, cw, ht, al in ((88, 150, "계층", PP_ALIGN.LEFT),
                           (238, 70, "주기", PP_ALIGN.RIGHT),
                           (324, 84, "담당", PP_ALIGN.RIGHT)):
        textbox(cx, 328, cw, 15, [(ht, 11, 600, INK_FNT, 1.2, 0.06, 0)],
                align=al, wrap=False)
    rect(88, 352, 320, 1, fill=RULE)
    tiers = [("실시간 반사", "20ms", "ESP_Drive", "라인센서 · ToF"),
             ("환경 감시", "100ms", "ESP_Env", "MQ-2 가스 · 화염"),
             ("인지 · 학습", "30fps", "RPi · 노트북", "카메라 · ACT")]
    top = 360
    for i, (nm, hz, who, what) in enumerate(tiers):
        if i:
            rect(88, top - 0.5, 320, 1, fill=RULE_SFT)
        textbox(88, top, 150, 70, [(nm, 13, 600, INK, 1.45, 0, 0),
                                   (what, 11, 400, INK_FNT, 1.4, 0, 2)],
                anchor=MSO_ANCHOR.MIDDLE, wrap=False)
        textbox(238, top, 70, 70, [(hz, 13, 600, ACCENT, 1.3, 0, 0)],
                anchor=MSO_ANCHOR.MIDDLE, align=PP_ALIGN.RIGHT, wrap=False)
        textbox(324, top, 84, 70, [(who, 12, 400, INK_DIM, 1.3, 0, 0)],
                anchor=MSO_ANCHOR.MIDDLE, align=PP_ALIGN.RIGHT, wrap=False)
        top += 70
    rect(88, 578, 320, 1, fill=RULE)
    label(88, 592, 320, "판단 기준을 계층으로 고정하니, 어떤 센서를 어느 보드에 "
          "붙일지가 논쟁이 아니라 규칙이 됐다.", size=11, color=INK_FNT, h=48,
          tag="p18.c0.note")

    card(COL[4], BODY_Y, 368, BODY_H, eyebrow="② 안전",
         title="정지 권한을 한 곳에 모았다", tag="p18.c1")
    rows(480, 269, 320, 371, [
        ("모터를 멈추는 것은 DRIVE 뿐",
         "하드웨어 풀다운 · DRIVE 로컬 · RPi · 사람의 4계층으로 나누되, "
         "실제로 모터를 끊는 권한은 DRIVE 한 곳에만 둔다."),
        ("하트비트 — 명령이 아니라 생존 신호",
         "STOP 을 보내는 방식이 아니라 생존 신호가 끊기면 멈추는 방식이라, "
         "RPi 사망 · WiFi 두절 · ENV 사망을 하나의 메커니즘으로 처리한다."),
        ("STBY 10kΩ 풀다운 페일세이프",
         "ESP32 가 죽거나 리셋되면 제어핀이 하이임피던스가 되어 모터가 자동 "
         "정지한다. 설계 결정을 하드웨어로 뒷받침했다."),
    ], name_size=13, desc_size=11, tag="p18.c1.rows")

    card(COL[8], BODY_Y, 368, BODY_H, eyebrow="③ 자원",
         title="없는 자원은 다르게 대체했다", tag="p18.c2")
    rows(872, 269, 320, 371, [
        ("전압 피드포워드",
         "엔코더 속도루프 없이 실제듀티 = 목표듀티 × (12.0 / 측정전압) 으로 "
         "배터리 전압 강하를 보상한다."),
        ("VL53L1X 논블로킹 읽기",
         "블로킹으로 읽으면 라인 PID 주기가 붕괴함을 규명하고 구조를 바꿨다."),
        ("라인 추종 PD 루프",
         "적분항 없이 KP=60 · KD=25 · 20ms(50Hz)로 구성했다. 센서 배선 없이 도는 "
         "가상 라인 모드로 조향 방향 · 비례 · 이탈 선회를 검증했고, 실측 게인 "
         "튜닝은 섀시 트랙 몫으로 남겼다."),
    ], name_size=13, desc_size=11, tag="p18.c2.rows")


# ══ 19 · 파급력 및 기대효과 ═══════════════════════════════════════════════════
def p19():
    slide("05 · 결과와 일정", "사람이 위험물에 다가가는 횟수를 줄인다",
          "지금 쓸 수 있는 곳과 기대효과, 그리고 실제 현장에 놓기 위해 넓혀야 할 네 축", 19)
    card(BODY_X, BODY_Y, 564, BODY_H, eyebrow="활용성", title="어디에 놓을 수 있나",
         tag="p19.left")
    label(88, 269, 516, "활용처", size=11, color=INK_FNT, weight=600, spc=0.06)
    cx = 88
    for t in ("반도체 FAB", "정유 · 화학 플랜트", "화학물질 보관창고"):
        cx += chip(cx, 290, t, size=12) + 8
    cx = 88
    for t in ("물류창고 야간 무인 시간대", "소방 · 안전관리 초동 대응 보조"):
        cx += chip(cx, 322, t, size=12) + 8
    rect(88, 368, 516, 1, fill=RULE_SFT)
    rows(88, 384, 516, 256, [
        ("감시의 공백을 메운다",
         "야간 · 연휴 · 교대 사이처럼 사람의 집중이 끊기는 시간대를 로봇이 "
         "같은 기준으로 이어서 지킨다."),
        ("사람이 도착하기 전에 격리가 끝나 있다",
         "이상을 발견하고 사람이 현장에 투입되기까지의 시간 동안, 초동 조치인 "
         "격리가 이미 완료된 상태를 만든다."),
        ("판정 근거가 기록으로 남는다",
         "색상값 · 가스값 · 시각이 EVENT LOG 에 쌓여 사후 확인과 원인 추적이 "
         "가능하다."),
    ], name_size=13, desc_size=11, tag="p19.left.rows")

    card(652, BODY_Y, 564, BODY_H, eyebrow="발전 가능성",
         title="현장에 놓기 위해 넓힐 네 축", tag="p19.right")
    rows(676, 269, 516, 371, [
        ("위험물 분류 확장",
         "지금은 색상 2분류뿐이다. 용기 라벨의 UN 번호와 QR/바코드를 읽어 "
         "MSDS(물질안전보건자료)와 연동하면 부식성 · 독성 · 압축가스까지 넓힐 수 있다."),
        ("초동 조치 범위 확장",
         "격리함 투입 외에 밸브 잠금, 국소 배기 가동, 흡착제 · 중화제 살포, "
         "스필 컨테인먼트 전개 같은 대응 동작으로 넓힌다."),
        ("온보드 자립 추론",
         "지금은 ACT 정책이 노트북 GPU 에서 돌고 USB 로 팔을 제어한다. 현장에서는 "
         "로봇이 스스로 판단해야 하므로, 온보드 추론의 정지 원인을 규명하거나 "
         "엣지 NPU 가속기를 얹어 노트북 없이 도는 구조로 만든다."),
        ("전 구역 주행 · 다중 로봇",
         "SLAM 기반 전 구역 주행으로 넓히고, 한 대로 감당할 수 없는 규모에는 "
         "구역 분담과 작업 핸드오프가 가능한 다중 로봇 구조로 확장한다."),
    ], name_size=13, desc_size=11, tag="p19.right.rows")


# ══ 20 · 개발 일정 및 업무 분장 ═══════════════════════════════════════════════
def p20():
    slide("05 · 결과와 일정", "13주 공정과 세 명의 역할",
          "2026-06-01부터 08-31까지 13주 · 기술적 선후관계로 순서를 정하고 역할을 나눴다", 20)
    field(BODY_X, BODY_Y, 564, BODY_H)
    label(96, 200, 516, "개발 일정 — 2026-06-01 ~ 08-31 · 13주", size=12,
          color=INK_DIM, weight=600, spc=0.08)
    phases = [("6월", "W1–W5", "계획 정본 · 저장소 · CI → 로봇팔 환경과 툴체인 → "
                              "전력 계통 설계·확정 → 3D 모델링 · 출력 → 캘리브레이션"),
              ("7월", "W6–W9", "캘리브레이션 정본 확정 → 텔레옵 마일스톤 → "
                              "DRIVE 보드와 주행 펌웨어 → 안전 체계 · 센서 체계 설계"),
              ("8월", "W10–W13", "시나리오 · 시연 설계 정본 → 세트 제작과 실측 → "
                                "수집 게이트 · 준비 → ACT 수집 · 학습 · 검증"),
              ("9월", "제출", "개발완료보고서 · 시연동영상 · 소스코드 저장소 정리")]
    top = 232
    for i, (m, w, txt) in enumerate(phases):
        if i:
            rect(96, top - 0.5, 516, 1, fill=RULE_SFT)
        rect(96, top + 12, 3, 44, fill=ACCENT if i < 3 else RULE)
        textbox(112, top, 84, 68, [(m, 17, 700, INK, 1.3, -0.02, 0),
                                   (w, 11, 400, INK_FNT, 1.3, 0, 2)],
                anchor=MSO_ANCHOR.MIDDLE, wrap=False)
        textbox(204, top, 408, 68, [(txt, 11, 400, INK_DIM, 1.5, 0, 0)],
                anchor=MSO_ANCHOR.MIDDLE, tag=f"p20.ph{i}")
        top += 68
    rect(96, 508, 516, 1, fill=RULE)
    label(96, 520, 516, "마일스톤", size=11, color=INK_FNT, weight=600, spc=0.06)
    ms = [("07/11", "캘리브레이션 정본 4종 확정", False),
          ("07/16", "텔레옵 마일스톤 — 60초 오류 0건 · 평균 55.5Hz", True),
          ("08/14", "시연 공간 확보 · 세트 제작 완료", False),
          ("08/26", "ACT 학습 완료 — 100,000 스텝", True)]
    for i, (d, t, star) in enumerate(ms):
        y = 544 + i * 26
        textbox(96, y, 60, 24, [(d, 12, 600, ACCENT if star else INK_FNT,
                                 1.3, 0, 0)],
                anchor=MSO_ANCHOR.MIDDLE, wrap=False)
        textbox(164, y, 448, 24,
                [(("★ " if star else "") + t, 12, 600 if star else 400,
                  INK if star else INK_DIM, 1.3, 0, 0)],
                anchor=MSO_ANCHOR.MIDDLE, wrap=False, tag=f"p20.ms{i}")

    field(652, BODY_Y, 564, BODY_H)
    label(684, 200, 516, "업무 분장", size=12, color=INK_DIM, weight=600, spc=0.08)
    people = [("팀장", "승환", "로봇팔 · 주행 · 전력 · 시연 설계",
               "SO-101 리더-팔로워 구성, 시연 100회 수집과 ACT 정책 학습, "
               "RTX 4060 롤아웃 파이프라인 · ESP_Drive 펌웨어와 안전 우선순위 판단 "
               "로직 · 배터리부터 각 보드까지 전력 계통 전 구간 · 시나리오와 세트 설계"),
              ("팀원", "강희", "센서 하드웨어 · 펌웨어 · 시연 영상",
               "MQ-2 가스센서와 화염센서 배선 · 납땜과 급전 경로 구성 · "
               "센서 샘플링과 3초 가스 정밀검사(GAS_CHECK) 로직 구현 · "
               "판정 결과(DETECTED / CLEAR / ERROR) 전달 통신 · 제출 시연 영상 제작"),
              ("팀원", "진우", "ROS2 통합 · 배포 · 저장소",
               "ROS2 워크스페이스 구성과 노드 통합 · sensor_bridge_node 와 "
               "amr_bridge_node 를 통한 RPi–ESP 통신 연결 · RPi 실물 대시보드 배포와 "
               "실기 검증 · GitHub 저장소 관리")]
    top = 232
    rh = 408 / 3
    for i, (role, name, area, work) in enumerate(people):
        if i:
            rect(684, top - 0.5, 516, 1, fill=RULE_SFT)
        chip(684, top + 14, role, size=11, fill=WASH if i == 0 else GROUND,
             color=ACCENT if i == 0 else INK_DIM, h=20)
        textbox(684, top + 42, 96, 28, [(name, 19, 600, INK, 1.3, -0.015, 0)],
                wrap=False)
        textbox(788, top + 12, 412, rh - 24,
                [(area, 12, 600, INK, 1.45, 0, 0),
                 (work, 11, 400, INK_DIM, 1.5, 0, 5)], tag=f"p20.pp{i}")
        top += rh


# ══ 마무리 (분량 제외) ════════════════════════════════════════════════════════
def s_close():
    """대회가 분량에서 제외하는 인사 페이지. 평가 대상 내용을 여기 두지 않는다."""
    new_slide()
    ground()
    mark(96, 232, 96)
    textbox(224, 244, 900, 44,
            [("감사합니다", 36, 700, INK, 1.1, -0.02, 0)],
            anchor=MSO_ANCHOR.MIDDLE, wrap=False)
    textbox(226, 300, 900, 22,
            [("HazardBot — 감지 · 판정에서 초동 조치까지", 14, 400, INK_DIM,
              1.5, 0, 0)], wrap=False)
    rect(96, 392, 1088, 1, fill=RULE)
    callout(96, 424, 1088, 128,
            [("Q & A", 12, 600, ACCENT, 1.2, 0.08, 0),
             ("남은 과제는 RPi 온보드 추론 경로의 원인 규명, 판정 → 조치 자동 "
              "연동의 실물 최종 검증, DRIVE 주행 재개다.",
              16, 400, INK, 1.6, -0.005, 8)])
    textbox(96, 596, 700, 18,
            [("제24회 임베디드SW경진대회 · 자유공모 · " + pend(TEAM),
              12, 600, INK_FNT, 1.2, 0.08, 0)],
            anchor=MSO_ANCHOR.MIDDLE, wrap=False)
    textbox(484, 596, 700, 18, [("2026-09-03", 12, 600, INK_FNT, 1.2, 0.08, 0)],
            anchor=MSO_ANCHOR.MIDDLE, align=PP_ALIGN.RIGHT, wrap=False)


# ══ 빌드 ══════════════════════════════════════════════════════════════════════
BODY_PAGES = [p01, p02, p03, p04, p05, p06, p07, p08, p09, p10,
              p11, p12, p13, p14, p15, p16, p17, p18, p19, p20]

if __name__ == "__main__":
    s_cover()
    for fn in BODY_PAGES:
        fn()
    s_close()
    D.save(OUT)
    n = len(D.prs.slides._sldIdLst)
    print("saved:", OUT)
    print(f"slides: {n}  (표지 1 + 본문 {len(BODY_PAGES)} + 마무리 1)")
    if not TEAM or not GITHUB_URL or not YOUTUBE_URL:
        miss = [k for k, v in (("TEAM", TEAM), ("GITHUB_URL", GITHUB_URL),
                               ("YOUTUBE_URL", YOUTUBE_URL)) if not v]
        print("미확정 값:", ", ".join(miss), "— build_deck.py 상단에서 채운다")
    if D.WARNINGS:
        print(f"\n--- {len(D.WARNINGS)} warning(s) ---")
        for w in D.WARNINGS:
            print("  " + w)
    else:
        print("\nno layout warnings")
