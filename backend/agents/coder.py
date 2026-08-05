from __future__ import annotations

from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from backend.graph.events import GraphEventWriter
from backend.agents.llm import LLMClient


class ChangeProposalStatus(StrEnum):
    PROPOSED = "proposed"


class ProposedFileChange(BaseModel):
    path: str = Field(min_length=1, max_length=1024)
    diff: str = Field(min_length=1)


class ChangeProposalRequest(BaseModel):
    objective: str = Field(min_length=1, max_length=2048)
    planner_analysis_id: UUID
    changes: list[ProposedFileChange] = Field(min_length=1)
    rationale: str = Field(min_length=1, max_length=4096)


class ChangeProposalResult(BaseModel):
    proposal_id: UUID
    status: ChangeProposalStatus
    objective: str
    changed_paths: list[str]
    planner_analysis_id: UUID
    simulation_required: bool = True


class CoderService:
    def __init__(self, event_writer: GraphEventWriter, llm: LLMClient) -> None:
        self.event_writer = event_writer
        self.llm = llm

    def record_proposal(self, request: ChangeProposalRequest) -> ChangeProposalResult:
        result = ChangeProposalResult(
            proposal_id=uuid4(),
            status=ChangeProposalStatus.PROPOSED,
            objective=request.objective,
            changed_paths=[change.path for change in request.changes],
            planner_analysis_id=request.planner_analysis_id,
        )
        self.event_writer.append(
            event_type="coder.change_proposal.created",
            aggregate_id=result.proposal_id,
            payload={
                **result.model_dump(mode="json"),
                "rationale": request.rationale,
                "changes": [change.model_dump() for change in request.changes],
            },
        )
        return result
