# From short paper to strong paper — NavBench full study plan

Date: 2026-10-08. Basis: the 4-page FORGE draft (`paper/forge/`), the review
(`paper/forge/REVIEW_2026-10-08.md`) and the implemented features (`FEATURES.md`).

## 1. Why the short paper is not yet a strong paper

| Reviewer objection (from the review) | What a strong paper must add |
|---|---|
| "Payload tokens are not agent cost" (construct validity) | An **agent-level study** showing whether payload metrics predict agent success, cost and tokens-to-success |
| "Small libraries, two languages, two graph tools" | Scale: **~40 repositories, 4 languages, 6–8 tools**, including large repositories (the falsification test predicted by the 0.75 elasticity) |
| "No accuracy on natural code" | A **human-audited natural layer** (κ reported) next to the fixture and runtime layers |
| "Incremental over Xu 2026 / Codebase-Memory" | A contribution nobody has: a **systematic audit of published efficiency claims** — how the field actually measures, re-measured |
| "The authors' own tool" | G1 becomes one tool among many; G1-v2 is reported only as a fresh-seed / natural-code case study of benchmark-driven repair |

## 2. The strong paper

**Working title:** *"N× Fewer Tokens"? Auditing and Re-Measuring the Efficiency Claims of
Code-Navigation Tools for Coding Agents*

**Thesis.** Efficiency claims for code-navigation tools are dominated by three hidden measurement
choices: baseline, sampling frame and output form. Under controlled measurement:
- graph tools trade completeness for size;
- payload efficiency does / does not (RQ4 decides) carry over to agent cost;
- simple routing captures most of the available benefit.

| RQ | Question | Evidence |
|---|---|---|
| **RQ1 Claims audit** | How are published efficiency claims measured? | Systematic catalogue of claims from papers and MCP code-intelligence tools (target 40–60 claims). Each is double-coded for baseline, sampling frame, output form, completeness reported, payload vs. agent, model, n, variance. A subset (8–10) is re-measured with their published setup and with NavBench's controlled setup |
| **RQ2 Measurement sensitivity** | How much do baseline, sampling and form move the ratio? | The current Q1/Q2 at scale: ~40 repositories × 4 languages × 6–8 tools. Includes the MSA form (feature B) and the absolute-path artifact |
| **RQ3 Correctness at matched cost** | Which tools reach useful token–completeness operating points, on code that matters? | Fixtures (the pattern taxonomy) + **human-audited natural targets** + runtime-observed calls. Includes **T3 multi-hop** (feature E), where graph tools claim their advantage |
| **RQ4 Payload → agent** | Do payload-level results predict agent-level outcomes? | Agents with each tool exposed via MCP, on test-scored tasks that need call-site knowledge. Metrics: success, tokens-to-success, billed cost including caching, turns. Mixed-effects models linking payload completeness and tokens to agent outcomes |
| **RQ5 Routing** | Can a cheap policy get the best of both? | Feature A at payload level, then the best 1–2 policies at agent level |

**Contributions:**
1. The first systematic audit of efficiency claims, with re-measurement. Released as a coded
   dataset.
2. NavBench at scale: a multi-language, multi-tool benchmark with three independent label layers
   plus a human audit, adapters (feature C) and a leaderboard.
3. Evidence on whether payload efficiency transfers to agents (RQ4); positive or negative, it is
   publishable.
4. Reporting guidelines, backed by RQ1–RQ4.

## 3. Design details

### 3.1 Corpus (fixed by criteria before results; extends `corpus.json`)

- **Languages:** Python and TypeScript (existing), plus **Go** and **Java**. Both have mature
  language servers (gopls, jdtls), and graph tools support them. If language-server cost is too
  high, Go alone.
- **Size:** 10 repositories per language, ~40 in total, spanning sizes. Include **≥ 2 large
  repositories per language** (≥ 5k declarations, many ambiguous names) — the falsification test
  for "graph saves nothing".
- **Layer C:** Python plus Go (`go test` with coverage-based call tracing) or Java (agent-based
  tracing). If tracing for the new languages is too costly, keep Layer C Python-only and say so.

### 3.2 Tools (adapters, feature C)

| Category | Tools |
|---|---|
| Lexical | rg -w; rg -w -C3 |
| Language servers | pyright, TS service, gopls, jdtls; plus an **LSP-over-MCP** server (e.g. Serena) as the agent-facing form |
| Graph | codebase-memory (current), G1 (frozen), 2–3 popular open MCP code-graph tools selected by fixed criteria (stars, activity, call-graph query support), plus a SCIP-index baseline (scip-python / scip-typescript) as the "compiler-grade static index" reference |

### 3.3 Human audit (natural layer)

- 300 S-ind targets, stratified by language and fan-out, with T1 caller sets.
- Two annotators with the IDE and the full repository. Third annotator adjudicates.
- Report Cohen's κ, then per-tool precision and recall on natural code.
- Effort: about 5–7 person-days.

### 3.4 Agent study (RQ4) — the decisive addition

**Tasks.** Test-scored edits that require knowing call sites: change a function signature and
update every caller; rename across files; "add a parameter and thread it through callers"; plus
callers questions scored against the audited gold.
- 40 tasks per language from the corpus, generated from the audited targets so the gold is known.
- Hidden tests verify that every call site was updated.

**Agent.** mini-SWE-agent (transparent) with each tool exposed through MCP. Conditions:
- rg only;
- rg + language server;
- rg + each graph tool;
- rg + the routing policy.

Same prompt and the same budget everywhere.

**Models.** Two open-weight models (pinned) and one frontier model on a subset. Three repetitions
each, because agent variance is up to 30× (Bai et al.).

**Metrics:**
- success (tests);
- tokens-to-success (Xu's metric);
- billed cost with prompt caching (per Weinberger & Hozez);
- turns, and tool-call mix.

**Analysis:**
- mixed-effects models (task and repository random effects);
- the correlation between each tool's payload metrics (completeness, MSA tokens) and its agent
  outcomes;
- cases where they disagree.

**Rough scale:**
- 160 tasks × 5 conditions × 2 models × 3 reps ≈ 4,800 runs;
- ~100–200k tokens per run → 0.5–1B tokens on open-weight models;
- a frontier subset of 40 tasks × 5 × 1 × 3 = 600 runs.

**Pilot first:** 20 tasks × 3 conditions × 1 model × 2 reps.

### 3.5 Claims audit (RQ1)

- **Sources:** academic papers (2024–2026) on code graphs, LSP and navigation for agents, plus
  README and blog claims of MCP code-intelligence tools (GitHub search with fixed criteria, e.g.
  ≥ 200 stars, a numeric efficiency claim).
- **Coding scheme:** baseline type; sampling frame (graph-conditioned or independent); output form;
  completeness or quality reported; payload vs. agent level; n repositories; n queries; variance or
  CI; model.
- Two coders, κ, disagreement resolution.
- **Re-measurement:** the 8–10 most-cited claims, reproduced with their own setup and then with
  NavBench controls (same queries, independent sampling, matched completeness).

### 3.6 Pre-registration

Freeze on OSF before any held-out or agent run (the existing `FREEZE.md` practice):
- RQ hypotheses;
- primary contrasts and margins;
- sampling;
- exclusion rules;
- analysis models.

## 4. Timeline (≈ 14–16 weeks, with gates)

| Weeks | Work | Gate |
|---|---|---|
| 1 | Commit; Linux environment; claims-audit coding scheme + pilot (15 claims, κ) | **G1:** κ ≥ 0.7 on the scheme |
| 2–3 | Corpus selection (4 languages), Go/Java adapters, new tool adapters, fixture generator for Go/Java (or a reduced language set) | **G2:** fixture gate passes per language |
| 3–4 | Full payload run (RQ2, RQ3) + Layer C; human audit in parallel | **G3:** audit κ ≥ 0.7 |
| 5 | Agent pilot (RQ4) | **G4:** success rates in 20–80% (tasks neither trivial nor impossible); variance estimate gives the number of repetitions |
| 6–9 | Full agent study; claims re-measurement | — |
| 10–11 | Analysis; routing at agent level (RQ5) | — |
| 12–14 | Writing (full paper, 10–12 pages + appendix); artifact (Zenodo DOI, Docker image) | Internal red-team against the review's objection list |

**Venue:** a full research track (ICSE / FSE / ASE), MSR for an audit-heavy framing, or TOSEM/EMSE
if the agent study runs long. Verify the CFPs. The FORGE short paper can still go out on 15 Nov as
an early version, **only if** the target venue's policy allows a substantially extended version.
Otherwise skip FORGE and keep the results unpublished until the full paper.

## 5. Resources needed

| Item | Need |
|---|---|
| Compute | A Linux machine or VM: 16 cores, 64 GB RAM, ~200 GB disk (LSP indexing of large repositories, cbm builds, Docker for agents) |
| LLM budget | ~0.5–1B open-weight tokens (NIM/Groq/DeepSeek-class pricing) + a frontier subset |
| People | 2 annotators × ~5 days (audit) + 2 coders × ~2 days (claims) |
| Tools | gopls, jdtls, scip-python/typescript, Serena, 2–3 graph MCP tools — all open source |

## 6. What stays out

- G1-v2 as a headline: it is the authors' tool repaired on the benchmark. Report it only as a
  fresh-seed and natural-code case study.
- Memory work: that is a separate paper (`docs/research/strong_paper_design.md`).
