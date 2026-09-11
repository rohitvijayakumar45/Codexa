"""Tests for lint-on-write: JavaScript syntax checking on write_file/edit_file, with auto-revert.

The mechanism comes from reading SWE-agent's actual edit tool (tools/windowed_edit_linting/bin/edit)
rather than a description of it: lint BEFORE the write, lint AFTER, and only ever act on errors the
write itself introduced. That distinction is the whole point — a file with pre-existing problems
elsewhere must not get blocked over them, and fixing an old bug must never look like introducing a
new one. Scoped to JS syntax specifically (via `node --check`, parse-only, nothing executes) rather
than HTML well-formedness: a single JS syntax error silently kills every interactive feature on the
page, which is the failure this platform's whole benchmark history keeps producing, whereas browsers
are forgiving enough of malformed HTML that it rarely breaks anything the way it looks like it might.
"""

from __future__ import annotations

import shutil

import pytest

from backend.agents.tools import (
    _extract_inline_scripts,
    _js_syntax_errors,
    _lint_javascript_regressions,
    execute_tool,
)

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="requires node on PATH")


# ── the primitives ──────────────────────────────────────────────────────────


class TestExtractingInlineScripts:
    def test_finds_an_inline_script_body(self):
        html = "<html><body><script>const x = 1;</script></body></html>"
        assert _extract_inline_scripts(html) == ["const x = 1;"]

    def test_skips_external_scripts(self):
        html = '<script src="app.js"></script>'
        assert _extract_inline_scripts(html) == []

    def test_skips_json_and_ldjson_payloads(self):
        html = (
            '<script type="application/json">{"a": 1}</script>'
            '<script type="application/ld+json">{}</script>'
        )
        assert _extract_inline_scripts(html) == []

    def test_a_module_script_is_still_checked(self):
        html = '<script type="module">const y = 2;</script>'
        assert _extract_inline_scripts(html) == ["const y = 2;"]

    def test_multiple_inline_scripts_are_all_returned(self):
        html = "<script>a();</script><script>b();</script>"
        assert _extract_inline_scripts(html) == ["a();", "b();"]

    def test_an_empty_script_body_is_skipped(self):
        assert _extract_inline_scripts("<script></script>") == []


class TestSyntaxErrorDetection:
    def test_clean_code_has_no_errors(self):
        assert _js_syntax_errors("function f(x) { return x + 1; }") == set()

    def test_broken_code_reports_an_error(self):
        errors = _js_syntax_errors("function f( { return 1; }")
        assert errors
        assert any("Error" in e for e in errors)

    def test_empty_code_is_clean(self):
        assert _js_syntax_errors("") == set()

    def test_the_same_error_normalises_to_the_same_message_despite_shifting_lines(self):
        # Line numbers shift with every edit; the comparison used to decide "is this a NEW error"
        # must not be fooled by that, or every edit would look like a fresh problem forever.
        a = _js_syntax_errors("function f( {}")
        b = _js_syntax_errors("\n\n\n\nfunction f( {}")
        assert a == b


class TestRegressionDetection:
    def test_a_brand_new_broken_file_is_reported(self):
        msg = _lint_javascript_regressions(None, "<script>function f( {}</script>", path="index.html")
        assert msg is not None
        assert "Error" in msg

    def test_a_brand_new_clean_file_reports_nothing(self):
        assert _lint_javascript_regressions(None, "<script>const x = 1;</script>", path="index.html") is None

    def test_an_unchanged_pre_existing_error_is_not_flagged(self):
        # The entire point of diffing before-vs-after: a file that already had this exact problem
        # must not be treated as though this write caused it.
        broken = "<script>function f( {}</script>"
        assert _lint_javascript_regressions(broken, broken, path="index.html") is None

    def test_fixing_a_pre_existing_error_reports_nothing(self):
        before = "<script>function f( {}</script>"
        after = "<script>function f() {}</script>"
        assert _lint_javascript_regressions(before, after, path="index.html") is None

    def test_introducing_a_new_error_into_a_previously_clean_file_is_caught(self):
        before = "<script>const x = 1;</script>"
        after = "<script>function f( {}</script>"
        msg = _lint_javascript_regressions(before, after, path="index.html")
        assert msg is not None
        assert "new" in msg.lower()

    def test_a_second_unrelated_pre_existing_error_does_not_mask_reporting_the_new_one(self):
        # Two independent script blocks, one broken before and after (must stay silent about it),
        # one that only broke on this write (must be reported).
        before = "<script>already( broken</script><script>const ok = 1;</script>"
        after = "<script>already( broken</script><script>still( broken</script>"
        msg = _lint_javascript_regressions(before, after, path="index.html")
        assert msg is not None

    def test_non_html_non_js_files_are_never_checked(self):
        assert _lint_javascript_regressions(None, "not even close to valid js {{{", path="styles.css") is None

    def test_bare_js_files_are_checked_directly_without_html_extraction(self):
        msg = _lint_javascript_regressions(None, "function f( {}", path="app.js")
        assert msg is not None


# ── wired into the real tools, with real revert ─────────────────────────────


@pytest.fixture
def repo(tmp_path, monkeypatch):
    import backend.agents.tools as tools_mod
    monkeypatch.setattr(tools_mod, "repo_root", lambda repository: tmp_path)
    return tmp_path


class TestWriteFileRevertsOnANewSyntaxError:
    def test_a_syntax_error_in_a_fresh_file_is_reported_but_the_file_stands(self, repo):
        # Nothing existed before, so there is nothing to revert TO — the model's attempt is left on
        # disk (still its best try) with the problem named, rather than silently discarded.
        result = execute_tool(
            "write_file", {"path": "index.html", "content": "<script>function f( {}</script>"}, "demo",
        )
        assert "Error" in result
        assert (repo / "index.html").exists()

    def test_a_clean_write_is_not_flagged(self, repo):
        result = execute_tool(
            "write_file", {"path": "index.html", "content": "<script>const x = 1;</script>"}, "demo",
        )
        assert "Error" not in result
        assert (repo / "index.html").read_text(encoding="utf-8") == "<script>const x = 1;</script>"

    def test_overwriting_a_clean_file_with_a_broken_one_reverts(self, repo):
        (repo / "index.html").write_text("<script>const good = 1;</script>", encoding="utf-8")
        result = execute_tool(
            "write_file", {"path": "index.html", "content": "<script>function f( {}</script>"}, "demo",
        )
        assert "REVERTED" in result
        # The file must be back to exactly what it was — not the broken content, not empty.
        assert (repo / "index.html").read_text(encoding="utf-8") == "<script>const good = 1;</script>"

    def test_overwriting_a_broken_file_with_an_equally_broken_one_does_not_revert(self, repo):
        # Same underlying error, still present — this write did not make anything worse, so it
        # must be allowed to stand even though the file is not clean.
        broken = "<script>function f( {}</script>"
        (repo / "index.html").write_text(broken, encoding="utf-8")
        result = execute_tool("write_file", {"path": "index.html", "content": broken}, "demo")
        assert "REVERTED" not in result

    def test_a_non_html_file_is_never_reverted_over_js_content(self, repo):
        # Regression guard for scope creep: this mechanism must stay confined to .html/.js/.mjs/.cjs.
        result = execute_tool(
            "write_file", {"path": "notes.txt", "content": "this isn't javascript at all {{{"}, "demo",
        )
        assert "REVERTED" not in result
        assert (repo / "notes.txt").exists()


class TestEditFileRevertsOnANewSyntaxError:
    def test_an_edit_that_introduces_a_syntax_error_is_reverted(self, repo):
        (repo / "index.html").write_text("<script>function f() { return 1; }</script>", encoding="utf-8")
        result = execute_tool("edit_file", {
            "path": "index.html",
            "old_text": "function f() { return 1; }",
            "new_text": "function f( { return 1; }",
        }, "demo")
        assert "REVERTED" in result
        assert (repo / "index.html").read_text(encoding="utf-8") == "<script>function f() { return 1; }</script>"

    def test_a_clean_edit_is_not_reverted(self, repo):
        (repo / "index.html").write_text("<script>const x = 1;</script>", encoding="utf-8")
        result = execute_tool("edit_file", {
            "path": "index.html", "old_text": "const x = 1;", "new_text": "const x = 2;",
        }, "demo")
        assert "REVERTED" not in result
        assert (repo / "index.html").read_text(encoding="utf-8") == "<script>const x = 2;</script>"

    def test_the_revert_restores_the_whole_file_not_just_the_edited_span(self, repo):
        # Deliberately not implemented as "reverse the old_text/new_text swap" — that would require
        # new_text to be unique in the file, which is not guaranteed (it could coincidentally match
        # a second, unrelated spot after the edit). A full-content restore from the pre-edit capture
        # sidesteps that failure mode entirely.
        original = "<p>keep this</p><script>function f() { return 1; }</script><p>and this</p>"
        (repo / "index.html").write_text(original, encoding="utf-8")
        result = execute_tool("edit_file", {
            "path": "index.html",
            "old_text": "function f() { return 1; }",
            "new_text": "function f( { return 1; }",
        }, "demo")
        assert "REVERTED" in result
        assert (repo / "index.html").read_text(encoding="utf-8") == original
