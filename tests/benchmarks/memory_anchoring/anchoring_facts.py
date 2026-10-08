"""Ground-truth fact extraction for the anchored-memory replay benchmark.

A "fact" is a claim a memory record could make about a repository at one commit — "the callers of
`Client.send` are {...}", "the build scripts are {...}". Its truth value at a later commit is
recomputed from that later snapshot with the same extractor, so staleness ground truth is exact and
LLM-free: a fact is stale iff its recomputed value differs (or its subject no longer exists).

Fact types (subject -> value):

    F1 signature   symbol key -> normalized declaration header (name + parameters)
    F2 callers     symbol key -> set of caller symbol keys
    F3 callees     symbol key -> set of callee symbol keys
    F4 imports     file       -> set of imported repo files
    F5 scripts     "repo"     -> set of build/run scripts (package.json scripts, pyproject scripts)
    F6 deps        "repo"     -> set of declared dependencies (package.json, pyproject, requirements)

F1 is deliberately NOT "the symbol's source hash": that would make the symbol anchor its own ground
truth. A body edit that keeps the signature is exactly the case where a symbol anchor
over-invalidates, and the benchmark has to be able to see that.
"""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.repository.analyze import Analysis, symbol_key

FACT_TYPES = ("F1_signature", "F2_callers", "F3_callees", "F4_imports", "F5_scripts", "F6_deps")
REPO_SUBJECT = "<repo>"

_SKIP = {"node_modules", ".git", ".venv", "venv", "dist", "build", ".next"}


@dataclass
class Snapshot:
    root: Path
    analysis: Analysis
    signatures: dict[str, str]
    callers: dict[str, frozenset[str]]
    callees: dict[str, frozenset[str]]
    imports: dict[str, frozenset[str]]
    scripts: frozenset[str]
    deps: frozenset[str]
    # which files each repo-level fact was read from (used by file-level anchoring)
    manifest_files: tuple[str, ...]

    def value(self, fact_type: str, subject: str) -> Any:
        """The fact's value, or None when its subject does not exist in this snapshot."""
        if fact_type == "F1_signature":
            return self.signatures.get(subject)
        if fact_type == "F2_callers":
            return self.callers.get(subject) if subject in self.signatures else None
        if fact_type == "F3_callees":
            return self.callees.get(subject) if subject in self.signatures else None
        if fact_type == "F4_imports":
            return self.imports.get(subject)
        if fact_type == "F5_scripts":
            return self.scripts
        if fact_type == "F6_deps":
            return self.deps
        raise ValueError(fact_type)


def _header(lines: list[str], line: int) -> str:
    """Declaration header starting at `line` (1-based): up to the first line that opens the body."""
    out: list[str] = []
    for raw in lines[line - 1: line + 7]:
        out.append(raw.strip())
        if raw.rstrip().endswith((":", "{")) or "=>" in raw or raw.rstrip().endswith(")"):
            break
    return re.sub(r"\s+", " ", " ".join(out)).strip()


def _manifests(root: Path) -> tuple[list[str], set[str], set[str]]:
    files: list[str] = []
    scripts: set[str] = set()
    deps: set[str] = set()
    pkgs = [root / "package.json"]
    try:
        pkgs += [p / "package.json" for p in sorted(root.iterdir())
                 if p.is_dir() and p.name not in _SKIP and not p.name.startswith(".")]
    except OSError:
        pass
    for pkg in pkgs:
        if not pkg.is_file():
            continue
        rel = pkg.relative_to(root).as_posix()
        files.append(rel)
        try:
            data = json.loads(pkg.read_text(encoding="utf-8", errors="ignore"))
        except (json.JSONDecodeError, ValueError):
            continue
        prefix = "" if rel == "package.json" else rel.rsplit("/", 1)[0] + ":"
        for name, cmd in (data.get("scripts") or {}).items():
            scripts.add(f"{prefix}{name}={cmd}")
        for section in ("dependencies", "devDependencies", "peerDependencies"):
            for name, ver in (data.get(section) or {}).items():
                deps.add(f"{name}@{ver}")
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        files.append("pyproject.toml")
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8", errors="ignore"))
        except (tomllib.TOMLDecodeError, ValueError):
            data = {}
        project = data.get("project") or {}
        for dep in project.get("dependencies") or []:
            deps.add(re.sub(r"\s+", "", str(dep)))
        for group, items in (project.get("optional-dependencies") or {}).items():
            for dep in items or []:
                deps.add(f"[{group}]" + re.sub(r"\s+", "", str(dep)))
        for name, target in (project.get("scripts") or {}).items():
            scripts.add(f"{name}={target}")
        for name, env in ((data.get("tool") or {}).get("hatch", {}).get("envs", {}) or {}).items():
            for sname, cmd in ((env or {}).get("scripts") or {}).items():
                scripts.add(f"hatch:{name}:{sname}={cmd}")
    for req in ("requirements.txt", "requirements-dev.txt"):
        rp = root / req
        if rp.is_file():
            files.append(req)
            for ln in rp.read_text(encoding="utf-8", errors="ignore").splitlines():
                ln = ln.split("#", 1)[0].strip()
                if ln:
                    deps.add(re.sub(r"\s+", "", ln))
    return files, scripts, deps


def snapshot(root: Path, analysis: Analysis) -> Snapshot:
    root = Path(root)
    file_lines: dict[str, list[str]] = {}
    signatures: dict[str, str] = {}
    for sym in analysis.symbols:
        lines = file_lines.get(sym.file)
        if lines is None:
            try:
                lines = (root / sym.file).read_text(encoding="utf-8", errors="ignore").split("\n")
            except OSError:
                lines = []
            file_lines[sym.file] = lines
        signatures[symbol_key(sym)] = _header(lines, sym.line)

    callers: dict[str, set[str]] = {k: set() for k in signatures}
    callees: dict[str, set[str]] = {k: set() for k in signatures}
    for src, dst in analysis.calls:
        callers.setdefault(dst, set()).add(src)
        callees.setdefault(src, set()).add(dst)
    imports: dict[str, set[str]] = {f: set() for f in analysis.files}
    for a, b in analysis.imports:
        imports.setdefault(a, set()).add(b)
    files, scripts, deps = _manifests(root)
    return Snapshot(
        root=root, analysis=analysis, signatures=signatures,
        callers={k: frozenset(v) for k, v in callers.items()},
        callees={k: frozenset(v) for k, v in callees.items()},
        imports={k: frozenset(v) for k, v in imports.items()},
        scripts=frozenset(scripts), deps=frozenset(deps), manifest_files=tuple(files),
    )


def subjects(snap: Snapshot, fact_type: str) -> list[str]:
    if fact_type in ("F1_signature", "F2_callers", "F3_callees"):
        return sorted(snap.signatures)
    if fact_type == "F4_imports":
        return sorted(snap.imports)
    if fact_type == "F5_scripts":
        return [REPO_SUBJECT] if snap.scripts else []
    if fact_type == "F6_deps":
        return [REPO_SUBJECT] if snap.deps else []
    raise ValueError(fact_type)
