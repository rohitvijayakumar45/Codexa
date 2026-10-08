"""Enrich already-scored rows without re-running any tool.

Older scored files (including the frozen confirmatory run, results/main/scored.jsonl.gz) predate
feature A (gold caller lists for policy evaluation) and feature B (MSA tokens). Both are pure
functions of data that is already stored:

  * layer-A gold callers  = enclosing declarations of each target's explicit sites — the sites (as
    call ids) are in <repo>.targets.json, and the independent index is deterministic, so regenerating
    the fixture (nb.fixtures; byte-identical, checked) and re-indexing reproduces the mapping;
  * MSA tokens            = cl100k count of forms.render_msa over the row's `_callers`.

Only fixture rows can be enriched offline (natural repositories need their pinned checkouts).

Usage: python -m nb.offline <scored.jsonl[.gz]> <targets_dir> <repos_dir> <out.jsonl>
"""
from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

NB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(NB_ROOT))

from nb import forms  # noqa: E402
from nb import index as I  # noqa: E402
from nb import tokens  # noqa: E402
from nb.score import fixture_gold_callers  # noqa: E402
from nb.tsclient import TsClient  # noqa: E402


def read_rows(path: Path) -> list[dict]:
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def write_rows(path: Path, rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def load_index(repos_dir: Path, repo: str, lang: str):
    root = repos_dir / repo
    tsc = TsClient(root) if lang == "ts" else None
    try:
        return I.load(root, lang, tsc)
    finally:
        if tsc:
            tsc.close()


def enrich(rows: list[dict], targets_dir: Path, repos_dir: Path) -> dict:
    stats = {"repos": 0, "gold_added": 0, "msa_added": 0, "skipped_repos": []}
    by_repo: dict[str, list[dict]] = {}
    for r in rows:
        if r.get("layer") == "fixture":
            by_repo.setdefault(r["repo"], []).append(r)
    for repo, rs in sorted(by_repo.items()):
        tpath = targets_dir / f"{repo}.targets.json"
        if not tpath.exists() or not (repos_dir / repo).exists():
            stats["skipped_repos"].append(repo)
            continue
        ix = load_index(repos_dir, repo, rs[0]["lang"])
        targets = {t["decl"]: t for t in json.loads(tpath.read_text())}
        stats["repos"] += 1
        for r in rs:
            if r.get("task") != "T1":
                continue
            t = targets.get(r["target"])
            if t and "A_gold_callers" not in r:
                r["A_gold_callers"] = sorted(fixture_gold_callers(ix, t))
                stats["gold_added"] += 1
            if r.get("tok_msa_cl100k") is None and r.get("status") != "unsupported":
                r["tok_msa_cl100k"] = tokens.count(forms.render_msa(ix, r.get("_callers", [])))[0]
                stats["msa_added"] += 1
    return stats


if __name__ == "__main__":
    src, tdir, rdir, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])
    rows = read_rows(src)
    print(json.dumps(enrich(rows, tdir, rdir)))
    write_rows(out, rows)
