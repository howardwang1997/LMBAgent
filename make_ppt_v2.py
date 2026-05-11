#!/usr/bin/env python3
"""Generate leadership-facing LMBAgent presentation with embedded analysis plots."""

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pathlib import Path

ASSETS = Path("ppt_assets")

prs = Presentation()
prs.slide_width  = Inches(13.333)
prs.slide_height = Inches(7.5)
W = prs.slide_width
H = prs.slide_height

BG_DARK  = RGBColor(0x0F, 0x16, 0x28)
ACCENT   = RGBColor(0x00, 0xD6, 0x8F)
ACCENT2  = RGBColor(0x4D, 0xA6, 0xFF)
WHITE    = RGBColor(0xFF, 0xFF, 0xFF)
LIGHT    = RGBColor(0xBB, 0xBB, 0xCC)
ORANGE   = RGBColor(0xFF, 0xB8, 0x00)
RED      = RGBColor(0xFF, 0x6B, 0x6B)


def _bg(slide):
    bg = slide.background.fill
    bg.solid()
    bg.fore_color.rgb = BG_DARK


def _text(slide, l, t, w, h, txt, sz=18, c=WHITE, bold=False, align=PP_ALIGN.LEFT):
    tb = slide.shapes.add_textbox(Inches(l), Inches(t), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = txt
    p.font.size = Pt(sz)
    p.font.color.rgb = c
    p.font.bold = bold
    p.alignment = align
    return tb


def _multi(slide, l, t, w, h, lines, sz=16, c=WHITE, bold=False, sp=1.2):
    tb = slide.shapes.add_textbox(Inches(l), Inches(t), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = line
        p.font.size = Pt(sz)
        p.font.color.rgb = c
        p.font.bold = bold
        p.space_after = Pt(sz * (sp - 1))
    return tb


def _accent_line(slide, l, t, w, color=ACCENT):
    s = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE,
                               Inches(l), Inches(t), Inches(w), Inches(0.04))
    s.fill.solid()
    s.fill.fore_color.rgb = color
    s.line.fill.background()


def _card(slide, l, t, w, h, color=RGBColor(0x14, 0x1E, 0x36)):
    s = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                               Inches(l), Inches(t), Inches(w), Inches(h))
    s.fill.solid()
    s.fill.fore_color.rgb = color
    s.line.fill.background()
    return s


def _img(slide, path, l, t, w=None, h=None):
    kw = {}
    if w: kw["width"] = Inches(w)
    if h: kw["height"] = Inches(h)
    return slide.shapes.add_picture(str(path), Inches(l), Inches(t), **kw)


def _notes(slide, text):
    slide.notes_slide.notes_text_frame.text = text


# ════════════════════════════════════════════════════
# 1  Title
# ════════════════════════════════════════════════════
sl = prs.slides.add_slide(prs.slide_layouts[6])
_bg(sl)
_accent_line(sl, 1, 2.2, 3.5)
_text(sl, 1, 2.4, 11, 1.2, "LMBAgent", 56, WHITE, True)
_text(sl, 1, 3.6, 11, 0.7, "Lithium-Metal Battery Experiment Data Analysis Agent", 24, LIGHT)
_text(sl, 1, 4.5, 11, 0.5, "AI-Driven Multi-Experiment Comparison, Degradation Diagnostics & DOE Intelligence", 16, ACCENT2)
_accent_line(sl, 1, 5.3, 2, ACCENT2)
_text(sl, 1, 5.6, 6, 0.4, "Validated on real Neware cycling data  |  434+326 cycles loaded", 14, LIGHT)
_text(sl, 9, 6.8, 4, 0.4, "2026.05", 14, LIGHT, align=PP_ALIGN.RIGHT)

_notes(sl, (
    "Slide 1: Title\n"
    "LMBAgent = Lithium-Metal Battery Agent\n"
    "Core value: Turn raw cycling data into actionable insights via AI\n"
    "Already validated on 2 real Neware datasets (760 cycles total)\n"
))


# ════════════════════════════════════════════════════
# 2  Architecture
# ════════════════════════════════════════════════════
sl = prs.slides.add_slide(prs.slide_layouts[6])
_bg(sl)
_text(sl, 0.6, 0.3, 8, 0.5, "Overall Architecture", 30, WHITE, True)
_accent_line(sl, 0.6, 0.85, 2.5)

_img(sl, ASSETS / "architecture.png", 0.5, 1.1, w=12.3)

_notes(sl, (
    "Slide 2: Architecture\n"
    "4 layers:\n"
    "  Data Sources: 6 formats auto-detected (NEWAREA/NEWAREB/TVC/PEC/Arbin/CSV)\n"
    "  Data Foundation: AI Smart Loader + Experiment Design YAML + SQLite persistence\n"
    "  Analysis Engine: Multi-experiment comparison, 7-mode NNLS decomposition, DOE diagnosis, historical search\n"
    "  Intelligence Layer: LLM Agent (18 tools, minimax-m2.7), Conclusion management, Streamlit Web UI (10 pages)\n"
    "Key design: all analysis via tool calling; Streamlit calls core library directly (no middleware)\n"
))


# ════════════════════════════════════════════════════
# 3  Data Loading — highlight AI smart loading
# ════════════════════════════════════════════════════
sl = prs.slides.add_slide(prs.slide_layouts[6])
_bg(sl)
_text(sl, 0.6, 0.3, 10, 0.5, "AI-Powered Smart Data Loading", 30, WHITE, True)
_accent_line(sl, 0.6, 0.85, 2.5)

# Left: challenges
_card(sl, 0.4, 1.2, 5.5, 3.0)
_text(sl, 0.6, 1.3, 5, 0.4, "Challenge: Diverse Data Formats", 16, ORANGE, True)
_multi(sl, 0.6, 1.8, 5, 2.2, [
    "NewareA: Chinese column names, record sheet",
    "NewareB: Mixed headers, Detail_* sheet",
    "TVC Report: Summary tables, no time-series",
    "PEC / Arbin / Generic CSV: 30+ column aliases",
    "",
    "Column names include units: e.g. '相对时间(h:min:s.ms)'",
    "Single capacity column needs current-direction splitting",
], 13, LIGHT, sp=1.2)

# Right: AI solution
_card(sl, 6.2, 1.2, 6.7, 3.0)
_text(sl, 6.4, 1.3, 6, 0.4, "Solution: AI + Rule-Based Hybrid", 16, ACCENT, True)
_multi(sl, 6.4, 1.8, 6.3, 2.2, [
    "1. Auto-detect format (extension + content analysis)",
    "2. Substring column matching (handles units in headers)",
    "3. Split capacity by current direction: I>0 charge, I<0 discharge",
    "4. If rules fail -> LLM analyzes file header with minimax-m2.7",
    "5. LLM returns: format, separator, column_map, skip_rows",
    "",
    "Fallback chain: exact match -> substring -> fuzzy -> LLM",
], 13, WHITE, sp=1.2)

# Bottom: results table
_img(sl, ASSETS / "metrics_table.png", 1.5, 4.5, w=10)

_notes(sl, (
    "Slide 3: AI Smart Loading\n"
    "Problem: 3 different Neware formats with inconsistent column names\n"
    "  NEWAREA: '容量(Ah)' single column, '数据序号/循环号/工步号/时间/总时间/电流(A)/电压(V)'\n"
    "  NEWAREB: '记录序号/状态/跳转/循环/步次/电流(A)/电压(V)/容量(Ah)/能量(Wh)/相对时间(h:min:s.ms)/绝对时间'\n"
    "  TVC: CD_Capacity_Data with Cycle_No./Charge/Discharge per sample\n"
    "Solution: 4-level fallback (exact -> substring -> fuzzy -> LLM)\n"
    "Key innovation: single 'capacity' column split by current sign into charge/discharge\n"
    "Results: NEWAREA 303k rows/434 cycles, NEWAREB 234k rows/326 cycles loaded correctly\n"
))


# ════════════════════════════════════════════════════
# 4  Capacity Fade Overlay (big plot)
# ════════════════════════════════════════════════════
sl = prs.slides.add_slide(prs.slide_layouts[6])
_bg(sl)
_text(sl, 0.6, 0.2, 10, 0.4, "Multi-Experiment Comparison: Capacity Fade", 28, WHITE, True)

_img(sl, ASSETS / "capacity_fade_overlay.png", 0.3, 0.7, w=8.0)

# Right side: key findings
_card(sl, 8.6, 0.7, 4.4, 2.8)
_text(sl, 8.8, 0.8, 4, 0.35, "Key Findings", 16, ORANGE, True)
_multi(sl, 8.8, 1.25, 4, 2.1, [
    "NEWAREA 1205XXL:",
    "  434 cycles, 152.7→142.3 mAh",
    "  Retention: 93.2%",
    "",
    "NEWAREB 1122XXL:",
    "  326 cycles, 152.8→148.2 mAh",
    "  Retention: 97.0%",
], 13, LIGHT, sp=1.1)

# Normalized retention below
_img(sl, ASSETS / "capacity_retention.png", 8.6, 3.8, w=4.4)

_notes(sl, (
    "Slide 4: Capacity Fade Comparison\n"
    "Both cells are LMB (lithium-metal battery) cycling data\n"
    "NEWAREA shows faster degradation (93.2% at cycle 434)\n"
    "NEWAREB maintains 97.0% at cycle 326\n"
    "Normalized view shows NEWAREA approaching 80% EOL trend earlier\n"
    "This overlay enables instant visual comparison of cell performance\n"
))


# ════════════════════════════════════════════════════
# 5  Voltage Curves + Delta V
# ════════════════════════════════════════════════════
sl = prs.slides.add_slide(prs.slide_layouts[6])
_bg(sl)
_text(sl, 0.6, 0.2, 10, 0.4, "Voltage Analysis: Curves & Delta-V", 28, WHITE, True)

_img(sl, ASSETS / "voltage_curves_overlay.png", 0.2, 0.65, w=8.5)
_img(sl, ASSETS / "delta_v_analysis.png", 0.2, 4.1, w=6.5)

# dQ/dV on right
_img(sl, ASSETS / "dqdV_analysis.png", 6.8, 4.1, w=6.2)

_notes(sl, (
    "Slide 5: Voltage Analysis\n"
    "Top: Discharge V(Q) curves at cycles 1/50/100/200/300 for both cells\n"
    "  NEWAREA shows more voltage curve evolution over cycling\n"
    "  Both cells show similar LMB discharge plateau ~3.4V\n"
    "Bottom-left: Delta-V at cycle 100 — direct overlay comparison\n"
    "Bottom-right: dQ/dV at cycle 100 — electrochemical fingerprint\n"
    "  dQ/dV peaks reveal phase transitions and degradation mechanisms\n"
))


# ════════════════════════════════════════════════════
# 6  Coulombic Efficiency
# ════════════════════════════════════════════════════
sl = prs.slides.add_slide(prs.slide_layouts[6])
_bg(sl)
_text(sl, 0.6, 0.2, 10, 0.4, "Coulombic Efficiency Comparison", 28, WHITE, True)

_img(sl, ASSETS / "coulombic_efficiency.png", 1.5, 0.8, w=10)

_card(sl, 1, 5.3, 11.3, 1.5)
_multi(sl, 1.3, 5.4, 10.8, 1.3, [
    "CE is a key indicator of lithium cycling efficiency — ideal = 100%",
    "NEWAREA: Mean CE ~99.5%, more scatter in early cycles (formation effects)",
    "NEWAREB: Mean CE ~99.7%, tighter distribution indicates more stable interface",
    "System auto-computes CE from charge/discharge capacity per cycle",
], 14, WHITE, sp=1.2)

_notes(sl, (
    "Slide 6: Coulombic Efficiency\n"
    "CE = Discharge_Cap / Charge_Cap x 100%\n"
    "For LMB: CE < 100% indicates lithium loss per cycle (SEI growth, dead Li)\n"
    "NEWAREA shows more CE variability, suggesting less stable SEI\n"
    "Both cells have CE > 99% which is typical for LMB with good electrolyte\n"
    "Auto-computed from raw data: capacity split by current direction\n"
))


# ════════════════════════════════════════════════════
# 7  Degradation Decomposition
# ════════════════════════════════════════════════════
sl = prs.slides.add_slide(prs.slide_layouts[6])
_bg(sl)
_text(sl, 0.6, 0.2, 12, 0.4, "Degradation Mode Decomposition (7-Mode NNLS)", 28, WHITE, True)

_img(sl, ASSETS / "degradation_decomposition.png", 0.5, 0.7, w=8.5)

# Right: explanation
_card(sl, 9.3, 0.7, 3.7, 4.0)
_text(sl, 9.5, 0.8, 3.3, 0.35, "7 Degradation Modes", 14, ORANGE, True)
_multi(sl, 9.5, 1.25, 3.3, 3.3, [
    "SEI Growth — impedance increase",
    "Li Plating — irreversible loss",
    "LAM(+) — cathode degradation",
    "LAM(-) — anode degradation",
    "R Growth — contact/transfer",
    "Diffusion — ion transport",
    "Electrolyte — depletion/drying",
    "",
    "Algorithm: dV(t) = sum(w_j x sig_j)",
    "solved via NNLS (scipy)",
], 11, LIGHT, sp=1.15)

_card(sl, 9.3, 5.0, 3.7, 2.0)
_text(sl, 9.5, 5.1, 3.3, 0.35, "NEWAREA Result", 14, ACCENT, True)
_multi(sl, 9.5, 5.5, 3.3, 1.4, [
    "Dominant: SEI Growth (early)",
    "Li Plating increases at high cycles",
    "Total fade: ~7% at cycle 434",
], 12, WHITE, sp=1.3)

# Bottom
_card(sl, 0.5, 5.0, 8.5, 2.0)
_multi(sl, 0.7, 5.1, 8, 1.8, [
    "What this enables:",
    "  Quantify which degradation mechanism dominates at each cycle",
    "  Compare degradation fingerprints across experiments with different designs",
    "  Correlate design factors (electrolyte, separator, formation) with mode contributions",
    "  Feed into DOE checker to recommend experiments that fill knowledge gaps",
], 13, LIGHT, sp=1.2)

_notes(sl, (
    "Slide 7: Degradation Decomposition\n"
    "Top panel: raw capacity fade curve\n"
    "Bottom panel: stacked area = contribution of each mode to total degradation\n"
    "Method: NNLS (Non-Negative Least Squares) decomposition of delta-V against 7 mode signatures\n"
    "  delta_V(t) = w_SEI * sig_SEI(t) + w_plating * sig_plating(t) + ... (7 modes)\n"
    "For NEWAREA: early degradation dominated by SEI growth, Li plating becomes significant later\n"
    "This is the key analytical capability — turns raw cycling data into mechanistic understanding\n"
    "Future: replace rule-based signatures with model-based (autobattery FNO) for higher accuracy\n"
))


# ════════════════════════════════════════════════════
# 8  DOE + Historical Search + Conclusions
# ════════════════════════════════════════════════════
sl = prs.slides.add_slide(prs.slide_layouts[6])
_bg(sl)
_text(sl, 0.6, 0.2, 12, 0.4, "DOE Intelligence, Historical Search & Conclusion Verification", 26, WHITE, True)

# 3 columns
# DOE
_card(sl, 0.3, 1.0, 4.1, 3.5)
_accent_line(sl, 0.5, 1.1, 2, ORANGE)
_text(sl, 0.5, 1.2, 3.8, 0.35, "DOE Intelligence", 16, ORANGE, True)
_multi(sl, 0.5, 1.7, 3.8, 2.7, [
    "Given loaded experiments:",
    "",
    "Analyze design factor variations",
    "Compute parameter space coverage",
    "Identify missing combinations",
    "Score DOE completeness (0-100%)",
    "",
    "Recommend:",
    "  - Missing factor combos",
    "  - Midpoint experiments",
    "  - New factor suggestions",
], 12, LIGHT, sp=1.15)

# Search
_card(sl, 4.6, 1.0, 4.1, 3.5)
_accent_line(sl, 4.8, 1.1, 2, ACCENT2)
_text(sl, 4.8, 1.2, 3.8, 0.35, "Historical Search", 16, ACCENT2, True)
_multi(sl, 4.8, 1.7, 3.8, 2.7, [
    "Every experiment vectorized:",
    "  Design factors (20d)",
    "  Performance features (17d)",
    "  Degradation weights (7d)",
    "",
    "Search modes:",
    "  Similar (cosine similarity)",
    "  Contrast (design-near,",
    "    degradation-far)",
    "  Keyword (cell_id, chemistry)",
], 12, LIGHT, sp=1.15)

# Conclusions
_card(sl, 8.9, 1.0, 4.1, 3.5)
_accent_line(sl, 9.1, 1.1, 2, RED)
_text(sl, 9.1, 1.2, 3.8, 0.35, "Conclusion Lifecycle", 16, RED, True)
_multi(sl, 9.1, 1.7, 3.8, 2.7, [
    "5-state lifecycle:",
    "  active",
    "    -> supported",
    "    -> challenged",
    "    -> superseded",
    "    -> retracted",
    "",
    "New data auto-triggers:",
    "  Feature extract -> Historical",
    "  search -> Compare -> Verify",
], 12, LIGHT, sp=1.15)

# Bottom: workflow
_card(sl, 0.3, 4.8, 12.7, 2.2)
_text(sl, 0.5, 4.9, 5, 0.35, "Closed-Loop Workflow", 16, ACCENT, True)
_multi(sl, 0.5, 5.35, 12, 1.5, [
    "New Experiment Data  -->  AI Smart Load  -->  Feature Extraction  -->  Historical Search",
    "     |                                                                        |",
    "     |    DOE Coverage Check  <--  Degradation Decomposition  <--  Comparison  <--+",
    "     |              |",
    "     +--  Conclusion Verified/Challenged  -->  Recommend Supplementary Experiments",
], 13, WHITE, sp=1.1)

_notes(sl, (
    "Slide 8: DOE + Search + Conclusions\n"
    "DOE Intelligence: Quantifies how well the current set of experiments covers the design space\n"
    "  Example: If we have electrolyte A+B tested at 25C and 45C, but never with separator X at 25C,\n"
    "  the DOE checker flags this missing combination and recommends it\n"
    "Historical Search: Every experiment is converted to a 44-dim feature vector\n"
    "  Similar search: find experiments with similar design AND performance (for benchmarking)\n"
    "  Contrast search: find experiments with similar design but DIFFERENT degradation (high info value)\n"
    "Conclusion Management: Conclusions have 5 states and auto-verify against new data\n"
    "  When new data arrives, system checks if existing conclusions are supported or challenged\n"
    "Closed loop: data -> analysis -> conclusions -> DOE gaps -> new experiments -> more data\n"
))


# ════════════════════════════════════════════════════
# 9  Summary & Impact
# ════════════════════════════════════════════════════
sl = prs.slides.add_slide(prs.slide_layouts[6])
_bg(sl)
_accent_line(sl, 1, 1.5, 4)
_text(sl, 1, 1.7, 11, 1, "Summary & Impact", 44, WHITE, True)

_card(sl, 0.5, 3.0, 6, 3.5)
_text(sl, 0.7, 3.1, 5.5, 0.4, "What We Built", 18, ACCENT, True)
_multi(sl, 0.7, 3.6, 5.5, 2.8, [
    "AI-powered data loading for 6 battery data formats",
    "Multi-experiment overlay comparison (capacity, CE, voltage, dQ/dV)",
    "7-mode degradation decomposition via NNLS",
    "DOE completeness scoring & gap recommendation",
    "Vector-based historical experiment search",
    "Conclusion lifecycle management with auto-verification",
    "10-page web UI, 18 LLM tools, 123 tests passing",
], 14, WHITE, sp=1.2)

_card(sl, 6.8, 3.0, 6, 3.5)
_text(sl, 7.0, 3.1, 5.5, 0.4, "Impact & Next Steps", 18, ORANGE, True)
_multi(sl, 7.0, 3.6, 5.5, 2.8, [
    "Reduced data loading time: minutes -> seconds",
    "First-time quantitative degradation mode attribution",
    "DOE gaps visible at a glance (was invisible before)",
    "",
    "Next:",
    "  Phase 5: Model-based signatures (replace rules)",
    "  Phase 6: Online adaptive model update",
    "  Phase 7: Multi-user + access control",
    "  Phase 8: autobattery FNO integration",
], 14, WHITE, sp=1.2)

_text(sl, 1, 6.8, 11.3, 0.4,
      "Data -> Insight -> Decision: accelerating lithium-metal battery R&D with AI",
      16, ACCENT2, True, PP_ALIGN.CENTER)

_notes(sl, (
    "Slide 9: Summary\n"
    "Key deliverables:\n"
    "  1. Universal data loader (6 formats, AI fallback)\n"
    "  2. Multi-experiment comparison engine\n"
    "  3. 7-mode NNLS degradation decomposition\n"
    "  4. DOE intelligence (coverage scoring + gap recommendation)\n"
    "  5. Historical search engine (44-dim vectors)\n"
    "  6. Conclusion management with auto-verification\n"
    "Engineering: 123/123 tests, 15 Python modules, 18 LLM tools, 10 web pages\n"
    "Validated on real Neware cycling data (NEWAREA 434 cycles + NEWAREB 326 cycles)\n"
    "Impact: turns hours of manual data handling into seconds of automated analysis\n"
))


# ── Save ──
out = "LMBAgent_Report.pptx"
prs.save(out)
print(f"Saved {out} ({prs.slide_width}, {prs.slide_height})")
