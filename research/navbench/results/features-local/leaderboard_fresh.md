# NavBench leaderboard

Repository-macro means. Tokens are cl100k. MSA = minimal sufficient answer (same information for every arm). ★ = Pareto-optimal on (native tokens, complete %).

## fixture · T1

| arm | n | recall | precision | complete % | native tok | loc tok | MSA tok | tok / complete | ★ |
|---|---|---|---|---|---|---|---|---|---|
| codexa2_refs | 160 | 1.00 | 1.00 | 100.0 | 73 | 20 | 22 | 73 | ★ |
| lsp | 160 | 0.97 | 0.64 | 90.0 | 486 | 39 | 32 | 540 |  |
| rg0 | 160 | 0.95 | 0.35 | 80.0 | 146 | 65 | 56 | 182 |  |
| rg3 | 160 | 0.95 | 0.35 | 80.0 | 491 | 65 | 56 | 613 |  |
| codexa_refs | 160 | 0.63 | 0.68 | 40.0 | 50 | 19 | 21 | 125 | ★ |
| codexa_orig | 160 | 0.47 | 1.00 | 40.0 | 94 | 7 | 7 | 235 |  |

## fixture · T2

| arm | n | hit % | precision | native tok |
|---|---|---|---|---|
| codexa2_def | 160 | 100.0 | 0.69 | 45 |
| codexa_def | 160 | 100.0 | 0.69 | 39 |
| lsp_def | 160 | 100.0 | 1.00 | 118 |
| rg_def | 160 | 100.0 | 0.68 | 37 |

## fixture · T3

| arm | n | recall | precision | complete % | native tok | loc tok | MSA tok | tok / complete | ★ |
|---|---|---|---|---|---|---|---|---|---|
| codexa2_t3 | 160 | 1.00 | 1.00 | 100.0 | 103 | 28 | 31 | 103 | ★ |
| lsp_t3 | 160 | 0.98 | 0.72 | 90.0 | 828 | 62 | 42 | 920 |  |
| rg0_t3 | 160 | 0.96 | 0.29 | 80.0 | 674 | 202 | 117 | 843 |  |
| codexa_t3 | 160 | 0.64 | 0.74 | 30.0 | 103 | 24 | 27 | 343 |  |
