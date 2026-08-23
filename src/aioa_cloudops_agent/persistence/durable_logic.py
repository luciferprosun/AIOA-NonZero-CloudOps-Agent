"""Provider-neutral transformations for durable NZ records."""

from aioa_cloudops_agent.nz import (
    ActionOutcome,
    ActionProposal,
    ActionResult,
    IdempotencyStatus,
    ProposalState,
)
from aioa_cloudops_agent.nz.errors import StorageConflictError


def completed_idempotency_status(result: ActionResult) -> IdempotencyStatus:
    """Map an explicit action outcome to its durable idempotency status."""

    if result.outcome is ActionOutcome.SUCCEEDED:
        return IdempotencyStatus.COMPLETED
    if result.outcome is ActionOutcome.FAILED:
        return IdempotencyStatus.FAILED
    return IdempotencyStatus.RECONCILIATION_REQUIRED


def transitioned_proposal(
    proposal: ActionProposal,
    next_state: ProposalState,
) -> ActionProposal:
    """Apply the small application-owned proposal-state policy."""

    allowed = {
        ProposalState.PROPOSED: {
            ProposalState.AWAITING_APPROVAL,
            ProposalState.SUPERSEDED,
        },
        ProposalState.AWAITING_APPROVAL: {ProposalState.SUPERSEDED},
        ProposalState.SUPERSEDED: set(),
    }
    if next_state not in allowed[proposal.state]:
        raise StorageConflictError(
            f"illegal proposal transition: {proposal.state.value} -> {next_state.value}"
        )
    values = proposal.model_dump()
    values["state"] = next_state
    return ActionProposal.model_validate(values)
