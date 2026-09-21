"""Builds the one-page PDF report: Codexa knowledge-graph token-reduction proof.

Sections: Dataset Description, Problem Statement, Methodology, Results & Insights
(with chart + table), Novelty. Reads chart.png (sibling) and
tests/benchmarks/memory_graph/payload_results/*.json for the numbers.
"""
import glob
import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, FrameBreak,
    Paragraph, Spacer, Table, TableStyle, Image, HRFlowable, KeepTogether,
)

HERE = Path(__file__).parent
RESULTS_DIR = HERE.parent / "payload_results"
OUT_PDF = HERE.parent.parent.parent.parent / "docs" / "Codexa_Token_Reduction_Report.pdf"

INK = colors.HexColor("#1a1a1a")
MUT = colors.HexColor("#5a5a5a")
ACCENT = colors.HexColor("#2a7d4a")
RAW_C = colors.HexColor("#c85a17")
RULE = colors.HexColor("#d8d5cf")
BG = colors.HexColor("#f6f5f2")

GITHUB_PROFILE = "https://github.com/rohitvijayakumar45"
GITHUB_REPO = "https://github.com/rohitvijayakumar45/Codexa"
AUTHOR = "Rohit V K"

# ---- load data -------------------------------------------------------------
files = sorted(glob.glob(str(RESULTS_DIR / "*.json")))
data = [json.load(open(f, encoding="utf-8")) for f in files]
data.sort(key=lambda d: -d["overall_reduction_x"])

n_total = sum(d["n_symbols"] for d in data)
raw_total = sum(d["raw_total_tokens"] for d in data)
graph_total = sum(d["graph_total_tokens"] for d in data)
overall_x = raw_total / graph_total
pct = (1 - graph_total / raw_total) * 100
price_in = data[0]["usd_per_1M_input"]

# ---- styles ------------------------------------------------------------
styles = {}
styles["title"] = ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=19,
                                  leading=22, textColor=INK, spaceAfter=1)
styles["byline"] = ParagraphStyle("byline", fontName="Helvetica", fontSize=9.3,
                                   leading=12.5, textColor=MUT, spaceAfter=0)
styles["h2"] = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=10.4,
                               leading=12.4, textColor=ACCENT, spaceBefore=5.5, spaceAfter=2.5,
                               letterSpacing=0.3)
styles["body"] = ParagraphStyle("body", fontName="Helvetica", fontSize=8.6,
                                 leading=11.4, textColor=INK, alignment=TA_LEFT)
styles["body_tight"] = ParagraphStyle("body_tight", parent=styles["body"], spaceAfter=3)
styles["bullet"] = ParagraphStyle("bullet", parent=styles["body"], leftIndent=10,
                                   bulletIndent=0, spaceAfter=4.5)
styles["headline_num"] = ParagraphStyle("headline_num", fontName="Helvetica-Bold", fontSize=15,
                                         leading=18, textColor=ACCENT, alignment=TA_CENTER)
styles["headline_cap"] = ParagraphStyle("headline_cap", fontName="Helvetica", fontSize=8.2,
                                         leading=10.5, textColor=MUT, alignment=TA_CENTER)
styles["caption"] = ParagraphStyle("caption", fontName="Helvetica-Oblique", fontSize=7.8,
                                    leading=10, textColor=MUT)
styles["footer"] = ParagraphStyle("footer", fontName="Helvetica", fontSize=8.3,
                                   leading=11, textColor=MUT)

story = []

# ---- header -----------------------------------------------------------
story.append(Paragraph(
    "Codexa OS Knowledge Graph: A Token-Reduction Proof for LLM Code Retrieval", styles["title"]))
story.append(Spacer(1, 2))

# GitHub link as its own prominent, bordered callout — a main point, not a small footnote.
gh_chip = Table(
    [[Paragraph(
        f"{AUTHOR} &nbsp;&nbsp;|&nbsp;&nbsp; CODE &amp; FULL WRITE-UP: "
        f"<link href='{GITHUB_REPO}' color='#ffffff'><u>{GITHUB_REPO}</u></link>"
        f"&nbsp;&nbsp;|&nbsp;&nbsp; "
        f"<link href='{GITHUB_PROFILE}' color='#ffffff'><u>{GITHUB_PROFILE}</u></link>",
        ParagraphStyle("ghlink", fontName="Helvetica-Bold", fontSize=8.6, leading=10.6,
                        textColor=colors.white))]],
    colWidths=[7.7 * inch],
)
gh_chip.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, -1), ACCENT),
    ("TOPPADDING", (0, 0), (-1, -1), 3.5),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
    ("LEFTPADDING", (0, 0), (-1, -1), 8),
]))
story.append(gh_chip)
story.append(Spacer(1, 3))
story.append(HRFlowable(width="100%", thickness=1.1, color=ACCENT, spaceAfter=4))

# ---- headline stat band -------------------------------------------------
headline_cells = [
    [Paragraph(f"{overall_x:.1f}x", styles["headline_num"]),
     Paragraph(f"{pct:.1f}%", styles["headline_num"]),
     Paragraph(f"{n_total}", styles["headline_num"]),
     Paragraph(f"{len(data)}", styles["headline_num"])],
    [Paragraph("fewer context tokens", styles["headline_cap"]),
     Paragraph("token reduction", styles["headline_cap"]),
     Paragraph("code symbols tested", styles["headline_cap"]),
     Paragraph("real repositories", styles["headline_cap"])],
]
headline_tbl = Table(headline_cells, colWidths=[1.75 * inch] * 4)
headline_tbl.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, -1), BG),
    ("BOX", (0, 0), (-1, -1), 0.6, RULE),
    ("INNERGRID", (0, 0), (-1, -1), 0.5, RULE),
    ("TOPPADDING", (0, 0), (-1, 0), 5),
    ("BOTTOMPADDING", (0, 0), (-1, 0), 1),
    ("TOPPADDING", (0, 1), (-1, 1), 0),
    ("BOTTOMPADDING", (0, 1), (-1, 1), 5),
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
]))
story.append(headline_tbl)
story.append(Spacer(1, 4))

# ---- two-column body: left = narrative sections, right = results ------
left_col = []
left_col.append(Paragraph("PROBLEM STATEMENT", styles["h2"]))
left_col.append(Paragraph(
    "LLM coding agents that answer from raw source files suffer four compounding failures: "
    "<b>hallucination</b> (no ground truth to check a claim against), <b>context bloat</b> "
    "(stale files pile up in the window), <b>runaway token usage</b> (cost scales with file size "
    "and reference count — hard questions can make an agent fail to converge at all; single "
    "runs we tested reached 300K–1.9M tokens with no answer), and <b>sycophancy</b> (a "
    "confidently-worded wrong answer talks a correct peer agent out of its own). Codexa's "
    "structural graph and persistent memory address all four: claims are checked against the "
    "graph instead of self-reported (hallucination), stale payloads are evicted by graph "
    "distance instead of a flat timer (bloat), the graph replaces raw-file reading (token usage "
    "— measured below), and disagreement is resolved by verifying claims against the graph "
    "before any free-text debate (sycophancy).", styles["body_tight"]))

left_col.append(Paragraph("METHODOLOGY", styles["h2"]))
left_col.append(Paragraph(
    "<b>Pipeline:</b> each repository is parsed with real <b>tree-sitter</b> grammars (Python, "
    "JavaScript, TypeScript, TSX) into an incremental concrete syntax tree, from which an "
    "<b>event-sourced structural knowledge graph</b> is built — nodes for files, functions and "
    "classes; edges for imports, calls and dependencies — derived from the actual parse tree, "
    "not regex or text pattern-matching. An LLM symbol-annotation pass then walks that graph "
    "once and writes a one-line semantic description of what each symbol does, cached by a "
    "content hash of its source span so a later re-ingest only re-annotates symbols whose code "
    "actually changed. Those annotations, plus three other memory types (Novelty — four in "
    "total: semantic, episodic, procedural, organizational), persist in a shared project memory "
    "store used by every model regardless of which LLM is active. <b>Measurement:</b> a "
    "deterministic, model-free comparison isolates the graph as the only variable, with no LLM "
    "in the loop. Per symbol, <i>graph retrieval</i> resolves its definition and every "
    "caller/dependent directly from the graph in one lookup; <i>raw retrieval</i> opens every "
    "file needed to derive the same facts, with that file set itself read from the graph's own "
    "incoming edges, so both arms answer the identical question. Tokens are counted with "
    "tiktoken (cl100k_base). An earlier end-to-end agentic benchmark across 3 LLMs was "
    "abandoned once every arm was found to thrash without converging on hard multi-hop "
    "questions — a convergence failure that would have measured model instability, not the "
    "architecture, and a failure mode structurally related to the sycophancy problem "
    "Quorum solves (Novelty).",
    styles["body_tight"]))

right_col = []
right_col.append(Paragraph("RESULTS &amp; INSIGHTS", styles["h2"]))

chart_w = 3.5 * inch
chart_h = chart_w * (934 / 2011)
right_col.append(Image(str(HERE / "chart.png"), width=chart_w, height=chart_h))
right_col.append(Spacer(1, 3))

tbl_data = [["Repository", "Raw tok", "Graph tok", "Reduction"]]
for d in data:
    tbl_data.append([
        d["repository"], f"{d['raw_total_tokens']:,}", f"{d['graph_total_tokens']:,}",
        f"{d['overall_reduction_x']:.0f}x",
    ])
tbl_data.append(["All (aggregate)", f"{raw_total:,}", f"{graph_total:,}", f"{overall_x:.1f}x"])

res_tbl = Table(tbl_data, colWidths=[1.5 * inch, 0.85 * inch, 0.85 * inch, 0.75 * inch])
res_tbl.setStyle(TableStyle([
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
    ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
    ("FONTSIZE", (0, 0), (-1, -1), 7.1),
    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
    ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
    ("BACKGROUND", (0, -1), (-1, -1), BG),
    ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, BG]),
    ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
    ("ALIGN", (0, 0), (0, -1), "LEFT"),
    ("TEXTCOLOR", (-1, 1), (-1, -1), ACCENT),
    ("LINEBELOW", (0, 0), (-1, 0), 0.6, ACCENT),
    ("LINEABOVE", (0, -1), (-1, -1), 0.8, ACCENT),
    ("TOPPADDING", (0, 0), (-1, -1), 2.2),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
    ("LEFTPADDING", (0, 0), (-1, -1), 4),
    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ("BOX", (0, 0), (-1, -1), 0.5, RULE),
]))
right_col.append(res_tbl)
right_col.append(Spacer(1, 4))

right_col.append(Paragraph(
    f"At an illustrative <b>${price_in:.2f}/1M input tokens</b>, these {n_total} lookups cost "
    f"<b>${raw_total/1e6*price_in:.3f} raw</b> vs. <b>${graph_total/1e6*price_in:.3f} via the "
    f"graph</b> — scaled to 100K lookups, roughly <b>$267 vs. $3</b>, a direct saving at any "
    f"provider's price.", styles["body_tight"]))

right_col.append(Paragraph(
    "<b>Key insight:</b> this raw baseline is conservative — real agentic runs on the same "
    "questions re-read files and chase leads, reaching 300K–1.9M tokens <i>without even "
    "converging</i>, so the true gap is larger than shown. Additive saving: Codexa's memory "
    "injects a fixed 0.2K–18K-token payload answering conventions without re-deriving them.",
    styles["body_tight"]))

right_col.append(Paragraph("NOVELTY", styles["h2"]))
for b in [
    "<b>Four memory types:</b> semantic, episodic, procedural, organizational — durable, "
    "shared across every model regardless of which LLM is active.",
    "<b>Symbol annotations:</b> an LLM writes what each symbol MEANS on top of what tree-sitter's "
    "parse already captures about its structure, cached by content hash so restarts reuse it for "
    "free instead of re-annotating unchanged code.",
    "<b>Graph:</b> an event-sourced structural knowledge graph (files/functions/classes as nodes, "
    "imports/calls/dependencies as edges) that answers navigation queries directly instead of "
    "re-reading files, and doubles as the mechanism that prevents context bloat — stale tool "
    "payloads are evicted by graph-distance from the file in play, not a fixed round-count.",
    "<b>Blast radius:</b> a reverse-dependency traversal of the same graph, run from any changed "
    "symbol, that surfaces every downstream node reachable by import/call/dependency edges — "
    "impact analysis before the change is made, not after.",
    "<b>Quorum:</b> agents answer independently, checked against the graph before seeing a peer's "
    "answer; ties debate only via structured belief cards, revising solely on a verified claim — "
    "closing the sycophancy vector.",
]:
    right_col.append(Paragraph(f"&bull;&nbsp; {b}", styles["bullet"]))

footer_flow = [
    HRFlowable(width="100%", thickness=0.6, color=RULE, spaceAfter=3),
    Paragraph(
        f"Codexa OS — engineering-intelligence platform (FastAPI + Next.js, event-sourced "
        f"knowledge graph, LLM build/chat agents). Full write-up: "
        f"<font face='Courier'>docs/graph_token_reduction_proof.md</font> in the project "
        f"repository above.", styles["footer"]),
]

# ---- build: a real 2-column page (header frame + independent left/right frames +
# footer frame), NOT a single-row Table. A Table cell is one atomic flowable that must fit
# whole before being placed, so wrapping both columns in one Table row forced the ENTIRE
# two-column body onto a fresh page the instant it didn't fit in whatever space remained
# after the header — wasting all of page 1. Two real Frames let the left and right columns
# each use exactly the space available on page 1, independently, which is what actually
# makes this a one-pager instead of a mostly-blank page 1 + a full page 2.
MARGIN = 0.4 * inch
GUTTER = 0.15 * inch
LEFT_W = 3.2 * inch
CONTENT_W = letter[0] - 2 * MARGIN
RIGHT_W = CONTENT_W - LEFT_W - GUTTER
HEADER_H = 1.68 * inch
FOOTER_H = 0.42 * inch
COL_H = letter[1] - 2 * MARGIN - HEADER_H - FOOTER_H

header_frame = Frame(MARGIN, MARGIN + FOOTER_H + COL_H, CONTENT_W, HEADER_H,
                      leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=2, id="header")
left_frame = Frame(MARGIN, MARGIN + FOOTER_H, LEFT_W, COL_H,
                    leftPadding=0, rightPadding=6, topPadding=2, bottomPadding=0, id="left")
right_frame = Frame(MARGIN + LEFT_W + GUTTER, MARGIN + FOOTER_H, RIGHT_W, COL_H,
                     leftPadding=6, rightPadding=0, topPadding=2, bottomPadding=0, id="right")
footer_frame = Frame(MARGIN, MARGIN, CONTENT_W, FOOTER_H,
                      leftPadding=0, rightPadding=0, topPadding=2, bottomPadding=0, id="footer")

doc = BaseDocTemplate(
    str(OUT_PDF), pagesize=letter,
    leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN, bottomMargin=MARGIN,
    title="Codexa OS Knowledge Graph: A Token-Reduction Proof",
    author=AUTHOR,
)
doc.addPageTemplates([PageTemplate(
    id="OnePager", frames=[header_frame, left_frame, right_frame, footer_frame])])

story = story + [FrameBreak()] + left_col + [FrameBreak()] + right_col + [FrameBreak()] + footer_flow
doc.build(story)
print("wrote", OUT_PDF)
