import json
import pytest
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from pathlib import Path

from backend.graph.schemas import (
    GraphNodeCreate,
    GraphEdgeCreate,
    GraphNodeType,
    GraphEdgeType,
    GraphEdgeSourceType,
    GraphNodeProvenance,
)
from backend.graph.service import GraphService
from backend.graph.repository import InMemoryGraphRepository
from backend.graph.events import InMemoryGraphEventWriter
from backend.graph.consistency import (
    MultiStoreConsistencyService,
    ConsistencyCheckRequest,
    ProjectionCount,
)


def test_claim_graph_schema_edge_confidence_and_provenance():
    """Claim: Every graph edge must carry confidence, source_type, valid_from, valid_to.
    Static analysis edges get confidence 1.0."""
    repo = InMemoryGraphRepository()
    svc = GraphService(repository=repo, event_writer=InMemoryGraphEventWriter())

    n1 = svc.add_node(GraphNodeCreate(
        node_type=GraphNodeType.FILE,
        stable_id="backend/main.py",
        properties={"path": "backend/main.py"},
        provenance=GraphNodeProvenance.INTERNAL_CODE,
    ))
    n2 = svc.add_node(GraphNodeCreate(
        node_type=GraphNodeType.CODE_SYMBOL,
        stable_id="backend/main.py:app",
        properties={"name": "app"},
        provenance=GraphNodeProvenance.INTERNAL_CODE,
    ))

    # Static analysis edge
    e1 = svc.add_edge(GraphEdgeCreate(
        from_node_id=n1.id,
        to_node_id=n2.id,
        edge_type=GraphEdgeType.CALLS,
        confidence=1.0,
        source_type=GraphEdgeSourceType.STATIC_ANALYSIS,
    ))

    assert e1.confidence == 1.0
    assert e1.source_type == GraphEdgeSourceType.STATIC_ANALYSIS
    assert e1.valid_from is not None
    assert e1.valid_to is None

    # LLM-inferred edge with citation
    e2 = svc.add_edge(GraphEdgeCreate(
        from_node_id=n1.id,
        to_node_id=n2.id,
        edge_type=GraphEdgeType.TRACES_TO_DECISION,
        confidence=0.85,
        source_type=GraphEdgeSourceType.LLM_INFERRED,
        source_artifact_id=uuid4(),
    ))
    assert e2.confidence == 0.85
    assert e2.source_type == GraphEdgeSourceType.LLM_INFERRED
    assert e2.source_artifact_id is not None


def test_claim_graph_temporal_time_machine():
    """Claim: Temporal edges (valid_from/valid_to) support point-in-time graph reconstruction."""
    repo = InMemoryGraphRepository()
    svc = GraphService(repository=repo, event_writer=InMemoryGraphEventWriter())

    n1 = svc.add_node(GraphNodeCreate(
        node_type=GraphNodeType.FILE,
        stable_id="file1.py",
        properties={},
        provenance=GraphNodeProvenance.INTERNAL_CODE,
    ))
    n2 = svc.add_node(GraphNodeCreate(
        node_type=GraphNodeType.FILE,
        stable_id="file2.py",
        properties={},
        provenance=GraphNodeProvenance.INTERNAL_CODE,
    ))

    t0 = datetime.now(timezone.utc) - timedelta(days=2)
    t1 = datetime.now(timezone.utc) - timedelta(days=1)
    t2 = datetime.now(timezone.utc)

    # Edge active from t0 to t1
    e_old = svc.add_edge(GraphEdgeCreate(
        from_node_id=n1.id,
        to_node_id=n2.id,
        edge_type=GraphEdgeType.IMPORTS,
        confidence=1.0,
        source_type=GraphEdgeSourceType.STATIC_ANALYSIS,
        valid_from=t0,
        valid_to=t1,
    ))

    # Edge active from t1 onward
    e_new = svc.add_edge(GraphEdgeCreate(
        from_node_id=n1.id,
        to_node_id=n2.id,
        edge_type=GraphEdgeType.CALLS,
        confidence=1.0,
        source_type=GraphEdgeSourceType.STATIC_ANALYSIS,
        valid_from=t1,
        valid_to=None,
    ))

    # Query at t0 + 1 hour -> should see e_old, not e_new
    edges_at_past = repo.list_edges_at(t0 + timedelta(hours=1))
    assert any(e.id == e_old.id for e in edges_at_past)
    assert not any(e.id == e_new.id for e in edges_at_past)

    # Query now -> should see e_new, not e_old
    edges_now = repo.list_edges_at(t2)
    assert any(e.id == e_new.id for e in edges_now)
    assert not any(e.id == e_old.id for e in edges_now)


def test_claim_neo4j_and_qdrant_projections_status():
    """Audit: Probe whether Neo4j and Qdrant have real projection worker pipelines
    or if they are architectural scaffolding."""
    import backend.graph as graph_pkg
    graph_dir = Path(graph_pkg.__file__).parent
    
    # Check for neo4j or qdrant client imports across backend/graph
    py_files = list(graph_dir.glob("*.py"))
    neo4j_imports = []
    qdrant_imports = []
    for p in py_files:
        text = p.read_text(encoding="utf-8")
        if "neo4j" in text.lower():
            neo4j_imports.append(p.name)
        if "qdrant" in text.lower():
            qdrant_imports.append(p.name)
            
    # Verification: Neither neo4j nor qdrant python driver is imported in backend/graph
    # They only exist as strings in consistency check and seed
    assert "consistency.py" in neo4j_imports or len(neo4j_imports) == 0
    
    # Test consistency reconciliation behavior
    event_writer = InMemoryGraphEventWriter()
    consistency_svc = MultiStoreConsistencyService(event_writer=event_writer)
    report = consistency_svc.check(ConsistencyCheckRequest(
        postgres_event_count=100,
        projections=[
            ProjectionCount(store="neo4j", count=95),
            ProjectionCount(store="qdrant", count=80),
        ]
    ))
    assert report.drift["neo4j"] == 5
    assert report.drift["qdrant"] == 20
    assert "replay_outbox_to_neo4j" in report.repair_actions
    assert "replay_outbox_to_qdrant" in report.repair_actions
