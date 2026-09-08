"""Reasoning must produce durable commitment, and execution must consume it.

The deadlock this closes, observed live on the PALIMPSEST benchmark:

    round 32 cut at 40,053 reasoning chars
    round 33 cut at 40,002 reasoning chars
    round 34 ran 20 minutes and was never cut at all

The first two are the same deliberation generated and thrown away twice. Discarding a cut round's
reasoning is correct — re-feeding it invites the model straight back into what it was stopped for —
but it left two states indistinguishable to the controller:

    "I have not decided what to build."
    "I have decided exactly what to build and had not yet emitted the tool call."

Both look like a cut round with nothing to show, so recovery was identical for both: retry, and be
cut again at the same size. A commitment cannot be recovered from a transcript that was deliberately
thrown away, so it has to be made as an ACTION — commit_direction — which survives the cut, lands in
the checkpoint, and turns the next round into a genuinely different one.

The third round exposed a separate hole: the budget counted only `reasoning_content`, so a model
deliberating in the CONTENT channel was invisible to it while still resetting the 90s stall
watchdog. Two guards, both blind, and an unbounded round between them.
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from backend.agents.jobs import (
    _COMMIT_FIRST_TEXT,
    _EXECUTION_CHARS,
    _MAX_ROUND_SECONDS,
    _PLANNING_CHARS,
    Job,
    JobManager,
    _execution_directive,
    _GenerationBudgetExceeded,
)
from backend.agents.tools import _commit_direction


def _thinking(text: str):
    return SimpleNamespace(choices=[SimpleNamespace(
        delta=SimpleNamespace(content=None, reasoning_content=text))])


def _content(text: str):
    return SimpleNamespace(choices=[SimpleNamespace(
        delta=SimpleNamespace(content=text, reasoning_content=None))])


class _BaseLLM:
    def record_usage(self, *a, **k):
        return {"prompt_tokens": 1, "completion_tokens": 1}

    def context_window(self, model):
        return 128_000

    def tier_of(self, model):
        return None

    def models_for_tier(self, tier):
        return []


def _job(job_id: str, *, groups=("repo",), commitment=None) -> Job:
    return Job(
        id=job_id, repository="demo-repo", model="fake-model",
        messages=[{"role": "user", "content": "Build a single-page archive"}],
        message_rounds=[-100],
        contract={"intent": "CREATE_ARTIFACT", "required_tools": [], "allowed_tools": [],
                  "success_criteria": [], "constraints": [], "suggested_workflow": []},
        active_tool_groups=list(groups),
        plan={"objective": "", "tasks": []},  # this file is about the round budget, not the plan
        commitment=commitment,
    )


# ── the commitment record itself ──────────────────────────────────────────────


class TestCommitmentIsAnAction:
    def test_it_records_the_decision_onto_the_context(self):
        ctx: dict = {}
        _commit_direction("A layered manuscript archive.", ["Spectral + IBM Plex Mono"],
                          "index.html", "write_file(index.html)", context=ctx)
        record = ctx["commitment"]
        assert record["direction"].startswith("A layered")
        assert record["primary_artifact"] == "index.html"

    def test_an_empty_direction_records_nothing(self):
        # A commitment that commits to nothing would satisfy the escape without ending the loop.
        ctx: dict = {}
        result = _commit_direction("", context=ctx)
        assert "Refused" in result
        assert "commitment" not in ctx

    def test_it_tells_the_model_the_decision_is_now_settled(self):
        text = _commit_direction("An archive.", context={})
        assert "do not reconsider" in text.lower()

    def test_it_is_cheap_enough_to_reach_inside_any_budget(self):
        # The entire point: a model that could not finish planning inside 40,000 characters can
        # still emit this. Bounded so a model cannot turn the commitment itself into another essay.
        ctx: dict = {}
        _commit_direction("x" * 5000, ["y" * 500] * 40, "a" * 500, "b" * 500, context=ctx)
        record = ctx["commitment"]
        assert len(record["direction"]) <= 1200
        assert len(record["decisions"]) <= 12


# ── the budget ────────────────────────────────────────────────────────────────


class TestTheBudgetSeesBothChannels:
    """Counting only `reasoning_content` was the hole. A round deliberating in the content channel
    ran for twenty minutes: never cut, because the counter saw nothing; never stalled, because
    chunks kept arriving."""

    class ContentChannelThinker(_BaseLLM):
        def __init__(self):
            self.rounds = 0

        def stream(self, model, messages, timeout=240, **kwargs):
            self.rounds += 1
            while True:
                yield _content("z" * 2000)

    def test_deliberation_in_the_content_channel_is_still_cut(self):
        llm = self.ContentChannelThinker()
        manager = JobManager(llm=llm, graph=None, store=None)
        job = _job("content-channel")

        with patch("backend.agents.jobs.litellm.stream_chunk_builder", return_value=None):
            manager._loop(job, resuming=False)

        assert job.status != "running", "an unbounded content-channel round must not survive"
        assert llm.rounds > 1, "it must be cut and retried, not hang on one round"

    def test_the_execution_budget_is_shorter_than_the_planning_one(self):
        # Once a direction is committed the thinking has been done and recorded. Giving an execution
        # round another forty thousand characters is how "deep task" turns back into "deep round".
        assert _EXECUTION_CHARS < _PLANNING_CHARS


class TestTheWallClockBackstop:
    def test_there_is_a_ceiling_that_does_not_depend_on_classification(self):
        # The one guard that cannot be evaded by emitting through an unexpected field — which is
        # exactly how the last deadlock survived the other two.
        assert 60 <= _MAX_ROUND_SECONDS <= 30 * 60

    def test_a_slow_trickle_that_never_fills_the_budget_still_ends(self, monkeypatch):
        monkeypatch.setattr("backend.agents.jobs._MAX_ROUND_SECONDS", 0.25)

        class Trickler(_BaseLLM):
            def __init__(self):
                self.rounds = 0

            def stream(self, model, messages, timeout=240, **kwargs):
                self.rounds += 1
                while True:
                    # Far too little to reach any character budget, forever.
                    time.sleep(0.02)
                    yield _content(".")

        llm = Trickler()
        manager = JobManager(llm=llm, graph=None, store=None)
        job = _job("trickle")
        with patch("backend.agents.jobs.litellm.stream_chunk_builder", return_value=None):
            manager._loop(job, resuming=False)

        assert job.status != "running"
        assert llm.rounds > 1


class TestTheExceptionCarriesItsCause:
    @pytest.mark.parametrize("reason", ["planning", "execution", "wall-clock"])
    def test_the_reason_survives(self, reason):
        # Load-bearing: the four causes recover differently, and recovering them identically is what
        # let one round repeat itself indefinitely.
        exc = _GenerationBudgetExceeded(40_053, 61.0, reason)
        assert exc.reason == reason
        assert exc.chars == 40_053


# ── recovery ──────────────────────────────────────────────────────────────────


class TestACutBeforeCommitmentAsksForTheDecision:
    class AlwaysDeliberates(_BaseLLM):
        def __init__(self):
            self.tool_choices: list = []

        def stream(self, model, messages, timeout=240, **kwargs):
            self.tool_choices.append(kwargs.get("tool_choice"))
            while True:
                yield _thinking("q" * 2000)

    def _run(self):
        llm = self.AlwaysDeliberates()
        manager = JobManager(llm=llm, graph=None, store=None)
        job = _job("cut-before-commit")
        with patch("backend.agents.jobs.litellm.stream_chunk_builder", return_value=None):
            manager._loop(job, resuming=False)
        return job, llm

    def test_the_next_round_is_forced_to_commit_rather_than_to_implement(self):
        """The core fix. Forcing write_file on a model that could not reach the end of its own
        planning asks it to do the hard thing under a shorter leash — and it deadlocked, twice, at
        40,053 and 40,002 characters."""
        _job_, llm = self._run()
        forced = [c for c in llm.tool_choices if isinstance(c, dict)]
        assert forced, f"nothing was forced: {llm.tool_choices}"
        assert forced[0] == {"type": "function",
                             "function": {"name": "commit_direction"}}, forced[0]

    def test_the_first_round_is_still_free(self):
        _job_, llm = self._run()
        assert llm.tool_choices[0] == "auto"

    def test_the_model_is_told_to_record_what_it_already_decided(self):
        job, _llm = self._run()
        sent = [m["content"] for m in job.messages if m.get("role") == "user"]
        assert any("commit_direction" in str(c) for c in sent)

    def test_the_cut_is_reported_with_its_cause(self):
        job, _llm = self._run()
        cuts = [e["tool_call"]["args"] for e in job.events
                if e.get("tool_call", {}).get("name") == "_round_cut"]
        assert cuts, "a cut must be visible, not silent"
        assert cuts[0]["cause"] == "cap_before_commit"
        assert cuts[0]["committed"] is False

    def test_consecutive_cuts_are_counted(self):
        # Two identical cuts in a row means repeating the round is pointless. The controller has to
        # be able to see the streak to change mode rather than retry.
        job, _llm = self._run()
        assert job.consecutive_cuts >= 2


class TestACutAfterCommitmentDrivesTheAction:
    def test_the_directive_carries_the_decision_forward(self):
        text = _execution_directive(
            {"direction": "A layered manuscript archive.",
             "decisions": ["Spectral + IBM Plex Mono", "oxide accent"],
             "primary_artifact": "index.html"},
            "write_file")
        assert "A layered manuscript archive." in text
        assert "Spectral + IBM Plex Mono" in text
        assert "index.html" in text
        assert "write_file" in text

    def test_it_forbids_reopening_the_decision(self):
        text = _execution_directive({"direction": "An archive."}, "write_file").lower()
        assert "do not reconsider" in text

    def test_it_carries_decisions_not_deliberation(self):
        # Replaying the reasoning that produced a decision is what invites a model back into the
        # deliberation it was cut out of. Replaying the decision itself ends it.
        text = _execution_directive({"direction": "An archive.", "decisions": ["serif headings"]},
                                    "write_file").lower()
        assert "reasoning" not in text and "chain of thought" not in text

    def test_a_committed_job_is_not_asked_to_commit_again(self):
        class Deliberates(_BaseLLM):
            def __init__(self):
                self.tool_choices: list = []

            def stream(self, model, messages, timeout=240, **kwargs):
                self.tool_choices.append(kwargs.get("tool_choice"))
                while True:
                    yield _thinking("w" * 2000)

        llm = Deliberates()
        manager = JobManager(llm=llm, graph=None, store=None)
        job = _job("already-committed", groups=("repo", "code"),
                   commitment={"direction": "An archive.", "decisions": [],
                               "primary_artifact": "index.html", "next_action": "write_file"})
        with patch("backend.agents.jobs.litellm.stream_chunk_builder", return_value=None):
            manager._loop(job, resuming=False)

        forced = [c for c in llm.tool_choices if isinstance(c, dict)]
        assert all(c["function"]["name"] != "commit_direction" for c in forced), forced

    def test_a_committed_job_reports_the_right_cause(self):
        class Deliberates(_BaseLLM):
            def stream(self, model, messages, timeout=240, **kwargs):
                while True:
                    yield _thinking("w" * 2000)

        manager = JobManager(llm=Deliberates(), graph=None, store=None)
        job = _job("committed-cause", commitment={"direction": "An archive.", "decisions": [],
                                                  "primary_artifact": "", "next_action": ""})
        with patch("backend.agents.jobs.litellm.stream_chunk_builder", return_value=None):
            manager._loop(job, resuming=False)

        causes = {e["tool_call"]["args"]["cause"] for e in job.events
                  if e.get("tool_call", {}).get("name") == "_round_cut"}
        assert causes == {"cap_after_commit"}, causes


class TestCommitmentIsDurable:
    def test_it_survives_a_checkpoint_round_trip(self):
        job = _job("durable", commitment={"direction": "An archive.", "decisions": ["serif"],
                                          "primary_artifact": "index.html", "next_action": ""})
        restored = Job.from_disk(job.to_disk())
        assert restored.commitment["direction"] == "An archive."
        assert restored.commitment["decisions"] == ["serif"]

    def test_a_checkpoint_written_before_this_existed_still_loads(self):
        data = _job("old").to_disk()
        del data["commitment"]
        del data["consecutive_cuts"]
        # An in-flight job resumed after a deploy must not be unresumable because of a new field.
        restored = Job.from_disk({**data, "commitment": None, "consecutive_cuts": 0})
        assert restored.commitment is None


class TestCancellationReachesTheProvider:
    """A cut must actually stop generation at the provider, not merely stop reading it. Setting a
    flag alone is a request the producer can only honour after its NEXT chunk arrives, which on a
    model mid-deliberation can be minutes and on a silent connection is never — the whole time
    billing for output nobody will read."""

    def test_the_stream_is_closed_when_the_consumer_stops_early(self):
        from backend.agents.jobs import _stream_with_watchdog

        class Source:
            def __init__(self):
                self.closed = False
                self.yielded = 0

            def __iter__(self):
                return self

            def __next__(self):
                self.yielded += 1
                return _content("x")

            def close(self):
                self.closed = True

        source = Source()
        stream = _stream_with_watchdog(source)
        next(stream)
        stream.close()  # consumer gives up, exactly as the budget cut does

        deadline = time.time() + 2
        while time.time() < deadline and not source.closed:
            time.sleep(0.01)
        assert source.closed, "the provider stream must be closed, not just abandoned"

    def test_a_cut_round_does_not_leave_the_producer_running(self):
        # The regression this guards: a cut left the producer thread pulling from an infinite
        # generator forever, burning provider quota for output nobody reads.
        import threading

        before = threading.active_count()

        class Endless(_BaseLLM):
            def stream(self, model, messages, timeout=240, **kwargs):
                while True:
                    yield _thinking("e" * 2000)

        manager = JobManager(llm=Endless(), graph=None, store=None)
        job = _job("no-orphans")
        with patch("backend.agents.jobs.litellm.stream_chunk_builder", return_value=None):
            manager._loop(job, resuming=False)

        deadline = time.time() + 5
        while time.time() < deadline and threading.active_count() > before + 2:
            time.sleep(0.05)
        assert threading.active_count() <= before + 2, "producer threads leaked past the cut"


class TestTheDirectiveTextItself:
    def test_the_commit_directive_does_not_just_ask_it_to_try_harder(self):
        # "Please act" was measured to be worth nothing: after an explicit instruction to call a
        # tool, the next round spent another 23,692 characters planning and called nothing.
        text = _COMMIT_FIRST_TEXT.lower()
        assert "commit_direction" in text
        assert "cheap" in text or "writes nothing to disk" in text
        assert "decide now" in text or "whatever you have" in text


class TestTheBudgetFollowsWhatTheTaskMustProduce:
    """`_EXECUTION_CHARS` was 18,000 on the theory that a committed direction means the thinking is
    done. That theory is wrong for the task that matters most: a round whose job is to produce a
    1,000-line document legitimately deliberates about its content before emitting the first token
    of the tool argument.

    Measured on a real run — three consecutive rounds cut at 18,004 / 18,007 / 18,004 characters,
    the same "regenerate and discard" signature as the original 40k deadlock, at a lower threshold,
    with no artifact produced. The budget now follows what the task must PRODUCE rather than which
    phase it is in.
    """

    def test_an_authoring_task_gets_the_full_allowance(self):
        from backend.agents.jobs import _AUTHORING_CHARS, _PLANNING_CHARS
        assert _AUTHORING_CHARS >= _PLANNING_CHARS, (
            "composing the artifact IS the deliberation for that task")

    def test_a_non_authoring_task_still_gets_the_short_leash(self):
        # The original reasoning does hold where a round only has to run or verify something.
        from backend.agents.jobs import _AUTHORING_CHARS, _EXECUTION_CHARS
        assert _EXECUTION_CHARS < _AUTHORING_CHARS

    def test_the_wall_clock_still_bounds_both(self):
        # Whatever the character budget, the guard that does not depend on classifying output stays.
        from backend.agents.jobs import _MAX_ROUND_SECONDS
        assert 60 <= _MAX_ROUND_SECONDS <= 30 * 60


class TestTheDebugOverrideNeverLeaksIntoTests:
    def test_the_round_cap_is_active_under_test(self):
        """CODEXA_ROUND_BUDGET=0 is a legitimate debugging switch set in .env, which
        backend/main.py loads at import. Several tests drive _loop with a model that never completes
        and rely on the round cap to terminate — with the cap gone they run forever, and the suite
        stopped finishing at all. A suite must never inherit a debugging switch from its machine."""
        from backend.agents.jobs import _UNLIMITED_ROUNDS
        assert _UNLIMITED_ROUNDS is False
