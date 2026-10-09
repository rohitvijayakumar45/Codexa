"""Annotation-budget benchmark: which K symbols deserve an LLM-written meaning?

Symbol annotation costs one light-model call per symbol, so production caps it at K per run and a
selection policy (backend/repository/annotation_policy.py) decides which K. This measures, for each
policy and budget K, how much of the code agents will actually need meanings for is covered —
without any LLM call: the policies are pure functions of the parsed repository, and "need" is read
from real git history.

Demand (what an agent is going to be asked about after commit t, over the next N commits):
    D_edit   symbols that exist at t and whose source changes by t+N — the code people work on next
    D_file   every symbol at t whose file changes by t+N (broader, noisier)
    D_gold   optional: gold symbols of real questions (--questions JSONL: {"question", "gold_symbols"})
             evaluated at HEAD

Per (policy, K):
    coverage        |annotated ∩ D| / |D|, averaged over sampled commits t
    invalidated_share  |annotated ∩ D_edit| / K — share of the K annotations invalidated again within
                    N commits (paid for, then thrown away: the flip side of annotating hot code)
    cost_tokens     prompt-token proxy of annotating the K symbols (snippet chars / 4 + overhead)
Baselines/bounds: `random` (seeded) is the floor, `oracle` (first K of D_edit) the ceiling. `lazy`
annotates nothing eagerly; its row reports deferred on-demand calls (|D_edit|) instead.

Usage
  python tests/benchmarks/annotation_budget/run.py --repo .codexa/repos/httpx --horizon 20 \
      --bases 10 --out tests/benchmarks/annotation_budget/results/httpx.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
for _p in (ROOT, HERE.parent / "memory_anchoring"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from backend.repository.analyze import Analysis, analyze_repo, symbol_key  # noqa: E402
from backend.repository.annotation_policy import POLICIES, rank_symbols  # noqa: E402
from replay import changed_files, ensure_repo_root, export, history  # noqa: E402

_PROMPT_OVERHEAD_TOKENS = 60
_SNIPPET_CHARS = 1500


def file_churn_at(repo: Path, sha: str, last_commits: int) -> dict[str, int]:
    out = subprocess.run(
        ["git", "-C", str(repo), "log", "--first-parent", f"-n{last_commits}", "--name-only",
         "--pretty=format:", sha],
        check=True, capture_output=True, text=True, encoding="utf-8", errors="replace",
    ).stdout
    churn: dict[str, int] = {}
    for line in out.splitlines():
        if line.strip():
            churn[line.strip()] = churn.get(line.strip(), 0) + 1
    return churn


def token_cost(root: Path, analysis: Analysis) -> dict[str, int]:
    cache: dict[str, list[str]] = {}
    cost: dict[str, int] = {}
    for s in analysis.symbols:
        lines = cache.get(s.file)
        if lines is None:
            try:
                lines = (root / s.file).read_text(encoding="utf-8", errors="ignore").split("\n")
            except OSError:
                lines = []
            cache[s.file] = lines
        end = s.end_line if s.end_line >= s.line else s.line
        chars = min(_SNIPPET_CHARS, len("\n".join(lines[max(0, s.line - 1):end])))
        cost[symbol_key(s)] = chars // 4 + _PROMPT_OVERHEAD_TOKENS
    return cost


def _budgets(spec: str, n_symbols: int) -> list[int]:
    out = []
    for tok in spec.split(","):
        tok = tok.strip().lower()
        if not tok:
            continue
        out.append(n_symbols if tok == "all" else int(tok))
    return sorted(set(out))


def evaluate_base(
    repo: Path, commits: list[str], i: int, horizon: int, budgets_spec: str, churn_window: int,
    tmp: Path, seeds: list[int],
) -> dict[str, Any] | None:
    t_sha, u_sha = commits[i], commits[min(i + horizon, len(commits) - 1)]
    root_t = export(repo, t_sha, tmp / f"t-{t_sha[:12]}")
    root_u = export(repo, u_sha, tmp / f"u-{u_sha[:12]}")
    a_t, a_u = analyze_repo(root_t), analyze_repo(root_u)
    hashes_u = {symbol_key(s): s.content_hash for s in a_u.symbols}
    keys_t = [symbol_key(s) for s in a_t.symbols]
    if not keys_t:
        return None
    diff = set(changed_files(repo, t_sha, u_sha))
    d_edit = {symbol_key(s) for s in a_t.symbols
              if symbol_key(s) in hashes_u and hashes_u[symbol_key(s)] != s.content_hash}
    d_file = {symbol_key(s) for s in a_t.symbols if s.file in diff}
    cost = token_cost(root_t, a_t)
    churn = file_churn_at(repo, t_sha, churn_window)
    budgets = _budgets(budgets_spec, len(keys_t))

    rows: dict[str, dict[str, Any]] = {}
    for policy in POLICIES:
        runs = seeds if policy == "random" else [0]
        per_k: dict[int, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        for seed in runs:
            ranked = [symbol_key(s) for s in rank_symbols(a_t.symbols, a_t.calls, policy, seed=seed, file_churn=churn)]
            for k in budgets:
                chosen = set(ranked[:k])
                m = per_k[k]
                m["coverage_edit"].append(len(chosen & d_edit) / len(d_edit) if d_edit else float("nan"))
                m["coverage_file"].append(len(chosen & d_file) / len(d_file) if d_file else float("nan"))
                m["invalidated_share"].append(len(chosen & d_edit) / len(chosen) if chosen else float("nan"))
                m["cost_tokens"].append(sum(cost[c] for c in chosen))
                m["annotated"].append(len(chosen))
        rows[policy] = {str(k): {name: _mean(vals) for name, vals in m.items()} for k, m in per_k.items()}
        if policy == "lazy":
            for k in budgets:
                rows[policy][str(k)]["deferred_calls"] = len(d_edit)
                rows[policy][str(k)]["deferred_cost_tokens"] = sum(cost[c] for c in d_edit)

    oracle_rank = sorted(d_edit) + [k for k in keys_t if k not in d_edit]
    rows["oracle"] = {}
    for k in budgets:
        chosen = set(oracle_rank[:k])
        rows["oracle"][str(k)] = {
            "coverage_edit": len(chosen & d_edit) / len(d_edit) if d_edit else float("nan"),
            "coverage_file": len(chosen & d_file) / len(d_file) if d_file else float("nan"),
            "invalidated_share": len(chosen & d_edit) / len(chosen) if chosen else float("nan"),
            "cost_tokens": sum(cost[c] for c in chosen), "annotated": len(chosen),
        }
    return {
        "t": t_sha[:10], "t_plus_n": u_sha[:10], "symbols": len(keys_t), "files_changed": len(diff),
        "d_edit": len(d_edit), "d_file": len(d_file), "total_cost_tokens_all": sum(cost.values()),
        "budgets": budgets, "policies": rows,
    }


def _mean(vals: list[float]) -> float | None:
    real = [v for v in vals if v == v]  # drop NaN
    return sum(real) / len(real) if real else None


def evaluate_gold(repo: Path, questions: Path, budgets_spec: str, churn_window: int, seeds: list[int]) -> dict[str, Any]:
    """Coverage of real questions' gold symbols at HEAD. gold_symbols may be `file#qualname` keys or
    bare qualnames/names (matched against every symbol with that qualname or name)."""
    a = analyze_repo(repo)
    by_name: dict[str, set[str]] = defaultdict(set)
    for s in a.symbols:
        key = symbol_key(s)
        by_name[key].add(key)
        by_name[s.qualname or s.name].add(key)
        by_name[s.name].add(key)
    gold_sets = []
    for line in questions.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        keys = set().union(*(by_name.get(g, set()) for g in item.get("gold_symbols", []))) if item.get("gold_symbols") else set()
        if keys:
            gold_sets.append(keys)
    churn = file_churn_at(repo, "HEAD", churn_window)
    budgets = _budgets(budgets_spec, len(a.symbols))
    out: dict[str, Any] = {"questions": len(gold_sets), "policies": {}}
    for policy in POLICIES:
        per_k: dict[str, list[float]] = defaultdict(list)
        for seed in (seeds if policy == "random" else [0]):
            ranked = [symbol_key(s) for s in rank_symbols(a.symbols, a.calls, policy, seed=seed, file_churn=churn)]
            for k in budgets:
                chosen = set(ranked[:k])
                # a question is "answerable from meanings" when ANY of its gold symbols is annotated
                per_k[str(k)].append(sum(1 for g in gold_sets if g & chosen) / len(gold_sets) if gold_sets else float("nan"))
        out["policies"][policy] = {k: _mean(v) for k, v in per_k.items()}
    return out


def run(repo: Path, *, horizon: int, bases: int, budgets: str, churn_window: int, seeds: list[int],
        questions: Path | None = None) -> dict[str, Any]:
    repo = repo.resolve()
    ensure_repo_root(repo)
    commits = history(repo)
    # need churn_window commits of history before t for git_churn, and horizon after it
    # (git_churn simply sees less history at early commits; short repos keep half their range)
    lo = min(churn_window, max(0, (len(commits) - horizon) // 2))
    candidates = list(range(lo, len(commits) - horizon))
    if not candidates:
        candidates = list(range(0, max(1, len(commits) - 1)))
    if len(candidates) > bases:
        step = len(candidates) / bases
        candidates = [candidates[int(j * step)] for j in range(bases)]
    per_base = []
    with tempfile.TemporaryDirectory(prefix="codexa-annot-") as tmp:
        for i in candidates:
            res = evaluate_base(repo, commits, i, horizon, budgets, churn_window, Path(tmp), seeds)
            if res:
                per_base.append(res)
                print(f"  t={res['t']} symbols={res['symbols']} d_edit={res['d_edit']} d_file={res['d_file']}")

    # aggregate: mean over bases, by policy x K-label. K labels differ per base only for "all".
    agg: dict[str, dict[str, dict[str, list[float]]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    labels = [t.strip().lower() for t in budgets.split(",") if t.strip()]
    for b in per_base:
        for label in labels:
            k = str(b["symbols"] if label == "all" else int(label))
            for policy, rows in b["policies"].items():
                for metric, val in rows.get(k, {}).items():
                    if val is not None:
                        agg[policy][label][metric].append(val)
    summary = {policy: {label: {m: _mean(v) for m, v in metrics.items()} for label, metrics in by_k.items()}
               for policy, by_k in agg.items()}
    out = {"repo": repo.name, "config": {"horizon": horizon, "bases": bases, "budgets": budgets,
                                         "churn_window": churn_window, "random_seeds": seeds},
           "summary": summary, "per_base": per_base}
    if questions:
        out["gold"] = evaluate_gold(repo, questions, budgets, churn_window, seeds)
    return out


def print_summary(res: dict[str, Any], metric: str = "coverage_edit") -> None:
    labels = [t.strip().lower() for t in res["config"]["budgets"].split(",") if t.strip()]
    print(f"\n== {res['repo']} — {metric} (mean over {len(res['per_base'])} commits, horizon "
          f"{res['config']['horizon']}) ==")
    print(f"{'policy':14}" + "".join(f"{'K=' + l:>9}" for l in labels))
    for policy, by_k in res["summary"].items():
        cells = []
        for l in labels:
            v = by_k.get(l, {}).get(metric)
            cells.append(f"{v:>9.3f}" if v is not None else f"{'-':>9}")
        print(f"{policy:14}" + "".join(cells))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True, action="append")
    ap.add_argument("--horizon", type=int, default=20, help="N: commits of future demand after t")
    ap.add_argument("--bases", type=int, default=10, help="sampled commits t")
    ap.add_argument("--budgets", default="0,20,40,80,160,all")
    ap.add_argument("--churn-window", type=int, default=50, help="commits of history git_churn looks back")
    ap.add_argument("--seeds", default="0,1,2,3,4", help="seeds averaged for the random policy")
    ap.add_argument("--questions", help="JSONL of {question, gold_symbols} (evaluated at HEAD)")
    ap.add_argument("--out", help="output JSON path (one repo) or directory (several)")
    args = ap.parse_args(argv)
    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
    single_file = bool(args.out) and len(args.repo) == 1 and args.out.endswith(".json")
    failures = 0
    for repo in args.repo:
        print(f"annotation budget: {repo}")
        try:
            res = run(Path(repo), horizon=args.horizon, bases=args.bases, budgets=args.budgets,
                      churn_window=args.churn_window, seeds=seeds,
                      questions=Path(args.questions) if args.questions else None)
        except Exception as exc:  # noqa: BLE001 - one bad repository must not lose the others
            failures += 1
            print(f"  FAILED: {type(exc).__name__}: {exc}")
            continue
        print_summary(res, "coverage_edit")
        print_summary(res, "invalidated_share")
        if args.out:
            out = Path(args.out) if single_file else Path(args.out) / f"{res['repo']}.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(res, indent=2), encoding="utf-8")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
