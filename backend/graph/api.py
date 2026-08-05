from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, status

from backend.graph.causal import (
    CausalChainRequest,
    CausalChainResult,
    CausalGraphOverview,
    CausalGraphService,
)
from backend.graph.consistency import (
    ConsistencyCheckRequest,
    ConsistencyCheckResult,
    MultiStoreConsistencyService,
)
from backend.graph.data_flow import DataFlowTraceRequest, DataFlowTraceResult, DataFlowTracingService
from backend.graph.schemas import (
    GraphEdge,
    GraphEdgeCreate,
    GraphNode,
    GraphNodeCreate,
    GraphNodeType,
    GraphSnapshot,
    GraphTimeline,
)
from backend.graph.service import GraphService


def create_graph_router(
    *,
    graph: GraphService,
    data_flow: DataFlowTracingService,
    causal_graph: CausalGraphService,
    consistency: MultiStoreConsistencyService,
) -> APIRouter:
    router = APIRouter(prefix="/graph", tags=["graph"])

    def _in_repo(node: GraphNode, repository: str | None) -> bool:
        if repository is None:
            return True
        owner = node.properties.get("repository")
        # codexa-os owns everything the platform seeded (untagged); loaded repos own their tag.
        if repository == "codexa-os":
            return owner is None or owner == "codexa-os"
        return owner == repository

    def _scope(nodes: list[GraphNode], edges: list[GraphEdge], repository: str | None):
        if repository is None:
            return nodes, edges
        kept = [n for n in nodes if _in_repo(n, repository)]
        ids = {n.id for n in kept}
        scoped_edges = [e for e in edges if e.from_node_id in ids and e.to_node_id in ids]
        return kept, scoped_edges

    @router.post("/nodes", response_model=GraphNode, status_code=status.HTTP_201_CREATED)
    def create_node(request: GraphNodeCreate) -> GraphNode:
        if request.node_type == GraphNodeType.SIMULATION_SCENARIO:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Simulation scenarios must be created via the Simulation Engine",
            )
        return graph.add_node(request)

    @router.get("/nodes", response_model=list[GraphNode])
    def list_nodes(repository: str | None = Query(default=None)) -> list[GraphNode]:
        return [n for n in graph.list_nodes() if _in_repo(n, repository)]

    @router.post("/edges", response_model=GraphEdge, status_code=status.HTTP_201_CREATED)
    def create_edge(request: GraphEdgeCreate) -> GraphEdge:
        return graph.add_edge(request)

    @router.get("/edges", response_model=list[GraphEdge])
    def list_edges(at_time: datetime | None = Query(default=None)) -> list[GraphEdge]:
        return graph.list_edges_at(at_time)

    @router.get("/edges/all", response_model=list[GraphEdge])
    def list_all_edges(repository: str | None = Query(default=None)) -> list[GraphEdge]:
        # Full temporal edge set including superseded edges, so the time-machine can replay
        # history client-side without re-querying per scrub tick.
        _, edges = _scope(graph.list_nodes(), graph.list_all_edges(), repository)
        return edges

    @router.get("/snapshots", response_model=GraphSnapshot)
    def get_snapshot(
        at_time: datetime | None = Query(default=None),
        repository: str | None = Query(default=None),
    ) -> GraphSnapshot:
        snapshot = graph.snapshot_at(at_time)
        nodes, edges = _scope(snapshot.nodes, snapshot.edges, repository)
        return GraphSnapshot(at_time=snapshot.at_time, nodes=nodes, edges=edges)

    @router.get("/timeline", response_model=GraphTimeline)
    def get_timeline() -> GraphTimeline:
        return graph.timeline()

    @router.post(
        "/data-flow/traces",
        response_model=DataFlowTraceResult,
        status_code=status.HTTP_201_CREATED,
    )
    def create_data_flow_trace(request: DataFlowTraceRequest) -> DataFlowTraceResult:
        return data_flow.create_trace(request)

    @router.post(
        "/causal/chains",
        response_model=CausalChainResult,
        status_code=status.HTTP_201_CREATED,
    )
    def create_causal_chain(request: CausalChainRequest) -> CausalChainResult:
        return causal_graph.record_chain(request)

    @router.get("/causal/overview", response_model=CausalGraphOverview)
    def get_causal_overview() -> CausalGraphOverview:
        return causal_graph.overview()

    @router.post(
        "/consistency/checks",
        response_model=ConsistencyCheckResult,
        status_code=status.HTTP_201_CREATED,
    )
    def check_projection_consistency(
        request: ConsistencyCheckRequest,
    ) -> ConsistencyCheckResult:
        return consistency.check(request)

    return router
