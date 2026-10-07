"""Re-apply the original G1 benchmark definition to the public corpus.

Original definition: graph-conditioned targets (S-cond), payload = whole files the graph selects
(defining file + files of the graph's callers), compared with the `lookup_symbol` + `get_dependencies`
output (`codexa_orig`). Also reports the same outputs against `rg -w`.
Usage: python -m nb.replicate_original <scored.jsonl[.gz]> <out.json>
"""
from __future__ import annotations

import gzip
import random
import json
import math
import statistics as st
import sys
from collections import defaultdict


def main():
    p = sys.argv[1]
    rows = [json.loads(l) for l in (gzip.open(p, "rt") if p.endswith(".gz") else open(p))]
    by = defaultdict(dict)
    for r in rows:
        if r["layer"] == "natural" and r["task"] == "T1":
            by[(r["sample"], r["repo"], r["target"])][r["arm"]] = r
    out = {}
    for samp in ("S-cond", "S-ind"):
        for label, num in (("wholefile_graphsel", lambda a: a["codexa_orig"]["wholefile_graphsel_tokens"]),
                           ("rg0", lambda a: a["rg0"]["tok_native_cl100k"])):
            per, tot = defaultdict(list), defaultdict(lambda: [0, 0])
            for (s, repo, t), a in by.items():
                g = a.get("codexa_orig")
                if s != samp or not g or g["status"] != "ok" or not g["tok_native_cl100k"]:
                    continue
                n = num(a)
                if not n:
                    continue
                per[repo].append(math.log(n / g["tok_native_cl100k"]))
                tot[repo][0] += n
                tot[repo][1] += g["tok_native_cl100k"]
            rng = random.Random(20261008)
            keys = list(per)
            boots = []
            for _ in range(2000):  # hierarchical bootstrap: repositories, then targets
                ks = [rng.choice(keys) for _ in keys]
                boots.append(math.exp(st.mean([st.mean([rng.choice(per[k]) for _ in per[k]]) for k in ks])))
            boots.sort()
            out[f"{samp}|{label}/codexa_orig"] = {
                "ci95": [boots[50], boots[1949]],
                "repo_macro_geomean": math.exp(st.mean([st.mean(v) for v in per.values()])),
                "pooled_ratio": sum(x[0] for x in tot.values()) / sum(x[1] for x in tot.values()),
                "n_targets": sum(len(v) for v in per.values()), "n_repos": len(per)}
    json.dump(out, open(sys.argv[2], "w"), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
