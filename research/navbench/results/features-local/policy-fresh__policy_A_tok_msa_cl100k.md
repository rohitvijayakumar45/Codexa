## Routing policies — layer A, tokens = `tok_msa_cl100k` (160 targets)

| policy | recall | complete % [95% CI] | mean tokens [95% CI] | tokens / complete answer | fallback fired % | Pareto |
|---|---|---|---|---|---|---|
| single:codexa2_refs | 1.00 | 100.0 [100.0, 100.0] | 22.1 [20.0, 24.0] | 22.1 | – | ★ |
| route:codexa2_refs>rg0@empty | 1.00 | 100.0 [100.0, 100.0] | 22.1 [20.0, 24.1] | 22.1 | 0.0 | ★ |
| route:codexa2_refs>rg0@unresolved | 1.00 | 100.0 [100.0, 100.0] | 22.1 [20.0, 24.1] | 22.1 | 0.0 | ★ |
| route:codexa2_refs>lsp@empty | 1.00 | 100.0 [100.0, 100.0] | 22.1 [20.0, 24.0] | 22.1 | 0.0 | ★ |
| route:codexa2_refs>lsp@unresolved | 1.00 | 100.0 [100.0, 100.0] | 22.1 [19.9, 24.2] | 22.1 | 0.0 | ★ |
| oracle | 1.00 | 100.0 [100.0, 100.0] | 22.1 [20.0, 24.2] | 22.1 | – |  |
| route:codexa2_refs>lsp@ambiguous | 1.00 | 100.0 [100.0, 100.0] | 39.3 [34.9, 43.6] | 39.3 | 50.0 |  |
| route:codexa2_refs>lsp@weak | 1.00 | 100.0 [100.0, 100.0] | 39.3 [34.8, 43.7] | 39.3 | 50.0 |  |
| route:codexa2_refs>lsp@always | 1.00 | 100.0 [100.0, 100.0] | 53.7 [50.6, 56.8] | 53.7 | 100.0 |  |
| route:codexa2_refs>rg0@ambiguous | 1.00 | 100.0 [100.0, 100.0] | 58.8 [50.9, 66.9] | 58.8 | 50.0 |  |
| route:codexa2_refs>rg0@weak | 1.00 | 100.0 [100.0, 100.0] | 58.8 [51.3, 66.8] | 58.8 | 50.0 |  |
| route:codexa2_refs>rg0@always | 1.00 | 100.0 [100.0, 100.0] | 78.1 [72.3, 83.7] | 78.1 | 100.0 |  |
| single:lsp | 0.97 | 90.0 [83.8, 95.0] | 31.7 [30.4, 33.0] | 35.2 | – |  |
| route:lsp>rg0@empty | 0.97 | 90.0 [83.8, 95.0] | 31.7 [30.2, 33.0] | 35.2 | 0.0 |  |
| route:lsp>rg0@ambiguous | 0.97 | 90.0 [84.4, 95.6] | 31.7 [30.3, 33.0] | 35.2 | 0.0 |  |
| route:lsp>rg0@unresolved | 0.97 | 90.0 [83.8, 95.0] | 31.7 [30.4, 33.0] | 35.2 | 0.0 |  |
| route:lsp>rg0@weak | 0.97 | 90.0 [83.8, 95.0] | 31.7 [30.3, 33.0] | 35.2 | 0.0 |  |
| route:codexa_refs>lsp@always | 0.97 | 90.0 [84.4, 95.0] | 52.4 [48.9, 55.7] | 58.2 | 100.0 |  |
| route:rg0>lsp@always | 0.97 | 90.0 [83.8, 95.0] | 87.7 [83.2, 92.5] | 97.5 | 100.0 |  |
| route:lsp>rg0@always | 0.97 | 90.0 [84.4, 95.0] | 87.7 [83.0, 92.2] | 97.5 | 100.0 |  |
| single:rg0 | 0.95 | 80.0 [73.8, 85.6] | 56.1 [52.3, 59.9] | 70.1 | – |  |
| route:rg0>lsp@empty | 0.95 | 80.0 [73.8, 86.2] | 56.1 [52.5, 59.9] | 70.1 | 0.0 |  |
| route:rg0>lsp@ambiguous | 0.95 | 80.0 [73.8, 86.2] | 56.1 [52.4, 59.9] | 70.1 | 0.0 |  |
| route:rg0>lsp@unresolved | 0.95 | 80.0 [73.8, 85.6] | 56.1 [52.2, 59.9] | 70.1 | 0.0 |  |
| route:rg0>lsp@weak | 0.95 | 80.0 [73.1, 86.2] | 56.1 [52.4, 60.0] | 70.1 | 0.0 |  |
| route:codexa_refs>rg0@always | 0.95 | 80.0 [73.8, 86.2] | 76.8 [70.8, 83.2] | 96.0 | 100.0 |  |
| route:codexa_refs>lsp@empty | 0.73 | 50.0 [41.2, 58.1] | 24.2 [22.1, 26.4] | 48.3 | 10.0 |  |
| route:codexa_refs>lsp@weak | 0.73 | 50.0 [41.2, 58.1] | 24.2 [22.1, 26.2] | 48.3 | 10.0 |  |
| route:codexa_refs>rg0@empty | 0.73 | 50.0 [41.2, 58.8] | 25.0 [22.9, 27.3] | 50.0 | 10.0 |  |
| route:codexa_refs>rg0@weak | 0.73 | 50.0 [41.9, 58.1] | 25.0 [22.8, 27.1] | 50.0 | 10.0 |  |
| single:codexa_refs | 0.63 | 40.0 [31.2, 48.8] | 20.8 [18.1, 23.4] | 51.9 | – | ★ |
| route:codexa_refs>rg0@ambiguous | 0.63 | 40.0 [31.2, 48.8] | 20.8 [18.3, 23.1] | 51.9 | 0.0 | ★ |
| route:codexa_refs>rg0@unresolved | 0.63 | 40.0 [31.2, 48.8] | 20.8 [18.1, 23.3] | 51.9 | 0.0 | ★ |
| route:codexa_refs>lsp@ambiguous | 0.63 | 40.0 [31.2, 48.8] | 20.8 [18.3, 23.3] | 51.9 | 0.0 | ★ |
| route:codexa_refs>lsp@unresolved | 0.63 | 40.0 [31.2, 49.4] | 20.8 [18.2, 23.3] | 51.9 | 0.0 | ★ |

`oracle` uses the labels and is an upper bound, not a deployable policy. Pareto = not dominated on (mean tokens, complete %) among deployable policies.