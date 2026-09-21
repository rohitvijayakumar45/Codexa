// Condensed one-page DOCX version of the token-reduction report. Much shorter than the PDF
// build_report.py output — single column, short paragraphs, compact table — so it reliably
// renders to exactly one page at Word's default margins.
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, WidthType,
  ShadingType, AlignmentType, BorderStyle, HeadingLevel, ImageRun,
  Header, Footer, ExternalHyperlink, VerticalAlign,
} = require("docx");

const HERE = __dirname;
const RESULTS_DIR = path.join(HERE, "..", "payload_results");
const CHART = path.join(HERE, "chart.png");
const OUT = path.join(HERE, "..", "..", "..", "..", "docs", "Codexa_Token_Reduction_Report.docx");

const INK = "1A1A1A";
const MUT = "5A5A5A";
const ACCENT = "2A7D4A";
const BG = "F0F1EE";

const files = fs.readdirSync(RESULTS_DIR).filter(f => f.endsWith(".json")).sort();
const data = files.map(f => JSON.parse(fs.readFileSync(path.join(RESULTS_DIR, f), "utf-8")));
data.sort((a, b) => b.overall_reduction_x - a.overall_reduction_x);

const nTotal = data.reduce((s, d) => s + d.n_symbols, 0);
const rawTotal = data.reduce((s, d) => s + d.raw_total_tokens, 0);
const graphTotal = data.reduce((s, d) => s + d.graph_total_tokens, 0);
const overallX = rawTotal / graphTotal;
const pct = (1 - graphTotal / rawTotal) * 100;
const priceIn = data[0].usd_per_1M_input;
const fmt = n => n.toLocaleString("en-US");

const GITHUB_REPO = "https://github.com/rohitvijayakumar45/Codexa";
const GITHUB_PROFILE = "https://github.com/rohitvijayakumar45";
const AUTHOR = "Rohit V K";

// ---- small helpers ---------------------------------------------------------
function p(children, opts = {}) {
  return new Paragraph({ spacing: { after: 80, ...opts.spacing }, ...opts, children });
}
function r(text, opts = {}) { return new TextRun({ text, ...opts }); }
function bold(text, opts = {}) { return r(text, { bold: true, ...opts }); }
function bullet(runs) {
  return new Paragraph({
    children: runs, bullet: { level: 0 }, spacing: { after: 60 },
  });
}
function link(text, url) {
  return new ExternalHyperlink({
    link: url,
    children: [new TextRun({ text, style: "Hyperlink", color: "FFFFFF", underline: {} })],
  });
}

// ---- header band: title + prominent GitHub link ----------------------------
const titlePara = new Paragraph({
  heading: HeadingLevel.TITLE,
  spacing: { after: 40 },
  children: [new TextRun({
    text: "Codexa OS Knowledge Graph: A Token-Reduction Proof",
    bold: true, size: 32, color: INK,
  })],
});

const ghChip = new Table({
  width: { size: 9350, type: WidthType.DXA },
  columnWidths: [9350],
  borders: {
    top: { style: BorderStyle.NONE }, bottom: { style: BorderStyle.NONE },
    left: { style: BorderStyle.NONE }, right: { style: BorderStyle.NONE },
    insideHorizontal: { style: BorderStyle.NONE }, insideVertical: { style: BorderStyle.NONE },
  },
  rows: [new TableRow({ children: [
    new TableCell({
      width: { size: 9350, type: WidthType.DXA },
      shading: { type: ShadingType.CLEAR, fill: ACCENT },
      margins: { top: 70, bottom: 70, left: 160, right: 160 },
      children: [new Paragraph({ children: [
        new TextRun({ text: `${AUTHOR}   |   CODE & FULL WRITE-UP:  `, bold: true, color: "FFFFFF", size: 18 }),
        link(GITHUB_REPO, GITHUB_REPO),
        new TextRun({ text: "    |    ", color: "FFFFFF", size: 18 }),
        link(GITHUB_PROFILE, GITHUB_PROFILE),
      ] })],
    }),
  ] })],
});

// ---- headline stat band -----------------------------------------------------
function statCell(big, small) {
  return new TableCell({
    width: { size: 2337, type: WidthType.DXA },
    shading: { type: ShadingType.CLEAR, fill: BG },
    margins: { top: 90, bottom: 60, left: 60, right: 60 },
    verticalAlign: VerticalAlign.CENTER,
    children: [
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 20 },
        children: [new TextRun({ text: big, bold: true, size: 30, color: ACCENT })] }),
      new Paragraph({ alignment: AlignmentType.CENTER,
        children: [new TextRun({ text: small, size: 15, color: MUT })] }),
    ],
  });
}
const statTable = new Table({
  width: { size: 9350, type: WidthType.DXA },
  columnWidths: [2337, 2337, 2337, 2339],
  borders: {
    top: { style: BorderStyle.SINGLE, size: 4, color: "D8D5CF" },
    bottom: { style: BorderStyle.SINGLE, size: 4, color: "D8D5CF" },
    left: { style: BorderStyle.SINGLE, size: 4, color: "D8D5CF" },
    right: { style: BorderStyle.SINGLE, size: 4, color: "D8D5CF" },
    insideHorizontal: { style: BorderStyle.SINGLE, size: 2, color: "D8D5CF" },
    insideVertical: { style: BorderStyle.SINGLE, size: 2, color: "D8D5CF" },
  },
  rows: [new TableRow({ children: [
    statCell(`${overallX.toFixed(1)}x`, "fewer context tokens"),
    statCell(`${pct.toFixed(1)}%`, "token reduction"),
    statCell(`${nTotal}`, "code symbols tested"),
    statCell(`${data.length}`, "real repositories"),
  ] })],
});

function h2(text) {
  return new Paragraph({
    spacing: { before: 160, after: 60 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: ACCENT, space: 2 } },
    children: [new TextRun({ text: text.toUpperCase(), bold: true, size: 19, color: ACCENT })],
  });
}
function body(runs) { return new Paragraph({ spacing: { after: 100 }, children: runs, alignment: AlignmentType.JUSTIFIED }); }
const bodySize = 17;

// ---- condensed sections ------------------------------------------------
const problemStatement = body([
  r("LLM coding agents that answer from raw source files suffer four compounding failures: ", { size: bodySize }),
  bold("hallucination", { size: bodySize }), r(", ", { size: bodySize }),
  bold("context bloat", { size: bodySize }), r(", ", { size: bodySize }),
  bold("runaway token usage", { size: bodySize }), r(" (hard questions can make an agent fail to converge; single runs we tested reached 300K–1.9M tokens with no answer), and ", { size: bodySize }),
  bold("sycophancy", { size: bodySize }),
  r(" (a confidently-worded wrong answer talks a correct peer agent out of its own). Codexa's structural graph and persistent memory address all four: claims are checked against the graph instead of self-reported, stale payloads are evicted by graph distance instead of a flat timer, the graph replaces raw-file reading, and disagreement is resolved by verifying claims before any free-text debate.", { size: bodySize }),
]);

const methodology = body([
  bold("Pipeline: ", { size: bodySize }),
  r("each repository is parsed with real ", { size: bodySize }),
  bold("tree-sitter", { size: bodySize }),
  r(" grammars (Python, JS, TS, TSX) into an ", { size: bodySize }),
  bold("event-sourced structural knowledge graph", { size: bodySize }),
  r(" — nodes for files/functions/classes, edges for imports/calls/dependencies — built from the real parse tree, not regex. An LLM annotation pass then writes a one-line semantic description per symbol, cached by content hash. These, plus three other memory types (semantic, episodic, procedural, organizational), persist in a shared store. ", { size: bodySize }),
  bold("Measurement: ", { size: bodySize }),
  r("a deterministic, model-free comparison (tiktoken cl100k_base) isolates the graph as the only variable — graph retrieval resolves a symbol's definition and callers in one lookup; raw retrieval opens every file needed for the same facts. An earlier agentic benchmark across 3 LLMs was abandoned once every arm thrashed without converging.", { size: bodySize }),
]);

// ---- results table -------------------------------------------------------
function tCell(text, opts = {}) {
  return new TableCell({
    width: { size: opts.w || 1870, type: WidthType.DXA },
    shading: opts.fill ? { type: ShadingType.CLEAR, fill: opts.fill } : undefined,
    margins: { top: 40, bottom: 40, left: 80, right: 80 },
    verticalAlign: VerticalAlign.CENTER,
    children: [new Paragraph({
      alignment: opts.right ? AlignmentType.RIGHT : AlignmentType.LEFT,
      children: [new TextRun({ text, size: 15, bold: !!opts.bold, color: opts.color || INK })],
    })],
  });
}
const colW = [2600, 2250, 2250, 2250];
const header = new TableRow({ children: [
  tCell("Repository", { w: colW[0], fill: ACCENT, bold: true, color: "FFFFFF" }),
  tCell("Raw tokens", { w: colW[1], fill: ACCENT, bold: true, color: "FFFFFF", right: true }),
  tCell("Graph tokens", { w: colW[2], fill: ACCENT, bold: true, color: "FFFFFF", right: true }),
  tCell("Reduction", { w: colW[3], fill: ACCENT, bold: true, color: "FFFFFF", right: true }),
] });
const rows = data.map((d, i) => new TableRow({ children: [
  tCell(d.repository, { w: colW[0], fill: i % 2 ? BG : "FFFFFF" }),
  tCell(fmt(d.raw_total_tokens), { w: colW[1], fill: i % 2 ? BG : "FFFFFF", right: true }),
  tCell(fmt(d.graph_total_tokens), { w: colW[2], fill: i % 2 ? BG : "FFFFFF", right: true }),
  tCell(`${d.overall_reduction_x.toFixed(0)}x`, { w: colW[3], fill: i % 2 ? BG : "FFFFFF", right: true, color: ACCENT, bold: true }),
] }));
const aggRow = new TableRow({ children: [
  tCell("All (aggregate)", { w: colW[0], fill: BG, bold: true }),
  tCell(fmt(rawTotal), { w: colW[1], fill: BG, bold: true, right: true }),
  tCell(fmt(graphTotal), { w: colW[2], fill: BG, bold: true, right: true }),
  tCell(`${overallX.toFixed(1)}x`, { w: colW[3], fill: BG, bold: true, right: true, color: ACCENT }),
] });
const resultsTable = new Table({
  width: { size: 9350, type: WidthType.DXA },
  columnWidths: colW,
  borders: {
    top: { style: BorderStyle.SINGLE, size: 4, color: "D8D5CF" },
    bottom: { style: BorderStyle.SINGLE, size: 4, color: "D8D5CF" },
    left: { style: BorderStyle.SINGLE, size: 4, color: "D8D5CF" },
    right: { style: BorderStyle.SINGLE, size: 4, color: "D8D5CF" },
    insideHorizontal: { style: BorderStyle.SINGLE, size: 2, color: "D8D5CF" },
    insideVertical: { style: BorderStyle.NONE },
  },
  rows: [header, ...rows, aggRow],
});

const costLine = body([
  r(`At $${priceIn.toFixed(2)}/1M input tokens, these ${nTotal} lookups cost $${(rawTotal/1e6*priceIn).toFixed(3)} raw vs. $${(graphTotal/1e6*priceIn).toFixed(3)} via the graph — scaled to 100K lookups, roughly $267 vs. $3. Raw agentic runs on the same questions reach 300K–1.9M tokens `, { size: bodySize }),
  new TextRun({ text: "without even converging", size: bodySize, italics: true }),
  r(", so the true gap is larger than shown.", { size: bodySize }),
]);

// ---- Novelty (condensed) --------------------------------------------------
const noveltyItems = [
  ["Four memory types: ", "semantic, episodic, procedural, organizational — shared across every active model."],
  ["Symbol annotations: ", "an LLM's one-line semantic gloss on top of tree-sitter's structural parse, cached by content hash."],
  ["Graph: ", "an event-sourced structural graph that answers navigation queries directly and prevents context bloat by evicting stale payloads via graph-distance, not a fixed round-count."],
  ["Blast radius: ", "reverse-dependency traversal of the graph surfacing every downstream node an edit could break, before the change is made."],
  ["Quorum: ", "agents answer independently and are checked against the graph before seeing a peer's answer; ties debate only via structured, verified belief cards — closing the sycophancy vector."],
];
const noveltyParas = noveltyItems.map(([label, rest]) => bullet([
  new TextRun({ text: label, bold: true, size: bodySize }),
  new TextRun({ text: rest, size: bodySize }),
]));

// ---- chart image ---------------------------------------------------------
const chartBuf = fs.readFileSync(CHART);
const chartImg = new Paragraph({
  alignment: AlignmentType.CENTER,
  spacing: { before: 80, after: 100 },
  children: [new ImageRun({
    type: "png", data: chartBuf,
    transformation: { width: 430, height: Math.round(430 * (934 / 2011)) },
  })],
});

const footer = new Paragraph({
  spacing: { before: 140 },
  border: { top: { style: BorderStyle.SINGLE, size: 3, color: "D8D5CF", space: 4 } },
  children: [new TextRun({
    text: "Codexa OS — engineering-intelligence platform (FastAPI + Next.js, event-sourced knowledge graph, LLM build/chat agents).",
    size: 14, color: MUT, italics: true,
  })],
});

// ---- document --------------------------------------------------------------
const doc = new Document({
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 }, // US Letter
        margin: { top: 620, bottom: 500, left: 550, right: 550 },
      },
    },
    children: [
      titlePara,
      new Paragraph({ spacing: { after: 100 }, children: [] }),
      ghChip,
      new Paragraph({ spacing: { after: 100 }, children: [] }),
      statTable,
      h2("Problem Statement"),
      problemStatement,
      h2("Methodology"),
      methodology,
      h2("Results & Insights"),
      chartImg,
      resultsTable,
      new Paragraph({ spacing: { before: 80 }, children: [] }),
      costLine,
      h2("Novelty"),
      ...noveltyParas,
      footer,
    ],
  }],
});

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync(OUT, buf);
  console.log("wrote", OUT);
});
