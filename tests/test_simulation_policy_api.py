from uuid import uuid4

from fastapi.testclient import TestClient

from backend.graph.schemas import GraphNodeType
from backend.main import create_app


def _node(client: TestClient, stable_id: str) -> str:
    response = client.post(
        "/graph/nodes",
        json={"node_type": "File", "stable_id": stable_id, "properties": {}},
    )
    assert response.status_code == 201
    return response.json()["id"]


def _edge(client: TestClient, from_node_id: str, to_node_id: str) -> None:
    response = client.post(
        "/graph/edges",
        json={
            "from_node_id": from_node_id,
            "to_node_id": to_node_id,
            "edge_type": "depends_on",
            "confidence": 1.0,
            "source_type": "static_analysis",
        },
    )
    assert response.status_code == 201


def test_simulation_passes_low_risk_change_and_writes_scenario_node() -> None:
    app = create_app()
    client = TestClient(app)
    source = _node(client, "file://backend/a.py")
    target = _node(client, "file://backend/b.py")
    _edge(client, source, target)

    response = client.post(
        "/simulation/scenarios",
        json={
            "proposal_id": str(uuid4()),
            "changed_node_ids": [source],
            "diff_text": "+def test_a():\n+    assert True\n",
            "deployment_steps": ["deploy backend"],
            "rollback_steps": ["revert commit"],
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "passed"
    assert body["predicted_blast_radius_node_ids"] == [target]
    assert body["rollback_viable"] is True
    assert body["deployment_sequence_viable"] is True
    assert body["predicted_test_failures"] == []
    assert any(
        node.node_type == GraphNodeType.SIMULATION_SCENARIO
        for node in app.state.graph_repository.nodes.values()
    )
    assert app.state.graph_event_writer.events[-1].event_type == "simulation.scenario.completed"


def test_simulation_blocks_schema_change_without_viable_rollback() -> None:
    app = create_app()
    client = TestClient(app)
    source = _node(client, "file://infra/migrations/0002.sql")

    response = client.post(
        "/simulation/scenarios",
        json={
            "proposal_id": str(uuid4()),
            "changed_node_ids": [source],
            "diff_text": "+ALTER TABLE repositories DROP COLUMN metadata;\n",
            "deployment_steps": [],
            "rollback_steps": ["revert app code"],
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "blocked"
    assert "schema_contract_tests" in body["predicted_test_failures"]
    assert "rollback_viability" in body["predicted_test_failures"]
    assert "deployment_sequence" in body["predicted_test_failures"]


def test_policy_execution_gate_blocks_missing_simulation() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/trust-safety/policy/execution-gate",
        json={
            "proposal_id": str(uuid4()),
            "simulation_id": None,
            "simulation_passed": False,
            "verification_passed": True,
            "risk_score": 0.2,
            "adversarial_findings": [],
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["decision"] == "blocked"
    assert "missing_simulation" in body["reasons"]


def test_policy_execution_gate_approves_verified_simulated_low_risk_change() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/trust-safety/policy/execution-gate",
        json={
            "proposal_id": str(uuid4()),
            "simulation_id": str(uuid4()),
            "simulation_passed": True,
            "verification_passed": True,
            "risk_score": 0.2,
            "adversarial_findings": [],
        },
    )

    assert response.status_code == 201
    assert response.json()["decision"] == "approved"
    assert response.json()["reasons"] == []
