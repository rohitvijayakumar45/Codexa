"""Conversation surface: model discovery + streaming, across all configured providers."""

from __future__ import annotations

import json
from typing import Iterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.agents.llm import LLMClient
from backend.agents.tools import TOOL_SCHEMAS, execute_tool, parse_args
from backend.graph.service import GraphService
from backend.memory.store import MemoryStore


def _approx_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(system|user|assistant|tool)$")
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)
    model: str | None = None


class AgentChatRequest(ChatRequest):
    repository: str = "codexa-os"


class ModelInfo(BaseModel):
    id: str
    label: str
    provider: str
    context_window: int
    tier: str
    default: bool


def create_chat_router(*, llm: LLMClient, graph: GraphService | None = None, store: MemoryStore | None = None) -> APIRouter:
    router = APIRouter(prefix="/chat", tags=["chat"])

    @router.get("/models", response_model=list[ModelInfo])
    def list_models() -> list[ModelInfo]:
        return [ModelInfo(**m) for m in llm.available_models()]

    @router.post("/stream")
    def stream(request: ChatRequest) -> StreamingResponse:
        model = request.model if (request.model in llm.available) else llm.default_model
        prompt_tokens = sum(_approx_tokens(m.content) for m in request.messages)

        def event_stream() -> Iterator[str]:
            content = ""
            try:
                for chunk in llm.stream(model, [m.model_dump() for m in request.messages]):
                    delta = chunk.choices[0].delta.content or ""
                    if delta:
                        content += delta
                        yield f"data: {json.dumps({'delta': delta})}\n\n"
            except Exception as exc:  # noqa: BLE001 - surface provider failures to the client
                yield f"data: {json.dumps({'error': f'{type(exc).__name__}: {exc}'})}\n\n"
                return
            usage = {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": _approx_tokens(content),
                "context_window": llm.context_window(model),
                "model": model,
            }
            yield f"data: {json.dumps({'done': True, 'usage': usage})}\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    @router.post("/agent")
    def agent(request: AgentChatRequest) -> StreamingResponse:
        """Tool-calling loop: the model may read/search/write files, search the web, or run code —
        or just answer. Streams tool-call traces then the final text."""
        model = request.model if (request.model in llm.available) else llm.default_model
        repo = request.repository or "codexa-os"
        messages = [m.model_dump() for m in request.messages]
        prompt_tokens = sum(_approx_tokens(m.content) for m in request.messages)

        def gen():
            content = ""
            real_prompt_tokens = 0
            real_completion_tokens = 0
            try:
                for _round in range(6):
                    try:
                        msg, usage = llm.complete_message(messages, model=model, tools=TOOL_SCHEMAS, agent="chat")
                    except Exception:  # model may not support tools — fall back to plain answer
                        msg, usage = llm.complete_message(messages, model=model, agent="chat")
                    real_prompt_tokens += usage["prompt_tokens"]
                    real_completion_tokens += usage["completion_tokens"]
                    tool_calls = getattr(msg, "tool_calls", None) or []
                    if tool_calls:
                        messages.append({
                            "role": "assistant",
                            "content": msg.content or "",
                            "tool_calls": [
                                {"id": tc.id, "type": "function",
                                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                                for tc in tool_calls
                            ],
                        })
                        for tc in tool_calls:
                            name = tc.function.name
                            args = parse_args(tc.function.arguments)
                            yield _sse({"tool_call": {"name": name, "args": args}})
                            result = execute_tool(name, args, repo, graph=graph, store=store)
                            yield _sse({"tool_result": {"name": name, "result": result[:600]}})
                            messages.append({"role": "tool", "tool_call_id": tc.id, "name": name, "content": result})
                        continue
                    content = msg.content or ""
                    for i in range(0, len(content), 18):
                        yield _sse({"delta": content[i:i + 18]})
                    break
            except Exception as exc:  # noqa: BLE001
                yield _sse({"error": f"{type(exc).__name__}: {exc}"})
                return
            yield _sse({"done": True, "usage": {
                # Real provider-reported counts (from complete_message's usage), not the length//4
                # heuristic — falls back to the approximation only if a provider reported nothing.
                "prompt_tokens": real_prompt_tokens or prompt_tokens,
                "completion_tokens": real_completion_tokens or _approx_tokens(content),
                "context_window": llm.context_window(model),
                "model": model,
            }})

        return StreamingResponse(gen(), media_type="text/event-stream")

    return router
