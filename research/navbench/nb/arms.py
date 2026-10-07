"""Retrieval arms. Each returns an ArmResult with the native output text and the facts it conveys.

fact_kind == "loc":    facts are (file, line, col) locations the tool returned
fact_kind == "caller": facts are caller declaration ids resolved from the tool's own output
                       ("unresolved:<text>" when the tool named something the index cannot map)
"""
from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from nb.index import Index, resolve_dotted

GLOBS = {"py": ["*.py"], "ts": ["*.ts", "*.tsx", "*.js", "*.jsx", "*.mjs", "*.cjs", "*.mts", "*.cts"]}


@dataclass
class ArmResult:
    arm: str
    status: str                     # ok | empty | error | timeout | unsupported
    native: str = ""
    facts: list = field(default_factory=list)
    fact_kind: str = "loc"
    truncated: bool = False
    latency_s: float = 0.0
    n_calls: int = 1
    note: str = ""


def _ident_re(name: str) -> re.Pattern:
    return re.compile(r"(?<![\w$])" + re.escape(name) + r"(?![\w$])")


# ------------------------------------------------------------------ ripgrep
def rg(ix: Index, name: str, context: int = 0, pattern: str | None = None, label: str | None = None) -> ArmResult:
    arm = label or f"rg{context}"
    args = ["rg", "-n", "--column", "--no-heading", "--color", "never"]
    if pattern is None:
        args += ["-w", "-F", name]
    else:
        args += ["-e", pattern]
    if context:
        args += ["-C", str(context)]
    for g in GLOBS[ix.lang]:
        args += ["-g", g]
    t = time.perf_counter()
    try:
        p = subprocess.run(args + ["."], cwd=ix.root, capture_output=True, text=True, timeout=60,
                           encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return ArmResult(arm, "timeout", latency_s=time.perf_counter() - t)
    lat = time.perf_counter() - t
    if p.returncode not in (0, 1):
        return ArmResult(arm, "error", note=p.stderr[:300], latency_s=lat)
    out = p.stdout
    facts = []
    rx = _ident_re(name)
    for line in out.splitlines():
        m = re.match(r"^(.*?):(\d+):(\d+):(.*)$", line)  # match lines; context lines use '-' separators
        if not m:
            continue
        f, ln, text = m.group(1), int(m.group(2)), m.group(4)
        f = f[2:] if f.startswith("./") else f
        for mm in rx.finditer(text):
            facts.append((f, ln, mm.start()))
    return ArmResult(arm, "ok" if facts else "empty", native=out, facts=facts, latency_s=lat)


DEF_PATTERNS = {
    "py": lambda n: rf"^\s*(async\s+)?(def|class)\s+{re.escape(n)}\b",
    "ts": lambda n: (rf"(function\s*\*?\s*{re.escape(n)}\b|class\s+{re.escape(n)}\b|"
                     rf"\b(const|let|var)\s+{re.escape(n)}\s*[:=]|^\s*(public\s+|private\s+|protected\s+|static\s+|async\s+|readonly\s+)*{re.escape(n)}\s*(<[^>]*>)?\s*\(|"
                     rf"^\s*(public\s+|private\s+|protected\s+|static\s+|readonly\s+)*{re.escape(n)}\s*=\s*(async\s*)?(\(|function))"),
}


# ------------------------------------------------------------------ language servers
def lsp_refs(ix: Index, client, decl: dict) -> ArmResult:
    t = time.perf_counter()
    try:
        locs = client.references(decl["file"], decl["line"], decl["col"])
    except Exception as e:  # noqa: BLE001
        return ArmResult("lsp", "error", note=str(e)[:300], latency_s=time.perf_counter() - t)
    lat = time.perf_counter() - t
    native = json.dumps([{"uri": "file://" + str(ix.root / f), "range": {"start": {"line": l - 1, "character": c},
                                                                         "end": {"line": l - 1, "character": c + len(decl["name"])}}}
                         for f, l, c in locs])
    return ArmResult("lsp", "ok" if locs else "empty", native=native, facts=[tuple(x) for x in locs], latency_s=lat)


def lsp_def(ix: Index, client, site: tuple[str, int, int], name: str) -> ArmResult:
    t = time.perf_counter()
    try:
        locs = client.definition(*site)
    except Exception as e:  # noqa: BLE001
        return ArmResult("lsp_def", "error", note=str(e)[:300], latency_s=time.perf_counter() - t)
    lat = time.perf_counter() - t
    native = json.dumps([{"uri": "file://" + str(ix.root / f), "range": {"start": {"line": l - 1, "character": c},
                                                                         "end": {"line": l - 1, "character": c + len(name)}}}
                         for f, l, c in locs])
    return ArmResult("lsp_def", "ok" if locs else "empty", native=native, facts=[tuple(x) for x in locs], latency_s=lat)


# ------------------------------------------------------------------ Codexa graph
class CodexaGraph:
    def __init__(self, repo_name: str):
        from backend.graph.events import InMemoryGraphEventWriter
        from backend.graph.repository import InMemoryGraphRepository
        from backend.graph.service import GraphService
        from backend.memory.store import MemoryStore
        from backend.repository.api import reindex_repository
        import backend.agents.tools as T
        self.T = T
        self.repo = repo_name
        self.graph = GraphService(repository=InMemoryGraphRepository(), event_writer=InMemoryGraphEventWriter())
        self.store = MemoryStore()
        t = time.perf_counter()
        info = reindex_repository(repo_name, store=self.store, graph=self.graph, llm=None)
        self.index_s = time.perf_counter() - t
        self.ok = info is not None

    def refs(self, ix: Index, name: str) -> ArmResult:
        t = time.perf_counter()
        try:
            out = self.T._find_references(name, self.repo, graph=self.graph)
        except Exception as e:  # noqa: BLE001
            return ArmResult("codexa_refs", "error", note=str(e)[:300], latency_s=time.perf_counter() - t)
        lat = time.perf_counter() - t
        facts, truncated = [], False
        m = re.search(r"References \((\d+)\):", out)
        if m and int(m.group(1)) > 30:
            truncated = True
        for line in out.splitlines():
            mm = re.match(r"\s+\w+ from (.+?) \((.+):(\d+|\?)\)$", line)
            if not mm:
                continue
            f, ln = mm.group(2), mm.group(3)
            did = ix.decl_at_line(f, int(ln)) if ln.isdigit() else None
            facts.append(did or f"unresolved:{mm.group(1)}@{f}:{ln}")
        status = "ok" if facts else ("empty" if "No symbol named" not in out else "empty")
        return ArmResult("codexa_refs", status, native=out, facts=facts, fact_kind="caller", truncated=truncated,
                         latency_s=lat, note="symbol not in graph" if "No symbol named" in out else "")

    def orig(self, ix: Index, name: str, decl: dict) -> ArmResult:
        """The original benchmark's pair: lookup_symbol + get_dependencies (callers from the target's block)."""
        t = time.perf_counter()
        try:
            a = self.T._lookup_symbol(name, self.repo, graph=self.graph, store=self.store)
            b = self.T._get_dependencies(name, self.repo, graph=self.graph)
        except Exception as e:  # noqa: BLE001
            return ArmResult("codexa_orig", "error", note=str(e)[:300], latency_s=time.perf_counter() - t, n_calls=2)
        lat = time.perf_counter() - t
        facts, truncated, in_block = [], False, False
        for line in a.splitlines():
            hm = re.match(r"^\S+ `(.+)` — (.+):(\d+|None)$", line)
            if hm:
                in_block = hm.group(2) == decl["file"] and hm.group(3) == str(decl["line"])
                continue
            if in_block and line.strip().startswith("called by:"):
                names = [x.strip() for x in line.split(":", 1)[1].split(",") if x.strip()]
                truncated = truncated or len(names) >= 10
                for q in names:
                    cands = sorted({ix.canon(d["id"]) for d in ix.decls.values() if d["qualname"] == q})
                    if not cands:  # Codexa labels nested functions by bare name
                        cands = sorted({ix.canon(d["id"]) for d in ix.decls.values()
                                        if d["qualname"].endswith("." + q) or d["name"] == q})
                    facts.extend(cands if cands else [f"unresolved:{q}"])
        return ArmResult("codexa_orig", "ok" if facts else "empty", native=a + "\n" + b, facts=facts,
                         fact_kind="caller", truncated=truncated, latency_s=lat, n_calls=2)

    def lookup(self, ix: Index, name: str) -> ArmResult:
        t = time.perf_counter()
        out = self.T._lookup_symbol(name, self.repo, graph=self.graph, store=self.store)
        lat = time.perf_counter() - t
        facts = []
        for line in out.splitlines():
            hm = re.match(r"^\S+ `(.+)` — (.+):(\d+)$", line)
            if hm:
                facts.append((hm.group(2), int(hm.group(3)), 0))
        return ArmResult("codexa_def", "ok" if facts else "empty", native=out, facts=facts, latency_s=lat)


# ------------------------------------------------------------------ codebase-memory-mcp
class CBM:
    """codebase-memory-mcp queried through a persistent MCP stdio session (as an agent would use it).
    Indexing uses the CLI once per repository (timed separately)."""

    def __init__(self, binary: str, home: str, root: Path, version: str):
        from nb.mcp import McpClient
        self.bin, self.home, self.root, self.version = binary, home, root, version
        self.project = str(root).strip("/").replace("/", "-")
        self.env = {"HOME": home, "PATH": "/usr/bin:/bin"}
        import glob as _glob
        import shutil as _shutil
        for old in _glob.glob(f"{home}/.cache/codebase-memory-mcp/{self.project}*"):  # cold index every run
            (_shutil.rmtree if Path(old).is_dir() else Path(old).unlink)(old)
        t = time.perf_counter()
        if version == "cur":
            r = self._run(["cli", "--quiet", "index_repository", "--repo-path", str(root)], timeout=3600)
        else:
            r = self._run(["cli", "index_repository", json.dumps({"repo_path": str(root)})], timeout=3600)
        self.index_s = time.perf_counter() - t
        self.ok = r is not None and r.returncode == 0
        self.mcp = McpClient([binary], self.env)

    def _run(self, args, timeout=120):
        try:
            return subprocess.run([self.bin] + args, capture_output=True, text=True, timeout=timeout,
                                  env=self.env, encoding="utf-8", errors="replace")
        except subprocess.TimeoutExpired:
            return None

    def close(self):
        self.mcp.close()

    def _call(self, tool, args):
        try:
            return self.mcp.call(tool, args, timeout=300)
        except Exception as e:  # noqa: BLE001
            return f"__error__ {e}", True

    def callers(self, ix: Index, name: str, decl: dict) -> ArmResult:
        arm = f"cbm_{self.version}"
        t = time.perf_counter()
        natives, n_calls = [], 0
        if self.version == "cur":
            base = {"project": self.project, "direction": "inbound", "depth": 1, "include_tests": True}
            txt, err = self._call("trace_path", dict(base, function_name=name)); n_calls += 1
            if txt.startswith("__error__"):
                return ArmResult(arm, "error", note=txt[:200], latency_s=time.perf_counter() - t)
            natives.append(txt)
            target_fn = name
            if '"status":"ambiguous"' in txt:
                try:
                    sug = json.loads(txt).get("suggestions", [])
                except json.JSONDecodeError:
                    sug = []
                same_file = [x for x in sug if x.get("file_path") == decl["file"]]
                want = [x["qualified_name"] for x in same_file if x["qualified_name"].endswith("." + decl["qualname"])]
                if not want:  # nested declarations are named module.<name> by this tool
                    want = [x["qualified_name"] for x in same_file if x["qualified_name"].endswith("." + decl["name"])]
                if not want:
                    return ArmResult(arm, "empty", native="\n".join(natives), fact_kind="caller",
                                     latency_s=time.perf_counter() - t, n_calls=n_calls, note="target not among suggestions")
                target_fn = want[0]
                txt, err = self._call("trace_path", dict(base, function_name=target_fn)); n_calls += 1
                natives.append(txt)
            lat = time.perf_counter() - t
            js, _ = self._call("trace_path", dict(base, function_name=target_fn, format="json"))  # facts only
            facts, truncated = [], False
            try:
                d = json.loads(js)
                if "error" in d:
                    return ArmResult(arm, "empty", native="\n".join(natives), fact_kind="caller", latency_s=lat,
                                     n_calls=n_calls, note=str(d.get("error"))[:120])
                cal = d.get("callers") if isinstance(d.get("callers"), dict) else {}
                cols = cal.get("cols", [])
                ni = cols.index("name") if "name" in cols else 0
                for g in cal.get("groups", []):
                    pre = g.get("qn_prefix", "")
                    for row in g.get("rows", []):
                        facts.append(self._resolve(ix, (pre + "." + row[ni]) if pre else row[ni]))
                tot = d.get("callers_total")
                truncated = bool(d.get("next_cursor") or d.get("next") or (tot is not None and tot > len(facts)))
            except (json.JSONDecodeError, ValueError, TypeError, AttributeError) as e:
                return ArmResult(arm, "error", native="\n".join(natives), note=f"parse: {e}"[:200], latency_s=lat,
                                 n_calls=n_calls)
        else:
            txt, err = self._call("trace_call_path", {"function_name": name, "project": self.project,
                                                      "direction": "inbound", "depth": 1}); n_calls += 1
            lat = time.perf_counter() - t
            if txt.startswith("__error__"):
                return ArmResult(arm, "error", note=txt[:200], latency_s=lat)
            natives.append(txt)
            facts, truncated = [], False
            try:
                d = json.loads(txt)
                if "error" in d:
                    return ArmResult(arm, "empty", native=txt, fact_kind="caller", latency_s=lat,
                                     note=str(d.get("error"))[:120])
                for c in d.get("callers", []):
                    facts.append(self._resolve(ix, c["qualified_name"]))
            except (json.JSONDecodeError, ValueError, TypeError) as e:
                return ArmResult(arm, "error", native=txt, note=f"parse: {e}"[:200], latency_s=lat)
        return ArmResult(arm, "ok" if facts else "empty", native="\n".join(natives), facts=facts, fact_kind="caller",
                         truncated=truncated, latency_s=lat, n_calls=n_calls)

    def _resolve(self, ix: Index, qn: str) -> str:
        q = qn[len(self.project) + 1:] if qn.startswith(self.project + ".") else qn
        if q.endswith(".__file__"):
            q = q[: -len(".__file__")]
        for ext in (".py", ".tsx", ".ts", ".jsx", ".mjs", ".cjs", ".js"):
            if q.endswith(ext):
                q = q[: -len(ext)]
                break
        did = resolve_dotted(ix, q)
        return did or f"unresolved:{q}"

    def definition(self, ix: Index, name: str) -> ArmResult:
        arm = f"cbm_{self.version}_def"
        t = time.perf_counter()
        txt, err = self._call("search_graph", {"project": self.project, "name_pattern": f"^{re.escape(name)}$"})
        lat = time.perf_counter() - t
        if txt.startswith("__error__"):
            return ArmResult(arm, "error", note=txt[:200], latency_s=lat)
        facts = []
        if self.version == "cur":
            for line in txt.splitlines():
                m = re.match(r"^\s+\S+\s+\w+\s+(\S+)\s+(\d+)-\d+", line)
                if m:
                    facts.append((m.group(1), int(m.group(2)), 0))
        else:
            try:
                for x in json.loads(txt).get("results", []):
                    did = self._resolve(ix, x["qualified_name"])
                    if did in ix.decls:
                        d = ix.decls[did]
                        facts.append((d["file"], d["line"], 0))
                    else:
                        facts.append((x.get("file_path", "?"), 0, 0))
            except (json.JSONDecodeError, AttributeError):
                pass
        return ArmResult(arm, "ok" if facts else "empty", native=txt, facts=facts, latency_s=lat)
