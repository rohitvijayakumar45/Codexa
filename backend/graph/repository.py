from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

import psycopg

from backend.graph.schemas import GraphEdge, GraphEdgeCreate, GraphNode, GraphNodeCreate


class GraphRepository(Protocol):
    def add_node(self, node: GraphNodeCreate) -> GraphNode:
        """Persist a graph node in Postgres source of truth."""

    def add_edge(self, edge: GraphEdgeCreate) -> GraphEdge:
        """Persist a spec-validated temporal graph edge."""

    def list_nodes(self) -> list[GraphNode]:
        """Return graph nodes for query APIs and graph visualization."""

    def list_edges_at(self, at_time: datetime | None = None) -> list[GraphEdge]:
        """Return active edges, optionally as of a point in time."""

    def list_all_edges(self) -> list[GraphEdge]:
        """Return all temporal edges, including edges no longer active."""

    def remove_by_repository(self, repository: str) -> int:
        """Delete every node (and edges touching them) tagged with this repository. Returns the
        number of nodes removed."""


class InMemoryGraphRepository:
    def __init__(self) -> None:
        self.nodes: dict[UUID, GraphNode] = {}
        self.node_ids_by_stable_id: dict[str, UUID] = {}
        self.edges: dict[UUID, GraphEdge] = {}

    def add_node(self, node: GraphNodeCreate) -> GraphNode:
        existing_id = self.node_ids_by_stable_id.get(node.stable_id)
        if existing_id is not None:
            existing = self.nodes[existing_id]
            updated = GraphNode(
                id=existing.id,
                created_at=existing.created_at,
                node_type=node.node_type,
                stable_id=node.stable_id,
                properties=node.properties,
            )
            self.nodes[existing_id] = updated
            return updated

        created = GraphNode(**node.model_dump())
        self.nodes[created.id] = created
        self.node_ids_by_stable_id[created.stable_id] = created.id
        return created

    def add_edge(self, edge: GraphEdgeCreate) -> GraphEdge:
        if edge.from_node_id not in self.nodes:
            raise ValueError("from_node_id does not exist")
        if edge.to_node_id not in self.nodes:
            raise ValueError("to_node_id does not exist")
        created = GraphEdge(**edge.model_dump())
        self.edges[created.id] = created
        return created

    def list_nodes(self) -> list[GraphNode]:
        return list(self.nodes.values())

    def list_edges_at(self, at_time: datetime | None = None) -> list[GraphEdge]:
        edges = list(self.edges.values())
        if at_time is None:
            return [edge for edge in edges if edge.valid_to is None]
        return [
            edge
            for edge in edges
            if edge.valid_from <= at_time and (edge.valid_to is None or edge.valid_to > at_time)
        ]

    def list_all_edges(self) -> list[GraphEdge]:
        return list(self.edges.values())

    def remove_by_repository(self, repository: str) -> int:
        dead_ids = {nid for nid, n in self.nodes.items() if n.properties.get("repository") == repository}
        for nid in dead_ids:
            node = self.nodes.pop(nid)
            if self.node_ids_by_stable_id.get(node.stable_id) == nid:
                del self.node_ids_by_stable_id[node.stable_id]
        for eid, edge in list(self.edges.items()):
            if edge.from_node_id in dead_ids or edge.to_node_id in dead_ids:
                del self.edges[eid]
        return len(dead_ids)


class PostgresGraphRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def add_node(self, node: GraphNodeCreate) -> GraphNode:
        node_id = uuid4()
        created_at = datetime.now(UTC)
        with psycopg.connect(self.database_url) as conn:
            cursor = conn.execute(
                """
                INSERT INTO graph_nodes (id, node_type, stable_id, properties, created_at)
                VALUES (%s, %s, %s, %s::jsonb, %s)
                ON CONFLICT (stable_id) DO UPDATE SET
                    node_type = EXCLUDED.node_type,
                    properties = EXCLUDED.properties
                RETURNING id, created_at
                """,
                (
                    node_id,
                    node.node_type,
                    node.stable_id,
                    json.dumps(node.properties),
                    created_at,
                ),
            )
            row = cursor.fetchone()
        if row is None:
            raise RuntimeError("graph node insert returned no row")
        return GraphNode(
            id=row[0],
            created_at=row[1],
            node_type=node.node_type,
            stable_id=node.stable_id,
            properties=node.properties,
        )

    def add_edge(self, edge: GraphEdgeCreate) -> GraphEdge:
        created = GraphEdge(**edge.model_dump())
        with psycopg.connect(self.database_url) as conn:
            conn.execute(
                """
                INSERT INTO graph_edges (
                    id,
                    from_node_id,
                    to_node_id,
                    edge_type,
                    confidence,
                    source_type,
                    source_artifact_id,
                    valid_from,
                    valid_to,
                    properties,
                    created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                """,
                (
                    created.id,
                    created.from_node_id,
                    created.to_node_id,
                    created.edge_type,
                    created.confidence,
                    created.source_type,
                    created.source_artifact_id,
                    created.valid_from,
                    created.valid_to,
                    json.dumps(created.properties),
                    created.created_at,
                ),
            )
        return created

    def list_nodes(self) -> list[GraphNode]:
        with psycopg.connect(self.database_url) as conn:
            rows = conn.execute(
                """
                SELECT id, node_type, stable_id, properties, created_at
                FROM graph_nodes
                ORDER BY created_at ASC
                """
            ).fetchall()

        return [
            GraphNode(
                id=row[0],
                node_type=row[1],
                stable_id=row[2],
                properties=row[3],
                created_at=row[4],
            )
            for row in rows
        ]

    def list_edges_at(self, at_time: datetime | None = None) -> list[GraphEdge]:
        if at_time is None:
            where_clause = "valid_to IS NULL"
            params: tuple[object, ...] = ()
        else:
            where_clause = "valid_from <= %s AND (valid_to IS NULL OR valid_to > %s)"
            params = (at_time, at_time)

        with psycopg.connect(self.database_url) as conn:
            rows = conn.execute(
                f"""
                SELECT
                    id,
                    from_node_id,
                    to_node_id,
                    edge_type,
                    confidence,
                    source_type,
                    valid_from,
                    valid_to,
                    source_artifact_id,
                    properties,
                    created_at
                FROM graph_edges
                WHERE {where_clause}
                ORDER BY valid_from ASC
                """,
                params,
            ).fetchall()

        return [
            GraphEdge(
                id=row[0],
                from_node_id=row[1],
                to_node_id=row[2],
                edge_type=row[3],
                confidence=row[4],
                source_type=row[5],
                valid_from=row[6],
                valid_to=row[7],
                source_artifact_id=row[8],
                properties=row[9],
                created_at=row[10],
            )
            for row in rows
        ]

    def list_all_edges(self) -> list[GraphEdge]:
        with psycopg.connect(self.database_url) as conn:
            rows = conn.execute(
                """
                SELECT
                    id,
                    from_node_id,
                    to_node_id,
                    edge_type,
                    confidence,
                    source_type,
                    valid_from,
                    valid_to,
                    source_artifact_id,
                    properties,
                    created_at
                FROM graph_edges
                ORDER BY valid_from ASC
                """
            ).fetchall()

        return [
            GraphEdge(
                id=row[0],
                from_node_id=row[1],
                to_node_id=row[2],
                edge_type=row[3],
                confidence=row[4],
                source_type=row[5],
                valid_from=row[6],
                valid_to=row[7],
                source_artifact_id=row[8],
                properties=row[9],
                created_at=row[10],
            )
            for row in rows
        ]

    def remove_by_repository(self, repository: str) -> int:
        with psycopg.connect(self.database_url) as conn:
            conn.execute(
                """
                DELETE FROM graph_edges
                WHERE from_node_id IN (SELECT id FROM graph_nodes WHERE properties->>'repository' = %s)
                   OR to_node_id IN (SELECT id FROM graph_nodes WHERE properties->>'repository' = %s)
                """,
                (repository, repository),
            )
            cursor = conn.execute(
                "DELETE FROM graph_nodes WHERE properties->>'repository' = %s",
                (repository,),
            )
            return cursor.rowcount if cursor.rowcount is not None else 0
