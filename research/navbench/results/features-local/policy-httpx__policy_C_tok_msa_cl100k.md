## Routing policies — layer C, tokens = `tok_msa_cl100k` (31 targets)

| policy | recall | complete % [95% CI] | mean tokens [95% CI] | tokens / complete answer | fallback fired % | Pareto |
|---|---|---|---|---|---|---|
| oracle | 1.00 | 100.0 [100.0, 100.0] | 62.9 [29.1, 107.7] | 62.9 | – |  |
| route:codexa2_refs>rg0@ambiguous | 1.00 | 100.0 [100.0, 100.0] | 149.9 [83.8, 230.5] | 149.9 | 41.9 | ★ |
| route:codexa2_refs>rg0@weak | 1.00 | 100.0 [100.0, 100.0] | 149.9 [84.5, 228.2] | 149.9 | 41.9 | ★ |
| single:rg0 | 1.00 | 100.0 [100.0, 100.0] | 155.3 [93.1, 224.4] | 155.3 | – |  |
| route:rg0>lsp@empty | 1.00 | 100.0 [100.0, 100.0] | 155.3 [91.6, 227.9] | 155.3 | 0.0 |  |
| route:rg0>lsp@ambiguous | 1.00 | 100.0 [100.0, 100.0] | 155.3 [92.4, 225.2] | 155.3 | 0.0 |  |
| route:rg0>lsp@unresolved | 1.00 | 100.0 [100.0, 100.0] | 155.3 [97.4, 225.3] | 155.3 | 0.0 |  |
| route:rg0>lsp@weak | 1.00 | 100.0 [100.0, 100.0] | 155.3 [95.8, 226.7] | 155.3 | 0.0 |  |
| route:codexa2_refs>rg0@always | 1.00 | 100.0 [100.0, 100.0] | 182.5 [120.3, 256.4] | 182.5 | 100.0 |  |
| route:codexa_refs>rg0@always | 1.00 | 100.0 [100.0, 100.0] | 192.3 [122.6, 269.0] | 192.3 | 100.0 |  |
| route:rg0>lsp@always | 1.00 | 100.0 [100.0, 100.0] | 202.7 [128.8, 293.1] | 202.7 | 100.0 |  |
| route:lsp>rg0@always | 1.00 | 100.0 [100.0, 100.0] | 202.7 [130.1, 294.1] | 202.7 | 100.0 |  |
| route:lsp>rg0@empty | 0.99 | 96.8 [90.3, 100.0] | 58.0 [31.5, 89.2] | 59.9 | 3.2 | ★ |
| route:lsp>rg0@weak | 0.99 | 96.8 [90.3, 100.0] | 58.0 [31.1, 90.2] | 59.9 | 3.2 | ★ |
| single:lsp | 0.95 | 93.5 [83.9, 100.0] | 47.5 [25.1, 74.5] | 50.7 | – | ★ |
| route:lsp>rg0@ambiguous | 0.95 | 93.5 [83.9, 100.0] | 47.5 [25.5, 74.8] | 50.7 | 0.0 | ★ |
| route:lsp>rg0@unresolved | 0.95 | 93.5 [83.9, 100.0] | 47.5 [25.5, 72.7] | 50.7 | 0.0 | ★ |
| route:codexa2_refs>lsp@ambiguous | 0.95 | 93.5 [83.9, 100.0] | 52.8 [29.9, 84.0] | 56.4 | 41.9 |  |
| route:codexa2_refs>lsp@weak | 0.95 | 93.5 [83.9, 100.0] | 52.8 [30.1, 81.7] | 56.4 | 41.9 |  |
| route:codexa2_refs>lsp@always | 0.95 | 93.5 [83.9, 100.0] | 74.7 [45.9, 110.1] | 79.8 | 100.0 |  |
| route:codexa_refs>lsp@always | 0.95 | 93.5 [83.9, 100.0] | 84.5 [55.1, 118.2] | 90.3 | 100.0 |  |
| route:codexa2_refs>rg0@empty | 0.92 | 87.1 [74.2, 96.8] | 88.9 [42.3, 145.1] | 102.0 | 16.1 |  |
| route:codexa2_refs>lsp@empty | 0.89 | 83.9 [71.0, 96.8] | 37.9 [22.0, 59.3] | 45.2 | 16.1 | ★ |
| single:codexa2_refs | 0.76 | 71.0 [54.8, 87.1] | 27.2 [16.4, 41.0] | 38.4 | – | ★ |
| route:codexa2_refs>rg0@unresolved | 0.76 | 71.0 [54.8, 87.1] | 27.2 [16.6, 41.8] | 38.4 | 0.0 | ★ |
| route:codexa2_refs>lsp@unresolved | 0.76 | 71.0 [54.8, 87.1] | 27.2 [16.4, 42.1] | 38.4 | 0.0 | ★ |
| route:codexa_refs>lsp@empty | 0.80 | 71.0 [54.8, 83.9] | 48.8 [30.5, 72.0] | 68.8 | 16.1 |  |
| route:codexa_refs>lsp@weak | 0.80 | 71.0 [54.8, 87.1] | 48.8 [29.8, 71.6] | 68.8 | 16.1 |  |
| route:codexa_refs>rg0@empty | 0.80 | 71.0 [54.8, 87.1] | 61.7 [36.6, 96.3] | 87.0 | 16.1 |  |
| route:codexa_refs>rg0@weak | 0.80 | 71.0 [54.8, 87.1] | 61.7 [35.8, 96.1] | 87.0 | 16.1 |  |
| single:codexa_refs | 0.64 | 54.8 [35.5, 71.0] | 37.0 [22.5, 55.6] | 67.5 | – |  |
| route:codexa_refs>rg0@ambiguous | 0.64 | 54.8 [38.7, 71.0] | 37.0 [23.0, 57.5] | 67.5 | 0.0 |  |
| route:codexa_refs>rg0@unresolved | 0.64 | 54.8 [35.5, 71.0] | 37.0 [22.3, 55.2] | 67.5 | 0.0 |  |
| route:codexa_refs>lsp@ambiguous | 0.64 | 54.8 [38.7, 71.0] | 37.0 [22.3, 55.6] | 67.5 | 0.0 |  |
| route:codexa_refs>lsp@unresolved | 0.64 | 54.8 [38.7, 71.0] | 37.0 [22.3, 56.7] | 67.5 | 0.0 |  |

`oracle` uses the labels and is an upper bound, not a deployable policy. Pareto = not dominated on (mean tokens, complete %) among deployable policies.