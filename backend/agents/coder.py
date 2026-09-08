from __future__ import annotations

import json
import re
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


class ProposeChangeRequest(BaseModel):
    repository: str = Field(min_length=1, max_length=100)
    objective: str = Field(min_length=1, max_length=2000)
    file_paths: list[str] = Field(default_factory=list, max_length=8)
    model: str | None = None


class ProposeChangeResult(BaseModel):
    proposal_id: UUID
    status: ChangeProposalStatus
    objective: str
    changed_paths: list[str]
    changes: list[ProposedFileChange]
    rationale: str


_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


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

    def propose(self, request: ProposeChangeRequest) -> ProposeChangeResult:
        """The real, callable entry point `record_proposal` never got wired to — it only persists a
        diff/rationale someone else already produced. This is the piece that was missing: read the
        named files, ask the LLM to actually produce the diff and rationale, then persist it through
        the same event path so the agent-network dashboard attributes real activity to this node."""
        from backend.files.api import read_file, repo_root

        file_blocks: list[str] = []
        for path in request.file_paths[:8]:
            try:
                content = read_file(repo_root(request.repository), path)
                body = content.content[:4000]
                file_blocks.append(f"=== {path} ===\n{body}")
            except Exception as exc:  # noqa: BLE001 - a missing/unreadable file shouldn't abort the whole proposal
                file_blocks.append(f"=== {path} ===\n(unreadable: {exc})")

        prompt = (
            f"You are the coding agent for the repository '{request.repository}'. "
            f"Objective: {request.objective}\n\n"
            + ("Current file contents:\n" + "\n\n".join(file_blocks) + "\n\n" if file_blocks else "")
            + "Respond with ONLY a JSON object (no markdown fences, no commentary) shaped exactly "
            'like: {"changes": [{"path": "relative/path", "diff": "unified diff or full new file '
            'content"}], "rationale": "why this change accomplishes the objective, in 2-4 sentences"}. '
            "Include one entry per file that needs to change. If you can't produce a concrete diff "
            "without more information, return an empty changes list and explain what's missing in "
            "rationale."
        )
        raw = self.llm.complete([{"role": "user", "content": prompt}], model=request.model, agent="coder")
        changes, rationale = self._parse_proposal(raw, request.file_paths)

        planner_analysis_id = uuid4()
        record = self.record_proposal(ChangeProposalRequest(
            objective=request.objective,
            planner_analysis_id=planner_analysis_id,
            changes=changes,
            rationale=rationale,
        ))
        return ProposeChangeResult(
            proposal_id=record.proposal_id,
            status=record.status,
            objective=record.objective,
            changed_paths=record.changed_paths,
            changes=changes,
            rationale=rationale,
        )

    @staticmethod
    def _parse_proposal(raw: str, fallback_paths: list[str]) -> tuple[list[ProposedFileChange], str]:
        """Robust against a model that doesn't follow the JSON-only instruction exactly (fenced
        code blocks, leading prose) — never lets a malformed response crash the request; falls back
        to recording the raw analysis as a single observational entry so nothing is silently lost."""
        match = _JSON_BLOCK.search(raw)
        if match:
            try:
                data = json.loads(match.group(0))
                raw_changes = data.get("changes") or []
                changes = [
                    ProposedFileChange(path=c["path"], diff=c["diff"])
                    for c in raw_changes
                    if isinstance(c, dict) and c.get("path") and c.get("diff")
                ]
                rationale = str(data.get("rationale") or "").strip()
                if changes and rationale:
                    return changes, rationale
                if rationale:
                    # Valid JSON, real rationale, but no concrete diff — still a real analysis
                    # result, not a parse failure; record it as a no-op observation.
                    path = fallback_paths[0] if fallback_paths else "NOTES.md"
                    return [ProposedFileChange(path=path, diff="(no concrete diff — see rationale)")], rationale
            except (json.JSONDecodeError, KeyError, TypeError):
                pass
        # Total parse failure — record the raw model output as the rationale rather than dropping it.
        path = fallback_paths[0] if fallback_paths else "NOTES.md"
        return (
            [ProposedFileChange(path=path, diff="(model did not return a parseable diff)")],
            raw.strip()[:4000] or "No rationale produced.",
        )
