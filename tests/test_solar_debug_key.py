"""Tests for the isolated Upstage Solar Pro debug key in backend/agents/llm.py.

Verifies:
1. UPSTAGE_DEBUG_API_KEY is recognized under the 'upstage_debug' provider.
2. It does NOT combine with UPSTAGE_API_KEY into a shared key rotation pool.
3. 'upstage_debug/solar-pro4' is in the 'debug' tier, so it is never automatically
   picked up by model_for_task() or failover rings.
4. _kwargs routes to UPSTAGE_API_BASE using UPSTAGE_DEBUG_API_KEY.
"""

from unittest.mock import MagicMock, patch
import os
import pytest

from backend.agents.llm import LLMClient, MODEL_REGISTRY, UPSTAGE_API_BASE


def test_upstage_debug_key_is_isolated_and_not_pooled(monkeypatch):
    monkeypatch.setenv("UPSTAGE_API_KEY", "primary-upstage-key")
    monkeypatch.setenv("UPSTAGE_DEBUG_API_KEY", "debug-upstage-key")
    monkeypatch.delenv("UPSTAGE_API_KEY_2", raising=False)

    client = LLMClient()

    # Neither provider should have multiple keys registered in _provider_keys
    assert "upstage" not in client._provider_keys
    assert "upstage_debug" not in client._provider_keys

    # Both models should be available
    assert "upstage/solar-pro4" in client.available
    assert "upstage_debug/solar-pro4" in client.available

    # Check tier isolation: debug tier must not be in normal orchestrator tiers
    debug_tier = client.tier_of("upstage_debug/solar-pro4")
    assert debug_tier == "debug"

    # Ensure model_for_task never routes to the debug model
    for task in ("chat", "coder", "planner", "architecture", "docs", "retrieval"):
        assert client.model_for_task(task) != "upstage_debug/solar-pro4"


def test_upstage_debug_kwargs_routing(monkeypatch):
    monkeypatch.setenv("UPSTAGE_API_KEY", "primary-upstage-key")
    monkeypatch.setenv("UPSTAGE_DEBUG_API_KEY", "debug-upstage-key")

    client = LLMClient()

    # Primary model routes with primary key
    kwargs_primary = client._kwargs("upstage/solar-pro4")
    assert kwargs_primary["model"] == "openai/solar-pro4"
    assert kwargs_primary["api_base"] == UPSTAGE_API_BASE
    assert kwargs_primary["api_key"] == "primary-upstage-key"

    # Debug model routes with debug key
    kwargs_debug = client._kwargs("upstage_debug/solar-pro4")
    assert kwargs_debug["model"] == "openai/solar-pro4"
    assert kwargs_debug["api_base"] == UPSTAGE_API_BASE
    assert kwargs_debug["api_key"] == "debug-upstage-key"


@patch("backend.agents.llm.litellm.completion")
def test_upstage_debug_completion_call(mock_completion, monkeypatch):
    monkeypatch.setenv("UPSTAGE_DEBUG_API_KEY", "debug-upstage-key")

    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = "solar pro debug response"
    mock_resp.choices[0].message.tool_calls = None
    mock_resp.usage.prompt_tokens = 10
    mock_resp.usage.completion_tokens = 5
    mock_resp.usage.completion_tokens_details = None
    mock_completion.return_value = mock_resp

    client = LLMClient()
    res = client.complete(
        messages=[{"role": "user", "content": "test debug prompt"}],
        model="upstage_debug/solar-pro4",
    )

    assert res == "solar pro debug response"
    called_kwargs = mock_completion.call_args.kwargs
    assert called_kwargs["model"] == "openai/solar-pro4"
    assert called_kwargs["api_base"] == UPSTAGE_API_BASE
    assert called_kwargs["api_key"] == "debug-upstage-key"
