"""Quorum mode — multiple independently-answering agents, checked against the real graph before
any of them ever sees a peer's answer, with a structured (never free-text) debate round as the
fallback for whatever the graph genuinely can't settle.

The point this exists to fix: unrestricted natural-language debate between LLM agents is a proven
vector for sycophantic conformity — a confidently-worded wrong answer can talk a correct agent out
of its own answer, and terminal majority voting is blind to which answer was actually grounded in
the code versus just persuasively phrased. This module avoids both failure modes the same way the
rest of this codebase avoids LLM-judged correctness elsewhere (backend/agents/verification.py,
backend/agents/receipts.py): claims are checked deterministically against the graph/filesystem, and
only genuine ties — claims the graph can't resolve either way — ever reach a debate round. When they
do, agents exchange structured belief cards (answer + confidence + which specific claims verified),
never raw argumentative prose, and may only revise on a peer's VERIFIED claim, never on confidence or
tone.
"""

from __future__ import annotations

import json
import re
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from backend.agents.llm import LLMClient
from backend.agents.verification import Claim, ClaimType, verify_claims
from backend.graph.schemas import GraphNodeCreate, GraphNodeProvenance, GraphNodeType
from backend.graph.service import GraphService

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)
# A reasoning-capable model (GLM/DeepSeek thinking mode, etc.) can emit its chain-of-thought inline
# in the completion text wrapped in <think> tags rather than as a separate reasoning field — stripped
# before JSON extraction so a verbose thought trace is never mistaken for (or leaked into) an answer.
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_MAX_CLAIMS = 5
# Below this many historically-verified-or-failed claims for a model, its calibration score isn't
# trusted yet — same cold-start guard as backend/agents/token_budget.py's MIN_SAMPLES_TO_TRUST_AVERAGE,
# so one unlucky early run doesn't permanently brand a model as unreliable off a tiny sample.
_MIN_CALIBRATION_SAMPLES = 5
# Generous enough that a reasoning model's <think> pass plus the actual JSON answer both fit in one
# completion — too small a budget here means the call gets cut off mid-thought with no JSON at all,
# which is a worse failure than the extra tokens this costs.
_MAX_TOKENS = 2000
_PANEL_SIZE = 3

# Only the claim types verify_claims can resolve without a tool-call log (no tools run in quorum
# mode) — TEST_PASSED/ACTION_PERFORMED would always fail here for reasons unrelated to correctness.
_ALLOWED_CLAIM_TYPES = {ClaimType.FILE_EXISTS, ClaimType.SYMBOL_EXISTS, ClaimType.SYMBOL_USED_N_TIMES}

_ANSWER_PROMPT = (
    "You are one independent agent on a panel answering the same question — you cannot see the "
    "other agents' answers. Answer the question about the repository '{repository}' as accurately "
    "as you can, using ONLY the real listing below — never guess from the repository's name or from "
    "general knowledge of what a project by that name usually contains.\n\n"
    "Actual repository contents:\n{repo_listing}\n\nQuestion: {query}\n\n"
    "Respond with ONLY a JSON object (no markdown fences, no commentary) shaped exactly like: "
    '{{"answer": "your answer, 2-6 sentences", "confidence": 0.0-1.0, '
    '"claims": [{{"type": "file_exists|symbol_exists|symbol_used_n_times", '
    '"target": "file path or symbol name", "assertion": "what you assert, e.g. a usage count"}}]}}. '
    f"List at most {_MAX_CLAIMS} claims — only ones CHECKABLE against the real repository (a file "
    "existing, a symbol existing, a symbol's usage count). If your answer makes no checkable claims, "
    "use an empty claims list. Never claim a test passed or an action was performed — no tools ran "
    "for this question."
)

_DEBATE_PROMPT = (
    "You are one of several agents that answered the same question independently. Your answer tied "
    "with at least one peer after each answer's claims were checked against the real repository. "
    "Below is your own answer and verification result, and a summary of each tied peer's.\n\n"
    "Your answer: {own_answer}\n"
    "Your claim verification: {own_verification}\n\n"
    "Peer answers and their verification:\n{peer_summary}\n\n"
    "Revise your answer ONLY if a peer cites a SPECIFIC claim that verified against the repository "
    "and contradicts or is missing from your own answer. Do not change your answer because a peer "
    "sounds more confident or is more persuasively worded — confidence and phrasing are not evidence. "
    "If your own claims verified and a peer's didn't, keep your answer as-is.\n\n"
    "Respond with ONLY a JSON object in the same shape as before: "
    '{{"answer": "...", "confidence": 0.0-1.0, "claims": [...]}}.'
)


class BeliefCardClaim(BaseModel):
    type: str
    target: str
    assertion: str


class BeliefCard(BaseModel):
    model: str
    answer: str
    confidence: float = Field(ge=0, le=1)
    claims: list[BeliefCardClaim]
    verified_count: int
    failed_count: int
    failed_reasons: list[str]
    round: int
    # This model's historical hit-rate on claims it has made across past Quorum runs (1.0 = neutral,
    # not enough history yet) — computed from every prior QuorumDecision already sitting in the
    # graph, not a separate store. Used to discount stated confidence when ranking; kept on the card
    # too so the UI can show it, not just apply it invisibly.
    calibration: float = 1.0


class QuorumRunRequest(BaseModel):
    repository: str = Field(min_length=1, max_length=100)
    query: str = Field(min_length=1, max_length=2000)
    models: list[str] | None = None  # override the auto-picked panel — mainly for tests


class QuorumRunResult(BaseModel):
    quorum_id: UUID
    query: str
    winning_answer: str | None
    winning_confidence: float | None
    resolved: bool  # False when the panel ended in a genuine, ungrounded tie
    cards: list[BeliefCard]  # every agent's final card (post-debate, if a debate round happened)
    debated: bool
    decision_node_id: UUID


class QuorumService:
    def __init__(self, llm: LLMClient, graph: GraphService) -> None:
        self.llm = llm
        self.graph = graph

    def run(self, request: QuorumRunRequest) -> QuorumRunResult:
        panel = self._panel_models(request.models)
        repo_listing = self._repo_listing(request.repository)  # computed once, shared by the whole panel
        cards = [self._ask(model, request, repo_listing) for model in panel]

        debated = False
        best = self._rank(cards)
        # A tie only needs a debate round if the tied cards actually disagree — several agents
        # independently landing on the same, equally-verified answer is agreement, not a conflict
        # to resolve, and shouldn't cost a second LLM round per agent for no reason.
        if len(best) > 1 and len({c.answer for c in best}) > 1:
            debated = True
            cards = self._debate_round(cards, best, request)
            best = self._rank(cards)

        # Resolved whenever the surviving top-scored cards agree on the answer text — whether
        # that's a single winner, or several agents landing on the identical answer independently
        # (or after debate). Only a real, still-disagreeing tie counts as unresolved.
        distinct_answers = {c.answer for c in best}
        winner = best[0] if len(distinct_answers) == 1 else None
        resolved = winner is not None

        decision_node = self._record(request, cards, winner, resolved, debated)
        return QuorumRunResult(
            quorum_id=uuid4(), query=request.query,
            winning_answer=winner.answer if winner else None,
            winning_confidence=winner.confidence if winner else None,
            resolved=resolved, cards=cards, debated=debated,
            decision_node_id=decision_node.id,
        )

    def _panel_models(self, override: list[str] | None) -> list[str]:
        if override:
            return override
        # A panel of clones of one model shares its training data and its blind spots — pull from
        # different providers first so the panel is genuinely heterogeneous, falling back to
        # whatever's available if this deployment only has one provider configured.
        candidates: list[str] = []
        for tier in ("balanced", "heavy", "light"):
            candidates.extend(self.llm.models_for_tier(tier))
        seen_providers: set[str] = set()
        panel: list[str] = []
        for model in candidates:
            provider = model.split("/", 1)[0]
            if provider in seen_providers:
                continue
            seen_providers.add(provider)
            panel.append(model)
            if len(panel) == _PANEL_SIZE:
                break
        if len(panel) < min(_PANEL_SIZE, len(candidates)):
            # Fewer distinct providers than the target panel size — fill the rest even if it means
            # repeating a provider, rather than running a smaller-than-configured panel.
            for model in candidates:
                if model not in panel:
                    panel.append(model)
                if len(panel) == _PANEL_SIZE:
                    break
        return panel

    def _ask(self, model: str, request: QuorumRunRequest, repo_listing: str) -> BeliefCard:
        prompt = _ANSWER_PROMPT.format(repository=request.repository, query=request.query, repo_listing=repo_listing)
        raw = self.llm.complete(
            [{"role": "user", "content": prompt}], model=model, agent="quorum", max_tokens=_MAX_TOKENS,
        )
        return self._card_from_raw(model, raw, request.repository, round_=1)

    def _repo_listing(self, repository: str) -> str:
        """The only grounding a panel agent gets before answering — a real listing of this
        repository's files and symbols, so "does X exist" is answered by reading an actual list
        instead of guessed from the repository's name. Bounded so a large repo doesn't blow the
        prompt budget; verify_claims() remains the real authority on any specific assertion after
        this (an agent can still misread the list — the listing narrows guessing, it doesn't replace
        verification)."""
        nodes = self.graph.list_nodes()

        def in_repo(n) -> bool:
            repo_prop = n.properties.get("repository")
            return (not repo_prop) if repository == "codexa-os" else repo_prop == repository

        files = sorted({n.properties.get("path", "") for n in nodes if n.node_type == "File" and in_repo(n)} - {""})
        symbols = sorted({n.properties.get("name", "") for n in nodes if n.node_type == "CodeSymbol" and in_repo(n)} - {""})
        if not files and not symbols:
            return "(no files or symbols are indexed for this repository)"
        parts = []
        if files:
            parts.append("Files:\n" + "\n".join(files[:120]))
        if symbols:
            parts.append("Symbols:\n" + ", ".join(symbols[:200]))
        return "\n\n".join(parts)

    def _card_from_raw(self, model: str, raw: str, repository: str, *, round_: int) -> BeliefCard:
        answer, confidence, claims = self._parse(raw)
        verified, failed, reasons = self._verify(claims, repository=repository)
        return BeliefCard(
            model=model, answer=answer, confidence=confidence,
            claims=[BeliefCardClaim(type=c.type.value, target=c.target, assertion=c.assertion) for c in claims],
            verified_count=verified, failed_count=failed, failed_reasons=reasons, round=round_,
            calibration=self._model_calibration(model),
        )

    def _model_calibration(self, model: str) -> float:
        """This model's historical hit-rate — verified / (verified + failed) claims — across every
        past QuorumDecision node already persisted in the graph. No separate tracking store: every
        run's belief cards are already written to the graph (self._record below), so this is a pure
        query over data that already exists, the same "reuse what's already logged" pattern as
        backend/agents/token_budget.py reading UsageTracker instead of keeping its own counters."""
        verified = failed = 0
        for node in self.graph.list_nodes():
            if node.node_type != GraphNodeType.QUORUM_DECISION:
                continue
            for card in node.properties.get("cards", []):
                if card.get("model") == model:
                    verified += card.get("verified_count", 0)
                    failed += card.get("failed_count", 0)
        total = verified + failed
        if total < _MIN_CALIBRATION_SAMPLES:
            return 1.0
        return verified / total

    def _parse(self, raw: str) -> tuple[str, float, list[Claim]]:
        raw = _THINK_BLOCK.sub("", raw).strip()
        fallback_answer = raw.strip()[:2000] or "No answer produced."
        match = _JSON_BLOCK.search(raw)
        if not match:
            return fallback_answer, 0.3, []
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return fallback_answer, 0.3, []
        answer = str(data.get("answer") or "").strip() or fallback_answer
        try:
            confidence = max(0.0, min(1.0, float(data.get("confidence") or 0.5)))
        except (TypeError, ValueError):
            confidence = 0.5
        claims: list[Claim] = []
        for c in (data.get("claims") or [])[:_MAX_CLAIMS]:
            if not isinstance(c, dict):
                continue
            try:
                ctype = ClaimType(c.get("type"))
            except ValueError:
                continue
            if ctype not in _ALLOWED_CLAIM_TYPES:
                continue
            target, assertion = c.get("target"), c.get("assertion")
            if isinstance(target, str) and target and isinstance(assertion, str):
                claims.append(Claim(type=ctype, target=target, assertion=assertion))
        return answer, confidence, claims

    def _verify(self, claims: list[Claim], *, repository: str) -> tuple[int, int, list[str]]:
        if not claims:
            return 0, 0, []
        failed = verify_claims(claims, graph=self.graph, messages=[], tool_exit_codes={}, repository=repository)
        failed_targets = {c.target for c, _ in failed}
        verified_count = sum(1 for c in claims if c.target not in failed_targets)
        return verified_count, len(failed), [reason for _, reason in failed]

    def _rank(self, cards: list[BeliefCard]) -> list[BeliefCard]:
        # Verified-minus-failed claims is ground truth against the real repository, so it dominates
        # the ranking. Confidence only breaks ties between cards the graph can't already tell apart —
        # and even then, it's discounted by the model's own track record: a model that talks
        # confidently but has historically been wrong a lot shouldn't win a tie on raw bravado alone.
        if not cards:
            return []

        def score(card: BeliefCard) -> tuple[int, float]:
            return (card.verified_count - card.failed_count, card.confidence * card.calibration)

        ranked = sorted(cards, key=score, reverse=True)
        top_score = score(ranked[0])
        return [c for c in ranked if score(c) == top_score]

    def _debate_round(
        self, all_cards: list[BeliefCard], tied: list[BeliefCard], request: QuorumRunRequest,
    ) -> list[BeliefCard]:
        tied_models = {c.model for c in tied}
        revised: list[BeliefCard] = []
        for card in all_cards:
            if card.model not in tied_models:
                revised.append(card)
                continue
            peers = [c for c in tied if c.model != card.model]
            peer_summary = "\n".join(
                f"- {p.model}: \"{p.answer}\" ({p.verified_count} verified, {p.failed_count} failed"
                f"{': ' + '; '.join(p.failed_reasons) if p.failed_reasons else ''})"
                for p in peers
            )
            prompt = _DEBATE_PROMPT.format(
                own_answer=card.answer,
                own_verification=(
                    f"{card.verified_count} verified, {card.failed_count} failed"
                    f"{': ' + '; '.join(card.failed_reasons) if card.failed_reasons else ''}"
                ),
                peer_summary=peer_summary or "(no tied peer)",
            )
            raw = self.llm.complete(
                [{"role": "user", "content": prompt}], model=card.model, agent="quorum_debate",
                max_tokens=_MAX_TOKENS,
            )
            revised.append(self._card_from_raw(card.model, raw, request.repository, round_=2))
        return revised

    def _record(
        self, request: QuorumRunRequest, cards: list[BeliefCard], winner: BeliefCard | None,
        resolved: bool, debated: bool,
    ):
        return self.graph.add_node(GraphNodeCreate(
            node_type=GraphNodeType.QUORUM_DECISION,
            stable_id=f"quorum://{uuid4()}",
            properties={
                "repository": request.repository,
                "query": request.query,
                "resolved": resolved,
                "debated": debated,
                "winning_model": winner.model if winner else None,
                "winning_answer": winner.answer if winner else None,
                "cards": [c.model_dump() for c in cards],
            },
            # Assembled from the user's own question plus deterministic graph verification of each
            # agent's claims — not external content — so this is trusted-user-originated data.
            provenance=GraphNodeProvenance.TRUSTED_USER,
        ))
