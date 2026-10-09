"""Render replay (Experiment A) and annotation-budget (Experiment B) result JSONs as Markdown tables.

  python tests/benchmarks/memory_anchoring/report.py \
      --replay tests/benchmarks/memory_anchoring/results \
      --budget tests/benchmarks/annotation_budget/results \
      --out docs/research/anchored_memory_results.md
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

_POLICY_LABEL = {
    "A0_never": "A0 never invalidate", "A1_repo": "A1 repo-level wipe", "A2_file": "A2 file anchors",
    "A3_symbol": "A3 symbol anchors", "A4_neighborhood": "A4 symbol + 1-hop files",
    "A5_query": "A5 graph-query anchors",
}
_COUNTS = ("tp", "fp", "fn", "tn", "anchors_total")


def _f(x: Any) -> str:
    return "–" if x is None else f"{x:.3f}"


def _metrics(tp: int, fp: int, fn: int, tn: int, anchors: float) -> dict[str, Any]:
    n = tp + fp + fn + tn
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    return {
        "n": n, "prevalence": (tp + fn) / n if n else None, "precision": p, "recall": r,
        "f1": 2 * p * r / (p + r) if p is not None and r is not None and p + r else None,
        "fir": fp / (fp + tn) if fp + tn else None, "ssr": fn / (tp + fn) if tp + fn else None,
        "anchors": anchors / n if n else None,
    }


def _pool(rows: list[dict[str, Any]]) -> dict[str, Any]:
    tot = defaultdict(float)
    for m in rows:
        for c in ("tp", "fp", "fn", "tn"):
            tot[c] += m[c]
        tot["anchors_total"] += (m.get("mean_anchors") or 0) * m["n"]
    return _metrics(int(tot["tp"]), int(tot["fp"]), int(tot["fn"]), int(tot["tn"]), tot["anchors_total"])


def _table(title: str, rows: dict[str, dict[str, Any]]) -> list[str]:
    out = [f"#### {title}", "",
           "| Policy | n | stale % | Precision | Recall | F1 | False-invalidation | Stale-served | Anchors/record |",
           "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for pol, m in rows.items():
        prev = "–" if m["prevalence"] is None else f"{100 * m['prevalence']:.1f}"
        out.append(f"| {_POLICY_LABEL.get(pol, pol)} | {m['n']} | {prev} | {_f(m['precision'])} | {_f(m['recall'])} | "
                   f"{_f(m['f1'])} | {_f(m['fir'])} | {_f(m['ssr'])} | {_f(m['anchors'])} |")
    return out + [""]


def replay_section(files: list[Path]) -> list[str]:
    data = [json.loads(p.read_text(encoding="utf-8")) for p in files]
    if not data:
        return []
    lines = ["## Experiment A — memory invalidation under git-history replay", ""]
    lines.append("Repositories: " + ", ".join(
        f"{d['repo']} ({len(d['pairs'])} commit pairs)" for d in data) + ".")
    lines.append("")
    policies = list(data[0]["overall"])
    pooled = {pol: _pool([d["overall"][pol] for d in data if pol in d["overall"]]) for pol in policies}
    lines += _table("Pooled over all repositories, k and fact types", pooled)
    facts = sorted({ft for d in data for ft in d.get("by_fact", {})})
    for ft in facts:
        rows = {pol: _pool([d["by_fact"][ft][pol] for d in data if ft in d.get("by_fact", {})
                            and pol in d["by_fact"][ft]]) for pol in policies}
        lines += _table(f"Fact type {ft} (pooled)", rows)
    ks = sorted({int(k) for d in data for k in d["by_k"]})
    lines += ["#### F1 by commit distance k (pooled over fact types)", "",
              "| Policy | " + " | ".join(f"k={k}" for k in ks) + " |", "|---|" + "---:|" * len(ks)]
    for pol in policies:
        cells = []
        for k in ks:
            rows = [d["by_k"][str(k)][ft][pol] for d in data if str(k) in d["by_k"]
                    for ft in d["by_k"][str(k)] if pol in d["by_k"][str(k)][ft]]
            cells.append(_f(_pool(rows)["f1"]) if rows else "–")
        lines.append(f"| {_POLICY_LABEL.get(pol, pol)} | " + " | ".join(cells) + " |")
    lines.append("")
    for d in data:
        lines += _table(f"{d['repo']} — overall", {pol: _pool([m]) for pol, m in d["overall"].items()})
    return lines


def budget_section(files: list[Path]) -> list[str]:
    data = [json.loads(p.read_text(encoding="utf-8")) for p in files]
    if not data:
        return []
    lines = ["## Experiment B — annotation budget vs. future demand", ""]
    for d in data:
        cfg = d["config"]
        labels = [t.strip().lower() for t in cfg["budgets"].split(",") if t.strip()]
        mean_syms = sum(b["symbols"] for b in d["per_base"]) / max(1, len(d["per_base"]))
        mean_edit = sum(b["d_edit"] for b in d["per_base"]) / max(1, len(d["per_base"]))
        lines.append(f"### {d['repo']} — {len(d['per_base'])} commits, horizon {cfg['horizon']}, "
                     f"mean {mean_syms:.0f} symbols, mean |D_edit| {mean_edit:.1f}")
        lines.append("")
        for metric, label in (("coverage_edit", "Coverage of D_edit (symbols edited next)"),
                              ("coverage_file", "Coverage of D_file (symbols in files edited next)"),
                              ("invalidated_share", "Share of the K annotations invalidated within the horizon")):
            lines += [f"#### {label}", "", "| Policy | " + " | ".join(f"K={l}" for l in labels) + " |",
                      "|---|" + "---:|" * len(labels)]
            for policy, by_k in d["summary"].items():
                lines.append(f"| {policy} | " + " | ".join(_f(by_k.get(l, {}).get(metric)) for l in labels) + " |")
            lines.append("")
        if "gold" in d:
            g = d["gold"]
            lines += [f"#### Gold-question coverage ({g['questions']} questions)", "",
                      "| Policy | " + " | ".join(f"K={l}" for l in labels) + " |", "|---|" + "---:|" * len(labels)]
            for policy, by_k in g["policies"].items():
                lines.append(f"| {policy} | " + " | ".join(_f(by_k.get(l)) for l in labels) + " |")
            lines.append("")
    return lines


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--replay", help="directory of replay result JSONs")
    ap.add_argument("--budget", help="directory of annotation-budget result JSONs")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    lines = ["# Anchored memory & annotation budget — results", "",
             "Generated by `tests/benchmarks/memory_anchoring/report.py`. Method and definitions: "
             "[anchored_memory_experiments.md](anchored_memory_experiments.md).", ""]
    if args.replay:
        lines += replay_section(sorted(Path(args.replay).glob("*.json")))
    if args.budget:
        lines += budget_section(sorted(Path(args.budget).glob("*.json")))
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
