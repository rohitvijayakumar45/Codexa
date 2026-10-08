"""Check that a new run reproduces the frozen run for every arm both contain (CLOUD_HANDOFF.md §1).

Compares raw rows keyed by (repo, target, sample, task, arm): facts + status, and native token counts.
Usage: python -m nb.equivalence <frozen_run_dir> <new_run_dir> [<out.json>]
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


def load(d: Path) -> dict:
    out = {}
    for f in sorted(d.glob("*.results.jsonl")):
        for line in open(f):
            r = json.loads(line)
            out[(r["repo"], r["target"], r["sample"], r["task"], r["arm"])] = r
    return out


def main():
    old, new = load(Path(sys.argv[1])), load(Path(sys.argv[2]))
    common = sorted(set(old) & set(new))
    per = defaultdict(Counter)
    examples = defaultdict(list)
    for k in common:
        a, b = old[k], new[k]
        arm = k[4]
        per[arm]["rows"] += 1
        same = a["status"] == b["status"] and sorted(map(str, a["facts"])) == sorted(map(str, b["facts"]))
        per[arm]["same_facts"] += same
        per[arm]["same_tokens"] += a["tok_native_cl100k"] == b["tok_native_cl100k"]
        if not same and len(examples[arm]) < 5:
            examples[arm].append({"key": list(k), "frozen": [a["status"], a["facts"][:4]], "new": [b["status"], b["facts"][:4]]})
    repos_old = {k[0] for k in old}
    only_old = Counter(k[4] for k in set(old) - set(new) if k[0] in {x[0] for x in new})
    res = {"per_arm": {a: dict(c) for a, c in sorted(per.items())}, "frozen_rows_missing_in_new": dict(only_old),
           "repos_frozen": len(repos_old), "examples": examples}
    for a, c in sorted(per.items()):
        print(f"{a:14s} rows {c['rows']:5d}  same facts {c['same_facts']:5d}  same tokens {c['same_tokens']:5d}")
    if only_old:
        print("frozen rows missing in new run (same repos):", dict(only_old))
    if len(sys.argv) > 3:
        Path(sys.argv[3]).write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
