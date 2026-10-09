"""Unit tests for the natural-repository task builder (research/agentbench/ab/natural.py): the reference
edits that validation relies on, and the static over-edit check."""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research" / "agentbench"))

from ab import natural as N  # noqa: E402

SRC = '''\
def target(a, b):
    return a + b


class K:
    def target(self):
        return 1


def use():
    x = target(1, 2)
    y = target(
        3,
        4,
    )
    z = mod.target(5, b=6)
    w = K().target()
    return x, y, z, w
'''


def _calls_with_value(src):
    return {(n, ln) for n, ln in N._value_calls(src)}


def test_edit_def_appends_required_parameter():
    out = N.edit_def(SRC, "target", 1)
    fn = N._find_def(ast.parse(out), "target", 1)
    assert [a.arg for a in fn.args.args] == ["a", "b", "tag"]
    assert not fn.args.defaults


def test_edit_def_without_parameters():
    out = N.edit_def("def f():\n    pass\n", "f", 1)
    assert "def f(tag: str):" in out


def test_edit_calls_handles_multiline_keyword_and_attribute_calls():
    out = N.edit_calls(SRC, "target", [(11, 8), (12, 8), (16, 12)])
    ast.parse(out)  # still valid Python
    assert _calls_with_value(out) == {("target", 11), ("target", 12), ("target", 16)}
    assert "b=6, tag='v2')" in out
    assert "4, tag='v2')" in out or "4,\n" in out


def test_edit_calls_rejects_a_site_that_is_not_a_call():
    assert N.edit_calls(SRC, "target", [(1, 4)]) is None


def test_edit_calls_uses_character_columns_with_non_ascii_text():
    src = 'def f(a):\n    pass\n\ns = "é"; f(1)\n'
    out = N.edit_calls(src, "f", [(4, 9)])  # "f" is character 9, byte 10
    assert out is not None and "f(1, tag='v2')" in out


def test_def_eligibility():
    tree = ast.parse("def a(x, y=1): pass\ndef b(*args): pass\n@property\ndef c(self): pass\ndef __eq__(s, o): pass\n"
                     "def d(x): pass\n")
    fns = {f.name: f for f in tree.body}
    assert N.def_eligible(fns["a"]) and N.def_eligible(fns["b"]) and N.def_eligible(fns["c"])
    assert N.def_eligible(fns["__eq__"]) == "dunder"
    assert N.def_eligible(fns["d"]) == ""


def test_over_edits_flags_non_gold_calls(tmp_path, monkeypatch):
    repo = "r"
    pristine = tmp_path / "data" / "repos" / repo
    pristine.mkdir(parents=True)
    (pristine / "m.py").write_text(SRC)
    work = tmp_path / "work"
    work.mkdir()
    edited = N.edit_calls(SRC, "target", [(11, 8), (17, 12)])  # (17,12) = K().target(): a look-alike
    (work / "m.py").write_text(edited)
    monkeypatch.setattr(N, "DATA", tmp_path / "data")

    class T:
        pass
    t = T()
    t.repo, t.gold_sites = repo, [("m.py", 11)]
    assert N.over_edits(t, work) == [["m.py", 17, "target"]]


def test_signature_changed_finds_nested_functions(tmp_path):
    from ab.tasks import Task, signature_changed
    (tmp_path / "m.py").write_text("def outer(x):\n    def helper(a, tag):\n        return a\n    return helper\n")
    t = Task(id="r:outer.helper", repo="r", lang="py", target_key="k", name="helper", qualname="outer.helper",
             file="m.py", line=2, param="tag", value="v2")
    assert signature_changed(t, tmp_path)


def test_junit_to_nodeid(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_more.py").write_text("")
    assert N.junit_to_nodeid(tmp_path, "tests.test_more.TestX::test_y") == "tests/test_more.py::TestX::test_y"
    assert N.junit_to_nodeid(tmp_path, "nowhere.TestX::t") is None
