"""Language-neutral view over the independent indexes (Python: stdlib ast; TS/JS: TypeScript compiler)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from nb import pyindex
from nb.tsclient import TsClient


@dataclass
class Index:
    root: Path
    lang: str                       # py | ts
    decls: dict[str, dict] = field(default_factory=dict)
    calls: dict[str, dict] = field(default_factory=dict)
    name_tok: dict[tuple[str, int, int], str] = field(default_factory=dict)
    files: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    spans: dict[str, list[tuple[int, int, str]]] = field(default_factory=dict)
    py: object = None               # PyIndex for runtime mapping
    by_file_line: dict[tuple[str, int], list[str]] = field(default_factory=dict)  # decl ids by def line
    by_qual: dict[tuple[str, str], str] = field(default_factory=dict)
    modules: dict[str, str] = field(default_factory=dict)   # dotted module path -> file

    def canon(self, did: str) -> str:
        """Declarations sharing (file, qualname) — e.g. alternative definitions under `if` branches — are one
        identity, because that is the finest identity a qualified-name-returning tool can express."""
        d = self.decls.get(did)
        return self.by_qual.get((d["file"], d["qualname"]), did) if d else did

    def enclosing(self, file: str, line: int) -> str:
        best = None
        for first, end, did in self.spans.get(file, ()):
            if first <= line <= end and (best is None or first >= best[0]):
                best = (first, did)
        return self.canon(best[1]) if best else f"module:{file}"

    def decl_at_line(self, file: str, line: int) -> str | None:
        ids = self.by_file_line.get((file, line))
        return self.canon(ids[0]) if ids else None


def _module_path(file: str, lang: str) -> str:
    p = file
    for ext in (".py", ".tsx", ".ts", ".jsx", ".mjs", ".cjs", ".js", ".mts", ".cts"):
        if p.endswith(ext):
            p = p[: -len(ext)]
            break
    for tail in ("/__init__", "/index"):
        if p.endswith(tail):
            p = p[: -len(tail)]
    return p.replace("/", ".")


def load(root: Path, lang: str, ts_client: TsClient | None = None) -> Index:
    ix = Index(root=root, lang=lang)
    if lang == "py":
        p = pyindex.load(root)
        ix.py = p
        ix.files = p.files
        ix.failures = p.parse_failures
        for d in p.decls.values():
            ix.decls[d.id] = {"id": d.id, "file": d.file, "kind": d.kind, "name": d.name, "qualname": d.qualname,
                              "line": d.line, "col": d.col, "first_line": d.first_line, "end_line": d.end_line,
                              "is_test": d.is_test}
        for c in p.calls.values():
            ix.calls[c.id] = {"id": c.id, "file": c.file, "line": c.line, "col": c.col, "name": c.name,
                              "caller": c.caller}
        ix.name_tok = dict(p.by_name_token)
        ix.spans = {f: list(v) for f, v in p.spans.items()}
    else:
        t = ts_client.index()
        ix.files = t["files"]
        ix.failures = t["failures"]
        for d in t["decls"]:
            d = dict(d)
            d.pop("caller", None)
            ix.decls[d["id"]] = d
            ix.spans.setdefault(d["file"], []).append((d["line"], d["end_line"], d["id"]))
        for c in t["calls"]:
            ix.calls[c["id"]] = c
            if c["name"]:
                ix.name_tok[(c["file"], c["line"], c["col"])] = c["id"]
    for d in ix.decls.values():
        ix.by_file_line.setdefault((d["file"], d["line"]), []).append(d["id"])
        if d["first_line"] != d["line"]:
            ix.by_file_line.setdefault((d["file"], d["first_line"]), []).append(d["id"])
        ix.by_qual.setdefault((d["file"], d["qualname"]), d["id"])
    for f in ix.files:
        ix.modules.setdefault(_module_path(f, lang), f)
    return ix


def resolve_dotted(ix: Index, dotted: str) -> str | None:
    """'pkg.mod.Class.meth' -> decl id, using the longest module prefix that names a file."""
    parts = dotted.split(".")
    for i in range(len(parts), 0, -1):
        f = ix.modules.get(".".join(parts[:i]))
        if f is not None:
            q = ".".join(parts[i:])
            if not q:
                return f"module:{f}"
            did = ix.by_qual.get((f, q))
            if did:
                return did
            # tools that name nested declarations module.name: accept a same-file bare-name match
            last = q.split(".")[-1]
            cands = sorted({ix.canon(d["id"]) for d in ix.decls.values() if d["file"] == f and d["name"] == last
                            and (d["qualname"] == last or d["qualname"].endswith("." + q) or "." not in q)})
            if cands:
                return cands[0]
    return None
