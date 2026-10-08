"""Context-rot claim extraction, oracles and full-history tracking (research/contextrot)."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "research" / "contextrot"))

from cr.extract import extract, negated  # noqa: E402
from cr.oracles import Snapshot, check  # noqa: E402
from cr.rot import kaplan_meier, median_survival, summarize, track  # noqa: E402

DOC = """# Agents guide

## Setup
```bash
$ npm install
npm run build   # compile
cd web && npm run dev
python -m pytest tests/unit
make lint
```

Run `npm run test:e2e` before pushing. Config lives in `src/config.ts` and [the docs](docs/setup.md).
The entry point is `createServer()`; set `API_TOKEN` locally.

## Stack
- Backend: FastAPI with Python 3.11+. Frontend: React 18.
- Never introduce MongoDB. Postgres stays; Redis is a cache — never write to it directly.

```
src/
├── config.ts
└── server/
    └── index.ts
```

Prefer small pull requests.
"""


def _repo(root: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return root


BASE = {
    "package.json": json.dumps({"scripts": {"build": "tsc", "test:e2e": "playwright test"},
                                "dependencies": {"react": "^18.2.0", "pg": "^8"}, "devDependencies": {"typescript": "5"}}),
    "web/package.json": json.dumps({"scripts": {"dev": "vite"}}),
    "pyproject.toml": "[project]\nname='x'\nrequires-python='>=3.11'\ndependencies=['fastapi>=0.110','pytest','redis']\n",
    "Makefile": "lint:\n\techo lint\n",
    "src/config.ts": "export const API_TOKEN = process.env.API_TOKEN;\n",
    "src/server/index.ts": "export function createServer() { return 1; }\n",
    "tests/unit/test_a.py": "def test_a():\n    assert True\n",
    "docs/setup.md": "setup\n",
}


class TestExtract:
    def test_classes(self):
        cl = extract(DOC)
        by = {(c.cls, c.text) for c in cl}
        assert ("command", "npm install") in by and ("command", "npm run build") in by
        assert ("command", "cd web && npm run dev") in by and ("command", "make lint") in by
        assert ("command", "npm run test:e2e") in by
        assert ("path", "src/config.ts") in by and ("path", "docs/setup.md") in by
        assert ("symbol", "createServer") in by and ("symbol", "API_TOKEN") in by
        assert {"src/config.ts", "src/server/index.ts", "src/server"} <= {t for c, t in by if c == "structure"}
        assert any(c.cls == "prose" and "small pull requests" in c.text for c in cl)

    def test_dependency_polarity_is_scoped(self):
        deps = {c.text: c for c in extract(DOC) if c.cls == "dependency"}
        assert deps["mongodb"].polarity == "negative"
        assert deps["postgres"].polarity == "positive"
        assert deps["redis"].polarity == "positive"          # "never write to it" does not negate Redis
        assert deps["react"].extra["version"] == "18"
        assert deps["python"].extra["at_least"] is True
        assert not negated("Neo4j is a projection; never write to it directly", 0)


class TestOracles:
    def test_all_true_on_matching_repo(self, tmp_path):
        snap = Snapshot(_repo(tmp_path / "r", BASE))
        verdicts = {(c.cls, c.text): check(snap, c).status for c in extract(DOC) if c.cls != "prose"}
        falses = {k: v for k, v in verdicts.items() if v == "false"}
        assert not falses, falses

    def test_detects_each_kind_of_rot(self, tmp_path):
        files = dict(BASE)
        files["package.json"] = json.dumps({"scripts": {"compile": "tsc"}, "dependencies": {"react": "^19.0.0", "mongoose": "8"}})
        del files["src/config.ts"]
        del files["Makefile"]
        files["src/server/index.ts"] = "export function startServer() { return 1; }\n"
        snap = Snapshot(_repo(tmp_path / "r", files))
        v = {(c.cls, c.text): check(snap, c) for c in extract(DOC) if c.cls != "prose"}
        assert v[("command", "npm run build")].status == "false"
        assert v[("command", "make lint")].status == "false"
        assert v[("path", "src/config.ts")].status == "false"
        assert v[("symbol", "createServer")].status == "false"
        assert v[("dependency", "react")].status == "false"       # 19 declared, claim says 18
        assert v[("dependency", "mongodb")].status == "false"     # "never introduce" but present
        assert v[("command", "cd web && npm run dev")].status == "true"

    def test_unknown_is_not_rot(self, tmp_path):
        snap = Snapshot(_repo(tmp_path / "r", BASE))
        c = next(c for c in extract("Run `python -m some_global_tool` and see `docs/<name>.md`.") if c.cls == "command")
        assert check(snap, c).status == "unknown"
        assert not [c for c in extract("see `docs/<name>.md`") if c.cls == "path"]  # placeholders are not claims
        from cr.oracles import check_path
        assert check_path(snap, "docs/<name>.md").status == "unknown"


@pytest.mark.skipif(shutil.which("git") is None, reason="requires git")
class TestRot:
    def _git(self, root, *args):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=root, check=True, capture_output=True)

    def test_lifecycle_rot_then_fix(self, tmp_path):
        root = tmp_path / "hist"
        root.mkdir()
        self._git(root, "init", "-q")
        agents = "Build with `npm run build`. Config in `src/config.ts`.\n"
        _repo(root, {**BASE, "AGENTS.md": agents})
        self._git(root, "add", "-A"); self._git(root, "commit", "-qm", "c0")
        for i in range(3):  # unrelated commits
            (root / f"n{i}.txt").write_text(str(i)); self._git(root, "add", "-A"); self._git(root, "commit", "-qm", f"n{i}")
        pkg = json.loads(BASE["package.json"]); pkg["scripts"] = {"compile": "tsc"}
        (root / "package.json").write_text(json.dumps(pkg)); self._git(root, "add", "-A"); self._git(root, "commit", "-qm", "rename")
        (root / "n9.txt").write_text("x"); self._git(root, "add", "-A"); self._git(root, "commit", "-qm", "n9")
        (root / "AGENTS.md").write_text("Build with `npm run compile`. Config in `src/config.ts`.\n")
        self._git(root, "add", "-A"); self._git(root, "commit", "-qm", "fix doc")

        lifes = {l.text: l for l in track(root, "AGENTS.md", every=1)}
        build = lifes["npm run build"]
        assert build.outcome == "rotted" and build.rot_commits == 4 and build.fixed
        assert lifes["src/config.ts"].outcome == "valid" and lifes["src/config.ts"].censored_commits == 6
        assert lifes["npm run compile"].outcome == "valid"
        s = summarize(list(lifes.values()))
        assert s["command"]["rotted"] == 1 and s["command"]["fixed_after_stale"] == 1


def test_kaplan_meier():
    km = kaplan_meier([(2, True), (4, False), (6, True), (8, True)])
    assert km[0] == (0.0, 1.0)
    assert km[1] == (2, 0.75)
    assert km[2][1] == pytest.approx(0.75 * (1 - 1 / 2))
    assert median_survival(km) == 6


class TestOracleFalsePositiveFixes:
    """Regressions for the false 'stale' verdicts found in the S1 pilot audit."""

    def test_acronyms_and_words_are_not_symbols(self):
        syms = {c.text for c in extract("Watch for `SSRF`, `RCE`, `advisory`, `exec`; call `JsonJwt` and `parse_config`.") if c.cls == "symbol"}
        assert syms == {"JsonJwt", "parse_config"}

    def test_express_verb_is_not_express_framework(self):
        assert not [c for c in extract("Comments should express intent.") if c.cls == "dependency"]
        assert [c for c in extract("Server: Express with Node.") if c.text == "express"]

    def test_example_context_is_unknown_not_false(self, tmp_path):
        snap = Snapshot(_repo(tmp_path / "r", BASE))
        c = next(c for c in extract("For example, create `src/MyClassTest.java` for each class.") if c.cls == "path")
        assert check(snap, c).status == "unknown"

    def test_bare_filename_and_tree_root(self, tmp_path):
        snap = Snapshot(_repo(tmp_path / "r", BASE))
        from cr.oracles import check_path
        assert check_path(snap, "index.ts").status == "true"           # lives in src/server/
        assert check_path(snap, "server/").status == "true"
        assert check_path(snap, "myrepo/src/config.ts").status == "true"  # tree drawn from the repo folder
        assert check_path(snap, "nowhere.ts").status == "false"

    def test_command_arguments_that_are_not_paths(self, tmp_path):
        files = {k: v for k, v in BASE.items() if k != "Makefile"}
        snap = Snapshot(_repo(tmp_path / "r", {**files, "CMakeLists.txt": "project(x)\n"}))
        from cr.oracles import check_command
        assert check_command(snap, "python -m pytest tests/unit/test_a.py::test_a").status == "true"
        assert check_command(snap, "docker pull ghcr.io/org/img:latest").status != "false"
        assert check_command(snap, "make rust_tests").status == "unknown"   # CMake-generated Makefile
