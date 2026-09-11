"""Conversation surface: model discovery + streaming, across all configured providers."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Iterator

import litellm
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.agents.llm import LLMClient
from backend.agents.jobs import JobManager
from backend.agents.phased_build import PhasedBuildManager
from backend.agents.task import build_task_prompt, generate_contract, resolve_contract_source
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


class PhasedBuildRequest(BaseModel):
    spec: str
    repository: str = "codexa-os"
    model: str | None = None


class ModelInfo(BaseModel):
    id: str
    label: str
    provider: str
    context_window: int
    tier: str
    default: bool


def create_chat_router(*, llm: LLMClient, graph: GraphService | None = None, store: MemoryStore | None = None) -> APIRouter:
    router = APIRouter(prefix="/chat", tags=["chat"])
    job_manager = JobManager(llm=llm, graph=graph, store=store)
    job_manager.load_interrupted_ids()
    phased_build_manager = PhasedBuildManager(llm=llm, job_manager=job_manager)

    @router.get("/models", response_model=list[ModelInfo])
    def list_models() -> list[ModelInfo]:
        return [ModelInfo(**m) for m in llm.available_models()]

    @router.post("/stream")
    def stream(request: ChatRequest) -> StreamingResponse:
        model = request.model if (request.model in llm.available) else llm.default_model
        prompt_tokens_approx = sum(_approx_tokens(m.content) for m in request.messages)

        def event_stream() -> Iterator[str]:
            content = ""
            chunks = []
            try:
                for chunk in llm.stream(model, [m.model_dump() for m in request.messages], timeout=180):
                    chunks.append(chunk)
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
            # Record real provider-reported usage (not the length//4 heuristic).
            real_usage: dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0}
            if chunks:
                try:
                    final = litellm.stream_chunk_builder(chunks, messages=[m.model_dump() for m in request.messages])
                    if final:
                        real_usage = llm.record_usage("chat", model, final)
                except Exception:  # noqa: BLE001
                    pass
            usage = {
                "prompt_tokens": real_usage.get("prompt_tokens") or prompt_tokens_approx,
                "completion_tokens": real_usage.get("completion_tokens") or _approx_tokens(content),
                "context_window": llm.context_window(model),
                "model": model,
            }
            yield f"data: {json.dumps({'done': True, 'usage': usage})}\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    @router.post("/agent")
    def agent(request: AgentChatRequest) -> dict:
        """Starts the tool-calling loop as a detached background job and returns its id
        immediately. The job keeps running on its own thread regardless of whether the client
        stays connected — a dropped connection (tab switch, network blip, backend restart) no
        longer cancels in-progress work. Subscribe to /agent/stream/{job_id} to watch it."""
        model = request.model if (request.model in llm.available) else llm.default_model
        repo = request.repository or "codexa-os"
        messages = [m.model_dump() for m in request.messages]
        # Annotate the system message for prompt caching. Providers that support prefix caching
        # (OpenAI, Anthropic, Gemini) will cache system + tools as a stable prefix across rounds,
        # turning re-sent context from billed tokens to near-free cache hits. litellm's
        # drop_params strips cache_control for providers that don't support it.
        if messages and messages[0].get("role") == "system":
            content = messages[0]["content"]
            if isinstance(content, str):
                messages[0]["content"] = [
                    {"type": "text", "text": content, "cache_control": {"type": "ephemeral"}},
                ]

        _last_user = ""
        for m in reversed(request.messages):
            if m.role == "user":
                _last_user = m.content
                break

        # See resolve_contract_source's docstring: a bare nudge ("continue", "hi") mid-task must
        # contract against the last substantive message, not itself — otherwise this system-prompt
        # injection tells the model "TASK MODE: CONVERSATION" (no required tools) for the exact turn
        # where a stalled/incomplete CREATE/MODIFY task still needs enforcing.
        _contract_source = resolve_contract_source(_last_user, messages[:-1] if messages else [])
        _task_prompt = build_task_prompt(generate_contract(_contract_source))
        if _task_prompt and messages and messages[0].get("role") == "system":
            existing = messages[0]["content"]
            if isinstance(existing, str):
                messages[0]["content"] = existing + "\n\n" + _task_prompt
            elif isinstance(existing, list):
                for block in existing:
                    if block.get("type") == "text":
                        block["text"] += "\n\n" + _task_prompt
                        break

        job = job_manager.create(repository=repo, model=model, messages=messages)
        job_manager.start(job, last_user_text=_last_user)
        return {"job_id": job.id}

    @router.post("/agent/job/{job_id}/cancel")
    def agent_job_cancel(job_id: str) -> dict:
        found = job_manager.cancel(job_id)
        if not found:
            raise HTTPException(status_code=404, detail="No such job.")
        return {"cancelled": True}

    @router.get("/agent/job/{job_id}")
    def agent_job_status(job_id: str) -> dict:
        job = job_manager.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="No such job.")
        return {
            "job_id": job.id, "status": job.status, "round": job.round,
            "continuable": job.status == "error" and job.error_reason in ("max_rounds", "stall_exhausted"),
            # Wait-state telemetry (see backend/agents/jobs.py _mark_wait / HARNESS_RESEARCH_
            # FINDINGS.md problem 2): distinguishes "quiet between rounds" from "stuck waiting on
            # the model" or "stuck inside one tool call", and how long it's been silent — instead
            # of "running" reading identically whether the job is 1 second or 7 hours into a hang.
            "wait_state": job.current_wait_state,
            "idle_seconds": round(time.time() - job.last_activity_ts, 1),
            # Independent repeat-call detector (see _tool_call_signature) — visible even when
            # rounds keep "completing successfully" by every other measure.
            "same_tool_signature_streak": job.same_tool_signature_streak,
        }

    @router.post("/agent/job/{job_id}/continue")
    def agent_job_continue(job_id: str) -> dict:
        """"Continue" — for a job that errored out from one of the two mechanically-recoverable
        reasons: ran out of tool-calling rounds, or exhausted its stall-recovery retries on a flaky
        provider connection. Re-runs the same job (same id, full message/tool-call history intact)
        with a fresh budget for whichever ran out, instead of the frontend's old fallback of
        starting a brand-new job from a condensed text summary, which threw away every tool call
        and all reasoning already done."""
        if job_manager.get(job_id) is None:
            raise HTTPException(status_code=404, detail="No such job.")
        job = job_manager.continue_job(job_id)
        if job is None:
            raise HTTPException(
                status_code=409,
                detail="Job isn't in a continuable state (must have errored out from running "
                       "out of rounds or exhausting stall-recovery retries, not any other failure).",
            )
        return {"job_id": job.id}

    @router.get("/agent/stream/{job_id}")
    def agent_stream(job_id: str) -> StreamingResponse:
        """Subscribes to a job's event log: replays everything emitted so far (so a reconnecting
        client catches up on whatever it missed) then tails new events as they arrive. If the job
        isn't in the live registry — the backend restarted after it checkpointed mid-flight — this
        transparently resumes it from the last completed round instead of failing."""
        job = job_manager.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="No such job.")
        if job.status in ("interrupted",):
            job = job_manager.resume(job_id)

        async def event_stream():
            index = 0
            while True:
                events = job.events
                if index < len(events):
                    evt = events[index]
                    index += 1
                    yield _sse(evt)
                    # "done" always means the job is actually finished - safe to stop right away.
                    # "error" is NOT necessarily terminal: backend/agents/jobs.py's _run auto-
                    # continues a "max_rounds"/"stall_exhausted" error right after emitting it, in
                    # the same background thread, often within microseconds - returning here on
                    # sight of the event used to end the SSE relay before that continuation's own
                    # events (the _auto_continue tool_call, the next round's thinking/tool_call/...)
                    # ever got a chance to be appended, so the frontend showed a dead Continue/Retry
                    # card for a job that was already running again server-side. Fall through to the
                    # catch-up check below instead, which re-reads job.status once there are no
                    # more buffered events left - by then the auto-continue (if any) has already
                    # happened, so it correctly distinguishes "still running" from "truly stopped".
                    if "done" in evt:
                        return
                elif job.status in ("done", "error"):
                    return
                else:
                    await asyncio.sleep(0.05)

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    @router.post("/agent/phased")
    def start_phased_build(request: PhasedBuildRequest) -> dict:
        """Splits a large spec into an ordered chain of smaller, independently-completable jobs
        instead of one continuous run — real evidence: two full-stack builds each pushed past
        100-300+ rounds in a single job before finishing, accumulating enough history along the way
        to correlate with real corruption and connection instability. Returns the full phase
        breakdown immediately (before any phase has even started) so the plan is visible up front,
        not discovered after the fact."""
        build = phased_build_manager.start(request.spec, request.repository, model=request.model)
        return {
            "phased_build_id": build.id,
            "phases": [{"title": p.title, "prompt": p.prompt} for p in build.phases],
        }

    @router.get("/agent/phased/{build_id}")
    def phased_build_status(build_id: str) -> dict:
        build = phased_build_manager.get(build_id)
        if build is None:
            raise HTTPException(status_code=404, detail="No such phased build.")
        return {
            "phased_build_id": build.id,
            "status": build.status,
            "current_phase": build.current_phase,
            "phases": [
                {"title": p.title, "job_id": p.job_id, "status": p.status, "detail": p.detail}
                for p in build.phases
            ],
        }

    return router
