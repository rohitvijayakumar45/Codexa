"""Tests for round-exhaustion continuation in backend/agents/jobs.py.

Regression coverage for a real, reported bug: a job that ran out of tool-calling rounds
(_MAX_ROUNDS) errored out permanently, and the frontend's only recovery was starting a brand-new
job from a condensed text summary — throwing away every tool call and all the reasoning already
done, so the model had to start thinking again from scratch. continue_job() re-runs the SAME job
(same message/tools_called/receipts history) with a bigger round budget instead.
"""

from types import SimpleNamespace

from backend.agents.jobs import Job, JobManager, _MAX_ROUNDS


def _fake_chunk(content: str):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=content, reasoning_content=None))])


class NeverFinishesLLM:
    """Every round: emits a chunk (so it counts as real progress, not a stall) but the raw stream
    builder assembles a message with no tool_calls and non-empty content — wait, to genuinely
    exhaust rounds without EVER completing, every round must keep producing tool_calls so the loop
    never reaches its "done" exit. Simplest: always emit a write_file tool call, forever."""

    def stream(self, model, messages, timeout=240, **kwargs):
        yield _fake_chunk("thinking some more...")

    def record_usage(self, *args, **kwargs):
        return {"prompt_tokens": 10, "completion_tokens": 5}

    def context_window(self, model):
        return 8000

    def tier_of(self, model):
        return None

    def models_for_tier(self, tier):
        return []


def _job(round_budget: int = _MAX_ROUNDS) -> Job:
    return Job(
        id="round-exhaustion-job",
        repository="demo-repo",
        model="fake-model",
        messages=[{"role": "user", "content": "Build a large full-stack app"}],
        message_rounds=[-100],
        contract={
            "intent": "CREATE_ARTIFACT", "required_tools": ["write_file"], "allowed_tools": [],
            "success_criteria": [], "constraints": [], "suggested_workflow": [],
        },
        active_tool_groups=[],
        round_budget=round_budget,
    )


class TestRoundExhaustionIsTaggedContinuable:
    def test_status_and_error_reason_set_on_exhaustion(self, monkeypatch):
        import backend.agents.jobs as jobs_mod
        monkeypatch.setattr(jobs_mod, "litellm", jobs_mod.litellm)  # no-op, just documents the dep

        manager = JobManager(llm=NeverFinishesLLM(), graph=None, store=None)
        job = _job(round_budget=2)  # small budget - exhausts fast

        # stream_round never emits tool_calls or a final message with content, so the round loop
        # just keeps looping - patch stream_chunk_builder so each round "completes" with an empty
        # non-tool message, forcing the loop to actually reach the exhaustion tail.
        import unittest.mock as mock
        empty_final = mock.MagicMock()
        empty_final.choices = [mock.MagicMock()]
        empty_final.choices[0].message.content = ""
        empty_final.choices[0].message.tool_calls = None
        with mock.patch("backend.agents.jobs.litellm.stream_chunk_builder", return_value=empty_final):
            manager._loop(job, resuming=False)

        assert job.status == "error"
        assert job.error_reason == "max_rounds"
        # No user-facing error yet: _run auto-continues this exact reason, in the same thread,
        # usually within microseconds. Emitting one here put a red "Ran out of tool-calling rounds"
        # card with Continue/Retry buttons in front of a job that was healthy, mid-task and about to
        # carry on by itself — observed on a real run at round 9 of 20 with two files already
        # written. The state transition is what _run reads and must still happen; the interruption
        # is what waits until a human genuinely has to decide something.
        assert not [e for e in job.events if "error" in e]
        assert any("Extending the round budget" in e.get("status", "") for e in job.events)

    def test_the_user_is_told_once_the_automatic_retries_are_genuinely_spent(self, monkeypatch):
        import unittest.mock as mock

        from backend.agents.jobs import _MAX_AUTO_CONTINUES

        manager = JobManager(llm=NeverFinishesLLM(), graph=None, store=None)
        job = _job(round_budget=2)
        job.auto_continues = _MAX_AUTO_CONTINUES  # nothing automatic left to try

        empty_final = mock.MagicMock()
        empty_final.choices = [mock.MagicMock()]
        empty_final.choices[0].message.content = ""
        empty_final.choices[0].message.tool_calls = None
        with mock.patch("backend.agents.jobs.litellm.stream_chunk_builder", return_value=empty_final):
            manager._loop(job, resuming=False)

        error_events = [e for e in job.events if "error" in e]
        assert error_events, "the user must be told once nothing automatic is left"
        assert error_events[-1].get("continuable") is True


class TestContinueJob:
    def test_continue_grants_more_rounds_and_resumes_same_history(self, monkeypatch):
        import unittest.mock as mock

        manager = JobManager(llm=NeverFinishesLLM(), graph=None, store=None)
        job = _job(round_budget=1)  # exhausts almost immediately
        manager._jobs[job.id] = job

        empty_final = mock.MagicMock()
        empty_final.choices = [mock.MagicMock()]
        empty_final.choices[0].message.content = ""
        empty_final.choices[0].message.tool_calls = None
        with mock.patch("backend.agents.jobs.litellm.stream_chunk_builder", return_value=empty_final):
            manager._loop(job, resuming=False)
        assert job.status == "error"
        assert job.error_reason == "max_rounds"
        original_round_budget = job.round_budget
        original_messages_len = len(job.messages)

        # continue_job spawns a background thread - run its target synchronously here instead of
        # sleeping/polling for it, so the test is deterministic. _MAX_AUTO_CONTINUES pinned to 0 so
        # _run's OWN auto-continue mechanism doesn't also kick in once the resumed job immediately
        # exhausts again (NeverFinishesLLM never produces a real completion) - this test is about
        # continue_job's single bump, not its interaction with _run's separate auto-continue loop.
        with mock.patch("backend.agents.jobs.threading.Thread") as mock_thread_cls, \
             mock.patch("backend.agents.jobs._MAX_AUTO_CONTINUES", 0):
            captured = {}

            def fake_thread(target, args, daemon, kwargs):
                captured["target"] = target
                captured["args"] = args
                captured["kwargs"] = kwargs
                return mock.MagicMock(start=lambda: target(*args, **kwargs))

            mock_thread_cls.side_effect = fake_thread
            with mock.patch("backend.agents.jobs.litellm.stream_chunk_builder", return_value=empty_final):
                result = manager.continue_job(job.id)

        assert result is not None
        assert result.round_budget == original_round_budget + _MAX_ROUNDS
        # Same job, same accumulated history - not a fresh restart.
        assert len(job.messages) >= original_messages_len
        assert job.id == "round-exhaustion-job"

    def test_returns_none_for_a_job_with_a_different_error_reason(self):
        manager = JobManager(llm=NeverFinishesLLM(), graph=None, store=None)
        job = _job()
        job.status = "error"
        job.error_reason = None  # e.g. a genuine crash, not round exhaustion
        manager._jobs[job.id] = job

        assert manager.continue_job(job.id) is None

    def test_returns_none_for_a_done_job(self):
        manager = JobManager(llm=NeverFinishesLLM(), graph=None, store=None)
        job = _job()
        job.status = "done"
        manager._jobs[job.id] = job

        assert manager.continue_job(job.id) is None

    def test_returns_none_for_a_nonexistent_job(self):
        manager = JobManager(llm=NeverFinishesLLM(), graph=None, store=None)
        assert manager.continue_job("does-not-exist") is None

    def test_resets_a_stale_cancelled_flag(self):
        # Regression: continue_job used to leave job.cancelled untouched - a job cancelled at some
        # earlier point that also happened to hit max_rounds would silently re-die the instant it
        # was continued (the round loop's first check kills a cancelled job with status "done", no
        # error at all - indistinguishable from just stopping dead).
        manager = JobManager(llm=NeverFinishesLLM(), graph=None, store=None)
        job = _job()
        job.status = "error"
        job.error_reason = "max_rounds"
        job.cancelled = True
        manager._jobs[job.id] = job

        import unittest.mock as mock
        with mock.patch("backend.agents.jobs.threading.Thread") as mock_thread_cls:
            mock_thread_cls.return_value = mock.MagicMock()  # don't actually run _loop here
            result = manager.continue_job(job.id)

        assert result is not None
        assert result.cancelled is False

    def test_returns_none_for_a_still_running_job(self):
        manager = JobManager(llm=NeverFinishesLLM(), graph=None, store=None)
        job = _job()
        job.status = "running"
        manager._jobs[job.id] = job

        assert manager.continue_job(job.id) is None


class TestCheckpointsSurviveATransientlyLockedFile:
    """Observed repeatedly on a real overnight run:

        job checkpoint failed for 05d1f8b6: [WinError 5] Access is denied:
        '...jobs\05d1f8b6.tmp' -> '...jobs\05d1f8b6.json'

    The project lives under OneDrive, and the sync client briefly opens files it sees changing.
    `os.replace` onto a handle another process holds fails immediately on Windows. The old code took
    one attempt and gave up with a warning — but the checkpoint IS the job's resumable state and its
    execution position, so dropping one means a restart resumes at a stale round and anything reading
    the file is told something untrue.
    """

    def _job_for_checkpoint(self):
        from backend.agents.jobs import Job

        return Job(
            id="checkpoint-retry-job", repository="demo", model="fake-model",
            messages=[], message_rounds=[], contract={"intent": "CONVERSATION"},
        )

    def test_a_transient_lock_is_retried_rather_than_dropped(self, monkeypatch):
        import backend.agents.jobs as jobs_mod

        calls = {"n": 0}
        real_replace = jobs_mod.os.replace

        def flaky_replace(src, dst):
            calls["n"] += 1
            if calls["n"] < 3:
                raise PermissionError(5, "Access is denied")
            return real_replace(src, dst)

        monkeypatch.setattr(jobs_mod.os, "replace", flaky_replace)
        manager = JobManager(llm=NeverFinishesLLM(), graph=None, store=None)
        job = self._job_for_checkpoint()
        manager._checkpoint(job)

        assert calls["n"] == 3, "must keep trying past a transient lock"
        assert (jobs_mod.JOBS_DIR / f"{job.id}.json").exists()

    def test_a_genuinely_unwritable_location_never_raises(self, monkeypatch):
        # A job that dies because it could not journal itself is worse than one running with a stale
        # checkpoint. It gives up, loudly, and carries on.
        import backend.agents.jobs as jobs_mod

        def always_denied(src, dst):
            raise PermissionError(5, "Access is denied")

        monkeypatch.setattr(jobs_mod.os, "replace", always_denied)
        manager = JobManager(llm=NeverFinishesLLM(), graph=None, store=None)
        manager._checkpoint(self._job_for_checkpoint())  # must not raise
