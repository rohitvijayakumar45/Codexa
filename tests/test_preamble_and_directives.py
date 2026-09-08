"""Two second-order failures of earlier fixes, both found on a live job rather than in review.

1. The design brief silently stopped reaching the model. The task prompt used to be attached by the
   HTTP layer and only `if messages[0]["role"] == "system"`, so API-started jobs got nothing; that
   was fixed by moving attachment server-side. But the frontend's system message is not a string —
   chat/api.py wraps it as [{"type": "text", "text": ..., "cache_control": {...}}] for prefix
   caching — and the replacement checked `isinstance(existing, str)`, matching neither branch and
   doing nothing at all. Verified on a real job: TASK MODE present (added by the HTTP layer, which
   handles the list), DESIGN INTENT absent. The same guarantee broken twice by the SHAPE of the
   caller's message rather than its absence.

2. Recovery directives stacked. The rule was "do not append if an identical one is among the last
   three messages", which fails as soon as assistant/tool pairs push the earlier copy out of that
   window. Measured on the same job: four copies of one 2,227-character directive, ~9KB re-sent on
   every later request — the pattern this codebase already documents as having preceded two
   providers going permanently silent.
"""

from __future__ import annotations

from backend.agents.jobs import Job, _attach_preamble, _replace_directive

PREAMBLE = "TASK MODE: CREATE_ARTIFACT\n\nDESIGN INTENT (decided for this task)"


def _job(messages, rounds=None) -> Job:
    return Job(id="j", repository="r", model="m", messages=messages,
               message_rounds=rounds if rounds is not None else [-100] * len(messages))


class TestThePreambleReachesEveryShapeOfCaller:
    def test_the_cached_list_shape_the_frontend_actually_sends(self):
        # The shape that silently dropped it. Regression-critical.
        job = _job([
            {"role": "system", "content": [
                {"type": "text", "text": "You are Codexa.", "cache_control": {"type": "ephemeral"}}]},
            {"role": "user", "content": "build a page"},
        ])
        _attach_preamble(job, PREAMBLE)
        block = job.messages[0]["content"][0]
        assert "DESIGN INTENT" in block["text"]
        # The preamble is stable for the life of the job, so it belongs inside the cached block.
        assert block["cache_control"] == {"type": "ephemeral"}

    def test_a_plain_string_system_message(self):
        job = _job([{"role": "system", "content": "You are Codexa."}])
        _attach_preamble(job, PREAMBLE)
        assert "DESIGN INTENT" in job.messages[0]["content"]

    def test_no_system_message_at_all(self):
        # Every API-started job, including every overnight benchmark job.
        job = _job([{"role": "user", "content": "build a page"}])
        _attach_preamble(job, PREAMBLE)
        assert job.messages[0]["role"] == "system"
        assert "TASK MODE" in job.messages[0]["content"]
        assert len(job.messages) == len(job.message_rounds), "index-matched lists must stay in step"

    def test_an_unexpected_shape_is_never_silently_dropped(self):
        # The failure mode itself: an unrecognised shape must not mean "do nothing".
        job = _job([{"role": "system", "content": {"weird": True}}])
        _attach_preamble(job, PREAMBLE)
        assert any("DESIGN INTENT" in str(m.get("content")) for m in job.messages)

    def test_attaching_twice_does_not_duplicate_it(self):
        job = _job([{"role": "system", "content": "You are Codexa."}])
        _attach_preamble(job, PREAMBLE)
        _attach_preamble(job, PREAMBLE)
        assert job.messages[0]["content"].count("DESIGN INTENT") == 1

    def test_an_empty_preamble_changes_nothing(self):
        job = _job([{"role": "user", "content": "hello"}])
        _attach_preamble(job, "")
        assert len(job.messages) == 1


class TestOnlyOneDirectiveIsEverLive:
    DIRECTIVE = "[SYSTEM: planning for this task is finished. Do not reconsider it.]"

    def _run(self, cuts: int):
        messages = [{"role": "user", "content": "build"}]
        rounds = [-100]
        for r in range(cuts):
            # The assistant/tool pair between cuts is what pushed the old directive out of the
            # three-message window the previous check looked at.
            messages.append({"role": "assistant", "content": "", "tool_calls": [{"id": "1"}]})
            rounds.append(r)
            messages.append({"role": "tool", "content": "ok"})
            rounds.append(r)
            _replace_directive(messages, rounds, self.DIRECTIVE, r)
        return messages, rounds

    def test_four_cuts_leave_one_directive_not_four(self):
        messages, _rounds = self._run(4)
        live = [m for m in messages if str(m.get("content", "")).startswith("[SYSTEM: planning")]
        assert len(live) == 1

    def test_it_stays_at_the_end_where_it_applies(self):
        messages, _rounds = self._run(3)
        assert str(messages[-1]["content"]).startswith("[SYSTEM: planning")

    def test_the_index_matched_lists_stay_in_step(self):
        # Compaction reads round numbers positionally; drift mis-ages unrelated messages.
        messages, rounds = self._run(5)
        assert len(messages) == len(rounds)

    def test_a_commit_directive_replaces_an_execution_one(self):
        # Both kinds are recovery instructions for the CURRENT round. Two contradictory ones live at
        # once would be worse than either alone.
        messages, rounds = self._run(2)
        _replace_directive(messages, rounds, "[SYSTEM: that round was stopped — commit first]", 9)
        live = [m for m in messages if str(m.get("content", "")).startswith("[SYSTEM: ")]
        assert len(live) == 1
        assert "commit first" in live[0]["content"]

    def test_real_conversation_content_is_never_removed(self):
        messages, rounds = self._run(3)
        assert messages[0]["content"] == "build"
        assert sum(1 for m in messages if m.get("role") == "tool") == 3
