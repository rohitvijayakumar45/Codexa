# NavBench feature additions (post-freeze, 2026-10-08)

These features come from the review in `paper/forge/REVIEW_2026-10-08.md` (§5). **None of them
changes the frozen confirmatory configuration** (`FREEZE.md`). A default `nb.run` still runs exactly
the frozen arms with the frozen sampling. This was verified as follows:

- `results/features-local/equivalence_v1_frozen.txt`: 100 regenerated held-out rows. Facts and
  statuses are identical to `results/main/raw_results.tar.gz` for every frozen arm runnable here
  (rg0, rg3, lsp, codexa_refs, codexa_orig and T2). The only differences are token counts of rg and
  LSP, which come from operating-system path rendering (see "Caveats").
- All 260 generated fixture source files are byte-identical after the generator changes.

| # | Feature | Where | Research question it serves |
|---|---|---|---|
| **A** | Completeness-aware routing policies, evaluated model-free | `nb/policy.py` | Is there a policy (graph tool first, fallback only on observable weakness) that reaches baseline completeness at lower cost? |
| **B** | Common output form: the "minimal sufficient answer" (MSA) | `nb/forms.py`, `tok_msa_cl100k` in rows | Do token differences survive when information content is held fixed? |
| **C** | Adapter registry, plugins, `unsupported` rows, leaderboard | `nb/adapters.py`, `nb/leaderboard.py`, `ADAPTERS.md` | Can a third party add a tool without touching the harness, under the same fairness rules? |
| **D** | G1-v2: Codexa call resolution v2 and `find_references` v2 | `backend/repository/resolve_v2.py`, `backend/agents/tools.py`; arm `codexa2_*` | Do the measured G1 failure modes disappear when fixed, and does that transfer to real code? |
| **E** | T3 multi-hop callers (depth 2) | generator `edges` + gate, `score.t3_gold`, `t3()` on every adapter | Do graph tools gain anything on multi-hop questions, where their advantage is usually claimed? |

Supporting changes:
- `nb.offline` enriches old scored rows with gold callers and MSA tokens, with no tool runs.
- The fixture generator has an opt-in `fresh` split (seeds 200–215).
- The gate checks every T3 edge against the Python runtime trace and the TypeScript index.
- Several Windows portability fixes, all no-ops on POSIX: trace paths, rg paths, pyright URIs and
  drive-letter case, and the tsserver self-reference filter.

## How to run

```bash
# A + B on the frozen data (no tool runs; regenerate fixtures first: python -m nb.fixtures <repos>)
python -m nb.offline results/main/scored.jsonl.gz results/main <repos> enriched.jsonl
python -m nb.policy enriched.jsonl out/ --token-key tok_msa_cl100k --fallbacks rg0,lsp
python -m nb.leaderboard enriched.jsonl out/

# D + E on fresh fixtures (seeds never used while designing resolution v2)
python -m nb.fixtures <repos> --fresh
python -m nb.run fx-py-fresh-200 py fixture out/ --arms rg0,rg3,lsp,codexa,codexa2,cbm_cur --tasks T1,T2,T3
python -m nb.score out/ && python -m nb.leaderboard out/scored.jsonl out/lb
```

## Local results (Windows, no codebase-memory binaries; `results/features-local/`)

### D and E — fresh fixtures (seeds 200–215; 32 fixtures; 160 explicit-call targets)

| arm | T1 recall | T1 precision | T1 complete | T1 MSA tok | T3 recall | T3 complete | T3 MSA tok |
|---|---|---|---|---|---|---|---|
| **codexa2 (G1-v2)** | **1.00** | **1.00** | **100.0%** | 22 | **1.00** | **100.0%** | 31 |
| lsp | 0.97 | 0.64 | 90.0% | 32 | 0.98 | 90.0% | 42 |
| rg0 | 0.95 | 0.35 | 80.0% | 56 | 0.96 | 80.0% | 117 |
| codexa (G1, frozen v1) | 0.63 | 0.68 | 40.0% | 21 | 0.64 | 30.0% | 27 |

The held-out split gives the same numbers.

**Read this as a fix-verification test, not as evidence of quality.** The fixture generator produces
exactly the patterns that v2 was designed to handle. Fresh seeds guard only against seed-specific
overfitting, not against pattern-level overfitting.

### D on real code — httpx at the pinned commit, Layer C (runtime-observed callers, stored trace)

| arm | n | caller recall | precision | complete % | native tok | MSA tok |
|---|---|---|---|---|---|---|
| rg0 | 31 | 1.00 | 0.42 | 100.0 | 415 | 155 |
| lsp | 31 | 0.95 | 0.94 | 93.5 | 563* | 47 |
| **codexa2 (G1-v2)** | 31 | **0.76** | **0.98** | **71.0** | 83 | 27 |
| codexa (G1 frozen) | 31 | 0.64 | 0.75 | 54.8 | 68 | 37 |

G1-v2 improves G1 on real code: recall +0.12, precision +0.23, completeness +16 points. It still
trails lexical search and the language server. This is one repository and 31 targets; Python
targets were re-sampled locally (pyright fan-out on Windows), so these are not the frozen S-ind
targets.

### A — routing policies

| data | best deployable policy | complete % | tokens | compare |
|---|---|---|---|---|
| Frozen fixtures, native tokens | `route:cbm_cur>lsp@ambiguous` (lsp only when cbm reports ambiguity; fires 45%) | **100.0** | 280 | lsp 90.0% @ 236; rg0 80.0% @ 140; oracle 100% @ 120 |
| Frozen fixtures, MSA tokens | same | **100.0** | 36.5 | lsp 90.0% @ 31.4; cbm_cur 89.4% @ 21.0 |
| httpx Layer C, native | `route:codexa2_refs>rg0@weak` (fires 42%) | 100.0 | 403.5 | rg0 100% @ 415.0 — **no meaningful saving** |
| httpx Layer C, MSA | `single:lsp` | 93.5 | 47.5 | routing does not help in the common form |

Routing reaches *higher completeness* than any single tool on fixtures. On real code it saves
nothing over ripgrep at matched completeness. That is consistent with Q3 of the paper.

### B — common form

In MSA form, information content is identical for identical caller sets, and the ordering on
fixtures becomes: codexa2 22 < cbm_cur 21 ≈ codexa 21 < lsp 32 < rg0 56 tokens. The LSP-JSON
penalty disappears (LSP: 236 native → 32 MSA).

## Caveats (state these if any of this enters a paper)

1. **Absolute paths inflate LSP-JSON token counts.** The native LSP form embeds absolute file URIs,
   so its token count depends on where the corpus sits on disk: the frozen run used
   `/work/nb/repos/<name>`. In this Windows run the long scratch path roughly doubles LSP-native
   tokens (e.g. 296 → 596). The MSA and location forms are path-independent. This is a measurement
   artifact the paper should mention for Q1.
2. **rg native tokens** differ slightly on Windows, because rg prints backslash paths.
3. **codebase-memory arms were not run locally** (no binaries). Their T3 support (`trace_path`
   depth 2) is implemented but untested.
4. **G1-v2 was shaped on the held-out failure taxonomy.** Fixture numbers verify the fixes; only
   natural-repository numbers estimate quality.
5. **The LSP T3 arm** maps reference locations to enclosing declarations using the independent index
   (the information `documentSymbol` gives a client) and does not charge for it.
6. **The rg T3 arm** charges for every grep and file outline, so it is a deliberately complete,
   not minimal, lexical strategy.
