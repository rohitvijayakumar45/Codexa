# Supplementary robustness analyses (post hoc; not part of the frozen protocol)

## R1 Held-out fixtures, full workload (all 160 explicit-call targets, no completeness conditioning)
| arm | caller recall | caller precision | F1 (macro of per-target) | complete % | native tok | loc tok | src tok | native ratio to rg0, all non-empty targets |
|---|---|---|---|---|---|---|---|---|
| rg0 | 0.95 [0.93, 0.96] | 0.35 [0.34, 0.37] | 0.50 [0.49, 0.52] | 80.0 [73.8, 85.6] | 140 [131, 149] | 65 [60, 70] | 134 [127, 142] | 1.00 |
| rg3 | 0.95 [0.93, 0.97] | 0.35 [0.34, 0.37] | 0.50 [0.49, 0.52] | 80.0 [73.8, 86.2] | 465 [443, 490] | 65 [60, 70] | 134 [126, 142] | 3.42 [3.29, 3.54] |
| lsp | 0.97 [0.96, 0.99] | 0.64 [0.60, 0.68] | 0.74 [0.71, 0.76] | 90.0 [84.4, 95.0] | 236 [222, 250] | 39 [36, 41] | 86 [80, 93] | 1.70 [1.62, 1.78] |
| codexa_refs | 0.63 [0.56, 0.71] | 0.68 [0.61, 0.75] | 0.62 [0.55, 0.69] | 40.0 [30.6, 48.8] | 50 [45, 54] | 18 [16, 21] | n/a | 0.33 [0.31, 0.36] |
| codexa_orig | 0.47 [0.38, 0.55] | 1.00 [1.00, 1.00] | 0.50 [0.42, 0.58] | 40.0 [31.2, 48.8] | 94 [86, 102] | 6 [5, 8] | n/a | 0.63 [0.59, 0.67] |
| cbm_cur | 0.94 [0.91, 0.97] | 0.98 [0.97, 0.99] | 0.95 [0.92, 0.97] | 89.4 [83.1, 95.0] | 160 [144, 177] | 19 [16, 21] | n/a | 1.01 [0.93, 1.09] |
| cbm_057 | 0.71 [0.65, 0.77] | 0.90 [0.86, 0.94] | 0.74 [0.67, 0.80] | 49.4 [40.6, 58.1] | 70 [64, 77] | 15 [13, 17] | n/a | 0.46 [0.41, 0.50] |
Precision is caller-level: share of returned callers (or callers enclosing returned locations) that are true callers; an empty answer has undefined precision and is excluded from the precision mean. F1 counts an empty answer as 0.

## R2 Composition of the jointly-complete subsets (primary contrast, each arm vs rg0)
| arm | n jointly complete / 160 | py / ts | ambiguous names | patterns (count) |
|---|---|---|---|---|
| codexa_refs | 64 | 40 / 24 | 24 | decorated 32, reexp 16, svc 16 |
| codexa_orig | 64 | 40 / 24 | 24 | decorated 32, reexp 16, svc 16 |
| cbm_cur | 127 | 64 / 63 | 63 | M 32, decorated 32, reexp 31, svc 32 |
| cbm_057 | 79 | 48 / 31 | 39 | decorated 32, reexp 31, svc 16 |
| lsp | 128 | 64 / 64 | 64 | M 32, decorated 32, reexp 32, svc 32 |

Targets on which every arm is complete: 64 / 160.

## R3 Primary contrast by output form (jointly complete targets; ratio arm/rg0 in the same form)
| arm | native | common location form | source-enriched form |
|---|---|---|---|
| codexa_refs | 0.35 [0.33, 0.37] | 0.28 [0.27, 0.29] | n/a |
| codexa_orig | 0.65 [0.62, 0.67] | 0.28 [0.27, 0.29] | n/a |
| cbm_cur | 1.03 [0.94, 1.12] | 0.27 [0.26, 0.29] | n/a |
| cbm_057 | 0.58 [0.56, 0.62] | 0.24 [0.23, 0.26] | n/a |
| lsp | 1.75 [1.65, 1.85] | 0.63 [0.59, 0.67] | 0.65 [0.61, 0.69] |
Graph arms return callers, so their common form is one `file::qualified_name` per line and they have no source-enriched form; location arms list one `file:line:col` per returned location.

## R4 Strict caller credit for location arms
| arm | layer A caller recall (lenient → strict) | layer A precision (lenient → strict) | layer A complete % (lenient → strict) | layer C caller recall (lenient → strict) |
|---|---|---|---|---|
| rg0 | 0.95 [0.93, 0.96] → 0.95 [0.93, 0.96] | 0.35 [0.33, 0.37] → 0.35 [0.34, 0.37] | 80.0 [73.8, 86.2] → 80.0 [73.1, 86.2] | 0.95 [0.92, 0.98] → 0.94 [0.90, 0.97] |
| rg3 | 0.95 [0.93, 0.96] → 0.95 [0.93, 0.96] | 0.35 [0.34, 0.37] → 0.35 [0.34, 0.37] | 80.0 [73.1, 86.2] → 80.0 [73.8, 85.6] | 0.95 [0.92, 0.98] → 0.94 [0.90, 0.97] |
| lsp | 0.97 [0.96, 0.99] → 0.97 [0.96, 0.99] | 0.64 [0.60, 0.68] → 0.64 [0.60, 0.68] | 90.0 [84.4, 95.0] → 90.0 [83.8, 95.6] | 0.79 [0.64, 0.90] → 0.78 [0.63, 0.89] |

Primary contrast with rg0 (and lsp) completeness judged strictly:
| arm | n jointly complete | ratio arm/rg0 [95% CI] |
|---|---|---|
| codexa_refs | 64 | 0.35 [0.33, 0.37] |
| codexa_orig | 64 | 0.65 [0.62, 0.67] |
| cbm_cur | 127 | 1.03 [0.94, 1.13] |
| cbm_057 | 79 | 0.58 [0.56, 0.62] |
| lsp | 128 | 1.75 [1.65, 1.85] |

## R5 S-cond vs S-ind, adjusted for target composition (natural repositories)
Fan-out = number of call sites among the language server's references; buckets 0, 1–2, 3–9, ≥10. Post-stratified = S-cond cell means (repo × kind × fan-out bucket) weighted by the S-ind cell shares, over cells present in both samples.
| arm | non-empty: S-cond → S-ind | non-empty, fan-out ≥ 1 only | non-empty, S-cond post-stratified → S-ind (same cells) | observed-call recall: S-cond → S-ind | observed-call recall, S-cond post-stratified → S-ind (same cells) |
|---|---|---|---|---|---|
| rg0 | 100 → 100 | 100 → 100 | 100 → 100 (diff +0, 95% CI +0 to +0) | 0.97 → 0.95 | 0.96 → 0.97 (diff -0.00, 95% CI -0.04 to +0.05) |
| rg3 | 100 → 100 | 100 → 100 | 100 → 100 (diff +0, 95% CI +0 to +0) | 0.97 → 0.95 | 0.96 → 0.97 (diff -0.00, 95% CI -0.04 to +0.05) |
| lsp | 97 → 83 | 100 → 100 | 91 → 92 (diff -1, 95% CI -5 to +3) | 0.84 → 0.77 | 0.84 → 0.84 (diff +0.00, 95% CI -0.05 to +0.05) |
| codexa_refs | 100 → 54 | 100 → 72 | 100 → 68 (diff +32, 95% CI +21 to +41) | 0.85 → 0.70 | 0.84 → 0.71 (diff +0.13, 95% CI +0.00 to +0.27) |
| codexa_orig | 99 → 44 | 99 → 64 | 99 → 57 (diff +42, 95% CI +29 to +53) | 0.81 → 0.63 | 0.80 → 0.67 (diff +0.13, 95% CI -0.01 to +0.28) |
| cbm_cur | 88 → 60 | 90 → 84 | 80 → 71 (diff +9, 95% CI +2 to +17) | 0.79 → 0.66 | 0.79 → 0.70 (diff +0.08, 95% CI -0.02 to +0.18) |
| cbm_057 | 84 → 62 | 84 → 80 | 84 → 76 (diff +8, 95% CI -0 to +15) | 0.72 → 0.60 | 0.70 → 0.62 (diff +0.09, 95% CI -0.04 to +0.23) |

Sample composition: S-cond: n=331, fan-out 0 = 9%, median name occurrences = 9, fan-out buckets {'1-2': 155, '10-inf': 52, '0-0': 31, '3-9': 93}, kinds {'method': 111, 'function': 188, 'class': 32}; S-ind: n=661, fan-out 0 = 35%, median name occurrences = 15, fan-out buckets {'0-0': 231, '1-2': 195, '3-9': 128, '10-inf': 107}, kinds {'function': 302, 'class': 105, 'method': 254}

## R6 S-ind estimates with the recorded inclusion weights (natural repositories)
Weighted within each repository by the stratified-sampling inclusion weight, then averaged over repositories.
| arm | non-empty % unweighted | non-empty % weighted | observed-call recall unweighted | weighted |
|---|---|---|---|---|
| rg0 | 100.0 | 100.0 | 0.95 | 0.93 |
| rg3 | 100.0 | 100.0 | 0.95 | 0.93 |
| lsp | 83.1 | 78.5 | 0.77 | 0.71 |
| codexa_refs | 54.2 | 51.7 | 0.70 | 0.67 |
| codexa_orig | 43.8 | 39.6 | 0.63 | 0.59 |
| cbm_cur | 60.0 | 54.0 | 0.66 | 0.61 |
| cbm_057 | 62.4 | 60.0 | 0.60 | 0.56 |

## R7 Q1 on a common subset: S-ind targets where every graph arm answered (non-empty)
226 targets in 17 repositories (of 661 S-ind targets). Per-cell n of the main Table I (non-empty answers of that arm):
| graph arm | main-table n (targets / repos) | whole files | rg -w | LSP JSON | LSP loc. |
|---|---|---|---|---|---|
| codexa_refs | 358 / 17 | 131.62 [84.46, 204.78] | 4.73 [3.65, 6.45] | 4.17 [2.91, 5.90] | 0.86 [0.61, 1.22] |
| codexa_orig | 290 / 17 | 83.84 [53.92, 129.39] | 3.01 [2.31, 4.19] | 2.66 [1.89, 3.85] | 0.55 [0.39, 0.78] |
| cbm_cur | 395 / 17 | 68.72 [42.32, 115.20] | 2.47 [1.93, 3.31] | 2.18 [1.63, 2.93] | 0.45 [0.34, 0.60] |
| cbm_057 | 413 / 17 | 70.92 [45.08, 114.95] | 2.55 [2.06, 3.21] | 2.25 [1.64, 3.10] | 0.46 [0.34, 0.64] |

## R8 Layer C recall split by caller location (Python; each target once; both samples)
| arm | recall on test-file callers | recall on library callers | targets with library callers |
|---|---|---|---|
| rg0 | 0.95 [0.91, 0.99] | 0.94 [0.89, 0.98] | 228 |
| rg3 | 0.95 [0.91, 0.99] | 0.94 [0.89, 0.98] | 228 |
| lsp | 0.76 [0.52, 0.93] | 0.86 [0.78, 0.93] | 228 |
| codexa_refs | 0.70 [0.58, 0.81] | 0.76 [0.68, 0.84] | 228 |
| codexa_orig | 0.67 [0.55, 0.79] | 0.67 [0.56, 0.78] | 228 |
| cbm_cur | 0.63 [0.46, 0.80] | 0.73 [0.63, 0.82] | 228 |
| cbm_057 | 0.65 [0.51, 0.77] | 0.63 [0.51, 0.73] | 228 |
