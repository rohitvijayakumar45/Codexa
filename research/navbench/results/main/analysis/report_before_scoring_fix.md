
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
| codexa_refs | 131.7 [85.0, 212.7] | 133.6 [84.3, 203.8] | 6.32 [4.63, 9.00] | 27.70 [20.81, 38.01] | 3.04 [1.69, 5.45] | 0.93 [0.63, 1.46] |
| codexa_orig | 84.8 [50.9, 139.9] | 82.5 [52.5, 131.3] | 3.00 [2.20, 4.43] | 13.13 [10.09, 18.12] | 2.18 [1.41, 3.27] | 0.49 [0.35, 0.72] |
| cbm_cur | 42.6 [26.1, 73.3] | 60.6 [40.4, 90.1] | 3.01 [2.28, 4.06] | 13.06 [10.20, 16.82] | 1.93 [1.33, 2.83] | 0.46 [0.33, 0.67] |
| cbm_057 | 54.4 [33.4, 89.9] | 67.9 [43.2, 104.4] | 3.54 [2.72, 4.67] | 15.45 [12.20, 19.77] | 1.31 [0.81, 2.15] | 0.44 [0.32, 0.62] |

Ratios > 1 mean the baseline payload is larger than the graph arm's native output. Graph rows restricted to targets where the graph arm returned a non-empty answer.

## Q2 — natural repositories: S-ind vs S-cond
| arm | sample | n | non-empty % | agreement with LSP callers (Jaccard) | observed-call caller recall (py, layer C) | complete on observed calls % |
|---|---|---|---|---|---|---|
| rg0 | S-ind | 585 | 100.0 [100.0, 100.0] | 0.41 [0.34, 0.48] | 0.94 [0.89, 0.98] | 90.9 [84.8, 96.2] |
| rg0 | S-cond | 331 | 100.0 [100.0, 100.0] | 0.51 [0.44, 0.57] | 0.97 [0.93, 1.00] | 94.1 [87.2, 99.3] |
| rg3 | S-ind | 585 | 100.0 [100.0, 100.0] | 0.41 [0.34, 0.48] | 0.94 [0.89, 0.98] | 90.9 [84.3, 96.3] |
| rg3 | S-cond | 331 | 100.0 [100.0, 100.0] | 0.51 [0.44, 0.57] | 0.97 [0.93, 1.00] | 94.1 [87.4, 99.4] |
| lsp | S-ind | 585 | 81.2 [74.1, 87.8] | 1.00 [1.00, 1.00] | 0.73 [0.59, 0.86] | 65.1 [49.9, 79.2] |
| lsp | S-cond | 331 | 97.4 [94.4, 99.4] | 1.00 [1.00, 1.00] | 0.84 [0.67, 0.97] | 79.2 [59.6, 93.9] |
| codexa_refs | S-ind | 585 | 47.3 [38.3, 55.9] | 0.24 [0.17, 0.31] | 0.65 [0.54, 0.76] | 52.7 [40.1, 66.5] |
| codexa_refs | S-cond | 331 | 100.0 [100.0, 100.0] | 0.54 [0.46, 0.62] | 0.85 [0.77, 0.91] | 71.2 [61.3, 81.2] |
| codexa_orig | S-ind | 585 | 35.6 [25.8, 45.3] | 0.23 [0.16, 0.31] | 0.57 [0.43, 0.71] | 45.8 [30.6, 61.1] |
| codexa_orig | S-cond | 331 | 99.1 [97.6, 100.0] | 0.54 [0.45, 0.63] | 0.81 [0.74, 0.89] | 67.4 [56.7, 79.1] |
| cbm_cur | S-ind | 585 | 56.0 [47.6, 63.6] | 0.36 [0.30, 0.43] | 0.61 [0.49, 0.72] | 48.7 [33.8, 62.5] |
| cbm_cur | S-cond | 331 | 87.5 [78.7, 94.1] | 0.56 [0.47, 0.63] | 0.79 [0.69, 0.88] | 68.5 [57.9, 77.7] |
| cbm_057 | S-ind | 585 | 59.2 [49.9, 68.7] | 0.27 [0.21, 0.34] | 0.57 [0.46, 0.68] | 46.0 [33.5, 58.7] |
| cbm_057 | S-cond | 331 | 83.9 [73.8, 91.8] | 0.44 [0.36, 0.52] | 0.72 [0.58, 0.84] | 60.5 [46.4, 73.8] |

### Q2 — target presence in the Codexa graph by sample (natural)
| sample | targets | in Codexa graph % | with ≥1 incoming Codexa edge % | provider call fan-out = 0 % |
|---|---|---|---|---|
| S-ind | 585 | 84.2 [75.6, 92.1] | 36.3 [25.7, 46.8] | 39.0 [30.4, 47.7] |
| S-cond | 331 | 100.0 [100.0, 100.0] | 100.0 [100.0, 100.0] | n/a |

### Layer C — observed-call recall (Python natural repositories; targets with ≥1 observed call; both samples)
| arm | targets | caller recall | site recall | complete % |
|---|---|---|---|---|
| rg0 | 323 | 0.95 [0.92, 0.98] | 0.94 [0.90, 0.97] | 92.5 [87.2, 97.0] |
| rg3 | 323 | 0.95 [0.92, 0.98] | 0.94 [0.90, 0.97] | 92.5 [87.3, 97.2] |
| lsp | 323 | 0.79 [0.64, 0.90] | 0.78 [0.62, 0.89] | 72.5 [57.1, 85.5] |
| codexa_refs | 323 | 0.75 [0.68, 0.82] | n/a | 61.9 [53.5, 71.1] |
| codexa_orig | 323 | 0.69 [0.61, 0.78] | n/a | 56.4 [45.3, 68.3] |
| cbm_cur | 323 | 0.70 [0.60, 0.79] | n/a | 58.9 [48.5, 68.9] |
| cbm_057 | 323 | 0.64 [0.53, 0.74] | n/a | 53.2 [41.7, 64.4] |

### Exploratory — what predicts the rg0/graph payload ratio (natural S-ind, OLS with repository-cluster bootstrap)
- codexa_refs (n=282, repos=17): intercept=-0.20 [-0.46, 0.09]; log(1+name occurrences)=0.75 [0.66, 0.88]; log(1+provider fan-out)=-0.09 [-0.22, 0.01]; method=-0.18 [-0.45, 0.04]; class=-0.15 [-0.49, 0.14]
- cbm_cur (n=329, repos=17): intercept=-0.78 [-1.01, -0.53]; log(1+name occurrences)=0.75 [0.66, 0.81]; log(1+provider fan-out)=-0.11 [-0.20, -0.01]; method=-0.38 [-0.59, -0.19]; class=-0.08 [-0.27, 0.19]
