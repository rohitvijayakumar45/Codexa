"""Tests for the reverse-dependency BFS (backend/agents/impact.py: blast_radius_ids), factored out
of the /agents/impact endpoint so backend/agents/jobs.py's context compaction can reuse the same
traversal as a "what's currently relevant" oracle (see test_jobs_context_window.py)."""

from types import SimpleNamespace
from uuid import uuid4

from backend.agents.impact import blast_radius_ids


def _edge(from_id, to_id, edge_type, confidence=1.0):
    return SimpleNamespace(from_node_id=from_id, to_node_id=to_id, edge_type=edge_type, confidence=confidence)


class FakeGraph:
    def __init__(self, edges):
        self._edges = edges

    def list_edges_at(self):
        return self._edges


class TestBlastRadiusIds:
    def test_transitive_reach_through_a_chain(self):
        # a -> b -> c (a imports b, b imports c). Changing c should reach b (depth 1) and a (depth 2).
        a, b, c = uuid4(), uuid4(), uuid4()
        graph = FakeGraph([_edge(a, b, "imports"), _edge(b, c, "imports")])

        radius = blast_radius_ids({c}, graph=graph, max_depth=3)

        assert radius.affected_ids == {a, b}
        assert radius.best_depth[b] == 1
        assert radius.best_depth[a] == 2
        assert radius.parent[a] == b
        assert radius.parent[b] == c

    def test_max_depth_caps_the_traversal(self):
        a, b, c = uuid4(), uuid4(), uuid4()
        graph = FakeGraph([_edge(a, b, "imports"), _edge(b, c, "imports")])

        radius = blast_radius_ids({c}, graph=graph, max_depth=1)

        assert radius.affected_ids == {b}
        assert a not in radius.affected_ids

    def test_confidence_propagates_as_the_minimum_along_the_path(self):
        a, b, c = uuid4(), uuid4(), uuid4()
        graph = FakeGraph([_edge(a, b, "imports", confidence=1.0), _edge(b, c, "imports", confidence=0.4)])

        radius = blast_radius_ids({c}, graph=graph, max_depth=3)

        assert radius.path_confidence[b] == 0.4
        assert radius.path_confidence[a] == 0.4  # the weakest link on the path, not the last edge alone

    def test_edge_types_outside_the_dependency_set_are_ignored(self):
        # "documents" isn't one of _DEP_EDGES (imports/depends_on/calls/flows_into/correlates_with)
        # — an edge of an untracked type must never propagate the blast radius.
        a, c = uuid4(), uuid4()
        graph = FakeGraph([_edge(a, c, "documents")])

        radius = blast_radius_ids({c}, graph=graph, max_depth=3)

        assert radius.affected_ids == set()

    def test_multiple_targets_are_explored_together(self):
        a, b, target1, target2 = uuid4(), uuid4(), uuid4(), uuid4()
        graph = FakeGraph([_edge(a, target1, "calls"), _edge(b, target2, "calls")])

        radius = blast_radius_ids({target1, target2}, graph=graph, max_depth=2)

        assert radius.affected_ids == {a, b}

    def test_target_nodes_are_never_included_in_their_own_affected_set(self):
        a, target = uuid4(), uuid4()
        graph = FakeGraph([_edge(a, target, "imports"), _edge(target, a, "imports")])  # a cycle

        radius = blast_radius_ids({target}, graph=graph, max_depth=3)

        assert target not in radius.affected_ids
        assert a in radius.affected_ids

    def test_no_edges_means_no_affected_nodes(self):
        target = uuid4()
        graph = FakeGraph([])

        radius = blast_radius_ids({target}, graph=graph, max_depth=3)

        assert radius.affected_ids == set()


# ── the analysis must not look outside the repository being changed ────────────

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.agents.impact import create_impact_router  # noqa: E402


def _node(label: str, repository: str):
    """Minimal stand-in for a GraphNode. Only the fields _resolve_targets and the endpoint read."""
    return SimpleNamespace(
        id=uuid4(), label=label, node_type="CodeSymbol", name=label,
        stable_id=f"symbol://{repository}/src/{label}.tsx#{label}",
        properties={"repository": repository, "path": f"src/{label}.tsx", "name": label},
    )


class _ScopedGraph:
    def __init__(self, nodes):
        self._nodes = nodes

    def list_nodes(self):
        return self._nodes

    def list_edges_at(self, at_time=None):
        return []


def _client(nodes) -> TestClient:
    app = FastAPI()
    app.include_router(create_impact_router(graph=_ScopedGraph(nodes), planner=None))
    return TestClient(app)


class TestImpactIsScopedToOneRepository:
    """A real report: a user created a brand-new empty repository, asked for a single HTML file, and
    was shown a blast-radius card whose change targets were `backend/graph`, `Board` and `Header` —
    symbols belonging to Codexa's own source and to other loaded projects, none of which their
    change could possibly touch.

    The graph holds every loaded repository at once and the endpoint was searching all of them. A
    blast radius computed over the wrong repository is worse than none at all, because it looks
    authoritative: it invites someone to weigh a risk that does not exist against work that cannot
    cause it.
    """

    NODES = [
        _node("Board", "codexa-os"),
        _node("Header", "codexa-os"),
        _node("Dashboard", "other-project"),
    ]

    def test_a_new_empty_repository_reports_nothing_to_affect(self):
        res = _client(self.NODES).post(
            "/agents/impact",
            json={"description": "update the Board header layout", "repository": "brand-new-repo"},
        ).json()
        assert res["resolved"] is False
        assert res["targets"] == []
        assert res["affected_count"] == 0

    def test_symbols_from_another_repository_are_never_named_as_targets(self):
        res = _client(self.NODES).post(
            "/agents/impact",
            json={"description": "update the Board and Header components", "repository": "brand-new-repo"},
        ).json()
        labels = {t["label"] for t in res["targets"]}
        assert "Board" not in labels and "Header" not in labels

    def test_it_still_resolves_within_the_correct_repository(self):
        # The scoping must not break the feature it protects — a real change in a real project still
        # gets a real answer.
        res = _client(self.NODES).post(
            "/agents/impact",
            json={"description": "update the Board component", "repository": "codexa-os"},
        ).json()
        assert res["resolved"] is True
        assert "Board" in {t["label"] for t in res["targets"]}

    def test_omitting_the_repository_keeps_the_old_whole_graph_behaviour(self):
        # Backwards compatible: the field is optional, and an older caller that does not send it
        # behaves exactly as before rather than silently analysing nothing.
        res = _client(self.NODES).post(
            "/agents/impact", json={"description": "update the Board component"},
        ).json()
        assert res["resolved"] is True
