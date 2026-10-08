"""NavBench feature additions (research/navbench): common answer form (B), routing policies (A),
leaderboard + adapter registry (C), T3 multi-hop gold (E), and generator invariance."""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pytest

NAVBENCH = Path(__file__).resolve().parent.parent / "research" / "navbench"
sys.path.insert(0, str(NAVBENCH))

from nb import adapters as AD  # noqa: E402
from nb import forms, leaderboard, policy  # noqa: E402
from nb import index as I  # noqa: E402
from nb.fixtures import gen_python  # noqa: E402
from nb.score import fixture_gold_callers, t3_gold  # noqa: E402


@pytest.fixture(scope="module")
def py_fixture(tmp_path_factory):
    root = tmp_path_factory.mktemp("fx") / "fx-py-heldout-100"
    man = gen_python(root, 100, False)
    return root, man, I.load(root, "py")


# ----------------------------------------------------------------------------------- generator --
def test_generator_targets_identical_to_frozen_run(py_fixture):
    """Recording T3 edges must not move any target: positions equal the frozen run's targets."""
    _root, man, _ix = py_fixture
    frozen = [t["decl"] for t in json.loads((NAVBENCH / "results/main/fx-py-heldout-100.targets.json").read_text())]
    assert [f"{t['file']}:{t['line']}:{t['col']}" for t in man["targets"]] == frozen
    assert man["edges"], "generator should record non-target call edges"


# ------------------------------------------------------------------------------------- forms B --
def test_msa_identical_for_identical_caller_sets(py_fixture):
    _root, man, ix = py_fixture
    t = next(x for x in man["targets"] if x["key"] == "direct")
    sites = [(s["file"], s["line"], s["col"]) for s in t["sites"] if s["category"] == "explicit"]
    callers = forms.msa_callers(ix, "loc", sites)
    assert forms.msa_text(ix, "loc", sites) == forms.msa_text(ix, "caller", callers)
    text = forms.render_msa(ix, callers + ["unresolved:foo@x.py:1"])
    assert "<module>" in text and "unresolved:foo@x.py:1" in text
    assert all(":" in line for line in text.splitlines())


# -------------------------------------------------------------------------------------- T3 (E) --
def test_t3_gold_two_hops(py_fixture):
    _root, man, ix = py_fixture
    t = next(x for x in man["targets"] if x["key"] == "direct")
    tid = f"{t['file']}:{t['line']}:{t['col']}"
    hop1 = {c for c in fixture_gold_callers(ix, {"gold": {"explicit": [
        {"call": ix.name_tok.get((s["file"], s["line"], s["col"]))} for s in t["sites"] if s["category"] == "explicit"]}})}
    g1, g2 = t3_gold(ix, man, tid, depth=1), t3_gold(ix, man, tid, depth=2)
    assert g1 == hop1
    run_all = next(d["id"] for d in ix.decls.values() if d["qualname"] == "run_all")
    assert run_all in g2 and run_all not in g1
    assert not any(c.endswith("main.py") for c in g2)  # main reaches the target in 3 hops, not 2


# -------------------------------------------------------------------------------- policies (A) --
def _row(repo, target, arm, callers, tok, status="ok", n_calls=1, gold=None):
    r = {"repo": repo, "target": target, "arm": arm, "task": "T1", "layer": "fixture", "status": status,
         "_callers": callers, "tok_native_cl100k": tok, "n_units": len(callers), "n_calls": n_calls,
         "n_unresolved": 0, "truncated": False}
    if gold is not None:
        r["A_gold_callers"] = gold
    return r


@pytest.fixture()
def policy_rows():
    rows = []
    for i, repo in enumerate(["r1", "r2"]):
        g = ["a", "b"]
        rows += [_row(repo, "t1", "graph", ["a", "b"], 10, gold=g),           # complete, cheap
                 _row(repo, "t1", "rg0", ["a", "b", "x"], 50, gold=g),
                 _row(repo, "t2", "graph", [], 5, status="empty", gold=g),     # empty -> fallback should fire
                 _row(repo, "t2", "rg0", ["a", "b"], 40, gold=g),
                 _row(repo, "t3", "graph", ["a"], 12, n_calls=2, gold=g),      # ambiguous follow-up
                 _row(repo, "t3", "rg0", ["b"], 30, gold=g)]
    return rows


def test_policy_triggers_and_union(policy_rows):
    res = policy.run(policy_rows, "A", "tok_native_cl100k", ["graph", "rg0"], ["rg0"])["policies"]
    assert res["single:graph"]["complete"] == pytest.approx(1 / 3)
    assert res["route:graph>rg0@empty"]["complete"] == pytest.approx(2 / 3)
    assert res["route:graph>rg0@weak"]["complete"] == pytest.approx(1.0)
    assert res["route:graph>rg0@weak"]["tokens"] == pytest.approx((10 + 45 + 42) / 3)
    assert res["route:graph>rg0@weak"]["fired"] == pytest.approx(2 / 3)
    assert res["oracle"]["tokens"] == pytest.approx((10 + 40 + 12) / 3)  # t3: neither complete -> cheapest arm
    assert res["route:graph>rg0@weak"]["pareto"]


def test_policy_base_calls_not_ambiguity():
    assert not policy.fires("ambiguous", {"arm": "codexa_orig", "n_calls": 2, "status": "ok", "n_units": 1})
    assert policy.fires("ambiguous", {"arm": "cbm_cur", "n_calls": 2, "status": "ok", "n_units": 1})


# ------------------------------------------------------------------------- leaderboard (C) --
def test_leaderboard_tokens_per_complete_and_unsupported():
    rows = []
    for repo in ("r1", "r2"):
        rows += [{"repo": repo, "layer": "fixture", "task": "T1", "arm": "cheap", "status": "ok", "n_units": 1,
                  "A_n_gold": 2, "A_caller_recall": 0.5, "A_caller_precision": 1.0, "A_complete": False,
                  "tok_native_cl100k": 10, "tok_loc_cl100k": 5, "tok_msa_cl100k": 6},
                 {"repo": repo, "layer": "fixture", "task": "T1", "arm": "full", "status": "ok", "n_units": 2,
                  "A_n_gold": 2, "A_caller_recall": 1.0, "A_caller_precision": 1.0, "A_complete": True,
                  "tok_native_cl100k": 40, "tok_loc_cl100k": 9, "tok_msa_cl100k": 12},
                 {"repo": repo, "layer": "fixture", "task": "T1", "arm": "missing", "status": "unsupported",
                  "note": "binary not found"}]
    t = {r["arm"]: r for r in leaderboard.table(rows, "fixture", "T1")}
    assert t["cheap"]["tokens_per_complete"] == math.inf
    assert t["full"]["tokens_per_complete"] == pytest.approx(40)
    assert t["missing"]["unsupported"]
    assert t["cheap"]["pareto"] and t["full"]["pareto"]
    assert "unsupported" in leaderboard.to_markdown({("fixture", "T1"): list(t.values())})


# ------------------------------------------------------------------------- adapters (C) --
def test_frozen_adapters_produce_frozen_arms():
    arms = [a for n in AD.FROZEN for a in AD.REGISTRY[n].t1_arms]
    assert arms == ["rg0", "rg3", "lsp", "codexa_refs", "codexa_orig", "cbm_cur", "cbm_057"]
    assert {AD.REGISTRY[n].t2_arm for n in AD.FROZEN_T2_ORDER} == {"lsp_def", "rg_def", "codexa_def", "cbm_cur_def", "cbm_057_def"}


def test_missing_binary_is_unsupported(monkeypatch, tmp_path):
    monkeypatch.setenv("NB_CBM_CUR", str(tmp_path / "nope"))
    ok, why = AD.make(["cbm_cur"])[0].available()
    assert not ok and "binary not found" in why


def test_plugin_registration(monkeypatch, tmp_path):
    (tmp_path / "nb_plugin_demo.py").write_text(
        "from nb.adapters import Adapter, register\n"
        "@register\nclass Demo(Adapter):\n    name = 'demo'\n    t1_arms = ('demo',)\n"
        "    def t1(self, ctx, decl):\n        return []\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv("NB_PLUGINS", "nb_plugin_demo")
    assert [a.name for a in AD.make(["demo"])] == ["demo"]
    with pytest.raises(KeyError):
        AD.make(["does-not-exist"])


def test_resolution_context_restores_env(monkeypatch):
    monkeypatch.setenv("CODEXA_CALL_RESOLUTION", "v2")
    with AD.resolution("v1"):
        import os
        assert os.environ["CODEXA_CALL_RESOLUTION"] == "v1"
    import os
    assert os.environ["CODEXA_CALL_RESOLUTION"] == "v2"
