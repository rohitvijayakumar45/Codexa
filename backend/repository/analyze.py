"""Static analysis of a cloned repository via real parsers (tree-sitter).

Extracts real code structure so the knowledge graph reflects the actual codebase rather than just
metadata: source files, the functions/classes/methods defined in them, file-to-file imports, and an
approximate call graph between symbols. Uses tree-sitter grammars (Python, JS, TS, TSX) for accurate
AST-based extraction — real symbol scopes (so a call inside a method attributes to that method, not
"until the next symbol line"), and precise import specifiers instead of regex-guessed ones. Bounded
so large repos stay fast.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import tree_sitter_javascript as _tsjs
import tree_sitter_python as _tspy
import tree_sitter_typescript as _tsts
from tree_sitter import Language, Node, Parser, Query, QueryCursor

_SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".next", ".agents", "coverage"}
_SRC_EXT = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".py"}

_MAX_FILES = 300
_MAX_SYMBOLS = 700
_MAX_EDGES = 1200
_MAX_FILE_BYTES = 200_000
_MAX_CALLS_PER_SYMBOL = 12

_PY_LANG = Language(_tspy.language())
_JS_LANG = Language(_tsjs.language())
_TS_LANG = Language(_tsts.language_typescript())
_TSX_LANG = Language(_tsts.language_tsx())

_DEF_CALL_QUERY = """
(function_definition name: (identifier) @def.name) @def.node
(class_definition name: (identifier) @def.name) @def.node
(call function: (identifier) @call.name)
(call function: (attribute attribute: (identifier) @call.name))
"""

_JS_DEF_CALL_QUERY = """
(function_declaration name: (identifier) @def.name) @def.node
(class_declaration name: (identifier) @def.name) @def.node
(method_definition name: (property_identifier) @def.name) @def.node
(variable_declarator name: (identifier) @def.name value: (arrow_function)) @def.node
(variable_declarator name: (identifier) @def.name value: (function_expression)) @def.node
(call_expression function: (identifier) @call.name)
(call_expression function: (member_expression property: (property_identifier) @call.name))
"""

_TS_DEF_CALL_QUERY = _JS_DEF_CALL_QUERY.replace(
    "(class_declaration name: (identifier)", "(class_declaration name: (type_identifier)"
)

_LANG_BY_EXT: dict[str, tuple[Language, str]] = {
    ".py": (_PY_LANG, _DEF_CALL_QUERY),
    ".js": (_JS_LANG, _JS_DEF_CALL_QUERY),
    ".jsx": (_JS_LANG, _JS_DEF_CALL_QUERY),
    ".mjs": (_JS_LANG, _JS_DEF_CALL_QUERY),
    ".ts": (_TS_LANG, _TS_DEF_CALL_QUERY),
    ".tsx": (_TSX_LANG, _TS_DEF_CALL_QUERY),
}

_QUERY_CACHE: dict[int, Query] = {}
_PARSER_CACHE: dict[int, Parser] = {}


def _query_for(lang: Language, query_src: str) -> Query:
    key = id(lang)
    q = _QUERY_CACHE.get(key)
    if q is None:
        q = Query(lang, query_src)
        _QUERY_CACHE[key] = q
    return q


def _parser_for(lang: Language) -> Parser:
    key = id(lang)
    p = _PARSER_CACHE.get(key)
    if p is None:
        p = Parser(lang)
        _PARSER_CACHE[key] = p
    return p


@dataclass
class Symbol:
    name: str
    kind: str  # function | class | component | hook
    file: str  # repo-relative posix path
    line: int
    end_line: int = 0
    content_hash: str = ""  # sha256 of the symbol's source span — drives staleness detection


@dataclass
class Analysis:
    files: list[str] = field(default_factory=list)
    symbols: list[Symbol] = field(default_factory=list)
    imports: list[tuple[str, str]] = field(default_factory=list)  # (from_file, to_file)
    calls: list[tuple[str, str]] = field(default_factory=list)  # (from_symbol_key, to_symbol_key)


def _rel(path: Path, root: Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/")


def _kind(name: str, node_type: str) -> str:
    if name.startswith("use") and len(name) > 3 and name[3].isupper():
        return "hook"
    if node_type in ("class_definition", "class_declaration"):
        return "class"
    if name[:1].isupper():
        return "component"
    return "function"


def _resolve_relative(spec_path: str, base_dir: Path, root: Path, by_rel: dict[str, str]) -> str | None:
    """spec_path is a relative filesystem-style path (dots-as-slashes already applied)."""
    target = (base_dir / spec_path).resolve()
    candidates = [target]
    for ext in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".py"):
        candidates.append(target.with_suffix(ext))
        candidates.append(target / f"index{ext}")
        candidates.append(target / f"__init__{ext}")
    for cand in candidates:
        try:
            rel = _rel(cand, root)
        except ValueError:
            continue
        if rel in by_rel:
            return rel
    return None


def _resolve_absolute(dotted: str, root: Path, by_rel: dict[str, str]) -> str | None:
    """Best-effort resolution of an absolute dotted import (e.g. `import pkg.mod`) against repo root."""
    return _resolve_relative(dotted.replace(".", "/"), root, root, by_rel)


def _py_import_specs(node: Node) -> list[tuple[str, bool]]:
    """Returns (spec, is_relative) pairs for a python import_statement/import_from_statement node."""
    specs: list[tuple[str, bool]] = []

    def dotted_text(n: Node) -> str:
        return n.text.decode("utf-8", errors="ignore") if n.text else ""

    if node.type == "import_statement":
        for child in node.children:
            if child.type == "dotted_name":
                specs.append((dotted_text(child), False))
            elif child.type == "aliased_import":
                dn = child.child_by_field_name("name") or next(
                    (c for c in child.children if c.type == "dotted_name"), None
                )
                if dn:
                    specs.append((dotted_text(dn), False))
    elif node.type == "import_from_statement":
        module = next((c for c in node.children if c.type in ("dotted_name", "relative_import")), None)
        if module is None:
            return specs
        if module.type == "dotted_name":
            specs.append((dotted_text(module), False))
        else:
            prefix = next((c for c in module.children if c.type == "import_prefix"), None)
            dots = prefix.text.decode("utf-8").count(".") if prefix and prefix.text else 1
            rest = next((c for c in module.children if c.type == "dotted_name"), None)
            up = "../" * (dots - 1)
            path = f"{up}{dotted_text(rest).replace('.', '/')}" if rest else up or "."
            specs.append((path, True))
    return specs


def _js_import_specs(node: Node) -> list[str]:
    specs: list[str] = []
    if node.type == "import_statement":
        src = node.child_by_field_name("source")
        if src is None:
            src = next((c for c in node.children if c.type == "string"), None)
        if src and src.text:
            text = src.text.decode("utf-8", errors="ignore").strip("'\"")
            if text.startswith("."):
                specs.append(text)
    elif node.type == "call_expression":
        fn = node.child_by_field_name("function")
        if fn is not None and fn.text and fn.text.decode("utf-8", errors="ignore") == "require":
            args = node.child_by_field_name("arguments")
            if args is not None:
                for c in args.children:
                    if c.type == "string" and c.text:
                        text = c.text.decode("utf-8", errors="ignore").strip("'\"")
                        if text.startswith("."):
                            specs.append(text)
    return specs


def _walk(node: Node, types: set[str]):
    if node.type in types:
        yield node
    for child in node.children:
        yield from _walk(child, types)


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

    name_to_keys: dict[str, list[str]] = {}
    call_set: set[tuple[str, str]] = set()

    for rel, path in by_rel.items():
        ext = path.suffix.lower()
        lang_query = _LANG_BY_EXT.get(ext)
        if lang_query is None:
            continue
        lang, query_src = lang_query
        try:
            if path.stat().st_size > _MAX_FILE_BYTES:
                continue
            source = path.read_bytes()
        except OSError:
            continue

        parser = _parser_for(lang)
        try:
            tree = parser.parse(source)
        except Exception:  # noqa: BLE001 - malformed source shouldn't break the whole ingest
            continue

        query = _query_for(lang, query_src)
        qc = QueryCursor(query)
        matches = qc.matches(tree.root_node)

        # Definitions: (start_byte, end_byte, symbol_key, name node line)
        defs: list[tuple[int, int, str, Node]] = []
        call_nodes: list[Node] = []
        is_py = ext == ".py"

        for _pattern_idx, captures in matches:
            def_node = captures.get("def.node")
            name_node = captures.get("def.name")
            if def_node and name_node:
                dn, nn = def_node[0], name_node[0]
                name = nn.text.decode("utf-8", errors="ignore") if nn.text else ""
                if not name or len(result.symbols) >= _MAX_SYMBOLS:
                    continue
                line = nn.start_point[0] + 1
                end_line = dn.end_point[0] + 1
                content_hash = hashlib.sha256(source[dn.start_byte:dn.end_byte]).hexdigest()[:16]
                sym = Symbol(
                    name=name, kind=_kind(name, dn.type), file=rel, line=line,
                    end_line=end_line, content_hash=content_hash,
                )
                result.symbols.append(sym)
                key = f"{rel}#{name}"
                defs.append((dn.start_byte, dn.end_byte, key, dn))
                name_to_keys.setdefault(name, []).append(key)
            call_name_nodes = captures.get("call.name")
            if call_name_nodes:
                call_nodes.extend(call_name_nodes)

        # Imports.
        import_node_types = {"import_statement"} if is_py else {"import_statement"}
        if is_py:
            import_node_types = {"import_statement", "import_from_statement"}
        for inode in _walk(tree.root_node, import_node_types):
            if is_py:
                for spec, is_rel in _py_import_specs(inode):
                    resolved = (
                        _resolve_relative(spec, path.parent, root, by_rel)
                        if is_rel
                        else _resolve_absolute(spec, root, by_rel)
                    )
                    if resolved and resolved != rel:
                        result.imports.append((rel, resolved))
            else:
                for spec in _js_import_specs(inode):
                    resolved = _resolve_relative(spec, path.parent, root, by_rel)
                    if resolved and resolved != rel:
                        result.imports.append((rel, resolved))
        if not is_py:
            for cnode in _walk(tree.root_node, {"call_expression"}):
                for spec in _js_import_specs(cnode):
                    resolved = _resolve_relative(spec, path.parent, root, by_rel)
                    if resolved and resolved != rel:
                        result.imports.append((rel, resolved))

        # Calls: attribute each call to its innermost enclosing definition, then resolve the callee
        # (same-file first, else a unique global match) — grounded, if imperfect.
        per_symbol_count: dict[str, int] = {}
        defs_sorted = sorted(defs, key=lambda d: d[1] - d[0])  # smallest span first = innermost priority
        for call_name_node in call_nodes:
            called = call_name_node.text.decode("utf-8", errors="ignore") if call_name_node.text else ""
            if not called or called == "require":
                continue
            pos = call_name_node.start_byte
            from_key = None
            for start, end, key, _dn in defs_sorted:
                if start <= pos <= end:
                    from_key = key
                    break
            if not from_key or called == from_key.split("#", 1)[-1]:
                continue
            if per_symbol_count.get(from_key, 0) >= _MAX_CALLS_PER_SYMBOL:
                continue
            to_key = f"{rel}#{called}" if f"{rel}#{called}" in name_to_keys.get(called, []) else None
            if not to_key:
                keys = name_to_keys.get(called)
                if keys and len(keys) == 1:
                    to_key = keys[0]
            if to_key and to_key != from_key:
                edge = (from_key, to_key)
                if edge not in call_set:
                    call_set.add(edge)
                    per_symbol_count[from_key] = per_symbol_count.get(from_key, 0) + 1
            if len(call_set) >= _MAX_EDGES:
                break
        if len(call_set) >= _MAX_EDGES:
            break

    result.imports = list(dict.fromkeys(result.imports))[:_MAX_EDGES]
    result.calls = list(call_set)[:_MAX_EDGES]
    return result
