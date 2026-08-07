"""Observability surface: the event ledger and the agent network.

Both read from real system state. The event ledger is the graph event log the services already
append to. The agent network describes the actual orchestration services from the architecture and
derives each agent's activity by attributing recorded events back to the agent that produced them —
so status reflects what the seeded run actually did, not a mock snapshot.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from backend.agents.llm import LLMClient
from backend.graph.events import GraphEventWriter


class EventRecord(BaseModel):
    id: str
    event_type: str
    occurred_at: datetime
    summary: str
    aggregate_id: str


class SnapshotMarker(BaseModel):
    at: datetime
    repository: str
    files: int
    symbols: int
    score: float


class AgentNode(BaseModel):
    id: str
    name: str
    role: str
    layer: str
    status: str  # active | idle
    activity_count: int
    last_active: datetime | None
    current_task: str | None
    depends_on: list[str]


class AgentNetwork(BaseModel):
    agents: list[AgentNode]


# The real orchestration graph, curated from backend/main.py wiring and the cognitive architecture
# in PROJECT_OVERVIEW.md. `depends_on` is the upstream agent whose output this agent consumes.
_AGENTS: list[dict[str, Any]] = [
    {"id": "perception", "name": "Trust Boundary", "role": "Isolates ingested artifacts", "layer": "Perception", "depends_on": []},
    {"id": "retrieval", "name": "Context Assembly", "role": "Assembles reasoning context", "layer": "Planning", "depends_on": ["perception"]},
    {"id": "research", "name": "Research Agent", "role": "External recommendations", "layer": "Planning", "depends_on": ["perception"]},
    {"id": "planner", "name": "Planner", "role": "Blast-radius & strategy", "layer": "Planning", "depends_on": ["retrieval"]},
    {"id": "coder", "name": "Coder", "role": "Change proposals", "layer": "Planning", "depends_on": ["planner"]},
    {"id": "simulation", "name": "Digital Twin", "role": "Simulates proposed changes", "layer": "Simulation", "depends_on": ["planner"]},
    {"id": "chaos", "name": "Chaos Premortem", "role": "Fault injection", "layer": "Simulation", "depends_on": ["simulation"]},
    {"id": "verification", "name": "Verification", "role": "Validates proposals", "layer": "Verification", "depends_on": ["coder", "simulation"]},
    {"id": "policy", "name": "Execution Gate", "role": "Policy enforcement", "layer": "Verification", "depends_on": ["verification"]},
    {"id": "sandbox", "name": "Sandbox Runner", "role": "Executes in Docker", "layer": "Execution", "depends_on": ["policy"]},
    {"id": "architecture", "name": "Architecture Evolution", "role": "Tracks debt & coupling", "layer": "Understanding", "depends_on": []},
    {"id": "nightly", "name": "Nightly Review", "role": "Architecture review", "layer": "Understanding", "depends_on": ["architecture"]},
    {"id": "causal", "name": "Causal Graph", "role": "Chains cause & effect", "layer": "Understanding", "depends_on": []},
    {"id": "health", "name": "Repository Health", "role": "Scores the repo", "layer": "Verification", "depends_on": ["architecture"]},
    {"id": "incident", "name": "Incident Learning", "role": "Distills prevention rules", "layer": "Learning", "depends_on": ["verification"]},
    {"id": "distillation", "name": "Policy Distillation", "role": "Updates policies", "layer": "Learning", "depends_on": ["incident"]},
]


def _summary(event_type: str, payload: dict[str, Any]) -> str:
    if event_type == "graph.node.created":
        node_type = payload.get("node_type", "node")
        props = payload.get("properties", {}) or {}
        label = props.get("name") or props.get("path") or props.get("summary") or props.get("repository") or props.get("module_path") or ""
        label = str(label)[:48]
        return f"{node_type}{f' · {label}' if label else ''}"
    if event_type == "graph.edge.created":
        return f"{payload.get('edge_type', 'edge')} relation formed"
    if event_type == "artifact.ingested":
        return f"Ingested {payload.get('kind', 'artifact')} ({payload.get('trust_level', 'unknown')})"
    if event_type == "planner.blast_radius.computed":
        return "Blast radius computed"
    if event_type == "repository.ingested":
        return f"Ingested {payload.get('repository', 'repository')} ({payload.get('files', 0)} files)"
    return event_type


def _attribute(event_type: str, payload: dict[str, Any]) -> str:
    """Which agent produced this event."""
    if event_type == "artifact.ingested":
        return "perception"
    if event_type == "planner.blast_radius.computed":
        return "planner"
    if event_type == "graph.node.created":
        node_type = payload.get("node_type")
        props = payload.get("properties", {}) or {}
        if node_type == "CausalEvent":
            return "causal"
        if node_type == "ArchitectureTrend":
            return "architecture"
        if node_type == "HealthMetric":
            return "health"
        if node_type == "ExternalArtifact" or props.get("decision_kind") == "research_recommendation":
            return "research"
        return "perception"
    return "perception"


def create_observability_router(*, event_writer: GraphEventWriter, llm: LLMClient) -> APIRouter:
    router = APIRouter(prefix="/observability", tags=["observability"])

    @router.get("/usage")
    def usage_summary() -> dict:
        return llm.usage.summary()

    @router.get("/usage/records")
    def usage_records(limit: int = Query(default=100, ge=1, le=500)) -> list[dict]:
        return [
            {
                "at": r.at, "agent": r.agent, "model": r.model, "provider": r.provider,
                "prompt_tokens": r.prompt_tokens, "completion_tokens": r.completion_tokens,
                "total_tokens": r.total_tokens,
            }
            for r in llm.usage.records(limit)
        ]

    @router.get("/events", response_model=list[EventRecord])
    def list_events(limit: int = Query(default=80, ge=1, le=500)) -> list[EventRecord]:
        events = list(getattr(event_writer, "events", []))
        records = [
            EventRecord(
                id=str(e.id),
                event_type=e.event_type,
                occurred_at=e.occurred_at,
                summary=_summary(e.event_type, e.payload),
                aggregate_id=str(e.aggregate_id),
            )
            for e in events
        ]
        records.sort(key=lambda r: r.occurred_at, reverse=True)
        return records[:limit]

    @router.get("/snapshots", response_model=list[SnapshotMarker])
    def snapshots() -> list[SnapshotMarker]:
        events = list(getattr(event_writer, "events", []))
        markers = [
            SnapshotMarker(
                at=e.occurred_at,
                repository=e.payload.get("repository", "repository"),
                files=e.payload.get("files", 0),
                symbols=e.payload.get("symbols", 0),
                score=e.payload.get("score", 0.0),
            )
            for e in events
            if e.event_type == "repository.ingested"
        ]
        markers.sort(key=lambda m: m.at)
        return markers

    @router.get("/agents", response_model=AgentNetwork)
    def agent_network() -> AgentNetwork:
        events = list(getattr(event_writer, "events", []))
        counts: dict[str, int] = {}
        last: dict[str, datetime] = {}
        task: dict[str, str] = {}
        for e in sorted(events, key=lambda x: x.occurred_at):
            agent = _attribute(e.event_type, e.payload)
            counts[agent] = counts.get(agent, 0) + 1
            last[agent] = e.occurred_at
            task[agent] = _summary(e.event_type, e.payload)

        agents = [
            AgentNode(
                id=a["id"],
                name=a["name"],
                role=a["role"],
                layer=a["layer"],
                status="active" if counts.get(a["id"], 0) > 0 else "idle",
                activity_count=counts.get(a["id"], 0),
                last_active=last.get(a["id"]),
                current_task=task.get(a["id"]),
                depends_on=a["depends_on"],
            )
            for a in _AGENTS
        ]
        return AgentNetwork(agents=agents)

    return router
