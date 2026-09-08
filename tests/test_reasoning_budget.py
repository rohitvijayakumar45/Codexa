"""A single round must not be able to run forever.

Every other guard in the loop acts BETWEEN rounds, which left one phase completely unwatched:
_stream_with_watchdog resets its 90s timer on every chunk, so a model that keeps emitting reasoning
never trips it; the round budget counts rounds, so an endless first round reads as "round 0,
healthy"; and validate_completion only runs once a round returns. A real build sat in round 0 for
tens of minutes emitting nothing but reasoning, with no checkpoint, no files, and no mechanism
capable of noticing — one observed call spent 30,478 reasoning tokens to yield 131 tokens of output.

The budget converts that invisible hang into an ordinary recoverable event: cut the round, tell the
model to stop planning and act, and keep going.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from backend.agents.jobs import (
    Job,
    JobManager,
    _MAX_REASONING_CHARS_PER_ROUND,
    _REASONING_NUDGE_TEXT,
    _ReasoningBudgetExceeded,
)


def _thinking_chunk(text: str):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=None, reasoning_content=text))])


def _text_chunk(text: str):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text, reasoning_content=None))])


class EndlessThinkerLLM:
    """Emits reasoning forever and never returns — the shape of the observed hang. Chunks keep
    arriving, so the stall watchdog is satisfied the entire time."""

    def __init__(self):
        self.rounds = 0

    def stream(self, model, messages, timeout=240, **kwargs):
        self.rounds += 1
        while True:
            yield _thinking_chunk("x" * 2000)

    def record_usage(self, *a, **k):
        return {"prompt_tokens": 0, "completion_tokens": 0}

    def context_window(self, model):
        return 128000

    def tier_of(self, model):
        return None

    def models_for_tier(self, tier):
        return []


class ThinksHardThenActsLLM:
    """Over-thinks the first round, then complies and calls a tool — the recovery path that
    matters: the job must survive the cut and go on to produce real work."""

    def __init__(self):
        self.saw_nudge = False

    def stream(self, model, messages, timeout=240, **kwargs):
        if any(m.get("content") == _REASONING_NUDGE_TEXT for m in messages):
            self.saw_nudge = True
            yield _text_chunk("Writing it now.")
            return
        while True:
            yield _thinking_chunk("y" * 2000)

    def record_usage(self, *a, **k):
        return {"prompt_tokens": 1, "completion_tokens": 1}

    def context_window(self, model):
        return 128000

    def tier_of(self, model):
        return None

    def models_for_tier(self, tier):
        return []


def _job(job_id: str, required_tools=None) -> Job:
    return Job(
        id=job_id,
        repository="demo-repo",
        model="fake-model",
        messages=[{"role": "user", "content": "Build a single-page app"}],
        message_rounds=[-100],
        contract={
            "intent": "CREATE_ARTIFACT", "required_tools": required_tools or [],
            "allowed_tools": [], "success_criteria": [], "constraints": [], "suggested_workflow": [],
        },
        active_tool_groups=[],
        # Explicit empty execution plan (backend/agents/plan.py) — these tests are about the
        # per-ROUND reasoning cut in isolation. The per-TASK reasoning budget that builds on it, and
        # the controller's task-aware forcing, are covered in tests/test_controller.py.
        plan={"objective": "", "tasks": []},
    )


class TestTheBudgetIsSane:
    def test_it_is_generous_enough_that_normal_thinking_never_hits_it(self):
        # Roughly 10k reasoning tokens. Real planning for one step is far below this; the cap is
        # for pathological deliberation, not for ordinary care.
        assert _MAX_REASONING_CHARS_PER_ROUND >= 20_000

    def test_the_nudge_tells_the_model_to_act_rather_than_to_continue(self):
        # A stall nudge says "carry on from where you left off". That is the wrong instruction
        # here and would restart the very deliberation that was just cut.
        text = _REASONING_NUDGE_TEXT.lower()
        assert "write_file" in text
        assert "must call a tool" in text
        assert "continue exactly from where you left off" not in text


class TestAnEndlessRoundIsCut:
    def test_a_round_that_only_thinks_does_not_run_forever(self):
        llm = EndlessThinkerLLM()
        manager = JobManager(llm=llm, graph=None, store=None)
        job = _job("reasoning-endless")

        with patch("backend.agents.jobs.litellm.stream_chunk_builder", return_value=None):
            manager._loop(job, resuming=False)

        # Terminates instead of hanging, and every round was cut rather than one running forever.
        assert job.status != "running"
        assert llm.rounds > 1

    def test_the_cut_does_not_consume_stall_recovery_budget(self):
        # Over-thinking is not a flaky connection. Spending the stall budget on it would leave a
        # job with no tolerance left for the real network failures that budget exists for.
        llm = EndlessThinkerLLM()
        manager = JobManager(llm=llm, graph=None, store=None)
        job = _job("reasoning-not-a-stall")

        with patch("backend.agents.jobs.litellm.stream_chunk_builder", return_value=None):
            manager._loop(job, resuming=False)

        assert job.stall_recoveries == 0

    def test_the_user_is_told_what_happened(self):
        llm = EndlessThinkerLLM()
        manager = JobManager(llm=llm, graph=None, store=None)
        job = _job("reasoning-visible")

        with patch("backend.agents.jobs.litellm.stream_chunk_builder", return_value=None):
            manager._loop(job, resuming=False)

        statuses = [e["status"] for e in job.events if "status" in e]
        assert any("planning" in s.lower() for s in statuses), statuses


class TestRecovery:
    def test_the_nudge_reaches_the_model_and_it_proceeds(self):
        llm = ThinksHardThenActsLLM()
        manager = JobManager(llm=llm, graph=None, store=None)
        job = _job("reasoning-recovers")

        final = MagicMock()
        final.choices = [MagicMock()]
        final.choices[0].message.content = "Writing it now."
        final.choices[0].message.tool_calls = None

        with patch("backend.agents.jobs.litellm.stream_chunk_builder", return_value=final):
            manager._loop(job, resuming=False)

        assert llm.saw_nudge, "the nudge must actually be sent to the model"
        assert job.status == "done"

    def test_the_nudge_is_not_stacked_over_and_over(self):
        # Repeated identical nudges are their own failure mode - a history full of duplicate
        # system messages was observed preceding a provider going permanently silent.
        llm = EndlessThinkerLLM()
        manager = JobManager(llm=llm, graph=None, store=None)
        job = _job("reasoning-no-pileup")

        with patch("backend.agents.jobs.litellm.stream_chunk_builder", return_value=None):
            manager._loop(job, resuming=False)

        nudges = [m for m in job.messages if m.get("content") == _REASONING_NUDGE_TEXT]
        assert len(nudges) <= 2, f"nudge stacked {len(nudges)} times"

    def test_messages_and_message_rounds_stay_in_sync(self):
        # These two lists are index-matched; compaction reads round numbers by position, so any
        # drift silently mis-ages the wrong message.
        llm = EndlessThinkerLLM()
        manager = JobManager(llm=llm, graph=None, store=None)
        job = _job("reasoning-sync")

        with patch("backend.agents.jobs.litellm.stream_chunk_builder", return_value=None):
            manager._loop(job, resuming=False)

        assert len(job.messages) == len(job.message_rounds)


class TestTheExceptionItself:
    def test_it_carries_the_measured_size(self):
        exc = _ReasoningBudgetExceeded(41234)
        assert exc.chars == 41234
        assert "41234" in str(exc)


class TestTheCutForcesAToolCallOnTheNextRound:
    """The nudge alone was measured to be insufficient. After a cut and an explicit "your next
    message must call a tool", the following round spent another 23,692 characters planning and
    called nothing. tool_choice="required" removes the option to reply with prose at all — the
    difference between asking a model to act and making acting the only legal response."""

    def _capture_tool_choice(self, llm_cls) -> list:
        seen = []

        class Recording(llm_cls):
            def stream(self, model, messages, timeout=240, **kwargs):
                seen.append(kwargs.get("tool_choice"))
                yield from super().stream(model, messages, timeout=timeout, **kwargs)

        manager = JobManager(llm=Recording(), graph=None, store=None)
        job = _job("force-tool")
        job.active_tool_groups = ["code"]  # a real group — tool_choice is only sent when tools exist
        with patch("backend.agents.jobs.litellm.stream_chunk_builder", return_value=None):
            manager._loop(job, resuming=False)
        return seen

    def test_the_first_round_is_free_to_choose(self):
        seen = self._capture_tool_choice(EndlessThinkerLLM)
        assert seen[0] == "auto"

    def test_the_round_after_a_cut_is_forced(self):
        seen = self._capture_tool_choice(EndlessThinkerLLM)
        assert len(seen) > 1
        assert seen[1] == "required", seen

    def test_forcing_is_consumed_and_does_not_persist(self):
        """Leaving it on permanently would mean the model could never deliver a final answer — a
        final response is by definition not a tool call. Forcing must apply to the round after a
        cut and then release, so a round that follows a NORMAL round is free again."""
        seen = []

        class CutOnceThenBehaves:
            """Round 0 over-thinks and is cut; every round after returns immediately."""

            def __init__(self):
                self.calls = 0

            def stream(self, model, messages, timeout=240, **kwargs):
                seen.append(kwargs.get("tool_choice"))
                self.calls += 1
                if self.calls == 1:
                    while True:
                        yield _thinking_chunk("z" * 2000)
                yield _text_chunk("done")

            def record_usage(self, *a, **k):
                return {"prompt_tokens": 1, "completion_tokens": 1}

            def context_window(self, model):
                return 128000

            def tier_of(self, model):
                return None

            def models_for_tier(self, tier):
                return []

        final = MagicMock()
        final.choices = [MagicMock()]
        final.choices[0].message.content = "done"
        final.choices[0].message.tool_calls = None

        manager = JobManager(llm=CutOnceThenBehaves(), graph=None, store=None)
        job = _job("force-released")
        job.active_tool_groups = ["code"]
        with patch("backend.agents.jobs.litellm.stream_chunk_builder", return_value=final):
            manager._loop(job, resuming=False)

        assert seen[0] == "auto", seen
        assert seen[1] == "required", seen  # the round right after the cut is forced
        # And the job then completes normally rather than being trapped in forced mode.
        assert job.status == "done"


class TestForcingNamesTheToolTheTaskActuallyNeeds:
    """tool_choice="required" was measured to be too weak. After a cut it made the model call
    something — but it chose the cheapest options available: screenshot against a URL serving
    nothing (ERR_CONNECTION_REFUSED) and list_directory on an empty repo — then resumed planning.
    Naming the contract's own outstanding required tool removes that escape hatch."""

    def _choices_for(self, required_tools, already_called=()):
        seen = []

        class Recording(EndlessThinkerLLM):
            def stream(self, model, messages, timeout=240, **kwargs):
                seen.append(kwargs.get("tool_choice"))
                yield from super().stream(model, messages, timeout=timeout, **kwargs)

        manager = JobManager(llm=Recording(), graph=None, store=None)
        job = _job("force-named", required_tools=list(required_tools))
        job.active_tool_groups = ["code", "browser"]
        job.tools_called = list(already_called)
        with patch("backend.agents.jobs.litellm.stream_chunk_builder", return_value=None):
            manager._loop(job, resuming=False)
        return seen

    def test_it_names_the_outstanding_required_tool(self):
        seen = self._choices_for(["write_file"])
        assert seen[1] == {"type": "function", "function": {"name": "write_file"}}, seen

    def test_a_requirement_already_satisfied_is_not_demanded_again(self):
        # write_file already happened; the outstanding requirement is the screenshot.
        seen = self._choices_for(["write_file", "screenshot"], already_called=["write_file"])
        assert seen[1] == {"type": "function", "function": {"name": "screenshot"}}, seen

    def test_it_falls_back_to_plain_required_when_nothing_is_outstanding(self):
        # An ANALYZE-style contract has no required tools; there is no specific call to demand,
        # so forcing must degrade to "call something" rather than crash or name nothing.
        seen = self._choices_for([])
        assert seen[1] == "required", seen

    def test_it_never_names_a_tool_the_job_cannot_call(self):
        # Naming a tool absent from this job's active groups would make the request unsatisfiable.
        seen = self._choices_for(["web_search"])  # 'external' group is not active here
        assert seen[1] == "required", seen
