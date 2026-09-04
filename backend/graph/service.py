from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from backend.graph.events import GraphEventWriter
from backend.graph.repository import GraphRepository
from backend.graph.schemas import (
    GraphEdge,
    GraphEdgeCreate,
    GraphNode,
    GraphNodeCreate,
    GraphSnapshot,
    GraphTimeline,
)


class GraphService:
    def __init__(self, repository: GraphRepository, event_writer: GraphEventWriter) -> None:
        self.repository = repository
        self.event_writer = event_writer

    def add_node(self, node: GraphNodeCreate) -> GraphNode:
        created = self.repository.add_node(node)
        self.event_writer.append(
            event_type="graph.node.created",
            aggregate_id=created.id,
            payload=created.model_dump(mode="json"),
        )
        return created

    def add_edge(self, edge: GraphEdgeCreate) -> GraphEdge:
        created = self.repository.add_edge(edge)
        self.event_writer.append(
            event_type="graph.edge.created",
            aggregate_id=created.id,
            payload=created.model_dump(mode="json"),
        )
        return created

    def list_nodes(self) -> list[GraphNode]:
        return self.repository.list_nodes()

    def remove_repository(self, repository: str) -> int:
        removed = self.repository.remove_by_repository(repository)
        if removed:
            # No node survives deletion to anchor the event to, so use a fresh id — the repository
            # name lives in the payload, which is what Time Machine / audit trails actually read.
            self.event_writer.append(
                event_type="repository.deleted",
                aggregate_id=uuid4(),
                payload={"repository": repository, "nodes_removed": removed},
            )
        return removed

    def list_edges_at(self, at_time: datetime | None = None) -> list[GraphEdge]:
        return self.repository.list_edges_at(at_time)

    def list_all_edges(self) -> list[GraphEdge]:
        """All temporal edges, including edges that have been superseded (valid_to set)."""
        return self.repository.list_all_edges()

    def snapshot_at(self, at_time: datetime | None = None) -> GraphSnapshot:
        if at_time is None:
            return GraphSnapshot(
                at_time=None,
                nodes=self.repository.list_nodes(),
                edges=self.repository.list_edges_at(None),
            )

        all_nodes = self.repository.list_nodes()
        active_edges = self.repository.list_edges_at(at_time)
        referenced_node_ids = {
            node_id
            for edge in active_edges
            for node_id in (edge.from_node_id, edge.to_node_id)
        }
        nodes = [
            node
            for node in all_nodes
            if node.created_at <= at_time or node.id in referenced_node_ids
        ]
        visible_node_ids = {node.id for node in nodes}
        edges = [
            edge
            for edge in active_edges
            if edge.from_node_id in visible_node_ids and edge.to_node_id in visible_node_ids
        ]
        return GraphSnapshot(at_time=at_time, nodes=nodes, edges=edges)

    def timeline(self) -> GraphTimeline:
        times: list[datetime] = []
        for node in self.repository.list_nodes():
            times.append(node.created_at)
        for edge in self.repository.list_all_edges():
            times.append(edge.valid_from)
            times.append(edge.created_at)
            if edge.valid_to is not None:
                times.append(edge.valid_to)

        if not times:
            return GraphTimeline()
        return GraphTimeline(starts_at=min(times), ends_at=max(times))
