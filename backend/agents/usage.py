"""Per-call LLM usage tracking — real provider token counts, tagged by the agent role/task that made
the call, so a usage view can show where tokens actually go across the architecture instead of one
opaque running total. In-memory, capped, reset on restart (same tradeoff as the rest of the graph)."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock

_MAX_RECORDS = 3000


@dataclass
class UsageRecord:
    at: datetime
    agent: str
    model: str
    provider: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class UsageTracker:
    def __init__(self) -> None:
        self._lock = Lock()
        self._records: deque[UsageRecord] = deque(maxlen=_MAX_RECORDS)

    def record(self, *, agent: str, model: str, provider: str, prompt_tokens: int, completion_tokens: int) -> None:
        if prompt_tokens <= 0 and completion_tokens <= 0:
            return
        with self._lock:
            self._records.append(UsageRecord(
                at=datetime.now(UTC), agent=agent or "unknown", model=model, provider=provider,
                prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ))

    def records(self, limit: int = 200) -> list[UsageRecord]:
        with self._lock:
            items = list(self._records)
        return items[-limit:][::-1]

    def summary(self) -> dict:
        with self._lock:
            items = list(self._records)

        def _bucket() -> dict[str, int]:
            return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "calls": 0}

        by_agent: dict[str, dict[str, int]] = {}
        by_model: dict[str, dict[str, int]] = {}
        totals = _bucket()
        for r in items:
            for store, key in ((by_agent, r.agent), (by_model, r.model)):
                slot = store.setdefault(key, _bucket())
                slot["prompt_tokens"] += r.prompt_tokens
                slot["completion_tokens"] += r.completion_tokens
                slot["total_tokens"] += r.total_tokens
                slot["calls"] += 1
            totals["prompt_tokens"] += r.prompt_tokens
            totals["completion_tokens"] += r.completion_tokens
            totals["total_tokens"] += r.total_tokens
            totals["calls"] += 1
        return {"totals": totals, "by_agent": by_agent, "by_model": by_model}
