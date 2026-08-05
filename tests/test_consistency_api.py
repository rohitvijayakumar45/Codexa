from fastapi.testclient import TestClient

from backend.main import create_app


def test_consistency_detects_drift_accurately() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/graph/consistency/checks",
        json={
            "postgres_event_count": 100,
            "projections": [
                {"store": "neo4j", "count": 95},
                {"store": "qdrant", "count": 100},
            ],
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["consistent"] is False
    assert body["drift"]["neo4j"] == 5
    assert "qdrant" not in body["drift"]


def test_consistency_suggests_appropriate_repair() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/graph/consistency/checks",
        json={
            "postgres_event_count": 100,
            "projections": [
                {"store": "neo4j", "count": 95},
                {"store": "qdrant", "count": 99},
            ],
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert "replay_outbox_to_neo4j" in body["repair_actions"]
    assert "replay_outbox_to_qdrant" in body["repair_actions"]
