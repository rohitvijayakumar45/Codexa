# NavBench leaderboard

Repository-macro means. Tokens are cl100k. MSA = minimal sufficient answer (same information for every arm). ★ = Pareto-optimal on (native tokens, complete %).

## fixture · T1

| arm | n | recall | precision | complete % | native tok | loc tok | MSA tok | tok / complete | ★ |
|---|---|---|---|---|---|---|---|---|---|
| codexa2_refs | 160 | 1.00 | 1.00 | 100.0 | 73 | 19 | 22 | 73 | ★ |
| lsp | 160 | 0.97 | 0.64 | 90.0 | 485 | 39 | 31 | 539 |  |
| rg0 | 160 | 0.95 | 0.35 | 80.0 | 145 | 65 | 55 | 181 |  |
| rg3 | 160 | 0.95 | 0.35 | 80.0 | 487 | 65 | 55 | 609 |  |
| codexa_refs | 160 | 0.63 | 0.68 | 40.0 | 50 | 18 | 21 | 124 | ★ |
| codexa_orig | 160 | 0.47 | 1.00 | 40.0 | 94 | 6 | 7 | 234 |  |

## fixture · T2

| arm | n | hit % | precision | native tok |
|---|---|---|---|---|
| codexa2_def | 160 | 100.0 | 0.69 | 44 |
| codexa_def | 160 | 100.0 | 0.69 | 38 |
| lsp_def | 160 | 100.0 | 1.00 | 118 |
| rg_def | 160 | 100.0 | 0.68 | 37 |

## fixture · T3

| arm | n | recall | precision | complete % | native tok | loc tok | MSA tok | tok / complete | ★ |
|---|---|---|---|---|---|---|---|---|---|
| codexa2_t3 | 160 | 1.00 | 1.00 | 100.0 | 102 | 27 | 31 | 102 | ★ |
| lsp_t3 | 160 | 0.98 | 0.72 | 90.0 | 828 | 61 | 42 | 920 |  |
| rg0_t3 | 160 | 0.96 | 0.29 | 80.0 | 669 | 199 | 115 | 836 |  |
| codexa_t3 | 160 | 0.64 | 0.74 | 30.0 | 102 | 24 | 26 | 340 |  |
