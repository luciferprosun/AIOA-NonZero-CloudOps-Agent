"""Clearly test-only in-memory implementation of the durable repository contract."""

from datetime import datetime
from uuid import UUID

from aioa_cloudops_agent.nz import (
    ActionProposal,
    ActionResult,
    Approval,
    ApprovalDecision,
    AuditEvent,
    Checkpoint,
    IdempotencyRecord,
    IdempotencyStatus,
    ProposalState,
    Run,
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
    ) -> Run:
        current = self._runs.get(run_id)
        if current is None:
            raise StorageConflictError("durable run does not exist")
        if current.state is not expected_state or current.version != expected_version:
            raise StorageConflictError("durable run state or version no longer matches")
        if next_state in {WorkflowState.APPROVED, WorkflowState.DENIED_BY_HUMAN}:
            if approval_proposal_id is None:
                raise StorageConflictError("decision transition requires a durable proposal decision")
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
                raise StorageConflictError("decision transition requires matching durable human decision")
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
