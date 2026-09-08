"""Tests for token-budget prediction (backend/agents/token_budget.py) and the usage-tracker
plumbing it reads from (backend/agents/usage.py: task_intent field, records_for_intent)."""

import tempfile
from pathlib import Path

from backend.agents.token_budget import (
    DEFAULT_BUDGET_TOKENS,
    MIN_SAMPLES_TO_TRUST_AVERAGE,
    SAFETY_MARGIN,
    predict_token_budget,
)
from backend.agents.usage import UsageTracker


def _tracker() -> UsageTracker:
    tmp = Path(tempfile.mkdtemp()) / "usage.jsonl"
    return UsageTracker(path=tmp)


class TestUsageTrackerIntentPlumbing:
    def test_records_for_intent_filters_by_task_intent(self):
        tracker = _tracker()
        tracker.record(agent="chat", model="m", provider="p", prompt_tokens=100, completion_tokens=50, task_intent="CREATE_ARTIFACT")
        tracker.record(agent="chat", model="m", provider="p", prompt_tokens=200, completion_tokens=50, task_intent="EXPLAIN_CONCEPT")

        create_records = tracker.records_for_intent("CREATE_ARTIFACT")
        assert len(create_records) == 1
        assert create_records[0].total_tokens == 150

    def test_records_with_no_intent_are_never_matched(self):
        tracker = _tracker()
        tracker.record(agent="chat", model="m", provider="p", prompt_tokens=100, completion_tokens=50)  # no task_intent

        assert tracker.records_for_intent("CREATE_ARTIFACT") == []

    def test_persists_and_reloads_task_intent_across_a_restart(self):
        path = Path(tempfile.mkdtemp()) / "usage.jsonl"
        first = UsageTracker(path=path)
        first.record(agent="chat", model="m", provider="p", prompt_tokens=100, completion_tokens=50, task_intent="RUN_EXECUTION")

        second = UsageTracker(path=path)  # simulates a backend restart re-loading the JSONL file
        assert len(second.records_for_intent("RUN_EXECUTION")) == 1

    def test_reloading_a_pre_existing_file_with_no_task_intent_key_does_not_crash(self):
        # Old records written before this field existed have no "task_intent" key at all.
        path = Path(tempfile.mkdtemp()) / "usage.jsonl"
        path.write_text(
            '{"at": "2026-01-01T00:00:00+00:00", "agent": "chat", "model": "m", "provider": "p", '
            '"prompt_tokens": 10, "completion_tokens": 5, "reasoning_tokens": 0, "total_tokens": 15}\n',
            encoding="utf-8",
        )
        tracker = UsageTracker(path=path)
        assert len(tracker.records(limit=10)) == 1
        assert tracker.records(limit=10)[0].task_intent is None


class TestPredictTokenBudget:
    def test_cold_start_returns_default_with_low_confidence(self):
        tracker = _tracker()

        prediction = predict_token_budget("CREATE_ARTIFACT", tracker)

        assert prediction.predicted_tokens == DEFAULT_BUDGET_TOKENS
        assert prediction.based_on_samples == 0
        assert prediction.confidence == "low"

    def test_below_minimum_sample_size_still_uses_default(self):
        tracker = _tracker()
        for _ in range(MIN_SAMPLES_TO_TRUST_AVERAGE - 1):
            tracker.record(agent="chat", model="m", provider="p", prompt_tokens=1000, completion_tokens=1000, task_intent="CREATE_ARTIFACT")

        prediction = predict_token_budget("CREATE_ARTIFACT", tracker)

        assert prediction.confidence == "low"
        assert prediction.predicted_tokens == DEFAULT_BUDGET_TOKENS

    def test_enough_samples_predicts_from_the_real_average_with_safety_margin(self):
        tracker = _tracker()
        for _ in range(MIN_SAMPLES_TO_TRUST_AVERAGE):
            tracker.record(agent="chat", model="m", provider="p", prompt_tokens=800, completion_tokens=200, task_intent="CREATE_ARTIFACT")
        # average total_tokens == 1000

        prediction = predict_token_budget("CREATE_ARTIFACT", tracker)

        assert prediction.based_on_samples == MIN_SAMPLES_TO_TRUST_AVERAGE
        assert prediction.predicted_tokens == round(1000 * SAFETY_MARGIN)
        assert prediction.confidence == "medium"

    def test_twenty_or_more_samples_reaches_high_confidence(self):
        tracker = _tracker()
        for _ in range(20):
            tracker.record(agent="chat", model="m", provider="p", prompt_tokens=500, completion_tokens=500, task_intent="EXPLAIN_CONCEPT")

        prediction = predict_token_budget("EXPLAIN_CONCEPT", tracker)

        assert prediction.confidence == "high"

    def test_different_intents_never_pollute_each_others_average(self):
        tracker = _tracker()
        for _ in range(MIN_SAMPLES_TO_TRUST_AVERAGE):
            tracker.record(agent="chat", model="m", provider="p", prompt_tokens=100, completion_tokens=0, task_intent="EXPLAIN_CONCEPT")
        for _ in range(MIN_SAMPLES_TO_TRUST_AVERAGE):
            tracker.record(agent="chat", model="m", provider="p", prompt_tokens=9000, completion_tokens=0, task_intent="CREATE_ARTIFACT")

        explain_prediction = predict_token_budget("EXPLAIN_CONCEPT", tracker)

        assert explain_prediction.predicted_tokens == round(100 * SAFETY_MARGIN)

    def test_custom_default_is_honored_on_cold_start(self):
        tracker = _tracker()

        prediction = predict_token_budget("SEARCH_EXTERNAL", tracker, default=9999)

        assert prediction.predicted_tokens == 9999
