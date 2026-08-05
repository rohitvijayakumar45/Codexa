from uuid import uuid4

from fastapi.testclient import TestClient

from backend.graph.schemas import GraphEdgeSourceType, GraphEdgeType, GraphNodeType
from backend.main import create_app


def test_record_intent_graph_chain_creates_cited_nodes_and_edges() -> None:
    app = create_app()
    client = TestClient(app)
    source_artifact_id = str(uuid4())

    response = client.post(
        "/memory/intent/chains",
        json={
            "source_artifact_id": source_artifact_id,
            "decision": "Use Postgres JSONB as source of truth",
            "tradeoff": "Simpler consistency model over direct graph writes",
            "rejected_alternative": "Use MongoDB",
            "confidence": 0.86,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["decision_node_id"]
    assert body["tradeoff_node_id"]
    assert body["rejected_alternative_node_id"]
    assert len(body["edge_ids"]) == 3

    repository = app.state.graph_repository
    node_types = {node.node_type for node in repository.nodes.values()}
    assert GraphNodeType.DECISION in node_types
    assert GraphNodeType.TRADEOFF in node_types
    assert GraphNodeType.REJECTED_ALTERNATIVE in node_types
    assert GraphNodeType.EXTERNAL_ARTIFACT in node_types
    assert all(
        edge.source_type == GraphEdgeSourceType.LLM_INFERRED
        and str(edge.source_artifact_id) == source_artifact_id
        for edge in repository.edges.values()
    )


def test_record_organizational_convention_creates_profile_from_artifact() -> None:
    app = create_app()
    client = TestClient(app)
    source_artifact_id = str(uuid4())

    response = client.post(
        "/memory/organizational/conventions",
        json={
            "source_artifact_id": source_artifact_id,
            "team": "backend",
            "author": "sam",
            "convention": "Avoid inheritance in service layer",
            "evidence": "Repeated review comments requested composition.",
            "confidence": 0.75,
        },
    )

    assert response.status_code == 201
    edge = next(iter(app.state.graph_repository.edges.values()))
    assert edge.edge_type == GraphEdgeType.DERIVED_FROM
    assert edge.source_type == GraphEdgeSourceType.LLM_INFERRED
    assert str(edge.source_artifact_id) == source_artifact_id


def test_record_engineering_dna_stores_repo_convention_profile() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/memory/engineering-dna/conventions",
        json={
            "source_artifact_id": str(uuid4()),
            "repository": "codexa-os",
            "category": "testing",
            "convention": "Trust-boundary paths require explicit isolation tests",
            "evidence": "Repository definition of done marks trust gating as safety-load-bearing.",
            "confidence": 0.92,
        },
    )

    assert response.status_code == 201
    profiles = [
        node
        for node in app.state.graph_repository.nodes.values()
        if node.node_type == GraphNodeType.CONVENTION_PROFILE
    ]
    assert profiles[0].properties["profile_kind"] == "engineering_dna"
    assert profiles[0].properties["category"] == "testing"
