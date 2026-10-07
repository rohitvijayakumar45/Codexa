"""Post-hoc robustness analyses requested in review (not part of the frozen protocol; reported as supplementary).

R1  Held-out fixtures, full workload: recall, precision, completeness and tokens over all explicit-call targets
    (no conditioning on completeness), and token ratios to rg0 over every target with a non-empty answer.
R2  Composition of the jointly-complete subsets used by the primary contrast (n, language, pattern, ambiguity).
R3  Primary contrast recomputed on the common location form (tok_loc_cl100k), and for location arms the
    source-enriched form (tok_src_cl100k).
R4  Strict caller credit for location arms (rg0, rg3, lsp): a caller is credited only through a returned location
    that is itself a gold call site (comment, string, import or declaration hits inside a true caller earn nothing).
    Reported for layer A and layer C, with the primary contrast recomputed under strict completeness.
R5  S-cond vs S-ind adjusted for target composition: the language server's call fan-out bucket, declaration kind,
    and name-occurrence bucket, per repository. Reports the raw difference, the difference restricted to targets
    with >= 1 call site, and S-cond post-stratified to the S-ind distribution of (repo, kind, fan-out bucket).

Usage: python -m nb.robustness <run_dir> <scored.jsonl[.gz]> [<extra scored.jsonl[.gz]> ...] <out_dir>
<run_dir> holds the raw <repo>.results.jsonl / targets.json files (needed for R4 and the fan-out of S-cond targets).
"""
from __future__ import annotations

import gzip
import json
import math
import os
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

NB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(NB_ROOT))

from nb import index as I  # noqa: E402
from nb import trace_map  # noqa: E402
from nb.analyze import by_repo, fmt, hboot, macro_mean  # noqa: E402
from nb.run import bucket  # noqa: E402
from nb.tsclient import TsClient  # noqa: E402

DATA = Path(os.environ.get("CODEXA_DATA_DIR", "/work/nb"))
ARMS = ["rg0", "rg3", "lsp", "codexa_refs", "codexa_orig", "cbm_cur", "cbm_057"]
GRAPH = ["codexa_refs", "codexa_orig", "cbm_cur", "cbm_057"]
LOC_ARMS = ["rg0", "rg3", "lsp"]


def _open(p):
    return gzip.open(p, "rt") if str(p).endswith(".gz") else open(p)


def derive(run_dir: Path) -> dict:
    """Per (repo, target, arm): strict caller metrics (location arms) and the provider call fan-out of every target."""
    out: dict = {}
    for meta in sorted(run_dir.glob("*.meta.json")):
        m = json.loads(meta.read_text())
        repo, lang, layer = m["repo"], m["lang"], m["layer"]
        if m.get("split") == "calib":
            continue
        root = DATA / "repos" / repo
        tsc = TsClient(root) if lang == "ts" else None
        ix = I.load(root, lang, tsc)
        if tsc:
            tsc.close()
        targets = {t["decl"]: t for t in json.loads((run_dir / f"{repo}.targets.json").read_text())}
        traced = None
        tr = DATA / "traces" / f"{repo}.json"
        if lang == "py" and layer == "natural" and tr.exists():
            tm = trace_map.load(ix.py, tr)
            traced = {}
            for (cid, did), v in tm["pairs"].items():
                if v["confirmed"]:
                    traced.setdefault(did, set()).add(cid)
        for line in open(run_dir / f"{repo}.results.jsonl"):
            r = json.loads(line)
            if r["task"] != "T1":
                continue
            t = targets[r["target"]]
            key = (repo, r["target"], r["arm"])
            rec: dict = {}
            if r["arm"] == "lsp":
                rec["lsp_call_fanout"] = sum(1 for f in r["facts"] if tuple(f) in ix.name_tok)
            if r["arm"] in LOC_ARMS:
                locs = [tuple(f) for f in r["facts"]]
                returned = {ix.enclosing(f, l) for f, l, c in locs}
                golds = []
                if layer == "fixture":
                    golds.append(("A", {g["call"] for g in t["gold"]["explicit"] if g["call"]}))
                if traced is not None:
                    golds.append(("C", traced.get(r["target"], set())))
                for lay, g_calls in golds:
                    if not g_calls:
                        continue
                    g_callers = {ix.enclosing(ix.calls[c]["file"], ix.calls[c]["line"]) for c in g_calls}
                    strict = {ix.enclosing(f, l) for f, l, c in locs if ix.name_tok.get((f, l, c)) in g_calls}
                    rc = len(strict & g_callers) / len(g_callers)
                    rec[f"{lay}_strict_caller_recall"] = rc
                    rec[f"{lay}_strict_caller_precision"] = (len(strict & g_callers) / len(returned)) if returned else None
                    rec[f"{lay}_strict_complete"] = rc == 1.0
            out[key] = rec
    return out


def gm_ratio(pairs_by_repo, key_a, key_b=None):
    key_b = key_b or key_a

    def f(groups):
        per = []
        for g in groups:
            logs = [math.log(a[key_a] / b[key_b]) for a, b in g if a.get(key_a) and b.get(key_b)]
            if logs:
                per.append(st.mean(logs))
        return math.exp(st.mean(per)) if per else None
    return hboot(pairs_by_repo, f)


def main():
    run_dir, out = Path(sys.argv[1]), Path(sys.argv[-1])
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for p in sys.argv[2:-1]:
        rows += [json.loads(l) for l in _open(p)]
    cache = out / "robustness_derived.json.gz"
    if cache.exists():
        der = {tuple(k.split("\t")): v for k, v in json.loads(gzip.open(cache, "rt").read()).items()}
    else:
        der = derive(run_dir)
        with gzip.open(cache, "wt") as fh:
            fh.write(json.dumps({"\t".join(k): v for k, v in der.items()}))
    for r in rows:
        r.update(der.get((r["repo"], r["target"], r["arm"]), {}))
    L: list[str] = ["# Supplementary robustness analyses (post hoc; not part of the frozen protocol)"]
    rep: dict = {}

    # ------------------------------------------------------------- layer A
    A = [r for r in rows if r["layer"] == "fixture" and r.get("split", "heldout") != "calib" and r["task"] == "T1" and r.get("A_n_gold")]
    idx = defaultdict(dict)
    for r in A:
        idx[(r["repo"], r["target"])][r["arm"]] = r

    def pairs(a, b, cond=lambda x, y: True):
        g = defaultdict(list)
        for (repo, _), arms in idx.items():
            if a in arms and b in arms and cond(arms[a], arms[b]):
                g[repo].append((arms[a], arms[b]))
        return g

    L.append("\n## R1 Held-out fixtures, full workload (all 160 explicit-call targets, no completeness conditioning)")
    L.append("| arm | caller recall | caller precision | F1 (macro of per-target) | complete % | native tok | loc tok | src tok | native ratio to rg0, all non-empty targets |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for arm in ARMS:
        s = [r for r in A if r["arm"] == arm]
        if not s:
            continue
        for r in s:
            p, rc = r.get("A_caller_precision"), r.get("A_caller_recall")
            r["_f1"] = (2 * p * rc / (p + rc)) if (p and rc) else 0.0
        g = by_repo(s)
        res = {k: hboot(g, macro_mean(k)) for k in ("A_caller_recall", "A_caller_precision", "_f1", "A_complete",
                                                     "tok_native_cl100k", "tok_loc_cl100k", "tok_src_cl100k")}
        ratio = gm_ratio(pairs(arm, "rg0"), "tok_native_cl100k") if arm != "rg0" else (1.0, None, None)
        rep[f"R1_{arm}"] = dict(res, ratio_all=ratio)
        L.append(f"| {arm} | {fmt(res['A_caller_recall'])} | {fmt(res['A_caller_precision'])} | {fmt(res['_f1'])} | "
                 f"{fmt(res['A_complete'], pct=True)} | {fmt(res['tok_native_cl100k'], nd=0)} | {fmt(res['tok_loc_cl100k'], nd=0)} | "
                 f"{fmt(res['tok_src_cl100k'], nd=0) if s[0].get('tok_src_cl100k') is not None else 'n/a'} | {fmt(ratio)} |")
    L.append("Precision is caller-level: share of returned callers (or callers enclosing returned locations) that are true callers; "
             "an empty answer has undefined precision and is excluded from the precision mean. F1 counts an empty answer as 0.")

    L.append("\n## R2 Composition of the jointly-complete subsets (primary contrast, each arm vs rg0)")
    L.append("| arm | n jointly complete / 160 | py / ts | ambiguous names | patterns (count) |")
    L.append("|---|---|---|---|---|")
    for arm in GRAPH + ["lsp"]:
        g = pairs(arm, "rg0", lambda a, b: a.get("A_complete") and b.get("A_complete"))
        xs = [a for v in g.values() for a, b in v]
        if not xs:
            continue
        lang = Counter(a["lang"] for a in xs)
        pat = Counter(a["pattern"] for a in xs)
        amb = sum(1 for a in xs if a.get("ambiguous"))
        rep[f"R2_{arm}"] = {"n": len(xs), "lang": lang, "patterns": pat, "ambiguous": amb}
        L.append(f"| {arm} | {len(xs)} | {lang['py']} / {lang['ts']} | {amb} | " + ", ".join(f"{k} {v}" for k, v in sorted(pat.items())) + " |")
    allc = [k for k, arms in idx.items() if all(arms.get(a, {}).get("A_complete") for a in ARMS if a in arms)]
    L.append(f"\nTargets on which every arm is complete: {len(allc)} / {len(idx)}.")
    rep["R2_all_arms_complete"] = len(allc)

    L.append("\n## R3 Primary contrast by output form (jointly complete targets; ratio arm/rg0 in the same form)")
    L.append("| arm | native | common location form | source-enriched form |")
    L.append("|---|---|---|---|")
    for arm in GRAPH + ["lsp"]:
        g = pairs(arm, "rg0", lambda a, b: a.get("A_complete") and b.get("A_complete"))
        res = [gm_ratio(g, k) for k in ("tok_native_cl100k", "tok_loc_cl100k")]
        src = gm_ratio(g, "tok_src_cl100k") if arm in LOC_ARMS else (None, None, None)
        rep[f"R3_{arm}"] = {"native": res[0], "loc": res[1], "src": src}
        L.append(f"| {arm} | {fmt(res[0])} | {fmt(res[1])} | {fmt(src)} |")
    L.append("Graph arms return callers, so their common form is one `file::qualified_name` per line and they have no "
             "source-enriched form; location arms list one `file:line:col` per returned location.")

    L.append("\n## R4 Strict caller credit for location arms")
    L.append("| arm | layer A caller recall (lenient → strict) | layer A precision (lenient → strict) | layer A complete % (lenient → strict) | layer C caller recall (lenient → strict) |")
    L.append("|---|---|---|---|---|")
    C = list({(r["repo"], r["target"], r["arm"]): r for r in rows
              if r["layer"] == "natural" and r["task"] == "T1" and r.get("C_n_gold")}.values())  # each target once
    for arm in LOC_ARMS:
        s = [r for r in A if r["arm"] == arm]
        g = by_repo(s)
        for r in s:
            r["_sc"] = 1.0 if r.get("A_strict_complete") else 0.0
        c = by_repo([r for r in C if r["arm"] == arm])
        vals = {k: hboot(g, macro_mean(k)) for k in ("A_caller_recall", "A_strict_caller_recall", "A_caller_precision",
                                                     "A_strict_caller_precision", "A_complete", "_sc")}
        cv = (hboot(c, macro_mean("C_caller_recall")), hboot(c, macro_mean("C_strict_caller_recall")))
        rep[f"R4_{arm}"] = dict(vals, C=cv)
        L.append(f"| {arm} | {fmt(vals['A_caller_recall'])} → {fmt(vals['A_strict_caller_recall'])} | "
                 f"{fmt(vals['A_caller_precision'])} → {fmt(vals['A_strict_caller_precision'])} | "
                 f"{fmt(vals['A_complete'], pct=True)} → {fmt(vals['_sc'], pct=True)} | {fmt(cv[0])} → {fmt(cv[1])} |")
    L.append("\nPrimary contrast with rg0 (and lsp) completeness judged strictly:")
    L.append("| arm | n jointly complete | ratio arm/rg0 [95% CI] |")
    L.append("|---|---|---|")
    for arm in GRAPH + ["lsp"]:
        ca = (lambda a: a.get("A_strict_complete")) if arm in LOC_ARMS else (lambda a: a.get("A_complete"))
        g = pairs(arm, "rg0", lambda a, b, ca=ca: ca(a) and b.get("A_strict_complete"))
        n = sum(len(v) for v in g.values())
        res = gm_ratio(g, "tok_native_cl100k") if n else (None, None, None)
        rep[f"R4_primary_{arm}"] = {"n": n, "ratio": res}
        L.append(f"| {arm} | {n} | {fmt(res)} |")

    # ------------------------------------------------------------- R5 sampling
    N = [r for r in rows if r["layer"] == "natural" and r["task"] == "T1"]
    fan = {(r["repo"], r["target"]): r.get("lsp_call_fanout") for r in N if r["arm"] == "lsp"}
    for r in N:
        fo = fan.get((r["repo"], r["target"]))
        r["_fan"] = fo
        r["_fanb"] = bucket(fo) if fo is not None else "?"
        r["_occb"] = bucket(r.get("name_occurrences") or 0)
        r["_ok"] = 1.0 if r["status"] == "ok" else 0.0
    L.append("\n## R5 S-cond vs S-ind, adjusted for target composition (natural repositories)")
    L.append("Fan-out = number of call sites among the language server's references; buckets 0, 1–2, 3–9, ≥10. "
             "Post-stratified = S-cond cell means (repo × kind × fan-out bucket) weighted by the S-ind cell shares, "
             "over cells present in both samples.")
    L.append("| arm | non-empty: S-cond → S-ind | non-empty, fan-out ≥ 1 only | non-empty, S-cond post-stratified → S-ind (same cells) | observed-call recall: S-cond → S-ind | observed-call recall, S-cond post-stratified → S-ind (same cells) |")
    L.append("|---|---|---|---|---|---|")
    comp = {}
    for samp in ("S-cond", "S-ind"):
        s = [r for r in N if r["arm"] == "rg0" and r["sample"] == samp]
        comp[samp] = {"n": len(s), "fan0": sum(1 for r in s if r["_fan"] == 0) / len(s),
                      "kind": Counter(r["kind"] for r in s), "fanb": Counter(r["_fanb"] for r in s),
                      "median_name_occ": st.median([r.get("name_occurrences") or 0 for r in s])}
    rep["R5_composition"] = comp

    def poststrat(rows_c, rows_i, key):
        """Returns (S-cond post-stratified, S-ind on the same cells), repo-macro, with a hierarchical bootstrap."""
        def cell(r):
            return (r["kind"], r["_fanb"])

        def stat(groups_pair):
            per_c, per_i = [], []
            for gc, gi in groups_pair:
                ci = defaultdict(list)
                for r in gi:
                    if r.get(key) is not None:
                        ci[cell(r)].append(r[key])
                cc = defaultdict(list)
                for r in gc:
                    if r.get(key) is not None:
                        cc[cell(r)].append(r[key])
                common = [k for k in ci if k in cc]
                if not common:
                    continue
                tot = sum(len(ci[k]) for k in common)
                per_c.append(sum(len(ci[k]) / tot * st.mean(cc[k]) for k in common))
                per_i.append(sum(len(ci[k]) / tot * st.mean(ci[k]) for k in common))
            return (st.mean(per_c), st.mean(per_i)) if per_c else (None, None)
        gc, gi = by_repo(rows_c), by_repo(rows_i)
        keys = [k for k in gc if k in gi]
        point = stat([(gc[k], gi[k]) for k in keys])
        import random
        rng = random.Random(20261008)
        diffs = []
        for _ in range(2000):
            ks = [rng.choice(keys) for _ in keys]
            v = stat([([rng.choice(gc[k]) for _ in gc[k]], [rng.choice(gi[k]) for _ in gi[k]]) for k in ks])
            if v[0] is not None:
                diffs.append(v[0] - v[1])
        diffs.sort()
        return point, (diffs[int(0.025 * len(diffs))], diffs[int(0.975 * len(diffs)) - 1]) if diffs else (None, None)

    for arm in ARMS:
        sc = [r for r in N if r["arm"] == arm and r["sample"] == "S-cond"]
        si = [r for r in N if r["arm"] == arm and r["sample"] == "S-ind"]
        if not sc or not si:
            continue
        raw = (hboot(by_repo(sc), macro_mean("_ok")), hboot(by_repo(si), macro_mean("_ok")))
        sc1, si1 = [r for r in sc if (r["_fan"] or 0) >= 1], [r for r in si if (r["_fan"] or 0) >= 1]
        f1 = (hboot(by_repo(sc1), macro_mean("_ok")), hboot(by_repo(si1), macro_mean("_ok")))
        ps, ps_ci = poststrat(sc, si, "_ok")
        scC, siC = [r for r in sc if r.get("C_n_gold")], [r for r in si if r.get("C_n_gold")]
        rc = (hboot(by_repo(scC), macro_mean("C_caller_recall")), hboot(by_repo(siC), macro_mean("C_caller_recall")))
        psC, psC_ci = poststrat(scC, siC, "C_caller_recall")
        rep[f"R5_{arm}"] = {"nonempty": raw, "nonempty_fan1": f1, "nonempty_poststrat": [ps, ps_ci],
                            "recallC": rc, "recallC_poststrat": [psC, psC_ci]}

        def pct(t):
            return f"{100*t[0]:.0f}" if t[0] is not None else "n/a"

        def d(p, ci, scale=100, nd=0):
            if p[0] is None:
                return "n/a"
            return (f"{scale*p[0]:.{nd}f} → {scale*p[1]:.{nd}f} (diff {scale*(p[0]-p[1]):+.{nd}f}, "
                    f"95% CI {scale*ci[0]:+.{nd}f} to {scale*ci[1]:+.{nd}f})")
        L.append(f"| {arm} | {pct(raw[0])} → {pct(raw[1])} | {pct(f1[0])} → {pct(f1[1])} | {d(ps, ps_ci)} | "
                 f"{rc[0][0]:.2f} → {rc[1][0]:.2f} | {d(psC, psC_ci, scale=1, nd=2)} |")
    L.append("\nSample composition: " + "; ".join(
        f"{k}: n={v['n']}, fan-out 0 = {100*v['fan0']:.0f}%, median name occurrences = {v['median_name_occ']}, "
        f"fan-out buckets {dict(v['fanb'])}, kinds {dict(v['kind'])}" for k, v in comp.items()))

    (out / "robustness.md").write_text("\n".join(L) + "\n")
    (out / "robustness.json").write_text(json.dumps(rep, default=str, indent=1))
    print("\n".join(L))


if __name__ == "__main__":
    main()
