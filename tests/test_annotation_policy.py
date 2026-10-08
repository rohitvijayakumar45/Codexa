"""Budgeted symbol-annotation selection policies (backend/repository/annotation_policy.py) and
their wiring into the annotation pass (backend/repository/semantic.py) and lookup_symbol's lazy
on-demand path."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from backend.memory.store import MemoryStore
from backend.repository import semantic
from backend.repository.analyze import Symbol, analyze_repo
from backend.repository.annotation_policy import (
    POLICIES,
    configured_budget,
    configured_policy,
    mine_file_churn,
    pagerank,
    rank_symbols,
    select_symbols,
)


def _sym(name: str, file: str = "lib/a.py", kind: str = "function", qualname: str = "", h: str = "h") -> Symbol:
    return Symbol(name=name, kind=kind, file=file, line=1, end_line=2, content_hash=h, qualname=qualname)


def _graph():
    syms = [_sym("leaf"), _sym("mid"), _sym("root"), _sym("_private"), _sym("test_x", file="tests/test_a.py"),
            _sym("Klass", kind="class", file="lib/b.py")]
    calls = [("lib/a.py#root", "lib/a.py#mid"), ("lib/a.py#mid", "lib/a.py#leaf"),
             ("lib/b.py#Klass", "lib/a.py#leaf"), ("tests/test_a.py#test_x", "lib/a.py#root")]
    return syms, calls


class FakeLLM:
    default_model = "fake/model"

    def __init__(self) -> None:
        self.calls = 0

    def models_for_task(self, task: str) -> list[str]:
        return [self.default_model]

    def complete(self, messages, model, agent):  # noqa: ANN001
        self.calls += 1
        return f"meaning #{self.calls}"


class TestRanking:
    @pytest.mark.parametrize("policy", [p for p in POLICIES if p != "lazy"])
    def test_every_eager_policy_is_a_permutation(self, policy):
        syms, calls = _graph()
        ranked = rank_symbols(syms, calls, policy)
        assert sorted(id(s) for s in ranked) == sorted(id(s) for s in syms)

    def test_lazy_annotates_nothing_eagerly(self):
        syms, calls = _graph()
        assert rank_symbols(syms, calls, "lazy") == []
        assert select_symbols(syms, calls, "lazy", 80) == []

    def test_unknown_policy_rejected(self):
        with pytest.raises(ValueError):
            rank_symbols([], [], "vibes")

    def test_callers_policy_is_the_production_priority(self):
        syms, calls = _graph()
        assert [s.name for s in rank_symbols(syms, calls, "callers")] == [s.name for s in semantic._priority(syms, calls)]
        order = [s.name for s in rank_symbols(syms, calls, "callers")]
        assert order.index("test_x") > order.index("_private") > order.index("leaf")

    def test_callers_exact_does_not_pool_same_named_symbols(self):
        a, b = _sym("send", file="lib/a.py"), _sym("send", file="lib/b.py")
        calls = [("x#f", "lib/b.py#send"), ("x#g", "lib/b.py#send")]
        assert [s.file for s in rank_symbols([a, b], calls, "callers_exact")] == ["lib/b.py", "lib/a.py"]

    def test_pagerank_flows_to_callees(self):
        syms, calls = _graph()
        assert rank_symbols(syms, calls, "pagerank")[0].name == "leaf"
        pr = pagerank(["a", "b", "c"], [("a", "b"), ("b", "c")])
        assert abs(sum(pr.values()) - 1.0) < 1e-6 and pr["c"] > pr["b"] > pr["a"]
        assert pagerank([], []) == {}

    def test_degree(self):
        syms, calls = _graph()
        top = rank_symbols(syms, calls, "degree")[:2]
        assert {s.name for s in top} <= {"leaf", "root", "mid"}

    def test_random_is_seeded(self):
        syms = [_sym(f"f{i}") for i in range(30)]
        a = [s.name for s in rank_symbols(syms, [], "random", seed=1)]
        assert a == [s.name for s in rank_symbols(syms, [], "random", seed=1)]
        assert a != [s.name for s in rank_symbols(syms, [], "random", seed=2)]
        assert [s.name for s in syms] == [f"f{i}" for i in range(30)]  # input not shuffled in place

    def test_git_churn_ranks_hot_files_first_and_falls_back_to_callers(self):
        syms, calls = _graph()
        ranked = rank_symbols(syms, calls, "git_churn", file_churn={"lib/b.py": 9})
        assert ranked[0].name == "Klass"
        assert [s.name for s in rank_symbols(syms, calls, "git_churn")] == [s.name for s in rank_symbols(syms, calls, "callers")]

    def test_select_is_a_prefix_of_the_ranking(self):
        syms, calls = _graph()
        assert select_symbols(syms, calls, "pagerank", 2) == rank_symbols(syms, calls, "pagerank")[:2]
        assert select_symbols(syms, calls, "pagerank", 0) == []


class TestConfiguration:
    def test_env_defaults_and_fallbacks(self, monkeypatch):
        monkeypatch.delenv("CODEXA_ANNOTATE_POLICY", raising=False)
        monkeypatch.delenv("CODEXA_ANNOTATE_BUDGET", raising=False)
        assert configured_policy() == "callers" and configured_budget() == 80
        monkeypatch.setenv("CODEXA_ANNOTATE_POLICY", "PageRank")
        monkeypatch.setenv("CODEXA_ANNOTATE_BUDGET", "12")
        assert configured_policy() == "pagerank" and configured_budget() == 12
        monkeypatch.setenv("CODEXA_ANNOTATE_POLICY", "nonsense")
        monkeypatch.setenv("CODEXA_ANNOTATE_BUDGET", "lots")
        assert configured_policy() == "callers" and configured_budget() == 80


def _src_repo(root: Path) -> None:
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "m.py").write_text(
        "def a():\n    return b()\n\n\ndef b():\n    return c()\n\n\ndef c():\n    return 1\n", encoding="utf-8")


class TestAnnotationPass:
    def test_budget_caps_fresh_llm_calls(self, tmp_path):
        _src_repo(tmp_path / "r")
        code = analyze_repo(tmp_path / "r")
        store, llm = MemoryStore(path=tmp_path / "m.json"), FakeLLM()
        stats = semantic.annotate_repository_symbols("r", tmp_path / "r", code.symbols, store=store, llm=llm,
                                                     calls=code.calls, policy="pagerank", budget=2)
        assert stats["annotated"] == 2 and llm.calls == 2 and stats["skipped"] == 1
        blob = semantic._load_blob(store, "r")
        assert "symbol://r/pkg/m.py#c" in blob  # pagerank: the most-called-into symbol goes first

    def test_lazy_pass_makes_no_calls_but_keeps_current_meanings(self, tmp_path):
        _src_repo(tmp_path / "r")
        code = analyze_repo(tmp_path / "r")
        store = MemoryStore(path=tmp_path / "m.json")
        semantic.annotate_repository_symbols("r", tmp_path / "r", code.symbols, store=store, llm=FakeLLM(),
                                             calls=code.calls, policy="callers", budget=1)
        llm = FakeLLM()
        stats = semantic.annotate_repository_symbols("r", tmp_path / "r", code.symbols, store=store, llm=llm,
                                                     calls=code.calls, policy="lazy", budget=80)
        assert llm.calls == 0 and stats["reused"] == 1
        assert len(semantic._load_blob(store, "r")) == 1

    def test_env_policy_is_used_when_not_passed(self, tmp_path, monkeypatch):
        _src_repo(tmp_path / "r")
        code = analyze_repo(tmp_path / "r")
        monkeypatch.setenv("CODEXA_ANNOTATE_BUDGET", "1")
        llm = FakeLLM()
        semantic.annotate_repository_symbols("r", tmp_path / "r", code.symbols,
                                             store=MemoryStore(path=tmp_path / "m.json"), llm=llm, calls=code.calls)
        assert llm.calls == 1


class TestOnDemand:
    def test_annotates_once_then_reuses_until_code_changes(self, tmp_path):
        _src_repo(tmp_path / "r")
        store, llm = MemoryStore(path=tmp_path / "m.json"), FakeLLM()
        c = next(s for s in analyze_repo(tmp_path / "r").symbols if s.name == "c")
        kwargs = dict(file=c.file, qualname="c", kind=c.kind, line=c.line, end_line=c.end_line, store=store, llm=llm)
        assert semantic.annotate_on_demand("r", tmp_path / "r", content_hash=c.content_hash, **kwargs) == "meaning #1"
        assert semantic.annotate_on_demand("r", tmp_path / "r", content_hash=c.content_hash, **kwargs) == "meaning #1"
        assert llm.calls == 1
        assert semantic.annotate_on_demand("r", tmp_path / "r", content_hash="changed", **kwargs) == "meaning #2"

    def test_lookup_symbol_lazy_path(self, tmp_path, monkeypatch):
        from backend.agents import tools
        from backend.graph.events import InMemoryGraphEventWriter
        from backend.graph.repository import InMemoryGraphRepository
        from backend.graph.service import GraphService
        from backend.repository import api as repo_api

        repo = tmp_path / "r"
        _src_repo(repo)
        graph = GraphService(repository=InMemoryGraphRepository(), event_writer=InMemoryGraphEventWriter())
        store, llm = MemoryStore(path=tmp_path / "m.json"), FakeLLM()
        repo_api._ingest("r", "", repo, False, store=store, graph=graph)
        monkeypatch.setattr(tools, "repo_root", lambda name: repo)

        monkeypatch.setenv("CODEXA_ANNOTATE_POLICY", "callers")
        assert "what it does" not in tools._lookup_symbol("c", "r", graph=graph, store=store, llm=llm)
        monkeypatch.setenv("CODEXA_ANNOTATE_POLICY", "lazy")
        assert "what it does: meaning #1" in tools._lookup_symbol("c", "r", graph=graph, store=store, llm=llm)
        assert "what it does: meaning #1" in tools._lookup_symbol("c", "r", graph=graph, store=store, llm=llm)
        assert llm.calls == 1  # cached under the node's content hash

    def test_lookup_symbol_never_serves_a_meaning_for_changed_code(self, tmp_path):
        from backend.agents import tools
        from backend.graph.events import InMemoryGraphEventWriter
        from backend.graph.repository import InMemoryGraphRepository
        from backend.graph.service import GraphService
        from backend.repository import api as repo_api

        repo = tmp_path / "r"
        _src_repo(repo)
        graph = GraphService(repository=InMemoryGraphRepository(), event_writer=InMemoryGraphEventWriter())
        store = MemoryStore(path=tmp_path / "m.json")
        repo_api._ingest("r", "", repo, False, store=store, graph=graph)
        semantic._save_blob(store, "r", {"symbol://r/pkg/m.py#c": {"hash": "stale-hash", "summary": "old meaning"}})
        assert "old meaning" not in tools._lookup_symbol("c", "r", graph=graph, store=store)


@pytest.mark.skipif(shutil.which("git") is None, reason="requires git on PATH")
def test_mine_file_churn(tmp_path):
    def git(*args):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=tmp_path,
                       check=True, capture_output=True)

    git("init", "-q")
    for i in range(3):
        (tmp_path / "hot.py").write_text(f"x = {i}\n", encoding="utf-8")
        if i == 0:
            (tmp_path / "cold.py").write_text("y = 0\n", encoding="utf-8")
        git("add", "-A")
        git("commit", "-q", "-m", f"c{i}")
    churn = mine_file_churn(tmp_path)
    assert churn == {"hot.py": 3, "cold.py": 1}
    assert mine_file_churn(tmp_path, last_commits=1) == {"hot.py": 1}
    assert mine_file_churn(tmp_path / "not-a-repo") == {}
