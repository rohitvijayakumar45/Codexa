from __future__ import annotations

from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from backend.graph.events import GraphEventWriter


class PolicyDecision(StrEnum):
    APPROVED = "approved"
    BLOCKED = "blocked"


class ExecutionGateRequest(BaseModel):
    proposal_id: UUID
    simulation_id: UUID | None = None
    simulation_passed: bool = False
    verification_passed: bool = False
    risk_score: float = Field(ge=0, le=1)
    adversarial_findings: list[str] = Field(default_factory=list)


class ExecutionGateResult(BaseModel):
    decision_id: UUID
    proposal_id: UUID
    decision: PolicyDecision
    reasons: list[str]


class PolicyEngine:
    def __init__(self, event_writer: GraphEventWriter) -> None:
        self.event_writer = event_writer

    def evaluate_execution_gate(self, request: ExecutionGateRequest) -> ExecutionGateResult:
        reasons: list[str] = []
        if request.simulation_id is None:
            reasons.append("missing_simulation")
        if not request.simulation_passed:
            reasons.append("simulation_not_passed")
        if not request.verification_passed:
            reasons.append("verification_not_passed")
        if request.risk_score >= 0.8:
            reasons.append("risk_score_requires_human_approval")
        if request.adversarial_findings:
            reasons.append("adversarial_findings_present")

        result = ExecutionGateResult(
            decision_id=uuid4(),
            proposal_id=request.proposal_id,
            decision=PolicyDecision.BLOCKED if reasons else PolicyDecision.APPROVED,
            reasons=reasons,
        )
        self.event_writer.append(
            event_type="policy.execution_gate.evaluated",
            aggregate_id=result.decision_id,
            payload=result.model_dump(mode="json"),
        )
        return result
