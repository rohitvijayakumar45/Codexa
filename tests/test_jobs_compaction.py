"""Tests for backend/agents/jobs.py's _compact_stale_payloads — specifically the graph-anchored
grace period added on top of the original flat round-count rule (backend/agents/context_window.py)."""

from types import SimpleNamespace
from uuid import uuid4

from backend.agents.jobs import (
    _COMPACTED_MARK,
    _LARGE_ASSISTANT_TEXT_CHARS,
    _STALE_AFTER_ROUNDS,
    _compact_stale_payloads,
)


def _write_file_call(path: str, content: str) -> dict:
    return {
        "role": "assistant", "content": "",
        "tool_calls": [{
            "id": "tc1", "type": "function",
            "function": {"name": "write_file", "arguments": f'{{"path": "{path}", "content": "{content}"}}'},
        }],
    }


def _file_node(path: str, repository: str):
    return SimpleNamespace(id=uuid4(), node_type="File", properties={"path": path, "repository": repository})


def _edge(from_id, to_id, edge_type="imports"):
    return SimpleNamespace(from_node_id=from_id, to_node_id=to_id, edge_type=edge_type, confidence=1.0)


class FakeGraph:
    def __init__(self, nodes, edges):
        self._nodes = nodes
        self._edges = edges

    def list_nodes(self):
        return self._nodes

    def list_edges_at(self):
        return self._edges


_LONG_CONTENT = "x" * 300  # over the 200-char compaction threshold


class TestCompactStalePayloadsWithoutGraph:
    def test_compacts_on_the_flat_schedule_when_no_graph_is_given(self):
        messages = [_write_file_call("a.py", _LONG_CONTENT)]
        message_rounds = [0]

        _compact_stale_payloads(messages, message_rounds, _STALE_AFTER_ROUNDS)  # graph=None (default)

        args = messages[0]["tool_calls"][0]["function"]["arguments"]
        assert _COMPACTED_MARK in args

    def test_does_not_compact_before_the_flat_threshold(self):
        messages = [_write_file_call("a.py", _LONG_CONTENT)]
        message_rounds = [0]

        _compact_stale_payloads(messages, message_rounds, _STALE_AFTER_ROUNDS - 1)

        args = messages[0]["tool_calls"][0]["function"]["arguments"]
        assert _COMPACTED_MARK not in args


class TestCompactStalePayloadsWithGraph:
    def test_file_in_current_blast_radius_gets_extended_grace(self):
        # a.py is the file the model most recently touched; b.py imports a.py, so it's still in the
        # radius — its stale write_file payload should survive past the normal threshold.
        a_node = _file_node("a.py", "repo")
        b_node = _file_node("b.py", "repo")
        graph = FakeGraph(nodes=[a_node, b_node], edges=[_edge(b_node.id, a_node.id, "imports")])

        messages = [
            _write_file_call("b.py", _LONG_CONTENT),
            _write_file_call("a.py", "recent edit"),  # anchor: most recently touched
        ]
        message_rounds = [0, 0]

        # Past the normal threshold, but b.py is protected by its graph relevance to the anchor.
        _compact_stale_payloads(messages, message_rounds, _STALE_AFTER_ROUNDS, graph=graph, repository="repo")

        args = messages[0]["tool_calls"][0]["function"]["arguments"]
        assert _COMPACTED_MARK not in args, "a file still in the blast radius should not compact on the normal schedule"

    def test_unrelated_file_compacts_on_the_normal_schedule_even_with_a_graph(self):
        a_node = _file_node("a.py", "repo")
        unrelated_node = _file_node("unrelated.py", "repo")
        graph = FakeGraph(nodes=[a_node, unrelated_node], edges=[])  # no edge connecting them

        messages = [
            _write_file_call("unrelated.py", _LONG_CONTENT),
            _write_file_call("a.py", "recent edit"),
        ]
        message_rounds = [0, 0]

        _compact_stale_payloads(messages, message_rounds, _STALE_AFTER_ROUNDS, graph=graph, repository="repo")

        args = messages[0]["tool_calls"][0]["function"]["arguments"]
        assert _COMPACTED_MARK in args, "a file with no graph relevance to the anchor should compact normally"

    def test_protected_file_eventually_compacts_once_grace_period_also_elapses(self):
        a_node = _file_node("a.py", "repo")
        b_node = _file_node("b.py", "repo")
        graph = FakeGraph(nodes=[a_node, b_node], edges=[_edge(b_node.id, a_node.id, "imports")])

        messages = [
            _write_file_call("b.py", _LONG_CONTENT),
            _write_file_call("a.py", "recent edit"),
        ]
        message_rounds = [0, 0]

        far_future_round = _STALE_AFTER_ROUNDS * 10
        _compact_stale_payloads(messages, message_rounds, far_future_round, graph=graph, repository="repo")

        args = messages[0]["tool_calls"][0]["function"]["arguments"]
        assert _COMPACTED_MARK in args, "protection is extended grace, not permanent immunity"

    def test_a_graph_lookup_failure_falls_back_to_the_flat_schedule(self):
        class BrokenGraph:
            def list_nodes(self):
                raise RuntimeError("graph unavailable")

            def list_edges_at(self):
                raise RuntimeError("graph unavailable")

        messages = [_write_file_call("a.py", _LONG_CONTENT)]
        message_rounds = [0]

        _compact_stale_payloads(messages, message_rounds, _STALE_AFTER_ROUNDS, graph=BrokenGraph(), repository="repo")

        args = messages[0]["tool_calls"][0]["function"]["arguments"]
        assert _COMPACTED_MARK in args, "a broken graph lookup must never block the underlying compaction"


class TestCompactLargePlainAssistantText:
    """Regression coverage for a live cost bug: a model that narrated a whole file's contents as
    plain chat text (instead of calling write_file) left that wall of text in history at full size
    forever — re-sent on every round of every later job in the same conversation, the single
    largest driver behind one job's cumulative prompt tokens reaching ~187k across 7 rounds."""

    def test_large_stale_assistant_reply_compacts(self):
        big_text = "x" * (_LARGE_ASSISTANT_TEXT_CHARS + 500)
        messages = [{"role": "assistant", "content": big_text}]
        message_rounds = [0]

        _compact_stale_payloads(messages, message_rounds, _STALE_AFTER_ROUNDS)

        assert _COMPACTED_MARK in messages[0]["content"]

    def test_large_assistant_reply_not_yet_stale_is_left_alone(self):
        big_text = "x" * (_LARGE_ASSISTANT_TEXT_CHARS + 500)
        messages = [{"role": "assistant", "content": big_text}]
        message_rounds = [0]

        _compact_stale_payloads(messages, message_rounds, _STALE_AFTER_ROUNDS - 1)

        assert messages[0]["content"] == big_text

    def test_short_stale_assistant_reply_is_never_compacted(self):
        # Ordinary short replies must never be touched, however old - only a wall-of-text dump is.
        short_text = "Done — created the file."
        messages = [{"role": "assistant", "content": short_text}]
        message_rounds = [0]

        _compact_stale_payloads(messages, message_rounds, _STALE_AFTER_ROUNDS * 10)

        assert messages[0]["content"] == short_text

    def test_a_message_with_tool_calls_is_handled_by_the_tool_call_branch_not_this_one(self):
        # An assistant message WITH tool_calls has content="" per the OpenAI shape - must not be
        # miscompacted by the plain-text branch (it's excluded by the `not tool_calls` guard).
        messages = [{
            "role": "assistant", "content": "",
            "tool_calls": [{"id": "tc1", "type": "function",
                             "function": {"name": "write_file", "arguments": '{"path": "a.py", "content": "x"}'}}],
        }]
        message_rounds = [0]

        _compact_stale_payloads(messages, message_rounds, _STALE_AFTER_ROUNDS * 10)

        assert messages[0]["content"] == ""  # untouched by the plain-text branch

    def test_already_compacted_text_is_not_recompacted(self):
        already = f"{_COMPACTED_MARK} — 9000 chars, already written to disk.]"
        messages = [{"role": "assistant", "content": already}]
        message_rounds = [0]

        _compact_stale_payloads(messages, message_rounds, _STALE_AFTER_ROUNDS * 10)

        assert messages[0]["content"] == already


def _screenshot_followup(image_b64: str = "AAAA") -> dict:
    return {
        "role": "user",
        "content": [
            {"type": "text", "text": "Here is a screenshot of the current state."},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
        ],
    }


class TestCompactStaleScreenshotVisionMessage:
    """A base64 screenshot is the heaviest payload type that can land in message history — worse
    per-round than any text blob above. Once stale, it must collapse like everything else."""

    def test_stale_screenshot_message_compacts(self):
        messages = [_screenshot_followup()]
        message_rounds = [0]

        _compact_stale_payloads(messages, message_rounds, _STALE_AFTER_ROUNDS)

        assert messages[0]["content"] == (
            f"{_COMPACTED_MARK} — a screenshot was shown here and already reviewed. "
            "Call screenshot again if you need to see the current state.]"
        )

    def test_screenshot_message_not_yet_stale_is_left_alone(self):
        messages = [_screenshot_followup()]
        message_rounds = [0]

        _compact_stale_payloads(messages, message_rounds, _STALE_AFTER_ROUNDS - 1)

        assert isinstance(messages[0]["content"], list)
        assert any(b.get("type") == "image_url" for b in messages[0]["content"])

    def test_user_message_with_list_content_but_no_image_is_left_alone(self):
        # e.g. a plain multi-block text message - must not be swept up by the image branch.
        messages = [{"role": "user", "content": [{"type": "text", "text": "just text, no image"}]}]
        message_rounds = [0]

        _compact_stale_payloads(messages, message_rounds, _STALE_AFTER_ROUNDS * 10)

        assert messages[0]["content"] == [{"type": "text", "text": "just text, no image"}]

    def test_plain_string_user_message_is_untouched_by_the_image_branch(self):
        messages = [{"role": "user", "content": "just a normal chat message"}]
        message_rounds = [0]

        _compact_stale_payloads(messages, message_rounds, _STALE_AFTER_ROUNDS * 10)

        assert messages[0]["content"] == "just a normal chat message"
