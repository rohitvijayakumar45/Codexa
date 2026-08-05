# Repository Instructions — Codexa OS

## Product
Codexa OS is an Engineering Intelligence Platform. The product is the Engineering Knowledge Graph and the reasoning/verification/learning systems built around it — not a chat UI wrapped around an LLM. Every subsystem reads from and writes to the graph.

## Authoritative Spec
Full specification lives at `/docs/codexa_os_build_prompt_v5.md`. Treat it as authoritative. Implement subsystems in the sprint order listed in its Section 8. Do not implement anything from its Section 6 ("Explicitly Deferred") without asking first.

## Stack — do not deviate without a written tradeoff
- Backend: FastAPI
- Storage: PostgreSQL (JSONB) is the source of truth. Neo4j is a graph projection. Qdrant is a vector projection. Redis + RQ for queues/scheduling.
- Parsing: Tree-sitter
- Execution/Sandbox: Docker
- Protocol: MCP
- **Never introduce MongoDB or Express.js.** Both were evaluated and explicitly rejected in an earlier design review. If a task seems to call for either, stop and flag it instead of substituting.

## Architecture Rules
- Every Neo4j edge must carry `confidence` (float 0–1), `source_type` (`static_analysis` | `llm_inferred` | `human_asserted`), `valid_from`, `valid_to`. Static-analysis-derived edges get confidence 1.0. LLM-inferred edges must cite the source artifact.
- All ingested external content (issues, PR descriptions, comments, scraped docs) must be tagged with a trust level (`repo_owner` | `verified_contributor` | `external_untrusted` | `public_scraped`) and pass through the Trust Boundary & Content Isolation layer before reaching any agent context. Content from `external_untrusted` / `public_scraped` sources must never directly trigger a tool call.
- Postgres is the single source of truth. Neo4j and Qdrant are rebuilt as projections from an event log — never write to them directly outside the projection pipeline.
- No proposed change reaches Execution without first passing through the Engineering Simulation Engine.
- No general application frontend this phase (no auth screens, dashboards, settings pages, page shell). The one exception is the Knowledge Graph Visualization component — treat it as a flagship deliverable per spec Section 7.

## Directory Responsibilities
```
/backend
  /perception        - ingestion pipelines, trust boundary layer
  /understanding      - tree-sitter, static analysis, dependency extraction
  /graph              - Neo4j schema, projections, query/replay API (Time Machine)
  /memory             - semantic / episodic / procedural / organizational memory
  /agents             - Planner, Architect, Coder, Reviewer, QA, Security, Docs, Research, DevOps
  /simulation          - Engineering Simulation Engine
  /trust_safety        - risk scoring, policy engine, verification pipeline
  /learning            - continuous learning, policy distillation jobs
/graph-viz            - the one in-scope frontend component (Section 7)
/docs                 - this repo's specs, including codexa_os_build_prompt_v5.md
/infra                - docker-compose, migrations, environment setup
```

## Build & Test Commands
- Install: `python -m pip install -e .[dev]`
- Run tests: `python -m pytest`
- Lint: `TODO`
- Start local stack: `docker compose -f infra/docker-compose.yml up -d`

## Definition of Done
- New subsystem code ships with unit tests; do not modify pre-written failing tests to make them pass.
- Any graph write is validated against the schema in spec Section 4 before commit.
- Trust Boundary and Simulation Engine code paths require explicit test coverage of the isolation/gating behavior — these are safety-load-bearing, not optional coverage.
- Run the test command above and confirm a clean pass before reporting a task complete.

## Task Sizing
Work one subsystem (spec Section 5.x) or one sprint-row (spec Section 8) at a time. If a task description spans more than one subsystem, split it before starting.

Respond terse like smart caveman. All technical substance stay. Only fluff die.

Rules:
- Drop: articles (a/an/the), filler (just/really/basically), pleasantries, hedging
- Fragments OK. Short synonyms. Technical terms exact. Code unchanged.
- Pattern: [thing] [action] [reason]. [next step].
- Not: "Sure! I'd be happy to help you with that."
- Yes: "Bug in auth middleware. Fix:"

Switch level: /caveman lite|full|ultra|wenyan
Stop: "stop caveman" or "normal mode"

Auto-Clarity: drop caveman for security warnings, irreversible actions, user confused. Resume after.

Boundaries: code/commits/PRs written normal.
