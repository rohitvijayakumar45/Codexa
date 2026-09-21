"""Compact chart for the one-page PDF report: raw vs graph tokens per repo (log scale) +
reduction factor labels. Reads the per-repo JSON results already produced by
retrieval_payload.py (tests/benchmarks/memory_graph/payload_results/*.json)."""
import json
import glob
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

HERE = Path(__file__).parent
RESULTS = HERE.parent / "payload_results"

files = sorted(glob.glob(str(RESULTS / "*.json")))
data = [json.load(open(f, encoding="utf-8")) for f in files]
data.sort(key=lambda d: d["overall_reduction_x"])

repos = [d["repository"] for d in data]
raw = [d["raw_total_tokens"] for d in data]
graph = [d["graph_total_tokens"] for d in data]
red = [d["overall_reduction_x"] for d in data]

INK = "#1a1a1a"
MUT = "#6b6b6b"
RAW_C = "#c85a17"
GPH_C = "#2a7d4a"

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["DejaVu Sans", "Arial"],
    "text.color": INK,
    "axes.edgecolor": "#d8d5cf",
    "axes.labelcolor": MUT,
    "xtick.color": MUT,
    "ytick.color": MUT,
})

fig, ax = plt.subplots(figsize=(6.6, 2.85), dpi=300)
y = range(len(repos))
bar_h = 0.32

ax.barh([i + bar_h / 2 for i in y], raw, height=bar_h, color=RAW_C, label="Raw file read")
ax.barh([i - bar_h / 2 for i in y], graph, height=bar_h, color=GPH_C, label="Graph retrieval")

ax.set_xscale("log")
ax.set_xlim(100, 2_000_000)
ax.set_yticks(list(y))
ax.set_yticklabels(repos, fontsize=8)
ax.set_xlabel("Context tokens to answer (log scale)", fontsize=7.5)
ax.tick_params(axis="x", labelsize=7)
for spine in ("top", "right", "left"):
    ax.spines[spine].set_visible(False)
ax.spines["bottom"].set_color("#d8d5cf")

for i, (r, g, x) in enumerate(zip(raw, graph, red)):
    ax.text(max(r, g) * 1.4, i, f"{x:.0f}x fewer", va="center", fontsize=7.3,
            color=GPH_C, fontweight="bold")

fig.legend(loc="upper center", bbox_to_anchor=(0.42, 1.06), ncol=2, fontsize=7.3, frameon=False)
fig.tight_layout(pad=0.4, rect=(0, 0, 1, 0.94))
out = HERE / "chart.png"
fig.savefig(out, dpi=300, bbox_inches="tight", transparent=False, facecolor="white")
print("wrote", out)
