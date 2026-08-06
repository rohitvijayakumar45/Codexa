import json
import logging
from unittest.mock import MagicMock, patch

import pytest

from backend.agents.llm import LLMClient


def test_llm_client_initialization_fails_without_api_key_for_nim(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "nvidia_nim")
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.setenv("LLM_FALLBACK_TO_LOCAL", "false")

    with pytest.raises(ValueError, match="NVIDIA_API_KEY is required when LLM_PROVIDER=nvidia_nim"):
        LLMClient()


def test_llm_client_initialization_falls_back_to_local(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "nvidia_nim")
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.setenv("LLM_FALLBACK_TO_LOCAL", "true")

    client = LLMClient()
    assert client.provider == "local"
    assert client.default_model == "ollama/qwen3:14b"


def test_llm_client_initialization_local(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "local")
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", "http://localhost:9999/v1")
    monkeypatch.setenv("LOCAL_LLM_DEFAULT_MODEL", "custom-model")

    client = LLMClient()
    assert client.provider == "local"
    import os
    assert os.getenv("OLLAMA_API_BASE") == "http://localhost:9999/v1"
    assert client.default_model == "custom-model"


@patch("backend.agents.llm.litellm.completion")
def test_llm_client_routing_and_overrides(mock_completion, monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "local")
    overrides = {"planner": "planner-model-v2"}
    monkeypatch.setenv("AGENT_MODEL_OVERRIDES", json.dumps(overrides))

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "generated text"
    mock_response.usage.prompt_tokens = 10
    mock_response.usage.completion_tokens = 20
    mock_completion.return_value = mock_response

    client = LLMClient()
    
    # Generate with overridden role
    result = client.generate(agent_role="planner", prompt="hello planner")
    assert result == "generated text"
    mock_completion.assert_called_with(
        model="planner-model-v2",
        messages=[{"role": "user", "content": "hello planner"}],
        fallbacks=[]
    )

    # Generate with non-overridden role (should use default)
    mock_completion.reset_mock()
    result = client.generate(agent_role="coder", prompt="hello coder")
    assert result == "generated text"
    mock_completion.assert_called_with(
        model="ollama/qwen3:14b",
        messages=[{"role": "user", "content": "hello coder"}],
        fallbacks=[]
    )


@patch("backend.agents.llm.litellm.completion")
def test_llm_client_logging(mock_completion, caplog, monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "nvidia_nim")
    monkeypatch.setenv("NVIDIA_API_KEY", "fake_key")
    monkeypatch.setenv("NVIDIA_NIM_DEFAULT_MODEL", "nvidia_nim/meta/llama3-70b-instruct")

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "generated text"
    mock_response.usage.prompt_tokens = 15
    mock_response.usage.completion_tokens = 25
    mock_completion.return_value = mock_response

    client = LLMClient()
    
    with caplog.at_level(logging.INFO):
        client.generate(agent_role="research", prompt="hello research")

    # Assert logging record
    log_text = caplog.text
    assert "LLM usage" in log_text
    assert "provider=nvidia_nim" in log_text
    assert "model=nvidia_nim/meta/llama3-70b-instruct" in log_text
    assert "prompt_tokens=15" in log_text
    assert "completion_tokens=25" in log_text


@patch("backend.agents.llm.litellm.completion")
def test_agent_call_site_uses_llm_transparently(mock_completion, monkeypatch) -> None:
    # This verifies that the PlannerService can run its `synthesize_plan` using the LLMClient
    monkeypatch.setenv("LLM_PROVIDER", "local")
    
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "planner synthesized output"
    mock_completion.return_value = mock_response

    client = LLMClient()
    from backend.agents.planner import PlannerService
    planner = PlannerService(repository=MagicMock(), event_writer=MagicMock(), llm=client)
    
    result = planner.synthesize_plan("create a plan")
    assert result == "planner synthesized output"
    mock_completion.assert_called_with(
        model="ollama/qwen3:14b",
        messages=[{"role": "user", "content": "create a plan"}],
        fallbacks=[]
    )
