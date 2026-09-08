from __future__ import annotations

import hashlib
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from backend.graph.events import GraphEventWriter
from backend.graph.service import GraphService
from backend.simulation.witness import hash_graph_state


class SandboxRunStatus(StrEnum):
    BLOCKED = "blocked"
    SCHEDULED = "scheduled"


class SandboxCommand(BaseModel):
    command: str = Field(min_length=1, max_length=2048)
    timeout_seconds: int = Field(default=300, ge=1, le=3600)


class SandboxRunRequest(BaseModel):
    proposal_id: UUID
    diff_text: str = Field(min_length=1)
    image: str = Field(default="python:3.12-slim", min_length=1, max_length=256)
    commands: list[SandboxCommand] = Field(min_length=1)


class SandboxRunResult(BaseModel):
    run_id: UUID
    proposal_id: UUID
    status: SandboxRunStatus
    image: str
    docker_args: list[str]
    commands: list[SandboxCommand]
    blocked_reasons: list[str]


class SandboxExecutionService:
    def __init__(self, event_writer: GraphEventWriter, graph: GraphService) -> None:
        self.event_writer = event_writer
        self.graph = graph

    def schedule_run(self, request: SandboxRunRequest) -> SandboxRunResult:
        blocked_reasons: list[str] = []
        
        # Verify simulation status from the source of truth
        nodes = self.graph.repository.list_nodes()
        scenario_nodes = [
            node for node in nodes
            if node.node_type == "SimulationScenario" 
            and node.properties.get("proposal_id") == str(request.proposal_id)
        ]
        
        if not scenario_nodes:
            blocked_reasons.append("missing_simulation_record")
        else:
            scenario_node = sorted(scenario_nodes, key=lambda n: n.created_at, reverse=True)[0]
            if scenario_node.properties.get("status") != "passed":
                blocked_reasons.append("simulation_blocked")
            else:
                diff_hash = hashlib.sha256(request.diff_text.encode("utf-8")).hexdigest()
                if scenario_node.properties.get("diff_hash") != diff_hash:
                    blocked_reasons.append("simulation_content_mismatch")
                # Beyond the diff itself: re-hash the exact dependency subgraph the simulation's
                # verdict was based on (backend/simulation/witness.py) and refuse to run if it
                # drifted since — a dependency renamed, deleted, or rewired between simulate and
                # execute would leave the diff hash untouched but silently invalidate the blast-radius
                # conclusion PASSED was based on.
                witness_ids = scenario_node.properties.get("witness_node_ids")
                stored_state_hash = scenario_node.properties.get("graph_state_hash")
                if witness_ids is not None and stored_state_hash is not None:
                    current_state_hash = hash_graph_state({UUID(wid) for wid in witness_ids}, graph=self.graph)
                    if current_state_hash != stored_state_hash:
                        blocked_reasons.append("graph_state_changed")

        result = SandboxRunResult(
            run_id=uuid4(),
            proposal_id=request.proposal_id,
            status=SandboxRunStatus.BLOCKED if blocked_reasons else SandboxRunStatus.SCHEDULED,
            image=request.image,
            docker_args=[
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--read-only",
                request.image,
            ],
            commands=request.commands,
            blocked_reasons=blocked_reasons,
        )
        self.event_writer.append(
            event_type="execution.sandbox_run.scheduled",
            aggregate_id=result.run_id,
            payload=result.model_dump(mode="json"),
        )
        return result
