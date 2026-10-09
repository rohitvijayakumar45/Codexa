"""Compare two codebase-memory arms query by query (facts, status, native token count).

Usage: python -m nb.compare_versions <run_dir_a> <arm_a> <run_dir_b> <arm_b> [<out.json>]
Example: python -m nb.compare_versions /work/nb/out-main cbm_057 /work/nb/out-055 cbm_055
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path


def load(run_dir: Path, arm: str) -> dict:
    out = {}
    for f in sorted(run_dir.glob("*.results.jsonl")):
        for line in open(f):
            r = json.loads(line)
            if r["arm"] in (arm, arm + "_def"):
                out[(r["repo"], r["target"], r["sample"], r["task"])] = r
    return out


def main():
    a, b = load(Path(sys.argv[1]), sys.argv[2]), load(Path(sys.argv[3]), sys.argv[4])
    res = Counter()
    diffs = []
    for k in sorted(set(a) | set(b)):
        if k not in a or k not in b:
            res["missing_" + ("a" if k not in a else "b")] += 1
            continue
        x, y = a[k], b[k]
        same_facts = sorted(map(str, x["facts"])) == sorted(map(str, y["facts"])) and x["status"] == y["status"]
        same_tok = x["tok_native_cl100k"] == y["tok_native_cl100k"]
        res["queries"] += 1
        res["same_facts"] += same_facts
        res["same_tokens"] += same_tok
        if not (same_facts and same_tok):
            diffs.append({"key": list(k), "a": [x["status"], x["facts"][:5], x["tok_native_cl100k"]],
                          "b": [y["status"], y["facts"][:5], y["tok_native_cl100k"]]})
    out = {"summary": dict(res), "differences": diffs}
    print(json.dumps(out["summary"]), len(diffs), "differences")
    if len(sys.argv) > 5:
        Path(sys.argv[5]).write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
