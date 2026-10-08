# NavBench v2 run (CLOUD_HANDOFF.md §1), 2026-10-08

## Setup
- Environment: the original `/work/nb` (Linux), same pinned tools and corpus as the frozen run.
- Fixtures were regenerated: the held-out split (seeds 100–115) plus the opt-in `fresh` split (seeds 200–215). `nb.gate_fixtures` passes, including the new T3 edge checks.
- Command, per repository and one at a time:
  `nb.run <repo> <lang> <layer> /work/nb/out-v2 --arms rg0,rg3,lsp,codexa,codexa2,cbm_cur,cbm_057 --tasks T1,T2,T3`
- Jobs: 81 in total (64 fixtures and 17 natural repositories). All finished, and no gate messages fired.
- Scoring uses the (declaration, sample)-keyed `nb.score` (the S-ind scoring fix; see FREEZE.md).
- Files here:
  - `scored.jsonl.gz` and `raw_results.tar.gz`;
  - meta and targets per repository;
  - `lb/`: leaderboard;
  - `policy/`: routing policies, layers A and C, MSA tokens;
  - `equivalence.json`.

## Reproduction of the frozen run (`nb.equivalence out-main out-v2`)
The re-run drew the **same targets**: all 1,216 frozen T1 rows are matched. Per arm:

| arm | rows | identical facts | identical native tokens |
|---|---|---|---|
| rg0, rg3, lsp | 1,216 each | 100% | 100% |
| rg_def, lsp_def, codexa_def, cbm_*_def | 160 each | 100% | 100% |
| cbm_cur | 1,216 | 1,212 | 1,212 |
| cbm_057 | 1,216 | 1,163 | 1,168 |
| codexa_refs | 1,216 | 1,209 | 1,209 |
| codexa_orig | 1,216 | 1,178 | 1,166 |

- **codebase-memory:** the differences match its own run-to-run variation, as measured in `results/main/supplement_cbm_versions`: v0.5.x 5.3%, current 0.4%.
- **G1 (frozen v1):** every one of the 45 differing rows is **truncated in both runs** (output caps of 10 or 30 entries). The tool returns a different subset of callers once it hits a cap, so G1 is not deterministic under truncation. All non-truncated G1 rows are identical. This is a G1 defect to state as a threat; it does not change the frozen analysis.

## Leaderboard (repository-macro means; `lb/leaderboard.md`)

**Fixtures, T1** (320 explicit-call targets; held-out and fresh pooled):

| arm | recall | precision | complete % | native tok | MSA tok |
|---|---|---|---|---|---|
| codexa2 (G1-v2) | 1.00 | 1.00 | 100.0 | 73 | 22 |
| lsp | 0.97 | 0.64 | 90.0 | 236 | 32 |
| cbm_cur | 0.94 | 0.98 | 89.1 | 160 | 21 |
| rg0 | 0.95 | 0.35 | 80.0 | 140 | 56 |
| cbm_057 | 0.70 | 0.91 | 49.1 | 69 | 16 |
| codexa (G1 v1) | 0.63 | 0.68 | 40.0 | 50 | 21 |

**Fixtures, T3 (depth-2 callers):**

| arm | complete % | MSA tok |
|---|---|---|
| codexa2 | 100 | 31 |
| lsp | 90 | 42 |
| cbm_cur | 89 | 30 |
| rg0 | 80 | 116 |
| codexa v1 | 30 | 27 |

**Natural code, T1, layer C** (runtime-observed callers; Python; 353 rows over both samples):

| arm | recall | precision | complete % | native tok | MSA tok |
|---|---|---|---|---|---|
| rg0 | 0.96 | 0.41 | 92.8 | 623 | 200 |
| lsp | 0.80 | 0.70 | 74.0 | 502 | 98 |
| codexa (G1 v1) | 0.76 | 0.85 | 62.8 | 84 | 55 |
| cbm_cur | 0.72 | 0.86 | 60.3 | 174 | 59 |
| **codexa2 (G1-v2)** | **0.69** | **0.93** | **58.5** | 93 | 38 |
| codexa_orig | 0.70 | 0.88 | 57.7 | 117 | 46 |
| cbm_057 | 0.67 | 0.73 | 56.6 | 160 | 62 |

## Finding 1: G1-v2's fixture perfection does not transfer to real code
- On fixtures G1-v2 is perfect (T1 and T3).
- On natural code its runtime-observed recall is **lower than v1's** (0.69 vs 0.76), with higher precision (0.93 vs 0.85).
- The local single-repository pilot (httpx: v2 better) did not generalise.

Per repository (layer C caller recall, v1 → v2):

| repo | v1 → v2 recall | v1 → v2 precision |
|---|---|---|
| httpx | 0.64 → 0.76 | 0.75 → 0.98 |
| jinja | 0.74 → 0.80 | 0.89 → 0.93 |
| rich | 0.77 → 0.81 | 0.90 → 0.91 |
| boltons | 0.73 → 0.77 | 0.72 → 0.89 |
| toolz | 0.81 → 0.79 | 0.94 → 0.94 |
| itsdangerous | 0.72 → 0.71 | 0.87 → 0.96 |
| attrs | 0.71 → 0.68 | 0.84 → 0.94 |
| **marshmallow** | **0.67 → 0.42** | 0.77 → 0.88 |
| **more-itertools** | **0.94 → 0.34** | 0.90 → 0.84 |

v2 loses at least half of v1's recall on 44 targets. Two failure modes were found by probing them; neither appears in the fixtures:
1. **Star re-exports.** `more_itertools/__init__.py` does `from .more import *`, and tests call `mi.chunked_even(...)`. v2 cannot resolve the module attribute through the star import, so it returns "References: (none found in graph)". v1 matched by bare name.
2. **Calls dispatched to overrides.** In marshmallow, code calls `self._deserialize(...)` or `field._deserialize(...)` on a base-typed receiver. At runtime the subclass override (e.g. `Enum._deserialize`) runs, but v2 binds the call statically to the base `Field._deserialize`, so the override's query returns no callers.

These are exactly the pattern-level overfitting risk that FEATURES.md caveat 4 warned about: fixture numbers verify fixes, and only natural-code numbers estimate quality.

## Finding 2: routing does not beat ripgrep on real code (policy/, MSA tokens)
**Layer A (fixtures):**
- `single:codexa2` is already complete (100% at 22 tokens), so routing adds nothing.
- Without v2, `route:cbm_cur>lsp@ambiguous` reaches 100% at 36.6 tokens, against lsp at 90% for 31.5 and rg0 at 80% for 55.7.

**Layer C (runtime-observed, 323 targets):**
- rg0 is complete on 92.5% of targets at 207 tokens.
- Every policy that matches this always falls back, and so costs more (245–415 tokens).
- The best weak-triggered routes trade completeness for tokens:

  | policy | complete % | tokens |
  |---|---|---|
  | codexa2>rg0@weak | 81.5 | 135 |
  | cbm_cur>rg0@weak | 79.3 | 128 |

- The label-using oracle (92.5% at 85 tokens) shows the potential, but no deployable trigger captures it.
- This is consistent with paper Q3: on real code, no saving at matched completeness.
