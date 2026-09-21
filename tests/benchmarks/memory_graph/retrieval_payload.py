"""Retrieval-payload benchmark: the token cost of ANSWERING a code-navigation question
via Codexa's knowledge graph vs raw file reading — measured directly, with no LLM in the loop.

Why this and not the agentic runner: on hard multi-hop questions no agent (mercury, solar, glm)
reliably converges — every arm thrashes to hundreds of thousands of tokens without a final answer,
so the agentic token totals measure loop instability, not retrieval efficiency. This script removes
the model entirely and measures the thing that actually drives cost: for a fixed information need,
how many tokens must each architecture pull into context to contain the answer.

Information need (per symbol X): "Where is X defined, and what calls / depends on it?" — the single
most common code-navigation question, and the unit a trace question is built from.

  - Graph retrieval  = lookup_symbol(X) + get_dependencies(X). One targeted result: the definition
                       site plus every caller/dependent, straight from the graph.
  - Raw retrieval    = to obtain the SAME facts, an agent must open the file that DEFINES X and every
                       file that REFERENCES X (the graph's own incoming edges name those files), then
                       read them to find the references. Payload = the bytes of those files.

Both file sets come from the same graph, so the comparison is apples-to-apples: identical answer,
two retrieval strategies. Tokens are counted with tiktoken (cl100k_base). Deterministic and
reproducible — re-running gives the same numbers.
"""
import json
import os
import random
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent.parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

import tiktoken

from backend.graph.service import GraphService
from backend.graph.repository import InMemoryGraphRepository
from backend.graph.events import InMemoryGraphEventWriter
from backend.repository.api import reindex_repository
from backend.memory.store import MemoryStore
from backend.files.api import repo_root
import backend.agents.tools as T

REPO = os.getenv("BENCHMARK_REPO", "Exam-Proctoring")
SAMPLE = int(os.getenv("PAYLOAD_SAMPLE", "40"))
PRICE_IN = float(os.getenv("BENCHMARK_PRICE_IN", "0.25"))   # USD / 1M input tokens
SEED = int(os.getenv("PAYLOAD_SEED", "7"))

_enc = tiktoken.get_encoding("cl100k_base")
def toks(s: str) -> int:
    return len(_enc.encode(s or ""))


def main() -> None:
    random.seed(SEED)
    graph = GraphService(repository=InMemoryGraphRepository(), event_writer=InMemoryGraphEventWriter())
    store = MemoryStore()
    print(f"Reindexing {REPO} into in-memory graph ...", flush=True)
    reindex_repository(REPO, store=store, graph=graph, llm=None)

    nodes = graph.list_nodes()
    edges = graph.list_edges_at()
    by_id = {n.id: n for n in nodes}

    def in_repo(n):
        rp = n.properties.get("repository")
        return (not rp) if REPO == "codexa-os" else rp == REPO

    # Candidate targets: symbols (functions/methods/classes) that have at least one incoming
    # caller/dependent edge — i.e. real navigation targets a trace question would land on.
    dep_edges = {"imports", "calls", "depends_on", "flows_into"}
    incoming_by_node: dict[str, set] = {}
    for e in edges:
        if e.edge_type in dep_edges:
            incoming_by_node.setdefault(e.to_node_id, set()).add(e.from_node_id)

    candidates = []
    for n in nodes:
        if not in_repo(n):
            continue
        kind = str(getattr(n, "node_type", "")).lower()
        name = n.properties.get("name")
        file_ = n.properties.get("file") or n.properties.get("path")
        if not name or not file_:
            continue
        if any(k in kind for k in ("function", "method", "symbol", "class")) and n.id in incoming_by_node:
            candidates.append(n)

    if not candidates:
        print("No symbols with dependents found — the graph may lack call/reference edges.")
        return
    random.shuffle(candidates)
    sample = candidates[:SAMPLE]
    print(f"{len(candidates)} navigable symbols in graph; sampling {len(sample)}.\n", flush=True)

    root = repo_root(REPO)
    file_cache: dict[str, int] = {}
    def file_tokens(rel: str) -> int:
        if rel in file_cache:
            return file_cache[rel]
        p = root / rel
        try:
            t = toks(p.read_text(encoding="utf-8", errors="ignore"))
        except Exception:  # noqa: BLE001
            t = 0
        file_cache[rel] = t
        return t

    rows = []
    for n in sample:
        name = n.properties.get("name")
        def_file = n.properties.get("file") or n.properties.get("path")
        # Files raw must open: the defining file + every file that references the symbol.
        ref_files = {def_file}
        for src_id in incoming_by_node.get(n.id, set()):
            src = by_id.get(src_id)
            if src:
                f = src.properties.get("file") or src.properties.get("path")
                if f:
                    ref_files.add(f)
        raw_tok = sum(file_tokens(f) for f in ref_files)

        graph_out = _safe(lambda: T._lookup_symbol(name, REPO, graph=graph, store=store))
        dep_out = _safe(lambda: T._get_dependencies(name, REPO, graph=graph))
        graph_tok = toks(graph_out) + toks(dep_out)

        if raw_tok <= 0 or graph_tok <= 0:
            continue
        rows.append({
            "symbol": name, "def_file": def_file, "n_ref_files": len(ref_files),
            "raw_tokens": raw_tok, "graph_tokens": graph_tok,
            "reduction_x": raw_tok / graph_tok,
        })

    if not rows:
        print("No measurable rows.")
        return

    raw_total = sum(r["raw_tokens"] for r in rows)
    graph_total = sum(r["graph_tokens"] for r in rows)
    import statistics as st
    mean_x = st.mean(r["reduction_x"] for r in rows)
    med_x = st.median(r["reduction_x"] for r in rows)

    # Memory arm (secondary): the whole project-memory payload Codexa injects is a small constant;
    # the raw alternative to "know the project conventions" is to read the repo. Report both sizes.
    mem_records = store.list(REPO) if hasattr(store, "list") else []
    mem_text = "\n".join(getattr(r, "content", "") or "" for r in mem_records) if mem_records else ""
    mem_tok = toks(mem_text)
    repo_src_tok = 0
    for f in sorted(file_cache):  # already-read files; approximate repo source scanned
        repo_src_tok += file_cache[f]

    out = {
        "repository": REPO, "n_symbols": len(rows),
        "raw_total_tokens": raw_total, "graph_total_tokens": graph_total,
        "overall_reduction_x": raw_total / graph_total,
        "mean_per_symbol_reduction_x": mean_x, "median_reduction_x": med_x,
        "usd_per_1M_input": PRICE_IN,
        "raw_cost_usd": raw_total / 1e6 * PRICE_IN, "graph_cost_usd": graph_total / 1e6 * PRICE_IN,
        "memory_records": len(mem_records), "memory_payload_tokens": mem_tok,
        "rows": sorted(rows, key=lambda r: -r["reduction_x"]),
    }
    (Path(__file__).parent / "retrieval_payload_result.json").write_text(json.dumps(out, indent=2), encoding="utf-8")

    print("=" * 64)
    print(f"RETRIEVAL PAYLOAD — {REPO}  (n={len(rows)} navigable symbols)")
    print("=" * 64)
    print(f"Raw file-retrieval total:   {raw_total:>12,} tokens")
    print(f"Graph retrieval total:      {graph_total:>12,} tokens")
    print(f"Overall reduction:          {raw_total / graph_total:>11.1f}x  "
          f"({(1 - graph_total / raw_total) * 100:.1f}% fewer tokens)")
    print(f"Per-symbol reduction:       mean {mean_x:.1f}x, median {med_x:.1f}x")
    print(f"Cost @ ${PRICE_IN:.2f}/1M in:  raw ${raw_total/1e6*PRICE_IN:.4f}  vs  "
          f"graph ${graph_total/1e6*PRICE_IN:.4f}  per {len(rows)} lookups")
    print(f"Project memory injected:    {mem_tok:,} tokens ({len(mem_records)} records) — a fixed "
          f"constant that replaces re-deriving conventions from source each time.")
    print("\nTop reductions:")
    for r in out["rows"][:8]:
        print(f"  {r['symbol'][:34]:34} raw {r['raw_tokens']:>7,} -> graph {r['graph_tokens']:>5,}  "
              f"= {r['reduction_x']:.0f}x  ({r['n_ref_files']} files)")
    print(f"\n[written] {Path(__file__).parent / 'retrieval_payload_result.json'}")


def _safe(fn):
    try:
        return fn() or ""
    except Exception as exc:  # noqa: BLE001
        return f"(error: {exc})"


if __name__ == "__main__":
    main()
