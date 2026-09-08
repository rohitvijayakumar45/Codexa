"""Two fixes that only look unrelated.

1. GLM (routed as tokenrouter/) never participated in per-model key rotation: _kwargs special-cased
   the tokenrouter/ and zai/ prefixes and returned early with a hardcoded os.getenv(...), so adding
   TOKENROUTER_API_KEY_2 did nothing at all and one key's quota was the hard ceiling for every GLM
   call in the system.

2. delegate_task (heavy model plans, a light/fast model executes the mechanical writes, only a short
   summary comes back) was unreachable: its "orchestration" group only matched wording like
   "delegate" / "every file" / "entire app". A real overnight full-stack build phrased as "Build a
   production-quality application called APEX ... 5 views" matched none of those, so the tool was
   never exposed — 0 delegate_task calls across 275 rounds while the orchestrator hand-wrote every
   file itself, ballooning its own context until compaction started eating the design conventions.

Both are about the same underlying thing: the expensive path was taken because the cheap one was
silently unavailable.
"""

from unittest.mock import MagicMock, patch

from backend.agents.llm import LLMClient
from backend.agents.tools import classify_intent, tool_groups, tools_for_groups


class TestTokenRouterKeyRotation:
    def _client(self, monkeypatch, keys: list[str]) -> LLMClient:
        monkeypatch.setenv("TOKENROUTER_API_KEY", keys[0])
        for i, k in enumerate(keys[1:], start=2):
            monkeypatch.setenv(f"TOKENROUTER_API_KEY_{i}", k)
        return LLMClient()

    def test_multiple_tokenrouter_keys_are_registered(self, monkeypatch):
        client = self._client(monkeypatch, ["k1", "k2", "k3", "k4"])
        assert client._provider_keys["tokenrouter"] == ["k1", "k2", "k3", "k4"]

    def test_kwargs_uses_the_rotating_key_not_the_raw_env_var(self, monkeypatch):
        client = self._client(monkeypatch, ["k1", "k2"])
        model = "tokenrouter/z-ai/glm-5.3-free"
        assert client._kwargs(model)["api_key"] == "k1"
        assert client._advance_key(model) is True
        # The whole point: this used to stay "k1" forever because the tokenrouter/ branch never
        # consulted _current_key at all.
        assert client._kwargs(model)["api_key"] == "k2"

    def test_rotation_walks_every_configured_key_then_stops(self, monkeypatch):
        client = self._client(monkeypatch, ["k1", "k2", "k3", "k4"])
        model = "tokenrouter/z-ai/glm-5.3-free"
        seen = [client._kwargs(model)["api_key"]]
        while client._advance_key(model):
            seen.append(client._kwargs(model)["api_key"])
        assert seen == ["k1", "k2", "k3", "k4"]

    def test_openai_compat_routing_is_preserved(self, monkeypatch):
        client = self._client(monkeypatch, ["k1", "k2"])
        kw = client._kwargs("tokenrouter/z-ai/glm-5.3-free")
        assert kw["model"] == "openai/z-ai/glm-5.3-free"
        assert "tokenrouter" in kw["api_base"]

    def test_single_key_still_falls_back_to_the_env_var(self, monkeypatch):
        # With only one key configured _provider_keys has no entry at all (nothing to rotate to),
        # so _current_key returns None and the env var must still be used - otherwise this fix
        # would break every single-key GLM setup.
        monkeypatch.delenv("TOKENROUTER_API_KEY_2", raising=False)
        monkeypatch.setenv("TOKENROUTER_API_KEY", "only-key")
        client = LLMClient()
        assert client._kwargs("tokenrouter/z-ai/glm-5.3-free")["api_key"] == "only-key"

    def test_unregistered_prefix_model_resolves_its_own_provider(self, monkeypatch):
        # zai/ models aren't in MODEL_REGISTRY; _provider_of used to fall back to "nvidia" for them,
        # which would have handed out an unrelated provider's key once rotation was wired in.
        monkeypatch.setenv("ZAI_API_KEY", "z1")
        client = LLMClient()
        assert client._provider_of("zai/glm-4.6") == "zai"


class TestDelegationIsActuallyReachable:
    def test_a_real_build_prompt_exposes_delegate_task(self):
        # The exact shape that got 0 delegate_task calls in 275 rounds - no "delegate", no
        # "every file", no "entire app" anywhere in it.
        prompt = (
            "Build a production-quality full-stack web application called APEX with a command "
            "surface, an orbit graph, a flow pipeline, a pulse telemetry view and a memory timeline."
        )
        groups = classify_intent(prompt)
        assert "orchestration" in groups
        names = {t["function"]["name"] for t in tools_for_groups(groups)}
        assert "delegate_task" in names

    def test_the_old_keyword_path_still_works(self):
        assert "orchestration" in classify_intent("delegate this and scaffold all the files")

    def test_plain_conversation_gets_no_tools_at_all(self):
        assert classify_intent("hey") == []

    def test_a_pure_question_does_not_pull_in_orchestration(self):
        # An EXPLAIN-shaped question shouldn't hand the model a file-writing delegate.
        groups = classify_intent("what is the difference between a mutex and a semaphore")
        assert "orchestration" not in groups

    def test_orchestration_group_actually_contains_the_tool(self):
        assert "delegate_task" in tool_groups["orchestration"]


class TestDelegationRoutesWritesToTheLightModel:
    def test_delegate_task_executes_against_the_light_tier_model(self):
        """The 'GLM thinks, Gemini writes' split, end to end: the worker model is chosen from the
        light tier (not the caller's heavy model), it is the one that issues write_file, and the
        caller gets back a short summary rather than the file's full content."""
        from backend.agents.tools import _delegate_task

        llm = MagicMock()
        llm.models_for_tier.return_value = ["gemini/gemini-3.7-flash"]

        tc = MagicMock()
        tc.id = "tc1"
        tc.function.name = "write_file"
        tc.function.arguments = '{"path": "src/App.tsx", "content": "export const App = () => null;"}'
        first = MagicMock()
        first.content = ""
        first.tool_calls = [tc]
        done = MagicMock()
        done.content = "Wrote App.tsx."
        done.tool_calls = None
        llm.complete_message.side_effect = [(first, {}), (done, {})]

        with patch("backend.agents.tools.execute_tool", return_value="Wrote 31 bytes to src/App.tsx.") as ex:
            out = _delegate_task("create src/App.tsx", "demo-repo", llm=llm, graph=None, store=None)

        assert llm.complete_message.call_args_list[0].kwargs["model"] == "gemini/gemini-3.7-flash"
        assert ex.call_args.args[0] == "write_file"
        assert "write_file" in out and "src/App.tsx" in out
        # The caller's context must not grow by the file body it delegated away.
        assert "export const App" not in out
