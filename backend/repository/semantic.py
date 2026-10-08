"""LLM-derived semantic annotation layer for CodeSymbol nodes.

The structural graph (`analyze.py`) knows *what calls what*; it has no idea *what anything means*.
This pass turns each symbol into a one-line, LLM-written description of its purpose — stored once,
shared by every model/conversation (it lives in MemoryStore, not chat history), and re-used across
restarts instead of re-generated, because each symbol's entry is keyed by a content hash of its
source span. A later ingest (including the automatic startup rehydration) only pays for symbols whose
actual code changed; everything else is reused for free. Bounded by a per-run cost ceiling and run on
the light model tier, since this is a bulk pass, not a one-off high-stakes call.
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.agents.llm import LLMClient
from backend.memory.store import MemoryStore
from backend.repository.analyze import Symbol
from backend.repository.annotation_policy import (
    DEFAULT_BUDGET, _rank_callers, configured_budget, configured_policy, rank_symbols,
)

# Default per-run cap; the live value is CODEXA_ANNOTATE_BUDGET (annotation_policy.configured_budget).
_MAX_ANNOTATE_PER_RUN = DEFAULT_BUDGET
_SOURCE = "symbol_annotations"
_TITLE = "Symbol semantic annotations"


def _load_blob(store: MemoryStore, repository: str) -> dict[str, dict[str, str]]:
    for rec in store.list(repository=repository, memory_type="semantic"):
        if rec.metadata.get("source") == _SOURCE:
            try:
                return json.loads(rec.content)
            except json.JSONDecodeError:
                return {}
    return {}


def _save_blob(store: MemoryStore, repository: str, blob: dict[str, dict[str, str]]) -> None:
    store.remove(repository, source=_SOURCE)
    if not blob:
        return
    store.add(
        repository=repository, memory_type="semantic", title=_TITLE,
        content=json.dumps(blob), metadata={"source": _SOURCE},
    )


def _annotate_one(llm: LLMClient, models: list[str], prompt: str) -> str | None:
    """Try each available light-tier model in turn — a rate-limited provider shouldn't silently
    drop the symbol; fall through to the next candidate before giving up."""
    for model in models:
        try:
            summary = llm.complete(
                [{"role": "user", "content": prompt}], model=model, agent="symbol_annotation",
            ).strip()
        except Exception:  # noqa: BLE001 - try the next candidate
            continue
        if summary:
            return summary
    return None


def _priority(symbols: list[Symbol], calls: list[tuple[str, str]] | None) -> list[Symbol]:
    """Order symbols so the per-run cap is spent on the ones questions are actually about.

    In file order, the first 80 of httpx's 324 symbols were mostly private helpers and dunder
    methods; `Client` and `Client.send` — the subject of the first question anyone asks — had no
    meaning at all, so the agent read the file to find out. Ranking classes strictly first was the
    next mistake: httpx has 87 of them, which used the whole second pass and still left `send`
    without a meaning, and nine slots went to test fixtures.

    So: library code before tests, public before private, then by how many call sites point at the
    symbol, with a class counted as if three things called it.

    Implementation lives in annotation_policy (policy "callers") alongside the alternatives it is
    benchmarked against.
    """
    return _rank_callers(symbols, calls)


def annotate_repository_symbols(
    repository: str, dest: Path, symbols: list[Symbol], *, store: MemoryStore, llm: LLMClient,
    calls: list[tuple[str, str]] | None = None, policy: str | None = None, budget: int | None = None,
) -> dict[str, int]:
    """Annotate up to `budget` symbols whose content hash changed (or is new), in the order the
    selection `policy` ranks them (annotation_policy; defaults from CODEXA_ANNOTATE_POLICY /
    CODEXA_ANNOTATE_BUDGET, i.e. "callers" / 80).

    Returns {"annotated": n, "reused": n, "skipped": n} for observability.
    """
    policy = policy or configured_policy()
    budget = configured_budget() if budget is None else budget
    blob = _load_blob(store, repository)
    stats = {"annotated": 0, "reused": 0, "skipped": 0}
    file_cache: dict[str, list[str]] = {}
    models = llm.models_for_task("summary") or [llm.default_model]
    # Non-Gemini first. This runs in the background after every edit; Gemini's free tier allows 20
    # requests per model per key per day, and the task planner and delegated workers need them.
    models = sorted(models, key=lambda m: m.startswith("gemini/"))

    churn = None
    if policy == "git_churn":
        from backend.repository.annotation_policy import mine_file_churn

        churn = mine_file_churn(dest)
    ranked = rank_symbols(symbols, calls, policy, file_churn=churn)
    ranked_keys = {id(s) for s in ranked}
    # Symbols the policy does not rank eagerly (all of them, for "lazy") still count as reused when
    # a current annotation exists — only fresh LLM calls are rationed.
    for sym in ranked + [s for s in symbols if id(s) not in ranked_keys]:
        stable_id = f"symbol://{repository}/{sym.file}#{sym.qualname or sym.name}"
        prior = blob.get(stable_id)
        if prior and prior.get("hash") == sym.content_hash:
            stats["reused"] += 1
            continue
        if stats["annotated"] >= budget or id(sym) not in ranked_keys:
            stats["skipped"] += 1
            continue

        lines = file_cache.get(sym.file)
        if lines is None:
            try:
                lines = (dest / sym.file).read_text(encoding="utf-8", errors="ignore").split("\n")
            except OSError:
                lines = []
            file_cache[sym.file] = lines
        end = sym.end_line if sym.end_line >= sym.line else sym.line
        snippet = "\n".join(lines[max(0, sym.line - 1):end])[:1500]
        if not snippet.strip():
            stats["skipped"] += 1
            continue

        prompt = (
            f"Describe what this {sym.kind} named `{sym.qualname or sym.name}` does in ONE short sentence — its "
            "purpose and any notable side effects. Be concrete and specific, no filler, no preamble.\n\n"
            f"```\n{snippet}\n```"
        )
        summary = _annotate_one(llm, models, prompt)
        if not summary:
            stats["skipped"] += 1
            continue

        blob[stable_id] = {"hash": sym.content_hash, "summary": summary, "file": sym.file, "name": sym.name,
                           "qualname": sym.qualname or sym.name}
        stats["annotated"] += 1

    # Keep only meanings that still describe the code: drop symbols that no longer exist, and any
    # whose code changed but wasn't re-annotated this run (cap reached, model unavailable). A missing
    # meaning makes the agent read the code; a stale one tells it something untrue.
    current = {f"symbol://{repository}/{s.file}#{s.qualname or s.name}": s.content_hash for s in symbols}
    blob = {k: v for k, v in blob.items() if k in current and v.get("hash") == current[k]}

    _save_blob(store, repository, blob)
    return stats


def _span_hash(lines: list[str], line: int, end_line: int) -> tuple[str, str]:
    """(snippet, content_hash) for a 1-based inclusive line span — the same hash analyze.py computes
    for Symbol.content_hash, so an on-demand annotation is reused/invalidated exactly like an eager one."""
    import hashlib

    end = end_line if end_line >= line else line
    span = "\n".join(lines[max(0, line - 1):end])
    return span, hashlib.sha256(span.encode("utf-8", errors="ignore")).hexdigest()[:16]


def annotate_on_demand(
    repository: str, dest: Path, *, file: str, qualname: str, kind: str, line: int, end_line: int,
    content_hash: str | None, store: MemoryStore, llm: LLMClient,
) -> str | None:
    """The `lazy` policy: write a symbol's meaning the first time an agent asks about it, then cache
    it under the same content-hash key an eager pass would use. Returns the summary, or None."""
    stable_id = f"symbol://{repository}/{file}#{qualname}"
    blob = _load_blob(store, repository)
    try:
        lines = (dest / file).read_text(encoding="utf-8", errors="ignore").split("\n")
    except OSError:
        return None
    snippet, span_hash = _span_hash(lines, line, end_line)
    current_hash = content_hash or span_hash
    prior = blob.get(stable_id)
    if prior and prior.get("hash") == current_hash:
        return prior.get("summary")
    if not snippet.strip():
        return None
    models = sorted(llm.models_for_task("summary") or [llm.default_model], key=lambda m: m.startswith("gemini/"))
    prompt = (
        f"Describe what this {kind} named `{qualname}` does in ONE short sentence — its "
        "purpose and any notable side effects. Be concrete and specific, no filler, no preamble.\n\n"
        f"```\n{snippet[:1500]}\n```"
    )
    summary = _annotate_one(llm, models, prompt)
    if not summary:
        return None
    blob[stable_id] = {"hash": current_hash, "summary": summary, "file": file,
                       "name": qualname.rsplit(".", 1)[-1], "qualname": qualname, "on_demand": "1"}
    _save_blob(store, repository, blob)
    return summary


def get_annotation(store: MemoryStore, repository: str, file: str, name: str) -> str | None:
    blob = _load_blob(store, repository)
    entry = blob.get(f"symbol://{repository}/{file}#{name}")
    return entry.get("summary") if entry else None
