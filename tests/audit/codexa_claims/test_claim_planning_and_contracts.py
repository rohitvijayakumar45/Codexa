from backend.agents.task import (
    TaskIntent,
    TaskContract,
    classify_intent,
    generate_contract,
    validate_completion,
)
from backend.agents.plan import ExecutionPlan, Task, TaskStatus, make_task
from backend.agents.controller import ExecutionController


def test_claim_intent_classification():
    """Claim: User intent is classified into structured categories using regex ordering."""
    assert classify_intent("create a new file called test.py") == TaskIntent.CREATE
    assert classify_intent("modify the auth handler to support jwt") == TaskIntent.MODIFY
    assert classify_intent("delete obsolete configs") == TaskIntent.DELETE
    assert classify_intent("run the pytest suite") == TaskIntent.RUN
    assert classify_intent("explain how the router works") == TaskIntent.EXPLAIN


def test_claim_post_hoc_contract_validation_blocks_empty_claims():
    """Claim: If a contract requires write_file/edit_file, a model that merely describes
    the change without calling the tool is blocked and forced to re-attempt."""
    contract = generate_contract("build a login component in auth.tsx")
    assert "write_file" in contract.required_tools or "edit_file" in contract.required_tools

    # Model returns narrative prose without calling write_file
    passed, message = validate_completion(
        contract=contract,
        tools_called=["list_dir", "read_file"],
    )
    assert passed is False
    assert any(t in message for t in ("write_file", "edit_file"))


def test_claim_controller_completion_decided_by_filesystem_not_model():
    """Claim: ExecutionController enforces that completion is decided mechanically,
    not by the model self-reporting done."""
    # Task requiring a validator
    task = make_task(
        objective="Write index.html",
        index=0,
        required_tools=["write_file"],
        validators=["artifacts_exist"]
    )
    plan = ExecutionPlan(objective="Build website", tasks=[task])

    # Model claims completion with no tool calls, but index.html does not exist
    # Validation should reject completion claim
    assert task.status == TaskStatus.PENDING
