import copy
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest

from aioa_cloudops_agent.config import DynamoDbSettings
from aioa_cloudops_agent.nz import (
    ActionProposal,
    ActionTarget,
    Approval,
    ApprovalDecision,
    AuditEvent,
    AuditEventType,
    AuthorityGate,
    BudgetCounters,
    Capability,
    Checkpoint,
    ExpectedPrecondition,
    IdempotencyRecord,
    ObservedInstanceState,
    ProposalState,
    Run,
    WorkflowState,
)
from aioa_cloudops_agent.nz.errors import StorageConflictError, StorageDependencyError
from aioa_cloudops_agent.persistence.nz_dynamodb import DynamoDbDurableTruthRepository
from aioa_cloudops_agent.persistence.semantic_idempotency import build_idempotency_record

RUN_ID = UUID("01890f6c-3311-7abc-8f4a-6e4f7f0b9b3a")
TRACE_ID = UUID("01890f6c-3311-7abc-8f4a-6e4f7f0b9b3b")
CORRELATION_ID = UUID("01890f6c-3311-7abc-8f4a-6e4f7f0b9b3c")
PROPOSAL_ID = UUID("01890f6c-3311-7abc-8f4a-6e4f7f0b9b3d")
OTHER_PROPOSAL_ID = UUID("01890f6c-3311-7abc-8f4a-6e4f7f0b9b3e")
EVENT_ID = UUID("01890f6c-3311-7abc-8f4a-6e4f7f0b9b3f")
NOW = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)
DIGEST = "a" * 64


class ConditionalCheckFailed(Exception):
    def __init__(self) -> None:
        self.response = {"Error": {"Code": "ConditionalCheckFailedException"}}
        super().__init__("conditional write rejected")


class FakeDynamoDbClient:
    def __init__(self) -> None:
        self.items: dict[tuple[str, str], dict[str, Any]] = {}
        self.operations: list[str] = []
        self.requests: list[dict[str, Any]] = []
        self.fail_operations: set[str] = set()

    @staticmethod
    def _key(value: dict[str, Any]) -> tuple[str, str]:
        return value["PK"]["S"], value["SK"]["S"]

    def _record(self, operation: str, request: dict[str, Any]) -> None:
        self.operations.append(operation)
        self.requests.append(copy.deepcopy(request))
        if operation in self.fail_operations:
            raise RuntimeError(f"synthetic {operation} dependency failure")

    def put_item(self, **kwargs: Any) -> dict[str, Any]:
        self._record("PutItem", kwargs)
        item = kwargs["Item"]
        key = self._key(item)
        if key in self.items:
            raise ConditionalCheckFailed
        self.items[key] = copy.deepcopy(item)
        return {}

    def get_item(self, **kwargs: Any) -> dict[str, Any]:
        self._record("GetItem", kwargs)
        item = self.items.get(self._key(kwargs["Key"]))
        return {} if item is None else {"Item": copy.deepcopy(item)}

    def update_item(self, **kwargs: Any) -> dict[str, Any]:
        self._record("UpdateItem", kwargs)
        key = self._key(kwargs["Key"])
        item = self.items.get(key)
        if item is None:
            raise ConditionalCheckFailed
        names = kwargs["ExpressionAttributeNames"]
        values = kwargs["ExpressionAttributeValues"]
        for clause in kwargs["ConditionExpression"].split(" AND "):
            name_token, value_token = clause.strip().split(" = ")
            if item.get(names[name_token]) != values[value_token]:
                raise ConditionalCheckFailed
        assignments = kwargs["UpdateExpression"].removeprefix("SET ").split(", ")
        for assignment in assignments:
            name_token, value_token = assignment.split(" = ")
            item[names[name_token]] = copy.deepcopy(values[value_token])
        return {}


def _repository(
    client: FakeDynamoDbClient | None = None,
) -> tuple[FakeDynamoDbClient, DynamoDbDurableTruthRepository]:
    actual_client = client or FakeDynamoDbClient()
    return actual_client, DynamoDbDurableTruthRepository(
        actual_client,
        DynamoDbSettings(table_name="state-table"),
    )


def _run() -> Run:
    return Run(
        run_id=RUN_ID,
        trace_id=TRACE_ID,
        correlation_id=CORRELATION_ID,
        idempotency_key="request:idle-ec2:0001",
        state=WorkflowState.RECEIVED,
        created_at=NOW,
        updated_at=NOW,
        budget=BudgetCounters(max_turns=8, max_tokens=8_192),
    )


def _proposal(
    *,
    proposal_id: UUID = PROPOSAL_ID,
    state: ProposalState = ProposalState.PROPOSED,
) -> ActionProposal:
    return ActionProposal(
        proposal_id=proposal_id,
        run_id=RUN_ID,
        action=Capability.STOP_SANDBOX_INSTANCE,
        target=ActionTarget(
            resource_id="i-0123456789abcdef0",
            sandbox_scope="hackathon-sandbox",
        ),
        expected_precondition=ExpectedPrecondition(
            instance_state=ObservedInstanceState.RUNNING,
            observed_at=NOW,
            evidence_hash=DIGEST,
        ),
        authority=AuthorityGate.PLAN_AND_CONFIRM,
        state=state,
        evidence_hash=DIGEST,
        created_at=NOW,
    )


def _approval() -> Approval:
    proposal = _proposal(state=ProposalState.AWAITING_APPROVAL)
    return Approval(
        proposal_id=PROPOSAL_ID,
        run_id=RUN_ID,
        action=proposal.action,
        target=proposal.target,
        evidence_hash=proposal.evidence_hash,
        interrupt_id="v1:before_tool_call:stop-1",
        request_hash="f" * 64,
        decision=ApprovalDecision.APPROVED,
        decided_at=NOW + timedelta(seconds=5),
        actor_session_id="human-session-001",
        decision_nonce="nonce-approved-0001",
    )


def _prepare_approved_repository() -> tuple[
    FakeDynamoDbClient,
    DynamoDbDurableTruthRepository,
    ActionProposal,
]:
    client, repository = _repository()
    run = repository.create_run(_run())
    for offset, state in enumerate(
        (
            WorkflowState.INVESTIGATING,
            WorkflowState.EVIDENCE_READY,
            WorkflowState.REMEDIATION_PROPOSED,
        ),
        start=1,
    ):
        run = repository.transition_run(
            RUN_ID,
            state,
            expected_state=run.state,
            expected_version=run.version,
            updated_at=NOW + timedelta(seconds=offset),
        )
    proposal = repository.create_proposal(_proposal())
    proposal = repository.transition_proposal(
        PROPOSAL_ID,
        ProposalState.AWAITING_APPROVAL,
        expected_state=ProposalState.PROPOSED,
    )
    run = repository.transition_run(
        RUN_ID,
        WorkflowState.AWAITING_APPROVAL,
        expected_state=WorkflowState.REMEDIATION_PROPOSED,
        expected_version=run.version,
        updated_at=NOW + timedelta(seconds=4),
    )
    repository.create_approval(_approval())
    repository.transition_run(
        RUN_ID,
        WorkflowState.APPROVED,
        expected_state=WorkflowState.AWAITING_APPROVAL,
        expected_version=run.version,
        updated_at=NOW + timedelta(seconds=6),
        approval_proposal_id=PROPOSAL_ID,
    )
    return client, repository, proposal


def test_run_round_trip_and_conditional_transition_use_consistent_reads() -> None:
    client, repository = _repository()
    run = repository.create_run(_run())

    assert repository.get_run(RUN_ID) == run
    updated = repository.transition_run(
        RUN_ID,
        WorkflowState.INVESTIGATING,
        expected_state=WorkflowState.RECEIVED,
        expected_version=1,
        updated_at=NOW + timedelta(seconds=1),
    )

    assert updated.state is WorkflowState.INVESTIGATING
    assert updated.version == 2
    assert repository.get_run(RUN_ID) == updated
    assert all(
        request["ConsistentRead"] is True
        for request in client.requests
        if "Key" in request and "UpdateExpression" not in request
    )
    update = next(request for request in client.requests if "UpdateExpression" in request)
    assert update["ConditionExpression"] == (
        "#state = :expected_state AND #version = :expected_version"
    )


def test_duplicate_run_and_stale_state_fail_closed() -> None:
    _, repository = _repository()
    repository.create_run(_run())

    with pytest.raises(StorageConflictError, match="already exists"):
        repository.create_run(_run())
    with pytest.raises(StorageConflictError, match="state or version"):
        repository.transition_run(
            RUN_ID,
            WorkflowState.INVESTIGATING,
            expected_state=WorkflowState.EVIDENCE_READY,
            expected_version=3,
            updated_at=NOW + timedelta(seconds=1),
        )


def test_proposal_and_approval_use_separate_create_only_items() -> None:
    client, repository = _repository()
    proposal = repository.create_proposal(_proposal())
    awaiting = repository.transition_proposal(
        PROPOSAL_ID,
        ProposalState.AWAITING_APPROVAL,
        expected_state=ProposalState.PROPOSED,
    )

    assert repository.get_proposal(PROPOSAL_ID) == awaiting
    assert repository.get_approval(PROPOSAL_ID) is None
    approval = repository.create_approval(_approval())
    assert repository.get_approval(PROPOSAL_ID) == approval
    assert proposal.authorizes_execution is False
    assert repository.create_approval(_approval()) == approval
    partition_keys = {key[0] for key in client.items}
    assert f"PROPOSAL#{PROPOSAL_ID}" in partition_keys
    assert (f"PROPOSAL#{PROPOSAL_ID}", "APPROVAL") in client.items


def test_idempotency_registration_reconciles_exact_duplicate() -> None:
    client, repository, proposal = _prepare_approved_repository()
    record = build_idempotency_record(
        proposal,
        registered_at=NOW + timedelta(seconds=7),
    )

    assert repository.register_idempotency(record) == record
    assert repository.register_idempotency(record) == record
    assert repository.get_idempotency(record.idempotency_key) == record
    put_requests = [
        request
        for operation, request in zip(client.operations, client.requests, strict=True)
        if operation == "PutItem" and request["Item"]["entity_type"] == {"S": "IDEMPOTENCY"}
    ]
    assert len(put_requests) == 1
    assert all("attribute_not_exists(PK)" in request["ConditionExpression"] for request in put_requests)


def test_idempotency_collision_with_inconsistent_payload_fails() -> None:
    _, repository, proposal = _prepare_approved_repository()
    record = build_idempotency_record(
        proposal,
        registered_at=NOW + timedelta(seconds=7),
    )
    repository.register_idempotency(record)
    conflict = IdempotencyRecord(
        idempotency_key=record.idempotency_key,
        proposal_id=OTHER_PROPOSAL_ID,
        action_fingerprint="b" * 64,
        registered_at=NOW + timedelta(seconds=7),
    )

    with pytest.raises(StorageConflictError, match="incompatible ownership"):
        repository.register_idempotency(conflict)


def test_checkpoint_and_audit_records_are_conditional_and_retrievable() -> None:
    client, repository = _repository()
    first = Checkpoint(
        run_id=RUN_ID,
        last_safe_state=WorkflowState.EVIDENCE_READY,
        resume_metadata={"evidence": "ready"},
        tool_result_hashes={"inspect_instance": DIGEST},
        created_at=NOW,
        version=1,
    )
    second = Checkpoint.model_validate(
        {
            **first.model_dump(),
            "last_safe_state": WorkflowState.REMEDIATION_PROPOSED,
            "created_at": NOW + timedelta(seconds=1),
            "version": 2,
        }
    )
    event = AuditEvent(
        event_id=EVENT_ID,
        run_id=RUN_ID,
        type=AuditEventType.CHECKPOINT_SAVED,
        timestamp=NOW,
        source="nz-control-plane",
        redacted_payload_hash=DIGEST,
    )

    repository.save_checkpoint(first, expected_version=None)
    repository.save_checkpoint(second, expected_version=1)
    repository.append_audit_event(event)

    assert repository.get_checkpoint(RUN_ID) == second
    assert repository.get_audit_event(RUN_ID, EVENT_ID) == event
    with pytest.raises(StorageConflictError, match="already exists"):
        repository.append_audit_event(event)
    assert {operation for operation in client.operations} <= {"GetItem", "PutItem", "UpdateItem"}


def test_dependency_failure_is_not_misreported_as_missing_state() -> None:
    client, repository = _repository()

    assert repository.get_run(RUN_ID) is None
    client.fail_operations.add("GetItem")
    with pytest.raises(StorageDependencyError, match="unable to read RUN") as captured:
        repository.get_run(RUN_ID)
    assert captured.value.retryable is True


def test_malformed_stored_payload_fails_as_dependency_error() -> None:
    client, repository = _repository()
    repository.create_run(_run())
    client.items[(f"RUN#{RUN_ID}", "META")]["record"] = {"S": "malformed"}

    with pytest.raises(StorageDependencyError, match="not a map"):
        repository.get_run(RUN_ID)


def test_adapter_has_no_scan_delete_or_cloudops_mutation_operations() -> None:
    _, repository = _repository()

    for operation in (
        "scan",
        "delete_item",
        "delete_table",
        "batch_write_item",
        "stop_instances",
        "terminate_instances",
        "execute_mutation",
    ):
        assert not hasattr(repository, operation)
