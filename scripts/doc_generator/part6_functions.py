"""Part 6: Section 37 Function-by-Function Technical Reference of Codexa Complete Documentation."""

def get_part6() -> str:
    return r'''## 37. Function-by-Function Technical Reference

This section provides an authoritative technical reference for the 20 most critical functions in Codexa OS, documenting their exact signatures, parameters, return types, call graphs, state changes, and failure modes.

---

### 1. `JobManager._loop(self, job_id: str) -> None`
- **File**: `backend/agents/jobs.py`
- **Purpose**: Primary worker loop driving the autonomous agent execution lifecycle across multiple rounds.
- **Parameters**: `job_id: str` — UUID string of the active job.
- **Return Value**: `None` (executes on background thread, yields SSE events and writes checkpoints).
- **Callers**: `JobManager.start()`, `JobManager.resume()`.
- **Downstream Calls**: `classify_intent()`, `LLMClient.stream()`, `execute_tool()`, `validate_completion()`, `extract_claims()`, `verify_claims()`, `_checkpoint()`, `_compact_stale_payloads()`, `reindex_repository()`.
- **State Changes**: Updates `job.round`, `job.status`, `job.messages`, `job.tools_called`, `job.current_wait_state`, `job.last_activity_ts`.
- **Side Effects**: Emits SSE events to connected web clients; writes serialized JSON to `backend/data/jobs/{job_id}.json`.
- **Failure Paths**: Catches model stalls and rotates models; catches provider HTTP 429/503 errors; marks `job.status = "failed"` if unrecoverable exception occurs.
- **Feature Relationship**: Autonomous Agent Execution Loop, Resilient Background Jobs.

---

### 2. `JobManager._checkpoint(self, job: Job) -> None`
- **File**: `backend/agents/jobs.py`
- **Purpose**: Durably persists the complete state of a job to disk with atomic rename retry logic for Windows OS file lock resilience.
- **Parameters**: `job: Job` — Dataclass instance containing conversation history, contract, and receipts.
- **Return Value**: `None`.
- **Callers**: `JobManager._loop()` after every tool execution and round completion.
- **Downstream Calls**: `os.replace()`, `json.dumps()`, `time.sleep()`.
- **State Changes**: Writes `backend/data/jobs/{job.id}.tmp` and renames to `{job.id}.json`.
- **Side Effects**: Disk I/O on host filesystem.
- **Failure Paths**: Catches `PermissionError` (`WinError 5`) caused by antivirus/OneDrive background indexing locks and applies exponential backoff retries.
- **Feature Relationship**: Crash Recovery, Resilient Background Jobs.

---

### 3. `validate_completion(contract: TaskContract, tools_called: list[str], messages: list[dict], working_repo: str) -> tuple[bool, str]`
- **File**: `backend/agents/task.py`
- **Purpose**: Enforces the invariant that an agent cannot declare a mutating task complete without having invoked real code-writing tools.
- **Parameters**:
  - `contract: TaskContract`: The governing contract specifying `required_tools` and `intent`.
  - `tools_called: list[str]`: Chronological list of tool names executed during the job.
  - `messages: list[dict]`: Conversation transcript.
  - `working_repo: str`: Name of the target repository.
- **Return Value**: `tuple[bool, str]` — `(is_valid, failure_reason)`.
- **Callers**: `JobManager._loop()`.
- **Downstream Calls**: None (pure validation logic).
- **State Changes**: None directly; rejection causes caller to inject a correction message.
- **Side Effects**: None.
- **Failure Paths**: Returns `(False, reason)` if intent was `CREATE_ARTIFACT` or `MODIFY_ARTIFACT` and no tool in `_DELEGATABLE_TOOLS` was called.
- **Feature Relationship**: Machine-Verifiable Task Contracts.

---

### 4. `classify_intent(message: str, system_note: str = "") -> list[str]`
- **File**: `backend/agents/tools.py`
- **Purpose**: Maps user prompt text into one or more of the 8 tool group names to bound the exposed tool schema space.
- **Parameters**:
  - `message: str`: User message content.
  - `system_note: str`: Optional system context.
- **Return Value**: `list[str]` — Subset of `["repo", "code", "runtime", "browser", "design", "git", "external", "orchestration"]`.
- **Callers**: `JobManager._loop()`, `start_agent_job()`.
- **Downstream Calls**: `_GROUP_SIGNALS` regex matching.
- **State Changes**: None.
- **Side Effects**: None.
- **Failure Paths**: Returns `[]` (empty list) for pure conversational greetings (`"hi"`, `"thank you"`), exposing zero tools.
- **Feature Relationship**: Tool Group Filtering, Dynamic Context Management.

---

### 5. `verify_claims(claims: list[Claim], repository: str, graph: Any, tool_calls: list[str] | None = None, exit_codes: list[int] | None = None) -> tuple[int, int, list[str]]`
- **File**: `backend/agents/verification.py`
- **Purpose**: Deterministically evaluates factual claims made in an agent's response against the repository filesystem, AST, and tool return logs.
- **Parameters**:
  - `claims: list[Claim]`: Structured assertions extracted by `extract_claims()`.
  - `repository: str`: Active repository name.
  - `graph: Any`: `GraphService` instance.
  - `tool_calls: list[str] | None`: Tools executed in this turn.
  - `exit_codes: list[int] | None`: Exit codes from tools.
- **Return Value**: `tuple[int, int, list[str]]` — `(verified_count, failed_count, failed_reasons)`.
- **Callers**: `JobManager._loop()`, `QuorumService._rank()`.
- **Downstream Calls**: `os.path.exists()`, `graph.list_nodes()`, AST symbol queries.
- **State Changes**: None.
- **Side Effects**: None.
- **Failure Paths**: Returns failed reasons for nonexistent files, missing symbols, failed tests, or uncalled actions.
- **Feature Relationship**: Graph-Grounded Claim Verification, Quorum Consensus.

---

### 6. `extract_claims(answer_text: str, llm: Any) -> list[Claim]`
- **File**: `backend/agents/verification.py`
- **Purpose**: Uses a lightweight model to extract up to 8 checkable positive factual claims from draft response prose.
- **Parameters**:
  - `answer_text: str`: Raw text generated by the agent.
  - `llm: Any`: `LLMClient` instance.
- **Return Value**: `list[Claim]` — List of typed claims (`ClaimType`, `target`, `assertion`).
- **Callers**: `JobManager._loop()`.
- **Downstream Calls**: `LLMClient.complete()` using a light-tier worker model.
- **State Changes**: None.
- **Side Effects**: Incurs minor token consumption on worker quota.
- **Failure Paths**: Catches LLM exceptions or JSON decode errors and returns `[]` (fails open so verification never blocks completion).
- **Feature Relationship**: Graph-Grounded Claim Verification.

---

### 7. `QuorumService.run(self, request: QuorumRunRequest) -> QuorumRunResult`
- **File**: `backend/agents/quorum.py`
- **Purpose**: Orchestrates multi-agent debate and consensus on architecture queries.
- **Parameters**: `request: QuorumRunRequest` — Contains question, repository, and optional model panel list.
- **Return Value**: `QuorumRunResult` — Winning answer, consensus boolean, belief cards, and graph decision node ID.
- **Callers**: API router `POST /agents/quorum/run`.
- **Downstream Calls**: `_gather_cards()`, `_rank()`, `_debate_round()`, `verify_claims()`, `GraphService.add_node()`.
- **State Changes**: Emits `QuorumDecision` node to Knowledge Graph.
- **Side Effects**: Queries 2 to 4 LLM providers concurrently.
- **Failure Paths**: Raises `QuorumUnavailableError` if all panel models fail.
- **Feature Relationship**: Multi-Agent Quorum Consensus.

---

### 8. `QuorumService._debate_round(self, all_cards: list[BeliefCard], tied: list[BeliefCard], request: QuorumRunRequest) -> list[BeliefCard]`
- **File**: `backend/agents/quorum.py`
- **Purpose**: Executes an adversarial rebuttal round between tied models that proposed conflicting answers.
- **Parameters**:
  - `all_cards: list[BeliefCard]`: Complete card collection.
  - `tied: list[BeliefCard]`: Top-scoring cards in conflict.
  - `request: QuorumRunRequest`: Original user request.
- **Return Value**: `list[BeliefCard]` — Revised cards post-debate.
- **Callers**: `QuorumService.run()`.
- **Downstream Calls**: `LLMClient.complete()` with peer critique context.
- **State Changes**: Updates answers and confidence scores on tied cards.
- **Side Effects**: Model inference calls.
- **Failure Paths**: If a model fails to revise, retains its round 1 card.
- **Feature Relationship**: Multi-Agent Quorum Consensus.

---

### 9. `LLMClient.stream(self, messages: list[dict], model: str | None = None, tools: list[dict] | None = None, ...) -> Iterator[Any]`
- **File**: `backend/agents/llm.py`
- **Purpose**: Generator yielding real-time chunks (reasoning tokens, content tokens, tool calls) with automatic rate-limit key failover.
- **Parameters**:
  - `messages: list[dict]`: Chat messages.
  - `model: str | None`: Target model ID.
  - `tools: list[dict] | None`: Function-calling schemas.
- **Return Value**: `Iterator[Any]` — Yields streaming chunk objects.
- **Callers**: `JobManager._loop()`.
- **Downstream Calls**: `_prepare_kwargs()`, `litellm.completion(stream=True)`.
- **State Changes**: Advances `_active_key_index` on HTTP 429.
- **Side Effects**: Network I/O to provider API.
- **Failure Paths**: Catches 429/503 errors; advances key index or walks `_FAILOVER_RING`.
- **Feature Relationship**: Model Router, Thinking / Reasoning Pipeline.

---

### 10. `LLMClient._prepare_kwargs(self, model: str, kwargs: dict) -> tuple[str, dict]`
- **File**: `backend/agents/llm.py`
- **Purpose**: Decorates provider requests with proper base URLs, bearer tokens, and extra model parameters (e.g. `reasoning_effort`).
- **Parameters**: `model: str`, `kwargs: dict`.
- **Return Value**: `tuple[str, dict]` — Sanitized `(effective_model, call_kwargs)`.
- **Callers**: `LLMClient.complete()`, `LLMClient.stream()`.
- **Downstream Calls**: Inspects `_MODEL_EXTRA_PARAMS`.
- **State Changes**: Sets `api_base`, merges extra parameters.
- **Side Effects**: None.
- **Failure Paths**: None.
- **Feature Relationship**: Provider Abstraction Layer.

---

### 11. `execute_tool(name: str, args: dict, repository: str) -> tuple[str, int]`
- **File**: `backend/agents/tools.py`
- **Purpose**: Central tool dispatcher validating security boundaries and executing actions against the filesystem or runtime.
- **Parameters**: `name: str`, `args: dict`, `repository: str`.
- **Return Value**: `tuple[str, int]` — `(output_string, exit_code)`.
- **Callers**: `JobManager._loop()`.
- **Downstream Calls**: `write_file()`, `edit_file()`, `run_command()`, `lookup_symbol()`, etc.
- **State Changes**: Filesystem changes, process execution.
- **Side Effects**: Disk I/O, subprocess spawns.
- **Failure Paths**: Returns exit code 1 and refusal text if attempting to mutate platform repo or read secret files.
- **Feature Relationship**: Tool Dispatch Engine, Security Isolation.

---

### 12. `analyze_repository(root: Path, repo_name: str) -> Analysis`
- **File**: `backend/repository/analyze.py`
- **Purpose**: Traverses a repository on disk, parsing source files with Tree-sitter and extracting symbol definitions, imports, and calls.
- **Parameters**: `root: Path` (filesystem directory), `repo_name: str`.
- **Return Value**: `Analysis` dataclass containing `files`, `symbols`, `edges`, `imports`.
- **Callers**: `backend/repository/api.py:load_repository()`, `reindex_repository()`.
- **Downstream Calls**: `_analyze_file()`, `_query_for()`, `_parser_for()`.
- **State Changes**: None directly.
- **Side Effects**: Reads files from disk.
- **Failure Paths**: Skips unparseable files or files exceeding 1 MB.
- **Feature Relationship**: Tree-sitter Static Analysis, Perception Plane.

---

### 13. `mine_change_coupling(dest: Path, known_files: set[str]) -> list[CouplingEdge]`
- **File**: `backend/repository/coupling.py`
- **Purpose**: Analyzes git commit history to detect pairs of files that change together without static code references.
- **Parameters**: `dest: Path`, `known_files: set[str]`.
- **Return Value**: `list[CouplingEdge]` — Coupled pairs with coupling strength $0.0–1.0$.
- **Callers**: `backend/repository/api.py:load_repository()`.
- **Downstream Calls**: `subprocess.run(["git", "log"])`.
- **State Changes**: Emits `CORRELATES_WITH` edges to graph.
- **Side Effects**: Spawns git subprocess.
- **Failure Paths**: Safely returns `[]` if directory is not a git repository or git fails.
- **Feature Relationship**: Git Change-Coupling Miner, Strata.

---

### 14. `extract_routes_and_intent(root: Path, known_files: set[str]) -> tuple[list[Route], list[Commit], list[Decision], list[Convention]]`
- **File**: `backend/repository/intent.py`
- **Purpose**: Extracts API routes, git commits, and architectural decisions from codebase manifests.
- **Parameters**: `root: Path`, `known_files: set[str]`.
- **Return Value**: Tuple containing extracted routes, commits, decisions, and conventions.
- **Callers**: `load_repository()`.
- **Downstream Calls**: Regex route matchers, JSON manifest parsers.
- **State Changes**: Emits `ApiRoute` and `Decision` nodes to graph.
- **Side Effects**: Reads disk files.
- **Failure Paths**: Returns empty lists for unparseable manifests.
- **Feature Relationship**: Multi-Framework Route Miner, Strata Intent Band.

---

### 15. `EngineeringSimulationEngine.run(self, request: SimulationRequest) -> SimulationResult`
- **File**: `backend/simulation/engine.py`
- **Purpose**: Computes blast radius, validates rollback viability, and hashes diff and graph state before execution.
- **Parameters**: `request: SimulationRequest`.
- **Return Value**: `SimulationResult` (`status: PASSED | BLOCKED`, blast radius node IDs, confidence).
- **Callers**: API router `POST /simulation/scenarios`.
- **Downstream Calls**: `PlannerService.compute_blast_radius()`, `hash_graph_state()`, `hashlib.sha256()`.
- **State Changes**: Adds `SimulationScenario` node to Knowledge Graph.
- **Side Effects**: Graph insertion.
- **Failure Paths**: Returns `status = BLOCKED` if destructive schema changes lack restore steps.
- **Feature Relationship**: Pre-Execution Simulation Engine.

---

### 16. `SandboxExecutionService.schedule_run(self, request: SandboxRunRequest) -> SandboxRunResult`
- **File**: `backend/execution/sandbox.py`
- **Purpose**: Verifies SHA-256 hash-binding of diff and dependency subgraph before scheduling sandbox run.
- **Parameters**: `request: SandboxRunRequest`.
- **Return Value**: `SandboxRunResult` (`status: SCHEDULED | BLOCKED`, docker args, blocked reasons).
- **Callers**: API router `POST /execution/sandbox-runs`.
- **Downstream Calls**: `hash_graph_state()`, `hashlib.sha256()`, `event_writer.append()`.
- **State Changes**: Emits `execution.sandbox_run.scheduled` event.
- **Side Effects**: Event log append.
- **Failure Paths**: Returns `BLOCKED` on diff mismatch or graph state drift.
- **Feature Relationship**: Cryptographic Sandbox Hash-Binding.

---

### 17. `MemoryStore.add(self, repository: str, memory_type: str, title: str, content: str, trust: float = 1.0) -> MemoryRecord`
- **File**: `backend/memory/store.py`
- **Purpose**: Appends or resolves conflicting memory records under thread safety.
- **Parameters**: `repository`, `memory_type`, `title`, `content`, `trust`.
- **Return Value**: `MemoryRecord`.
- **Callers**: `load_repository()`, `commit_direction()`.
- **Downstream Calls**: `resolve_conflict()`, `_save()`.
- **State Changes**: Modifies `self._records`, updates `.codexa/memories.json`.
- **Side Effects**: Disk write under `self._lock`.
- **Failure Paths**: Raises `ValueError` for unknown memory types.
- **Feature Relationship**: 4-Tier MemoryStore.

---

### 18. `resolve_conflict(existing: MemoryRecord, incoming_content: str, incoming_trust: float, incoming_created_at: datetime) -> ConflictDecision`
- **File**: `backend/memory/conflict.py`
- **Purpose**: Applies mathematical conflict resolution formula to determine whether new memory supersedes existing fact.
- **Parameters**: `existing: MemoryRecord`, `incoming_content`, `incoming_trust`, `incoming_created_at`.
- **Return Value**: `ConflictDecision` (`action: KEEP_EXISTING | REPLACE | CORROBORATE`).
- **Callers**: `MemoryStore.add()`.
- **Downstream Calls**: None (pure formula computation).
- **State Changes**: None.
- **Side Effects**: None.
- **Failure Paths**: None.
- **Feature Relationship**: Deterministic Conflict Resolution.

---

### 19. `TrustBoundaryService.isolate(self, artifact: IngestArtifactRequest) -> IsolatedArtifact`
- **File**: `backend/perception/trust_boundary.py`
- **Purpose**: Strips prompt override and injection instructions from untrusted external text.
- **Parameters**: `artifact: IngestArtifactRequest`.
- **Return Value**: `IsolatedArtifact` (`isolated_content`, `findings`, `safe_for_agent_context`).
- **Callers**: API router `POST /perception/artifacts`.
- **Downstream Calls**: `_instruction_reasons()`.
- **State Changes**: None.
- **Side Effects**: None.
- **Failure Paths**: Replaces injection lines with `[stripped external instruction]`.
- **Feature Relationship**: Trust Boundary Security Isolation.

---

### 20. `create_app() -> FastAPI`
- **File**: `backend/main.py`
- **Purpose**: Application factory configuring middleware, database connections, and registering all 74 REST endpoints.
- **Parameters**: None.
- **Return Value**: Configured `FastAPI` instance.
- **Callers**: Uvicorn server runner (`backend.main:app`).
- **Downstream Calls**: `ensure_schema()`, 17 service initializers, 14 router factories, `seed_graph()`.
- **State Changes**: Initializes `app.state`, starts background rehydration thread.
- **Side Effects**: Connects to PostgreSQL, binds HTTP listeners.
- **Failure Paths**: Catches database connection failures and falls back to in-memory repositories.
- **Feature Relationship**: System Architecture & API Gateway.

---
'''

if __name__ == '__main__':
    print(f"Part 6 length: {len(get_part6())} characters, ~{len(get_part6().split())} words")
