import hashlib
from uuid import uuid4
from unittest.mock import MagicMock
from backend.simulation.engine import (
    EngineeringSimulationEngine,
    SimulationRequest,
    SimulationStatus,
)
from backend.execution.sandbox import (
    SandboxExecutionService,
    SandboxRunRequest,
    SandboxRunStatus,
    SandboxCommand,
)
from backend.agents.planner import PlannerService
from backend.graph.service import GraphService
from backend.graph.repository import InMemoryGraphRepository
from backend.graph.events import InMemoryGraphEventWriter
from backend.graph.schemas import GraphNodeCreate, GraphNodeType, GraphNodeProvenance


def test_claim_simulation_and_blast_radius():
    """Claim: Simulation engine computes blast radius and flags destructive schema changes as BLOCKED."""
    repo = InMemoryGraphRepository()
    event_writer = InMemoryGraphEventWriter()
    svc = GraphService(repository=repo, event_writer=event_writer)
    planner = PlannerService(repository=repo, event_writer=event_writer, llm=MagicMock())
    engine = EngineeringSimulationEngine(graph=svc, planner=planner)

    n1 = svc.add_node(GraphNodeCreate(
        node_type=GraphNodeType.FILE,
        stable_id="models.py",
        properties={},
        provenance=GraphNodeProvenance.INTERNAL_CODE,
    ))

    # Schema change with DROP COLUMN without explicit restore step -> BLOCKED
    req = SimulationRequest(
        proposal_id=uuid4(),
        changed_node_ids=[n1.id],
        diff_text="ALTER TABLE users DROP COLUMN email;",
        deployment_steps=["run migration"],
        rollback_steps=["rollback"],
    )

    result = engine.run(req)
    # The destructive schema change without an explicit restore step is correctly BLOCKED
    assert result.status == SimulationStatus.BLOCKED
    assert result.scenario_node_id is not None


def test_claim_content_binding_integrity_and_sandbox_hash_gating():
    """Claim: Sandbox execution verifies the diff SHA-256 matches the simulation record."""
    repo = InMemoryGraphRepository()
    event_writer = InMemoryGraphEventWriter()
    svc = GraphService(repository=repo, event_writer=event_writer)
    planner = PlannerService(repository=repo, event_writer=event_writer, llm=MagicMock())
    engine = EngineeringSimulationEngine(graph=svc, planner=planner)
    sandbox = SandboxExecutionService(event_writer=event_writer, graph=svc)

    n1 = svc.add_node(GraphNodeCreate(
        node_type=GraphNodeType.FILE,
        stable_id="api.py",
        properties={},
        provenance=GraphNodeProvenance.INTERNAL_CODE,
    ))

    proposal_id = uuid4()
    diff_text = "def new_feature(): pass"

    # Run non-destructive simulation
    sim_res = engine.run(SimulationRequest(
        proposal_id=proposal_id,
        changed_node_ids=[n1.id],
        diff_text=diff_text,
        deployment_steps=["deploy"],
        rollback_steps=["rollback"],
    ))
    assert sim_res.status == SimulationStatus.PASSED

    # 1. Matching diff -> SCHEDULED
    run_ok = sandbox.schedule_run(SandboxRunRequest(
        proposal_id=proposal_id,
        diff_text=diff_text,
        commands=[SandboxCommand(command="pytest")]
    ))
    assert run_ok.status == SandboxRunStatus.SCHEDULED
    assert "docker" in run_ok.docker_args

    # 2. Tampered diff (different bytes) -> BLOCKED
    run_tampered = sandbox.schedule_run(SandboxRunRequest(
        proposal_id=proposal_id,
        diff_text="def malicious_payload(): evil()",
        commands=[SandboxCommand(command="pytest")]
    ))
    assert run_tampered.status == SandboxRunStatus.BLOCKED
    assert "simulation_content_mismatch" in run_tampered.blocked_reasons
