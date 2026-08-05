import hashlib
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.graph.schemas import GraphNodeCreate, GraphNodeType
from backend.main import create_app


def test_sandbox_execution_blocks_without_simulation_record() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/execution/sandbox-runs",
        json={
            "proposal_id": str(uuid4()),
            "diff_text": "print('hello')",
            "commands": [{"command": "python -m pytest"}],
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "blocked"
    assert "missing_simulation_record" in body["blocked_reasons"]


def test_sandbox_execution_blocks_for_blocked_simulation() -> None:
    app = create_app()
    client = TestClient(app)
    proposal_id = str(uuid4())

    app.state.graph_repository.add_node(
        GraphNodeCreate(
            node_type=GraphNodeType.SIMULATION_SCENARIO,
            stable_id=f"simulation://{uuid4()}",
            properties={"proposal_id": proposal_id, "status": "blocked"},
        )
    )

    response = client.post(
        "/execution/sandbox-runs",
        json={
            "proposal_id": proposal_id,
            "diff_text": "print('hello')",
            "commands": [{"command": "python -m pytest"}],
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "blocked"
    assert "simulation_blocked" in body["blocked_reasons"]


def test_sandbox_execution_schedules_for_passed_simulation() -> None:
    app = create_app()
    client = TestClient(app)
    proposal_id = str(uuid4())
    diff_text = "print('hello')"
    diff_hash = hashlib.sha256(diff_text.encode("utf-8")).hexdigest()

    app.state.graph_repository.add_node(
        GraphNodeCreate(
            node_type=GraphNodeType.SIMULATION_SCENARIO,
            stable_id=f"simulation://{uuid4()}",
            properties={"proposal_id": proposal_id, "diff_hash": diff_hash, "status": "passed"},
        )
    )

    response = client.post(
        "/execution/sandbox-runs",
        json={
            "proposal_id": proposal_id,
            "diff_text": diff_text,
            "commands": [{"command": "python -m pytest", "timeout_seconds": 600}],
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "scheduled"
    assert body["blocked_reasons"] == []
    assert body["docker_args"][:2] == ["docker", "run"]
    assert "--network" in body["docker_args"]
    assert "--read-only" in body["docker_args"]


def test_sandbox_execution_blocks_content_mismatch() -> None:
    app = create_app()
    client = TestClient(app)
    proposal_id = str(uuid4())
    diff_text = "print('hello')"
    diff_hash = hashlib.sha256(diff_text.encode("utf-8")).hexdigest()

    app.state.graph_repository.add_node(
        GraphNodeCreate(
            node_type=GraphNodeType.SIMULATION_SCENARIO,
            stable_id=f"simulation://{uuid4()}",
            properties={"proposal_id": proposal_id, "diff_hash": diff_hash, "status": "passed"},
        )
    )

    # Attempt to execute a modified diff under the same proposal
    response = client.post(
        "/execution/sandbox-runs",
        json={
            "proposal_id": proposal_id,
            "diff_text": "import os; os.system('rm -rf /')",
            "commands": [{"command": "python -m pytest", "timeout_seconds": 600}],
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "blocked"
    assert "simulation_content_mismatch" in body["blocked_reasons"]


def test_chaos_premortem_required_for_high_risk_change() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/simulation/chaos/pre-mortems",
        json={
            "proposal_id": str(uuid4()),
            "risk_score": 0.8,
            "threshold": 0.6,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["required"] is True
    assert {scenario["kind"] for scenario in body["scenarios"]} == {
        "dependency_down",
        "db_connection_drop",
        "cpu_spike",
        "network_partition",
    }


def test_chaos_premortem_not_required_for_low_risk_change() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/simulation/chaos/pre-mortems",
        json={
            "proposal_id": str(uuid4()),
            "risk_score": 0.2,
        },
    )

    assert response.status_code == 201
    assert response.json()["required"] is False
    assert response.json()["scenarios"] == []
