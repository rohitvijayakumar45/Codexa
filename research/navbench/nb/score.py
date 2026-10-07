"""Score raw arm results against fixture manifests (layer A), runtime traces (layer C) and each other (layer B).

Output: one row per (repo, target, task, arm) with precision/recall at site, caller and file level,
plus availability, truncation and token counts. Nothing here is tuned on held-out data.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

NB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(NB_ROOT))

from nb import index as I  # noqa: E402
from nb import tokens  # noqa: E402
from nb import trace_map  # noqa: E402
from nb.tsclient import TsClient  # noqa: E402

DATA = Path(os.environ.get("CODEXA_DATA_DIR", "/work/nb"))


def _pr(ret: set, gold: set):
    if not ret and not gold:
        return None, None
    p = (len(ret & gold) / len(ret)) if ret else None
    r = (len(ret & gold) / len(gold)) if gold else None
    return p, r


def units(ix, row) -> dict:
    """Map an arm's facts to site / caller / file units."""
    facts = row["facts"]
    if row["fact_kind"] == "loc":
        locs = [tuple(f) for f in facts]
        sites = set()
        site_calls = set()
        for f, l, c in locs:
            sites.add((f, l, c))
            cid = ix.name_tok.get((f, l, c))
            if cid:
                site_calls.add(cid)
        callers = {ix.enclosing(f, l) for f, l, c in locs}
        files = {f for f, l, c in locs}
        return {"sites": sites, "site_calls": site_calls, "callers": callers, "files": files, "n_units": len(sites)}
    callers = set(facts)
    files = set()
    for did in callers:
        if did.startswith("module:"):
            files.add(did[len("module:"):])
        elif did in ix.decls:
            files.add(ix.decls[did]["file"])
        else:
            files.add("?" + did)
    return {"sites": None, "site_calls": None, "callers": callers, "files": files, "n_units": len(callers)}


def score_repo(outdir: Path, repo: str, lang: str, layer: str, trace_file: Path | None = None, split: str | None = None) -> list[dict]:
    root = DATA / "repos" / repo
    tsc = TsClient(root) if lang == "ts" else None
    ix = I.load(root, lang, tsc)
    if tsc:
        tsc.close()
    # a declaration can be drawn into both natural samples; key by (declaration, sample)
    targets = {(t["decl"], t["sample"]): t for t in json.loads((outdir / f"{repo}.targets.json").read_text())}
    traced = None
    if trace_file and trace_file.exists() and lang == "py":
        tm = trace_map.load(ix.py, trace_file)
        traced = {}
        for (cid, did), v in tm["pairs"].items():
            if v["confirmed"]:
                traced.setdefault(did, set()).add(cid)
    file_tok: dict = {}

    def ftok(f):
        if f not in file_tok:
            try:
                file_tok[f] = tokens.count((root / f).read_text(encoding="utf-8", errors="replace"))[0]
            except OSError:
                file_tok[f] = 0
        return file_tok[f]

    rows = []
    by_target_arm: dict = {}
    for line in open(outdir / f"{repo}.results.jsonl"):
        r = json.loads(line)
        by_target_arm[(r["target"], r["sample"], r["task"], r["arm"])] = r
    for (tid, samp, task, arm), r in by_target_arm.items():
        t = targets[(tid, samp)]
        d = ix.decls[tid]
        u = units(ix, r)
        out = {k: r[k] for k in ("repo", "lang", "layer", "target", "sample", "task", "arm", "status", "truncated",
                                 "latency_s", "n_calls", "tok_native_cl100k", "tok_native_o200k", "tok_loc_cl100k",
                                 "tok_src_cl100k", "fact_kind", "note")}
        out.update({"split": split, "name": d["name"], "kind": d["kind"], "weight": t.get("weight", 1.0), "pattern": t.get("pattern"),
                    "ambiguous": t.get("ambiguous"), "in_codexa": t.get("in_codexa"),
                    "codexa_has_in_edge": t.get("codexa_has_in_edge"), "name_occurrences": t.get("name_occurrences"),
                    "stratum": "|".join(t.get("stratum", [])) if t.get("stratum") else None,
                    "provider_call_fanout": t.get("provider_call_fanout"), "n_units": u["n_units"],
                    "n_unresolved": sum(1 for x in u["callers"] if str(x).startswith("unresolved:"))})
        if task == "T1":
            gold_sets = []
            if layer == "fixture":
                g_calls = {g["call"] for g in t["gold"]["explicit"] if g["call"]}
                gold_sets.append(("A", g_calls))
                dyn = {g["call"] for g in t["gold"]["dynamic"] + t["gold"]["indirect"] if g["call"]}
                out["dyn_gold"] = len(dyn)
            if traced is not None:
                gold_sets.append(("C", traced.get(tid, set())))
            for lay, g_calls in gold_sets:
                g_callers = {ix.enclosing(ix.calls[c]["file"], ix.calls[c]["line"]) for c in g_calls}
                g_files = {ix.calls[c]["file"] for c in g_calls}
                pre = f"{lay}_"
                out[pre + "n_gold"] = len(g_calls)
                if u["site_calls"] is not None:
                    hit = u["site_calls"] & g_calls
                    out[pre + "site_recall"] = len(hit) / len(g_calls) if g_calls else None
                    out[pre + "site_precision"] = (sum(1 for s in u["sites"] if ix.name_tok.get(s) in g_calls) / len(u["sites"])) if u["sites"] else None
                p, rc = _pr(u["callers"], g_callers)
                out[pre + "caller_precision"], out[pre + "caller_recall"] = p, rc
                p, rc = _pr(u["files"], g_files)
                out[pre + "file_precision"], out[pre + "file_recall"] = p, rc
                out[pre + "complete"] = (rc_c := out[pre + "caller_recall"]) is not None and rc_c == 1.0
                if lay == "A":
                    out["A_wholefile_tokens"] = sum(ftok(f) for f in g_files | {d["file"]})
                # layer A: recall of dynamic/indirect sites at caller level (reported separately)
            if layer == "fixture" and r["fact_kind"] == "loc":
                dyn_calls = [g for g in t["gold"]["dynamic"]]
                out["A_dynamic_found"] = sum(1 for g in dyn_calls if (g["file"], g["line"], g["col"]) in u["sites"]) if dyn_calls else None
        else:  # T2
            gold = (d["file"], d["line"])
            ret = {(f, l) for f, l, c in (tuple(x) for x in r["facts"])}
            ret_decl = set()
            for f, l in ret:
                did = ix.decl_at_line(f, l)
                ret_decl.add(did or f"?{f}:{l}")
            out["T2_hit"] = ix.canon(tid) in ret_decl
            out["T2_precision"] = (1 / len(ret_decl)) if ix.canon(tid) in ret_decl else (0.0 if ret_decl else None)
            out["T2_n"] = len(ret_decl)
        out["_callers"] = sorted(map(str, u["callers"]))
        rows.append(out)
    # original-benchmark style whole-file payload (Q1): def file + files the Codexa graph says reference X
    # and the provider-based whole-file payload: def file + files of provider (LSP) call-site facts
    lsp = {r["target"]: r for (tid, samp, task, arm), r in by_target_arm.items() if arm == "lsp" and task == "T1"}
    cxo = {r["target"]: r for (tid, samp, task, arm), r in by_target_arm.items() if arm == "codexa_refs" and task == "T1"}
    for o in rows:
        if o["task"] != "T1":
            continue
        d = ix.decls[o["target"]]
        lf = {tuple(x)[0] for x in lsp[o["target"]]["facts"]} if o["target"] in lsp else set()
        o["wholefile_provider_tokens"] = sum(ftok(f) for f in (lf | {d["file"]}) if not f.startswith("<external>"))
        cf = set()
        for did in (cxo[o["target"]]["facts"] if o["target"] in cxo else []):
            if did in ix.decls:
                cf.add(ix.decls[did]["file"])
        o["wholefile_graphsel_tokens"] = sum(ftok(f) for f in cf | {d["file"]})
    return rows


if __name__ == "__main__":
    outdir = Path(sys.argv[1])
    allrows = []
    for meta in sorted(outdir.glob("*.meta.json")):
        m = json.loads(meta.read_text())
        tr = DATA / "traces" / f"{m['repo']}.json"
        allrows += score_repo(outdir, m["repo"], m["lang"], m["layer"], tr, m.get("split"))
    with open(outdir / "scored.jsonl", "w") as fh:
        for r in allrows:
            fh.write(json.dumps(r) + "\n")
    print(len(allrows), "rows")
