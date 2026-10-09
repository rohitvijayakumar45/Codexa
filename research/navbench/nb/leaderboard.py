"""Leaderboard over scored rows (feature C), one table per (layer, task).

Repository-macro means (every repository weighs the same), sample sizes, and three token columns:
native output, the common location form, and the minimal sufficient answer (MSA, feature B) — the
last holds information content fixed, so its differences are differences in what was found.
"Tokens / complete" divides all tokens spent by the number of complete answers, so a tool that is
cheap because it is often incomplete is not rewarded. Pareto marks arms not dominated on
(mean native tokens, complete %). Unsupported arms (tool not installed) are listed, not scored.

Usage: python -m nb.leaderboard <scored.jsonl[.gz]> <out_dir>
"""
from __future__ import annotations

import json
import math
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

NB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(NB_ROOT))

from nb.offline import read_rows  # noqa: E402

QUALITY = {
    ("fixture", "T1"): ("A_caller_recall", "A_caller_precision", "A_complete", "A_n_gold"),
    ("fixture", "T3"): ("T3_caller_recall", "T3_caller_precision", "T3_complete", "T3_n_gold"),
    ("natural", "T1"): ("C_caller_recall", "C_caller_precision", "C_complete", "C_n_gold"),
}


def _macro(groups: dict[str, list], key) -> float | None:
    per = []
    for rs in groups.values():
        xs = [key(r) for r in rs]
        xs = [x for x in xs if x is not None]
        if xs:
            per.append(st.mean(xs))
    return st.mean(per) if per else None


def table(rows: list[dict], layer: str, task: str) -> list[dict]:
    sel = [r for r in rows if r.get("layer") == layer and r.get("task") == task]
    by_arm: dict[str, list[dict]] = defaultdict(list)
    for r in sel:
        by_arm[r["arm"]].append(r)
    q = QUALITY.get((layer, task))
    out = []
    for arm, rs in sorted(by_arm.items()):
        if all(r.get("status") == "unsupported" for r in rs):
            out.append({"arm": arm, "unsupported": True, "note": rs[0].get("note", "")})
            continue
        if q:
            rs_q = [r for r in rs if (r.get(q[3]) or 0) > 0]  # targets with gold (explicit sites / observed calls)
        elif task == "T2":
            rs_q = [r for r in rs if r.get("T2_hit") is not None]
        else:
            rs_q = rs
        groups: dict[str, list] = defaultdict(list)
        for r in rs_q:
            groups[r["repo"]].append(r)
        row = {"arm": arm, "n": len(rs_q), "repos": len(groups),
               "non_empty": _macro(groups, lambda r: 1.0 if (r.get("status") == "ok" and r.get("n_units")) else 0.0),
               "tok_native": _macro(groups, lambda r: r.get("tok_native_cl100k")),
               "tok_loc": _macro(groups, lambda r: r.get("tok_loc_cl100k")),
               "tok_msa": _macro(groups, lambda r: r.get("tok_msa_cl100k"))}
        if q:
            row["recall"] = _macro(groups, lambda r: r.get(q[0]))
            row["precision"] = _macro(groups, lambda r: r.get(q[1]))
            row["complete"] = _macro(groups, lambda r: (1.0 if r.get(q[2]) else 0.0) if r.get(q[0]) is not None else None)
            n_c = sum(1 for r in rs_q if r.get(q[2]))
            row["tokens_per_complete"] = (sum(r.get("tok_native_cl100k") or 0 for r in rs_q) / n_c) if n_c else math.inf
        elif task == "T2":
            row["hit"] = _macro(groups, lambda r: 1.0 if r.get("T2_hit") else 0.0)
            row["precision"] = _macro(groups, lambda r: r.get("T2_precision"))
        out.append(row)
    scored = [r for r in out if not r.get("unsupported") and r.get("complete") is not None and r.get("tok_native") is not None]
    for a in scored:
        a["pareto"] = not any(
            b is not a and b["tok_native"] <= a["tok_native"] and b["complete"] >= a["complete"]
            and (b["tok_native"] < a["tok_native"] or b["complete"] > a["complete"]) for b in scored)
    return out


def _f(x, pct=False, nd=2):
    if x is None:
        return "–"
    if x == math.inf:
        return "∞"
    return f"{100 * x:.1f}" if pct else (f"{x:.0f}" if nd == 0 else f"{x:.{nd}f}")


def to_markdown(tables: dict) -> str:
    out = ["# NavBench leaderboard", "",
           "Repository-macro means. Tokens are cl100k. MSA = minimal sufficient answer (same information for every "
           "arm). ★ = Pareto-optimal on (native tokens, complete %).", ""]
    for (layer, task), rows in tables.items():
        if not rows:
            continue
        out += [f"## {layer} · {task}", ""]
        if task == "T2":
            out += ["| arm | n | hit % | precision | native tok |", "|---|---|---|---|---|"]
            for r in rows:
                if r.get("unsupported"):
                    out.append(f"| {r['arm']} | unsupported: {r['note']} | | | |")
                    continue
                out.append(f"| {r['arm']} | {r['n']} | {_f(r.get('hit'), True)} | {_f(r.get('precision'))} | {_f(r['tok_native'], nd=0)} |")
        else:
            out += ["| arm | n | recall | precision | complete % | native tok | loc tok | MSA tok | tok / complete | ★ |",
                    "|---|---|---|---|---|---|---|---|---|---|"]
            for r in sorted(rows, key=lambda r: (r.get("unsupported", False), -(r.get("complete") or 0), r.get("tok_native") or 0)):
                if r.get("unsupported"):
                    out.append(f"| {r['arm']} | unsupported: {r['note']} | | | | | | | | |")
                    continue
                out.append(f"| {r['arm']} | {r['n']} | {_f(r.get('recall'))} | {_f(r.get('precision'))} | {_f(r.get('complete'), True)} | "
                           f"{_f(r['tok_native'], nd=0)} | {_f(r['tok_loc'], nd=0)} | {_f(r['tok_msa'], nd=0)} | "
                           f"{_f(r.get('tokens_per_complete'), nd=0)} | {'★' if r.get('pareto') else ''} |")
        out.append("")
    return "\n".join(out)


def build(rows: list[dict]) -> dict:
    keys = sorted({(r.get("layer"), r.get("task")) for r in rows if r.get("layer") and r.get("task")})
    return {k: table(rows, *k) for k in keys}


if __name__ == "__main__":
    rows = read_rows(Path(sys.argv[1]))
    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    tables = build(rows)
    (out / "leaderboard.json").write_text(json.dumps({f"{k[0]}|{k[1]}": v for k, v in tables.items()}, indent=1,
                                                    default=lambda x: None))
    md = to_markdown(tables)
    (out / "leaderboard.md").write_text(md, encoding="utf-8")
    print(md)
