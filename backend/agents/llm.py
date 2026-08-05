import json
import logging
import os
from typing import Any

from openai import OpenAI

logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(self) -> None:
        self.provider = os.getenv("LLM_PROVIDER", "local")
        
        overrides_env = os.getenv("AGENT_MODEL_OVERRIDES", "{}")
        try:
            self.agent_overrides = json.loads(overrides_env)
        except json.JSONDecodeError:
            self.agent_overrides = {}

        fallback = os.getenv("LLM_FALLBACK_TO_LOCAL", "false").lower() == "true"

        if self.provider == "nvidia_nim":
            api_key = os.getenv("NVIDIA_API_KEY")
            if not api_key:
                if fallback:
                    self.provider = "local"
                else:
                    raise ValueError("NVIDIA_API_KEY is required when LLM_PROVIDER=nvidia_nim")

        if self.provider == "nvidia_nim":
            base_url = os.getenv("NVIDIA_NIM_BASE_URL", "https://integrate.api.nvidia.com/v1")
            self.default_model = os.getenv("NVIDIA_NIM_DEFAULT_MODEL", "meta/llama3-70b-instruct")
            api_key = os.getenv("NVIDIA_API_KEY")
        else:
            base_url = os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:11434/v1")
            self.default_model = os.getenv("LOCAL_LLM_DEFAULT_MODEL", "qwen3:14b")
            api_key = "dummy"

        self.client = OpenAI(base_url=base_url, api_key=api_key)

    def generate(self, agent_role: str, prompt: str, **kwargs: Any) -> str:
        model = self.agent_overrides.get(agent_role, self.default_model)

        response = self.client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            **kwargs,
        )

        usage = response.usage
        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0

        logger.info(
            "LLM usage: provider=%s, model=%s, prompt_tokens=%d, completion_tokens=%d",
            self.provider,
            model,
            prompt_tokens,
            completion_tokens,
        )

        return response.choices[0].message.content or ""
