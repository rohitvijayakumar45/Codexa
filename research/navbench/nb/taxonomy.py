"""Error taxonomy for graph-arm misses on held-out fixtures (layer A) and observed calls (layer C).

For Codexa the graph is inspectable, so each missed gold caller is classified:
  target_missing      target declaration absent from the graph
  module_level_caller gold call site is at module level (Codexa attributes no caller there)
  caller_missing      enclosing caller declaration absent from the graph
  wrong_resolution    caller has a `calls` edge to a different node with the target's name
  no_relation         caller present, no `calls` edge to any node with the target's name
  truncated           output hit the tool's own result cap
For codebase-memory-mcp only output-level causes are observable: target_missing (not found /
not among suggestions), truncated, and missed_relation_unobservable.
Usage: python -m nb.taxonomy <out_dir with scored.jsonl>
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

os.environ.setdefault("CODEXA_DATA_DIR", "/work/nb")
NB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(NB_ROOT.parent.parent))
sys.path.insert(0, str(NB_ROOT))

from nb import arms as A  # noqa: E402
from nb import index as I  # noqa: E402
from nb import trace_map  # noqa: E402
from nb.tsclient import TsClient  # noqa: E402

DATA = Path(os.environ["CODEXA_DATA_DIR"])


def main():
    outdir = Path(sys.argv[1])
    rows = [json.loads(l) for l in open(outdir / "scored.jsonl")]
    by_repo = defaultdict(list)
    for r in rows:
        if r["task"] == "T1" and r["arm"] in ("codexa_refs", "codexa_orig", "cbm_cur", "cbm_057") and \
                ((r["layer"] == "fixture" and r.get("split") != "calib" and r.get("A_n_gold")) or r.get("C_n_gold")):
            by_repo[(r["repo"], r["lang"], r["layer"])].append(r)
    counts = defaultdict(Counter)
    for (repo, lang, layer), rs in by_repo.items():
        root = DATA / "repos" / repo
        tsc = TsClient(root) if lang == "ts" else None
        ix = I.load(root, lang, tsc)
        if tsc:
            tsc.close()
        targets = {t["decl"]: t for t in json.loads((outdir / f"{repo}.targets.json").read_text())}
        traced = None
        if layer == "natural" and lang == "py" and (DATA / "traces" / f"{repo}.json").exists():
            tm = trace_map.load(ix.py, DATA / "traces" / f"{repo}.json")
            traced = defaultdict(set)
            for (cid, did), v in tm["pairs"].items():
                if v["confirmed"]:
                    traced[did].add(cid)
        cx = A.CodexaGraph(repo)
        nodes = [n for n in cx.graph.list_nodes() if n.node_type == "CodeSymbol" and n.properties.get("repository") == repo]
        node_by_key = {}
        for n in nodes:
            node_by_key.setdefault((n.properties.get("file"), n.properties.get("line")), n)
        by_id = {n.id: n for n in nodes}
        out_calls = defaultdict(list)
        for e in cx.graph.list_edges_at():
            if e.edge_type == "calls":
                out_calls[e.from_node_id].append(e.to_node_id)

        def node_for(did):
            d = ix.decls[did]
            return node_by_key.get((d["file"], d["line"])) or node_by_key.get((d["file"], d["first_line"]))

        for r in rs:
            t = targets[r["target"]]
            d = ix.decls[r["target"]]
            if layer == "fixture":
                gold_calls = {g["call"] for g in t["gold"]["explicit"] if g["call"]}
                lay = "A"
            else:
                gold_calls = traced.get(r["target"], set()) if traced else set()
                lay = "C"
            gold_callers = {ix.enclosing(ix.calls[c]["file"], ix.calls[c]["line"]) for c in gold_calls}
            missed = gold_callers - set(r["_callers"])
            key = (lay, r["arm"])
            counts[key]["gold_callers"] += len(gold_callers)
            counts[key]["missed"] += len(missed)
            for g in missed:
                if r["arm"].startswith("codexa"):
                    tn = node_for(r["target"])
                    if tn is None:
                        c = "target_missing"
                    elif g.startswith("module:"):
                        c = "module_level_caller"
                    elif node_for(g) is None:
                        c = "caller_missing"
                    else:
                        gn = node_for(g)
                        callee_names = {by_id[x].properties.get("name") for x in out_calls.get(gn.id, []) if x in by_id}
                        tgt_ids = set(out_calls.get(gn.id, []))
                        if tn.id in tgt_ids:
                            c = "truncated" if r["truncated"] else "lookup_mismatch"
                        elif d["name"] in callee_names:
                            c = "wrong_resolution"
                        else:
                            c = "no_relation"
                else:
                    note = (r.get("note") or "").lower()
                    if r["status"] == "empty" and ("not found" in note or "suggestion" in note):
                        c = "target_missing"
                    elif r["truncated"]:
                        c = "truncated"
                    else:
                        c = "missed_relation_unobservable"
                counts[key][c] += 1
    res = {f"{k[0]}|{k[1]}": dict(v) for k, v in counts.items()}
    (outdir / "taxonomy.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
