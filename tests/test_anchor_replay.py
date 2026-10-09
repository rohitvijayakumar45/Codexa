"""The git-history replay benchmark (tests/benchmarks/memory_anchoring) on a synthetic repository
whose every commit is a known, labelled change — so each policy's expected hit/miss is exact — plus
graph-query anchors (backend/memory/anchors.py `query_anchor`)."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from backend.memory.anchors import check_anchors, query_anchor, query_result
from backend.repository.analyze import analyze_repo

sys.path.insert(0, str(Path(__file__).resolve().parent / "benchmarks" / "memory_anchoring"))

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="requires git on PATH")

A0 = "def f(x):\n    return x + 1\n\n\ndef g():\n    return f(1)\n"
B0 = "from a import f\n\n\ndef h():\n    return 0\n"
COMMITS = [
    # c0: baseline
    {"a.py": A0, "b.py": B0, "package.json": '{"scripts": {"dev": "vite"}}'},
    # c1: f's BODY changes, signature does not -> F1 not stale, but symbol/file anchors fire
    {"a.py": A0.replace("x + 1", "x + 2")},
    # c2: h (in b.py, which already imports a.py) starts calling f -> callers(f) grows
    {"b.py": B0.replace("return 0", "return f(2)")},
    # c3: f's SIGNATURE changes -> F1 stale
    {"a.py": A0.replace("x + 1", "x + 2").replace("def f(x)", "def f(x, y=0)")},
    # c4: README only -> nothing about the code is stale
    {"README.md": "# demo\n"},
]


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=root, check=True,
                   capture_output=True)


@pytest.fixture()
def synthetic_repo(tmp_path) -> Path:
    root = tmp_path / "synthetic"
    root.mkdir()
    _git(root, "init", "-q")
    for i, files in enumerate(COMMITS):
        for rel, text in files.items():
            (root / rel).write_text(text, encoding="utf-8")
        _git(root, "add", "-A")
        _git(root, "commit", "-q", "-m", f"c{i}")
    return root


class TestQueryAnchors:
    def test_query_results_and_existence(self, tmp_path):
        (tmp_path / "a.py").write_text(A0, encoding="utf-8")
        code = analyze_repo(tmp_path)
        assert query_result(code, "callers", "a.py#f") == ["a.py#g"]
        assert query_result(code, "callees", "a.py#g") == ["a.py#f"]
        assert query_result(code, "callers", "a.py#g") == []
        assert query_result(code, "callers", "a.py#nope") == ["<subject does not exist>"]
        with pytest.raises(ValueError):
            query_result(code, "vibes", "a.py#f")

    def test_query_anchor_ignores_irrelevant_edits_but_catches_answer_changes(self, tmp_path):
        (tmp_path / "a.py").write_text(A0, encoding="utf-8")
        anchor = [query_anchor(analyze_repo(tmp_path), "callers", "a.py#f")]
        (tmp_path / "a.py").write_text(A0.replace("x + 1", "x * 3"), encoding="utf-8")
        assert check_anchors(tmp_path, anchor).status == "valid"  # f's body changed, its callers did not
        (tmp_path / "a.py").write_text(A0 + "\n\ndef k():\n    return f(0)\n", encoding="utf-8")
        assert check_anchors(tmp_path, anchor).status == "stale"

    def test_deleting_an_uncalled_symbol_is_stale(self, tmp_path):
        (tmp_path / "a.py").write_text(A0, encoding="utf-8")
        anchor = [query_anchor(analyze_repo(tmp_path), "callers", "a.py#g")]  # g has no callers
        (tmp_path / "a.py").write_text("def f(x):\n    return x\n", encoding="utf-8")
        assert check_anchors(tmp_path, anchor).status == "stale"


class TestReplay:
    def _run(self, repo: Path):
        from replay import run_replay

        return run_replay(repo, ks=[1], pairs_per_k=100, max_facts=1000, ttls=[2], log=lambda _m: None)

    def _cell(self, result, fact: str, policy: str):
        return result.cells[(1, fact, policy)]

    def test_rejects_a_directory_that_is_not_a_repository_root(self, synthetic_repo):
        from replay import run_replay

        sub = synthetic_repo / "sub"
        sub.mkdir()
        with pytest.raises(ValueError, match="not a git repository root"):
            run_replay(sub, ks=[1], pairs_per_k=1, max_facts=1, ttls=[], log=lambda _m: None)

    def test_labelled_history(self, synthetic_repo):
        res = self._run(synthetic_repo)
        assert len(res.pairs) == 4

        # F1 signature: only c2->c3 changes f's signature. Symbol anchors catch it (recall 1) but
        # also fire on c0->c1's body-only edit (a false invalidation) — the precision cost measured.
        sym = self._cell(res, "F1_signature", "A3_symbol")
        assert sym.fn == 0 and sym.tp == 1 and sym.fp >= 1
        assert self._cell(res, "F1_signature", "A0_never").fn == 1

        # F2 callers(f): grows at c1->c2 via a call added in b.py. f's own symbol anchor cannot see
        # that; the neighbourhood (importers of a.py) and the exact graph query both can.
        assert self._cell(res, "F2_callers", "A3_symbol").fn >= 1
        assert self._cell(res, "F2_callers", "A4_neighborhood").fn == 0
        query = self._cell(res, "F2_callers", "A5_query")
        assert query.fn == 0 and query.fp == 0 and query.tp >= 1

        # Repo-level wipe: every pair has a diff, so every true fact is thrown away.
        wipe = self._cell(res, "F1_signature", "A1_repo")
        assert wipe.fn == 0 and wipe.tn == 0

        # The exact query anchor never throws away a still-true callers fact (incl. the README-only
        # commit c3->c4, where the byte-level policies also stay quiet about a.py/b.py facts).
        assert self._cell(res, "F2_callers", "A5_query").fp == 0

        summary = res.summary()
        assert summary["overall"]["A5_query"]["recall"] == 1.0
        assert summary["overall"]["A1_repo"]["false_invalidation_rate"] == 1.0
        assert summary["overall"]["A0_never"]["recall"] == 0.0
        assert set(summary["by_fact"]) >= {"F1_signature", "F2_callers", "F3_callees", "F4_imports", "F5_scripts"}

    def test_scripts_fact_uses_manifest_anchors(self, synthetic_repo):
        res = self._run(synthetic_repo)
        # package.json never changes after c0: no script fact is ever stale or invalidated
        cell = self._cell(res, "F5_scripts", "A2_file")
        assert cell.tp == cell.fp == cell.fn == 0 and cell.tn == 4


def test_annotation_budget_harness_on_synthetic_history(synthetic_repo):
    import importlib.util

    path = Path(__file__).resolve().parent / "benchmarks" / "annotation_budget" / "run.py"
    spec = importlib.util.spec_from_file_location("annotation_budget_run", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    run_budget = module.run

    out = run_budget(synthetic_repo, horizon=2, bases=3, budgets="0,1,all", churn_window=2, seeds=[0, 1])
    assert out["per_base"], "expected at least one evaluated commit"
    oracle, lazy = out["summary"]["oracle"], out["summary"]["lazy"]
    assert oracle["all"]["coverage_edit"] == 1.0
    assert lazy["1"]["coverage_edit"] == 0.0
    for policy, by_k in out["summary"].items():
        assert by_k["0"].get("coverage_edit", 0.0) in (0.0, None), policy
