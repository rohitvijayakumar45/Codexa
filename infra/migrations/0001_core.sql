CREATE TYPE trust_level AS ENUM (
    'repo_owner',
    'verified_contributor',
    'external_untrusted',
    'public_scraped'
);

CREATE TYPE artifact_kind AS ENUM (
    'issue_body',
    'pr_description',
    'comment',
    'scraped_doc'
);

CREATE TYPE graph_edge_source_type AS ENUM (
    'static_analysis',
    'llm_inferred',
    'human_asserted'
);

CREATE TYPE graph_node_type AS ENUM (
    'Repository',
    'File',
    'CodeSymbol',
    'ApiRoute',
    'SchemaField',
    'ExternalArtifact',
    'ArchitectureTrend',
    'SimulationScenario',
    'CausalEvent',
    'Decision',
    'Tradeoff',
    'RejectedAlternative',
    'OnboardingPath',
    'HealthMetric',
    'PreventionRule',
    'ConventionProfile'
);

CREATE TYPE graph_edge_type AS ENUM (
    'calls',
    'imports',
    'depends_on',
    'causes',
    'mitigates',
    'increases_risk_of',
    'correlates_with',
    'derived_from',
    'supersedes',
    'flows_into',
    'traces_to_decision'
);

CREATE TABLE ingested_artifacts (
    id UUID PRIMARY KEY,
    source_uri TEXT NOT NULL,
    kind artifact_kind NOT NULL,
    trust_level trust_level NOT NULL,
    raw_content TEXT NOT NULL,
    isolated_content TEXT NOT NULL,
    instruction_content_removed BOOLEAN NOT NULL DEFAULT FALSE,
    isolation_findings JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE graph_events (
    id UUID PRIMARY KEY,
    aggregate_id UUID NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX graph_events_aggregate_id_idx ON graph_events (aggregate_id);
CREATE INDEX graph_events_event_type_idx ON graph_events (event_type);

CREATE TABLE graph_nodes (
    id UUID PRIMARY KEY,
    node_type graph_node_type NOT NULL,
    stable_id TEXT NOT NULL UNIQUE,
    properties JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX graph_nodes_type_idx ON graph_nodes (node_type);

CREATE TABLE graph_edges (
    id UUID PRIMARY KEY,
    from_node_id UUID NOT NULL REFERENCES graph_nodes(id),
    to_node_id UUID NOT NULL REFERENCES graph_nodes(id),
    edge_type graph_edge_type NOT NULL,
    confidence DOUBLE PRECISION NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    source_type graph_edge_source_type NOT NULL,
    source_artifact_id UUID REFERENCES ingested_artifacts(id),
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    properties JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (valid_to IS NULL OR valid_to > valid_from),
    CHECK (
        source_type <> 'static_analysis'
        OR confidence = 1.0
    ),
    CHECK (
        source_type <> 'llm_inferred'
        OR source_artifact_id IS NOT NULL
    )
);

CREATE INDEX graph_edges_type_idx ON graph_edges (edge_type);
CREATE INDEX graph_edges_temporal_idx ON graph_edges (valid_from, valid_to);
