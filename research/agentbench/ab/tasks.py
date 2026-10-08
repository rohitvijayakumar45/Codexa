"""Test-scored agent tasks that need complete call-site knowledge (RQ4).

T-callers ("change signature"): add a required trailing parameter to a target function or method,
and update **every** call site to pass it. The repository's own execution is the oracle:

    Python      `python main.py` runs every fixture call path; a missed call site raises TypeError
                (missing argument), and so does a wrongly edited look-alike (an extra argument)
    TypeScript  `tsc --noEmit --strict` rejects both missing and extra arguments

So success measures completeness *and* precision of the agent's call-site knowledge, without an LLM
judge. Tasks are generated from NavBench fixtures. Their gold call sites are known from the manifest,
which also gives a per-site diagnosis of failures.
"""
from __future__ import annotations

import ast
import json
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

NAVBENCH = Path(__file__).resolve().parents[2] / "navbench"
TSC = NAVBENCH / "node_modules" / "typescript" / "bin" / "tsc"


@dataclass
class Task:
    id: str
    repo: str
    lang: str
    target_key: str
    name: str
    qualname: str
    file: str
    line: int
    param: str
    value: str
    gold_sites: list = field(default_factory=list)   # [(file, line)] explicit call sites
    prompt: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def _prompt(t: "Task") -> str:
    typ = "str" if t.lang == "py" else "string"
    kind = "method" if "." in t.qualname else "function"
    return (f"In this repository, add a new required parameter `{t.param}: {typ}` as the LAST parameter of the "
            f"{kind} `{t.qualname}` defined in `{t.file}` (line {t.line}). The parameter is not used in the body. "
            f"Then update EVERY call site of this {kind} in the repository so that it passes the string "
            f"{t.value!r} as the new last argument. Do not change any other function, and do not add a default value. "
            f"When you are done, call `finish`.")


def from_fixture(root: Path, keys: tuple[str, ...] = ("direct", "M", "reexp", "decorated")) -> list[Task]:
    man = json.loads((root / ".navbench-manifest.json").read_text())
    lang = "py" if man["language"] == "python" else "ts"
    out = []
    for t in man["targets"]:
        if t["key"] not in keys or t["kind"] == "class":
            continue
        sites = [(s["file"], s["line"]) for s in t["sites"] if s["category"] == "explicit"]
        if not sites:
            continue
        task = Task(id=f"{root.name}:{t['key']}", repo=root.name, lang=lang, target_key=t["key"], name=t["name"],
                    qualname=t["qualname"], file=t["file"], line=t["line"], param="tag", value="v2", gold_sites=sites)
        task.prompt = _prompt(task)
        out.append(task)
    return out


def _last_param_ok(params: str, param: str) -> bool:
    """`params` is a parameter list; its last entry must be `param` without a default value."""
    parts = [p.strip() for p in params.split(",") if p.strip()]
    if not parts:
        return False
    last = parts[-1]
    return "=" not in last and re.split(r"[\s:?]", last, maxsplit=1)[0] == param


def _ts_def_params(text: str, qualname: str) -> str | None:
    cls, _, name = qualname.rpartition(".")
    n = re.escape(name)
    if cls:
        m = re.search(rf"^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+{re.escape(cls)}\b.*?^}}", text, re.M | re.S)
        if not m:
            return None
        body = m.group(0)
        mm = re.search(rf"^\s+(?:(?:public|private|protected|static|async|readonly|override)\s+)*{n}\s*(?:<[^>]*>)?\s*\(([^)]*)\)",
                       body, re.M)
        return mm.group(1) if mm else None
    mm = (re.search(rf"\bfunction\s*\*?\s*{n}\s*(?:<[^>]*>)?\s*\(([^)]*)\)", text)
          or re.search(rf"\b(?:const|let|var)\s+{n}\s*(?::[^=]+)?=\s*(?:async\s*)?(?:<[^>]*>)?\s*\(([^)]*)\)", text))
    return mm.group(1) if mm else None


def signature_changed(task: Task, workdir: Path) -> bool:
    """Did the agent actually give the target the new required last parameter?

    The execution oracle alone also passes on untouched code (nothing calls the function wrongly),
    so success requires this as well."""
    try:
        text = (workdir / task.file).read_text(encoding="utf-8")
    except OSError:
        return False
    if task.lang == "ts":
        params = _ts_def_params(text, task.qualname)
        return params is not None and _last_param_ok(params, task.param)
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return False
    *owners, name = task.qualname.split(".")
    scope = tree.body
    for o in owners:
        cls = next((n for n in scope if isinstance(n, ast.ClassDef) and n.name == o), None)
        if cls is None:
            return False
        scope = cls.body
    fn = next((n for n in scope if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name), None)
    if fn is None or not fn.args.args:
        return False
    return fn.args.args[-1].arg == task.param and not fn.args.defaults


def check(task: Task, workdir: Path, timeout: int = 120) -> dict:
    """Run the repository's own oracle on the agent's result.

    success = the target has the new parameter (`signature_changed`) AND the program still runs /
    type-checks (`oracle_ok`), i.e. every call site was updated and no look-alike was touched."""
    if task.lang == "py":
        p = subprocess.run([sys.executable, "main.py"], cwd=workdir, capture_output=True, text=True, timeout=timeout)
        ok = p.returncode == 0
        out = (p.stdout + p.stderr)[-1500:]
    else:
        p = subprocess.run(["node", str(TSC), "--noEmit", "-p", "."], cwd=workdir, capture_output=True, text=True,
                           timeout=timeout)
        ok = p.returncode == 0
        out = (p.stdout + p.stderr)[-1500:]
    # per-site diagnosis: does each gold call line now mention the value?
    hit = 0
    for f, ln in task.gold_sites:
        try:
            line = (workdir / f).read_text(encoding="utf-8").splitlines()[ln - 1]
        except (OSError, IndexError):
            continue
        hit += int(task.value in line)
    sig = signature_changed(task, workdir)
    return {"success": ok and sig, "oracle_ok": ok, "signature_changed": sig, "oracle_output": out,
            "sites_updated": hit, "sites_total": len(task.gold_sites)}


def materialize(task: Task, fixtures_dir: Path, dest: Path) -> Path:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(fixtures_dir / task.repo, dest, ignore=shutil.ignore_patterns(".navbench-manifest.json", "__pycache__"))
    return dest
