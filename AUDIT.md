# Codexa engineering audit

A war-room pass over the whole platform: six adversarial investigations run in parallel against
separate subsystems, consolidated, then implemented. Each investigation was told to break its area
on paper and verify claims by execution, not to review the code.

Findings that are recorded here were **confirmed**, most of them by running the failing path.

Baseline at the start: **728 tests passing.** After this pass: **790**.

---

## Why so many of these are second-order

More than half the defects below are failures introduced by an earlier fix in this same codebase.
That is the useful pattern to take away, not the individual bugs:

| Earlier fix | Failure it introduced |
|---|---|
| Reasoning budget cuts an endless round | Two cuts in a row regenerating the same plan; deadlock |
| Budget counts `reasoning_content` | Deliberation in the *content* channel was invisible; unbounded round |
| Cancel the round on budget exceeded | `source.close()` on a generator raises from another thread; provider never stopped |
| Move the task prompt server-side | The frontend's system message is a *list*; the `isinstance(str)` branch silently did nothing |
| Dedup nudges within the last 3 messages | Assistant/tool pairs push the old one out of the window; four copies stacked |
| Clear the thrash window on task change | Validation attempts now win the race; forcing never fires |
| `try_advance` completes a task when its checks pass | Ran the full validator set — a browser launch — after *every* tool round |

A fix is a new assumption. The next audit should attack it.

---

## CRITICAL

### 1. Repository names could escape the repository store
`backend/files/api.py` — `repo_root()` only checked that the resolved path existed. Repository names
arrive from HTTP bodies and from model-authored tool arguments, so `repository="../.."` resolved to
Codexa's own project root. The mutation guard compared the *string* to `"codexa-os"`, which `"../.."`
is not, so the guard passed and `write_file` / `delete_file` / `apply_patch` operated on Codexa's own
source. `"../../.."` reached the parent directory.

**Why the safeguard missed it:** the guard asked a proxy question (is the name "codexa-os"?) instead
of the real one (does this resolve to the platform?), and `_safe` faithfully confined traversal to a
root that was already wrong.

**Fix:** `repo_root` rejects any name that is not a single path segment and asserts the resolved
parent is the repository store. `is_platform_repo()` answers the guard's real question by resolution.

### 2. Shell tools bypassed the platform-mutation guard entirely
`backend/agents/tools.py` — `_MUTATING_TOOLS` enumerated file-API tools. Everything that reaches the
disk through a shell walked past it: `run_command` executes with `shell=True` and
`cwd=repo_root(repository)`, so on the platform repository it could rewrite Codexa's own source.
`run_python` takes no repository argument at all, so the check could never apply to it however the
set was written — and it runs arbitrary code in a subprocess inheriting the server's environment,
including every provider key.

**Fix:** the guard covers `run_command`, `run_python`, `run_tests`, `typecheck`, `lint`, `build` and
`start_dev_server`, and resolves the repository rather than comparing its name.

### 3. `read_file(".env")` returned every provider key
Reads are deliberately open on the platform repository. `.env` sits at its root, so `_safe` correctly
allowed it and nothing filtered it. The contents entered the conversation history, the job event log
streamed to the browser, and the checkpoint JSON on disk, where they persist after the job ends.

**Fix:** a credential-filename denylist refuses the read outright. Redacting was rejected — a partial
secret in a transcript is still a secret in a transcript.

### 4. Cancellation never reached the provider
`backend/agents/jobs.py` — the consumer called `source.close()`, but `source` is a generator and the
producer thread is inside it. Python raises `ValueError: generator already executing`, which a
best-effort `except Exception` swallowed. Every cut left the producer blocked on a live HTTP response
with the provider still generating and billing. **Orphaned generation was the normal case, not an
edge case.**

**Fix:** `CancellableStream` in `llm.py` holds the live litellm wrapper — which changes on key
failover — and closes *that*, safely from any thread. Verified: provider closed, zero chunks after
close, zero threads leaked.

### 5. A build request could be structurally unable to build
`classify_intent` and `generate_contract` derive from the same text with different regexes and
disagreed. `"build an html game of snake"` matched `runtime` but not `code` — the `code` alternative
is `build.?a\b`, which `"build an"` fails — so `write_file`, `edit_file`, `create_files` and
`delegate_build` were absent for the whole job, while the contract still demanded `write_file`. The
model was told to call a tool it had never been offered.

**Fix (structural):** the invariant is that a job's tools must be a superset of its contract's
requirements. `groups_providing()` derives the needed groups from the requirement; keyword
classification still offers useful extras but no longer decides whether the job is *possible*.

---

## HIGH

### 6. Design guidance stopped reaching the model — again
The task prompt was moved server-side precisely so it could not depend on the caller. But the
frontend's system message is not a string: it is wrapped as
`[{"type": "text", "text": …, "cache_control": …}]` for prefix caching, and the injection checked
`isinstance(existing, str)`. It matched neither branch and did nothing. Verified on a live job:
`TASK MODE` present (added by the HTTP layer, which handles the list), `DESIGN INTENT` absent.

**Fix:** `_attach_preamble` handles string, list and unknown shapes, appends into the cached block,
and is idempotent. An unrecognised shape now inserts rather than silently dropping.

### 7. The design-completion gate was dead code
`design_evidence` was fully plumbed — `_Ctx.design`, the controller's `design=` argument — and
referenced by nothing outside its registry and two unit tests, because `plan_builder` overwrites
every task's validators with `infer_validators`, which never returned it.

**Fix:** inferred for any task expecting a renderable artifact. It no-ops when the task carries no
design intent, so it cannot invent an opinion about work nobody asked to be designed.

### 8. Recovery directives stacked
The rule was "do not append if an identical one is among the last three messages", which fails as
soon as assistant/tool pairs push the earlier copy out of that window. Measured on a live job: **four
copies of one 2,227-character directive**, ~9KB re-sent on every later request — the pattern this
codebase already documents as having preceded two providers going permanently silent.

**Fix:** `_replace_directive` keeps exactly one, at the end, where it applies.

### 9. A cancelled round still executed its tool calls
`job.cancelled` was checked between chunks and at the top of the round, and nowhere in between — so a
cancel landing mid-stream fell through to the tool executor and ran every `write_file`,
`delete_file` and `run_command` in the partial message. If the break truncated before any tool call
arrived, the round read as a *completion claim* and could mark the active task COMPLETED.

### 10. `try_advance` launched a browser after every tool round
The task-advancement check I added ran the full validator set, which includes `renders_cleanly`
(launches Chromium, loads, scrolls, waits) and `no_build_errors` (`npx tsc`, up to 30s). A twelve-round
task paid twelve browser launches, mostly against a half-written file — and a render that
legitimately failed mid-build could fail the check on work still in progress.

**Fix:** expensive validators are excluded from the speculative poll and settled only where a
completion is actually claimed.

### 11. Per-round reasoning was charged twice
`round_reasoning_chars` was initialised once at `_loop` scope, so a round emitting no reasoning (a
pure `write_file` round) left the previous round's value in place and charged it again. Three such
rounds crossed the per-task ceiling and triggered a spurious intervention on a task writing files
perfectly.

### 12. A FAILED task could be resurrected to COMPLETED
`active_task` is captured at the top of the round. An intervention during that round can fail it and
insert a recovery task; treating the round as a completion claim then marked the FAILED task
COMPLETED, leaving the plan showing it both done and awaiting recovery.

### 13. The plan snapshot was only emitted when the plan was first built
The emit sat inside `if plan is None:`. A resumed job, an auto-continue or a Continue click never
re-sent it — and `continue_job` clears `job.events`, so a client replaying from index 0 saw no plan
at all. **This is the "task card doesn't show up" report.**

### 14. The controller froze its repository at loop entry
After a mid-job repository switch, every snapshot, progress comparison and validator inspected the
abandoned repository: perpetual "no progress", interventions and task failures while real files were
being written elsewhere.

### 15. Malformed tool arguments killed a job permanently
A model can emit arguments that are valid JSON but not an object. `json.loads` succeeds, then
`.get()` raises `AttributeError` out of compaction — which runs outside any try in the round loop —
killing the job with `error_reason=None`, so it was neither auto-continued nor eligible for Continue.
The bad message stayed in history, so every resume re-crashed on it.

### 16. `delegate_build` did not satisfy the job contract
`validators.py` allowed both delegating tools; `task.py` allowed only `delegate_task`. A job that
built everything through `delegate_build` — the path the tool description recommends — was told "you
must call write_file" with the files already on disk. The divergence was documented in a comment and
not closed.

### 17. Codexa's own artefacts forged progress
`screenshot` writes `.codexa-screenshot.png` into the repository root, and the snapshot skipped
dot-*directories* only. Every screenshot round therefore reported real disk progress with nothing
built — and `is_thrashing`, whose docstring names the screenshot loop as the exact escape it exists
to catch, could never fire, because the screenshot tool supplied the disk change the check looked for.

### 18. "not X but Y" lost the Y
The negation stripper consumed 80 characters after any negation word and stopped only at a full stop.
`"Build not a landing page but a luxurious editorial archive"` reduced to `"Build"`, so a classical
archive classified as generic contemporary with the wrong skills. The construction it broke on is the
commonest way a brief states what it wants.

### 19. Completion attempts beat forcing, so forcing never fired
A no-tool round increments both the validation attempts and the no-progress streak; with both budgets
at 3, attempts always won — the task reached FAILED at round 2 while the streak was still 2.

**Fix:** a rejected completion claim now forces the outstanding tool itself. A model that has just
declared itself finished has demonstrated it will not reach for the tool on its own.

### 20. The test suite wrote to the developer's real state
`conftest` redirected job checkpoints only. A full run appended rows to the real `.codexa/usage.jsonl`
(2,835 accumulated) and wrote into `backend/data/phased_builds/` (330 files). One test's assertion
depended on it: a "records nothing" check compared `len(records())` before and after, but `records()`
returns the last 200 rows of a ledger with thousands, so both sides were 200 and **the test could not
fail**.

---

## Known-remaining, not yet fixed

Recorded rather than hidden. Ranked by what I would do next.

- **`run_round` silently re-runs a whole round.** `emitted` is set only by thinking/delta yields, so
  a pure tool-call round never sets it — a wall-clock cut on a large `write_file` re-streams the
  entire round at full cost instead of entering recovery, unlogged.
- **Cut and stalled rounds record zero usage.** The budget raise happens before `record_usage`, so
  the most expensive rounds contribute nothing to token accounting — the bulk of the known undercount.
- **Streamed usage is a local estimate.** `stream_options={"include_usage": True}` is never passed, so
  for the default provider litellm synthesizes usage; a 400KB base64 screenshot counts as 93 tokens.
- **Reasoning tokens excluded from every total**, including the context gauge.
- **`continue_job` TOCTOU** — the continuable check and the `status = "running"` write are both
  outside the lock, so two Continue clicks can drive one job on two threads.
- **SSE closes on a transient error the loop is about to auto-continue**, orphaning a live job in the
  UI with no terminal event.
- **`_delegate_task` can report success having written nothing** (`_delegate_build` has the guard it
  lacks).
- **`_typecheck` / `_lint` / `_apply_patch`** have unreachable branches (`if (root / "x")` is always
  truthy) and `_apply_patch`'s hunk split never matches its own documented format.
- **`page.goto` accepts any scheme**, including `file://` — local files can be rendered into the
  vision context.
- **Shell argument injection** in `git_diff(files=…)`, `run_tests(scope=…)`, `typecheck`, `lint`,
  `build` — f-string interpolation under `shell=True`.
- **Memory store writes non-atomically** and treats a parse failure as "empty", so a torn write
  silently discards all memory.
- **`list_directory` / `tree` skip `_safe()`**.
- **No authentication on any endpoint**; job checkpoints accumulate unbounded (90 files, 6.4MB).
