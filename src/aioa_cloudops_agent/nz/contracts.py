"""Pydantic contracts at Non-Zero model, control, and durable boundaries."""

import hashlib
import json
from datetime import datetime, timedelta
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator

from aioa_cloudops_agent.domain.enums import AuthorityGate

from .authority import require_capability_authority
from .enums import (
    ActionOutcome,
    ApprovalDecision,
    AuditEventType,
    Capability,
    ExecutionAcknowledgementStatus,
    IdempotencyStatus,
    ObservedInstanceState,
    ProposalState,
    VerificationDisposition,
    VerificationProofOrigin,
    WorkflowState,
)
from .errors import FailureDetail
from .identifiers import (
    Ec2InstanceId,
    IdempotencyKey,
    NonEmptyText,
    Sha256Digest,
    ShortIdentifier,
    Uuid7Identifier,
)
from .transitions import validate_workflow_transition


def _require_utc(name: str, value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be a timezone-aware UTC datetime")
    return value


class NonZeroContract(BaseModel):
    """Shared strict shape: immutable fields and no unknown model output."""

    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)


class BudgetCounters(NonZeroContract):
    """Bounded consumption retained with a durable run."""

    max_turns: int = Field(gt=0, le=1_000)
    max_tokens: int = Field(gt=0, le=10_000_000)
    turns_used: int = Field(default=0, ge=0)
    tokens_used: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_consumption(self) -> Self:
        if self.turns_used > self.max_turns:
            raise ValueError("turns_used must not exceed max_turns")
        if self.tokens_used > self.max_tokens:
            raise ValueError("tokens_used must not exceed max_tokens")
        return self


class Run(NonZeroContract):
    """Versioned workflow truth with explicit identity, lifecycle, and budgets."""

    run_id: Uuid7Identifier
    trace_id: Uuid7Identifier
    correlation_id: Uuid7Identifier
    idempotency_key: IdempotencyKey
    state: WorkflowState
    created_at: datetime
    updated_at: datetime
    budget: BudgetCounters
    version: int = Field(default=1, gt=0)

    @field_validator("created_at", "updated_at")
    @classmethod
    def validate_timestamp(cls, value: datetime, info: object) -> datetime:
        field_name = getattr(info, "field_name", "timestamp")
        return _require_utc(field_name, value)

    @model_validator(mode="after")
    def validate_time_order(self) -> Self:
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not precede created_at")
        return self

    @classmethod
    def new(
        cls,
        *,
        run_id: Uuid7Identifier,
        trace_id: Uuid7Identifier,
        correlation_id: Uuid7Identifier,
        idempotency_key: IdempotencyKey,
        created_at: datetime,
        budget: BudgetCounters,
    ) -> "Run":
        return cls(
            run_id=run_id,
            trace_id=trace_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            state=WorkflowState.RECEIVED,
            created_at=created_at,
            updated_at=created_at,
            budget=budget,
            version=1,
        )


def transition_run(run: Run, next_state: WorkflowState, *, updated_at: datetime) -> Run:
    """Create a validated next version without trusting unvalidated model updates."""

    if not isinstance(run, Run):
        raise TypeError("run must be a Run")
    valid_state = validate_workflow_transition(run.state, next_state)
    valid_time = _require_utc("updated_at", updated_at)
    if valid_time < run.updated_at:
        raise ValueError("updated_at must not precede the current run timestamp")
    values = run.model_dump()
    values.update(
        {
            "state": valid_state,
            "updated_at": valid_time,
            "version": run.version + 1,
        }
    )
    return Run.model_validate(values)


class ActionTarget(NonZeroContract):
    """One explicit sandbox EC2 target; no arbitrary resource argument map."""

    resource_type: Literal["AWS::EC2::Instance"] = "AWS::EC2::Instance"
    resource_id: Ec2InstanceId
    region: Literal["eu-central-1"] = "eu-central-1"
    sandbox_scope: ShortIdentifier
    required_tag_key: ShortIdentifier = "AIOACloudOpsSandbox"
    required_tag_value: ShortIdentifier = "true"


class ExpectedPrecondition(NonZeroContract):
    """Evidence-backed state expected immediately before future execution."""

    instance_state: ObservedInstanceState
    observed_at: datetime
    evidence_hash: Sha256Digest

    @field_validator("observed_at")
    @classmethod
    def validate_observed_at(cls, value: datetime) -> datetime:
        return _require_utc("observed_at", value)


class ActionProposal(NonZeroContract):
    """Durable write-before-execute proposal that is never approval."""

    proposal_id: Uuid7Identifier
    run_id: Uuid7Identifier
    action: Capability
    target: ActionTarget
    expected_precondition: ExpectedPrecondition
    authority: AuthorityGate
    state: ProposalState = ProposalState.PROPOSED
    evidence_hash: Sha256Digest
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return _require_utc("created_at", value)

    @model_validator(mode="after")
    def validate_mutation_proposal(self) -> Self:
        if self.action is not Capability.STOP_SANDBOX_INSTANCE:
            raise ValueError("only the canonical sandbox stop may form a mutation proposal")
        require_capability_authority(self.action, self.authority)
        if self.expected_precondition.instance_state is not ObservedInstanceState.RUNNING:
            raise ValueError("stop proposal requires a running-instance precondition")
        if self.evidence_hash != self.expected_precondition.evidence_hash:
            raise ValueError("proposal evidence_hash must match precondition evidence")
        return self

    @property
    def authorizes_execution(self) -> Literal[False]:
        """Make the proposal/approval boundary unambiguous to callers."""

        return False


class Approval(NonZeroContract):
    """Explicit human approval or denial, separate from proposal state."""

    proposal_id: Uuid7Identifier
    run_id: Uuid7Identifier
    action: Capability
    target: ActionTarget
    evidence_hash: Sha256Digest
    interrupt_id: NonEmptyText
    request_hash: Sha256Digest
    decision: ApprovalDecision
    decided_at: datetime
    actor_session_id: ShortIdentifier
    decision_nonce: NonEmptyText = Field(min_length=16, max_length=256)

    @field_validator("decided_at")
    @classmethod
    def validate_decided_at(cls, value: datetime) -> datetime:
        return _require_utc("decided_at", value)

    @model_validator(mode="after")
    def validate_action_binding(self) -> Self:
        if self.action is not Capability.STOP_SANDBOX_INSTANCE:
            raise ValueError("approval can bind only the canonical sandbox stop")
        return self


class ActionResult(NonZeroContract):
    """Explicit future action outcome; no generic success boolean."""

    outcome: ActionOutcome
    observed_state: ObservedInstanceState | None = None
    evidence_hash: Sha256Digest | None = None
    failure: FailureDetail | None = None

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        if self.outcome is ActionOutcome.SUCCEEDED:
            if self.observed_state is None or self.evidence_hash is None or self.failure is not None:
                raise ValueError("successful action result requires evidence and forbids failure")
        elif self.failure is None:
            raise ValueError("non-success action result requires explicit failure detail")
        return self


class ExecutionAcknowledgement(NonZeroContract):
    """Safe provider receipt that cannot represent post-action verification."""

    status: Literal[ExecutionAcknowledgementStatus.ACCEPTED] = (
        ExecutionAcknowledgementStatus.ACCEPTED
    )
    proposal_id: Uuid7Identifier
    run_id: Uuid7Identifier
    action: Literal[Capability.STOP_SANDBOX_INSTANCE] = Capability.STOP_SANDBOX_INSTANCE
    target: ActionTarget
    previous_state: Literal[ObservedInstanceState.RUNNING] = ObservedInstanceState.RUNNING
    current_state: Literal[ObservedInstanceState.STOPPING, ObservedInstanceState.STOPPED]
    request_reference: NonEmptyText | None = None
    acknowledged_at: datetime
    acknowledgement_hash: Sha256Digest

    @field_validator("acknowledged_at")
    @classmethod
    def validate_acknowledged_at(cls, value: datetime) -> datetime:
        return _require_utc("acknowledged_at", value)


class VerificationEvidence(NonZeroContract):
    """Immutable proof that independent EC2 read-back observed the stopped target."""

    evidence_id: Uuid7Identifier
    proposal_id: Uuid7Identifier
    run_id: Uuid7Identifier
    trace_id: Uuid7Identifier
    correlation_id: Uuid7Identifier
    disposition: Literal[VerificationDisposition.VERIFIED] = VerificationDisposition.VERIFIED
    action: Literal[Capability.STOP_SANDBOX_INSTANCE] = Capability.STOP_SANDBOX_INSTANCE
    target: ActionTarget
    observed_state: Literal[ObservedInstanceState.STOPPED] = ObservedInstanceState.STOPPED
    verified_at: datetime
    proof_origin: VerificationProofOrigin = VerificationProofOrigin.EXECUTION_ACKNOWLEDGEMENT
    execution_acknowledgement_hash: Sha256Digest | None = None
    recovery_observation_hash: Sha256Digest | None = None
    observation_hash: Sha256Digest
    request_reference: NonEmptyText | None = None
    evidence_hash: Sha256Digest

    @field_validator("verified_at")
    @classmethod
    def validate_verified_at(cls, value: datetime) -> datetime:
        return _require_utc("verified_at", value)

    @model_validator(mode="after")
    def validate_evidence_hash(self) -> Self:
        if self.proof_origin is VerificationProofOrigin.EXECUTION_ACKNOWLEDGEMENT:
            if self.execution_acknowledgement_hash is None:
                raise ValueError("acknowledgement proof requires its durable hash")
            if self.recovery_observation_hash is not None:
                raise ValueError("acknowledgement proof cannot contain recovery proof")
        elif (
            self.recovery_observation_hash is None
            or self.execution_acknowledgement_hash is not None
        ):
            raise ValueError("recovery proof requires only its read-back hash")
        canonical = json.dumps(
            self.evidence_payload(),
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        if self.evidence_hash != hashlib.sha256(canonical).hexdigest():
            raise ValueError("verification evidence_hash does not match canonical evidence")
        return self

    def evidence_payload(self) -> dict[str, object]:
        """Return canonical decision-relevant proof without provider response leakage."""

        payload: dict[str, object] = {
            "action": self.action.value,
            "correlation_id": str(self.correlation_id),
            "disposition": self.disposition.value,
            "observation_hash": self.observation_hash,
            "observed_state": self.observed_state.value,
            "proposal_id": str(self.proposal_id),
            "request_reference": self.request_reference,
            "run_id": str(self.run_id),
            "target": self.target.model_dump(mode="json"),
            "trace_id": str(self.trace_id),
            "verified_at": self.verified_at.isoformat(),
        }
        if self.proof_origin is VerificationProofOrigin.EXECUTION_ACKNOWLEDGEMENT:
            # Keep the pre-Day-11 canonical shape so already persisted hashes remain valid.
            payload["execution_acknowledgement_hash"] = self.execution_acknowledgement_hash
        else:
            payload["proof_origin"] = self.proof_origin.value
            payload["recovery_observation_hash"] = self.recovery_observation_hash
        return payload

    @classmethod
    def create(
        cls,
        *,
        evidence_id: Uuid7Identifier,
        proposal: ActionProposal,
        run: Run,
        verified_at: datetime,
        acknowledgement: ExecutionAcknowledgement,
        observation_hash: Sha256Digest,
    ) -> "VerificationEvidence":
        """Build linked final proof and its stable canonical SHA-256 digest."""

        if (
            proposal.run_id != run.run_id
            or acknowledgement.proposal_id != proposal.proposal_id
            or acknowledgement.run_id != run.run_id
            or acknowledgement.target != proposal.target
        ):
            raise ValueError("verification evidence prerequisites do not share one identity")
        values: dict[str, object] = {
            "evidence_id": evidence_id,
            "proposal_id": proposal.proposal_id,
            "run_id": run.run_id,
            "trace_id": run.trace_id,
            "correlation_id": run.correlation_id,
            "target": proposal.target,
            "verified_at": verified_at,
            "execution_acknowledgement_hash": acknowledgement.acknowledgement_hash,
            "observation_hash": observation_hash,
            "request_reference": acknowledgement.request_reference,
        }
        provisional = cls.model_construct(**values, evidence_hash="0" * 64)
        canonical = json.dumps(
            provisional.evidence_payload(),
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return cls(**values, evidence_hash=hashlib.sha256(canonical).hexdigest())

    @classmethod
    def create_from_recovery(
        cls,
        *,
        evidence_id: Uuid7Identifier,
        proposal: ActionProposal,
        run: Run,
        verified_at: datetime,
        observation_hash: Sha256Digest,
    ) -> "VerificationEvidence":
        """Create proof from approved lost-ACK work plus independent stopped read-back."""

        if proposal.run_id != run.run_id:
            raise ValueError("recovery evidence prerequisites do not share one run")
        values: dict[str, object] = {
            "evidence_id": evidence_id,
            "proposal_id": proposal.proposal_id,
            "run_id": run.run_id,
            "trace_id": run.trace_id,
            "correlation_id": run.correlation_id,
            "target": proposal.target,
            "verified_at": verified_at,
            "proof_origin": VerificationProofOrigin.RECOVERY_READ_BACK,
            "recovery_observation_hash": observation_hash,
            "observation_hash": observation_hash,
        }
        provisional = cls.model_construct(**values, evidence_hash="0" * 64)
        canonical = json.dumps(
            provisional.evidence_payload(),
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return cls(**values, evidence_hash=hashlib.sha256(canonical).hexdigest())


class IdempotencyRecord(NonZeroContract):
    """Semantic duplicate ownership and optional durable action outcome."""

    idempotency_key: IdempotencyKey
    proposal_id: Uuid7Identifier
    action_fingerprint: Sha256Digest
    status: IdempotencyStatus = IdempotencyStatus.REGISTERED
    execution_acknowledgement: ExecutionAcknowledgement | None = None
    action_result: ActionResult | None = None
    registered_at: datetime
    completed_at: datetime | None = None

    @field_validator("registered_at")
    @classmethod
    def validate_registered_at(cls, value: datetime) -> datetime:
        return _require_utc("registered_at", value)

    @field_validator("completed_at")
    @classmethod
    def validate_completed_at(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _require_utc("completed_at", value)

    @model_validator(mode="after")
    def validate_status_payload(self) -> Self:
        if self.status is IdempotencyStatus.REGISTERED:
            if self.action_result is not None or self.completed_at is not None:
                raise ValueError("registered idempotency record cannot contain a result")
        elif self.action_result is None or self.completed_at is None:
            raise ValueError("resolved idempotency record requires result and completed_at")
        elif self.completed_at < self.registered_at:
            raise ValueError("completed_at must not precede registered_at")
        return self


class Checkpoint(NonZeroContract):
    """Versioned last-safe-state foundation for later restart reconciliation."""

    run_id: Uuid7Identifier
    last_safe_state: WorkflowState
    resume_metadata: dict[str, JsonValue] = Field(default_factory=dict)
    tool_result_hashes: dict[ShortIdentifier, Sha256Digest] = Field(default_factory=dict)
    created_at: datetime
    version: int = Field(default=1, gt=0)

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return _require_utc("created_at", value)

    @model_validator(mode="after")
    def validate_last_safe_state(self) -> Self:
        if self.last_safe_state in {WorkflowState.EXECUTING, WorkflowState.VERIFYING}:
            raise ValueError("checkpoint cannot label an active side-effect state as safe")
        return self


class AuditEvent(NonZeroContract):
    """Append-oriented provenance event with redacted payload evidence."""

    event_id: Uuid7Identifier
    run_id: Uuid7Identifier
    type: AuditEventType
    timestamp: datetime
    source: ShortIdentifier
    tool_name: ShortIdentifier | None = None
    model_id: NonEmptyText | None = None
    redacted_payload_hash: Sha256Digest
    metadata: dict[ShortIdentifier, NonEmptyText] = Field(default_factory=dict)

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, value: datetime) -> datetime:
        return _require_utc("timestamp", value)

    @model_validator(mode="after")
    def prohibit_sensitive_metadata(self) -> Self:
        sensitive_terms = ("credential", "password", "secret", "token")
        if any(
            any(term in key.casefold() for term in sensitive_terms)
            for key in self.metadata
        ):
            raise ValueError("sensitive audit metadata keys are prohibited")
        return self
