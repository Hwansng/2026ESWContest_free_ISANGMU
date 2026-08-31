# -*- coding: utf-8 -*-
"""렌더된 22장(표지 + 본문 20 + 마무리)을 한 페이지에 모은 검토용 프루프 시트."""
import base64, io, os, sys
from PIL import Image

# 렌더 PNG 폴더를 인자로 받는다. PowerPoint에서 내보낸 s01.png~s22.png 가 들어 있어야 한다.
# 슬라이드 번호(s01~s22)와 쪽번호는 다르다 — 표지·마무리는 대회 분량 산정에서 빠지므로
# 본문 20p 의 쪽번호는 슬라이드 번호에서 1을 뺀 값이다.
HERE = os.path.dirname(os.path.abspath(__file__))
RENDER = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(HERE, "render")
DST = os.path.join(os.path.dirname(RENDER), "deck_review.html")

SLIDES = [
    (1, None, "표지", "HazardBot — 자유공모 · 개발완료보고서", None),
    (2, 1, "목차", "대회 필수항목 7개에 맞춘 5개 장", "00 · 목차"),
    (3, 2, "개발 배경 · 동기", "사람이 계속 지킬 수 없는 구역이 있다", "01 · 개발 개요"),
    (4, 3, "개발 목표 · 필요성", "감지 · 판정 · 초동 조치를 하나의 흐름으로", "01 · 개발 개요"),
    (5, 4, "작품 개요 · 제출 링크", "작품 개요와 제출 링크", "01 · 개발 개요"),
    (6, 5, "시스템 개요", "HazardBot — 감지에서 초동 조치까지", "02 · 개발 환경"),
    (7, 6, "하드웨어 · 전력 계통", "네 개의 하드웨어 단위와 세 개의 전력 레일", "02 · 개발 환경"),
    (8, 7, "개발 환경 · 오픈소스", "개발 환경과 활용한 오픈소스", "02 · 개발 환경"),
    (9, 8, "소프트웨어 아키텍처", "ROS2 노드가 판정과 조치를 이어 붙인다", "02 · 개발 환경"),
    (10, 9, "파일 구성 · 주요 함수", "소스코드 최종 커밋 후 작성 — 보류", "02 · 개발 환경"),
    (11, 10, "위험물 판정 로직", "색으로 나누고, 필요할 때만 가스로 확인한다", "03 · 개발 프로그램"),
    (12, 11, "GAS_CHECK 정밀검사", "적색 물질은 3초 정밀검사를 거친다", "03 · 개발 프로그램"),
    (13, 12, "ACT 로봇팔 학습", "사람의 시연 100회를 정책으로 학습했다", "03 · 개발 프로그램"),
    (14, 13, "ACT 초동 조치 동작", "집어서 넣고 뚜껑까지, 한 번에 수행한다", "03 · 개발 프로그램"),
    (15, 14, "통합 파이프라인 · 대시보드", "판정에서 조치까지, 그리고 화면에 남는 기록",
     "03 · 개발 프로그램"),
    (16, 15, "검증 결과", "파지 30회, 판정 3케이스를 실물로 확인했다", "03 · 개발 프로그램"),
    (17, 16, "장애요인과 해결방안", "막힌 지점마다 원인을 규명하고 우회했다",
     "04 · 장애요인과 해결"),
    (18, 17, "작품의 차별성", "발견에서 멈추지 않고 조치까지 간다", "05 · 결과와 일정"),
    (19, 18, "기술적 우수성 · 완성도", "임베디드 자원 제약을 구조로 풀었다", "05 · 결과와 일정"),
    (20, 19, "파급력 및 기대효과", "사람이 위험물에 다가가는 횟수를 줄인다", "05 · 결과와 일정"),
    (21, 20, "개발 일정 · 업무 분장", "13주 공정과 세 명의 역할", "05 · 결과와 일정"),
    (22, None, "마무리 · Q&A", "감사합니다 — 분량 제외", None),
]

# 키는 슬라이드 번호(s01~s22)이지 쪽번호가 아니다.
NOTES = {
    1: "🔴 팀번호_팀명은 확정 후 삽입 — build_deck.py 상단 TEAM",
    4: "시연 공간 사진 — 사진/전체 시연장.jpg",
    5: "🔴 GitHub · YouTube 링크는 확정 후 삽입 — build_deck.py 상단 "
       "GITHUB_URL / YOUTUBE_URL. 대회가 필수로 지정한 항목이다",
    10: "🔴 보류 페이지 — 소스코드 최종 커밋 후 실제 트리와 함수로 채운다",
    13: "ACT 시연 데이터 수집 — ACT데이터_학습.mp4 의 7초. 사람이 두 손으로 잡은 "
        "흰 팔이 리더암, 섀시 위가 팔로워암이다",
    14: "네 단계 각 프레임 — rollout_성공률_측정.mp4 의 7 · 9 · 13 · 19초",
    15: "대시보드 전체 화면 — HazardBot_대시보드.mp4 의 150초. EVENT LOG 한 화면에 "
        "세 판정이 모두 남아 있는 프레임을 골랐다",
    16: "막대 수치는 rollout_plan.csv 30행을 다시 집계해 산출",
    17: "일자와 경위는 docs/02_schedule/작업일정_전체_2026-06-01_2026-08-31.md",
    21: "13주 공정과 마일스톤도 같은 공정표에서 가져왔다",
}


def data_uri(n):
    im = Image.open(os.path.join(RENDER, f"s{n:02d}.png")).convert("RGB")
    im = im.resize((1600, 900), Image.LANCZOS)
    b = io.BytesIO()
    im.save(b, "JPEG", quality=84, optimize=True, progressive=True)
    return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()


CSS = """
<title>HazardBot 덱 프루프</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans+KR:wght@300;400;500;600&display=swap">
<style>
:root{
  --ground:#ececed; --surface:#ffffff; --raise:#f6f6f7;
  --ink:#1d1d1f; --muted:#6e6e73; --faint:#9a9aa0;
  --line:#d8d8dc; --line-soft:#e6e6e9; --accent:#0066cc; --shadow:rgba(20,22,30,.13);
  --sans:'IBM Plex Sans KR',system-ui,sans-serif;
  --mono:'IBM Plex Mono','IBM Plex Sans KR',ui-monospace,monospace;
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --ground:#141416; --surface:#1c1c1f; --raise:#232327;
    --ink:#f2f2f4; --muted:#98989f; --faint:#6b6b73;
    --line:#2e2e33; --line-soft:#26262b; --accent:#2997ff; --shadow:rgba(0,0,0,.5);
  }
}
:root[data-theme="dark"]{
  --ground:#141416; --surface:#1c1c1f; --raise:#232327;
  --ink:#f2f2f4; --muted:#98989f; --faint:#6b6b73;
  --line:#2e2e33; --line-soft:#26262b; --accent:#2997ff; --shadow:rgba(0,0,0,.5);
}
*{box-sizing:border-box}
body{margin:0;background:var(--ground);color:var(--ink);
  font-family:var(--sans);font-weight:400;-webkit-font-smoothing:antialiased}
a{color:inherit}
.wrap{max-width:1500px;margin:0 auto;padding:0 28px 96px;
  display:grid;grid-template-columns:230px minmax(0,1fr);gap:44px;align-items:start}

/* ── 머리말 ─────────────────────────────────────────────── */
header{grid-column:1/-1;padding:56px 0 34px;border-bottom:1px solid var(--line)}
.eyebrow{font-family:var(--mono);font-size:11.5px;letter-spacing:.14em;
  text-transform:uppercase;color:var(--accent);margin:0 0 14px}
h1{font-size:clamp(30px,4.4vw,46px);font-weight:600;letter-spacing:-.022em;
  line-height:1.1;margin:0;text-wrap:balance}
.lede{margin:14px 0 0;max-width:62ch;font-size:16px;line-height:1.6;
  font-weight:300;color:var(--muted)}
.facts{display:flex;flex-wrap:wrap;gap:8px 10px;margin:26px 0 0;padding:0;list-style:none}
.facts li{font-family:var(--mono);font-size:11.5px;letter-spacing:.02em;
  color:var(--muted);background:var(--surface);border:1px solid var(--line);
  border-radius:3px;padding:5px 10px}
.facts b{font-weight:500;color:var(--ink)}

/* ── 좌측 색인 ──────────────────────────────────────────── */
nav{position:sticky;top:22px;padding:30px 0 0}
.navhead{font-family:var(--mono);font-size:10.5px;letter-spacing:.16em;
  text-transform:uppercase;color:var(--faint);margin:0 0 14px}
.chap{font-size:11.5px;font-weight:600;letter-spacing:.04em;color:var(--faint);
  margin:20px 0 7px;padding-top:12px;border-top:1px solid var(--line-soft)}
.chap:first-of-type{border-top:0;padding-top:0;margin-top:0}
nav ol{list-style:none;margin:0;padding:0}
nav a{display:flex;gap:9px;align-items:baseline;text-decoration:none;
  padding:4px 8px 4px 6px;border-radius:4px;border-left:2px solid transparent;
  font-size:13px;line-height:1.35;color:var(--muted)}
nav a:hover{background:var(--surface);color:var(--ink)}
nav a .n{font-family:var(--mono);font-size:11px;color:var(--faint);
  font-variant-numeric:tabular-nums;flex:none}
nav a.on{color:var(--ink);font-weight:500;border-left-color:var(--accent);background:var(--surface)}
nav a.on .n{color:var(--accent)}
nav a:focus-visible{outline:2px solid var(--accent);outline-offset:1px}

/* ── 슬라이드 ───────────────────────────────────────────── */
main{padding-top:30px;display:flex;flex-direction:column;gap:52px;min-width:0}
.slide{scroll-margin-top:22px}
.slug{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;margin:0 0 11px;padding-left:2px}
.slug .pg{font-family:var(--mono);font-size:12px;font-weight:500;color:var(--accent);
  font-variant-numeric:tabular-nums;flex:none}
.slug .nm{font-size:15px;font-weight:600;letter-spacing:-.01em}
.slug .ti{font-size:13px;color:var(--muted);font-weight:300}
.frame{background:var(--surface);border:1px solid var(--line);border-radius:8px;
  padding:9px;box-shadow:0 2px 5px var(--shadow),0 14px 34px -18px var(--shadow)}
.frame img{display:block;width:100%;height:auto;border-radius:3px;
  background:var(--raise)}
.note{margin:10px 0 0;padding-left:2px;font-family:var(--mono);font-size:11px;
  line-height:1.5;color:var(--faint)}
footer{grid-column:1/-1;margin-top:70px;padding-top:24px;border-top:1px solid var(--line);
  font-size:12.5px;color:var(--faint);line-height:1.7}
footer code{font-family:var(--mono);font-size:11.5px;color:var(--muted)}

@media (max-width:940px){
  .wrap{grid-template-columns:1fr;gap:0;padding:0 18px 72px}
  nav{display:none}
  main{padding-top:26px;gap:40px}
}
@media (prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}}
html{scroll-behavior:smooth}
</style>
"""


def build():
    chapters = []
    for sn, pg, name, title, rail in SLIDES:
        ch = rail.split(" · ", 1)[1] if rail else "분량 제외"
        if not chapters or chapters[-1][0] != ch:
            chapters.append((ch, []))
        chapters[-1][1].append((sn, pg, name))

    nav = ['<nav aria-label="슬라이드 색인">'
           '<p class="navhead">22장 · 본문 20p</p>']
    for ch, items in chapters:
        nav.append(f'<p class="chap">{ch}</p><ol>')
        for sn, pg, name in items:
            lbl = f"{pg:02d}" if pg else "—"
            nav.append(f'<li><a href="#p{sn:02d}" data-pg="{sn:02d}">'
                       f'<span class="n">{lbl}</span><span>{name}</span></a></li>')
        nav.append("</ol>")
    nav.append("</nav>")

    main = ["<main>"]
    for sn, pg, name, title, rail in SLIDES:
        note = NOTES.get(sn)
        slug = f"{pg:02d} / 20" if pg else "분량 제외"
        main.append(f'''<section class="slide" id="p{sn:02d}">
  <p class="slug"><span class="pg">{slug}</span>
    <span class="nm">{name}</span><span class="ti">{title}</span></p>
  <div class="frame"><img src="{data_uri(sn)}" alt="{name} — {title}" loading="lazy" decoding="async"></div>
  {f'<p class="note">{note}</p>' if note else ''}
</section>''')
    main.append("</main>")

    html = f"""{CSS}
<div class="wrap">
<header>
  <p class="eyebrow">Proof sheet · 2026-09-02 · 대회 양식 반영</p>
  <h1>HazardBot 개발완료보고서</h1>
  <p class="lede">PowerPoint에서 내보낸 22장을 그대로 올렸습니다. 파일이 아니라 실제 렌더 결과라,
    여기서 보이는 것이 심사위원이 보는 것입니다. 대회는 <b>표지와 인사 페이지를 20p 산정에서
    제외</b>하므로 물리적으로는 22장이지만, 평가 대상 본문은 20p 입니다.</p>
  <ul class="facts">
    <li>표지 + 본문 <b>20</b>p + 마무리 · 16:9 1280×720</li>
    <li>서체 <b>Pretendard</b> (SIL OFL 1.1)</li>
    <li>강조색 <b>#0066cc</b> 단일</li>
    <li>본문 하단 <b>y≤664</b> · 본문 20p 전부 통과</li>
    <li>제목 <b>y=76</b> · 헤더 룰 <b>y=158</b> 픽셀 동일</li>
    <li>미확정 <b>팀명 · GitHub · YouTube</b></li>
  </ul>
</header>
{''.join(nav)}
{''.join(main)}
<footer>
  원본 파일 <code>PPT/HazardBot_개발완료보고서_2026-09-01.pptx</code> ·
  내용 근거 <code>PPT_구성안_2026-09-01.md</code> · 형식 근거 <code>design.md</code> ·
  분량·필수항목 근거 <code>PPT/양식/</code> · 검증 수치 <code>rollout_plan.csv</code><br>
  사진과 대시보드 화면은 <code>PPT/사진</code>, <code>PPT/영상</code> 원본에서 직접 추출했습니다.
  제출은 PDF 변환본으로 하며 파일명은
  <code>2026ESWContest_자유공모_팀명_개발완료보고서.pdf</code> 입니다.
</footer>
</div>
<script>
const links = [...document.querySelectorAll('nav a')];
const byPg = new Map(links.map(a => [a.dataset.pg, a]));
const io = new IntersectionObserver(entries => {{
  entries.forEach(e => {{
    if (!e.isIntersecting) return;
    links.forEach(a => a.classList.remove('on'));
    const a = byPg.get(e.target.id.slice(1));
    if (a) a.classList.add('on');
  }});
}}, {{rootMargin: '-15% 0px -70% 0px', threshold: 0}});
document.querySelectorAll('.slide').forEach(s => io.observe(s));
</script>
"""
    with open(DST, "w", encoding="utf-8") as f:
        f.write(html)
    print("wrote:", DST, os.path.getsize(DST) // 1024, "KB")


if __name__ == "__main__":
    build()
