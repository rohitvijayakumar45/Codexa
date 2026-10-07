"""Independent Python source index (stdlib `ast`), sharing nothing with the evaluated graph tools.

Provides the declaration sampling frame, the call-node table used to normalise every arm's
locations, and enclosing-declaration lookup for caller-level scoring.
"""
from __future__ import annotations

import ast
import bisect
from dataclasses import dataclass, field
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "site-packages", "build", "dist",
             ".tox", ".nox", ".mypy_cache", ".pytest_cache", ".eggs"}


@dataclass
class Decl:
    id: str            # "file:line:col" of the name token (1-based line, 0-based col)
    file: str
    kind: str          # function | method | class
    name: str
    qualname: str
    line: int          # line of the name token (def/class line)
    col: int           # col of the name token
    first_line: int    # first decorator line, else def line
    end_line: int
    is_test: bool


@dataclass
class CallNode:
    id: str            # "file:line:col" of the callee name token
    file: str
    line: int
    col: int
    end_line: int
    end_col: int       # span of the whole call expression (for runtime-position matching)
    span_line: int
    span_col: int
    name: str | None   # callee name token text, None for complex callees
    caller: str        # enclosing decl id, or "module:<file>"


@dataclass
class PyIndex:
    root: Path
    decls: dict[str, Decl] = field(default_factory=dict)
    calls: dict[str, CallNode] = field(default_factory=dict)
    by_name_token: dict[tuple[str, int, int], str] = field(default_factory=dict)  # (file,line,col)->call id
    by_span: dict[tuple[str, int, int, int, int], str] = field(default_factory=dict)
    calls_by_line: dict[tuple[str, int], list[str]] = field(default_factory=dict)
    spans: dict[str, list[tuple[int, int, str]]] = field(default_factory=dict)  # file -> (def line,end,decl)
    files: list[str] = field(default_factory=list)
    parse_failures: list[str] = field(default_factory=list)
    by_codekey: dict[tuple[str, int], str] = field(default_factory=dict)  # (file, first_line or line)->decl
    decorator_sites: set[tuple[str, int]] = field(default_factory=set)  # (file, line) of decorator expressions

    def enclosing(self, file: str, line: int) -> str:
        best = None
        for first, end, did in self.spans.get(file, ()):
            if first <= line <= end and (best is None or first >= best[0]):
                best = (first, did)
        return best[1] if best else f"module:{file}"

    def module_dotted(self, file: str) -> str:
        p = file[:-3] if file.endswith(".py") else file
        if p.endswith("/__init__"):
            p = p[: -len("/__init__")]
        return p.replace("/", ".")


def is_test_path(rel: str) -> bool:
    parts = rel.split("/")
    base = parts[-1]
    return any(p in ("tests", "test", "testing") for p in parts[:-1]) or base.startswith("test_") \
        or base.endswith("_test.py") or base == "conftest.py"


def build(root: Path) -> PyIndex:
    idx = PyIndex(root=root)
    for p in sorted(root.rglob("*.py")):
        rel = p.relative_to(root).as_posix()
        if any(part in SKIP_DIRS for part in rel.split("/")[:-1]):
            continue
        idx.files.append(rel)
        try:
            src = p.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(src, filename=rel)
        except (SyntaxError, ValueError):
            idx.parse_failures.append(rel)
            continue
        lines = src.splitlines()
        _CTX["lines"] = lines
        _walk(idx, rel, tree, lines, [], None)
    return idx


_CTX: dict = {}


def ch(line: int, bcol: int) -> int:
    """ast byte column -> character column (LSP/tsserver positions are character-based)."""
    lines = _CTX.get("lines") or []
    if not (0 < line <= len(lines)):
        return bcol
    return len(lines[line - 1].encode("utf-8")[:bcol].decode("utf-8", errors="ignore"))


def _name_col(lines: list[str], line: int, kw_col: int, name: str) -> int:
    text = lines[line - 1] if 0 < line <= len(lines) else ""
    i = text.find(name, kw_col)
    return i if i >= 0 else kw_col


def _walk(idx: PyIndex, rel: str, node: ast.AST, lines, stack: list[str], cls: str | None) -> None:
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            col = _name_col(lines, child.lineno, ch(child.lineno, child.col_offset), child.name)
            did = f"{rel}:{child.lineno}:{col}"
            first = min([d.lineno for d in child.decorator_list] + [child.lineno])
            if isinstance(child, ast.ClassDef):
                kind = "class"
            else:
                kind = "method" if cls is not None and stack and stack[-1] == cls else "function"
            qual = ".".join(stack + [child.name])
            d = Decl(did, rel, kind, child.name, qual, child.lineno, col, first,
                     getattr(child, "end_lineno", child.lineno), is_test_path(rel))
            idx.decls[did] = d
            idx.spans.setdefault(rel, []).append((child.lineno, d.end_line, did))  # decorators run in the outer scope
            idx.by_codekey[(rel, first)] = did
            idx.by_codekey.setdefault((rel, child.lineno), did)
            # decorators belong to the enclosing scope
            for dec in child.decorator_list:
                idx.decorator_sites.add((rel, dec.lineno))
                _walk_expr(idx, rel, dec)
            for sub in ([child.args] if not isinstance(child, ast.ClassDef) else child.bases + child.keywords):
                _walk_expr(idx, rel, sub)
            _walk(idx, rel, child, lines, stack + [child.name],
                  child.name if isinstance(child, ast.ClassDef) else None)
        else:
            if isinstance(child, ast.Call):
                _add_call(idx, rel, child)
            _walk(idx, rel, child, lines, stack, cls)


def _walk_expr(idx: PyIndex, rel: str, node: ast.AST) -> None:
    if isinstance(node, ast.Call):
        _add_call(idx, rel, node)
    for c in ast.iter_child_nodes(node):
        _walk_expr(idx, rel, c)


def _add_call(idx: PyIndex, rel: str, call: ast.Call) -> None:
    f = call.func
    if isinstance(f, ast.Name):
        name, line, col = f.id, f.lineno, ch(f.lineno, f.col_offset)
    elif isinstance(f, ast.Attribute):
        name, line = f.attr, f.end_lineno
        col = ch(line, f.end_col_offset) - len(f.attr)
    else:
        name, line, col = None, call.lineno, ch(call.lineno, call.col_offset)
    cid = f"{rel}:{line}:{col}"
    cn = CallNode(cid, rel, line, col, call.end_lineno, ch(call.end_lineno, call.end_col_offset), call.lineno,
                  ch(call.lineno, call.col_offset), name, "")
    idx.calls[cid] = cn
    if name:
        idx.by_name_token[(rel, line, col)] = cid
    idx.by_span[(rel, cn.span_line, cn.span_col, cn.end_line, cn.end_col)] = cid
    idx.calls_by_line.setdefault((rel, line), []).append(cid)


def finalize(idx: PyIndex) -> PyIndex:
    for cn in idx.calls.values():
        cn.caller = idx.enclosing(cn.file, cn.line)
    return idx


def load(root: Path) -> PyIndex:
    return finalize(build(root))
