"""Tests for _is_healthy_clone and the self-healing behaviour it enables in /repository/load.

The bug this closes, observed live: a repository load for a real, non-empty GitHub repo
(shaun031/Tourism-Management — confirmed via `git ls-remote` to have real commits) produced a
directory containing only Codexa's own `.codexa-repo.json` marker file. The clone had been
interrupted mid-operation (this session's own repeated backend restarts, landing while a clone
subprocess was running, is the concrete cause here) and left a `.git` folder with no working tree
and a HEAD that could not resolve — `git log` reported "your current branch appears to be broken"
and "No commits yet".

The bug was not the interruption itself (that can always happen). It was that `/repository/load`'s
only check for "do I need to clone this" was `dest.exists()`, which is true for a broken half-clone
exactly as it is for a healthy one. Every subsequent load of the same URL silently skipped cloning
and re-ingested the same empty directory forever after, with nothing anywhere to explain why the
user saw "codebase is empty, no architecture."
"""

from __future__ import annotations

import shutil
import subprocess

import pytest

from backend.repository.api import _is_healthy_clone, _remove_directory

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="requires git on PATH")


def _git(*args: str, cwd) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True)


class TestIsHealthyClone:
    def test_a_directory_with_no_git_folder_at_all_is_unhealthy(self, tmp_path):
        (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
        assert _is_healthy_clone(tmp_path) is False

    def test_an_empty_directory_is_unhealthy(self, tmp_path):
        assert _is_healthy_clone(tmp_path) is False

    def test_a_git_init_with_zero_commits_is_unhealthy(self, tmp_path):
        # This is the EXACT state the real interrupted clone was found in: a .git directory exists,
        # but HEAD does not resolve to anything because nothing was ever committed/checked out.
        _git("init", cwd=tmp_path)
        assert _is_healthy_clone(tmp_path) is False

    def test_a_real_commit_makes_it_healthy(self, tmp_path):
        _git("init", cwd=tmp_path)
        _git("config", "user.email", "test@example.com", cwd=tmp_path)
        _git("config", "user.name", "Test", cwd=tmp_path)
        (tmp_path / "README.md").write_text("hello", encoding="utf-8")
        _git("add", "README.md", cwd=tmp_path)
        _git("commit", "-m", "first commit", cwd=tmp_path)
        assert _is_healthy_clone(tmp_path) is True

    def test_a_nonexistent_path_is_unhealthy(self, tmp_path):
        assert _is_healthy_clone(tmp_path / "does-not-exist") is False

    def test_a_broken_clone_nested_inside_another_real_repo_is_still_unhealthy(self, tmp_path):
        # The false positive caught live, on the second real repository this ran against (the
        # first, a plain interrupted `git init`-shaped state, was already covered above). Every
        # cloned repo lives under Codexa's own .codexa/repos/, which is itself INSIDE Codexa's own
        # git-tracked working tree — and a REAL interrupted `git clone` can be killed even earlier
        # than a bare `git init` ever leaves things: the live case had ONLY `.git/objects/pack/`,
        # no HEAD, no config, no refs/ at all, because it died while still fetching the pack file,
        # before git had written any of the files that even mark a directory as a git boundary.
        # `git rev-parse HEAD` run there does not fail — git's directory discovery does not
        # recognise that `.git` as a real repository at all (no HEAD file to find), so it walks
        # UP past it and resolves the OUTER repository's real HEAD instead. A check using only
        # `rev-parse HEAD` reports that broken inner clone as healthy — the opposite of what it
        # exists to catch. This reproduces the exact structure and the exact degenerate .git state.
        outer = tmp_path / "outer-project"
        outer.mkdir()
        _git("init", cwd=outer)
        _git("config", "user.email", "test@example.com", cwd=outer)
        _git("config", "user.name", "Test", cwd=outer)
        (outer / "README.md").write_text("outer project", encoding="utf-8")
        _git("add", "README.md", cwd=outer)
        _git("commit", "-m", "outer commit", cwd=outer)

        nested_broken = outer / "repos" / "SomeRepo"
        (nested_broken / ".git" / "objects" / "pack").mkdir(parents=True)  # exactly what was found live

        # Sanity check on the premise itself: plain `rev-parse HEAD` from inside the broken nested
        # clone really does resolve to the OUTER repo's commit, which is the bug being guarded
        # against — if this assertion ever stops holding, the test above it would no longer be
        # exercising the failure this one exists to catch.
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(nested_broken), capture_output=True, text=True,
        )
        assert head.returncode == 0, "premise broken: git did not walk up to the outer repo"

        assert _is_healthy_clone(nested_broken) is False

    def test_a_healthy_clone_nested_inside_another_real_repo_is_still_healthy(self, tmp_path):
        # The other side of the same fix: the toplevel check must not produce a false NEGATIVE for
        # a genuinely complete nested clone, which is the normal, common case for this platform —
        # every real repository it clones lives inside its own git-tracked tree exactly like this.
        outer = tmp_path / "outer-project"
        outer.mkdir()
        _git("init", cwd=outer)

        nested_healthy = outer / "repos" / "SomeRepo"
        nested_healthy.mkdir(parents=True)
        _git("init", cwd=nested_healthy)
        _git("config", "user.email", "test@example.com", cwd=nested_healthy)
        _git("config", "user.name", "Test", cwd=nested_healthy)
        (nested_healthy / "index.html").write_text("<html></html>", encoding="utf-8")
        _git("add", "index.html", cwd=nested_healthy)
        _git("commit", "-m", "real commit", cwd=nested_healthy)

        assert _is_healthy_clone(nested_healthy) is True


class TestRemoveDirectory:
    """The bug this closes: shutil.rmtree(dest, ignore_errors=True) reported success on Windows
    while a `.git` file was still briefly held open, leaving the directory in place. The
    subsequent `git clone` into that not-actually-empty directory then failed with a confusing,
    truncated "Clone failed: Cloning into '...'" that named none of this. _remove_directory must
    actually confirm the directory is gone, not just ask shutil to try and trust it.
    """

    def test_removes_a_real_directory(self, tmp_path):
        target = tmp_path / "repo"
        target.mkdir()
        (target / "file.txt").write_text("x", encoding="utf-8")
        _remove_directory(target)
        assert not target.exists()

    def test_a_directory_that_never_existed_is_not_an_error(self, tmp_path):
        _remove_directory(tmp_path / "never-was-here")  # must not raise

    def test_retries_a_transient_failure_and_succeeds(self, tmp_path, monkeypatch):
        import backend.repository.api as repo_api

        target = tmp_path / "repo"
        target.mkdir()
        calls = {"n": 0}
        real_rmtree = shutil.rmtree

        def flaky_rmtree(path, **_kw):
            calls["n"] += 1
            if calls["n"] < 3:
                raise OSError("[WinError 32] file in use by another process")
            real_rmtree(path)

        monkeypatch.setattr(repo_api.shutil, "rmtree", flaky_rmtree)
        monkeypatch.setattr(repo_api.time, "sleep", lambda s: None)  # don't slow the test down
        _remove_directory(target)
        assert calls["n"] == 3
        assert not target.exists()

    def test_raises_the_real_error_when_every_retry_fails(self, tmp_path, monkeypatch):
        import backend.repository.api as repo_api

        target = tmp_path / "repo"
        target.mkdir()

        def always_fails(path, **_kw):
            raise OSError("[WinError 32] file in use by another process")

        monkeypatch.setattr(repo_api.shutil, "rmtree", always_fails)
        monkeypatch.setattr(repo_api.time, "sleep", lambda s: None)
        with pytest.raises(OSError, match="WinError 32"):
            _remove_directory(target)
