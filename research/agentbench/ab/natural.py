"""Harder RQ4 tasks: change-signature tasks on the natural NavBench Python repositories, graded by their
own (hidden) test suites.

Task:   add a required trailing parameter `tag: str` to a function or method and update every call site.
Oracle: the repository's test suite at the pinned commit. Success = the signature changed AND no test fails
        that passed on the untouched repository. The agent's own `run_program` is only a syntax check,
        so it cannot iterate against the oracle.

Every task is validated automatically before use:
  1. reference solution (def edit + `tag='v2'` at every gold site) -> no new test failures;
  2. def-only mutant (no call site updated)                        -> new failures (the change is exercised
                                                                       and the working copy is what is imported);
  3. for EACH gold site, the reference minus that one site        -> new failures (every site is checked);
  4. up to 3 look-alike calls (same name, not gold) given the extra argument -> detection recorded (precision).
Gold sites = language-server call sites (NavBench out-v2 `lsp` row) U runtime-observed call sites (layer C).

Usage: python -m ab.natural build <navbench_run_dir> <out_dir> [--repos a,b] [--max-candidates 30] [--workers 3]
       python -m ab.natural select <out_dir>/validated.jsonl <tasks.json> [--n 40] [--seed 20261008]
       python -m ab.natural rebaseline <tasks.json> [--runs 5]     (flaky tests -> baseline_failed)
       python -m ab.natural selftest <tasks.json> <out_dir>/validated.jsonl [--n 40] [--conditions ...]
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
NAVBENCH = HERE.parents[0] / "navbench"
sys.path.insert(0, str(NAVBENCH))

# NavBench data (pinned repositories, venvs, traces); separate from CODEXA_DATA_DIR, which agent runs point at a sandbox
DATA = Path(os.environ.get("NB_DATA_DIR", "/work/nb"))
PY_REPOS = ["more-itertools", "toolz", "marshmallow", "itsdangerous", "jinja", "attrs", "rich", "httpx", "boltons"]
PARAM, VALUE = "tag", "v2"
SKIP_DECORATORS = {"property", "cached_property", "overload", "setter", "getter", "deleter", "abstractmethod",
                   "classmethod_property", "contextmanager", "asynccontextmanager", "fixture"}
PYTEST = ["-m", "pytest", "-q", "-p", "no:cacheprovider", "-o", "addopts=", "--timeout=120"]


# ----------------------------------------------------------------------------------------------- tests
def venv_python(repo: str) -> str:
    return str(DATA / "venvs" / repo / "bin" / "python")


def pkg_path(root: Path) -> Path:
    return root / "src" if (root / "src").is_dir() else root


def run_tests(root: Path, repo: str, stop_first: bool = False, timeout: int = 600) -> dict:
    """Run the suite in `root` (imports resolve to `root` first); returns failing test ids from JUnit XML."""
    with tempfile.TemporaryDirectory() as td:
        xml = Path(td) / "junit.xml"
        env = dict(os.environ, PYTHONPATH=f"{pkg_path(root)}{os.pathsep}{root}", PYTHONDONTWRITEBYTECODE="1",
                   TERM="dumb", PAGER="cat", CI="1")
        env.pop("CODEXA_DATA_DIR", None)
        cmd = [venv_python(repo)] + PYTEST + (["-x"] if stop_first else []) + [f"--junitxml={xml}"]
        try:
            p = subprocess.run(cmd, cwd=root, env=env, capture_output=True, text=True, errors="replace",
                               timeout=timeout, stdin=subprocess.DEVNULL)
            rc, tail = p.returncode, (p.stdout + p.stderr)[-1500:]
        except subprocess.TimeoutExpired:
            return {"rc": "timeout", "failed": None, "n": 0, "tail": "timeout"}
        failed, n = set(), 0
        if xml.exists():
            try:
                for tc in ET.parse(xml).getroot().iter("testcase"):
                    n += 1
                    if tc.find("failure") is not None or tc.find("error") is not None:
                        failed.add(f"{tc.get('classname')}::{tc.get('name')}")
            except ET.ParseError:
                failed = None
        return {"rc": rc, "failed": failed, "n": n, "tail": tail}


def check_natural(task, workdir: Path, timeout: int = 900) -> dict:
    """Hidden-test oracle for a natural task (see module docstring)."""
    from ab.tasks import signature_changed
    res = run_tests(workdir, task.repo, timeout=timeout)
    base_failed = set(task.baseline_failed or [])
    nf = None if res["failed"] is None else sorted(res["failed"] - base_failed)
    ok = nf is not None and not nf
    hit = 0
    for f, ln in task.gold_sites:
        try:
            hit += int(VALUE in (workdir / f).read_text(encoding="utf-8").splitlines()[ln - 1])
        except (OSError, IndexError):
            pass
    sig = signature_changed(task, workdir)
    extra = over_edits(task, workdir)
    return {"success": ok and sig, "strict_success": ok and sig and not extra, "over_edits": extra[:20],
            "n_over_edits": len(extra), "oracle_ok": ok, "signature_changed": sig, "new_failures": (nf or [])[:20],
            "n_new_failures": len(nf) if nf is not None else None, "oracle_output": res["tail"][-800:],
            "sites_updated": hit, "sites_total": len(task.gold_sites)}


def _value_calls(src: str) -> set:
    """(callee name, callee-token line) of every call that passes VALUE (positionally or as `tag=`)."""
    out = set()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return out
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        vals = list(n.args) + [k.value for k in n.keywords]
        if any(isinstance(v, ast.Constant) and v.value == VALUE for v in vals):
            f = n.func
            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "?")
            out.add((name, f.end_lineno if isinstance(f, ast.Attribute) else f.lineno))
    return out


def over_edits(task, workdir: Path) -> list:
    """Calls given the new argument that are not gold sites (static precision check; tests cannot see edits in
    unexercised code such as examples/)."""
    gold = {(f, ln) for f, ln in task.gold_sites}
    pristine = DATA / "repos" / task.repo
    extra = []
    for p in workdir.rglob("*.py"):
        rel = p.relative_to(workdir).as_posix()
        try:
            new = p.read_text(encoding="utf-8")
            old = (pristine / rel).read_text(encoding="utf-8") if (pristine / rel).exists() else ""
        except (OSError, UnicodeDecodeError):
            continue
        if new == old:
            continue
        for name, ln in _value_calls(new) - _value_calls(old):
            if (rel, ln) not in gold:
                extra.append([rel, ln, name])
    return extra


def materialize_natural(task, dest: Path) -> Path:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(DATA / "repos" / task.repo, dest,
                    ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc", ".codexa-repo.json"))
    return dest


def syntax_check_cmd(task) -> list[str]:
    """The agent's `run_program` for natural tasks: byte-compile only (the tests stay hidden)."""
    return [venv_python(task.repo), "-m", "compileall", "-q", "-x", r"(\.git|node_modules)", "."]


def new_failures(res: dict, base: dict) -> set | None:
    if res["failed"] is None or res["rc"] == "timeout":
        return None
    return res["failed"] - base["failed"]


# ----------------------------------------------------------------------------------------------- edits
def _find_def(tree: ast.AST, name: str, line: int):
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name and n.lineno == line:
            return n
    return None


def _dec_name(d: ast.expr) -> str:
    d = d.func if isinstance(d, ast.Call) else d
    return d.attr if isinstance(d, ast.Attribute) else getattr(d, "id", "")


def def_eligible(fn) -> str:
    a = fn.args
    if a.vararg or a.kwarg or a.kwonlyargs or a.defaults or a.kw_defaults or a.posonlyargs:
        return "varargs/defaults/kw-only/pos-only parameters"
    if any(_dec_name(d) in SKIP_DECORATORS for d in fn.decorator_list):
        return "decorator changes call protocol"
    if fn.name.startswith("__") and fn.name.endswith("__"):
        return "dunder"
    return ""


def _insert(lines: list[bytes], line: int, col: int, text: bytes) -> None:
    b = lines[line - 1]
    lines[line - 1] = b[:col] + text + b[col:]


def edit_def(src: str, name: str, line: int) -> str | None:
    tree = ast.parse(src)
    fn = _find_def(tree, name, line)
    if fn is None:
        return None
    lines = src.encode("utf-8").split(b"\n")
    if fn.args.args:
        last = fn.args.args[-1]
        _insert(lines, last.end_lineno, last.end_col_offset, f", {PARAM}: str".encode())
    else:
        hdr = lines[fn.lineno - 1]
        m = re.search(rb"def\s+" + re.escape(name.encode()) + rb"\s*(\[[^\]]*\])?\s*\(", hdr)
        if not m:
            return None
        _insert(lines, fn.lineno, m.end(), f"{PARAM}: str".encode())
    return b"\n".join(lines).decode("utf-8")


def _find_call(tree: ast.AST, name: str, line: int, col_chars: int, line_text: str):
    col = len(line_text[:col_chars].encode("utf-8"))  # index columns are characters; ast uses UTF-8 bytes
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        if isinstance(f, ast.Name) and f.id == name and f.lineno == line and f.col_offset == col:
            return n
        if isinstance(f, ast.Attribute) and f.attr == name and f.end_lineno == line and \
                f.end_col_offset - len(name.encode()) == col:
            return n
    return None


def edit_calls(src: str, name: str, sites: list[tuple[int, int]]) -> str | None:
    """Add `tag='v2'` to the calls whose callee name token is at each (line, char col). None if any is not a call."""
    tree = ast.parse(src)
    text_lines = src.split("\n")
    calls = []
    for ln, col in sites:
        c = _find_call(tree, name, ln, col, text_lines[ln - 1])
        if c is None:
            return None
        calls.append(c)
    lines = src.encode("utf-8").split(b"\n")
    for c in sorted(calls, key=lambda c: (c.end_lineno, c.end_col_offset), reverse=True):
        el, ec = c.end_lineno, c.end_col_offset - 1           # position of the closing ')'
        before = b"\n".join(lines[: el - 1] + [lines[el - 1][:ec]]).rstrip()
        sep = b"" if before.endswith(b"(") else (b" " if before.endswith(b",") else b", ")
        _insert(lines, el, ec, sep + f"{PARAM}='{VALUE}'".encode())
    return b"\n".join(lines).decode("utf-8")


def apply(root: Path, decl: dict, sites: list[tuple[str, int, int]], with_def: bool = True) -> dict | None:
    """Returns {file: new_text} for the reference-style edit, or None if any edit is impossible."""
    by_file: dict[str, list] = {}
    for f, ln, col in sites:
        by_file.setdefault(f, []).append((ln, col))
    files = set(by_file) | ({decl["file"]} if with_def else set())
    out = {}
    for f in files:
        src = (root / f).read_text(encoding="utf-8")
        if f in by_file:
            src = edit_calls(src, decl["name"], by_file[f])
            if src is None:
                return None
        if with_def and f == decl["file"]:
            src = edit_def(src, decl["name"], decl["line"])
            if src is None:
                return None
        out[f] = src
    return out


class Patch:
    """Temporarily overwrite files in a working copy."""

    def __init__(self, root: Path, files: dict):
        self.root, self.files, self.orig = root, files, {}

    def __enter__(self):
        for f, t in self.files.items():
            self.orig[f] = (self.root / f).read_text(encoding="utf-8")
            (self.root / f).write_text(t, encoding="utf-8")
        return self

    def __exit__(self, *exc):
        for f, t in self.orig.items():
            (self.root / f).write_text(t, encoding="utf-8")


# ----------------------------------------------------------------------------------------------- build
def gold_sites(repo: str, run_dir: Path, ix, traced: dict) -> dict:
    """target decl id -> sorted [(file, line, col)] gold call sites (LSP call tokens U runtime-observed)."""
    out: dict = {}
    for line in open(run_dir / f"{repo}.results.jsonl"):
        r = json.loads(line)
        if r["arm"] != "lsp" or r["task"] != "T1":
            continue
        s = {tuple(f) for f in r["facts"] if tuple(f) in ix.name_tok}
        out.setdefault(r["target"], set()).update(s)
    for did, cids in traced.items():
        if did in out:
            out[did].update((ix.calls[c]["file"], ix.calls[c]["line"], ix.calls[c]["col"]) for c in cids)
    return {k: sorted(v) for k, v in out.items()}


def build_repo(args) -> list[dict]:
    repo, run_dir, out_dir, max_cand = args
    from nb import index as I
    from nb import trace_map
    src_root = DATA / "repos" / repo
    work = Path(out_dir) / "work" / repo
    if work.exists():
        shutil.rmtree(work)
    shutil.copytree(src_root, work, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc", ".codexa-repo.json"))
    ix = I.load(work, "py", None)
    traced: dict = {}
    tm = trace_map.load(ix.py, DATA / "traces" / f"{repo}.json")
    for (cid, did), v in tm["pairs"].items():
        if v["confirmed"]:
            traced.setdefault(did, set()).add(cid)
    gold = gold_sites(repo, Path(run_dir), ix, traced)
    targets = json.loads((Path(run_dir) / f"{repo}.targets.json").read_text())
    base = run_tests(work, repo)
    log = Path(out_dir) / f"{repo}.log"
    seen = set()
    cands = []
    for t in targets:
        did = t["decl"]
        if did in seen:
            continue
        seen.add(did)
        d = ix.decls[did]
        if d["kind"] not in ("function", "method") or d.get("is_test") or d["name"].startswith("test"):
            continue
        sites = [s for s in gold.get(did, []) if not (s[0] == d["file"] and s[1] == d["line"])]
        if not 1 <= len(sites) <= 15:
            continue
        cands.append((d, sites, t))
    rng = random.Random(f"20261008:{repo}")
    rng.shuffle(cands)

    def validate(d, sites, t):
        rec = {"repo": repo, "target": d["id"], "name": d["name"], "qualname": d["qualname"], "file": d["file"],
               "line": d["line"], "kind": d["kind"], "sample": t["sample"], "gold_sites": [list(s) for s in sites],
               "name_occurrences": t.get("name_occurrences"), "valid": False, "reason": ""}
        try:
            fn = _find_def(ast.parse((work / d["file"]).read_text(encoding="utf-8")), d["name"], d["line"])
            why = "def not found" if fn is None else def_eligible(fn)
            if why:
                rec["reason"] = why
                return rec
            ref = apply(work, d, sites)
            if ref is None:
                rec["reason"] = "a gold site is not an editable call expression"
                return rec
            with Patch(work, ref):
                r = run_tests(work, repo)
            nf = new_failures(r, base)
            if nf is None or nf:
                rec["reason"] = f"reference solution fails {sorted(nf)[:3] if nf else r['rc']}"
                return rec
            defonly = apply(work, d, [])
            with Patch(work, defonly):
                nf = new_failures(run_tests(work, repo, stop_first=True), base)
            if not nf:
                rec["reason"] = "def-only change is not detected by the tests"
                return rec
            undetected = []
            for i, s in enumerate(sites):
                mut = apply(work, d, sites[:i] + sites[i + 1:])
                with Patch(work, mut):
                    nf = new_failures(run_tests(work, repo, stop_first=True), base)
                if not nf:
                    undetected.append(s)
            if undetected:
                rec["reason"] = f"{len(undetected)} gold site(s) not detected when omitted"
                rec["undetected_sites"] = [list(s) for s in undetected]
                return rec
            # look-alikes: same-named call expressions that are not gold sites
            gold_set = {tuple(s) for s in sites}
            look = [(c["file"], c["line"], c["col"]) for c in ix.calls.values()
                    if c["name"] == d["name"] and (c["file"], c["line"], c["col"]) not in gold_set
                    and not (c["file"] == d["file"] and c["line"] == d["line"])]
            rng.shuffle(look)
            det = []
            for s in look[:3]:
                over = apply(work, d, sites + [s])
                if over is None:
                    continue
                with Patch(work, over):
                    nf = new_failures(run_tests(work, repo, stop_first=True), base)
                det.append({"site": list(s), "detected": bool(nf)})
            rec.update({"valid": True, "lookalike_calls": len(look), "lookalike_checks": det,
                        "baseline_failed": sorted(base["failed"] or []), "baseline_n": base["n"]})
        except Exception as e:  # noqa: BLE001 - a candidate that cannot be processed is recorded, not fatal
            rec["reason"] = f"error: {type(e).__name__}: {e}"[:300]
        return rec

    # one JSON line per processed candidate, written immediately: a rerun skips them (resumable)
    done_path = Path(out_dir) / f"{repo}.cands.jsonl"
    done = {}
    if done_path.exists():
        for line in open(done_path):
            r = json.loads(line)
            done[r["target"]] = r
    results = []
    for d, sites, t in cands[:max_cand]:
        if d["id"] in done:
            results.append(done[d["id"]])
            continue
        rec = validate(d, sites, t)
        results.append(rec)
        with open(done_path, "a") as fh:
            fh.write(json.dumps(rec) + "\n")
        with open(log, "a") as fh:
            fh.write(json.dumps({k: rec[k] for k in ("target", "valid", "reason")}) + "\n")
    return results


def build(run_dir: str, out_dir: str, repos: list[str], max_cand: int, workers: int) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "validated.jsonl").unlink(missing_ok=True)
    with ProcessPoolExecutor(workers) as ex:
        allres = []
        for res in ex.map(build_repo, [(r, run_dir, out_dir, max_cand) for r in repos]):
            allres += res
            with open(out / "validated.jsonl", "a") as fh:  # cleared at the start of build()
                for r in res:
                    fh.write(json.dumps(r) + "\n")
    v = [r for r in allres if r["valid"]]
    print(f"{len(allres)} candidates, {len(v)} valid")


def select(validated: str, out: str, n: int, seed: int) -> None:
    """Stratify valid tasks by repository and by rg-hostility (name occurrences per gold site)."""
    rows = [json.loads(l) for l in open(validated)]
    v = [r for r in rows if r["valid"]]
    for r in v:
        r["rg_ratio"] = (r["name_occurrences"] or 0) / max(1, len(r["gold_sites"]))
        r["rg_hostile"] = r["rg_ratio"] >= 3
    rng = random.Random(seed)
    by_repo: dict = {}
    for r in v:
        by_repo.setdefault(r["repo"], []).append(r)
    for rs in by_repo.values():
        rs.sort(key=lambda r: (not r["rg_hostile"], rng.random()))  # rg-hostile first within each repo
    pick = []
    while len(pick) < n and any(by_repo.values()):
        for repo in sorted(by_repo):
            if by_repo[repo] and len(pick) < n:
                pick.append(by_repo[repo].pop(0))
    tasks = []
    for r in pick:
        tasks.append({"id": f"{r['repo']}:{r['qualname']}", "repo": r["repo"], "lang": "py", "target_key": r["target"],
                      "name": r["name"], "qualname": r["qualname"], "file": r["file"], "line": r["line"],
                      "param": PARAM, "value": VALUE, "gold_sites": [s[:2] for s in r["gold_sites"]],
                      "natural": True, "rg_ratio": round(r["rg_ratio"], 2), "rg_hostile": r["rg_hostile"],
                      "baseline_failed": r["baseline_failed"], "lookalike_checks": r["lookalike_checks"]})
    Path(out).write_text(json.dumps(tasks, indent=1))
    print(f"{len(tasks)} tasks ({sum(t['rg_hostile'] for t in tasks)} rg-hostile) from {len(v)} valid -> {out}")


def selftest(tasks_file: str, conditions: list[str], limit: int) -> None:
    """End-to-end check with no model calls: the grader accepts the reference solution and rejects an untouched
    copy, and every navigation condition builds and answers `find_callers` on the task's workspace."""
    from ab.run import Navigator
    from ab.tasks import from_file
    work = Path(os.environ["CODEXA_DATA_DIR"]) / "repos"
    rows = []
    for t in from_file(Path(tasks_file))[:limit]:
        root = materialize_natural(t, work / "ab-selftest")
        (root / ".codexa-repo.json").write_text(json.dumps({"url": "agentbench://ab-selftest"}))
        untouched = check_natural(t, root)
        decl = {"file": t.file, "name": t.name, "line": t.line}
        rec = {"task": t.id, "untouched_success": untouched["success"], "untouched_oracle_ok": untouched["oracle_ok"]}
        # reference solution: re-derive the gold sites with columns from the validation record
        full = _gold_with_cols.get(t.id)
        if full is not None:
            ref = apply(root, decl, [tuple(x) for x in full])
            for f, text in ref.items():
                (root / f).write_text(text, encoding="utf-8")
            v = check_natural(t, root)
            rec.update({"reference_success": v["success"], "reference_strict": v["strict_success"],
                        "reference_sites": f"{v['sites_updated']}/{v['sites_total']}"})
            shutil.rmtree(root)
            root = materialize_natural(t, work / "ab-selftest")
            (root / ".codexa-repo.json").write_text(json.dumps({"url": "agentbench://ab-selftest"}))
        for cond in conditions:
            nav = Navigator(cond, t, root, "ab-selftest")
            try:
                f = nav.build()
                out = f(t.name) if f else ""
                rec[f"nav_{cond}"] = f"ok {len(out)} chars"
            except Exception as e:  # noqa: BLE001
                rec[f"nav_{cond}"] = f"ERROR {type(e).__name__}: {e}"[:160]
            finally:
                nav.close()
        shutil.rmtree(root, ignore_errors=True)
        rows.append(rec)
        print(json.dumps(rec), flush=True)
    bad = [r for r in rows if r.get("reference_strict") is not True or r["untouched_success"]
           or any(str(v).startswith("ERROR") for k, v in r.items() if k.startswith("nav_"))]
    print(f"selftest: {len(rows)} tasks, {len(bad)} with problems")


_gold_with_cols: dict = {}


def rebaseline(tasks_file: str, runs: int) -> None:
    """Make the hidden-test oracle robust to flaky tests: run each repository's untouched suite `runs` times in a
    materialized copy (as agent runs use) and store the union of failing tests as `baseline_failed`."""
    tasks = json.loads(Path(tasks_file).read_text())
    work = Path(os.environ["CODEXA_DATA_DIR"]) / "repos"
    union: dict = {}
    for repo in sorted({t["repo"] for t in tasks}):
        root = work / f"ab-baseline-{repo}"
        if root.exists():
            shutil.rmtree(root)
        shutil.copytree(DATA / "repos" / repo, root, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))
        fails = set()
        for _ in range(runs):
            fails |= run_tests(root, repo)["failed"] or set()
        shutil.rmtree(root, ignore_errors=True)
        union[repo] = fails
        print(f"{repo}: {len(fails)} tests fail in at least one of {runs} untouched runs")
    for t in tasks:
        extra = union[t["repo"]] - set(t["baseline_failed"])
        t["baseline_failed"] = sorted(set(t["baseline_failed"]) | union[t["repo"]])
        if extra:
            t["baseline_flaky_added"] = sorted(extra)
    Path(tasks_file).write_text(json.dumps(tasks, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("build", "select", "selftest", "rebaseline"))
    ap.add_argument("a")
    ap.add_argument("rest", nargs="*")
    ap.add_argument("--repos", default=",".join(PY_REPOS))
    ap.add_argument("--max-candidates", type=int, default=30)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--seed", type=int, default=20261008)
    ap.add_argument("--conditions", default="rg,lsp,codexa,codexa2,routed,cbm_cur")
    ap.add_argument("--runs", type=int, default=5)
    a = ap.parse_args()
    a.b = a.rest[0] if a.rest else None
    if a.cmd == "rebaseline":  # a = tasks file (updated in place)
        rebaseline(a.a, a.runs)
        return
    if a.cmd == "selftest":  # a = tasks file, b = validated.jsonl (for gold-site columns)
        for line in open(a.b):
            r = json.loads(line)
            if r["valid"]:
                _gold_with_cols[f"{r['repo']}:{r['qualname']}"] = r["gold_sites"]
        selftest(a.a, a.conditions.split(","), a.n)
        return
    if a.cmd == "build":
        build(a.a, a.b, a.repos.split(","), a.max_candidates, a.workers)
    else:
        select(a.a, a.b, a.n, a.seed)


if __name__ == "__main__":
    main()
