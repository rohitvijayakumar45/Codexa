"""Code-anchored memory: deterministic invalidation of memory records when the code they describe
changes (backend/memory/anchors.py, MemoryStore anchors/invalidate, anchor-driven repo ingestion,
retrieval-time freshness in backend/memory/context.py).

Safety-relevant behaviour pinned here:
- a descriptive fact about changed code is never served again (invalidated, not just flagged);
- episodic history is never destroyed by a code change (flagged outdated instead);
- a record with no anchors, or an anchor kind the checker does not know, is never invalidated —
  the destructive side fails open.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from backend.graph.events import InMemoryGraphEventWriter
from backend.graph.repository import InMemoryGraphRepository
from backend.graph.service import GraphService
from backend.memory import context as memory_context
from backend.memory.anchors import (
    check_anchors,
    file_anchor,
    is_outdated,
    symbol_anchor,
    symbols_index_anchor,
    sweep_repository,
    tree_anchor,
)
from backend.memory.store import MemoryStore
from backend.repository import api as repo_api
from backend.repository.analyze import analyze_repo, symbol_key


def _write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _store(tmp_path: Path) -> MemoryStore:
    return MemoryStore(path=tmp_path / "memories.json")


# --- anchor checks --------------------------------------------------------------------------------

class TestFileAnchors:
    def test_valid_until_the_file_changes(self, tmp_path):
        _write(tmp_path, "a.py", "x = 1\n")
        anchors = [file_anchor(tmp_path, "a.py")]
        assert check_anchors(tmp_path, anchors).status == "valid"
        _write(tmp_path, "a.py", "x = 2\n")
        result = check_anchors(tmp_path, anchors)
        assert result.status == "stale"
        assert result.changed[0]["path"] == "a.py"

    def test_deleting_the_file_is_a_change(self, tmp_path):
        _write(tmp_path, "a.py", "x = 1\n")
        anchors = [file_anchor(tmp_path, "a.py")]
        (tmp_path / "a.py").unlink()
        assert check_anchors(tmp_path, anchors).status == "stale"

    def test_absent_file_anchor_goes_stale_when_the_file_appears(self, tmp_path):
        anchors = [file_anchor(tmp_path, "package.json")]
        assert anchors[0]["hash"] is None
        assert check_anchors(tmp_path, anchors).status == "valid"
        _write(tmp_path, "package.json", "{}")
        assert check_anchors(tmp_path, anchors).status == "stale"

    def test_no_anchors_is_unanchored_not_stale(self, tmp_path):
        assert check_anchors(tmp_path, []).status == "unanchored"
        assert check_anchors(tmp_path, None).status == "unanchored"

    def test_unknown_anchor_kind_fails_open(self, tmp_path):
        assert check_anchors(tmp_path, [{"kind": "from_the_future", "x": 1}]).status == "valid"


class TestStructuralAnchors:
    def _repo(self, root: Path) -> None:
        _write(root, "pkg/core.py", "def parse(text):\n    return text.split()\n\n\ndef other():\n    return 1\n")

    def test_symbol_anchor_tracks_only_its_own_span(self, tmp_path):
        self._repo(tmp_path)
        code = analyze_repo(tmp_path)
        parse = next(s for s in code.symbols if s.name == "parse")
        anchors = [symbol_anchor(parse)]
        # editing a DIFFERENT symbol in the same file keeps it valid (a file anchor would not)
        _write(tmp_path, "pkg/core.py", "def parse(text):\n    return text.split()\n\n\ndef other():\n    return 2\n")
        assert check_anchors(tmp_path, anchors).status == "valid"
        assert check_anchors(tmp_path, [file_anchor(tmp_path, "pkg/core.py") | {"hash": "old"}]).status == "stale"
        _write(tmp_path, "pkg/core.py", "def parse(text):\n    return text.split(',')\n\n\ndef other():\n    return 2\n")
        assert check_anchors(tmp_path, anchors).status == "stale"

    def test_symbol_anchor_stale_when_symbol_removed(self, tmp_path):
        self._repo(tmp_path)
        parse = next(s for s in analyze_repo(tmp_path).symbols if s.name == "parse")
        _write(tmp_path, "pkg/core.py", "def other():\n    return 1\n")
        assert check_anchors(tmp_path, [symbol_anchor(parse)]).status == "stale"

    def test_tree_and_symbols_index_anchors(self, tmp_path):
        self._repo(tmp_path)
        code = analyze_repo(tmp_path)
        tree = [tree_anchor(code.all_files)]
        index = [symbols_index_anchor(code.symbols)]
        _write(tmp_path, "pkg/core.py", "def parse(text):\n    return 0\n\n\ndef other():\n    return 1\n")
        assert check_anchors(tmp_path, tree).status == "valid"   # same paths
        assert check_anchors(tmp_path, index).status == "valid"  # same symbol keys
        _write(tmp_path, "pkg/new.py", "def added():\n    pass\n")
        assert check_anchors(tmp_path, tree).status == "stale"
        assert check_anchors(tmp_path, index).status == "stale"

    def test_precomputed_analysis_is_used(self, tmp_path):
        self._repo(tmp_path)
        code = analyze_repo(tmp_path)
        parse = next(s for s in code.symbols if s.name == "parse")
        assert symbol_key(parse) == "pkg/core.py#parse"
        assert check_anchors(tmp_path, [symbol_anchor(parse)], analysis=code).status == "valid"


# --- store ----------------------------------------------------------------------------------------

class TestStoreAnchors:
    def test_anchors_persist_across_reload(self, tmp_path):
        _write(tmp_path, "a.py", "x = 1\n")
        store = _store(tmp_path)
        rec = store.add(repository="r", memory_type="semantic", title="t", content="c",
                        anchors=[file_anchor(tmp_path, "a.py")])
        again = MemoryStore(path=store.path)
        assert again.get(rec.id).anchors == rec.anchors

    def test_invalidate_hides_record_and_is_idempotent(self, tmp_path):
        store = _store(tmp_path)
        rec = store.add(repository="r", memory_type="semantic", title="t", content="c")
        assert store.invalidate(rec.id, reason="because") is True
        assert store.invalidate(rec.id, reason="again") is False
        assert rec.id not in {r.id for r in store.list("r")}
        assert store.get(rec.id).metadata["invalidated_reason"] == "because"
        assert store.invalidate("missing", reason="x") is False

    def test_corroboration_repins_anchors_and_clears_outdated(self, tmp_path):
        store = _store(tmp_path)
        first = store.add(repository="r", memory_type="episodic", title="t", content="same",
                          anchors=[{"kind": "file", "path": "a.py", "hash": "old"}])
        store.update_metadata(first.id, {"outdated_at": "2026-01-01"})
        again = store.add(repository="r", memory_type="episodic", title="t", content="same",
                          anchors=[{"kind": "file", "path": "a.py", "hash": "new"}])
        assert again.id == first.id
        assert again.anchors[0]["hash"] == "new"
        assert not is_outdated(again)


# --- sweep ----------------------------------------------------------------------------------------

class TestSweep:
    def test_sweep_invalidates_descriptive_flags_episodic_ignores_unanchored(self, tmp_path):
        _write(tmp_path, "a.py", "x = 1\n")
        _write(tmp_path, "b.py", "y = 1\n")
        store = _store(tmp_path)
        a = [file_anchor(tmp_path, "a.py")]
        sem = store.add(repository="r", memory_type="semantic", title="about a", content="x is 1", anchors=a)
        proc = store.add(repository="r", memory_type="procedural", title="run a", content="python a.py", anchors=a)
        epi = store.add(repository="r", memory_type="episodic", title="edited a", content="set x", anchors=a)
        keep = store.add(repository="r", memory_type="semantic", title="about b", content="y is 1",
                         anchors=[file_anchor(tmp_path, "b.py")])
        loose = store.add(repository="r", memory_type="organizational", title="team", content="no anchors")

        _write(tmp_path, "a.py", "x = 2\n")
        report = sweep_repository(store, "r", tmp_path)

        active = {r.id for r in store.list("r")}
        assert sem.id not in active and proc.id not in active
        assert epi.id in active and is_outdated(store.get(epi.id))
        assert keep.id in active and loose.id in active
        assert set(report.invalidated) == {sem.id, proc.id}
        assert report.outdated == [epi.id]
        assert report.unanchored == 1 and report.valid == 1

    def test_sweep_is_idempotent(self, tmp_path):
        _write(tmp_path, "a.py", "x = 1\n")
        store = _store(tmp_path)
        store.add(repository="r", memory_type="episodic", title="e", content="c",
                  anchors=[file_anchor(tmp_path, "a.py")])
        _write(tmp_path, "a.py", "x = 2\n")
        first = sweep_repository(store, "r", tmp_path, now=datetime(2026, 1, 1, tzinfo=UTC))
        second = sweep_repository(store, "r", tmp_path)
        assert len(first.outdated) == 1 and second.outdated == []
        assert store.list("r", "episodic")[0].metadata["outdated_at"].startswith("2026-01-01")

    def test_sweep_only_touches_the_named_repository(self, tmp_path):
        _write(tmp_path, "a.py", "x = 1\n")
        store = _store(tmp_path)
        other = store.add(repository="other", memory_type="semantic", title="t", content="c",
                          anchors=[file_anchor(tmp_path, "a.py")])
        _write(tmp_path, "a.py", "x = 2\n")
        sweep_repository(store, "r", tmp_path)
        assert other.id in {r.id for r in store.list("other")}


# --- retrieval-time freshness ---------------------------------------------------------------------

class TestRetrievalFreshness:
    def test_stale_descriptive_not_served_and_episodic_marked(self, tmp_path, monkeypatch):
        _write(tmp_path, "a.py", "x = 1\n")
        store = _store(tmp_path)
        a = [file_anchor(tmp_path, "a.py")]
        sem = store.add(repository="r", memory_type="semantic", title="about a", content="x is 1", anchors=a)
        epi = store.add(repository="r", memory_type="episodic", title="edited a", content="set x", anchors=a)
        monkeypatch.setattr("backend.files.api.repo_root", lambda repo: tmp_path)
        _write(tmp_path, "a.py", "x = 2\n")
        fresh = memory_context._fresh_records(store, "r", store.list("r"))
        ids = {r.id for r in fresh}
        assert sem.id not in ids and store.get(sem.id).invalid_at is not None
        assert epi.id in ids and is_outdated(store.get(epi.id))

    def test_context_route_prefixes_outdated_episodes(self, tmp_path, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        _write(tmp_path, "a.py", "x = 1\n")
        store = _store(tmp_path)
        store.add(repository="r", memory_type="episodic", title="history of loading", content="loaded it",
                  anchors=[file_anchor(tmp_path, "a.py")])
        monkeypatch.setattr("backend.files.api.repo_root", lambda repo: tmp_path)
        _write(tmp_path, "a.py", "x = 2\n")
        graph = GraphService(repository=InMemoryGraphRepository(), event_writer=InMemoryGraphEventWriter())
        app = FastAPI()
        app.include_router(memory_context.create_context_router(store=store, graph=graph))
        items = TestClient(app).get("/memory/context", params={"repository": "r", "query": "history loaded"}).json()
        episode = next(i for i in items if i["title"] == "history of loading")
        assert episode["content"].startswith("(code changed since)")

    def test_memory_type_ablation_switch(self, monkeypatch):
        monkeypatch.setenv("CODEXA_MEMORY_TYPES", "semantic, procedural")
        assert memory_context._type_enabled("semantic") and memory_context._type_enabled("procedural")
        assert not memory_context._type_enabled("episodic")
        monkeypatch.delenv("CODEXA_MEMORY_TYPES")
        assert memory_context._type_enabled("episodic")


# --- ingestion ------------------------------------------------------------------------------------

class TestAnchoredIngest:
    def _graph(self) -> GraphService:
        return GraphService(repository=InMemoryGraphRepository(), event_writer=InMemoryGraphEventWriter())

    def _repo(self, root: Path) -> None:
        _write(root, "package.json", '{"name": "demo", "scripts": {"dev": "vite"}, "dependencies": {"react": "1"}}')
        _write(root, "src/app.js", "export function main() { return helper(); }\nfunction helper() { return 1; }\n")

    def _records(self, store: MemoryStore, repo: str = "demo") -> dict[str, object]:
        return {r.title: r for r in store.list(repo)}

    def test_ingest_attaches_anchors_to_every_digest_fact(self, tmp_path):
        repo = tmp_path / "demo"
        self._repo(repo)
        store = _store(tmp_path)
        repo_api._ingest("demo", "", repo, False, store=store, graph=self._graph())
        recs = self._records(store)
        for title in ("Project structure", "Stack & conventions", "How to build & run", "Key functions & components"):
            assert recs[title].anchors, title
        assert any(t.startswith("Loaded into Codexa (") for t in recs)

    def test_reingest_keeps_unchanged_facts_and_replaces_changed_ones(self, tmp_path):
        repo = tmp_path / "demo"
        self._repo(repo)
        store = _store(tmp_path)
        repo_api._ingest("demo", "", repo, False, store=store, graph=self._graph())
        before = self._records(store)

        _write(repo, "package.json", '{"name": "demo", "scripts": {"dev": "vite", "test": "vitest"}, "dependencies": {"react": "1"}}')
        repo_api._ingest("demo", "", repo, True, store=store, graph=self._graph(), record_load_event=False)
        after = self._records(store)

        # layout and symbols did not change: the SAME record survives (corroborated), not a rewrite
        assert after["Project structure"].id == before["Project structure"].id
        assert after["Key functions & components"].id == before["Key functions & components"].id
        # the build instructions changed: the old record is invalidated, the new one is current
        assert after["How to build & run"].id != before["How to build & run"].id
        assert "npm run test" in after["How to build & run"].content
        assert store.get(before["How to build & run"].id).invalid_at is not None

    def test_reindex_does_not_append_load_events_but_reload_does(self, tmp_path):
        repo = tmp_path / "demo"
        self._repo(repo)
        store = _store(tmp_path)
        repo_api._ingest("demo", "", repo, False, store=store, graph=self._graph())
        repo_api._ingest("demo", "", repo, True, store=store, graph=self._graph(), record_load_event=False)
        repo_api._ingest("demo", "", repo, True, store=store, graph=self._graph(), invalidate_docs=False)
        loads = [r for r in store.list("demo", "episodic") if r.metadata.get("event") == "repo_load"]
        assert len(loads) == 1

    def test_ingest_sweeps_agent_experience_about_changed_code(self, tmp_path):
        repo = tmp_path / "demo"
        self._repo(repo)
        store = _store(tmp_path)
        repo_api._ingest("demo", "", repo, False, store=store, graph=self._graph())
        fact = store.add(repository="demo", memory_type="semantic", title="main returns helper()",
                         content="main delegates to helper", anchors=[file_anchor(repo, "src/app.js")])
        _write(repo, "src/app.js", "export function main() { return 2; }\n")
        repo_api._ingest("demo", "", repo, True, store=store, graph=self._graph(), record_load_event=False)
        assert store.get(fact.id).invalid_at is not None

    def test_symbol_nodes_carry_content_hash(self, tmp_path):
        repo = tmp_path / "demo"
        self._repo(repo)
        graph = self._graph()
        repo_api._ingest("demo", "", repo, False, store=_store(tmp_path), graph=graph)
        sym = next(n for n in graph.list_nodes() if n.node_type == "CodeSymbol" and n.properties["name"] == "main")
        assert len(sym.properties["content_hash"]) == 16
        assert sym.properties["end_line"] >= sym.properties["line"]
