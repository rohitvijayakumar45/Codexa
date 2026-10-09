"""Pluggable retrieval adapters (feature C).

Every evaluated tool is an Adapter: it declares which tasks it answers (T1 direct callers, T2
definition lookup, T3 multi-hop callers) and under which arm labels its rows are written. The
frozen study's arms are reproduced *unchanged* by wrapping nb/arms.py:

    adapter    T1 arm(s)                    T2 arm         T3 arm
    rg0        rg0                          rg_def         rg0_t3
    rg3        rg3                          -              -
    lsp        lsp                          lsp_def        lsp_t3
    codexa     codexa_refs, codexa_orig     codexa_def     codexa_t3     (G1 as frozen: resolution v1)
    cbm_cur    cbm_cur                      cbm_cur_def    cbm_cur_t3
    cbm_057    cbm_057                      cbm_057_def    -
    codexa2    codexa2_refs                 codexa2_def    codexa2_t3    (G1-v2: resolution v2)

`FROZEN` lists the adapters (in the frozen row order) that `nb.run` uses by default, so a default
run reproduces the confirmatory configuration in FREEZE.md. An adapter whose tool is not
installed (e.g. a missing codebase-memory binary) is reported as `unsupported`, never silently
dropped.

Third-party tools: put a module on PYTHONPATH that subclasses Adapter and calls `register(...)`,
then set NB_PLUGINS=that.module (comma-separated for several). See ADAPTERS.md.
"""
from __future__ import annotations

import contextlib
import importlib
import json
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from nb import arms as A
from nb.arms import ArmResult

TASKS = ("T1", "T2", "T3")


@dataclass
class Ctx:
    repo: str
    lang: str
    layer: str
    root: Path
    ix: object
    provider: object = None               # PyrightClient (py) or TsClient (ts)
    data_dir: Path = Path(os.environ.get("CODEXA_DATA_DIR", "/work/nb"))
    extra: dict = field(default_factory=dict)


class Adapter:
    name = ""
    t1_arms: tuple[str, ...] = ()
    t2_arm: str | None = None
    t3_arm: str | None = None

    def available(self) -> tuple[bool, str]:
        return True, ""

    def setup(self, ctx: Ctx) -> dict:
        """Index/prepare for one repository; returns timing/meta to record."""
        return {}

    def t1(self, ctx: Ctx, decl: dict) -> list[ArmResult]:
        raise NotImplementedError

    def t2(self, ctx: Ctx, decl: dict, site: tuple[str, int, int]) -> ArmResult:
        raise NotImplementedError

    def t3(self, ctx: Ctx, decl: dict, depth: int) -> ArmResult:
        raise NotImplementedError

    def close(self) -> None:
        pass

    def unsupported(self, arm: str, note: str) -> ArmResult:
        return ArmResult(arm, "unsupported", note=note[:200])


REGISTRY: dict[str, type[Adapter]] = {}
FROZEN = ["rg0", "rg3", "lsp", "codexa", "cbm_cur", "cbm_057"]
FROZEN_T2_ORDER = ["lsp", "rg0", "codexa", "cbm_cur", "cbm_057"]


def register(cls: type[Adapter]) -> type[Adapter]:
    if not cls.name:
        raise ValueError("adapter needs a name")
    REGISTRY[cls.name] = cls
    return cls


def load_plugins() -> None:
    for mod in [m.strip() for m in os.environ.get("NB_PLUGINS", "").split(",") if m.strip()]:
        importlib.import_module(mod)


def make(names: list[str]) -> list[Adapter]:
    load_plugins()
    missing = [n for n in names if n not in REGISTRY]
    if missing:
        raise KeyError(f"unknown adapter(s) {missing}; registered: {sorted(REGISTRY)}")
    return [REGISTRY[n]() for n in names]


@contextlib.contextmanager
def resolution(mode: str):
    """Pin Codexa's call-resolution algorithm (backend/repository/analyze.py: resolution_mode)."""
    old = os.environ.get("CODEXA_CALL_RESOLUTION")
    os.environ["CODEXA_CALL_RESOLUTION"] = mode
    try:
        yield
    finally:
        if old is None:
            os.environ.pop("CODEXA_CALL_RESOLUTION", None)
        else:
            os.environ["CODEXA_CALL_RESOLUTION"] = old


# ------------------------------------------------------------------------------- lexical ----
_DEF_LINE = {
    "py": re.compile(r"^\s*(?:async\s+)?(?:def|class)\s+([A-Za-z_]\w*)"),
    "ts": re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:declare\s+)?(?:abstract\s+)?(?:async\s+)?"
                     r"(?:function\s*\*?\s*([A-Za-z_$][\w$]*)|class\s+([A-Za-z_$][\w$]*)|"
                     r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*(?::[^=]+)?=\s*(?:async\s*)?(?:\(|function|[A-Za-z_$][\w$]*\s*=>)|"
                     r"(?:(?:public|private|protected|static|readonly|override|async|get|set)\s+)*([A-Za-z_$][\w$]*)\s*(?:<[^>]*>)?\s*\([^)]*\)\s*(?::\s*[^{;]+)?\{)"),
}
_DEF_RG = {"py": r"^\s*(async\s+)?(def|class)\s+\w+",
           "ts": r"(function\s*\*?\s*\w+|class\s+\w+|(const|let|var)\s+\w+\s*(:[^=]+)?=\s*(async\s*)?(\(|function|\w+\s*=>)|^\s*((public|private|protected|static|readonly|override|async|get|set)\s+)*\w+\s*(<[^>]*>)?\s*\([^)]*\)\s*(:\s*[^{;]+)?\{)"}
_KEYWORDS = {"if", "for", "while", "switch", "catch", "return", "function", "constructor", "else", "with"}


def _outline(ctx: Ctx, rel: str) -> tuple[str, list[tuple[int, str]]]:
    """A lexical outline of one file via ripgrep: (raw output, [(line, name)])."""
    args = ["rg", "-n", "--no-heading", "--color", "never", "-e", _DEF_RG[ctx.lang], rel]
    try:
        p = subprocess.run(args, cwd=ctx.root, capture_output=True, text=True, timeout=60,
                           encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return "", []
    out, defs = p.stdout, []
    for line in out.splitlines():
        m = re.match(r"^(\d+):(.*)$", line)
        if not m:
            continue
        mm = _DEF_LINE[ctx.lang].match(m.group(2))
        if mm:
            name = next((g for g in mm.groups() if g), None)
            if name and name not in _KEYWORDS:
                defs.append((int(m.group(1)), name))
    return out, defs


# ---------------------------------------------------------------------------------- ripgrep ----
@register
class Rg0(Adapter):
    name = "rg0"
    t1_arms = ("rg0",)
    t2_arm = "rg_def"
    t3_arm = "rg0_t3"

    def t1(self, ctx, decl):
        return [A.rg(ctx.ix, decl["name"], 0)]

    def t2(self, ctx, decl, site):
        return A.rg(ctx.ix, decl["name"], 0, pattern=A.DEF_PATTERNS[ctx.lang](decl["name"]), label="rg_def")

    def t3(self, ctx, decl, depth):
        """Breadth-first lexical search, as an agent with grep would do it: grep the name, outline each
        matched file to find the enclosing definitions, grep those names, repeat. Every grep and
        outline output is charged."""
        t = time.perf_counter()
        natives, facts, n_calls = [], [], 0
        frontier, seen_names, outlined = [decl["name"]], {decl["name"]}, {}
        for _hop in range(depth):
            nxt = []
            for name in frontier:
                r = A.rg(ctx.ix, name, 0)
                n_calls += 1
                natives.append(r.native)
                facts.extend(r.facts)
                for f, l, _c in r.facts:
                    if f not in outlined:
                        raw, defs = _outline(ctx, f)
                        n_calls += 1
                        natives.append(raw)
                        outlined[f] = defs
                    enc = [n for dl, n in outlined[f] if dl < l]
                    if enc and enc[-1] not in seen_names:
                        seen_names.add(enc[-1])
                        nxt.append(enc[-1])
            frontier = nxt
        uniq = list(dict.fromkeys(tuple(x) for x in facts))
        return ArmResult("rg0_t3", "ok" if uniq else "empty", native="\n".join(natives), facts=uniq,
                         latency_s=time.perf_counter() - t, n_calls=n_calls)


@register
class Rg3(Adapter):
    name = "rg3"
    t1_arms = ("rg3",)

    def t1(self, ctx, decl):
        return [A.rg(ctx.ix, decl["name"], 3)]


# ------------------------------------------------------------------------------ language server ----
@register
class Lsp(Adapter):
    name = "lsp"
    t1_arms = ("lsp",)
    t2_arm = "lsp_def"
    t3_arm = "lsp_t3"

    def t1(self, ctx, decl):
        return [A.lsp_refs(ctx.ix, ctx.provider, decl)]

    def t2(self, ctx, decl, site):
        return A.lsp_def(ctx.ix, ctx.provider, site, decl["name"])

    def t3(self, ctx, decl, depth):
        """References, then references of each enclosing declaration. The enclosing declaration of a
        reference is taken from the independent index — the information an LSP client gets from
        documentSymbol — and is not charged."""
        t = time.perf_counter()
        natives, facts, n_calls = [], [], 0
        frontier, seen = [decl], {decl["id"]}
        for _hop in range(depth):
            nxt = []
            for d in frontier:
                r = A.lsp_refs(ctx.ix, ctx.provider, d)
                n_calls += 1
                if r.status == "error":
                    return ArmResult("lsp_t3", "error", note=r.note, latency_s=time.perf_counter() - t, n_calls=n_calls)
                natives.append(r.native)
                facts.extend(r.facts)
                for f, l, _c in r.facts:
                    did = ctx.ix.enclosing(f, l)
                    if did in ctx.ix.decls and did not in seen:
                        seen.add(did)
                        nxt.append(ctx.ix.decls[did])
            frontier = nxt
        uniq = list(dict.fromkeys(tuple(x) for x in facts))
        return ArmResult("lsp_t3", "ok" if uniq else "empty", native="\n".join(natives), facts=uniq,
                         latency_s=time.perf_counter() - t, n_calls=n_calls)


# ------------------------------------------------------------------------------------ Codexa ----
_REF_LINE = re.compile(r"\s+\w+ from (.+?) \((.+):(\d+|\?)\)(?: \[depth (\d+)\])?$")


def _codexa_caller_facts(ix, out: str) -> list[str]:
    facts = []
    for line in out.splitlines():
        mm = _REF_LINE.match(line)
        if not mm:
            continue
        name, f, ln = mm.group(1), mm.group(2), mm.group(3)
        if name == "<module>":
            facts.append(f"module:{f}")
            continue
        did = ix.decl_at_line(f, int(ln)) if ln.isdigit() else None
        facts.append(did or f"unresolved:{name}@{f}:{ln}")
    return facts


@register
class Codexa(Adapter):
    """G1 exactly as frozen: call resolution v1 and the original find_references output."""
    name = "codexa"
    t1_arms = ("codexa_refs", "codexa_orig")
    t2_arm = "codexa_def"
    t3_arm = "codexa_t3"
    mode = "v1"

    def setup(self, ctx):
        with resolution(self.mode):
            self.cx = A.CodexaGraph(ctx.repo)
        return {"codexa_index_s": self.cx.index_s, "codexa_ok": self.cx.ok}

    def t1(self, ctx, decl):
        with resolution(self.mode):
            return [self.cx.refs(ctx.ix, decl["name"]), self.cx.orig(ctx.ix, decl["name"], decl)]

    def t2(self, ctx, decl, site):
        with resolution(self.mode):
            return self.cx.lookup(ctx.ix, decl["name"])

    def t3(self, ctx, decl, depth):
        """The frozen tool has no depth: an agent re-queries each caller by name."""
        t = time.perf_counter()
        natives, facts, n_calls = [], [], 0
        frontier, seen = [decl["name"]], {decl["name"]}
        with resolution(self.mode):
            for _hop in range(depth):
                nxt = []
                for name in frontier:
                    out = self.cx.T._find_references(name, self.cx.repo, graph=self.cx.graph)
                    n_calls += 1
                    natives.append(out)
                    for line in out.splitlines():
                        mm = _REF_LINE.match(line)
                        if mm and mm.group(1) not in seen and mm.group(1) != "<module>":
                            seen.add(mm.group(1))
                            nxt.append(mm.group(1))
                    facts.extend(_codexa_caller_facts(ctx.ix, out))
                frontier = nxt
        uniq = list(dict.fromkeys(facts))
        return ArmResult("codexa_t3", "ok" if uniq else "empty", native="\n".join(natives), facts=uniq,
                         fact_kind="caller", latency_s=time.perf_counter() - t, n_calls=n_calls)


@register
class Codexa2(Adapter):
    """G1-v2: call resolution v2 (backend/repository/resolve_v2.py) and find_references with ambiguity
    reporting and depth. Follows the same ambiguity protocol as codebase-memory: the qualified id is
    only sent after the tool itself reports ambiguity."""
    name = "codexa2"
    t1_arms = ("codexa2_refs",)
    t2_arm = "codexa2_def"
    t3_arm = "codexa2_t3"
    mode = "v2"

    def setup(self, ctx):
        with resolution(self.mode):
            self.cx = A.CodexaGraph(ctx.repo)
        return {"codexa2_index_s": self.cx.index_s, "codexa2_ok": self.cx.ok}

    def _query(self, ctx, decl, depth, arm):
        t = time.perf_counter()
        natives = []
        with resolution(self.mode):
            out = self.cx.T._find_references(decl["name"], self.cx.repo, graph=self.cx.graph, depth=depth)
            natives.append(out)
            n_calls = 1
            if out.startswith("Ambiguous:"):
                pick = None
                for line in out.splitlines()[1:]:
                    m = re.match(r"\s+(.+?#.+?) \(line (\d+|\?)\)$", line)
                    if m and m.group(1).split("#", 1)[0] == decl["file"] and m.group(2) == str(decl["line"]):
                        pick = m.group(1)
                        break
                if pick is None:
                    return ArmResult(arm, "empty", native=out, fact_kind="caller", n_calls=n_calls,
                                     latency_s=time.perf_counter() - t, note="target not among candidates")
                out = self.cx.T._find_references(pick, self.cx.repo, graph=self.cx.graph, depth=depth)
                natives.append(out)
                n_calls += 1
        facts = list(dict.fromkeys(_codexa_caller_facts(ctx.ix, out)))
        m = re.search(r"References \((\d+)\):", out)
        truncated = bool(m and int(m.group(1)) > 60)
        note = "symbol not in graph" if "No symbol named" in out else ""
        return ArmResult(arm, "ok" if facts else "empty", native="\n".join(natives), facts=facts, fact_kind="caller",
                         truncated=truncated, latency_s=time.perf_counter() - t, n_calls=n_calls, note=note)

    def t1(self, ctx, decl):
        return [self._query(ctx, decl, 1, "codexa2_refs")]

    def t2(self, ctx, decl, site):
        with resolution(self.mode):
            r = self.cx.lookup(ctx.ix, decl["name"])
        r.arm = "codexa2_def"
        return r

    def t3(self, ctx, decl, depth):
        return self._query(ctx, decl, depth, "codexa2_t3")


# --------------------------------------------------------------------------- codebase-memory ----
class _CbmBase(Adapter):
    version = ""
    binary_env = ""
    default_binary = ""

    def _binary(self) -> str:
        return os.environ.get(self.binary_env, self.default_binary)

    def available(self):
        b = self._binary()
        return (Path(b).exists(), "" if Path(b).exists() else f"binary not found: {b}")

    def setup(self, ctx):
        home = str(ctx.data_dir / f"cbmhome-{self.version}")
        Path(home).mkdir(parents=True, exist_ok=True)
        self.c = A.CBM(self._binary(), home, ctx.root, self.version)
        return {f"cbm_{self.version}_index_s": self.c.index_s, f"cbm_{self.version}_ok": self.c.ok}

    def t1(self, ctx, decl):
        return [self.c.callers(ctx.ix, decl["name"], decl)]

    def t2(self, ctx, decl, site):
        return self.c.definition(ctx.ix, decl["name"])

    def close(self):
        if hasattr(self, "c"):
            self.c.close()


@register
class CbmCur(_CbmBase):
    name = "cbm_cur"
    t1_arms = ("cbm_cur",)
    t2_arm = "cbm_cur_def"
    t3_arm = "cbm_cur_t3"
    version = "cur"
    binary_env = "NB_CBM_CUR"
    default_binary = "/work/nb/bin/cbm-cur"

    def t3(self, ctx, decl, depth):
        r = self.c.callers(ctx.ix, decl["name"], decl, depth=depth)
        r.arm = "cbm_cur_t3"
        return r


@register
class Cbm057(_CbmBase):
    name = "cbm_057"
    t1_arms = ("cbm_057",)
    t2_arm = "cbm_057_def"
    version = "057"
    binary_env = "NB_CBM_057"
    default_binary = "/work/nb/bin/cbm-057"


def describe() -> list[dict]:
    load_plugins()
    return [{"adapter": n, "t1": list(c.t1_arms), "t2": c.t2_arm, "t3": c.t3_arm} for n, c in REGISTRY.items()]


if __name__ == "__main__":
    print(json.dumps(describe(), indent=1))
