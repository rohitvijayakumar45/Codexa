# Adding a tool to NavBench

Every evaluated tool is an *adapter* (`nb/adapters.py`). An adapter answers some of three tasks,
and writes its rows under arm labels of its choosing:

| Task | Question | Method | Returns |
|---|---|---|---|
| T1 | direct callers of a target declaration | `t1(ctx, decl) -> list[ArmResult]` | locations (`fact_kind="loc"`) or caller declaration ids (`fact_kind="caller"`) |
| T2 | definition of the name at a call site | `t2(ctx, decl, site) -> ArmResult` | locations |
| T3 | callers within `depth` hops (default 2) | `t3(ctx, decl, depth) -> ArmResult` | locations or caller ids |

## Minimal plugin

```python
# my_tool_adapter.py  (anywhere on PYTHONPATH)
import subprocess, time
from nb.adapters import Adapter, register
from nb.arms import ArmResult

@register
class MyTool(Adapter):
    name = "mytool"                 # used with --arms
    t1_arms = ("mytool",)           # arm label(s) its T1 rows are written under
    t3_arm = "mytool_t3"            # optional

    def available(self):            # tool missing -> rows are written as "unsupported"
        return True, ""

    def setup(self, ctx):           # index ctx.root once per repository; return timings for meta.json
        return {"mytool_index_s": 0.0}

    def t1(self, ctx, decl):        # decl: {"name", "qualname", "file", "line", "col", ...}
        t = time.perf_counter()
        out = subprocess.run(["mytool", "callers", decl["name"]], cwd=ctx.root,
                             capture_output=True, text=True).stdout
        locs = [(f, int(l), int(c)) for f, l, c in (x.split(":") for x in out.split())]
        return [ArmResult("mytool", "ok" if locs else "empty", native=out, facts=locs,
                          latency_s=time.perf_counter() - t)]
```

To run it:

```bash
NB_PLUGINS=my_tool_adapter python -m nb.run <repo> <py|ts> <fixture|natural> <out> --arms rg0,lsp,mytool --tasks T1,T3
```

## Rules that keep the comparison fair

- **Native output is what gets counted.** `ArmResult.native` must be exactly the text the tool
  would put in a model's context, including any follow-up calls. Count every call in `n_calls`.
- **No labels.** An adapter receives the target declaration and nothing else. A qualified name may
  be sent only *after* the tool itself reports ambiguity; see `Codexa2` and `CBM` for the protocol.
- **Caller ids** returned with `fact_kind="caller"` must be resolved through the independent index:
  `ctx.ix.decl_at_line(file, line)`, or `nb.index.resolve_dotted(ctx.ix, "pkg.mod.Class.fn")`.
  Anything the index cannot map should be returned as `unresolved:<text>`, which counts against the
  tool.
- **Determinism.** Cold-index per repository (remove caches in `setup`), and do not retry on
  failure. Record `error` or `timeout`; rows are never dropped.

## What you get

```bash
python -m nb.score <out>
python -m nb.leaderboard <out>/scored.jsonl <out>/lb    # leaderboard.md / leaderboard.json
python -m nb.policy <out>/scored.jsonl <out>/policy --fallbacks rg0,lsp   # routing policies (layer A)
```

The leaderboard reports three token measures:
- native tokens;
- tokens in a common location form;
- tokens of the **minimal sufficient answer** (`nb/forms.py`), which holds information content
  fixed.

It also reports tokens per complete answer, and a Pareto flag on (tokens, completeness).
