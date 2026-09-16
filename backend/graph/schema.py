"""Idempotent Postgres schema bootstrap for the graph/event/artifact stores.

Called once at startup when CODEXA_DATABASE_URL is set, so pointing Codexa at a fresh Postgres
database is turnkey — no separate `psql -f migration` step. Everything is CREATE ... IF NOT EXISTS,
so it is safe to run on every boot and never touches an existing table's data.

Type columns (node_type, edge_type, source_type, ...) are plain TEXT with CHECK-free storage rather
than Postgres ENUMs on purpose: the old infra/migrations/0001_core.sql used ENUMs and they drifted
(e.g. the code added the 'QuorumDecision' node type but the enum never gained it, which would reject
the insert at runtime). TEXT keeps the schema in lockstep with backend/graph/schemas.py without a
migration per new node/edge kind; the Pydantic models are the single source of truth for the vocab.
"""

from __future__ import annotations

import logging

import psycopg

logger = logging.getLogger(__name__)

_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS ingested_artifacts (
        id UUID PRIMARY KEY,
        source_uri TEXT NOT NULL,
        kind TEXT NOT NULL,
        trust_level TEXT NOT NULL,
        raw_content TEXT NOT NULL,
        isolated_content TEXT NOT NULL,
        instruction_content_removed BOOLEAN NOT NULL DEFAULT FALSE,
        isolation_findings JSONB NOT NULL DEFAULT '[]'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS graph_events (
        id UUID PRIMARY KEY,
        aggregate_id UUID NOT NULL,
        event_type TEXT NOT NULL,
        payload JSONB NOT NULL,
        occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS graph_events_aggregate_id_idx ON graph_events (aggregate_id)",
    "CREATE INDEX IF NOT EXISTS graph_events_event_type_idx ON graph_events (event_type)",
    """
    CREATE TABLE IF NOT EXISTS graph_nodes (
        id UUID PRIMARY KEY,
        node_type TEXT NOT NULL,
        stable_id TEXT NOT NULL UNIQUE,
        properties JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS graph_nodes_type_idx ON graph_nodes (node_type)",
    """
    CREATE TABLE IF NOT EXISTS graph_edges (
        id UUID PRIMARY KEY,
        from_node_id UUID NOT NULL REFERENCES graph_nodes(id),
        to_node_id UUID NOT NULL REFERENCES graph_nodes(id),
        edge_type TEXT NOT NULL,
        confidence DOUBLE PRECISION NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
        source_type TEXT NOT NULL,
        source_artifact_id UUID REFERENCES ingested_artifacts(id),
        valid_from TIMESTAMPTZ NOT NULL,
        valid_to TIMESTAMPTZ,
        properties JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        CHECK (valid_to IS NULL OR valid_to > valid_from)
    )
    """,
    "CREATE INDEX IF NOT EXISTS graph_edges_type_idx ON graph_edges (edge_type)",
    "CREATE INDEX IF NOT EXISTS graph_edges_temporal_idx ON graph_edges (valid_from, valid_to)",
)


def ensure_schema(database_url: str) -> None:
    """Create the graph/event/artifact tables if they don't already exist. Idempotent.

    Raises on a genuine connection/DDL failure so a misconfigured CODEXA_DATABASE_URL surfaces loudly
    at boot instead of every graph write failing one-by-one later.
    """
    with psycopg.connect(database_url) as conn:
        for stmt in _STATEMENTS:
            conn.execute(stmt)
        conn.commit()
    logger.info("Postgres graph schema ensured (%d objects).", len(_STATEMENTS))
