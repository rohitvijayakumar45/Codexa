# NavBench leaderboard

Repository-macro means. Tokens are cl100k. MSA = minimal sufficient answer (same information for every arm). ★ = Pareto-optimal on (native tokens, complete %).

## fixture · T1

| arm | n | recall | precision | complete % | native tok | loc tok | MSA tok | tok / complete | ★ |
|---|---|---|---|---|---|---|---|---|---|
| codexa2_refs | 320 | 1.00 | 1.00 | 100.0 | 73 | 20 | 22 | 73 | ★ |
| lsp | 320 | 0.97 | 0.64 | 90.0 | 236 | 39 | 32 | 262 |  |
| cbm_cur | 320 | 0.94 | 0.98 | 89.1 | 160 | 19 | 21 | 180 |  |
| rg0 | 320 | 0.95 | 0.35 | 80.0 | 140 | 65 | 56 | 176 |  |
| rg3 | 320 | 0.95 | 0.35 | 80.0 | 467 | 65 | 56 | 584 |  |
| cbm_057 | 320 | 0.70 | 0.91 | 49.1 | 69 | 14 | 16 | 141 | ★ |
| codexa_refs | 320 | 0.63 | 0.68 | 40.0 | 50 | 19 | 21 | 125 | ★ |
| codexa_orig | 320 | 0.47 | 1.00 | 40.0 | 94 | 7 | 7 | 235 |  |

## fixture · T2

| arm | n | hit % | precision | native tok |
|---|---|---|---|---|
| cbm_057_def | 320 | 100.0 | 0.76 | 99 |
| cbm_cur_def | 320 | 100.0 | 0.72 | 97 |
| codexa2_def | 320 | 100.0 | 0.69 | 45 |
| codexa_def | 320 | 100.0 | 0.69 | 38 |
| lsp_def | 320 | 100.0 | 1.00 | 57 |
| rg_def | 320 | 100.0 | 0.68 | 37 |

## fixture · T3

| arm | n | recall | precision | complete % | native tok | loc tok | MSA tok | tok / complete | ★ |
|---|---|---|---|---|---|---|---|---|---|
| codexa2_t3 | 320 | 1.00 | 1.00 | 100.0 | 102 | 28 | 31 | 102 | ★ |
| lsp_t3 | 320 | 0.98 | 0.72 | 90.0 | 402 | 62 | 42 | 447 |  |
| cbm_cur_t3 | 320 | 0.95 | 0.98 | 89.1 | 181 | 27 | 30 | 203 |  |
| rg0_t3 | 320 | 0.96 | 0.29 | 80.0 | 656 | 200 | 116 | 820 |  |
| codexa_t3 | 320 | 0.64 | 0.74 | 30.0 | 102 | 24 | 27 | 342 |  |

## natural · T1

| arm | n | recall | precision | complete % | native tok | loc tok | MSA tok | tok / complete | ★ |
|---|---|---|---|---|---|---|---|---|---|
| rg0 | 353 | 0.96 | 0.41 | 92.8 | 623 | 242 | 200 | 665 | ★ |
| rg3 | 353 | 0.96 | 0.41 | 92.8 | 2346 | 242 | 200 | 2539 |  |
| lsp | 353 | 0.80 | 0.70 | 74.0 | 502 | 100 | 98 | 700 | ★ |
| codexa_refs | 353 | 0.76 | 0.85 | 62.8 | 84 | 50 | 55 | 133 | ★ |
| cbm_cur | 353 | 0.72 | 0.86 | 60.3 | 174 | 53 | 59 | 295 |  |
| codexa2_refs | 353 | 0.69 | 0.93 | 58.5 | 93 | 35 | 38 | 161 |  |
| codexa_orig | 353 | 0.70 | 0.88 | 57.7 | 117 | 42 | 46 | 204 |  |
| cbm_057 | 353 | 0.67 | 0.73 | 56.6 | 160 | 56 | 62 | 284 |  |

## natural · T3

| arm | n | recall | precision | complete % | native tok | loc tok | MSA tok | tok / complete | ★ |
|---|---|---|---|---|---|---|---|---|---|
| codexa2_t3 | 992 | – | – | – | 151 | 54 | 60 | – |  |
| codexa_t3 | 992 | – | – | – | 168 | 66 | 73 | – |  |
| cbm_cur_t3 | 992 | – | – | – | 292 | 71 | 81 | – |  |
| lsp_t3 | 992 | – | – | – | 2673 | 456 | 204 | – |  |
| rg0_t3 | 992 | – | – | – | 17711 | 5192 | 1550 | – |  |
