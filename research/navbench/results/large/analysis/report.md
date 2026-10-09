
## Layer A — held-out fixtures, T1 direct call sites (py); explicit-call targets only
| arm | n | caller recall | caller precision | complete-answer % | site recall | site precision | native tokens (mean) |
|---|---|---|---|---|---|---|---|

## Layer A — held-out fixtures, T1 direct call sites (ts); explicit-call targets only
| arm | n | caller recall | caller precision | complete-answer % | site recall | site precision | native tokens (mean) |
|---|---|---|---|---|---|---|---|

## Layer A — held-out fixtures, T1 direct call sites (all); explicit-call targets only
| arm | n | caller recall | caller precision | complete-answer % | site recall | site precision | native tokens (mean) |
|---|---|---|---|---|---|---|---|

### Layer A caller recall by pattern (held-out, both languages; mean over targets)
| arm |  |
|---|
| rg0 |  |
| rg3 |  |
| lsp |  |
| codexa_refs |  |
| codexa_orig |  |
| cbm_cur |  |
| cbm_057 |  |

### Layer A by name ambiguity (caller recall / precision, held-out, both languages)
- rg0: 
- rg3: 
- lsp: 
- codexa_refs: 
- codexa_orig: 
- cbm_cur: 
- cbm_057: 

### PRIMARY: tokens at matched quality (held-out fixtures; targets where both arms are complete at caller level)
| graph arm | n jointly complete | jointly-complete share | geo-mean tokens graph/rg0 [95% CI] |
|---|---|---|---|
| codexa_refs | 0 | 0/0 | n/a |
| codexa_orig | 0 | 0/0 | n/a |
| cbm_cur | 0 | 0/0 | n/a |
| cbm_057 | 0 | 0/0 | n/a |
| lsp | 0 | 0/0 | n/a |

## Layer A — T2 definition lookup (held-out fixtures)
| arm | n | hit rate | precision | native tokens |
|---|---|---|---|---|

## Q1 — natural repositories: payload ratio of each baseline to each graph arm (repo-macro geometric mean, S-ind)
| graph arm | whole-file (graph-selected, original method) | whole-file (provider-selected) | rg -w (k=0) | rg -C3 | LSP JSON | LSP loc form |
|---|---|---|---|---|---|---|
| codexa_refs | 131.1 [64.5, 254.8] | 108.6 [29.1, 328.2] | 21.90 [5.55, 106.84] | 110.14 [30.91, 523.67] | 1.21 [0.22, 4.81] | 0.87 [0.49, 2.00] |
| codexa_orig | 82.6 [53.9, 142.1] | 60.5 [31.6, 96.9] | 3.40 [1.48, 12.78] | 18.44 [8.33, 62.74] | 0.47 [0.04, 2.22] | 0.36 [0.22, 0.64] |
| cbm_cur | 28.8 [12.7, 65.2] | 88.6 [33.0, 205.4] | 3.22 [2.42, 4.46] | 16.33 [12.24, 22.80] | 2.21 [1.33, 3.65] | 0.61 [0.36, 1.09] |
| cbm_057 | 47.6 [25.7, 86.2] | 105.6 [47.4, 218.5] | 4.18 [2.95, 5.96] | 21.02 [14.87, 30.73] | 1.53 [0.77, 3.20] | 0.64 [0.42, 1.10] |

Ratios > 1 mean the baseline payload is larger than the graph arm's native output. Graph rows restricted to targets where the graph arm returned a non-empty answer.

## Q2 — natural repositories: S-ind vs S-cond
| arm | sample | n | non-empty % | agreement with LSP callers (Jaccard) | observed-call caller recall (py, layer C) | complete on observed calls % |
|---|---|---|---|---|---|---|
| rg0 | S-ind | 158 | 100.0 [100.0, 100.0] | 0.41 [0.29, 0.54] | 0.84 [0.70, 0.96] | 73.2 [50.6, 92.9] |
| rg0 | S-cond | 80 | 100.0 [100.0, 100.0] | 0.45 [0.32, 0.59] | 0.81 [0.53, 1.00] | 66.7 [16.7, 100.0] |
| rg3 | S-ind | 158 | 100.0 [100.0, 100.0] | 0.41 [0.30, 0.55] | 0.84 [0.68, 0.96] | 73.2 [50.0, 92.9] |
| rg3 | S-cond | 80 | 100.0 [100.0, 100.0] | 0.45 [0.32, 0.59] | 0.81 [0.53, 1.00] | 66.7 [16.7, 100.0] |
| lsp | S-ind | 158 | 83.0 [74.3, 90.5] | 1.00 [1.00, 1.00] | 0.69 [0.49, 0.85] | 50.6 [23.8, 75.0] |
| lsp | S-cond | 80 | 92.5 [83.8, 98.8] | 1.00 [1.00, 1.00] | 0.78 [0.47, 1.00] | 61.1 [11.1, 100.0] |
| codexa_refs | S-ind | 158 | 22.9 [10.6, 39.0] | 0.10 [0.01, 0.22] | 0.07 [0.00, 0.29] | 7.1 [0.0, 28.6] |
| codexa_refs | S-cond | 80 | 100.0 [100.0, 100.0] | 0.58 [0.47, 0.69] | 0.75 [0.42, 1.00] | 61.1 [11.1, 100.0] |
| codexa_orig | S-ind | 158 | 12.1 [1.9, 25.0] | 0.10 [0.01, 0.22] | 0.07 [0.00, 0.29] | 7.1 [0.0, 28.6] |
| codexa_orig | S-cond | 80 | 96.2 [87.5, 100.0] | 0.55 [0.44, 0.66] | 0.72 [0.33, 1.00] | 61.1 [11.1, 100.0] |
| cbm_cur | S-ind | 158 | 55.1 [45.3, 65.7] | 0.38 [0.29, 0.47] | 0.37 [0.13, 0.60] | 35.1 [12.5, 58.3] |
| cbm_cur | S-cond | 80 | 88.8 [78.8, 96.2] | 0.64 [0.53, 0.75] | 0.69 [0.28, 1.00] | 61.1 [11.1, 100.0] |
| cbm_057 | S-ind | 158 | 61.4 [48.8, 74.9] | 0.29 [0.20, 0.39] | 0.23 [0.07, 0.42] | 15.5 [0.0, 32.7] |
| cbm_057 | S-cond | 80 | 92.5 [86.2, 97.5] | 0.52 [0.38, 0.65] | 0.69 [0.28, 1.00] | 61.1 [11.1, 100.0] |

### Q2 — target presence in the Codexa graph by sample (natural)
| sample | targets | in Codexa graph % | with ≥1 incoming Codexa edge % | provider call fan-out = 0 % |
|---|---|---|---|---|
| S-ind | 158 | 38.1 [22.7, 56.3] | 13.4 [2.5, 27.6] | 33.4 [23.1, 44.5] |
| S-cond | 80 | 100.0 [100.0, 100.0] | 100.0 [100.0, 100.0] | n/a |

### Layer C — observed-call recall (Python natural repositories; targets with ≥1 observed call; both samples, each target once)
| arm | targets | caller recall | site recall | complete % |
|---|---|---|---|---|
| rg0 | 29 | 0.78 [0.63, 0.92] | 0.76 [0.61, 0.92] | 63.5 [40.6, 88.5] |
| rg3 | 29 | 0.78 [0.64, 0.92] | 0.76 [0.61, 0.92] | 63.5 [37.5, 88.5] |
| lsp | 29 | 0.67 [0.52, 0.85] | 0.66 [0.48, 0.84] | 46.4 [21.9, 73.1] |
| codexa_refs | 29 | 0.21 [0.00, 0.43] | n/a | 13.2 [0.0, 28.1] |
| codexa_orig | 29 | 0.19 [0.00, 0.41] | n/a | 13.2 [0.0, 28.1] |
| cbm_cur | 29 | 0.42 [0.23, 0.62] | n/a | 35.6 [15.6, 59.6] |
| cbm_057 | 29 | 0.31 [0.16, 0.46] | n/a | 20.9 [6.2, 38.0] |

### Exploratory — what predicts the rg0/graph payload ratio (natural S-ind, OLS with repository-cluster bootstrap)
- codexa_refs (n=36, repos=4): intercept=-0.75 [-1.18, 0.05]; log(1+name occurrences)=0.89 [0.77, 1.05]; log(1+provider fan-out)=-0.13 [-0.35, 0.10]; method=0.15 [-0.63, 0.39]; class=-0.17 [-0.74, 0.43]
- cbm_cur (n=87, repos=4): intercept=-0.87 [-1.18, -0.63]; log(1+name occurrences)=0.73 [0.52, 0.88]; log(1+provider fan-out)=-0.11 [-0.26, 0.10]; method=-0.18 [-0.49, 0.28]; class=0.14 [-0.08, 0.54]
