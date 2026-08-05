# Codexa OS — Frontend Discovery Inventory

Written before any UI code, per the frontend brief. This is the source of truth for what the
backend actually exposes today, what each screen can honestly be backed by, and where the docs
promise more than the code delivers.

## 1. What this system is

Codexa OS is an **Engineering Intelligence Platform** built around an **Engineering Knowledge
Graph** ("the engineering brain"). A FastAPI backend ingests engineering artifacts, builds a
temporal, confidence-weighted graph of code/architecture/history, and runs cognitive subsystems
(simulation, causal reasoning, health scoring, incident learning, policy distillation) on top of
it. The flagship frontend deliverable is a live, force-directed visualization of that graph.

Personality: a serious, technical, research-grade *instrument* for staff/principal engineers and
platform teams. Not a consumer dashboard. The design should read like precision tooling.

## 2. Stack (as actually pinned)

- Backend: FastAPI (`backend/main.py` → `create_app()`), Pydantic v2 schemas.
- Storage: PostgreSQL when `CODEXA_DATABASE_URL`/`DATABASE_URL` is set, else **in-memory**
  (`InMemory*Repository`). No env file present, so **the default boot is in-memory and empty**.
- Frontend (`graph-viz/`, kept deps only, source deleted for rebuild): Next.js **16.3.0**,
  React **19.2.8**, Tailwind **v4**, `framer-motion` 12, `zustand` 5, `@tanstack/react-query` 5,
  `three` 0.182 + `@react-three/fiber` 9 + `@react-three/drei` 10, `recharts` 2, `lucide-react`.
- Infra: `infra/docker-compose.yml` + `infra/migrations` exist (Postgres/Neo4j/Qdrant/Redis per
  overview), not required for the in-memory dev path.
- LLM: `backend/agents/llm.py` uses the OpenAI SDK pointed at a **local Ollama** default
  (`localhost:11434`, `qwen3:14b`) or NVIDIA NIM. No key/env present → no live LLM by default.

## 3. API surface — every endpoint, grouped by router

Base URL default (dev): FastAPI on its own host/port. **CORS currently allows only
`http://localhost:5173` and `http://127.0.0.1:5173`** (Vite), NOT the Next.js dev origin.

Legend: **R** = read (GET, safe to back a view directly), **W** = write/compute (POST, mutates the
in-memory graph and returns a computed result).

### graph (`/graph`) — the core, and the only real read surface
- **R** `GET /graph/nodes` → `GraphNode[]`
- **R** `GET /graph/edges?at_time=<iso>` → `GraphEdge[]` (temporal filter)
- **R** `GET /graph/snapshots?at_time=<iso>` → `GraphSnapshot { at_time, nodes[], edges[] }`
- **R** `GET /graph/timeline` → `GraphTimeline { starts_at, ends_at }`
- **R** `GET /graph/causal/overview` → `CausalGraphOverview { event_node_ids[], causal_edge_ids[] }`
- **W** `POST /graph/nodes` → `GraphNode` (403 for `SimulationScenario` type)
- **W** `POST /graph/edges` → `GraphEdge`
- **W** `POST /graph/data-flow/traces` → `DataFlowTraceResult`
- **W** `POST /graph/causal/chains` → `CausalChainResult`
- **W** `POST /graph/consistency/checks` → `ConsistencyCheckResult`

### understanding (`/understanding`)
- **R** `GET /understanding/architecture/trends` → `ArchitectureTrendResult[]`
- **W** `POST /understanding/architecture/trends` → `ArchitectureTrendResult`
- **W** `POST /understanding/architecture/nightly-review` → `NightlyArchitectureReviewResult`

### trust-safety (`/trust-safety`)
- **R** `GET /trust-safety/confidence/calibrations` → `ConfidenceCalibrationResult[]`
- **W** `POST /trust-safety/confidence/calibrations` → `ConfidenceCalibrationResult`
- **W** `POST /trust-safety/verification/proposals` → `VerificationResult`
- **W** `POST /trust-safety/policy/execution-gate` → `ExecutionGateResult`
- **W** `POST /trust-safety/economics/estimates` → `EngineeringEconomicsResult`
- **W** `POST /trust-safety/health/repository` → `RepositoryHealthResult { score, components{} }`
- **W** `POST /trust-safety/incidents/learning` → `IncidentLearningResult`

### agents (`/agents`) — all write/compute
- **W** `POST /agents/planner/blast-radius` → `BlastRadiusResult`
- **W** `POST /agents/coder/proposals` → `ChangeProposalResult`
- **W** `POST /agents/research/recommendations` → `ResearchRecommendationResult`
- **W** `POST /agents/retrieval/context` → `ContextAssemblyResult`

### simulation (`/simulation`) — all write/compute
- **W** `POST /simulation/scenarios` → `SimulationResult`
- **W** `POST /simulation/chaos/pre-mortems` → `ChaosPremortemResult`

### memory (`/memory`) — all write/compute
- **W** `POST /memory/intent/chains` → `IntentGraphResult`
- **W** `POST /memory/organizational/conventions` → `ConventionProfileResult`
- **W** `POST /memory/engineering-dna/conventions` → `EngineeringDNAResult`

### perception (`/perception`)
- **W** `POST /perception/artifacts` → `IsolatedArtifact` (trust-boundary isolation of ingested text)

### execution (`/execution`)
- **W** `POST /execution/sandbox-runs` → `SandboxRunResult`

### learning (`/learning`)
- **W** `POST /learning/policy-distillation/runs` → `PolicyDistillationResult`

## 4. Core data model (graph — this is what the 3D viz renders)

`GraphNode` = `{ id: UUID, node_type, stable_id, properties: {}, created_at }`.
`node_type` ∈ Repository, File, CodeSymbol, ApiRoute, SchemaField, ExternalArtifact,
ArchitectureTrend, SimulationScenario, CausalEvent, Decision, Tradeoff, RejectedAlternative,
OnboardingPath, HealthMetric, PreventionRule, ConventionProfile. **→ node color/shape encodes
`node_type`.**

`GraphEdge` = `{ id, from_node_id, to_node_id, edge_type, confidence: 0..1, source_type,
valid_from, valid_to?, source_artifact_id?, properties, created_at }`.
`edge_type` ∈ calls, imports, depends_on, causes, mitigates, increases_risk_of, correlates_with,
derived_from, supersedes, flows_into, traces_to_decision. `source_type` ∈ static_analysis,
llm_inferred, human_asserted. **→ edge opacity/thickness encodes `confidence`; style encodes
`source_type`; `valid_from`/`valid_to` drive the time-scrubber.**

Invariants (enforced server-side, must be respected by any write UI): static_analysis edges must
have confidence 1.0; llm_inferred edges must cite `source_artifact_id`; `valid_to` > `valid_from`.

This graph structure is the one true graph/tree/relational model in the system. Every subsystem
result is ultimately projected into these nodes/edges.

## 5. Screen → backing endpoint map (honest)

| Screen | Real backing | Read or seed-then-read |
|---|---|---|
| **Knowledge Graph (3D, signature)** | `GET /graph/snapshots`, `/graph/timeline`, `/graph/causal/overview` | Read — but empty until seeded |
| Architecture | `GET /understanding/architecture/trends` | Read — empty until a trend is POSTed |
| Confidence / trust | `GET /trust-safety/confidence/calibrations` | Read — empty until seeded |
| Analytics / health | **no GET** — only `POST /health/repository`, `/economics/estimates` | Needs list endpoints OR compute-on-submit UX |
| Agents (blast radius, proposals, retrieval) | **no GET** — POST-only | Interactive tools: user submits → result renders |
| Simulation / chaos | **no GET** — POST-only | Interactive tools |
| Memory / intent / DNA | **no GET** — POST-only | Interactive tools |
| Time Machine | `GET /graph/snapshots?at_time=`, `/graph/timeline` | Read — depends on seeded temporal data |
| **Documentation (Phase 6, new)** | **does not exist yet** — must be built | New endpoint required |

## 6. Gaps — docs promise vs. code reality

1. **Empty store on boot.** Default is in-memory with zero nodes/edges. Every read view renders
   empty until data is created. There is **no seed path** in the repo. The brief forbids mock data,
   so real data must be produced by the backend (seed module or Postgres + migration seed), not
   faked in the frontend.
2. **Thin read surface.** Most subsystems (agents, simulation, memory, economics, incidents,
   sandbox, learning) are **POST-only compute endpoints with no GET/list**. They cannot back a
   passive "here is your data" view; they are inherently *interactive tools* (submit a request,
   render the returned result). Any view that wants to *list* past results needs new GET endpoints.
3. **CORS origin mismatch.** Backend allows `:5173` (Vite) only; the kept frontend is Next.js
   (`:3000`). Backend CORS must include the Next origin (trivial fix).
4. **No Documentation endpoint.** Phase 6 requires an LLM-generated docs endpoint that does not
   exist. Must be built in the backend (walk routes/schemas → structured docs), with caching +
   regenerate, and a deterministic fallback when no LLM is reachable.
5. **No live LLM by default.** LLM client points at local Ollama with no env/key present. Docs
   generation must degrade gracefully (deterministic route/schema introspection) when the model
   endpoint is unreachable, and only call the LLM when configured.
6. **Overview claims (Neo4j/Qdrant/Redis, live agent traversal, cluster drift) are backend
   projections/roadmap**, not something the current in-memory API streams. The viz should encode
   what the API actually returns (node_type, confidence, temporal validity) and treat
   "live traversal" as a future websocket, not fake it.

## 7. Decisions this inventory forces (see chat)

- How to get **real** data into the graph (seed module vs. Postgres seed vs. frontend-triggered
  seeding) — gates every read-backed view.
- Whether to **add GET/list endpoints** for POST-only subsystems, or present those as interactive
  submit-and-render tools (honest to current design).
- Docs endpoint: LLM-backed with deterministic fallback.
