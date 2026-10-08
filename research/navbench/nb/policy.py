"""Completeness-aware routing policies, evaluated model-free (feature A).

Q3 found that small graph outputs coincide with incomplete answers, and that the only complete
graph tool costs as much as ripgrep. A natural question the frozen study leaves open: is there a
*policy* — query a graph tool, and fall back to a lexical or language-server arm only when the first
answer looks unreliable — that reaches the fallback's completeness at lower cost?

Every policy here is computed from already-scored rows, with no new tool runs:

    single:<arm>                    the arm alone
    route:<first>><fallback>@<trigger>
                                    answer = first's callers, plus fallback's callers if `trigger`
                                    fires on first's own output; tokens = first + (fallback if fired)
    oracle                          per target, the cheapest complete arm (an upper bound — not
                                    deployable, it uses the labels)

Triggers use only what an agent can see in the first tool's reply (never the labels):

    always         fire unconditionally (union of both tools)
    empty          the reply was empty / not ok
    ambiguous      the tool reported ambiguity (it needed a follow-up call, n_calls > 1)
    unresolved     the reply named callers the index could not map
    weak           empty OR ambiguous OR unresolved OR truncated

Metrics (layer A, targets with explicit call sites; layer C when C_gold_callers exist): caller
recall, complete-answer rate, mean tokens, tokens per complete answer — repository-macro means with a
hierarchical bootstrap (repositories, then targets), and the Pareto set on (tokens, completeness).

Usage: python -m nb.policy <scored.jsonl[.gz]> <out_dir> [--token-key tok_native_cl100k] [--layer A|C]
       [--arms a,b,...] [--fallbacks rg0,lsp]
"""
from __future__ import annotations

import json
import math
import random
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

NB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(NB_ROOT))

from nb.offline import read_rows  # noqa: E402

TRIGGERS = ("always", "empty", "ambiguous", "unresolved", "weak")
B = 2000
RNG = random.Random(20261008)


# Calls an arm makes by design; more than this means the tool asked for disambiguation.
BASE_CALLS = {"codexa_orig": 2}


def fires(trigger: str, r: dict) -> bool:
    empty = r.get("status") != "ok" or not r.get("n_units")
    ambiguous = (r.get("n_calls") or 1) > BASE_CALLS.get(r.get("arm"), 1)
    unresolved = (r.get("n_unresolved") or 0) > 0
    truncated = bool(r.get("truncated"))
    return {"always": True, "empty": empty, "ambiguous": ambiguous, "unresolved": unresolved,
            "weak": empty or ambiguous or unresolved or truncated}[trigger]


def outcome(callers: set, gold: set, tokens: float) -> dict:
    recall = len(callers & gold) / len(gold) if gold else None
    return {"recall": recall, "complete": recall == 1.0 if recall is not None else None, "tokens": tokens}


def build_targets(rows: list[dict], layer: str, token_key: str) -> dict:
    """(repo, target) -> {"gold": set, "arms": {arm: row}} for T1 rows that carry gold callers."""
    gkey = f"{layer}_gold_callers"
    out: dict = {}
    for r in rows:
        if r.get("task") != "T1" or r.get("status") == "unsupported" or r.get(token_key) is None:
            continue
        k = (r["repo"], r["target"])
        e = out.setdefault(k, {"gold": None, "arms": {}})
        if r.get(gkey) is not None:
            e["gold"] = set(r[gkey])
        e["arms"][r["arm"]] = r
    return {k: v for k, v in out.items() if v["gold"]}


def evaluate_policy(name: str, tgt: dict, token_key: str) -> dict | None:
    arms = tgt["arms"]
    gold = tgt["gold"]
    if name == "oracle":
        best = None
        for a, r in arms.items():
            o = outcome(set(r.get("_callers", [])), gold, r[token_key])
            key = (not o["complete"], o["tokens"])
            if best is None or key < best[0]:
                best = (key, o)
        return best[1] if best else None
    if name.startswith("single:"):
        a = name.split(":", 1)[1]
        if a not in arms:
            return None
        r = arms[a]
        return outcome(set(r.get("_callers", [])), gold, r[token_key])
    # route:first>fallback@trigger
    spec = name.split(":", 1)[1]
    pair, trigger = spec.split("@")
    first, fb = pair.split(">")
    if first not in arms or fb not in arms:
        return None
    r1, r2 = arms[first], arms[fb]
    callers = set(r1.get("_callers", []))
    tok = r1[token_key]
    if fires(trigger, r1):
        callers |= set(r2.get("_callers", []))
        tok += r2[token_key]
    o = outcome(callers, gold, tok)
    o["fired"] = fires(trigger, r1)
    return o


def summarize(per_target: dict[tuple, dict]) -> dict:
    by_repo: dict[str, list[dict]] = defaultdict(list)
    for (repo, _t), o in per_target.items():
        by_repo[repo].append(o)

    def stat(groups: list[list[dict]]) -> dict:
        rec = [st.mean([o["recall"] for o in g]) for g in groups if g]
        comp = [st.mean([1.0 if o["complete"] else 0.0 for o in g]) for g in groups if g]
        tok = [st.mean([o["tokens"] for o in g]) for g in groups if g]
        allo = [o for g in groups for o in g]
        n_complete = sum(1 for o in allo if o["complete"])
        return {"recall": st.mean(rec), "complete": st.mean(comp), "tokens": st.mean(tok),
                "tokens_per_complete": (sum(o["tokens"] for o in allo) / n_complete) if n_complete else math.inf,
                "fired": (st.mean([1.0 if o.get("fired") else 0.0 for o in allo]) if any("fired" in o for o in allo) else None)}

    keys = sorted(by_repo)
    point = stat([by_repo[k] for k in keys])
    boots = defaultdict(list)
    for _ in range(B):
        ks = [RNG.choice(keys) for _ in keys]
        s = stat([[RNG.choice(by_repo[k]) for _ in by_repo[k]] for k in ks])
        for m, v in s.items():
            if v is not None and v != math.inf:
                boots[m].append(v)
    ci = {}
    for m, vs in boots.items():
        vs.sort()
        ci[m] = [vs[int(0.025 * len(vs))], vs[int(0.975 * len(vs)) - 1]] if vs else None
    return {"n_targets": sum(len(v) for v in by_repo.values()), "n_repos": len(keys), **point, "ci95": ci}


def pareto(results: dict[str, dict]) -> set[str]:
    front = set()
    for a, ra in results.items():
        dominated = False
        for b, rb in results.items():
            if a == b:
                continue
            if (rb["tokens"] <= ra["tokens"] and rb["complete"] >= ra["complete"]
                    and (rb["tokens"] < ra["tokens"] or rb["complete"] > ra["complete"])):
                dominated = True
                break
        if not dominated:
            front.add(a)
    return front


def policy_names(arms: list[str], fallbacks: list[str]) -> list[str]:
    names = [f"single:{a}" for a in arms]
    for first in arms:
        for fb in fallbacks:
            if fb == first:
                continue
            for trig in TRIGGERS:
                names.append(f"route:{first}>{fb}@{trig}")
    return names + ["oracle"]


def run(rows: list[dict], layer: str = "A", token_key: str = "tok_native_cl100k",
        arms: list[str] | None = None, fallbacks: list[str] | None = None) -> dict:
    targets = build_targets(rows, layer, token_key)
    present = sorted({a for t in targets.values() for a in t["arms"]})
    arms = [a for a in (arms or present) if a in present]
    fallbacks = [f for f in (fallbacks or ["rg0", "lsp"]) if f in present]
    results = {}
    for name in policy_names(arms, fallbacks):
        per = {}
        for k, t in targets.items():
            o = evaluate_policy(name, t, token_key)
            if o is not None and o["recall"] is not None:
                per[k] = o
        if per:
            results[name] = summarize(per)
    front = pareto({k: v for k, v in results.items() if k != "oracle"})
    for k, v in results.items():
        v["pareto"] = k in front
    return {"layer": layer, "token_key": token_key, "n_targets": len(targets), "policies": results}


def to_markdown(res: dict) -> str:
    def f(x, pct=False):
        if x is None:
            return "–"
        if x == math.inf:
            return "∞"
        return f"{100 * x:.1f}" if pct else f"{x:.1f}"

    lines = [f"## Routing policies — layer {res['layer']}, tokens = `{res['token_key']}` ({res['n_targets']} targets)", "",
             "| policy | recall | complete % [95% CI] | mean tokens [95% CI] | tokens / complete answer | fallback fired % | Pareto |",
             "|---|---|---|---|---|---|---|"]
    rows = sorted(res["policies"].items(), key=lambda kv: (-kv[1]["complete"], kv[1]["tokens"]))
    for name, r in rows:
        ci = r.get("ci95") or {}
        cc = ci.get("complete")
        tc = ci.get("tokens")
        lines.append(f"| {name} | {r['recall']:.2f} | {f(r['complete'], True)}"
                     + (f" [{f(cc[0], True)}, {f(cc[1], True)}]" if cc else "")
                     + f" | {f(r['tokens'])}" + (f" [{f(tc[0])}, {f(tc[1])}]" if tc else "")
                     + f" | {f(r['tokens_per_complete'])} | {f(r['fired'], True)} | {'★' if r.get('pareto') else ''} |")
    lines.append("")
    lines.append("`oracle` uses the labels and is an upper bound, not a deployable policy. Pareto = not dominated on "
                 "(mean tokens, complete %) among deployable policies.")
    return "\n".join(lines)


def _opt(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


if __name__ == "__main__":
    rows = read_rows(Path(sys.argv[1]))
    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    token_key = _opt("--token-key", "tok_native_cl100k")
    layer = _opt("--layer", "A")
    arms = [a for a in _opt("--arms", "").split(",") if a] or None
    fbs = [a for a in _opt("--fallbacks", "rg0,lsp").split(",") if a]
    res = run(rows, layer, token_key, arms, fbs)
    stem = f"policy_{layer}_{token_key}"
    (out / f"{stem}.json").write_text(json.dumps(res, indent=1, default=lambda x: None))
    (out / f"{stem}.md").write_text(to_markdown(res), encoding="utf-8")
    print(to_markdown(res))
