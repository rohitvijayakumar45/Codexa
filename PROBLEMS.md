# Codexa — every problem encountered, in order

Written for an outside reviewer. It records what broke, the evidence, what was changed, and whether
the change worked. Where a fix caused a new failure that is stated plainly, because that is the
dominant pattern in this log and probably the most useful thing in it.

Nothing here is inferred. Every measurement came from a real run — job checkpoints in
`backend/data/jobs/`, server logs, or files on disk.

**Status at time of writing:** 823 tests passing (from 728 at the start). Branch
`feat/task-driven-execution`. One benchmark still running and not yet successful — see §8.

---

## 0. What the system is

Codexa runs an LLM in a tool-calling loop against a user repository. A job streams a model round,
executes any tool calls, checkpoints to disk, and repeats. The benchmark used throughout is
"produce a single self-contained HTML page to a high design standard", because it exercises
planning, authoring, browser validation and refinement in one task.

Default model is `tokenrouter/z-ai/glm-5.3-free` — a **reasoning model on a free tier**. Two of its
properties matter for almost everything below: it emits a large volume of reasoning before acting,
and it is slow and intermittently unavailable.

---

## 1. The original problem: indefinite reasoning

**Symptom.** A build sat in a single round for **48 minutes**, emitted **39,655 reasoning tokens**,
and wrote zero files. One call spent 30,478 reasoning tokens to produce 131 tokens of output.
Reading the trace, the model had designed three complete, different products and discarded two.

**Why nothing caught it.** Every guard in the loop acted *between* rounds:

| Guard | Why it could not fire |
|---|---|
| 90s stall watchdog | Resets on every chunk; a model that keeps emitting never trips it |
| Round budget | Counts rounds; one endless round reads as "round 0, healthy" |
| Completion validation | Only runs after a round returns |

A round could burn unlimited wall-clock and context invisibly.

**What was tried, in order:**

1. **Prompt commitment clause** — "commit in three sentences, don't revisit". *Partially worked*:
   killed the three-product divergence, did not reduce volume (still 38,567 chars in round 0).
2. **Reasoning budget** (cut the round at 40,000 chars) — *worked*, converted an invisible hang into
   a bounded recoverable event.
3. **Text nudge after the cut** — *failed, measured*: the next round spent another **23,692
   characters** planning and called nothing.
4. **`tool_choice: "required"`** — *gamed*: the model satisfied it with `screenshot` against a URL
   serving nothing (ERR_CONNECTION_REFUSED) and `list_directory` on an empty repo, then resumed
   planning.
5. **Naming the specific tool** — better, but see §3.

**Lesson.** Prompting does not constrain. Only the lifecycle does.

---

## 2. Silent success

**Symptom.** A job reported `done` at round 6 having written nothing.

**Root cause.** Intent classification ranked by earliest match position. A prompt titled
`# ATLAS — Single-HTML Frontend Benchmark` matched "Benchmark" (an ANALYZE verb) at position 31,
beating "Build an…" at position 42. ANALYZE requires no tools, so nothing obliged the model to write
anything and its narrative reply was accepted.

**Fix.** Rank by `(starts a line, then position)` — a heading noun must not outrank the imperative
beneath it.

**Then a deeper fix:** an execution plan (`plan.py`), one active task at a time, and the rule that
**Codexa decides completion from the filesystem, never from the model's claim**.

---

## 3. The task system, and what it broke

The plan closed the original problem but introduced a series of its own.

**3a. Failed task deadlocked the whole plan.** `is_ready` required dependencies to be COMPLETED.
Generated plans are linear chains, so one task failing three times blocked all seven behind it — and
those tasks were independently attemptable. **Fix:** dependencies express *order*, so a TERMINAL
dependency (completed or failed) unblocks. Failure no longer cascades.

**3b. `Recover: Recover: Recover:` chains** burned the whole revision budget re-attempting something
already shown impossible. **Fix:** recovery does not recurse.

**3c. Interventions and validation attempts shared one counter**, so three slow-but-legitimate rounds
exhausted the validation budget of a task that had never claimed to be done. **Fix:** separate
budgets — they are different failures needing different responses.

**3d. A task could only complete when the model STOPPED calling tools.** `on_completion_claim` ran
only on a round with no tool calls. A task whose check had already passed stayed active, and a model
with no useful action left does not fall silent — it invents one:

```
task 1 "Inspect the repository"  held 16 rounds
9 × list_directory (45% of all tool calls), a screenshot of a repo with no page,
1 intervention — all of it manufactured after the task was already satisfiable
```

**Fix:** `try_advance` — a task ends when its checks pass, whether or not the model noticed.

---

## 4. Task-boundary leakage (the subtlest)

**Symptom.** The model called `commit_direction`, received success, wrote in its own reasoning that
writing the page *"is task 3"* — and then designed task 3's CSS architecture, JavaScript
architecture, fourteen archive records, timeline behaviour, FLIP implementation and mobile layout
anyway. Roughly **18,000 characters** of it.

**Root cause, traced not inferred.** `try_advance` refuses to complete a task with **no validators**
(deliberately — "nothing to verify" must not mean "complete instantly"). But the generated plan
contained a task with no required tools and therefore no validators: *"Commit to one direction"*. It
could only complete via a no-tool-call round.

**So the model was structurally required to keep generating prose in order to end the task**, and it
filled that prose with future work. Measured on the same plan:

| Task | Criterion | Rounds | Reasoning chars |
|---|---|---|---|
| Inspect repository | `tools_called` | 1 | **69** |
| Commit to one direction | none | 2 | **2,002 / 5,806** |

**Fix.** Commit tasks require `commit_direction`, so recording the decision *is* the criterion.
Also: task context now separates CURRENT from LATER — later tasks are named without their tools or
artifacts. A model given the whole plan solves the whole plan.

**Result:** the same task now completes in 1 round with **0 reasoning characters**.

---

## 5. Second-order failures — fixes that caused new bugs

This is the pattern worth a second opinion. Over half the defects found were introduced by an
earlier fix in the same codebase.

| Fix | Failure it introduced | Detected by |
|---|---|---|
| Reasoning budget cuts an endless round | Two cuts in a row regenerating the same plan — deadlock | Live run |
| Budget counts `reasoning_content` | Deliberation in the **content channel** invisible; 20-min unbounded round | Live run |
| Cancel the round on budget exceeded | `close()` on a generator raises `ValueError: generator already executing` from another thread, swallowed — **provider never stopped, kept billing** | Audit agent, reproduced |
| Move task prompt server-side | Frontend sends system content as a **list**; `isinstance(str)` check silently did nothing | Live job inspection |
| Dedup nudges within last 3 messages | Assistant/tool pairs push the old one out — **four copies stacked**, ~9KB re-sent per request | Live job inspection |
| `try_advance` on validators passing | Ran the **full validator set incl. a browser launch** after every tool round | Audit agent |
| Clear the thrash window | Validation attempts now win the race — forcing never fires | Test failure |
| `_EXECUTION_CHARS = 18_000` post-commit | Cut the artifact write at 18,004 / 18,007 / 18,004 — same regenerate-and-discard signature | Live run |
| `_MAX_ROUND_SECONDS = 540` backstop | Cut a write at 14,596 chars purely on elapsed time, leaving `...` on disk | Live run |

**The recurring shape:** a budget calibrated for one phase gets applied to a different one. Three
separate instances (reasoning channel, execution chars, wall clock).

---

## 6. The war-room audit — 20 confirmed defects

Six adversarial investigations run in parallel against separate subsystems. Full detail in
`AUDIT.md`. The four CRITICALs:

1. **Repository traversal.** `repository="../.."` resolved to Codexa's own source while being
   unequal to `"codexa-os"` — the string the mutation guard compared. `write_file`/`delete_file`
   operated on the platform's own code.
2. **Shell tools bypassed the guard entirely.** `run_command` runs `shell=True` in the repo root;
   `run_python` takes no repository argument so the check could never apply to it.
3. **`read_file(".env")` returned every provider key** into the conversation, the SSE stream, and
   the on-disk checkpoint.
4. **Cancellation never reached the provider** (see §5). Orphaned generation was the *normal case*.

Plus, notably: **`"build an html game of snake"` got no `write_file` at all.** `classify_intent` and
`generate_contract` derive from the same text with different regexes and disagreed — the `code`
group needs `build.?a\b`, which "build an" fails. The job was structurally incapable of building
anything while its contract demanded a file. Fixed by deriving tools from the contract.

---

## 7. Design quality — why output stayed generic

**Measured: across 21 benchmark jobs and ~1,000 tool calls, `get_design_guidance` was called
exactly ONCE.** 202KB of design expertise was effectively never in context. Four causes:

1. It is a **pull** tool nothing requires.
2. `build_task_prompt` was appended by the HTTP layer only `if messages[0]["role"] == "system"` — so
   API-started jobs got no task prompt at all.
3. Loaded guidance was **compacted away after 3 rounds**, before implementation.
4. The default skill is 88KB and **truncates to 30KB mid-rule**.

**A correction to my own diagnosis, worth recording.** I assumed the output was short on interaction
code. Measured, it isn't:

```
VELUM    16 listeners · 11 buttons · 30 transitions · focus-visible · reduced-motion · 30% JS
AURELIA  45 listeners · 32 buttons · 51 media queries · 52% JS
```

The capability was there. **Nothing checked whether it ran.** AURELIA's 45 listeners never attach —
its script dies on `Unexpected token ','` — and it passed two full refinement passes because the
only checks were "file exists" and "screenshot taken", both true of a blank page.

Two more screenshot-tool failures compounded it:
- It captured the **pre-animation frame** (`networkidle` fires while elements are still at
  `opacity: 0`), so "look at it and fix what's wrong" saw a blank cream rectangle.
- `browser_console` was a **stub** returning "requires an active Playwright session", making "fix
  console errors" literally unsatisfiable.

**Then, the animation gap specifically.** The user observed HTML getting more polished while
animation stayed generic. Three structural causes:
- Motion guidance was **adjectives** ("Motion carries meaning") — unimplementable.
- The `animate` skill (the one with implementation recipes) loaded **only for "choreographed"**
  briefs; most real briefs are "considered".
- Motion was **a third of** "Add interactions, transitions and the real states", and it was always
  the third that got dropped, because that task is satisfied by doing the first two.

---

## 8. Open / unresolved

**8a. The current benchmark — partially resolved while this was being written.**

Latest run (`tidepool2`, a deliberately small brief: one file, 300–500 lines, twelve records, two
behaviours). Round 3 was cut at 40,047 chars after 987 seconds without emitting anything — the wall
clock being off meant the round ran 16.5 minutes, and it still consumed the full authoring budget on
deliberation. But the **recovery then worked**: the forced write landed.

```
round 3 cut (cap_after_commit) at 40,047 chars / 987s — streak 1
round 8 · plan 3/9 · index.html 29,538 bytes, 1,015 lines, substance OK
```

So the cut is expensive but no longer a deadlock — one cut, recovery, artifact. That is the
difference from §1, where the same shape repeated indefinitely.

**The motion work (§7) is confirmed in the output.** Measured on that artifact:

```
--ease defined · exactly 1 cubic-bezier in the whole file
--fast: 120ms   --base: 240ms   --slow: 480ms      (the scale from the brief, used as given)
ad-hoc easings (ease-in-out / ease-out / linear):  0
focus-visible × 5 · prefers-reduced-motion × 2 · 9 transitions · 8 listeners
```

Zero ad-hoc easings is the specific signal: "different elements using different curves" was named in
the brief as the clearest tell of uncrafted motion, and it is absent. Before this change the same
system produced scattered `transition: all .3s ease`. This is one artifact, not a trend — but it is
the first run where the motion system was specified as values and executed as a milestone.

**The open question that remains for a reviewer:** why does a 300–500 line brief consume >40,000
characters of deliberation before the first tool call? Tool-call arguments are not counted (verified:
assistant messages show `chars=0, tool_calls=1`), so those characters were genuinely thinking.
Possible readings:
- the model composes the document in reasoning and must then re-emit every byte as a tool argument —
  double generation, which the delegation tooling explicitly warns about;
- the resident brief (~2.7KB) plus loaded design guidance is now large enough to provoke long
  synthesis;
- a reasoning model on a free tier front-loads by nature, and the answer is to stop counting
  characters and force the tool call earlier instead.

**8b. Known-unfixed from the audit** (recorded in `AUDIT.md`, not hidden):
- `run_round` silently re-runs a whole round — `emitted` is never set for a tool-only round, so a
  cut re-streams the entire round at full cost, unlogged.
- Cut and stalled rounds **record zero usage** — the most expensive rounds contribute nothing to
  token accounting. Bulk of the known ~20× undercount.
- Streamed usage is a **local estimate** (`stream_options={"include_usage": True}` never passed); a
  400KB base64 screenshot counts as 93 tokens.
- Reasoning tokens excluded from every total, including the context gauge.
- `continue_job` TOCTOU — two Continue clicks can drive one job on two threads.
- SSE closes on a transient error the loop is about to auto-continue, orphaning a live job.
- `page.goto` accepts any scheme including `file://`; shell-argument injection in
  `git_diff(files=…)`, `run_tests(scope=…)`.
- Memory store writes non-atomically and treats a parse failure as "empty".

**8c. Environmental, not code.** The backend and frontend were twice terminated together by the host
(`"stopped by the app"`, identical timestamps), killing in-flight jobs. Checkpointing survived it
every time. Provider availability is intermittent — the plan-proposal call fails with
`Connection error` on most runs and falls back to the deterministic plan.

---

## 9. What I would most like a second opinion on

1. **Is a character budget the right instrument at all?** Three separate calibration failures
   (§5) suggest the quantity being bounded may be the wrong one.
2. **§8a** — the specific question of why deliberation exceeds 40k on a small brief.
3. **Is the plan too coarse or too fine?** Nine tasks for a 400-line page may itself be the reason
   so much cross-task planning happens.
4. **Whether `intent_fidelity` (checking for a mechanism rather than a keyword) is sound**, or
   whether static analysis of this kind is doomed and only browser exercise should count.
