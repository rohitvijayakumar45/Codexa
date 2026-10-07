"""Gate 1 (fixtures): manifest, independent index and runtime tracer must agree.

Python: for every target, the traced call sites (confirmed entries) must equal the manifest's
explicit + dynamic + indirect sites, compared as (file, line). The index must contain each target
declaration at the manifest position and a call node at each explicit site.
TypeScript: the independent TS index must contain each target declaration and a call node at
each explicit site (compile + run were checked when the fixtures were generated).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from nb import pyindex, trace_map
from nb.tsclient import TsClient

PY = sys.executable


def check_py(root: Path) -> list[str]:
    man = json.loads((root / ".navbench-manifest.json").read_text())
    idx = pyindex.load(root)
    errs = []
    out = root.parent / f".trace-{root.name}.json"
    subprocess.run([PY, "-m", "nb.trace_run", str(root), str(out), "--", "main.py"], check=True,
                   cwd=Path(__file__).resolve().parent.parent, capture_output=True)
    tr = trace_map.load(idx, out)
    out.unlink()
    for t in man["targets"]:
        did = f"{t['file']}:{t['line']}:{t['col']}"
        if did not in idx.decls:
            errs.append(f"{root.name}: decl missing {did} {t['key']}")
            continue
        for s in t["sites"]:
            if s["category"] == "explicit" and (s["file"], s["line"], s["col"]) not in idx.by_name_token:
                errs.append(f"{root.name}: no call node at explicit site {s}")
        want = {(s["file"], s["line"]) for s in t["sites"] if s["category"] in ("explicit", "dynamic", "indirect")}
        got = {(idx.calls[c].file, idx.calls[c].line) for (c, d), v in tr["pairs"].items() if d == did and v["confirmed"]}
        if want != got:
            errs.append(f"{root.name}:{t['key']} manifest-only={sorted(want - got)} trace-only={sorted(got - want)}")
    if tr["unmapped"]["site"] or tr["unmapped"]["callee"]:  # decorator applications are expected
        errs.append(f"{root.name}: unmapped trace records {tr['unmapped']}")
    return errs


def check_ts(root: Path) -> list[str]:
    man = json.loads((root / ".navbench-manifest.json").read_text())
    c = TsClient(root)
    ix = c.index()
    c.close()
    decl_ids = {d["id"] for d in ix["decls"]}
    call_ids = {x["id"] for x in ix["calls"]}
    errs = []
    for t in man["targets"]:
        if f"{t['file']}:{t['line']}:{t['col']}" not in decl_ids:
            errs.append(f"{root.name}: decl missing {t['key']}")
        for s in t["sites"]:
            if s["category"] == "explicit" and f"{s['file']}:{s['line']}:{s['col']}" not in call_ids:
                errs.append(f"{root.name}: no call node at explicit site {s}")
    return errs


if __name__ == "__main__":
    base = Path(sys.argv[1])
    errs = []
    for d in sorted(base.glob("fx-py-*")):
        errs += check_py(d)
    for d in sorted(base.glob("fx-ts-*")):
        errs += check_ts(d)
    print("\n".join(errs) if errs else "GATE fixtures: PASS")
    sys.exit(1 if errs else 0)
