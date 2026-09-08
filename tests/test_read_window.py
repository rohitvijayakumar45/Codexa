"""read_file must be able to read a whole large file, one window at a time.

The observed failure: read_file returned `_truncate(content)` — the first 6,000 characters, with no
offset parameter and no continuation. A 43,409-byte index.html was therefore visible only in its
first 14%, and a model asked to refine it had no supported way to reach the part it needed.

It routed around the tool instead: run_command with sed-style extraction, writing the file back out
as _c1.txt, _c2.txt, _chunk2.txt, _gap.txt and five more, then reading those. Thirty-four tool calls
and twenty-eight rounds to read one file, nine junk files left in the repository, the task failed
validation three times, and nothing was improved.
"""

import pytest

from backend.agents.tools import _READ_WINDOW_LINES, _read_window

BIG = "\n".join(f"line {i} content" for i in range(1, 1201))


class TestASmallFileIsUnchanged:
    def test_it_is_returned_verbatim_with_no_framing(self):
        # The overwhelmingly common case. Adding a header to every small read would be noise in
        # every prompt, and would break callers that compare content exactly.
        assert _read_window("alpha\nbeta", path="x.txt") == "alpha\nbeta"

    def test_an_empty_file_says_so_rather_than_returning_nothing(self):
        assert "empty" in _read_window("", path="x.txt")


class TestALargeFileIsWindowed:
    def test_the_first_window_starts_at_line_one(self):
        out = _read_window(BIG, path="index.html")
        assert out.splitlines()[0] == "[index.html - lines 1-400 of 1200]"

    def test_it_says_exactly_how_to_continue(self):
        # A truncation notice that does not name the next call is what sent a model to the shell.
        out = _read_window(BIG, path="index.html")
        assert 'read_file with path="index.html" and start_line=401' in out
        assert "800 more lines" in out

    def test_it_forbids_the_workaround_that_was_actually_observed(self):
        assert "Do NOT use run_command" in _read_window(BIG, path="index.html")

    def test_continuing_returns_the_next_window(self):
        out = _read_window(BIG, path="index.html", start_line=401)
        assert out.splitlines()[0] == "[index.html - lines 401-800 of 1200]"
        assert "line 401 content" in out
        assert "line 400 content" not in out

    def test_the_windows_tile_the_file_with_no_gaps_or_overlap(self):
        seen, start = [], 1
        while start <= 1200:
            out = _read_window(BIG, path="index.html", start_line=start)
            seen += [l for l in out.splitlines() if l.startswith("line ")]
            if "truncated here" not in out:
                break
            start += _READ_WINDOW_LINES
        assert seen == BIG.split("\n"), "a file must be fully readable by following the windows"

    def test_the_final_window_is_not_marked_truncated(self):
        out = _read_window(BIG, path="index.html", start_line=801)
        assert "truncated here" not in out
        assert "line 1200 content" in out


class TestEdgeCases:
    def test_reading_past_the_end_explains_itself(self):
        out = _read_window(BIG, path="index.html", start_line=9999)
        assert "past the end" in out

    def test_a_start_line_below_one_is_clamped(self):
        assert "lines 1-400" in _read_window(BIG, path="index.html", start_line=0)

    def test_one_enormous_line_cannot_blow_the_window_budget(self):
        # Minified CSS or JS is a single line of tens of thousands of characters. Returning 400 of
        # those would put more in the prompt than the whole file was worth.
        minified = "\n".join(["x" * 30_000] * 10)
        out = _read_window(minified, path="bundle.css")
        assert len(out) < 60_000
        assert "truncated here" in out

    @pytest.mark.parametrize("size", [399, 400, 401])
    def test_the_boundary_around_one_full_window_behaves(self, size):
        content = "\n".join(f"l{i}" for i in range(size))
        out = _read_window(content, path="f.txt")
        if size <= 400:
            assert "truncated here" not in out
        else:
            assert "truncated here" in out
