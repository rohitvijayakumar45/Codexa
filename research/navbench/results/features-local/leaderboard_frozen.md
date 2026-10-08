# NavBench leaderboard

Repository-macro means. Tokens are cl100k. MSA = minimal sufficient answer (same information for every arm). ★ = Pareto-optimal on (native tokens, complete %).

## fixture · T1

| arm | n | recall | precision | complete % | native tok | loc tok | MSA tok | tok / complete | ★ |
|---|---|---|---|---|---|---|---|---|---|
| lsp | 160 | 0.97 | 0.64 | 90.0 | 236 | 39 | – | 262 | ★ |
| cbm_cur | 160 | 0.94 | 0.98 | 89.4 | 160 | 19 | – | 179 | ★ |
| rg0 | 160 | 0.95 | 0.35 | 80.0 | 140 | 65 | – | 175 | ★ |
| rg3 | 160 | 0.95 | 0.35 | 80.0 | 465 | 65 | – | 582 |  |
| cbm_057 | 160 | 0.71 | 0.90 | 49.4 | 70 | 15 | – | 143 | ★ |
| codexa_refs | 160 | 0.63 | 0.68 | 40.0 | 50 | 18 | – | 124 | ★ |
| codexa_orig | 160 | 0.47 | 1.00 | 40.0 | 94 | 6 | – | 234 |  |

## fixture · T2

| arm | n | hit % | precision | native tok |
|---|---|---|---|---|
| cbm_057_def | 160 | 100.0 | 0.76 | 98 |
| cbm_cur_def | 160 | 100.0 | 0.72 | 97 |
| codexa_def | 160 | 100.0 | 0.69 | 38 |
| lsp_def | 160 | 100.0 | 1.00 | 57 |
| rg_def | 160 | 100.0 | 0.68 | 37 |

## natural · T1

| arm | n | recall | precision | complete % | native tok | loc tok | MSA tok | tok / complete | ★ |
|---|---|---|---|---|---|---|---|---|---|
| rg0 | 323 | 0.95 | 0.41 | 92.5 | 638 | 250 | – | 697 | ★ |
| rg3 | 323 | 0.95 | 0.41 | 92.5 | 2412 | 250 | – | 2636 |  |
| lsp | 323 | 0.79 | 0.69 | 72.5 | 514 | 102 | – | 725 | ★ |
| codexa_refs | 323 | 0.75 | 0.84 | 61.9 | 84 | 50 | – | 136 | ★ |
| cbm_cur | 323 | 0.70 | 0.86 | 58.9 | 177 | 55 | – | 303 |  |
| codexa_orig | 323 | 0.69 | 0.87 | 56.4 | 117 | 43 | – | 208 |  |
| cbm_057 | 323 | 0.64 | 0.72 | 53.2 | 169 | 59 | – | 320 |  |
