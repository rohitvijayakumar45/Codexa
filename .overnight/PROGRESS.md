# Overnight job — progress checklist

Started 2026-09-10. Resume from the first unchecked item. Do not commit unless asked.

Prototype source of truth: `C:\Users\rohit\AppData\Local\Temp\claude\C--Users-rohit-OneDrive-Documents-Codexa\5a01b696-6048-480f-bdc2-3cee63a93ff1\scratchpad\strata-{a,b,c,d,e}` (+ assembled `codexa-strata.html`), also published at https://claude.ai/code/artifact/c76f4dc9-616e-411f-8bfc-cd91f0f0a762

## 1. Strata tab (new route /strata, above Knowledge graph in rail)
- [x] graph tokens (--g-*) for Blueprint + Noir in globals.css
- [x] lib/strata/{model,layout,geometry}.ts — computed layout reproducing prototype
- [x] components/strata/* — canvas (bands, hulls, glyphs, tapered edges, leaders), inspector, time bar, legend, search, focus, matrix
- [x] real agent halo (job-store touched paths from chat tool calls) — logic tested with node strip-types
- [x] rail entry + route
- [x] verified in browser, both themes, all 3 views, time scrub (31d shows old edge, 25d ghost), hover leader, search+Enter, lint+tsc clean

## 2. Theme adaptation
- [x] old Knowledge graph tab works in Noir (lib/theme.ts useWorkspaceTheme + readGraphPalette; GraphScene takes palette; SURFACE uses vars)
- [x] Architecture tab works in Noir (bg + card fill via vars)

## 3. Time machine — ledger/timeline visible (snapshots no longer take full height)
- [x] redesigned: fixed viewing strip, ledger owns remaining height with category filter + future-dimming, snapshots in own scrolling column, snapshot ticks on chart; verified in browser
## 4. Agent network — redesign + real-time updates
- [x] lanes by layer, cards w/ status (working <60s / recent <15m / idle), 30-min sparkline, tapered edges (live = signal + flowing dash), live feed of model calls + events, agent detail w/ run panels preserved, 2s polling of agents+events+usage records. Runtime agents from usage log (chat, plan, delegate_build, …) shown. Verified real-time by injecting a fresh usage record in-page: card flipped to Working within one poll.
## 5. Repository score — redesign
- [x] verdict-first: gauge in semantic colour (ink/warn/danger + icon + word, never the signal colour) with target tick, plain-language verdict, measured-facts tiles (when the backend measured them), breakdown weakest-first with target tick + reasoning, portfolio dot strip ranking this repo among every ingested repo, prioritised actions. Verified Blueprint + Noir; gauge offset matches score.

## Cleanup
- [x] WorkspaceShell theme read via useSyncExternalStore (was setState-in-effect lint error I introduced earlier)
- Remaining lint errors are pre-existing in chat/page.tsx (7) + 2 warnings in usage/page.tsx, lib/api.ts — untouched.

## Status: ALL FIVE ITEMS DONE (2026-09-11). Theme left on Blueprint (user's stored preference). Nothing committed.

## Round 2 (2026-09-11, user feedback on Exam-Proctoring)
- [x] backend/repository/intent.py: API routes (Express/FastAPI/Flask/Next), commits (own .git only), dependency-evidenced decisions, observed conventions; wired into _ingest; coupling.py got the same own-.git guard. tests/test_repository_intent.py (7) — full suite 949 passed.
- [x] backend restarted via launch.json "backend" (serverId in preview_list); Exam-Proctoring now 24 routes, 1 commit, 10 decisions, 3 conventions.
- [x] Strata: signal-colour selection ring + related rings (file -> its symbols + what they call), gold leaders, bundled fan-out (>6 file links drawn on demand, "N files" label), wrapping intent/signal rows, dense symbol pitch, per-repo time span.
- [x] Focus: every neighbour listed in balanced grid columns (no "+N more"), top-aligned, canvas widens + scrolls sideways + centres on selection, drag-to-pan.
- [x] Matrix: fixed readable cells, grows and scrolls both ways, notes moved top-left.
- [x] browser verification on Exam-Proctoring: Strata shows 24 routes / 10 decisions / 3 conventions / commit; App.tsx selection ring rgb(194,65,90) (Noir signal), 3 lit symbols, gold leaders #c9a227; Blueprint ring rgb(15,111,212). Focus on utils.ts lists all 43 incoming (no "+N more"), svg 2380x686, top-aligned, sideways scroll + drag-pan. Matrix 5846x5592 scrolls both ways. No console errors. Tuning: BUNDLE_OVER=2, symbol pitch 26 above 100 symbols.

## Round 3 (2026-09-11): cloning end to end + Strata density
Root causes found live:
- Re-clone/delete failed on Windows: git pack files are read-only; rmtree could not delete them ("WinError 5"), after deleting everything else — destroyed BarbellHub / Pulse-Benchmark / Spoon-Knife checkouts, left 6 temp clones. Fix: rmtree onexc chmod + retry (`_make_writable`), `_discard`, startup + per-load sweep of `.name.load-*`.
- Any repo with real history crashed mid-ingest: coupling edges were static_analysis with fractional confidence (schema invariant). Fix: confidence 1.0 + properties.strength; impact.py and Strata read the strength; coupling wrapped like intent.
- Frontend hid every backend error ("Backend responded 400"): lib/api.ts failureMessage() surfaces FastAPI `detail`.
- URL handling: GitHub/GitLab/Bitbucket page URLs + scheme-less accepted (`_normalize_url`); credential prompts disabled (fast fail); core.longpaths; readable git error mapping; 10-minute timeout; per-repo lock; never overwrite a different repo or agent-made project (`owner-repo` / `-2` names).
- load flow is `load_repository()` (module-level). Tests: tests/test_repository_load_pipeline.py (27 incl. real coupled history), clone_health updated. Full suite 976 passed.
- BarbellHub + Pulse-Benchmark original URLs unknown (not recorded) — user must re-load them by URL; Spoon-Knife repaired.
- Strata dense mode (>120 edges): quiet hairlines, intent/commit links on demand, length-sampled smooth tapers, more spacing; Full screen = in-page overlay (+ native when allowed), F / Esc.

## Round 4 (2026-09-11): "fatal: fetch-pack: invalid index-pack output" on BarbellHub
- Intermittent (same clone succeeded 3x in probes, inside and outside OneDrive). Fix: clone into system temp `codexa-clones/` (outside OneDrive's filter driver) then move in (rename, shutil.move across volumes); retry up to 3x ONLY on transient download failures (_TRANSIENT_MARKERS); never retry not-found/private; clear "kept getting interrupted" message; sweeps cover the temp root. Tests: TestGitCloneRetries + outside-folder test.
- BarbellHub re-loaded and repaired (268 files).

## Round 5 (2026-09-11): BarbellHub had 0 API routes
- Cause: plain `http.createServer` dispatch table keyed "METHOD /path" (`routes[req.method + ' ' + pathname]`), incl. a table spread in from api/coach/routes.js — no framework, so no extractor matched.
- Fix: `_TABLE_RE` in backend/repository/intent.py (key must be followed by `:` + a handler; runs before the framework-hint gate). BarbellHub now 38 routes; Exam-Proctoring 24 / Auralis 25 unchanged. Test: test_plain_http_route_tables. Full suite 982 passed.
- Not extractable (honest gap): fullstack-bench dispatches by URL segments (`seg[1] === 'health' && method === 'GET'`) — no path literals to read.

## Log
- 2026-09-11: Strata built — lib/strata/{geometry,model,layout}.ts, components/strata/{Glyph,Inspector,TimeBar,Matrix,StrataView}.tsx, app/(workspace)/strata/page.tsx, rail entry (Layers icon, above Knowledge graph), --color-g-* tokens + scoped .strata CSS in globals.css, job-store `touched` + chat onToolCall feeds it (agent halo). tsc + eslint clean. Browser: Blueprint + Noir render, Strata 28 nodes/24 edges, Focus opens on GraphService, Matrix 73 cells. Frontend dev server is an external node on :3000 (not a preview server) — use tab "seed".
