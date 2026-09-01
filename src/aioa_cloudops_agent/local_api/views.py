"""Sanitized read models for the portable judge experience."""

from aioa_cloudops_agent.agent.local_composition import LocalHitlRuntime
from aioa_cloudops_agent.config import ModelProviderName, RuntimeMode
from aioa_cloudops_agent.nz import AuditEvent, Checkpoint, Run

from .contracts import (
    LocalApprovalDecisionView,
    LocalApprovalRequestView,
    LocalAuditEventView,
    LocalCheckpointView,
    LocalExecutionIntentView,
    LocalRuntimeView,
    LocalRunView,
)

_PUBLIC_AUDIT_METADATA = frozenset(
    {
        "authority",
        "decision",
        "policy_code",
        "proposal_id",
        "request_id",
        "resource_id",
        "resource_type",
    }
)


def runtime_view(runtime: LocalHitlRuntime) -> LocalRuntimeView:
    """Build public-safe counters from the explicit portable/mock composition."""

    if not isinstance(runtime, LocalHitlRuntime):
        raise TypeError("runtime must be LocalHitlRuntime")
    settings = runtime.runtime_settings
    if (
        settings.mode is not RuntimeMode.PORTABLE
        or settings.model_provider is not ModelProviderName.MOCK
        or settings.aws_calls_allowed
        or runtime.provider_runtime.external_network_allowed
        or runtime.provider_runtime.aws_calls_allowed
    ):
        raise ValueError("judge runtime truth requires the portable deterministic boundary")
    provider_calls = runtime.model_provider.calls + runtime.model_provider.plan_calls
    external_calls = runtime.model_provider.network_calls + runtime.cloud_provider.network_calls
    return LocalRuntimeView(
        runtime_mode=settings.mode.value,
        provider=settings.model_provider.value,
        model_id=runtime.provider_runtime.model_id,
        process_provider_calls=provider_calls,
        process_external_network_calls=external_calls,
        process_sandbox_mutations=runtime.executor.mutation_calls,
    )


def _checkpoint_view(checkpoint: Checkpoint | None) -> LocalCheckpointView | None:
    if checkpoint is None:
        return None
    request = checkpoint.local_approval_request
    approval = checkpoint.local_approval
    intent = checkpoint.local_execution_intent
    return LocalCheckpointView(
        last_safe_state=checkpoint.last_safe_state,
        version=checkpoint.version,
        resource_evidence=checkpoint.resource_evidence,
        remediation_proposal=checkpoint.remediation_proposal,
        approval_request=(
            None
            if request is None
            else LocalApprovalRequestView(
                request_id=request.request_id,
                proposal_id=request.proposal_id,
                proposal_hash=request.proposal_hash,
                evidence_hash=request.evidence_hash,
                proposal_version=request.proposal_version,
                operation_type=request.operation_type,
                target_resource_type=request.target_resource_type,
                target_resource_id=request.target_resource_id,
                requested_at=request.requested_at,
                expires_at=request.expires_at,
                request_hash=request.request_hash,
            )
        ),
        approval=(
            None
            if approval is None
            else LocalApprovalDecisionView(
                request_id=approval.request_id,
                proposal_id=approval.proposal_id,
                request_hash=approval.request_hash,
                proposal_hash=approval.proposal_hash,
                evidence_hash=approval.evidence_hash,
                proposal_version=approval.proposal_version,
                decision=approval.decision,
                decided_at=approval.decided_at,
                decision_hash=approval.decision_hash,
            )
        ),
        execution_intent=(
            None
            if intent is None
            else LocalExecutionIntentView(
                proposal_id=intent.proposal_id,
                proposal_hash=intent.proposal_hash,
                evidence_hash=intent.evidence_hash,
                decision_hash=intent.decision_hash,
                operation_type=intent.operation_type,
                target_resource_type=intent.target_resource_type,
                target_resource_id=intent.target_resource_id,
                registered_at=intent.registered_at,
                intent_hash=intent.intent_hash,
            )
        ),
        execution_receipt=checkpoint.local_execution_receipt,
        verification=checkpoint.local_verification,
    )


def _audit_event_view(event: AuditEvent) -> LocalAuditEventView:
    return LocalAuditEventView(
        event_id=event.event_id,
        type=event.type,
        timestamp=event.timestamp,
        source=event.source,
        redacted_payload_hash=event.redacted_payload_hash,
        metadata={
            key: value
            for key, value in event.metadata.items()
            if key in _PUBLIC_AUDIT_METADATA
        },
    )


def run_view(
    runtime: LocalHitlRuntime,
    run: Run,
    checkpoint: Checkpoint | None,
    audit_events: tuple[AuditEvent, ...],
) -> LocalRunView:
    """Project authoritative state into the sole judge-facing run representation."""

    if not isinstance(runtime, LocalHitlRuntime) or not isinstance(run, Run):
        raise TypeError("runtime and run must use canonical local contracts")
    if checkpoint is not None and checkpoint.run_id != run.run_id:
        raise ValueError("checkpoint does not belong to the requested run")
    if any(event.run_id != run.run_id for event in audit_events):
        raise ValueError("audit timeline contains another run")
    receipt = None if checkpoint is None else checkpoint.local_execution_receipt
    return LocalRunView(
        run=run,
        checkpoint=_checkpoint_view(checkpoint),
        audit_events=tuple(_audit_event_view(event) for event in audit_events),
        runtime=runtime_view(runtime),
        run_sandbox_mutations=int(receipt is not None),
    )
