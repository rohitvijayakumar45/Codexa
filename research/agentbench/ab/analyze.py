"""Pilot / full analysis for RQ4.

Per condition: success rate (with a task-cluster bootstrap CI), mean tokens, tokens-to-success
(total tokens spent / successes, Xu 2026), steps, tool mix. Per target type. Rep-to-rep agreement
(variance estimate for sizing the full study). And the payload→agent link: each condition's NavBench
payload metrics on the same targets (complete %, MSA tokens) next to its agent outcomes.

Usage: python -m ab.analyze <results.jsonl> [--navbench-scored <scored.jsonl>] [--out report.md]
"""
from __future__ import annotations

import json
import random
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

ARM_OF = {"lsp": "lsp", "codexa": "codexa_refs", "codexa2": "codexa2_refs", "rg": "rg0"}


def load(p: Path, include_invalid: bool = False) -> list[dict]:
    """Rows of a results.jsonl. The last row per (task, condition, rep) wins (resumed runs append), and
    runs that died on a provider error are dropped: they say nothing about the condition."""
    last: dict[tuple, dict] = {}
    for l in open(p, encoding="utf-8"):
        if l.strip():
            r = json.loads(l)
            last[(r["task"], r["condition"], r["rep"])] = r
    rows = list(last.values())
    return rows if include_invalid else [r for r in rows if not r.get("error")]


def boot_ci(groups: dict[str, list[float]], stat=st.mean, b: int = 2000, seed: int = 1) -> tuple[float, float]:
    rng = random.Random(seed)
    keys = list(groups)
    vals = []
    for _ in range(b):
        sample = [x for k in (rng.choice(keys) for _ in keys) for x in groups[k]]
        if sample:
            vals.append(stat(sample))
    vals.sort()
    return vals[int(0.025 * len(vals))], vals[int(0.975 * len(vals)) - 1]


def summarize(rows: list[dict]) -> dict:
    by_c: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_c[r["condition"]].append(r)
    out = {}
    for c, rs in sorted(by_c.items()):
        g: dict[str, list[float]] = defaultdict(list)
        for r in rs:
            g[r["task"]].append(1.0 if r["success"] else 0.0)
        succ = sum(r["success"] for r in rs)
        tok = sum(r["total_tokens"] for r in rs)
        tools = defaultdict(int)
        for r in rs:
            for k, v in r["tool_calls"].items():
                tools[k] += v
        out[c] = {"runs": len(rs), "success": succ / len(rs), "success_ci": boot_ci(g),
                  "mean_tokens": tok / len(rs), "tokens_to_success": tok / succ if succ else float("inf"),
                  "mean_steps": st.mean(r["steps"] for r in rs),
                  "sites_recall": st.mean(r["sites_updated"] / max(1, r["sites_total"]) for r in rs),
                  "find_callers_calls": tools.get("find_callers", 0) / len(rs),
                  "search_calls": tools.get("search", 0) / len(rs),
                  "errors": sum(1 for r in rs if r.get("error"))}
    return out


def by_target(rows: list[dict]) -> dict:
    t: dict[tuple, list[bool]] = defaultdict(list)
    for r in rows:
        t[(r["target"], r["condition"])].append(r["success"])
    return {f"{k[0]}|{k[1]}": sum(v) / len(v) for k, v in sorted(t.items())}


def rep_agreement(rows: list[dict]) -> float | None:
    g: dict[tuple, list[bool]] = defaultdict(list)
    for r in rows:
        g[(r["task"], r["condition"])].append(r["success"])
    pairs = [v for v in g.values() if len(v) >= 2]
    return st.mean(1.0 if len(set(v)) == 1 else 0.0 for v in pairs) if pairs else None


def payload_link(rows: list[dict], scored: list[dict]) -> dict:
    """Join agent outcomes with NavBench payload metrics of the same (fixture, target)."""
    pay = {}
    for r in scored:
        if r.get("task") == "T1" and r.get("layer") == "fixture":
            pay[(r["repo"], r["arm"], r["target"])] = r
    out = {}
    for c, arm in ARM_OF.items():
        rs = [r for r in rows if r["condition"] == c]
        comp, tok = [], []
        for r in rs:
            repo = r["task"].split(":")[0]
            match = [v for (rp, a, _t), v in pay.items() if rp == repo and a == arm]
            if match:
                comp.append(st.mean(1.0 if m.get("A_complete") else 0.0 for m in match))
                tok.append(st.mean(m.get("tok_msa_cl100k") or 0 for m in match))
        if rs:
            out[c] = {"agent_success": st.mean(1.0 if r["success"] else 0.0 for r in rs),
                      "payload_complete": st.mean(comp) if comp else None,
                      "payload_msa_tokens": st.mean(tok) if tok else None}
    return out


def to_md(s: dict, bt: dict, agree, link: dict | None) -> str:
    L = ["| condition | runs | success [95% CI] | mean tokens | tokens/success | steps | sites recall | find_callers/run | search/run | errors |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for c, r in s.items():
        lo, hi = r["success_ci"]
        L.append(f"| {c} | {r['runs']} | {100*r['success']:.0f}% [{100*lo:.0f}, {100*hi:.0f}] | {r['mean_tokens']:.0f} | "
                 f"{r['tokens_to_success']:.0f} | {r['mean_steps']:.1f} | {r['sites_recall']:.2f} | "
                 f"{r['find_callers_calls']:.1f} | {r['search_calls']:.1f} | {r['errors']} |")
    L += ["", f"Rep-to-rep agreement on success: {agree:.2f}" if agree is not None else "", "", "| target | " + " | ".join(s) + " |",
          "|---|" + "---|" * len(s)]
    targets = sorted({k.split("|")[0] for k in bt})
    for t in targets:
        L.append(f"| {t} | " + " | ".join(f"{100*bt.get(f'{t}|{c}', float('nan')):.0f}%" for c in s) + " |")
    if link:
        L += ["", "| condition | agent success | payload complete (NavBench) | payload MSA tokens |", "|---|---|---|---|"]
        for c, v in link.items():
            pc = "–" if v["payload_complete"] is None else f"{100*v['payload_complete']:.0f}%"
            pt = "–" if v["payload_msa_tokens"] is None else f"{v['payload_msa_tokens']:.0f}"
            L.append(f"| {c} | {100*v['agent_success']:.0f}% | {pc} | {pt} |")
    return "\n".join(L)


if __name__ == "__main__":
    rows = load(Path(sys.argv[1]))
    n_all = len(load(Path(sys.argv[1]), include_invalid=True))
    scored = None
    if "--navbench-scored" in sys.argv:
        sp = Path(sys.argv[sys.argv.index("--navbench-scored") + 1])
        scored = [json.loads(l) for l in open(sp, encoding="utf-8") if l.strip()]
    s = summarize(rows)
    md = (f"Valid runs: {len(rows)} of {n_all} (runs that ended on a provider error are excluded).\n\n"
          + to_md(s, by_target(rows), rep_agreement(rows), payload_link(rows, scored) if scored else None))
    if "--out" in sys.argv:
        Path(sys.argv[sys.argv.index("--out") + 1]).write_text(md, encoding="utf-8")
    print(md)
