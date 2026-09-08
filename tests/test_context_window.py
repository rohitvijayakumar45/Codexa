"""Tests for graph-anchored context eviction (backend/agents/context_window.py)."""

import json
from types import SimpleNamespace
from uuid import uuid4

from backend.agents.context_window import _file_node_id, _latest_touched_path, relevant_paths


def _file_node(path: str, repository: str | None = None):
    props = {"path": path}
    if repository:
        props["repository"] = repository
    return SimpleNamespace(id=uuid4(), node_type="File", properties=props)


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


def _tool_call_message(name: str, **args) -> dict:
    return {
        "role": "assistant", "content": "",
        "tool_calls": [{"id": "tc1", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}],
    }


class TestLatestTouchedPath:
    def test_finds_the_most_recent_write_file_path(self):
        messages = [
            _tool_call_message("write_file", path="a.py", content="x"),
            {"role": "tool", "name": "write_file", "content": "ok"},
            _tool_call_message("write_file", path="b.py", content="y"),
        ]
        assert _latest_touched_path(messages) == "b.py"

    def test_ignores_non_file_tool_calls(self):
        messages = [
            _tool_call_message("write_file", path="a.py", content="x"),
            _tool_call_message("run_command", command="ls"),
        ]
        assert _latest_touched_path(messages) == "a.py"

    def test_returns_none_when_no_file_tool_was_ever_called(self):
        messages = [_tool_call_message("run_command", command="ls")]
        assert _latest_touched_path(messages) is None

    def test_returns_none_for_empty_messages(self):
        assert _latest_touched_path([]) is None


class TestFileNodeId:
    def test_finds_matching_file_in_repository(self):
        node = _file_node("calc.py", repository="myrepo")
        graph = FakeGraph([node], [])
        assert _file_node_id("calc.py", "myrepo", graph) == node.id

    def test_no_match_returns_none(self):
        graph = FakeGraph([_file_node("calc.py", repository="myrepo")], [])
        assert _file_node_id("missing.py", "myrepo", graph) is None

    def test_codexa_os_matches_nodes_with_no_repository_tag(self):
        # Same convention used throughout tools.py/verification.py: a node with no repository
        # property belongs to the platform's own self-referential graph.
        node = _file_node("backend/main.py")  # no repository tag
        graph = FakeGraph([node], [])
        assert _file_node_id("backend/main.py", "codexa-os", graph) == node.id


class TestRelevantPaths:
    def test_returns_none_when_no_anchor_can_be_determined(self):
        graph = FakeGraph([], [])
        assert relevant_paths([], repository="repo", graph=graph) is None

    def test_returns_none_when_anchor_path_has_no_graph_node(self):
        messages = [_tool_call_message("write_file", path="ghost.py", content="x")]
        graph = FakeGraph([], [])
        assert relevant_paths(messages, repository="repo", graph=graph) is None

    def test_includes_the_anchor_itself_and_its_blast_radius(self):
        anchor = _file_node("calc.py", repository="repo")
        neighbor = _file_node("utils.py", repository="repo")
        unrelated = _file_node("unrelated.py", repository="repo")
        graph = FakeGraph(
            nodes=[anchor, neighbor, unrelated],
            edges=[_edge(neighbor.id, anchor.id, "imports")],  # utils.py imports calc.py
        )
        messages = [_tool_call_message("write_file", path="calc.py", content="x")]

        result = relevant_paths(messages, repository="repo", graph=graph)

        assert result == {"calc.py", "utils.py"}
        assert "unrelated.py" not in result
