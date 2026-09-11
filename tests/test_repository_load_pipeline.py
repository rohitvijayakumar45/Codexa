"""The /repository/load pipeline end to end (backend/repository/api.py `load_repository`).

The bugs these close, all observed live:

- Every re-load of a repository that already had a folder on disk failed with "[WinError 5] Access
  is denied" on `.git/objects/pack/*.idx`. git writes pack files read-only and Windows refuses to
  delete read-only files, so the swap failed — AFTER the removal had already deleted everything
  else, destroying the old checkout. Five failed attempts at one repository left five orphaned temp
  clones behind.
- Pasted GitHub page URLs (".../tree/main") and scheme-less URLs ("github.com/owner/repo") were
  rejected or handed to git verbatim.
- git's useless "Cloning into '...'" preamble was reported as the error, and the frontend then
  replaced even that with "Backend responded 400".
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from types import SimpleNamespace

import pytest

from backend.graph.events import InMemoryGraphEventWriter
from backend.graph.repository import InMemoryGraphRepository
from backend.graph.schemas import GraphNodeType
from backend.graph.service import GraphService
from backend.memory.store import MemoryStore
from backend.repository import api as repo_api
from backend.repository.api import (
    CloneError,
    _clone_error_message,
    _is_healthy_clone,
    _normalize_url,
    _remove_directory,
    load_repository,
)

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="requires git on PATH")


def _git(*args: str, cwd) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True)


def _read_only(path) -> None:
    os.chmod(path, stat.S_IREAD)


class TestRemoveDirectoryReadOnly:
    def test_removes_read_only_git_pack_files(self, tmp_path):
        target = tmp_path / "repo"
        pack = target / ".git" / "objects" / "pack"
        pack.mkdir(parents=True)
        (pack / "pack-abc.idx").write_bytes(b"x")
        (target / "README.md").write_text("x", encoding="utf-8")
        _read_only(pack / "pack-abc.idx")
        _read_only(target / "README.md")
        _remove_directory(target)
        assert not target.exists()


class TestNormalizeUrl:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("https://github.com/octocat/Hello-World", "https://github.com/octocat/Hello-World"),
            ("https://github.com/octocat/Hello-World.git", "https://github.com/octocat/Hello-World.git"),
            ("https://github.com/octocat/Hello-World/tree/master", "https://github.com/octocat/Hello-World"),
            ("https://github.com/octocat/Hello-World/blob/master/README", "https://github.com/octocat/Hello-World"),
            ("https://github.com/octocat/Hello-World?tab=readme#top", "https://github.com/octocat/Hello-World"),
            ("  github.com/octocat/Hello-World  ", "https://github.com/octocat/Hello-World"),
            ("www.github.com/octocat/Hello-World/", "https://github.com/octocat/Hello-World"),
            ("https://gitlab.com/group/sub/proj/-/tree/main", "https://gitlab.com/group/sub/proj"),
            ("git@github.com:octocat/Hello-World.git", "git@github.com:octocat/Hello-World.git"),
        ],
    )
    def test_accepts_what_people_paste(self, raw, expected):
        assert _normalize_url(raw) == expected

    @pytest.mark.parametrize("raw", ["", "not a url", "https://github.com/octocat", "ftp://x/y/z", "github.com"])
    def test_rejects_things_that_are_not_repositories(self, raw):
        assert _normalize_url(raw) is None


class TestCloneErrorMessage:
    def test_missing_or_private_repository(self):
        msg = _clone_error_message(
            "Cloning into 'x'...\nremote: Repository not found.\nfatal: repository 'https://github.com/a/b/' not found\n"
        )
        assert msg.startswith("Repository not found, or it's private")

    def test_disabled_credential_prompt_reads_as_private(self):
        msg = _clone_error_message(
            "Cloning into 'x'...\nfatal: could not read Username for 'https://github.com': terminal prompts disabled\n"
        )
        assert "private" in msg

    def test_network_failure(self):
        assert "network" in _clone_error_message("fatal: unable to access 'https://x/': Could not resolve host: x\n")

    def test_uses_the_fatal_line_not_the_cloning_preamble(self):
        msg = _clone_error_message("Cloning into 'x'...\nfatal: Remote branch nope not found in upstream origin\n")
        assert msg == "Clone failed: fatal: Remote branch nope not found in upstream origin"

    def test_an_interrupted_download_says_so(self):
        for stderr in ("Cloning into 'x'...\nfatal: early EOF\n", "fatal: fetch-pack: invalid index-pack output\n"):
            assert "kept getting interrupted" in _clone_error_message(stderr)

    def test_nothing_but_the_preamble(self):
        assert "gave no reason" in _clone_error_message("Cloning into 'x'...\n")


def _make_source(root) -> None:
    root.mkdir(parents=True)
    _git("init", cwd=root)
    _git("config", "user.email", "test@example.com", cwd=root)
    _git("config", "user.name", "Test", cwd=root)
    (root / "server.js").write_text(
        "const express = require('express');\nconst app = express();\n"
        "function health(req, res) {}\napp.get('/health', health);\n",
        encoding="utf-8",
    )
    (root / "package.json").write_text(json.dumps({"dependencies": {"express": "^5.0.0"}}), encoding="utf-8")
    _git("add", ".", cwd=root)
    _git("commit", "-m", "init", cwd=root)


@pytest.fixture()
def pipeline(tmp_path, monkeypatch):
    data = tmp_path / "data"
    monkeypatch.setattr(repo_api, "DATA_DIR", data)
    source = tmp_path / "source"
    _make_source(source)
    calls: list[str] = []
    real_clone = repo_api._git_clone

    def clone_from_local_source(url, dest):
        calls.append(url)
        real_clone(str(source), dest)

    monkeypatch.setattr(repo_api, "_git_clone", clone_from_local_source)
    clone_tmp = tmp_path / "clone-tmp"
    clone_tmp.mkdir()
    monkeypatch.setattr(repo_api, "_clone_tmp_root", lambda: clone_tmp)
    return SimpleNamespace(
        clone_tmp=clone_tmp,
        repos=data / "repos",
        calls=calls,
        store=MemoryStore(path=tmp_path / "memories.json"),
        graph=GraphService(repository=InMemoryGraphRepository(), event_writer=InMemoryGraphEventWriter()),
    )


def _repo_nodes(graph, name):
    return [n for n in graph.list_nodes() if n.properties.get("repository") == name]


class TestLoadRepository:
    def test_a_fresh_load_clones_normalises_and_ingests_everything(self, pipeline):
        info, dest = load_repository(
            "https://github.com/someone/sample/tree/main", store=pipeline.store, graph=pipeline.graph
        )
        assert info.name == "sample"
        assert pipeline.calls == ["https://github.com/someone/sample"]
        assert _is_healthy_clone(dest)
        meta = json.loads((dest / ".codexa-repo.json").read_text(encoding="utf-8"))
        assert meta["url"] == "https://github.com/someone/sample"
        types = {n.node_type for n in _repo_nodes(pipeline.graph, "sample")}
        assert {
            GraphNodeType.REPOSITORY,
            GraphNodeType.FILE,
            GraphNodeType.API_ROUTE,
            GraphNodeType.DECISION,
            GraphNodeType.CAUSAL_EVENT,
            GraphNodeType.HEALTH_METRIC,
        } <= types

    def test_replaces_a_broken_clone_whose_pack_files_are_read_only(self, pipeline):
        broken = pipeline.repos / "sample"
        pack = broken / ".git" / "objects" / "pack"
        pack.mkdir(parents=True)
        (pack / "pack-old.idx").write_bytes(b"x")
        _read_only(pack / "pack-old.idx")
        leftover = pipeline.repos / ".sample.load-deadbeef" / ".git" / "objects" / "pack"
        leftover.mkdir(parents=True)
        (leftover / "p.pack").write_bytes(b"x")
        _read_only(leftover / "p.pack")

        info, dest = load_repository("https://github.com/someone/sample", store=pipeline.store, graph=pipeline.graph)
        assert info.name == "sample"
        assert dest == broken.resolve() and _is_healthy_clone(dest)
        assert (dest / "server.js").exists()
        assert not list(pipeline.repos.glob(".sample.load-*"))

    def test_reloading_a_healthy_clone_neither_reclones_nor_duplicates(self, pipeline):
        load_repository("https://github.com/someone/sample", store=pipeline.store, graph=pipeline.graph)
        first = len(_repo_nodes(pipeline.graph, "sample"))
        info, _ = load_repository("github.com/someone/sample", store=pipeline.store, graph=pipeline.graph)
        assert len(pipeline.calls) == 1
        assert info.already_loaded is True
        assert len(_repo_nodes(pipeline.graph, "sample")) == first

    def test_never_overwrites_a_different_repository_or_a_local_project(self, pipeline):
        other = pipeline.repos / "sample"
        other.mkdir(parents=True)
        (other / ".codexa-repo.json").write_text(
            json.dumps({"url": "https://github.com/other/sample", "name": "sample"}), encoding="utf-8"
        )
        (other / "keep.txt").write_text("mine", encoding="utf-8")
        agent_made = pipeline.repos / "someone-sample"
        agent_made.mkdir()
        (agent_made / "app.py").write_text("print(1)", encoding="utf-8")

        info, dest = load_repository("https://github.com/someone/sample", store=pipeline.store, graph=pipeline.graph)
        assert info.name == "sample-2" and _is_healthy_clone(dest)
        assert (other / "keep.txt").read_text(encoding="utf-8") == "mine"
        assert (agent_made / "app.py").exists()

    def test_a_failed_clone_leaves_no_temp_folder_and_says_why(self, pipeline, monkeypatch):
        def fail(url, dest):
            dest.mkdir(parents=True)
            (dest / "partial").write_bytes(b"x")
            _read_only(dest / "partial")
            raise CloneError("Repository not found, or it's private.")

        monkeypatch.setattr(repo_api, "_git_clone", fail)
        with pytest.raises(CloneError, match="not found"):
            load_repository("https://github.com/someone/missing", store=pipeline.store, graph=pipeline.graph)
        assert not list(pipeline.repos.glob(".missing.load-*"))
        assert not list(pipeline.clone_tmp.glob("missing.load-*"))

    def test_clones_outside_the_repository_folder_then_moves_in(self, pipeline, monkeypatch):
        seen = []
        real = repo_api._git_clone

        def spy(url, dest):
            seen.append(dest)
            real(url, dest)

        monkeypatch.setattr(repo_api, "_git_clone", spy)
        _, dest = load_repository("https://github.com/someone/sample", store=pipeline.store, graph=pipeline.graph)
        assert seen and seen[0].parent == pipeline.clone_tmp
        assert _is_healthy_clone(dest) and not list(pipeline.clone_tmp.iterdir())

    def test_rejects_something_that_is_not_a_repository_url(self, pipeline):
        with pytest.raises(ValueError, match="doesn't look like a git URL"):
            load_repository("hello there", store=pipeline.store, graph=pipeline.graph)


def test_a_repository_whose_history_has_coupled_files_loads(tmp_path, monkeypatch):
    """The live failure behind "cloning is completely broken": a real repository (sindresorhus/p-limit)
    has files that change together often enough to produce co-change coupling, and writing that
    coupling as a static-analysis edge with a fractional confidence failed schema validation, so the
    load crashed half-ingested. Tiny repositories never produced a coupling pair, which hid it."""
    monkeypatch.setattr(repo_api, "DATA_DIR", tmp_path / "data")
    source = tmp_path / "coupled"
    source.mkdir()
    _git("init", cwd=source)
    _git("config", "user.email", "test@example.com", cwd=source)
    _git("config", "user.name", "Test", cwd=source)
    for i in range(4):
        (source / "index.js").write_text(f"const helper = require('./helper');\nmodule.exports = () => helper({i});\n", encoding="utf-8")
        (source / "helper.js").write_text(f"module.exports = (n) => n + {i};\n", encoding="utf-8")
        _git("add", ".", cwd=source)
        _git("commit", "-m", f"change {i}", cwd=source)
    real_clone = repo_api._git_clone
    monkeypatch.setattr(repo_api, "_git_clone", lambda url, dest: real_clone(str(source), dest))
    graph = GraphService(repository=InMemoryGraphRepository(), event_writer=InMemoryGraphEventWriter())

    info, _ = load_repository("https://github.com/someone/coupled", store=MemoryStore(path=tmp_path / "m.json"), graph=graph)

    assert info.name == "coupled"
    coupling = [e for e in graph.list_edges_at() if e.edge_type == "correlates_with"]
    assert len(coupling) == 2  # symmetric pair
    assert all(e.confidence == 1.0 and 0 < e.properties["strength"] <= 1 for e in coupling)
    assert all(e.properties["shared_commits"] >= 3 for e in coupling)


class TestGitCloneRetries:
    """"fatal: fetch-pack: invalid index-pack output" failed a real load of a repository that then
    cloned fine three times in a row — a transient download failure must be retried, a missing or
    private repository must not be."""

    @staticmethod
    def _fake_runs(monkeypatch, stderrs):
        calls = {"n": 0}

        def fake_run(cmd, **kwargs):
            calls["n"] += 1
            i = calls["n"] - 1
            if i < len(stderrs) and stderrs[i]:
                raise subprocess.CalledProcessError(128, cmd, stderr=stderrs[i])
            os.makedirs(cmd[-1], exist_ok=True)

        monkeypatch.setattr(repo_api.subprocess, "run", fake_run)
        monkeypatch.setattr(repo_api.time, "sleep", lambda s: None)
        return calls

    def test_retries_an_interrupted_download_and_succeeds(self, tmp_path, monkeypatch):
        calls = self._fake_runs(monkeypatch, ["Cloning into 'x'...\nfatal: fetch-pack: invalid index-pack output\n",
                                              "fatal: early EOF\n"])
        repo_api._git_clone("https://github.com/a/b", tmp_path / "dest")
        assert calls["n"] == 3 and (tmp_path / "dest").exists()

    def test_gives_up_after_three_interrupted_downloads_with_a_clear_message(self, tmp_path, monkeypatch):
        calls = self._fake_runs(monkeypatch, ["fatal: fetch-pack: invalid index-pack output\n"] * 3)
        with pytest.raises(CloneError, match="kept getting interrupted"):
            repo_api._git_clone("https://github.com/a/b", tmp_path / "dest")
        assert calls["n"] == 3

    def test_never_retries_a_missing_repository(self, tmp_path, monkeypatch):
        calls = self._fake_runs(monkeypatch, ["remote: Repository not found.\nfatal: repository not found\n"] * 3)
        with pytest.raises(CloneError, match="not found"):
            repo_api._git_clone("https://github.com/a/missing", tmp_path / "dest")
        assert calls["n"] == 1
