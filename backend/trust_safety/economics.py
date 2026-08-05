from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from backend.graph.schemas import GraphNodeCreate, GraphNodeType
from backend.graph.service import GraphService


class EngineeringEconomicsRequest(BaseModel):
    proposal: str = Field(min_length=1, max_length=512)
    changed_files: int = Field(ge=0)
    changed_lines: int = Field(ge=0)
    test_delta: int = Field(default=0)
    historical_review_hours: float = Field(default=2.0, ge=0)
    shortcut_taken: bool = False


class EngineeringEconomicsResult(BaseModel):
    tradeoff_node_id: UUID
    proposal: str
    implementation_effort_hours: float = Field(ge=0)
    projected_maintenance_hours: float = Field(ge=0)
    technical_debt_score: float = Field(ge=0, le=1)
    tradeoff_statement: str


class EngineeringEconomicsService:
    def __init__(self, graph: GraphService) -> None:
        self.graph = graph

    def estimate(self, request: EngineeringEconomicsRequest) -> EngineeringEconomicsResult:
        implementation_effort = round(
            request.historical_review_hours
            + request.changed_files * 0.4
            + request.changed_lines / 180,
            2,
        )
        test_credit = min(request.test_delta * 0.03, 0.25)
        debt_score = min(
            1.0,
            max(
                0.0,
                request.changed_files * 0.04
                + request.changed_lines / 1200
                + (0.25 if request.shortcut_taken else 0)
                - test_credit,
            ),
        )
        maintenance = round(implementation_effort * (0.5 + debt_score * 1.5), 2)
        statement = (
            f"This plan is estimated at {implementation_effort}h now and "
            f"{maintenance}h future maintenance."
        )
        node = self.graph.add_node(
            GraphNodeCreate(
                node_type=GraphNodeType.TRADEOFF,
                stable_id=f"engineering-economics://{request.proposal}",
                properties={
                    "proposal": request.proposal,
                    "implementation_effort_hours": implementation_effort,
                    "projected_maintenance_hours": maintenance,
                    "technical_debt_score": round(debt_score, 6),
                    "tradeoff_statement": statement,
                },
            )
        )
        return EngineeringEconomicsResult(
            tradeoff_node_id=node.id,
            proposal=request.proposal,
            implementation_effort_hours=implementation_effort,
            projected_maintenance_hours=maintenance,
            technical_debt_score=round(debt_score, 6),
            tradeoff_statement=statement,
        )
