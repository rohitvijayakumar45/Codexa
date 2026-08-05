from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator


class GraphNodeType(StrEnum):
    REPOSITORY = "Repository"
    FILE = "File"
    CODE_SYMBOL = "CodeSymbol"
    API_ROUTE = "ApiRoute"
    SCHEMA_FIELD = "SchemaField"
    EXTERNAL_ARTIFACT = "ExternalArtifact"
    ARCHITECTURE_TREND = "ArchitectureTrend"
    SIMULATION_SCENARIO = "SimulationScenario"
    CAUSAL_EVENT = "CausalEvent"
    DECISION = "Decision"
    TRADEOFF = "Tradeoff"
    REJECTED_ALTERNATIVE = "RejectedAlternative"
    ONBOARDING_PATH = "OnboardingPath"
    HEALTH_METRIC = "HealthMetric"
    PREVENTION_RULE = "PreventionRule"
    CONVENTION_PROFILE = "ConventionProfile"


class GraphEdgeType(StrEnum):
    CALLS = "calls"
    IMPORTS = "imports"
    DEPENDS_ON = "depends_on"
    CAUSES = "causes"
    MITIGATES = "mitigates"
    INCREASES_RISK_OF = "increases_risk_of"
    CORRELATES_WITH = "correlates_with"
    DERIVED_FROM = "derived_from"
    SUPERSEDES = "supersedes"
    FLOWS_INTO = "flows_into"
    TRACES_TO_DECISION = "traces_to_decision"


class GraphEdgeSourceType(StrEnum):
    STATIC_ANALYSIS = "static_analysis"
    LLM_INFERRED = "llm_inferred"
    HUMAN_ASSERTED = "human_asserted"


class GraphNodeCreate(BaseModel):
    node_type: GraphNodeType
    stable_id: str = Field(min_length=1, max_length=512)
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphNode(GraphNodeCreate):
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class GraphEdgeCreate(BaseModel):
    from_node_id: UUID
    to_node_id: UUID
    edge_type: GraphEdgeType
    confidence: float = Field(ge=0, le=1)
    source_type: GraphEdgeSourceType
    valid_from: datetime = Field(default_factory=lambda: datetime.now(UTC))
    valid_to: datetime | None = None
    source_artifact_id: UUID | None = None
    properties: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_spec_invariants(self) -> "GraphEdgeCreate":
        if self.valid_to is not None and self.valid_to <= self.valid_from:
            raise ValueError("valid_to must be after valid_from")
        if self.source_type == GraphEdgeSourceType.STATIC_ANALYSIS and self.confidence != 1.0:
            raise ValueError("static_analysis edges must have confidence 1.0")
        if self.source_type == GraphEdgeSourceType.LLM_INFERRED and self.source_artifact_id is None:
            raise ValueError("llm_inferred edges must cite source_artifact_id")
        return self


class GraphEdge(GraphEdgeCreate):
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class GraphSnapshot(BaseModel):
    at_time: datetime | None = None
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class GraphTimeline(BaseModel):
    starts_at: datetime | None = None
    ends_at: datetime | None = None
