"""Conversation surface for the Codexa workstation.

Wraps the existing LLMClient so the frontend chat can (a) discover which models the backend can
actually route to, and (b) stream a real completion. Token usage is reported so the UI can show
context-window consumption. When no model endpoint is reachable (e.g. no local Ollama running and
no NVIDIA key), the stream yields a clear error event instead of pretending to answer.
"""

from __future__ import annotations

import json
from typing import Iterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.agents.llm import LLMClient

# Known context windows for the models this backend is likely to route to. Falls back to a safe
# default for anything unlisted rather than inventing a precise number.
_CONTEXT_WINDOWS: dict[str, int] = {
    "qwen3:14b": 32768,
    "meta/llama-3.1-8b-instruct": 131072,
    "meta/llama-3.1-70b-instruct": 131072,
    "mistralai/mistral-nemotron": 131072,
}
_DEFAULT_CONTEXT = 32768


def _context_window(model: str) -> int:
    return _CONTEXT_WINDOWS.get(model, _CONTEXT_WINDOWS.get(model.split("/")[-1], _DEFAULT_CONTEXT))


def _approx_tokens(text: str) -> int:
    # Deterministic char-based approximation; the client only needs a stable gauge, not exact BPE.
    return max(1, len(text) // 4)


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(system|user|assistant)$")
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)
    model: str | None = None


class ModelInfo(BaseModel):
    id: str
    label: str
    provider: str
    context_window: int
    default: bool


def _label(model: str) -> str:
    tail = model.split("/")[-1]
    return tail.replace(":", " ").replace("-", " ").title()


def create_chat_router(*, llm: LLMClient) -> APIRouter:
    router = APIRouter(prefix="/chat", tags=["chat"])

    # Verified working + responsive on this account (others 404 or time out).
    _NVIDIA_MODELS = [
        "meta/llama-3.1-8b-instruct",
        "meta/llama-3.1-70b-instruct",
        "mistralai/mistral-nemotron",
    ]

    @router.get("/models", response_model=list[ModelInfo])
    def list_models() -> list[ModelInfo]:
        seen: dict[str, ModelInfo] = {}
        candidates = [llm.default_model, *llm.agent_overrides.values()]
        if llm.provider == "nvidia_nim":
            candidates = [llm.default_model, *_NVIDIA_MODELS]
        for model in candidates:
            if not model or model in seen:
                continue
            seen[model] = ModelInfo(
                id=model,
                label=_label(model),
                provider=llm.provider,
                context_window=_context_window(model),
                default=model == llm.default_model,
            )
        return list(seen.values())

    @router.post("/stream")
    def stream(request: ChatRequest) -> StreamingResponse:
        model = request.model or llm.default_model
        prompt_tokens = sum(_approx_tokens(m.content) for m in request.messages)

        def event_stream() -> Iterator[str]:
            # Some hosted providers (and this environment) don't stream reliably, so we take the
            # full completion and reveal it progressively over SSE. The content and usage are real.
            try:
                response = llm.client.chat.completions.create(
                    model=model,
                    messages=[m.model_dump() for m in request.messages],
                )
                content = response.choices[0].message.content or ""
                usage_obj = getattr(response, "usage", None)
            except Exception as exc:  # noqa: BLE001 - surface any provider failure to the client
                yield f"data: {json.dumps({'error': f'{type(exc).__name__}: {exc}'})}\n\n"
                return

            step = 18
            for i in range(0, len(content), step):
                yield f"data: {json.dumps({'delta': content[i : i + step]})}\n\n"

            usage = {
                "prompt_tokens": getattr(usage_obj, "prompt_tokens", None) or prompt_tokens,
                "completion_tokens": getattr(usage_obj, "completion_tokens", None) or _approx_tokens(content),
                "context_window": _context_window(model),
                "model": model,
            }
            yield f"data: {json.dumps({'done': True, 'usage': usage})}\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    return router
