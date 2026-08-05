from fastapi.testclient import TestClient

from backend.main import create_app


def test_economics_effort_estimate_scales_with_diff_size() -> None:
    app = create_app()
    client = TestClient(app)

    small = client.post(
        "/trust-safety/economics/estimates",
        json={
            "proposal": "small change",
            "changed_files": 1,
            "changed_lines": 10,
            "test_delta": 1,
            "historical_review_hours": 2.0,
            "shortcut_taken": False,
        },
    ).json()

    large = client.post(
        "/trust-safety/economics/estimates",
        json={
            "proposal": "large change",
            "changed_files": 10,
            "changed_lines": 500,
            "test_delta": 5,
            "historical_review_hours": 2.0,
            "shortcut_taken": False,
        },
    ).json()

    assert large["implementation_effort_hours"] > small["implementation_effort_hours"]
    assert large["projected_maintenance_hours"] > small["projected_maintenance_hours"]


def test_economics_review_cost_computation() -> None:
    app = create_app()
    client = TestClient(app)

    # 1 file * 0.4 + 180 lines / 180 + 2.0 historical = 2.0 + 0.4 + 1.0 = 3.4 implementation effort
    response = client.post(
        "/trust-safety/economics/estimates",
        json={
            "proposal": "specific change",
            "changed_files": 1,
            "changed_lines": 180,
            "test_delta": 0,
            "historical_review_hours": 2.0,
            "shortcut_taken": False,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["implementation_effort_hours"] == 3.4
