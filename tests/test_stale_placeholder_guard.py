"""Tests for the stale-compaction-placeholder write guard in backend/agents/tools.py.

Regression coverage for a REAL, observed data-corruption bug: backend/agents/jobs.py's
_compact_stale_payloads redacts old tool-call arguments in the conversation history with a
"[compacted ...]" placeholder once they're stale, purely so a long job doesn't resend the same huge
blob every round — it was never meant to touch the actual file on disk. In one overnight run, a
model saw that placeholder in its own history, mistook it for the file's real current content, and
wrote it back verbatim via write_file — permanently destroying three real source files (a stylesheet
and two React components) in a single build. execute_tool now refuses any write whose content IS
that placeholder, at every write path (write_file, edit_file, create_files), instead of silently
letting it corrupt the repo.
"""

from backend.agents.jobs import _COMPACTED_MARK as JOBS_COMPACTED_MARK
from backend.agents.tools import _COMPACTED_MARK, execute_tool


def test_jobs_and_tools_share_the_exact_same_marker():
    # jobs.py imports this from tools.py (not a separate copy) - a second, drifted definition
    # would silently stop being recognized by the guard below.
    assert JOBS_COMPACTED_MARK is _COMPACTED_MARK


class TestWriteFileGuard:
    def test_rejects_content_that_is_a_stale_placeholder(self, tmp_path, monkeypatch):
        import backend.agents.tools as tools_mod
        monkeypatch.setattr(tools_mod, "repo_root", lambda repository: tmp_path)

        placeholder = f"{_COMPACTED_MARK} — 32076 chars, already written to disk.]"
        result = execute_tool("write_file", {"path": "styles/design.css", "content": placeholder}, "demo-repo")

        assert "Refused" in result
        assert not (tmp_path / "styles/design.css").exists()

    def test_accepts_normal_content(self, tmp_path, monkeypatch):
        import backend.agents.tools as tools_mod
        monkeypatch.setattr(tools_mod, "repo_root", lambda repository: tmp_path)

        result = execute_tool("write_file", {"path": "index.html", "content": "<html></html>"}, "demo-repo")

        assert "Wrote" in result
        assert (tmp_path / "index.html").read_text(encoding="utf-8") == "<html></html>"

    def test_content_that_merely_mentions_compacted_midway_is_not_rejected(self, tmp_path, monkeypatch):
        # Only a content string that STARTS WITH the marker is stale placeholder text - a real file
        # that happens to discuss compaction in a comment must never be blocked.
        import backend.agents.tools as tools_mod
        monkeypatch.setattr(tools_mod, "repo_root", lambda repository: tmp_path)

        content = "// this cache entry gets [compacted] after 3 rounds\nconst x = 1;"
        result = execute_tool("write_file", {"path": "cache.js", "content": content}, "demo-repo")

        assert "Wrote" in result


class TestEditFileGuard:
    def test_rejects_new_text_that_is_a_stale_placeholder(self, tmp_path, monkeypatch):
        import backend.agents.tools as tools_mod
        monkeypatch.setattr(tools_mod, "repo_root", lambda repository: tmp_path)
        real_file = tmp_path / "App.tsx"
        real_file.write_text("export default function App() { return null; }", encoding="utf-8")

        placeholder = f"{_COMPACTED_MARK} — 900 chars, already written to disk.]"
        result = execute_tool(
            "edit_file",
            {"path": "App.tsx", "old_text": "return null;", "new_text": placeholder},
            "demo-repo",
        )

        assert "Refused" in result
        assert real_file.read_text(encoding="utf-8") == "export default function App() { return null; }"


class TestCreateFilesGuard:
    def test_rejects_only_the_placeholder_file_not_the_whole_batch(self, tmp_path, monkeypatch):
        import backend.agents.tools as tools_mod
        monkeypatch.setattr(tools_mod, "repo_root", lambda repository: tmp_path)

        placeholder = f"{_COMPACTED_MARK} — 500 chars, already written to disk.]"
        files = [
            {"path": "good.txt", "content": "real content"},
            {"path": "bad.txt", "content": placeholder},
        ]
        result = execute_tool("create_files", {"files": files}, "demo-repo")

        assert "OK good.txt" in result
        assert "REJECTED bad.txt" in result
        assert (tmp_path / "good.txt").exists()
        assert not (tmp_path / "bad.txt").exists()


# ── destroying work that already exists ───────────────────────────────────────

from backend.agents.tools import _reject_if_destroys_existing_work  # noqa: E402


class TestAWriteMustNotObliterateRealWork:
    """The real incident: a run wrote a genuine 26,343-byte index.html, spent three rounds searching
    the repository, then called write_file on the same path with the literal 11 bytes "PLACEHOLDER"
    — apparently intending to rebuild the page section by section. The good file was gone and
    nothing objected. The plan's validator had already accepted the real file, so the task had
    passed; the destruction happened afterwards, silently, and the run carried on as though the
    artifact still existed.

    write_file is whole-file replacement, so this is the only moment the previous content still
    exists to compare against.
    """

    def _existing(self, tmp_path, size: int):
        (tmp_path / "index.html").write_text("x" * size, encoding="utf-8")
        return tmp_path

    def test_replacing_a_real_file_with_a_placeholder_is_refused(self, tmp_path):
        root = self._existing(tmp_path, 26_343)
        rejection = _reject_if_destroys_existing_work(root, "index.html", "PLACEHOLDER")
        assert rejection is not None
        assert "26343" in rejection and "destroying work" in rejection

    def test_the_refusal_tells_the_model_what_to_do_instead(self, tmp_path):
        # A rejection the model cannot act on just becomes another stalled round.
        root = self._existing(tmp_path, 26_343)
        rejection = _reject_if_destroys_existing_work(root, "index.html", "PLACEHOLDER")
        assert "edit_file" in rejection
        assert "read_file" in rejection

    def test_a_genuine_rewrite_is_allowed(self, tmp_path):
        # Real refactors shrink a file by a third, occasionally by half. The guard must not make
        # legitimate rewriting impossible — that would be a worse failure than the one it prevents.
        root = self._existing(tmp_path, 26_343)
        assert _reject_if_destroys_existing_work(root, "index.html", "y" * 13_000) is None

    def test_growing_a_file_is_always_allowed(self, tmp_path):
        root = self._existing(tmp_path, 26_343)
        assert _reject_if_destroys_existing_work(root, "index.html", "y" * 40_000) is None

    def test_a_brand_new_file_is_never_blocked(self, tmp_path):
        assert _reject_if_destroys_existing_work(tmp_path, "new.html", "tiny") is None

    def test_a_small_existing_file_is_not_protected(self, tmp_path):
        # Replacing a 40-byte stub with a 2-byte one is not the failure being guarded against, and
        # treating it as one would block ordinary scaffolding.
        root = self._existing(tmp_path, 40)
        assert _reject_if_destroys_existing_work(root, "index.html", "y") is None

    def test_a_failed_stat_never_blocks_the_write(self, tmp_path):
        # Fail open: this guard is a safety net, and a safety net that blocks real work when it
        # cannot see clearly is worse than no net.
        assert _reject_if_destroys_existing_work(tmp_path, "nope/../../x.html", "tiny") is None

    def test_non_string_content_is_ignored(self, tmp_path):
        root = self._existing(tmp_path, 26_343)
        assert _reject_if_destroys_existing_work(root, "index.html", None) is None
