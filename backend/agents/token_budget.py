"""Predicts how many tokens a task is likely to cost, from this repository's own history of tasks
with the same classified intent (backend/agents/task.py's CREATE_ARTIFACT/EXPLAIN_CONCEPT/... labels)
— not a guess, and not a hand-picked constant per intent type. Cold-starts to a fixed default until
there's enough real history to trust, then reports a real average with a safety margin.

This is deliberately just a predictor, not an enforcer: it doesn't cap anything or refuse a task that
runs over budget (backend/agents/jobs.py has its own round-budget cap for that, unrelated to token
count). What it's for is visibility — surfacing "tasks like this one usually cost about N tokens"
before the work starts, and building the historical signal a future enforcement layer could use.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DEFAULT_BUDGET_TOKENS = 4000
MIN_SAMPLES_TO_TRUST_AVERAGE = 3
SAFETY_MARGIN = 1.3  # headroom above the historical average, not a hard ceiling


@dataclass
class TokenBudgetPrediction:
    predicted_tokens: int
    based_on_samples: int
    confidence: str  # "low" (default, insufficient history) | "medium" | "high"


def predict_token_budget(
    intent: str, usage: Any, *, default: int = DEFAULT_BUDGET_TOKENS,
) -> TokenBudgetPrediction:
    records = usage.records_for_intent(intent)
    n = len(records)
    if n < MIN_SAMPLES_TO_TRUST_AVERAGE:
        return TokenBudgetPrediction(predicted_tokens=default, based_on_samples=n, confidence="low")
    average = sum(r.total_tokens for r in records) / n
    predicted = round(average * SAFETY_MARGIN)
    confidence = "high" if n >= 20 else "medium"
    return TokenBudgetPrediction(predicted_tokens=predicted, based_on_samples=n, confidence=confidence)
