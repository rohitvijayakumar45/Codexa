"""Analysis for the frozen protocol (FREEZE.md). Usage: python -m nb.analyze <scored.jsonl> <out_dir>

Repositories (fixtures count as repositories) are the clustering unit; intervals are 95% percentile
intervals from a hierarchical bootstrap (resample repositories, then targets within each).
"""
from __future__ import annotations

import json
import math
import random
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

B = 2000
RNG = random.Random(20261008)
T1_ARMS = ["rg0", "rg3", "lsp", "codexa_refs", "codexa_orig", "cbm_cur", "cbm_057"]
GRAPH_ARMS = ["codexa_refs", "codexa_orig", "cbm_cur", "cbm_057"]
T2_ARMS = ["lsp_def", "rg_def", "codexa_def", "cbm_cur_def", "cbm_057_def"]


def load(p):
    return [json.loads(l) for l in open(p)]


def hboot(groups: dict, stat, b=B):
    """groups: repo -> list of items. stat: list[list[item]] -> float. Returns (point, lo, hi)."""
    keys = list(groups)
    point = stat([groups[k] for k in keys])
    vals = []
    for _ in range(b):
        ks = [RNG.choice(keys) for _ in keys]
        sample = [[RNG.choice(groups[k]) for _ in groups[k]] for k in ks]
        v = stat(sample)
        if v is not None and not (isinstance(v, float) and math.isnan(v)):
            vals.append(v)
    if not vals or point is None:
        return point, None, None
    vals.sort()
    return point, vals[int(0.025 * len(vals))], vals[int(0.975 * len(vals)) - 1]


def macro_mean(key):
    def f(groups):
        per = []
        for g in groups:
            xs = [r[key] for r in g if r.get(key) is not None]
            if xs:
                per.append(st.mean([float(x) for x in xs]))
        return st.mean(per) if per else None
    return f


def fmt(t, pct=False, nd=2):
    p, lo, hi = t
    if p is None:
        return "n/a"
    if pct:
        return f"{100*p:.1f} [{100*lo:.1f}, {100*hi:.1f}]" if lo is not None else f"{100*p:.1f}"
    return f"{p:.{nd}f} [{lo:.{nd}f}, {hi:.{nd}f}]" if lo is not None else f"{p:.{nd}f}"


def by_repo(rows):
    g = defaultdict(list)
    for r in rows:
        g[r["repo"]].append(r)
    return g


def geo_ratio(num_arm, den_arm, key="tok_native_cl100k", require=None):
    """Repo-macro geometric mean of per-target token ratio num/den over targets passing `require`."""
    def f(groups):
        per = []
        for g in groups:
            logs = [math.log(r[0][key] / r[1][key]) for r in g if r[0].get(key) and r[1].get(key)]
            if logs:
                per.append(st.mean(logs))
        return math.exp(st.mean(per)) if per else None
    return f


def paired(rows, a, b, task="T1"):
    idx = defaultdict(dict)
    for r in rows:
        if r["task"] == task:
            idx[(r["repo"], r["target"])][r["arm"]] = r
    out = defaultdict(list)
    for (repo, t), arms in idx.items():
        if a in arms and b in arms:
            out[repo].append((arms[a], arms[b]))
    return out


def main():
    rows = load(sys.argv[1])
    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    rep = {}
    lines = []

    # ---------------------------------------------------------------- Layer A (held-out fixtures)
    A = [r for r in rows if r["layer"] == "fixture" and r.get("split", "heldout") != "calib"]
    for lang in ("py", "ts", "all"):
        sub = [r for r in A if r["task"] == "T1" and r.get("A_n_gold") and (lang == "all" or r["lang"] == lang)]
        lines.append(f"\n## Layer A — held-out fixtures, T1 direct call sites ({lang}); explicit-call targets only")
        lines.append("| arm | n | caller recall | caller precision | complete-answer % | site recall | site precision | native tokens (mean) |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for arm in T1_ARMS:
            s = [r for r in sub if r["arm"] == arm]
            if not s:
                continue
            g = by_repo(s)
            row = {k: hboot(g, macro_mean(k)) for k in ("A_caller_recall", "A_caller_precision", "A_complete",
                                                        "A_site_recall", "A_site_precision", "tok_native_cl100k")}
            rep[f"A_{lang}_{arm}"] = row
            lines.append(f"| {arm} | {len(s)} | {fmt(row['A_caller_recall'])} | {fmt(row['A_caller_precision'])} | "
                         f"{fmt(row['A_complete'], pct=True)} | {fmt(row['A_site_recall'])} | {fmt(row['A_site_precision'])} | "
                         f"{fmt(row['tok_native_cl100k'], nd=0)} |")
    # pattern breakdown (caller recall per pattern, pooled languages)
    lines.append("\n### Layer A caller recall by pattern (held-out, both languages; mean over targets)")
    pats = sorted({r["pattern"] for r in A if r.get("pattern")})
    lines.append("| arm | " + " | ".join(pats) + " |")
    lines.append("|---|" + "---|" * len(pats))
    for arm in T1_ARMS:
        cells = []
        for p_ in pats:
            xs = [r["A_caller_recall"] for r in A if r["task"] == "T1" and r["arm"] == arm and r["pattern"] == p_
                  and r.get("A_caller_recall") is not None]
            cells.append(f"{st.mean(xs):.2f}" if xs else "–")
        lines.append(f"| {arm} | " + " | ".join(cells) + " |")
    lines.append("\n### Layer A by name ambiguity (caller recall / precision, held-out, both languages)")
    for arm in T1_ARMS:
        cells = []
        for amb in (False, True):
            s = [r for r in A if r["task"] == "T1" and r["arm"] == arm and r.get("A_n_gold") and r.get("ambiguous") == amb]
            if s:
                rr = st.mean([r["A_caller_recall"] for r in s])
                pp = [r["A_caller_precision"] for r in s if r.get("A_caller_precision") is not None]
                cells.append(f"{'ambiguous' if amb else 'unique'}: R={rr:.2f} P={st.mean(pp) if pp else float('nan'):.2f}")
        lines.append(f"- {arm}: " + "; ".join(cells))

    # primary contrast: token ratio graph/rg0 on jointly complete targets
    lines.append("\n### PRIMARY: tokens at matched quality (held-out fixtures; targets where both arms are complete at caller level)")
    lines.append("| graph arm | n jointly complete | jointly-complete share | geo-mean tokens graph/rg0 [95% CI] |")
    lines.append("|---|---|---|---|")
    for arm in GRAPH_ARMS + ["lsp"]:
        pr = paired([r for r in A if r.get("A_n_gold")], arm, "rg0")
        both = {k: [x for x in v if x[0].get("A_complete") and x[1].get("A_complete")] for k, v in pr.items()}
        both = {k: v for k, v in both.items() if v}
        n_both = sum(len(v) for v in both.values())
        n_all = sum(len(v) for v in pr.values())
        res = hboot(both, geo_ratio(arm, "rg0")) if both else (None, None, None)
        rep[f"PRIMARY_{arm}"] = {"n": n_both, "n_all": n_all, "ratio": res}
        lines.append(f"| {arm} | {n_both} | {n_both}/{n_all} | {fmt(res)} |")

    # T2 fixtures
    T2 = [r for r in A if r["task"] == "T2"]
    lines.append("\n## Layer A — T2 definition lookup (held-out fixtures)")
    lines.append("| arm | n | hit rate | precision | native tokens |")
    lines.append("|---|---|---|---|---|")
    for arm in T2_ARMS:
        s = [r for r in T2 if r["arm"] == arm]
        if s:
            g = by_repo(s)
            lines.append(f"| {arm} | {len(s)} | {fmt(hboot(g, macro_mean('T2_hit')), pct=True)} | "
                         f"{fmt(hboot(g, macro_mean('T2_precision')))} | {fmt(hboot(g, macro_mean('tok_native_cl100k')), nd=0)} |")

    # ---------------------------------------------------------------- Q1 natural: baseline choice
    N = [r for r in rows if r["layer"] == "natural" and r["task"] == "T1"]
    lines.append("\n## Q1 — natural repositories: payload ratio of each baseline to each graph arm (repo-macro geometric mean, S-ind)")
    lines.append("| graph arm | whole-file (graph-selected, original method) | whole-file (provider-selected) | rg -w (k=0) | rg -C3 | LSP JSON | LSP loc form |")
    lines.append("|---|---|---|---|---|---|---|")
    S = [r for r in N if r["sample"] == "S-ind"]
    for arm in GRAPH_ARMS:
        cells = []
        g = by_repo([r for r in S if r["arm"] == arm and r["status"] == "ok"])
        for key in ("wholefile_graphsel_tokens", "wholefile_provider_tokens"):
            def f(groups, key=key):
                per = [st.mean([math.log(r[key] / r["tok_native_cl100k"]) for r in gg if r.get(key) and r.get("tok_native_cl100k")]) for gg in groups]
                per = [x for x in per if x == x]
                return math.exp(st.mean(per)) if per else None
            cells.append(fmt(hboot(g, f), nd=1))
        for base, k in (("rg0", "tok_native_cl100k"), ("rg3", "tok_native_cl100k"), ("lsp", "tok_native_cl100k"), ("lsp", "tok_loc_cl100k")):
            pr = paired([r for r in S if (r["arm"] != arm or r["status"] == "ok")], base, arm)

            def f2(groups, k=k):
                per = []
                for gg in groups:
                    logs = [math.log(a[k] / b["tok_native_cl100k"]) for a, b in gg if a.get(k) and b.get("tok_native_cl100k") and b["status"] == "ok"]
                    if logs:
                        per.append(st.mean(logs))
                return math.exp(st.mean(per)) if per else None
            cells.append(fmt(hboot({kk: v for kk, v in pr.items() if v}, f2), nd=2))
        lines.append(f"| {arm} | " + " | ".join(cells) + " |")
    lines.append("\nRatios > 1 mean the baseline payload is larger than the graph arm's native output. Graph rows restricted to targets where the graph arm returned a non-empty answer.")

    # ---------------------------------------------------------------- Q2 sampling & availability & agreement
    lines.append("\n## Q2 — natural repositories: S-ind vs S-cond")
    lines.append("| arm | sample | n | non-empty % | agreement with LSP callers (Jaccard) | observed-call caller recall (py, layer C) | complete on observed calls % |")
    lines.append("|---|---|---|---|---|---|---|")
    lsp_c = {(r["repo"], r["target"]): set(r["_callers"]) for r in N if r["arm"] == "lsp"}
    for arm in T1_ARMS:
        for samp in ("S-ind", "S-cond"):
            s = [r for r in N if r["arm"] == arm and r["sample"] == samp]
            if not s:
                continue
            for r in s:
                r["_ok"] = 1.0 if r["status"] == "ok" else 0.0
                a, b = set(r["_callers"]), lsp_c.get((r["repo"], r["target"]), set())
                r["_jac"] = (len(a & b) / len(a | b)) if (a | b) else None
            g = by_repo(s)
            gc = by_repo([r for r in s if r.get("C_n_gold")])
            lines.append(f"| {arm} | {samp} | {len(s)} | {fmt(hboot(g, macro_mean('_ok')), pct=True)} | "
                         f"{fmt(hboot(g, macro_mean('_jac')))} | "
                         f"{fmt(hboot(gc, macro_mean('C_caller_recall'))) if gc else 'n/a'} | "
                         f"{fmt(hboot(gc, macro_mean('C_complete')), pct=True) if gc else 'n/a'} |")
    # coverage: how often each sample's targets are present in / have edges in the Codexa graph
    lines.append("\n### Q2 — target presence in the Codexa graph by sample (natural)")
    lines.append("| sample | targets | in Codexa graph % | with ≥1 incoming Codexa edge % | provider call fan-out = 0 % |")
    lines.append("|---|---|---|---|---|")
    for samp in ("S-ind", "S-cond"):
        s = [r for r in N if r["arm"] == "rg0" and r["sample"] == samp]
        for r in s:
            r["_in"] = 1.0 if r.get("in_codexa") else 0.0
            r["_edge"] = 1.0 if r.get("codexa_has_in_edge") else 0.0
            r["_fan0"] = (1.0 if r.get("provider_call_fanout") == 0 else 0.0) if r.get("provider_call_fanout") is not None else None
        g = by_repo(s)
        if s:
            lines.append(f"| {samp} | {len(s)} | {fmt(hboot(g, macro_mean('_in')), pct=True)} | {fmt(hboot(g, macro_mean('_edge')), pct=True)} | "
                         f"{fmt(hboot(g, macro_mean('_fan0')), pct=True)} |")
    # layer C site-level for location arms
    lines.append("\n### Layer C — observed-call recall (Python natural repositories; targets with ≥1 observed call; both samples, each target once)")
    lines.append("| arm | targets | caller recall | site recall | complete % |")
    lines.append("|---|---|---|---|---|")
    for arm in T1_ARMS:
        s = list({(r["repo"], r["target"]): r for r in N if r["arm"] == arm and r.get("C_n_gold")}.values())  # once per target
        if s:
            g = by_repo(s)
            lines.append(f"| {arm} | {len(s)} | {fmt(hboot(g, macro_mean('C_caller_recall')))} | "
                         f"{fmt(hboot(g, macro_mean('C_site_recall'))) if s[0].get('C_site_recall') is not None or arm in ('rg0','rg3','lsp') else 'n/a'} | "
                         f"{fmt(hboot(g, macro_mean('C_complete')), pct=True)} |")
    # exploratory regression: log(rg0 tokens / graph tokens) ~ log name occurrences + log provider fanout + kind
    try:
        import numpy as np
        lines.append("\n### Exploratory — what predicts the rg0/graph payload ratio (natural S-ind, OLS with repository-cluster bootstrap)")
        for arm in ("codexa_refs", "cbm_cur"):
            pr = paired([r for r in S], "rg0", arm)
            X, y, grp = [], [], []
            for repo, pairs_ in pr.items():
                for a_, b_ in pairs_:
                    if b_["status"] != "ok" or not a_.get("tok_native_cl100k") or not b_.get("tok_native_cl100k"):
                        continue
                    X.append([1.0, math.log(1 + (a_.get("name_occurrences") or 0)), math.log(1 + (b_.get("provider_call_fanout") or 0)),
                              1.0 if b_["kind"] == "method" else 0.0, 1.0 if b_["kind"] == "class" else 0.0])
                    y.append(math.log(a_["tok_native_cl100k"] / b_["tok_native_cl100k"]))
                    grp.append(repo)
            if len(y) < 20:
                continue
            X, y = np.array(X), np.array(y)
            beta = np.linalg.lstsq(X, y, rcond=None)[0]
            repos_ = sorted(set(grp))
            boots = []
            for _ in range(1000):
                pick = [RNG.choice(repos_) for _ in repos_]
                idx = [i for rp in pick for i, g_ in enumerate(grp) if g_ == rp]
                boots.append(np.linalg.lstsq(X[idx], y[idx], rcond=None)[0])
            boots = np.array(boots)
            names = ["intercept", "log(1+name occurrences)", "log(1+provider fan-out)", "method", "class"]
            lines.append(f"- {arm} (n={len(y)}, repos={len(repos_)}): " + "; ".join(
                f"{n_}={b:.2f} [{np.percentile(boots[:, i], 2.5):.2f}, {np.percentile(boots[:, i], 97.5):.2f}]" for i, (n_, b) in enumerate(zip(names, beta))))
    except Exception as e:  # noqa: BLE001
        lines.append(f"(regression skipped: {e})")
    (out / "report.md").write_text("\n".join(lines) + "\n")
    (out / "report.json").write_text(json.dumps(rep, default=str, indent=1))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
