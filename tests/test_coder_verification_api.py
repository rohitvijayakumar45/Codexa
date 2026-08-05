from uuid import uuid4

from fastapi.testclient import TestClient

from backend.main import create_app


def test_coder_records_change_proposal_with_simulation_required() -> None:
    app = create_app()
    client = TestClient(app)
    planner_analysis_id = str(uuid4())

    response = client.post(
        "/agents/coder/proposals",
        json={
            "objective": "Add trust-boundary isolation tests",
            "planner_analysis_id": planner_analysis_id,
            "rationale": "Trust boundary is safety-load-bearing.",
            "changes": [
                {
                    "path": "tests/test_trust_boundary.py",
                    "diff": "+def test_new_case():\n+    assert True\n",
                }
            ],
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "proposed"
    assert body["simulation_required"] is True
    assert body["changed_paths"] == ["tests/test_trust_boundary.py"]
    assert app.state.graph_event_writer.events[-1].event_type == "coder.change_proposal.created"


def test_verification_fails_rejected_stack_terms() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/trust-safety/verification/proposals",
        json={
            "proposal_id": str(uuid4()),
            "diff_text": "+import express from 'express'\n+// tests included\n",
            "declared_test_commands": ["python -m pytest"],
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "failed"
    banned_stack_gate = next(gate for gate in body["gates"] if gate["name"] == "banned_stack")
    assert banned_stack_gate["passed"] is False
    assert body["simulation_required"] is True


def test_verification_passes_with_tests_and_no_rejected_stack() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/trust-safety/verification/proposals",
        json={
            "proposal_id": str(uuid4()),
            "diff_text": "+def test_planner_path():\n+    assert result\n",
            "declared_test_commands": [],
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "passed"
    assert all(gate["passed"] for gate in body["gates"])
    assert app.state.graph_event_writer.events[-1].event_type == "verification.proposal.checked"
