"""Tests for per-provider API-key failover in backend/agents/llm.py's LLMClient.

A provider with a second key configured (PROVIDER_ENV_VAR_2, e.g. GEMINI_API_KEY_2 — an
independent account, not a quota pool shared with the primary) fails over to it on a
RateLimitError, sticky (stays on the new key rather than flipping back every call). The point
under test isn't just "it retries" — it's that a stream already partway through never gets
silently restarted (which would duplicate/garble what the caller already received), while a
call that never got a single chunk out is retried fully transparently, so no real work is lost
either way.
"""

from unittest.mock import MagicMock, patch

import litellm
import pytest

from backend.agents.llm import LLMClient, is_rate_limit_error


def _rate_limit_error(model: str = "gemini/gemini-3.7-flash") -> litellm.RateLimitError:
    return litellm.RateLimitError(message="rate limited", llm_provider="gemini", model=model)


def _mid_stream_fallback_wrapping_rate_limit(model: str = "gemini/gemini-3.7-flash"):
    # Reproduces a REAL observed failure: litellm.completion(stream=True) raised this wrapper
    # class (a ServiceUnavailableError subclass, NOT RateLimitError) around a genuine 429 that
    # surfaced mid-stream. A bare `except litellm.RateLimitError` never catches this at all.
    inner = _rate_limit_error(model)
    return litellm.exceptions.MidStreamFallbackError(
        message="quota exceeded", model=model, llm_provider="gemini", original_exception=inner,
    )


def _mid_stream_fallback_wrapping_something_else(model: str = "gemini/gemini-3.7-flash"):
    # A genuine outage, NOT a rate limit - must never trigger key failover (failing over to a
    # second key does nothing for a real service outage and just burns the sticky rotation).
    inner = litellm.APIConnectionError(message="connection reset", llm_provider="gemini", model=model)
    return litellm.exceptions.MidStreamFallbackError(
        message="connection reset", model=model, llm_provider="gemini", original_exception=inner,
    )


def _fake_response(text: str = "ok") -> MagicMock:
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = text
    resp.choices[0].message.tool_calls = None
    resp.usage.prompt_tokens = 1
    resp.usage.completion_tokens = 1
    resp.usage.completion_tokens_details = None
    return resp


def _fake_chunk(text: str) -> MagicMock:
    chunk = MagicMock()
    chunk.choices = [MagicMock()]
    chunk.choices[0].delta.content = text
    chunk.choices[0].delta.reasoning_content = None
    return chunk


def _client_with_two_gemini_keys(monkeypatch) -> LLMClient:
    monkeypatch.setenv("GEMINI_API_KEY", "primary-key")
    monkeypatch.setenv("GEMINI_API_KEY_2", "secondary-key")
    # Clearing the higher slots is what makes "two keys" actually mean two. Any test importing
    # backend.main runs load_dotenv(), so the developer's real GEMINI_API_KEY_3/_4 become visible
    # and this client silently registers four keys — which broke three assertions here the moment
    # two more keys were added to .env. A fixture that only sets what it needs, without clearing
    # what it does not, is a fixture whose meaning changes when someone edits their environment.
    for n in range(3, 8):
        monkeypatch.delenv(f"GEMINI_API_KEY_{n}", raising=False)
    return LLMClient()


class TestKeyRegistration:
    def test_two_keys_configured_are_both_tracked(self, monkeypatch):
        client = _client_with_two_gemini_keys(monkeypatch)
        assert client._provider_keys["gemini"] == ["primary-key", "secondary-key"]
        # The rotation index is per-model (see llm.py's __init__ for why - Google tracks quota per
        # model per key, not pooled across a provider's models), so nothing is pre-populated here;
        # a model with no entry yet defaults to key 0 via .get(model, 0).
        assert client._active_key_index.get("gemini/gemini-3.7-flash", 0) == 0

    def test_single_key_provider_gets_no_failover_entry(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "only-key")
        monkeypatch.delenv("GEMINI_API_KEY_2", raising=False)
        client = LLMClient()
        assert "groq" not in client._provider_keys  # only one key - nothing to fail over to

    def test_kwargs_uses_the_active_key(self, monkeypatch):
        client = _client_with_two_gemini_keys(monkeypatch)
        assert client._kwargs("gemini/gemini-3.7-flash")["api_key"] == "primary-key"

    def test_advance_key_moves_to_the_next_one_and_is_sticky(self, monkeypatch):
        client = _client_with_two_gemini_keys(monkeypatch)
        assert client._advance_key("gemini/gemini-3.7-flash") is True
        assert client._kwargs("gemini/gemini-3.7-flash")["api_key"] == "secondary-key"
        # No third key configured - nothing left to advance to.
        assert client._advance_key("gemini/gemini-3.7-flash") is False

    def test_advance_key_is_tracked_per_model_not_pooled_across_a_providers_models(self, monkeypatch):
        # The real motivating bug: a gemini-3.8-flash rate limit used to advance a SHARED
        # provider-level index, so a later gemini-3.7-flash call skipped key 1 entirely - even
        # though Google tracks each model's quota separately per key. 3.8 exhausting its keys must
        # leave 3.7 untouched, starting fresh at key 0.
        client = _client_with_two_gemini_keys(monkeypatch)
        assert client._advance_key("gemini/gemini-3.8-flash") is True
        assert client._kwargs("gemini/gemini-3.8-flash")["api_key"] == "secondary-key"
        assert client._kwargs("gemini/gemini-3.7-flash")["api_key"] == "primary-key"

    def test_kwargs_never_sets_api_key_for_a_single_key_provider(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "only-key")
        client = LLMClient()
        assert "api_key" not in client._kwargs("groq/openai/gpt-oss-20b")


class TestNonStreamingFailover:
    def test_complete_fails_over_transparently_on_rate_limit(self, monkeypatch):
        client = _client_with_two_gemini_keys(monkeypatch)
        with patch("backend.agents.llm.litellm.completion") as mock_completion:
            mock_completion.side_effect = [_rate_limit_error(), _fake_response("second key worked")]
            result = client.complete([{"role": "user", "content": "hi"}], model="gemini/gemini-3.7-flash")

        assert result == "second key worked"
        assert client._active_key_index.get("gemini/gemini-3.7-flash", 0) == 1  # stayed on the secondary
        assert mock_completion.call_args_list[0].kwargs["api_key"] == "primary-key"
        assert mock_completion.call_args_list[1].kwargs["api_key"] == "secondary-key"

    def test_complete_message_fails_over_too(self, monkeypatch):
        client = _client_with_two_gemini_keys(monkeypatch)
        with patch("backend.agents.llm.litellm.completion") as mock_completion:
            mock_completion.side_effect = [_rate_limit_error(), _fake_response("recovered")]
            msg, _usage = client.complete_message([{"role": "user", "content": "hi"}], model="gemini/gemini-3.7-flash")

        assert msg.content == "recovered"

    def test_raises_once_every_key_is_exhausted(self, monkeypatch):
        client = _client_with_two_gemini_keys(monkeypatch)
        with patch("backend.agents.llm.litellm.completion") as mock_completion:
            mock_completion.side_effect = [_rate_limit_error(), _rate_limit_error()]
            with pytest.raises(litellm.RateLimitError):
                client.complete([{"role": "user", "content": "hi"}], model="gemini/gemini-3.7-flash")

    def test_single_key_provider_never_retries_and_raises_immediately(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "only-key")
        client = LLMClient()
        with patch("backend.agents.llm.litellm.completion") as mock_completion:
            mock_completion.side_effect = [_rate_limit_error(model="groq/openai/gpt-oss-20b")]
            with pytest.raises(litellm.RateLimitError):
                client.complete([{"role": "user", "content": "hi"}], model="groq/openai/gpt-oss-20b")
        assert mock_completion.call_count == 1  # no key to fail over to - fails fast


class TestStreamingFailover:
    def test_rate_limited_before_any_chunk_retries_transparently(self, monkeypatch):
        client = _client_with_two_gemini_keys(monkeypatch)

        def side_effect(**kwargs):
            if kwargs.get("api_key") == "primary-key":
                raise _rate_limit_error()
            return iter([_fake_chunk("hello")])

        with patch("backend.agents.llm.litellm.completion", side_effect=side_effect):
            chunks = list(client.stream("gemini/gemini-3.7-flash", [{"role": "user", "content": "hi"}]))

        assert len(chunks) == 1
        assert chunks[0].choices[0].delta.content == "hello"
        assert client._active_key_index.get("gemini/gemini-3.7-flash", 0) == 1

    def test_rate_limited_mid_stream_is_not_silently_retried(self, monkeypatch):
        # The whole point: once the caller has already received real chunks, swallowing the error
        # and restarting from the top would hand back duplicated content. It must surface instead.
        client = _client_with_two_gemini_keys(monkeypatch)

        def generator_that_dies_partway():
            yield _fake_chunk("partial ")
            raise _rate_limit_error()

        with patch("backend.agents.llm.litellm.completion", return_value=generator_that_dies_partway()):
            gen = client.stream("gemini/gemini-3.7-flash", [{"role": "user", "content": "hi"}])
            first_chunk = next(gen)
            assert first_chunk.choices[0].delta.content == "partial "
            with pytest.raises(litellm.RateLimitError):
                next(gen)

        # No failover attempted - this is a "let the caller's own recovery handle it" case, not
        # a wasted key.
        assert client._active_key_index.get("gemini/gemini-3.7-flash", 0) == 0

    def test_stream_raises_once_every_key_is_exhausted(self, monkeypatch):
        client = _client_with_two_gemini_keys(monkeypatch)
        with patch("backend.agents.llm.litellm.completion", side_effect=_rate_limit_error()):
            with pytest.raises(litellm.RateLimitError):
                list(client.stream("gemini/gemini-3.7-flash", [{"role": "user", "content": "hi"}]))


class TestIsRateLimitError:
    """is_rate_limit_error is the fix for a real bug: a genuine Gemini 429 arrived wrapped in
    litellm.MidStreamFallbackError (a ServiceUnavailableError subclass) and every
    `except litellm.RateLimitError` in this file silently let it through with zero failover."""

    def test_bare_rate_limit_error_is_recognized(self):
        assert is_rate_limit_error(_rate_limit_error()) is True

    def test_wrapped_rate_limit_is_recognized_via_original_exception(self):
        assert is_rate_limit_error(_mid_stream_fallback_wrapping_rate_limit()) is True

    def test_wrapper_around_a_non_rate_limit_cause_is_not_recognized(self):
        assert is_rate_limit_error(_mid_stream_fallback_wrapping_something_else()) is False

    def test_unrelated_exception_is_not_recognized(self):
        assert is_rate_limit_error(ValueError("boom")) is False


class TestWrappedRateLimitFailover:
    """The exact real-world shape: a rate limit that only surfaces as
    litellm.MidStreamFallbackError, not a bare litellm.RateLimitError."""

    def test_streaming_fails_over_on_a_wrapped_rate_limit_before_any_chunk(self, monkeypatch):
        client = _client_with_two_gemini_keys(monkeypatch)

        def side_effect(**kwargs):
            if kwargs.get("api_key") == "primary-key":
                raise _mid_stream_fallback_wrapping_rate_limit()
            return iter([_fake_chunk("recovered on key 2")])

        with patch("backend.agents.llm.litellm.completion", side_effect=side_effect):
            chunks = list(client.stream("gemini/gemini-3.7-flash", [{"role": "user", "content": "hi"}]))

        assert chunks[0].choices[0].delta.content == "recovered on key 2"
        assert client._active_key_index.get("gemini/gemini-3.7-flash", 0) == 1

    def test_streaming_does_not_fail_over_on_a_wrapped_non_rate_limit_error(self, monkeypatch):
        # A real outage wrapped the same way must NOT burn a key rotation - it re-raises as-is.
        client = _client_with_two_gemini_keys(monkeypatch)
        with patch(
            "backend.agents.llm.litellm.completion",
            side_effect=_mid_stream_fallback_wrapping_something_else(),
        ):
            with pytest.raises(litellm.exceptions.MidStreamFallbackError):
                list(client.stream("gemini/gemini-3.7-flash", [{"role": "user", "content": "hi"}]))
        assert client._active_key_index.get("gemini/gemini-3.7-flash", 0) == 0

    def test_non_streaming_fails_over_on_a_wrapped_rate_limit(self, monkeypatch):
        client = _client_with_two_gemini_keys(monkeypatch)
        with patch("backend.agents.llm.litellm.completion") as mock_completion:
            mock_completion.side_effect = [
                _mid_stream_fallback_wrapping_rate_limit(), _fake_response("second key worked"),
            ]
            result = client.complete([{"role": "user", "content": "hi"}], model="gemini/gemini-3.7-flash")

        assert result == "second key worked"
        assert client._active_key_index.get("gemini/gemini-3.7-flash", 0) == 1
