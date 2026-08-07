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

_MAX_ANNOTATE_PER_RUN = 80
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


def annotate_repository_symbols(
    repository: str, dest: Path, symbols: list[Symbol], *, store: MemoryStore, llm: LLMClient,
) -> dict[str, int]:
    """Annotate up to _MAX_ANNOTATE_PER_RUN symbols whose content hash changed (or is new).

    Returns {"annotated": n, "reused": n, "skipped": n} for observability.
    """
    blob = _load_blob(store, repository)
    stats = {"annotated": 0, "reused": 0, "skipped": 0}
    file_cache: dict[str, list[str]] = {}
    models = llm.models_for_task("summary") or [llm.default_model]

    for sym in symbols:
        stable_id = f"symbol://{repository}/{sym.file}#{sym.name}"
        prior = blob.get(stable_id)
        if prior and prior.get("hash") == sym.content_hash:
            stats["reused"] += 1
            continue
        if stats["annotated"] >= _MAX_ANNOTATE_PER_RUN:
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
            f"Describe what this {sym.kind} named `{sym.name}` does in ONE short sentence — its "
            "purpose and any notable side effects. Be concrete and specific, no filler, no preamble.\n\n"
            f"```\n{snippet}\n```"
        )
        summary = _annotate_one(llm, models, prompt)
        if not summary:
            stats["skipped"] += 1
            continue

        blob[stable_id] = {"hash": sym.content_hash, "summary": summary, "file": sym.file, "name": sym.name}
        stats["annotated"] += 1

    # Drop entries for symbols that no longer exist in this ingest.
    live_ids = {f"symbol://{repository}/{s.file}#{s.name}" for s in symbols}
    blob = {k: v for k, v in blob.items() if k in live_ids}

    _save_blob(store, repository, blob)
    return stats


def get_annotation(store: MemoryStore, repository: str, file: str, name: str) -> str | None:
    blob = _load_blob(store, repository)
    entry = blob.get(f"symbol://{repository}/{file}#{name}")
    return entry.get("summary") if entry else None
