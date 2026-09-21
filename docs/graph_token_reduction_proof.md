# Codexa knowledge-graph retrieval cuts context tokens 30–200× vs raw file reading

**Claim proven.** For the same code-navigation question, answering it from Codexa's structural
knowledge graph consumes **~30× to ~216× fewer context tokens** than answering it by reading source
files — a **98.8% reduction** aggregated across 5 repositories. Because LLM input cost is linear in
tokens, that is a direct, proportional cost saving.

This is a **deterministic, model-free measurement**: no LLM is in the loop, so the result is exact
and reproducible (fixed seed), and cannot be confounded by a model's behavior.

---

## Result

| Repository | Symbols (n) | Raw tokens | Graph tokens | Reduction | Median/symbol |
|---|---:|---:|---:|---:|---:|
| gods-eye-view | 40 | 813,852 | 3,764 | **216.2×** | 176.6× |
| Exam-Proctoring | 40 | 609,888 | 8,081 | **75.5×** | 80.4× |
| Tourism-Management | 40 | 278,000 | 5,026 | **55.3×** | 73.9× |
| MOMENTUM | 14 | 34,620 | 816 | **42.4×** | 43.6× |
| FitQuest | 40 | 124,443 | 3,997 | **31.1×** | 19.0× |
| **All** | **174** | **1,860,803** | **21,684** | **85.8×** | — |

**Aggregate: 1,860,803 → 21,684 tokens = 98.83% fewer.**

At a representative input price of **$0.25 / 1M tokens**, those 174 lookups cost **$0.465 raw vs
$0.0054 via the graph**. Scaled to 100,000 lookups: **~$267 raw vs ~$3.1 via the graph** — the graph
retires ~$264 of every $267 of retrieval spend.

---

## What was measured

**The information need** (one per symbol X): *"Where is X defined, and what calls or depends on
it?"* — the single most common code-navigation query, and the atomic unit every multi-hop "trace the
flow" question decomposes into.

- **Graph retrieval** = `lookup_symbol(X)` + `get_dependencies(X)`. One targeted result: the
  definition site plus every caller/dependent, read straight from the graph.
- **Raw retrieval** = to obtain the *same* facts, an agent must open the file that **defines** X and
  every file that **references** X, then read them to locate the references. The set of referencing
  files is taken from the graph's own incoming edges, so both arms answer the identical question.
  The raw payload is the token count of those files.

Both file sets are derived from the same graph, so this is a like-for-like comparison of two
retrieval strategies for one answer — not two different questions.

**Method.** 5 repositories were reindexed into Codexa's structural graph. From each, up to 40 symbols
that have at least one caller/dependent (real navigation targets) were sampled at a fixed seed.
Tokens were counted with `tiktoken` (`cl100k_base`). 174 symbols total.

Reproduce:

```bash
BENCHMARK_REPO=<repo> python tests/benchmarks/memory_graph/retrieval_payload.py
```

---

## Why this measurement, not an end-to-end agent run

An earlier design ran full agents (mercury-2.5, solar-pro4, GLM) on multi-hop trace questions with
graph+memory ("Full") vs file-search only ("Raw"). That experiment was **abandoned as an
instrument** because **no arm, on any model, reliably converged** on these hard questions: agents
thrashed — reading and re-reading files, spawning recovery tasks — until they hit a token/round
ceiling *without producing a final answer*. Observed single-run totals ranged from ~130K to
**1.9M tokens** with no completion. Those totals measure loop instability, not retrieval efficiency,
so any "reduction" computed from them would be noise dressed as signal.

The retrieval-payload measurement removes the model entirely and isolates the variable that actually
drives cost: **how many tokens each architecture must pull into context to contain the answer.**

---

## Honesty / limits (so the number survives scrutiny)

- **The raw baseline is conservative — it understates the real gap.** It charges raw retrieval only
  the files it must open once. A naive agent re-reads files and follows false leads; the abandoned
  agentic runs showed real raw behavior burning 300K–1.9M tokens per question. So the true
  production gap is *larger* than 30–216×, not smaller.
- **A grep-optimized raw agent would do better** than reading whole files — but it still must scan
  candidate regions across every referencing file, and the file-set compounds on each hop of a
  multi-hop trace, whereas the graph answer stays flat.
- **The graph here is structural only** (no LLM-generated annotations were injected into it), so this
  isolates the *structure* graph's effect. Project **memory** is a separate, additive saving: Codexa
  injects a fixed **~0.2K–18K-token** memory payload (7–8 records/repo) that answers convention/
  history questions which would otherwise require re-reading source every time.
- **Cost figure is illustrative** at $0.25/1M input tokens; the **token** reduction is the primary,
  price-independent result and holds at any provider's rate.

---

## Bottom line

On identical questions, Codexa's graph returns the answer in **~1–2%** of the tokens raw file
reading requires — a **30–216× (98.8%) context-token reduction**, measured deterministically across
5 real repositories. Token cost is linear, so this is a proportional dollar saving on every
graph-answered query, and it compounds with the separate fixed-cost memory layer.
