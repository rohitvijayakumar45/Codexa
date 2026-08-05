from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from backend.graph.schemas import GraphNodeCreate, GraphNodeType
from backend.graph.service import GraphService
from backend.understanding.architecture_evolution import ArchitectureEvolutionService


class NightlyArchitectureReviewRequest(BaseModel):
    repository: str = Field(min_length=1, max_length=256)
    knowledge_gaps: list[str] = Field(default_factory=list)
    open_draft_pr: bool = False


class NightlyArchitectureReviewResult(BaseModel):
    review_node_id: UUID
    repository: str
    draft_rfc_markdown: str
    human_approval_required: bool = True
    would_open_draft_pr: bool


class NightlyArchitectureReviewService:
    def __init__(
        self,
        *,
        graph: GraphService,
        architecture_evolution: ArchitectureEvolutionService,
    ) -> None:
        self.graph = graph
        self.architecture_evolution = architecture_evolution

    def run(self, request: NightlyArchitectureReviewRequest) -> NightlyArchitectureReviewResult:
        trends = self.architecture_evolution.list_trends()
        alerted = [trend for trend in trends if trend.alerts]
        findings = [
            f"- {trend.module_path}: {', '.join(trend.alerts)}"
            for trend in alerted
        ] or ["- No architecture trend alerts found."]
        gaps = [f"- {gap}" for gap in request.knowledge_gaps] or ["- No knowledge gaps supplied."]
        markdown = "\n".join(
            [
                f"# Nightly Architecture Review: {request.repository}",
                "",
                "## Architecture Findings",
                *findings,
                "",
                "## Knowledge Gaps",
                *gaps,
                "",
                "## Approval Gate",
                "This draft requires human approval before any PR or repo mutation.",
            ]
        )
        node = self.graph.add_node(
            GraphNodeCreate(
                node_type=GraphNodeType.DECISION,
                stable_id=f"nightly-architecture-review://{request.repository}",
                properties={
                    "decision_kind": "nightly_architecture_review",
                    "repository": request.repository,
                    "draft_rfc_markdown": markdown,
                    "human_approval_required": True,
                    "would_open_draft_pr": request.open_draft_pr,
                },
            )
        )
        result = NightlyArchitectureReviewResult(
            review_node_id=node.id,
            repository=request.repository,
            draft_rfc_markdown=markdown,
            would_open_draft_pr=request.open_draft_pr,
        )
        self.graph.event_writer.append(
            event_type="nightly_architecture_review.draft_generated",
            aggregate_id=result.review_node_id,
            payload=result.model_dump(mode="json"),
        )
        return result
