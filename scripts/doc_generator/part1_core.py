"""Part 1: Sections 1 through 9 of Codexa Complete Documentation."""

def get_part1() -> str:
    return r'''# Codexa — Complete Internal Architecture and Functionality Documentation

## 1. Executive Summary

Codexa OS is an **Engineering Intelligence Platform** designed to act as a persistent, self-healing, and mathematically verifiable "digital twin" of a software repository. Unlike conventional AI coding assistants that simply wrap a chat user interface around a stateless Large Language Model (LLM) context window, Codexa OS anchors all reasoning, planning, code authoring, and verification in an **Engineering Knowledge Graph (EKG)**. Every subsystem in the platform—including static AST parsers, git change-coupling miners, multi-agent debate protocols, simulation sandboxes, and continuous learning pipelines—reads from and writes directly to this central graph.

This document represents an exhaustive, ground-truth technical audit and architectural reverse-engineering of the Codexa OS codebase. Every claim, subsystem, API endpoint, tool, model router path, and background job described herein has been verified directly against the production Python and TypeScript source code.

### Core Architectural Findings at a Glance
1. **Source of Truth Architecture**: PostgreSQL with JSONB schema acts as the durable, transactional source of truth and event log. The system includes an in-memory graph repository (`InMemoryGraphRepository`) with turnkey in-memory event streaming for local zero-dependency development, and a PostgreSQL repository (`PostgresGraphRepository`) for production persistence. Read-optimized projections (Neo4j for topological cypher queries and Qdrant for dense vector similarity) are formally specified in the architecture; currently, the active backend operates directly on PostgreSQL and in-memory graph indices.
2. **Deterministic Dual-Loop Execution**: Codexa separates work into a high-frequency **Fast Loop** (the agent tool-calling execution engine running in `backend/agents/jobs.py` with multi-provider failover, live reasoning streams, and atomic checkpointing) and a low-frequency **Slow Loop** (background git mining, architectural drift projection, policy distillation, and multi-store event reconciliation).
3. **Machine-Verifiable Task Contracts**: Codexa enforces the principle: *"Never confuse generating an implementation with implementing it."* Every user message is classified into a strict `TaskContract` with explicit required tools. If an agent hallucinates a fix in chat prose without calling a mutating filesystem tool (`write_file`, `edit_file`, `delegate_task`), the completion validator mechanically rejects the response and forces a corrective execution round.
4. **Quorum Grounded Multi-Agent Debate**: To eliminate sycophancy and hallucinations during high-stakes architecture decisions, Codexa's Quorum subsystem gathers structured "belief cards" across diverse model providers, deterministically verifies their factual claims against the repository AST and Knowledge Graph, and triggers adversarial peer debate rounds only when top-ranking models disagree.
5. **Simulation & Sandbox Hash-Binding**: Code changes cannot touch production without passing the Engineering Simulation Engine, which calculates blast radius via reverse-BFS traversal and hashes the exact diff and witnessed subgraph using SHA-256. The sandbox execution gate cryptographically verifies that neither the code nor the dependency graph has drifted before scheduling Docker execution.

---

## 2. What Codexa Is

### Simple Explanation
Imagine you hire a brilliant principal software engineer who has complete photographic memory of every file, function, git commit, API route, and bug that has ever existed in your company's codebase. When you ask this engineer to build a feature, they do not merely start typing code into a text box. First, they pull up a dynamic, 3D architectural map of your system to see everything that depends on the code you want to change. Second, they verify whether a similar change caused a production outage three months ago. Third, if there is ambiguity, they convene a panel of senior architects to debate the tradeoffs. Fourth, they simulate the blast radius of their changes in a sandbox before applying them. Finally, after writing the code, they mechanically test that the files were created, functions compile, and claims hold true.

Codexa OS is the automated software platform that does exactly this.

### Technical Explanation
Codexa OS is an agentic, graph-native software engineering operating system. It treats a codebase not as unstructured text files or a flat sequence of prompt tokens, but as an attributed, typed, time-indexed directed property graph $G = (V, E, \tau)$.
- Vertices $V$ encompass structural code entities (files, classes, functions, API routes), organizational knowledge (architectural decisions, tradeoffs, team conventions), and operational events (incidents, pull requests, simulation scenarios).
- Edges $E$ define topological relationships (`calls`, `imports`, `depends_on`), causal chains (`causes`, `mitigates`, `increases_risk_of`), and traceability flows (`flows_into`, `traces_to_decision`).
- Temporal domain $\tau$ defines validity intervals $[\text{valid\\_from}, \text{valid\\_to}]$ for every relationship, enabling instantaneous point-in-time reconstruction of the codebase architecture via the Time Machine API.

Stateless LLMs fail on codebases exceeding 10,000 lines because context windows suffer from attention degradation ("needle in a haystack" loss), quadratic token cost scaling, and hallucinated import paths. Codexa OS overcomes these fundamental LLM limits by using static Tree-sitter parsers and git mining to construct a deterministic graph index, and then using graph-anchored context assembly to inject only the precise 1-to-2 hop semantic neighborhood of a targeted symbol into the LLM's prompt.

---

## 3. System Mental Model

The architecture of Codexa OS is organized around three fundamental planes: the **Perception Plane**, the **Reasoning Plane**, and the **Execution & Verification Plane**.

```mermaid
graph TD
    subgraph Perception Plane
        A[Git Repository / Working Tree] --> B[Tree-sitter AST Parser]
        A --> C[Git History Miner]
        A --> D[Package Manifest Analyzer]
        E[External Docs / Issues] --> F[Trust Boundary & Content Isolation]
    end

    subgraph Central Nervous System
        B --> G[(Engineering Knowledge Graph)]
        C --> G
        D --> G
        F --> G
        G <--> H[(MemoryStore: 4-Tier Memory)]
        G <--> I[(PostgreSQL Event Log)]
    end

    subgraph Reasoning Plane
        J[User Prompt / Task] --> K[Intent Classifier & Task Contract]
        K --> L[Multi-Model Router & Failover Ring]
        L --> M[Agent Controller / Job Manager]
        M <--> N[Quorum Multi-Agent Debate]
        M <--> G
        M <--> H
    end

    subgraph Execution & Verification Plane
        M --> O[Tool Dispatch Engine: 55 Tools]
        O --> P[Simulation Engine: Blast Radius & Hash Binding]
        P --> Q[Sandbox Execution Gate]
        O --> R[Filesystem Mutation Engine]
        R --> S[Post-Hoc Claim & Contract Validator]
        S -->|Passed| T[Atomic Git Commit / PR]
        S -->|Failed| M
    end
```

### The Dual-Loop Engine
1. **The Fast Loop (Seconds to Minutes)**:
   - Driven by `backend/agents/jobs.py` (`JobManager`).
   - Handles real-time user tasks via Server-Sent Events (SSE) streaming.
   - Evaluates task contracts, resolves model routing, executes tool calls, validates factual claims, and updates the local filesystem.
   - Emits granular lifecycle events (`round_start`, `reasoning_chunk`, `tool_call`, `tool_return`, `checkpoint`) to the frontend.
2. **The Slow Loop (Minutes to Hours)**:
   - Driven by background workers, repository rehydration threads, and nightly review routines.
   - Mines multi-commit git histories to detect latent change-coupling ($C_{ij} \ge 0.30$) between files that share no static import statements.
   - Re-evaluates architectural debt trajectories, extrapolating when coupled modules will reach unmaintainable complexity bottlenecks.
   - Distills incident post-mortems into permanent `PreventionRule` nodes that alter future blast-radius risk scoring.

---

## 4. Repository Structure

The Codexa OS codebase is structured into clean separation of concerns across backend services, frontend visualization, database migrations, and verification suites:

```
Codexa/
├── backend/                        # FastAPI Python application backend
│   ├── main.py                     # Application factory (create_app), ASGI middleware, router registration
│   ├── seed.py                     # Self-referential graph seeding for codexa-os repository
│   ├── agents/                     # Autonomous agent orchestration, execution loops, and tools
│   │   ├── api.py                  # Agent endpoints (/agents/planner, /agents/coder, /agents/quorum)
│   │   ├── coder.py                # CoderService for code generation proposals
│   │   ├── context_window.py       # Context window limits and token truncation rules
│   │   ├── controller.py           # Legacy controller interface
│   │   ├── design_intent.py        # Design intent extraction from user briefs
│   │   ├── impact.py               # Downstream blast radius and impact router (/agents/impact)
│   │   ├── jobs.py                 # Core JobManager, SSE streaming, failover rings, checkpointing (2,154 lines)
│   │   ├── llm.py                  # Multi-provider LLMClient, model registry, key rotation (786 lines)
│   │   ├── phased_build.py         # Multi-phase project scaffolding and build manager
│   │   ├── plan.py                 # ExecutionPlan and task state machine
│   │   ├── planner.py              # PlannerService for task breakdown and blast radius
│   │   ├── plan_builder.py         # Automatic plan assembly from intent
│   │   ├── progress.py             # Build progress tracking
│   │   ├── quorum.py               # QuorumService for structured multi-model debate (436 lines)
│   │   ├── receipts.py             # ActionReceipt tracking for tool execution proof
│   │   ├── research.py             # ResearchAgentService for repository Q&A
│   │   ├── retrieval.py            # ContextAssemblyService for graph traversal
│   │   ├── round_telemetry.py      # Telemetry per round
│   │   ├── semantic.py             # Semantic symbol analysis
│   │   ├── task.py                 # TaskIntent enum, TaskContract, and validate_completion (509 lines)
│   │   ├── token_budget.py         # Dynamic token allocation across planning and coding
│   │   ├── tools.py                # Comprehensive tool dispatch engine, 55 tools (3,555 lines)
│   │   ├── usage.py                # UsageTracker for prompt/completion/reasoning token accounting
│   │   ├── validators.py           # Syntax, lint, and build output validators
│   │   ├── verification.py         # Claim extraction and deterministic fact checking (256 lines)
│   │   └── design_skills/          # 10 specialized design knowledge guides (.md)
│   ├── chat/                       # Chat endpoints, streaming sessions, and agent job bridges
│   │   └── api.py                  # /chat/stream, /chat/agent, /chat/agent/job/{id}
│   ├── docs_gen/                   # Automated repository documentation generation
│   │   └── api.py                  # /docs-gen/generated, /docs-gen/regenerate
│   ├── execution/                  # Sandbox scheduling and command execution
│   │   ├── api.py                  # /execution/sandbox-runs
│   │   └── sandbox.py              # SandboxExecutionService with hash-binding verification
│   ├── files/                      # Filesystem CRUD operations and repository safety boundaries
│   │   └── api.py                  # /files/read, /files/write, /files/edit, /files/tree, /files/search
│   ├── graph/                      # Knowledge graph domain logic and repository abstractions
│   │   ├── api.py                  # /graph/nodes, /graph/edges, /graph/timeline, /graph/snapshots
│   │   ├── causal.py               # CausalGraphService for failure root cause chains
│   │   ├── consistency.py          # MultiStoreConsistencyService for outbox reconciliation
│   │   ├── data_flow.py            # DataFlowTracingService (schema -> route -> client)
│   │   ├── events.py               # GraphEventWriter (InMemory and Postgres implementations)
│   │   ├── repository.py           # GraphRepository (InMemory and Postgres implementations)
│   │   ├── schema.py               # Postgres table creation (ensure_schema)
│   │   ├── schemas.py              # GraphNode, GraphEdge, Node/Edge Type enums
│   │   └── service.py              # GraphService high-level query and mutation coordinator
│   ├── learning/                   # Continuous repository learning and policy distillation
│   │   ├── api.py                  # /learning/policy-distillation/runs
│   │   └── policy_distillation.py  # Distills repeated review rejections into policy rules
│   ├── memory/                     # Durable 4-tier memory system and conflict resolution
│   │   ├── api.py                  # /memory/records, /memory/types, /memory/context
│   │   ├── conflict.py             # Deterministic conflict resolution formula
│   │   ├── context.py              # Type-aware retrieval weighting and graph-anchored context
│   │   ├── records_api.py          # REST endpoints for CRUD on memory records
│   │   ├── schemas.py              # MemoryRecord schemas, IntentGraph, EngineeringDNA
│   │   ├── services.py             # IntentGraphService, EngineeringDNAService
│   │   └── store.py                # MemoryStore (.codexa/memories.json persistence)
│   ├── observability/              # Live agent inspection, metrics, and telemetry
│   │   └── api.py                  # /observability/events, /observability/usage, /observability/agents
│   ├── perception/                 # Ingestion pipeline, trust boundaries, and sanitization
│   │   ├── api.py                  # /perception/artifacts
│   │   ├── repository.py           # ArtifactRepository (InMemory and Postgres)
│   │   ├── schemas.py              # IngestArtifactRequest, TrustLevel enum
│   │   └── trust_boundary.py       # Prompt injection sanitization regexes
│   ├── repository/                 # Repository ingestion, Tree-sitter AST parsing, Git mining
│   │   ├── analyze.py              # Tree-sitter parsers (Python, JS, TS, TSX)
│   │   ├── api.py                  # /repository/load, /repository/create, /repository/list
│   │   ├── coupling.py             # Git log change-coupling miner
│   │   ├── intent.py               # Express/FastAPI route extractor, dependency analyzer
│   │   ├── scoring.py              # Repository architecture health scoring
│   │   └── semantic.py             # Semantic LLM-derived code symbol summaries
│   ├── simulation/                 # Pre-execution blast radius simulation
│   │   ├── api.py                  # /simulation/scenarios, /simulation/chaos/pre-mortems
│   │   ├── chaos.py                # ChaosPremortemService
│   │   ├── engine.py               # EngineeringSimulationEngine, SHA-256 diff hashing
│   │   └── witness.py              # Subgraph witness state hashing
│   ├── trust_safety/               # Health metrics, economics, calibration, and incident learning
│   │   ├── api.py                  # /trust-safety/health, /trust-safety/economics, /trust-safety/incidents
│   │   ├── confidence.py           # Multi-factor confidence calibration
│   │   ├── economics.py            # Technical debt score and engineering effort estimator
│   │   ├── explain.py              # Deterministic graph-templated incident explanation
│   │   ├── health.py               # RepositoryHealthService
│   │   ├── incident.py             # IncidentLearningService (causal graph builder)
│   │   ├── policy.py               # PolicyEngine execution gates
│   │   └── verification.py         # VerificationService
│   └── understanding/              # Architectural evolution and automated review
│       ├── api.py                  # /understanding/architecture/trends, /understanding/architecture/nightly-review
│       ├── architecture_evolution.py # Linear extrapolation of module coupling debt
│       └── nightly_review.py       # Automated codebase drift analysis
├── graph-viz/                      # Flagship Next.js 15 WebGL / Three.js Frontend Application
│   ├── app/                        # Next.js App Router
│   │   ├── (workspace)/            # Workspace layout shell with global navigation rail
│   │   │   ├── chat/page.tsx       # Live agent execution interface, chat history, impact cards
│   │   │   ├── strata/page.tsx     # 3-band architectural Strata visualization (Signals, Code, Intent)
│   │   │   ├── graph/page.tsx      # 3D interactive WebGL Knowledge Graph (Three.js)
│   │   │   ├── architecture/page.tsx # Architecture trends, health scores, and coupling matrices
│   │   │   ├── time-machine/page.tsx # Historical architecture replay and drift scrubber
│   │   │   ├── memory/page.tsx     # 4-tier memory inspector and conflict audit view
│   │   │   ├── ide/page.tsx        # In-browser repository code editor and tree browser
│   │   │   ├── docs/page.tsx       # Generated living documentation viewer
│   │   │   ├── usage/page.tsx      # Token usage, provider costs, and latency analytics
│   │   │   └── agents/page.tsx     # Active agent processes and Quorum inspection
│   ├── components/                 # React UI Components
│   │   ├── strata/                 # StrataView, Matrix, TimeBar, Glyph, Inspector
│   │   ├── graph/                  # GraphScene (Three.js canvas), GraphSearch, Inspector
│   │   ├── chat/                   # ExecutionPane, ImpactCard, RepoDialog
│   │   ├── shell/                  # Rail, RepoSwitcher, JobWatcher, PageHeader
│   │   └── ui/                     # ThinkingLoader, MarkdownView, Primitives
│   └── lib/                        # Client-side stores and math libraries
│       ├── api.ts                  # Fetch client for all 74 backend endpoints
│       ├── chat-store.ts           # Zustand/React state for chat conversations
│       ├── job-store.ts            # Active SSE job streaming and event dispatch
│       ├── repo-store.ts           # Selected active repository state
│       └── strata/                 # Custom geometry, cubic bezier routing, matrix layout
├── client/                         # Legacy React/Vite client application (minimal)
├── docs/                           # Authoritative architectural specifications
│   ├── codexa_os_build_prompt_v5.md # Ground-truth master specification v5
│   └── semantic_memory_layer_proposal.md # Memory architecture proposal
├── infra/                          # Infrastructure and container configurations
│   ├── docker-compose.yml          # PostgreSQL 16, Neo4j 5.x, Qdrant, Redis definitions
│   └── migrations/                 # PostgreSQL schema migrations
│       └── 0001_core.sql           # Core DDL for nodes, edges, events, and artifacts
├── tests/                          # Automated pytest test suites (79 files)
│   ├── audit/codexa_claims/        # 10 comprehensive claim verification suites
│   │   ├── runner.py               # Master test runner (10/10 passing suites)
│   │   └── evidence/               # Cryptographic JSON evidence files
│   └── benchmarks/                 # Memory and graph benchmarking suites
└── CODEXA_CLAIMS_AND_PROOF_AUDIT.md # Historical audit log with empirical evidence
```

---

## 5. High-Level Architecture

The architecture of Codexa OS is designed around strict unidirectional boundaries. Unsanitized external inputs cannot touch agent contexts, and unverified agent outputs cannot touch the filesystem.

```mermaid
flowchart TB
    subgraph Client Layer [Frontend Presentation Layer: graph-viz Next.js 15]
        UI_Chat[Chat & Execution Pane]
        UI_Strata[Strata 3-Band Architectural View]
        UI_Graph[Three.js 3D Knowledge Graph]
        UI_Time[Time Machine Temporal Scrubber]
        UI_Memory[Memory & Engineering DNA Inspector]
    end

    subgraph API_Gateway [FastAPI Gateway: backend/main.py]
        MW_Catch[_CatchUnhandledMiddleware]
        MW_CORS[CORSMiddleware]
        Router_Agents[/agents/* Router]
        Router_Chat[/chat/* Router]
        Router_Graph[/graph/* Router]
        Router_Memory[/memory/* Router]
        Router_Files[/files/* Router]
        Router_Sim[/simulation/* Router]
    end

    subgraph Core_Services [Domain Services Layer]
        JM[JobManager: jobs.py]
        LLM[LLMClient: llm.py]
        TB[TrustBoundaryService]
        PE[PolicyEngine & Verification]
        SIM[EngineeringSimulationEngine]
        AST[Tree-sitter Analyzer: analyze.py]
        MINE[Git Coupling Miner: coupling.py]
        INTENT[Route & Decision Miner: intent.py]
        MEM[MemoryStore: store.py]
        GS[GraphService: service.py]
        QRM[QuorumService: quorum.py]
    end

    subgraph Storage_Layer [Storage & Persistence Layer]
        PG[(PostgreSQL: 0001_core.sql)]
        MEM_JSON[(.codexa/memories.json)]
        JOBS_JSON[(backend/data/jobs/*.json)]
        REPOS_DIR[(.codexa/repos/*)]
        MEM_STORE[(In-Memory Graph State)]
    end

    UI_Chat -->|HTTP / SSE Stream| MW_Catch
    UI_Strata -->|REST Queries| MW_Catch
    UI_Graph -->|REST Nodes/Edges| MW_Catch
    MW_Catch --> MW_CORS
    MW_CORS --> Router_Chat & Router_Agents & Router_Graph & Router_Memory & Router_Files & Router_Sim

    Router_Chat --> JM
    Router_Agents --> QRM & SIM & PE
    JM --> LLM
    JM --> TB
    JM --> MEM
    JM --> GS
    JM -->|Mutations| Storage_Layer

    AST --> GS
    MINE --> GS
    INTENT --> GS
    GS --> PG & MEM_STORE
    MEM --> MEM_JSON
    JM --> JOBS_JSON
```

---

## 6. End-to-End Request Lifecycle

When a developer types a prompt into the Codexa OS interface—such as:
> *"Fix the race condition in auth token refresh and ensure user sessions do not drop."*

The following 18-step sequence is executed deterministically:

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant UI as Frontend (graph-viz)
    participant API as FastAPI Router (/chat/agent)
    participant JM as JobManager (jobs.py)
    participant Intent as Intent Classifier (task.py)
    participant Mem as MemoryStore & Context (context.py)
    participant Graph as GraphService & AST
    participant Router as Model Router (llm.py)
    participant Model as LLM Provider (Upstage/Gemini/Z.ai)
    participant Tools as Tool Engine (tools.py)
    participant Verify as Claim Verifier (verification.py)
    participant Disk as Filesystem & Git

    User->>UI: Types request & clicks Send
    UI->>API: POST /chat/agent (repo, message, model)
    API->>JM: JobManager.create() & start in background thread
    API-->>UI: Returns { job_id } immediately (Non-blocking)
    UI->>API: GET /chat/agent/stream/{job_id} (SSE Subscription)
    
    rect rgb(240, 248, 255)
    Note over JM,Intent: Step 1: Task Contract Formulation
    JM->>Intent: classify_intent(message)
    Intent-->>JM: TaskContract (intent=MODIFY_ARTIFACT, required_tools=['edit_file|write_file'])
    end

    rect rgb(255, 250, 240)
    Note over JM,Graph: Step 2: Graph-Anchored Context Assembly
    JM->>Graph: Resolve symbols mentioned in prompt ('auth token refresh')
    Graph-->>JM: Candidate CodeSymbol & File nodes (auth.ts)
    JM->>Mem: 1. Check pre-computed symbol semantic annotations (source="symbol_annotations")
    Mem-->>JM: Return cached symbol purpose & invariant summaries (semantic.py)
    JM->>Graph: 2. 1-to-2 hop AST traversal (calls, imports, depends_on)
    Graph-->>JM: Linked dependency neighborhood & interfaces
    JM->>Mem: 3. Pull procedural, episodic & convention memory records
    Mem-->>JM: Stack conventions, token refresh rules
    end

    rect rgb(245, 255, 245)
    Note over JM,Model: Step 3: Inference & Tool Invocation Loop
    JM->>Router: Select model from heavy tier with failover
    Router->>Model: stream(system_prompt + context + tools)
    Model-->>JM: SSE reasoning chunks (thought tokens streamed to UI)
    Model-->>JM: Tool Call: read_file("src/auth.ts")
    JM->>Tools: execute_tool("read_file")
    Tools->>Disk: Read file contents (Secret check passed)
    Disk-->>Tools: File contents
    Tools-->>JM: Tool Return
    JM->>UI: SSE Event: tool_return
    
    JM->>Model: Next round with tool return in history
    Model-->>JM: SSE reasoning chunks
    Model-->>JM: Tool Call: edit_file("src/auth.ts", old_text, new_text)
    JM->>Tools: execute_tool("edit_file")
    Tools->>Disk: Atomically write patched bytes to disk
    Disk-->>Tools: 0 (Success)
    Tools-->>JM: Tool Return: Success
    end

    rect rgb(255, 240, 245)
    Note over JM,Verify: Step 4: Machine-Gated Completion Validation
    Model-->>JM: Final text response ("I fixed the race condition...")
    JM->>Intent: validate_completion(contract, tools_called)
    Intent-->>JM: Contract Validated (required mutating tool was called)
    JM->>Verify: extract_claims(final_text)
    Verify->>Verify: Deterministically check claims against AST & file on disk
    Verify-->>JM: All claims verified
    JM->>Graph: Trigger background re-index of modified auth.ts
    JM->>Disk: Checkpoint job state to backend/data/jobs/{job_id}.json
    end

    JM->>UI: SSE Event: status = "completed"
    UI-->>User: Renders final response, diff view, and impact summary
```

### 6.1 Step-by-Step Architectural Execution Sequence

1. **User Prompt Dispatch**: Developer enters a request in the Next.js frontend (`/graph-viz/app/(workspace)/chat/page.tsx`). The frontend sends an HTTP `POST /chat/agent` payload carrying the repository identifier, conversation history, user prompt, and model preference to FastAPI (`backend/api/chat.py`).
2. **Asynchronous Job Initialization**: FastAPI invokes `JobManager.create()`, allocating an isolated job thread, initializing message histories, and persisting a checkpoint JSON record to `backend/data/jobs/{job_id}.json`. The router immediately responds to the browser with `{ job_id }`.
3. **SSE Channel Subscription**: The browser establishes an EventSource connection to `GET /chat/agent/stream/{job_id}`, receiving real-time Server-Sent Events (`round_start`, `reasoning_chunk`, `tool_call`, `tool_return`, `status`).
4. **Task Contract Formulation (Step 1)**: `JobManager` dispatches the raw prompt to `IntentClassifier.classify_intent()` (`backend/agents/task.py`). The classifier matches regex signatures against intent categories (`MODIFY_ARTIFACT`, `ANALYZE`, `EXPLAIN`). For mutation requests, it generates a `TaskContract` enforcing that mutating tools (`edit_file`, `write_file`) must be executed before the job can complete.
5. **Symbol Candidate Matching**: Context assembly begins (`backend/memory/context.py`). The query string is tokenized and matched against targetable graph nodes (`CodeSymbol`, `File`, `Module`, `Package`) indexed in Neo4j/in-memory graph state.
6. **Pre-Computed Symbol Semantic Annotations Lookup (Checked First)**:
   - Before executing graph traversal or reading raw file contents, Codexa loads `symbol_annotations` records from `MemoryStore` (`backend/memory/context.py:_load_annotations` querying `memory_type="semantic"`, metadata `source="symbol_annotations"`).
   - These annotations were pre-computed asynchronously by `backend/repository/semantic.py` using light-tier LLM passes and keyed by `symbol://{repository}/{file}#{qualname}`.
   - For each matched symbol (e.g. `refreshToken`), Codexa extracts the cached one-line purpose summary, invariants, and structural behavior (`entry["summary"]`).
   - This prevents LLM context saturation: the model understands the semantic role of targeted functions immediately without requiring multi-thousand token raw source ingestion.
7. **1-to-2 Hop AST Neighborhood Traversal**: `GraphService` retrieves structural relationships (`calls`, `imports`, `depends_on`) anchored to the matched symbols. Up to 10 incoming/outgoing relations per match are extracted, grounding the agent in the immediate call graph.
8. **Procedural & Convention Memory Injection**: `MemoryStore` filters out raw cache blobs and scores procedural/episodic records against the prompt, appending architectural invariants, testing rules, and project-specific conventions to the system context.
9. **Model Routing & Inference**: `ModelRouter` (`backend/agents/llm.py`) selects the optimal provider from the heavy tier (Upstage Solar Pro, Gemini 2.5 Flash, GLM, etc.) with automatic failover on rate limits (HTTP 429). The system prompt, grounded context, memory digest, and tool schemas are dispatched.
10. **SSE Thought Token Streaming**: Reasoning chunks from the provider are streamed directly to the frontend's `ThinkingLoader` component in real time.
11. **Tool Invocation & Sandboxed Execution**: When the model emits a tool call (e.g., `read_file` or `edit_file`), `backend/agents/tools.py` validates arguments, enforces file path confinement to `.codexa/repos/`, checks secret boundaries, and executes the operation atomically.
12. **Machine-Gated Completion Validation**: When the model signals completion:
    - `task.py:validate_completion()` verifies that required tools from the `TaskContract` were actually executed.
    - `ClaimVerifier` (`backend/agents/verification.py`) parses the model's textual assertions against the AST and disk diffs, detecting hallucinated file edits or imaginary imports.
    - `GraphService` triggers background re-indexing of modified files.
    - `JobManager` marks job status as `completed`, writing the final state to disk and closing the SSE stream.

---

## 7. Frontend Architecture

The Codexa OS frontend is a modern web application built using **Next.js 15**, **React 19**, **Tailwind CSS**, and **Three.js** with WebGL rendering. It resides in the `/graph-viz` directory.

### 7.1 Core Pages and Routes
- `/chat` (`app/(workspace)/chat/page.tsx`): The primary agent interaction workspace. Displays real-time SSE streaming text, collapsible model thinking logs (`ThinkingLoader`), structured tool execution cards, impact assessments (`ImpactCard`), and repository dialogs (`RepoDialog`).
- `/strata` (`app/(workspace)/strata/page.tsx`): The flagship 3-band architectural visualizer. Renders Code, Signals, and Intent along horizontal planes with cubic bezier dependency routing and temporal scrubbing.
- `/graph` (`app/(workspace)/graph/page.tsx`): 3D interactive force-directed WebGL Knowledge Graph powered by Three.js (`components/graph/GraphScene.tsx`). Features live agent traversal illumination, node clustering, and symbol inspection.
- `/architecture` (`app/(workspace)/architecture/page.tsx`): Architectural trend charts, component coupling matrices, and technical debt projections.
- `/time-machine` (`app/(workspace)/time-machine/page.tsx`): Historical architectural drift scrubber allowing point-in-time graph state queries.
- `/memory` (`app/(workspace)/memory/page.tsx`): Visual explorer for the 4 memory tiers (Semantic, Episodic, Procedural, Organizational) and conflict resolution histories.
- `/ide` (`app/(workspace)/ide/page.tsx`): Full in-browser file tree browser and code viewer (`components/ide/CodeEditor.tsx`).
- `/docs` (`app/(workspace)/docs/page.tsx`): Living documentation viewer generated from the Knowledge Graph.
- `/usage` (`app/(workspace)/usage/page.tsx`): Real-time token consumption, reasoning budget accounting, and provider latency analytics.
- `/agents` (`app/(workspace)/agents/page.tsx`): Visual status board for background worker jobs and Quorum debate panels.

### 7.2 State Management and Networking
The frontend utilizes lightweight reactive stores:
- `job-store.ts`: Connects to backend SSE endpoints (`/chat/agent/stream/{job_id}`). Manages active jobs, decodes custom event streams, and maps raw events (`round_start`, `reasoning_chunk`, `tool_call`, `tool_return`, `checkpoint`) to React state.
- `chat-store.ts`: Manages conversation history, message trees, and model selection.
- `repo-store.ts`: Tracks the currently active repository, triggering re-fetching across all workspace views when switched.
- `api.ts`: Centralized fetch client wrapping all 74 backend REST endpoints with error normalization.

---

## 8. Backend Architecture

The backend is built with **FastAPI** and Python 3.12, located in `/backend`. The application entry point is `backend/main.py:create_app()`.

### 8.1 Middleware and Error Isolation Stack
To prevent silent failure modes in web browsers, `backend/main.py` introduces a specialized middleware sequence:
```python
app.add_middleware(_CatchUnhandledMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_DEV_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
```
**The `_CatchUnhandledMiddleware` Invariant**:
Under Starlette, registering an `@app.exception_handler(Exception)` causes 500 errors to be caught by `ServerErrorMiddleware`, which sits *outside* `CORSMiddleware`. As a result, internal 500 exceptions are transmitted over the raw socket without CORS headers, causing the browser to report a misleading generic "Failed to fetch / Network Error". By implementing `_CatchUnhandledMiddleware` as an explicit `BaseHTTPMiddleware` registered *before* `CORSMiddleware`, unhandled exceptions are caught inside the CORS boundary, properly decorated with `Access-Control-Allow-Origin`, and returned as clean JSON error payloads.

### 8.2 Dependency Injection and Service Composition
`create_app()` initializes and wires 17 core domain services:
- `GraphService` (backed by `PostgresGraphRepository` or `InMemoryGraphRepository`)
- `CausalGraphService` and `DataFlowTracingService`
- `MultiStoreConsistencyService`
- `LLMClient` (handling multi-provider model routing)
- `PlannerService`, `CoderService`, `ResearchAgentService`, and `QuorumService`
- `ContextAssemblyService`
- `VerificationService`, `PolicyEngine`, `ConfidenceCalibrationService`, `EngineeringEconomicsService`, and `RepositoryHealthService`
- `EngineeringSimulationEngine` and `SandboxExecutionService`
- `ArchitectureEvolutionService` and `NightlyArchitectureReviewService`
- `MemoryStore`, `IntentGraphService`, and `EngineeringDNAService`
- `TrustBoundaryService`

---

## 9. API Reference

The backend exposes **74 distinct OpenAPI endpoints** covering the entire platform lifecycle. The table below documents every endpoint:

| Method | Path | Controller Function | Description | Implementation Status |
|---|---|---|---|---|
| `POST` | `/agents/planner/plan` | `create_plan` | Generates a structured execution plan from a goal | IMPLEMENTED |
| `POST` | `/agents/planner/blast-radius` | `calculate_blast_radius` | Computes downstream affected nodes from a change | IMPLEMENTED |
| `POST` | `/agents/coder/propose` | `propose_code_change` | Proposes a code diff from task specification | IMPLEMENTED |
| `POST` | `/agents/coder/proposals` | `create_coder_proposal` | Saves a coder proposal to the graph | IMPLEMENTED |
| `POST` | `/agents/research/ask` | `ask_research_question` | Answers architectural questions using the graph | IMPLEMENTED |
| `POST` | `/agents/research/recommendations` | `get_recommendations` | Recommends refactorings and dependency cleanups | IMPLEMENTED |
| `POST` | `/agents/retrieval/context` | `assemble_context` | Traverses graph for token-budgeted context assembly | IMPLEMENTED |
| `POST` | `/agents/quorum/run` | `run_quorum` | Executes multi-model debate with verified claims | IMPLEMENTED |
| `POST` | `/agents/impact` | `calculate_impact` | Evaluates file-level blast radius and incident history | IMPLEMENTED |
| `POST` | `/chat/stream` | `chat_stream` | Basic streaming chat endpoint | IMPLEMENTED |
| `POST` | `/chat/agent` | `start_agent_job` | Dispatches background autonomous agent job | IMPLEMENTED |
| `GET` | `/chat/agent/job/{job_id}` | `get_agent_job` | Polls current state and status of an agent job | IMPLEMENTED |
| `GET` | `/chat/agent/stream/{job_id}` | `stream_agent_job` | SSE stream emitting live tokens, tools, & events | IMPLEMENTED |
| `POST` | `/chat/agent/job/{job_id}/cancel` | `cancel_agent_job` | Cancels a running background agent job | IMPLEMENTED |
| `POST` | `/chat/agent/job/{job_id}/continue` | `continue_agent_job` | Resumes an interrupted or paused agent job | IMPLEMENTED |
| `POST` | `/chat/agent/phased` | `start_phased_build` | Initiates multi-phase project scaffolding build | IMPLEMENTED |
| `GET` | `/chat/agent/phased/{build_id}` | `get_phased_build` | Returns current phase and results of phased build | IMPLEMENTED |
| `POST` | `/chat/agent/phased/{build_id}/cancel` | `cancel_phased_build` | Terminates an active phased build | IMPLEMENTED |
| `GET` | `/chat/models` | `list_available_models` | Lists configured LLM models grouped by tier | IMPLEMENTED |
| `GET` | `/docs-gen/generated` | `get_generated_docs` | Retrieves living documentation for active repo | IMPLEMENTED |
| `POST` | `/docs-gen/regenerate` | `regenerate_docs` | Triggers background documentation regeneration | IMPLEMENTED |
| `POST` | `/execution/sandbox-runs` | `schedule_sandbox_run` | Validates hash-binding & schedules sandbox run | IMPLEMENTED |
| `GET` | `/files/tree` | `get_file_tree` | Returns recursive nested directory tree of repo | IMPLEMENTED |
| `GET` | `/files/read` | `read_file_content` | Reads file content (blocks secret filenames) | IMPLEMENTED |
| `POST` | `/files/write` | `write_file_content` | Writes complete file content atomically | IMPLEMENTED |
| `POST` | `/files/edit` | `edit_file_content` | Surgically replaces exact text matches | IMPLEMENTED |
| `POST` | `/files/save` | `save_file_content` | Saves file from UI IDE and triggers re-index | IMPLEMENTED |
| `POST` | `/files/delete` | `delete_file_path` | Deletes a file or empty directory | IMPLEMENTED |
| `POST` | `/files/move` | `move_file_path` | Moves or renames files/folders | IMPLEMENTED |
| `POST` | `/files/mkdir` | `make_directory` | Creates directories recursively | IMPLEMENTED |
| `GET` | `/files/search` | `search_file_contents` | Regex search across repository files | IMPLEMENTED |
| `POST` | `/graph/nodes` | `create_node` | Creates a typed node in the Knowledge Graph | IMPLEMENTED |
| `GET` | `/graph/nodes` | `list_nodes` | Lists graph nodes filtered by type or property | IMPLEMENTED |
| `POST` | `/graph/edges` | `create_edge` | Creates a directed, typed, confidence-scored edge | IMPLEMENTED |
| `GET` | `/graph/edges` | `list_edges` | Lists edges filtered by from/to or type | IMPLEMENTED |
| `GET` | `/graph/edges/all` | `list_all_edges` | Lists all active edges in the knowledge graph | IMPLEMENTED |
| `GET` | `/graph/timeline` | `get_graph_timeline` | Returns historical change events for time scrubber | IMPLEMENTED |
| `GET` | `/graph/snapshots` | `get_graph_snapshot` | Returns complete graph state at given timestamp | IMPLEMENTED |
| `POST` | `/graph/causal/chains` | `record_causal_chain` | Records incident -> root cause -> fix graph chain | IMPLEMENTED |
| `GET` | `/graph/causal/overview` | `get_causal_overview` | Returns aggregate statistics of causal incidents | IMPLEMENTED |
| `POST` | `/graph/consistency/checks` | `check_consistency` | Reconciles Postgres event log with projections | IMPLEMENTED |
| `POST` | `/graph/data-flow/traces` | `trace_data_flow` | Traces flow from database schema to API routes | IMPLEMENTED |
| `POST` | `/learning/policy-distillation/runs` | `run_policy_distillation` | Distills review rejections into prevention rules | IMPLEMENTED |
| `GET` | `/memory/records` | `list_memory_records` | Lists memory records for a repository | IMPLEMENTED |
| `POST` | `/memory/records` | `create_memory_record` | Creates memory record with conflict resolution | IMPLEMENTED |
| `GET` | `/memory/types` | `list_memory_types` | Returns supported memory types (4 tiers) | IMPLEMENTED |
| `GET` | `/memory/repositories` | `list_memory_repos` | Lists repositories having stored memory bundles | IMPLEMENTED |
| `GET` | `/memory/context` | `get_memory_context` | Retrieves type-weighted memory context for query | IMPLEMENTED |
| `POST` | `/memory/intent/chains` | `record_intent_chain` | Records decision, tradeoff, rejected alternative | IMPLEMENTED |
| `POST` | `/memory/organizational/conventions` | `record_convention` | Stores team convention profile | IMPLEMENTED |
| `POST` | `/memory/engineering-dna/conventions` | `record_dna` | Stores repo-specific Engineering DNA convention | IMPLEMENTED |
| `GET` | `/observability/events` | `list_observable_events` | Returns recent system-wide graph events | IMPLEMENTED |
| `GET` | `/observability/usage` | `get_usage_summary` | Returns total token usage and cost breakdown | IMPLEMENTED |
| `GET` | `/observability/usage/records` | `list_usage_records` | Returns itemized LLM request usage records | IMPLEMENTED |
| `GET` | `/observability/usage/daily` | `get_daily_usage` | Returns daily token usage aggregates | IMPLEMENTED |
| `GET` | `/observability/snapshots` | `get_system_snapshot` | Returns full health and memory system snapshot | IMPLEMENTED |
| `GET` | `/observability/agents` | `list_active_agents` | Returns status of all running background agents | IMPLEMENTED |
| `POST` | `/perception/artifacts` | `ingest_artifact` | Ingests external text through trust boundary | IMPLEMENTED |
| `POST` | `/repository/load` | `load_repository` | Clones/loads repo, runs AST & git coupling | IMPLEMENTED |
| `POST` | `/repository/create` | `create_repository` | Scaffolds a new local repository on disk | IMPLEMENTED |
| `GET` | `/repository/list` | `list_repositories` | Lists all loaded repositories on disk | IMPLEMENTED |
| `POST` | `/repository/activate` | `activate_repository` | Sets repository as active for chat and graph | IMPLEMENTED |
| `DELETE` | `/repository/{name}` | `delete_repository` | Deletes a loaded repository and its memory | IMPLEMENTED |
| `POST` | `/repository/annotate` | `annotate_repository` | Triggers LLM semantic annotation of symbols | IMPLEMENTED |
| `GET` | `/repository/docs` | `get_repository_docs` | Retrieves living architectural documentation | IMPLEMENTED |
| `POST` | `/repository/docs/regenerate` | `regenerate_repo_docs` | Forces full regeneration of repository docs | IMPLEMENTED |
| `POST` | `/simulation/scenarios` | `run_simulation` | Simulates blast radius and generates hash witness | IMPLEMENTED |
| `POST` | `/simulation/chaos/pre-mortems` | `run_chaos_premortem` | Injects synthetic faults to evaluate resilience | IMPLEMENTED |
| `POST` | `/trust-safety/confidence/calibrations` | `calibrate_confidence` | Computes weighted multi-factor confidence | IMPLEMENTED |
| `GET` | `/trust-safety/confidence/calibrations` | `list_calibrations` | Lists historical confidence calibration records | IMPLEMENTED |
| `POST` | `/trust-safety/economics/estimates` | `estimate_economics` | Computes technical debt score & effort hours | IMPLEMENTED |
| `POST` | `/trust-safety/health/repository` | `evaluate_repo_health` | Evaluates coupling, churn, and quality health | IMPLEMENTED |
| `POST` | `/trust-safety/incidents/learning` | `record_incident_learning` | Links incident to prevention rules in graph | IMPLEMENTED |
| `GET` | `/trust-safety/incidents/{id}/explain` | `explain_incident` | Graph-templated causal incident explanation | IMPLEMENTED |
| `POST` | `/trust-safety/policy/execution-gate` | `evaluate_execution_gate` | Checks if proposed change meets safety policy | IMPLEMENTED |
| `POST` | `/trust-safety/verification/proposals` | `verify_proposal` | Formally verifies proposal against assertions | IMPLEMENTED |
| `GET` | `/understanding/architecture/trends` | `get_architecture_trends` | Returns projected module coupling bottlenecks | IMPLEMENTED |
| `POST` | `/understanding/architecture/trends` | `record_architecture_trend` | Records architectural trend metric in graph | IMPLEMENTED |
| `POST` | `/understanding/architecture/nightly-review` | `run_nightly_review` | Runs automated review of architectural drift | IMPLEMENTED |

---
'''

if __name__ == '__main__':
    print(f"Part 1 length: {len(get_part1())} characters, ~{len(get_part1().split())} words")
