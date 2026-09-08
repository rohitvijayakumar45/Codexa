"""A committed capability must be materially implemented, not merely answered in kind.

The failure this addresses is semantic substitution. A model asked for a "smooth scroll experience"
writes `scroll-behavior: smooth`; asked for a "shared-element transition" it fades a modal in; asked
for "immersive interaction" it adds `hover: scale(1.02)`. Each is a defensible reading of the words
and none is the thing — and the artifact then passes every check that asks "is there interaction
code here", because there is.

So each capability is defined by the MECHANISM it cannot exist without (does the code measure
geometry and invert it? does a frame loop consume scroll position?) and separately by the cheaper
thing mistaken for it. That is structural rather than vocabulary, because vocabulary is exactly what
the cheap version also has.

Honest limit, stated in the module under test and worth repeating: this detects the ABSENCE OF A
MECHANISM. Presence is necessary, never sufficient — it cannot tell a beautiful transition from an
ugly one, and behavioural proof needs the browser.
"""

from __future__ import annotations

import re

import pytest

from backend.agents.design_intent import derive
from backend.agents.plan import make_task
from backend.agents.task import generate_contract
from backend.agents.validators import _CAPABILITY_MECHANISMS, validate_task

VELUM = "prompts/overnight/1-velum.md"

# Every promise, none of the mechanism. This is the artifact shape the check exists for.
CHEAP = """<!doctype html><html><head><style>
html{scroll-behavior:smooth}
.card:hover{transform:scale(1.02)}
.reader{opacity:0;transition:opacity .3s}.reader.open{opacity:1}
@media (max-width:640px){body{font-size:14px}}
</style></head><body>
<input type="search" placeholder="Search the archive">
<div class="card">A</div><div class="reader"></div>
<script>document.querySelector('.card').addEventListener('click',function(){
  document.querySelector('.reader').classList.add('open');});</script>
</body></html>"""

REAL = """<!doctype html><html><head><style>
.plate{transition:transform .4s cubic-bezier(.16,1,.3,1)}
@media (max-width:640px){.grid{grid-template-columns:1fr;flex-direction:column}}
@media (prefers-reduced-motion: reduce){*{animation:none}}
</style></head><body>
<input id="q" type="search"><div class="grid"></div><div id="reader"></div>
<script>
function openRecord(card){
  var first = card.getBoundingClientRect();
  var target = document.getElementById('reader');
  var last = target.getBoundingClientRect();
  target.style.transform = 'translate(' + (first.left-last.left) + 'px,' +
    (first.top-last.top) + 'px) scale(' + (first.width/last.width) + ')';
  requestAnimationFrame(function(){ target.style.transform = 'translate(0,0) scale(1)'; });
}
document.querySelector('.grid').addEventListener('click', function(e){ openRecord(e.target); });
document.getElementById('q').addEventListener('input', function(e){
  document.querySelectorAll('.plate').forEach(function(p){
    p.hidden = !p.dataset.title.includes(e.target.value); });
});
function frame(){ var y = window.scrollY;
  document.querySelectorAll('.plate').forEach(function(p){
    p.style.transform = 'translateY(' + (y*0.04) + 'px)'; });
  requestAnimationFrame(frame); }
requestAnimationFrame(frame);
</script></body></html>"""


def _check(tmp_path, monkeypatch, html: str):
    for module in ("backend.agents.validators",):
        monkeypatch.setattr(f"{module}.repo_root", lambda _r, _p=tmp_path: _p)
    (tmp_path / "index.html").write_text(html, encoding="utf-8")
    brief = open(VELUM, encoding="utf-8").read()
    intent = derive(brief, generate_contract(brief))
    task = make_task("final", index=1, expected_artifacts=["index.html"],
                     validators=["intent_fidelity"])
    return validate_task(task, repository="demo", tools_called_in_task=[],
                         design=intent.to_dict())


class TestTheBriefsPromisesAreCaptured:
    def test_a_rich_brief_commits_to_real_capabilities(self):
        brief = open(VELUM, encoding="utf-8").read()
        intent = derive(brief, generate_contract(brief))
        assert "shared_element_transition" in intent.capabilities
        assert "scroll_linked_motion" in intent.capabilities
        assert "filterable_collection" in intent.capabilities

    def test_a_modest_brief_commits_to_nothing_it_did_not_ask_for(self):
        # Under-claiming is the safe direction: a capability nobody asked for would fail a build
        # for not having it.
        brief = "Build a simple html page listing my favourite books with a screenshot"
        intent = derive(brief, generate_contract(brief))
        assert intent.capabilities == []

    def test_every_committed_name_is_one_the_validator_knows(self):
        brief = open(VELUM, encoding="utf-8").read()
        intent = derive(brief, generate_contract(brief))
        assert set(intent.capabilities) <= set(_CAPABILITY_MECHANISMS)


class TestCheapSubstitutionsAreCaught:
    def test_the_substitution_page_fails(self, tmp_path, monkeypatch):
        assert _check(tmp_path, monkeypatch, CHEAP).passed is False

    def test_smooth_scroll_css_is_not_scroll_driven_motion(self, tmp_path, monkeypatch):
        detail = _check(tmp_path, monkeypatch, CHEAP).detail
        assert "scroll-behavior" in detail and "not scroll-driven motion" in detail

    def test_a_fading_modal_is_not_a_shared_element(self, tmp_path, monkeypatch):
        detail = _check(tmp_path, monkeypatch, CHEAP).detail
        assert "not a shared element" in detail

    def test_the_failure_names_what_is_missing_rather_than_scoring_it(self, tmp_path, monkeypatch):
        # "no FLIP transition" is far less actionable than naming the substitution found instead.
        detail = _check(tmp_path, monkeypatch, CHEAP).detail
        assert "committed but not implemented" in detail
        assert "/10" not in detail and "score" not in detail.lower()


class TestARealImplementationPasses:
    def test_mechanisms_present_means_pass(self, tmp_path, monkeypatch):
        result = _check(tmp_path, monkeypatch, REAL)
        assert result.passed, result.detail

    def test_it_says_which_capabilities_it_found(self, tmp_path, monkeypatch):
        assert "present" in _check(tmp_path, monkeypatch, REAL).detail


class TestItNeverInventsAnOpinion:
    def test_a_task_with_no_committed_capabilities_passes(self, tmp_path, monkeypatch):
        monkeypatch.setattr("backend.agents.validators.repo_root", lambda _r: tmp_path)
        (tmp_path / "index.html").write_text(CHEAP, encoding="utf-8")
        task = make_task("final", index=1, expected_artifacts=["index.html"],
                         validators=["intent_fidelity"])
        result = validate_task(task, repository="demo", tools_called_in_task=[])
        assert result.passed
        assert "no capabilities" in result.detail

    def test_every_pattern_compiles(self):
        for spec in _CAPABILITY_MECHANISMS.values():
            for pattern in spec["mechanism"] + spec["substitution"]:
                re.compile(pattern)


class TestMotionIsAFirstClassDimension:
    """Observed across several runs: the HTML kept getting more polished while the animation stayed
    generic. Three causes, all structural rather than a failure of model capability.

    1. The motion principles were adjectives. "Motion carries meaning" is true and unimplementable —
       a model reading it writes `transition: all .3s ease` and moves on. What separates crafted
       motion from decorated motion is a few decisions made ONCE (one curve, a duration scale, a
       stagger step, which properties may animate), so those are given as values.
    2. The `animate` skill — the one with implementation recipes rather than principles — loaded
       only for "choreographed" briefs, so an ordinary UI brief never saw them.
    3. Motion was a third of "Add interactions, transitions and the real states", and it was always
       the third that got dropped: that task is satisfied by doing the first two.
    """

    def _intent(self, path="prompts/bench/small-tidepool.md"):
        from backend.agents.design_intent import derive
        from backend.agents.task import generate_contract
        text = open(path, encoding="utf-8").read()
        return text, derive(text, generate_contract(text))

    def test_the_motion_brief_carries_implementable_values(self):
        from backend.agents.design_intent import brief
        _text, intent = self._intent()
        body = brief(intent)
        assert "MOTION TOKENS" in body
        assert "cubic-bezier" in body, "one named curve, not an adjective"
        assert "ms" in body, "a duration scale, not 'quick'"

    def test_it_names_the_properties_that_may_animate(self):
        from backend.agents.design_intent import brief
        _text, intent = self._intent()
        body = brief(intent)
        assert "transform and opacity" in body
        assert "prefers-reduced-motion" in body

    def test_an_ordinary_ui_brief_gets_the_animation_skill(self):
        # It was gated on "choreographed", which most real briefs are not.
        _text, intent = self._intent()
        assert intent.motion == "considered"
        assert "animate" in intent.skills

    def test_a_brief_with_no_motion_ask_gets_no_motion_guidance(self):
        # The guidance must not appear where nobody asked for movement.
        from backend.agents.design_intent import brief, derive
        from backend.agents.task import generate_contract
        text = "Build a plain html page of my reading list with a screenshot"
        intent = derive(text, generate_contract(text))
        if intent is not None:
            assert "MOTION TOKENS" not in brief(intent)

    def test_motion_is_its_own_milestone(self):
        from backend.agents.plan_builder import fallback_plan
        from backend.agents.task import generate_contract
        text, _intent = self._intent()
        plan = fallback_plan(text, generate_contract(text))
        motion = [t for t in plan.tasks if "motion system" in t.objective.lower()]
        assert len(motion) == 1, "motion folded into another task is the part that gets dropped"
        assert motion[0].required_tools, "a milestone with no required tool cannot end on its round"
        assert motion[0].validators

    def test_the_states_task_no_longer_carries_motion_too(self):
        from backend.agents.plan_builder import fallback_plan
        from backend.agents.task import generate_contract
        text, _intent = self._intent()
        plan = fallback_plan(text, generate_contract(text))
        states = next(t for t in plan.tasks if "interaction states" in t.objective.lower())
        assert "transition" not in states.objective.lower()
