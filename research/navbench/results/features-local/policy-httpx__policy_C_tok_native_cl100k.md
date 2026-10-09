## Routing policies — layer C, tokens = `tok_native_cl100k` (31 targets)

| policy | recall | complete % [95% CI] | mean tokens [95% CI] | tokens / complete answer | fallback fired % | Pareto |
|---|---|---|---|---|---|---|
| oracle | 1.00 | 100.0 [100.0, 100.0] | 202.4 [107.8, 328.5] | 202.4 | – |  |
| route:codexa2_refs>rg0@ambiguous | 1.00 | 100.0 [100.0, 100.0] | 403.5 [213.2, 627.7] | 403.5 | 41.9 | ★ |
| route:codexa2_refs>rg0@weak | 1.00 | 100.0 [100.0, 100.0] | 403.5 [218.8, 618.5] | 403.5 | 41.9 | ★ |
| single:rg0 | 1.00 | 100.0 [100.0, 100.0] | 415.0 [246.4, 596.6] | 415.0 | – |  |
| route:rg0>lsp@empty | 1.00 | 100.0 [100.0, 100.0] | 415.0 [247.6, 604.0] | 415.0 | 0.0 |  |
| route:rg0>lsp@ambiguous | 1.00 | 100.0 [100.0, 100.0] | 415.0 [245.0, 596.7] | 415.0 | 0.0 |  |
| route:rg0>lsp@unresolved | 1.00 | 100.0 [100.0, 100.0] | 415.0 [257.6, 604.4] | 415.0 | 0.0 |  |
| route:rg0>lsp@weak | 1.00 | 100.0 [100.0, 100.0] | 415.0 [256.1, 611.4] | 415.0 | 0.0 |  |
| route:codexa_refs>rg0@always | 1.00 | 100.0 [100.0, 100.0] | 483.3 [311.2, 683.0] | 483.3 | 100.0 |  |
| route:codexa2_refs>rg0@always | 1.00 | 100.0 [100.0, 100.0] | 498.1 [331.4, 707.9] | 498.1 | 100.0 |  |
| route:rg0>lsp@always | 1.00 | 100.0 [100.0, 100.0] | 977.8 [642.3, 1399.1] | 977.8 | 100.0 |  |
| route:lsp>rg0@always | 1.00 | 100.0 [100.0, 100.0] | 977.8 [631.5, 1422.9] | 977.8 | 100.0 |  |
| route:lsp>rg0@empty | 0.99 | 96.8 [90.3, 100.0] | 586.8 [345.1, 880.8] | 606.4 | 3.2 |  |
| route:lsp>rg0@weak | 0.99 | 96.8 [90.3, 100.0] | 586.8 [341.4, 880.4] | 606.4 | 3.2 |  |
| route:codexa2_refs>lsp@ambiguous | 0.95 | 93.5 [83.9, 100.0] | 360.9 [145.3, 672.5] | 385.8 | 41.9 | ★ |
| route:codexa2_refs>lsp@weak | 0.95 | 93.5 [83.9, 100.0] | 360.9 [146.4, 652.9] | 385.8 | 41.9 | ★ |
| single:lsp | 0.95 | 93.5 [83.9, 100.0] | 562.8 [310.7, 866.7] | 601.6 | – |  |
| route:lsp>rg0@ambiguous | 0.95 | 93.5 [83.9, 100.0] | 562.8 [311.7, 876.1] | 601.6 | 0.0 |  |
| route:lsp>rg0@unresolved | 0.95 | 93.5 [83.9, 100.0] | 562.8 [304.3, 841.1] | 601.6 | 0.0 |  |
| route:codexa_refs>lsp@always | 0.95 | 93.5 [83.9, 100.0] | 631.1 [370.5, 926.5] | 674.6 | 100.0 |  |
| route:codexa2_refs>lsp@always | 0.95 | 93.5 [83.9, 100.0] | 645.8 [396.4, 947.8] | 690.4 | 100.0 |  |
| route:codexa2_refs>rg0@empty | 0.92 | 87.1 [74.2, 96.8] | 241.2 [111.8, 396.8] | 276.9 | 16.1 | ★ |
| route:codexa2_refs>lsp@empty | 0.89 | 83.9 [71.0, 96.8] | 190.6 [84.2, 373.6] | 227.2 | 16.1 | ★ |
| single:codexa2_refs | 0.76 | 71.0 [54.8, 87.1] | 83.0 [62.6, 107.0] | 117.0 | – | ★ |
| route:codexa2_refs>rg0@unresolved | 0.76 | 71.0 [54.8, 87.1] | 83.0 [63.0, 106.2] | 117.0 | 0.0 | ★ |
| route:codexa2_refs>lsp@unresolved | 0.76 | 71.0 [54.8, 87.1] | 83.0 [63.4, 106.4] | 117.0 | 0.0 | ★ |
| route:codexa_refs>rg0@empty | 0.80 | 71.0 [54.8, 87.1] | 130.0 [73.7, 210.0] | 183.2 | 16.1 |  |
| route:codexa_refs>rg0@weak | 0.80 | 71.0 [54.8, 87.1] | 130.0 [71.8, 216.6] | 183.2 | 16.1 |  |
| route:codexa_refs>lsp@empty | 0.80 | 71.0 [54.8, 83.9] | 186.9 [81.5, 373.5] | 263.4 | 16.1 |  |
| route:codexa_refs>lsp@weak | 0.80 | 71.0 [54.8, 87.1] | 186.9 [80.6, 367.0] | 263.4 | 16.1 |  |
| single:codexa_refs | 0.64 | 54.8 [35.5, 71.0] | 68.3 [50.4, 91.3] | 124.5 | – | ★ |
| route:codexa_refs>rg0@ambiguous | 0.64 | 54.8 [38.7, 71.0] | 68.3 [50.4, 93.7] | 124.5 | 0.0 | ★ |
| route:codexa_refs>rg0@unresolved | 0.64 | 54.8 [35.5, 71.0] | 68.3 [49.6, 91.2] | 124.5 | 0.0 | ★ |
| route:codexa_refs>lsp@ambiguous | 0.64 | 54.8 [38.7, 71.0] | 68.3 [49.7, 91.3] | 124.5 | 0.0 | ★ |
| route:codexa_refs>lsp@unresolved | 0.64 | 54.8 [38.7, 71.0] | 68.3 [50.1, 92.1] | 124.5 | 0.0 | ★ |

`oracle` uses the labels and is an upper bound, not a deployable policy. Pareto = not dominated on (mean tokens, complete %) among deployable policies.