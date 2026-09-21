"""Part 3: Sections 18 through 24 of Codexa Complete Documentation."""

def get_part3() -> str:
    return r'''## 18. Neo4j Graph Architecture

The Knowledge Graph is the central repository of structural, operational, and architectural truth in Codexa OS.

### 18.1 Graph Schema: Nodes and Edges
The graph schema is defined in `backend/graph/schemas.py`.

#### The 17 Node Types (`GraphNodeType`)
1. `Repository`: Root entity representing a project repository.
2. `File`: Source code, configuration, or documentation file on disk.
3. `CodeSymbol`: Class, method, function, component, or hook extracted via AST.
4. `ApiRoute`: HTTP API endpoint (Express route, FastAPI decorator, Next.js handler).
5. `SchemaField`: Database table column or JSON schema property.
6. `ExternalArtifact`: Ingested issue, PR description, or documentation document.
7. `ArchitectureTrend`: Metric tracking complexity or coupling drift over time.
8. `SimulationScenario`: Proposed change scenario evaluated for blast radius.
9. `CausalEvent`: Incident, root cause, or deployment trigger.
10. `Decision`: Architectural decision extracted from code manifests.
11. `Tradeoff`: Engineering economics tradeoff record.
12. `RejectedAlternative`: Evaluated and rejected technical approach.
13. `OnboardingPath`: Recommended reading sequence for new developers.
14. `HealthMetric`: Composite repository health assessment.
15. `PreventionRule`: Guardrail derived from past incident post-mortems.
16. `ConventionProfile`: Observed team code conventions and patterns.
17. `QuorumDecision`: Consensus outcome from a multi-agent Quorum debate.

#### The 11 Edge Types (`GraphEdgeType`)
1. `calls`: Function invocation between `CodeSymbol` nodes.
2. `imports`: File-to-file or symbol-to-symbol import declaration.
3. `depends_on`: Generic structural or package dependency.
4. `causes`: Causal link from root cause to production incident.
5. `mitigates`: Remediation link from fix/test to incident or root cause.
6. `increases_risk_of`: Correlation indicating elevated failure probability.
7. `correlates_with`: Git-mined co-change coupling between files.
8. `derived_from`: Lineage link showing provenance from an artifact.
9. `supersedes`: Versioning link showing a new entity replacing an old one.
10. `flows_into`: Full-stack data trace (e.g. SchemaField -> Route -> Client).
11. `traces_to_decision`: Code file or route grounded in an architectural decision.

### 18.2 Metadata and Temporal Versioning Invariants
Every edge in the graph carries strict metadata:
- **`confidence`**: Float between $0.0$ and $1.0$. Static analysis edges (`static_analysis`) always receive $1.0$.
- **`source_type`**: Must be one of `static_analysis`, `llm_inferred`, or `human_asserted`. LLM-inferred edges must cite the backing artifact ID.
- **`valid_from` & `valid_to`**: UTC timestamps establishing the temporal interval during which the relationship existed. When an import is deleted, `valid_to` is set to the deletion timestamp rather than physically deleting the row. This powers the Time Machine API.

### 18.3 Architectural Status: PostgreSQL vs Neo4j
- **Actual Active Implementation**: The current production backend operates directly on PostgreSQL (via `PostgresGraphRepository` using JSONB) or in-memory (`InMemoryGraphRepository`). Graph traversals (BFS for blast radius, dependency tracing) are executed via recursive Python and SQL queries.
- **Documented Intent**: Neo4j is specified as a read-optimized Cypher projection for ultra-large topologies. A Docker container definition exists in `infra/docker-compose.yml`, but live Cypher connections are currently inactive in the backend service layer.

---

## 19. Qdrant Semantic Search

### 19.1 Architectural Specification
The authoritative specification (`docs/codexa_os_build_prompt_v5.md`) describes Qdrant as a vector projection engine:
- Code chunks (functions, classes, docstrings) are vectorized using dense text embeddings.
- Payloads store symbol stable IDs, repository tags, and file paths.
- Natural-language queries are embedded to retrieve relevant code blocks via cosine similarity.

### 19.2 Current Operational Implementation
In the active codebase:
1. `backend/memory/context.py` implements a fast, zero-dependency semantic discovery engine. It uses token-overlap matching combined with query intent classification (`_TYPE_SIGNALS`) and graph neighborhood expansion.
2. When the user queries "where is authentication handled", the engine:
   - Scans symbol names and semantic summaries in the Knowledge Graph.
   - Evaluates keyword overlap with $2\times$ weight on symbol/file titles.
   - Adds a $+0.35$ bonus if the query phrasing matches the target memory tier.
   - Traverses 1 hop of `calls` and `imports` edges to assemble the complete context block.
3. The standalone Qdrant vector projection remains an architectural specification ready for activation when deployment scales beyond single-node instances.

---

## 20. MemoryStore Architecture & Conflict Resolution

Codexa OS provides durable, project-specific memory in `backend/memory/store.py` (`MemoryStore`).

### 20.1 The Four Memory Tiers
Memories survive server restarts by persisting to disk at `.codexa/memories.json`. The store categorizes facts into 4 tiers:
1. **Semantic Memory**: Core repository architecture facts, component roles, and module purposes (e.g. "What the system does", "Database schema conventions").
2. **Episodic Memory**: History of previous agent runs, user interactions, and milestone builds.
3. **Procedural Memory**: Explicit instructions on how to build, run, test, and deploy the codebase (e.g. `npm run dev`, `pytest`, environment variables).
4. **Organizational Memory**: Engineering DNA, team conventions, code style habits, and PR review policies.

### 20.2 Deterministic Conflict Resolution (`backend/memory/conflict.py`)
When a new memory fact arrives that shares the same `(repository, memory_type, title)` key as an existing record, Codexa does *not* ask an LLM to resolve the dispute. It applies a deterministic mathematical scoring formula:

$$\text{Score} = (\text{trust} \times 0.40) + (\min(1.0, \log_2(\text{corroboration\_count} + 1) \times 0.25) \times 0.30) + (\text{recency} \times 0.30)$$

- **`trust`**: Float $0.0$ to $1.0$ determined by author trust level (`repo_owner` = 1.0, `external_untrusted` = 0.2).
- **`corroboration_count`**: Increments each time the exact same fact is observed across multiple commits or PRs.
- **`recency`**: Normalized decay score favoring recent observations.

#### Soft-Delete Audit Trail
If the incoming record scores higher than the existing record, the old record is *soft-deleted* by setting `invalid_at = datetime.now(UTC)`. It is never physically erased from disk, ensuring a complete audit trail of how project knowledge evolved.

---

## 21. Postgres and Event Architecture

PostgreSQL serves as the ultimate source of truth. The database schema is defined in `infra/migrations/0001_core.sql` and initialized automatically via `backend/graph/schema.py:ensure_schema()`.

```mermaid
erDiagram
    GRAPH_NODES ||--o{ GRAPH_EDGES : "from_node"
    GRAPH_NODES ||--o{ GRAPH_EDGES : "to_node"
    GRAPH_EVENTS ||--o{ GRAPH_NODES : "aggregate"
    ARTIFACTS ||--o{ GRAPH_NODES : "provenance"

    GRAPH_NODES {
        uuid id PK
        varchar node_type
        varchar stable_id UK
        jsonb properties
        timestamp created_at
        timestamp updated_at
    }

    GRAPH_EDGES {
        uuid id PK
        uuid from_node_id FK
        uuid to_node_id FK
        varchar edge_type
        float confidence
        varchar source_type
        timestamp valid_from
        timestamp valid_to
        uuid source_artifact_id
        jsonb properties
    }

    GRAPH_EVENTS {
        uuid id PK
        varchar event_type
        uuid aggregate_id
        jsonb payload
        timestamp created_at
    }

    ARTIFACTS {
        uuid id PK
        varchar source_uri
        varchar kind
        varchar trust_level
        text raw_content
        text isolated_content
        boolean instruction_content_removed
        timestamp created_at
    }
```

### 21.1 Turnkey Schema Initialization (`ensure_schema`)
When `CODEXA_DATABASE_URL` is set, `backend/main.py` calls `ensure_schema()` on boot. It executes idempotent DDL creating tables, primary keys, foreign keys, and indexes on `node_type`, `stable_id`, `(from_node_id, to_node_id)`, and `created_at`. If no database URL is set, the application falls back to `InMemoryGraphRepository` and `InMemoryGraphEventWriter`, allowing full local test and dev operation without Docker.

### 21.2 Outbox Pattern and Event Consistency
Every mutation to nodes or edges records an event in `graph_events`. `backend/graph/consistency.py` (`MultiStoreConsistencyService`) monitors the event log. It verifies that event counts match node/edge mutations and emits reconciliation actions if drift is detected.

---

## 22. Redis and Background Workers

### 22.1 Architectural Specification
The build specification defines Redis + RQ (Redis Queue) as the asynchronous job scheduling backbone for long-running operations:
- Git repository cloning and change-coupling analysis.
- Background AST re-indexing on commit hooks.
- Asynchronous policy distillation jobs.

### 22.2 Current Operational Implementation
In the active codebase:
1. Agent jobs are managed in-process via Python daemon threads in `backend/agents/jobs.py` (`JobManager._loop`).
2. Thread synchronization uses standard `threading.Lock` primitives.
3. Checkpoints are serialized directly to JSON files in `backend/data/jobs/{job_id}.json`.
4. Repository rehydration runs on a background daemon thread (`rehydrate` thread in `backend/main.py`).
5. Redis infrastructure is configured in `infra/docker-compose.yml`, while in-process thread execution provides single-process deployment simplicity.

---

## 23. Strata

Strata is Codexa OS's signature 3-band architectural visualizer, implemented in `graph-viz/components/strata/StrataView.tsx` and `graph-viz/lib/strata/`.

```mermaid
graph TB
    subgraph Signal_Band [Signals Band: Top]
        S1[Git Commits]
        S2[Production Incidents]
        S3[Architecture Trends]
    end

    subgraph Code_Band [Code Band: Middle]
        C1[API Routes: Express / FastAPI]
        C2[Source Files: .ts / .py]
        C3[Code Symbols: Functions / Classes]
    end

    subgraph Intent_Band [Intent Band: Bottom]
        I1[Architectural Decisions]
        I2[Declared Packages / Tradeoffs]
        I3[Team Conventions & Rules]
    end

    S1 -.->|modified| C2
    S2 -.->|implicates| C2
    C1 -->|calls / flows_into| C3
    C3 -->|defined_in| C2
    I1 -.->|evidenced_by| C2
    I3 -.->|enforced_in| C2
```

### 23.1 The Three Visual Bands
Strata organizes the Knowledge Graph along horizontal strata:
1. **Signals Band (Top)**: Real-world operational events, including git commits (`Commit`), production outages (`CausalEvent`), and health trend metrics (`ArchitectureTrend`).
2. **Code Band (Middle)**: Concrete code artifacts, including source files (`File`), API routes (`ApiRoute`), and symbols (`CodeSymbol`).
3. **Intent Band (Bottom)**: The "why" behind the code, including architectural choices (`Decision`), declared dependencies, and team conventions (`ConventionProfile`).

### 23.2 Three Interaction Modes
- **Strata Mode**: Default view showing all three bands with cubic bezier curve routing connecting related nodes across bands.
- **Focus Mode**: Isolates a single selected file or symbol and renders its immediate 1-hop dependencies with clear directional arrows.
- **Matrix Mode (`StrataMatrix.tsx`)**: Renders an $N \times N$ adjacency matrix displaying call frequencies and co-change coupling scores between modules.

### 23.3 The Time Bar Scrubber (`TimeBar.tsx`)
A timeline scrubber sits at the bottom of the Strata interface. Scrubbing backward queries `/graph/snapshots?at={timestamp}`. Nodes and edges that were created after the selected timestamp visually fade out, allowing engineers to watch architectural debt accumulate or observe how a refactoring unfolded over months.

---

## 24. Quorum

Quorum (`backend/agents/quorum.py`) is Codexa OS's multi-agent deliberation and consensus mechanism.

```mermaid
sequenceDiagram
    autonumber
    participant Client as API Caller (/agents/quorum/run)
    participant QS as QuorumService
    participant Panel as Panel Models (Parallel)
    participant Verifier as AST & Graph Verifier
    participant Judge as Calibration Scorer

    Client->>QS: QuorumRunRequest (question, models)
    QS->>Panel: Parallel inference: Gather Belief Cards
    Panel-->>QS: Returns BeliefCards with checkable claims & answers
    
    loop For Each BeliefCard
        QS->>Verifier: verify_claims(card.claims)
        Verifier->>Verifier: Check files, symbols, & tests on disk/graph
        Verifier-->>QS: verified_count, failed_count
    end

    QS->>Judge: _rank(cards): Score = verified - failed + calibration_confidence
    Judge-->>QS: Ranked cards

    alt Tie and Models Disagree
        Note over QS,Panel: Debate Round Triggered
        QS->>Panel: Send opposing peer arguments & failed claims
        Panel-->>QS: Revised BeliefCards
        QS->>Verifier: Re-verify claims
        QS->>Judge: Re-rank revised cards
    end

    QS->>Client: QuorumRunResult (winning answer, consensus_reached, belief_cards)
```

### 24.1 Belief Cards and Checkable Claims
Unlike standard LLM debates where agents output unstructured text, Quorum requires each model to output a structured `BeliefCard`:
```python
class BeliefCard(BaseModel):
    model: str
    answer: str
    confidence: float
    claims: list[BeliefCardClaim]
    reasoning: str
```
Every claim must be checkable against the repository:
- `file_exists`: Verifies file path exists on disk.
- `symbol_exists`: Verifies symbol is registered in Tree-sitter AST.
- `symbol_used_n_times`: Verifies exact call count in Knowledge Graph.
- `test_passed`: Verifies test runner output.

### 24.2 Deterministic Ranking
Quorum ranks cards using real ground truth:
$$\text{Score} = (\text{verified\_claims} - \text{failed\_claims}, \text{calibrated\_confidence})$$
Factual claims dominate the ranking. Subjective confidence only breaks ties between models with identical verification scores, and confidence is penalized if the model historically exhibited poor calibration.

### 24.3 Adversarial Debate Rounds
If two or more models tie for the top score *and* their proposed answers disagree, Quorum executes a `_debate_round`:
1. Each tied model receives the opposing models' answers, along with their verified and failed claims.
2. The model is asked to defend its position or concede.
3. Revised belief cards are gathered, re-verified, and re-ranked.
This eliminates sycophancy, ensuring consensus is grounded strictly in code facts.

---
'''

if __name__ == '__main__':
    print(f"Part 3 length: {len(get_part3())} characters, ~{len(get_part3().split())} words")
