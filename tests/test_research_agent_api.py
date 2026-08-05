from uuid import uuid4

from fastapi.testclient import TestClient

from backend.graph.schemas import GraphNodeType, GraphEdgeType
from backend.main import create_app


def test_research_agent_aggregates_context() -> None:
    app = create_app()
    client = TestClient(app)

    # Make a research recommendation with citations
    response = client.post(
        "/agents/research/recommendations",
        json={
            "query": "How does the cache work?",
            "recommendation": "Use Redis for caching with TTL.",
            "citations": [
                {
                    "url": "https://redis.io/docs",
                    "title": "Redis Docs",
                    "summary": "Redis documentation about TTL.",
                },
                {
                    "url": "https://docs.python.org/3/library/functools.html",
                    "title": "functools",
                    "summary": "Python cache decorator.",
                },
            ],
            "confidence": 0.85,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert len(body["citation_node_ids"]) == 2
    assert len(body["edge_ids"]) == 2

    # Verify nodes and edges are persisted in the graph
    nodes = app.state.graph_repository.nodes.values()
    decision_nodes = [n for n in nodes if n.node_type == GraphNodeType.DECISION]
    assert len(decision_nodes) == 1
    
    artifact_nodes = [n for n in nodes if n.node_type == GraphNodeType.EXTERNAL_ARTIFACT]
    assert len(artifact_nodes) == 2
    
    # Check the trust level assigned to scraped content
    assert artifact_nodes[0].properties.get("trust_level") == "public_scraped"
    
    # Check edges
    edges = app.state.graph_repository.edges.values()
    assert len(edges) == 2
    for edge in edges:
        assert edge.edge_type == GraphEdgeType.DERIVED_FROM


def test_research_agent_identifies_knowledge_gaps() -> None:
    # A research agent query without citations (representing a failure to find context)
    # The API schema dictates `citations` must have min_length=1. So if it fails to find citations,
    # the client shouldn't be able to construct a valid request, or it returns 422 if it tries to submit an empty list.
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/agents/research/recommendations",
        json={
            "query": "Unknown component that does not exist",
            "recommendation": "No information found.",
            "citations": [],
            "confidence": 0.0,
        },
    )

    # FastAPI enforces min_length=1 on citations list
    assert response.status_code == 422
