from __future__ import annotations

import hashlib
import re
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from backend.agents.planner import BlastRadiusRequest, PlannerService
from backend.graph.schemas import GraphNodeCreate, GraphNodeType
from backend.graph.service import GraphService


class SimulationStatus(StrEnum):
    PASSED = "passed"
    BLOCKED = "blocked"


class SimulationRequest(BaseModel):
    proposal_id: UUID
    changed_node_ids: list[UUID] = Field(min_length=1)
    diff_text: str = Field(min_length=1)
    deployment_steps: list[str] = Field(default_factory=list)
    rollback_steps: list[str] = Field(default_factory=list)
    max_depth: int = Field(default=4, ge=1, le=8)


class SimulationResult(BaseModel):
    simulation_id: UUID
    proposal_id: UUID
    status: SimulationStatus
    predicted_blast_radius_node_ids: list[UUID]
    predicted_test_failures: list[str]
    predicted_performance_delta_ms: float
    rollback_viable: bool
    deployment_sequence_viable: bool
    confidence: float = Field(ge=0, le=1)
    scenario_node_id: UUID


class EngineeringSimulationEngine:
    schema_change_pattern = re.compile(r"\b(alter\s+table|drop\s+column|jsonb|migration)\b", re.I)
    destructive_schema_pattern = re.compile(r"\bdrop\s+column\b", re.I)

    def __init__(self, graph: GraphService, planner: PlannerService) -> None:
        self.graph = graph
        self.planner = planner

    def run(self, request: SimulationRequest) -> SimulationResult:
        blast_radius = self.planner.compute_blast_radius(
            BlastRadiusRequest(
                changed_node_ids=request.changed_node_ids,
                max_depth=request.max_depth,
            )
        )
        affected_count = len(blast_radius.affected_node_ids)
        schema_change = bool(self.schema_change_pattern.search(request.diff_text))
        destructive_schema_change = bool(self.destructive_schema_pattern.search(request.diff_text))
        rollback_viable = bool(request.rollback_steps) and not (
            destructive_schema_change and not self._has_explicit_restore_step(request.rollback_steps)
        )
        deployment_sequence_viable = bool(request.deployment_steps)
        predicted_failures = self._predicted_failures(
            schema_change=schema_change,
            affected_count=affected_count,
            rollback_viable=rollback_viable,
            deployment_sequence_viable=deployment_sequence_viable,
        )
        confidence = max(
            0.2,
            min(
                0.95,
                0.9
                - (affected_count * 0.03)
                - (0.1 if schema_change else 0)
                - (0.15 if predicted_failures else 0),
            ),
        )
        status = (
            SimulationStatus.PASSED
            if rollback_viable and deployment_sequence_viable and not predicted_failures
            else SimulationStatus.BLOCKED
        )
        
        diff_hash = hashlib.sha256(request.diff_text.encode("utf-8")).hexdigest()

        scenario_node = self.graph.add_node(
            GraphNodeCreate(
                node_type=GraphNodeType.SIMULATION_SCENARIO,
                stable_id=f"simulation://{uuid4()}",
                properties={
                    "proposal_id": str(request.proposal_id),
                    "diff_hash": diff_hash,
                    "status": status,
                    "affected_count": affected_count,
                    "predicted_failures": predicted_failures,
                    "confidence": confidence,
                },
            )
        )
        result = SimulationResult(
            simulation_id=uuid4(),
            proposal_id=request.proposal_id,
            status=status,
            predicted_blast_radius_node_ids=blast_radius.affected_node_ids,
            predicted_test_failures=predicted_failures,
            predicted_performance_delta_ms=(affected_count * 5.0) + (20.0 if schema_change else 0.0),
            rollback_viable=rollback_viable,
            deployment_sequence_viable=deployment_sequence_viable,
            confidence=confidence,
            scenario_node_id=scenario_node.id,
        )
        self.graph.event_writer.append(
            event_type="simulation.scenario.completed",
            aggregate_id=result.simulation_id,
            payload=result.model_dump(mode="json"),
        )
        return result

    def _predicted_failures(
        self,
        *,
        schema_change: bool,
        affected_count: int,
        rollback_viable: bool,
        deployment_sequence_viable: bool,
    ) -> list[str]:
        failures: list[str] = []
        if schema_change:
            failures.append("schema_contract_tests")
        if affected_count > 5:
            failures.append("integration_tests")
        if not rollback_viable:
            failures.append("rollback_viability")
        if not deployment_sequence_viable:
            failures.append("deployment_sequence")
        return failures

    def _has_explicit_restore_step(self, rollback_steps: list[str]) -> bool:
        return any(re.search(r"\b(restore|backfill|recreate)\b", step, re.I) for step in rollback_steps)
