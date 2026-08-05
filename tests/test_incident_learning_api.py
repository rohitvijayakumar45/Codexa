from uuid import uuid4

from fastapi.testclient import TestClient

from backend.graph.schemas import GraphNodeType
from backend.main import create_app


def test_incident_learning_generates_prevention_rule() -> None:
    app = create_app()
    client = TestClient(app)
    source_artifact_id = str(uuid4())

    response = client.post(
        "/trust-safety/incidents/learning",
        json={
            "source_artifact_id": source_artifact_id,
            "incident": "System crashed on startup",
            "root_cause": "Missing environment variable validation",
            "fix": "Add validation logic at startup",
            "regression_test": "Test missing env var",
            "prevention_rule": "Always validate env vars",
            "confidence": 0.9,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["prevention_rule_node_id"]

    nodes = app.state.graph_repository.nodes.values()
    prevention_rule_nodes = [n for n in nodes if n.node_type == GraphNodeType.PREVENTION_RULE]
    assert len(prevention_rule_nodes) == 1
    assert prevention_rule_nodes[0].properties["summary"] == "Always validate env vars"


def test_incident_learning_ignores_invalid_chain() -> None:
    app = create_app()
    client = TestClient(app)
    source_artifact_id = str(uuid4())

    # Try to post an invalid request (missing fields)
    response = client.post(
        "/trust-safety/incidents/learning",
        json={
            "source_artifact_id": source_artifact_id,
            "incident": "System crashed on startup",
            # Missing root_cause, fix, regression_test, prevention_rule
            "confidence": 0.9,
        },
    )

    # FastAPI will reject the incomplete request with a 422 Unprocessable Entity
    assert response.status_code == 422
