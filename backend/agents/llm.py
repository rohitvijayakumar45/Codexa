"""Multi-provider LLM client with task-based routing and real per-model context windows.

Wraps litellm so the app can route across NVIDIA NIM, Groq, Google Gemini, and z.ai (GLM). Two
things live here on purpose:

  * A model registry with each model's REAL documented context window and a capability tier
    (heavy / balanced / light).
  * A routing layer keyed off task type — high-stakes work (architecture, graph, reasoning) goes to
    the heavy tier (GLM 5.x); low-stakes work (docs, summaries) goes to a light tier — so we don't
    default everything to the most expensive model.

A model is only offered if the provider's API key is configured.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Iterator

import litellm

from backend.agents.usage import UsageTracker

logger = logging.getLogger(__name__)
litellm.suppress_debug_info = True
litellm.drop_params = True

ZAI_API_BASE = "https://api.z.ai/api/paas/v4"

# id -> (label, context_window, tier, provider). Context windows are the models' documented limits.
MODEL_REGISTRY: dict[str, tuple[str, int, str, str]] = {
    "nvidia_nim/meta/llama-3.1-8b-instruct": ("Llama 3.1 8B", 131072, "light", "nvidia"),
    "nvidia_nim/meta/llama-3.1-70b-instruct": ("Llama 3.1 70B", 131072, "balanced", "nvidia"),
    "nvidia_nim/mistralai/mistral-nemotron": ("Mistral Nemotron", 128000, "balanced", "nvidia"),
    "groq/llama-3.3-70b-versatile": ("Llama 3.3 70B (Groq)", 131072, "balanced", "groq"),
    "groq/llama-3.1-8b-instant": ("Llama 3.1 8B (Groq)", 131072, "light", "groq"),
    "gemini/gemini-2.5-flash": ("Gemini 2.5 Flash", 1048576, "light", "gemini"),
    "gemini/gemini-2.5-pro": ("Gemini 2.5 Pro", 1048576, "heavy", "gemini"),
    "zai/glm-5.2": ("GLM 5.2", 1000000, "heavy", "zai"),
    "zai/glm-4.5-air": ("GLM 4.5 Air", 128000, "light", "zai"),
}

_PROVIDER_ENV = {
    "nvidia": "NVIDIA_API_KEY",
    "groq": "GROQ_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "zai": "ZAI_API_KEY",
}

# Preference order within each tier (first available wins).
_TIER_ORDER: dict[str, list[str]] = {
    "heavy": ["zai/glm-5.2", "gemini/gemini-2.5-pro", "nvidia_nim/meta/llama-3.1-70b-instruct"],
    "balanced": ["groq/llama-3.3-70b-versatile", "nvidia_nim/meta/llama-3.1-70b-instruct", "zai/glm-5.2"],
    "light": [
        "groq/llama-3.1-8b-instant",
        "nvidia_nim/meta/llama-3.1-8b-instruct",
        "zai/glm-4.5-air",
        "gemini/gemini-2.5-flash",
    ],
}

# High-stakes generation routes to heavy (GLM); low-stakes to light.
TASK_TIER: dict[str, str] = {
    "architecture": "heavy",
    "graph": "heavy",
    "reasoning": "heavy",
    "planner": "heavy",
    "research": "heavy",
    "coder": "heavy",
    "docs": "light",
    "summary": "light",
    "retrieval": "light",
    "chat": "balanced",
}

DEFAULT_CONTEXT = 32768


class LLMClient:
    def __init__(self) -> None:
        overrides_env = os.getenv("AGENT_MODEL_OVERRIDES", "{}")
        try:
            self.agent_overrides: dict[str, str] = json.loads(overrides_env)
        except json.JSONDecodeError:
            self.agent_overrides = {}

        # litellm reads GROQ_API_KEY / GEMINI_API_KEY from env; NVIDIA needs NVIDIA_NIM_API_KEY.
        if os.getenv("NVIDIA_API_KEY"):
            os.environ.setdefault("NVIDIA_NIM_API_KEY", os.environ["NVIDIA_API_KEY"])

        self.available: list[str] = [
            model
            for model, (_l, _c, _t, provider) in MODEL_REGISTRY.items()
            if os.getenv(_PROVIDER_ENV[provider])
        ]

        configured = os.getenv("LLM_DEFAULT_MODEL") or os.getenv("NVIDIA_NIM_DEFAULT_MODEL")
        if configured and configured in MODEL_REGISTRY and configured in self.available:
            self.default_model = configured
        else:
            self.default_model = self.model_for_task("chat")

        self.provider = MODEL_REGISTRY.get(self.default_model, (None, None, None, "nvidia"))[3]
        self.usage = UsageTracker()
        logger.info("LLM ready: default=%s available=%s", self.default_model, self.available)

    # --- routing ------------------------------------------------------------
    def model_for_task(self, task: str) -> str:
        tier = TASK_TIER.get(task, "balanced")
        for candidate in _TIER_ORDER.get(tier, []):
            if candidate in self.available:
                return candidate
        for tier_order in ("balanced", "light", "heavy"):
            for candidate in _TIER_ORDER[tier_order]:
                if candidate in self.available:
                    return candidate
        return self.available[0] if self.available else "nvidia_nim/meta/llama-3.1-8b-instruct"

    def models_for_task(self, task: str) -> list[str]:
        """All available models for a task's tier, in priority order — for callers that want to
        retry against the next candidate on a runtime failure (e.g. a rate-limited provider)."""
        tier = TASK_TIER.get(task, "balanced")
        return [c for c in _TIER_ORDER.get(tier, []) if c in self.available]

    def context_window(self, model: str) -> int:
        return MODEL_REGISTRY.get(model, ("", DEFAULT_CONTEXT, "", ""))[1]

    def available_models(self) -> list[dict[str, Any]]:
        out = []
        for model in self.available:
            label, ctx, tier, provider = MODEL_REGISTRY[model]
            out.append({
                "id": model,
                "label": label,
                "provider": provider,
                "context_window": ctx,
                "tier": tier,
                "default": model == self.default_model,
            })
        return out

    # --- calling ------------------------------------------------------------
    def _kwargs(self, model: str) -> dict[str, Any]:
        # z.ai is OpenAI-compatible; route it through litellm's openai provider with its base+key.
        if model.startswith("zai/"):
            return {
                "model": "openai/" + model.split("/", 1)[1],
                "api_base": ZAI_API_BASE,
                "api_key": os.getenv("ZAI_API_KEY", ""),
            }
        return {"model": model}

    def _record_usage(self, agent: str, model: str, response: Any) -> dict[str, int]:
        usage_obj = getattr(response, "usage", None)
        prompt = int(getattr(usage_obj, "prompt_tokens", 0) or 0) if usage_obj else 0
        completion = int(getattr(usage_obj, "completion_tokens", 0) or 0) if usage_obj else 0
        # Reasoning-capable models (Gemini 2.5, GLM thinking mode) bill internal "thinking" tokens
        # as part of completion_tokens with no visible text — break it out so a tiny visible answer
        # doesn't look like a mystery 500-token response.
        details = getattr(usage_obj, "completion_tokens_details", None) if usage_obj else None
        reasoning = int(getattr(details, "reasoning_tokens", 0) or 0) if details else 0
        provider = MODEL_REGISTRY.get(model, ("", 0, "", "unknown"))[3]
        self.usage.record(
            agent=agent, model=model, provider=provider,
            prompt_tokens=prompt, completion_tokens=completion, reasoning_tokens=reasoning,
        )
        return {"prompt_tokens": prompt, "completion_tokens": completion}

    def complete(self, messages: list[dict], *, model: str | None = None, agent: str = "generate", **kwargs: Any) -> str:
        model = model or self.default_model
        response = litellm.completion(messages=messages, **self._kwargs(model), **kwargs)
        self._record_usage(agent, model, response)
        return response.choices[0].message.content or ""

    def stream(self, model: str, messages: list[dict], **kwargs: Any) -> Iterator[Any]:
        model = model or self.default_model
        return litellm.completion(messages=messages, stream=True, **self._kwargs(model), **kwargs)

    def record_usage(self, agent: str, model: str, response: Any) -> dict[str, int]:
        """Public entry point for callers that assembled their own response (e.g. from raw stream
        chunks via litellm.stream_chunk_builder) and need it logged the same way as complete()."""
        return self._record_usage(agent, model, response)

    def complete_message(
        self, messages: list[dict], *, model: str | None = None, tools: list | None = None, agent: str = "chat",
    ) -> tuple[Any, dict[str, int]]:
        """Non-streaming completion returning (raw message [may carry tool_calls], real usage dict)."""
        model = model or self.default_model
        extra: dict[str, Any] = {}
        if tools:
            extra = {"tools": tools, "tool_choice": "auto"}
        response = litellm.completion(messages=messages, **self._kwargs(model), **extra)
        usage = self._record_usage(agent, model, response)
        return response.choices[0].message, usage

    def generate(self, agent_role: str, prompt: str, *, task: str | None = None, **kwargs: Any) -> str:
        """Back-compat single-prompt call. Routes by agent_role/task unless overridden."""
        model = self.agent_overrides.get(agent_role) or self.model_for_task(task or agent_role)
        return self.complete([{"role": "user", "content": prompt}], model=model, agent=agent_role, **kwargs)
