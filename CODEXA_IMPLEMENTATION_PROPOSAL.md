# Codexa OS — Implementation Proposal for the Invention Portfolio

*Response to the patent-research report. This document examines each of the ~60 proposed inventions against the actual current codebase (not the abstract spec) and assigns each a disposition: **BUILD NOW** (concrete spec included, ready to implement), **BUILD NEXT** (concrete integration point identified, medium lift), **DEFER** (real value, large lift or depends on something not built yet), **FOLD IN** (already partially exists — extend rather than build new), or **SKIP** (low value in this codebase, or legally risky as an independent claim per the report's own prior-art findings).*

---

## Part 1 — Examination: is the report accurate about this codebase?

Checked against the actual source, not just the earlier inventory document:

- **Confirmed accurate**: the checkpoint/resume architecture (§1), task-contract validation loop (§2), simulate→execute SHA-256 hash binding (§8 — `backend/simulation/engine.py:86` hashes the diff, `backend/execution/sandbox.py:63-65` re-hashes and gates on mismatch), and the graph-attributed audit-trail pattern (§9, every `event_writer.append` call) are all real, all exactly where the report says.
- **One nuance worth flagging**: the report's Part B novelty check on the hash-binding mechanism (item 4) is the correct call — it's the weakest of the five for an independent claim (closely anticipated by OpenPort's State Witness and two USPTO filings on agent-binary hashing). The report already folds it into 5.1/5.3 as a dependent embodiment rather than a standalone claim. Agreed — do not file it alone.
- **A gap the report doesn't call out**: `validate_completion` (`backend/agents/task.py:281`) already implements roughly half of what §2.1 (Claim-Extraction-and-Graph-Verification Gate) proposes — it checks that a *required tool* was called, not that the model's *claims about what happened* are true. The correction-and-retry mechanism it uses (inject a correction message, force another round — `backend/agents/jobs.py:413-419`) is exactly the right scaffold to extend for claim verification. This makes 2.1 cheaper to build than the report estimates, since the retry/correction plumbing already exists — I only need to add claim extraction + resolution, not a new control-flow mechanism.

No corrections needed to the prior-art conclusions (Part B) — they're well-sourced and appropriately hedged.

---

## Part 2 — BUILD NOW: full specs (matches the report's own Stage 2 picks)

### 2.1 — Claim-Extraction-and-Graph-Verification Gate
**Why first**: cheapest, highest-value, and slots directly into an existing extension point.

**New file**: `backend/agents/verification.py`
```python
class ClaimType(str, Enum):
    FILE_EXISTS = "file_exists"
    SYMBOL_EXISTS = "symbol_exists"
    SYMBOL_USED_N_TIMES = "symbol_used_n_times"
    TEST_PASSED = "test_passed"
    ACTION_PERFORMED = "action_performed"

@dataclass
class Claim:
    type: ClaimType
    target: str          # file path, symbol name, or tool name
    assertion: str        # what was claimed (e.g. "created", "3 usages", "passed")

def extract_claims(answer_text: str, llm: LLMClient) -> list[Claim]:
    # one cheap delegate-tier call, JSON-mode prompt: "list checkable factual claims
    # in this answer as {type, target, assertion}". Same parse-with-fallback pattern
    # already used in coder.py's _parse_proposal / research.py's _parse_answer —
    # reuse that exact regex+json.loads+fallback idiom, don't write a new one.
    ...

def verify_claim(claim: Claim, *, graph: GraphService, tool_log: list[dict], repository: str) -> tuple[bool, str]:
    # FILE_EXISTS / SYMBOL_EXISTS / SYMBOL_USED_N_TIMES -> resolve against graph.list_nodes()
    #   (same lookup pattern as _lookup_symbol/_find_references in tools.py)
    # TEST_PASSED / ACTION_PERFORMED -> scan tool_log (the turn's own "tool" role
    #   messages already sitting in jobs.py's `messages` list) for a matching
    #   tool_call_id + non-error result. No new logging needed — the data already exists.
    ...
```

**Hook point** — `backend/agents/jobs.py`, right after line 413's `validate_completion` passes, before the "done" branch at line 436:
```python
if passed:
    claims = extract_claims(content, llm)  # content = msg.content
    failed = [c for c in claims if not verify_claim(c, graph=self._graph, tool_log=messages, repository=working_repo)[0]]
    if failed and _round < 8:
        correction = _build_claim_correction(failed)  # same shape as task.py's correction string
        self._emit(job, {"tool_call": {"name": "_claim_verification", "args": {"status": "failed", "claims": [f.target for f in failed]}}})
        messages.append({"role": "user", "content": correction})
        message_rounds.append(_round)
        self._checkpoint(job)
        continue
```
This is a **direct extension of the existing `if not passed and _round < 8` branch** at jobs.py:414-419 — same control flow, one more failure condition. No new retry/round-budget logic needed.

**Frontend**: emit the failed-claim event as a `tool_call`/`tool_result` pair (already renders in the existing `ToolTrace` component, `chat/page.tsx` — zero new UI code).

**Effort**: ~1 new file (~120 lines), ~15 lines added to jobs.py. No new dependencies.

---

### 2.3 — Test-Result Provenance Binding
**Relationship to 2.1**: this is `TEST_PASSED`/`ACTION_PERFORMED` claim verification made stricter — instead of "did *any* tool call happen," require the claim to bind to a specific tool-return record with an exit code / hash.

**Concrete addition**: `run_command`/`run_tests` results in `tools.py` already return raw stdout+stderr text (`_run_command`, `_run_tests`) but no structured exit code. Small change: have `_run_command`/`_run_tests` return `{"exit_code": int, "output": str, "hash": sha256(output)}` as a structured result (still rendered as text to the model, but the **structured form is what `verify_claim` checks**, not the text). This closes the exact gap the report flags: "unbound completion language is deterministically rejected."

**Effort**: ~20 lines in `tools.py` (`_run_command`, `_run_tests`), reuses 2.1's hook entirely — no separate control flow.

---

### 5.1 — Verifiable Agent Action Framework (receipt chain)
**Scope for a first pass** (not the full framework — the report's broader version, e.g. graph-node witness binding, is 5.3/DEFER below): a hash-chained receipt log for every *mutating* tool call, extending the pattern that already exists for simulation→execution.

**New file**: `backend/agents/receipts.py`
```python
@dataclass
class ActionReceipt:
    action_id: str          # uuid4
    tool: str
    args_hash: str          # sha256(json.dumps(args, sort_keys=True))
    result_hash: str        # sha256(result_text)
    prev_receipt_hash: str  # chain link — hash of the previous receipt in this job
    timestamp: float

def record_receipt(job: "Job", tool: str, args: dict, result: str) -> ActionReceipt:
    prev = job.receipts[-1].result_hash if job.receipts else "genesis"
    receipt = ActionReceipt(
        action_id=str(uuid4()), tool=tool,
        args_hash=hashlib.sha256(json.dumps(args, sort_keys=True).encode()).hexdigest(),
        result_hash=hashlib.sha256(result.encode()).hexdigest(),
        prev_receipt_hash=prev, timestamp=time.time(),
    )
    job.receipts.append(receipt)
    return receipt
```
**Hook point** — `backend/agents/jobs.py:389-398`, the existing tool-execution loop already does `result = execute_tool(...)`. Add one line: `record_receipt(job, name, args, result)` right after. `job.receipts: list[ActionReceipt]` is a new field on the `Job` dataclass, persisted to disk exactly like everything else already is (`to_disk()`/`from_disk()` already serialize the whole job — receipts ride along for free).

**What this buys immediately**: (a) 5.5's idempotency-key gap — on resume, check `job.receipts` for an action with the same `args_hash` under the same tool before re-executing a mutating call during a resumed round, closing a real correctness gap in the *existing* checkpoint/resume system (a resumed round could otherwise redo a write it already did, if the resume boundary lands mid-round rather than between rounds — worth checking whether this can currently happen). (b) a queryable, tamper-evident action log for free, viewable in the Agent Network / Usage dashboards as a new "actions" tab.

**Effort**: ~60 lines new file, ~5 lines in jobs.py, one new `Job` field.

---

## Part 3 — BUILD NEXT: concrete integration points, medium lift

| # | Feature | Integration point | Note |
|---|---|---|---|
| 5.3 | Graph-state witness binding | `backend/agents/impact.py` (blast-radius result) + `backend/simulation/engine.py:86` | Extend the existing diff-hash to also hash the set of graph node IDs the blast-radius traversal touched; re-check at execution that those nodes' `properties` are unchanged. Builds directly on the hash-binding code that already exists. |
| 3.1 | Deterministic memory conflict resolver | `backend/memory/store.py` | Add a `resolve_conflict(existing, new)` pure function keyed on `(created_at, metadata.trust, corroboration_count)` — no LLM call. Needs a `trust`/`corroboration_count` field added to memory records first (small schema change). |
| 1.1 | Graph-anchored context windowing | `backend/memory/context.py` + `backend/agents/impact.py`'s BFS | The BFS traversal already exists (§7); reuse it as the eviction oracle for `_compact_stale_payloads` in `jobs.py` instead of the current fixed 3-round staleness window. |
| 7.1 | Provenance-typed taint tracking | `backend/perception/trust_boundary.py` + `backend/graph/schemas.py` | Requires adding a `provenance` field to `GraphNodeCreate`/context items and threading it through `execute_tool`'s argument construction — real work, but the categories (TRUSTED_USER/INTERNAL_CODE/EXTERNAL_UNTRUSTED) already exist as concepts in `trust_boundary.py`. |
| 6.1 | Graph-mutation consensus | `backend/graph/service.py` `add_node`/`add_edge` | Currently single-writer (only the chat job thread + explicit repo-load calls write the graph) — this feature only matters once multiple agents write concurrently, which isn't true yet (Planner/Coder/Research write independently, not concurrently, in the current design). Correctly flagged by the report as solving a multi-agent coordination problem Codexa doesn't have in its current single-active-job-per-conversation model. |
| 8.2 | Graph-grounded explanation generator | `backend/observability/api.py`'s `_summary()` | Already template-based, not LLM — this is a small extension: forbid any `_summary()` string that isn't built from a graph/event field, which is already true today. Mostly a documentation/audit exercise, not new code. |
| 4.1 | Predictive token-budget allocation | `backend/agents/task.py` `generate_contract` + `backend/agents/llm.py` `UsageTracker` | The usage tracker already has per-agent historical data; `generate_contract` already knows the intent type. Needs a small aggregation query joining the two. |

---

## Part 4 — DEFER (real value, large lift, or needs a prerequisite)

- **9.7 Graph-native semantic diff reindex** — valuable (replaces this session's clear-then-rebuild with incremental AST diffing) but a genuinely large lift (needs a real AST-diff algorithm, not just re-parsing). Do this once repo sizes actually make full-rebuild reindex slow — no evidence yet that they do.
- **6.3 Speculative parallel agent execution** — requires multi-agent concurrent graph writes to exist first (see 6.1 above — not true yet). Ordering dependency, not a rejection.
- **4.4 Speculative draft-then-verify** — depends on 2.1's groundedness scoring existing and being cheap enough to run per-span; build after 2.1 ships and is measured.
- **1.4 Multi-resolution context representation** — real value for very large files, but the codebase's current file-read tools already truncate large content (`_truncate` in `tools.py`); the marginal gain over the existing truncation is unproven without a large-repo stress test.
- **3.7 Sleep-time memory consolidation** — needs a background scheduler that doesn't exist yet (the job system is request-triggered, not cron-triggered). Real feature, needs new infrastructure first.
- **8.5 Time-Machine decision overlay** — frontend-heavy (needs a new synchronized-timeline UI component), backend data already exists (trust decisions are graph-attributed, Time Machine already scrubs the graph by time) — this is mostly a frontend build, not backend.

## Part 5 — SKIP (independent claim risk or low marginal value here)

- **Standalone SHA-256 diff hash as its own claim** — report already correctly folds this into 5.1/5.3; do not file separately (confirmed above).
- **9.6 Cost-of-change economics gating** — `backend/trust_safety/economics.py` is confirmed-stub (hardcoded linear coefficients per the earlier audit); gating real decisions on a stub formula would be actively misleading until that service has real calibration data behind it. Fix the formula's inputs before gating anything on its output.
- **6.4 Delegation capability scoping** — the existing `delegate_task` already restricts the delegate's tool set to a fixed allowlist (`_EXECUTOR_TOOL_NAMES` in `tools.py`) — a static version of this already exists and covers the actual risk (delegate can't do anything the caller couldn't); a dynamic per-call capability token is more machinery than the current single-delegation-depth design needs.

---

## Recommendation

Build **Part 2 in full** now (2.1, 2.3, 5.1) — all three are small, additive, reuse existing control flow, and are exactly what the report's own Stage 2 recommends. That's roughly 200 lines across 2 new files and 3 small edits to existing ones, no new dependencies, no schema migrations.

Part 3 is a reasonable next batch once Part 2 is measured (the report's own gate: check whether groundedness gating actually reduces hallucinated completions before investing further).

Parts 4-5 either need infrastructure Codexa doesn't have yet or would gate real decisions on services that are currently stubs — building them now would be premature.
