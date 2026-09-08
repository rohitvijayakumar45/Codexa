"""Per-call LLM usage tracking — real provider token counts, tagged by the agent role/task that made
the call, so a usage view can show where tokens actually go across the architecture instead of one
opaque running total.

Persisted to a gitignored append-only JSON-lines file (`.codexa/usage.jsonl`) so history survives a
backend restart — every other in-memory store in this app already has this problem; usage data is
the one that's actively misleading to lose, since "per-agent token usage" implies a real ledger, not
a counter that resets whenever uvicorn does.

Also separates `reasoning_tokens` out of `completion_tokens`: reasoning-capable models (Gemini 2.5,
GLM's thinking mode) bill internal "thinking" tokens as part of completion_tokens with zero visible
text to show for them — a 3-word answer can genuinely report 500 completion tokens. That's real,
billed usage, not a tracking bug, but showing it as one flat number is misleading; breaking it out
lets the UI say "497 of which were reasoning" instead of just looking wrong.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock

from backend.memory.store import DATA_DIR

_MAX_IN_MEMORY = 200_000  # ~200k tiny records is still only tens of MB; the JSONL file is the real backing store


@dataclass
class UsageRecord:
    at: datetime
    agent: str
    model: str
    provider: str
    prompt_tokens: int
    completion_tokens: int
    reasoning_tokens: int
    total_tokens: int
    # Which task-contract intent (backend/agents/task.py: CREATE_ARTIFACT, EXPLAIN_CONCEPT, ...) this
    # call was made under, when known — lets predict_token_budget (backend/agents/token_budget.py)
    # learn "how many tokens does this KIND of task actually cost" instead of only "how many tokens
    # does the chat agent cost overall," which is all `agent` alone distinguishes today. Optional and
    # additive: existing records/callers with no intent keep working exactly as before.
    task_intent: str | None = None


def _bucket() -> dict[str, int]:
    return {"prompt_tokens": 0, "completion_tokens": 0, "reasoning_tokens": 0, "total_tokens": 0, "calls": 0}


def _add(bucket: dict[str, int], r: UsageRecord) -> None:
    bucket["prompt_tokens"] += r.prompt_tokens
    bucket["completion_tokens"] += r.completion_tokens
    bucket["reasoning_tokens"] += r.reasoning_tokens
    bucket["total_tokens"] += r.total_tokens
    bucket["calls"] += 1


class UsageTracker:
    def __init__(self, path=None) -> None:
        self.path = path or (DATA_DIR / "usage.jsonl")
        self._lock = Lock()
        self._records: list[UsageRecord] = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return
        for line in lines[-_MAX_IN_MEMORY:]:
            if not line.strip():
                continue
            try:
                d = json.loads(line)
                self._records.append(UsageRecord(
                    at=datetime.fromisoformat(d["at"]), agent=d["agent"], model=d["model"],
                    provider=d["provider"], prompt_tokens=d["prompt_tokens"],
                    completion_tokens=d["completion_tokens"], reasoning_tokens=d.get("reasoning_tokens", 0),
                    total_tokens=d["total_tokens"], task_intent=d.get("task_intent"),
                ))
            except (json.JSONDecodeError, KeyError, ValueError):
                continue

    def _append_to_disk(self, r: UsageRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps({
            "at": r.at.isoformat(), "agent": r.agent, "model": r.model, "provider": r.provider,
            "prompt_tokens": r.prompt_tokens, "completion_tokens": r.completion_tokens,
            "reasoning_tokens": r.reasoning_tokens, "total_tokens": r.total_tokens,
            "task_intent": r.task_intent,
        })
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def record(
        self, *, agent: str, model: str, provider: str,
        prompt_tokens: int, completion_tokens: int, reasoning_tokens: int = 0,
        task_intent: str | None = None,
    ) -> None:
        if prompt_tokens <= 0 and completion_tokens <= 0:
            return
        rec = UsageRecord(
            at=datetime.now(UTC), agent=agent or "unknown", model=model, provider=provider,
            prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
            reasoning_tokens=reasoning_tokens, total_tokens=prompt_tokens + completion_tokens,
            task_intent=task_intent,
        )
        with self._lock:
            self._records.append(rec)
            self._append_to_disk(rec)

    def _since(self, days: int | None) -> list[UsageRecord]:
        with self._lock:
            items = list(self._records)
        if days is None:
            return items
        cutoff = datetime.now(UTC) - timedelta(days=days)
        return [r for r in items if r.at >= cutoff]

    def records(self, limit: int = 200, days: int | None = None) -> list[UsageRecord]:
        return self._since(days)[-limit:][::-1]

    def summary(self, days: int | None = None) -> dict:
        items = self._since(days)
        by_agent: dict[str, dict[str, int]] = {}
        by_model: dict[str, dict[str, int]] = {}
        totals = _bucket()
        for r in items:
            _add(by_agent.setdefault(r.agent, _bucket()), r)
            _add(by_model.setdefault(r.model, _bucket()), r)
            _add(totals, r)
        return {"totals": totals, "by_agent": by_agent, "by_model": by_model}

    def records_for_intent(self, task_intent: str, *, days: int | None = None) -> list[UsageRecord]:
        return [r for r in self._since(days) if r.task_intent == task_intent]

    def daily(self, days: int = 30) -> list[dict]:
        """One bucket per calendar day (UTC), zero-filled for continuity — for a usage chart."""
        items = self._since(days)
        by_day: dict[str, dict[str, int]] = {}
        for r in items:
            key = r.at.date().isoformat()
            _add(by_day.setdefault(key, _bucket()), r)
        today = datetime.now(UTC).date()
        out = []
        for i in range(days - 1, -1, -1):
            key = (today - timedelta(days=i)).isoformat()
            bucket = by_day.get(key, _bucket())
            out.append({"date": key, **bucket})
        return out
