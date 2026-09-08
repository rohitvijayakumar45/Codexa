"""Claim extraction and graph/tool-grounded verification for the agent's final answer.

Extends the existing task-contract check (backend/agents/task.py: "was the required tool called")
with a second, complementary gate: "are the specific factual claims in the answer actually true."
An agent can call write_file and still tell the user it created a function that doesn't compile, or
say "tests passed" after a test run that actually failed — required-tool validation misses both,
since the tool WAS called. This module catches that class by extracting checkable claims from the
draft answer and resolving each against the code knowledge graph or the turn's own tool-return log
(never against the model's self-report), rejecting the answer for a correction round on any claim
that doesn't hold up. Every claim type is resolved deterministically — no LLM judgment call decides
whether a claim is true, only whether the answer contains one worth checking (extraction), matching
the "don't ask the LLM to track freshness" principle used elsewhere in this codebase's memory layer.

A failure to extract or resolve claims never blocks the answer — this is a net added safety check,
not a new way for the turn to fail outright.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)
_MAX_CLAIMS = 8  # bounded — this is a spot-check, not exhaustive fact-checking of the whole answer


class ClaimType(str, Enum):
    FILE_EXISTS = "file_exists"
    SYMBOL_EXISTS = "symbol_exists"
    SYMBOL_USED_N_TIMES = "symbol_used_n_times"
    TEST_PASSED = "test_passed"
    ACTION_PERFORMED = "action_performed"


@dataclass
class Claim:
    type: ClaimType
    target: str  # file path, symbol name, or tool name
    assertion: str  # what was claimed, e.g. "3", "passed", "created"


_EXTRACT_PROMPT_HEADER = (
    "Below is an AI coding assistant's answer to a user. List every CHECKABLE POSITIVE factual claim "
    "it makes about the codebase or about actions it just performed — the kind of claim that could be "
    "independently verified by looking at the actual files or the record of what tools were called. "
    "Only extract a claim that asserts something IS true / DOES exist / WAS done / DID pass. "
    "If the answer says something does NOT exist, was NOT done, or did NOT pass — that is already a "
    "cautious, negative statement and must NOT be extracted as a claim to check (there is nothing "
    "riskier than the answer already stated). "
    "Ignore opinions, explanations, and claims about anything other than this session's own work.\n\n"
    "Respond with ONLY a JSON object (no markdown fences, no commentary) shaped exactly like: "
    '{"claims": [{"type": "file_exists|symbol_exists|symbol_used_n_times|test_passed|'
    'action_performed", "target": "the file path, symbol name, or tool name", '
    '"assertion": "what was claimed, e.g. a count or \'passed\'/\'created\'"}]}. '
    f"List at most {_MAX_CLAIMS} claims, the most consequential ones. If there is nothing checkable, "
    'return {"claims": []}.\n\n'
    "Answer to check:\n"
)


def _extract_prompt(answer: str) -> str:
    # Plain concatenation, not str.format() — the header above contains literal JSON braces that
    # .format() would otherwise try (and fail) to interpret as placeholders.
    return _EXTRACT_PROMPT_HEADER + answer

# Tool names whose mere presence in this turn's tool-call log substantiates an ACTION_PERFORMED
# claim naming them — anything not listed here can still be claimed but won't be auto-verified.
_KNOWN_ACTIONS = {
    "write_file", "edit_file", "delete_file", "move_file", "create_directory",
    "create_files", "apply_patch", "commit", "create_branch", "run_command", "run_tests",
}
_TEST_TOOLS = {"run_tests", "run_command"}


def extract_claims(answer_text: str, llm: Any) -> list[Claim]:
    """One cheap delegate-tier call to pull structured claims out of the draft answer. Never
    raises — a parse failure or malformed response just yields no claims (nothing to verify),
    since this is a safety net on top of the answer, not a requirement for producing one."""
    if not answer_text or not answer_text.strip():
        return []
    try:
        worker_models = llm.models_for_tier("light")
        model = worker_models[0] if worker_models else None
        raw = llm.complete(
            [{"role": "user", "content": _extract_prompt(answer_text[:6000])}],
            model=model, agent="claim_extraction",
        )
    except Exception as exc:  # noqa: BLE001 - extraction failure must never block the answer
        logger.warning("claim extraction call failed: %s", exc)
        return []

    match = _JSON_BLOCK.search(raw)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    claims: list[Claim] = []
    for c in (data.get("claims") or [])[:_MAX_CLAIMS]:
        if not isinstance(c, dict):
            continue
        try:
            ctype = ClaimType(c.get("type"))
        except ValueError:
            continue
        target, assertion = c.get("target"), c.get("assertion")
        if isinstance(target, str) and target and isinstance(assertion, str) and not _is_negated(assertion):
            claims.append(Claim(type=ctype, target=target, assertion=assertion))
    return claims


_NEGATION_MARKERS = re.compile(
    r"\b(not|n't|no|never|fail(ed|s)?|miss(ing)?|absent|doesn't|does not|didn't|did not|"
    r"isn't|is not|wasn't|was not|cannot|can't|couldn't)\b",
    re.IGNORECASE,
)


def _is_negated(assertion: str) -> bool:
    """Deterministic backstop, not just a prompt instruction: the extraction prompt asks the model
    to only report positive claims, but this is a verification gate — it shouldn't rest solely on an
    LLM correctly following that instruction. A claim whose own assertion text is phrased as a
    negation (the model already said the file DOESN'T exist / tests did NOT pass) must never be
    checked as if it asserted the opposite; that flips a truthful, cautious answer into a rejected
    one and wastes a correction round telling the model to stop saying something already true."""
    return bool(_NEGATION_MARKERS.search(assertion))


def _in_repo(node: Any, repository: str) -> bool:
    repo_prop = node.properties.get("repository")
    return (not repo_prop) if repository == "codexa-os" else repo_prop == repository


_USAGE_EDGE_TYPES = ("calls", "imports", "depends_on", "flows_into")  # matches tools.py's _get_dependencies


def _count_symbol_usages(graph: Any, symbol: str, repository: str) -> int:
    edges = [e for e in graph.list_edges_at() if e.edge_type in _USAGE_EDGE_TYPES]
    nodes_by_id = {n.id: n for n in graph.list_nodes()}
    count = 0
    for e in edges:
        target = nodes_by_id.get(e.to_node_id)
        if target and target.node_type == "CodeSymbol" and target.properties.get("name") == symbol and _in_repo(target, repository):
            count += 1
    return count


def _resolve_claim(claim: Claim, *, graph: Any, repository: str) -> tuple[bool, str]:
    """Resolves a single claim against the live knowledge graph (or, for FILE_EXISTS, the real
    filesystem). Returns (holds, reason)."""
    if claim.type == ClaimType.FILE_EXISTS:
        # Checked against disk, not the graph: analyze_repo (backend/repository/analyze.py) only
        # captures recognized SOURCE-code extensions as File nodes — a README.md or a .json config
        # file genuinely on disk has no graph node at all, which would make this claim type reject
        # every true claim about a non-source file. The graph is the right source of truth for
        # SYMBOL_* claims (only it knows about parsed code structure); for "does this file exist,"
        # the filesystem itself is strictly more complete and just as fast to check.
        from backend.files.api import repo_root

        try:
            root = repo_root(repository)
            exists = (root / claim.target).exists()
        except Exception as exc:  # noqa: BLE001 - an unresolvable repository must not block the answer
            return True, f"could not check filesystem — not verified ({exc})"
        return exists, ("file exists on disk" if exists else f"no file at '{claim.target}' in the repository")

    if graph is None:
        return True, "no graph available — not checked"  # fail open, not closed

    nodes = graph.list_nodes()

    if claim.type == ClaimType.SYMBOL_EXISTS:
        found = any(
            n.node_type == "CodeSymbol" and _in_repo(n, repository) and n.properties.get("name") == claim.target
            for n in nodes
        )
        return found, ("symbol found in graph" if found else f"no symbol named '{claim.target}' in the graph")

    if claim.type == ClaimType.SYMBOL_USED_N_TIMES:
        try:
            claimed_n = int(re.search(r"\d+", claim.assertion).group())
        except (AttributeError, ValueError):
            return True, "claimed count not parseable — not checked"
        actual_n = _count_symbol_usages(graph, claim.target, repository)
        return actual_n == claimed_n, f"graph shows {actual_n} usage(s), answer claimed {claimed_n}"

    return True, "not a graph-resolvable claim type"


def verify_claims(
    claims: list[Claim], *, graph: Any, messages: list[dict], tool_exit_codes: dict[str, int | None],
    repository: str,
) -> list[tuple[Claim, str]]:
    """Resolves each claim against the graph (structural claims) or this turn's own tool-call
    messages and real exit codes (test/action claims — never against the model's self-report).
    Returns the list of (claim, reason) for claims that did NOT hold."""
    tool_messages = [m for m in messages if m.get("role") == "tool"]
    failed: list[tuple[Claim, str]] = []

    for claim in claims:
        if claim.type in (ClaimType.FILE_EXISTS, ClaimType.SYMBOL_EXISTS, ClaimType.SYMBOL_USED_N_TIMES):
            holds, reason = _resolve_claim(claim, graph=graph, repository=repository)
            if not holds:
                failed.append((claim, reason))
            continue

        if claim.type == ClaimType.TEST_PASSED:
            ran_with_zero_exit = any(
                m.get("name") in _TEST_TOOLS and tool_exit_codes.get(m.get("tool_call_id")) == 0
                for m in tool_messages
            )
            if not ran_with_zero_exit:
                failed.append((claim, "no test/command run this turn exited with code 0 — the pass claim isn't bound to a real successful execution"))
            continue

        if claim.type == ClaimType.ACTION_PERFORMED:
            if claim.target not in _KNOWN_ACTIONS:
                continue  # not an auto-verifiable action name — don't fail on lack of coverage
            performed = any(m.get("name") == claim.target for m in tool_messages)
            if not performed:
                failed.append((claim, f"tool '{claim.target}' was not actually called this turn"))
            continue

    return failed


def build_correction_message(failed: list[tuple["Claim", str]]) -> str:
    lines = [
        "[SYSTEM: your answer made claims that don't check out against the actual code/tool "
        "results. Do not repeat these claims — investigate and either fix the underlying issue or "
        "correct your answer to reflect what's actually true.]",
    ]
    for claim, reason in failed:
        lines.append(f"- Claimed {claim.type.value} for '{claim.target}' ({claim.assertion}): {reason}")
    return "\n".join(lines)
