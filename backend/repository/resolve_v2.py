"""Call resolution v2: two-pass, scope-, import- and receiver-aware.

The v1 resolver in analyze.py matches a call to a definition by bare name: same file first, then a
unique global match. The NavBench study (research/navbench) measured exactly where that loses
callers on seeded fixtures:

  * a same-named local helper nested in *another* function shadows the real target (the nested
    def is in the caller's file, so "same file first" picks it);
  * module-level calls are dropped, because there is no enclosing symbol to attribute them to;
  * relations it never records: calls through an import alias, a module/namespace attribute, a
    re-export, a typed receiver (`s: Svc = ...; s.m()`), `super().m()`, and TS `new X()`.

v2 keeps v1's symbol set and graph identities (same def query, same `file#qualname` keys, same
import edges) and replaces only call resolution:

  pass 1  per file: definitions with their lexical parents, module-level names, import bindings
          (local name -> (file, name) or -> module), TS re-exports, class bases, local variable
          types, and every call site with its scope chain;
  pass 2  resolve each call:
          identifier  -> nested def visible in an enclosing function scope, else a module-level
                         def, else an import binding (following re-export chains), else a unique
                         global top-level def;
          a.b(...)    -> self/this: the enclosing class (then its bases); super: the bases;
                         a typed local: that class; an imported module: its top-level b;
                         a class name: its member b; else a globally unique method b;
          new X(...)  -> X's class.
          Calls outside any definition are attributed to a per-file `<module>` pseudo-symbol.

Unresolvable calls are dropped rather than guessed: an edge into the wrong definition is worse
than a missing one.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from tree_sitter import Node, QueryCursor

from backend.repository.analyze import (
    _CLASS_NODES,
    _FUNCTION_NODES,
    _LANG_BY_EXT,
    _MAX_EDGES,
    _MAX_FILE_BYTES,
    _MAX_SYMBOLS,
    Analysis,
    Symbol,
    _discover,
    _js_import_specs,
    _kind,
    _parser_for,
    _py_import_specs,
    _qualify,
    _query_for,
    _resolve_absolute,
    _resolve_relative,
    _walk,
)

MODULE_SYMBOL = "<module>"
_MAX_CALLS_PER_SYMBOL = 64
_MAX_CHAIN = 6


def _text(n: Node | None) -> str:
    return n.text.decode("utf-8", errors="ignore") if n is not None and n.text else ""


@dataclass
class _Def:
    key: str
    name: str
    qual: str
    start: int
    end: int
    is_class: bool
    parent_fn: str | None = None     # innermost enclosing *function* def (nested-scope visibility)
    nested_in_fn: bool = False


@dataclass
class _Call:
    pos: int
    scope: list[str]                 # enclosing def keys, innermost first
    kind: str                        # name | attr | new
    name: str
    recv: str = ""                   # attr: identifier text, "self"/"this", "super", or "" (complex)


@dataclass
class _Mod:
    rel: str
    is_py: bool
    defs: list[_Def] = field(default_factory=list)
    by_key: dict[str, _Def] = field(default_factory=dict)
    top: dict[str, str] = field(default_factory=dict)             # module-level name -> key
    members: dict[str, dict[str, str]] = field(default_factory=dict)  # class key -> {member: key}
    bases: dict[str, list[str]] = field(default_factory=dict)     # class key -> base identifier names
    bindings: dict[str, tuple] = field(default_factory=dict)      # local -> ("sym", file, name) | ("mod", file)
    reexports: dict[str, tuple[str, str]] = field(default_factory=dict)
    var_types: dict[str | None, dict[str, str]] = field(default_factory=dict)  # scope key -> {var: type}
    calls: list[_Call] = field(default_factory=list)
    nested: dict[str, dict[str, str]] = field(default_factory=dict)  # parent fn key -> {name: key}
    n_lines: int = 1


class _Resolver:
    def __init__(self, mods: dict[str, _Mod]):
        self.mods = mods
        self.global_top: dict[str, list[str]] = {}
        self.global_methods: dict[str, list[str]] = {}
        for m in mods.values():
            for d in m.defs:
                if d.nested_in_fn:
                    continue
                if "." in d.qual:
                    self.global_methods.setdefault(d.name, []).append(d.key)
                else:
                    self.global_top.setdefault(d.name, []).append(d.key)

    # -- bindings -------------------------------------------------------------------------------
    def _export(self, file: str, name: str, depth: int = 0) -> str | None:
        """Top-level definition `name` of module `file`, following re-export chains."""
        m = self.mods.get(file)
        if m is None or depth > _MAX_CHAIN:
            return None
        if name in m.top:
            return m.top[name]
        b = m.bindings.get(name)
        if b and b[0] == "sym":
            return self._export(b[1], b[2], depth + 1)
        r = m.reexports.get(name)
        if r:
            return self._export(r[0], r[1], depth + 1)
        return None

    def ident(self, m: _Mod, scope: list[str], name: str) -> str | None:
        for skey in scope:  # nested defs are visible only inside their parent function
            hit = m.nested.get(skey, {}).get(name)
            if hit:
                return hit
        if name in m.top:
            return m.top[name]
        b = m.bindings.get(name)
        if b:
            return self._export(b[1], b[2]) if b[0] == "sym" else None
        cands = self.global_top.get(name, [])
        return cands[0] if len(cands) == 1 else None

    def _class_of(self, m: _Mod, scope: list[str]) -> str | None:
        for skey in scope:
            d = m.by_key.get(skey)
            if d is None:
                continue
            if d.is_class:
                return d.key
            if "." in d.qual:  # a method: its class is file#Owner
                owner = f"{m.rel}#{d.qual.rsplit('.', 1)[0]}"
                if owner in m.by_key:
                    return owner
        return None

    def member(self, class_key: str, attr: str, depth: int = 0, skip_self: bool = False) -> str | None:
        if depth > _MAX_CHAIN:
            return None
        file = class_key.split("#", 1)[0]
        m = self.mods.get(file)
        if m is None:
            return None
        if not skip_self:
            hit = m.members.get(class_key, {}).get(attr)
            if hit:
                return hit
        for base in m.bases.get(class_key, []):
            bkey = self.ident(m, [], base)
            if bkey and bkey != class_key:
                hit = self.member(bkey, attr, depth + 1)
                if hit:
                    return hit
        return None

    def _var_type(self, m: _Mod, scope: list[str], var: str) -> str | None:
        for skey in scope + [None]:
            t = m.var_types.get(skey, {}).get(var)
            if t:
                return t
        return None

    def call(self, m: _Mod, c: _Call) -> str | None:
        if c.kind in ("name", "new"):
            return self.ident(m, c.scope, c.name)
        # attribute / member call
        if c.recv in ("self", "this"):
            cls = self._class_of(m, c.scope)
            return self.member(cls, c.name) if cls else None
        if c.recv == "super":
            cls = self._class_of(m, c.scope)
            return self.member(cls, c.name, skip_self=True) if cls else None
        if c.recv:
            t = self._var_type(m, c.scope, c.recv)
            if t:
                tkey = self.ident(m, c.scope, t)
                if tkey and m_is_class(self, tkey):
                    hit = self.member(tkey, c.name)
                    if hit:
                        return hit
            b = m.bindings.get(c.recv)
            if b and b[0] == "mod":
                return self._export(b[1], c.name)
            rkey = self.ident(m, c.scope, c.recv)
            if rkey and m_is_class(self, rkey):
                return self.member(rkey, c.name)
            if rkey:  # a known non-class receiver (function/variable): don't guess its methods
                return None
        cands = self.global_methods.get(c.name, [])
        return cands[0] if len(cands) == 1 else None


def m_is_class(r: _Resolver, key: str) -> bool:
    m = r.mods.get(key.split("#", 1)[0])
    d = m.by_key.get(key) if m else None
    return bool(d and d.is_class)


# ---------------------------------------------------------------------------------- pass 1 ----
def _collect(rel: str, path: Path, root: Path, by_rel: dict[str, Path], result: Analysis) -> _Mod | None:
    ext = path.suffix.lower()
    lq = _LANG_BY_EXT.get(ext)
    if lq is None:
        return None
    lang, query_src = lq
    try:
        if path.stat().st_size > _MAX_FILE_BYTES:
            return None
        source = path.read_bytes()
        tree = _parser_for(lang).parse(source)
    except Exception:  # noqa: BLE001 - malformed source shouldn't break the whole ingest
        return None
    is_py = ext == ".py"
    m = _Mod(rel=rel, is_py=is_py, n_lines=source.count(b"\n") + 1)

    # Definitions: exactly v1's query, keys and symbols.
    raw_defs: list[tuple[Node, _Def]] = []
    for _i, caps in QueryCursor(_query_for(lang, query_src)).matches(tree.root_node):
        dnode, nnode = caps.get("def.node"), caps.get("def.name")
        if not (dnode and nnode):
            continue
        dn, nn = dnode[0], nnode[0]
        name = _text(nn)
        if not name or len(result.symbols) >= _MAX_SYMBOLS:
            continue
        qual = _qualify(dn, name)
        result.symbols.append(Symbol(
            name=name, kind=_kind(name, dn.type), file=rel, line=nn.start_point[0] + 1,
            end_line=dn.end_point[0] + 1, content_hash=hashlib.sha256(source[dn.start_byte:dn.end_byte]).hexdigest()[:16],
            qualname=qual if qual != name else "",
        ))
        d = _Def(key=f"{rel}#{qual}", name=name, qual=qual, start=dn.start_byte, end=dn.end_byte,
                 is_class=dn.type in _CLASS_NODES)
        raw_defs.append((dn, d))
    by_node = {(dn.start_byte, dn.end_byte): d for dn, d in raw_defs}
    for dn, d in raw_defs:
        p = dn.parent
        while p is not None:
            if p.type in _FUNCTION_NODES and (p.start_byte, p.end_byte) in by_node:
                d.parent_fn = by_node[(p.start_byte, p.end_byte)].key
                d.nested_in_fn = True
                break
            if p.type == "variable_declarator" and (p.start_byte, p.end_byte) in by_node:
                d.parent_fn = by_node[(p.start_byte, p.end_byte)].key
                d.nested_in_fn = True
                break
            if p.type in _CLASS_NODES:
                break
            p = p.parent
        m.defs.append(d)
        m.by_key.setdefault(d.key, d)
        if d.nested_in_fn and d.parent_fn and "." not in d.qual:
            m.nested.setdefault(d.parent_fn, {}).setdefault(d.name, d.key)
        if not d.nested_in_fn:
            if "." in d.qual:
                owner = f"{rel}#{d.qual.rsplit('.', 1)[0]}"
                m.members.setdefault(owner, {}).setdefault(d.name, d.key)
            else:
                m.top.setdefault(d.name, d.key)
        if d.is_class:
            m.bases[d.key] = _bases(dn, is_py)

    # Imports (edges exactly as v1) and bindings.
    for inode in _walk(tree.root_node, {"import_statement", "import_from_statement"} if is_py else {"import_statement"}):
        if is_py:
            for spec, is_rel in _py_import_specs(inode):
                resolved = _resolve_relative(spec, path.parent, root, by_rel) if is_rel else _resolve_absolute(spec, root, by_rel)
                if resolved and resolved != rel:
                    result.imports.append((rel, resolved))
            _py_bindings(inode, path, root, by_rel, m)
        else:
            for spec in _js_import_specs(inode):
                resolved = _resolve_relative(spec, path.parent, root, by_rel)
                if resolved and resolved != rel:
                    result.imports.append((rel, resolved))
            _ts_bindings(inode, path, root, by_rel, m)
    if not is_py:
        for cnode in _walk(tree.root_node, {"call_expression"}):
            for spec in _js_import_specs(cnode):
                resolved = _resolve_relative(spec, path.parent, root, by_rel)
                if resolved and resolved != rel:
                    result.imports.append((rel, resolved))
        for enode in _walk(tree.root_node, {"export_statement"}):
            _ts_reexports(enode, path, root, by_rel, m)

    # Calls, local variable types.
    spans = sorted(((d.start, d.end, d.key) for d in m.defs), key=lambda t: t[1] - t[0])

    def scope_of(pos: int) -> list[str]:
        return [k for s, e, k in spans if s <= pos <= e]

    call_types = {"call"} if is_py else {"call_expression", "new_expression"}
    for node in _walk(tree.root_node, call_types | ({"assignment"} if is_py else {"variable_declarator"})):
        if node.type in ("assignment", "variable_declarator"):
            _var_type(node, is_py, scope_of(node.start_byte), m)
            continue
        c = _call(node, is_py)
        if c is None:
            continue
        kind, name, recv, pos = c
        if name == "require" and kind == "name":
            continue
        m.calls.append(_Call(pos=pos, scope=scope_of(pos), kind=kind, name=name, recv=recv))
    return m


def _bases(dn: Node, is_py: bool) -> list[str]:
    out = []
    if is_py:
        sup = dn.child_by_field_name("superclasses")
        for c in (sup.named_children if sup is not None else []):
            if c.type == "identifier":
                out.append(_text(c))
            elif c.type == "attribute":
                out.append(_text(c.child_by_field_name("attribute")))
    else:
        for h in dn.named_children:
            if h.type == "class_heritage":
                for ext in h.named_children:
                    if ext.type == "extends_clause":
                        for v in ext.named_children:
                            if v.type in ("identifier", "type_identifier"):
                                out.append(_text(v))
            elif h.type == "extends_clause":  # javascript grammar
                for v in h.named_children:
                    if v.type == "identifier":
                        out.append(_text(v))
    return out


def _py_module_file(module_node: Node, path: Path, root: Path, by_rel: dict[str, Path]) -> tuple[str | None, str, bool]:
    """(resolved module file, filesystem-style spec, is_relative) for an import_from module node."""
    if module_node.type == "dotted_name":
        spec = _text(module_node)
        return _resolve_absolute(spec, root, by_rel), spec.replace(".", "/"), False
    prefix = next((c for c in module_node.children if c.type == "import_prefix"), None)
    dots = _text(prefix).count(".") if prefix is not None else 1
    rest = next((c for c in module_node.children if c.type == "dotted_name"), None)
    up = "../" * (dots - 1)
    spec = f"{up}{_text(rest).replace('.', '/')}" if rest is not None else (up or ".")
    return _resolve_relative(spec, path.parent, root, by_rel), spec, True


def _py_bindings(node: Node, path: Path, root: Path, by_rel: dict[str, Path], m: _Mod) -> None:
    if node.type == "import_from_statement":
        mod = node.child_by_field_name("module_name") or next(
            (c for c in node.children if c.type in ("dotted_name", "relative_import")), None)
        if mod is None:
            return
        mfile, spec, is_rel = _py_module_file(mod, path, root, by_rel)
        for c in node.children:
            if c is mod or c.type not in ("dotted_name", "aliased_import"):
                continue
            if c.type == "aliased_import":
                orig = _text(c.child_by_field_name("name"))
                local = _text(c.child_by_field_name("alias")) or orig
            else:
                orig = local = _text(c)
            if "." in orig:
                continue
            sub_spec = f"{spec.rstrip('/')}/{orig}" if spec not in (".", "") else orig
            sub = (_resolve_relative(sub_spec, path.parent, root, by_rel) if is_rel
                   else _resolve_absolute(sub_spec.replace("/", "."), root, by_rel))
            if sub and not (mfile and sub == mfile):
                m.bindings[local] = ("mod", sub)
            elif mfile:
                m.bindings[local] = ("sym", mfile, orig)
    else:  # import_statement
        for c in node.named_children:
            if c.type == "aliased_import":
                target = _resolve_absolute(_text(c.child_by_field_name("name")), root, by_rel)
                alias = _text(c.child_by_field_name("alias"))
                if target and alias:
                    m.bindings[alias] = ("mod", target)
            elif c.type == "dotted_name" and "." not in _text(c):
                target = _resolve_absolute(_text(c), root, by_rel)
                if target:
                    m.bindings[_text(c)] = ("mod", target)


def _ts_source(node: Node, path: Path, root: Path, by_rel: dict[str, Path]) -> str | None:
    src = node.child_by_field_name("source") or next((c for c in node.children if c.type == "string"), None)
    spec = _text(src).strip("'\"") if src is not None else ""
    return _resolve_relative(spec, path.parent, root, by_rel) if spec.startswith(".") else None


def _ts_bindings(node: Node, path: Path, root: Path, by_rel: dict[str, Path], m: _Mod) -> None:
    target = _ts_source(node, path, root, by_rel)
    if target is None:
        return
    for clause in node.named_children:
        if clause.type != "import_clause":
            continue
        for part in clause.named_children:
            if part.type == "identifier":  # default import
                m.bindings[_text(part)] = ("sym", target, "default")
            elif part.type == "namespace_import":
                ident = next((x for x in part.named_children if x.type == "identifier"), None)
                if ident is not None:
                    m.bindings[_text(ident)] = ("mod", target)
            elif part.type == "named_imports":
                for spec in part.named_children:
                    if spec.type != "import_specifier":
                        continue
                    ids = [x for x in spec.named_children if x.type == "identifier"]
                    if not ids:
                        continue
                    orig = _text(spec.child_by_field_name("name") or ids[0])
                    alias = spec.child_by_field_name("alias")
                    local = _text(alias) if alias is not None else (_text(ids[1]) if len(ids) > 1 else orig)
                    m.bindings[local] = ("sym", target, orig)


def _ts_reexports(node: Node, path: Path, root: Path, by_rel: dict[str, Path], m: _Mod) -> None:
    target = _ts_source(node, path, root, by_rel)
    if target is None:
        return
    for clause in node.named_children:
        if clause.type != "export_clause":
            continue
        for spec in clause.named_children:
            if spec.type != "export_specifier":
                continue
            ids = [x for x in spec.named_children if x.type == "identifier"]
            if not ids:
                continue
            orig = _text(spec.child_by_field_name("name") or ids[0])
            alias = spec.child_by_field_name("alias")
            exported = _text(alias) if alias is not None else (_text(ids[1]) if len(ids) > 1 else orig)
            m.reexports[exported] = (target, orig)


def _var_type(node: Node, is_py: bool, scope: list[str], m: _Mod) -> None:
    skey = scope[0] if scope else None
    if is_py:
        left = node.child_by_field_name("left")
        if left is None or left.type != "identifier":
            return
        ann = node.child_by_field_name("type")
        tname = ""
        if ann is not None:
            ident = ann if ann.type == "identifier" else next((x for x in ann.named_children if x.type == "identifier"), None)
            tname = _text(ident)
        if not tname:
            right = node.child_by_field_name("right")
            if right is not None and right.type == "call":
                fn = right.child_by_field_name("function")
                if fn is not None and fn.type == "identifier":
                    tname = _text(fn)
        if tname:
            m.var_types.setdefault(skey, {})[_text(left)] = tname
    else:
        name = node.child_by_field_name("name")
        if name is None or name.type != "identifier":
            return
        tname = ""
        ann = node.child_by_field_name("type")
        if ann is not None:
            ti = next((x for x in ann.named_children if x.type == "type_identifier"), None)
            tname = _text(ti)
        if not tname:
            val = node.child_by_field_name("value")
            if val is not None and val.type == "new_expression":
                ctor = val.child_by_field_name("constructor")
                if ctor is not None and ctor.type == "identifier":
                    tname = _text(ctor)
        if tname:
            m.var_types.setdefault(skey, {})[_text(name)] = tname


def _call(node: Node, is_py: bool) -> tuple[str, str, str, int] | None:
    """(kind, name, receiver, position of the callee name token) for a call node."""
    if node.type == "new_expression":
        ctor = node.child_by_field_name("constructor")
        if ctor is not None and ctor.type == "identifier":
            return "new", _text(ctor), "", ctor.start_byte
        return None
    fn = node.child_by_field_name("function")
    if fn is None:
        return None
    if fn.type == "identifier":
        return "name", _text(fn), "", fn.start_byte
    if is_py and fn.type == "attribute":
        obj, attr = fn.child_by_field_name("object"), fn.child_by_field_name("attribute")
        if attr is None:
            return None
        recv = ""
        if obj is not None:
            if obj.type == "identifier":
                recv = _text(obj)
            elif obj.type == "call":
                f2 = obj.child_by_field_name("function")
                if f2 is not None and _text(f2) == "super":
                    recv = "super"
        return "attr", _text(attr), recv, attr.start_byte
    if not is_py and fn.type == "member_expression":
        obj, prop = fn.child_by_field_name("object"), fn.child_by_field_name("property")
        if prop is None:
            return None
        recv = ""
        if obj is not None:
            if obj.type in ("identifier", "this", "super"):
                recv = _text(obj)
        return "attr", _text(prop), recv, prop.start_byte
    return None


# ---------------------------------------------------------------------------------- pass 2 ----
def analyze_repo_v2(root: Path) -> Analysis:
    root = root.resolve()
    result, by_rel = _discover(root)
    mods: dict[str, _Mod] = {}
    for rel, path in by_rel.items():
        m = _collect(rel, path, root, by_rel, result)
        if m is not None:
            mods[rel] = m

    r = _Resolver(mods)
    call_set: set[tuple[str, str]] = set()
    per_symbol: dict[str, int] = {}
    module_syms: set[str] = set()
    for rel, m in mods.items():
        for c in m.calls:
            to_key = r.call(m, c)
            if not to_key:
                continue
            from_key = c.scope[0] if c.scope else f"{rel}#{MODULE_SYMBOL}"
            if to_key == from_key:
                continue
            if per_symbol.get(from_key, 0) >= _MAX_CALLS_PER_SYMBOL:
                continue
            edge = (from_key, to_key)
            if edge in call_set:
                continue
            call_set.add(edge)
            per_symbol[from_key] = per_symbol.get(from_key, 0) + 1
            if not c.scope and rel not in module_syms and len(result.symbols) < _MAX_SYMBOLS:
                module_syms.add(rel)
                result.symbols.append(Symbol(name=MODULE_SYMBOL, kind="module", file=rel, line=1,
                                             end_line=m.n_lines, qualname=""))
            if len(call_set) >= _MAX_EDGES:
                break
        if len(call_set) >= _MAX_EDGES:
            break
    # Module-level edges whose pseudo-symbol could not be created (symbol cap) would dangle: drop them.
    result.calls = [e for e in call_set
                    if not e[0].endswith(f"#{MODULE_SYMBOL}") or e[0].split("#", 1)[0] in module_syms][:_MAX_EDGES]
    result.imports = list(dict.fromkeys(result.imports))[:_MAX_EDGES]
    return result
