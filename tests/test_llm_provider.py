"""LLMClient initialization, routing, overrides and usage recording.

Rewritten against the current architecture. The previous version of this file tested a design that
no longer exists — a single LLM_PROVIDER with an LLM_FALLBACK_TO_LOCAL escape hatch, LOCAL_LLM_*
env vars, an ollama/qwen3:14b default and a `fallbacks=[]` kwarg on every call — and had been
failing for long enough to be treated as an accepted "baseline". Six permanently-red tests teach a
team to read red as normal, which is how a real regression hides in plain sight; they are rewritten
here rather than deleted so the behaviour they cared about (does it initialise sanely, does routing
respect overrides, is usage recorded, do agent call sites work through the client) keeps coverage
under the model-registry design that actually shipped.

Today's shape: no single provider and no hard failure on a missing key — a model is simply offered
only when its provider's key is configured, routing picks the best AVAILABLE model per task tier,
and the local Ollama model is the always-present floor.
"""

import json
import logging
from unittest.mock import MagicMock, patch

from backend.agents.llm import MODEL_REGISTRY, LLMClient

_ALL_PROVIDER_KEYS = [
    "NVIDIA_API_KEY", "NVIDIA_NIM_API_KEY", "GROQ_API_KEY", "GEMINI_API_KEY", "ZAI_API_KEY",
    "OPENROUTER_API_KEY", "TOKENROUTER_API_KEY", "AWS_BEARER_TOKEN_BEDROCK", "CEREBRAS_API_KEY",
    "MISTRAL_API_KEY", "DASHSCOPE_API_KEY",
]


def _clear_hosted_providers(monkeypatch) -> None:
    """Strip every hosted provider key (including the _2/_3 rotation slots) so only the local,
    keyless Ollama entry survives — the modern equivalent of the old 'fall back to local' path."""
    for var in _ALL_PROVIDER_KEYS:
        monkeypatch.delenv(var, raising=False)
        for n in range(2, 6):
            monkeypatch.delenv(f"{var}_{n}", raising=False)
    monkeypatch.delenv("LLM_DEFAULT_MODEL", raising=False)
    monkeypatch.delenv("NVIDIA_NIM_DEFAULT_MODEL", raising=False)


class TestInitialization:
    def test_a_provider_without_a_key_is_simply_not_offered(self, monkeypatch):
        # Replaces a test asserting LLMClient() RAISES when NVIDIA_API_KEY is missing. Raising on a
        # single absent key is wrong for a multi-provider client: one unconfigured provider must
        # not stop the other nine from working.
        _clear_hosted_providers(monkeypatch)
        client = LLMClient()
        assert not any(m.startswith("nvidia_nim/") for m in client.available)

    def test_a_configured_provider_is_offered(self, monkeypatch):
        _clear_hosted_providers(monkeypatch)
        monkeypatch.setenv("GEMINI_API_KEY", "gem-1")
        client = LLMClient()
        assert any(m.startswith("gemini/") for m in client.available)

    def test_the_local_model_is_the_always_available_floor(self, monkeypatch):
        # Replaces "falls back to local". The local daemon needs no key, so with every hosted
        # provider stripped the client must still resolve to a usable model rather than dying.
        _clear_hosted_providers(monkeypatch)
        client = LLMClient()
        assert "ollama_chat/josiefied-qwen3:latest" in client.available
        assert client.default_model in client.available

    def test_ollama_base_url_is_defaulted_for_a_keyless_local_daemon(self, monkeypatch):
        monkeypatch.delenv("OLLAMA_API_BASE", raising=False)
        LLMClient()
        import os

        assert os.getenv("OLLAMA_API_BASE") == "http://localhost:11434"

    def test_an_explicit_default_model_is_honoured_when_available(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "gem-1")
        monkeypatch.setenv("LLM_DEFAULT_MODEL", "gemini/gemini-2.5-flash")
        assert LLMClient().default_model == "gemini/gemini-2.5-flash"

    def test_an_unavailable_default_model_is_ignored_rather_than_trusted(self, monkeypatch):
        # A stale LLM_DEFAULT_MODEL pointing at an unconfigured provider must not become the
        # default — every call would fail on a missing key.
        _clear_hosted_providers(monkeypatch)
        monkeypatch.setenv("LLM_DEFAULT_MODEL", "groq/openai/gpt-oss-120b")
        client = LLMClient()
        assert client.default_model != "groq/openai/gpt-oss-120b"
        assert client.default_model in client.available


class TestRoutingAndOverrides:
    @patch("backend.agents.llm.litellm.completion")
    def test_an_agent_override_wins_over_tier_routing(self, mock_completion, monkeypatch):
        _clear_hosted_providers(monkeypatch)
        monkeypatch.setenv("GEMINI_API_KEY", "gem-1")
        monkeypatch.setenv("AGENT_MODEL_OVERRIDES", json.dumps({"planner": "gemini/gemini-2.5-flash"}))
        mock_completion.return_value = _fake_response("generated text")

        client = LLMClient()
        assert client.generate(agent_role="planner", prompt="hello planner") == "generated text"
        assert mock_completion.call_args.kwargs["model"] == "gemini/gemini-2.5-flash"

    @patch("backend.agents.llm.litellm.completion")
    def test_a_role_without_an_override_routes_by_task_tier(self, mock_completion, monkeypatch):
        # _clear_hosted_providers is load-bearing, not tidiness: any test importing backend.main
        # triggers load_dotenv(), which makes the developer's REAL provider keys visible and can
        # silently re-route this call to a different tier. Pinning the environment is what makes
        # the assertion mean the same thing alone and in the full suite.
        _clear_hosted_providers(monkeypatch)
        monkeypatch.setenv("GEMINI_API_KEY", "gem-1")
        monkeypatch.setenv("AGENT_MODEL_OVERRIDES", json.dumps({"planner": "gemini/gemini-2.5-flash"}))
        mock_completion.return_value = _fake_response("generated text")

        client = LLMClient()
        client.generate(agent_role="coder", prompt="hello coder")
        used = mock_completion.call_args.kwargs["model"]
        assert used != "gemini/gemini-2.5-flash"
        assert used == client.model_for_task("coder")

    def test_malformed_overrides_json_degrades_instead_of_crashing_startup(self, monkeypatch):
        monkeypatch.setenv("AGENT_MODEL_OVERRIDES", "{not valid json")
        assert LLMClient().agent_overrides == {}

    def test_every_routed_model_is_registered_and_available(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "gem-1")
        client = LLMClient()
        for task in ("architecture", "coder", "planner", "docs", "chat", "retrieval"):
            model = client.model_for_task(task)
            assert model in MODEL_REGISTRY, f"{task} routed to unregistered {model}"
            assert model in client.available, f"{task} routed to unavailable {model}"


class TestUsageRecording:
    @patch("backend.agents.llm.litellm.completion")
    def test_real_provider_reported_usage_is_recorded(self, mock_completion, monkeypatch):
        # Replaces a test asserting a specific "LLM usage provider=... prompt_tokens=..." log line.
        # Usage is now structured data in UsageTracker (the /usage dashboard reads it), so assert on
        # the record rather than on log formatting.
        monkeypatch.setenv("GEMINI_API_KEY", "gem-1")
        mock_completion.return_value = _fake_response("generated text", prompt=15, completion=25)

        client = LLMClient()
        client.generate(agent_role="research", prompt="hello research")

        records = client.usage.records()
        assert records, "a completed call must leave a usage record"
        latest = records[0]
        assert latest.prompt_tokens == 15
        assert latest.completion_tokens == 25
        assert latest.agent == "research"
        assert latest.provider == "gemini"

    @patch("backend.agents.llm.litellm.completion")
    def test_a_zero_token_response_records_nothing(self, mock_completion, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "gem-1")
        mock_completion.return_value = _fake_response("", prompt=0, completion=0)

        client = LLMClient()
        before = len(client.usage.records())
        client.generate(agent_role="research", prompt="x")
        assert len(client.usage.records()) == before

    @patch("backend.agents.llm.litellm.completion")
    def test_client_startup_is_logged_for_operator_visibility(self, mock_completion, caplog, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "gem-1")
        with caplog.at_level(logging.INFO, logger="backend.agents.llm"):
            client = LLMClient()
        assert "LLM ready" in caplog.text
        assert client.default_model in caplog.text


class TestAgentCallSites:
    @patch("backend.agents.llm.litellm.completion")
    def test_planner_runs_through_the_client_transparently(self, mock_completion, monkeypatch):
        _clear_hosted_providers(monkeypatch)
        monkeypatch.setenv("GEMINI_API_KEY", "gem-1")
        mock_completion.return_value = _fake_response("planner synthesized output")

        client = LLMClient()
        from backend.agents.planner import PlannerService

        planner = PlannerService(repository=MagicMock(), event_writer=MagicMock(), llm=client)
        assert planner.synthesize_plan("create a plan") == "planner synthesized output"
        assert mock_completion.call_args.kwargs["messages"] == [
            {"role": "user", "content": "create a plan"}
        ]
        assert mock_completion.call_args.kwargs["model"] in client.available


def _fake_response(text: str, *, prompt: int = 10, completion: int = 20) -> MagicMock:
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = text
    resp.usage.prompt_tokens = prompt
    resp.usage.completion_tokens = completion
    resp.usage.completion_tokens_details = None
    return resp
