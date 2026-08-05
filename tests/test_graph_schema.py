from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.graph.repository import InMemoryGraphRepository
from backend.graph.schemas import (
    GraphEdgeCreate,
    GraphEdgeSourceType,
    GraphEdgeType,
    GraphNodeCreate,
    GraphNodeType,
)


def test_static_analysis_edges_require_confidence_one() -> None:
    with pytest.raises(ValidationError, match="static_analysis edges must have confidence 1.0"):
        GraphEdgeCreate(
            from_node_id=uuid4(),
            to_node_id=uuid4(),
            edge_type=GraphEdgeType.CALLS,
            confidence=0.99,
            source_type=GraphEdgeSourceType.STATIC_ANALYSIS,
        )


def test_llm_inferred_edges_require_source_artifact_citation() -> None:
    with pytest.raises(ValidationError, match="llm_inferred edges must cite source_artifact_id"):
        GraphEdgeCreate(
            from_node_id=uuid4(),
            to_node_id=uuid4(),
            edge_type=GraphEdgeType.CAUSES,
            confidence=0.7,
            source_type=GraphEdgeSourceType.LLM_INFERRED,
        )


def test_temporal_edge_lookup_returns_edges_active_at_time() -> None:
    repository = InMemoryGraphRepository()
    source = repository.add_node(
        GraphNodeCreate(node_type=GraphNodeType.FILE, stable_id="file://backend/a.py")
    )
    target = repository.add_node(
        GraphNodeCreate(node_type=GraphNodeType.FILE, stable_id="file://backend/b.py")
    )
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = start + timedelta(days=2)
    edge = repository.add_edge(
        GraphEdgeCreate(
            from_node_id=source.id,
            to_node_id=target.id,
            edge_type=GraphEdgeType.IMPORTS,
            confidence=1.0,
            source_type=GraphEdgeSourceType.STATIC_ANALYSIS,
            valid_from=start,
            valid_to=end,
        )
    )

    assert repository.list_edges_at(start + timedelta(days=1)) == [edge]
    assert repository.list_edges_at(end + timedelta(seconds=1)) == []
