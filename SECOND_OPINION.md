# Codexa — three problems found tonight, need a second opinion

Codexa is an autonomous coding agent (task-driven execution, GLM 5.3 as the primary model)
that builds single-file HTML products end to end: plans a task list, commits to a design
direction, writes the file, screenshots and fixes what it sees. Tonight's user complaint,
verbatim: designs look clean individually but are "completely identical" across different
products, and even one file takes a long time with repeated issues. Investigated all three.
Here's what was found, with evidence, not guesses.

---

## 1. Every design converges on the same palette, even across unrelated products

Four different builds — a personal journal, a coffee reference, a life dashboard, a field
guide — produced near-identical output:

```
             paper       ink        accent      easing
Solace       #F6F3EE     #1B1917    #B4552F     cubic-bezier(0.16, 1, 0.3, 1)
brew         #F6F1E7     #1A1310    #D9603B     cubic-bezier(0.16, 1, 0.3, 1)
tidepool     #f4f0e6     #1c1a17    #9c4a2f      cubic-bezier(0.16, 1, 0.3, 1)
```

Warm-cream paper, near-black ink, burnt-orange accent, serif display type — and the exact
same easing curve to four decimal places, across products that share nothing conceptually.

### Root cause

Design guidance lives in skill files (up to 1206 lines) that the model only sees if it
calls a `get_design_guidance` tool. The resident system brief that's *always* in context
just tells the model which skill names to go load — it doesn't contain the actual content.

Tool results older than 3 rounds get compacted out of context to control token cost
(`_STALE_AFTER_ROUNDS = 3`). Measured on one job's own telemetry: guidance was loaded at
round 1, but `write_file` (the round that actually needed it) didn't happen until round 6.
By then context had shrunk back to 2,826 tokens — the ~18,000-token skill file was long
gone from context.

**The damning part**: that specific job was assigned `anti_slop.md` — a skill file that
*explicitly bans this exact palette by hex code*, with a dedicated section:

```
PREMIUM-CONSUMER PALETTE BAN (mandatory, second-most-recurring AI-tell):
  Backgrounds: #f5f1ea, #f7f5f1, #fbf8f1, #efeae0, #ece6db, #faf7f1, #e8dfcb
  Accents: #b08947, #b6553a, #9a2436, #9c6e2a, #bc7c3a, #7d5621
  Text: #1a1714, #1a1814, #1b1814
```

And it still produced `#D9603B` / `#1A1310` — the exact banned family. The ban never
survived to the round that needed it, so the model fell back to its own training-data
default, which is precisely the cliché this file exists to prevent.

Separately, in a different part of the same guidance system, a "concrete motion tokens"
principle gives one literal example easing curve (`cubic-bezier(0.16, 1, 0.3, 1)`) instead
of a decision framework — and the model copies that literal number verbatim every time
instead of choosing its own. Same failure shape, different subsystem: a specific example
meant as illustration gets treated as the answer.

### Question for a second opinion

Is "make the constraint durable, not the whole skill file" (i.e., extract the actual
decided values — chosen palette, chosen curve — into a small persistent state block that
survives compaction, the way a `commit_direction` tool result already does) the right fix?
Or is there a better-known pattern for this class of problem (large reference material vs.
small durable decisions) in agentic coding systems?

---

## 2. Generation is slow, and roughly half of it is measured, quantified waste

Percent of each job's wall-clock time spent in rounds that were generated, then cut off by
a token budget and discarded (the model re-runs the round after being force-directed):

```
job          cuts   wasted wall-time   % of total job time
a38e038c      9       44 min            68.7%
21fe2c22      6       36 min            50.2%
39d06f87      6       24 min            51.1%
99a34c84      5       16 min            40.3%
```

The pattern: on an "authoring" round (writing/committing to a direction), the model is
given no output-length information in advance and simply reasons until it hits a hard
character cap (~40,000 chars), gets cut off, and the *next* round is forced to call the
specific tool needed (`write_file`, `commit_direction`, etc.) — which then completes in
seconds with near-zero reasoning, proving the work didn't need the first attempt's length
at all. One job hit this same cut-then-force pattern twice in a row on the identical task.

Additionally: the job-level round cap and wall-clock cap are both currently disabled
(`CODEXA_ROUND_BUDGET=0`, `CODEXA_ROUND_SECONDS=0`) — a debugging override from earlier
that was never restored. So on top of the per-round waste, there's currently no outer
bound on total job runtime at all.

### Question for a second opinion

Given a model that reliably "thinks past" a length budget before committing to output on
open-ended authoring rounds — is a hard character-count cutoff (current approach) the
right lever, or is there a better-known technique (e.g., a much smaller max_tokens with a
retry-with-more-budget escalation, structured output constraints, or a completely different
prompting strategy for "produce one artifact" vs. "decide something") for controlling
runaway deliberation on generation-heavy steps specifically?

---

## 3. A live hang, caught mid-freeze

One job was found frozen: the live API reported `status: running, round: 39`, but its
on-disk checkpoint hadn't been updated in **7 hours**. Confirmed as a genuine hang (not a
busy loop) via near-zero backend CPU usage over that span.

Exact sequence from logs leading up to the freeze:

```
task A: cut at ~40k chars x3 -> intervention 1/3 (reasoning exhausted)
      -> intervention 2/3 (thrashing) -> intervention 3/3 (too many rounds)
      -> task marked FAILED, a narrower "recovery" task B is created
task B (the recovery): intervention 3/3 (thrashing)
      -> system explicitly refuses to create a second-level recovery
         ("no recursion" — one repair attempt per task, by design)
-> nothing in the logs after this point, ever
```

The outer exception handler around the whole per-job worker loop (`try/except Exception`,
catches everything, flips job status to `"error"` and returns) never fired — the job's
status stayed `"running"`, never became `"error"`. That rules out a raised-and-swallowed
exception; something is genuinely blocking with no timeout.

Traced the code immediately after the point where the recovery-refusal happens: when that
refusal returns "no tool to force" (None), the per-round loop does not appear to
re-select the active task before proceeding — it looks like it falls through and runs
another model round using the now-stale task reference instead of restarting the loop's
task-selection step fresh. Not 100% confirmed as *the* hang site (a live debugger session
would confirm), but it's a real correctness gap in that path regardless.

Not deterministic: the identical two-level exhaustion (task fails -> recovery created ->
recovery also fails) happened once in a *different* job earlier the same night, and that
job kept running normally afterward. So this looks like a race condition tied to something
timing-dependent, not a guaranteed crash on every occurrence.

### Question for a second opinion

Given "the broad exception handler never fired, CPU is idle, nothing after the log line" —
what's the most likely class of Python bug that produces exactly this signature? (Current
leading guesses: an un-timeout'd blocking call somewhere in the recovery path that isn't
covered by the existing LLM-stream watchdog, or a genuine deadlock on a lock/condition
variable shared between the per-job worker thread and something else.) Is there a faster
way to root-cause this without attaching a live debugger to the running process — e.g.
from log signature alone, or from a targeted code-reading strategy?

---

## What's already been tried / is already in place (context, not asking about these)

- Per-round generation is capped by character count across both "reasoning" and "visible
  content" channels (not just one), because a model was once observed to deliberate for 48
  minutes / ~40k tokens with no cap catching it because it was reasoning in the untracked
  channel.
- A "commit_direction" tool exists specifically so an early planning decision becomes
  durable state instead of living only in a transcript that gets compacted or discarded.
- Recovery tasks intentionally do not recurse (one repair attempt per original task) — a
  prior version allowed chained repairs and it produced a "Recover: Recover: Recover: ..."
  chain that burned the whole revision budget re-attempting something already proven
  impossible.
- Design skill selection already picks one specific skill file per detected "character"
  (e.g. classical/editorial vs. luxury vs. data-dense vs. contemporary) rather than dumping
  every skill file into every job.
