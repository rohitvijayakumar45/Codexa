## Routing policies — layer A, tokens = `tok_native_cl100k` (160 targets)

| policy | recall | complete % [95% CI] | mean tokens [95% CI] | tokens / complete answer | fallback fired % | Pareto |
|---|---|---|---|---|---|---|
| single:codexa2_refs | 1.00 | 100.0 [100.0, 100.0] | 73.3 [66.3, 80.2] | 73.3 | – | ★ |
| route:codexa2_refs>rg0@empty | 1.00 | 100.0 [100.0, 100.0] | 73.3 [66.4, 80.5] | 73.3 | 0.0 | ★ |
| route:codexa2_refs>rg0@unresolved | 1.00 | 100.0 [100.0, 100.0] | 73.3 [66.1, 80.3] | 73.3 | 0.0 | ★ |
| route:codexa2_refs>lsp@empty | 1.00 | 100.0 [100.0, 100.0] | 73.3 [66.5, 80.3] | 73.3 | 0.0 | ★ |
| route:codexa2_refs>lsp@unresolved | 1.00 | 100.0 [100.0, 100.0] | 73.3 [66.2, 80.7] | 73.3 | 0.0 | ★ |
| oracle | 1.00 | 100.0 [100.0, 100.0] | 73.3 [66.2, 80.2] | 73.3 | – |  |
| route:codexa2_refs>rg0@ambiguous | 1.00 | 100.0 [100.0, 100.0] | 169.2 [146.1, 191.5] | 169.2 | 50.0 |  |
| route:codexa2_refs>rg0@weak | 1.00 | 100.0 [100.0, 100.0] | 169.2 [147.0, 192.1] | 169.2 | 50.0 |  |
| route:codexa2_refs>rg0@always | 1.00 | 100.0 [100.0, 100.0] | 219.0 [203.3, 234.7] | 219.0 | 100.0 |  |
| route:codexa2_refs>lsp@ambiguous | 1.00 | 100.0 [100.0, 100.0] | 351.2 [300.8, 405.2] | 351.2 | 50.0 |  |
| route:codexa2_refs>lsp@weak | 1.00 | 100.0 [100.0, 100.0] | 351.2 [292.1, 408.2] | 351.2 | 50.0 |  |
| route:codexa2_refs>lsp@always | 1.00 | 100.0 [100.0, 100.0] | 558.8 [527.0, 593.5] | 558.8 | 100.0 |  |
| single:lsp | 0.97 | 90.0 [83.8, 95.0] | 485.6 [455.2, 514.8] | 539.5 | – |  |
| route:lsp>rg0@empty | 0.97 | 90.0 [83.8, 95.0] | 485.6 [457.1, 513.6] | 539.5 | 0.0 |  |
| route:lsp>rg0@ambiguous | 0.97 | 90.0 [84.4, 95.6] | 485.6 [457.4, 515.8] | 539.5 | 0.0 |  |
| route:lsp>rg0@unresolved | 0.97 | 90.0 [83.8, 95.0] | 485.6 [456.5, 516.6] | 539.5 | 0.0 |  |
| route:lsp>rg0@weak | 0.97 | 90.0 [83.8, 95.0] | 485.6 [458.3, 514.5] | 539.5 | 0.0 |  |
| route:codexa_refs>lsp@always | 0.97 | 90.0 [84.4, 95.0] | 535.6 [505.9, 567.2] | 595.1 | 100.0 |  |
| route:rg0>lsp@always | 0.97 | 90.0 [83.8, 95.0] | 631.3 [593.9, 669.4] | 701.5 | 100.0 |  |
| route:lsp>rg0@always | 0.97 | 90.0 [84.4, 95.0] | 631.3 [597.6, 666.8] | 701.5 | 100.0 |  |
| single:rg0 | 0.95 | 80.0 [73.8, 85.6] | 145.7 [137.2, 154.8] | 182.1 | – |  |
| route:rg0>lsp@empty | 0.95 | 80.0 [73.8, 86.2] | 145.7 [136.6, 155.2] | 182.1 | 0.0 |  |
| route:rg0>lsp@ambiguous | 0.95 | 80.0 [73.8, 86.2] | 145.7 [136.6, 154.8] | 182.1 | 0.0 |  |
| route:rg0>lsp@unresolved | 0.95 | 80.0 [73.8, 85.6] | 145.7 [136.0, 154.6] | 182.1 | 0.0 |  |
| route:rg0>lsp@weak | 0.95 | 80.0 [73.1, 86.2] | 145.7 [136.7, 155.2] | 182.1 | 0.0 |  |
| route:codexa_refs>rg0@always | 0.95 | 80.0 [73.8, 86.2] | 195.7 [182.6, 209.1] | 244.7 | 100.0 |  |
| route:codexa_refs>rg0@empty | 0.73 | 50.0 [41.2, 58.8] | 62.4 [56.8, 68.8] | 124.9 | 10.0 | ★ |
| route:codexa_refs>rg0@weak | 0.73 | 50.0 [41.9, 58.1] | 62.4 [56.7, 68.3] | 124.9 | 10.0 | ★ |
| route:codexa_refs>lsp@empty | 0.73 | 50.0 [41.2, 58.1] | 108.6 [80.1, 139.8] | 217.2 | 10.0 |  |
| route:codexa_refs>lsp@weak | 0.73 | 50.0 [41.2, 58.1] | 108.6 [80.1, 140.1] | 217.2 | 10.0 |  |
| single:codexa_refs | 0.63 | 40.0 [31.2, 48.8] | 50.0 [45.4, 54.7] | 125.1 | – | ★ |
| route:codexa_refs>rg0@ambiguous | 0.63 | 40.0 [31.2, 48.8] | 50.0 [45.6, 54.4] | 125.1 | 0.0 | ★ |
| route:codexa_refs>rg0@unresolved | 0.63 | 40.0 [31.2, 48.8] | 50.0 [45.4, 54.7] | 125.1 | 0.0 | ★ |
| route:codexa_refs>lsp@ambiguous | 0.63 | 40.0 [31.2, 48.8] | 50.0 [45.7, 54.6] | 125.1 | 0.0 | ★ |
| route:codexa_refs>lsp@unresolved | 0.63 | 40.0 [31.2, 49.4] | 50.0 [45.3, 54.7] | 125.1 | 0.0 | ★ |

`oracle` uses the labels and is an upper bound, not a deployable policy. Pareto = not dominated on (mean tokens, complete %) among deployable policies.