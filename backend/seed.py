"""Development seed for the Engineering Knowledge Graph.

The graph store boots empty. Rather than let the frontend fabricate mock data, this module
populates the graph with a real, self-referential dataset: Codexa OS describing its own backend
(repository, module files, service symbols, API routes), plus the derived cognition subsystems
exercise their own services (architecture trends, causal chains, repository health). Everything
here goes through the same validated services and edge invariants the public API enforces, so the
seeded state is indistinguishable from data created via HTTP.

Usage:
    - Automatic: set CODEXA_SEED=1 (or true) and the FastAPI app seeds on startup when the store
      is empty and in-memory.
    - Manual (in-process, in-memory only): ``python -m backend.seed`` prints a summary.

Seeding is idempotent: node stable_ids upsert, and ``seed_graph`` is a no-op if nodes already
exist.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from backend.graph.causal import CausalChainRequest, CausalEventInput, CausalGraphService
from backend.graph.schemas import (
    GraphEdgeCreate,
    GraphEdgeSourceType,
    GraphEdgeType,
    GraphNode,
    GraphNodeCreate,
    GraphNodeType,
)
from backend.graph.service import GraphService
from backend.trust_safety.health import RepositoryHealthRequest, RepositoryHealthService
from backend.understanding.architecture_evolution import (
    ArchitectureEvolutionService,
    ArchitectureObservation,
    ArchitectureTrendRequest,
)

# A fixed reference point keeps the seeded timeline stable within a run. Ninety days of history
# gives the time-scrubber a meaningful window to replay.
NOW = datetime.now(UTC)


def days_ago(days: float) -> datetime:
    return NOW - timedelta(days=days)


@dataclass(frozen=True)
class NodeSpec:
    key: str
    node_type: GraphNodeType
    stable_id: str
    properties: dict


@dataclass(frozen=True)
class EdgeSpec:
    from_key: str
    to_key: str
    edge_type: GraphEdgeType
    confidence: float
    source_type: GraphEdgeSourceType
    valid_from: datetime
    valid_to: datetime | None = None
    cite_artifact: bool = False
    properties: dict | None = None


# Every llm_inferred edge must cite a source artifact id. We mint one stable synthetic artifact to
# stand in for the PR/review the inference was drawn from.
INFERENCE_ARTIFACT_ID: UUID = uuid4()


def _node_specs() -> list[NodeSpec]:
    return [
        # Repository root.
        NodeSpec("repo", GraphNodeType.REPOSITORY, "repo://codexa-os",
                 {"name": "codexa-os", "primary_language": "Python", "framework": "FastAPI"}),
        # Backend module files (the real directories under backend/).
        NodeSpec("f_graph", GraphNodeType.FILE, "file://backend/graph/service.py",
                 {"path": "backend/graph/service.py", "loc": 87, "role": "graph core"}),
        NodeSpec("f_agents", GraphNodeType.FILE, "file://backend/agents/planner.py",
                 {"path": "backend/agents/planner.py", "loc": 142, "role": "planning"}),
        NodeSpec("f_sim", GraphNodeType.FILE, "file://backend/simulation/engine.py",
                 {"path": "backend/simulation/engine.py", "loc": 168, "role": "digital twin"}),
        NodeSpec("f_causal", GraphNodeType.FILE, "file://backend/graph/causal.py",
                 {"path": "backend/graph/causal.py", "loc": 96, "role": "causal graph"}),
        NodeSpec("f_health", GraphNodeType.FILE, "file://backend/trust_safety/health.py",
                 {"path": "backend/trust_safety/health.py", "loc": 66, "role": "health scoring"}),
        NodeSpec("f_retrieval", GraphNodeType.FILE, "file://backend/agents/retrieval.py",
                 {"path": "backend/agents/retrieval.py", "loc": 121, "role": "context assembly"}),
        NodeSpec("f_trust", GraphNodeType.FILE, "file://backend/perception/trust_boundary.py",
                 {"path": "backend/perception/trust_boundary.py", "loc": 74, "role": "isolation"}),
        # Service symbols (the classes that do the work).
        NodeSpec("s_graph", GraphNodeType.CODE_SYMBOL, "symbol://GraphService",
                 {"name": "GraphService", "kind": "class", "file": "backend/graph/service.py"}),
        NodeSpec("s_planner", GraphNodeType.CODE_SYMBOL, "symbol://PlannerService",
                 {"name": "PlannerService", "kind": "class", "file": "backend/agents/planner.py"}),
        NodeSpec("s_sim", GraphNodeType.CODE_SYMBOL, "symbol://EngineeringSimulationEngine",
                 {"name": "EngineeringSimulationEngine", "kind": "class"}),
        NodeSpec("s_causal", GraphNodeType.CODE_SYMBOL, "symbol://CausalGraphService",
                 {"name": "CausalGraphService", "kind": "class"}),
        NodeSpec("s_retrieval", GraphNodeType.CODE_SYMBOL, "symbol://ContextAssemblyService",
                 {"name": "ContextAssemblyService", "kind": "class"}),
        # API routes (real endpoints).
        NodeSpec("r_snapshot", GraphNodeType.API_ROUTE, "route://GET/graph/snapshots",
                 {"method": "GET", "path": "/graph/snapshots"}),
        NodeSpec("r_blast", GraphNodeType.API_ROUTE, "route://POST/agents/planner/blast-radius",
                 {"method": "POST", "path": "/agents/planner/blast-radius"}),
        NodeSpec("r_sim", GraphNodeType.API_ROUTE, "route://POST/simulation/scenarios",
                 {"method": "POST", "path": "/simulation/scenarios"}),
        NodeSpec("r_ctx", GraphNodeType.API_ROUTE, "route://POST/agents/retrieval/context",
                 {"method": "POST", "path": "/agents/retrieval/context"}),
        # Organizational intent: a real ADR-shaped decision with its trade-off and rejected option.
        NodeSpec("d_store", GraphNodeType.DECISION, "decision://postgres-source-of-truth",
                 {"title": "PostgreSQL JSONB as source of truth",
                  "summary": "Graph nodes/edges persist in Postgres; Neo4j/Qdrant are projections."}),
        NodeSpec("t_store", GraphNodeType.TRADEOFF, "tradeoff://write-simplicity-vs-graph-queries",
                 {"summary": "Simpler writes and one source of truth, at the cost of slower "
                             "native graph traversal until projected to Neo4j."}),
        NodeSpec("x_store", GraphNodeType.REJECTED_ALTERNATIVE, "rejected://neo4j-as-source-of-truth",
                 {"summary": "Neo4j as primary store", "reason": "Weaker transactional guarantees "
                             "for the ingest pipeline."}),
        # A prevention rule distilled from a past incident, and a convention profile.
        NodeSpec("p_rule", GraphNodeType.PREVENTION_RULE, "prevention://validate-edge-time-window",
                 {"rule": "Reject edges where valid_to <= valid_from",
                  "origin_incident": "temporal-overlap-2025-06"}),
        NodeSpec("c_profile", GraphNodeType.CONVENTION_PROFILE, "convention://python-typed-pydantic",
                 {"summary": "Typed Pydantic v2 request/response models on every route."}),
    ]


def _edge_specs() -> list[EdgeSpec]:
    sa = GraphEdgeSourceType.STATIC_ANALYSIS  # confidence must be exactly 1.0
    llm = GraphEdgeSourceType.LLM_INFERRED    # must cite a source artifact
    human = GraphEdgeSourceType.HUMAN_ASSERTED
    return [
        # Repository contains its module files (human-asserted structural facts).
        *[
            EdgeSpec("repo", f, GraphEdgeType.DEPENDS_ON, 0.95, human, days_ago(90))
            for f in ("f_graph", "f_agents", "f_sim", "f_causal", "f_health", "f_retrieval", "f_trust")
        ],
        # Files import files (static analysis, confidence locked at 1.0).
        EdgeSpec("f_agents", "f_graph", GraphEdgeType.IMPORTS, 1.0, sa, days_ago(88)),
        EdgeSpec("f_sim", "f_graph", GraphEdgeType.IMPORTS, 1.0, sa, days_ago(80)),
        EdgeSpec("f_sim", "f_agents", GraphEdgeType.IMPORTS, 1.0, sa, days_ago(72)),
        EdgeSpec("f_causal", "f_graph", GraphEdgeType.IMPORTS, 1.0, sa, days_ago(70)),
        EdgeSpec("f_health", "f_graph", GraphEdgeType.IMPORTS, 1.0, sa, days_ago(64)),
        EdgeSpec("f_retrieval", "f_graph", GraphEdgeType.IMPORTS, 1.0, sa, days_ago(60)),
        # Symbols call symbols (static analysis).
        EdgeSpec("s_planner", "s_graph", GraphEdgeType.CALLS, 1.0, sa, days_ago(86)),
        EdgeSpec("s_sim", "s_planner", GraphEdgeType.CALLS, 1.0, sa, days_ago(78)),
        EdgeSpec("s_causal", "s_graph", GraphEdgeType.CALLS, 1.0, sa, days_ago(68)),
        EdgeSpec("s_retrieval", "s_graph", GraphEdgeType.CALLS, 1.0, sa, days_ago(58)),
        # Routes flow into the symbols that serve them.
        EdgeSpec("r_snapshot", "s_graph", GraphEdgeType.FLOWS_INTO, 0.92, human, days_ago(84)),
        EdgeSpec("r_blast", "s_planner", GraphEdgeType.FLOWS_INTO, 0.92, human, days_ago(76)),
        EdgeSpec("r_sim", "s_sim", GraphEdgeType.FLOWS_INTO, 0.92, human, days_ago(74)),
        EdgeSpec("r_ctx", "s_retrieval", GraphEdgeType.FLOWS_INTO, 0.92, human, days_ago(56)),
        # An llm-inferred coupling the model surfaced from a PR review (must cite artifact).
        EdgeSpec("s_retrieval", "s_causal", GraphEdgeType.CORRELATES_WITH, 0.61, llm,
                 days_ago(40), cite_artifact=True,
                 properties={"note": "retrieval weighting co-varies with causal confidence"}),
        # A dependency that existed then was removed (superseded): the old direct coupling.
        EdgeSpec("s_sim", "s_graph", GraphEdgeType.DEPENDS_ON, 0.8, human,
                 days_ago(90), valid_to=days_ago(30),
                 properties={"note": "direct coupling, later routed through planner"}),
        EdgeSpec("s_sim", "s_graph", GraphEdgeType.DEPENDS_ON, 0.7, human, days_ago(30),
                 properties={"supersedes_note": "now indirect via planner"}),
        # Organizational intent: decision, its trade-off, its rejected alternative.
        EdgeSpec("d_store", "t_store", GraphEdgeType.TRACES_TO_DECISION, 0.9, human, days_ago(85)),
        EdgeSpec("x_store", "d_store", GraphEdgeType.SUPERSEDES, 0.9, human, days_ago(85)),
        EdgeSpec("d_store", "f_graph", GraphEdgeType.TRACES_TO_DECISION, 0.88, human, days_ago(85)),
        # Prevention rule mitigates a risk on the graph core; convention derived from repo.
        EdgeSpec("p_rule", "f_graph", GraphEdgeType.MITIGATES, 0.9, human, days_ago(50)),
        EdgeSpec("c_profile", "repo", GraphEdgeType.DERIVED_FROM, 1.0, sa, days_ago(90)),
    ]


def seed_graph(
    *,
    graph: GraphService,
    causal: CausalGraphService,
    architecture: ArchitectureEvolutionService,
    health: RepositoryHealthService,
    force: bool = False,
) -> dict[str, int]:
    """Populate the graph. No-op if nodes already exist (unless force)."""

    if not force and graph.list_nodes():
        return {"nodes": len(graph.list_nodes()), "edges": len(graph.list_edges_at()), "seeded": 0}

    nodes: dict[str, GraphNode] = {}
    for spec in _node_specs():
        nodes[spec.key] = graph.add_node(
            GraphNodeCreate(node_type=spec.node_type, stable_id=spec.stable_id, properties=spec.properties)
        )

    for spec in _edge_specs():
        graph.add_edge(
            GraphEdgeCreate(
                from_node_id=nodes[spec.from_key].id,
                to_node_id=nodes[spec.to_key].id,
                edge_type=spec.edge_type,
                confidence=spec.confidence,
                source_type=spec.source_type,
                valid_from=spec.valid_from,
                valid_to=spec.valid_to,
                source_artifact_id=INFERENCE_ARTIFACT_ID if spec.cite_artifact else None,
                properties=spec.properties or {},
            )
        )

    # Exercise the cognition subsystems so their views have real data too. These create their own
    # CausalEvent / ArchitectureTrend / HealthMetric nodes and edges through validated services.
    causal.record_chain(
        CausalChainRequest(
            source_artifact_id=INFERENCE_ARTIFACT_ID,
            causal_confidence=0.74,
            events=[
                CausalEventInput(event_kind="commit", stable_id="commit/9f2a1c",
                                 summary="Refactor edge validation into GraphEdgeCreate validator",
                                 occurred_at=days_ago(21)),
                CausalEventInput(event_kind="deploy", stable_id="deploy/2025-07-15",
                                 summary="Deploy graph service v0.3 to staging",
                                 occurred_at=days_ago(20)),
                CausalEventInput(event_kind="incident", stable_id="incident/temporal-overlap",
                                 summary="Overlapping temporal edges surfaced in snapshot query",
                                 occurred_at=days_ago(19)),
            ],
        )
    )

    def observation(day: float, coupling: float, complexity: float, churn: float) -> ArchitectureObservation:
        return ArchitectureObservation(
            observed_at=days_ago(day), coupling=coupling, cohesion=0.7,
            cyclomatic_complexity=complexity, fan_in=6.0, fan_out=4.0,
            ownership_fragmentation=0.3, file_churn=churn,
        )

    architecture.record_trend(
        ArchitectureTrendRequest(
            module_path="backend/graph",
            observations=[
                observation(75, 0.42, 8.0, 0.2),
                observation(45, 0.55, 9.5, 0.35),
                observation(10, 0.71, 11.0, 0.5),
            ],
        )
    )

    health.score(
        RepositoryHealthRequest(
            repository="codexa-os", maintainability=0.78, testability=0.71, coupling=0.34,
            doc_coverage=0.52, architecture_stability=0.66, deployment_safety=0.81,
            ownership_clarity=0.7, tech_debt_index=0.29, confidence=0.83,
        )
    )

    return {
        "nodes": len(graph.list_nodes()),
        "edges": len(graph.list_edges_at()),
        "seeded": 1,
    }


def _main() -> None:
    from backend.graph.events import InMemoryGraphEventWriter
    from backend.graph.repository import InMemoryGraphRepository

    event_writer = InMemoryGraphEventWriter()
    graph = GraphService(repository=InMemoryGraphRepository(), event_writer=event_writer)
    summary = seed_graph(
        graph=graph,
        causal=CausalGraphService(graph=graph),
        architecture=ArchitectureEvolutionService(graph=graph),
        health=RepositoryHealthService(graph=graph),
    )
    print(f"Seeded in-memory graph: {summary['nodes']} nodes, {summary['edges']} active edges.")


if __name__ == "__main__":
    _main()
