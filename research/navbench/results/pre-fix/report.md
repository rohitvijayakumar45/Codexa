
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
| codexa_refs | 128.6 [83.9, 205.0] | 128.9 [83.0, 199.3] | 6.65 [4.95, 9.46] | 29.02 [21.76, 40.31] | 2.86 [1.62, 5.13] | 0.90 [0.61, 1.39] |
| codexa_orig | 80.0 [48.3, 134.4] | 74.7 [46.7, 116.9] | 3.06 [2.23, 4.53] | 13.27 [10.07, 18.79] | 1.95 [1.25, 3.05] | 0.45 [0.31, 0.66] |
| cbm_cur | 42.6 [25.9, 72.1] | 59.9 [39.4, 90.2] | 3.10 [2.38, 4.13] | 13.36 [10.63, 17.02] | 1.83 [1.28, 2.73] | 0.44 [0.31, 0.64] |
| cbm_057 | 51.9 [31.6, 86.2] | 63.9 [38.6, 100.6] | 3.43 [2.63, 4.52] | 14.89 [11.65, 18.99] | 1.24 [0.76, 1.98] | 0.41 [0.29, 0.60] |

Ratios > 1 mean the baseline payload is larger than the graph arm's native output. Graph rows restricted to targets where the graph arm returned a non-empty answer.

## Q2 — natural repositories: S-ind vs S-cond
| arm | sample | n | non-empty % | agreement with LSP callers (Jaccard) | observed-call caller recall (py, layer C) | complete on observed calls % |
|---|---|---|---|---|---|---|
| rg0 | S-ind | 591 | 100.0 [100.0, 100.0] | 0.39 [0.32, 0.47] | 0.93 [0.85, 0.98] | 89.5 [81.2, 96.2] |
| rg0 | S-cond | 331 | 100.0 [100.0, 100.0] | 0.49 [0.42, 0.55] | 0.97 [0.92, 1.00] | 94.1 [87.5, 99.3] |
| rg3 | S-ind | 591 | 100.0 [100.0, 100.0] | 0.39 [0.32, 0.47] | 0.93 [0.85, 0.98] | 89.5 [80.9, 96.3] |
| rg3 | S-cond | 331 | 100.0 [100.0, 100.0] | 0.49 [0.42, 0.55] | 0.97 [0.93, 1.00] | 94.1 [87.7, 99.3] |
| lsp | S-ind | 591 | 81.5 [74.5, 87.8] | 1.00 [1.00, 1.00] | 0.68 [0.52, 0.82] | 58.8 [40.8, 75.9] |
| lsp | S-cond | 331 | 96.5 [93.5, 99.1] | 1.00 [1.00, 1.00] | 0.78 [0.59, 0.93] | 67.2 [47.5, 85.6] |
| codexa_refs | S-ind | 591 | 48.5 [39.2, 57.7] | 0.24 [0.17, 0.30] | 0.62 [0.48, 0.74] | 50.0 [35.0, 65.3] |
| codexa_refs | S-cond | 331 | 100.0 [100.0, 100.0] | 0.52 [0.44, 0.61] | 0.85 [0.78, 0.92] | 71.9 [61.2, 82.0] |
| codexa_orig | S-ind | 591 | 35.7 [25.6, 46.2] | 0.23 [0.16, 0.30] | 0.54 [0.39, 0.68] | 42.6 [26.2, 59.5] |
| codexa_orig | S-cond | 331 | 99.1 [97.6, 100.0] | 0.52 [0.43, 0.61] | 0.82 [0.74, 0.89] | 68.8 [58.5, 79.8] |
| cbm_cur | S-ind | 591 | 56.2 [48.2, 64.7] | 0.36 [0.29, 0.42] | 0.62 [0.50, 0.72] | 47.8 [33.6, 62.2] |
| cbm_cur | S-cond | 331 | 87.8 [78.9, 94.4] | 0.54 [0.46, 0.62] | 0.80 [0.69, 0.88] | 67.8 [55.9, 78.8] |
| cbm_057 | S-ind | 591 | 58.9 [50.1, 67.4] | 0.26 [0.20, 0.33] | 0.62 [0.52, 0.71] | 48.1 [36.0, 60.3] |
| cbm_057 | S-cond | 331 | 83.6 [73.6, 91.5] | 0.42 [0.35, 0.50] | 0.71 [0.58, 0.84] | 60.6 [46.8, 73.8] |

### Q2 — target presence in the Codexa graph by sample (natural)
| sample | targets | in Codexa graph % | with ≥1 incoming Codexa edge % | provider call fan-out = 0 % |
|---|---|---|---|---|
| S-ind | 591 | 83.8 [74.5, 91.5] | 36.7 [26.7, 47.2] | 39.3 [30.7, 47.9] |
| S-cond | 331 | 100.0 [100.0, 100.0] | 100.0 [100.0, 100.0] | n/a |

### Layer C — observed-call recall (Python natural repositories; targets with ≥1 observed call; both samples)
| arm | targets | caller recall | site recall | complete % |
|---|---|---|---|---|
| rg0 | 326 | 0.95 [0.90, 0.98] | 0.93 [0.88, 0.98] | 91.8 [85.3, 97.3] |
| rg3 | 326 | 0.95 [0.90, 0.98] | 0.93 [0.88, 0.97] | 91.8 [85.1, 96.9] |
| lsp | 326 | 0.73 [0.56, 0.87] | 0.72 [0.55, 0.86] | 63.3 [45.9, 79.6] |
| codexa_refs | 326 | 0.74 [0.67, 0.82] | n/a | 61.5 [53.2, 71.5] |
| codexa_orig | 326 | 0.68 [0.59, 0.78] | n/a | 55.7 [45.0, 67.6] |
| cbm_cur | 326 | 0.71 [0.62, 0.79] | n/a | 58.4 [48.7, 68.6] |
| cbm_057 | 326 | 0.66 [0.57, 0.75] | n/a | 54.7 [44.3, 65.8] |

### Exploratory — what predicts the rg0/graph payload ratio (natural S-ind, OLS with repository-cluster bootstrap)
- codexa_refs (n=292, repos=17): intercept=-0.25 [-0.53, 0.05]; log(1+name occurrences)=0.78 [0.68, 0.90]; log(1+provider fan-out)=-0.09 [-0.23, 0.02]; method=-0.17 [-0.44, 0.04]; class=-0.16 [-0.42, 0.08]
- cbm_cur (n=332, repos=17): intercept=-0.81 [-1.02, -0.55]; log(1+name occurrences)=0.76 [0.66, 0.82]; log(1+provider fan-out)=-0.10 [-0.18, -0.00]; method=-0.43 [-0.61, -0.27]; class=-0.08 [-0.28, 0.16]
