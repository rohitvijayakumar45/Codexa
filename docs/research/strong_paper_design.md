# Strong Paper Design (v2) — Memory Rot in Coding Agents

Date: 2026-09-25. This **supersedes** [`paper_plan.md`](paper_plan.md) as the primary plan. It builds on
the prior-art review in [`novelty_matrix.md`](novelty_matrix.md), extended here with a second, wider
literature pass (§2). Quorum/debate stay out.

---

## 0. The decision in one paragraph

The anchored-memory idea on its own is no longer a strong paper. Anand (2026), EA-Graph and ECK own
anchoring as a *detection* technique, and Anand shows an LLM claim judge beats anchors on precision.

What **nobody** has done is answer the three questions practitioners and researchers are now asking
about coding-agent memory in the wild:

1. **How much of it is stale, and how fast does it rot?**
2. **Does stale memory actually hurt agents, and through what mechanism?**
3. **What is the cheapest way to keep it fresh without throwing away what is still true?**

At least five 2026 groups name these questions as open and leave them unanswered (§2). Codexa already
has most of the machinery needed to answer all three: the tree-sitter graph, anchors, the git replay
harness, the memory store and the job harness.

The strong paper is a **large-scale empirical study plus a method**: in-the-wild prevalence and
dynamics, then controlled harm with dose-response, then deterministic, claim-typed prevention. The
prevention is evaluated both as detection and as recovered agent performance.

**Working title:** *Memory Rot: How Stale Context Misleads Coding Agents, and How to Keep It Fresh*

**Alternatives:** *Stale by Default: …*; *When Agent Memory Lies About the Code*

---

## 1. Why this is a strong paper (not a systems note)

| Property reviewers reward | How this design delivers it |
|---|---|
| An important, timely problem | Context files are now standard: 60k+ repositories use AGENTS.md (ContextCov) and 2.3k files were studied in Agent READMEs. **GitHub Copilot Memory is on by default** for Pro users and relies on citation checks plus a 28-day expiry. Agent instruction files and notes make up **60.5% of agents' documentation interactions** (Gao & Chen 2026) |
| An explicitly open question | Harm from stale context is RQ3 of Treude & Baltes 2026 ("which forms of context rot affect AI assistant behavior?"), future work in Lulla et al. 2026 and Agent READMEs, and untested publicly in Copilot's "self-healing" claim. Anand 2026 states that no memory system was modified to use its arms |
| Rigour | Full-history survival analysis (not two snapshots); a controlled paired design with **dose-response**; a mechanistic trace analysis; human-validated labels with κ; pre-registration; multiple harnesses and models, including open-weight ones |
| A method contribution, not only measurement | Claim-typed deterministic validators plus anchors, claim-class routing (with a soundness argument) and an anchor-gated cascade for residual claims. Evaluated head-to-head against DOCER (regex), an LLM auditor, Copilot-style just-in-time verification and Anand's claim judge, **on detection and on recovered agent outcomes** |
| Artifacts | A dataset of typed claims with staleness histories; the harm benchmark (tasks × rot doses); the checker as a CI tool and agent hook |
| A clear headline finding either way | If harm is large, prevention matters and ours is the cheapest sound option. If harm is small, "agents silently absorb stale memory at a measurable efficiency cost, and never verify" is itself the finding (see the fallbacks in §8) |

---

## 2. Literature — full landscape after the second pass

### 2.1 Directly adjacent (must be cited and differentiated)

| Work | What it did | What it left open (our opening) |
|---|---|---|
| **Treude & Baltes, *Context Rot*** (arXiv 2606.09090, Jun 2026) | Ran DOCER unmodified on 356 repositories (612 AI config files). **23.0% of repositories** had stale code-element references; per-reference rate 1.27%; regex precision about 64%. Two snapshots only | Only *referential* rot; no commands, dependencies, structure or behaviour; two-snapshot design; regex false positives. **No harm measurement (their RQ3). No repair (RQ4)**. Dataset on Zenodo (10.5281/zenodo.19375880) |
| **Lulla et al., *On the Impact of AGENTS.md Files on the Efficiency of AI Coding Agents*** (2601.20404) | 10 repositories, 124 merged PRs, Codex; the historical AGENTS.md vs. no file; **runtime −28.6% (median), output tokens −16.6%** | File *presence*, not *accuracy*. The paired pre-PR snapshot design is exactly what we reuse |
| **Gloaguen et al. (ETH), *Evaluating AGENTS.md*** (2602.11988) | SWE-bench plus real issues, several agents; context files **do not raise success** and **cost ~20% more** | *Why* they don't help is untested; staleness is a candidate explanation we can measure |
| **Chakrabarti, *Why Does CLAUDE.md Keep Growing?*** (2608.11095) | 247,694 instruction lifetimes, 1,867 repositories; files grow +226% over their lifetime; deletion hazard falls with age, because deleting needs a rationale | Validity is not measured. **Anchors are a machine-checkable rationale**, and they license safe deletion (our link to their theory) |
| **Chatlatanagulchai et al., *Agent READMEs*** (2511.12884) | 2,303 context files; structure, maintenance and content taxonomy | Explicitly calls for a "linter … verify that the commands … match the actual scripts in package.json" and for "context debt" |
| **Anand, *Impact Is Not Invalidation*** (2609.25130) | Behavioural claims (test assertions), 23 Python libraries; file and symbol anchors vs. testmon vs. LLM judges; claim judge P 0.79 / R 0.72 | No cascade, no deployment or agent study, Python only, no context files. **The benchmark is released: our detection baseline and second test set** |
| **EA-Graph** (2608.04278) | Span-hash anchored verification memory; synthetic worlds; anchored F1 1.0 vs. prose 0.27 (Haiku) | Synthetic; n is tiny; no in-the-wild data |
| **ECK** (2608.16295) | Authored code-knowledge units; AST-bounded fingerprints for freshness | Hand-authored; tiny evaluation (26 patches) |
| **GitHub Copilot Memory** (blog, docs) | Agent-written memories with **file:line citations**; the agent is *prompted* to verify citations before use; a 28-day expiry; reports +7 pts PR merge rate | Verification is LLM- and agent-side, and costs tool calls on every use. Only internal evaluation; "self-healing" is untested publicly. **This is our deployed baseline** |
| **Gao & Chen, *From Agent Behaviour to Agent-Friendly Documentation*** (2608.20195) | 557 SWE-chat sessions and 33k AIDev PRs. Agent files and notes are 60.5% of documentation interactions. A **"Verify" (code vs. docs) interaction was never observed** | Direct evidence that agents trust memory without checking it, which motivates machine-side freshness |
| **Nakayashiki, *Budgeted Verification Failures*** (2608.25553) | Under a verification budget, 16 LLMs rarely re-check stale constraints (~75% stale-consistent decisions) | Not code; motivates removing verification from the agent's budget |
| **ContextCov** (2603.00822) | Compiles AGENTS.md rules into runtime guardrails (tree-sitter, dependency graph, LLM judge); 88.3% compliance on SWE-bench Lite | *Enforces* instructions and never asks whether they are still *true*. Enforcing a stale rule is worse; complementary |
| **Codified Context** (2602.20478) | A 108k-line C# case study; calls staleness "the primary failure mode"; a session-start drift hook | An anecdote with no statistics; its drift hook is the file-changed heuristic (our A2 baseline) |
| **STALE** (2605.06527); **MemoryAgentBench**; **LongMemEval** | Stale and conflicting memory in dialogue; LLM-managed updates fail on implicit conflicts | Not code, where staleness is *decidable* from repository state |
| **SWE-Bench-CL** (2507.00014) | Chronological per-repository task sequences with a memory module | Staleness of memory across the sequence is not analysed. **This is our testbed for agent-written memory** |
| **RepoAgent** (EMNLP 2024 demo) | Documentation regenerated when an object's code *or its reference relationships* change (git pre-commit) | The engineering heuristic behind our hybrid anchor; never evaluated for staleness accuracy |
| **AIDev** (2602.09185) | 932,791 agentic PRs (Codex, Devin, Copilot, Cursor, Claude Code) across 116k repositories | Enables the observational harm analysis: context-file staleness *at PR time* vs. PR outcome |

### 2.2 Classical foundations (cite them; they pre-empt any claim of "new theory")

- **Code–documentation inconsistency:** iComment/@tComment (Tan et al.); Panthaplackel et al. (AAAI 2021); DOCER (Tan et al. 2024); Wen et al. (ICPC 2019); installation-instruction checkers (FindICI).
- **Soundness of change-based invalidation:** safe regression test selection (Rothermel & Harrold); Ekstazi; testmon. Incremental computation: verifying traces and early cutoff (Mokhov et al., ICFP 2018), Salsa, Adapton.
- **Survival analysis in MSR:** code decay and comment/link rot studies (for methodological precedent).

---

## 3. Research questions

| RQ | Question | Study |
|---|---|---|
| **RQ1 Prevalence and dynamics** | What fraction of coding-agent memory about code is false at any point in time? Which claim types rot fastest? What predicts rot? | S1 (MSR, all file histories) |
| **RQ2 Harm** | Does stale memory change agent behaviour and outcomes? Which claim types matter? What is the dose-response? | S2 (controlled) + S3 (observational, AIDev) |
| **RQ3 Self-verification** | Do agents detect stale memory on their own, or when prompted Copilot-style? At what cost? | S2 traces + S4 conditions |
| **RQ4 Prevention** | Which freshness mechanism gives the best detection accuracy per unit cost, and which one recovers agent performance? | S4 (detection) + S5 (recovery) |

---

## 4. Claim model (the conceptual core, Section 3 of the paper)

A memory item (a line of a context file, an agent-written memory, a gloss, an episodic note) is split
into **atomic claims**. Every claim belongs to a class, and each class has its own validity oracle.

| Class | Examples | Deterministic oracle (Codexa) | Anchor (cheap re-check) |
|---|---|---|---|
| **Referential: path** | "Tests live in `tests/unit/`", "see `src/config.ts`" | path exists in the tree | file/tree anchor |
| **Referential: symbol** | "`AuthService.login` handles sessions" (the existence part) | symbol exists in the tree-sitter graph | symbols-index / symbol anchor |
| **Procedural: command** | "Run `pnpm test:unit`", "`make dev`" | script exists in package.json / pyproject / Makefile target / bin, *and* the package manager matches the lockfile | manifest anchors |
| **Dependency / version** | "Uses React 18", "Python ≥ 3.11" | manifest and lockfile values | manifest anchors |
| **Structural** | "`api/` calls into `core/` only", "X is called by Y" | graph query (imports, calls) | **query anchor, which is exact** |
| **Interface** | "`parse(text, *, strict)` returns a `Doc`" | signature header from the graph | normalised-AST / signature anchor |
| **Descriptive** | "`retry()` backs off exponentially" (LLM gloss) | none. Needs a judge, or a proxy (span + callee closure changed) | span + callee-closure anchor → cascade to the judge |
| **Convention / behavioural** | "Never import from `internal/`", "all handlers are async" | partly checkable (graph or AST rule); otherwise a judge | rule-compiled check (ContextCov-style) or the judge |
| **Episodic** | "Last migration broke CI because …" | historical, never false; can be *outdated* | anchors flag it, never delete it |

**Claim-class routing (method).** Validate each claim with the cheapest oracle that is *sound* for its
class. Deterministic oracles cover the referential, procedural, dependency, structural and interface
classes. For the descriptive and behavioural classes, a sound anchor prefilter (span plus
callee/import closure) decides *when* to ask an LLM claim judge (Anand-style prompt). Soundness follows
the safe-RTS argument: if a claim's truth is a function of its anchored views, then no anchor change
means no truth change. We state it as the memory analogue, citing Rothermel & Harrold and Mokhov
et al.; it is not a new theorem.

**The link to Chakrabarti's catastrophic remembering.** Instructions accumulate because deletion
needs a rationale. For an anchored claim, anchor death *is* that rationale. We measure what share of
real context-file content is anchorable, and therefore auto-prunable.

---

## 5. Studies

### S1 — Prevalence and dynamics in the wild (RQ1)

**Corpus.** Every repository with AGENTS.md, CLAUDE.md, `.github/copilot-instructions.md` or
`.cursor/rules/*`:
- the union of Baltes et al.'s Zenodo dataset, the Agent READMEs repositories, and a GitHub code
  search refresh;
- repositories with ≥ 50 commits after the file was created;
- target **3–5k repositories**.

**Claim extraction.**
- Deterministic parsers first: inline code spans, fenced commands, paths, identifiers and version
  strings.
- An LLM extractor for the residual prose, classified into the §4 classes.
- Human validation of 600 claims, double-annotated, reporting κ and extractor precision/recall per
  class.

**Rot tracking.**
- Replay each file's claims over **every** later commit (Codexa's replay harness), recording the
  first commit at which each claim's oracle fails, and whether the file was later fixed.
- Kaplan–Meier curves per claim class, plus a Cox model (covariates: churn, repository size,
  language, file age, number of contributors, agent tool).

**Outputs:**
- the stale share at a random point in time;
- the claim half-life per class;
- time-to-fix;
- the share of file lines that are anchorable (the catastrophic-remembering link).

**Validity.** Manual audit of 300 flagged stale claims (precision) and 300 unflagged ones
(recall estimate). Report DOCER on the same sample as the baseline.

### S2 — Controlled harm with dose-response (RQ2, RQ3)

**Tasks.**
- Real merged PRs as tasks (Lulla's design): pre-PR snapshot, PR description as the task, hidden
  tests or the PR's tests for grading.
- Draw from repositories in S1 that have a context file with ≥ 5 checkable claims.
- Prefer tasks created **after the models' training cutoffs**; add SWE-bench-Live-style tasks.
- Target **120 tasks / 30 repositories** (pilot: 30 tasks / 8 repositories).

**Conditions** (a paired design; the same task and the same seed across conditions):
- C0: no context file.
- C1: the current, accurate file (verified by our oracles, stale claims repaired).
- C2–C4: **rot doses**. Replace 1, 3, or all anchorable claims with their *historical stale values*
  mined from the repository's own history (an old command name, an old path, an old dependency
  version). These are realistic, not synthetic, perturbations.
- C5: **class-isolated rot**. Only commands, only paths, only structure or only conventions stale
  (which classes matter).
- C6: rot plus a **Copilot-style verification instruction** ("verify cited locations before relying
  on memory"), to measure self-verification (RQ3).

**Agents.**
- Harnesses: mini-SWE-agent (transparent, reproducible) and one production-style harness (OpenHands
  or Codexa JobManager).
- Models: two open-weight models and one frontier model. Run in Docker.

**Metrics:**
- resolve rate;
- tokens, wall time, rounds;
- **stale-induced actions**, parsed from traces: invoking a stale command, opening a missing path,
  editing a moved file, importing a removed symbol;
- recovery time after the first failure;
- verification actions.

**Statistics.**
- Mixed-effects logistic regression (task and repository random effects) for resolution.
- Negative binomial for tokens.
- Dose-response trend test.
- Pre-registered on OSF before the full run.

### S3 — Observational harm at scale (RQ2, triangulation)

- **Data:** AIDev agentic PRs whose repositories have a context file.
- **Exposure:** the number and classes of stale claims in the context file *at the PR's base commit*,
  computed with the S1 oracles.
- **Outcomes:** merged vs. rejected; review rounds; follow-up fix commits; CI failure on the first
  push.
- **Model:** mixed-effects logistic regression, controlling for agent, repository, PR size and
  repository activity. Add negative-control exposures: stale claims in files the agent never reads,
  such as the README of an unrelated subpackage.
- Report the result as association, and triangulate it with S2.

### S4 — Detection accuracy vs. cost (RQ4)

**Test sets:**
- (a) the S1 human-labelled claims across all classes;
- (b) Anand's released behavioural claim benchmark;
- (c) Codexa's structural replay set (already built).

**Methods:**

| # | Method |
|---|---|
| M0 | never invalidate |
| M1 | TTL-28d (Copilot) |
| M2 | file-changed heuristic (Codified Context / A2) |
| M3 | DOCER regex (Treude) |
| M4 | whole-file LLM auditor (claude-drift / agents-md-curator style) |
| M5 | per-claim LLM judge at every change (Anand A6) |
| M6 | agent-side just-in-time citation verification (Copilot) |
| **M7** | **ours: typed deterministic oracles + anchors + routing + cascade to M5 on the residual** |

**Metrics:**
- precision and recall per class;
- FIR (still-true claims wrongly discarded) and SSR (stale claims still served);
- LLM calls and tokens per 1k claims per 100 commits;
- latency at use time.

The headline is a **Pareto frontier of detection F1 against dollars**.

### S5 — Does prevention recover performance? (RQ4)

**Setting A: context files.**
- Rerun the rot conditions C2–C5 with each prevention method applied before the agent starts:
  - *flag*: annotate the stale claims;
  - *drop*: remove them;
  - *repair*: our deterministic repair where one exists (for example, renamed-path tracking through
    `git log --follow`, or the closest existing script), and an LLM repair otherwise.
- Metric: how much of the C1–C4 gap each method closes, and at what cost.

**Setting B: agent-written memory.**
- SWE-Bench-CL chronological sequences. Memory is written by the agent during earlier tasks (Codexa
  experience + procedural records, or Copilot-style cited facts). Later tasks run at later commits,
  so staleness occurs naturally.
- Conditions: M0 / M1 / M6 / M7.
- Metrics: resolve rate, stale-memory uses, and tokens.

---

## 6. Contributions (as they would appear in the paper)

1. **The first full-history, multi-class measurement of memory rot** in coding-agent context files:
   prevalence, half-life per claim class, predictors, fix latency, and the share of content that is
   auto-prunable.
2. **The first controlled evidence of harm**, with class-specific dose-response and a mechanistic
   trace analysis, triangulated with an observational analysis over agentic PRs in AIDev.
3. **Evidence on agent self-verification.** It rarely happens unprompted, and Copilot-style prompting
   recovers some performance at a measured cost.
4. **Claim-class routing with anchor-gated cascading.** It dominates the regex, TTL, whole-file LLM,
   per-claim LLM and just-in-time verification baselines on the detection-per-dollar frontier, and
   recovers most of the harm.
5. **Released artifacts:** the typed claim dataset with rot histories, the harm benchmark with rot
   doses, and the checker (CLI, CI action and agent hook, built on Codexa's graph).

---

## 7. What Codexa contributes, concretely

| Needed piece | Codexa status |
|---|---|
| Tree-sitter graph (paths, symbols, calls, imports) | ✅ `backend/repository/analyze.py` (fix the truncation first: `_MAX_SYMBOLS`) |
| Anchors (file, symbol, tree, index, query) and the sweep | ✅ `backend/memory/anchors.py` |
| Git replay harness | ✅ `tests/benchmarks/memory_anchoring/replay.py` |
| Manifest/script parsing (package.json, pyproject) | ✅ partial (`_read_manifest`); extend to Makefile, lockfile→package manager, requirements |
| Memory store with experience/procedural writes | ✅ for Setting B |
| Agent harness with traces | ✅ JobManager (plus mini-SWE-agent for neutrality) |
| **New:** claim extractor (deterministic + LLM residual) | ❌ build |
| **New:** per-class oracles (command resolvability, version checks, convention rules) | ❌ build |
| **New:** rot-dose injector (historical values from git) | ❌ build |
| **New:** trace parser for stale-induced actions | ❌ build |
| **New:** cascade to the claim judge (Anand prompt) | ❌ build |

---

## 8. Gates, fallbacks and risk register

| Gate | When | Pass | If it fails |
|---|---|---|---|
| **G0 Foundations** | week 1 | Truncation fixed; extractor precision ≥ 0.85 on 200 claims; oracles validated on 100 claims | Fix before any study |
| **G1 Prevalence** | week 3 | Always publishable (descriptive) | — |
| **G2 Harm pilot** | week 5 | A C4 vs. C1 effect on *any* primary metric (resolve, tokens or time) at p < 0.05, or ≥ 30% of runs with ≥ 1 stale-induced action | Rarely all null. If resolve and cost are both null but stale-induced actions occur, the finding is that agents absorb rot through self-correction, and the paper measures the tax. If everything is null, the paper becomes S1 + S4 (prevalence plus detection), framed as "rot is common but agents are robust — until X" |
| **G3 Cascade** | week 6 | On Anand's held-out split, M7 reaches ≥ 95% of M5's F1 with ≤ 35% of M5's LLM calls | Report the frontier honestly; deterministic classes stay a clear win; the residual classes become a limitation |
| **G4 Recovery** | week 8 | The best prevention closes ≥ 50% of the C4–C1 gap | Report which classes remain unrecoverable |

**Risk register:**

| Risk | Mitigation |
|---|---|
| **Being scooped.** Treude, Baltes and Lulla share authors and infrastructure, and RQ3 is their stated next step | Move fast on the S2 pilot. Differentiate through claim classes beyond references, full histories, the prevention method and agent-written memory (Setting B). Post a preprint as soon as S1 plus the S2 pilot are done |
| **Harm is small** (Gloaguen found context files barely matter) | Dose-response plus efficiency plus mechanistic traces; Lulla shows the effect of context files lives in efficiency |
| **Cost of the S2/S5 agent runs** | Pilot first. Mostly open-weight models via NIM. Cap rounds; cache |
| **Contamination** | Post-cutoff tasks; report per-model results |
| **Observational confounding in S3** | Negative controls, fixed effects, and presentation as triangulation only |

---

## 9. Compute and effort estimate

| Study | Runs / volume | Rough cost |
|---|---|---|
| S1 | 3–5k repositories × full histories. CPU-only replay, plus LLM extraction of residual claims (~200k claims × ~300 tokens) | ~60M tokens + CPU days |
| S2 pilot | 30 tasks × 5 conditions × 1 model × 2 seeds = 300 runs × ~80k tokens | ~25M tokens |
| S2 full | 120 × 8 × 3 models × 2 seeds ≈ 5.8k runs | ~450M tokens (mostly open-weight) |
| S3 | AIDev subset, CPU-only oracles | CPU |
| S4 | M4/M5/M6 LLM baselines on ~5k labelled claims | ~40M tokens |
| S5 | ~40% of S2 volume | ~180M tokens |

**Human annotation:** about 1,500 claims, double-coded, which is roughly 40 hours for two annotators.

---

## 10. Timeline (≈ 12 weeks)

| Week | Work |
|---|---|
| 1 | G0: analyzer truncation fix, claim extractor, per-class oracles; commit current work; download the Baltes Zenodo dataset, Anand's benchmark and the AIDev subset |
| 2–3 | S1 at scale plus the validation audit → **preprint-ready descriptive results** |
| 3–4 | Rot-dose injector, trace parser, harness in Docker; OSF pre-registration |
| 5 | S2 pilot → G2 |
| 5–6 | S4 detection (incl. Anand's benchmark) → G3 |
| 6–8 | S2 full, S3 observational |
| 8–9 | S5 recovery (Settings A and B) → G4 |
| 10–11 | Writing, figures, artifact packaging (Zenodo DOI) |
| 12 | Internal red-team review against §11; submit |

**Venue:** decide after G2. A full SE venue (ICSE/FSE/ASE) or the TOSEM/EMSE journals if everything
lands; MSR if it is mostly S1 + S4. Post the preprint at week 5–6 either way. Verify every CFP date;
none are assumed here.

---

## 11. Reviewer red-team (pre-empted)

| Attack | Pre-emption |
|---|---|
| "Treude & Baltes already measured context rot." | Theirs covers referential claims only, two snapshots, regex at 64% precision, and no harm. We cover 8 claim classes, full histories, validated oracles, harm and prevention, and we use DOCER as a baseline |
| "Lulla / Gloaguen already tested context files." | They test *presence*, we test *correctness*, holding presence fixed (C1 vs. C2–C5) |
| "The injected rot is artificial." | Stale values are the repository's own historical values; S3 adds naturally occurring rot; S1 gives the real distribution of rot, which we match |
| "An LLM judge (Anand) is better at detection." | It is included as M5. The cascade uses it where it is needed; the frontier shows the cost of using it everywhere |
| "Copilot already verifies citations." | M6 is evaluated publicly for the first time, including its cost and its miss rate under budget (cf. Nakayashiki) |
| "The oracles depend on your parser." | Parser coverage is reported; unparseable claims are routed to the judge, not counted as valid; the oracles are human-validated |
| "The anchor theory is just safe RTS." | We say so, and cite it. The contribution is routing across claim classes and the empirical frontier |
| "Observational S3 is confounded." | Presented only as triangulation, with negative controls |

---

## 12. What is dropped from earlier plans (and where it goes)

| Dropped | Where it goes |
|---|---|
| Budgeted gloss selection (C5) | A separate short paper later; Aider, Louis and defect prediction pre-empt most of it |
| Experiential memory as a contribution | Becomes Setting B's *testbed*, not a claim |
| Token-reduction multipliers | Gone |
| Quorum/debate | Gone |
| The structural replay benchmark | Becomes a test set in S4, not a headline |

## 13. Immediate next steps

1. Commit the current work (anchors, experience memory, policies, benchmarks, docs).
2. Fix analyzer truncation (make the caps configurable, fail the replay when truncated).
3. Pull the datasets: Baltes et al. on Zenodo (10.5281/zenodo.19375880), Anand's benchmark, and
   an AIDev subset.
4. Build the claim extractor plus per-class oracles, and validate them on 200 claims → gate G0.
5. Write the OSF pre-registration draft for S2.

## Sources (second pass)

- Treude & Baltes, *Context Rot* — https://arxiv.org/abs/2606.09090
- Lulla et al., *On the Impact of AGENTS.md Files…* — https://arxiv.org/abs/2601.20404
- Gloaguen et al., *Evaluating AGENTS.md* — https://arxiv.org/abs/2602.11988
- Chakrabarti, *Why Does CLAUDE.md Keep Growing?* — https://arxiv.org/abs/2608.11095
- Chatlatanagulchai et al., *Agent READMEs* — https://arxiv.org/abs/2511.12884
- Gao & Chen, *From Agent Behaviour to Agent-Friendly Documentation* — https://arxiv.org/abs/2608.20195
- Sharma, *ContextCov* — https://arxiv.org/abs/2603.00822
- Vasilopoulos, *Codified Context* — https://arxiv.org/abs/2602.20478
- *AIDev* — https://arxiv.org/abs/2602.09185
- *SWE-Bench-CL* — https://arxiv.org/abs/2507.00014
- *RepoAgent* — https://aclanthology.org/2024.emnlp-demo.46.pdf
- GitHub, *Building an agentic memory system for GitHub Copilot* — https://github.blog/ai-and-ml/github-copilot/building-an-agentic-memory-system-for-github-copilot/
- GitHub Docs, *About Copilot Memory* — https://docs.github.com/en/copilot/concepts/agents/copilot-memory
- Li et al., *RepoMirage* — https://arxiv.org/abs/2605.26177 (not about memory; checked and excluded)
- First-pass sources: see [`novelty_matrix.md`](novelty_matrix.md) §5.
