"""Re-score finished runs from their transcripts, without calling the model again.

The agent's only write tool is `replace_in_file`, which is deterministic, so replaying its calls in
order on a fresh copy of the fixture rebuilds the agent's final tree exactly. Used when the oracle
changes (e.g. the signature-change requirement added after the first pilot).

    python -m ab.regrade <run dir> --fixtures <fixtures dir>

Rewrites <run dir>/results.jsonl in place (the old file is kept as results.pre-regrade.jsonl).
"""
from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path

from ab.agent import Workspace
from ab.tasks import Task, check, materialize


def edits(transcript: list[dict]) -> list[dict]:
    out = []
    for m in transcript:
        if m.get("role") != "assistant":
            continue
        for c in m.get("tool_calls") or []:
            if c["function"]["name"] != "replace_in_file":
                continue
            try:
                out.append(json.loads(c["function"].get("arguments") or "{}"))
            except json.JSONDecodeError:
                continue
    return out


def replay(task: Task, transcript: list[dict], fixtures: Path, dest: Path) -> dict:
    root = materialize(task, fixtures, dest)
    ws = Workspace(root, task.lang, [])
    for args in edits(transcript):
        try:
            ws.replace_in_file(**args)
        except Exception:  # noqa: BLE001 - the same call failed (and was reported) during the run
            continue
    return check(task, root)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--fixtures", required=True)
    a = ap.parse_args()
    run = Path(a.run_dir)
    tasks = {t["id"]: Task(**t) for t in json.loads((run / "tasks.json").read_text())}
    rows = [json.loads(l) for l in open(run / "results.jsonl", encoding="utf-8") if l.strip()]
    shutil.copy(run / "results.jsonl", run / "results.pre-regrade.jsonl")
    changed = 0
    with tempfile.TemporaryDirectory(prefix="ab-regrade-") as tmp:
        for r in rows:
            t = tasks[r["task"]]
            name = f"ab-{t.repo}-{t.target_key}-{r['condition']}-r{r['rep']}"
            transcript = json.loads((run / "transcripts" / f"{name}.json").read_text())
            v = replay(t, transcript, Path(a.fixtures), Path(tmp) / name)
            changed += v["success"] != r["success"]
            r.update(v, valid=not r.get("error"))
            shutil.rmtree(Path(tmp) / name, ignore_errors=True)
    with open(run / "results.jsonl", "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    print(f"regraded {len(rows)} runs; success changed on {changed}")


if __name__ == "__main__":
    main()
