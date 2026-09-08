"""Design intent: turning Codexa's design skills from documentation into execution constraints.

The problem this exists for
---------------------------
Codexa ships 202KB of genuine design expertise in backend/agents/design_skills/ — Emil Kowalski on
interaction polish, Apple on motion and materials, an 88KB anti-slop rulebook. The output was still
consistently a competent static brochure rather than an interactive product.

Measured before writing any of this, across 21 real benchmark jobs and roughly a thousand tool
calls: `get_design_guidance` was called exactly **once**. Not "loaded too passively" — not loaded.
Four separate mechanisms combined to make that the default outcome:

1. It is a PULL tool. The model has to decide to spend a round on it before it can benefit, and
   nothing anywhere obliges it to.
2. `build_task_prompt` — which lists the required tools and would have said to load guidance — is
   appended to the system message by the HTTP layer, and only `if messages[0]["role"] == "system"`.
   A job started through the API with just a user message silently gets no task prompt at all. Every
   job in the overnight run was in that shape, so none of them ever saw TASK MODE or REQUIRED TOOLS.
3. Even when loaded, the tool result is compacted away after `_STALE_AFTER_ROUNDS` (3) rounds. All
   implementation and every refinement pass happens after that, with the guidance already redacted.
4. The default skill is 88KB and gets truncated to 30KB — two thirds discarded silently, mid-rule.

So the fix is not more words in a prompt. It is: decide what the interface should be before building
it, select only the expertise that fits, distil it into constraints small enough to live in context
for the whole job, and check the result against those constraints rather than against "it rendered".

What this module is
-------------------
A `DesignIntent` is derived from the request and carried alongside the task contract. It names the
visual and interaction character, chooses a small compatible set of skills, and — most importantly —
produces `principles`: short, imperative, checkable statements that are cheap enough to re-send every
round. The full skill files remain the depth behind them; this is the part that stays resident.

It deliberately does not score beauty. Nothing here judges whether a page is attractive, because
that is not a thing this system can honestly measure. What it does is make the difference between a
static page and an interactive product explicit up front, and observable afterwards.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from backend.agents.task import TaskContract, TaskIntent

# ── character detection ───────────────────────────────────────────────────────
#
# Deliberately coarse. The aim is not to classify taste, it is to avoid handing a luxury archive the
# same guidance as a terminal dashboard — which is what a single default skill for everything does.

_CLASSICAL = re.compile(
    r"\b(classical|editorial|archive|museum|manuscript|gallery|library|journal|literary|"
    r"typographic|serif|paper|ivory|parchment|heritage|curated|catalogue|catalog)\b", re.I)
_LUXURY = re.compile(
    r"\b(luxury|luxurious|premium|private (?:bank|office)|wealth|family office|bespoke|"
    r"refined|elegant|sophisticated|high[- ]end|expensive|couture|boutique)\b", re.I)
_DATA_DENSE = re.compile(
    r"\b(dashboard|terminal|console|telemetry|metrics|monitoring|analytics|admin|"
    r"data[- ]dense|tabular|grid of data|observability|logs?)\b", re.I)
_PLAYFUL = re.compile(
    r"\b(playful|fun|vibrant|energetic|bold|consumer|social|game|gaming|colorful|colourful)\b", re.I)

_MOTION_WANTED = re.compile(
    r"\b(animat\w*|motion|transition|scroll[- ]?(?:driven|linked|behaviou?r)?|parallax|"
    r"reveal|micro[- ]interaction|smooth scroll|choreograph\w*|easing|spring)\b", re.I)
_INTERACTION_WANTED = re.compile(
    r"\b(interact\w*|filter|search|sort|explore|browse|drag|hover|click|select|"
    r"detail view|modal|dialog|drawer|palette|keyboard|navigat\w*|state[s]?)\b", re.I)
_RESPONSIVE_WANTED = re.compile(r"\b(responsive|mobile|tablet|breakpoint|small screens?)\b", re.I)
_PRODUCT_NOT_PAGE = re.compile(
    r"\b(application|app|product|workspace|tool|browser|explorer|interface|"
    r"working environment|not a (?:landing|marketing) page)\b", re.I)


@dataclass(frozen=True)
class DesignIntent:
    """What this interface is supposed to be, decided before it is built.

    Carried on the job next to the contract. The contract says what must exist; this says what it
    must be like — and the two are checked separately, because "the HTML runs" was being allowed to
    mean "the frontend is finished".
    """

    character: str                       # e.g. "classical-editorial"
    interaction_depth: str               # "static" | "explorable" | "product"
    motion: str                          # "minimal" | "considered" | "choreographed"
    density: str                         # "airy" | "balanced" | "dense"
    responsive: bool
    #: Skill ids from tools._DESIGN_SKILLS, most important first. Small on purpose.
    skills: list[str] = field(default_factory=list)
    #: Short imperative constraints, cheap enough to re-send every round.
    principles: list[str] = field(default_factory=list)
    #: Capabilities the finished artifact must demonstrably have. Checked as facts about the file,
    #: never as an aesthetic score.
    quality_checks: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> "DesignIntent | None":
        if not data:
            return None
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})


# ── skill selection ───────────────────────────────────────────────────────────
#
# Visual-style skills are MUTUALLY EXCLUSIVE: minimalist editorial and industrial brutalism disagree
# about nearly everything, and loading both does not average them — it gives the model licence to
# take whichever rule is most convenient at each decision, which is how a design system drifts.
# Craft skills (polish, motion) are additive because they operate on a different axis and cannot
# contradict a visual style.

_VISUAL_STYLE = {
    "classical-editorial": "minimalist_editorial",
    "luxury-refined": "high_end_agency",
    "data-dense": "industrial_brutalist",
    "contemporary": "anti_slop",
}
# Never more than this many. Each additional file is thousands of tokens competing with the actual
# implementation context, and past three the model is being handed a reading list rather than a brief.
MAX_SKILLS = 3


# A negated clause ends at the first contrast word, clause boundary, or ~40 characters — whichever
# comes first.
#
# The first version consumed 80 characters after any negation word and stopped only at a full stop.
# "not X but Y" is the most common shape a brief uses to state what it wants, and that version ate
# the Y: "Build not a landing page but a luxurious editorial archive of rare manuscripts" reduced to
# "Build", so a classical archive classified as generic contemporary and got the wrong skill set.
# The clause being removed is the X; the Y is the actual instruction and must survive.
_NEGATED = re.compile(
    r"\b(?:not|never|avoid|avoiding|rather than|instead of|without|no)\b"
    r"(?:(?!\b(?:but|rather|instead|however|yet)\b)[^.;,\n]){0,40}",
    re.I,
)


def _strip_negations(text: str) -> str:
    return _NEGATED.sub(" ", text or "")


def _character_of(text: str) -> str:
    # Order matters: a "luxury private bank with editorial typography" is both, and the classical
    # reading produces the better result for the light/serif briefs this platform is asked for.
    if _CLASSICAL.search(text):
        return "classical-editorial"
    if _LUXURY.search(text):
        return "luxury-refined"
    if _DATA_DENSE.search(text):
        return "data-dense"
    if _PLAYFUL.search(text):
        return "contemporary"
    return "contemporary"


def _interaction_depth(text: str) -> str:
    """How much this thing has to *do*.

    The single most consequential field. The observed failure was a model satisfying a rich brief
    with a beautiful static page: every visual instruction honoured, almost no behaviour. Naming the
    expected depth up front, and checking for it afterwards, is what makes that difference
    inspectable instead of a matter of taste.
    """
    signals = sum(bool(p.search(text)) for p in (_INTERACTION_WANTED, _PRODUCT_NOT_PAGE))
    if _PRODUCT_NOT_PAGE.search(text) and _INTERACTION_WANTED.search(text):
        return "product"
    if signals:
        return "explorable"
    return "static"


def _motion_level(text: str) -> str:
    if not _MOTION_WANTED.search(text):
        return "minimal"
    hits = len(_MOTION_WANTED.findall(text))
    return "choreographed" if hits >= 4 else "considered"


def select_skills(text: str, character: str, motion: str, depth: str) -> list[str]:
    """One visual style plus at most two craft skills, most important first."""
    chosen = [_VISUAL_STYLE.get(character, "anti_slop")]
    # Interaction feel is a different axis from visual style and cannot contradict it.
    if depth in ("explorable", "product"):
        chosen.append("emil_design_eng")
    if motion == "choreographed":
        chosen.append("animate")
    elif motion == "considered" and "emil_design_eng" not in chosen:
        chosen.append("emil_design_eng")
    if depth == "product" and "animate" not in chosen and len(chosen) < MAX_SKILLS:
        chosen.append("apple_design")
    return chosen[:MAX_SKILLS]


# ── the resident brief ────────────────────────────────────────────────────────

_PRINCIPLES_BY_DEPTH = {
    "static": [],
    "explorable": [
        "This is an interface, not a page. Every primary object must be openable, filterable or "
        "sortable — a reader must be able to DO something, not only scroll.",
        "Every interactive element needs its real states: hover, focus-visible, active, disabled, "
        "loading, empty and error. A control with only a resting state is unfinished.",
    ],
    "product": [
        "This is a product, not a landing page. If the whole experience can be consumed by "
        "scrolling once, it has failed regardless of how it looks.",
        "Build at least one signature interaction the product is organised around — a detail view "
        "that transitions from its source, a filter that recomposes the collection, a command "
        "palette. It must change what is on screen, not merely decorate it.",
        "Every interactive element needs its real states: hover, focus-visible, active, disabled, "
        "loading, empty and error. A control with only a resting state is unfinished.",
        "State changes must be visible and reversible. The user should always be able to tell what "
        "just happened and get back.",
    ],
}

_PRINCIPLES_BY_MOTION = {
    "minimal": [],
    "considered": [
        "Motion carries meaning: it shows where something came from or what changed. Animate "
        "transform and opacity; give everything one shared easing curve and a short duration scale.",
        "Honour prefers-reduced-motion by disabling movement, not by leaving it on.",
    ],
    "choreographed": [
        "Scrolling is the primary experience. Use IntersectionObserver reveals that fire once, "
        "stagger by index, and never re-animate on scroll-back.",
        "Motion carries meaning: it shows where something came from or what changed. Animate "
        "transform and opacity only, on one shared easing curve.",
        "One signature transition should be the thing a person remembers — a layout morph, a "
        "continuous transform, a scrubber that redraws as it moves.",
        "Honour prefers-reduced-motion by disabling movement, not by leaving it on.",
    ],
}

_PRINCIPLES_BY_CHARACTER = {
    "classical-editorial": [
        "Serif carries identity — names, headings, body. Mono or small-caps sans carries data: "
        "labels, numbers, coordinates, timestamps.",
        "Hairline rules and generous whitespace do the structural work. Not boxes, not cards with "
        "borders on every side, not shadows on things that are not floating.",
        "One accent colour, used on under 8% of the interface.",
    ],
    "luxury-refined": [
        "Restraint reads as expensive: precise grids, thin rules, tactile surfaces, and motion that "
        "is quiet and fast rather than showy.",
        "One accent colour, used sparingly. No gradients beyond a barely perceptible wash.",
    ],
    "data-dense": [
        "Information density is the point: tight rhythm, aligned numerals, monospace for data.",
        "Structure comes from alignment and rules, never from decoration.",
    ],
    "contemporary": [
        "Establish a real type scale and spacing scale and use only those values.",
    ],
}

_ANTI_PATTERNS = [
    "No generic SaaS look: no wall of equal rounded cards, no template sidebar, no meaningless "
    "chart, no emoji as icons, no border-radius over 16px, no glassmorphism.",
    "No placeholder text of any kind. Invent specific, plausible content with real names, dates "
    "and attributions.",
]


def derive(request: str, contract: TaskContract) -> DesignIntent | None:
    """Build the design intent for a frontend task, or None when the task is not one.

    None matters: attaching a design brief to "run the tests" is noise in every prompt for the rest
    of that job. UI-ness is taken from the contract (task.py already sets `screenshot` as a required
    tool for a UI task) rather than re-derived here, so the two cannot disagree.
    """
    if contract.intent not in (TaskIntent.CREATE, TaskIntent.MODIFY):
        return None
    if "screenshot" not in contract.required_tools:
        return None

    text = request or ""
    # Character, density and motion are read from the AFFIRMATIVE text only. What a brief rules out
    # must not be mistaken for what it asks for.
    positive = _strip_negations(text)
    character = _character_of(positive)
    depth = _interaction_depth(text)
    motion = _motion_level(positive)
    density = "dense" if _DATA_DENSE.search(positive) else (
        "airy" if character in ("classical-editorial", "luxury-refined") else "balanced")
    responsive = bool(_RESPONSIVE_WANTED.search(text)) or depth != "static"

    principles = (
        _PRINCIPLES_BY_CHARACTER.get(character, [])
        + _PRINCIPLES_BY_DEPTH.get(depth, [])
        + _PRINCIPLES_BY_MOTION.get(motion, [])
        + _ANTI_PATTERNS
    )
    if responsive:
        principles.append(
            "Recompose the layout at small widths — change what is shown and how it is arranged. "
            "Stacking the desktop columns is not a mobile design.")
    principles.append(
        "Keyboard access throughout, with a visible :focus-visible ring. If it can be clicked it "
        "must be reachable and operable from the keyboard.")

    checks = ["interaction", "states"]
    if motion != "minimal":
        checks.append("motion")
    if responsive:
        checks.append("responsive")
    checks.append("accessibility")

    return DesignIntent(
        character=character,
        interaction_depth=depth,
        motion=motion,
        density=density,
        responsive=responsive,
        skills=select_skills(text, character, motion, depth),
        principles=principles,
        quality_checks=checks,
    )


def brief(intent: DesignIntent | None) -> str:
    """The resident design brief: small enough to live in context for the whole job.

    This is the half of the fix that addresses the compaction problem. The full skill files are tens
    of thousands of characters and get redacted after three rounds, which is before any real
    implementation happens. A few hundred characters of imperative constraint can simply stay.
    """
    if intent is None:
        return ""
    lines = [
        "DESIGN INTENT (decided for this task — apply it while implementing, not afterwards):",
        f"- Character: {intent.character}   Interaction: {intent.interaction_depth}   "
        f"Motion: {intent.motion}   Density: {intent.density}",
    ]
    if intent.skills:
        lines.append(
            f"- Load the full guidance with get_design_guidance for: {', '.join(intent.skills)} "
            f"(start with {intent.skills[0]}). These are chosen to be compatible; do not load others."
        )
    lines.append("")
    lines.append("NON-NEGOTIABLE DESIGN CONSTRAINTS:")
    lines += [f"- {p}" for p in intent.principles]
    if intent.interaction_depth != "static":
        lines += [
            "",
            "A page that merely looks right is NOT complete. Before you report this finished, it "
            "must actually do the things above when clicked, typed into, and resized.",
        ]
    return "\n".join(lines)
