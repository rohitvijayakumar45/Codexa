
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
| codexa_refs | 118.1 [53.6, 217.0] | 86.6 [43.9, 171.2] | 10.23 [4.55, 25.37] | 46.27 [20.70, 104.78] | 2.31 [1.29, 4.59] | 0.74 [0.46, 1.54] |
| codexa_orig | 58.7 [24.1, 131.8] | 55.6 [23.0, 116.9] | 3.88 [2.09, 8.93] | 18.33 [10.07, 41.14] | 1.57 [0.79, 3.02] | 0.44 [0.28, 0.81] |
| cbm_cur | 57.1 [23.8, 110.7] | 71.1 [37.3, 131.7] | 3.98 [2.29, 8.42] | 17.97 [10.94, 34.23] | 1.73 [1.07, 2.97] | 0.43 [0.29, 0.74] |
| cbm_057 | 71.0 [36.4, 122.4] | 88.8 [48.4, 153.6] | 5.36 [2.80, 11.08] | 23.78 [13.05, 45.21] | 1.26 [0.64, 2.53] | 0.47 [0.29, 0.81] |

Ratios > 1 mean the baseline payload is larger than the graph arm's native output. Graph rows restricted to targets where the graph arm returned a non-empty answer.

## Q2 — natural repositories: S-ind vs S-cond
| arm | sample | n | non-empty % | agreement with LSP callers (Jaccard) | observed-call caller recall (py, layer C) | complete on observed calls % |
|---|---|---|---|---|---|---|
| rg0 | S-ind | 118 | 100.0 [100.0, 100.0] | 0.30 [0.24, 0.36] | n/a | n/a |
| rg0 | S-cond | 60 | 100.0 [100.0, 100.0] | 0.40 [0.32, 0.48] | n/a | n/a |
| rg3 | S-ind | 118 | 100.0 [100.0, 100.0] | 0.30 [0.24, 0.37] | n/a | n/a |
| rg3 | S-cond | 60 | 100.0 [100.0, 100.0] | 0.40 [0.32, 0.49] | n/a | n/a |
| lsp | S-ind | 118 | 83.0 [70.9, 93.2] | 1.00 [1.00, 1.00] | n/a | n/a |
| lsp | S-cond | 60 | 95.0 [83.3, 100.0] | 1.00 [1.00, 1.00] | n/a | n/a |
| codexa_refs | S-ind | 118 | 48.4 [36.2, 60.7] | 0.23 [0.12, 0.36] | n/a | n/a |
| codexa_refs | S-cond | 60 | 100.0 [100.0, 100.0] | 0.53 [0.42, 0.67] | n/a | n/a |
| codexa_orig | S-ind | 118 | 33.1 [17.1, 51.8] | 0.21 [0.07, 0.37] | n/a | n/a |
| codexa_orig | S-cond | 60 | 98.3 [93.3, 100.0] | 0.49 [0.38, 0.62] | n/a | n/a |
| cbm_cur | S-ind | 118 | 60.9 [48.7, 72.5] | 0.38 [0.29, 0.49] | n/a | n/a |
| cbm_cur | S-cond | 60 | 76.7 [61.7, 90.0] | 0.55 [0.41, 0.69] | n/a | n/a |
| cbm_057 | S-ind | 118 | 64.4 [53.8, 74.7] | 0.31 [0.21, 0.41] | n/a | n/a |
| cbm_057 | S-cond | 60 | 81.7 [70.0, 93.3] | 0.43 [0.29, 0.61] | n/a | n/a |

### Q2 — target presence in the Codexa graph by sample (natural)
| sample | targets | in Codexa graph % | with ≥1 incoming Codexa edge % | provider call fan-out = 0 % |
|---|---|---|---|---|
| S-ind | 118 | 81.4 [68.7, 94.9] | 34.8 [20.3, 51.3] | 33.9 [21.4, 45.8] |
| S-cond | 60 | 100.0 [100.0, 100.0] | 100.0 [100.0, 100.0] | n/a |

### Layer C — observed-call recall (Python natural repositories; targets with ≥1 observed call; both samples)
| arm | targets | caller recall | site recall | complete % |
|---|---|---|---|---|

### Exploratory — what predicts the rg0/graph payload ratio (natural S-ind, OLS with repository-cluster bootstrap)
- codexa_refs (n=57, repos=3): intercept=-0.40 [-0.65, -0.15]; log(1+name occurrences)=0.77 [0.68, 1.03]; log(1+provider fan-out)=-0.08 [-0.32, 0.06]; method=0.40 [-0.44, 0.44]; class=-0.39 [-0.41, 0.00]
- cbm_cur (n=72, repos=3): intercept=-0.69 [-1.01, -0.54]; log(1+name occurrences)=0.63 [0.52, 0.69]; log(1+provider fan-out)=0.09 [-0.26, 0.39]; method=-0.12 [-0.86, 0.27]; class=0.26 [0.22, 0.96]
