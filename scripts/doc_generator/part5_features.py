"""Part 5: Section 36 Feature-by-Feature Documentation of Codexa Complete Documentation."""

def get_part5() -> str:
    return r'''## 36. Feature-by-Feature Documentation

This section provides an exhaustive technical audit of every major feature implemented in Codexa OS. Each feature is evaluated across all 17 standardized criteria.

---

### 1. 3D WebGL Knowledge Graph Visualization

- **Simple explanation**: A dynamic 3D interactive map of your codebase that lets you fly through files, functions, and API routes like a star system, watching nodes glow as agents touch them.
- **Technical explanation**: A Three.js WebGL force-directed graph renderer executing in an HTML5 canvas. Visualizes `GraphNode` entities as spherical glyphs and `GraphEdge` relationships as directional lines. Nodes are clustered by directory and module; edge opacity reflects confidence scores ($0.0–1.0$). Real-time SSE events from background agent jobs trigger active node pulsing.
- **User interaction**: Developer clicks the "Graph" tab in the navigation rail, drags to rotate in 3D space, scrolls to zoom, clicks nodes to open the symbol inspector, and searches for symbols using the search bar.
- **Frontend path**: `graph-viz/app/(workspace)/graph/page.tsx` -> `components/graph/GraphScene.tsx` -> `components/graph/Inspector.tsx`.
- **Backend path**: `GET /graph/nodes` -> `GET /graph/edges/all` -> `backend/graph/api.py:list_all_edges()`.
- **Model path**: None (direct graph projection rendering).
- **Tool path**: `lookup_symbol`, `list_symbols`.
- **Data flow**: PostgreSQL/InMemoryGraph -> FastAPI JSON serialization -> React Query / fetch -> Three.js BufferGeometry instantiation -> 60fps WebGL render loop.
- **Persistence**: PostgreSQL `graph_nodes` and `graph_edges` tables.
- **Validation**: Schema validation via Pydantic `GraphNode` and `GraphEdge` models.
- **Failure behavior**: If graph retrieval fails or is empty, renders an empty-state message with a button to load a repository.
- **Dependencies**: Three.js, React Three Fiber (or standard Three.js canvas), Lucide React.
- **Relevant files**: `graph-viz/components/graph/GraphScene.tsx`, `backend/graph/service.py`, `backend/graph/api.py`.
- **Relevant functions**: `GraphScene.render()`, `GraphService.list_nodes()`, `GraphService.list_edges_at()`.
- **Current implementation status**: IMPLEMENTED.
- **Evidence**: Verified live via frontend test suites and API tests in `tests/test_graph_api.py`.
- **Limitations**: In ultra-large codebases ($>10,000$ symbols), client-side WebGL frame rates may degrade without aggressive node level-of-detail (LOD) culling.

---

### 2. Strata 3-Band Architectural Visualizer

- **Simple explanation**: An architectural view that organizes your project into three horizontal layers: business events at the top, source code in the middle, and architectural intent at the bottom.
- **Technical explanation**: A custom multi-band SVG/Canvas visualization component (`StrataView.tsx`) that partitions graph nodes into three semantic strata: Signals (`Commit`, `CausalEvent`, `ArchitectureTrend`), Code (`File`, `ApiRoute`, `CodeSymbol`), and Intent (`Decision`, `Tradeoff`, `ConventionProfile`). Connects related cross-strata nodes via tapered cubic bezier curves.
- **User interaction**: Developer navigates to the "Strata" tab, toggles between "Strata", "Focus", and "Matrix" modes, hovers nodes to see connection paths, and drags the Time Bar to scrub historical states.
- **Frontend path**: `graph-viz/app/(workspace)/strata/page.tsx` -> `components/strata/StrataView.tsx` -> `components/strata/Matrix.tsx` -> `components/strata/TimeBar.tsx`.
- **Backend path**: `GET /graph/nodes` -> `GET /graph/edges/all` -> `GET /graph/snapshots`.
- **Model path**: None.
- **Tool path**: `tree`, `get_project_metadata`.
- **Data flow**: Graph query -> Node partitioning into 3 vertical bands -> Layout algorithm (`lib/strata/layout.ts`) -> SVG bezier path calculation (`lib/strata/geometry.ts`) -> Interactive DOM rendering.
- **Persistence**: Graph state in PostgreSQL / In-Memory.
- **Validation**: Strict type checks in `lib/strata/model.ts`.
- **Failure behavior**: Degrades gracefully to single-band view if intent or signal nodes are absent.
- **Dependencies**: React, Lucide React, custom bezier geometry math.
- **Relevant files**: `graph-viz/components/strata/StrataView.tsx`, `graph-viz/lib/strata/geometry.ts`, `graph-viz/lib/strata/layout.ts`.
- **Relevant functions**: `StrataView()`, `focusLayout()`, `route()`, `cubic()`.
- **Current implementation status**: IMPLEMENTED.
- **Evidence**: Live visual verified in browser auditor subagent transcripts and unit tests.
- **Limitations**: Graph bundling thresholds (`BUNDLE_OVER = 2`) hide dense edges until explicit node selection to avoid visual clutter.

---

### 3. Engineering Time Machine (Temporal History Replay)

- **Simple explanation**: A time slider that lets you scrub back in time to see exactly what your codebase architecture looked like weeks or months ago.
- **Technical explanation**: Point-in-time graph snapshot reconstruction engine. Utilizes the temporal interval properties (`valid_from`, `valid_to`) attached to all graph edges. When queried with timestamp $t$, queries all edges where $\text{valid\_from} \le t < \text{valid\_to}$.
- **User interaction**: User drags slider on the `/time-machine` page or Strata TimeBar; graph dynamically re-renders to reflect historical topology.
- **Frontend path**: `graph-viz/app/(workspace)/time-machine/page.tsx` -> `components/strata/TimeBar.tsx`.
- **Backend path**: `GET /graph/snapshots?at={iso_timestamp}` -> `backend/graph/api.py:get_graph_snapshot()`.
- **Model path**: None.
- **Tool path**: `git_log`.
- **Data flow**: Frontend timestamp selection -> REST query -> SQL `WHERE valid_from <= :at AND (valid_to IS NULL OR valid_to > :at)` -> JSON snapshot response -> Frontend visual diffing.
- **Persistence**: Temporal fields in PostgreSQL `graph_edges` table.
- **Validation**: ISO 8601 datetime parsing in Pydantic.
- **Failure behavior**: Returns nearest valid snapshot if exact timestamp contains no events.
- **Dependencies**: FastAPI, PostgreSQL JSONB.
- **Relevant files**: `backend/graph/service.py`, `backend/graph/repository.py`, `backend/graph/api.py`.
- **Relevant functions**: `GraphService.snapshot_at()`, `GraphRepository.list_edges_at()`.
- **Current implementation status**: IMPLEMENTED.
- **Evidence**: Verified in `tests/audit/codexa_claims/test_claim_graph_and_projections.py`.
- **Limitations**: Reconstructing deleted file contents historically depends on git object availability.

---

### 4. Tree-sitter Multi-Language AST Parsing

- **Simple explanation**: A language parser that reads code files and extracts functions, classes, and calls with absolute grammatical precision.
- **Technical explanation**: Native AST parser integration utilizing official Tree-sitter bindings for Python, JavaScript, TypeScript, and TSX. Compiles S-expression pattern queries to identify function definitions, class declarations, method implementations, arrow functions, and call expressions with precise AST parent-scope attribution.
- **User interaction**: Triggered automatically when loading a repository or saving a file.
- **Frontend path**: Status displayed in repository loading progress dialogs.
- **Backend path**: `POST /repository/load` -> `backend/repository/api.py:load_repository()` -> `backend/repository/analyze.py:analyze_repository()`.
- **Model path**: None (100% deterministic static analysis).
- **Tool path**: `lookup_symbol`, `list_symbols`.
- **Data flow**: File bytes on disk -> Tree-sitter C grammar parser -> Concrete Syntax Tree -> S-expression query match -> `Symbol` dataclasses -> `GraphNode` creation in EKG.
- **Persistence**: Emits `CodeSymbol` nodes and `calls`/`imports` edges to PostgreSQL/In-Memory graph.
- **Validation**: File extension filtering (`.py`, `.js`, `.ts`, `.tsx`) and file size bounds ($\le 1\text{ MB}$).
- **Failure behavior**: Malformed syntax creates `ERROR` nodes in AST while preserving extraction of surrounding valid symbols.
- **Dependencies**: `tree_sitter`, `tree_sitter_python`, `tree_sitter_javascript`, `tree_sitter_typescript`.
- **Relevant files**: `backend/repository/analyze.py`.
- **Relevant functions**: `analyze_repository()`, `_analyze_file()`, `_query_for()`, `_parser_for()`.
- **Current implementation status**: IMPLEMENTED.
- **Evidence**: Tested in `tests/audit/codexa_claims/test_claim_treesitter.py` (1,131 symbols extracted from httpx with zero errors).
- **Limitations**: C/C++, Rust, and Go grammars are not currently registered in `_LANG_BY_EXT`.

---

### 5. Git Change-Coupling Miner

- **Simple explanation**: A background analyzer that discovers which files frequently change together in git commits, revealing hidden dependencies that no code import shows.
- **Technical explanation**: A mining engine (`backend/repository/coupling.py`) that parses git commit logs using `git log -250 --name-only`. Computes co-occurrence matrices for file pairs across commits. Identifies pairs sharing $\ge 3$ commits with coupling strength $\ge 0.30$, emitting `CORRELATES_WITH` graph edges.
- **User interaction**: Automatic on repository load; results visible in Strata Matrix view and Impact analysis cards.
- **Frontend path**: `components/chat/ImpactCard.tsx` and `components/strata/Matrix.tsx`.
- **Backend path**: `POST /repository/load` -> `backend/repository/coupling.py:mine_change_coupling()`.
- **Model path**: None.
- **Tool path**: `get_dependencies`.
- **Data flow**: Subprocess `git log` execution -> Commit grouping -> Combinatorial pair counting -> Coupling strength calculation -> `GraphEdgeCreate(edge_type=CORRELATES_WITH)`.
- **Persistence**: Saved as `correlates_with` edges in the Knowledge Graph.
- **Validation**: Filters commits with $>20$ files (skips mass automated refactors or vendored dumps).
- **Failure behavior**: If directory is not a git repository (`not owns_git(dest)`), safely returns empty list without error.
- **Dependencies**: Host `git` executable.
- **Relevant files**: `backend/repository/coupling.py`, `backend/repository/intent.py`.
- **Relevant functions**: `mine_change_coupling()`, `owns_git()`.
- **Current implementation status**: IMPLEMENTED.
- **Evidence**: Verified in `tests/test_coupling_incident_risk.py`.
- **Limitations**: Shallow git clones (`git clone --depth 1`) provide insufficient commit history for coupling detection.

---

### 6. Multi-Framework Route & Architectural Intent Miner

- **Simple explanation**: An automatic scanner that detects all API routes (FastAPI, Express, Flask, Next.js) and declared software architecture decisions from configuration files.
- **Technical explanation**: Regex- and AST-driven route and manifest analyzer (`backend/repository/intent.py`). Extracts Express routes (`app.get`, `router.route`), FastAPI/Flask decorators (`@app.get`, `@router.post`), and Next.js route files (`route.ts`). Links routes to symbol handlers via `flows_into` edges. Inspects `package.json` and `pyproject.toml` to extract architectural decisions (`Decision` nodes).
- **User interaction**: Automatic upon loading repository; routes visible in Strata Code band.
- **Frontend path**: Strata Code band and IDE file tree.
- **Backend path**: `POST /repository/load` -> `backend/repository/intent.py:extract_routes_and_intent()`.
- **Model path**: None (evidence-based static extraction).
- **Tool path**: `get_project_metadata`.
- **Data flow**: Manifests and code files -> Regex/AST extraction -> `ApiRoute` and `Decision` nodes -> Graph insertion.
- **Persistence**: Saved as `ApiRoute` and `Decision` nodes in PostgreSQL/In-Memory graph.
- **Validation**: Maximum read cap of 2 MB per file (`_MAX_READ`).
- **Failure behavior**: Files exceeding size cap or lacking recognized frameworks are skipped silently.
- **Dependencies**: Standard Python libraries (`json`, `re`, `pathlib`).
- **Relevant files**: `backend/repository/intent.py`.
- **Relevant functions**: `extract_routes_and_intent()`, `_extract_express_routes()`, `_extract_fastapi_routes()`.
- **Current implementation status**: IMPLEMENTED.
- **Evidence**: Verified in `tests/audit/codexa_claims/test_claim_strata.py`.
- **Limitations**: Obfuscated or dynamically constructed metaprogramming routes (e.g. `router[method](...)`) may not be captured.

---

### 7. Multi-Agent Quorum Debate & Consensus

- **Simple explanation**: A feature where multiple different AI models independently solve an architecture problem, verify their claims against real code, and debate each other if they disagree.
- **Technical explanation**: Multi-model consensus system (`backend/agents/quorum.py`). Solicits structured `BeliefCard` objects in parallel from a panel of models. Verifies factual claims deterministically against repository AST and graph. If top-ranked models disagree, initiates an adversarial debate round providing peer critiques, and selects the winner using claim verification scores.
- **User interaction**: Triggered via API or during high-stakes planning tasks; debate logs visible on `/agents` page.
- **Frontend path**: `graph-viz/app/(workspace)/agents/page.tsx`.
- **Backend path**: `POST /agents/quorum/run` -> `backend/agents/quorum.py:QuorumService.run()`.
- **Model path**: Panel models (e.g. Gemini 3.8, Solar Pro, DeepSeek, GLM) queried in parallel.
- **Tool path**: None during debate (claims checked against pre-existing graph).
- **Data flow**: Request -> ThreadPoolExecutor parallel LLM calls -> BeliefCard parsing -> Verification against AST/disk -> Ranking -> Optional Debate round -> `QuorumRunResult`.
- **Persistence**: Emits `QuorumDecision` node to Knowledge Graph.
- **Validation**: BeliefCard schema validation with Pydantic; claim verification via `verify_claims()`.
- **Failure behavior**: If all panel models fail, falls back to reserve models; raises `QuorumUnavailableError` if all fail.
- **Dependencies**: `LLMClient`, `GraphService`.
- **Relevant files**: `backend/agents/quorum.py`, `backend/agents/verification.py`.
- **Relevant functions**: `QuorumService.run()`, `QuorumService._debate_round()`, `QuorumService._rank()`.
- **Current implementation status**: IMPLEMENTED.
- **Evidence**: Verified in `tests/audit/codexa_claims/test_claim_quorum.py`.
- **Limitations**: Incurring multiple parallel model calls increases token consumption and API costs.

---

### 8. Machine-Verifiable Task Contracts

- **Simple explanation**: A strict security guard that prevents an AI assistant from saying "I fixed your code!" when it actually forgot to save the file.
- **Technical explanation**: Deterministic contract enforcement layer (`backend/agents/task.py`). Classifies user prompts into `TaskIntent` and generates a `TaskContract` with explicit `required_tools`. At the conclusion of an agent round, `validate_completion()` mechanically checks if required mutating tools (`write_file`, `edit_file`, `delegate_task`) were invoked.
- **User interaction**: Automatic on all chat and agent requests.
- **Frontend path**: Renders validation errors and retry notices in Chat Execution Pane.
- **Backend path**: `backend/agents/jobs.py` -> `backend/agents/task.py:validate_completion()`.
- **Model path**: Used during initial intent classification; bypassed during validation (pure code logic).
- **Tool path**: Intercepts tool return events.
- **Data flow**: User message -> Regex intent classifier -> `TaskContract` -> Agent execution loop -> Completion validator -> Pass or Correction Injection.
- **Persistence**: Task contract serialized in `job.contract` inside job checkpoints.
- **Validation**: Hard programmatic enforcement of required tool execution.
- **Failure behavior**: Injects an authoritative system prompt forcing the model into a corrective execution round.
- **Dependencies**: Python standard library (`re`, `dataclasses`).
- **Relevant files**: `backend/agents/task.py`, `backend/agents/jobs.py`.
- **Relevant functions**: `classify_intent()`, `generate_contract()`, `validate_completion()`.
- **Current implementation status**: IMPLEMENTED.
- **Evidence**: Verified in `tests/audit/codexa_claims/test_claim_planning_and_contracts.py`.
- **Limitations**: Highly conversational multi-intent prompts (combining chatting and editing) may occasionally require fallback intent heuristics.

---

### 9. Graph-Grounded Claim Verification Engine

- **Simple explanation**: An automated fact-checker that inspects the AI's final answer, finds every factual statement (like "tests passed" or "function X created"), and verifies it against reality.
- **Technical explanation**: Post-hoc factual assertion verification engine (`backend/agents/verification.py`). Dispatches a lightweight model call to extract structured claims (`file_exists`, `symbol_exists`, `symbol_used_n_times`, `test_passed`, `action_performed`). Resolves each claim against the filesystem, Tree-sitter AST, and the turn's tool execution log.
- **User interaction**: Transparent to user; unverified claims prompt automated agent self-correction.
- **Frontend path**: Displayed in `ThinkingLoader` and job status events.
- **Backend path**: `backend/agents/jobs.py` -> `backend/agents/verification.py:verify_claims()`.
- **Model path**: Light-tier model used for claim extraction; verification is 100% deterministic code.
- **Tool path**: Inspects `job.tools_called` and `job.tool_exit_codes`.
- **Data flow**: Final answer draft -> Extraction prompt -> Structured claims JSON -> AST/disk verification -> Verified count / Failed count.
- **Persistence**: Checkpointed in job execution logs.
- **Validation**: Programmatic verification of existence, call counts, and exit codes.
- **Failure behavior**: Appends unverified claim warnings to agent context, prompting an immediate correction round.
- **Dependencies**: `LLMClient`, `tree_sitter`, filesystem access.
- **Relevant files**: `backend/agents/verification.py`.
- **Relevant functions**: `extract_claims()`, `verify_claims()`.
- **Current implementation status**: IMPLEMENTED.
- **Evidence**: Verified in `tests/audit/codexa_claims/test_claim_e2e_and_failures.py`.
- **Limitations**: Subjective statements ("this code is elegant") are excluded; only positive factual claims are verified.

---

### 10. Engineering Simulation Engine & Blast Radius

- **Simple explanation**: A pre-flight simulator that calculates what other parts of your app will break before allowing a code change to be executed.
- **Technical explanation**: Pre-execution simulation engine (`backend/simulation/engine.py`). Performs reverse-BFS traversal over Knowledge Graph dependency and change-coupling edges up to depth 4 to identify affected nodes. Scans diffs for destructive SQL migrations (`DROP COLUMN`, `ALTER TABLE`) and validates rollback viability. Computes cryptographic SHA-256 hashes of the diff and the witnessed dependency subgraph.
- **User interaction**: User views blast radius and risk score on `ImpactCard` in the chat UI before confirming execution.
- **Frontend path**: `graph-viz/components/chat/ImpactCard.tsx`.
- **Backend path**: `POST /simulation/scenarios` -> `backend/simulation/engine.py:EngineeringSimulationEngine.run()`.
- **Model path**: None (graph traversal and regex heuristics).
- **Tool path**: `summarize_changes`.
- **Data flow**: Code diff + changed node IDs -> Reverse BFS graph traversal -> Regex destructive check -> Risk scoring -> SHA-256 diff & witness hashing -> `SimulationResult`.
- **Persistence**: Emits `SimulationScenario` node to graph with `diff_hash` and `graph_state_hash`.
- **Validation**: Validates rollback steps and deployment sequences.
- **Failure behavior**: Sets status to `BLOCKED` if destructive changes lack explicit restore steps or blast radius exceeds safety bounds.
- **Dependencies**: `GraphService`, `PlannerService`, `hashlib`.
- **Relevant files**: `backend/simulation/engine.py`, `backend/simulation/witness.py`.
- **Relevant functions**: `EngineeringSimulationEngine.run()`, `hash_graph_state()`.
- **Current implementation status**: IMPLEMENTED.
- **Evidence**: Verified in `tests/audit/codexa_claims/test_claim_simulation_and_sandbox.py`.
- **Limitations**: Blast radius predictions rely on static imports and mined coupling; dynamic runtime reflection is not traced.

---

### 11. Cryptographic Sandbox Hash-Binding

- **Simple explanation**: A tamper-proof seal ensuring that the exact code simulated is the exact code executed, and that no files were altered in between.
- **Technical explanation**: Cryptographic execution gating mechanism (`backend/execution/sandbox.py`). When scheduling a sandbox run, the service checks the `SimulationScenario` node for the proposal. Verifies that status was `PASSED`. Re-hashes the incoming diff text with SHA-256 and compares it to `diff_hash`. Re-hashes the witnessed subgraph and compares it to `graph_state_hash`. If any bit has drifted, execution is blocked.
- **User interaction**: Automatic safety gate prior to test or deployment execution.
- **Frontend path**: ExecutionPane status indicators.
- **Backend path**: `POST /execution/sandbox-runs` -> `backend/execution/sandbox.py:SandboxExecutionService.schedule_run()`.
- **Model path**: None.
- **Tool path**: `run_command`, `run_tests`.
- **Data flow**: SandboxRunRequest -> Query simulation node -> Re-hash diff & graph witness -> Equality check -> Schedule or Block.
- **Persistence**: Appends `execution.sandbox_run.scheduled` event to event log.
- **Validation**: Cryptographic equality of SHA-256 digests.
- **Failure behavior**: Returns `SandboxRunStatus.BLOCKED` with explicit reasons (`simulation_content_mismatch`, `graph_state_changed`).
- **Dependencies**: `hashlib`, `GraphService`, `GraphEventWriter`.
- **Relevant files**: `backend/execution/sandbox.py`, `backend/simulation/witness.py`.
- **Relevant functions**: `SandboxExecutionService.schedule_run()`.
- **Current implementation status**: IMPLEMENTED.
- **Evidence**: Verified in `tests/audit/codexa_claims/test_claim_simulation_and_sandbox.py`.
- **Limitations**: Current sandbox execution synthesizes the Docker CLI argument array rather than spawning live container daemons on the host.

---

### 12. 4-Tier Durable MemoryStore with Conflict Resolution

- **Simple explanation**: A long-term project memory that remembers conventions, decisions, and past tasks across restarts, automatically resolving contradictions using a mathematical formula.
- **Technical explanation**: Durable disk-backed memory store (`backend/memory/store.py`). Partitions records into Semantic, Episodic, Procedural, and Organizational tiers. Persists to `.codexa/memories.json` under thread locks. Resolves conflicting facts on identical keys using the formula: $\text{Score} = (\text{trust} \times 0.4) + (\log_2(\text{corroboration}) \times 0.3) + (\text{recency} \times 0.3)$.
- **User interaction**: Memory viewable and editable on `/memory` page.
- **Frontend path**: `graph-viz/app/(workspace)/memory/page.tsx`.
- **Backend path**: `GET /memory/records`, `POST /memory/records` -> `backend/memory/store.py:MemoryStore.add()`.
- **Model path**: None in storage; memory blocks injected into all chat model prompts.
- **Tool path**: `commit_direction`.
- **Data flow**: Ingested fact -> Key collision check -> Formula score comparison -> Winner kept active, loser soft-deleted with `invalid_at` -> JSON serialization.
- **Persistence**: `.codexa/memories.json`.
- **Validation**: Schema validation via Pydantic `MemoryRecord`.
- **Failure behavior**: Corrupt JSON on disk falls back to clean reload; write locks prevent file corruption.
- **Dependencies**: Python standard library (`json`, `threading`, `pathlib`).
- **Relevant files**: `backend/memory/store.py`, `backend/memory/conflict.py`.
- **Relevant functions**: `MemoryStore.add()`, `MemoryStore.context_block()`, `resolve_conflict()`.
- **Current implementation status**: IMPLEMENTED.
- **Evidence**: Verified in `tests/audit/codexa_claims/test_claim_memory.py`.
- **Limitations**: Natural-language similarity clustering across differently-worded facts is not yet active (exact key matching used).

---

### 13. Graph-Anchored Type-Aware Context Assembly

- **Simple explanation**: An intelligent context retriever that pulls only the 1 or 2 files relevant to your question, boosting procedural memory for "how to" questions and semantic memory for "what is" questions.
- **Technical explanation**: Grounded context assembler (`backend/memory/context.py`). Resolves user queries to `File` and `CodeSymbol` nodes, extracting 1-hop dependencies along `imports`, `calls`, and `depends_on`. Applies regex query classifiers (`_TYPE_SIGNALS`) to award a $+0.35$ ranking bonus to matching memory tiers, truncating content blocks to 800 characters to prevent prompt bloat.
- **User interaction**: Operates automatically during every chat prompt construction.
- **Frontend path**: Visible in chat execution details.
- **Backend path**: `GET /memory/context?q={query}` -> `backend/memory/context.py:get_memory_context()`.
- **Model path**: None (pre-inference context assembly).
- **Tool path**: None.
- **Data flow**: Query string -> Type signal detection -> Graph node symbol resolution -> 1-hop edge expansion -> Relevance scoring -> Truncated context string.
- **Persistence**: Ephemeral context generated per turn.
- **Validation**: Bounded at $\le 5$ symbols, $\le 4$ neighbors, $\le 800$ characters per record.
- **Failure behavior**: If no symbols match, falls back gracefully to baseline repository digest records.
- **Dependencies**: `GraphService`, `MemoryStore`.
- **Relevant files**: `backend/memory/context.py`.
- **Relevant functions**: `_relevance_score()`, `_truncate()`, `get_memory_context()`.
- **Current implementation status**: IMPLEMENTED.
- **Evidence**: Verified in `tests/audit/codexa_claims/test_claim_memory.py`.
- **Limitations**: Synonym expansion for queries using novel jargon requires exact keyword or graph symbol alignment.

---

### 14. Multi-Provider LLM Router with Key Rotation & Failover Rings

- **Simple explanation**: An intelligent model router that switches between Gemini, Solar Pro, DeepSeek, and Groq, automatically rotating to backup API keys or fallback models if one hits a rate limit.
- **Technical explanation**: Multi-provider wrapper (`backend/agents/llm.py`). Connects to 13 providers. Organizes models into capability tiers. Maintains round-robin index `_active_key_index` across multi-key environments. Intercepts HTTP 429/503 errors to transparently rotate keys or walk the `_FAILOVER_RING` mid-turn.
- **User interaction**: User selects preferred model in Chat model switcher; failover occurs transparently if needed.
- **Frontend path**: Model dropdown in chat page header; provider indicator in `ThinkingLoader`.
- **Backend path**: `backend/agents/jobs.py` -> `backend/agents/llm.py:LLMClient.stream()`.
- **Model path**: Routes across Upstage, Gemini, Groq, Z.ai, SiliconFlow, NVIDIA NIM, and local Ollama.
- **Tool path**: Passes tool schemas to provider-native function calling APIs.
- **Data flow**: Messages array -> `_prepare_kwargs` (adds base URLs, auth headers, reasoning effort) -> `litellm.completion` / `stream` -> Error handler (key rotate / failover) -> Token generator.
- **Persistence**: Active model and token usage logged in job checkpoint.
- **Validation**: Drops unsupported parameters per provider via `litellm.drop_params = True`.
- **Failure behavior**: Walks failover ring; raises clean `RuntimeError` only if all ring candidates are exhausted.
- **Dependencies**: `litellm`, `dotenv`.
- **Relevant files**: `backend/agents/llm.py`.
- **Relevant functions**: `LLMClient.complete()`, `LLMClient.stream()`, `_prepare_kwargs()`.
- **Current implementation status**: IMPLEMENTED.
- **Evidence**: Verified in `tests/test_glm_multikey_and_delegation.py` and `tests/test_solar_debug_key.py`.
- **Limitations**: Some free providers (e.g. Unorouter free tier) impose strict 1 request/minute rate limits requiring extended sleep cooloffs.

---

### 15. Resilient Background Job Execution & SSE Streaming

- **Simple explanation**: A background worker that runs agent tasks in separate threads, continuously saving progress to disk so you can refresh the page or restart the server without losing your work.
- **Technical explanation**: Background execution engine (`backend/agents/jobs.py`). Spawns worker threads via `JobManager._loop()`. Streams events to the browser via Server-Sent Events (SSE). Serializes full job state atomically to `backend/data/jobs/{id}.json` after every tool execution. Recovers interrupted jobs automatically on server boot.
- **User interaction**: User watches real-time thinking tokens, tool calls, and file diffs stream in the chat interface.
- **Frontend path**: `graph-viz/lib/job-store.ts` connecting to `/chat/agent/stream/{id}`.
- **Backend path**: `POST /chat/agent` -> `GET /chat/agent/stream/{id}` -> `backend/agents/jobs.py:JobManager.start()`.
- **Model path**: Continuous streaming inference loops across multiple rounds.
- **Tool path**: Dispatches all 55 tools dynamically.
- **Data flow**: Thread execution -> `_emit()` appends to queue -> SSE generator yields JSON strings -> Browser EventSource dispatches to React store.
- **Persistence**: `backend/data/jobs/{job_id}.json` with Windows atomic rename retry backoff.
- **Validation**: Round budget enforcement ($\le 15$ rounds) and tool streak loop prevention.
- **Failure behavior**: Automatic model rotation on stall; graceful resume from disk checkpoint on server reboot.
- **Dependencies**: Python `threading`, `json`, FastAPI `StreamingResponse`.
- **Relevant files**: `backend/agents/jobs.py`.
- **Relevant functions**: `JobManager.start()`, `JobManager._loop()`, `JobManager._checkpoint()`, `JobManager.resume()`.
- **Current implementation status**: IMPLEMENTED.
- **Evidence**: Verified in `tests/audit/codexa_claims/test_claim_resilience_and_recovery.py`.
- **Limitations**: Background threads run in-process; scaling across multiple physical servers requires transitioning to Redis RQ.

---

### 16. Phased Project Scaffolding & Build Manager

- **Simple explanation**: A structured build manager that creates large software projects step-by-step—scaffolding directories first, implementing core logic second, and testing third.
- **Technical explanation**: Multi-phase project synthesis controller (`backend/agents/phased_build.py`). Translates a specification into 3 sequential phases: Architecture & Scaffolding, Core Implementation, and Integration & Tests. Spawns dedicated child `Job` instances for each phase, verifying phase artifacts before advancing.
- **User interaction**: User submits prompt like "Build a Pomodoro timer web app"; watches phases advance on progress meter.
- **Frontend path**: `components/shell/JobWatcher.tsx` and Chat workspace.
- **Backend path**: `POST /chat/agent/phased` -> `backend/agents/phased_build.py:PhasedBuildManager.start()`.
- **Model path**: Heavy orchestrator models for Phase 1 & 2; light models for Phase 3 tests.
- **Tool path**: `create_project`, `create_files`, `write_file`, `run_tests`.
- **Data flow**: Spec -> Phase decomposition -> Phase 1 job dispatch -> Verification -> Phase 2 job dispatch -> Verification -> Final project.
- **Persistence**: `backend/data/phased_builds/{build_id}.json`.
- **Validation**: Machine verification of phase success criteria before transitioning.
- **Failure behavior**: Child job failures trigger recovery attempts before failing the overall phase.
- **Dependencies**: `JobManager`, `LLMClient`.
- **Relevant files**: `backend/agents/phased_build.py`.
- **Relevant functions**: `PhasedBuildManager.start()`, `PhasedBuildManager._run_phase()`.
- **Current implementation status**: IMPLEMENTED.
- **Evidence**: Verified in `tests/test_delegate_build.py`.
- **Limitations**: Extremely large projects with $>50$ files can encounter cumulative token budget constraints.

---

### 17. Trust Boundary & Prompt Injection Content Isolation

- **Simple explanation**: A security filter that sanitizes incoming GitHub issues and web documents, stripping out malicious prompt injection attacks before the AI ever sees them.
- **Technical explanation**: Perception security layer (`backend/perception/trust_boundary.py`). Tags incoming text with a `TrustLevel`. Scans untrusted text with regular expressions matching prompt override attacks, tool execution commands, secret exfiltration directives, and destructive file instructions. Strips offending lines, replacing them with `[stripped external instruction]`.
- **User interaction**: Automatic protection when ingesting external artifacts via `/perception/artifacts`.
- **Frontend path**: None (backend security pipeline).
- **Backend path**: `POST /perception/artifacts` -> `backend/perception/trust_boundary.py:TrustBoundaryService.isolate()`.
- **Model path**: Pre-LLM sanitization gate.
- **Tool path**: Enforces that untrusted artifacts never directly invoke tools.
- **Data flow**: Untrusted artifact -> Regex pattern match -> Sanitization -> `IsolatedArtifact` -> EKG node creation.
- **Persistence**: Stored in PostgreSQL `artifacts` table with `instruction_content_removed` boolean flag.
- **Validation**: Regex matching against `INSTRUCTION_PATTERNS`.
- **Failure behavior**: Strips instructions while preserving legitimate text, logging security findings in `IsolatedArtifact.findings`.
- **Dependencies**: Python standard library `re`.
- **Relevant files**: `backend/perception/trust_boundary.py`, `backend/perception/schemas.py`.
- **Relevant functions**: `TrustBoundaryService.isolate()`, `_instruction_reasons()`.
- **Current implementation status**: IMPLEMENTED.
- **Evidence**: Verified in `tests/audit/codexa_claims/test_claim_security_and_trust_boundary.py`.
- **Limitations**: Novel multi-turn linguistic steganography or zero-shot obfuscations may require continuous regex updates.

---

### 18. Platform Mutation Guard & Secret File Protector

- **Simple explanation**: A built-in guardrail that prevents the AI assistant from ever editing Codexa's own code or reading your private `.env` API keys.
- **Technical explanation**: Host protection subsystem in `backend/agents/tools.py` and `backend/files/api.py`. Enforces `_MUTATING_TOOLS` blocking whenever target repository is `codexa-os`. Intercepts file read requests matching `_SECRET_FILENAMES` (`.env`, `credentials.json`, `id_rsa`, `*.pem`), returning an explicit refusal message before opening the file handle.
- **User interaction**: Transparent; user receives refusal message if attempting to access platform secrets.
- **Frontend path**: Refusal message rendered in Chat Execution Pane.
- **Backend path**: `backend/agents/tools.py:execute_tool()` and `backend/files/api.py:read_file()`.
- **Model path**: Intercepts tool call before execution.
- **Tool path**: Enforced on `read_file`, `write_file`, `edit_file`, `run_command`, `run_python`.
- **Data flow**: Tool invocation arguments -> Path normalization -> Secret filename check & Platform repo check -> Allow or Raise PermissionError.
- **Persistence**: Rejections logged in `job.tool_exit_codes` with exit code 1.
- **Validation**: Exact filename matching and case-insensitive prefix/suffix matching.
- **Failure behavior**: Deterministic refusal string returned to agent; execution continues safely.
- **Dependencies**: `pathlib`, `os`.
- **Relevant files**: `backend/agents/tools.py`, `backend/files/api.py`.
- **Relevant functions**: `_is_secret_file()`, `_refuse_secret()`, `is_platform_repo()`.
- **Current implementation status**: IMPLEMENTED.
- **Evidence**: Verified in `tests/audit/codexa_claims/test_claim_security_and_trust_boundary.py`.
- **Limitations**: Custom secret file names not matching standard patterns (e.g. `my_super_secret_config.txt`) must be declared manually.

---

### 19. Causal Incident Learning & Graph-Templated Explainability

- **Simple explanation**: When a bug occurs, Codexa records what broke, why it broke, how it was fixed, and a rule to prevent it from ever happening again—then explains it using verified facts instead of AI storytelling.
- **Technical explanation**: Incident learning pipeline (`backend/trust_safety/incident.py`) and explainability engine (`backend/trust_safety/explain.py`). Ingests incident post-mortems and constructs causal graph chains: $\text{RootCause} \xrightarrow{\text{CAUSES}} \text{Incident}$, $\text{Fix} \xrightarrow{\text{MITIGATES}} \text{RootCause}$, $\text{PreventionRule} \xrightarrow{\text{MITIGATES}} \text{RootCause}$. When explaining incidents, `explain_incident()` templates strictly over real graph edges, omitting unverified stages and avoiding LLM confabulation.
- **User interaction**: Viewable on `/trust-safety` page and via `GET /trust-safety/incidents/{id}/explain`.
- **Frontend path**: Strata Signal band and Incident Inspector cards.
- **Backend path**: `POST /trust-safety/incidents/learning` -> `GET /trust-safety/incidents/{id}/explain`.
- **Model path**: None during explanation (deterministic graph templating).
- **Tool path**: None.
- **Data flow**: Post-mortem data -> Causal graph nodes and edges -> Linked affected files -> Graph-templated narrative assembly.
- **Persistence**: Emits `CausalEvent` and `PreventionRule` nodes to PostgreSQL.
- **Validation**: Validates causal edge types and non-empty string fields.
- **Failure behavior**: If no causal nodes exist, returns clean empty narrative without guessing.
- **Dependencies**: `GraphService`.
- **Relevant files**: `backend/trust_safety/incident.py`, `backend/trust_safety/explain.py`.
- **Relevant functions**: `IncidentLearningService.record()`, `explain_incident()`.
- **Current implementation status**: IMPLEMENTED.
- **Evidence**: Verified in `tests/test_explain.py`.
- **Limitations**: Requires human or automated post-mortem input to seed the initial incident root cause analysis.

---

### 20. Architecture Evolution & Technical Debt Extrapolation

- **Simple explanation**: A forecasting tool that tracks how messy and tightly coupled your codebase is becoming, alerting you weeks before a module becomes an unmanageable bottleneck.
- **Technical explanation**: Architectural trend analysis engine (`backend/understanding/architecture_evolution.py`). Evaluates module coupling, complexity metrics, and churn rates across historical commits. Fits linear regression trajectories to project future complexity scores, generating alerts when coupling exceeds maintainability thresholds.
- **User interaction**: Visualized as trend graphs on `/architecture` page.
- **Frontend path**: `graph-viz/app/(workspace)/architecture/page.tsx`.
- **Backend path**: `GET /understanding/architecture/trends` -> `backend/understanding/api.py:get_architecture_trends()`.
- **Model path**: None (mathematical trend extrapolation).
- **Tool path**: None.
- **Data flow**: Historical commits & graph coupling -> Complexity scoring -> Trend fitting -> `ArchitectureTrend` graph node.
- **Persistence**: Emits `ArchitectureTrend` nodes to PostgreSQL EKG.
- **Validation**: Bounds projected complexity scores between $0.0$ and $1.0$.
- **Failure behavior**: Returns baseline trend if commit history is under 10 commits.
- **Dependencies**: `GraphService`, Python standard library math.
- **Relevant files**: `backend/understanding/architecture_evolution.py`.
- **Relevant functions**: `ArchitectureEvolutionService.record_trend()`, `ArchitectureEvolutionService.get_trends()`.
- **Current implementation status**: IMPLEMENTED.
- **Evidence**: Verified in `tests/test_architecture_evolution_api.py`.
- **Limitations**: Linear extrapolation assumes constant team velocity and commit frequency.

---
'''

if __name__ == '__main__':
    print(f"Part 5 length: {len(get_part5())} characters, ~{len(get_part5().split())} words")
