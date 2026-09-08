"""Tests for the coupling x incident-history join (backend/agents/impact.py:
_coupling_incident_risks) and the file-linkage that makes it possible
(backend/trust_safety/incident.py: affected_file_ids). Two structures — git-mined change coupling
and incident learning — that already existed independently in this graph and were never queried
together before this."""

from types import SimpleNamespace
from uuid import uuid4

from backend.agents.impact import _coupling_incident_risks


def _node(node_id, node_type, **properties):
    return SimpleNamespace(id=node_id, node_type=node_type, properties=properties)


def _edge(from_id, to_id, edge_type):
    return SimpleNamespace(from_node_id=from_id, to_node_id=to_id, edge_type=edge_type)


class TestCouplingIncidentRisks:
    def test_finds_incident_linked_to_a_coupled_file_in_the_subgraph(self):
        file_a, root_cause, incident, prevention = uuid4(), uuid4(), uuid4(), uuid4()
        nodes_by_id = {
            file_a: _node(file_a, "File", path="risky.py"),
            root_cause: _node(root_cause, "CausalEvent", event_kind="root_cause", summary="missing null check"),
            incident: _node(incident, "CausalEvent", event_kind="incident", summary="prod crash on null user"),
            prevention: _node(prevention, "PreventionRule", summary="always null-check user before use"),
        }
        edges = [
            _edge(file_a, root_cause, "correlates_with"),
            _edge(root_cause, incident, "causes"),
            _edge(prevention, root_cause, "mitigates"),
        ]

        risks = _coupling_incident_risks(nodes_by_id, {file_a}, edges)

        assert len(risks) == 1
        assert risks[0].file_label == "risky.py"
        assert risks[0].root_cause_summary == "missing null check"
        assert risks[0].incident_summary == "prod crash on null user"
        assert risks[0].prevention_rule == "always null-check user before use"

    def test_file_outside_the_subgraph_is_ignored(self):
        file_a, root_cause = uuid4(), uuid4()
        nodes_by_id = {
            file_a: _node(file_a, "File", path="risky.py"),
            root_cause: _node(root_cause, "CausalEvent", event_kind="root_cause", summary="x"),
        }
        edges = [_edge(file_a, root_cause, "correlates_with")]

        risks = _coupling_incident_risks(nodes_by_id, set(), edges)  # file_a not in the subgraph

        assert risks == []

    def test_ordinary_file_to_file_coupling_is_never_mistaken_for_incident_linkage(self):
        file_a, file_b = uuid4(), uuid4()
        nodes_by_id = {
            file_a: _node(file_a, "File", path="a.py"),
            file_b: _node(file_b, "File", path="b.py"),
        }
        edges = [_edge(file_a, file_b, "correlates_with")]  # plain git-coupling, not an incident edge

        risks = _coupling_incident_risks(nodes_by_id, {file_a}, edges)

        assert risks == []

    def test_incident_with_no_prevention_rule_still_surfaces_with_none(self):
        file_a, root_cause, incident = uuid4(), uuid4(), uuid4()
        nodes_by_id = {
            file_a: _node(file_a, "File", path="risky.py"),
            root_cause: _node(root_cause, "CausalEvent", event_kind="root_cause", summary="x"),
            incident: _node(incident, "CausalEvent", event_kind="incident", summary="y"),
        }
        edges = [_edge(file_a, root_cause, "correlates_with"), _edge(root_cause, incident, "causes")]

        risks = _coupling_incident_risks(nodes_by_id, {file_a}, edges)

        assert risks[0].prevention_rule is None

    def test_duplicate_edges_do_not_duplicate_the_risk(self):
        file_a, root_cause, incident = uuid4(), uuid4(), uuid4()
        nodes_by_id = {
            file_a: _node(file_a, "File", path="risky.py"),
            root_cause: _node(root_cause, "CausalEvent", event_kind="root_cause", summary="x"),
            incident: _node(incident, "CausalEvent", event_kind="incident", summary="y"),
        }
        edges = [
            _edge(file_a, root_cause, "correlates_with"),
            _edge(file_a, root_cause, "correlates_with"),  # e.g. re-ingested
            _edge(root_cause, incident, "causes"),
        ]

        risks = _coupling_incident_risks(nodes_by_id, {file_a}, edges)

        assert len(risks) == 1


class TestIncidentRecordingLinksAffectedFiles:
    def test_affected_file_ids_creates_correlates_with_edges_to_root_cause(self):
        from backend.graph.events import InMemoryGraphEventWriter
        from backend.graph.repository import InMemoryGraphRepository
        from backend.graph.schemas import GraphNodeCreate, GraphNodeType
        from backend.graph.service import GraphService
        from backend.trust_safety.incident import IncidentLearningRequest, IncidentLearningService

        graph = GraphService(repository=InMemoryGraphRepository(), event_writer=InMemoryGraphEventWriter())
        file_node = graph.add_node(GraphNodeCreate(
            node_type=GraphNodeType.FILE, stable_id="file://demo/risky.py", properties={"path": "risky.py"},
        ))
        service = IncidentLearningService(graph=graph)

        result = service.record(IncidentLearningRequest(
            source_artifact_id=uuid4(), incident="prod crash", root_cause="missing null check",
            fix="add null check", regression_test="test_null_user", prevention_rule="always null-check",
            confidence=0.9, affected_file_ids=[file_node.id],
        ))

        edges = graph.list_edges_at()
        linking = [e for e in edges if e.from_node_id == file_node.id and e.to_node_id == result.root_cause_node_id]
        assert len(linking) == 1
        assert linking[0].edge_type == "correlates_with"

    def test_no_affected_file_ids_creates_no_extra_edges(self):
        from backend.graph.events import InMemoryGraphEventWriter
        from backend.graph.repository import InMemoryGraphRepository
        from backend.graph.service import GraphService
        from backend.trust_safety.incident import IncidentLearningRequest, IncidentLearningService

        graph = GraphService(repository=InMemoryGraphRepository(), event_writer=InMemoryGraphEventWriter())
        service = IncidentLearningService(graph=graph)

        result = service.record(IncidentLearningRequest(
            source_artifact_id=uuid4(), incident="x", root_cause="y", fix="z",
            regression_test="t", prevention_rule="p", confidence=0.5,
        ))

        assert len(result.edge_ids) == 4  # unchanged from before affected_file_ids existed
