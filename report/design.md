# HazardBot Deck — Design System

> **Scope.** This file is the single source of truth for building the *HazardBot 개발완료보고서* slide deck. It defines the canvas, the fixed slide frame, type, color, the brand mark, and the density rules. Slide **content** lives in `PPT_구성안_2026-09-01.md`; this file says nothing about what goes on each page, only how it must look.

## 0. How to Use This File

1. Every slide is a **1280 × 720 artboard**. Nothing else. See §2.
2. The header block (chapter rail → title → subtitle → rule) sits at **identical pixel coordinates on every slide**. See §3. This is the hardest rule in the system.
3. **Pretendard is the only font.** No fallback face, no monospace, no display face, no Google Font. See §4.
4. The **HazardBot mark** (§6) is the only logo that may appear anywhere in the deck.
5. Fill the body region. A slide whose lower third is empty is a defect, not a style. See §8.
6. Reference tokens (`{colors.primary}`, `{typography.title}`, `{component.metric-strip}`) — never inline a hex or a raw px size that isn't in a table here.
7. If content does not fit the body region: split into two slides, or cut. Never shrink type below the minimums in §4, never reduce the §3 margins, never let the body scroll or overflow.

## 1. Overview

The deck is a **quiet engineering report**: an off-white parchment ground, near-black ink, hairline rules, one quiet blue, and no decorative chrome. Nothing on a slide exists to look like something — every mark on the page is either content, a label for content, or a hairline that separates two pieces of content.

The visual model is a **technical field notebook, not a marketing deck**. Slides are dense and evenly filled, the way a spec sheet is dense: a header block that never moves, a body divided into a small number of rectangular fields, and a footer that quietly states where you are. Emphasis is created by *surface change* (parchment → white field → dark tile) and by *the single accent*, never by shadows, gradients, glows, or oversized type.

**One color carries meaning, and it carries it the same way on every slide.** `{colors.primary}` (Action Blue) marks the one thing a slide is about — the key figure, the active step in a pipeline, the row that matters. Everything else is neutral: ink, muted ink, parchment, white, hairline. There is no second brand color, and no structural hue for diagrams — diagrams are monochrome and the blue marks the live element. If a slide has three colored things on it, two of them are wrong.

The one exception is the status triad (hazard / oxidizer / clear), which is *content*, not styling: it encodes 판정 결과 and appears only inside badges, chart series, and legend rows.

**Key Characteristics**

- Fixed 16:9 artboard, fixed header frame, fixed footer — the eye never re-hunts for the title.
- Parchment ground (`{colors.canvas-parchment}` #f5f5f7) with white (`{colors.canvas}`) reserved for *fields* — diagrams, screenshots, tables — so content reads as inset into the page.
- A single blue accent (`{colors.primary}` — #0066cc) carries every emphasis. No second brand color exists.
- Pretendard across the entire deck, four weights only (300 / 400 / 600 / 700).
- Hairlines instead of borders-with-weight; surface change instead of shadows. Exactly one shadow exists in the system, and it is only for photographs (§9).
- Bodies are **filled**, not centered-in-void: every slide bottom lands on a metric strip, an evidence rail, or the last row of a grid.
- Near-black tile (`{colors.surface-tile-1}` #272729) is reserved for section dividers, as rhythm at a chapter boundary — never as decoration, and never for the cover. A deck with no dividers therefore carries no dark surface at all: parchment from the first page to the last.

## 2. Canvas & Format

### 16:9, and only 16:9

| Property | Value |
|---|---|
| Artboard | **1280 × 720 px**, every slide, no exceptions |
| Aspect ratio | 16:9 — no 4:3, no A4, no portrait, no auto-height, no scrolling page |
| Export | PNG or PDF at **2×** (2560 × 1440); 3× if the deck will be projected above 1440p |
| Overflow | Forbidden. `overflow: hidden` on the slide box is a safety net, not a layout strategy |
| Bleed | None. All content sits inside the §3 safe margins |

```css
.slide {
  position: relative;
  width: 1280px;
  height: 720px;
  overflow: hidden;
  background: var(--canvas-parchment);
  color: var(--ink);
  font-family: 'Pretendard', sans-serif;
  page-break-after: always;   /* one slide per printed page */
}
@page { size: 1280px 720px; margin: 0; }
```

Slides stack vertically in the source document with a 32px gap between them for authoring convenience; that gap is a preview affordance and must not print.

### Why the fixed pixel canvas

Everything in this file is specified in absolute px against 1280 × 720. There is **no responsive behavior, no breakpoints, no fluid type**. A slide that reflows is a slide whose title moved — which §3 forbids. Scale the whole artboard with a `transform: scale()` on a wrapper if you need to preview it smaller; never scale the contents individually.

## 3. The Master Frame — Fixed Positions

Every slide carries the same four header elements at the same coordinates, and the same footer. A reader's eye should be able to rest at one height and read the title of every slide in the deck without moving.

```
 x=0                                                                    x=1280
 ┌───────────────────────────────────────────────────────────────────────┐ y=0
 │                                                                       │
 │   ◾ 03 · 시스템 구성                                          y=44 ──┼── header rail (18h)
 │                                                                       │
 │   소프트웨어 아키텍처                                          y=72 ──┼── title (44h)
 │   ROS2 노드·토픽 그래프                                       y=122 ──┼── subtitle (24h)
 │   ─────────────────────────────────────────────────────────  y=158 ──┼── rule (1px)
 │                                                                       │
 │   ┌─────────────────────────────────────────────────────────┐ y=176 ─┼── body top
 │   │                                                         │        │
 │   │                     BODY  1152 × 488                    │        │
 │   │                                                         │        │
 │   └─────────────────────────────────────────────────────────┘ y=664 ─┼── body bottom
 │                                                                       │
 │   ▣ HazardBot 개발완료보고서                            07 / 20  y=676┼── footer (20h)
 └───────────────────────────────────────────────────────────────────────┘ y=720
 x=64                                                             x=1216
```

### Coordinate table — memorize this

| Token | Region | x | y | width | height |
|---|---|---|---|---|---|
| `{frame.slide}` | Artboard | 0 | 0 | 1280 | 720 |
| `{frame.rail}` | Chapter rail | 64 | 44 | 1152 | 18 |
| `{frame.title}` | Slide title | 64 | 72 | 1152 | 44 |
| `{frame.subtitle}` | Slide subtitle | 64 | 122 | 1152 | 24 |
| `{frame.rule}` | Header hairline | 64 | 158 | 1152 | 1 |
| `{frame.body}` | Body region | 64 | 176 | 1152 | 488 |
| `{frame.footer}` | Footer bar | 64 | 676 | 1152 | 20 |

Safe margins: **64 left · 64 right · 44 top · 24 bottom**. Content never crosses them.

```css
.rail     { position:absolute; left:64px; top:44px;  width:1152px; height:18px;  }
.title    { position:absolute; left:64px; top:72px;  width:1152px; height:44px;  }
.subtitle { position:absolute; left:64px; top:122px; width:1152px; height:24px;  }
.rule     { position:absolute; left:64px; top:158px; width:1152px; height:1px;
            background: var(--hairline); }
.body     { position:absolute; left:64px; top:176px; width:1152px; height:488px; }
.footer   { position:absolute; left:64px; top:676px; width:1152px; height:20px;
            display:flex; align-items:center; justify-content:space-between; }
```

### Rules that make the frame hold

- **Title is always one line.** 36px SemiBold in 1152px fits roughly 34 Korean characters. If it doesn't fit, rewrite the title — do not wrap it, do not shrink it, do not let it push the subtitle down.
- **Subtitle height is reserved whether or not it is used.** A slide with no subtitle leaves the 24px band empty; the rule stays at y=158. Never close the gap.
- **The rail is never empty.** Format: `{chapter number, 2 digits} · {chapter name}`, preceded by a 6×6px amber square at 6px gap. Same chapter name for every slide in that chapter.
- **The footer is never empty and never changes shape.** Left: the 18px mark + `HazardBot 개발완료보고서`. Right: `{page, 2 digits} / 20`. Nothing else ever goes in the footer.
- **The three exceptions, and only these three:**
  1. `{component.slide-cover}` — parchment ground like every other slide, but no rail, no rule, no footer, no page number.
  2. `{component.slide-divider}` — dark ground, but the rail / title / subtitle / rule / footer stay at the *exact same coordinates*; only the surface and ink colors invert.
  3. `{component.slide-full-bleed}` — a single edge-to-edge photograph or dashboard capture. The header block still sits at its coordinates, over a scrim (§9). The body region is what goes full-bleed, not the frame.

## 4. Typography — Pretendard Only

### Font family

**Pretendard is the only typeface in this deck.** There is no display face, no secondary UI face, no monospace face, and no system fallback that is expected to ever render. Big Shoulders — used for the wordmark in the original mark artifact — is **not used here**; the HazardBot wordmark is reset in Pretendard Bold (§6).

```css
@font-face { font-family:'Pretendard'; font-weight:300;
             src:url('./폰트/Pretendard-Light.otf')    format('opentype'); font-display:block; }
@font-face { font-family:'Pretendard'; font-weight:400;
             src:url('./폰트/Pretendard-Regular.otf')  format('opentype'); font-display:block; }
@font-face { font-family:'Pretendard'; font-weight:600;
             src:url('./폰트/Pretendard-SemiBold.otf') format('opentype'); font-display:block; }
@font-face { font-family:'Pretendard'; font-weight:700;
             src:url('./폰트/Pretendard-Bold.otf')     format('opentype'); font-display:block; }

:root { font-family:'Pretendard', sans-serif; }
```

**Font loading, by output path** — the deck is wrong if Pretendard fails to load, so pick the right one:

- **Local HTML → print to PDF (recommended).** Use the `url()` declarations above; the OTFs in `PPT/폰트/` load directly, size is irrelevant. If the toolchain mangles the non-ASCII folder name, copy `폰트/` to `./fonts/` and update the paths.
- **Published as an Artifact.** External stylesheets are restricted to `fonts.googleapis.com`, and Pretendard is not hosted there — a jsDelivr or CDN stylesheet **will silently fail**. Convert the four weights to `.woff2`, subset to Hangul + Latin + digits, and inline them as `data:font/woff2;base64,…` inside the `@font-face` blocks.
- Never write a fallback chain that could actually resolve (`-apple-system`, `Malgun Gothic`, `sans-serif` as a real target). A missing Pretendard must look broken, so it gets fixed.

### Weight ladder — 300 / 400 / 600 / 700

Only four weights are used. Thin, ExtraLight, Medium, ExtraBold, and Black are present in the folder but are **not part of this system** — do not reach for them to solve a hierarchy problem. Emphasis inside body copy is 600, never 500 and never 800.

### Hierarchy

| Token | Size | Weight | Line Height | Letter Spacing | Use |
|---|---|---|---|---|---|
| `{typography.deck-title}` | 60px | 700 | 1.06 | -0.025em | Cover title only |
| `{typography.deck-subtitle}` | 20px | 400 | 1.5 | -0.01em | Cover one-line summary |
| `{typography.section-numeral}` | 96px | 700 | 1.0 | -0.03em | Section divider chapter numeral |
| `{typography.rail}` | 13px | 600 | 1.0 | 0.12em | Chapter rail |
| `{typography.title}` | 36px | 600 | 1.15 | -0.02em | Slide title (one line, always) |
| `{typography.subtitle}` | 17px | 400 | 1.45 | -0.01em | Slide subtitle, `{colors.ink-muted-80}` |
| `{typography.lead}` | 22px | 300 | 1.55 | -0.01em | Single-statement slides (goal, conclusion) — rare, and the only use of weight 300 |
| `{typography.card-title}` | 19px | 600 | 1.35 | -0.015em | Card and field headings |
| `{typography.body}` | 16px | 400 | 1.65 | -0.005em | Default body copy |
| `{typography.body-strong}` | 16px | 600 | 1.65 | -0.005em | Inline emphasis inside body copy |
| `{typography.body-dense}` | 14px | 400 | 1.6 | 0 | 4-column cards, side rails, list-heavy fields |
| `{typography.label}` | 12px | 600 | 1.2 | 0.08em | Eyebrow labels inside cards and fields |
| `{typography.metric}` | 44px | 700 | 1.0 | -0.02em | Key figures — `tnum` on |
| `{typography.metric-sub}` | 15px | 600 | 1.3 | 0 | Metric caption line |
| `{typography.chip}` | 13px | 400 | 1.0 | 0 | Topic / node / file names — `tnum` on |
| `{typography.caption}` | 12px | 400 | 1.5 | 0 | Image and diagram captions |
| `{typography.footnote}` | 11px | 400 | 1.45 | 0 | Evidence rail, source notes |
| `{typography.footer}` | 11px | 600 | 1.0 | 0.06em | Footer bar, page number |

**Absolute minimum size: 11px.** At 1280×720 projected to 1080p that renders at ~16.5px — legible from the back of a room. Anything smaller does not go on a slide; it goes in the speaker notes.

### Korean typesetting rules

These are not optional — Korean set with Latin defaults looks broken at slide sizes.

```css
.body, .card, p, li { word-break: keep-all; overflow-wrap: break-word; text-wrap: pretty; }
.metric, .chip, table { font-feature-settings: "tnum" 1; }
```

- **`word-break: keep-all`** everywhere. Korean must break at word boundaries, never mid-어절.
- **Never justify.** All Korean copy is left-aligned, ragged right. `text-align: justify` on Hangul produces rivers.
- **Line length:** 30–45 Korean characters. Past that, split the field into two columns.
- **Tabular figures (`tnum`)** on every metric, table, and chip so numbers align in columns and don't jitter between slides.
- **Pretendard has no true italic.** Never use `font-style: italic` — the browser will synthesize an oblique that is visibly wrong on Hangul. Emphasis is weight 600 or `{colors.primary}`, nothing else.
- Latin words and code identifiers inside Korean sentences stay in Pretendard. Do not switch face for `mission_orchestrator` or `/hazard/detected` — use `{component.code-chip}` instead (§11).
- Do not letterspace Hangul body copy. Positive tracking is reserved for `{typography.rail}`, `{typography.label}`, and `{typography.footer}`, which are short Latin-and-number-heavy strings.

## 5. Colors

> **Source.** This is the Apple web color system documented in the previous `design.md`, retargeted from a website to a 16:9 slide deck. Interactive roles — link, CTA, focus ring — have no meaning in a printed deck, so Action Blue is repointed from "click me" to "this is the point." Three groups are **additions**, marked as such below: a status triad (the analyzed pages surfaced no status or validation states), two derived tints, and a dark-surface hairline. Everything else is the source system unchanged.

### Brand & Accent
- **Action Blue** (`{colors.primary}` — #0066cc): The single accent, and the only brand color in the system. Nothing on a slide is clickable, so Action Blue carries emphasis rather than interaction: the rail tick, `{component.metric-block}` figures, and the one active element per slide. No second brand color exists.
- **Focus Blue** (`{colors.primary-focus}` — #0071e3): A marginally brighter sibling. The source reserved it for keyboard focus rings; the deck has none, so it is repointed to the 1.5px stroke on an active diagram node — the one place a slightly hotter blue holds its edge against a tinted fill.
- **Sky Link Blue** (`{colors.primary-on-dark}` — #2997ff): The accent on dark grounds. Action Blue goes muddy against #272729 — always swap on the cover and section dividers.
- **Blue Wash** (`{colors.primary-wash}` — #ebf3fb) — *addition*: Action Blue at ~8% over white. The fill behind an active node, a highlighted table row, or a callout band. Fill only — never text, never a rule. The source defined no tinted state because its pages never needed one.

### Surface
- **Pure White** (`{colors.canvas}` — #ffffff): What content sits *in* — diagram fields, cards, screenshot mats, table bodies. White is a field color, not a page color.
- **Parchment** (`{colors.canvas-parchment}` — #f5f5f7): The default slide ground, and the fill of nodes and chips that sit inside a white field. The signature off-white — just different enough from white to separate two surfaces without a border.
- **Pearl** (`{colors.surface-pearl}` — #fafafc): A near-white band surface, lighter than parchment so a band still reads as a band against the ground. Used for `{component.metric-strip}` and `{component.evidence-rail}`.
- **Near-Black Tile 1** (`{colors.surface-tile-1}` — #272729): The dark ground. Section dividers only — the cover is parchment (§11). A deck without dividers never uses it.
- **Near-Black Tile 2** (`{colors.surface-tile-2}` — #2a2a2c): A micro-step lighter — card surface on a dark ground.
- **Near-Black Tile 3** (`{colors.surface-tile-3}` — #252527): A micro-step darker — embedded video and image frames on a dark slide.
- **Pure Black** (`{colors.surface-black}` — #000000): True void. In a deck it appears only as the mat behind a full-bleed video still and as the pupil of the §6 mark. Never a slide ground.
- **Translucent Chip Gray** (`{colors.surface-chip-translucent}` — #d2d2d7, applied at ~64% alpha as `rgba(210, 210, 215, 0.64)`): Chips and small controls laid over a photograph.

### Text
- **Near-Black Ink** (`{colors.ink}` — #1d1d1f): Every title, every body paragraph, every table figure on a light ground. Chosen instead of pure black to keep the page photographic rather than printed. The source's `{colors.body}` carries the same hex — one near-black tone for all text on light surfaces — so the deck folds the two into `{colors.ink}`.
- **Ink Muted 80** (`{colors.ink-muted-80}` — #333333): Subtitles, card body copy, secondary reads.
- **Ink Muted 48** (`{colors.ink-muted-48}` — #7a7a7a): Captions, footnotes, the page number, axis labels, and diagram arrows with their labels.
- **Body On Dark** (`{colors.body-on-dark}` — #ffffff): All text on a dark ground.
- **Body Muted** (`{colors.body-muted}` — #cccccc): Secondary copy on a dark ground, where pure white is too loud.

### Hairlines
- **Hairline** (`{colors.hairline}` — #e0e0e0): The 1px border on every field, card, node, and table — the deck's primary structural line.
- **Divider Soft** (`{colors.divider-soft}` — #f0f0f0): Dividers *inside* a card or field, where the hairline would read as a second frame.
- **Hairline On Dark** (`{colors.hairline-on-dark}` — #3a3a3c) — *addition*: the 1px line on a dark ground. The analyzed pages carried no bordered element on a dark tile.

### Status — addition, content only
The source surfaced no status or validation colors. The deck's 판정 content needs them, so they are taken from Apple's platform semantic palette using the accessible-on-white variants. They appear **only** inside status badges, chart series, and legend rows — never as a surface, never as decoration, never as a second accent.

- **Hazard** (`{colors.status-hazard}` — #d70015 / on dark #ff6961): 위험 판정, 가스 검출, failure counts.
- **Oxidizer** (`{colors.status-oxidizer}` — #b25000 / on dark #ffd426): 황색 산화성 고체 판정.
- **Clear** (`{colors.status-clear}` — #248a3d / on dark #30db5b): 정상 / 통과 / CLEAR, success counts.

### Diagrams & Charts
The source had no diagrams and therefore no diagram color. Rather than invent a second structural hue, the deck extends the source's own logic: **diagrams are monochrome, and the single blue marks the one active element.**

- Node: `{colors.canvas-parchment}` fill, 1px `{colors.hairline}` border, label in `{colors.ink}`, description in `{colors.ink-muted-80}`.
- Active node: `{colors.primary-wash}` fill, 1.5px `{colors.primary-focus}` border. One per slide.
- Arrows, connectors, and their labels: `{colors.ink-muted-48}`.
- Chart: base series `{colors.ink-muted-48}`; the one series the slide is arguing in `{colors.primary}`; axes and gridlines `{colors.hairline}`; axis labels `{colors.ink-muted-48}`. Status colors only when the series *is* a status (성공/실패, 검출/정상). No 3D, no shadows, no rounded bar caps.

### Gradients
**None.** The source defines zero gradient tokens, and the deck keeps it that way — it is the rare system with no gradient-based token at all. Depth comes from surface change and hairlines. The only permitted non-flat fill is the §9 photo scrim.

## 6. Brand Mark

### The only logo in the deck

The **HazardBot mark** is the sole logo permitted on any slide. Do **not** place a MiniMax mark, a slide-generator watermark, a template vendor badge, a "Made with…" credit, an AI-tool logo, or any stock brand mark anywhere in the deck — cover, footer, divider, or last page. If a generation tool inserts one, remove it before export.

Institutional or partner logos (school, lab, competition) are the one possible addition; if required they go on the cover only, bottom-aligned, at the same optical weight as the mark, separated by a 1px `{colors.hairline-on-dark}` vertical divider.

### The mark

Camera eye and arm face the same direction — *what it sees is what it reaches for*. The mark carries three roles:

- **Mechanism** — body, arm, elbow, wheels, beacon stem — a solid `{colors.ink}` #1d1d1f (on dark `{colors.body-on-dark}` #ffffff). One value for every structural part; the body is a filled mass, not an outline.
- **Accent** — eye, beacon, wrist, gripper — in `{colors.primary}` #0066cc (on dark `{colors.primary-on-dark}` #2997ff). The parts that actively respond to hazard, in the deck's own accent value.
- **Pupil** — `{colors.surface-black}` #000000 on both grounds, so the direction of gaze reads independently of the surface behind it.

**Every colour in the mark is a §5 token.** There is no mark-only colour, which is why the mark drops onto any slide surface unmodified. The mark's accent does not count against the one-free-emphasis rule in §13 — the footer mark is chrome, not slide content.

```html
<!-- on parchment (#f5f5f7) / white -->
<svg viewBox="0 0 100 100" role="img" aria-label="HazardBot">
  <line x1="47" y1="39" x2="47" y2="30" stroke="#1d1d1f" stroke-width="3.5" stroke-linecap="round"/>
  <circle cx="47" cy="28" r="3.4" fill="#0066cc"/>
  <path d="M 65 47 L 81 37" fill="none" stroke="#1d1d1f" stroke-width="5.5" stroke-linecap="round"/>
  <circle cx="81" cy="37" r="3.5" fill="#1d1d1f"/>
  <path d="M 81 37 L 88 51" fill="none" stroke="#1d1d1f" stroke-width="5.5" stroke-linecap="round"/>
  <circle cx="88" cy="51" r="4.2" fill="#0066cc"/>
  <path d="M 88 51 L 95 45" fill="none" stroke="#0066cc" stroke-width="4" stroke-linecap="round"/>
  <path d="M 88 51 L 94 58" fill="none" stroke="#0066cc" stroke-width="4" stroke-linecap="round"/>
  <circle cx="38" cy="74" r="6.5" fill="#1d1d1f"/>
  <circle cx="56" cy="74" r="6.5" fill="#1d1d1f"/>
  <rect x="27" y="39" width="40" height="33" rx="14" fill="#1d1d1f"
        stroke="#1d1d1f" stroke-width="2.5"/>
  <circle cx="50" cy="55" r="9" fill="#0066cc"/>
  <circle cx="53" cy="53" r="2.2" fill="#000000"/>
</svg>
```

**On dark ground (#272729):** swap `#1d1d1f → #ffffff` and `#0066cc → #2997ff`; the pupil stays `#000000`. Nothing else changes. Define both as `<symbol>` blocks once and `<use>` them.

### Wordmark

Set **`HazardBot` in Pretendard Bold 700, tracking -0.02em**, in `{colors.ink}` (or `{colors.body-on-dark}`). The mark artifact's Big Shoulders wordmark is not used in this deck — §4 admits one face only.

### Lockups & placement

| Context | Mark size | Lockup |
|---|---|---|
| Cover | 132px | Horizontal: mark + 32px gap + wordmark at 60px / 700, tagline beneath at `{typography.label}` |
| Section divider | 40px | Mark only, top-right of the body region |
| Content slide footer | 18px | Mark + 8px gap + `HazardBot 개발완료보고서` at `{typography.footer}` |
| Minimum | 16px | Below this the gripper joints collapse — never go smaller |

- **Clear space:** half the mark's width on all four sides. Nothing enters it, including the footer text baseline box.
- Never recolor outside the two approved variants, never outline it, never rotate it, never place it on a photograph without the §9 scrim, never stretch it non-uniformly, never re-draw it in a different stroke weight.

## 7. Layout & Grid

### Grid

The body region (1152 × 488) is a **12-column grid**: column 74px, gutter 24px. Span math: `width = 98n − 24`.

| Span | Width | Typical use |
|---|---|---|
| 3 | 270px | Quarter card |
| 4 | 368px | Third card · side rail |
| 6 | 564px | Half |
| 8 | 760px | Primary field (diagram, screenshot) |
| 12 | 1152px | Full-width band |

Vertical rhythm inside the body is an **8px baseline**; row gap is always 24px.

### Spacing tokens

`{spacing.xxs}` 4 · `{spacing.xs}` 8 · `{spacing.sm}` 12 · `{spacing.md}` 16 · `{spacing.lg}` 24 · `{spacing.xl}` 32 · `{spacing.xxl}` 48

- **Card inner padding:** `{spacing.lg}` (24px). Never below 16px, never above 32px.
- **Gutter and row gap:** `{spacing.lg}` (24px), everywhere, always.
- **Label → content:** `{spacing.sm}` (12px). **Card title → body:** `{spacing.md}` (16px).
- **List item spacing:** `{spacing.sm}` (12px) between items; bullets are 5×5px `{colors.primary}` squares at 8px gap, vertically centered on the first line's x-height — not round dots, not typographic bullets.

### Alignment discipline

Everything in the body region aligns to the grid's column edges. If a field's left edge does not land on a column edge (64, 162, 260, 358, 456, 554, 652, 750, 848, 946, 1044, 1142 in slide coordinates), it is misplaced. Optical centering is allowed only inside a field, never for the field itself.

## 8. Density — Fill the Body

The body region is 1152 × 488. A three-bullet slide floating in the top 120px of it, with 368px of paper below, is the single most common defect in a deck like this — and the one this section exists to prevent.

### The fill rule

> **The bottom edge of the lowest element in the body must land between y = 640 and y = 664.**

That is: fill at least ~95% of the body's height, and never overflow it. This is checkable — measure it on every slide before export.

### How to fill — in this order

1. **Stretch the rows you have.** Cards in a row are `align-items: stretch` and fill the row's full height; they do not hug their content. A 2-card row on a 488px body means two 488px-tall cards, not two 180px cards pinned to the top.
2. **Add a bottom-pinned band.** The two standard fillers, both sized to land exactly on y = 664:
   - `{component.metric-strip}` — 1152 × 96, three or four key figures with labels. Use when the slide has numbers worth restating.
   - `{component.evidence-rail}` — 1152 × 144, three or four short evidence/source items in `{typography.footnote}` on a `{colors.canvas}` band. Use when the slide has claims worth grounding (file paths, verification counts, doc references).
3. **Promote a supporting visual.** A small diagram, a status legend, a captioned thumbnail strip — content that was going to be spoken anyway.
4. **Split the field.** A wide diagram plus a side rail (`L5`) is denser and more informative than the same diagram alone.

### How *not* to fill

- Do not scale type up to consume space. The §4 table is fixed.
- Do not vertically center a short block in the body. Content starts at the body top and grows down.
- Do not add decorative shapes, oversized icons, background patterns, watermark logos, or stock imagery as filler.
- Do not stretch a diagram beyond its natural proportions to reach the bottom edge — pair it with a rail instead.
- Do not pad a list to eight items when it has four. Add a *different kind* of block, not more of the same.

### The density ceiling

Dense is not crowded. These caps hold in every case:

- At least **35% of the body area stays quiet** — ground or field background with no ink on it.
- At most **5 top-level blocks** in the body region.
- No card smaller than **200 × 96**.
- At most **7 list items** per column, at most **9 rows** per table.
- Every field keeps its full inner padding — density comes from *more content blocks*, never from tighter margins.

## 9. Elevation & Depth

| Level | Treatment | Use |
|---|---|---|
| Flat | No border, no shadow | Slide ground, section bands, dark dividers |
| Hairline | 1px `{colors.hairline}` | Fields, cards, tables, diagram canvases |
| Surface step | `{colors.canvas}` fill on `{colors.canvas-parchment}` | Cards, metric strips, evidence rails |
| Inset field | `{colors.canvas}` fill + 1px `{colors.hairline}` | Diagram canvases, screenshot mats, table bodies |
| Photo shadow | `rgba(0, 0, 0, 0.22) 3px 5px 30px 0` | Photographs and hardware shots only — the source system's one shadow, unchanged |

**Shadow philosophy.** Exactly one shadow exists, and it applies only to photographic content — hardware shots, the arm, the demo space. Never on cards, never on text, never on diagram nodes, never on the mark. Elevation in the deck comes from surface steps and hairlines.

**Photo scrim.** The one non-flat fill in the system: when the header block or the mark must sit over a photograph, lay `linear-gradient(180deg, rgba(0,0,0,0.72) 0%, rgba(0,0,0,0.12) 62%)` over the top 240px of the image. It is a legibility device, not decoration — never use it where nothing sits on top of it.

## 10. Shapes

| Token | Value | Use |
|---|---|---|
| `{rounded.none}` | 0 | Slide ground, full-bleed bands, table cells, chart bars |
| `{rounded.xs}` | 3px | Status badges, code chips, bullet squares |
| `{rounded.sm}` | 6px | Cards, fields, screenshot mats, diagram nodes |
| `{rounded.md}` | 10px | The single hero field on an `L1` slide |
| `{rounded.full}` | 50% | Step numerals in a flow, legend dots |

Two radii grammars only: **6px for anything rectangular that holds content**, **3px for small chips**. Nothing in between, and no pill shapes — pills read as buttons, and there is nothing to click in a deck.

### Imagery geometry

- Screenshots (dashboard captures) sit in a `{component.image-mat}`: white mat, 1px `{colors.hairline}`, `{rounded.sm}`, 12px inner padding, `{typography.caption}` beneath.
- Hardware photographs are cropped to 16:9 or 4:3, `{rounded.sm}`, and carry the photo shadow.
- Never crop a photograph into a circle, a hexagon, or a blob. Never apply a color overlay other than the scrim.
- Every image carries a caption in `{typography.caption}`, `{colors.ink-muted-80}`, left-aligned to the image's left edge.

## 11. Components

### Frame

**`header-rail`** — `{frame.rail}`. A 6×6px `{colors.primary}` square + 6px gap + chapter string in `{typography.rail}`, `{colors.ink-muted-80}`. On dark: `{colors.primary-on-dark}` + `{colors.body-muted}`.

**`slide-title`** — `{frame.title}`. `{typography.title}`, `{colors.ink}`. One line. On dark: `{colors.body-on-dark}`.

**`slide-subtitle`** — `{frame.subtitle}`. `{typography.subtitle}`, `{colors.ink-muted-80}`. One line, or empty with the height reserved.

**`footer-bar`** — `{frame.footer}`. Left: 18px mark + 8px gap + deck name in `{typography.footer}`, `{colors.ink-muted-48}`. Right: `07 / 20` in `{typography.footer}`, `{colors.ink-muted-48}`, `tnum`. Never anything else.

### Content blocks

**`card`** — `{colors.canvas}` fill, 1px `{colors.hairline}` border, `{rounded.sm}`, padding `{spacing.lg}`. Optional `{typography.label}` eyebrow in `{colors.ink-muted-80}`, then `{typography.card-title}`, then `{typography.body}` or `{typography.body-dense}`. Stretches to its row height.

**`card-outlined`** — `{colors.canvas}` fill, 1px `{colors.hairline}`, `{rounded.sm}`, padding `{spacing.lg}`. Use when cards sit next to a white field and the `{colors.canvas}` fill would read as a third surface.

**`card-accent`** — `{component.card}` with a 3px `{colors.primary}` bar on its left edge and `{colors.primary-wash}` fill. **One per slide, maximum** — it marks the single most important block.

**`card-numbered`** — `{component.card}` with a 28px `{rounded.full}` numeral in `{colors.ink-muted-48}` / `{colors.body-on-dark}` at the top-left, then title and body. For ordered sequences (pipeline steps, procedure stages).

**`metric-block`** — `{typography.label}` eyebrow → `{typography.metric}` figure in `{colors.primary}` (`tnum`) → `{typography.metric-sub}` label in `{colors.ink}` → optional `{typography.caption}` qualifier in `{colors.ink-muted-80}`. The qualifier line is where "근거리 100% / 원거리 66.7%" goes — a bare 86.7% with no qualifier is a misleading slide.

**`metric-strip`** — `{colors.surface-pearl}` fill, `{rounded.sm}`, padding `{spacing.lg}`, three or four `{component.metric-block}`s in equal columns separated by 1px `{colors.divider-soft}` vertical dividers. Two heights, because a 44px figure plus a label plus a qualifier line does not fit in 96px:

- **compact — 1152 × 96** (`y = 568…664`): label + figure only. The qualifier moves into the slide body. Pairs with `L7`.
- **full — 1152 × 144** (`y = 520…664`): label + figure + `{typography.metric-sub}` qualifier. Use whenever a figure needs its conditions stated beside it — which is most figures in this deck. Pairs with `L8`.

**`evidence-rail`** — 1152 × 144, `{colors.surface-pearl}` fill, `{rounded.sm}`, padding `{spacing.lg}`. A `{typography.label}` heading, then three or four items in `{typography.footnote}`, `{colors.ink-muted-80}`, separated by 1px `{colors.divider-soft}` verticals. Holds source files, verification counts, doc references. Pinned to the body bottom (`y = 520…664`).

**`diagram-field`** — `{colors.canvas}` fill, 1px `{colors.hairline}`, `{rounded.sm}`, inner padding `{spacing.xl}`. The container for every node graph, flow chart, power tree, and architecture diagram. Nodes: `{colors.canvas-parchment}` fill, 1.5px `{colors.ink-muted-48}` stroke, `{rounded.sm}`, label in `{typography.body-dense}` 600. The *active* node in the story: `{colors.primary-wash}` fill, 1.5px `{colors.primary-focus}` stroke. One per slide. Arrows: 1.5px `{colors.ink-muted-48}` with a 7px solid arrowhead; labels in `{typography.caption}`, `{colors.ink-muted-80}`.

**`flow-step`** — A horizontal sequence inside a `{component.diagram-field}`: numbered `{rounded.full}` marker, step title in `{typography.body-dense}` 600, one-line description in `{typography.caption}`. Steps connected by a 1.5px `{colors.ink-muted-48}` line with arrowheads. The decision branch (색상 판정) forks vertically with the branch condition on the line in `{typography.caption}`.

**`status-badge`** — Inline pill-free chip: `{rounded.xs}`, 4px × 10px padding, `{typography.label}`, on a 14%-tint fill of its status color with the text in the full status color. Three variants: `-hazard`, `-oxidizer`, `-clear`. Only these three exist.

**`code-chip`** — For ROS2 topics, node names, file paths, and constants (`/hazard/detected`, `arm_act_node`, `GAS_CHECK_TIMEOUT_S`). Pretendard `{typography.chip}` with `tnum`, `{colors.ink}`, `{colors.canvas}` fill, `{rounded.xs}`, 2px × 7px padding. There is no monospace font in this deck — the chip's fill and tight tracking do the work a mono face would.

**`callout`** — Full body width, `{colors.primary-wash}` fill, 3px `{colors.primary}` left bar, `{rounded.sm}`, padding `{spacing.lg}`. `{typography.body}`. For a single quoted judgment string (`황색 산화성 고체 감지 — 취급구역 내 위치 자체가 위반`) or one conclusion sentence. One per slide.

**`table-spec`** — `{colors.canvas}` body, 1px `{colors.hairline}` outer, `{rounded.sm}`. Header row: `{typography.label}`, `{colors.ink-muted-80}`, `{colors.canvas}` fill, 1px `{colors.hairline}` bottom. Data rows: `{typography.body-dense}`, 1px `{colors.divider-soft}` separators, 14px vertical / 16px horizontal cell padding. Numeric columns right-aligned with `tnum`. No zebra striping, no vertical rules.

**`image-mat`** — See §10. White mat + hairline + caption.

**`legend-row`** — Horizontal run of `{typography.caption}` items, each preceded by a 10px `{rounded.full}` swatch, 20px apart. Sits directly beneath its chart or diagram, left-aligned to it.

**`bar-row`** — The deck's only chart form. A horizontal comparison bar, used when two to four categories are compared on one scale (성공률, 구간 비중). Vertical bars are not used: category names in Korean do not fit under a 100px column without rotating type, and §4 forbids rotated Hangul.

Each row is a fixed height with three zones — name at the left (`{typography.body-dense}` 600, with the raw count beneath in `{typography.footnote}` / `{colors.ink-muted-48}`), the bar in the middle, the value right-aligned at 19px/700 `{colors.ink}` with `tnum`. The bar sits in a full-width **track** of `{colors.divider-soft}` so an incomplete bar reads as a share of the whole rather than a floating rectangle; the fill is `{colors.primary}` for the one series the slide is arguing and `{colors.ink-muted-48}` for the rest. Square caps, `{rounded.none}`, no axis, no gridlines — the track *is* the axis. A summary row may follow below a 1px `{colors.divider-soft}` rule, with its figure in `{colors.primary}`.

Status colors replace the two neutrals only when the series *is* a status (성공/실패, 검출/정상). Never more than four rows; past that the comparison belongs in a `{component.table-spec}`.

**`bullet-list`** — `{typography.body}` items, 12px apart, 5×5px `{colors.primary}` square marker at 8px gap. Sub-items indent 20px with a 5×1px `{colors.ink-muted-48}` dash marker. Two levels maximum.

### Slide types

**`slide-cover`** — Full-bleed `{colors.canvas-parchment}` — **the same ground as every content slide.** The 132px mark + wordmark lockup at x=96, vertically centered slightly above the midline; `{typography.deck-subtitle}` one-line summary beneath in `{colors.ink-muted-80}`; a 1px `{colors.hairline}` rule; then team, names, and date in `{typography.label}` / `{colors.ink-muted-48}`, matching the footer's ink on every other page. The mark and wordmark use the on-light variant (§6): `{colors.ink}` mechanism, `{colors.primary}` accent and tagline. No rail, no page number, no footer. The only slide that breaks the frame entirely.

The cover is paper, not a dark plate. A near-black title card followed by nineteen parchment slides announces a different document than the one that follows; holding one ground from the first page makes the deck read as a single report and lets the mark, not a surface change, carry the opening. The dark treatment is available as a variant if a deck ever needs a title plate — but it is not the default, and a deck must not use both.

**`slide-divider`** — `{colors.surface-tile-1}`, frame coordinates unchanged. Rail, title (the chapter name), and subtitle in their dark-ground inks. Body region: `{typography.section-numeral}` chapter numeral in `{colors.primary-on-dark}` at the left, and at the right a list of that chapter's slide titles in `{typography.body-dense}`, `{colors.body-muted}`, with their page numbers — which is also what keeps the divider's body filled. 40px mark top-right.

**`slide-agenda`** — Paper ground. Two forms, chosen by chapter count:

- **Three chapters** — `L3`: three `{component.card}`s, each a chapter with its numeral, name, and the slides it contains in `{typography.body-dense}`.
- **Four to six chapters** — `L1`: one full-body `{component.diagram-field}` holding one **chapter row** per chapter, split by 1px `{colors.divider-soft}` rules. Row: 26px/700 numeral in `{colors.ink-muted-48}` at the left, chapter name in `{typography.card-title}`, its slide titles beneath in `{typography.body-dense}` / `{colors.ink-muted-80}`, and the page range right-aligned in 13px/600 `{colors.ink-muted-48}` with `tnum`. Rows divide the field's inner height equally. Cards do not scale past three — four 270px cards cannot hold six slide titles without dropping below the §4 minimum.

**`slide-full-bleed`** — Body region only goes edge to edge (the frame stays). Photograph or dashboard capture at 1280 × 488 positioned at y=176, with the §9 scrim under the header block if the image reaches it.

## 12. Body Layout Presets

Every content slide uses one of these. All dimensions are inside the 1152 × 488 body region; gap is always 24px.

| Preset | Composition | Fits |
|---|---|---|
| `L1 · full` | 1152 × 488 | One large diagram, one full-bleed capture, one big table |
| `L2 · halves` | 564 + 564 | Two parallel ideas; before/after; text ↔ image |
| `L3 · thirds` | 368 × 3 | Three components, three phases, three roles |
| `L4 · quarters` | 270 × 4 | Four hardware units, four limitations |
| `L5 · 8+4` | 760 + 368 | Diagram (left) + notes rail (right) — the workhorse |
| `L6 · 4+8` | 368 + 760 | List (left) + diagram or capture (right) |
| `L7 · stage + strip` | 1152 × 368 over 1152 × 96 | Any visual that needs its numbers restated beneath |
| `L8 · stage + band` | 1152 × 320 over 1152 × 144 | Any claim that needs evidence beneath — band is an `{component.evidence-rail}` or a full `{component.metric-strip}` |
| `L9 · 2×2` | 564 × 232, four cells | Four paired items; a comparison matrix |
| `L10 · 2×3` | 368 × 232, six cells | Six topics, six nodes, six team responsibilities |
| `L11 · flow + detail` | 1152 × 200 flow over 1152 × 264 | A pipeline plus its per-step detail |

Suggested assignment for this deck (adjust as content settles): cover → `slide-cover`; 목차 → `slide-agenda`; 배경/목표 → `L6`, `L2`; 시스템 개요 → `L5`; 하드웨어 구성 → `L4`; 소프트웨어 아키텍처 → `L5`; 판정 로직 → `L11`; GAS_CHECK → `L11`; ACT 학습/동작 → `L6`, `L7`; 통합 파이프라인 → `L11`; 대시보드 → `L3` of `image-mat`s; 전력 계통 → `L5`; 제어 경로 → `L7`; 검증 결과 → `L7`; 영상 안내 → `L1` + `metric-strip`; 한계·계획 → `L9`; 팀 구성 → `L3`; 결론 → `L8`.

## 13. Do's and Don'ts

### Do

- Keep the rail, title, subtitle, rule, and footer at their `{frame.*}` coordinates on every single slide. This is the deck's spine.
- Set everything in Pretendard, in 300 / 400 / 600 / 700 only.
- Use `{colors.primary}` for its three specced roles and nothing else: the rail tick, the `{component.metric-block}` figures, and **one** free emphasis that marks what the slide is about (an active node, a `{component.card-accent}`, or a `{component.callout}`). One free emphasis per slide, never two.
- Use `{colors.ink-muted-48}` for every diagram, arrow, and hardware block, so mechanism reads the same way on every page.
- Fill the body to y = 640–664 using a `{component.metric-strip}` or `{component.evidence-rail}` when the primary content stops short.
- Put every diagram and screenshot inside a white field with a 1px hairline — content sits *in* a field, on paper.
- Set `word-break: keep-all` on all Korean copy and `tnum` on every figure.
- Qualify every headline number where the qualification matters (86.7% carries 30회 / 근거리 100% / 원거리 66.7%).
- Use `{component.code-chip}` for topic, node, and file names instead of reaching for a monospace face.

### Don't

- Don't move, resize, or drop the header block on any slide. A slide whose title sits at a different height than the previous one is broken, however good it looks alone.
- Don't use any font but Pretendard — not for a numeral, not for a code identifier, not for the wordmark, not as a fallback.
- Don't use `font-style: italic`; Pretendard has no italic and the synthesized oblique wrecks Hangul.
- Don't place a MiniMax logo, a generator watermark, a tool badge, or any third-party mark anywhere in the deck.
- Don't leave the lower third of the body empty, and don't fix it by enlarging type or adding decorative shapes.
- Don't introduce a second accent color; don't promote a status color to a decorative or surface role.
- Don't use gradients, glows, 3D, bevels, or drop shadows on anything but a photograph.
- Don't use white as a full-slide background — white is a field color, paper is the page.
- Don't use pill radii; there is nothing clickable on a slide.
- Don't justify Korean text, don't letterspace Hangul body copy, and don't run body lines past ~45 Korean characters.
- Don't let content overflow the body region or cross the safe margins. Split the slide instead.
- Don't use `{colors.primary}` (#0066cc) on a dark tile or `{colors.primary-on-dark}` (#2997ff) on parchment — each is the wrong value on the other surface.

## 14. Iteration Guide

1. Work one slide, or one component, at a time. Reference its token key directly (`{component.metric-strip}`, `{frame.body}`, `L5`).
2. Before touching visuals, check the frame: are rail / title / subtitle / rule / footer at their exact coordinates?
3. Then check density: where does the lowest element's bottom edge land? If it's above y = 640, apply §8 in order.
4. Then check color: setting aside the rail tick and the metric figures, how many things are accent-colored? More than one free emphasis means picking the real one.
5. Variants of a component (`-accent`, `-outlined`, `-numbered`, `-hazard`) are separate entries in §11 — don't invent an undocumented variant, add one here first.
6. There are no hover, focus, or transition states — this is a printed artifact. Never document or build them.
7. When a slide feels wrong, change the layout preset before changing the type or the color. It's almost always the preset.

## 15. Known Gaps

- **Photography direction is unspecified.** The deck's hardware shots, arm wide-shots, and demo-space images come from `사진/` and `영상/`; this system defines how they're framed (§10) but not which frames to choose.
- **Chart specifics beyond the bar row.** Single-scale comparison is settled — see `{component.bar-row}` in §11. Anything beyond it (grouped bars, distributions, time series, a real axis) has no styling yet and needs a decision recorded here first. The 5-segment proportional strip on the 시연 영상 slide is a `{component.bar-row}` track split by content, not a second chart type.
- **Appendix slides.** If the deck grows past 20 pages, the footer's `/ 20` denominator and the divider slide lists both need updating; no appendix-specific frame variant is defined.
- **Print color.** Values are specified for screen and projection. In print, `{colors.canvas-parchment}` (#f5f5f7), `{colors.surface-pearl}` (#fafafc) and `{colors.canvas}` (#ffffff) sit within three points of each other and will collapse on uncoated stock — the whole light surface system becomes one flat white. For a print run, carry the structure on `{colors.hairline}` borders alone and drop the surface steps.
- **Pretendard `.woff2` subsets** are not yet built. The Artifact path in §4 requires them; the local print path does not.
