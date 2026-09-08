"""Tests for the stall-recovery exhaustion path in backend/agents/jobs.py's _loop.

Regression coverage for a live bug: a job whose provider stalled mid-stream on every attempt died
with a bare "TimeoutError: ..." once stall recovery ran out, giving no signal about whether the
task's required tool (e.g. write_file for a CREATE task) was ever actually called — the model's
prior narration was left looking like a completed answer even though nothing was written. The fix
checks task-contract completion before giving up and says so explicitly.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import litellm

from backend.agents.jobs import Job, JobManager


def _fake_chunk(content: str):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=content, reasoning_content=None))])


class StallingLLM:
    """Every call to stream() yields one chunk (so the round counts as having emitted something)
    then raises — simulating a provider that stalls mid-response every single attempt."""

    def stream(self, model, messages, timeout=240, **kwargs):
        yield _fake_chunk("partial narration")
        raise TimeoutError("provider timeout")

    def record_usage(self, *args, **kwargs):
        return {"prompt_tokens": 0, "completion_tokens": 0}

    def context_window(self, model):
        return 8000

    def tier_of(self, model):
        return None

    def models_for_tier(self, tier):
        return []


class SilentlyHangingLLM:
    """Every call to stream() raises immediately — ZERO chunks ever emitted. This is the real shape
    of _stream_with_watchdog's TimeoutError (a connection that was accepted but never sent a single
    byte back), which used to fall through to a completely unguarded retry-without-tools call with
    no exception handling and no bounded retry count — any further failure there killed the job
    outright, bypassing stall-recovery entirely."""

    def stream(self, model, messages, timeout=240, **kwargs):
        raise TimeoutError("No response from the model for 90s")
        yield  # pragma: no cover - makes this a generator function

    def record_usage(self, *args, **kwargs):
        return {"prompt_tokens": 0, "completion_tokens": 0}

    def context_window(self, model):
        return 8000

    def tier_of(self, model):
        return None

    def models_for_tier(self, tier):
        return []


def _job(*, required_tools: list[str], tools_called: list[str] | None = None) -> Job:
    return Job(
        id="test-job",
        repository="demo-repo",
        model="fake-model",
        messages=[{"role": "user", "content": "Create a new project called pulse-dashboard"}],
        message_rounds=[-100],
        contract={
            "intent": "CREATE_ARTIFACT", "required_tools": required_tools, "allowed_tools": [],
            "success_criteria": [], "constraints": [], "suggested_workflow": [],
        },
        active_tool_groups=[],
        tools_called=tools_called or [],
        # Pinned to an explicit empty plan (backend/agents/plan.py): "this job needs no execution
        # plan", which is the shape a conversational turn genuinely has. These tests are about
        # stall recovery and model failover in isolation — with a real plan the loop correctly keeps
        # a job alive across many more rounds until its tasks verify on disk, which would drown the
        # single mechanism under test in unrelated task machinery. Plan-driven execution has its own
        # coverage in tests/test_execution_plan.py and tests/test_controller.py.
        plan={"objective": "", "tasks": []},
    )


class TestStallExhaustionReportsTaskCompletion:
    def test_job_errors_out_after_max_stall_recoveries(self):
        manager = JobManager(llm=StallingLLM(), graph=None, store=None)
        job = _job(required_tools=["write_file"])

        manager._loop(job, resuming=False)

        assert job.status == "error"

    def test_incomplete_required_tool_is_named_explicitly_not_a_raw_exception(self):
        manager = JobManager(llm=StallingLLM(), graph=None, store=None)
        job = _job(required_tools=["write_file"])  # write_file never actually called

        manager._loop(job, resuming=False)

        error_events = [e["error"] for e in job.events if "error" in e]
        assert error_events, "expected a terminal error event"
        assert "write_file" in error_events[-1]
        assert "TimeoutError" not in error_events[-1]
        assert "nothing" in error_events[-1].lower() or "created" in error_events[-1].lower()

    def test_already_satisfied_contract_gets_a_neutral_message_not_a_false_incompleteness_claim(self):
        manager = JobManager(llm=StallingLLM(), graph=None, store=None)
        # write_file already succeeded earlier this job; the stall happened on a LATER round.
        job = _job(required_tools=["write_file"], tools_called=["write_file"])

        manager._loop(job, resuming=False)

        error_events = [e["error"] for e in job.events if "error" in e]
        assert error_events
        assert "write_file" not in error_events[-1]  # nothing to blame it for - it was called

    def test_no_required_tools_never_blames_a_missing_tool(self):
        manager = JobManager(llm=StallingLLM(), graph=None, store=None)
        job = _job(required_tools=[])  # e.g. an ANALYZE/EXPLAIN/CONVERSATION task

        manager._loop(job, resuming=False)

        error_events = [e["error"] for e in job.events if "error" in e]
        assert error_events
        assert "required tool" not in error_events[-1].lower()

    def test_job_never_reaches_running_state_forever(self):
        # The concrete complaint behind this bug: the job must reach a terminal status, not sit at
        # "running" indefinitely once recovery is exhausted.
        manager = JobManager(llm=StallingLLM(), graph=None, store=None)
        job = _job(required_tools=["write_file"])

        manager._loop(job, resuming=False)

        assert job.status != "running"


class StallsOnEveryModelLLM:
    """Every model stalls mid-stream, every attempt - unlike RateLimitedThenRecoversLLM, no
    model here ever succeeds. Used to prove stall-exhaustion switches to a DIFFERENT model rather
    than leaving job.model unchanged for the next auto-continue/manual Continue to hammer again."""

    def __init__(self):
        self.models_tried: list[str] = []

    def stream(self, model, messages, timeout=240, **kwargs):
        self.models_tried.append(model)
        yield _fake_chunk("partial narration")
        raise TimeoutError("provider timeout")

    def record_usage(self, *args, **kwargs):
        return {"prompt_tokens": 0, "completion_tokens": 0}

    def context_window(self, model):
        return 8000

    def tier_of(self, model):
        return "heavy"

    def models_for_tier(self, tier):
        return ["model-a", "model-b", "model-c"]

    def failover_ring(self, tier):
        return ["model-a", "model-b", "model-c"]


class TestStallExhaustionSwitchesModel:
    """Regression coverage for a real dead job: it spent all 20 auto-continues stuck on
    tokenrouter/z-ai/glm-5.3-free because stall-exhaustion (unlike rate-limit failover) never
    switched models at all - every continue (automatic or the user's own Continue click) just
    hammered the same already-dead connection again.

    Rotation happens at the single point a stall-exhausted job actually RESUMES (_run's own
    auto-continue, or continue_job() for a manual Continue click) rather than at the moment of
    exhaustion itself - so it rotates exactly once per exhaustion instead of needing the same
    dead model to fail a second time before a later exhaustion's rotation kicks in. job.model is
    deliberately left as the model that just failed right up until then, for an accurate
    checkpoint of what actually broke."""

    def test_stall_exhaustion_leaves_job_model_as_the_one_that_just_failed(self):
        fake_llm = StallsOnEveryModelLLM()
        manager = JobManager(llm=fake_llm, graph=None, store=None)
        job = _job(required_tools=[])
        job.model = "model-a"

        manager._loop(job, resuming=False)

        assert job.status == "error"
        assert job.error_reason == "stall_exhausted"
        assert job.model == "model-a"
        assert not [e for e in job.events if "model_switched" in e]

    def test_a_manual_continue_after_stall_exhaustion_rotates_to_a_different_model(self):
        fake_llm = StallsOnEveryModelLLM()
        manager = JobManager(llm=fake_llm, graph=None, store=None)
        job = _job(required_tools=[])
        job.model = "model-a"
        manager._loop(job, resuming=False)

        with manager._lock:
            manager._jobs[job.id] = job
        resumed = manager.continue_job(job.id)

        assert resumed is not None
        # Retrying the exact model that just stalled out is very likely to just stall again -
        # continue_job() must not hand it straight back the dead model.
        assert resumed.model == "model-b"
        model_switch_events = [e["model_switched"] for e in resumed.events if "model_switched" in e]
        assert "model-b" in model_switch_events

    def test_the_automatic_auto_continue_also_rotates_after_a_stall_exhaustion(self):
        # _run's OWN auto-continue loop (not a manual Continue click) must rotate the same way -
        # this is what actually saves an unattended overnight run from burning its entire
        # auto-continue budget on one dead connection.
        fake_llm = StallsOnEveryModelLLM()
        manager = JobManager(llm=fake_llm, graph=None, store=None)
        job = _job(required_tools=[])
        job.model = "model-a"

        manager._run(job, resuming=False)

        # Every model in the ring stalls too, so this keeps rotating (a -> b -> c -> a -> ...)
        # across auto_continues until the whole budget is exhausted - the key assertion is that it
        # actually visited more than one model along the way, not that it ends on any particular one.
        assert job.status == "error"
        assert len(set(fake_llm.models_tried)) > 1
        model_switch_events = [e["model_switched"] for e in job.events if "model_switched" in e]
        assert len(model_switch_events) > 0
        assert len(set(model_switch_events)) > 1


def _mid_stream_fallback_wrapping_rate_limit(model: str):
    inner = litellm.RateLimitError(message="rate limited", llm_provider="gemini", model=model)
    return litellm.exceptions.MidStreamFallbackError(
        message="quota exceeded", model=model, llm_provider="gemini", original_exception=inner,
    )


class RateLimitedThenRecoversLLM:
    """model-a rate-limits before a single chunk goes out (the "wrapped, not bare, RateLimitError"
    shape that a real Gemini quota hit actually arrives as); model-b, the next candidate in the
    same tier, completes normally."""

    def __init__(self):
        self.models_tried: list[str] = []

    def stream(self, model, messages, timeout=240, **kwargs):
        self.models_tried.append(model)
        if model == "model-a":
            raise _mid_stream_fallback_wrapping_rate_limit(model)
        yield _fake_chunk("done")

    def record_usage(self, *args, **kwargs):
        return {"prompt_tokens": 0, "completion_tokens": 0}

    def context_window(self, model):
        return 8000

    def tier_of(self, model):
        return "balanced"

    def models_for_tier(self, tier):
        return ["model-a", "model-b"]


class TestWrappedRateLimitTriggersModelSwitch:
    """Regression coverage for a real bug: a Gemini 429 that surfaced as
    litellm.MidStreamFallbackError (not a bare litellm.RateLimitError) fell straight through the
    isinstance check in _loop's run_round, skipping even the last-resort model-switch fallback."""

    def test_wrapped_rate_limit_switches_to_the_next_model_in_tier(self):
        fake_llm = RateLimitedThenRecoversLLM()
        manager = JobManager(llm=fake_llm, graph=None, store=None)
        job = _job(required_tools=[])
        job.model = "model-a"

        final_message = MagicMock()
        final_message.choices = [MagicMock()]
        final_message.choices[0].message.content = ""
        final_message.choices[0].message.tool_calls = None

        with patch("backend.agents.jobs.litellm.stream_chunk_builder", return_value=final_message):
            manager._loop(job, resuming=False)

        assert fake_llm.models_tried == ["model-a", "model-b"]
        model_switch_events = [e["model_switched"] for e in job.events if "model_switched" in e]
        assert model_switch_events == ["model-b"]
        assert job.status != "error"


class AllRingModelsRateLimitThenTheSecondLapRecoversLLM:
    """model-a, model-b, model-c (a tier's whole failover_ring) all rate-limit on their first
    attempt; model-a recovers on the SECOND lap - the real motivation for round-robin: by the time
    a lap completes, real time has passed and an earlier model's rate-limit window may have
    rolled, so it deserves another shot before falling to weaker non-ring models."""

    def __init__(self):
        self.models_tried: list[str] = []
        self._model_a_calls = 0

    def stream(self, model, messages, timeout=240, **kwargs):
        self.models_tried.append(model)
        if model == "model-a":
            self._model_a_calls += 1
            if self._model_a_calls == 1:
                raise _mid_stream_fallback_wrapping_rate_limit(model)
            yield _fake_chunk("recovered on lap two")
            return
        raise _mid_stream_fallback_wrapping_rate_limit(model)

    def record_usage(self, *args, **kwargs):
        return {"prompt_tokens": 0, "completion_tokens": 0}

    def context_window(self, model):
        return 8000

    def tier_of(self, model):
        return "heavy"

    def models_for_tier(self, tier):
        return ["model-a", "model-b", "model-c", "model-d"]

    def failover_ring(self, tier):
        return ["model-a", "model-b", "model-c"]  # model-d deliberately excluded - not in the ring


class TestRoundRobinFailoverRing:
    """A tier with a failover_ring (see llm.py) round-robins back to its own start once every
    model in the ring has been tried, instead of dropping to the tier's non-ring last-resort
    models or giving up outright - the real request behind this: "when this falls to glm after
    glm hits a break move back to start of queue ie 3.8 kinda like round robin"."""

    def test_exhausting_the_whole_ring_wraps_back_to_its_first_model_instead_of_a_non_ring_model(self):
        fake_llm = AllRingModelsRateLimitThenTheSecondLapRecoversLLM()
        manager = JobManager(llm=fake_llm, graph=None, store=None)
        job = _job(required_tools=[])
        job.model = "model-a"

        final_message = MagicMock()
        final_message.choices = [MagicMock()]
        final_message.choices[0].message.content = ""
        final_message.choices[0].message.tool_calls = None

        with patch("backend.agents.jobs.litellm.stream_chunk_builder", return_value=final_message):
            manager._loop(job, resuming=False)

        # model-a -> model-b -> model-c (ring exhausted) -> wraps back to model-a, which recovers -
        # never reaches model-d, the excluded non-ring last-resort.
        assert fake_llm.models_tried == ["model-a", "model-b", "model-c", "model-a"]
        assert "model-d" not in fake_llm.models_tried
        assert job.status != "error"


class TestZeroChunkFailureUsesTheSameStallRecoveryAsPartialFailure:
    """Regression coverage for a real bug found during the auto-continue/watchdog audit: a round
    that failed with ZERO chunks ever emitted took a completely different, unguarded path than a
    round that emitted some chunks first - no exception handling, no bounded retry count. Any
    further failure there (including the identical silent-hang happening again) killed the job
    outright with a bare "TimeoutError: ..." message, bypassing every safety net below it."""

    def test_a_zero_chunk_failure_recovers_via_stall_recovery_not_a_bare_crash(self):
        manager = JobManager(llm=SilentlyHangingLLM(), graph=None, store=None)
        job = _job(required_tools=["write_file"])

        manager._loop(job, resuming=False)

        # Must still reach the SAME bounded, explicit exhaustion message as the partial-chunk case
        # - not an unhandled "TimeoutError: ..." from an unguarded fallback.
        assert job.status == "error"
        error_events = [e["error"] for e in job.events if "error" in e]
        assert error_events
        assert "TimeoutError" not in error_events[-1]
        assert job.stall_recoveries >= 1

    def test_a_zero_chunk_failure_respects_the_same_max_stall_recoveries_cap(self):
        manager = JobManager(llm=SilentlyHangingLLM(), graph=None, store=None)
        job = _job(required_tools=["write_file"])

        manager._loop(job, resuming=False)

        from backend.agents.jobs import _MAX_STALL_RECOVERIES
        assert job.stall_recoveries == _MAX_STALL_RECOVERIES


class TestStallExhaustionIsAutoRecoverable:
    """Regression coverage for a real, live-observed bug: a job that exhausted its stall-recovery
    retries (error_reason == "stall_exhausted") went completely unrecognized by _run's
    auto-continue mechanism — which only checked for error_reason == "max_rounds" — and sat there
    permanently needing a manual restart even though its auto_continues counter was nowhere near
    its own cap. Confirmed live: a job died with auto_continues=3/20, and _run's own new diagnostic
    logging showed error_reason=None at the exact decision point (the field genuinely wasn't
    "max_rounds", because the real cause was stall exhaustion, an entirely different, unrecognized
    reason)."""

    def test_stall_exhaustion_sets_a_recognizable_error_reason(self):
        manager = JobManager(llm=StallingLLM(), graph=None, store=None)
        job = _job(required_tools=["write_file"])
        from backend.agents.jobs import _MAX_AUTO_CONTINUES
        job.auto_continues = _MAX_AUTO_CONTINUES  # already at cap - _run gives up after one exhaustion

        manager._run(job, resuming=False)

        assert job.status == "error"
        assert job.error_reason == "stall_exhausted"
        error_events = [e["error"] for e in job.events if "error" in e]
        assert error_events
        assert "TimeoutError" not in error_events[-1]

    def test_stall_exhaustion_auto_continues_and_resets_the_stall_counter(self):
        manager = JobManager(llm=StallingLLM(), graph=None, store=None)
        job = _job(required_tools=["write_file"])
        # Only allow ONE auto-continue so this test doesn't have to run 20 full exhaustion cycles -
        # the fix under test (recognizing stall_exhausted at all) is proven by the first cycle.
        from backend.agents import jobs as jobs_mod
        with patch.object(jobs_mod, "_MAX_AUTO_CONTINUES", 1):
            manager._run(job, resuming=False)

        auto_continue_events = [
            e["tool_call"] for e in job.events if e.get("tool_call", {}).get("name") == "_auto_continue"
        ]
        assert len(auto_continue_events) == 1
        # Final state: exhausted its ONE allowed auto-continue, genuinely terminal now.
        assert job.status == "error"
        assert job.error_reason == "stall_exhausted"
        assert job.auto_continues == 1

    def test_continue_job_accepts_stall_exhausted_and_resets_the_counter(self):
        manager = JobManager(llm=StallingLLM(), graph=None, store=None)
        job = _job(required_tools=["write_file"])
        job.status = "error"
        job.error_reason = "stall_exhausted"
        job.stall_recoveries = 2
        manager._jobs[job.id] = job

        with patch("backend.agents.jobs.threading.Thread") as mock_thread_cls:
            mock_thread_cls.return_value = MagicMock()  # don't actually run _run here
            result = manager.continue_job(job.id)

        assert result is not None
        assert result.stall_recoveries == 0
        assert result.error_reason is None
        assert result.status == "running"


class TestConsecutiveStallNudgesAreCollapsed:
    """Regression coverage for a real, live-observed failure: a run of consecutive zero-chunk
    stalls appended a fresh, byte-identical nudge message every single time. A live incident saw
    6+ of these stack up back to back (on two separate jobs) right before the connection went
    completely silent for the rest of the run and never recovered - a growing wall of exact
    duplicate messages is exactly the kind of malformed-looking input that could itself be feeding
    the very stalls it's meant to recover from, not just a symptom of them."""

    def test_two_consecutive_zero_chunk_stalls_produce_only_one_nudge_message(self):
        manager = JobManager(llm=SilentlyHangingLLM(), graph=None, store=None)
        job = _job(required_tools=["write_file"])

        manager._loop(job, resuming=False)

        from backend.agents.jobs import _STALL_NUDGE_TEXT
        nudge_count = sum(
            1 for m in job.messages
            if m.get("role") == "user" and m.get("content") == _STALL_NUDGE_TEXT
        )
        # _MAX_STALL_RECOVERIES stalls happen before exhaustion, but every one of them is a
        # zero-chunk stall immediately following the previous nudge - all collapse into one.
        assert nudge_count == 1

    def test_messages_and_message_rounds_stay_in_sync_when_nudges_are_collapsed(self):
        # Regression for a bug caught while building the fix above: skipping the messages.append
        # for a collapsed nudge but still unconditionally appending to message_rounds would
        # silently desync the two parallel arrays.
        manager = JobManager(llm=SilentlyHangingLLM(), graph=None, store=None)
        job = _job(required_tools=["write_file"])

        manager._loop(job, resuming=False)

        assert len(job.messages) == len(job.message_rounds)

    def test_a_nudge_after_real_partial_content_is_not_collapsed(self):
        # StallingLLM yields one real chunk before failing each time - the assistant's partial
        # content message sits between nudges, so nothing should ever be deduped here.
        manager = JobManager(llm=StallingLLM(), graph=None, store=None)
        job = _job(required_tools=["write_file"])

        manager._loop(job, resuming=False)

        from backend.agents.jobs import _MAX_STALL_RECOVERIES, _STALL_NUDGE_TEXT
        nudge_count = sum(
            1 for m in job.messages
            if m.get("role") == "user" and m.get("content") == _STALL_NUDGE_TEXT
        )
        assert nudge_count == _MAX_STALL_RECOVERIES
        assert len(job.messages) == len(job.message_rounds)
