from fastapi.testclient import TestClient

from backend.main import create_app
from backend.trust_safety.confidence import WEIGHTS


def test_confidence_calibration_computes_expected_score() -> None:
    app = create_app()
    client = TestClient(app)

    # All inputs at 0.5 should result in an overall score of 0.5 (since weights sum to 1.0)
    response = client.post(
        "/trust-safety/confidence/calibrations",
        json={
            "subject": "proposal://one",
            "evidence_coverage": 0.5,
            "repo_familiarity": 0.5,
            "test_coverage_overlap": 0.5,
            "historical_similarity": 0.5,
            "verification_pass_rate": 0.5,
            "dependency_certainty": 0.5,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["confidence"] == 0.5


def test_confidence_calibration_returns_detailed_breakdown() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/trust-safety/confidence/calibrations",
        json={
            "subject": "proposal://two",
            "evidence_coverage": 1.0,
            "repo_familiarity": 0.0,
            "test_coverage_overlap": 1.0,
            "historical_similarity": 0.0,
            "verification_pass_rate": 1.0,
            "dependency_certainty": 0.0,
        },
    )

    assert response.status_code == 201
    body = response.json()
    breakdown = body["breakdown"]
    
    # 1.0 inputs should equal their respective weights
    assert breakdown["evidence_coverage"] == WEIGHTS["evidence_coverage"]
    assert breakdown["test_coverage_overlap"] == WEIGHTS["test_coverage_overlap"]
    assert breakdown["verification_pass_rate"] == WEIGHTS["verification_pass_rate"]
    
    # 0.0 inputs should equal 0.0
    assert breakdown["repo_familiarity"] == 0.0
    assert breakdown["historical_similarity"] == 0.0
    assert breakdown["dependency_certainty"] == 0.0
