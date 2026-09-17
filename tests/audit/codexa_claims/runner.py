"""Master Audit Runner: Executes all claim verification test suites and dumps
structured empirical evidence to tests/audit/codexa_claims/evidence/
"""

import sys
import os
import json
import time
from pathlib import Path
import pytest

AUDIT_DIR = Path(__file__).parent
EVIDENCE_DIR = AUDIT_DIR / "evidence"
EVIDENCE_DIR.mkdir(exist_ok=True)

# Add project root to sys.path
PROJECT_ROOT = AUDIT_DIR.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def run_test_module(module_path: Path) -> dict:
    start_time = time.time()
    # Run pytest directly against the module
    result = pytest.main([str(module_path), "-v", "--capture=sys"])
    duration = time.time() - start_time
    
    return {
        "module": module_path.name,
        "exit_code": int(result),
        "status": "PASSED" if result == 0 else "FAILED",
        "duration_seconds": round(duration, 3),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def main():
    print("=" * 70)
    print("CODEXA COMPREHENSIVE CLAIMS AND NOVELTY AUDIT HARNESS")
    print("=" * 70)

    test_modules = [
        AUDIT_DIR / "test_claim_graph_and_projections.py",
        AUDIT_DIR / "test_claim_treesitter.py",
        AUDIT_DIR / "test_claim_memory.py",
        AUDIT_DIR / "test_claim_strata.py",
        AUDIT_DIR / "test_claim_quorum.py",
        AUDIT_DIR / "test_claim_planning_and_contracts.py",
        AUDIT_DIR / "test_claim_simulation_and_sandbox.py",
        AUDIT_DIR / "test_claim_security_and_trust_boundary.py",
        AUDIT_DIR / "test_claim_resilience_and_recovery.py",
        AUDIT_DIR / "test_claim_e2e_and_failures.py",
    ]

    summary = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_suites": len(test_modules),
        "suites": [],
        "overall_status": "PASSED",
    }

    for mod in test_modules:
        print(f"\n---> Running suite: {mod.name}")
        report = run_test_module(mod)
        summary["suites"].append(report)
        
        # Save individual suite evidence
        evidence_file = EVIDENCE_DIR / f"{mod.stem}_evidence.json"
        evidence_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"     Result: {report['status']} in {report['duration_seconds']}s")

    if any(s["status"] == "FAILED" for s in summary["suites"]):
        summary["overall_status"] = "FAILED"

    # Save master summary evidence
    master_evidence = EVIDENCE_DIR / "master_audit_evidence.json"
    master_evidence.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    
    print("\n" + "=" * 70)
    print(f"AUDIT EXECUTION COMPLETE. Overall: {summary['overall_status']}")
    print(f"Evidence directory: {EVIDENCE_DIR}")
    print("=" * 70)

    return 0 if summary["overall_status"] == "PASSED" else 1


if __name__ == "__main__":
    sys.exit(main())
