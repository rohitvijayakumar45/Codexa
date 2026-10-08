"""RQ4 agent experiment runner (pilot and full).

Conditions = which `find_callers` backend the agent has, on top of the lexical baseline that every
condition gets (`search` = ripgrep -w):

    rg        no find_callers
    lsp       language server references (pyright / TS service), per matching declaration
    codexa    Codexa find_references, frozen G1 (resolution v1)
    codexa2   Codexa find_references v2 (ambiguity listing, qualified ids)
    routed    codexa2, plus a ripgrep fallback appended when the graph answer is empty, ambiguous
              or unresolved (feature A's "weak" trigger)

Usage:
  python -m ab.run --fixtures <dir> --split fresh --n-tasks 20 --conditions rg,lsp,codexa2 \
      --model nvidia_nim/qwen/qwen3-coder-480b-a35b-instruct --reps 2 --out <dir>
"""
from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
CODEXA = HERE.parents[1]
NAVBENCH = CODEXA / "research" / "navbench"
for p in (HERE, CODEXA, NAVBENCH):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from ab.agent import Workspace, litellm_llm, run_agent  # noqa: E402
from ab.tasks import TSC, Task, check, from_fixture, materialize  # noqa: E402

CONDITIONS = ("rg", "lsp", "codexa", "codexa2", "routed")


def run_cmd(task: Task) -> list[str]:
    return [sys.executable, "main.py"] if task.lang == "py" else ["node", str(TSC), "--noEmit", "-p", "."]


class Navigator:
    """Builds the find_callers backend for one condition over one (pre-edit) workspace."""

    def __init__(self, condition: str, task: Task, root: Path, repo_name: str):
        self.condition, self.task, self.root, self.repo = condition, task, root, repo_name
        self._closers = []

    def build(self):
        c = self.condition
        if c == "rg":
            return None
        if c == "lsp":
            return self._lsp()
        if c in ("codexa", "codexa2", "routed"):
            return self._codexa("v1" if c == "codexa" else "v2", routed=(c == "routed"))
        raise ValueError(c)

    def _lsp(self):
        from nb import arms as A
        from nb import index as I
        from nb.lsp import PyrightClient
        from nb.tsclient import TsClient

        tsc = TsClient(self.root) if self.task.lang == "ts" else None
        ix = I.load(self.root, self.task.lang, tsc)
        if self.task.lang == "py":
            prov = PyrightClient(self.root)
            prov.warm(ix.files, [])
        else:
            prov = tsc
        self._closers.append(prov.close)

        def find(symbol: str) -> str:
            matches = [d for d in ix.decls.values() if symbol in (d["name"], d["qualname"])][:5]
            if not matches:
                return f"No declaration named '{symbol}'."
            parts = []
            for d in matches:
                r = A.lsp_refs(ix, prov, d)
                parts.append(f"# references of {d['qualname']} ({d['file']}:{d['line']})\n{r.native or '[]'}")
            return "\n".join(parts)
        return find

    def _codexa(self, mode: str, routed: bool):
        from nb.adapters import resolution
        from nb.arms import CodexaGraph

        with resolution(mode):
            cx = CodexaGraph(self.repo)
        ws = Workspace(self.root, self.task.lang, run_cmd(self.task))

        def find(symbol: str) -> str:
            with resolution(mode):
                out = cx.T._find_references(symbol, cx.repo, graph=cx.graph)
            if routed and (out.startswith("Ambiguous") or "References: (none" in out or out.startswith("No symbol")):
                out += "\n# fallback: lexical search\n" + ws.search(symbol.split("#")[-1].split(".")[-1])
            return out
        return find

    def close(self):
        for c in self._closers:
            try:
                c()
            except Exception:  # noqa: BLE001
                pass


def _load_keys() -> None:
    """Provider keys from Codexa's .env (never printed). litellm expects NVIDIA_NIM_API_KEY."""
    try:
        from dotenv import load_dotenv
        load_dotenv(CODEXA / ".env")
    except ImportError:
        pass
    if os.environ.get("NVIDIA_API_KEY") and not os.environ.get("NVIDIA_NIM_API_KEY"):
        os.environ["NVIDIA_NIM_API_KEY"] = os.environ["NVIDIA_API_KEY"]


def main() -> None:
    _load_keys()
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixtures", required=True)
    ap.add_argument("--split", default="fresh")
    ap.add_argument("--n-tasks", type=int, default=20)
    ap.add_argument("--conditions", default="rg,lsp,codexa2")
    ap.add_argument("--model", required=True)
    ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--max-steps", type=int, default=30)
    ap.add_argument("--seed", type=int, default=20261008)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    fixtures = Path(a.fixtures)
    tasks = []
    for fx in sorted(fixtures.glob(f"fx-*-{a.split}-*")):
        tasks += from_fixture(fx)
    rng = random.Random(a.seed)
    py = [t for t in tasks if t.lang == "py"]
    ts = [t for t in tasks if t.lang == "ts"]
    tasks = rng.sample(py, min(len(py), a.n_tasks // 2)) + rng.sample(ts, min(len(ts), a.n_tasks - a.n_tasks // 2))
    out = Path(a.out)
    (out / "transcripts").mkdir(parents=True, exist_ok=True)
    (out / "tasks.json").write_text(json.dumps([t.as_dict() for t in tasks], indent=1))
    work = Path(os.environ["CODEXA_DATA_DIR"]) / "repos"
    llm = litellm_llm(a.model)
    done = set()
    res_path = out / "results.jsonl"
    if res_path.exists():
        for line in open(res_path, encoding="utf-8"):
            r = json.loads(line)
            done.add((r["task"], r["condition"], r["rep"]))
    for rep in range(a.reps):
        for t in tasks:
            for cond in a.conditions.split(","):
                if (t.id, cond, rep) in done:
                    continue
                name = f"ab-{t.repo}-{t.target_key}-{cond}-r{rep}"
                root = materialize(t, fixtures, work / name)
                (root / ".codexa-repo.json").write_text(json.dumps({"url": f"agentbench://{name}"}))
                nav = Navigator(cond, t, root, name)
                t0 = time.perf_counter()
                try:
                    finder = nav.build()
                    setup_s = time.perf_counter() - t0
                    log = run_agent(t.prompt, Workspace(root, t.lang, run_cmd(t)), llm, find_callers=finder,
                                    max_steps=a.max_steps)
                finally:
                    nav.close()
                verdict = check(t, root)
                row = {"task": t.id, "lang": t.lang, "target": t.target_key, "condition": cond, "rep": rep, "model": a.model,
                       **verdict, "steps": log.steps, "finished": log.finished, "error": log.error,
                       "prompt_tokens": log.prompt_tokens, "completion_tokens": log.completion_tokens,
                       "total_tokens": log.prompt_tokens + log.completion_tokens, "tool_calls": log.tool_calls,
                       "tool_output_chars": log.tool_output_chars, "wall_s": round(log.wall_s, 1), "setup_s": round(setup_s, 1)}
                with open(res_path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(row) + "\n")
                (out / "transcripts" / f"{name}.json").write_text(json.dumps(log.transcript)[:2_000_000])
                shutil.rmtree(root, ignore_errors=True)
                print(f"{t.id:28} {cond:8} r{rep} success={verdict['success']} sites={verdict['sites_updated']}/"
                      f"{verdict['sites_total']} steps={log.steps} tok={row['total_tokens']} {log.error[:60]}", flush=True)


if __name__ == "__main__":
    main()
