"""Tests for the generate_with_qwen tool (backend/agents/tools.py) and the "content" tier
isolation it depends on (backend/agents/llm.py's MODEL_REGISTRY/model_for_task).

qwen-plus-character has NO function/tool-calling support (confirmed via Alibaba's own docs, every
region) — the whole point of this tool is that it's the ONLY way that model is ever reachable: a
plain llm.complete() call with no tools=, never the model driving a job's tool-calling loop. These
tests mock llm entirely — no real DashScope call, per the user's explicit "don't spend any of this
budget testing it" instruction.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.agents.llm import MODEL_REGISTRY, _TIER_ORDER, LLMClient
from backend.agents.tools import TOOL_SCHEMAS, _QWEN_CONTENT_MODEL, execute_tool


class TestContentTierIsolation:
    """The model must be registered (so key/provider lookup works) but structurally unreachable by
    any of the normal auto-routing paths — it would break a job on its first tool call."""

    def test_registered_with_a_tier_no_normal_routing_path_uses(self):
        assert MODEL_REGISTRY[_QWEN_CONTENT_MODEL][2] == "content"

    def test_never_appears_in_any_real_tier_order_list(self):
        for tier in ("heavy", "balanced", "light"):
            assert _QWEN_CONTENT_MODEL not in _TIER_ORDER[tier]

    def test_model_for_task_never_returns_it_even_as_last_resort(self, monkeypatch):
        # Simulate every other provider being unavailable except dashscope - the one scenario
        # where the old `self.available[0]` fallback could have handed this back as if it were a
        # normal orchestrating model.
        monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
        for env_var in [
            "NVIDIA_API_KEY", "GROQ_API_KEY", "GEMINI_API_KEY", "GEMINI_API_KEY_2", "ZAI_API_KEY",
            "OPENROUTER_API_KEY", "TOKENROUTER_API_KEY", "AWS_BEARER_TOKEN_BEDROCK",
            "CEREBRAS_API_KEY", "MISTRAL_API_KEY",
        ]:
            monkeypatch.delenv(env_var, raising=False)
        monkeypatch.setenv("OLLAMA_API_BASE", "")  # also drop the local fallback

        client = LLMClient()
        assert client.available == [_QWEN_CONTENT_MODEL]
        assert client.model_for_task("chat") != _QWEN_CONTENT_MODEL


class TestToolSchema:
    def test_generate_with_qwen_is_a_registered_tool(self):
        names = [t["function"]["name"] for t in TOOL_SCHEMAS]
        assert "generate_with_qwen" in names

    def test_schema_requires_a_brief(self):
        schema = next(t for t in TOOL_SCHEMAS if t["function"]["name"] == "generate_with_qwen")
        assert schema["function"]["parameters"]["required"] == ["brief"]


class TestExecuteToolDispatch:
    def test_calls_llm_complete_with_the_content_model_and_no_tools_kwarg(self):
        fake_llm = MagicMock()
        fake_llm.available = [_QWEN_CONTENT_MODEL]
        fake_llm.complete.return_value = "generated code here"

        result = execute_tool(
            "generate_with_qwen", {"brief": "write a hello world function"}, "demo-repo", llm=fake_llm,
        )

        assert result == "generated code here"
        fake_llm.complete.assert_called_once()
        call_args, call_kwargs = fake_llm.complete.call_args
        assert call_kwargs["model"] == _QWEN_CONTENT_MODEL
        assert "tools" not in call_kwargs  # this model can't accept tools at all

    def test_no_llm_client_returns_graceful_text_not_a_crash(self):
        result = execute_tool("generate_with_qwen", {"brief": "anything"}, "demo-repo", llm=None)
        assert "unavailable" in result.lower()

    def test_missing_dashscope_key_returns_graceful_text_not_a_crash(self):
        fake_llm = MagicMock()
        fake_llm.available = []  # DASHSCOPE_API_KEY not configured this session
        result = execute_tool("generate_with_qwen", {"brief": "anything"}, "demo-repo", llm=fake_llm)
        assert "unavailable" in result.lower()
        fake_llm.complete.assert_not_called()

    def test_llm_call_failure_is_reported_not_raised(self):
        fake_llm = MagicMock()
        fake_llm.available = [_QWEN_CONTENT_MODEL]
        fake_llm.complete.side_effect = RuntimeError("quota exhausted")

        result = execute_tool("generate_with_qwen", {"brief": "anything"}, "demo-repo", llm=fake_llm)

        assert "quota exhausted" in result
        assert "write the content yourself" in result.lower()
