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


class DataFlowTraceRequest(BaseModel):
    schema_name: str = Field(default="public", min_length=1, max_length=128)
    table_name: str = Field(min_length=1, max_length=128)
    field_name: str = Field(min_length=1, max_length=128)
    route_method: str = Field(min_length=1, max_length=16)
    route_path: str = Field(min_length=1, max_length=512)
    consumer_stable_id: str | None = Field(default=None, max_length=512)
    consumer_label: str | None = Field(default=None, max_length=256)


class DataFlowTraceResult(BaseModel):
    schema_field_node_id: UUID
    route_node_id: UUID
    consumer_node_id: UUID | None
    edge_ids: list[UUID]


class DataFlowTracingService:
    def __init__(self, graph: GraphService) -> None:
        self.graph = graph

    def create_trace(self, request: DataFlowTraceRequest) -> DataFlowTraceResult:
        valid_from = datetime.now(UTC)
        schema_field = self.graph.add_node(
            GraphNodeCreate(
                node_type=GraphNodeType.SCHEMA_FIELD,
                stable_id=(
                    f"postgres://{request.schema_name}.{request.table_name}.{request.field_name}"
                ),
                properties={
                    "schema_name": request.schema_name,
                    "table_name": request.table_name,
                    "field_name": request.field_name,
                },
            )
        )
        route = self.graph.add_node(
            GraphNodeCreate(
                node_type=GraphNodeType.API_ROUTE,
                stable_id=f"fastapi://{request.route_method.upper()} {request.route_path}",
                properties={
                    "method": request.route_method.upper(),
                    "path": request.route_path,
                },
            )
        )
        first_edge = self.graph.add_edge(
            GraphEdgeCreate(
                from_node_id=schema_field.id,
                to_node_id=route.id,
                edge_type=GraphEdgeType.FLOWS_INTO,
                confidence=1.0,
                source_type=GraphEdgeSourceType.STATIC_ANALYSIS,
                valid_from=valid_from,
                properties={"trace_stage": "schema_field_to_route"},
            )
        )

        edge_ids = [first_edge.id]
        consumer_node_id: UUID | None = None
        if request.consumer_stable_id:
            consumer = self.graph.add_node(
                GraphNodeCreate(
                    node_type=GraphNodeType.CODE_SYMBOL,
                    stable_id=request.consumer_stable_id,
                    properties={"label": request.consumer_label or request.consumer_stable_id},
                )
            )
            second_edge = self.graph.add_edge(
                GraphEdgeCreate(
                    from_node_id=route.id,
                    to_node_id=consumer.id,
                    edge_type=GraphEdgeType.FLOWS_INTO,
                    confidence=1.0,
                    source_type=GraphEdgeSourceType.STATIC_ANALYSIS,
                    valid_from=valid_from,
                    properties={"trace_stage": "route_to_consumer"},
                )
            )
            consumer_node_id = consumer.id
            edge_ids.append(second_edge.id)

        return DataFlowTraceResult(
            schema_field_node_id=schema_field.id,
            route_node_id=route.id,
            consumer_node_id=consumer_node_id,
            edge_ids=edge_ids,
        )
