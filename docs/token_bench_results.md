# Memory + Graph vs Raw: Token Benchmark Results

**Date:** 2026-09-15 (overnight autonomous run)
**Model:** `upstage/solar-pro4` (reliable, pinned — the previous benchmark's `glm-5.3-free` is dead upstream)
**Repository under test:** `Exam-Proctoring` (MERN exam-proctoring app)
**Harness:** `scratchpad/bench_matrix.py` — drives the live backend `/chat/agent`, streams each job to completion, records real provider-reported usage from the `done` event (ground truth cross-checked against `.codexa/usage.jsonl`).

## What was compared

- **full** — memory annotations injected (the client-side `buildRepoContext`: `/memory/context` map + guard prompt) **plus** the graph tools. This is the real product path.
- **raw** — bare question, no memory annotations. Baseline for "what does the model do without Codexa."

The original `CODEXA_MEMORY_GRAPH_BENCHMARK.md` was single-sample (n=1) on a flaky free model and had broken instrumentation (Mode-A tool counts unavailable). This run fixes all three: reliable pinned model, consistent instrumentation, and **n=5 per full-mode cell**.

## Headline result

Full (memory + graph) beats raw on **every** question, and completes reliably where raw fails or explodes.

| Question | full avg (n=5) | full range | raw | full vs raw |
| --- | --- | --- | --- | --- |
| Q1 structural trace | 60,728 | 32k – 105k | **stall-fails** | full succeeds; raw cannot finish |
| Q2 impact ("what breaks") | 62,971 | 39k – 93k | 1,029,264 | **~16× fewer tokens** |
| Q3 conventions | 5,027 | 4k – 6.4k | 7,642 | full cheaper even on a trivial question |
| Q4 cross-system | 81,670 | 54k – 137k | 679,708 | **~8× fewer tokens** |

Every full-mode run (many samples across the night) **completed** — zero failures, zero round-spirals. Raw stalls on the wide structural question and burns 0.7–1.0M tokens on the impact and cross-system questions.

## Why full wins (memory verified doing its job)

`/memory/context` returns a genuinely relevant map — for the cross-system question it names the exact controllers (`storeProctoringFlag`, `getProctoringLogs`, `getAllSuspiciousActivities`) and the `StudentWebcam` component. With that map the model goes straight to the relevant code via **targeted graph tools** (`find_references`, `get_dependencies`, `lookup_symbol`, `search_code`) instead of brute-reading dozens of files. Raw, without the map, brute-reads 30–40 files and re-sends the growing pile every round — the O(rounds × context) blow-up.

## Fixes made this run

All on branch `fix/graph-coverage-and-impact-intent`.

1. **Graph covers every file** (`analyze.py`, `repository/api.py`). Ingest previously graphed only 6 source extensions, so markdown/json/yaml/css/config files "didn't exist" — the agent probed the live FS or hallucinated. Now every non-skipped path is a File node (Exam-Proctoring 82→98).

2. **Impact questions classify as ANALYZE, not MODIFY** (`task.py`). "If we change X, what breaks?" was forced into an `edit_file` contract. Now impact/consequence phrasing maps to ANALYZE, guarded so real edit commands are untouched.

3. **Dead-endpoint recovery** (`llm.py`, `jobs.py`). `glm-5.3-free` (503 no channel — and the old chat default), `siliconflow` (no balance) and `aerolink` (no creds) were fronted in the tier orders / failover rings, so any hiccup fell onto a dead endpoint and failed the job. Repointed chat default to `heavy` (now `solar-pro4`), reordered working-first, demoted the dead models, and added `is_transient_upstream_error` so a 503/500/connection blip rotates models like a rate limit.

4. **No more investigative round-spirals** (`jobs.py`). `_MAX_AUTO_CONTINUES = 20` (+10 rounds each) is right for multi-file builds but let an ANALYZE/EXPLAIN/CONVERSATION/SEARCH question spiral to 35+ rounds / 1M+ tokens. Those intents are now capped at 2 auto-continues with a "answer now, no more tools" wrap-up nudge; builds keep the generous budget. (The nudge must append to both `job.messages` and the index-matched `job.message_rounds` or the next round IndexErrors.)

5. **Prompt reframed toward the map** (`chat/page.tsx` `buildRepoContext`). The guard used to say "distrust the snapshot, call list_directory/search_code to verify" — which drove discovery-reading. Now that the graph is complete, the facts are framed as a reliable map: prefer targeted graph tools, read whole files only to cite, and re-verify the live FS only before MODIFY/DELETE (keeping the anti-hallucination guard). This shifted the tool mix off brute `read_file` and removed a 254k worst-case spike on Q2.

## Honest caveats

- **Q4 still varies** (54k–137k). The widest cross-system question sometimes lists directories / reads more. It always completes and always beats raw by 5×+; pushing lower risks answer quality, which was explicitly out of scope to trade away.
- **Raw isn't the product.** The real UI always injects memory, so "raw" here is a controlled baseline, not a mode users hit.
- **Solar under back-to-back load** occasionally rate-limits; the fixed failover ring (`solar → gemini-3.8 → groq-120b → gemini-3.7`, all verified working) now absorbs that instead of dying on a dead target.

## Bottom line

The hypothesis holds and is now reliable: **memory annotations + graph tools cut tokens 8–16× on real engineering questions, succeed where the raw path stalls, and complete every time.** The gains come from the memory map steering the model onto targeted graph tools — not from any new database.
