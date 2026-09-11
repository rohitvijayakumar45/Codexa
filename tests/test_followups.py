"""Follow-ups from the claim-by-claim review of the product brief:

- the job event log now persists to disk, so a subscriber after a server restart replays the whole
  run instead of one synthesized ending;
- key rotation never walks gemini-2.5-flash onto keys where Google has retired it (404);
- retired / unreliable models are out of automatic rotation.
"""

from types import SimpleNamespace

from backend.agents import jobs
from backend.agents.llm import _TIER_ORDER, MODEL_REGISTRY, LLMClient


class TestEventLogPersists:
    def test_the_final_event_flushes_the_whole_log_to_disk(self, tmp_path, monkeypatch):
        monkeypatch.setattr(jobs, "JOBS_DIR", tmp_path)
        job = SimpleNamespace(id="job-1", events=[], events_persisted=0)
        emit = jobs.JobManager._emit
        emit(None, job, {"status": "Reading App.tsx"})
        emit(None, job, {"tool_call": {"name": "read_file", "args": {"path": "src/App.tsx"}}})
        assert jobs._read_events("job-1") == []  # batched, not one file write per chunk
        emit(None, job, {"done": True})
        assert jobs._read_events("job-1") == job.events
        assert len(job.events) == 3

    def test_flushes_append_only_what_is_new(self, tmp_path, monkeypatch):
        monkeypatch.setattr(jobs, "JOBS_DIR", tmp_path)
        job = SimpleNamespace(id="job-3", events=[{"status": "a"}], events_persisted=0)
        jobs._flush_events(job)
        job.events.append({"status": "b"})
        jobs._flush_events(job)
        jobs._flush_events(job)  # nothing new
        assert jobs._read_events("job-3") == [{"status": "a"}, {"status": "b"}]

    def test_a_line_cut_off_by_a_crash_is_skipped(self, tmp_path, monkeypatch):
        monkeypatch.setattr(jobs, "JOBS_DIR", tmp_path)
        (tmp_path / "job-2.events.jsonl").write_text('{"status": "ok"}\n{"delta": "half a li', encoding="utf-8")
        assert jobs._read_events("job-2") == [{"status": "ok"}]

    def test_no_log_means_no_events(self, tmp_path, monkeypatch):
        monkeypatch.setattr(jobs, "JOBS_DIR", tmp_path)
        assert jobs._read_events("never-ran") == []


class TestRetiredModelKeys:
    def _client(self, keys):
        return SimpleNamespace(
            _provider_keys={"gemini": keys}, _active_key_index={},
            _provider_of=lambda m: "gemini", describe_active=lambda m: m, _on_key_switch=None,
        )

    def test_gemini_2_5_never_rotates_past_the_first_key(self):
        fake = self._client(["k1", "k2", "k3", "k4"])
        assert LLMClient._advance_key(fake, "gemini/gemini-2.5-flash") is False
        assert fake._active_key_index.get("gemini/gemini-2.5-flash", 0) == 0

    def test_other_models_still_rotate_through_every_key(self):
        fake = self._client(["k1", "k2", "k3", "k4"])
        steps = [LLMClient._advance_key(fake, "gemini/gemini-3.6-flash") for _ in range(4)]
        assert steps == [True, True, True, False]


def test_dead_and_flaky_models_are_out_of_automatic_rotation():
    assert "openrouter/minimax/minimax-m3:free" not in MODEL_REGISTRY  # no longer free
    rotation = {m for tier in _TIER_ORDER.values() for m in tier}
    assert "nvidia_nim/deepseek-ai/deepseek-v4-pro-0813" not in rotation  # timed out after 182s
    assert "nvidia_nim/mistralai/mistral-nemotron" not in rotation  # returned 500
    # Still selectable by hand.
    assert "nvidia_nim/deepseek-ai/deepseek-v4-pro-0813" in MODEL_REGISTRY
