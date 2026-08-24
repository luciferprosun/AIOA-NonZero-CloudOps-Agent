"""Clearly test-only in-memory implementation of the durable repository contract."""

from datetime import datetime
from uuid import UUID

from aioa_cloudops_agent.nz import (
    ActionProposal,
    ActionResult,
    Approval,
    ApprovalDecision,
    AuditEvent,
    BudgetCounters,
    Checkpoint,
    ExecutionAcknowledgement,
    IdempotencyRecord,
    IdempotencyStatus,
    ObservedInstanceState,
    ProposalState,
    Run,
    VerificationEvidence,
    VerificationProofOrigin,
    WorkflowState,
    transition_run,
)
from aioa_cloudops_agent.nz.errors import StorageConflictError

from .durable_logic import (
    completed_idempotency_status,
    transitioned_proposal,
    validate_approval_binding,
)
from .semantic_idempotency import derive_action_fingerprint, derive_idempotency_key


class InMemoryTestDurableTruthRepository:
    """Deterministic test fake; never a production durability fallback."""

    def __init__(self) -> None:
        self._runs: dict[UUID, Run] = {}
        self._proposals: dict[UUID, ActionProposal] = {}
        self._approvals: dict[UUID, Approval] = {}
        self._idempotency: dict[str, IdempotencyRecord] = {}
        self._checkpoints: dict[UUID, Checkpoint] = {}
        self._audit_events: dict[tuple[UUID, UUID], AuditEvent] = {}
        self._verification_evidence: dict[tuple[UUID, UUID], VerificationEvidence] = {}

    def create_run(self, run: Run) -> Run:
        if run.version != 1 or run.state is not WorkflowState.RECEIVED:
            raise StorageConflictError("new durable run must start at RECEIVED version 1")
        if run.run_id in self._runs:
            raise StorageConflictError("durable run already exists")
        self._runs[run.run_id] = run
        return run

    def get_run(self, run_id: UUID) -> Run | None:
        return self._runs.get(run_id)

    def transition_run(
        self,
        run_id: UUID,
        next_state: WorkflowState,
        *,
        expected_state: WorkflowState,
        expected_version: int,
        updated_at: datetime,
        approval_proposal_id: UUID | None = None,
        verification_proposal_id: UUID | None = None,
    ) -> Run:
        current = self._runs.get(run_id)
        if current is None:
            raise StorageConflictError("durable run does not exist")
        if current.state is not expected_state or current.version != expected_version:
            raise StorageConflictError("durable run state or version no longer matches")
        if next_state in {WorkflowState.APPROVED, WorkflowState.DENIED_BY_HUMAN}:
            if approval_proposal_id is None:
                raise StorageConflictError(
                    "decision transition requires a durable proposal decision"
                )
            proposal = self._proposals.get(approval_proposal_id)
            approval = self._approvals.get(approval_proposal_id)
            expected_decision = (
                ApprovalDecision.APPROVED
                if next_state is WorkflowState.APPROVED
                else ApprovalDecision.DENIED
            )
            if (
                proposal is None
                or proposal.run_id != run_id
                or proposal.state is not ProposalState.AWAITING_APPROVAL
                or approval is None
                or approval.decision is not expected_decision
            ):
                raise StorageConflictError(
                    "decision transition requires matching durable human decision"
                )
        if next_state is WorkflowState.SUCCESS_WITH_EVIDENCE:
            if verification_proposal_id is None:
                raise StorageConflictError("SUCCESS_WITH_EVIDENCE requires durable verification")
            proposal = self._proposals.get(verification_proposal_id)
            evidence = self._verification_evidence.get((run_id, verification_proposal_id))
            idempotency = (
                self._idempotency.get(derive_idempotency_key(proposal))
                if proposal is not None
                else None
            )
            if (
                proposal is None
                or evidence is None
                or evidence.run_id != run_id
                or evidence.observed_state is not ObservedInstanceState.STOPPED
                or idempotency is None
                or idempotency.status is not IdempotencyStatus.COMPLETED
                or idempotency.action_result is None
                or idempotency.action_result.evidence_hash != evidence.evidence_hash
            ):
                raise StorageConflictError("SUCCESS_WITH_EVIDENCE proof is incomplete")
        updated = transition_run(current, next_state, updated_at=updated_at)
        self._runs[run_id] = updated
        return updated

    def create_proposal(self, proposal: ActionProposal) -> ActionProposal:
        if proposal.state is not ProposalState.PROPOSED:
            raise StorageConflictError("new durable proposal must start at PROPOSED")
        if proposal.proposal_id in self._proposals:
            raise StorageConflictError("durable proposal already exists")
        self._proposals[proposal.proposal_id] = proposal
        return proposal

    def update_run_budget(
        self,
        run_id: UUID,
        budget: BudgetCounters,
        *,
        expected_version: int,
        updated_at: datetime,
    ) -> Run:
        if not isinstance(budget, BudgetCounters):
            raise TypeError("budget must be BudgetCounters")
        if (
            isinstance(expected_version, bool)
            or not isinstance(expected_version, int)
            or expected_version <= 0
        ):
            raise TypeError("expected_version must be a positive integer")
        if not isinstance(updated_at, datetime):
            raise TypeError("updated_at must be datetime")
        current = self._runs.get(run_id)
        if current is None or current.version != expected_version:
            raise StorageConflictError("durable run budget version no longer matches")
        if (
            budget.max_turns != current.budget.max_turns
            or budget.max_tokens != current.budget.max_tokens
            or budget.max_elapsed_seconds != current.budget.max_elapsed_seconds
            or budget.turns_used < current.budget.turns_used
            or budget.tokens_used < current.budget.tokens_used
            or budget.elapsed_milliseconds_used < current.budget.elapsed_milliseconds_used
            or updated_at < current.updated_at
        ):
            raise StorageConflictError("durable run budget update is not monotonic")
        values = current.model_dump()
        values.update(
            {
                "budget": budget,
                "updated_at": updated_at,
                "version": current.version + 1,
            }
        )
        updated = Run.model_validate(values)
        self._runs[run_id] = updated
        return updated

    def get_proposal(self, proposal_id: UUID) -> ActionProposal | None:
        return self._proposals.get(proposal_id)

    def transition_proposal(
        self,
        proposal_id: UUID,
        next_state: ProposalState,
        *,
        expected_state: ProposalState,
    ) -> ActionProposal:
        current = self._proposals.get(proposal_id)
        if current is None or current.state is not expected_state:
            raise StorageConflictError("durable proposal state no longer matches")
        updated = transitioned_proposal(current, next_state)
        self._proposals[proposal_id] = updated
        return updated

    def create_approval(self, approval: Approval) -> Approval:
        proposal = self._proposals.get(approval.proposal_id)
        if proposal is None or proposal.state is not ProposalState.AWAITING_APPROVAL:
            raise StorageConflictError("human decision requires an awaiting durable proposal")
        validate_approval_binding(proposal, approval)
        existing = self._approvals.get(approval.proposal_id)
        if existing is not None:
            if existing == approval:
                return existing
            raise StorageConflictError("conflicting human decision already exists")
        self._approvals[approval.proposal_id] = approval
        return approval

    def get_approval(self, proposal_id: UUID) -> Approval | None:
        return self._approvals.get(proposal_id)

    def register_idempotency(self, record: IdempotencyRecord) -> IdempotencyRecord:
        existing = self._idempotency.get(record.idempotency_key)
        if existing is not None:
            if (
                existing.proposal_id != record.proposal_id
                or existing.action_fingerprint != record.action_fingerprint
            ):
                raise StorageConflictError("idempotency key has incompatible ownership")
            return existing
        proposal = self._proposals.get(record.proposal_id)
        if (
            proposal is None
            or proposal.state is not ProposalState.AWAITING_APPROVAL
            or record.action_fingerprint != derive_action_fingerprint(proposal)
            or record.idempotency_key != derive_idempotency_key(proposal)
        ):
            raise StorageConflictError("idempotency registration lacks a matching proposal")
        approval = self._approvals.get(record.proposal_id)
        run = self._runs.get(proposal.run_id)
        if approval is None or approval.decision is not ApprovalDecision.APPROVED:
            raise StorageConflictError("idempotency registration requires human approval")
        if run is None or run.state is not WorkflowState.APPROVED:
            raise StorageConflictError("idempotency registration requires an approved run")
        self._idempotency[record.idempotency_key] = record
        return record

    def get_idempotency(self, idempotency_key: str) -> IdempotencyRecord | None:
        return self._idempotency.get(idempotency_key)

    def complete_idempotency(
        self,
        idempotency_key: str,
        result: ActionResult,
        *,
        completed_at: datetime,
        expected_status: IdempotencyStatus = IdempotencyStatus.REGISTERED,
    ) -> IdempotencyRecord:
        current = self._idempotency.get(idempotency_key)
        if current is None or current.status is not expected_status:
            raise StorageConflictError("idempotency status no longer matches")
        values = current.model_dump()
        values.update(
            {
                "status": completed_idempotency_status(result),
                "action_result": result,
                "completed_at": completed_at,
            }
        )
        updated = IdempotencyRecord.model_validate(values)
        self._idempotency[idempotency_key] = updated
        return updated

    def record_execution_acknowledgement(
        self,
        idempotency_key: str,
        acknowledgement: ExecutionAcknowledgement,
        *,
        expected_status: IdempotencyStatus = IdempotencyStatus.REGISTERED,
    ) -> IdempotencyRecord:
        current = self._idempotency.get(idempotency_key)
        if current is None or current.status is not expected_status:
            raise StorageConflictError("idempotency status no longer matches")
        if current.execution_acknowledgement is not None:
            if current.execution_acknowledgement == acknowledgement:
                return current
            raise StorageConflictError("conflicting execution acknowledgement exists")
        if acknowledgement.proposal_id != current.proposal_id:
            raise StorageConflictError("execution acknowledgement ownership is invalid")
        updated = current.model_copy(update={"execution_acknowledgement": acknowledgement})
        self._idempotency[idempotency_key] = updated
        return updated

    def save_checkpoint(
        self,
        checkpoint: Checkpoint,
        *,
        expected_version: int | None,
    ) -> Checkpoint:
        current = self._checkpoints.get(checkpoint.run_id)
        if current is None:
            if expected_version is not None or checkpoint.version != 1:
                raise StorageConflictError("new checkpoint must start at version 1")
        elif expected_version != current.version or checkpoint.version != current.version + 1:
            raise StorageConflictError("checkpoint version no longer matches")
        self._checkpoints[checkpoint.run_id] = checkpoint
        return checkpoint

    def get_checkpoint(self, run_id: UUID) -> Checkpoint | None:
        return self._checkpoints.get(run_id)

    def append_audit_event(self, event: AuditEvent) -> AuditEvent:
        key = (event.run_id, event.event_id)
        if key in self._audit_events:
            raise StorageConflictError("audit event already exists")
        self._audit_events[key] = event
        return event

    def get_audit_event(self, run_id: UUID, event_id: UUID) -> AuditEvent | None:
        return self._audit_events.get((run_id, event_id))

    def create_verification_evidence(
        self,
        evidence: VerificationEvidence,
    ) -> VerificationEvidence:
        key = (evidence.run_id, evidence.proposal_id)
        existing = self._verification_evidence.get(key)
        if existing is not None:
            if existing == evidence:
                return existing
            raise StorageConflictError("conflicting verification evidence already exists")
        proposal = self._proposals.get(evidence.proposal_id)
        run = self._runs.get(evidence.run_id)
        idempotency = (
            self._idempotency.get(derive_idempotency_key(proposal))
            if proposal is not None
            else None
        )
        approval = self._approvals.get(evidence.proposal_id)
        acknowledgement_matches = (
            evidence.proof_origin is VerificationProofOrigin.EXECUTION_ACKNOWLEDGEMENT
            and idempotency is not None
            and idempotency.execution_acknowledgement is not None
            and idempotency.execution_acknowledgement.acknowledgement_hash
            == evidence.execution_acknowledgement_hash
        )
        recovery_matches = (
            evidence.proof_origin is VerificationProofOrigin.RECOVERY_READ_BACK
            and idempotency is not None
            and idempotency.status is IdempotencyStatus.REGISTERED
            and idempotency.execution_acknowledgement is None
            and approval is not None
            and approval.decision is ApprovalDecision.APPROVED
            and approval.run_id == evidence.run_id
            and approval.target == evidence.target
        )
        if (
            proposal is None
            or run is None
            or run.state is not WorkflowState.VERIFYING
            or proposal.run_id != evidence.run_id
            or proposal.target != evidence.target
            or run.trace_id != evidence.trace_id
            or run.correlation_id != evidence.correlation_id
            or idempotency is None
            or not (acknowledgement_matches or recovery_matches)
        ):
            raise StorageConflictError("verification evidence does not match the proposal")
        self._verification_evidence[key] = evidence
        return evidence

    def get_verification_evidence(
        self,
        run_id: UUID,
        proposal_id: UUID,
    ) -> VerificationEvidence | None:
        return self._verification_evidence.get((run_id, proposal_id))
