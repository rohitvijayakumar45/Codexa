"""Ledger summaries (backend/observability/api.py `_summary`) must read as sentences, not as cut-off
strings — "Decision · React for the UI: declared in frontend/package.j" was the live example."""

from __future__ import annotations

from backend.observability.api import _clip, _summary


def test_clip_cuts_at_a_word_boundary_and_marks_the_cut():
    text = "React for the UI: declared in frontend/package.json (react@^18.3.1)."
    out = _clip(text, 40)
    assert out.endswith("…")
    assert len(out) <= 41
    assert not out[:-1].endswith(("frontend/package.j", " "))


def test_short_text_is_untouched():
    assert _clip("calls relation formed") == "calls relation formed"


def test_a_decision_is_named_by_its_title_not_its_summary():
    payload = {"node_type": "Decision", "properties": {"title": "React for the UI",
                                                      "summary": "React for the UI: declared in frontend/package.json (react@^18)."}}
    assert _summary("graph.node.created", payload) == "Decision · React for the UI"


def test_edge_types_read_as_words():
    assert _summary("graph.edge.created", {"edge_type": "traces_to_decision"}) == "traces to decision relation formed"
