"""Run a natural Python repository's test suite under the layer-C tracer, within a wall-clock budget.

Usage: python -m nb.trace_repo <repo> [plain_budget_s] [traced_budget_s]
Writes $CODEXA_DATA_DIR/traces/<repo>.json and <repo>.trace-meta.json. When the budget is reached the
tracer receives SIGTERM and saves the calls observed so far; pytest progress is recorded so the share
of the suite that ran is reported. Subprocesses spawned by tests are not traced (known gap).
"""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

DATA = Path(os.environ.get("CODEXA_DATA_DIR", "/work/nb"))
NB = Path(__file__).resolve().parent.parent
PYTEST = ["-m", "pytest", "-q", "-p", "no:cacheprovider", "-o", "addopts=", "--timeout=120"]


def run_budget(cmd, cwd, env, budget):
    t = time.time()
    p = subprocess.Popen(cmd, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True, errors="replace")
    try:
        out, _ = p.communicate(timeout=budget)
        finished = True
    except subprocess.TimeoutExpired:
        p.send_signal(signal.SIGTERM)
        try:
            out, _ = p.communicate(timeout=120)
        except subprocess.TimeoutExpired:
            p.kill()
            out, _ = p.communicate()
        finished = False
    progress = sum(len(re.findall(r"[.FEsxX]", ln)) for ln in out.splitlines() if re.fullmatch(r"[.FEsxX]+(\s+\[\s*\d+%\])?", ln.strip()))
    pct = re.findall(r"\[\s*(\d+)%\]", out)
    return {"seconds": time.time() - t, "finished": finished, "tests_progressed": progress,
            "last_pct": int(pct[-1]) if pct else (100 if finished else None), "tail": out.strip().splitlines()[-2:]}


def main() -> None:
    repo = sys.argv[1]
    plain_b = int(sys.argv[2]) if len(sys.argv) > 2 else 600
    traced_b = int(sys.argv[3]) if len(sys.argv) > 3 else 1200
    root = DATA / "repos" / repo
    py = str(DATA / "venvs" / repo / "bin" / "python")
    out = DATA / "traces" / f"{repo}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PYTHONPATH=str(NB), PYTHONDONTWRITEBYTECODE="1", TERM="dumb", PAGER="cat", CI="1")
    meta = {"repo": repo, "plain": run_budget([py] + PYTEST, root, env, plain_b)}
    meta["traced"] = run_budget([py, "-m", "nb.trace_run", str(root), str(out), "--"] + PYTEST, root, env, traced_b)
    meta["trace_written"] = out.exists()
    (DATA / "traces" / f"{repo}.trace-meta.json").write_text(json.dumps(meta, indent=1))
    print(json.dumps({k: (v if k == "repo" else {kk: vv for kk, vv in v.items() if kk != "tail"} if isinstance(v, dict) else v) for k, v in meta.items()}))


if __name__ == "__main__":
    main()
