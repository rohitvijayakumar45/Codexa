"""Map raw runtime records (nb.trace_run) onto the independent Python index."""
from __future__ import annotations

import json
from pathlib import Path

from nb.pyindex import PyIndex


def _ch(root: Path, cache: dict, rel: str, line: int, bcol: int) -> int:
    lines = cache.get(rel)
    if lines is None:
        try:
            lines = cache[rel] = (root / rel).read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            lines = cache[rel] = []
    if not (0 < line <= len(lines)):
        return bcol
    return len(lines[line - 1].encode("utf-8")[:bcol].decode("utf-8", errors="ignore"))


def map_records(idx: PyIndex, raw: dict) -> dict:
    """Returns {"pairs": {(call_id, decl_id): {"attempted", "confirmed"}}, "unmapped": {...}}"""
    root = idx.root
    cache: dict = {}
    pairs: dict[tuple[str, str], dict] = {}
    unmapped = {"site": 0, "callee": 0, "decorator_application": 0}
    by_qual = {(d.file, d.qualname): d.id for d in idx.decls.values()}
    for r in raw["records"]:
        if r["line"] is None or r["bcol"] is None:
            unmapped["site"] += 1
            continue
        f = r["site_file"]
        key = (f, r["line"], _ch(root, cache, f, r["line"], r["bcol"]), r["end_line"],
               _ch(root, cache, f, r["end_line"], r["end_bcol"]))
        cid = idx.by_span.get(key)
        if cid is None:
            # decorator applications are calls without an ast.Call node (implicit calls)
            unmapped["decorator_application" if (f, r["line"]) in idx.decorator_sites else "site"] += 1
            continue
        cf = r["callee_file"]
        if r["callee_kind"] == "class":
            did = by_qual.get((cf, r["callee_qualname"]))
        else:
            did = idx.by_codekey.get((cf, r["callee_firstline"]))
            if did is None or idx.decls[did].qualname.split(".")[-1] != r["callee_qualname"].split(".")[-1]:
                did = by_qual.get((cf, r["callee_qualname"].replace(".<locals>", "")), did)
        if did is None:
            unmapped["callee"] += 1
            continue
        p = pairs.setdefault((cid, did), {"attempted": 0, "confirmed": 0})
        p["attempted"] += r["attempted"]
        p["confirmed"] += r["confirmed"]
    return {"pairs": pairs, "unmapped": unmapped, "stats": raw.get("stats", {})}


def load(idx: PyIndex, path: Path) -> dict:
    return map_records(idx, json.loads(path.read_text()))
