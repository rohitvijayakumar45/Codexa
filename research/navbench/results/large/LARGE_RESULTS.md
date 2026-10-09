# Large-repository extension (falsification test), 2026-10-09

The protocol is frozen (`nb.run` defaults, same sampling, scoring and analysis). The repositories and the criteria
fixed before results are in `corpus.json` → `large_extension`. The layer-C traces used the frozen budgets
(300 s plain, 900 s traced). In that time the traced runs covered only **9%** (networkx) and **2%** (sqlalchemy)
of the test suites, so layer C has 29 targets. SQLAlchemy's untouched (plain) run crashed after 104 s in a compiled
extension.

Prediction tested: the rg/graph payload ratio grows with name frequency (elasticity ≈ 0.77 on the 17-repository
corpus), so graph tools should gain in large repositories. **The prediction fails, and the headline stands.**

| repo | frame decls | S-ind n | median name occurrences | G1 coverage | non-empty S-ind: cbm cur / G1 / LSP | rg/cbm-cur payload (n) | LSP-loc/cbm-cur |
|---|---|---|---|---|---|---|---|
| networkx | 8,294 | 39 | 14 | 44% | 67 / 44 / 87% | 3.56 (26) | 0.56 |
| sqlalchemy | 40,719 | 40 | 12.5 | 23% | 50 / 10 / 75% | 3.23 (20) | 0.57 |
| typeorm | 7,503 | 39 | 18 | 62% | 54 / 26 / 90% | 3.33 (21) | 1.25 |
| nest | 7,622 | 40 | 17.5 | 37% | 50 / 12 / 80% | 2.80 (20) | 0.34 |
| **pooled** (`analysis/report.md`) | | 158 | (17-repo corpus: 15) | | 55 / 23 / 83% | **3.22 [2.42, 4.46]** | 0.61 [0.36, 1.09] |

On the 17-repository corpus the same rg/cbm-cur ratio is 2.92 [2.29, 3.79].

- **Why the ratio does not grow:** independently sampled declarations in large repositories are not more
  ambiguous. The median name-occurrence count is 12.5–18, against 15 in the main corpus. The elasticity is
  unchanged (cbm current 0.73 [0.52, 0.88]).
- **Coverage gets worse.** Layer C caller recall (29 Python targets with observed calls):

  | tool | caller recall |
  |---|---|
  | rg -w | 0.78 [0.63, 0.92] |
  | language server | 0.67 [0.52, 0.85] |
  | cbm current | 0.42 [0.23, 0.62] |
  | cbm v0.5.x | 0.31 [0.16, 0.46] |
  | G1 | 0.19–0.21 |

- **G1** stops at its fixed symbol budget (4,000 symbols), so it indexes only 23–62% of the declarations.
- **S-cond → S-ind** (non-empty answers): G1 100 → 23%; cbm current 89 → 55%. Sampling conditioned on G1's edges
  inflates G1's coverage even more than in the small corpus.

Caveats: this run is exploratory, with 4 repositories, about 40 S-ind targets each, and partial traces.
