
## Layer A — held-out fixtures, T1 direct call sites (py); explicit-call targets only
| arm | n | caller recall | caller precision | complete-answer % | site recall | site precision | native tokens (mean) |
|---|---|---|---|---|---|---|---|
| rg0 | 80 | 0.95 [0.93, 0.97] | 0.35 [0.33, 0.38] | 80.0 [71.2, 88.8] | 0.95 [0.93, 0.97] | 0.29 [0.27, 0.31] | 140 [128, 153] |
| rg3 | 80 | 0.95 [0.93, 0.97] | 0.35 [0.33, 0.38] | 80.0 [71.2, 88.8] | 0.95 [0.93, 0.97] | 0.29 [0.27, 0.31] | 468 [434, 504] |
| lsp | 80 | 0.95 [0.93, 0.97] | 0.67 [0.61, 0.73] | 80.0 [70.0, 88.8] | 0.95 [0.93, 0.97] | 0.55 [0.50, 0.61] | 224 [208, 239] |
| codexa_refs | 80 | 0.73 [0.64, 0.81] | 0.73 [0.64, 0.82] | 50.0 [38.8, 62.5] | n/a | n/a | 54 [48, 59] |
| codexa_orig | 80 | 0.57 [0.46, 0.67] | 1.00 [1.00, 1.00] | 50.0 [37.5, 61.3] | n/a | n/a | 97 [88, 108] |
| cbm_cur | 80 | 1.00 [1.00, 1.00] | 0.96 [0.94, 0.98] | 100.0 [100.0, 100.0] | n/a | n/a | 162 [137, 187] |
| cbm_057 | 80 | 0.82 [0.76, 0.87] | 0.95 [0.93, 0.97] | 60.0 [48.8, 70.0] | n/a | n/a | 77 [69, 86] |

## Layer A — held-out fixtures, T1 direct call sites (ts); explicit-call targets only
| arm | n | caller recall | caller precision | complete-answer % | site recall | site precision | native tokens (mean) |
|---|---|---|---|---|---|---|---|
| rg0 | 80 | 0.95 [0.93, 0.97] | 0.35 [0.33, 0.38] | 80.0 [70.0, 87.5] | 0.95 [0.93, 0.97] | 0.30 [0.28, 0.31] | 140 [127, 151] |
| rg3 | 80 | 0.95 [0.93, 0.97] | 0.35 [0.33, 0.38] | 80.0 [70.0, 88.8] | 0.95 [0.93, 0.97] | 0.30 [0.28, 0.31] | 462 [431, 497] |
| lsp | 80 | 1.00 [1.00, 1.00] | 0.62 [0.57, 0.67] | 100.0 [100.0, 100.0] | 1.00 [1.00, 1.00] | 0.48 [0.46, 0.50] | 247 [226, 269] |
| codexa_refs | 80 | 0.53 [0.44, 0.63] | 0.63 [0.52, 0.74] | 30.0 [18.8, 41.2] | n/a | n/a | 46 [39, 52] |
| codexa_orig | 80 | 0.37 [0.27, 0.47] | 1.00 [1.00, 1.00] | 30.0 [20.0, 41.2] | n/a | n/a | 90 [79, 101] |
| cbm_cur | 80 | 0.89 [0.83, 0.94] | 1.00 [1.00, 1.00] | 78.8 [70.0, 87.5] | n/a | n/a | 158 [137, 181] |
| cbm_057 | 80 | 0.60 [0.51, 0.69] | 0.85 [0.77, 0.91] | 38.8 [28.7, 50.0] | n/a | n/a | 64 [54, 74] |

## Layer A — held-out fixtures, T1 direct call sites (all); explicit-call targets only
| arm | n | caller recall | caller precision | complete-answer % | site recall | site precision | native tokens (mean) |
|---|---|---|---|---|---|---|---|
| rg0 | 160 | 0.95 [0.93, 0.97] | 0.35 [0.34, 0.37] | 80.0 [73.8, 85.6] | 0.95 [0.93, 0.96] | 0.29 [0.28, 0.31] | 140 [131, 149] |
| rg3 | 160 | 0.95 [0.93, 0.97] | 0.35 [0.34, 0.37] | 80.0 [73.1, 86.2] | 0.95 [0.93, 0.97] | 0.29 [0.28, 0.31] | 465 [441, 490] |
| lsp | 160 | 0.97 [0.96, 0.99] | 0.64 [0.60, 0.68] | 90.0 [84.4, 95.0] | 0.97 [0.96, 0.99] | 0.52 [0.48, 0.55] | 236 [222, 249] |
| codexa_refs | 160 | 0.63 [0.56, 0.71] | 0.68 [0.60, 0.75] | 40.0 [31.2, 49.4] | n/a | n/a | 50 [45, 54] |
| codexa_orig | 160 | 0.47 [0.38, 0.55] | 1.00 [1.00, 1.00] | 40.0 [31.2, 49.4] | n/a | n/a | 94 [86, 102] |
| cbm_cur | 160 | 0.94 [0.91, 0.97] | 0.98 [0.97, 0.99] | 89.4 [83.1, 95.0] | n/a | n/a | 160 [143, 178] |
| cbm_057 | 160 | 0.71 [0.64, 0.78] | 0.90 [0.86, 0.94] | 49.4 [40.6, 57.5] | n/a | n/a | 70 [64, 77] |

### Layer A caller recall by pattern (held-out, both languages; mean over targets)
| arm | M | decorated | direct | dyn | hof | reexp | svc |
|---|---|---|---|---|---|---|---|
| rg0 | 1.00 | 1.00 | 0.75 | – | – | 1.00 | 1.00 |
| rg3 | 1.00 | 1.00 | 0.75 | – | – | 1.00 | 1.00 |
| lsp | 1.00 | 1.00 | 0.88 | – | – | 1.00 | 1.00 |
| codexa_refs | 0.67 | 1.00 | 0.50 | – | – | 0.50 | 0.50 |
| codexa_orig | 0.33 | 1.00 | 0.00 | – | – | 0.50 | 0.50 |
| cbm_cur | 1.00 | 1.00 | 0.75 | – | – | 0.97 | 1.00 |
| cbm_057 | 0.33 | 1.00 | 0.75 | – | – | 0.97 | 0.50 |

### Layer A by name ambiguity (caller recall / precision, held-out, both languages)
- rg0: unique: R=0.95 P=0.38; ambiguous: R=0.95 P=0.32
- rg3: unique: R=0.95 P=0.38; ambiguous: R=0.95 P=0.32
- lsp: unique: R=0.97 P=0.64; ambiguous: R=0.97 P=0.64
- codexa_refs: unique: R=0.73 P=0.83; ambiguous: R=0.53 P=0.54
- codexa_orig: unique: R=0.57 P=1.00; ambiguous: R=0.37 P=1.00
- cbm_cur: unique: R=0.95 P=0.98; ambiguous: R=0.94 P=0.98
- cbm_057: unique: R=0.72 P=0.91; ambiguous: R=0.70 P=0.91

### PRIMARY: tokens at matched quality (held-out fixtures; targets where both arms are complete at caller level)
| graph arm | n jointly complete | jointly-complete share | geo-mean tokens graph/rg0 [95% CI] |
|---|---|---|---|
| codexa_refs | 64 | 64/160 | 0.35 [0.33, 0.37] |
| codexa_orig | 64 | 64/160 | 0.65 [0.62, 0.67] |
| cbm_cur | 127 | 127/160 | 1.03 [0.94, 1.13] |
| cbm_057 | 79 | 79/160 | 0.58 [0.56, 0.62] |
| lsp | 128 | 128/160 | 1.75 [1.65, 1.85] |

## Layer A — T2 definition lookup (held-out fixtures)
| arm | n | hit rate | precision | native tokens |
|---|---|---|---|---|
| lsp_def | 160 | 100.0 [100.0, 100.0] | 1.00 [1.00, 1.00] | 57 [57, 58] |
| rg_def | 160 | 100.0 [100.0, 100.0] | 0.68 [0.62, 0.73] | 37 [32, 41] |
| codexa_def | 160 | 100.0 [100.0, 100.0] | 0.69 [0.64, 0.75] | 38 [35, 42] |
| cbm_cur_def | 160 | 100.0 [100.0, 100.0] | 0.72 [0.66, 0.78] | 97 [91, 103] |
| cbm_057_def | 160 | 100.0 [100.0, 100.0] | 0.76 [0.70, 0.82] | 98 [90, 107] |

## Q1 — natural repositories: payload ratio of each baseline to each graph arm (repo-macro geometric mean, S-ind)
| graph arm | whole-file (graph-selected, original method) | whole-file (provider-selected) | rg -w (k=0) | rg -C3 | LSP JSON | LSP loc form |
|---|---|---|---|---|---|---|
| codexa_refs | 139.3 [92.5, 216.1] | 140.9 [94.7, 212.1] | 6.01 [4.59, 8.11] | 26.63 [20.87, 35.54] | 3.10 [1.89, 5.26] | 0.88 [0.63, 1.29] |
| codexa_orig | 85.6 [54.5, 133.4] | 89.2 [59.6, 135.7] | 3.27 [2.49, 4.49] | 14.46 [11.37, 18.95] | 2.46 [1.66, 3.66] | 0.54 [0.39, 0.76] |
| cbm_cur | 48.0 [30.4, 80.0] | 63.8 [43.1, 94.7] | 2.92 [2.30, 3.83] | 12.78 [10.26, 16.24] | 1.92 [1.36, 2.77] | 0.45 [0.33, 0.62] |
| cbm_057 | 60.8 [39.0, 94.4] | 73.5 [47.5, 109.5] | 3.54 [2.80, 4.56] | 15.55 [12.62, 19.76] | 1.46 [0.95, 2.22] | 0.46 [0.34, 0.63] |

Ratios > 1 mean the baseline payload is larger than the graph arm's native output. Graph rows restricted to targets where the graph arm returned a non-empty answer.

## Q2 — natural repositories: S-ind vs S-cond
| arm | sample | n | non-empty % | agreement with LSP callers (Jaccard) | observed-call caller recall (py, layer C) | complete on observed calls % |
|---|---|---|---|---|---|---|
| rg0 | S-ind | 661 | 100.0 [100.0, 100.0] | 0.42 [0.36, 0.50] | 0.95 [0.90, 0.98] | 91.9 [86.0, 96.8] |
| rg0 | S-cond | 331 | 100.0 [100.0, 100.0] | 0.51 [0.44, 0.57] | 0.97 [0.93, 1.00] | 94.1 [87.6, 99.2] |
| rg3 | S-ind | 661 | 100.0 [100.0, 100.0] | 0.42 [0.36, 0.49] | 0.95 [0.90, 0.98] | 91.9 [86.4, 96.8] |
| rg3 | S-cond | 331 | 100.0 [100.0, 100.0] | 0.51 [0.44, 0.57] | 0.97 [0.93, 1.00] | 94.1 [87.4, 99.3] |
| lsp | S-ind | 661 | 83.1 [76.2, 88.8] | 1.00 [1.00, 1.00] | 0.77 [0.63, 0.87] | 70.3 [56.3, 82.1] |
| lsp | S-cond | 331 | 97.4 [94.4, 99.7] | 1.00 [1.00, 1.00] | 0.84 [0.66, 0.97] | 79.2 [61.7, 94.8] |
| codexa_refs | S-ind | 661 | 54.2 [46.6, 61.2] | 0.30 [0.22, 0.36] | 0.70 [0.61, 0.79] | 56.5 [46.2, 67.9] |
| codexa_refs | S-cond | 331 | 100.0 [100.0, 100.0] | 0.54 [0.46, 0.62] | 0.85 [0.77, 0.91] | 71.2 [61.1, 81.1] |
| codexa_orig | S-ind | 661 | 43.8 [35.2, 52.2] | 0.29 [0.21, 0.35] | 0.63 [0.51, 0.74] | 50.7 [38.0, 64.6] |
| codexa_orig | S-cond | 331 | 99.1 [97.6, 100.0] | 0.54 [0.45, 0.63] | 0.81 [0.74, 0.89] | 67.4 [56.8, 78.7] |
| cbm_cur | S-ind | 661 | 60.0 [52.8, 66.8] | 0.40 [0.33, 0.46] | 0.66 [0.56, 0.75] | 54.1 [41.9, 66.1] |
| cbm_cur | S-cond | 331 | 87.5 [78.5, 94.3] | 0.56 [0.47, 0.64] | 0.79 [0.69, 0.88] | 68.5 [58.3, 78.5] |
| cbm_057 | S-ind | 661 | 62.4 [53.4, 71.1] | 0.30 [0.24, 0.36] | 0.60 [0.50, 0.69] | 49.4 [38.6, 60.5] |
| cbm_057 | S-cond | 331 | 83.9 [74.3, 92.1] | 0.44 [0.36, 0.52] | 0.72 [0.58, 0.84] | 60.5 [45.6, 74.6] |

### Q2 — target presence in the Codexa graph by sample (natural)
| sample | targets | in Codexa graph % | with ≥1 incoming Codexa edge % | provider call fan-out = 0 % |
|---|---|---|---|---|
| S-ind | 661 | 86.4 [78.9, 93.3] | 44.7 [36.0, 53.2] | 34.8 [27.0, 42.5] |
| S-cond | 331 | 100.0 [100.0, 100.0] | 100.0 [100.0, 100.0] | n/a |

### Layer C — observed-call recall (Python natural repositories; targets with ≥1 observed call; both samples, each target once)
| arm | targets | caller recall | site recall | complete % |
|---|---|---|---|---|
| rg0 | 323 | 0.95 [0.92, 0.98] | 0.94 [0.90, 0.97] | 92.5 [87.6, 96.9] |
| rg3 | 323 | 0.95 [0.92, 0.98] | 0.94 [0.90, 0.97] | 92.5 [87.2, 97.2] |
| lsp | 323 | 0.79 [0.65, 0.90] | 0.78 [0.63, 0.89] | 72.5 [57.5, 85.1] |
| codexa_refs | 323 | 0.75 [0.68, 0.82] | n/a | 61.9 [53.3, 70.9] |
| codexa_orig | 323 | 0.69 [0.61, 0.78] | n/a | 56.4 [46.3, 68.1] |
| cbm_cur | 323 | 0.70 [0.60, 0.78] | n/a | 58.9 [48.7, 68.8] |
| cbm_057 | 323 | 0.64 [0.54, 0.74] | n/a | 53.2 [41.6, 65.1] |

### Exploratory — what predicts the rg0/graph payload ratio (natural S-ind, OLS with repository-cluster bootstrap)
- codexa_refs (n=358, repos=17): intercept=-0.22 [-0.41, 0.00]; log(1+name occurrences)=0.77 [0.69, 0.87]; log(1+provider fan-out)=-0.09 [-0.23, -0.00]; method=-0.12 [-0.36, 0.06]; class=-0.11 [-0.41, 0.14]
- cbm_cur (n=395, repos=17): intercept=-0.82 [-0.99, -0.61]; log(1+name occurrences)=0.77 [0.69, 0.81]; log(1+provider fan-out)=-0.12 [-0.20, -0.03]; method=-0.37 [-0.56, -0.18]; class=-0.06 [-0.24, 0.19]
