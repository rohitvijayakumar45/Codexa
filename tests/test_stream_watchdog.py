"""Tests for backend/agents/jobs.py's _stream_with_watchdog.

Regression coverage for a REAL, observed overnight incident: a provider (tokenrouter/GLM) accepted
a request and kept the connection open but sent back literally nothing — no chunk, no error, no
keepalive — for 25+ minutes straight. The per-call `timeout=` kwarg passed to litellm never fired,
and job.cancelled couldn't help either (only checked between chunks, and zero chunks ever arrived).
The whole job thread just sat there forever with no way to recover short of restarting the process.
_stream_with_watchdog enforces a real, code-level wall-clock deadline independently of whatever the
underlying HTTP client's own timeout semantics do or don't catch.
"""

import time

import pytest

from backend.agents.jobs import _stream_with_watchdog
import backend.agents.jobs as jobs_mod


def _fast_generator(items):
    for item in items:
        yield item


def _hanging_generator(delay: float, then_yield=None):
    """Simulates a connection that stays open but sends nothing for `delay` seconds."""
    time.sleep(delay)
    if then_yield is not None:
        yield then_yield


def _erroring_generator(exc: Exception):
    raise exc
    yield  # pragma: no cover - makes this a generator function


class TestNormalStreaming:
    def test_yields_every_chunk_in_order(self):
        result = list(_stream_with_watchdog(_fast_generator([1, 2, 3])))
        assert result == [1, 2, 3]

    def test_empty_source_yields_nothing_and_does_not_hang(self):
        result = list(_stream_with_watchdog(_fast_generator([])))
        assert result == []


class TestTimeoutEnforcement:
    def test_raises_timeout_error_when_source_stays_silent(self, monkeypatch):
        monkeypatch.setattr(jobs_mod, "_CHUNK_TIMEOUT_SECONDS", 0.1)
        with pytest.raises(TimeoutError):
            list(_stream_with_watchdog(_hanging_generator(delay=1.0)))

    def test_does_not_time_out_if_a_chunk_arrives_before_the_deadline(self, monkeypatch):
        monkeypatch.setattr(jobs_mod, "_CHUNK_TIMEOUT_SECONDS", 2.0)
        result = list(_stream_with_watchdog(_hanging_generator(delay=0.1, then_yield="ok")))
        assert result == ["ok"]

    def test_deadline_resets_on_each_chunk_not_just_the_start(self, monkeypatch):
        # Three chunks, each arriving just under the per-chunk deadline apart - total elapsed time
        # far exceeds the deadline, but it must never fire since no SINGLE gap exceeds it.
        monkeypatch.setattr(jobs_mod, "_CHUNK_TIMEOUT_SECONDS", 0.2)

        def slow_but_steady():
            for i in range(3):
                time.sleep(0.1)
                yield i

        result = list(_stream_with_watchdog(slow_but_steady()))
        assert result == [0, 1, 2]


class TestErrorPropagation:
    def test_an_exception_from_the_source_is_re_raised_unchanged(self):
        original = ValueError("boom")
        with pytest.raises(ValueError, match="boom"):
            list(_stream_with_watchdog(_erroring_generator(original)))

    def test_error_after_some_chunks_still_yields_those_first(self):
        def source():
            yield "a"
            yield "b"
            raise RuntimeError("mid-stream failure")

        gen = _stream_with_watchdog(source())
        assert next(gen) == "a"
        assert next(gen) == "b"
        with pytest.raises(RuntimeError, match="mid-stream failure"):
            next(gen)
