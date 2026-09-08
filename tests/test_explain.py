"""Tests for graph-grounded causal explanations (backend/trust_safety/explain.py).

Reuses the FakeGraph/_node/_edge pattern from tests/test_verification.py (SimpleNamespace objects
shaped like backend/graph/schemas.py's real Node/Edge) — no existing fake-graph fixture is shared
between test modules, so this is deliberately self-contained rather than importing test internals
from another test file.
"""

from types import SimpleNamespace
from uuid import uuid4

from backend.trust_safety.explain import explain_incident


def _node(node_type: str, **properties) -> SimpleNamespace:
    return SimpleNamespace(id=uuid4(), node_type=node_type, properties=properties)


def _edge(from_node, to_node, edge_type: str) -> SimpleNamespace:
    return SimpleNamespace(id=uuid4(), from_node_id=from_node.id, to_node_id=to_node.id, edge_type=edge_type)


class FakeGraph:
    def __init__(self, nodes, edges):
        self._nodes = nodes
        self._edges = edges

    def list_nodes(self):
        return self._nodes

    def list_edges_at(self):
        return self._edges


def _full_chain(tag: str):
    """Builds a complete incident -> root_cause -> fix/regression_test/prevention_rule chain,
    exactly matching what backend/trust_safety/incident.py's IncidentLearningService.record writes."""
    incident = _node("CausalEvent", event_kind="incident", summary="Prod outage", confidence=0.9, source_artifact_id=tag)
    root_cause = _node("CausalEvent", event_kind="root_cause", summary="Null pointer in handler", source_artifact_id=tag)
    fix = _node("CausalEvent", event_kind="fix", summary="Added null guard", source_artifact_id=tag)
    regression_test = _node("CausalEvent", event_kind="regression_test", summary="test_handler_rejects_null", source_artifact_id=tag)
    prevention_rule = _node("PreventionRule", summary="Require null-check lint rule", source_artifact_id=tag)

    edges = [
        _edge(root_cause, incident, "causes"),
        _edge(fix, root_cause, "mitigates"),
        _edge(regression_test, incident, "mitigates"),
        _edge(prevention_rule, root_cause, "mitigates"),
    ]
    nodes = [incident, root_cause, fix, regression_test, prevention_rule]
    return nodes, edges


class TestExplainIncident:
    def test_full_chain_produces_all_five_sentences_in_order(self):
        tag = "artifact-1"
        nodes, edges = _full_chain(tag)
        graph = FakeGraph(nodes, edges)

        result = explain_incident(tag, graph=graph)

        assert len(result.sentences) == 5
        assert "Prod outage" in result.sentences[0].text
        assert "Null pointer in handler" in result.sentences[1].text
        assert "confidence 90%" in result.sentences[1].text
        assert "Added null guard" in result.sentences[2].text
        assert "test_handler_rejects_null" in result.sentences[3].text
        assert "Require null-check lint rule" in result.sentences[4].text

    def test_narrative_is_the_joined_sentence_text(self):
        tag = "artifact-2"
        nodes, edges = _full_chain(tag)
        graph = FakeGraph(nodes, edges)

        result = explain_incident(tag, graph=graph)

        assert result.narrative == " ".join(s.text for s in result.sentences)

    def test_every_sentence_carries_its_backing_node_and_edge_ids(self):
        tag = "artifact-3"
        nodes, edges = _full_chain(tag)
        graph = FakeGraph(nodes, edges)

        result = explain_incident(tag, graph=graph)

        # The incident sentence has no incoming edge (nothing causes the top of the chain).
        assert result.sentences[0].node_ids and result.sentences[0].edge_ids == []
        # Every other sentence must cite both the node it describes and the edge connecting it in.
        for sentence in result.sentences[1:]:
            assert sentence.node_ids
            assert sentence.edge_ids

    def test_unknown_id_returns_empty_narrative_not_a_guess(self):
        tag = "artifact-4"
        nodes, edges = _full_chain(tag)
        graph = FakeGraph(nodes, edges)

        result = explain_incident("some-other-artifact-id-never-recorded", graph=graph)

        assert result.sentences == []
        assert result.narrative == "No incident record found for this id."

    def test_missing_fix_stage_omits_only_that_sentence_never_fabricates_it(self):
        tag = "artifact-5"
        incident = _node("CausalEvent", event_kind="incident", summary="Prod outage", source_artifact_id=tag)
        root_cause = _node("CausalEvent", event_kind="root_cause", summary="Null pointer", source_artifact_id=tag)
        # No fix node recorded at all.
        edges = [_edge(root_cause, incident, "causes")]
        graph = FakeGraph([incident, root_cause], edges)

        result = explain_incident(tag, graph=graph)

        texts = [s.text for s in result.sentences]
        assert not any("Fixed by" in t for t in texts)
        assert any("Prod outage" in t for t in texts)
        assert any("Null pointer" in t for t in texts)

    def test_node_present_but_edge_missing_omits_the_sentence(self):
        # A fix node exists tagged with this artifact id, but the MITIGATES edge connecting it to
        # root_cause was never written — explain_incident must not describe an unconnected node as
        # if it were part of the causal chain just because it happens to share the tag.
        tag = "artifact-6"
        incident = _node("CausalEvent", event_kind="incident", summary="Prod outage", source_artifact_id=tag)
        root_cause = _node("CausalEvent", event_kind="root_cause", summary="Null pointer", source_artifact_id=tag)
        fix = _node("CausalEvent", event_kind="fix", summary="Orphaned fix note", source_artifact_id=tag)
        edges = [_edge(root_cause, incident, "causes")]  # no fix -> root_cause edge
        graph = FakeGraph([incident, root_cause, fix], edges)

        result = explain_incident(tag, graph=graph)

        assert not any("Orphaned fix note" in s.text for s in result.sentences)

    def test_nodes_tagged_with_a_different_artifact_id_are_never_mixed_in(self):
        tag_a = "artifact-a"
        tag_b = "artifact-b"
        nodes_a, edges_a = _full_chain(tag_a)
        nodes_b, edges_b = _full_chain(tag_b)
        graph = FakeGraph(nodes_a + nodes_b, edges_a + edges_b)

        result = explain_incident(tag_a, graph=graph)

        assert len(result.sentences) == 5  # only tag_a's chain, not both combined
