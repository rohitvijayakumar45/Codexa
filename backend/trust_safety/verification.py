from __future__ import annotations

import re
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from backend.graph.events import GraphEventWriter


class VerificationStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"


class VerificationGate(BaseModel):
    name: str
    passed: bool
    reason: str


class VerificationRequest(BaseModel):
    proposal_id: UUID
    diff_text: str = Field(min_length=1)
    declared_test_commands: list[str] = Field(default_factory=list)


class VerificationResult(BaseModel):
    verification_id: UUID
    proposal_id: UUID
    status: VerificationStatus
    gates: list[VerificationGate]
    simulation_required: bool = True


class VerificationService:
    banned_stack_pattern = re.compile(r"\b(mongodb|mongoose|express(?:\.js)?)\b", re.I)
    test_pattern = re.compile(r"(^|[^a-zA-Z0-9])(pytest|unittest|tests?|test_[a-zA-Z0-9_]+)", re.I)

    def __init__(self, event_writer: GraphEventWriter) -> None:
        self.event_writer = event_writer

    def verify_proposal(self, request: VerificationRequest) -> VerificationResult:
        gates = [
            self._banned_stack_gate(request.diff_text),
            self._test_intent_gate(request.diff_text, request.declared_test_commands),
            VerificationGate(
                name="simulation_required",
                passed=True,
                reason="Proposal must pass Engineering Simulation Engine before execution.",
            ),
        ]
        status = (
            VerificationStatus.PASSED
            if all(gate.passed for gate in gates)
            else VerificationStatus.FAILED
        )
        result = VerificationResult(
            verification_id=uuid4(),
            proposal_id=request.proposal_id,
            status=status,
            gates=gates,
        )
        self.event_writer.append(
            event_type="verification.proposal.checked",
            aggregate_id=result.verification_id,
            payload=result.model_dump(mode="json"),
        )
        return result

    def _banned_stack_gate(self, diff_text: str) -> VerificationGate:
        match = self.banned_stack_pattern.search(diff_text)
        if match is None:
            return VerificationGate(
                name="banned_stack",
                passed=True,
                reason="No rejected storage/server stack detected.",
            )
        return VerificationGate(
            name="banned_stack",
            passed=False,
            reason=f"Rejected stack term detected: {match.group(0)}.",
        )

    def _test_intent_gate(
        self, diff_text: str, declared_test_commands: list[str]
    ) -> VerificationGate:
        has_tests = bool(self.test_pattern.search(diff_text) or declared_test_commands)
        if has_tests:
            return VerificationGate(
                name="test_intent",
                passed=True,
                reason="Proposal includes tests or declares test commands.",
            )
        return VerificationGate(
            name="test_intent",
            passed=False,
            reason="Proposal must include tests or declare verification commands.",
        )
