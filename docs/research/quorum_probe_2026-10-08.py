"""Read-only, scripted Quorum counterexamples. No LLM/API or database calls.

Run from any directory: python <absolute path to this file>
Only output: sibling JSON research artifact. Application files stay unchanged.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
fixture = runpy.run_path(str(ROOT / "tests/test_quorum.py"))
Q = fixture["QuorumService"]
R = fixture["QuorumRunRequest"]
F = fixture["FakeLLM"]
panel = fixture["_PANEL"]
card = fixture["_card"]
graph = fixture["_graph_with_symbol"]("foo")

from backend.agents.verification import Claim, ClaimType  # noqa: E402

service = Q(F(panel, {}), graph)
results = {
    "evidence_kind": "scripted software counterexamples; not real-model research results",
    "network_calls": 0,
    "persistent_graph_writes": 0,
    "zero_confidence_parsed": service._parse(
        '{"answer":"x","confidence":0.0,"claims":[]}'
    )[1],
    "unparseable_count_verification": service._verify(
        [Claim(ClaimType.SYMBOL_USED_N_TIMES, "foo", "many")], repository="demo-repo"
    ),
    "missing_repository_file_verification": service._verify(
        [Claim(ClaimType.FILE_EXISTS, "missing.py", "exists")],
        repository="nonexistent-probe-repository",
    ),
    "outside_repository_absolute_path_verification": service._verify(
        [Claim(ClaimType.FILE_EXISTS, sys.executable, "exists")], repository="codexa-os"
    ),
    "mixed_assertions_same_target_verification": service._verify(
        [Claim(ClaimType.SYMBOL_EXISTS, "foo", "exists"),
         Claim(ClaimType.SYMBOL_USED_N_TIMES, "foo", "99")], repository="demo-repo"
    ),
}


def run(scripts):
    result = Q(F(panel, scripts), graph).run(
        R(repository="demo-repo", query="scripted query", models=panel)
    )
    return {
        "winner": result.winning_answer,
        "resolved": result.resolved,
        "debated": result.debated,
        "cards": [{"answer": c.answer, "verified": c.verified_count,
                   "failed": c.failed_count, "round": c.round} for c in result.cards],
    }


results["majority_ignored"] = run({
    ("quorum", panel[0]): card("correct", 0.8, "foo"),
    ("quorum", panel[1]): card("correct", 0.7, "foo"),
    ("quorum", panel[2]): card("wrong", 0.99, "foo"),
})
results["duplicate_padding"] = run({
    ("quorum", panel[0]): card("correct", 0.8, "foo"),
    ("quorum", panel[1]): json.dumps({
        "answer": "wrong", "confidence": 0.1,
        "claims": [{"type": "symbol_exists", "target": "foo", "assertion": "exists"}] * 5,
    }),
    ("quorum", panel[2]): card("correct", 0.7, "foo"),
})
results["unsupported_revision"] = run({
    ("quorum", panel[0]): card("correct", 0.8, "foo"),
    ("quorum", panel[1]): card("wrong", 0.8, "foo"),
    ("quorum", panel[2]): card("other", 0.2),
    ("quorum_debate", panel[0]): card("wrong", 0.9, "foo"),
    ("quorum_debate", panel[1]): card("wrong", 0.9, "foo"),
})
results["all_failed_still_resolves"] = run({
    ("quorum", panel[0]): card("wrong A", 0.9, "absent"),
    ("quorum", panel[1]): card("wrong B", 0.8, "absent"),
    ("quorum", panel[2]): card("wrong C", 0.7, "absent"),
})
for rel in ["tests/test_quorum.py", "tests/test_verification.py",
            "tests/audit/codexa_claims/test_claim_quorum.py"]:
    tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
    results.setdefault("static_test_counts", {})[rel] = sum(
        isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test_")
        for n in ast.walk(tree)
    )

output = Path(__file__).with_suffix(".json")
output.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
print(json.dumps(results, indent=2))
