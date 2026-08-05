from __future__ import annotations

from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from backend.graph.schemas import GraphNodeCreate, GraphNodeType
from backend.graph.service import GraphService


class PolicyDistillationRequest(BaseModel):
    repository: str = Field(min_length=1, max_length=256)
    accepted_change_ids: list[UUID] = Field(default_factory=list)
    reverted_change_ids: list[UUID] = Field(default_factory=list)
    review_comment_summaries: list[str] = Field(default_factory=list)
    incident_outcome_summaries: list[str] = Field(default_factory=list)


class PolicyDistillationResult(BaseModel):
    distillation_id: UUID
    memory_node_id: UUID
    repository: str
    prompt_template_delta: str
    risk_weight_delta: dict[str, float]
    retrieval_weight_delta: dict[str, float]
    version: int


class PolicyDistillationService:
    def __init__(self, graph: GraphService) -> None:
        self.graph = graph
        self._versions_by_repository: dict[str, int] = {}

    def distill(self, request: PolicyDistillationRequest) -> PolicyDistillationResult:
        version = self._versions_by_repository.get(request.repository, 0) + 1
        self._versions_by_repository[request.repository] = version
        reverted_pressure = min(len(request.reverted_change_ids) * 0.05, 0.25)
        incident_pressure = min(len(request.incident_outcome_summaries) * 0.08, 0.32)
        review_pressure = min(len(request.review_comment_summaries) * 0.03, 0.21)
        prompt_delta = self._prompt_delta(request)
        risk_delta = {
            "revert_history": round(reverted_pressure, 6),
            "incident_history": round(incident_pressure, 6),
            "review_friction": round(review_pressure, 6),
        }
        retrieval_delta = {
            "organizational_memory": round(0.1 + review_pressure, 6),
            "incident_prevention_rules": round(0.1 + incident_pressure, 6),
            "recent_reverts": round(reverted_pressure, 6),
        }
        node = self.graph.add_node(
            GraphNodeCreate(
                node_type=GraphNodeType.CONVENTION_PROFILE,
                stable_id=f"policy-distillation://{request.repository}/v{version}",
                properties={
                    "profile_kind": "policy_distillation",
                    "repository": request.repository,
                    "version": version,
                    "prompt_template_delta": prompt_delta,
                    "risk_weight_delta": risk_delta,
                    "retrieval_weight_delta": retrieval_delta,
                    "accepted_change_ids": [str(item) for item in request.accepted_change_ids],
                    "reverted_change_ids": [str(item) for item in request.reverted_change_ids],
                },
            )
        )
        result = PolicyDistillationResult(
            distillation_id=uuid4(),
            memory_node_id=node.id,
            repository=request.repository,
            prompt_template_delta=prompt_delta,
            risk_weight_delta=risk_delta,
            retrieval_weight_delta=retrieval_delta,
            version=version,
        )
        self.graph.event_writer.append(
            event_type="learning.policy_distillation.completed",
            aggregate_id=result.distillation_id,
            payload=result.model_dump(mode="json"),
        )
        return result

    def _prompt_delta(self, request: PolicyDistillationRequest) -> str:
        if request.incident_outcome_summaries:
            return "Prioritize prevention rules and regression tests from recent incidents."
        if request.reverted_change_ids:
            return "Increase scrutiny for patterns matching recently reverted changes."
        if request.review_comment_summaries:
            return "Retrieve team review conventions before generating implementation guidance."
        return "No behavioral prompt change; retain current repository conventions."
