"""run_command must be able to run Python, on any machine, regardless of PATH.

Observed live: an agent ran `python ...` inside a fresh repo and got Windows' App Execution Alias
stub back — "Python was not found; run without arguments to install from the Microsoft Store" — with
exit code 9009, while the identical command worked from a normal shell on the same machine. The
server process inherits its launcher's PATH, and in that PATH the Store shim shadows the real
interpreter. The model cannot diagnose or route around this: it asks for Python, receives prose
about an app store, and burns rounds guessing (the same run had already resorted to doing file
writes through run_python as a workaround).

Resolving to sys.executable removes the ambiguity — the process running this code is a working
Python by definition. The risk to guard against is over-eager rewriting, so most of these tests are
about what must be left ALONE.
"""

import subprocess
import sys

from backend.agents.tools import _resolve_python


class TestRewritesRealInvocations:
    def test_python_resolves_to_this_interpreter(self):
        assert _resolve_python("python --version") == f'"{sys.executable}" --version'

    def test_python3_is_handled_too(self):
        assert _resolve_python("python3 script.py").startswith(f'"{sys.executable}"')

    def test_pip_becomes_module_invocation(self):
        # `pip` on PATH can point at a different interpreter's site-packages entirely; -m pip
        # guarantees the install lands where the resolved interpreter will look for it.
        assert _resolve_python("pip install requests") == f'"{sys.executable}" -m pip install requests'

    def test_leading_whitespace_is_preserved(self):
        assert _resolve_python("  python x.py") == f'  "{sys.executable}" x.py'

    def test_arguments_are_left_untouched(self):
        out = _resolve_python("python -m http.server 8000 --bind 127.0.0.1")
        assert out.endswith("-m http.server 8000 --bind 127.0.0.1")


class TestLeavesEverythingElseAlone:
    def test_python_as_a_search_term_is_not_a_command(self):
        assert _resolve_python("grep python README.md") == "grep python README.md"

    def test_a_longer_word_starting_with_python_is_not_rewritten(self):
        assert _resolve_python("pythonic --help") == "pythonic --help"

    def test_python_after_a_runner_is_that_runners_business(self):
        # `uv run python` deliberately resolves the interpreter itself; hijacking it would break
        # the very environment isolation the user asked for.
        assert _resolve_python("uv run python x.py") == "uv run python x.py"

    def test_unrelated_commands_pass_through(self):
        for cmd in ("npm run dev", "git status", "ls -la", "npx tsc --noEmit"):
            assert _resolve_python(cmd) == cmd

    def test_an_empty_command_is_safe(self):
        assert _resolve_python("") == ""


class TestTheResolvedCommandActuallyRuns:
    def test_it_executes_through_a_shell_the_way_run_command_does(self):
        # The end-to-end claim: whatever PATH this process inherited, the rewritten command runs.
        proc = subprocess.run(
            _resolve_python("python --version"),
            shell=True, capture_output=True, text=True, timeout=30,
        )
        assert proc.returncode == 0, proc.stderr
        assert "Python" in (proc.stdout + proc.stderr)
        # The specific failure this fixes must not reappear.
        assert "Microsoft Store" not in (proc.stdout + proc.stderr)
