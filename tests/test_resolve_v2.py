"""Call resolution v2 (backend/repository/resolve_v2.py) and find_references v2.

Each case is one of the failure modes the NavBench study measured for the v1 resolver (shadowing,
module-level calls, aliases, module attributes, re-exports, typed receivers, super, TS `new`), plus
the guarantee that v1 stays available unchanged for reproducing frozen results.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.graph.events import InMemoryGraphEventWriter
from backend.graph.repository import InMemoryGraphRepository
from backend.graph.service import GraphService
from backend.memory.store import MemoryStore
from backend.repository import api as repo_api
from backend.repository.analyze import analyze_repo, resolution_mode

PY_CORE = '''
def target(x):
    return x + 1


def relay(x):
    return x


class Svc:
    def op(self, x):
        return x

    def caller_self(self):
        return self.op(1)


class Other:
    def op(self, x):
        return -x
'''
PY_INIT = "from .core import relay\n"
PY_USE = '''
from .core import target, Svc, Other
from .core import target as alias_call
from . import core
from pkg import relay

VALUE = target(0)


def use_direct():
    return target(1)


def use_alias():
    return alias_call(2)


def use_attr():
    return core.target(3)


def use_typed():
    s: Svc = Svc()
    return s.op(4)


def use_other():
    o = Other()
    return o.op(5)


def use_reexport():
    return relay(9)


def use_shadow():
    def target(x):
        return -x
    return target(10)


class Sub(Svc):
    def op(self, x):
        return super().op(x)
'''

TS_CORE = '''export function target(x: number): number { return x + 1; }
export function relay(x: number): number { return x; }
export class Svc { op(x: number): number { return x; } callerSelf(): number { return this.op(1); } }
export class Other { op(x: number): number { return -x; } }
'''
TS_INDEX = 'export { relay } from "./core";\n'
TS_USE = '''import { target, Svc, Other } from "./core";
import { target as aliasCall } from "./core";
import * as core from "./core";
import { relay } from "./index";
export const VALUE = target(0);
export function useDirect(): number { return target(1); }
export function useAlias(): number { return aliasCall(2); }
export function useNs(): number { return core.target(3); }
export function useTyped(): number { const s: Svc = new Svc(); return s.op(4); }
export function useOther(): number { const o = new Other(); return o.op(5); }
export function useReexport(): number { return relay(9); }
export function useShadow(): number { function target(x: number): number { return -x; } return target(10); }
export class Sub extends Svc { op(x: number): number { return super.op(x); } }
'''


def _write(root: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return root


def _callers(root: Path, mode: str, monkeypatch) -> dict[str, set[str]]:
    monkeypatch.setenv("CODEXA_CALL_RESOLUTION", mode)
    out: dict[str, set[str]] = {}
    for fr, to in analyze_repo(root).calls:
        out.setdefault(to, set()).add(fr)
    return out


@pytest.fixture()
def py_repo(tmp_path):
    return _write(tmp_path / "pyrepo", {"pkg/__init__.py": PY_INIT, "pkg/core.py": PY_CORE, "pkg/use.py": PY_USE})


@pytest.fixture()
def ts_repo(tmp_path):
    return _write(tmp_path / "tsrepo", {"src/core.ts": TS_CORE, "src/index.ts": TS_INDEX, "src/use.ts": TS_USE})


class TestMode:
    def test_default_is_v2_and_v1_selectable(self, monkeypatch):
        monkeypatch.delenv("CODEXA_CALL_RESOLUTION", raising=False)
        assert resolution_mode() == "v2"
        monkeypatch.setenv("CODEXA_CALL_RESOLUTION", "v1")
        assert resolution_mode() == "v1"
        monkeypatch.setenv("CODEXA_CALL_RESOLUTION", "nonsense")
        assert resolution_mode() == "v2"

    def test_symbols_and_imports_identical_across_modes(self, py_repo, monkeypatch):
        monkeypatch.setenv("CODEXA_CALL_RESOLUTION", "v1")
        a1 = analyze_repo(py_repo)
        monkeypatch.setenv("CODEXA_CALL_RESOLUTION", "v2")
        a2 = analyze_repo(py_repo)
        real2 = [s for s in a2.symbols if s.kind != "module"]
        assert [(s.file, s.qualname or s.name, s.line) for s in a1.symbols] == \
               [(s.file, s.qualname or s.name, s.line) for s in real2]
        assert a1.imports == a2.imports


class TestPythonV2:
    def test_target_callers_complete_and_shadow_excluded(self, py_repo, monkeypatch):
        c = _callers(py_repo, "v2", monkeypatch)
        assert c["pkg/core.py#target"] == {
            "pkg/use.py#<module>", "pkg/use.py#use_direct", "pkg/use.py#use_alias", "pkg/use.py#use_attr"}
        assert c["pkg/use.py#target"] == {"pkg/use.py#use_shadow"}  # the local helper, not core.target

    def test_receivers_super_reexport_constructor(self, py_repo, monkeypatch):
        c = _callers(py_repo, "v2", monkeypatch)
        assert c["pkg/core.py#Svc.op"] == {"pkg/core.py#Svc.caller_self", "pkg/use.py#use_typed", "pkg/use.py#Sub.op"}
        assert c["pkg/core.py#Other.op"] == {"pkg/use.py#use_other"}
        assert c["pkg/core.py#relay"] == {"pkg/use.py#use_reexport"}
        assert "pkg/use.py#use_typed" in c["pkg/core.py#Svc"]

    def test_v1_reproduces_the_measured_gaps(self, py_repo, monkeypatch):
        c = _callers(py_repo, "v1", monkeypatch)
        got = c.get("pkg/core.py#target", set())
        assert "pkg/use.py#<module>" not in got          # module-level calls dropped
        assert "pkg/use.py#use_alias" not in got         # alias not followed
        assert "pkg/use.py#use_direct" not in got        # shadowed by the same-file nested def

    def test_module_pseudo_symbols_not_in_digest(self, py_repo, monkeypatch):
        monkeypatch.setenv("CODEXA_CALL_RESOLUTION", "v2")
        code = analyze_repo(py_repo)
        assert any(s.kind == "module" for s in code.symbols)
        assert "<module>" not in repo_api._functions_summary(code)


class TestTypeScriptV2:
    def test_ts_relations(self, ts_repo, monkeypatch):
        c = _callers(ts_repo, "v2", monkeypatch)
        assert c["src/core.ts#target"] == {
            "src/use.ts#<module>", "src/use.ts#useDirect", "src/use.ts#useAlias", "src/use.ts#useNs"}
        assert c["src/core.ts#Svc.op"] == {"src/core.ts#Svc.callerSelf", "src/use.ts#useTyped", "src/use.ts#Sub.op"}
        assert c["src/core.ts#relay"] == {"src/use.ts#useReexport"}
        assert "src/use.ts#useTyped" in c["src/core.ts#Svc"]      # new Svc()
        assert c["src/use.ts#target"] == {"src/use.ts#useShadow"}


class TestFindReferencesV2:
    @pytest.fixture()
    def graph(self, tmp_path, py_repo, monkeypatch):
        monkeypatch.setenv("CODEXA_CALL_RESOLUTION", "v2")
        g = GraphService(repository=InMemoryGraphRepository(), event_writer=InMemoryGraphEventWriter())
        repo_api._ingest("pyrepo", "", py_repo, False, store=MemoryStore(path=tmp_path / "m.json"), graph=g)
        return g

    def test_ambiguity_then_qualified_query(self, graph):
        from backend.agents.tools import _find_references

        out = _find_references("target", "pyrepo", graph=graph)
        assert out.startswith("Ambiguous: 2 symbols named 'target'")
        assert "pkg/core.py#target" in out and "pkg/use.py#target" in out
        out = _find_references("pkg/core.py#target", "pyrepo", graph=graph)
        assert "calls from use_direct" in out and "calls from <module> (pkg/use.py:1)" in out
        assert "use_shadow" not in out

    def test_depth_two_reaches_callers_of_callers(self, graph):
        from backend.agents.tools import _find_references

        out = _find_references("Svc.op", "pyrepo", graph=graph, depth=2)
        assert "calls from Svc.caller_self" in out and "[depth 1]" in out
        one = _find_references("Svc.op", "pyrepo", graph=graph, depth=1)
        assert "[depth" not in one

    def test_v1_output_unchanged(self, graph, monkeypatch):
        from backend.agents.tools import _find_references

        monkeypatch.setenv("CODEXA_CALL_RESOLUTION", "v1")
        out = _find_references("target", "pyrepo", graph=graph)
        assert not out.startswith("Ambiguous")
        assert out.startswith("Definition:")
