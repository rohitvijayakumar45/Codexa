"""Code anchors: deterministic invalidation of memory against the code it describes.

A memory record that describes the code ("the build command is `npm run dev`", "`parse()` is the
tokenizer entry point", "the project is laid out as backend/ + web/") silently goes stale the moment
that code changes. Before this module the only defence was a repository-wide wipe on reload, which
throws away every still-true fact along with the stale ones and does nothing at all between reloads.

An anchor pins a record to a concrete, hashable piece of the repository:

    file           a repo-relative path + sha256 of its bytes (or None: "this file must not exist")
    symbol         a symbol key (file#qualname) + the content hash of that symbol's source span
    tree           a hash of the sorted list of every non-skipped path (project layout)
    symbols_index  a hash of the sorted list of every symbol key (the repo's public surface)
    query          a hash of the result of a deterministic graph query — callers(X), callees(X),
                   imports(file). For a fact that IS a graph query result, this is exact: it goes
                   stale iff the answer changed, not whenever some byte near it did.

`check_anchors` recomputes each anchor against the working tree. No LLM, no heuristics: an anchor
either still hashes to the same value or it does not. A record is `valid` when every anchor matches,
`stale` when any anchor changed, and `unanchored` when it carries no anchors (it is then left alone —
the absence of evidence is not evidence of staleness).

What happens to a stale record depends on its memory type (see `sweep_repository`):

    semantic / procedural / organizational   descriptive: a claim about the CURRENT code. Stale means
                                             false, so the record is soft-invalidated (invalid_at).
    episodic                                 historical: "on 2026-09-20 the agent edited X" stays
                                             true after X changes. It is flagged outdated instead, so
                                             retrieval can say "(code changed since)" rather than
                                             either hiding real history or presenting it as current.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Literal

if TYPE_CHECKING:  # pragma: no cover - typing only
    from backend.memory.store import MemoryStore
    from backend.repository.analyze import Analysis, Symbol

AnchorStatus = Literal["valid", "stale", "unanchored"]

DESCRIPTIVE_TYPES = ("semantic", "procedural", "organizational")
HISTORICAL_TYPES = ("episodic",)


# --- anchor construction ------------------------------------------------------------------------

def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hash_lines(items: Iterable[str]) -> str:
    return _sha256_bytes("\n".join(sorted(items)).encode("utf-8"))


def file_hash(root: Path, rel: str) -> str | None:
    """sha256 of a repo-relative file's bytes, or None if it does not exist / is not a file."""
    path = Path(root) / rel
    try:
        if not path.is_file():
            return None
        return _sha256_bytes(path.read_bytes())
    except OSError:
        return None


def file_anchor(root: Path, rel: str) -> dict[str, Any]:
    """Anchor to a file's current bytes. A missing file is anchored as hash=None, which is itself a
    checkable claim: the record stays valid only while the file keeps not existing."""
    rel = rel.replace("\\", "/")
    return {"kind": "file", "path": rel, "hash": file_hash(root, rel)}


def symbol_anchor(sym: "Symbol") -> dict[str, Any]:
    from backend.repository.analyze import symbol_key

    return {"kind": "symbol", "key": symbol_key(sym), "file": sym.file, "content_hash": sym.content_hash}


def tree_anchor(paths: Iterable[str]) -> dict[str, Any]:
    return {"kind": "tree", "hash": _hash_lines(p.replace("\\", "/") for p in paths)}


def symbols_index_anchor(symbols: Iterable["Symbol"]) -> dict[str, Any]:
    from backend.repository.analyze import symbol_key

    return {"kind": "symbols_index", "hash": _hash_lines(symbol_key(s) for s in symbols)}


QUERY_KINDS = ("callers", "callees", "imports")


_MISSING = "<subject does not exist>"


class QueryIndex:
    """callers/callees/imports lookups over one Analysis, built in a single pass over its edges."""

    def __init__(self, analysis: "Analysis") -> None:
        from backend.repository.analyze import symbol_key

        self.symbols = {symbol_key(s) for s in analysis.symbols}
        self.files = set(analysis.files)
        self.edges: dict[tuple[str, str], set[str]] = {}
        for a, b in analysis.calls:
            self.edges.setdefault(("callers", b), set()).add(a)
            self.edges.setdefault(("callees", a), set()).add(b)
        for a, b in analysis.imports:
            self.edges.setdefault(("imports", a), set()).add(b)

    def result(self, query: str, subject: str) -> list[str]:
        if query not in QUERY_KINDS:
            raise ValueError(f"unknown graph query: {query}")
        # The subject's existence is part of the answer: "X has no callers" and "X was deleted"
        # must not hash the same, or deleting an uncalled symbol would look like no change.
        exists = subject in (self.files if query == "imports" else self.symbols)
        if not exists:
            return [_MISSING]
        return sorted(self.edges.get((query, subject), set()))


def query_result(analysis: "Analysis", query: str, subject: str) -> list[str]:
    """Deterministic graph queries over a parsed repository (the same edges the knowledge graph is
    built from): callers/callees of a symbol key, files imported by a file."""
    return QueryIndex(analysis).result(query, subject)


def query_anchor(analysis: "Analysis", query: str, subject: str, *,
                 index: QueryIndex | None = None) -> dict[str, Any]:
    """Pass a prebuilt `index` when anchoring many facts against the same analysis."""
    result = (index or QueryIndex(analysis)).result(query, subject)
    return {"kind": "query", "query": query, "subject": subject, "hash": _hash_lines(result)}


def file_anchors(root: Path, rels: Iterable[str]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for rel in rels:
        rel = rel.replace("\\", "/")
        if rel and rel not in seen:
            seen.add(rel)
            out.append(file_anchor(root, rel))
    return out


# --- anchor checking ----------------------------------------------------------------------------

@dataclass
class AnchorCheck:
    status: AnchorStatus
    changed: list[dict[str, Any]] = field(default_factory=list)  # anchors that no longer match

    @property
    def reason(self) -> str:
        if self.status != "stale":
            return self.status
        parts = []
        for a in self.changed[:4]:
            label = a.get("path") or a.get("key") or a["kind"]
            parts.append(f"{a['kind']}:{label}")
        more = f" (+{len(self.changed) - 4} more)" if len(self.changed) > 4 else ""
        return "anchors changed: " + ", ".join(parts) + more


class _LazyAnalysis:
    """Runs the (whole-repo) tree-sitter analysis at most once, and only if some anchor actually
    needs it. File anchors are checked by hashing alone, so a sweep over records anchored purely to
    files never parses anything."""

    def __init__(self, root: Path, analysis: "Analysis | None") -> None:
        self._root = Path(root)
        self._analysis = analysis
        self._symbol_hashes: dict[str, str] | None = None
        self._query_index: QueryIndex | None = None

    @property
    def analysis(self) -> "Analysis":
        if self._analysis is None:
            from backend.repository.analyze import analyze_repo

            self._analysis = analyze_repo(self._root)
        return self._analysis

    def query_hash(self, query: str, subject: str) -> str:
        if self._query_index is None:
            self._query_index = QueryIndex(self.analysis)
        return _hash_lines(self._query_index.result(query, subject))

    def symbol_hashes(self) -> dict[str, str]:
        if self._symbol_hashes is None:
            from backend.repository.analyze import symbol_key

            self._symbol_hashes = {symbol_key(s): s.content_hash for s in self.analysis.symbols}
        return self._symbol_hashes


def _anchor_matches(root: Path, anchor: dict[str, Any], lazy: _LazyAnalysis,
                    file_cache: dict[str, str | None]) -> bool:
    kind = anchor.get("kind")
    if kind == "file":
        rel = anchor.get("path", "")
        if rel not in file_cache:
            file_cache[rel] = file_hash(root, rel)
        return file_cache[rel] == anchor.get("hash")
    if kind == "symbol":
        return lazy.symbol_hashes().get(anchor.get("key", "")) == anchor.get("content_hash")
    if kind == "tree":
        return tree_anchor(lazy.analysis.all_files)["hash"] == anchor.get("hash")
    if kind == "symbols_index":
        return symbols_index_anchor(lazy.analysis.symbols)["hash"] == anchor.get("hash")
    if kind == "query" and anchor.get("query") in QUERY_KINDS:
        return lazy.query_hash(anchor["query"], anchor.get("subject", "")) == anchor.get("hash")
    # Unknown anchor kinds are treated as matching: an anchor this code cannot evaluate must never
    # destroy a record (fail open on the destructive side).
    return True


def check_anchors(
    root: Path, anchors: list[dict[str, Any]] | None, analysis: "Analysis | None" = None,
    *, _lazy: _LazyAnalysis | None = None, _file_cache: dict[str, str | None] | None = None,
) -> AnchorCheck:
    if not anchors:
        return AnchorCheck(status="unanchored")
    lazy = _lazy or _LazyAnalysis(root, analysis)
    cache = _file_cache if _file_cache is not None else {}
    changed = [a for a in anchors if not _anchor_matches(Path(root), a, lazy, cache)]
    return AnchorCheck(status="stale" if changed else "valid", changed=changed)


# --- sweeping a repository's memory -------------------------------------------------------------

@dataclass
class SweepReport:
    checked: int = 0
    valid: int = 0
    unanchored: int = 0
    invalidated: list[str] = field(default_factory=list)   # record ids (descriptive types)
    outdated: list[str] = field(default_factory=list)      # record ids (episodic)

    def as_dict(self) -> dict[str, Any]:
        return {
            "checked": self.checked, "valid": self.valid, "unanchored": self.unanchored,
            "invalidated": len(self.invalidated), "outdated": len(self.outdated),
        }


def sweep_repository(
    store: "MemoryStore", repository: str, root: Path, analysis: "Analysis | None" = None,
    *, now: datetime | None = None,
) -> SweepReport:
    """Re-check every active anchored record of `repository` against the working tree at `root`.

    Descriptive records whose anchors changed are soft-invalidated; episodic records are flagged
    outdated (metadata only — they stay active). Records without anchors are never touched.
    Idempotent: a second sweep over an unchanged tree changes nothing."""
    now = now or datetime.now(UTC)
    report = SweepReport()
    lazy = _LazyAnalysis(Path(root), analysis)
    cache: dict[str, str | None] = {}
    for record in store.list(repository=repository):
        report.checked += 1
        result = check_anchors(root, record.anchors, _lazy=lazy, _file_cache=cache)
        if result.status == "unanchored":
            report.unanchored += 1
            continue
        if result.status == "valid":
            report.valid += 1
            continue
        if record.memory_type in HISTORICAL_TYPES:
            if not record.metadata.get("outdated_at"):
                store.update_metadata(record.id, {"outdated_at": now.isoformat(),
                                                  "outdated_reason": result.reason})
                report.outdated.append(record.id)
        else:
            store.invalidate(record.id, reason=result.reason, when=now)
            report.invalidated.append(record.id)
    return report


def is_outdated(record: Any) -> bool:
    return bool(getattr(record, "metadata", {}).get("outdated_at"))
