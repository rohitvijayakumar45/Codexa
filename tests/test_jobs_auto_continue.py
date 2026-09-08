"""Tests for automatic round-budget continuation in backend/agents/jobs.py's _run.

Direct follow-up to continue_job() (tests/test_jobs_continue.py): that required a human to click
"Continue" every single time a job ran out of rounds. For an unattended/overnight run that's a real
gap — the job just sits there erroring out, waiting for nobody. _run now auto-continues a bounded
number of times (_MAX_AUTO_CONTINUES) on its own before finally surfacing to the user, exactly the
"don't just make it work, make it polished" fix requested.
"""

from unittest.mock import MagicMock, patch

from backend.agents.jobs import Job, JobManager, _MAX_AUTO_CONTINUES, _MAX_ROUNDS


def _fake_chunk(content: str):
    from types import SimpleNamespace
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=content, reasoning_content=None))])


class NeverFinishesLLM:
    """Every round emits one chunk (real progress, not a stall) but stream_chunk_builder is mocked
    to always assemble a message with no tool_calls and empty content — nothing ever satisfies
    validate_completion's "done" path, so this job runs out of rounds every single time, forever."""

    def stream(self, model, messages, timeout=240, **kwargs):
        yield _fake_chunk("still working...")

    def record_usage(self, *args, **kwargs):
        return {"prompt_tokens": 1, "completion_tokens": 1}

    def context_window(self, model):
        return 8000

    def tier_of(self, model):
        return None

    def models_for_tier(self, tier):
        return []


def _job() -> Job:
    return Job(
        id="auto-continue-job",
        repository="demo-repo",
        model="fake-model",
        messages=[{"role": "user", "content": "Build a large full-stack app"}],
        message_rounds=[-100],
        contract={
            "intent": "CREATE_ARTIFACT", "required_tools": ["write_file"], "allowed_tools": [],
            "success_criteria": [], "constraints": [], "suggested_workflow": [],
        },
        active_tool_groups=[],
        # Explicit empty execution plan (backend/agents/plan.py) — see the same note in
        # tests/test_jobs_stall_recovery.py. These tests are about the auto-continue budget itself;
        # a real plan would keep the job running for its own reasons and stop the round-exhaustion
        # path under test from being what actually ends the job.
        plan={"objective": "", "tasks": []},
    )


def _tool_call_final(call_id: str = "call_1"):
    # A message that keeps calling a (nonexistent) tool forever - real round-by-round activity
    # that never reaches the "final answer, no tool_calls" done-check at all, exhausting purely by
    # running out of rounds while still "in the middle of work" - the actual real-world shape
    # observed in production (a model that keeps calling tools every round and never wraps up).
    # "keep_working" falls through execute_tool's dispatch to its harmless "Unknown tool: x" reply
    # (backend/agents/tools.py) rather than touching the filesystem.
    m = MagicMock()
    m.choices = [MagicMock()]
    msg = m.choices[0].message
    msg.content = ""
    tc = MagicMock()
    tc.id = call_id
    tc.function.name = "keep_working"
    tc.function.arguments = "{}"
    msg.tool_calls = [tc]
    return m


class TestBoundedAutoContinue:
    def test_auto_continues_up_to_the_cap_then_finally_errors(self):
        manager = JobManager(llm=NeverFinishesLLM(), graph=None, store=None)
        job = _job()

        with patch("backend.agents.jobs.litellm.stream_chunk_builder", return_value=_tool_call_final()):
            manager._run(job, resuming=False)

        assert job.status == "error"
        assert job.error_reason == "max_rounds"
        assert job.auto_continues == _MAX_AUTO_CONTINUES
        # round_budget grew by _MAX_ROUNDS for the original attempt + each auto-continue
        assert job.round_budget == _MAX_ROUNDS * (_MAX_AUTO_CONTINUES + 1)

    def test_auto_continue_event_is_emitted_each_time(self):
        manager = JobManager(llm=NeverFinishesLLM(), graph=None, store=None)
        job = _job()

        with patch("backend.agents.jobs.litellm.stream_chunk_builder", return_value=_tool_call_final()):
            manager._run(job, resuming=False)

        auto_continue_events = [
            e["tool_call"] for e in job.events
            if e.get("tool_call", {}).get("name") == "_auto_continue"
        ]
        assert len(auto_continue_events) == _MAX_AUTO_CONTINUES
        assert auto_continue_events[0]["args"]["auto_continues_used"] == 1
        assert auto_continue_events[-1]["args"]["auto_continues_used"] == _MAX_AUTO_CONTINUES

    def test_succeeds_without_ever_erroring_if_it_finishes_within_an_auto_continue(self):
        # First pass exhausts (empty final every round); once auto-continued, the NEXT round
        # finally produces real content and no tool_calls - a genuine completion.
        call_count = {"n": 0}

        def stream_chunk_builder_side_effect(chunks, messages):
            call_count["n"] += 1
            if call_count["n"] <= _MAX_ROUNDS:
                return _tool_call_final(call_id=f"call_{call_count['n']}")
            m = MagicMock()
            m.choices = [MagicMock()]
            m.choices[0].message.content = "All done."
            m.choices[0].message.tool_calls = None
            return m

        manager = JobManager(llm=NeverFinishesLLM(), graph=None, store=None)
        job = _job()
        job.contract["required_tools"] = []  # so the real completion round actually finalizes

        with patch(
            "backend.agents.jobs.litellm.stream_chunk_builder",
            side_effect=stream_chunk_builder_side_effect,
        ):
            manager._run(job, resuming=False)

        assert job.status == "done"
        assert job.auto_continues == 1
        assert job.round_budget == _MAX_ROUNDS * 2

    def test_a_genuine_unrecoverable_error_is_never_auto_continued(self):
        # A failure that escapes _loop entirely (outside the per-round stall-recovery try/except,
        # e.g. a bug in post-round processing) hits _run's own generic exception handler, which
        # leaves error_reason untouched (not "max_rounds" or "stall_exhausted") - genuinely
        # unrecoverable, unlike a repeated stream failure (see TestStallExhaustionIsAutoRecoverable
        # in test_jobs_stall_recovery.py - THAT case now correctly auto-continues, since a
        # persistently-failing connection is exactly the case _MAX_AUTO_CONTINUES exists to retry).
        manager = JobManager(llm=NeverFinishesLLM(), graph=None, store=None)
        job = _job()
        job.contract["required_tools"] = []  # so the round reaches validate_completion at all

        final = MagicMock()
        final.choices = [MagicMock()]
        final.choices[0].message.content = "done"
        final.choices[0].message.tool_calls = None
        with patch("backend.agents.jobs.litellm.stream_chunk_builder", return_value=final), \
             patch("backend.agents.jobs.validate_completion", side_effect=RuntimeError("bug")):
            manager._run(job, resuming=False)

        assert job.status == "error"
        assert job.error_reason is None
        assert job.auto_continues == 0  # never touched - this isn't a recoverable reason at all


class TestManualContinueResetsAutoBudget:
    def test_continue_job_resets_auto_continues_for_a_fresh_bounded_run(self):
        manager = JobManager(llm=NeverFinishesLLM(), graph=None, store=None)
        job = _job()
        job.status = "error"
        job.error_reason = "max_rounds"
        job.auto_continues = _MAX_AUTO_CONTINUES  # already exhausted once
        manager._jobs[job.id] = job

        with patch("backend.agents.jobs.threading.Thread") as mock_thread_cls:
            mock_thread_cls.return_value = MagicMock()  # don't actually run _run here
            result = manager.continue_job(job.id)

        assert result is not None
        assert result.auto_continues == 0
