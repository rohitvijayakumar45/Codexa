"""Part 4: Sections 25 through 35 of Codexa Complete Documentation."""

def get_part4() -> str:
    return r'''## 25. Planning System

Codexa OS implements a hierarchical planning architecture divided into goal decomposition, contract formulation, and multi-phase execution.

### 25.1 The Planning Lifecycle
When a complex goal is received:
1. `PlannerService` (`backend/agents/planner.py`) analyzes the goal and decomposes it into ordered subtasks.
2. For each subtask, the planner identifies required tool groups, expected file artifacts, and dependencies.
3. The planner calls `compute_blast_radius()` to identify which existing graph nodes will be impacted by the changes.
4. An `ExecutionPlan` is generated containing typed tasks, each governed by its own lifecycle state machine.

### 25.2 Task State Machine
Each task within a plan progresses through explicit states:
$$\\text{PENDING} \\longrightarrow \\text{IN\\_PROGRESS} \\longrightarrow \\text{VALIDATING} \\longrightarrow \\begin{cases} \\text{COMPLETED} \\\\ \\text{FAILED} \\longrightarrow \\text{RECOVERING} \\longrightarrow \\text{IN\\_PROGRESS} \\end{cases}$$

- `PENDING`: Task queued, waiting for dependencies to satisfy.
- `IN_PROGRESS`: Agent actively executing tool calls.
- `VALIDATING`: Code generated; validation gates running tests and checking claims.
- `COMPLETED`: All artifacts exist, tests pass, and claims are verified.
- `FAILED`: Validation failed or tool error occurred.
- `RECOVERING`: Error injected into agent prompt; agent performing corrective round.

### 25.3 Phased Builds (`PhasedBuildManager`)
For large scaffolding tasks (such as building an entire full-stack application from scratch), Codexa invokes `PhasedBuildManager` (`backend/agents/phased_build.py`). It divides work into 3 distinct phases:
- **Phase 1: Architecture & Scaffolding**: Directory layout, package manifests, and configuration files.
- **Phase 2: Core Implementation**: Business logic, API routes, and database models.
- **Phase 3: Integration & Tests**: Test suites, end-to-end verification, and documentation.
A phase cannot begin until the preceding phase has achieved machine-verified completion.

---

## 26. Task Execution System

The autonomous execution loop is implemented in `backend/agents/jobs.py` (`JobManager`).

### 26.1 Job Dataclass and State Tracking
The `Job` dataclass tracks the complete state of an execution session:
- `id`: Unique UUID identifying the job.
- `repository`: Name of the target repository.
- `model`: Currently active LLM identifier.
- `messages`: Conversation history containing system prompts, user turns, and tool calls.
- `round`: Current execution round counter (bounded by `round_budget`, default 15).
- `tools_called`: Complete log of tool invocations across all rounds.
- `tool_exit_codes`: Itemized status return codes from each tool.
- `active_tool_groups`: Currently active subsets of the 55 available tools.
- `contract`: The governing `TaskContract`.
- `current_wait_state`: Live status indicator (`"calling_llm"`, `"executing_tool"`, `"validating"`).
- `last_activity_ts`: High-precision timestamp of the last state change.
- `same_tool_signature_streak`: Detector for infinite tool-calling loops.

### 26.2 Action Receipts (`backend/agents/receipts.py`)
To prove that tools actually executed on disk rather than merely being narrated by an LLM, every tool execution produces an `ActionReceipt`:
```python
class ActionReceipt(BaseModel):
    receipt_id: UUID
    tool_name: str
    arguments_hash: str
    exit_code: int
    output_summary: str
    timestamp: datetime
```
Action receipts are appended to the job record and persisted in the checkpoint on disk.

---

## 27. Context Management

Context management in Codexa OS prevents context saturation, token budget exhaustion, and model degradation over extended execution sessions.

### 27.1 Payload Compaction (`_compact_stale_payloads`)
As an agent executes multiple rounds, historical tool calls (such as large file reads or multi-hundred-line file writes) remain in the conversation history. If left unmanaged, the history quickly exhausts the model's context window.

After a round completes, `_compact_stale_payloads` scans past turns:
1. Arguments to mutating tools (`write_file`, `create_files`) executed more than 2 rounds ago are truncated and replaced with a placeholder:
   `[compacted — 12,450 chars written to disk]`
2. Tool outputs exceeding 800 characters are summarized.
3. This reduces historical token overhead by up to $75\%$ while preserving the record that the action occurred.

### 27.2 Graph-Anchored Neighborhood Context
Instead of dumping an entire repository's files into the prompt, `backend/memory/context.py` resolves the user's prompt to specific graph nodes:
- Targets `File` and `CodeSymbol` nodes matching words in the prompt.
- Retrieves up to 5 target symbols.
- Expands up to 4 immediate neighbors along `calls`, `imports`, and `depends_on` edges.
- Formats the resulting bounded subgraph into a concise context block ($\le 800$ characters per symbol).

---

## 28. Validation System

Codexa OS enforces strict separation between an agent claiming it completed a task and the system verifying completion.

$$\text{Agent Claims "Done"} \quad \neq \quad \text{Codexa Verifies "Done"}$$

### 28.1 The Two Validation Gates
Every completing turn must pass through two independent validation gates:

```mermaid
flowchart TD
    Model[Model Emits Final Text Response] --> Gate1{Gate 1: Contract Validation}
    Gate1 -->|Required Tools NOT Called| Reject1[Reject: Inject Correction Message]
    Gate1 -->|Required Tools Called| Gate2{Gate 2: Claim Verification}
    Reject1 --> NextRound[Next Agent Round]
    
    Gate2 --> Extract[extract_claims: Pull Factual Assertions]
    Extract --> Verify[verify_claims: Check Files, AST, & Tool Returns]
    Verify -->|Unverified Claims Found| Reject2[Reject: Inject Unverified Facts Warning]
    Reject2 --> NextRound
    Verify -->|All Claims Verified| Pass[Approve & Complete Task]
```

1. **Gate 1: Task Contract Completion Validation (`validate_completion`)**:
   - Compares the `TaskContract.required_tools` against `job.tools_called`.
   - If the intent was `CREATE_ARTIFACT` or `MODIFY_ARTIFACT` and the agent called zero mutating tools (`write_file`, `edit_file`, `delegate_task`), completion is rejected immediately.
   - Rejection injects an authoritative correction message:
     ```
     You described completing the task, but no file was written or modified.
     You MUST call write_file or edit_file to apply the changes to disk.
     ```
2. **Gate 2: Graph-Grounded Claim Verification (`verify_claims`)**:
   - `extract_claims()` extracts up to 8 checkable factual claims from the draft text.
   - For `file_exists`: Checks `os.path.exists()` on disk.
   - For `symbol_exists`: Queries Tree-sitter AST to verify function/class definition.
   - For `test_passed`: Checks tool exit codes from `run_tests`.
   - For `action_performed`: Verifies tool was present in the turn's execution receipts.
   - If any claim fails, the turn is rejected with explicit feedback detailing which claim could not be verified.

---

## 29. Recovery System

Autonomous software development inevitably encounters transient errors, API rate limits, model hallucinations, and process crashes. Codexa OS incorporates automated recovery mechanisms at every layer.

### 29.1 Model Stall Rotation (`_rotate_away_from_stalled_model`)
If a model provider stalls (produces zero tokens for 45 seconds, returns empty responses, or throws consecutive HTTP 503 errors):
1. `JobManager` captures the stall event.
2. Increments `job.stall_recoveries`.
3. Calls `_rotate_away_from_stalled_model()`, selecting the next candidate in `_FAILOVER_RING`.
4. Resumes the job seamlessly on the new model without losing round history.

### 29.2 Crash Recovery via Disk Checkpoints
Every time an agent executes a tool or receives an observation, `JobManager._checkpoint()` serializes the full `Job` dataclass to disk at:
`backend/data/jobs/{job_id}.json`

If the Codexa server is abruptly terminated (SIGKILL, power failure, OS reboot):
1. On boot, `JobManager.load_interrupted_ids()` scans `backend/data/jobs/`.
2. Identifies any jobs where `status == "running"`.
3. Restores the exact conversation state, tool offsets, and receipts.
4. Resumes execution from the exact incomplete round.

---

## 30. Cancellation and Timeouts

To prevent runaway inference bills or hanging processes, Codexa implements deterministic timeouts and cancel endpoints.

### 30.1 Cancellation Endpoints
- `POST /chat/agent/job/{job_id}/cancel`: Sets `job.cancelled = True`.
- `POST /chat/agent/phased/{build_id}/cancel`: Cancels an entire multi-phase build.
The active background thread checks `job.cancelled` between streaming chunks and tool calls, gracefully terminating the loop, closing open file handles, and emitting a final `status: "cancelled"` SSE event.

### 30.2 Subprocess Timeouts
All tool commands executed on the host system are strictly bounded:
- `run_python`: **10-second** timeout.
- `run_command` (shell): **30-second** timeout.
- `run_tests`: **60-second** timeout.
- `SandboxExecutionService` (Docker sandbox): **300-second** timeout.
If a command exceeds its timeout, the subprocess is sent `SIGKILL` and a structured error is returned to the agent.

---

## 31. Concurrency / Hang Handling

Codexa OS is designed for thread-safe concurrent execution:
- **`MemoryStore._lock`**: Protects `.codexa/memories.json` reads and writes, ensuring concurrent repo loads do not corrupt memory records.
- **`JobManager._lock`**: Coordinates job creation, state transitions, and checkpointing across concurrent user sessions.
- **ThreadPoolExecutor in Quorum**: Panel models are queried concurrently using Python's `concurrent.futures.ThreadPoolExecutor(max_workers=4)`. If one provider is slow, timeouts prevent the overall debate from hanging.
- **Tool Signature Streak Counter (`same_tool_signature_streak`)**: If an agent calls the exact same tool with identical arguments 3 times in a row without making progress, the loop breaks the cycle by injecting an intervention prompt.

---

## 32. Security

Allowing autonomous agents to generate and execute code presents serious security risks. Codexa OS neutralizes these through defense-in-depth isolation.

### 32.1 Content Isolation & Prompt Injection Defense (`TrustBoundaryService`)
All external artifacts (GitHub issues, bug reports, user-supplied URLs, scraped documentation) are assigned a `TrustLevel`:
- `repo_owner`: Trusted.
- `verified_contributor`: Semi-trusted.
- `external_untrusted`: Untrusted.
- `public_scraped`: Untrusted.

For untrusted content, `TrustBoundaryService` (`backend/perception/trust_boundary.py`) applies regular expression filters against known injection patterns:
- `prompt_override`: Catches phrases like *"ignore previous instructions"*, *"forget system prompt"*.
- `tool_invocation`: Catches instructions commanding terminal execution.
- `secret_exfiltration`: Catches instructions directing the model to print API keys or `.env` files.
- `destructive_instruction`: Catches commands ordering file or database deletion.
Matching lines are replaced with `[stripped external instruction]`, guaranteeing that untrusted text cannot hijack tool calling.

### 32.2 Path Traversal and Platform Protection
1. **Path Normalization**: All file paths supplied to tools are resolved via `pathlib.Path` against the repository root. Any path resolving outside the root (`../../etc/passwd`) raises `ValueError: Access denied: path outside repository`.
2. **Platform Mutation Guard**: Protects the Codexa OS codebase itself from agent modification.
3. **Secret File Reading Block**: Protects API keys and certificates from leaking into conversation histories.

---

## 33. Persistence Model

Codexa OS utilizes a hybrid persistence architecture combining relational databases, flat-file JSON stores, and git repositories:

| Store | Location | Purpose | Consistency Model |
|---|---|---|---|
| **PostgreSQL** | Docker / Host DB | Authoritative Knowledge Graph, event log, artifacts | ACID Transactions |
| **In-Memory Graph** | Python process heap | Fast local development and test graph | Ephemeral |
| **MemoryStore** | `.codexa/memories.json` | 4-tier project memory (Semantic, Episodic, Procedural, Org) | Thread-locked Atomic File |
| **Job Checkpoints** | `backend/data/jobs/*.json` | Resumable agent session states and receipts | Atomic Replace with Retry |
| **Phased Builds** | `backend/data/phased_builds/*.json` | Multi-phase build progress and phase results | Atomic Replace with Retry |
| **Cloned Repositories** | `.codexa/repos/{name}/` | Physical working trees for analyzed codebases | Git Working Tree |

---

## 34. Design Intelligence

Codexa OS includes dedicated design intelligence in `backend/agents/design_intent.py` and `backend/agents/design_skills/` to prevent AI-generated interfaces from looking generic, template-driven, or amateurish.

### 34.1 The 10 Design Skill Guides
The platform embeds 10 specialized design knowledge guides that agents load via `get_design_guidance`:
1. `anti_slop.md`: Rules against generic gradients, floating cards, and unstyled templates.
2. `apple_design.md`: Apple design principles, typography tracking, and translucent materials.
3. `emil_design_eng.md`: Emil Kowalski's interaction design and micro-animation philosophy.
4. `high_end_agency.md`: Editorial spacing, typographic contrast, and luxury agency aesthetics.
5. `minimalist_editorial.md`: Swiss print aesthetics, monochrome palettes, and flat bento grids.
6. `industrial_brutalist.md`: Mechanical interfaces, terminal layouts, and utilitarian data displays.
7. `animate.md`: Motion choreography, spring vs timing curves, and exit animations.
8. `animation_vocabulary.md`: Glossary of interaction patterns (pop-in, rubber-banding, layout morph).
9. `web_design_guidelines.md`: Comprehensive accessibility (WCAG), performance, and form ergonomics.
10. `shadcn_ui.md`: Tailwind CSS component compositions.

When a user brief requests UI development, `derive_design()` extracts visual intent, selects an appropriate style guide, and injects precise design constraints into the agent's prompt.

---

## 35. Analytics / Observability

Codexa OS tracks end-to-end telemetry across all agent actions in `backend/agents/usage.py` (`UsageTracker`).

### 35.1 Token & Cost Telemetry
The `UsageTracker` records every model invocation:
- `prompt_tokens`: Input tokens billed.
- `completion_tokens`: Output content tokens billed.
- `reasoning_tokens`: Thinking tokens generated.
- `latency_ms`: Duration of the inference call.
- `cost_estimate`: Estimated USD cost based on provider rate tables.

### 35.2 Live Observability Endpoints
- `GET /observability/usage`: Global token consumption and cost breakdown.
- `GET /observability/usage/daily`: Daily usage aggregates.
- `GET /observability/events`: Live feed of graph events and agent mutations.
- `GET /observability/agents`: Status of active background workers.

---
'''

if __name__ == '__main__':
    print(f"Part 4 length: {len(get_part4())} characters, ~{len(get_part4().split())} words")
