"""Lightweight static analysis of a cloned repository.

Extracts real code structure so the knowledge graph reflects the actual codebase rather than just
metadata: source files, the functions/classes/components defined in them, file-to-file imports, and
an approximate call graph between symbols. Regex-based and language-aware (JS/TS + Python primarily)
— not a full parser, but grounded in the real source. Bounded so large repos stay fast.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".next", ".agents", "coverage"}
_SRC_EXT = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".py", ".go", ".rs", ".java"}

_MAX_FILES = 300
_MAX_SYMBOLS = 700
_MAX_EDGES = 1200
_MAX_FILE_BYTES = 200_000

# JS/TS symbol patterns (line-anchored).
_JS_FUNC = re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)")
_JS_CONST_FN = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?const\s+([A-Za-z_$][\w$]*)\s*(?::[^=]+)?=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>"
)
_JS_CLASS = re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+([A-Za-z_$][\w$]*)")
_JS_IMPORT = re.compile(r"""import\s+(?:[^'"]+\s+from\s+)?['"](\.[^'"]+)['"]""")
_JS_REQUIRE = re.compile(r"""require\(\s*['"](\.[^'"]+)['"]\s*\)""")

# Python patterns.
_PY_DEF = re.compile(r"^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)")
_PY_CLASS = re.compile(r"^\s*class\s+([A-Za-z_]\w*)")
_PY_IMPORT = re.compile(r"^\s*from\s+(\.[\w.]*)\s+import|^\s*import\s+([\w.]+)")

_CALL = re.compile(r"\b([A-Za-z_$][\w$]*)\s*\(")
_KEYWORDS = {"if", "for", "while", "switch", "catch", "return", "function", "await", "typeof", "super", "new"}


@dataclass
class Symbol:
    name: str
    kind: str  # function | class | component | hook
    file: str  # repo-relative posix path
    line: int


@dataclass
class Analysis:
    files: list[str] = field(default_factory=list)
    symbols: list[Symbol] = field(default_factory=list)
    imports: list[tuple[str, str]] = field(default_factory=list)  # (from_file, to_file)
    calls: list[tuple[str, str]] = field(default_factory=list)  # (from_symbol_key, to_symbol_key)


def _rel(path: Path, root: Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/")


def _kind(name: str, base: str) -> str:
    if name.startswith("use") and len(name) > 3 and name[3].isupper():
        return "hook"
    if base == "class":
        return "class"
    if name[:1].isupper():
        return "component"
    return "function"


def _resolve_import(spec: str, from_file: Path, root: Path, by_rel: dict[str, str]) -> str | None:
    target = (from_file.parent / spec).resolve()
    candidates = [target]
    for ext in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".py"):
        candidates.append(target.with_suffix(ext))
        candidates.append(target / f"index{ext}")
    for cand in candidates:
        try:
            rel = _rel(cand, root)
        except ValueError:
            continue
        if rel in by_rel:
            return rel
    return None


def analyze_repo(root: Path) -> Analysis:
    root = root.resolve()
    result = Analysis()

    source_files: list[Path] = []
    for p in sorted(root.rglob("*")):
        if any(part in _SKIP_DIRS for part in p.parts):
            continue
        if p.is_file() and p.suffix.lower() in _SRC_EXT and not p.name.endswith(".d.ts"):
            source_files.append(p)
        if len(source_files) >= _MAX_FILES:
            break

    by_rel = {_rel(p, root): p for p in source_files}
    result.files = list(by_rel.keys())

    # Pass 1: symbols + imports.
    name_to_keys: dict[str, list[str]] = {}
    file_symbols: dict[str, list[Symbol]] = {}
    for rel, path in by_rel.items():
        try:
            if path.stat().st_size > _MAX_FILE_BYTES:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        lines = text.split("\n")
        is_py = path.suffix.lower() == ".py"

        for i, line in enumerate(lines, start=1):
            name = None
            base = "function"
            if is_py:
                m = _PY_DEF.match(line) or _PY_CLASS.match(line)
                if m:
                    name = m.group(1)
                    base = "class" if line.lstrip().startswith("class") else "function"
            else:
                m = _JS_FUNC.match(line) or _JS_CONST_FN.match(line)
                if m:
                    name, base = m.group(1), "function"
                else:
                    m = _JS_CLASS.match(line)
                    if m:
                        name, base = m.group(1), "class"
            if name and len(result.symbols) < _MAX_SYMBOLS:
                sym = Symbol(name=name, kind=_kind(name, base), file=rel, line=i)
                result.symbols.append(sym)
                file_symbols.setdefault(rel, []).append(sym)
                name_to_keys.setdefault(name, []).append(f"{rel}#{name}")

        # Imports.
        if is_py:
            for m in _PY_IMPORT.finditer(text):
                spec = m.group(1)
                if spec:
                    resolved = _resolve_import(spec.replace(".", "/"), path, root, by_rel)
                    if resolved:
                        result.imports.append((rel, resolved))
        else:
            for pat in (_JS_IMPORT, _JS_REQUIRE):
                for m in pat.finditer(text):
                    resolved = _resolve_import(m.group(1), path, root, by_rel)
                    if resolved and resolved != rel:
                        result.imports.append((rel, resolved))

    result.imports = list(dict.fromkeys(result.imports))[:_MAX_EDGES]

    # Pass 2: approximate calls. A symbol body is the text from its line to the next symbol in the
    # same file. Within it, calls to known symbol names become edges (same-file first, else a unique
    # global match) — grounded, if imperfect.
    call_set: set[tuple[str, str]] = set()
    for rel, syms in file_symbols.items():
        path = by_rel[rel]
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").split("\n")
        except OSError:
            continue
        ordered = sorted(syms, key=lambda s: s.line)
        local_names = {s.name: f"{rel}#{s.name}" for s in ordered}
        for idx, sym in enumerate(ordered):
            start = sym.line
            end = ordered[idx + 1].line if idx + 1 < len(ordered) else len(lines) + 1
            body = "\n".join(lines[start:end - 1])
            from_key = f"{rel}#{sym.name}"
            per_symbol = 0
            for cm in _CALL.finditer(body):
                called = cm.group(1)
                if called == sym.name or called in _KEYWORDS:
                    continue
                to_key = local_names.get(called)
                if not to_key:
                    keys = name_to_keys.get(called)
                    if keys and len(keys) == 1:
                        to_key = keys[0]
                if to_key and to_key != from_key:
                    edge = (from_key, to_key)
                    if edge not in call_set:
                        call_set.add(edge)
                        per_symbol += 1
                if per_symbol >= 8:
                    break
            if len(call_set) >= _MAX_EDGES:
                break

    result.calls = list(call_set)[:_MAX_EDGES]
    return result
