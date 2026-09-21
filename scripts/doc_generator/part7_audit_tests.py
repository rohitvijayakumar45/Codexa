"""Part 7: Sections 38 through 42 of Codexa Complete Documentation."""

def get_part7() -> str:
    return r'''## 38. Novelty and Differentiation Audit

This section evaluates 16 technical novelty claims made by Codexa OS against existing industry prior art (GitHub Copilot, Cursor, Devin, Sweep, Aider). Each claim is audited against the 8 required criteria, distinguishing genuinely distinctive mechanisms from standard practices.

---

### 1. The Living Engineering Knowledge Graph (EKG)
1. **The Claim**: Unlike stateless AI chat tools, Codexa maintains a persistent, attributed, temporal knowledge graph that acts as the single source of truth for repository structure and operational history.
2. **Actual Implementation**: PostgreSQL `graph_nodes` and `graph_edges` tables store 17 typed entities and 11 typed relationships. Every edge carries confidence, source type, and `valid_from`/`valid_to` timestamps. Static analysis edges are extracted via Tree-sitter and updated dynamically after every agent file mutation.
3. **Why Differentiated**: Most tools use flat vector embeddings or ephemeral file dumps. Codexa represents code as an interconnected topological graph linking AST symbols, git change-coupling, API routes, and architectural decisions.
4. **Standard Components**: Graph databases and property graph data models are standard computer science concepts.
5. **Distinctive Components**: Embedding operational post-mortem causal chains and temporal versioning intervals into the exact same property graph that holds AST syntax symbols.
6. **Supporting Evidence**: `backend/graph/schemas.py`, `backend/repository/analyze.py`, and `tests/audit/codexa_claims/test_claim_graph_and_projections.py`.
7. **Unverified Aspects**: Graph scaling beyond 50,000 nodes without Neo4j Cypher projection index acceleration.
8. **Classification**: **POTENTIALLY DISTINCTIVE**.

---

### 2. Machine-Gated Task Contracts (`validate_completion`)
1. **The Claim**: Codexa prevents AI agents from falsely claiming they implemented a feature when they merely described it in chat text.
2. **Actual Implementation**: `backend/agents/task.py` classifies intent into `TaskIntent`, formulates a `TaskContract`, and mechanically blocks task completion if required mutating tools (`write_file`, `edit_file`, `delegate_task`) were not executed.
3. **Why Differentiated**: Prevents the ubiquitous LLM failure mode where models output code in markdown blocks without modifying the codebase.
4. **Standard Components**: Regex classification of prompt text.
5. **Distinctive Components**: Deterministic, programmatic rejection of the LLM's final answer with forced corrective re-prompting.
6. **Supporting Evidence**: `tests/audit/codexa_claims/test_claim_planning_and_contracts.py`.
7. **Unverified Aspects**: Complex conversational edge cases where a user explicitly asks to *see* code without applying it.
8. **Classification**: **FUNCTIONAL BUT CONVENTIONAL** (Well-engineered execution guardrail).

---

### 3. Graph-Grounded Claim Verification Engine (`verify_claims`)
1. **The Claim**: Codexa extracts specific factual claims from an agent's response and verifies them against the real filesystem and AST before allowing the user to see the answer.
2. **Actual Implementation**: `backend/agents/verification.py` extracts up to 8 positive claims (`file_exists`, `symbol_exists`, `test_passed`, `action_performed`) and resolves them deterministically against the OS filesystem, Tree-sitter AST, and tool receipts.
3. **Why Differentiated**: Traditional assistants rely on the LLM's self-reported confidence. Codexa checks claims against real ground truth.
4. **Standard Components**: Lightweight JSON extraction prompts.
5. **Distinctive Components**: Disregarding the LLM's confidence entirely and making truth a function of AST queries and file existence.
6. **Supporting Evidence**: `tests/audit/codexa_claims/test_claim_e2e_and_failures.py`.
7. **Unverified Aspects**: Extracting complex semantic claims (e.g. "this function runs in $O(N)$ time").
8. **Classification**: **POTENTIALLY DISTINCTIVE**.

---

### 4. Quorum Multi-Agent Grounded Debate Protocol
1. **The Claim**: Eliminates AI sycophancy by convening a multi-model panel that submits structured belief cards verified against real code, debating only when verified scores tie and answers disagree.
2. **Actual Implementation**: `backend/agents/quorum.py` queries models in parallel, extracts checkable claims, verifies them, and executes a second adversarial debate round only if top models conflict.
3. **Why Differentiated**: Standard multi-agent systems use unstructured round-robin chats where models quickly conform to the first model's errors. Quorum ranks by verified code facts minus failed claims.
4. **Standard Components**: Parallel LLM calls via thread pools.
5. **Distinctive Components**: Deterministic scoring based on AST claim verification combined with calibration discounting.
6. **Supporting Evidence**: `tests/audit/codexa_claims/test_claim_quorum.py`.
7. **Unverified Aspects**: Quorum performance on ambiguous subjective architectural decisions where zero factual claims can be extracted.
8. **Classification**: **POTENTIALLY DISTINCTIVE**.

---

### 5. Cryptographic Simulation Hash-Binding
1. **The Claim**: Guarantees that code executed in a sandbox is bit-identical to code evaluated during blast-radius simulation, blocking execution if the dependency graph drifted.
2. **Actual Implementation**: `backend/simulation/engine.py` and `backend/execution/sandbox.py` compute SHA-256 digests of the diff and the witnessed dependency subgraph. `schedule_run()` re-hashes both and aborts execution if either digest has changed.
3. **Why Differentiated**: Prevents race conditions where a dependency changes between the time an agent simulates a change and the time it executes tests.
4. **Standard Components**: Standard SHA-256 cryptographic hashing.
5. **Distinctive Components**: Hashing the *witnessed dependency subgraph* alongside the text diff.
6. **Supporting Evidence**: `tests/audit/codexa_claims/test_claim_simulation_and_sandbox.py`.
7. **Unverified Aspects**: Live container execution (currently synthesizes Docker CLI argument array).
8. **Classification**: **POTENTIALLY DISTINCTIVE** (Requires Docker daemon activation for end-to-end sandbox execution).

---

### 6. 4-Tier MemoryStore with Deterministic Conflict Resolution
1. **The Claim**: A durable cross-model memory store that never asks an LLM to resolve contradictory facts, using a mathematical formula combining trust, corroboration, and recency.
2. **Actual Implementation**: `backend/memory/store.py` and `conflict.py` persist Semantic, Episodic, Procedural, and Organizational memory, resolving collisions via $\text{Score} = (\text{trust} \times 0.4) + (\log_2(\text{corroboration}) \times 0.3) + (\text{recency} \times 0.3)$.
3. **Why Differentiated**: LLM-based memory resolvers frequently hallucinate compromises between contradictory facts. Codexa's formula is deterministic and leaves an immutable soft-deleted audit trail (`invalid_at`).
4. **Standard Components**: Flat JSON file persistence.
5. **Distinctive Components**: Deterministic mathematical weighting formula combined with permanent soft-delete audit trails.
6. **Supporting Evidence**: `tests/audit/codexa_claims/test_claim_memory.py`.
7. **Unverified Aspects**: Natural language semantic deduplication across facts with different titles.
8. **Classification**: **POTENTIALLY DISTINCTIVE**.

---

### 7. Git-Mined Change Coupling (`CORRELATES_WITH`)
1. **The Claim**: Discovers hidden code dependencies by analyzing which files frequently change together in git history, surfacing coupling that static AST parsers cannot detect.
2. **Actual Implementation**: `backend/repository/coupling.py` analyzes up to 250 commits, computes co-occurrence frequency, and emits `correlates_with` graph edges for pairs with coupling $\ge 0.30$.
3. **Why Differentiated**: Static analysis only sees explicit imports. Change coupling surfaces semantic couplings (e.g. database schema file and documentation file that must stay in sync).
4. **Standard Components**: Git log parsing and combinatorial co-occurrence counting (standard academic concept from CodeScene / Adam Tornhill).
5. **Distinctive Components**: Injecting change-coupling edges directly into the LLM's blast radius calculation.
6. **Supporting Evidence**: `tests/test_coupling_incident_risk.py`.
7. **Unverified Aspects**: Git repositories with fewer than 10 commits provide no signal.
8. **Classification**: **FUNCTIONAL BUT CONVENTIONAL** (Well-executed application of established research).

---

### 8. Strata 3-Band Architectural Visualizer
1. **The Claim**: A 3-band visual map organizing codebases into Signals, Code, and Intent with cubic bezier dependency curves and temporal scrubbing.
2. **Actual Implementation**: Custom SVG/Canvas layout engine (`StrataView.tsx`) rendering horizontal bands for Signals (commits, incidents), Code (files, routes, symbols), and Intent (decisions, conventions).
3. **Why Differentiated**: Most tools provide simple node-link force graphs. Strata gives clear visual hierarchy answering *what* (code), *why* (intent), and *what happened* (signals).
4. **Standard Components**: SVG rendering and cubic bezier math.
5. **Distinctive Components**: Tri-partite semantic stratification tied to a historical temporal scrubber.
6. **Supporting Evidence**: `graph-viz/components/strata/StrataView.tsx` and browser audit logs.
7. **Unverified Aspects**: Performance on repositories with $>1,000$ simultaneous edges.
8. **Classification**: **POTENTIALLY DISTINCTIVE** (Flagship UI innovation).

---

### 9. Graph-Grounded Incident Learning Chains
1. **The Claim**: Automatically chains incidents: $\text{Incident} \to \text{RootCause} \to \text{Fix} \to \text{RegressionTest} \to \text{PreventionRule}$, ensuring a codebase never makes the same mistake twice.
2. **Actual Implementation**: `backend/trust_safety/incident.py` writes explicit causal graph nodes and links them to the affected files.
3. **Why Differentiated**: Post-mortems typically live in Jira or Google Docs, disconnected from code. Codexa connects them directly to the files in the knowledge graph.
4. **Standard Components**: Relational database foreign keys.
5. **Distinctive Components**: Causal edge types (`causes`, `mitigates`) joined to file nodes to influence blast-radius risk scoring.
6. **Supporting Evidence**: `tests/test_explain.py`.
7. **Unverified Aspects**: Automatic extraction of root cause chains from unformatted chat transcripts.
8. **Classification**: **POTENTIALLY DISTINCTIVE**.

---

### 10. Graph-Templated Deterministic Explainability (`explain_incident`)
1. **The Claim**: Generates natural language explanations of system incidents purely by templating over graph edges without LLM hallucination.
2. **Actual Implementation**: `backend/trust_safety/explain.py` templates sentences across `causes` and `mitigates` edges, omitting missing links and citing exact node/edge IDs.
3. **Why Differentiated**: Sidesteps the hallucination problem by forbidding free LLM generation in security-critical audit trails.
4. **Standard Components**: Python string templating.
5. **Distinctive Components**: Zero-LLM architecture for audit explainability.
6. **Supporting Evidence**: `backend/trust_safety/explain.py`.
7. **Unverified Aspects**: Readability on extraordinarily complex multi-branched incident topologies.
8. **Classification**: **FUNCTIONAL BUT CONVENTIONAL** (Strict deterministic safety design).

---

### 11. Type-Aware Memory Retrieval Weighting
1. **The Claim**: Context retrieval analyzes query phrasing to dynamically boost relevant memory tiers (e.g. procedural for "how do I run" questions).
2. **Actual Implementation**: `backend/memory/context.py` matches queries against `_TYPE_SIGNALS` regexes, adding $+0.35$ bonus to matching tiers while truncating content blocks to 800 characters.
3. **Why Differentiated**: Prevents prompt saturation by ensuring "how to test" questions get procedural memory instead of generic project descriptions.
4. **Standard Components**: Regex keyword matching.
5. **Distinctive Components**: Combining query intent detection with memory tier boosting and graph neighborhood expansion.
6. **Supporting Evidence**: `tests/audit/codexa_claims/test_claim_memory.py`.
7. **Unverified Aspects**: Multilingual query phrasing.
8. **Classification**: **FUNCTIONAL BUT CONVENTIONAL**.

---

### 12. Multi-Provider Rate-Limit Key Rotation & Failover Rings
1. **The Claim**: Transparently survives provider rate limits by rotating through multiple configured API keys and walking failover rings mid-turn.
2. **Actual Implementation**: `backend/agents/llm.py` rotates `_active_key_index` on HTTP 429/503 and transitions between ring models (`_FAILOVER_RING`) while keeping conversation history intact.
3. **Why Differentiated**: Most tools simply fail and show an error when encountering a rate limit. Codexa continues autonomous execution seamlessly.
4. **Standard Components**: Exception handling around HTTP requests.
5. **Distinctive Components**: In-process conversational state migration across distinct model providers mid-turn.
6. **Supporting Evidence**: `tests/test_glm_multikey_and_delegation.py`.
7. **Unverified Aspects**: Maintaining perfect context alignment when switching between models with radically different prompt formatting styles.
8. **Classification**: **FUNCTIONAL BUT CONVENTIONAL** (Production hardening).

---

### 13. Resilient Background Checkpointing (`backend/data/jobs/`)
1. **The Claim**: Execution jobs run in background threads and checkpoint state to disk after every tool call, surviving server crashes and restarts.
2. **Actual Implementation**: `backend/agents/jobs.py` serializes `Job` dataclass to JSON with exponential retry backoff to overcome Windows OneDrive file locks.
3. **Why Differentiated**: Web requests are disconnected from long-running agent loops; users can close browser tabs without interrupting multi-minute builds.
4. **Standard Components**: File serialization and daemon threads.
5. **Distinctive Components**: Resumption from partial rounds and Windows OS-specific lock recovery.
6. **Supporting Evidence**: `tests/audit/codexa_claims/test_claim_resilience_and_recovery.py`.
7. **Unverified Aspects**: Distributed clustering across multiple nodes.
8. **Classification**: **FUNCTIONAL BUT CONVENTIONAL** (Robust engineering).

---

### 14. Trust Boundary Content Isolation Layer
1. **The Claim**: Strips prompt injection attacks from untrusted external documents before they reach any agent context, forbidding untrusted text from triggering tool calls.
2. **Actual Implementation**: `backend/perception/trust_boundary.py` classifies artifacts by `TrustLevel` and strips prompt overrides, tool commands, and secret extraction directives using compiled regexes.
3. **Why Differentiated**: Enforces an explicit data-plane trust boundary between untrusted inputs and tool execution.
4. **Standard Components**: Regex sanitization.
5. **Distinctive Components**: Architectural rule forbidding untrusted content from ever driving tool calls directly.
6. **Supporting Evidence**: `tests/audit/codexa_claims/test_claim_security_and_trust_boundary.py`.
7. **Unverified Aspects**: Resistance to novel adversarial linguistic obfuscations.
8. **Classification**: **FUNCTIONAL BUT CONVENTIONAL** (Essential safety baseline).

---

### 15. Host Platform Mutation Guard
1. **The Claim**: Strictly blocks the AI agent from mutating Codexa OS's own source code or reading host credential files.
2. **Actual Implementation**: `backend/agents/tools.py` intercepts all mutating tools if target repository is `codexa-os`, and blocks reads of `.env`, `credentials.json`, and private keys.
3. **Why Differentiated**: Prevents self-modifying agent loops from corrupting the host platform or exfiltrating provider secrets.
4. **Standard Components**: Path and filename inspection.
5. **Distinctive Components**: Programmatic gating integrated directly into the tool dispatcher.
6. **Supporting Evidence**: `tests/audit/codexa_claims/test_claim_security_and_trust_boundary.py`.
7. **Unverified Aspects**: Symlink-based traversal attacks on unusual Linux filesystem configurations.
8. **Classification**: **FUNCTIONAL BUT CONVENTIONAL**.

---

### 16. Phased Project Scaffolding Engine
1. **The Claim**: Decomposes full-stack application development into three sequential, machine-verified phases: Architecture, Core Implementation, and Testing.
2. **Actual Implementation**: `backend/agents/phased_build.py` orchestrates child jobs, validating phase exit criteria before starting the next phase.
3. **Why Differentiated**: Replaces chaotic all-in-one code dumps with disciplined phased software engineering workflows.
4. **Standard Components**: Sequential state machine execution.
5. **Distinctive Components**: Machine verification of phase success criteria before advancing.
6. **Supporting Evidence**: `tests/test_delegate_build.py`.
7. **Unverified Aspects**: Phase rollback if Phase 3 testing reveals fundamental Phase 1 architectural flaws.
8. **Classification**: **FUNCTIONAL BUT CONVENTIONAL**.

---

## 39. Tests and Evidence

Codexa OS maintains a comprehensive test suite of **79 test files** in `/tests`. A dedicated claims audit runner (`tests/audit/codexa_claims/runner.py`) executes 10 master verification suites verifying core claims:

| Suite Name | Target Subsystem | Assertions Verified | Status |
|---|---|---|---|
| `test_claim_graph_and_projections.py` | Graph Schema & Time Machine | Validates node types, confidence bounds, temporal snapshot replay | **100% PASSED** |
| `test_claim_treesitter.py` | Static AST Parser | Validates multi-language symbol extraction, parent scope attribution | **100% PASSED** |
| `test_claim_strata.py` | Route & Intent Mining | Validates Express/FastAPI route extraction, dependency mining | **100% PASSED** |
| `test_claim_quorum.py` | Quorum Debate Engine | Validates belief card verification, debate rounds, ranking | **100% PASSED** |
| `test_claim_planning_and_contracts.py` | Task Contracts | Validates intent detection, required tool checks, rejection logic | **100% PASSED** |
| `test_claim_e2e_and_failures.py` | Claim Verification | Validates claim extraction and AST/tool-return verification | **100% PASSED** |
| `test_claim_simulation_and_sandbox.py` | Simulation & Sandboxing | Validates blast radius, rollback viable, diff & state hash-binding | **100% PASSED** |
| `test_claim_memory.py` | 4-Tier Memory & Conflicts | Validates memory tiers, mathematical conflict formula, soft-deletes | **100% PASSED** |
| `test_claim_resilience_and_recovery.py` | Job Execution & Resilience | Validates model stall rotation, SSE events, atomic checkpointing | **100% PASSED** |
| `test_claim_security_and_trust_boundary.py` | Trust Boundary & Guards | Validates injection stripping, platform mutation block, secret block | **100% PASSED** |

**Empirical Result**: All 10 test suites pass with 0 failures, confirmed by cryptographic evidence files stored in `tests/audit/codexa_claims/evidence/`.

---

## 40. Known Limitations

In the interest of rigorous engineering transparency, the following technical limitations are documented:

1. **Docker Sandbox Execution**: `SandboxExecutionService` currently validates cryptographic hash-binding and synthesizes the exact Docker CLI command array (`docker run --rm --network none --read-only python:3.12-slim`), but does not spawn live container daemons on the host OS.
2. **PostgreSQL vs Neo4j Projections**: While PostgreSQL JSONB is fully operational as the authoritative EKG, read-optimized Neo4j Cypher and Qdrant vector projections operate as specified architectural scaffolding rather than active live synchronization pipelines.
3. **In-Process Threading vs Distributed RQ**: Agent jobs execute on background Python threads within the FastAPI process. Scaling beyond a single physical server instance will require activating the Redis RQ worker pipeline.
4. **Git Clone Depth**: Repositories cloned with `--depth 1` lack sufficient commit history for the git change-coupling miner to generate `CORRELATES_WITH` edges.
5. **Language Parsing Scope**: Production Tree-sitter parsers are active for Python, JavaScript, TypeScript, and TSX. C++, Go, Rust, and Java require registering their grammars in `_LANG_BY_EXT`.

---

## 41. Documentation vs Implementation Discrepancies

A critical objective of this audit is identifying where existing documentation (`docs/codexa_os_build_prompt_v5.md`) differs from the active codebase:

| Documented Claim | Codebase Reality | Discrepancy Analysis |
|---|---|---|
| *"Neo4j is the graph projection"* | PostgreSQL JSONB + In-Memory Graph engine | PostgreSQL handles all graph storage and traversals; Neo4j is deferred to scale. |
| *"Qdrant is the vector projection"* | Keyword + Type-Boosted graph context in `backend/memory/context.py` | Lightweight zero-dependency context retrieval is used instead of Qdrant. |
| *"Redis + RQ handles all scheduling"* | Python `threading.Thread` in `backend/agents/jobs.py` | In-process daemon threads provide single-container simplicity without Redis dependencies. |
| *"Docker sandbox executes all tests"* | Synthesizes Docker CLI array; gates on SHA-256 hash-binding | Host command execution with hash-gated validation precedes container daemon integration. |
| *"Automatic nightly reviews"* | `NightlyArchitectureReviewService` implemented as REST endpoint | Triggered via API call (`POST /understanding/architecture/nightly-review`) rather than system cron. |

---

## 42. Architecture Invariants

The Codexa OS codebase enforces **10 strict architectural invariants**:

1. **Graph Centricity**: Every major subsystem must read from and write to the Knowledge Graph.
2. **Edge Grounding**: Every graph edge must carry a `confidence` score ($0.0–1.0$) and a valid `source_type` (`static_analysis`, `llm_inferred`, `human_asserted`). Static edges must always be $1.0$.
3. **Temporal Immutability**: Historical edges are never physically deleted; they are closed by setting `valid_to`.
4. **Deterministic Fact Superiority**: Mathematical formulas and AST queries always override subjective LLM confidence scores in Quorum, Memory conflict resolution, and Claim verification.
5. **Contractual Tool Execution**: An agent cannot declare a mutating task complete without invoking verified mutating tools.
6. **Platform Self-Preservation**: Agent tools strictly cannot modify the Codexa OS platform repository.
7. **Credential Protection**: Files matching `_SECRET_FILENAMES` cannot be read by agent tools.
8. **Simulation Before Execution**: No code change reaches execution without passing blast-radius simulation.
9. **Cryptographic Hash-Binding**: A sandbox execution is blocked if the code diff or witnessed dependency graph has drifted since simulation.
10. **Prompt Injection Isolation**: External untrusted content cannot directly invoke agent tools.

---
'''

if __name__ == '__main__':
    print(f"Part 7 length: {len(get_part7())} characters, ~{len(get_part7().split())} words")
