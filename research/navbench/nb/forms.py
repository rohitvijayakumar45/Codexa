"""Common output forms (feature B: output-form specification).

Q1 showed that a token ratio can flip sign with output form alone: tools differ in *what* they
return (bare names, locations, JSON, source lines), so comparing native outputs mixes information
content with encoding. The "minimal sufficient answer" (MSA) for T1/T3 holds the information
constant across every arm:

    one line per returned caller declaration:  <file>:<line> <qualified name>

Location-returning arms are reduced to the enclosing caller declarations of their locations (what
an agent needs to act on a "who calls X?" answer); caller-returning arms are rendered as-is. Two
arms that return the same caller set therefore produce byte-identical MSA text and the same token
count, so any remaining token difference between arms is *only* a difference in what they found.

Unresolvable caller names ("unresolved:…") are kept verbatim, so a tool is not rewarded for output
the index could not interpret, and module-level callers render as `<file>:1 <module>`.
"""
from __future__ import annotations

from typing import Iterable


def msa_callers(ix, fact_kind: str, facts: Iterable) -> list[str]:
    """Caller-declaration ids for an arm's facts (location facts are mapped to enclosing callers)."""
    if fact_kind == "loc":
        out = {ix.enclosing(f, l) for f, l, _c in (tuple(x) for x in facts)}
    else:
        out = {str(x) for x in facts}
    return sorted(out)


def render_msa(ix, callers: Iterable[str]) -> str:
    lines = []
    for did in sorted(set(callers)):
        if did.startswith("module:"):
            lines.append(f"{did[len('module:'):]}:1 <module>")
        elif did.startswith("unresolved:"):
            lines.append(did)
        elif did in ix.decls:
            d = ix.decls[did]
            lines.append(f"{d['file']}:{d['line']} {d['qualname']}")
        else:
            lines.append(did)
    return "\n".join(lines)


def msa_text(ix, fact_kind: str, facts: Iterable) -> str:
    return render_msa(ix, msa_callers(ix, fact_kind, facts))
