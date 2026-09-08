"""Graph-grounded causal explanations — no LLM, no free text.

An explanation is assembled ONLY by templating over CAUSAL_EVENT/PREVENTION_RULE nodes and the
CAUSES/MITIGATES edges connecting them (the causal chain backend/trust_safety/incident.py writes:
incident -> root_cause -> fix / regression_test / prevention_rule). Every sentence in the output
carries the node/edge ids that back it; a link with no node on one end (that stage of the chain was
never recorded) is simply omitted — never fabricated, never smoothed over with a guess. This is the
deliberate alternative to asking an LLM to summarize "why did this happen": an LLM can produce a
fluent explanation that references something wasn't actually in the graph, which is exactly the kind
of unverifiable claim backend/agents/verification.py exists to catch on the *chat* side. Here, on the
audit side, we sidestep the problem instead of catching it after the fact — templating over real
edges cannot invent a fact that isn't there.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

_STAGE_ORDER = ("incident", "root_cause", "fix", "regression_test")


@dataclass
class ExplanationSentence:
    text: str
    node_ids: list[UUID]
    edge_ids: list[UUID]


@dataclass
class Explanation:
    # `sentences` already carries each claim's backing node/edge ids — a UI drilling from
    # "why" to the exact graph records that produced it reads those directly rather than a
    # separately-flattened view of the same data.
    narrative: str
    sentences: list[ExplanationSentence] = field(default_factory=list)


def explain_incident(source_artifact_id: UUID, *, graph: Any) -> Explanation:
    """Builds a causal-chain explanation for one incident-learning record, purely from graph
    traversal. Returns an empty narrative (not an error) if nothing was ever recorded for this id —
    "no explanation available" is itself an honest answer, never replaced with a guess."""
    tag = str(source_artifact_id)
    nodes = graph.list_nodes()
    edges = [e for e in graph.list_edges_at() if e.edge_type in ("causes", "mitigates")]

    causal_by_kind: dict[str, Any] = {}
    prevention_rule = None
    for n in nodes:
        if n.properties.get("source_artifact_id") != tag:
            continue
        if n.node_type == "CausalEvent":
            causal_by_kind[n.properties.get("event_kind")] = n
        elif n.node_type == "PreventionRule":
            prevention_rule = n

    def edge_between(from_node, to_node, edge_type: str):
        if from_node is None or to_node is None:
            return None
        return next(
            (e for e in edges if e.edge_type == edge_type and e.from_node_id == from_node.id and e.to_node_id == to_node.id),
            None,
        )

    incident = causal_by_kind.get("incident")
    root_cause = causal_by_kind.get("root_cause")
    fix = causal_by_kind.get("fix")
    regression_test = causal_by_kind.get("regression_test")

    sentences: list[ExplanationSentence] = []

    if incident is not None:
        sentences.append(ExplanationSentence(
            text=f"Incident: {incident.properties.get('summary')}.",
            node_ids=[incident.id], edge_ids=[],
        ))

    cause_edge = edge_between(root_cause, incident, "causes")
    if root_cause is not None and cause_edge is not None:
        confidence = incident.properties.get("confidence") if incident else None
        conf_text = f" (confidence {round(confidence * 100)}%)" if isinstance(confidence, (int, float)) else ""
        sentences.append(ExplanationSentence(
            text=f"Caused by: {root_cause.properties.get('summary')}{conf_text}.",
            node_ids=[root_cause.id], edge_ids=[cause_edge.id],
        ))

    fix_edge = edge_between(fix, root_cause, "mitigates")
    if fix is not None and fix_edge is not None:
        sentences.append(ExplanationSentence(
            text=f"Fixed by: {fix.properties.get('summary')}.",
            node_ids=[fix.id], edge_ids=[fix_edge.id],
        ))

    test_edge = edge_between(regression_test, incident, "mitigates")
    if regression_test is not None and test_edge is not None:
        sentences.append(ExplanationSentence(
            text=f"Regression test added: {regression_test.properties.get('summary')}.",
            node_ids=[regression_test.id], edge_ids=[test_edge.id],
        ))

    rule_edge = edge_between(prevention_rule, root_cause, "mitigates")
    if prevention_rule is not None and rule_edge is not None:
        sentences.append(ExplanationSentence(
            text=f"Prevention rule in place: {prevention_rule.properties.get('summary')}.",
            node_ids=[prevention_rule.id], edge_ids=[rule_edge.id],
        ))

    narrative = " ".join(s.text for s in sentences) if sentences else "No incident record found for this id."
    return Explanation(narrative=narrative, sentences=sentences)
