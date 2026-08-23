"""Bounded Strands investigation ending at a durable non-authorizing proposal."""

from collections.abc import Callable
from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from strands.types.agent import Limits

from aioa_cloudops_agent.cloudops import (
    EvidenceBuildOutcome,
    EvidenceDecision,
    RemediationEvidenceBundle,
)
from aioa_cloudops_agent.domain import AuthorityGate
from aioa_cloudops_agent.nz import (
    ActionProposal,
    AuditEvent,
    AuditEventType,
    Capability,
    Checkpoint,
    ControlResult,
    FailureDetail,
    FailureKind,
    ProposalState,
    Run,
    WorkflowState,
)
from aioa_cloudops_agent.nz.errors import StorageConflictError, StorageDependencyError
from aioa_cloudops_agent.nz.identifiers import Uuid7Identifier
from aioa_cloudops_agent.persistence import DurableTruthRepository, compute_evidence_digest

from .factory import READ_ONLY_TOOL_NAMES, PrimaryAgentRuntime
from .runtime import build_investigation_request


class InvestigationCompletion(BaseModel):
    """Evidence-backed package result that explicitly carries no execution authority."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: Uuid7Identifier
    trace_id: Uuid7Identifier
    correlation_id: Uuid7Identifier
    proposal: ActionProposal
    evidence: RemediationEvidenceBundle | None
    final_state: Literal[WorkflowState.REMEDIATION_PROPOSED]
    agent_summary: str = Field(min_length=1, max_length=1_024)
    reconciled: bool = False

    @model_validator(mode="after")
    def validate_completion(self) -> Self:
        if self.proposal.run_id != self.run_id:
            raise ValueError("completion proposal belongs to another run")
        if self.proposal.authorizes_execution:
            raise ValueError("investigation completion cannot authorize execution")
        if not self.reconciled and self.evidence is None:
            raise ValueError("new completion requires its typed evidence bundle")
        if self.evidence is not None and (
            self.evidence.run_id != self.run_id
            or self.evidence.trace_id != self.trace_id
            or self.evidence.correlation_id != self.correlation_id
            or self.evidence.evidence_hash != self.proposal.evidence_hash
        ):
            raise ValueError("completion identities or evidence hash do not match")
        return self


InvestigationFlowResult = ControlResult[InvestigationCompletion]


_FAILURE_STATE = {
    FailureKind.VALIDATION_FAILURE: WorkflowState.MODEL_OUTPUT_INVALID,
    FailureKind.POLICY_DENIAL: WorkflowState.DENIED_BY_POLICY,
    FailureKind.AMBIGUOUS_RESULT: WorkflowState.AMBIGUOUS_RESULT,
    FailureKind.DEPENDENCY_UNAVAILABLE: WorkflowState.DEPENDENCY_UNAVAILABLE,
    FailureKind.BUDGET_EXHAUSTION: WorkflowState.BUDGET_EXHAUSTED,
    FailureKind.EXECUTION_FAILURE: WorkflowState.EXECUTION_FAILED,
    FailureKind.VERIFICATION_FAILURE: WorkflowState.VERIFICATION_FAILED,
    FailureKind.RECOVERY_REQUIREMENT: WorkflowState.RECOVERY_REQUIRED,
}


class BoundedInvestigationFlow:
    """Let Strands orchestrate reads while NZ owns durable state and proposal validity."""

    def __init__(
        self,
        runtime: PrimaryAgentRuntime,
        repository: DurableTruthRepository,
        *,
        clock: Callable[[], datetime],
        event_id_factory: Callable[[], UUID],
    ) -> None:
        if not isinstance(runtime, PrimaryAgentRuntime):
            raise TypeError("runtime must be PrimaryAgentRuntime")
        if not callable(clock) or not callable(event_id_factory):
            raise TypeError("clock and event_id_factory must be callable")
        self._runtime = runtime
        self._repository = repository
        self._clock = clock
        self._event_id_factory = event_id_factory

    def execute(self, run: Run) -> InvestigationFlowResult:
        """Run one bounded investigation or reconcile its exact durable completion."""

        identity = self._runtime.identity
        if not isinstance(run, Run):
            raise TypeError("run must be a Run")
        if (
            run.run_id != identity.run_id
            or run.trace_id != identity.trace_id
            or run.correlation_id != identity.correlation_id
        ):
            return self._failure(
                FailureKind.VALIDATION_FAILURE,
                "RUN_IDENTITY_INVALID",
                "Run identity does not match the Strands tool context",
            )

        try:
            current = self._repository.get_run(run.run_id)
        except StorageDependencyError:
            return self._storage_failure("Durable run lookup is unavailable")
        if current is not None:
            if current != run:
                if current.state is WorkflowState.REMEDIATION_PROPOSED:
                    return self._reconcile_completion(current)
                return self._failure(
                    FailureKind.RECOVERY_REQUIREMENT,
                    "RUN_ALREADY_ACTIVE",
                    "Existing durable run requires explicit recovery",
                )
        else:
            try:
                current = self._repository.create_run(run)
                self._append_audit(
                    run,
                    event_type=AuditEventType.RUN_CREATED,
                    payload_hash=compute_evidence_digest(run.model_dump(mode="json")),
                    source="nz-control-plane",
                )
            except StorageConflictError:
                try:
                    raced = self._repository.get_run(run.run_id)
                except StorageDependencyError:
                    return self._storage_failure("Durable run reconciliation is unavailable")
                if raced is not None and raced.state is WorkflowState.REMEDIATION_PROPOSED:
                    return self._reconcile_completion(raced)
                return self._failure(
                    FailureKind.RECOVERY_REQUIREMENT,
                    "RUN_CREATE_CONFLICT",
                    "Durable run ownership could not be reconciled",
                )
            except StorageDependencyError:
                return self._storage_failure("Durable run creation is unavailable")

        if current.state is not WorkflowState.RECEIVED:
            return self._failure(
                FailureKind.RECOVERY_REQUIREMENT,
                "RUN_STATE_UNSAFE",
                "Investigation can start only from durable RECEIVED state",
            )
        try:
            current = self._transition(current, WorkflowState.INVESTIGATING)
        except (StorageConflictError, StorageDependencyError):
            return self._storage_failure("Durable INVESTIGATING transition failed")

        limits: Limits = {
            "turns": run.budget.max_turns,
            "output_tokens": min(
                run.budget.max_tokens,
                self._runtime.model_settings.max_output_tokens,
            ),
            "total_tokens": run.budget.max_tokens,
        }
        try:
            agent_result = self._runtime.agent(
                build_investigation_request(self._runtime.target),
                limits=limits,
            )
        except Exception:
            return self._fail_durable_run(
                current,
                FailureDetail(
                    kind=FailureKind.DEPENDENCY_UNAVAILABLE,
                    code="STRANDS_DEPENDENCY_UNAVAILABLE",
                    message="Strands or model dependency is unavailable",
                    retryable=True,
                ),
            )

        if str(agent_result.stop_reason).startswith("limit_"):
            return self._fail_durable_run(
                current,
                FailureDetail(
                    kind=FailureKind.BUDGET_EXHAUSTION,
                    code="AGENT_BUDGET_EXHAUSTED",
                    message="Bounded Strands investigation exhausted its budget",
                    retryable=False,
                ),
            )

        context = self._runtime.tool_context
        failure = context.first_failure()
        if failure is not None:
            return self._fail_durable_run(current, failure)
        if tuple(context.tool_calls) != READ_ONLY_TOOL_NAMES:
            return self._fail_durable_run(
                current,
                FailureDetail(
                    kind=FailureKind.VALIDATION_FAILURE,
                    code="TOOL_SEQUENCE_INVALID",
                    message="Strands did not complete the canonical bounded tool sequence",
                    retryable=False,
                ),
            )
        outcome = context.evidence()
        inspection = context.inspection()
        utilization = context.utilization()
        if outcome is None or inspection is None or utilization is None:
            return self._fail_durable_run(
                current,
                FailureDetail(
                    kind=FailureKind.VALIDATION_FAILURE,
                    code="TOOL_EVIDENCE_MISSING",
                    message="Typed tool evidence is incomplete",
                    retryable=False,
                ),
            )

        try:
            self._append_tool_audits(run, outcome)
            current = self._transition(current, WorkflowState.EVIDENCE_READY)
            first_checkpoint = Checkpoint(
                run_id=run.run_id,
                last_safe_state=WorkflowState.EVIDENCE_READY,
                resume_metadata={
                    "classification": outcome.evidence.utilization_classification.value,
                    "proposal_id": str(self._runtime.proposal_id),
                },
                tool_result_hashes={
                    "inspect_instance": inspection.evidence_digest,
                    "read_utilization_metrics": utilization.evidence_digest,
                    "build_remediation_evidence": outcome.evidence.evidence_hash,
                },
                created_at=self._clock(),
                version=1,
            )
            self._repository.save_checkpoint(first_checkpoint, expected_version=None)
        except (StorageConflictError, StorageDependencyError):
            return self._fail_durable_run(
                current,
                FailureDetail(
                    kind=FailureKind.DEPENDENCY_UNAVAILABLE,
                    code="EVIDENCE_DURABILITY_FAILED",
                    message="Evidence checkpoint or audit durability failed",
                    retryable=True,
                ),
            )

        if outcome.decision is EvidenceDecision.NOT_ELIGIBLE:
            return self._fail_durable_run(
                current,
                FailureDetail(
                    kind=FailureKind.POLICY_DENIAL,
                    code="INSTANCE_NOT_IDLE",
                    message="Deterministic evidence does not support an idle-instance proposal",
                    retryable=False,
                ),
            )
        proposal = outcome.proposal
        if proposal is None:
            return self._fail_durable_run(
                current,
                FailureDetail(
                    kind=FailureKind.RECOVERY_REQUIREMENT,
                    code="PROPOSAL_MISSING",
                    message="Eligible evidence did not produce a typed proposal",
                    retryable=False,
                ),
            )

        try:
            durable_proposal = self._create_or_reconcile_proposal(proposal)
            self._append_audit(
                run,
                event_type=AuditEventType.PROPOSAL_CREATED,
                payload_hash=proposal.evidence_hash,
                source="nz-control-plane",
                metadata={"proposal_id": str(proposal.proposal_id)},
            )
            current = self._transition(current, WorkflowState.REMEDIATION_PROPOSED)
            self._repository.save_checkpoint(
                Checkpoint(
                    run_id=run.run_id,
                    last_safe_state=WorkflowState.REMEDIATION_PROPOSED,
                    resume_metadata={
                        "classification": outcome.evidence.utilization_classification.value,
                        "proposal_id": str(proposal.proposal_id),
                    },
                    tool_result_hashes={
                        "inspect_instance": inspection.evidence_digest,
                        "read_utilization_metrics": utilization.evidence_digest,
                        "build_remediation_evidence": outcome.evidence.evidence_hash,
                    },
                    created_at=self._clock(),
                    version=2,
                ),
                expected_version=1,
            )
            if self._repository.get_approval(proposal.proposal_id) is not None:
                raise StorageConflictError("unexpected approval exists before HITL")
        except StorageDependencyError:
            return self._fail_durable_run(
                current,
                FailureDetail(
                    kind=FailureKind.DEPENDENCY_UNAVAILABLE,
                    code="PROPOSAL_DURABILITY_FAILED",
                    message="Durable proposal persistence is unavailable",
                    retryable=True,
                ),
            )
        except StorageConflictError:
            return self._fail_durable_run(
                current,
                FailureDetail(
                    kind=FailureKind.RECOVERY_REQUIREMENT,
                    code="PROPOSAL_CONFLICT",
                    message="Durable proposal state could not be reconciled",
                    retryable=False,
                ),
            )

        return ControlResult[InvestigationCompletion].succeeded(
            self._completion(
                run=current,
                proposal=durable_proposal,
                evidence=outcome.evidence,
                reconciled=False,
            )
        )

    def _transition(self, run: Run, next_state: WorkflowState) -> Run:
        return self._repository.transition_run(
            run.run_id,
            next_state,
            expected_state=run.state,
            expected_version=run.version,
            updated_at=self._clock(),
        )

    def _append_tool_audits(self, run: Run, outcome: EvidenceBuildOutcome) -> None:
        context = self._runtime.tool_context
        inspection = context.inspection()
        utilization = context.utilization()
        if inspection is None or utilization is None:
            raise StorageConflictError("tool audit requires complete evidence")
        for tool_name, digest, metadata in (
            (
                "inspect_instance",
                inspection.evidence_digest,
                {"instance_id": inspection.instance_id},
            ),
            (
                "read_utilization_metrics",
                utilization.evidence_digest,
                {"classification": utilization.classification.value},
            ),
            (
                "build_remediation_evidence",
                outcome.evidence.evidence_hash,
                {"decision": outcome.decision.value},
            ),
        ):
            self._append_audit(
                run,
                event_type=AuditEventType.TOOL_OBSERVED,
                payload_hash=digest,
                source="strands-agent",
                tool_name=tool_name,
                metadata=metadata,
            )

    def _append_audit(
        self,
        run: Run,
        *,
        event_type: AuditEventType,
        payload_hash: str,
        source: str,
        tool_name: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> None:
        self._repository.append_audit_event(
            AuditEvent(
                event_id=self._event_id_factory(),
                run_id=run.run_id,
                type=event_type,
                timestamp=self._clock(),
                source=source,
                tool_name=tool_name,
                model_id=self._runtime.model_settings.model_id,
                redacted_payload_hash=payload_hash,
                metadata={
                    "trace_id": str(run.trace_id),
                    "correlation_id": str(run.correlation_id),
                    **(metadata or {}),
                },
            )
        )

    def _create_or_reconcile_proposal(self, proposal: ActionProposal) -> ActionProposal:
        try:
            return self._repository.create_proposal(proposal)
        except StorageConflictError as conflict:
            existing = self._repository.get_proposal(proposal.proposal_id)
            if existing != proposal:
                raise StorageConflictError("proposal ownership is incompatible") from conflict
            return existing

    def _reconcile_completion(self, run: Run) -> InvestigationFlowResult:
        try:
            proposal = self._repository.get_proposal(self._runtime.proposal_id)
            approval = self._repository.get_approval(self._runtime.proposal_id)
        except StorageDependencyError:
            return self._storage_failure("Durable proposal reconciliation is unavailable")
        if (
            proposal is None
            or proposal.run_id != run.run_id
            or proposal.action is not Capability.STOP_SANDBOX_INSTANCE
            or proposal.authority is not AuthorityGate.PLAN_AND_CONFIRM
            or proposal.state is not ProposalState.PROPOSED
            or proposal.target.resource_id != self._runtime.target.instance_id
            or proposal.target.region != self._runtime.target.region
            or proposal.target.required_tag_key != self._runtime.target.required_tag_key
            or proposal.target.required_tag_value != self._runtime.target.required_tag_value
            or proposal.authorizes_execution
            or approval is not None
        ):
            return self._failure(
                FailureKind.RECOVERY_REQUIREMENT,
                "PROPOSAL_RECONCILIATION_FAILED",
                "Existing durable proposal is missing or incompatible",
            )
        evidence_outcome = self._runtime.tool_context.evidence()
        return ControlResult[InvestigationCompletion].succeeded(
            self._completion(
                run=run,
                proposal=proposal,
                evidence=None if evidence_outcome is None else evidence_outcome.evidence,
                reconciled=True,
            )
        )

    def _completion(
        self,
        *,
        run: Run,
        proposal: ActionProposal,
        evidence: RemediationEvidenceBundle | None,
        reconciled: bool,
    ) -> InvestigationCompletion:
        summary = (
            f"run_id={run.run_id} trace_id={run.trace_id} "
            f"correlation_id={run.correlation_id} proposal_id={proposal.proposal_id}; "
            "durable remediation proposal created; human approval is still absent."
        )
        return InvestigationCompletion(
            run_id=run.run_id,
            trace_id=run.trace_id,
            correlation_id=run.correlation_id,
            proposal=proposal,
            evidence=evidence,
            final_state=WorkflowState.REMEDIATION_PROPOSED,
            agent_summary=summary,
            reconciled=reconciled,
        )

    def _fail_durable_run(
        self,
        run: Run,
        failure: FailureDetail,
    ) -> InvestigationFlowResult:
        target_state = _FAILURE_STATE[failure.kind]
        try:
            self._transition(run, target_state)
        except (StorageConflictError, StorageDependencyError):
            return self._storage_failure("Failed to persist the terminal investigation state")
        return ControlResult[InvestigationCompletion].failed(failure)

    @staticmethod
    def _failure(
        kind: FailureKind,
        code: str,
        message: str,
        *,
        retryable: bool = False,
    ) -> InvestigationFlowResult:
        return ControlResult[InvestigationCompletion].failed(
            FailureDetail(
                kind=kind,
                code=code,
                message=message,
                retryable=retryable,
            )
        )

    @classmethod
    def _storage_failure(cls, message: str) -> InvestigationFlowResult:
        return cls._failure(
            FailureKind.DEPENDENCY_UNAVAILABLE,
            "DURABLE_TRUTH_UNAVAILABLE",
            message,
            retryable=True,
        )
