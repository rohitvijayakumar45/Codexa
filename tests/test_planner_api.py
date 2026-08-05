from fastapi.testclient import TestClient

from backend.main import create_app


def _create_node(client: TestClient, stable_id: str) -> str:
    response = client.post(
        "/graph/nodes",
        json={
            "node_type": "File",
            "stable_id": stable_id,
            "properties": {},
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def _create_edge(client: TestClient, from_node_id: str, to_node_id: str, confidence: float) -> str:
    response = client.post(
        "/graph/edges",
        json={
            "from_node_id": from_node_id,
            "to_node_id": to_node_id,
            "edge_type": "depends_on",
            "confidence": confidence,
            "source_type": "human_asserted",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_planner_blast_radius_traverses_active_graph_and_records_event() -> None:
    app = create_app()
    client = TestClient(app)
    source = _create_node(client, "file://backend/source.py")
    service = _create_node(client, "file://backend/service.py")
    route = _create_node(client, "file://backend/route.py")
    unrelated = _create_node(client, "file://backend/unrelated.py")
    first_edge = _create_edge(client, source, service, 0.8)
    second_edge = _create_edge(client, service, route, 0.6)

    response = client.post(
        "/agents/planner/blast-radius",
        json={
            "changed_node_ids": [source],
            "max_depth": 3,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["changed_node_ids"] == [source]
    assert set(body["affected_node_ids"]) == {route, service}
    assert unrelated not in body["affected_node_ids"]
    assert body["confidence"] == 0.6
    assert body["paths"][-1]["node_ids"] == [source, service, route]
    assert body["paths"][-1]["edge_ids"] == [first_edge, second_edge]

    events = app.state.graph_event_writer.events
    assert events[-1].event_type == "planner.blast_radius.computed"
    assert set(events[-1].payload["affected_node_ids"]) == {route, service}


def test_planner_blast_radius_respects_max_depth() -> None:
    app = create_app()
    client = TestClient(app)
    source = _create_node(client, "file://a.py")
    middle = _create_node(client, "file://b.py")
    deep = _create_node(client, "file://c.py")
    _create_edge(client, source, middle, 1.0)
    _create_edge(client, middle, deep, 1.0)

    response = client.post(
        "/agents/planner/blast-radius",
        json={
            "changed_node_ids": [source],
            "max_depth": 1,
        },
    )

    assert response.status_code == 201
    assert response.json()["affected_node_ids"] == [middle]
