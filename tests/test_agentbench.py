"""RQ4 agent harness (research/agentbench): task generation, execution oracle, agent loop."""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
for p in (ROOT / "research" / "agentbench", ROOT / "research" / "navbench"):
    sys.path.insert(0, str(p))

from ab.agent import Workspace, run_agent  # noqa: E402
from ab.tasks import TSC, check, from_fixture, materialize  # noqa: E402
from nb.fixtures import gen_python, gen_ts  # noqa: E402


@pytest.fixture(scope="module")
def fixtures(tmp_path_factory):
    base = tmp_path_factory.mktemp("fx")
    gen_python(base / "fx-py-fresh-200", 200, False)
    if TSC.exists() and shutil.which("node"):
        gen_ts(base / "fx-ts-fresh-201", 201, True)
    return base


def _scripted(task, root, complete=True):
    """A fake LLM that performs the edit (all call sites, or only the definition)."""
    steps = []
    lines = (root / task.file).read_text(encoding="utf-8").splitlines()
    dline = lines[task.line - 1]
    typ = "str" if task.lang == "py" else "string"
    new_def = re.sub(r"\(([^)]*)\)", lambda m: f"({m.group(1)}, tag: {typ})" if m.group(1) else f"(tag: {typ})", dline, count=1)
    steps.append(("replace_in_file", {"path": task.file, "old": dline, "new": new_def}))
    if complete:
        for f, ln in task.gold_sites:
            line = (root / f).read_text(encoding="utf-8").splitlines()[ln - 1]
            name = task.name if task.name in line else None
            new = re.sub(rf"(\b\w*{re.escape(task.name) if name else ''}\w*\([^()]*)\)", r'\1, "v2")', line, count=1) if name \
                else re.sub(r"(\w+\([^()]*)\)", r'\1, "v2")', line, count=1)
            new = new.replace('(, "v2")', '("v2")')
            steps.append(("replace_in_file", {"path": f, "old": line, "new": new}))
    steps.append(("finish", {}))
    it = iter(steps)

    def llm(messages, tools):
        name, args = next(it)
        return {"content": "", "tool_calls": [{"id": f"c{len(messages)}", "type": "function",
                                               "function": {"name": name, "arguments": json.dumps(args)}}]}, \
               {"prompt_tokens": 10, "completion_tokens": 2}
    return llm


def _ws(task, root):
    import sys as _s
    cmd = [_s.executable, "main.py"] if task.lang == "py" else ["node", str(TSC), "--noEmit", "-p", "."]
    return Workspace(root, task.lang, cmd)


def test_tasks_generated_with_gold(fixtures):
    tasks = from_fixture(fixtures / "fx-py-fresh-200")
    assert {t.target_key for t in tasks} == {"direct", "M", "reexp", "decorated"}
    t = next(t for t in tasks if t.target_key == "direct")
    assert len(t.gold_sites) == 4 and "EVERY call site" in t.prompt


@pytest.mark.parametrize("fx", ["fx-py-fresh-200", "fx-ts-fresh-201"])
def test_oracle_rewards_complete_and_rejects_partial(fixtures, tmp_path, fx):
    if not (fixtures / fx).exists():
        pytest.skip("TypeScript toolchain not installed")
    task = next(t for t in from_fixture(fixtures / fx) if t.target_key == "direct")
    untouched = materialize(task, fixtures, tmp_path / "u")
    u = check(task, untouched)
    assert u["oracle_ok"] and not u["signature_changed"]            # the program runs, but nothing was done
    assert not u["success"]                                         # so an untouched tree is not a success
    good = materialize(task, fixtures, tmp_path / "g")
    log = run_agent(task.prompt, _ws(task, good), _scripted(task, good, complete=True))
    v = check(task, good)
    assert log.finished and v["success"], v["oracle_output"]
    assert v["sites_updated"] == v["sites_total"]
    bad = materialize(task, fixtures, tmp_path / "b")
    run_agent(task.prompt, _ws(task, bad), _scripted(task, bad, complete=False))
    assert not check(task, bad)["success"]                         # missed call sites are caught
    assert log.prompt_tokens > 0 and log.tool_calls["replace_in_file"] >= 2


def test_workspace_confinement_and_tools(fixtures, tmp_path):
    task = from_fixture(fixtures / "fx-py-fresh-200")[0]
    root = materialize(task, fixtures, tmp_path / "w")
    ws = _ws(task, root)
    assert ".navbench-manifest.json" not in ws.list_files()      # the agent never sees the gold
    assert "ERROR" in ws.replace_in_file(task.file, "def ", "def ")  # ambiguous snippet refused
    with pytest.raises(ValueError):
        ws.read_file("../outside.txt")
    assert "main.py" in ws.list_files()
    assert "exit code 0" in ws.run_program()


@pytest.mark.parametrize("fx", ["fx-py-fresh-200", "fx-ts-fresh-201"])
def test_signature_check_per_target_kind(fixtures, tmp_path, fx):
    if not (fixtures / fx).exists():
        pytest.skip("TypeScript toolchain not installed")
    from ab.tasks import signature_changed
    for task in from_fixture(fixtures / fx):
        root = materialize(task, fixtures, tmp_path / task.target_key)
        assert not signature_changed(task, root), task.id
        f = root / task.file                                            # edit the definition by line number:
        lines = f.read_text(encoding="utf-8").splitlines()              # a method's def line can repeat in a look-alike
        typ = "str" if task.lang == "py" else "string"
        lines[task.line - 1] = re.sub(r"\(([^)]*)\)", lambda m: f"({m.group(1)}, tag: {typ})", lines[task.line - 1], count=1)
        f.write_text("\n".join(lines) + "\n", encoding="utf-8")
        assert signature_changed(task, root), task.id                  # method, re-export, decorated, direct


def test_default_value_does_not_count(fixtures, tmp_path):
    from ab.tasks import signature_changed
    task = next(t for t in from_fixture(fixtures / "fx-py-fresh-200") if t.target_key == "direct")
    root = materialize(task, fixtures, tmp_path / "d")
    f = root / task.file
    lines = f.read_text(encoding="utf-8").splitlines()
    lines[task.line - 1] = re.sub(r"\(([^)]*)\)", r"(\1, tag='v2')", lines[task.line - 1], count=1)
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert check(task, root)["oracle_ok"] and not signature_changed(task, root)


def test_regrade_replays_transcript(fixtures, tmp_path):
    from ab.regrade import replay
    task = next(t for t in from_fixture(fixtures / "fx-py-fresh-200") if t.target_key == "direct")
    live = materialize(task, fixtures, tmp_path / "live")
    log = run_agent(task.prompt, _ws(task, live), _scripted(task, live, complete=True))
    assert replay(task, log.transcript, fixtures, tmp_path / "re") == check(task, live)
