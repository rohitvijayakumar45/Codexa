"""Conversation surface: model discovery + streaming, across all configured providers."""

from __future__ import annotations

import json
from typing import Iterator

import litellm
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


_COMPACTED_MARK = "[compacted"
# How many rounds a bulky payload stays in full before being collapsed. Deliberately generous (not
# 1) so the model still has it available if it circles back to reference it a round or two later —
# this trades a small amount of extra tokens for zero risk of the model losing information it still
# needs, per the "zero impact on output" requirement this was built under.
_STALE_AFTER_ROUNDS = 3


def _compact_stale_payloads(messages: list[dict], message_rounds: list[int], current_round: int) -> None:
    """Collapses old, already-acted-upon bulky tool payloads in place so a long multi-round
    tool-calling task doesn't keep re-sending the same huge blobs on every subsequent round.

    Targets only content that (a) the model has already had multiple rounds to act on, and (b) is
    reconstructable/irrelevant to future reasoning even once removed: get_design_guidance's dumped
    style-guide text (the model already used it to decide what to write; it can call the tool again
    if it genuinely needs it later), and write_file/edit_file's file content (the file is on disk —
    that's the source of truth, not the chat transcript; edit_file's old_text match happens against
    the live file too, not history). Nothing else is touched, so ordinary conversation, tool_call_id
    pairing, and every other message stay exactly as the model produced them.
    """
    for i, msg in enumerate(messages):
        if current_round - message_rounds[i] < _STALE_AFTER_ROUNDS:
            continue
        if msg.get("role") == "tool" and msg.get("name") == "get_design_guidance":
            content = msg.get("content", "")
            if isinstance(content, str) and not content.startswith(_COMPACTED_MARK):
                msg["content"] = (
                    f"{_COMPACTED_MARK} — this design guidance ({len(content)} chars) was loaded "
                    "earlier in this conversation and already used. Call get_design_guidance again "
                    "if you need to re-check its rules.]"
                )
        elif msg.get("role") == "assistant" and msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                fn = tc.get("function", {})
                if fn.get("name") not in ("write_file", "edit_file"):
                    continue
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except (json.JSONDecodeError, TypeError):
                    continue
                changed = False
                for key in ("content", "new_text", "old_text"):
                    val = args.get(key)
                    if isinstance(val, str) and len(val) > 200 and not val.startswith(_COMPACTED_MARK):
                        args[key] = f"{_COMPACTED_MARK} — {len(val)} chars, already written to disk.]"
                        changed = True
                if changed:
                    fn["arguments"] = json.dumps(args)


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
                for chunk in llm.stream(model, [m.model_dump() for m in request.messages], timeout=180):
                    delta = chunk.choices[0].delta
                    thinking = getattr(delta, "reasoning_content", None)
                    if thinking:
                        yield _sse({"thinking": thinking})
                    text = delta.content or ""
                    if text:
                        content += text
                        yield _sse({"delta": text})
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
        # Parallel array (same length/order as `messages`) tracking which round each entry was
        # appended at, so _compact_stale_payloads knows how old something is. Pre-existing messages
        # get a sentinel far in the past — harmless, since compaction only ever touches messages that
        # structurally match a tool result/tool call, which none of the original request messages are.
        message_rounds = [-100] * len(messages)
        prompt_tokens = sum(_approx_tokens(m.content) for m in request.messages)

        def _stream_round(*, with_tools: bool):
            """Streams one model turn live (reasoning_content as 'thinking' deltas, content as
            'delta' events) and returns the reassembled message + usage once the round ends.

            `timeout` is httpx's read timeout — the max gap between two received chunks, not a cap
            on the whole round (it resets every time a chunk arrives). 180s because some providers
            (observed on zai/GLM) go silent for well over a minute mid-generation on large/complex
            completions (e.g. a single big HTML+CSS+JS file in one write_file call) without erroring
            — that's real in-progress work stalling, not a hang, and a short timeout kills it."""
            kwargs = {"tools": TOOL_SCHEMAS, "tool_choice": "auto"} if with_tools else {}
            chunks = []
            for chunk in llm.stream(model, messages, timeout=240, **kwargs):
                chunks.append(chunk)
                delta = chunk.choices[0].delta
                thinking = getattr(delta, "reasoning_content", None)
                if thinking:
                    yield ("thinking", thinking)
                if delta.content:
                    yield ("delta", delta.content)
            final = litellm.stream_chunk_builder(chunks, messages=messages)
            usage = llm.record_usage("chat", model, final) if final else {"prompt_tokens": 0, "completion_tokens": 0}
            yield ("final", (final.choices[0].message if final else None, usage))

        def _run_round(*, with_tools: bool):
            """Wraps _stream_round with retries for failures that happen before any output exists
            yet — safe to retry since nothing shown to the user needs to be undone. A rate-limit
            error (litellm.RateLimitError) switches to the next available model in the same tier
            instead of just retrying the same one — Groq's TPM rejections fire before a single token
            streams, on the pre-flight size check, so this never risks duplicating output. Any other
            failure gets one retry against the same model. Once any chunk has been emitted for this
            round, nothing here is safely retryable and the failure is raised as before."""
            nonlocal model
            tried = {model}
            for attempt in range(1, 6):
                emitted = False
                try:
                    for kind, payload in _stream_round(with_tools=with_tools):
                        if kind != "final":
                            emitted = True
                        yield (kind, payload)
                    return
                except Exception as exc:
                    if emitted:
                        raise
                    if isinstance(exc, litellm.RateLimitError):
                        tier = llm.tier_of(model)
                        next_model = next(
                            (m for m in llm.models_for_tier(tier) if m not in tried), None,
                        ) if tier else None
                        if next_model:
                            model = next_model
                            tried.add(model)
                            yield ("model_switched", model)
                            continue
                    if attempt >= 2:
                        raise

        def gen():
            content = ""
            real_prompt_tokens = 0
            real_completion_tokens = 0
            # Reassigned if create_project succeeds mid-loop, so a "build a new project" request can
            # scaffold it in the same turn instead of needing the user to switch repos and ask again.
            working_repo = repo
            # A stall that happens AFTER a round has already streamed some thinking/content can't be
            # silently retried by _run_round (the partial output is already on screen) — it used to
            # just surface as an error, mirroring exactly what large single-shot generations (e.g. one
            # huge write_file call) kept hitting in practice. Give those a bounded number of automatic
            # "continue where you left off" recoveries instead of failing outright — the same thing a
            # user manually retyping "CONTINUE" was doing by hand.
            stall_recoveries = 0
            max_stall_recoveries = 2
            try:
                # Was 6 — raised because stall recoveries now also consume a round, and a multi-step
                # scaffold (create_project + design guidance + several directories/files) can
                # legitimately need more than 6 tool rounds on its own.
                for _round in range(10):
                    _compact_stale_payloads(messages, message_rounds, _round)
                    msg = None
                    usage = {"prompt_tokens": 0, "completion_tokens": 0}
                    saw_any_chunk = False
                    partial_content = ""
                    try:
                        for kind, payload in _run_round(with_tools=True):
                            if kind == "final":
                                msg, usage = payload
                            elif kind == "model_switched":
                                # Not real model output — a rate-limited model was swapped for the
                                # next one in its tier before anything streamed, so this must NOT
                                # mark saw_any_chunk (that would wrongly block the no-tools fallback
                                # path below on a genuine tool-support failure).
                                yield _sse({kind: payload})
                            else:
                                saw_any_chunk = True
                                if kind == "delta":
                                    partial_content += payload
                                yield _sse({kind: payload})
                    except Exception:
                        if saw_any_chunk:
                            if stall_recoveries >= max_stall_recoveries:
                                raise
                            stall_recoveries += 1
                            if partial_content:
                                messages.append({"role": "assistant", "content": partial_content})
                                message_rounds.append(_round)
                            messages.append({
                                "role": "user",
                                "content": (
                                    "[SYSTEM: the connection stalled mid-response (provider timeout). "
                                    "Continue exactly from where you left off — do not repeat any text "
                                    "already written above. If you were in the middle of a tool call "
                                    "such as write_file, redo that call from scratch with the complete "
                                    "content, since a partial/interrupted tool call was not saved.]"
                                ),
                            })
                            message_rounds.append(_round)
                            continue
                        # model may not support tools — fall back to plain streaming
                        for kind, payload in _run_round(with_tools=False):
                            if kind == "final":
                                msg, usage = payload
                            else:
                                yield _sse({kind: payload})
                    real_prompt_tokens += usage["prompt_tokens"]
                    real_completion_tokens += usage["completion_tokens"]
                    tool_calls = getattr(msg, "tool_calls", None) or [] if msg else []
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
                        message_rounds.append(_round)
                        for tc in tool_calls:
                            name = tc.function.name
                            args = parse_args(tc.function.arguments)
                            yield _sse({"tool_call": {"name": name, "args": args}})
                            tool_ctx: dict = {}
                            result = execute_tool(name, args, working_repo, graph=graph, store=store, context=tool_ctx, llm=llm)
                            if tool_ctx.get("new_repository"):
                                working_repo = tool_ctx["new_repository"]
                                yield _sse({"repo_switched": working_repo})
                            yield _sse({"tool_result": {"name": name, "result": result[:600]}})
                            messages.append({"role": "tool", "tool_call_id": tc.id, "name": name, "content": result})
                            message_rounds.append(_round)
                        continue
                    content = msg.content or "" if msg else ""
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
