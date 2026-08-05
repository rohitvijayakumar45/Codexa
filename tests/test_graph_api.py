from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from backend.main import create_app


def test_create_data_flow_trace_writes_nodes_edges_and_events() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/graph/data-flow/traces",
        json={
            "schema_name": "public",
            "table_name": "repositories",
            "field_name": "metadata",
            "route_method": "GET",
            "route_path": "/repositories/{repository_id}",
            "consumer_stable_id": "python://backend.agents.planner.RepositoryContext",
            "consumer_label": "RepositoryContext",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["schema_field_node_id"]
    assert body["route_node_id"]
    assert body["consumer_node_id"]
    assert len(body["edge_ids"]) == 2

    repository = app.state.graph_repository
    assert len(repository.nodes) == 3
    assert len(repository.edges) == 2
    assert {edge.edge_type for edge in repository.edges.values()} == {"flows_into"}
    assert {edge.confidence for edge in repository.edges.values()} == {1.0}
    assert {edge.source_type for edge in repository.edges.values()} == {"static_analysis"}

    events = app.state.graph_event_writer.events
    assert [event.event_type for event in events].count("graph.node.created") == 3
    assert [event.event_type for event in events].count("graph.edge.created") == 2


def test_data_flow_trace_reuses_existing_stable_nodes() -> None:
    app = create_app()
    client = TestClient(app)
    payload = {
        "schema_name": "public",
        "table_name": "repositories",
        "field_name": "metadata",
        "route_method": "GET",
        "route_path": "/repositories/{repository_id}",
    }

    first = client.post("/graph/data-flow/traces", json=payload).json()
    second = client.post("/graph/data-flow/traces", json=payload).json()

    assert first["schema_field_node_id"] == second["schema_field_node_id"]
    assert first["route_node_id"] == second["route_node_id"]
    assert len(app.state.graph_repository.nodes) == 2
    assert len(app.state.graph_repository.edges) == 2


def test_time_machine_snapshot_replays_temporal_edges() -> None:
    app = create_app()
    client = TestClient(app)
    source = client.post(
        "/graph/nodes",
        json={"node_type": "File", "stable_id": "file://backend/source.py"},
    ).json()
    target = client.post(
        "/graph/nodes",
        json={"node_type": "File", "stable_id": "file://backend/target.py"},
    ).json()
    valid_from = datetime.now(UTC)
    valid_to = valid_from + timedelta(days=1)

    client.post(
        "/graph/edges",
        json={
            "from_node_id": source["id"],
            "to_node_id": target["id"],
            "edge_type": "imports",
            "confidence": 1.0,
            "source_type": "static_analysis",
            "valid_from": valid_from.isoformat(),
            "valid_to": valid_to.isoformat(),
        },
    )

    active = client.get(
        "/graph/snapshots",
        params={"at_time": (valid_from + timedelta(hours=1)).isoformat()},
    )
    expired = client.get(
        "/graph/snapshots",
        params={"at_time": (valid_to + timedelta(hours=1)).isoformat()},
    )
    timeline = client.get("/graph/timeline")

    assert active.status_code == 200
    assert len(active.json()["nodes"]) == 2
    assert len(active.json()["edges"]) == 1
    assert expired.status_code == 200
    assert len(expired.json()["nodes"]) == 2
    assert expired.json()["edges"] == []
    assert timeline.status_code == 200
    assert timeline.json()["starts_at"] is not None
    assert timeline.json()["ends_at"] is not None


def test_cannot_create_simulation_scenario_via_generic_api() -> None:
    app = create_app()
    client = TestClient(app)
    
    response = client.post(
        "/graph/nodes",
        json={
            "node_type": "SimulationScenario",
            "stable_id": "simulation://evil",
            "properties": {"status": "passed", "proposal_id": "123"}
        },
    )
    
    assert response.status_code == 403
    assert "Simulation scenarios must be created via the Simulation Engine" in response.text
