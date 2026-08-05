from datetime import UTC, datetime

from fastapi.testclient import TestClient

from backend.graph.schemas import GraphNodeType
from backend.main import create_app


def test_architecture_evolution_records_trend_and_alerts() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/understanding/architecture/trends",
        json={
            "module_path": "backend/perception",
            "observations": [
                {
                    "observed_at": datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
                    "coupling": 0.5,
                    "cohesion": 0.8,
                    "cyclomatic_complexity": 4,
                    "fan_in": 2,
                    "fan_out": 3,
                    "ownership_fragmentation": 1,
                    "file_churn": 4,
                },
                {
                    "observed_at": datetime(2026, 1, 31, tzinfo=UTC).isoformat(),
                    "coupling": 0.75,
                    "cohesion": 0.7,
                    "cyclomatic_complexity": 6,
                    "fan_in": 3,
                    "fan_out": 5,
                    "ownership_fragmentation": 2,
                    "file_churn": 10,
                },
            ],
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["module_path"] == "backend/perception"
    assert "coupling_growth_over_40_percent" in body["alerts"]
    assert "complexity_increasing" in body["alerts"]
    assert body["bottleneck_eta_days"] is not None
    assert any(
        node.node_type == GraphNodeType.ARCHITECTURE_TREND
        for node in app.state.graph_repository.nodes.values()
    )
    assert any(
        edge.edge_type == "derived_from"
        for edge in app.state.graph_repository.edges.values()
    )

    trends_response = client.get("/understanding/architecture/trends")

    assert trends_response.status_code == 200
    trends = trends_response.json()
    assert len(trends) == 1
    assert trends[0]["module_path"] == "backend/perception"
    assert trends[0]["trend_node_id"] == body["trend_node_id"]


def test_graph_nodes_endpoint_lists_created_nodes_for_visualization() -> None:
    app = create_app()
    client = TestClient(app)
    created = client.post(
        "/graph/nodes",
        json={
            "node_type": "Repository",
            "stable_id": "repo://codexa-os",
            "properties": {"name": "codexa-os"},
        },
    ).json()

    response = client.get("/graph/nodes")

    assert response.status_code == 200
    assert response.json()[0]["id"] == created["id"]
    assert response.json()[0]["node_type"] == "Repository"
