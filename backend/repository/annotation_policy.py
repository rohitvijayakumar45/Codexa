"""Which symbols get an LLM-written meaning when the budget cannot cover all of them.

Annotation (backend/repository/semantic.py) costs one light-model call per symbol, so a run is
capped (CODEXA_ANNOTATE_BUDGET, default 80). The cap makes the ORDER in which symbols are considered
the whole policy: the first K symbols needing a (re-)annotation get one, the rest go without. This
module isolates that ordering so it can be selected at runtime (CODEXA_ANNOTATE_POLICY) and compared
head-to-head (tests/benchmarks/annotation_budget/).

Policies — every one is deterministic given its inputs (random is seeded):

    callers      library before tests, public before private, then by call sites pointing at the
                 bare name, a class counted as three callers. The production default.
    callers_exact   same shape, but call sites are counted per exact symbol key (file#qualname) so
                 two unrelated `send`s no longer pool their callers.
    pagerank     PageRank over the call graph (caller -> callee), importance flowing to callees.
    degree       in-degree + out-degree in the call graph.
    file_order   the order the parser produced (the original, pre-_priority behaviour).
    random       seeded shuffle — the floor any real policy has to beat.
    git_churn    symbols in files the recent git history touched most, callers as tie-break — code
                 people are actively working on is code agents get asked about. Needs file_churn
                 (e.g. from mine_file_churn); without it this is exactly `callers`.
    lazy         annotate nothing eagerly; meanings are written on demand the first time an agent
                 looks a symbol up (see semantic.annotate_on_demand).
"""

from __future__ import annotations

import os
import random as _random
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from backend.repository.analyze import Symbol

POLICIES = ("callers", "callers_exact", "pagerank", "degree", "git_churn", "file_order", "random", "lazy")
DEFAULT_POLICY = "callers"
DEFAULT_BUDGET = 80
_CLASS_WEIGHT = 3


def configured_policy() -> str:
    policy = os.getenv("CODEXA_ANNOTATE_POLICY", DEFAULT_POLICY).strip().lower()
    return policy if policy in POLICIES else DEFAULT_POLICY


def configured_budget() -> int:
    try:
        return max(0, int(os.getenv("CODEXA_ANNOTATE_BUDGET", str(DEFAULT_BUDGET))))
    except ValueError:
        return DEFAULT_BUDGET


def _key(sym: "Symbol") -> str:
    return f"{sym.file}#{sym.qualname or sym.name}"


def _in_tests(sym: "Symbol") -> bool:
    return (sym.file.startswith(("tests/", "test/")) or "/tests/" in sym.file
            or sym.file.rsplit("/", 1)[-1].startswith("test_"))


def _rank_callers(symbols: list["Symbol"], calls: list[tuple[str, str]] | None) -> list["Symbol"]:
    callers: dict[str, int] = {}
    for _src, dst in calls or []:
        name = dst.rsplit("#", 1)[-1].rsplit(".", 1)[-1]
        callers[name] = callers.get(name, 0) + 1

    def score(sym: "Symbol") -> tuple[int, int, int]:
        weight = callers.get(sym.name, 0) + (_CLASS_WEIGHT if sym.kind == "class" else 0)
        return (0 if _in_tests(sym) else 1, 0 if sym.name.startswith("_") else 1, weight)

    return sorted(symbols, key=score, reverse=True)


def _rank_callers_exact(symbols: list["Symbol"], calls: list[tuple[str, str]] | None) -> list["Symbol"]:
    callers: dict[str, int] = {}
    for _src, dst in calls or []:
        callers[dst] = callers.get(dst, 0) + 1

    def score(sym: "Symbol") -> tuple[int, int, int]:
        weight = callers.get(_key(sym), 0) + (_CLASS_WEIGHT if sym.kind == "class" else 0)
        return (0 if _in_tests(sym) else 1, 0 if sym.name.startswith("_") else 1, weight)

    return sorted(symbols, key=score, reverse=True)


def _rank_degree(symbols: list["Symbol"], calls: list[tuple[str, str]] | None) -> list["Symbol"]:
    degree: dict[str, int] = {}
    for src, dst in calls or []:
        degree[src] = degree.get(src, 0) + 1
        degree[dst] = degree.get(dst, 0) + 1
    return sorted(symbols, key=lambda s: degree.get(_key(s), 0), reverse=True)


def pagerank(nodes: list[str], edges: list[tuple[str, str]], *, damping: float = 0.85,
             iterations: int = 60, tol: float = 1e-10) -> dict[str, float]:
    """Plain power-iteration PageRank; dangling mass is redistributed uniformly. No dependency on
    networkx — the call graphs here are at most a few thousand nodes."""
    index = {n: i for i, n in enumerate(nodes)}
    n = len(nodes)
    if n == 0:
        return {}
    out: list[list[int]] = [[] for _ in range(n)]
    for src, dst in edges:
        if src in index and dst in index and src != dst:
            out[index[src]].append(index[dst])
    rank = [1.0 / n] * n
    for _ in range(iterations):
        dangling = sum(rank[i] for i in range(n) if not out[i])
        new = [(1.0 - damping) / n + damping * dangling / n] * n
        for i, targets in enumerate(out):
            if targets:
                share = damping * rank[i] / len(targets)
                for j in targets:
                    new[j] += share
        delta = sum(abs(a - b) for a, b in zip(new, rank))
        rank = new
        if delta < tol:
            break
    return {node: rank[i] for node, i in index.items()}


def _rank_pagerank(symbols: list["Symbol"], calls: list[tuple[str, str]] | None) -> list["Symbol"]:
    keys = [_key(s) for s in symbols]
    pr = pagerank(keys, list(calls or []))
    return sorted(symbols, key=lambda s: pr.get(_key(s), 0.0), reverse=True)


def _rank_git_churn(symbols: list["Symbol"], calls: list[tuple[str, str]] | None,
                    file_churn: dict[str, int] | None) -> list["Symbol"]:
    base = _rank_callers(symbols, calls)  # stable sort below keeps this as the tie-break
    if not file_churn:
        return base
    return sorted(base, key=lambda s: file_churn.get(s.file, 0), reverse=True)


def mine_file_churn(root, *, last_commits: int = 50, rev: str = "HEAD") -> dict[str, int]:
    """How many of the last `last_commits` first-parent commits touched each file. Empty when the
    directory is not a git repository."""
    import subprocess

    try:
        out = subprocess.run(
            ["git", "-C", str(root), "log", "--first-parent", f"-n{last_commits}", "--name-only",
             "--pretty=format:", rev],
            check=True, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    churn: dict[str, int] = {}
    for line in out.splitlines():
        line = line.strip()
        if line:
            churn[line] = churn.get(line, 0) + 1
    return churn


def rank_symbols(
    symbols: list["Symbol"], calls: list[tuple[str, str]] | None, policy: str = DEFAULT_POLICY,
    *, seed: int = 0, file_churn: dict[str, int] | None = None,
) -> list["Symbol"]:
    """All symbols, in the order the policy wants them annotated. `lazy` returns an empty list: it
    annotates nothing eagerly. Python's sort is stable, so ties keep parser order in every policy."""
    policy = (policy or DEFAULT_POLICY).lower()
    symbols = list(symbols)
    if policy == "callers":
        return _rank_callers(symbols, calls)
    if policy == "callers_exact":
        return _rank_callers_exact(symbols, calls)
    if policy == "pagerank":
        return _rank_pagerank(symbols, calls)
    if policy == "degree":
        return _rank_degree(symbols, calls)
    if policy == "git_churn":
        return _rank_git_churn(symbols, calls, file_churn)
    if policy == "file_order":
        return symbols
    if policy == "random":
        _random.Random(seed).shuffle(symbols)
        return symbols
    if policy == "lazy":
        return []
    raise ValueError(f"unknown annotation policy: {policy!r} (choose from {', '.join(POLICIES)})")


def select_symbols(
    symbols: list["Symbol"], calls: list[tuple[str, str]] | None, policy: str = DEFAULT_POLICY,
    budget: int = DEFAULT_BUDGET, *, seed: int = 0, file_churn: dict[str, int] | None = None,
) -> list["Symbol"]:
    """The first `budget` symbols of the policy's ranking — the set a cold-start run would annotate."""
    return rank_symbols(symbols, calls, policy, seed=seed, file_churn=file_churn)[:max(0, budget)]
