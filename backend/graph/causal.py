from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from backend.graph.schemas import (
    GraphEdgeCreate,
    GraphEdgeSourceType,
    GraphEdgeType,
    GraphNodeCreate,
    GraphNodeType,
)
from backend.graph.service import GraphService


class CausalEventInput(BaseModel):
    event_kind: str = Field(min_length=1, max_length=64)
    stable_id: str = Field(min_length=1, max_length=512)
    summary: str = Field(min_length=1, max_length=1024)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CausalChainRequest(BaseModel):
    source_artifact_id: UUID
    events: list[CausalEventInput] = Field(min_length=2)
    causal_confidence: float = Field(ge=0, le=1)


class CausalChainResult(BaseModel):
    event_node_ids: list[UUID]
    edge_ids: list[UUID]
    causal_confidence: float = Field(ge=0, le=1)


class CausalGraphOverview(BaseModel):
    event_node_ids: list[UUID]
    causal_edge_ids: list[UUID]


class CausalGraphService:
    def __init__(self, graph: GraphService) -> None:
        self.graph = graph

    def record_chain(self, request: CausalChainRequest) -> CausalChainResult:
        nodes = [
            self.graph.add_node(
                GraphNodeCreate(
                    node_type=GraphNodeType.CAUSAL_EVENT,
                    stable_id=f"causal-event://{event.stable_id}",
                    properties={
                        "event_kind": event.event_kind,
                        "summary": event.summary,
                        "occurred_at": event.occurred_at.isoformat(),
                        "confidence": request.causal_confidence,
                    },
                )
            )
            for event in request.events
        ]
        edges = [
            self.graph.add_edge(
                GraphEdgeCreate(
                    from_node_id=source.id,
                    to_node_id=target.id,
                    edge_type=GraphEdgeType.CAUSES,
                    confidence=request.causal_confidence,
                    source_type=GraphEdgeSourceType.LLM_INFERRED,
                    source_artifact_id=request.source_artifact_id,
                    valid_from=request.events[index].occurred_at,
                    properties={"chain_index": index},
                )
            )
            for index, (source, target) in enumerate(zip(nodes, nodes[1:]))
        ]
        return CausalChainResult(
            event_node_ids=[node.id for node in nodes],
            edge_ids=[edge.id for edge in edges],
            causal_confidence=request.causal_confidence,
        )

    def overview(self) -> CausalGraphOverview:
        causal_nodes = [
            node for node in self.graph.list_nodes() if node.node_type == GraphNodeType.CAUSAL_EVENT
        ]
        causal_edges = [
            edge
            for edge in self.graph.list_edges_at()
            if edge.edge_type in {GraphEdgeType.CAUSES, GraphEdgeType.INCREASES_RISK_OF}
        ]
        return CausalGraphOverview(
            event_node_ids=[node.id for node in causal_nodes],
            causal_edge_ids=[edge.id for edge in causal_edges],
        )
