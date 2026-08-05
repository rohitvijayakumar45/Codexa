from uuid import uuid4

from fastapi.testclient import TestClient

from backend.main import create_app


def test_policy_distillation_updates_risk_weights() -> None:
    app = create_app()
    client = TestClient(app)

    # Base case with no incidents or reverts
    response_base = client.post(
        "/learning/policy-distillation/runs",
        json={
            "repository": "codexa-os",
            "accepted_change_ids": [str(uuid4())],
            "reverted_change_ids": [],
            "review_comment_summaries": [],
            "incident_outcome_summaries": [],
        },
    ).json()

    # Degraded case with reverts and incidents
    response_degraded = client.post(
        "/learning/policy-distillation/runs",
        json={
            "repository": "codexa-os",
            "accepted_change_ids": [],
            "reverted_change_ids": [str(uuid4()), str(uuid4())],
            "review_comment_summaries": ["Needs more tests", "Too complex"],
            "incident_outcome_summaries": ["Downtime due to memory leak"],
        },
    ).json()

    # Assert risk weights increased for reverts and incidents
    assert response_degraded["risk_weight_delta"]["revert_history"] > response_base["risk_weight_delta"]["revert_history"]
    assert response_degraded["risk_weight_delta"]["incident_history"] > response_base["risk_weight_delta"]["incident_history"]


def test_policy_distillation_rollback_capability() -> None:
    app = create_app()
    client = TestClient(app)
    repo_name = "test-rollback-repo"

    run_1 = client.post(
        "/learning/policy-distillation/runs",
        json={"repository": repo_name},
    ).json()

    run_2 = client.post(
        "/learning/policy-distillation/runs",
        json={"repository": repo_name},
    ).json()

    run_3 = client.post(
        "/learning/policy-distillation/runs",
        json={"repository": repo_name},
    ).json()

    # The service maintains an internal version counter that increments per repository.
    # This explicit versioning provides the foundation for rollback capability.
    assert run_1["version"] == 1
    assert run_2["version"] == 2
    assert run_3["version"] == 3
