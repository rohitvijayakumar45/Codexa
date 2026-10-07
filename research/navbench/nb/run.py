"""Run all arms on one repository (fixture or natural) and write JSONL results.

Usage: python -m nb.run <repo_name> <lang py|ts> <layer fixture|natural> <out_dir> [--per-sample N]

Repositories live in $CODEXA_DATA_DIR/repos/<repo_name> (Codexa requires this layout).
"""
from __future__ import annotations

import json
import os
import random
import sys
import time
from pathlib import Path

os.environ.setdefault("CODEXA_DATA_DIR", "/work/nb")
NB_ROOT = Path(__file__).resolve().parent.parent
CODEXA_ROOT = NB_ROOT.parent.parent
sys.path.insert(0, str(CODEXA_ROOT))

from nb import arms as A  # noqa: E402
from nb import index as I  # noqa: E402
from nb import tokens  # noqa: E402
from nb.lsp import PyrightClient  # noqa: E402
from nb.tsclient import TsClient  # noqa: E402

CBM_CUR = os.environ.get("NB_CBM_CUR", "/work/nb/bin/cbm-cur")
CBM_057 = os.environ.get("NB_CBM_057", "/work/nb/bin/cbm-057")
SEED = 20261008
FANOUT_BUCKETS = [(0, 0), (1, 2), (3, 9), (10, 10 ** 9)]


def bucket(n: int) -> str:
    for lo, hi in FANOUT_BUCKETS:
        if lo <= n <= hi:
            return f"{lo}-{hi if hi < 10 ** 9 else 'inf'}"
    return "?"


def forms(ix: Index, res: A.ArmResult, lines_cache: dict) -> tuple[str, str | None, list]:
    """(loc form, src form, facts parsed back from loc form) — loc/src re-serialise only returned facts."""
    if res.fact_kind == "loc":
        loc = "\n".join(f"{f}:{l}:{c}" for f, l, c in res.facts)
        src_lines = []
        for f, l, c in res.facts:
            text = _line(ix, f, l, lines_cache)
            src_lines.append(f"{f}:{l}:{c}: {text.strip()}")
        back = [tuple([x.rsplit(":", 2)[0], int(x.rsplit(":", 2)[1]), int(x.rsplit(":", 2)[2])]) for x in loc.splitlines()]
        return loc, "\n".join(src_lines), back
    out = []
    for did in res.facts:
        if did.startswith("unresolved:") or did.startswith("module:"):
            out.append(did)
        else:
            d = ix.decls[did]
            out.append(f"{d['file']}::{d['qualname']}")
    back = []
    rev = {f"{f}::{q}": did for (f, q), did in ix.by_qual.items()}
    for x in out:
        back.append(rev.get(x, x))
    return "\n".join(out), None, back


Index = I.Index


def _line(ix: Index, f: str, l: int, cache: dict) -> str:
    if f not in cache:
        try:
            cache[f] = (ix.root / f).read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            cache[f] = []
    ls = cache[f]
    return ls[l - 1] if 0 < l <= len(ls) else ""


def record(out, base: dict, res: A.ArmResult, ix: Index, cache: dict, gate: list) -> None:
    loc, src, back = forms(ix, res, cache)
    if [tuple(x) if isinstance(x, list) else x for x in back] != [tuple(x) if isinstance(x, (list, tuple)) else x for x in res.facts]:
        gate.append(f"form-equivalence failed: {base.get('target')} {res.arm}")
    n_cl, n_o2 = tokens.count(res.native)
    l_cl, l_o2 = tokens.count(loc)
    s_cl, s_o2 = tokens.count(src) if src is not None else (None, None)
    row = dict(base, arm=res.arm, status=res.status, fact_kind=res.fact_kind, facts=res.facts, truncated=res.truncated,
               latency_s=round(res.latency_s, 4), n_calls=res.n_calls, note=res.note,
               tok_native_cl100k=n_cl, tok_native_o200k=n_o2, tok_loc_cl100k=l_cl, tok_loc_o200k=l_o2,
               tok_src_cl100k=s_cl, tok_src_o200k=s_o2, native_chars=len(res.native))
    out.write(json.dumps(row) + "\n")


def main() -> None:
    repo, lang, layer, outdir = sys.argv[1], sys.argv[2], sys.argv[3], Path(sys.argv[4])
    per_sample = int(sys.argv[sys.argv.index("--per-sample") + 1]) if "--per-sample" in sys.argv else 40
    root = Path(os.environ["CODEXA_DATA_DIR"]) / "repos" / repo
    outdir.mkdir(parents=True, exist_ok=True)
    meta = {"repo": repo, "lang": lang, "layer": layer, "started": time.time()}
    gate: list[str] = []
    rng = random.Random(f"{SEED}:{repo}")

    # ---------------------------------------------------------------- setup (timed separately)
    t = time.perf_counter()
    ts_client = TsClient(root) if lang == "ts" else None
    ix = I.load(root, lang, ts_client)
    meta["index_frame_s"] = time.perf_counter() - t
    meta["frame"] = {"files": len(ix.files), "decls": len(ix.decls), "calls": len(ix.calls), "parse_failures": ix.failures[:50],
                     "n_parse_failures": len(ix.failures)}
    if lang == "py":
        venv_py = root.parent.parent / "venvs" / repo / "bin" / "python"
        provider = PyrightClient(root, python=str(venv_py) if venv_py.exists() else None)
        # probes: the 5 declarations with the most same-name occurrences across the frame's call nodes
        name_calls: dict = {}
        for c_ in ix.calls.values():
            if c_["name"]:
                name_calls[c_["name"]] = name_calls.get(c_["name"], 0) + 1
        probe_decls = sorted((d for d in ix.decls.values() if d["kind"] in ("function", "method", "class")),
                             key=lambda d: -name_calls.get(d["name"], 0))[:5]
        meta["provider_warmup"] = provider.warm(ix.files, [(d["file"], d["line"], d["col"]) for d in probe_decls])
    else:
        provider = ts_client
    t = time.perf_counter()
    cx = A.CodexaGraph(repo)
    meta["codexa_index_s"] = cx.index_s
    meta["codexa_ok"] = cx.ok
    cbms = {}
    for ver, binary in (("cur", CBM_CUR), ("057", CBM_057)):
        home = f"/work/nb/cbmhome-{ver}"
        Path(home).mkdir(parents=True, exist_ok=True)
        c = A.CBM(binary, home, root, ver)
        cbms[ver] = c
        meta[f"cbm_{ver}_index_s"] = c.index_s
        meta[f"cbm_{ver}_ok"] = c.ok

    # Codexa graph coverage of the frame (missing definitions), by (file, def line)
    cx_nodes = [n for n in cx.graph.list_nodes() if n.node_type == "CodeSymbol" and n.properties.get("repository") == repo]
    cx_keys = {(n.properties.get("file"), n.properties.get("line")) for n in cx_nodes}
    in_edges: dict = {}
    for e in cx.graph.list_edges_at():
        if e.edge_type in ("imports", "calls", "depends_on", "flows_into"):
            in_edges.setdefault(e.to_node_id, 0)
            in_edges[e.to_node_id] += 1
    cond_keys = {(n.properties.get("file"), n.properties.get("line")) for n in cx_nodes if n.id in in_edges}
    frame_targets = [d for d in ix.decls.values() if not d["is_test"] and d["kind"] in ("function", "method", "class")]
    meta["coverage"] = {"frame_targets": len(frame_targets),
                        "codexa_has": sum(1 for d in frame_targets if (d["file"], d["line"]) in cx_keys or (d["file"], d["first_line"]) in cx_keys),
                        "codexa_nodes": len(cx_nodes),
                        "codexa_nodes_not_in_frame": sum(1 for k in cx_keys if k not in {(d["file"], d["line"]) for d in ix.decls.values()}
                                                         and k not in {(d["file"], d["first_line"]) for d in ix.decls.values()})}

    # ---------------------------------------------------------------- targets
    targets = []   # dicts: decl, sample, weight, gold (fixture) / provider fanout
    if layer == "fixture":
        man = json.loads((root / ".navbench-manifest.json").read_text())
        meta["split"] = man.get("split")
        for t_ in man["targets"]:
            did = f"{t_['file']}:{t_['line']}:{t_['col']}"
            gold = {"explicit": [], "dynamic": [], "indirect": [], "reference": [], "distractor": []}
            for s in t_["sites"]:
                cid = ix.name_tok.get((s["file"], s["line"], s["col"]))
                gold[s["category"]].append({"file": s["file"], "line": s["line"], "col": s["col"], "call": cid,
                                            "caller": s["caller"]})
            targets.append({"decl": did, "sample": "fixture", "weight": 1.0, "pattern": t_["key"], "gold": gold,
                             "ambiguous": man["ambiguous"]})
    else:
        pool = rng.sample(frame_targets, min(300, len(frame_targets)))
        fan = {}
        for d in pool:
            try:
                locs = provider.references(d["file"], d["line"], d["col"])
            except Exception:  # noqa: BLE001
                locs = None
            fan[d["id"]] = None if locs is None else sum(1 for (f, l, c) in locs if (f, l, c) in ix.name_tok)
        strata: dict = {}
        for d in pool:
            k = (d["kind"], bucket(fan[d["id"]]) if fan[d["id"]] is not None else "provider-error")
            strata.setdefault(k, []).append(d)
        n_total = per_sample
        alloc = {k: max(2, round(n_total * len(v) / len(pool))) for k, v in strata.items()}
        while sum(alloc.values()) > n_total and max(alloc.values()) > 2:
            k = max(alloc, key=alloc.get)
            alloc[k] -= 1
        scale = len(frame_targets) / len(pool)
        for k, v in strata.items():
            pick = rng.sample(v, min(alloc[k], len(v)))
            w = scale * len(v) / len(pick)
            for d in pick:
                targets.append({"decl": d["id"], "sample": "S-ind", "weight": w, "stratum": list(k),
                                "provider_call_fanout": fan[d["id"]]})
        cond = [d for d in frame_targets if (d["file"], d["line"]) in cond_keys or (d["file"], d["first_line"]) in cond_keys]
        for d in rng.sample(cond, min(per_sample // 2, len(cond))):
            targets.append({"decl": d["id"], "sample": "S-cond", "weight": len(cond) / max(1, min(per_sample // 2, len(cond)))})
        meta["strata"] = {f"{k[0]}|{k[1]}": [len(v), alloc[k]] for k, v in strata.items()}
        meta["n_cond_frame"] = len(cond)
    for tg in targets:
        d = ix.decls[tg["decl"]]
        tg["in_codexa"] = (d["file"], d["line"]) in cx_keys or (d["file"], d["first_line"]) in cx_keys
        tg["codexa_has_in_edge"] = (d["file"], d["line"]) in cond_keys or (d["file"], d["first_line"]) in cond_keys
        tg["name_occurrences"] = None
    (outdir / f"{repo}.targets.json").write_text(json.dumps(targets))

    # ---------------------------------------------------------------- queries
    cache: dict = {}
    with open(outdir / f"{repo}.results.jsonl", "w") as out:
        for qi, tg in enumerate(targets):
            d = ix.decls[tg["decl"]]
            base = {"repo": repo, "lang": lang, "layer": layer, "target": tg["decl"], "sample": tg["sample"],
                    "task": "T1", "query_index": qi, "name": d["name"]}
            r0 = A.rg(ix, d["name"], 0)
            tg["name_occurrences"] = len(r0.facts)
            for res in (r0, A.rg(ix, d["name"], 3), A.lsp_refs(ix, provider, d), cx.refs(ix, d["name"]),
                        cx.orig(ix, d["name"], d), cbms["cur"].callers(ix, d["name"], d),
                        cbms["057"].callers(ix, d["name"], d)):
                record(out, base, res, ix, cache, gate)
            # whole-file sensitivity payload: defining file + files of every provider call-site reference
            # (fixtures: + gold explicit sites)
            # T2: definition lookup from one call site
            site = None
            if layer == "fixture":
                ex = [g for g in tg["gold"]["explicit"] if g["call"]]
                if ex:
                    g = ex[0]
                    site = (g["file"], g["line"], g["col"])
            if site:
                b2 = dict(base, task="T2", site=list(site))
                for res in (A.lsp_def(ix, provider, site, d["name"]),
                            A.rg(ix, d["name"], 0, pattern=A.DEF_PATTERNS[lang](d["name"]), label="rg_def"),
                            cx.lookup(ix, d["name"]), cbms["cur"].definition(ix, d["name"]),
                            cbms["057"].definition(ix, d["name"])):
                    record(out, b2, res, ix, cache, gate)
    (outdir / f"{repo}.targets.json").write_text(json.dumps(targets))
    meta["gate_messages"] = gate
    meta["finished"] = time.time()
    (outdir / f"{repo}.meta.json").write_text(json.dumps(meta, indent=1))
    for c in cbms.values():
        c.close()
    if lang == "py":
        provider.close()
    if ts_client:
        ts_client.close()
    print(json.dumps({"repo": repo, "targets": len(targets), "gate": len(gate)}))


if __name__ == "__main__":
    main()
