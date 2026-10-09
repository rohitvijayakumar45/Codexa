# Combined Paper Plan — Context Providers for Coding Agents: Cheap, Complete, and Current?

Date: 2026-10-08. This merges two studies into one paper:

- the NavBench measurement study (`research/navbench`; the FORGE draft, review, features and
  `STRONG_PAPER_PLAN.md`);
- the Memory Rot study (`docs/research/strong_paper_design.md`; anchors, replay harness and
  experience memory in `backend/memory`, `tests/benchmarks/memory_anchoring`).

Decisions so far:
- one strong combined paper;
- heavy runs in the original NavBench environment;
- LLM budget sized after an agent pilot.

---

## 1. One thesis, not two papers stapled together

Coding agents are given repository context in two ways:

| Family | Examples | What vendors and papers report | What they don't |
|---|---|---|---|
| **On-demand context** (navigation tools) | grep, language servers, code-graph MCP tools | "N× fewer tokens" | **completeness**: does the answer contain all the call sites? |
| **Persisted context** (memory) | AGENTS.md / CLAUDE.md, agent memory (e.g. Copilot Memory), experience banks | "faster / fewer tokens" | **freshness**: is the context still true after the code moved? |

**Thesis.** Context for coding agents must be judged on **three axes at once — cost, completeness
and currency.** Measured that way:
1. the advertised savings of structural tools largely disappear at matched completeness (NavBench
   results);
2. persisted context rots measurably and misleads agents (Memory Rot);
3. **deterministic program structure pays off as a verifier and router, not as a substitute.** It
   decides when a cheap answer is incomplete (routing) and when remembered context is stale
   (anchors). It should not replace the evidence the agent needs.

Point 3 is the unifying claim. Both of its mechanisms already exist and are measured:
- the routing policies (NavBench feature A);
- code anchors with claim-class routing (backend/memory/anchors.py, the query/hybrid anchors).

**Working title:** *Cheap, Complete, and Current? Measuring the Context Coding Agents Are Given*

---

## 2. Research questions

| RQ | Question | Study | Status |
|---|---|---|---|
| **RQ1 Claims audit** | How do papers and tools evaluate context providers — and do they report completeness and freshness at all? | Systematic catalogue of ≥ 50 efficiency claims (both families), double-coded; re-measure 8–10 | new (desk work; can start now) |
| **RQ2 Cost vs. completeness** (on-demand) | How do baseline, sampling frame and output form move the ratio, and what do tools cost at matched completeness, including multi-hop? | NavBench at scale: ~30–40 repositories, 3–4 languages, 6–8 tools; fixtures + runtime + **human audit**; T1 + T3; MSA form | short-paper results + features exist; scale-up needs the environment |
| **RQ3 Currency** (persisted) | How fast does persisted context become false, by claim class? Which detection mechanism is accurate per dollar? | Memory Rot S1 (full-history claim tracking in context files) + S4 (deterministic oracles/anchors vs. regex, TTL, LLM auditor, claim-level LLM judge; plus Anand 2026's released benchmark) | anchors + replay harness exist; claim extractor and oracles to build |
| **RQ4 Agent impact** (unified) | Do completeness and currency deficits change agent outcomes, and do token savings survive end to end? | One agent harness with test-scored tasks; navigation × context conditions (§4) | pilot first |
| **RQ5 Structure as verifier** | Does structure add more value routing and verifying than substituting? | Routing policies (RQ2 data + agent cells) and anchor-gated freshness repair (RQ3 + agent cells), against the substitute-only conditions | mechanisms built |

---

## 3. Shared corpus (fixed by criteria before results)

Repositories that serve **both** halves:
- public, permissive licence;
- Python / TypeScript (plus Go if the language-server and graph tooling hold up);
- ≥ 300 commits;
- a test suite runnable from a checkout (Layer C and test-scored agent tasks);
- **a committed AGENTS.md / CLAUDE.md / copilot-instructions file**, for persisted context.

Target **30 repositories**, about 10 of them large. Keep the existing 17 NavBench repositories as a
subset where they qualify. Repositories without a context file still count for RQ2.

RQ3's in-the-wild prevalence analysis (S1) uses a much larger set: 3–5k repositories with context
files. It needs no agents.

---

## 4. The unified agent study (RQ4/RQ5) — the paper's centrepiece

**Harness.** mini-SWE-agent (neutral, transparent), tools exposed over MCP. Docker per task; pinned
models; three repetitions.

**Tasks** (generated from audited ground truth, scored by hidden tests):
- T-callers: change a function's signature and update every caller;
- T-rename: rename a symbol across files;
- T-build: a task whose success requires running the right build/test command (exercises the
  persisted context);
- a callers question scored against the audited gold.

**Conditions.** A fractional design — main effects plus the two key interactions, not the full
4 × 4 grid:

| Cell | Navigation available | Persisted context |
|---|---|---|
| N1 | rg only | accurate context file |
| N2 | rg + language server | accurate |
| N3 | rg + best graph tool (cbm current) | accurate |
| N4 | rg + routed graph (graph → fallback on weakness) | accurate |
| C0 | rg + LSP | none |
| C2 | rg + LSP | **stale** (historical values; rot doses from the repository's own history) |
| C3 | rg + LSP | stale + **anchor-verified** (stale claims flagged or dropped before the run) |
| C4 | rg + LSP | stale + Copilot-style "verify citations first" instruction |
| X1 | rg + graph | stale (does a graph tool rescue stale context?) |
| X2 | rg + routed graph | stale + anchor-verified (both verifier mechanisms on) |

**Metrics:**
- success;
- tokens-to-success;
- billed cost with prompt caching;
- turns;
- **stale-induced actions** (running a dead command, opening a moved path);
- missed call sites in the final diff.

**Analysis:**
- mixed-effects models with task and repository random effects;
- payload-level metrics from RQ2/RQ3 as predictors of agent outcomes (does the cheap benchmark
  predict the expensive one?).

**Pilot (approved: "pilot first"):**
- 20 tasks × cells {N1, N3, C0, C2, C3} × 1 open-weight model × 2 repetitions = 200 runs;
- outputs: variance, success range, and a size estimate for the full study.

---

## 5. Building blocks — status

| Block | Status | Remaining |
|---|---|---|
| NavBench harness, three label layers, frozen run | ✅ | scale corpus; Go adapters (optional) |
| Adapters / leaderboard / MSA / routing / T3 / G1-v2 (features A–E) | ✅ local | full run in the original environment |
| Code anchors (file/symbol/query/hybrid), sweep, replay harness | ✅ | claim-class oracles for context-file claims |
| Experience memory, memory-type ablation switch | ✅ | — |
| **Claims audit** (RQ1) | ❌ | coding scheme, sources, two coders |
| **Context-file claim extractor + per-class oracles** (RQ3) | ❌ | paths, commands, symbols, dependencies, structure; LLM residual |
| **Rot-dose injector** (historical values) | ❌ | from git history of the context file and the code |
| **Agent harness** (mini-SWE-agent + MCP wiring + task generator + hidden tests) | ❌ | the biggest build |
| **Human audit** (natural callers) | ❌ | 300 targets, two annotators |

---

## 6. Timeline (≈ 20 weeks) with gates and a split-fallback

| Weeks | Work | Gate |
|---|---|---|
| 1–2 | Commit; environment access; claims-audit scheme + pilot coding (κ); claim extractor + oracles on 5 repositories | **G1:** claims κ ≥ 0.7; oracle precision ≥ 0.85 |
| 3–4 | Agent harness + task generator; corpus selection; RQ3 S1 prevalence run | — |
| 5 | **Agent pilot** (200 runs, open models) | **G2:** success 20–80%; measurable variance → size the budget |
| 6–9 | RQ2 full NavBench run (scale + human audit) ‖ RQ3 detection study | **G3:** human-audit κ ≥ 0.7 |
| 10–14 | Full agent study (RQ4/RQ5) | — |
| 15–17 | Analysis, claims re-measurement | — |
| 18–20 | Writing; artifact (Docker, Zenodo); red-team | — |

**Split-fallback.** If G2 fails (agents insensitive or tasks unscorable), or the timeline slips past
week 12, split along the seam: NavBench (RQ1 + RQ2 + RQ5-routing) and Memory Rot (RQ3 +
RQ5-anchors). Each half stands alone; nothing is wasted.

**Venue.** The combined scope suits a journal (TOSEM / EMSE) or a full ICSE/FSE research-track paper
with a long appendix. Verify the CFPs. Skip FORGE for the short version unless the chosen venue's
policy explicitly allows a substantially extended follow-up.

---

## 7. Threats specific to combining

| Threat | Mitigation |
|---|---|
| "Two papers in one" | One thesis (cost × completeness × currency), one corpus, one agent harness, one statistical model; structure-as-verifier is the single claimed insight |
| Page budget | The main paper carries RQ1, RQ4, RQ5 and the headline tables of RQ2/RQ3; per-tool and per-class detail goes to the appendix |
| Authors' own tools (G1, anchors) | G1 frozen; G1-v2 and anchors evaluated on fresh seeds, natural code and Anand's external benchmark; every competitor adapter is public |
| Scoop risk (Treude/Baltes on context-rot harm) | Preprint the claims audit + RQ3 prevalence early (week ~8) |

---

## 8. Immediate next steps (no heavy environment needed)

1. Commit the current work in two commits (features; memory) — awaiting your OK.
2. **Environment access:** how to reach the original NavBench environment (where `/work/nb`
   lives — host or SSH, a cloud session, or a snapshot).
3. Start RQ1: coding scheme + collect candidate claims (papers + MCP tool READMEs).
4. Build the context-file claim extractor + oracles. Codexa's own AGENTS.md is the first test
   subject: it still claims Neo4j / Qdrant / Redis / MCP, which are not in the code.
5. Agent harness skeleton + task generator from NavBench fixtures, then the 200-run pilot on
   open-weight models.
