"""delegate_build: the heavy orchestrator sends a SPEC, a worker model authors and saves the files.

Two things are under test, and they matter for different reasons.

Context: unlike delegate_task (which needs every byte inline in the plan, so the content still
passes through the orchestrator on the way out), delegate_build sends intent and receives a
summary. The file body never enters the orchestrator's context in either direction — which is what
stops a long multi-file build from inflating one conversation until compaction starts dropping the
conventions later files depend on.

Rotation: this is the second level of a two-level scheme. A single model's keys rotate inside
llm.complete_message, so a rate limit only reaches _WorkerSession once every key for that model is
spent; rotating the MODEL then moves to a genuinely independent quota bucket (Google meters per
model per project) rather than retrying the same exhausted limit.
"""

from unittest.mock import MagicMock, patch

import litellm
import pytest

from backend.agents.llm import LLMClient
from backend.agents.tools import (
    GRAPH_DIRTYING_TOOLS,
    _delegate_build,
    _EXECUTOR_TOOL_NAMES,
    _MAX_WORKER_LAPS,
    _WorkerSession,
    classify_intent,
    tool_groups,
    tools_for_groups,
)


def _rate_limit(model: str = "gemini/gemini-3.7-flash") -> litellm.RateLimitError:
    return litellm.RateLimitError(message="quota exceeded", llm_provider="gemini", model=model)


def _tool_call(name: str, arguments: str, call_id: str = "tc1") -> MagicMock:
    tc = MagicMock()
    tc.id = call_id
    tc.function.name = name
    tc.function.arguments = arguments
    return tc


def _msg(content: str = "", tool_calls: list | None = None) -> MagicMock:
    m = MagicMock()
    m.content = content
    m.tool_calls = tool_calls
    return m


class FakeLLM:
    """Worker ring of four models. `fail` names the models that always rate-limit."""

    def __init__(self, ring: list[str], responses: list, fail: set[str] | None = None):
        self._ring = ring
        self._responses = list(responses)
        self._fail = fail or set()
        self.calls: list[str] = []

    def worker_ring(self) -> list[str]:
        return list(self._ring)

    def complete_message(self, messages, *, model=None, tools=None, agent="chat"):
        self.calls.append(model)
        if model in self._fail:
            raise _rate_limit(model)
        return self._responses.pop(0), {"prompt_tokens": 1, "completion_tokens": 1}


class TestWorkerRotation:
    def test_rate_limited_worker_rotates_to_the_next_model(self):
        llm = FakeLLM(
            ring=["gemini-a", "gemini-b", "gemini-c", "gemini-d"],
            responses=[_msg("done")],
            fail={"gemini-a"},
        )
        session = _WorkerSession(llm)
        session.complete([], tools=None, agent="t")

        assert llm.calls == ["gemini-a", "gemini-b"]
        assert session.model == "gemini-b"
        assert session.switches == ["gemini-b"]

    def test_rotation_walks_the_whole_ring_before_giving_up(self):
        llm = FakeLLM(
            ring=["g-a", "g-b", "g-c", "g-d"],
            responses=[_msg("done")],
            fail={"g-a", "g-b", "g-c"},
        )
        session = _WorkerSession(llm)
        session.complete([], tools=None, agent="t")

        assert llm.calls == ["g-a", "g-b", "g-c", "g-d"]
        assert session.switches == ["g-b", "g-c", "g-d"]

    def test_a_spent_ring_wraps_for_another_lap_before_giving_up(self):
        # Round-robin, not a queue: a full lap costs real wall-clock time, so by the time the last
        # model 429s the first one's window may have rolled. Bounded by _MAX_WORKER_LAPS so a
        # genuinely dead ring still terminates rather than spinning against every provider forever.
        llm = FakeLLM(ring=["g-a", "g-b"], responses=[], fail={"g-a", "g-b"})
        session = _WorkerSession(llm)
        with pytest.raises(litellm.RateLimitError):
            session.complete([], tools=None, agent="t")
        assert llm.calls == ["g-a", "g-b"] * _MAX_WORKER_LAPS
        assert session.lap == _MAX_WORKER_LAPS - 1

    def test_wrapping_resets_key_rotation_so_a_new_lap_retries_every_key(self):
        # Sticky key rotation is right within a lap and wrong across one - without this, a wrapped
        # lap would only ever retry each model's LAST key while its earlier, separately-metered
        # keys sat untouched for the rest of the job.
        llm = FakeLLM(ring=["g-a", "g-b"], responses=[_msg("done")], fail={"g-a", "g-b"})
        llm.reset_keys = MagicMock()
        session = _WorkerSession(llm)
        session.rotate()  # a -> b, still lap 1, no reset
        llm.reset_keys.assert_not_called()
        session.rotate()  # ring spent -> wrap to lap 2
        llm.reset_keys.assert_called_once_with(["g-a", "g-b"])
        assert session.model == "g-a"

    def test_a_ring_that_recovers_on_the_second_lap_succeeds(self):
        class RecoversOnLapTwo(FakeLLM):
            def complete_message(self, messages, *, model=None, tools=None, agent="chat"):
                self.calls.append(model)
                if self.calls.count(model) < 2:  # every model 429s the first time it's tried
                    raise _rate_limit(model)
                return _msg("done"), {}

        llm = RecoversOnLapTwo(ring=["g-a", "g-b"], responses=[])
        session = _WorkerSession(llm)
        session.complete([], tools=None, agent="t")
        assert llm.calls == ["g-a", "g-b", "g-a"]  # wrapped, and the first model worked on lap 2

    def test_a_non_rate_limit_error_also_rotates_to_the_next_model(self):
        # Real, observed failure: 3.8-flash returned a genuine (non-rate-limit) provider error
        # mid-build, the OLD behavior (only is_rate_limit_error rotated) hit _delegate_build's outer
        # except and gave up on the spot, leaving 3.7 and every configured key completely untouched.
        # complete() now rotates on ANY exception — still bounded by the same lap budget as a rate
        # limit would be, so a genuinely dead ring still terminates rather than retrying forever.
        class Broken(FakeLLM):
            def complete_message(self, messages, *, model=None, tools=None, agent="chat"):
                self.calls.append(model)
                raise ValueError("malformed request")

        llm = Broken(ring=["g-a", "g-b"], responses=[])
        session = _WorkerSession(llm)
        with pytest.raises(ValueError):
            session.complete([], tools=None, agent="t")
        assert llm.calls == ["g-a", "g-b"] * _MAX_WORKER_LAPS
        assert session.lap == _MAX_WORKER_LAPS - 1

    def test_a_non_rate_limit_error_that_recovers_on_the_next_model_succeeds(self):
        # The direct fix, expressed positively: one bad model doesn't fail the whole build when a
        # peer in the ring is healthy.
        class OneBadModel(FakeLLM):
            def complete_message(self, messages, *, model=None, tools=None, agent="chat"):
                self.calls.append(model)
                if model == "g-a":
                    raise ValueError("malformed request")
                return _msg("done"), {}

        llm = OneBadModel(ring=["g-a", "g-b"], responses=[])
        session = _WorkerSession(llm)
        session.complete([], tools=None, agent="t")
        assert llm.calls == ["g-a", "g-b"]
        assert session.model == "g-b"

    def test_falls_back_to_the_light_tier_when_worker_ring_is_absent(self):
        # Older clients / test doubles without worker_ring must still delegate, not hard-fail.
        llm = MagicMock(spec=["models_for_tier", "complete_message", "default_model"])
        llm.models_for_tier.return_value = ["light-1", "light-2"]
        assert _WorkerSession(llm).ring == ["light-1", "light-2"]


class TestDelegateBuildAuthorsFiles:
    def test_worker_writes_the_file_and_only_a_summary_comes_back(self):
        body = "export const PulseView = () => <div className='apex-card' />;"
        llm = FakeLLM(
            ring=["gemini-a"],
            responses=[
                _msg(tool_calls=[_tool_call("write_file", f'{{"path": "src/views/PulseView.tsx", "content": "{body}"}}')]),
                _msg("Created PulseView using the apex-* tokens."),
            ],
        )
        with patch("backend.agents.tools.execute_tool", return_value="Wrote 62 bytes to src/views/PulseView.tsx."):
            out = _delegate_build("build PulseView", "demo-repo", llm=llm, graph=None, store=None)

        assert "src/views/PulseView.tsx" in out
        assert "files written" in out
        # The whole point: the orchestrator's context must not grow by the file body.
        assert "export const PulseView" not in out

    def test_the_spec_not_finished_content_is_what_reaches_the_worker(self):
        llm = FakeLLM(ring=["gemini-a"], responses=[_msg("done")])
        _delegate_build("build a telemetry view using apex-* tokens", "demo-repo", llm=llm, graph=None, store=None)
        # captured via the fake's recorded call - assert the worker was actually invoked
        assert llm.calls == ["gemini-a"]

    def test_rotation_during_a_build_is_reported_to_the_caller(self):
        # A caller that can see its worker walked the ring knows the budget is thin and can stop
        # delegating, rather than retrying into a wall.
        llm = FakeLLM(
            ring=["gemini-a", "gemini-b"],
            responses=[_msg("done")],
            fail={"gemini-a"},
        )
        out = _delegate_build("build something", "demo-repo", llm=llm, graph=None, store=None)
        assert "rotated on rate limits" in out
        assert "gemini-b" in out

    def test_a_build_that_wrote_nothing_says_so_loudly(self):
        llm = FakeLLM(ring=["gemini-a"], responses=[_msg("I could not determine the layout.")])
        out = _delegate_build("build something", "demo-repo", llm=llm, graph=None, store=None)
        assert "no files were written" in out.lower()

    def test_exhausted_ring_degrades_to_a_message_instead_of_crashing_the_turn(self):
        llm = FakeLLM(ring=["gemini-a", "gemini-b"], responses=[], fail={"gemini-a", "gemini-b"})
        out = _delegate_build("build something", "demo-repo", llm=llm, graph=None, store=None)
        assert "worker unavailable" in out
        assert "RateLimitError" in out

    def test_no_llm_client_degrades_gracefully(self):
        out = _delegate_build("build something", "demo-repo", llm=None, graph=None, store=None)
        assert "unavailable" in out and "yourself" in out


class TestWorkerIsGroundedInTheRealRepo:
    """A delegated worker starts with zero context, so 'follow the house conventions' has to be
    structural rather than a thing the orchestrator is trusted to remember writing into its spec.
    Relying on caller diligence is precisely the assumption that produced four mutually
    incompatible design vocabularies in one app."""

    def _capture_system(self, repository: str) -> str:
        captured: dict[str, str] = {}

        class L:
            def worker_ring(self):
                return ["gemini-a"]

            def complete_message(self, messages, *, model=None, tools=None, agent="chat"):
                captured["sys"] = messages[0]["content"]
                return _msg("done"), {}

        _delegate_build("build a view", repository, llm=L(), graph=None, store=None)
        return captured["sys"]

    def test_worker_must_read_before_writing_unconditionally(self):
        system = self._capture_system("demo-repo")
        assert "GROUND YOURSELF" in system
        # The silent-failure point is the reason the rule is non-negotiable, so it must be stated.
        assert "SILENTLY" in system

    def test_measured_conventions_are_injected_without_the_spec_asking(self, tmp_path, monkeypatch):
        repo = tmp_path / "repos" / "conv-repo" / "src"
        repo.mkdir(parents=True)
        (repo / "existing.ts").write_text("const a = 'x';\nconst b = 'y';\n", encoding="utf-8")
        monkeypatch.setattr("backend.agents.tools.repo_root", lambda _r: tmp_path / "repos" / "conv-repo")

        system = self._capture_system("conv-repo")
        assert "MEASURED CONVENTIONS" in system
        assert "single" in system  # single quotes, observed from the real file

    def test_an_empty_repo_degrades_to_no_convention_block(self, tmp_path, monkeypatch):
        empty = tmp_path / "repos" / "empty-repo"
        empty.mkdir(parents=True)
        monkeypatch.setattr("backend.agents.tools.repo_root", lambda _r: empty)

        system = self._capture_system("empty-repo")
        assert "MEASURED CONVENTIONS" not in system
        assert "GROUND YOURSELF" in system  # the rule itself still applies

    def test_convention_detection_failure_never_breaks_the_build(self, monkeypatch):
        monkeypatch.setattr(
            "backend.agents.tools._detect_conventions",
            MagicMock(side_effect=OSError("disk gone")),
        )
        system = self._capture_system("demo-repo")  # must not raise
        assert "GROUND YOURSELF" in system


class TestUltraHeavyTierIsolation:
    """The whole reason ultra_heavy exists: the orchestrator and its own delegated workers must
    draw from disjoint quota. A Gemini orchestrator delegating to Gemini workers competes with
    itself — the more it delegates, the faster it rate-limits the pool doing the work."""

    def _client(self, monkeypatch) -> LLMClient:
        monkeypatch.setenv("TOKENROUTER_API_KEY", "glm-1")
        monkeypatch.setenv("GEMINI_API_KEY", "gem-1")
        return LLMClient()

    def test_glm_reports_the_ultra_heavy_tier(self, monkeypatch):
        # tier_of is what jobs.py uses to pick a rate-limited orchestrator's failover ring. While
        # this said "balanced", GLM resolved the balanced ring and walked straight onto Gemini.
        client = self._client(monkeypatch)
        assert client.tier_of("tokenrouter/z-ai/glm-5.3-free") == "ultra_heavy"

    def test_the_orchestrator_ring_never_contains_a_worker_model(self, monkeypatch):
        client = self._client(monkeypatch)
        orchestrator = client.failover_ring("ultra_heavy")
        workers = client.worker_ring()
        assert orchestrator, "ultra_heavy must have a ring"
        assert workers, "workers must exist"
        assert not (set(orchestrator) & set(workers)), (
            f"orchestrator and worker pools overlap: {set(orchestrator) & set(workers)} — "
            "they would compete for the same quota"
        )

    def test_the_worker_ring_stays_inside_the_gemini_family(self, monkeypatch):
        client = self._client(monkeypatch)
        ring = client.worker_ring()
        assert ring
        assert all(m.startswith("gemini/") for m in ring), ring

    def test_a_rate_limited_glm_orchestrator_does_not_fall_back_onto_gemini(self, monkeypatch):
        client = self._client(monkeypatch)
        ring = client.failover_ring(client.tier_of("tokenrouter/z-ai/glm-5.3-free"))
        assert not any(m.startswith("gemini/") for m in ring), ring

    def test_build_roles_route_to_the_orchestrator_tier(self, monkeypatch):
        client = self._client(monkeypatch)
        assert client.model_for_task("coder") == "tokenrouter/z-ai/glm-5.3-free"

    def test_the_default_model_is_the_orchestrator(self, monkeypatch):
        # default_model is what the UI picker starts on, and the picker's value is what /chat/agent
        # runs a job with — it overrides tier routing completely. So this, not TASK_TIER["coder"],
        # is what decides which model actually orchestrates real work. While "chat" pointed at the
        # balanced tier every job ran on Gemini despite architecture/coder/planner all naming
        # ultra_heavy, which also meant the orchestrator was competing with its own workers for
        # Gemini quota.
        client = self._client(monkeypatch)
        assert client.default_model == "tokenrouter/z-ai/glm-5.3-free"
        assert client.model_for_task("chat") == client.default_model

    def test_multiple_orchestrator_keys_round_robin_and_wrap(self, monkeypatch):
        monkeypatch.setenv("TOKENROUTER_API_KEY", "glm-1")
        monkeypatch.setenv("TOKENROUTER_API_KEY_2", "glm-2")
        monkeypatch.setenv("TOKENROUTER_API_KEY_3", "glm-3")
        monkeypatch.setenv("GEMINI_API_KEY", "gem-1")
        client = LLMClient()
        model = "tokenrouter/z-ai/glm-5.3-free"

        seen = [client._kwargs(model)["api_key"]]
        while client._advance_key(model):
            seen.append(client._kwargs(model)["api_key"])
        assert seen == ["glm-1", "glm-2", "glm-3"]

        # Wrapping to a new lap must return to key 1 — otherwise a wrapped orchestrator ring would
        # retry only the last, already-exhausted key forever.
        client.reset_keys([model])
        assert client._kwargs(model)["api_key"] == "glm-1"

    def test_each_orchestrator_key_gets_its_own_rate_bucket(self, monkeypatch):
        # Independent keys are independent projects with independent quota; metering them as one
        # model-wide bucket would serialise all three behind a single limit.
        monkeypatch.setenv("TOKENROUTER_API_KEY", "glm-1")
        monkeypatch.setenv("TOKENROUTER_API_KEY_2", "glm-2")
        client = LLMClient()
        model = "tokenrouter/z-ai/glm-5.3-free"
        client._limiter.wait(model, 0)
        client._limiter.wait(model, 1)
        assert f"{model}#0" in client._limiter._calls
        assert f"{model}#1" in client._limiter._calls

    def test_routing_still_works_with_no_glm_key_configured(self, monkeypatch):
        # ultra_heavy is a preference, not a hard dependency - model_for_task must fall through.
        monkeypatch.delenv("TOKENROUTER_API_KEY", raising=False)
        monkeypatch.setenv("GEMINI_API_KEY", "gem-1")
        client = LLMClient()
        assert client.model_for_task("coder").startswith("gemini/")

    def test_reset_keys_clears_sticky_rotation(self, monkeypatch):
        monkeypatch.setenv("TOKENROUTER_API_KEY", "k1")
        monkeypatch.setenv("TOKENROUTER_API_KEY_2", "k2")
        client = LLMClient()
        model = "tokenrouter/z-ai/glm-5.3-free"
        assert client._advance_key(model) is True
        assert client._kwargs(model)["api_key"] == "k2"
        client.reset_keys([model])
        assert client._kwargs(model)["api_key"] == "k1"


class TestDelegateBuildRegistration:
    def test_exposed_on_a_real_build_prompt(self):
        groups = classify_intent("Build a production-quality dashboard application with five views")
        names = {t["function"]["name"] for t in tools_for_groups(groups)}
        assert "delegate_build" in names

    def test_lives_in_the_orchestration_group(self):
        assert "delegate_build" in tool_groups["orchestration"]

    def test_triggers_a_graph_reindex_because_it_writes_files(self):
        assert "delegate_build" in GRAPH_DIRTYING_TOOLS

    def test_workers_cannot_delegate_recursively(self):
        assert "delegate_build" not in _EXECUTOR_TOOL_NAMES
        assert "delegate_task" not in _EXECUTOR_TOOL_NAMES
