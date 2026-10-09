"""Experiential memory written at the end of an agent job (backend/memory/experience.py and the
JobManager._record_experience hook). Everything recorded must come from the job's real tool calls
and real exit codes — never from the model's own narration of what it did."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from backend.agents.jobs import Job, JobManager
from backend.memory.anchors import check_anchors, is_outdated, sweep_repository
from backend.memory.experience import SOURCE, extract_experience, record_job_experience
from backend.memory.store import MemoryStore


def _call(call_id: str, name: str, **args) -> dict:
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


def _assistant(*calls: dict, content: str = "") -> dict:
    return {"role": "assistant", "content": content, "tool_calls": list(calls)}


def _messages() -> list[dict]:
    return [
        {"role": "user", "content": "Add a /health endpoint and make sure the tests pass"},
        _assistant(_call("c1", "read_file", path="src/app.py"), _call("c2", "read_files", paths=["README.md", "./src/app.py"])),
        _assistant(_call("c3", "edit_file", path="src/app.py", old_text="a", new_text="b")),
        _assistant(_call("c4", "create_files", files=[{"path": "tests/test_health.py", "content": "x"}])),
        _assistant(_call("c5", "apply_patch", patch="--- a/src/util.py\n+++ b/src/util.py\n@@\n-x\n+y\n")),
        _assistant(_call("c6", "run_command", command="python -m pytest -q"), _call("c7", "run_command", command="ls -la")),
        _assistant(_call("c8", "run_command", command="npm run lint")),
        {"role": "assistant", "content": "All tests pass and the endpoint works."},  # narration: ignored
    ]


_EXIT = {"c6": 0, "c7": 0, "c8": 1}


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    for rel, text in {"src/app.py": "app = 1\n", "src/util.py": "y\n", "tests/test_health.py": "x\n",
                      "README.md": "# r\n", "pyproject.toml": "[project]\nname='r'\n"}.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    return root


def _record(store: MemoryStore, root: Path, job_id: str = "job-aaaaaaaa-1", messages=None, codes=None,
            status: str = "done") -> list[str]:
    return record_job_experience(
        store, repository="r", root=root, job_id=job_id, status=status,
        task_text="Add a /health endpoint and make sure the tests pass",
        messages=messages if messages is not None else _messages(), tool_exit_codes=codes if codes is not None else _EXIT,
    )


class TestExtract:
    def test_extracts_real_tool_activity(self):
        exp = extract_experience(_messages(), _EXIT)
        assert exp.modified == ["src/app.py", "tests/test_health.py", "src/util.py"]
        assert exp.read == ["README.md"]  # src/app.py was read then modified: listed once, as modified
        assert exp.verified_commands == ["python -m pytest -q", "ls -la"]
        assert exp.failed_commands == ["npm run lint"]

    def test_unknown_exit_code_is_neither_verified_nor_failed(self):
        exp = extract_experience([_assistant(_call("x", "run_command", command="npm test"))], {})
        assert exp.verified_commands == [] and exp.failed_commands == []

    def test_compacted_arguments_still_yield_the_path(self):
        compacted = {"id": "c", "type": "function",
                     "function": {"name": "write_file", "arguments": '{"path": "src/big.py", "content": "[compacted'}}
        assert extract_experience([_assistant(compacted)], {}).modified == ["src/big.py"]

    def test_move_and_delete(self):
        msgs = [_assistant(_call("a", "move_file", from_path="old.py", to_path="new.py"),
                           _call("b", "delete_file", path="gone.py"))]
        exp = extract_experience(msgs, {})
        assert exp.modified == ["new.py"] and exp.deleted == ["old.py", "gone.py"]

    def test_dotfiles_keep_their_leading_dot(self):
        exp = extract_experience([_assistant(_call("a", "write_file", path="./.env.example", content="x"))], {})
        assert exp.modified == [".env.example"]


class TestRecord:
    def test_writes_anchored_episode_and_procedural_for_verified_project_commands(self, tmp_path):
        root = _repo(tmp_path)
        store = MemoryStore(path=tmp_path / "m.json")
        ids = _record(store, root)
        episode = store.get(ids[0])
        assert episode.memory_type == "episodic" and episode.title.startswith("Task job-aaaa: Add a /health")
        assert episode.metadata["source"] == SOURCE and episode.metadata["job_id"] == "job-aaaaaaaa-1"
        assert "Modified: src/app.py" in episode.content and "`npm run lint`" in episode.content
        assert {a["path"] for a in episode.anchors} >= {"src/app.py", "src/util.py", "README.md"}
        assert check_anchors(root, episode.anchors).status == "valid"

        procedural = [r for r in store.list("r", "procedural") if r.metadata.get("source") == SOURCE]
        assert [r.title for r in procedural] == ["Verified command: python -m pytest -q"]  # not `ls`, not the failure
        assert any(a["path"] == "pyproject.toml" for a in procedural[0].anchors)

    def test_same_command_verified_again_corroborates(self, tmp_path):
        root = _repo(tmp_path)
        store = MemoryStore(path=tmp_path / "m.json")
        _record(store, root, job_id="job-1")
        _record(store, root, job_id="job-2")
        procedural = [r for r in store.list("r", "procedural") if r.metadata.get("source") == SOURCE]
        assert len(procedural) == 1 and procedural[0].corroboration_count == 2
        assert len([r for r in store.list("r", "episodic") if r.metadata.get("source") == SOURCE]) == 2

    def test_re_recording_a_job_replaces_its_episode(self, tmp_path):
        root = _repo(tmp_path)
        store = MemoryStore(path=tmp_path / "m.json")
        first = _record(store, root, status="error")[0]
        second = _record(store, root, status="done")[0]
        episodes = [r for r in store.list("r", "episodic") if r.metadata.get("source") == SOURCE]
        assert [e.id for e in episodes] == [second]
        assert store.get(first).invalid_at is not None

    def test_pure_conversation_writes_nothing(self, tmp_path):
        store = MemoryStore(path=tmp_path / "m.json")
        before = len(store.list("r"))
        assert _record(store, _repo(tmp_path), messages=[{"role": "user", "content": "hi"}]) == []
        assert len(store.list("r")) == before

    def test_later_code_change_outdates_episode_and_manifest_change_invalidates_command(self, tmp_path):
        root = _repo(tmp_path)
        store = MemoryStore(path=tmp_path / "m.json")
        episode_id = _record(store, root)[0]
        (root / "src/app.py").write_text("app = 2\n", encoding="utf-8")
        (root / "pyproject.toml").write_text("[project]\nname='renamed'\n", encoding="utf-8")
        sweep_repository(store, "r", root)
        assert is_outdated(store.get(episode_id)) and store.get(episode_id).invalid_at is None
        assert not [r for r in store.list("r", "procedural") if r.metadata.get("source") == SOURCE]


class TestJobHook:
    def _job(self, **overrides) -> Job:
        job = Job(id="job-hook-0001", repository="r", model="m", messages=_messages(), tool_exit_codes=dict(_EXIT),
                  status="done", contract_source="Add a /health endpoint")
        job.working_repo = "r"
        for k, v in overrides.items():
            setattr(job, k, v)
        return job

    def _manager(self, store) -> SimpleNamespace:
        return SimpleNamespace(_store=store)

    def test_hook_records_experience(self, tmp_path, monkeypatch):
        root = _repo(tmp_path)
        monkeypatch.setattr("backend.files.api.repo_root", lambda repo: root)
        store = MemoryStore(path=tmp_path / "m.json")
        JobManager._record_experience(self._manager(store), self._job())
        assert [r for r in store.list("r", "episodic") if r.metadata.get("job_id") == "job-hook-0001"]

    def test_hook_disabled_by_env(self, tmp_path, monkeypatch):
        monkeypatch.setattr("backend.files.api.repo_root", lambda repo: _repo(tmp_path))
        monkeypatch.setenv("CODEXA_EXPERIENCE_MEMORY", "0")
        store = MemoryStore(path=tmp_path / "m.json")
        JobManager._record_experience(self._manager(store), self._job())
        assert not [r for r in store.list("r") if r.metadata.get("source") == SOURCE]

    def test_hook_skips_cancelled_jobs_and_missing_store(self, tmp_path, monkeypatch):
        monkeypatch.setattr("backend.files.api.repo_root", lambda repo: _repo(tmp_path))
        store = MemoryStore(path=tmp_path / "m.json")
        JobManager._record_experience(self._manager(store), self._job(cancelled=True))
        JobManager._record_experience(self._manager(None), self._job())
        assert not [r for r in store.list("r") if r.metadata.get("source") == SOURCE]

    def test_hook_never_raises(self, tmp_path, monkeypatch):
        def boom(repo):
            raise RuntimeError("disk on fire")

        monkeypatch.setattr("backend.files.api.repo_root", boom)
        JobManager._record_experience(self._manager(MemoryStore(path=tmp_path / "m.json")), self._job())
