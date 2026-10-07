"""Paper figures (static). Usage: python -m nb.figures <scored.jsonl> <out_dir>

Palette: validated two-slot categorical (#2a78d6 blue, #eb6834 orange); identity is always also carried
by marker shape and direct labels; text in ink colours; one axis per panel.
"""
from __future__ import annotations

import json
import math
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker  # noqa: E402,F401

BLUE, ORANGE = "#2a78d6", "#eb6834"
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"
ARMS = ["rg0", "rg3", "lsp", "codexa_refs", "codexa_orig", "cbm_cur", "cbm_057"]
LABEL = {"rg0": "ripgrep -w", "rg3": "ripgrep -w -C3", "lsp": "language server", "codexa_refs": "Codexa find_references",
         "codexa_orig": "Codexa lookup+deps", "cbm_cur": "codebase-memory (current)", "cbm_057": "codebase-memory (v0.5.7)"}
GRAPH = ["codexa_refs", "codexa_orig", "cbm_cur", "cbm_057"]
OFFS = {"py": {"rg0": (-5, 5, "right"), "rg3": (0, 7, "center"), "lsp": (0, -12, "center"), "cbm_cur": (0, 7, "center"),
               "cbm_057": (5, 2, "left"), "codexa_refs": (5, 2, "left"), "codexa_orig": (5, 2, "left")},
        "ts": {"rg0": (-5, 5, "right"), "rg3": (0, 7, "center"), "lsp": (0, 7, "center"), "cbm_cur": (0, -12, "center"),
               "cbm_057": (5, 2, "left"), "codexa_refs": (5, 2, "left"), "codexa_orig": (5, 2, "left")}}

plt.rcParams.update({"font.size": 8, "axes.edgecolor": INK2, "axes.labelcolor": INK, "xtick.color": INK2,
                     "ytick.color": INK2, "axes.spines.top": False, "axes.spines.right": False, "font.family": "DejaVu Sans"})


def load(p):
    return [json.loads(l) for l in open(p)]


def save(fig, out, name):
    fig.savefig(out / f"{name}.pdf", bbox_inches="tight")
    fig.savefig(out / f"{name}.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def fig_q1(rows, out):
    """Per-repository geometric-mean ratio of baseline payload to graph-arm payload (S-ind, non-empty graph answers)."""
    N = [r for r in rows if r["layer"] == "natural" and r["task"] == "T1" and r["sample"] == "S-ind"]
    by = defaultdict(dict)
    for r in N:
        by[(r["repo"], r["target"])][r["arm"]] = r
    baselines = [("whole files (graph-selected)", None, "wholefile_graphsel_tokens"),
                 ("whole files (provider-selected)", None, "wholefile_provider_tokens"),
                 ("ripgrep -w -C3", "rg3", "tok_native_cl100k"), ("ripgrep -w", "rg0", "tok_native_cl100k"),
                 ("language server (LSP JSON)", "lsp", "tok_native_cl100k"), ("language server (location form)", "lsp", "tok_loc_cl100k")]
    fig, axes = plt.subplots(1, len(GRAPH), figsize=SIZES["fig1"], sharey=True, sharex=True)
    for ax, g in zip(axes, GRAPH):
        for yi, (lab, arm, key) in enumerate(baselines):
            per_repo = defaultdict(list)
            for (repo, t), arms in by.items():
                gr = arms.get(g)
                if not gr or gr["status"] != "ok" or not gr["tok_native_cl100k"]:
                    continue
                src = gr if arm is None else arms.get(arm)
                if not src or not src.get(key):
                    continue
                per_repo[(repo, gr["lang"])].append(math.log(src[key] / gr["tok_native_cl100k"]))
            xs = [(math.exp(st.mean(v)), lang) for (repo, lang), v in per_repo.items() if v]
            for x, lang in xs:
                ax.scatter(x, yi + (0.12 if lang == "ts" else -0.12), s=12, c=BLUE if lang == "py" else ORANGE,
                           marker="o" if lang == "py" else "^", linewidths=0, zorder=3)
            if xs:
                gm = math.exp(st.mean([math.log(x) for x, _ in xs]))
                ax.plot([gm, gm], [yi - 0.32, yi + 0.32], color=INK, lw=2, zorder=4)
        ax.axvline(1, color=INK2, lw=0.8, ls="--")
        ax.set_xscale("log")
        ax.set_title(SHORT.get(g, LABEL[g]), fontsize=plt.rcParams["font.size"] + 0.5, color=INK)
        ax.grid(axis="x", color=GRID, lw=0.6)
        ax.set_yticks(range(len(baselines)))
        ax.set_yticklabels([b[0] for b in baselines])
    axes[0].scatter([], [], c=BLUE, marker="o", s=12, label="Python repo")
    axes[0].scatter([], [], c=ORANGE, marker="^", s=12, label="TS/JS repo")
    axes[0].plot([], [], color=INK, lw=2, label="geo-mean of repos")
    fig.supxlabel("baseline tokens ÷ graph-tool tokens (log scale; dashed line = equal size)",
                  fontsize=plt.rcParams["font.size"] + 0.5, y=0.02)
    fig.legend(*axes[0].get_legend_handles_labels(), loc="lower center", ncol=3, fontsize=plt.rcParams["font.size"],
               frameon=False, bbox_to_anchor=(0.5, -0.1))
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    save(fig, out, "fig1_q1_baselines")


def fig_layerA(rows, out):
    """Held-out fixtures: mean native tokens vs mean caller recall per arm (repo-macro), per language."""
    A = [r for r in rows if r["layer"] == "fixture" and r.get("split") != "calib" and r["task"] == "T1" and r.get("A_n_gold")]
    fig, axes = plt.subplots(1, 2, figsize=SIZES["fig2"], sharey=True)
    markers = {"rg0": "o", "rg3": "o", "lsp": "s", "codexa_refs": "D", "codexa_orig": "D", "cbm_cur": "^", "cbm_057": "^"}
    for ax, lang, col in ((axes[0], "py", BLUE), (axes[1], "ts", ORANGE)):
        for arm in ARMS:
            s = [r for r in A if r["lang"] == lang and r["arm"] == arm]
            if not s:
                continue
            per = defaultdict(list)
            for r in s:
                per[r["repo"]].append(r)
            rec = st.mean([st.mean([x["A_caller_recall"] for x in v]) for v in per.values()])
            tok = st.mean([st.mean([x["tok_native_cl100k"] for x in v]) for v in per.values()])
            ax.scatter(tok, rec, s=34, marker=markers[arm], c=col, edgecolors="white", linewidths=1.2, zorder=3)
            dx, dy, ha = OFFS[lang].get(arm, (4, 3, "left"))
            ax.annotate(LABEL[arm], (tok, rec), xytext=(dx, dy), textcoords="offset points", fontsize=6.5, color=INK, ha=ha)
        ax.set_xscale("log")
        ax.set_xticks([50, 100, 200, 400])
        ax.get_xaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
        ax.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
        ax.set_xlim(35, 700)
        ax.set_ylim(0, 1.05)
        ax.grid(color=GRID, lw=0.6)
        ax.set_title("Python fixtures" if lang == "py" else "TypeScript fixtures", fontsize=8)
        ax.set_xlabel("native output tokens per query (cl100k, mean)")
    axes[0].set_ylabel("caller-level recall (mean)")
    save(fig, out, "fig2_layerA_operating_points")


def fig_q2(rows, out):
    """S-cond (graph-conditioned) vs S-ind (independent): non-empty answer rate per arm, repo-macro."""
    N = [r for r in rows if r["layer"] == "natural" and r["task"] == "T1"]
    fig, ax = plt.subplots(figsize=SIZES["fig3"])
    for yi, arm in enumerate(ARMS[::-1]):
        vals = {}
        for samp in ("S-cond", "S-ind"):
            per = defaultdict(list)
            for r in N:
                if r["arm"] == arm and r["sample"] == samp:
                    per[r["repo"]].append(1.0 if r["status"] == "ok" else 0.0)
            if per:
                vals[samp] = 100 * st.mean([st.mean(v) for v in per.values()])
        if len(vals) == 2:
            ax.plot([vals["S-ind"], vals["S-cond"]], [yi, yi], color=GRID, lw=2, zorder=1)
        if "S-cond" in vals:
            ax.scatter(vals["S-cond"], yi, c=BLUE, marker="o", s=24, zorder=3, edgecolors="white", linewidths=1)
        if "S-ind" in vals:
            ax.scatter(vals["S-ind"], yi, c=ORANGE, marker="s", s=24, zorder=3, edgecolors="white", linewidths=1)
    ax.set_yticks(range(len(ARMS)))
    ax.set_yticklabels([LABEL[a] for a in ARMS[::-1]])
    ax.set_xlim(0, 105)
    ax.set_xlabel("queries with a non-empty answer (%)")
    ax.grid(axis="x", color=GRID, lw=0.6)
    ax.scatter([], [], c=BLUE, marker="o", s=24, label="graph-conditioned sample (S-cond)")
    ax.scatter([], [], c=ORANGE, marker="s", s=24, label="independent sample (S-ind)")
    ax.legend(loc="lower left", fontsize=6.5, frameon=False)
    save(fig, out, "fig3_q2_sampling")


SIZES = {"fig1": (10.5, 2.8), "fig2": (7.2, 3.0), "fig3": (4.6, 2.8)}
SHORT = {"cbm_cur": "codebase-memory (current)", "cbm_057": "codebase-memory v0.5.7"}
ANON = {"codexa_refs": "G1 find_references", "codexa_orig": "G1 lookup+deps"}

if __name__ == "__main__":
    import os
    if os.environ.get("NB_ANON"):  # double-anonymous submission: the authors' own prototype is not named
        LABEL.update(ANON)
        SHORT.update({"cbm_cur": "cbm (current)", "cbm_057": "cbm v0.5.7"})
        SIZES.update({"fig1": (7.3, 2.3), "fig2": (3.5, 2.2), "fig3": (3.5, 2.2)})
        plt.rcParams.update({"font.size": 6.2})
    rows = load(sys.argv[1])
    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    fig_q1(rows, out)
    fig_layerA(rows, out)
    fig_q2(rows, out)
    print("figures written to", out)
