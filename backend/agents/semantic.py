"""Local semantic code search over the in-memory knowledge graph.

Embeds every CodeSymbol and File node for a repository once, then answers a natural-language query
by cosine similarity — so "where is cheating detected" jumps straight to the proctoring controllers
instead of the agent grepping several terms and reading wrong files to find them. No vector-DB
server: a plain numpy matrix (brute-force cosine) is instant at repo scale (a few thousand nodes),
and embeddings are cached to disk (.codexa/embeddings/<repo>.npz) keyed by the node set so a
restart re-loads them for free instead of re-calling the embedding API.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

_CACHE_DIR = Path(".codexa") / "embeddings"


def _in_repo(node: Any, repository: str) -> bool:
    rp = node.properties.get("repository")
    # codexa-os is the self-repo whose nodes carry no explicit repository tag.
    return (not rp) if repository == "codexa-os" else rp == repository


def _index_items(graph: Any, repository: str) -> list[tuple[str, str, dict]]:
    """(node_id, text_to_embed, display_meta) for every symbol/file node in the repo."""
    items: list[tuple[str, str, dict]] = []
    for n in graph.list_nodes():
        if not _in_repo(n, repository):
            continue
        p = n.properties
        if n.node_type == "CodeSymbol":
            label = str(p.get("qualname") or p.get("name") or "?")
            kind = str(p.get("kind", "symbol"))
            file_ = p.get("file")
            text = f"{kind} {label} in {file_}"
            items.append((n.id, text, {"type": "symbol", "label": label, "kind": kind,
                                       "file": file_, "line": p.get("line")}))
        elif n.node_type == "File":
            path = str(p.get("path") or "?")
            items.append((n.id, f"file {path}", {"type": "file", "label": path,
                                                 "kind": "file", "file": path, "line": None}))
    return items


class SemanticIndex:
    """Per-repository embedding index, built lazily and cached in-process (+ on disk)."""

    def __init__(self) -> None:
        self._repos: dict[str, tuple[list[dict], np.ndarray]] = {}

    def build(self, repository: str, graph: Any, llm: Any, *, force: bool = False) -> int:
        if not force and repository in self._repos:
            return len(self._repos[repository][0])
        items = _index_items(graph, repository)
        if not items:
            self._repos[repository] = ([], np.zeros((0, 1), dtype=np.float32))
            return 0
        ids = [i for i, _, _ in items]
        metas = [m for _, _, m in items]
        sig = hashlib.sha1("|".join(ids).encode()).hexdigest()[:16]
        cache = _CACHE_DIR / f"{repository}.npz"
        if not force and cache.exists():
            try:
                d = np.load(cache, allow_pickle=False)
                if str(d["sig"]) == sig and d["mat"].shape[0] == len(ids):
                    self._repos[repository] = (metas, d["mat"].astype(np.float32))
                    return len(ids)
            except Exception:  # noqa: BLE001 - a bad cache just means re-embed
                logger.warning("semantic cache unreadable for %s; rebuilding", repository)
        texts = [t for _, t, _ in items]
        vecs = np.asarray(llm.embed(texts), dtype=np.float32)
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        mat = vecs / norms  # unit vectors so cosine == dot product
        self._repos[repository] = (metas, mat)
        try:
            _CACHE_DIR.mkdir(parents=True, exist_ok=True)
            np.savez(cache, sig=np.str_(sig), mat=mat)
        except Exception:  # noqa: BLE001 - caching is a nicety, not required
            logger.warning("could not write semantic cache for %s", repository)
        return len(ids)

    def search(self, repository: str, query: str, graph: Any, llm: Any, *, k: int = 8) -> list[dict]:
        if repository not in self._repos:
            self.build(repository, graph, llm)
        metas, mat = self._repos.get(repository, ([], None))  # type: ignore[assignment]
        if mat is None or len(metas) == 0:
            return []
        q = np.asarray(llm.embed([query])[0], dtype=np.float32)
        q = q / (np.linalg.norm(q) or 1.0)
        scores = mat @ q
        order = np.argsort(-scores)[:k]
        return [{**metas[i], "score": round(float(scores[i]), 3)} for i in order]

    def invalidate(self, repository: str) -> None:
        self._repos.pop(repository, None)


# Process-wide singleton — built lazily on first search per repo, mirroring the in-memory graph.
INDEX = SemanticIndex()
