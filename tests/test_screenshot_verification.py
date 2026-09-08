"""Tests for the static-file visual-verification fix (backend/agents/tools.py:
_start_dev_server, _screenshot_structured, execute_tool's screenshot dispatch).

Regression coverage for a real, observed failure: a UI build wrote a real, substantial file but
the required "screenshot before declaring done" step failed outright for a static single-HTML-file
project (start_dev_server demanded a package.json that will never exist for that kind of artifact),
so the model never actually looked at its own output before calling the task complete.
"""

from unittest.mock import patch

from backend.agents.tools import _start_dev_server, _screenshot_structured, execute_tool


class TestStartDevServerStaticFileHandling:
    def test_static_html_entry_returns_a_usable_file_url_not_an_error(self, tmp_path, monkeypatch):
        (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
        with patch("backend.agents.tools.repo_root", return_value=tmp_path):
            result = _start_dev_server("demo-repo")

        assert "No package.json" in result  # still says why - just doesn't dead-end there
        assert "file:" in result
        assert "index.html" in result

    def test_no_package_json_and_no_static_entry_still_errors_clearly(self, tmp_path):
        with patch("backend.agents.tools.repo_root", return_value=tmp_path):
            result = _start_dev_server("demo-repo")

        assert "No package.json" in result
        assert "no command" not in result.lower() or "provide a command" in result

    def test_package_json_takes_priority_over_a_static_entry(self, tmp_path):
        (tmp_path / "package.json").write_text('{"scripts": {"dev": "vite"}}', encoding="utf-8")
        (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
        with patch("backend.agents.tools.repo_root", return_value=tmp_path), \
             patch("backend.agents.tools.subprocess.Popen") as mock_popen:
            mock_popen.return_value.pid = 4242
            result = _start_dev_server("demo-repo")

        assert "PID 4242" in result
        mock_popen.assert_called_once()
        assert mock_popen.call_args.args[0] == "vite"


class TestScreenshotStructured:
    def test_missing_playwright_returns_text_only_no_bytes(self, tmp_path):
        with patch("backend.agents.tools.repo_root", return_value=tmp_path), \
             patch.dict("sys.modules", {"playwright.sync_api": None}):
            text, png = _screenshot_structured("demo-repo")

        assert png is None
        assert "Playwright" in text


class TestExecuteToolScreenshotVisionWiring:
    def test_vision_capable_model_gets_screenshot_stashed_in_context(self, tmp_path):
        fake_png = b"\x89PNG fake bytes"
        with patch("backend.agents.tools._screenshot_structured", return_value=("Screenshot saved: x", fake_png)), \
             patch("backend.agents.tools.litellm.supports_vision", return_value=True):
            ctx: dict = {}
            execute_tool(
                "screenshot", {"url": "file:///x/index.html"}, "demo-repo",
                context=ctx, model="gemini/gemini-3.7-flash",
            )

        assert "screenshot_b64" in ctx
        import base64
        assert base64.b64decode(ctx["screenshot_b64"]) == fake_png

    def test_non_vision_model_gets_no_image_stashed(self, tmp_path):
        fake_png = b"\x89PNG fake bytes"
        with patch("backend.agents.tools._screenshot_structured", return_value=("Screenshot saved: x", fake_png)), \
             patch("backend.agents.tools.litellm.supports_vision", return_value=False):
            ctx: dict = {}
            execute_tool(
                "screenshot", {"url": "file:///x/index.html"}, "demo-repo",
                context=ctx, model="groq/openai/gpt-oss-20b",
            )

        assert "screenshot_b64" not in ctx

    def test_no_model_given_never_crashes_and_skips_the_image(self, tmp_path):
        fake_png = b"\x89PNG fake bytes"
        with patch("backend.agents.tools._screenshot_structured", return_value=("Screenshot saved: x", fake_png)):
            ctx: dict = {}
            result = execute_tool("screenshot", {"url": "file:///x/index.html"}, "demo-repo", context=ctx)

        assert "screenshot_b64" not in ctx
        assert "Screenshot saved" in result

    def test_failed_screenshot_never_stashes_anything(self, tmp_path):
        with patch("backend.agents.tools._screenshot_structured", return_value=("Screenshot failed: boom", None)), \
             patch("backend.agents.tools.litellm.supports_vision", return_value=True):
            ctx: dict = {}
            execute_tool(
                "screenshot", {"url": "file:///x/index.html"}, "demo-repo",
                context=ctx, model="gemini/gemini-3.7-flash",
            )

        assert "screenshot_b64" not in ctx

    def test_a_vision_support_lookup_failure_never_blocks_the_text_result(self, tmp_path):
        fake_png = b"\x89PNG fake bytes"
        with patch("backend.agents.tools._screenshot_structured", return_value=("Screenshot saved: x", fake_png)), \
             patch("backend.agents.tools.litellm.supports_vision", side_effect=RuntimeError("boom")):
            ctx: dict = {}
            result = execute_tool(
                "screenshot", {"url": "file:///x/index.html"}, "demo-repo",
                context=ctx, model="gemini/gemini-3.7-flash",
            )

        assert "screenshot_b64" not in ctx
        assert "Screenshot saved" in result
