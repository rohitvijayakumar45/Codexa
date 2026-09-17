import json
import tempfile
from pathlib import Path
from backend.memory.store import MemoryStore, MEMORY_TYPES
from backend.memory.context import _relevance_score, _TYPE_MATCH_BONUS
from backend.memory.conflict import resolve_conflict


def test_claim_memorystore_four_types_and_disk_persistence():
    """Claim: MemoryStore supports exactly 4 memory types and durably persists across restarts."""
    assert set(MEMORY_TYPES) == {"semantic", "episodic", "procedural", "organizational"}
    
    with tempfile.TemporaryDirectory() as tmpdir:
        mem_file = Path(tmpdir) / "memories.json"
        store1 = MemoryStore(path=mem_file)

        store1.add(repository="test-repo", memory_type="semantic", title="Architecture", content="FastAPI backend")
        store1.add(repository="test-repo", memory_type="procedural", title="RunCommand", content="pytest -q")
        store1.add(repository="test-repo", memory_type="episodic", title="Incident 1", content="DB connection dropped")
        store1.add(repository="test-repo", memory_type="organizational", title="Conventions", content="Prefer composition")

        # Reload store from disk
        store2 = MemoryStore(path=mem_file)
        repo_mems = store2.list(repository="test-repo")
        assert len(repo_mems) == 4
        types_found = {m.memory_type for m in repo_mems}
        assert types_found == {"semantic", "episodic", "procedural", "organizational"}


def test_claim_memory_conflict_resolution():
    """Claim: Conflicting facts with same (repo, type, title) are resolved deterministically
    via trust, corroboration, and soft-delete (invalid_at), never silently overwritten."""
    with tempfile.TemporaryDirectory() as tmpdir:
        mem_file = Path(tmpdir) / "memories.json"
        store = MemoryStore(path=mem_file)

        # High-trust initial fact
        rec1 = store.add(
            repository="myrepo",
            memory_type="semantic",
            title="Database",
            content="PostgreSQL",
            trust=1.0,
        )

        # Lower-trust incoming claim trying to contradict
        rec2 = store.add(
            repository="myrepo",
            memory_type="semantic",
            title="Database",
            content="MongoDB",
            trust=0.4,
        )

        active = store.list(repository="myrepo")
        # Active record should still be PostgreSQL
        assert len(active) == 1
        assert active[0].content == "PostgreSQL"
        
        # Soft-deleted record is preserved in history (filtering by repository to ignore self-seed)
        all_raw = json.loads(mem_file.read_text(encoding="utf-8"))
        myrepo_raw = [r for r in all_raw if r["repository"] == "myrepo"]
        assert len(myrepo_raw) == 2
        mongo_rec = next(r for r in myrepo_raw if r["content"] == "MongoDB")
        assert mongo_rec["invalid_at"] is not None


def test_claim_type_aware_retrieval_weighting():
    """Claim: Query phrasing biases ranking toward matching memory types (e.g. procedural for run/build)."""
    score_procedural = _relevance_score(
        query="how do I build this project?",
        title="Build",
        content="compile steps",
        memory_type="procedural"
    )
    score_org = _relevance_score(
        query="how do I build this project?",
        title="Build",
        content="compile steps",
        memory_type="organizational"
    )
    # The procedural score gets the _TYPE_MATCH_BONUS for "how do I" / "build"
    assert score_procedural > score_org
    assert round(score_procedural - score_org, 2) == round(_TYPE_MATCH_BONUS, 2)
