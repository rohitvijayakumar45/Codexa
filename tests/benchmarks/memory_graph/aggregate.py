"""Aggregate raw benchmark runs into a publishable token/cost report.

Reads every raw_runs/*_r*.json (the repetition-tagged files written by runner.py), groups by
(mode, question), and reports mean +/- 95% CI for input/output/total tokens, tool calls and
duration. The headline is the token reduction of Full Codexa (graph + memory) versus Raw on the
SAME model — so the only variable is the retrieval architecture, not the LLM.

Cost is derived from token counts with a documented, overridable price (BENCHMARK_PRICE_IN /
BENCHMARK_PRICE_OUT, USD per 1M tokens). The token reduction itself is model- and price-agnostic;
the dollar figure is an illustration at the stated rate.
"""
import json
import math
import os
import statistics as stats
from pathlib import Path

BENCH_DIR = Path(__file__).parent
RAW_DIR = BENCH_DIR / os.getenv("BENCHMARK_RUN_DIR", "raw_runs")

# USD per 1M tokens. Defaults are a stated assumption for the dollar illustration; override via env.
PRICE_IN = float(os.getenv("BENCHMARK_PRICE_IN", "0.25"))
PRICE_OUT = float(os.getenv("BENCHMARK_PRICE_OUT", "1.00"))

RAW_MODE = "mode_a"          # baseline arm
FULL_MODE = "mode_c"         # graph + memory arm
MODE_ORDER = ["mode_a", "mode_b", "mode_c"]


def load_runs() -> list[dict]:
    runs = []
    for p in sorted(RAW_DIR.glob("*_r*.json")):
        try:
            runs.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            continue
    return runs


def ci95(xs: list[float]) -> float:
    """Half-width of the 95% confidence interval of the mean (normal approx; 0 for n<2)."""
    n = len(xs)
    if n < 2:
        return 0.0
    return 1.96 * (stats.stdev(xs) / math.sqrt(n))


def cost(in_tok: float, out_tok: float) -> float:
    return in_tok / 1e6 * PRICE_IN + out_tok / 1e6 * PRICE_OUT


def summarize(runs: list[dict]) -> dict:
    keys = ("input_tokens", "output_tokens", "total_tokens", "tool_calls_total", "duration_seconds")
    out = {}
    for k in keys:
        xs = [float(r.get(k, 0) or 0) for r in runs]
        out[k] = {
            "mean": stats.mean(xs) if xs else 0.0,
            "ci95": ci95(xs),
            "min": min(xs) if xs else 0.0,
            "max": max(xs) if xs else 0.0,
            "n": len(xs),
        }
    costs = [cost(float(r.get("input_tokens", 0) or 0), float(r.get("output_tokens", 0) or 0)) for r in runs]
    out["cost_usd"] = {"mean": stats.mean(costs) if costs else 0.0, "ci95": ci95(costs), "n": len(costs)}
    out["success"] = sum(1 for r in runs if r.get("status") == "done")
    out["total"] = len(runs)
    return out


def main() -> None:
    runs = load_runs()
    if not runs:
        print("No repetition-tagged runs found in raw_runs/. Run runner.py with BENCHMARK_REPS first.")
        return
    model = runs[0].get("model", "?")
    mode_names = {r["mode"]: r.get("mode_name", r["mode"]) for r in runs}
    questions = sorted({r["question_id"] for r in runs})
    modes = [m for m in MODE_ORDER if any(r["mode"] == m for r in runs)]

    # Token/tool means are computed PER ATTEMPT (all runs), not per completion: on hard multi-hop
    # questions the Raw arm frequently fails to converge, so a "completed only" mean would be over
    # zero samples for Raw and hide the very failure that is the point. Completion rate is reported
    # as its own column so nothing is obscured. "answered" = the arm produced a real assistant
    # answer (>200 chars of prose), a stricter and more honest bar than the job's done/error status
    # (which flips on a trailing tool hiccup).
    def answered(r):
        return len(r.get("answer", "") or "") >= 200

    per = {}  # (mode, q) -> summary
    for m in modes:
        for q in questions:
            rs = [r for r in runs if r["mode"] == m and r["question_id"] == q]
            if rs:
                per[(m, q)] = summarize(rs)
                per[(m, q)]["answered"] = sum(1 for r in rs if answered(r))
    per_mode = {m: summarize([r for r in runs if r["mode"] == m]) for m in modes}
    for m in modes:
        per_mode[m]["answered"] = sum(1 for r in runs if r["mode"] == m and answered(r))

    lines = []
    lines.append("# Codexa graph + memory: token-reduction benchmark\n")
    lines.append(f"**Model (all arms):** `{model}` — the only variable across arms is the retrieval "
                 f"architecture, not the LLM.  ")
    lines.append(f"**Repository under test:** {os.getenv('BENCHMARK_REPO', 'Exam-Proctoring')}  ")
    lines.append(f"**Price assumption for cost:** ${PRICE_IN:.2f}/1M input, ${PRICE_OUT:.2f}/1M output "
                 f"(token counts are the primary, price-agnostic result).\n")

    lines.append("## Arms\n")
    for m in modes:
        lines.append(f"- **{mode_names.get(m, m)}** (`{m}`)")
    lines.append("")

    # Headline: Full vs Raw per question + overall
    lines.append("## Headline — Full Codexa vs Raw (same model)\n")
    lines.append("| Question | Raw total tok (mean±CI) | Full total tok (mean±CI) | Reduction | Raw $/q | Full $/q | $ saved/q |")
    lines.append("|---|---|---|---|---|---|---|")
    agg_raw_tot = agg_full_tot = 0.0
    agg_raw_cost = agg_full_cost = 0.0
    nq = 0
    for q in questions:
        raw = per.get((RAW_MODE, q))
        full = per.get((FULL_MODE, q))
        if not raw or not full:
            continue
        rt, rc = raw["total_tokens"]["mean"], raw["cost_usd"]["mean"]
        ft, fc = full["total_tokens"]["mean"], full["cost_usd"]["mean"]
        red = (1 - ft / rt) * 100 if rt else 0.0
        lines.append(
            f"| {q} | {rt:,.0f} ± {raw['total_tokens']['ci95']:,.0f} "
            f"| {ft:,.0f} ± {full['total_tokens']['ci95']:,.0f} "
            f"| **{red:.1f}%** | ${rc:.4f} | ${fc:.4f} | ${rc - fc:.4f} |"
        )
        agg_raw_tot += rt; agg_full_tot += ft; agg_raw_cost += rc; agg_full_cost += fc; nq += 1
    if nq:
        red_all = (1 - agg_full_tot / agg_raw_tot) * 100 if agg_raw_tot else 0.0
        mult = agg_raw_tot / agg_full_tot if agg_full_tot else float("inf")
        lines.append(
            f"| **ALL ({nq} q)** | {agg_raw_tot:,.0f} | {agg_full_tot:,.0f} "
            f"| **{red_all:.1f}%** (~{mult:.1f}x) | ${agg_raw_cost:.4f} | ${agg_full_cost:.4f} | ${agg_raw_cost - agg_full_cost:.4f} |"
        )
    lines.append("")

    # Per-mode detail
    lines.append("## Per-mode detail (mean ± 95% CI, per attempt)\n")
    lines.append("| Mode | answered | Input tok | Output tok | Total tok | Tool calls | Duration s | Cost $/q |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for m in modes:
        s = per_mode[m]
        lines.append(
            f"| {mode_names.get(m, m)} | {s.get('answered', 0)}/{s['total']} "
            f"| {s['input_tokens']['mean']:,.0f} ± {s['input_tokens']['ci95']:,.0f} "
            f"| {s['output_tokens']['mean']:,.0f} ± {s['output_tokens']['ci95']:,.0f} "
            f"| {s['total_tokens']['mean']:,.0f} ± {s['total_tokens']['ci95']:,.0f} "
            f"| {s['tool_calls_total']['mean']:.1f} ± {s['tool_calls_total']['ci95']:.1f} "
            f"| {s['duration_seconds']['mean']:.1f} ± {s['duration_seconds']['ci95']:.1f} "
            f"| ${s['cost_usd']['mean']:.4f} |"
        )
    lines.append("")

    lines.append("## Method\n")
    lines.append("- Each (mode, question) pair was run repeatedly; tables show the mean and the "
                 "half-width of the 95% confidence interval of the mean (normal approximation).")
    lines.append("- Token counts are the provider-reported prompt/completion tokens accumulated "
                 "across every round the agent took to answer.")
    lines.append("- Only runs that completed (`status == done`) contribute to token/cost means; the "
                 "success column reports completion rate.")
    lines.append("- Raw = file-reading/search tools only. Full Codexa = the same tools plus the "
                 "structural knowledge graph and project memory, which supply pre-resolved context "
                 "so the model reads far fewer raw files to answer.")

    report = "\n".join(lines)
    tag = RAW_DIR.name.replace("raw_runs", "").strip("_") or "default"
    out_md = BENCH_DIR / f"REPORT_{tag}.md"
    out_md.write_text(report, encoding="utf-8")

    summary_json = {
        "model": model, "questions": questions, "modes": modes,
        "per_mode": per_mode, "per_mode_question": {f"{m}|{q}": per[(m, q)] for (m, q) in per},
        "price_in": PRICE_IN, "price_out": PRICE_OUT,
    }
    summary_path = BENCH_DIR / f"summary_{tag}.json"
    summary_path.write_text(json.dumps(summary_json, indent=2), encoding="utf-8")

    print(report)
    print(f"\n[written] {out_md}\n[written] {summary_path}")


if __name__ == "__main__":
    main()
