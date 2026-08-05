from fastapi.testclient import TestClient

from backend.main import create_app


def test_health_score_calculates_component_metrics() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/trust-safety/health/repository",
        json={
            "repository": "codexa-os",
            "maintainability": 0.8,
            "testability": 0.75,
            "coupling": 0.25,
            "doc_coverage": 0.6,
            "architecture_stability": 0.7,
            "deployment_safety": 0.65,
            "ownership_clarity": 0.7,
            "tech_debt_index": 0.3,
            "confidence": 0.85,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert 0 <= body["score"] <= 1
    
    # Check components
    components = body["components"]
    assert components["maintainability"] == 0.8
    assert components["testability"] == 0.75
    # The API computes inverted metrics: coupling -> 1 - coupling
    assert components["coupling"] == 0.75
    assert components["tech_debt"] == 0.7


def test_health_score_degrades_with_incidents() -> None:
    app = create_app()
    client = TestClient(app)

    # Base case: low tech debt, low coupling
    base = client.post(
        "/trust-safety/health/repository",
        json={
            "repository": "codexa-os",
            "maintainability": 0.9,
            "testability": 0.9,
            "coupling": 0.1,
            "doc_coverage": 0.9,
            "architecture_stability": 0.9,
            "deployment_safety": 0.9,
            "ownership_clarity": 0.9,
            "tech_debt_index": 0.1,
            "confidence": 0.9,
        },
    ).json()

    # Degraded case (simulating recent incidents affecting stability, tech debt, and deployment safety)
    degraded = client.post(
        "/trust-safety/health/repository",
        json={
            "repository": "codexa-os",
            "maintainability": 0.9,
            "testability": 0.9,
            "coupling": 0.1,
            "doc_coverage": 0.9,
            "architecture_stability": 0.5, # Lowered
            "deployment_safety": 0.5, # Lowered
            "ownership_clarity": 0.9,
            "tech_debt_index": 0.6, # Increased tech debt index
            "confidence": 0.9,
        },
    ).json()

    assert base["score"] > degraded["score"]
