# Token usage investigation — Codexa OS chat/agent pipeline

**Status:** partially fixed, second opinion requested on the remaining items.
**Scope:** `backend/chat/api.py` (multi-round tool-calling loop), `graph-viz/app/(workspace)/chat/page.tsx` (client-side history), `backend/memory/context.py` (repo-context injection), `backend/agents/tools.py` (tool payload sizes).

## Headline numbers (real, from `.codexa/usage.jsonl` for this session)

| Model | Calls | Prompt tokens (sum) | Completion tokens | Reasoning tokens |
|---|---:|---:|---:|---:|
| `zai/glm-5.2` | 44 | **609,858** | 58,513 | 18,148 |
| `gemini/gemini-2.5-flash` | 20 | 164,934 | 69,007 | 7,205 |
| `nvidia_nim/nvidia/nemotron-3-ultra-550b-a55b` | 9 | 82,810 | 491 | 851 |
| `nvidia_nim/meta/llama-3.1-8b-instruct` | 4 | 45,154 | 1,480 | 0 |
| `groq/openai/gpt-oss-120b` | 6 | 18,294 | 4,329 | 307 |
| `nvidia_nim/openai/gpt-oss-120b` | 5 | 16,982 | 2,027 | 266 |
| `groq/llama-3.3-70b-versatile` | 4 | 11,356 | 3,907 | 0 |
| others | 5 | 4,295 | 1,166 | 663 |
| **Total (all providers)** | 99 | **953,683** | **140,920** | **27,373** |

The GLM 5.2 total — **609,858 prompt tokens** — is the number the "600k tokens for a single HTML file" complaint referred to. It is real, sourced from the usage tracker, not an estimate. It is a *sum across many separate API calls* within one multi-round agent task (and across several such tasks this session), not one single 600k-token request — but that distinction is exactly the point of this doc: the architecture pays for the same growing context repeatedly, once per round, and that compounding is what turns a single user-visible request ("build me an HTML page") into hundreds of thousands of billed tokens.

## Incident 1: single-HTML generation task, ~600k tokens

**What the user asked for:** one large single-file HTML/CSS/JS page (a "luxury landing page" style benchmark prompt), built by the chat agent via its tool-calling loop (`create_project` → `get_design_guidance` → `create_directory` → `write_file` → verification calls).

**What actually happened**, traced through a real logged run (`.codexa/usage.jsonl`, timestamps 2026-08-07T10:31–10:36, `zai/glm-5.2`):

```
Round   prompt_tokens
1       470
2       2,817
3       3,361
4       26,802   <- +23,441 in one round: get_design_guidance's tool result landed in history
5       29,501
6       5,060    <- new request in the same window (parallel testing), included for completeness
7       11,990
8       13,600
9       14,182
10      29,558   (this round alone: 30,079 completion tokens — the actual file body)
11      56,817
12      57,230
13      59,271
14      59,549
```

Two mechanisms drive this, both in `backend/chat/api.py`'s `gen()`:

1. **The tool-calling loop keeps one `messages` list for the entire request and only ever appends to it.** Every round's request is billed for the *entire* accumulated context, not just what changed. A task needing N rounds pays for the growing context N times over, not once.
2. **Individual tool payloads are large and, until this session's fix, permanently retained:**
   - `get_design_guidance` (in `backend/agents/tools.py`) returns up to 24,000 characters (~6,000 tokens) of a design-system reference doc. It was being re-sent on *every subsequent round* for the rest of the task.
   - `write_file`'s tool call carries the **entire file body** in `function.arguments` — for this task, tens of KB of HTML/CSS/JS — also re-sent on every subsequent round (e.g. when the agent then calls `list_directory`/`read_file` to verify its own work).

## Incident 2: a "small" follow-up message hit an 8,000 TPM cap

```
RateLimitError: Request too large for model `qwen/qwen3.6-27b` ...
tokens per minute (TPM): Limit 8000, Requested 20738
```

This looked alarming because the user-visible ask ("delete these two directories") was trivial. The real cause: this was message 4–5 of an ongoing conversation, and **the client resends the entire conversation history on every message, uncapped** (`buildHistory()` in `graph-viz/app/(workspace)/chat/page.tsx`). By that point in the thread the full back-and-forth (initial question, a tool-call attempt, a blast-radius approval cycle, the follow-up) was being sent in full every time, plus the repo-context injection on top. 20,738 tokens for "the whole conversation so far" is unremarkable — it only looks wrong in isolation. The account's Groq tier caps that specific model at 8,000 TPM, far below what a normal multi-turn conversation needs.

Contributing factor found while investigating: `backend/memory/context.py`'s fallback path (used when a query doesn't resolve to specific graph nodes) injects up to 16 memory records with **uncapped content** — records like "Project structure" or "Key functions & components" are full-tree/full-function-list dumps that can be several KB each.

## What's already been fixed this session

1. **Tool-payload history compaction** (`backend/chat/api.py`, `_compact_stale_payloads`): once a `get_design_guidance` result or a `write_file`/`edit_file` call's content is 3+ rounds old, it's collapsed to a short marker (`[compacted — N chars, already written to disk]`). Verified live: real multi-round task, compaction fired on the design-guidance blob by round 6, output unaffected (file content is always re-read from disk, never from history, so nothing was lost). 3-round grace window chosen deliberately — errs toward safety over savings.
2. **Model registry diversification**: GLM 5.2 running out of balance used to mean falling back to a plain 70B model. Now `nvidia_nim/nvidia/nemotron-3-ultra-550b-a55b` and `groq/openai/gpt-oss-120b` sit between them as real frontier-adjacent options — doesn't reduce tokens, but reduces how much a single provider's limits (balance *or* rate limit) can strand the whole app.
3. **Tier-order fix**: `groq/qwen/qwen3.6-27b` was briefly the default "balanced" model; discovered its 8,000 TPM account cap makes it unusable as a default and moved it to last in that tier's fallback order.
4. **Per-round timeout tuning + stall-recovery**: unrelated to token *volume*, but relevant context — earlier fixes in this session (90s → 240s per-chunk timeout, 2 automatic "continue where you left off" recoveries) were themselves partly a reaction to how large these accumulated-context requests had gotten; a large request taking a long time to process was being killed by too-short timeouts before compaction addressed the size itself.

## What's identified but NOT yet fixed (proposed, pending a decision)

1. **Client-side conversation history has no cap at all.** `buildHistory()` sends every prior turn, forever, on every message. This is the direct cause of Incident 2 and is architecturally the same class of bug as the tool-payload one already fixed, just one layer up (conversation turns instead of tool rounds). Proposed fix: cap to the last N turns, or a token-budget cutoff, when building the request — the full history stays in the UI/local store, only what's sent to the model is capped.
2. **`memory/context.py`'s fallback path injects uncapped record content.** Proposed fix: apply the same truncation helper already used elsewhere (`_truncate`, `backend/agents/tools.py`) to each `ContextItem.content`.
3. **No automatic fallback on rate-limit errors.** A 429 currently surfaces as a dead-end error to the user (with a manual Retry button added earlier this session). Proposed: on a rate-limit specifically, automatically retry against the next model in the same tier, mirroring the stall-recovery mechanism already built for timeouts.

## Open questions for a second opinion

- Is a fixed 3-round staleness window for tool-payload compaction the right trade-off, or should it be based on actual token count / model context window instead of a round count?
- For capping conversation history: turn-count cutoff (simple, predictable) vs. token-budget cutoff (more accurate, more complex, needs a tokenizer per-provider)?
- Should there be a hard per-request token ceiling that requires explicit user confirmation before a task is allowed to proceed into a very large single-shot generation (e.g. the "single 40KB+ HTML file in one `write_file` call" pattern), independent of the compaction fixes?
- Separately (not a token-cost issue, but adjacent): the blast-radius "approve" flow currently asks the model for an *implementation plan*, not to actually execute the change — is that the intended design, or should approval trigger real tool execution?
