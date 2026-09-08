"""Tests for deterministic memory conflict resolution (backend/memory/conflict.py) and its wiring
into MemoryStore.add() (backend/memory/store.py)."""

import tempfile
from pathlib import Path

from backend.memory.conflict import resolve_conflict
from backend.memory.store import MemoryStore


# ── Pure resolver logic ──────────────────────────────────────────────────────

class TestResolveConflict:
    def test_identical_content_corroborates(self):
        r = resolve_conflict(
            existing_content="Python 3.12, FastAPI backend", existing_trust=1.0, existing_corroboration_count=1,
            new_content="Python 3.12, FastAPI backend", new_trust=1.0,
        )
        assert r.action == "corroborate"

    def test_identical_content_ignores_surrounding_whitespace(self):
        r = resolve_conflict(
            existing_content="Python 3.12", existing_trust=1.0, existing_corroboration_count=1,
            new_content="  Python 3.12  ", new_trust=1.0,
        )
        assert r.action == "corroborate"

    def test_new_record_with_higher_score_supersedes(self):
        r = resolve_conflict(
            existing_content="uses MongoDB", existing_trust=0.3, existing_corroboration_count=1,
            new_content="uses PostgreSQL", new_trust=1.0,
        )
        assert r.action == "supersede"

    def test_tied_score_supersedes_favoring_recency(self):
        r = resolve_conflict(
            existing_content="uses MongoDB", existing_trust=1.0, existing_corroboration_count=1,
            new_content="uses PostgreSQL", new_trust=1.0,
        )
        assert r.action == "supersede"

    def test_low_scoring_new_record_is_rejected(self):
        r = resolve_conflict(
            existing_content="uses PostgreSQL", existing_trust=1.0, existing_corroboration_count=5,
            new_content="uses MongoDB", new_trust=0.2,
        )
        assert r.action == "reject"

    def test_corroboration_count_amplifies_existing_score(self):
        # Same per-record trust, but the existing record has been corroborated many times —
        # a single new contradicting record shouldn't be able to override that on trust alone.
        r = resolve_conflict(
            existing_content="A", existing_trust=0.9, existing_corroboration_count=10,
            new_content="B", new_trust=0.9,
        )
        assert r.action == "reject"


# ── MemoryStore.add() integration ───────────────────────────────────────────

def _store() -> MemoryStore:
    tmp = Path(tempfile.mkdtemp()) / "memories.json"
    return MemoryStore(path=tmp)


class TestMemoryStoreConflictWiring:
    def test_first_add_for_a_title_just_creates_a_record(self):
        store = _store()
        record = store.add(repository="repo", memory_type="organizational", title="Stack", content="FastAPI")
        assert record.content == "FastAPI"
        assert record.corroboration_count == 1
        assert record.invalid_at is None

    def test_repeating_identical_content_corroborates_instead_of_duplicating(self):
        store = _store()
        first = store.add(repository="repo", memory_type="organizational", title="Stack", content="FastAPI")
        second = store.add(repository="repo", memory_type="organizational", title="Stack", content="FastAPI")

        assert first.id == second.id  # same record, reinforced — not a new one
        assert second.corroboration_count == 2
        records = store.list(repository="repo", memory_type="organizational")
        assert len(records) == 1

    def test_higher_scoring_new_content_supersedes_and_soft_invalidates_old(self):
        store = _store()
        old = store.add(repository="repo", memory_type="organizational", title="Stack", content="MongoDB", trust=0.3)
        new = store.add(repository="repo", memory_type="organizational", title="Stack", content="PostgreSQL", trust=1.0)

        active = store.list(repository="repo", memory_type="organizational")
        assert len(active) == 1
        assert active[0].content == "PostgreSQL"

        # The old record still exists (soft-invalidated), visible via include_invalid — history preserved.
        all_records = store.list(repository="repo", memory_type="organizational", include_invalid=True)
        assert len(all_records) == 2
        old_after = next(r for r in all_records if r.id == old.id)
        assert old_after.invalid_at is not None

    def test_low_scoring_new_content_is_rejected_and_stored_already_invalid(self):
        store = _store()
        store.add(repository="repo", memory_type="organizational", title="Stack", content="PostgreSQL", trust=1.0)
        for _ in range(5):  # build up corroboration so the existing record's score is high
            store.add(repository="repo", memory_type="organizational", title="Stack", content="PostgreSQL", trust=1.0)

        rejected = store.add(repository="repo", memory_type="organizational", title="Stack", content="MongoDB", trust=0.1)

        assert rejected.invalid_at is not None
        active = store.list(repository="repo", memory_type="organizational")
        assert len(active) == 1
        assert active[0].content == "PostgreSQL"

    def test_different_titles_never_conflict(self):
        store = _store()
        store.add(repository="repo", memory_type="organizational", title="Stack", content="FastAPI")
        store.add(repository="repo", memory_type="organizational", title="Conventions", content="PEP8")

        assert len(store.list(repository="repo", memory_type="organizational")) == 2

    def test_different_repositories_never_conflict(self):
        store = _store()
        store.add(repository="repo-a", memory_type="organizational", title="Stack", content="FastAPI")
        store.add(repository="repo-b", memory_type="organizational", title="Stack", content="Django")

        assert len(store.list(repository="repo-a")) == 1
        assert len(store.list(repository="repo-b")) == 1

    def test_repositories_summary_excludes_invalidated_records(self):
        store = _store()
        store.add(repository="repo", memory_type="organizational", title="Stack", content="MongoDB", trust=0.1)
        store.add(repository="repo", memory_type="organizational", title="Stack", content="PostgreSQL", trust=1.0)

        summary = next(s for s in store.repositories() if s.repository == "repo")
        assert summary.total == 1
        assert summary.counts["organizational"] == 1

    def test_superseding_after_removal_behaves_like_a_fresh_add(self):
        # The repo-load path always calls remove() before add() — confirms that flow (no lingering
        # "existing" record) still behaves exactly like a first-time add, not a conflict.
        store = _store()
        store.add(repository="repo", memory_type="semantic", title="What it is", content="v1", metadata={"source": "repo_load"})
        store.remove("repo", source="repo_load")
        record = store.add(repository="repo", memory_type="semantic", title="What it is", content="v2", metadata={"source": "repo_load"})

        assert record.content == "v2"
        assert record.corroboration_count == 1
        assert record.invalid_at is None
