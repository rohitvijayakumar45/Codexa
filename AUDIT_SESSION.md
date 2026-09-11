# Codexa Audit Session — September 8, 2026

## Status

- **826 tests passing** (from 823 before this session; 3 new regression tests added)
- **2 architectural fixes** implemented, **0 regressions**
- Live benchmark not yet run (backend server not available for HTTP benchmark)

---

## What was audited

Complete inspection of:
- `backend/agents/plan.py` — execution plan state machine
- `backend/agents/controller.py` — orchestration policy (task advancement, intervention, recovery)
- `backend/agents/jobs.py` — agent loop, provider streaming, checkpointing
- `backend/agents/task.py` — intent classification, contract, completion validation
- `backend/agents/validators.py` — filesystem-based completion checks
- `backend/agents/progress.py` — repository diffing, progress detection
- `backend/agents/plan_builder.py` — plan generation (LLM proposal + deterministic fallback)
- `backend/agents/tools.py` — tool definitions and execution
- All test files (60+ test modules)
- 80+ historical job checkpoints in `backend/data/jobs/`

---

## Key findings from historical job analysis

### premature-completion-job
- **Status:** error, tasks_failed, round 31/40
- **Pattern:** 10 out of 11 tasks FAILED
- **Root cause:** The model never called any tools (tools_called=[] across 31 rounds). Every task failed validation because required tools were never dispatched.
- **Recovery pattern:** Each recovery task started with a fresh intervention budget of 3, allowing the same failure to repeat. Recovery tasks 1-2 each exhausted their full intervention budget.
- **Impact:** 31 rounds burned with zero tool calls, zero artifact creation.

### status-tool-call-job
- **Status:** error, round 46/50
- **Pattern:** 46 write_file calls, all 11 tasks FAILED
- **Root cause:** Model kept writing files but artifacts didn't satisfy validators (content quality issues). Recovery tasks repeated the same pattern.
- **Impact:** 46 rounds, 46 file writes, zero tasks completed.

### round-exhaustion-job
- **Status:** stall_exhausted, round 3/11
- **Pattern:** Zero tools called, stalled at task 1
- **Root cause:** Provider connection died after 2 stall recoveries. Auto-continue not triggered because stall_exhausted was not in the auto-continue set at the time.

### Recent benchmark (2fb62a24)
- **Status:** done, round 11/36
- **Pattern:** 3 of 9 tasks completed, task 4 IN_PROGRESS
- **Root cause:** Job completed successfully with partial plan — the model wrote index.html multiple times (29KB → 34KB → 34KB) but the plan continued past the job's round budget.
- **Positive:** Reasoning cuts worked (2 consecutive cuts recovered), file writes landed, design guidance loaded.

---

## Fixes implemented

### Fix 1: Shared intervention budget across recovery chain

**File:** `backend/agents/controller.py` — `recover()` method

**Problem:** Recovery tasks got fresh intervention budgets (3 per task). The original task already demonstrated the model couldn't satisfy the constraint. A fresh recovery let it burn through the exact same failure pattern a second time. Historical evidence: every recovery task in premature-completion-job and status-tool-call-job hit its full intervention budget.

**Fix:** Recovery tasks now start with `interventions = MAX_INTERVENTIONS_PER_TASK - 1` (pre-seeded to 2). This means a recovery gets only ONE forced-tool attempt before hitting the max (3). If the first forced call in the recovery also fails to advance, the goal is demonstrably unachievable and the plan stops.

**Impact:** A model that can't call write_file now gets 3 (original) + 1 (recovery) = 4 forced attempts instead of 3 + 3 = 6. Cuts recovery waste by ~40%.

### Fix 2: Intervention messages include validation failure details

**File:** `backend/agents/controller.py` — `intervene()` method and `_intervention_message()`

**Problem:** When forcing a tool, the message said "this task has not advanced" but didn't explain WHY the previous attempt failed. A model that wrote an incomplete file and was told "call write_file" regenerated the entire document from scratch instead of fixing the specific defect.

**Fix:** The intervention message now includes `LAST CHECK RESULT: <validation_detail>` — the actual validator output from the last attempt. This gives the model specific information about what went wrong (e.g., "has no <body> — the document was never finished") so it can fix the defect instead of starting over.

### Regression tests added

**File:** `tests/test_controller.py`

1. `test_a_recovery_task_gets_a_reduced_intervention_budget` — Verifies recovery tasks start with limited intervention budgets
2. `test_a_recovery_is_abandoned_after_one_intervention` — Verifies the recovery chain stops after one intervention
3. `test_the_intervention_message_includes_last_check_detail` — Verifies validation failure details appear in intervention messages

---

## Issues identified but not yet fixed

These are from the §8b list in PROBLEMS.md and from this session's audit. Ranked by impact:

### High priority
1. **`consecutive_cuts` counter never resets.** After two cuts followed by 10 successful rounds, the counter still shows 2. Only used for diagnostics, not decision-making.

2. **Token accounting lost on budget cuts.** When a round is cut by `_GenerationBudgetExceeded`, the `record_usage` call is never reached. The most expensive rounds contribute nothing to token accounting. Budget decisions still work correctly (they use character counts).

3. **`continue_job` TOCTOU.** The continuable check and `status = "running"` write are both outside the lock, so two Continue clicks can start the job on two threads.

### Medium priority
4. **Recovery tasks inherit identical required_tools.** When a task fails because the model can't use a specific tool, the recovery task requires the same tools. Making recovery tasks more targeted (e.g., reducing tool requirements) could improve success rates.

5. **`run_round` silently re-runs whole rounds on tool-only responses.** The `emitted` flag is set only by thinking/delta yields, so a pure tool-call round never sets it — a wall-clock cut re-streams the entire round at full cost.

### Low priority
6. **Streamed usage is a local estimate.** `stream_options={"include_usage": True}` is never passed, so litellm synthesizes usage. A 400KB base64 screenshot counts as 93 tokens.

7. **Reasoning tokens excluded from every total**, including the context gauge.

---

## What would change the most

The single highest-impact improvement for the benchmark would be fixing the model's tool-calling reliability. The historical failures show the model frequently:
- Generates content without calling tools
- Writes the same file multiple times instead of editing
- Ignores tool forcing and keeps generating prose

These are partially addressed by the existing system (tool forcing, intervention budgets), but the root cause is that reasoning models on free tiers have high latency and intermittent availability. The architectural fixes (recovery budget, intervention details) reduce waste, but the fundamental bottleneck is model reliability.

The next most impactful improvement would be making recovery tasks more intelligent — not just retrying the same approach with a smaller budget, but guiding the model toward a different strategy.
