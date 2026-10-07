"""Post-freeze supplementary arm: codebase-memory-mcp v0.5.5 (the release the Codebase-Memory preprint evaluates).

Re-uses the frozen targets of a completed run (no re-sampling) and the v0.5.7 adapter (same MCP interface).
Writes <out>/<repo>.results.jsonl with only the cbm_055 rows, plus copies of the targets and meta files,
so that nb.score can score it on its own.
Usage: python -m nb.run_extra_arm <main_out_dir> <repo> <lang> <layer> <out_dir> [<version label> [<binary>]]
The optional version label ("055" by default; "cur" selects the current-version adapter) and binary also allow
re-running an existing version on the same targets, to measure the tool's run-to-run stability.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path

os.environ.setdefault("CODEXA_DATA_DIR", "/work/nb")
NB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(NB_ROOT.parent.parent))

from nb import arms as A  # noqa: E402
from nb import index as I  # noqa: E402
from nb.run import record  # noqa: E402
from nb.tsclient import TsClient  # noqa: E402

CBM_055 = os.environ.get("NB_CBM_055", "/work/nb/bin/cbm-055")


def main() -> None:
    main_out, repo, lang, layer, outdir = Path(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4], Path(sys.argv[5])
    ver = sys.argv[6] if len(sys.argv) > 6 else "055"
    binary = sys.argv[7] if len(sys.argv) > 7 else CBM_055
    root = Path(os.environ["CODEXA_DATA_DIR"]) / "repos" / repo
    outdir.mkdir(parents=True, exist_ok=True)
    targets = json.loads((main_out / f"{repo}.targets.json").read_text())
    meta = json.loads((main_out / f"{repo}.meta.json").read_text())
    shutil.copy(main_out / f"{repo}.targets.json", outdir / f"{repo}.targets.json")
    tsc = TsClient(root) if lang == "ts" else None
    ix = I.load(root, lang, tsc)
    home = f"/work/nb/cbmhome-extra-{ver}"
    Path(home).mkdir(parents=True, exist_ok=True)
    c = A.CBM(binary, home, root, ver)
    meta[f"cbm_{ver}_index_s"], meta[f"cbm_{ver}_ok"] = c.index_s, c.ok
    gate: list[str] = []
    cache: dict = {}
    with open(outdir / f"{repo}.results.jsonl", "w") as out:
        for qi, tg in enumerate(targets):
            d = ix.decls[tg["decl"]]
            base = {"repo": repo, "lang": lang, "layer": layer, "target": tg["decl"], "sample": tg["sample"],
                    "task": "T1", "query_index": qi, "name": d["name"]}
            record(out, base, c.callers(ix, d["name"], d), ix, cache, gate)
            if layer == "fixture":
                ex = [g for g in tg["gold"]["explicit"] if g["call"]]
                if ex:
                    site = (ex[0]["file"], ex[0]["line"], ex[0]["col"])
                    record(out, dict(base, task="T2", site=list(site)), c.definition(ix, d["name"]), ix, cache, gate)
    c.close()
    if tsc:
        tsc.close()
    meta[f"gate_messages_{ver}"] = gate
    meta[f"finished_{ver}"] = time.time()
    (outdir / f"{repo}.meta.json").write_text(json.dumps(meta, indent=1))
    print(json.dumps({"repo": repo, "targets": len(targets), "gate": len(gate)}))


if __name__ == "__main__":
    main()
