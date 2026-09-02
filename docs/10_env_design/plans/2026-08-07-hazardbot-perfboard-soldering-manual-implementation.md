# HazardBot Perfboard Soldering Manual Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a visually verified Korean A4 PDF that teaches a complete beginner how to solder the HazardBot sensor and drive perfboards one action at a time.

**Architecture:** Store the approved Korean copy and wiring nets as validated Python data, render reusable vector diagrams with ReportLab, and assemble the manual with a dedicated PDF builder. Verify the generated PDF structurally with Python and visually by rendering every page to PNG before delivery.

**Tech Stack:** Python 3, ReportLab, pypdf, pdfplumber, Poppler PDF rendering, `unittest`, PowerShell

## Global Constraints

- Output one printable A4 PDF containing clearly separated sensor-board and drive-board sections.
- Write for a reader with no soldering experience and a reading level suitable for a 12-year-old.
- Explain each physical action separately: setup, hand/tool position, action, correct result, common mistake, and checkpoint.
- Use exact wiring from `docs/superpowers/specs/2026-08-07-hazardbot-perfboard-soldering-manual-design.md`.
- Use two single-sided 100×100mm, 2.54mm perfboards and four 20-pin female headers trimmed to 19 pins.
- Use existing resistors and jumper wires; do not make additional purchases mandatory.
- Use the four female headers only for the two 38-pin ESP32 boards.
- Keep TB6612FNG VM, power GND, A01/A02, and B01/B02 outside the thin logic rails and preserve the already-tested direct wiring.
- Mark hot-iron, power-on, and motor-power work as requiring teacher or adult supervision.
- Use both color and repeated net labels so the guide remains usable when actual jumper colors differ.
- Render and inspect every PDF page before claiming completion.

## File Structure

- Create `tools/soldering_manual/content.py`: approved Korean copy, wiring nets, page-section definitions, and consistency validation.
- Create `tools/soldering_manual/diagrams.py`: reusable ReportLab vector diagrams for board faces, holder orientation, solder joints, rails, dividers, and power boundaries.
- Create `tools/soldering_manual/build_manual.py`: A4 layout, typography, page headers/footers, tables, callouts, and final PDF assembly.
- Create `tests/soldering_manual/test_manual.py`: pin-map, required-section, diagram-registry, PDF page-count, and text-extraction checks.
- Create `docs/guides/HazardBot_만능기판_납땜_설명서.pdf`: final user-facing PDF.
- Create `tmp/soldering-manual-render/`: rendered PNG pages and contact sheet used only for visual QA.

---

### Task 1: Lock the Manual Content and Wiring Nets

**Files:**
- Create: `tools/soldering_manual/content.py`
- Create: `tests/soldering_manual/test_manual.py`
- Reference: `docs/superpowers/specs/2026-08-07-hazardbot-perfboard-soldering-manual-design.md`
- Reference: `docs/중요/README.md`

**Interfaces:**
- Produces: `MANUAL_TITLE: str`, `SECTIONS: tuple[dict, ...]`, `SENSOR_NETS: tuple[tuple[str, str], ...]`, `DRIVE_NETS: tuple[tuple[str, str], ...]`, `COLOR_LEGEND: dict[str, str]`, and `validate_content() -> None`.
- Consumes: no generated files.

- [ ] **Step 1: Write failing content tests**

Create `tests/soldering_manual/test_manual.py` with exact assertions for the approved wiring and required sections:

```python
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.soldering_manual import content


class ManualContentTests(unittest.TestCase):
    def test_sensor_nets_match_v10_wiring(self):
        self.assertIn(("MQ-135 AO", "10kΩ → GPIO34 중점; 20kΩ → GND"), content.SENSOR_NETS)
        self.assertIn(("MQ-2 AO", "10kΩ → GPIO35 중점; 20kΩ → GND"), content.SENSOR_NETS)
        self.assertIn(("KY-026 DO", "GPIO27"), content.SENSOR_NETS)
        self.assertIn(("VL53L1X SDA/SCL", "GPIO21/GPIO22"), content.SENSOR_NETS)

    def test_drive_nets_match_confirmed_wiring(self):
        required = {
            ("PWMA", "GPIO25"), ("AIN1/AIN2", "GPIO26/GPIO27"),
            ("PWMB", "GPIO14"), ("BIN1/BIN2", "GPIO16/GPIO17"),
            ("STBY", "GPIO4"), ("S1/S2/S3/S4/S5", "GPIO13/18/19/23/32"),
        }
        self.assertTrue(required.issubset(set(content.DRIVE_NETS)))

    def test_manual_has_separate_board_sections_and_checklist(self):
        ids = {section["id"] for section in content.SECTIONS}
        self.assertTrue({"basics", "sensor_board", "drive_board", "final_check"}.issubset(ids))

    def test_content_validation_passes(self):
        content.validate_content()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test and confirm the expected failure**

Run:

```powershell
C:\Users\rkdgm\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe tests\soldering_manual\test_manual.py
```

Expected: `ModuleNotFoundError: No module named 'tools.soldering_manual'`.

- [ ] **Step 3: Implement the approved content model**

Create `tools/soldering_manual/content.py` with immutable tuples and a validation function. Include all approved sections and use these exact core nets:

```python
MANUAL_TITLE = "HazardBot 만능기판 납땜 설명서"

SENSOR_NETS = (
    ("5V 레일", "ESP32 5V/VIN → MQ-135 VCC, MQ-2 VCC"),
    ("3.3V 레일", "ESP32 3V3 → KY-026 VCC, VL53L1X VIN"),
    ("GND 레일", "ESP32 GND → 센서 4개 GND, 두 20kΩ 저항"),
    ("MQ-135 AO", "10kΩ → GPIO34 중점; 20kΩ → GND"),
    ("MQ-2 AO", "10kΩ → GPIO35 중점; 20kΩ → GND"),
    ("KY-026 DO", "GPIO27"),
    ("VL53L1X SDA/SCL", "GPIO21/GPIO22"),
)

DRIVE_NETS = (
    ("PWMA", "GPIO25"),
    ("AIN1/AIN2", "GPIO26/GPIO27"),
    ("PWMB", "GPIO14"),
    ("BIN1/BIN2", "GPIO16/GPIO17"),
    ("STBY", "GPIO4"),
    ("TB6612 VCC/logic GND", "ESP32 3V3/GND"),
    ("S1/S2/S3/S4/S5", "GPIO13/18/19/23/32"),
    ("라인센서 VCC/GND", "ESP32 3V3/GND"),
)
```

`validate_content()` must reject duplicate section IDs, missing required section IDs, duplicate left-hand net names, and any text that routes `VM`, `A01`, `A02`, `B01`, or `B02` through a logic rail.

- [ ] **Step 4: Run the content tests**

Run the same command as Step 2.

Expected: four tests pass and exit code is `0`.

- [ ] **Step 5: Commit the validated content**

```powershell
git add tools\soldering_manual\content.py tests\soldering_manual\test_manual.py
git commit -m "Add soldering manual content model"
```

---

### Task 2: Build Reusable Beginner-Friendly Diagrams

**Files:**
- Create: `tools/soldering_manual/diagrams.py`
- Modify: `tests/soldering_manual/test_manual.py`

**Interfaces:**
- Consumes: `COLOR_LEGEND` from `tools.soldering_manual.content`.
- Produces: `DIAGRAMS: dict[str, Callable[[], Drawing]]` and `get_diagram(name: str) -> Drawing`.
- Required diagram names: `board_faces`, `holder_position`, `iron_contact`, `good_bad_joints`, `header_cut`, `header_alignment`, `rail_cross_section`, `sensor_top`, `sensor_bottom`, `mq_dividers`, `drive_top`, `drive_bottom`, `motor_power_boundary`, `power_on_sequence`.

- [ ] **Step 1: Add failing diagram-registry tests**

Append to `tests/soldering_manual/test_manual.py`:

```python
from tools.soldering_manual import diagrams


class ManualDiagramTests(unittest.TestCase):
    def test_all_required_diagrams_exist_and_have_size(self):
        required = {
            "board_faces", "holder_position", "iron_contact", "good_bad_joints",
            "header_cut", "header_alignment", "rail_cross_section", "sensor_top",
            "sensor_bottom", "mq_dividers", "drive_top", "drive_bottom",
            "motor_power_boundary", "power_on_sequence",
        }
        self.assertEqual(required, set(diagrams.DIAGRAMS))
        for name in required:
            drawing = diagrams.get_diagram(name)
            self.assertGreaterEqual(drawing.width, 240)
            self.assertGreaterEqual(drawing.height, 120)
```

- [ ] **Step 2: Run tests and verify the diagram import fails**

Run:

```powershell
C:\Users\rkdgm\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe tests\soldering_manual\test_manual.py
```

Expected: import failure for `tools.soldering_manual.diagrams`.

- [ ] **Step 3: Implement diagram primitives**

Create `tools/soldering_manual/diagrams.py` using `reportlab.graphics.shapes.Drawing`, `Rect`, `Circle`, `Line`, `String`, `Polygon`, and `Path`. Define helpers with these signatures:

```python
def label(drawing, x, y, text, *, size=10, color=None, anchor="start") -> None: ...
def perfboard(drawing, x, y, width, height, *, copper_side=False) -> None: ...
def pad(drawing, x, y, *, soldered=False) -> None: ...
def wire(drawing, points, *, color, width=4, dashed=False) -> None: ...
def warning_mark(drawing, x, y, text) -> None: ...
def get_diagram(name: str): ...
```

Every diagram must label views as `부품면` or `납땜면`, show the bottom view horizontally mirrored where appropriate, and pair every colored wire with a text net label.

- [ ] **Step 4: Implement the fourteen diagrams**

Build diagrams that explicitly show:

- Board holder gripping only the perfboard edge, with the copper side facing upward for soldering.
- Iron tip touching both the copper pad and metal lead before solder is added.
- Correct volcano-shaped joint versus insufficient, oversized, cold, and bridged joints.
- The twentieth female-header socket being sacrificed while nineteen remain intact.
- ESP32 used only as an alignment jig while two header corner pins are tacked.
- Sensor pigtail entering from the component side while a bare tinned rail lies across the copper pads.
- Separate 5V, 3.3V, and GND rails with at least two empty pad rows between them.
- Both 10kΩ/20kΩ MQ dividers with GPIO34 and GPIO35 at their midpoints.
- Drive logic rails separate from the external motor-power path.

- [ ] **Step 5: Run diagram tests**

Run the full test script.

Expected: content and diagram tests pass.

- [ ] **Step 6: Commit the diagram library**

```powershell
git add tools\soldering_manual\diagrams.py tests\soldering_manual\test_manual.py
git commit -m "Add soldering manual diagrams"
```

---

### Task 3: Assemble the A4 PDF

**Files:**
- Create: `tools/soldering_manual/build_manual.py`
- Modify: `tests/soldering_manual/test_manual.py`
- Create: `docs/guides/HazardBot_만능기판_납땜_설명서.pdf`

**Interfaces:**
- Consumes: `content.SECTIONS`, `content.SENSOR_NETS`, `content.DRIVE_NETS`, and `diagrams.get_diagram()`.
- Produces: `build_manual(output_path: Path) -> Path` and a valid A4 PDF.

- [ ] **Step 1: Add a failing PDF smoke test**

Append a test that builds into a temporary directory, reads the output with `pypdf.PdfReader`, and checks the title, section text, and page count:

```python
import tempfile
from pypdf import PdfReader
from tools.soldering_manual.build_manual import build_manual


class ManualPdfTests(unittest.TestCase):
    def test_pdf_contains_both_boards_and_checklist(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "manual.pdf"
            build_manual(output)
            reader = PdfReader(str(output))
            self.assertGreaterEqual(len(reader.pages), 18)
            self.assertLessEqual(len(reader.pages), 26)
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            for phrase in ("센서용 기판", "주행용 기판", "GPIO34", "GPIO25", "통전 전 검사"):
                self.assertIn(phrase, text)
```

- [ ] **Step 2: Run tests and verify the builder import fails**

Run the full test script.

Expected: import failure for `tools.soldering_manual.build_manual`.

- [ ] **Step 3: Implement typography and page components**

Use A4 pages, 15mm margins, page numbers, and Korean fonts. Register `C:\Windows\Fonts\malgun.ttf` and `C:\Windows\Fonts\malgunbd.ttf`; fail with a clear message if either file is absent. Implement:

```python
def register_fonts() -> tuple[str, str]: ...
def build_styles() -> dict[str, ParagraphStyle]: ...
def step_block(number: int, title: str, body: str, diagram_name: str): ...
def warning_box(text: str): ...
def checkpoint(items: tuple[str, ...]): ...
def build_manual(output_path: Path) -> Path: ...
```

Do not place Korean text inside raster images; keep labels as vector text or PDF text for readability.

- [ ] **Step 4: Assemble the approved 18–22 page structure**

Build these page groups in order:

1. Cover and finished-board overview.
2. Safety, tools, board faces, and holder setup.
3. Four-step practice joint and good/bad comparison.
4. Header cutting, alignment, tack soldering, and full soldering.
5. Sensor-board placement, pigtail preparation, and three power rails.
6. Rail soldering sequence split into separate actions.
7. MQ dividers and all sensor signal wires.
8. Sensor-board inspection and V10 bring-up.
9. Drive-board placement, logic rail, TB6612 controls, and line sensor.
10. Motor-power boundary and wheel-off-ground bring-up.
11. Final inspection flow and one-page field checklist.

Use `PageBreak` deliberately so sensor and drive sections start on new pages.

- [ ] **Step 5: Run all automated tests**

Run:

```powershell
C:\Users\rkdgm\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe tests\soldering_manual\test_manual.py
```

Expected: all tests pass and the temporary PDF has 18–26 pages.

- [ ] **Step 6: Build the final PDF**

Run:

```powershell
C:\Users\rkdgm\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe tools\soldering_manual\build_manual.py --output docs\guides\HazardBot_만능기판_납땜_설명서.pdf
```

Expected: command prints the absolute PDF path and page count.

- [ ] **Step 7: Commit the PDF builder and first complete PDF**

```powershell
git add tools\soldering_manual\build_manual.py tests\soldering_manual\test_manual.py docs\guides\HazardBot_만능기판_납땜_설명서.pdf
git commit -m "Build illustrated soldering manual"
```

---

### Task 4: Render and Visually Verify Every Page

**Files:**
- Inspect: `docs/guides/HazardBot_만능기판_납땜_설명서.pdf`
- Create during QA: `tmp/soldering-manual-render/page-*.png`
- Modify if necessary: `tools/soldering_manual/content.py`
- Modify if necessary: `tools/soldering_manual/diagrams.py`
- Modify if necessary: `tools/soldering_manual/build_manual.py`
- Regenerate: `docs/guides/HazardBot_만능기판_납땜_설명서.pdf`

**Interfaces:**
- Consumes: final PDF from Task 3.
- Produces: visually approved PDF with no clipping, overlap, unreadable labels, or incorrect view mirroring.

- [ ] **Step 1: Render the PDF to page PNG files**

Use the PDF skill's bundled rendering command or Poppler at 150 DPI, writing all pages to `tmp/soldering-manual-render/`.

Expected: one PNG per PDF page.

- [ ] **Step 2: Create and inspect a contact sheet**

Create a contact sheet containing every page thumbnail and inspect overall rhythm, blank pages, section separation, and accidental overflow.

- [ ] **Step 3: Inspect critical pages at full resolution**

Inspect at least these pages individually:

- Board-holder orientation.
- Good/bad solder-joint comparison.
- Female-header cutting and ESP32 alignment.
- Rail cross-section and bottom-side mirroring.
- Sensor top/bottom layout and both MQ dividers.
- Drive top/bottom layout and motor-power boundary.
- Final one-page checklist.

- [ ] **Step 4: Correct every visual defect and rebuild**

Fix any clipped Korean text, overlapping labels, tiny callouts, incorrect left-right mirroring, page orphan, or ambiguous net. Rebuild the PDF and rerender all pages after the last change.

- [ ] **Step 5: Run final structural verification**

Run the full test script again and use `pypdf` or `pdfinfo` to confirm A4 page size and page count.

Expected: tests pass, all pages are A4, and every page has been visually inspected.

- [ ] **Step 6: Commit visual-QA corrections**

```powershell
git add tools\soldering_manual docs\guides\HazardBot_만능기판_납땜_설명서.pdf tests\soldering_manual\test_manual.py
git commit -m "Polish soldering manual layout"
```

---

### Task 5: Final Delivery Check

**Files:**
- Verify: `docs/guides/HazardBot_만능기판_납땜_설명서.pdf`
- Verify: `docs/superpowers/specs/2026-08-07-hazardbot-perfboard-soldering-manual-design.md`

**Interfaces:**
- Consumes: visually approved final PDF.
- Produces: final user handoff with an absolute clickable file link and concise usage note.

- [ ] **Step 1: Confirm the output exists and is non-empty**

Run a file listing that reports the absolute path, byte size, and modified time.

Expected: PDF exists under `docs/guides/` and has a non-zero size.

- [ ] **Step 2: Recheck the most safety-sensitive extracted text**

Extract the final PDF text and confirm it includes all of these phrases:

```text
교사 또는 성인의 감독
5V와 3.3V는 연결하지 않기
VM 12V는 로직 레일에 연결하지 않기
바퀴를 바닥에서 띄우기
이상하면 즉시 전원 분리
```

- [ ] **Step 3: Run the final test suite**

```powershell
C:\Users\rkdgm\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe tests\soldering_manual\test_manual.py
```

Expected: exit code `0` with all tests passing.

- [ ] **Step 4: Deliver the PDF**

Provide a clickable absolute link to `docs/guides/HazardBot_만능기판_납땜_설명서.pdf`, state the verified page count, and advise reading the safety and practice sections before parts arrive.
