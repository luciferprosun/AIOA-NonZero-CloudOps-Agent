import io
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from pydantic import ValidationError

from aioa_cloudops_agent.config import SandboxRemediationSettings
from aioa_cloudops_agent.domain import AuthorityGate
from aioa_cloudops_agent.nz import (
    ActionProposal,
    ActionTarget,
    Approval,
    ApprovalDecision,
    BudgetCounters,
    Capability,
    Checkpoint,
    ExecutionAcknowledgement,
    ExpectedPrecondition,
    FailureKind,
    IdempotencyStatus,
    ObservedInstanceState,
    ProposalState,
    ResultStatus,
    Run,
    WorkflowState,
)
from aioa_cloudops_agent.persistence import (
    load_execution_prerequisites,
    register_approved_action,
)
from aioa_cloudops_agent.persistence.memory import InMemoryTestDurableTruthRepository
from aioa_cloudops_agent.remediation import (
    Ec2SandboxStopExecutor,
    LambdaPrivateRemediationExecutor,
    RemediationAmbiguousError,
    RemediationDependencyError,
    RemediationDisabledError,
    RemediationScopeError,
    StopExecutionCommand,
    StopSandboxInstanceCoordinator,
    build_stop_execution_command,
    create_stop_sandbox_instance_tool,
)

INSTANCE_ID = "i-0123456789abcdef0"
OTHER_INSTANCE_ID = "i-0fedcba9876543210"
RUN_ID = UUID("01890f6c-3311-7abc-8f4a-6e4f7f0b9b3a")
TRACE_ID = UUID("01890f6c-3311-7abc-8f4a-6e4f7f0b9b3b")
CORRELATION_ID = UUID("01890f6c-3311-7abc-8f4a-6e4f7f0b9b3c")
PROPOSAL_ID = UUID("01890f6c-3311-7abc-8f4a-6e4f7f0b9b3d")
EVENT_IDS = tuple(
    UUID(f"01890f6c-3311-7abc-8f4a-6e4f7f0b9b{value:02x}")
    for value in range(100, 120)
)
NOW = datetime(2026, 8, 23, 19, 0, tzinfo=UTC)
DIGEST = "a" * 64
REQUEST_HASH = "b" * 64


class EventIdFactory:
    def __init__(self) -> None:
        self.index = 0

    def __call__(self) -> UUID:
        value = EVENT_IDS[self.index]
        self.index += 1
        return value


class RecordingPrivateExecutor:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.commands: list[StopExecutionCommand] = []

    def execute(self, command: StopExecutionCommand) -> ExecutionAcknowledgement:
        self.commands.append(command)
        if self.error is not None:
            raise self.error
        return ExecutionAcknowledgement(
            proposal_id=command.proposal_id,
            run_id=command.run_id,
            target=command.target,
            current_state=ObservedInstanceState.STOPPING,
            request_reference="request-safe-001",
            acknowledged_at=NOW + timedelta(seconds=20),
            acknowledgement_hash="c" * 64,
        )


class FakeAwsError(Exception):
    def __init__(self, code: str) -> None:
        self.response = {"Error": {"Code": code}}


class FakeEc2StopClient:
    def __init__(
        self,
        *,
        instance_id: str = INSTANCE_ID,
        state: str = "running",
        root_device_type: str = "ebs",
        tag_value: str = "true",
        actual_error: Exception | None = None,
    ) -> None:
        self.instance_id = instance_id
        self.state = state
        self.root_device_type = root_device_type
        self.tag_value = tag_value
        self.actual_error = actual_error
        self.describe_calls: list[list[str]] = []
        self.stop_calls: list[dict[str, object]] = []

    def describe_instances(self, *, InstanceIds: list[str]) -> dict[str, object]:
        self.describe_calls.append(InstanceIds)
        return {
            "Reservations": [
                {
                    "Instances": [
                        {
                            "InstanceId": self.instance_id,
                            "State": {"Name": self.state},
                            "RootDeviceType": self.root_device_type,
                            "Tags": [
                                {
                                    "Key": "AIOACloudOpsSandbox",
                                    "Value": self.tag_value,
                                }
                            ],
                        }
                    ]
                }
            ]
        }

    def stop_instances(
        self,
        *,
        InstanceIds: list[str],
        DryRun: bool = False,
    ) -> dict[str, object]:
        self.stop_calls.append({"InstanceIds": InstanceIds, "DryRun": DryRun})
        if DryRun:
            raise FakeAwsError("DryRunOperation")
        if self.actual_error is not None:
            raise self.actual_error
        return {
            "StoppingInstances": [
                {
                    "InstanceId": self.instance_id,
                    "PreviousState": {"Name": "running"},
                    "CurrentState": {"Name": "stopping"},
                }
            ],
            "ResponseMetadata": {"RequestId": "request-safe-001"},
        }


class FakeLambdaClient:
    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.calls: list[dict[str, object]] = []

    def invoke(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(kwargs)
        return {"Payload": io.BytesIO(self.payload)}


def _proposal() -> ActionProposal:
    return ActionProposal(
        proposal_id=PROPOSAL_ID,
        run_id=RUN_ID,
        action=Capability.STOP_SANDBOX_INSTANCE,
        target=ActionTarget(
            resource_id=INSTANCE_ID,
            sandbox_scope="hackathon-sandbox",
        ),
        expected_precondition=ExpectedPrecondition(
            instance_state=ObservedInstanceState.RUNNING,
            observed_at=NOW,
            evidence_hash=DIGEST,
        ),
        authority=AuthorityGate.PLAN_AND_CONFIRM,
        state=ProposalState.PROPOSED,
        evidence_hash=DIGEST,
        created_at=NOW,
    )


def _approval(proposal: ActionProposal, decision: ApprovalDecision) -> Approval:
    return Approval(
        proposal_id=proposal.proposal_id,
        run_id=proposal.run_id,
        action=proposal.action,
        target=proposal.target,
        evidence_hash=proposal.evidence_hash,
        interrupt_id="v1:before_tool_call:stop-1",
        request_hash=REQUEST_HASH,
        decision=decision,
        decided_at=NOW + timedelta(seconds=5),
        actor_session_id="human-session-001",
        decision_nonce="decision-nonce-0001",
    )


def _repository(
    decision: ApprovalDecision | None = ApprovalDecision.APPROVED,
) -> tuple[InMemoryTestDurableTruthRepository, ActionProposal]:
    repository = InMemoryTestDurableTruthRepository()
    run = repository.create_run(
        Run.new(
            run_id=RUN_ID,
            trace_id=TRACE_ID,
            correlation_id=CORRELATION_ID,
            idempotency_key="request:idle-ec2:0001",
            created_at=NOW,
            budget=BudgetCounters(max_turns=8, max_tokens=8_192),
        )
    )
    for offset, state in enumerate(
        (
            WorkflowState.INVESTIGATING,
            WorkflowState.EVIDENCE_READY,
            WorkflowState.REMEDIATION_PROPOSED,
            WorkflowState.AWAITING_APPROVAL,
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
    if decision is not None:
        repository.create_approval(_approval(proposal, decision))
        next_state = (
            WorkflowState.APPROVED
            if decision is ApprovalDecision.APPROVED
            else WorkflowState.DENIED_BY_HUMAN
        )
        run = repository.transition_run(
            RUN_ID,
            next_state,
            expected_state=WorkflowState.AWAITING_APPROVAL,
            expected_version=run.version,
            updated_at=NOW + timedelta(seconds=6),
            approval_proposal_id=PROPOSAL_ID,
        )
    repository.save_checkpoint(
        Checkpoint(
            run_id=RUN_ID,
            last_safe_state=run.state,
            resume_metadata={"proposal_id": str(PROPOSAL_ID)},
            tool_result_hashes={"build_remediation_evidence": DIGEST},
            created_at=NOW + timedelta(seconds=6),
            version=1,
        ),
        expected_version=None,
    )
    return repository, proposal


def _command() -> StopExecutionCommand:
    repository, _ = _repository()
    register_approved_action(repository, PROPOSAL_ID, registered_at=NOW + timedelta(seconds=7))
    return build_stop_execution_command(
        load_execution_prerequisites(repository, PROPOSAL_ID),
        issued_at=NOW + timedelta(seconds=8),
    )


def _settings(
    *,
    instance_id: str = INSTANCE_ID,
    aws_mutations_enabled: bool = True,
    allow_live_sandbox_stop: bool = True,
) -> SandboxRemediationSettings:
    return SandboxRemediationSettings(
        instance_id=instance_id,
        aws_mutations_enabled=aws_mutations_enabled,
        allow_live_sandbox_stop=allow_live_sandbox_stop,
    )


def _coordinator(
    repository: InMemoryTestDurableTruthRepository,
    executor: RecordingPrivateExecutor,
) -> StopSandboxInstanceCoordinator:
    return StopSandboxInstanceCoordinator(
        repository,
        executor,
        clock=lambda: NOW + timedelta(seconds=10),
        event_id_factory=EventIdFactory(),
    )


def test_private_executor_requires_both_live_flags_before_any_aws_call() -> None:
    client = FakeEc2StopClient()
    executor = Ec2SandboxStopExecutor(
        client,
        _settings(allow_live_sandbox_stop=False),
        clock=lambda: NOW,
    )

    with pytest.raises(RemediationDisabledError):
        executor.execute(_command())

    assert client.describe_calls == []
    assert client.stop_calls == []


@pytest.mark.parametrize(
    ("client", "settings"),
    [
        (FakeEc2StopClient(instance_id=OTHER_INSTANCE_ID), _settings()),
        (FakeEc2StopClient(state="stopped"), _settings()),
        (FakeEc2StopClient(root_device_type="instance-store"), _settings()),
        (FakeEc2StopClient(tag_value="false"), _settings()),
        (FakeEc2StopClient(), _settings(instance_id=OTHER_INSTANCE_ID)),
    ],
)
def test_private_executor_fails_closed_for_non_sandbox_or_stale_target(
    client: FakeEc2StopClient,
    settings: SandboxRemediationSettings,
) -> None:
    executor = Ec2SandboxStopExecutor(client, settings, clock=lambda: NOW)

    with pytest.raises(RemediationScopeError):
        executor.execute(_command())

    assert all(call["DryRun"] is True for call in client.stop_calls)


def test_private_executor_dry_runs_then_stops_exactly_one_target_gracefully() -> None:
    client = FakeEc2StopClient()
    executor = Ec2SandboxStopExecutor(client, _settings(), clock=lambda: NOW)

    acknowledgement = executor.execute(_command())

    assert client.describe_calls == [[INSTANCE_ID]]
    assert client.stop_calls == [
        {"InstanceIds": [INSTANCE_ID], "DryRun": True},
        {"InstanceIds": [INSTANCE_ID], "DryRun": False},
    ]
    assert acknowledgement.current_state is ObservedInstanceState.STOPPING
    assert acknowledgement.target.resource_id == INSTANCE_ID
    assert acknowledgement.acknowledgement_hash


def test_ambiguous_stop_acknowledgement_is_not_retried() -> None:
    client = FakeEc2StopClient(actual_error=TimeoutError("lost acknowledgement"))
    executor = Ec2SandboxStopExecutor(client, _settings(), clock=lambda: NOW)

    with pytest.raises(RemediationAmbiguousError):
        executor.execute(_command())

    assert len(client.stop_calls) == 2


def test_aws_stop_error_is_explicit_dependency_failure() -> None:
    client = FakeEc2StopClient(actual_error=FakeAwsError("UnauthorizedOperation"))
    executor = Ec2SandboxStopExecutor(client, _settings(), clock=lambda: NOW)

    with pytest.raises(RemediationDependencyError):
        executor.execute(_command())

    assert len(client.stop_calls) == 2


def test_approved_action_claims_stable_idempotency_and_enters_verifying() -> None:
    repository, _ = _repository()
    executor = RecordingPrivateExecutor()
    coordinator = _coordinator(repository, executor)

    result = coordinator.execute(PROPOSAL_ID)

    assert result.status is ResultStatus.SUCCESS
    assert result.value is not None
    assert result.value.current_state is ObservedInstanceState.STOPPING
    assert repository.get_run(RUN_ID).state is WorkflowState.VERIFYING
    record = repository.get_idempotency(executor.commands[0].idempotency_key)
    assert record is not None
    assert record.status is IdempotencyStatus.REGISTERED
    assert record.execution_acknowledgement == result.value
    assert record.action_result is None
    assert len(executor.commands) == 1


def test_duplicate_acknowledged_action_never_invokes_executor_twice() -> None:
    repository, _ = _repository()
    executor = RecordingPrivateExecutor()
    coordinator = _coordinator(repository, executor)

    first = coordinator.execute(PROPOSAL_ID)
    duplicate = coordinator.execute(PROPOSAL_ID)

    assert first.status is ResultStatus.SUCCESS
    assert duplicate.status is ResultStatus.SUCCESS
    assert duplicate.value == first.value
    assert len(executor.commands) == 1


def test_unresolved_in_progress_action_requires_recovery_without_replay() -> None:
    repository, _ = _repository()
    register_approved_action(repository, PROPOSAL_ID, registered_at=NOW)
    executor = RecordingPrivateExecutor()

    result = _coordinator(repository, executor).execute(PROPOSAL_ID)

    assert result.status is ResultStatus.FAILURE
    assert result.failure is not None
    assert result.failure.kind is FailureKind.RECOVERY_REQUIREMENT
    assert repository.get_run(RUN_ID).state is WorkflowState.RECOVERY_REQUIRED
    assert executor.commands == []


@pytest.mark.parametrize("decision", [None, ApprovalDecision.DENIED])
def test_missing_or_denied_approval_never_invokes_executor(
    decision: ApprovalDecision | None,
) -> None:
    repository, _ = _repository(decision)
    executor = RecordingPrivateExecutor()

    result = _coordinator(repository, executor).execute(PROPOSAL_ID)

    assert result.status is ResultStatus.FAILURE
    assert executor.commands == []


@pytest.mark.parametrize(
    ("error", "expected_state", "expected_kind"),
    [
        (
            RemediationDependencyError("provider unavailable"),
            WorkflowState.DEPENDENCY_UNAVAILABLE,
            FailureKind.DEPENDENCY_UNAVAILABLE,
        ),
        (
            RemediationAmbiguousError("lost acknowledgement"),
            WorkflowState.RECOVERY_REQUIRED,
            FailureKind.RECOVERY_REQUIREMENT,
        ),
    ],
)
def test_executor_failure_never_becomes_success(
    error: Exception,
    expected_state: WorkflowState,
    expected_kind: FailureKind,
) -> None:
    repository, _ = _repository()
    executor = RecordingPrivateExecutor(error)

    result = _coordinator(repository, executor).execute(PROPOSAL_ID)

    assert result.status is ResultStatus.FAILURE
    assert result.failure is not None and result.failure.kind is expected_kind
    assert repository.get_run(RUN_ID).state is expected_state
    assert len(executor.commands) == 1


def test_stop_tool_accepts_only_proposal_reference_and_no_mutation_options() -> None:
    calls: list[UUID] = []

    def handler(proposal_id: UUID) -> dict[str, object]:
        calls.append(proposal_id)
        return {"status": "SUCCESS", "value": "accepted", "failure": None}

    stop_tool = create_stop_sandbox_instance_tool(handler)
    schema = stop_tool.tool_spec["inputSchema"]["json"]

    assert schema["required"] == ["proposal_id"]
    assert set(schema["properties"]) == {"proposal_id"}
    assert not any(name in str(schema) for name in ("Force", "Hibernate", "SkipOsShutdown"))
    stop_tool(proposal_id=str(PROPOSAL_ID))
    assert calls == [PROPOSAL_ID]
    with pytest.raises(TypeError):
        stop_tool(proposal_id=str(PROPOSAL_ID), Force=True)


def test_model_like_payload_cannot_construct_privileged_execution_command() -> None:
    payload = _command().model_dump(mode="json")
    payload["Force"] = True
    payload["InstanceIds"] = [OTHER_INSTANCE_ID]

    with pytest.raises(ValidationError):
        StopExecutionCommand.model_validate(payload)


def test_lambda_boundary_invokes_only_explicit_function_and_validates_ack() -> None:
    acknowledgement = RecordingPrivateExecutor().execute(_command())
    client = FakeLambdaClient(acknowledgement.model_dump_json().encode("utf-8"))
    boundary = LambdaPrivateRemediationExecutor(client, "private-remediation-executor")

    restored = boundary.execute(_command())

    assert restored == acknowledgement
    assert len(client.calls) == 1
    assert client.calls[0]["FunctionName"] == "private-remediation-executor"
    assert client.calls[0]["InvocationType"] == "RequestResponse"
