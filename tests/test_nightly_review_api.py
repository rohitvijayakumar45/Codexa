from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from backend.main import create_app


def test_nightly_review_detects_drift() -> None:
    app = create_app()
    client = TestClient(app)

    # First, record a trend with a coupling growth that triggers an alert
    first_time = datetime.now(UTC) - timedelta(days=10)
    second_time = datetime.now(UTC)

    client.post(
        "/understanding/architecture/trends",
        json={
            "module_path": "backend.graph",
            "observations": [
                {
                    "observed_at": first_time.isoformat(),
                    "coupling": 0.2,
                    "cohesion": 0.8,
                    "cyclomatic_complexity": 10,
                    "fan_in": 5,
                    "fan_out": 2,
                    "ownership_fragmentation": 0.1,
                    "file_churn": 1.5,
                },
                {
                    "observed_at": second_time.isoformat(),
                    "coupling": 0.5,  # Increased by > 40%
                    "cohesion": 0.8,
                    "cyclomatic_complexity": 12,  # Complexity increasing
                    "fan_in": 5,
                    "fan_out": 3,
                    "ownership_fragmentation": 0.1,
                    "file_churn": 1.5,
                },
            ],
        },
    )

    response = client.post(
        "/understanding/architecture/nightly-review",
        json={
            "repository": "codexa-os",
            "knowledge_gaps": [],
            "open_draft_pr": True,
        },
    )

    assert response.status_code == 201
    body = response.json()
    markdown = body["draft_rfc_markdown"]
    assert "coupling_growth_over_40_percent" in markdown
    assert "complexity_increasing" in markdown


def test_nightly_review_generates_maintenance_tasks() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/understanding/architecture/nightly-review",
        json={
            "repository": "codexa-os",
            "knowledge_gaps": ["No owner mapped for backend.graph"],
            "open_draft_pr": False,
        },
    )

    assert response.status_code == 201
    body = response.json()
    markdown = body["draft_rfc_markdown"]
    assert "No architecture trend alerts found." in markdown
    assert "No owner mapped for backend.graph" in markdown
    assert body["would_open_draft_pr"] is False
    assert body["human_approval_required"] is True
