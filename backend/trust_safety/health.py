from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from backend.graph.schemas import GraphNodeCreate, GraphNodeType
from backend.graph.service import GraphService


class RepositoryHealthRequest(BaseModel):
    repository: str = Field(min_length=1, max_length=256)
    maintainability: float = Field(ge=0, le=1)
    testability: float = Field(ge=0, le=1)
    coupling: float = Field(ge=0, le=1)
    doc_coverage: float = Field(ge=0, le=1)
    architecture_stability: float = Field(ge=0, le=1)
    deployment_safety: float = Field(ge=0, le=1)
    ownership_clarity: float = Field(ge=0, le=1)
    tech_debt_index: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)


class RepositoryHealthResult(BaseModel):
    health_node_id: UUID
    repository: str
    score: float = Field(ge=0, le=1)
    components: dict[str, float]


class RepositoryHealthService:
    def __init__(self, graph: GraphService) -> None:
        self.graph = graph

    def score(self, request: RepositoryHealthRequest) -> RepositoryHealthResult:
        components = {
            "maintainability": request.maintainability,
            "testability": request.testability,
            "coupling": 1 - request.coupling,
            "doc_coverage": request.doc_coverage,
            "architecture_stability": request.architecture_stability,
            "deployment_safety": request.deployment_safety,
            "ownership_clarity": request.ownership_clarity,
            "tech_debt": 1 - request.tech_debt_index,
            "confidence": request.confidence,
        }
        score = round(sum(components.values()) / len(components), 6)
        node = self.graph.add_node(
            GraphNodeCreate(
                node_type=GraphNodeType.HEALTH_METRIC,
                stable_id=f"repository-health://{request.repository}",
                properties={
                    "metric_kind": "repository_health",
                    "repository": request.repository,
                    "score": score,
                    "components": components,
                },
            )
        )
        return RepositoryHealthResult(
            health_node_id=node.id,
            repository=request.repository,
            score=score,
            components=components,
        )
