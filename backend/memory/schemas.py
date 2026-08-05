from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class IntentGraphRequest(BaseModel):
    source_artifact_id: UUID
    decision: str = Field(min_length=1, max_length=512)
    tradeoff: str = Field(min_length=1, max_length=512)
    rejected_alternative: str = Field(min_length=1, max_length=512)
    confidence: float = Field(ge=0, le=1)


class IntentGraphResult(BaseModel):
    decision_node_id: UUID
    tradeoff_node_id: UUID
    rejected_alternative_node_id: UUID
    edge_ids: list[UUID]


class ConventionProfileRequest(BaseModel):
    source_artifact_id: UUID
    team: str = Field(min_length=1, max_length=128)
    convention: str = Field(min_length=1, max_length=512)
    evidence: str = Field(min_length=1, max_length=1024)
    confidence: float = Field(ge=0, le=1)
    author: str | None = Field(default=None, max_length=128)


class ConventionProfileResult(BaseModel):
    profile_node_id: UUID
    source_node_id: UUID
    edge_id: UUID


class EngineeringDNARequest(BaseModel):
    source_artifact_id: UUID
    repository: str = Field(min_length=1, max_length=256)
    category: str = Field(min_length=1, max_length=128)
    convention: str = Field(min_length=1, max_length=512)
    evidence: str = Field(min_length=1, max_length=1024)
    confidence: float = Field(ge=0, le=1)


class EngineeringDNAResult(BaseModel):
    convention_node_id: UUID
    source_node_id: UUID
    edge_id: UUID
