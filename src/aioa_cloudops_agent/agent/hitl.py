"""Native Strands HITL prompt derived only from durable typed proposal data."""

import json
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from strands.hooks.events import BeforeToolCallEvent
from strands.interventions import Confirm, Deny, InterventionAction
from strands.vended_interventions.hitl import HumanInTheLoop

from aioa_cloudops_agent.nz import (
    ActionProposal,
    ActionTarget,
    ApprovalDecision,
    AuthorityGate,
    Capability,
    ExpectedPrecondition,
    NonEmptyText,
    ProposalState,
    Sha256Digest,
    ShortIdentifier,
    Uuid7Identifier,
)
from aioa_cloudops_agent.persistence import DurableTruthRepository, compute_evidence_digest
from aioa_cloudops_agent.remediation import STOP_SANDBOX_INSTANCE_TOOL_NAME

STOP_IMPACT_SUMMARY: Literal[
    "Gracefully stopping the sandbox instance is reversible but changes AWS workload state."
] = "Gracefully stopping the sandbox instance is reversible but changes AWS workload state."


class ApprovalPayload(BaseModel):
    """Human-visible mutation facts copied from one immutable durable proposal."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    proposal_id: Uuid7Identifier
    run_id: Uuid7Identifier
    action: Capability
    target: ActionTarget
    expected_precondition: ExpectedPrecondition
    authority: Literal[AuthorityGate.PLAN_AND_CONFIRM] = AuthorityGate.PLAN_AND_CONFIRM
    evidence_hash: Sha256Digest
    impact_summary: Literal[
        "Gracefully stopping the sandbox instance is reversible but changes AWS workload state."
    ] = STOP_IMPACT_SUMMARY

    @model_validator(mode="after")
    def validate_stop_payload(self) -> Self:
        if self.action is not Capability.STOP_SANDBOX_INSTANCE:
            raise ValueError("approval payload must describe the canonical sandbox stop")
        if self.evidence_hash != self.expected_precondition.evidence_hash:
            raise ValueError("approval payload evidence binding is inconsistent")
        return self


class ApprovalInterrupt(BaseModel):
    """Serializable caller boundary returned when native Strands execution pauses."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    interrupt_id: NonEmptyText
    payload: ApprovalPayload
    request_hash: Sha256Digest
    trace_id: Uuid7Identifier
    correlation_id: Uuid7Identifier
    reconciled: bool = False


class ApprovalResumeRequest(BaseModel):
    """Typed external response that must echo the exact durable approval binding."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    interrupt_id: NonEmptyText
    proposal_id: Uuid7Identifier
    run_id: Uuid7Identifier
    action: Capability
    target: ActionTarget
    evidence_hash: Sha256Digest
    request_hash: Sha256Digest
    decision: ApprovalDecision
    actor_session_id: ShortIdentifier
    decision_nonce: NonEmptyText = Field(min_length=16, max_length=256)


def build_approval_payload(proposal: ActionProposal) -> ApprovalPayload:
    """Build the human payload from the durable proposal, never model prose."""

    if not isinstance(proposal, ActionProposal):
        raise TypeError("proposal must be an ActionProposal")
    return ApprovalPayload(
        proposal_id=proposal.proposal_id,
        run_id=proposal.run_id,
        action=proposal.action,
        target=proposal.target,
        expected_precondition=proposal.expected_precondition,
        authority=proposal.authority,
        evidence_hash=proposal.evidence_hash,
    )


def approval_request_hash(payload: ApprovalPayload) -> str:
    """Hash the exact human-visible facts for tamper and replay detection."""

    if not isinstance(payload, ApprovalPayload):
        raise TypeError("payload must be an ApprovalPayload")
    return compute_evidence_digest(payload.model_dump(mode="json"))


class DurableProposalHumanInTheLoop(HumanInTheLoop):
    """Use native Confirm while replacing model input with durable proposal facts."""

    def __init__(
        self,
        repository: DurableTruthRepository,
        *,
        allowed_tools: list[str],
    ) -> None:
        self._repository = repository
        super().__init__(
            allowed_tools=allowed_tools,
            classifier=None,
            enable_trust=False,
            ask=None,
        )

    async def before_tool_call(
        self,
        event: BeforeToolCallEvent,
        **kwargs: object,
    ) -> InterventionAction:
        action = await super().before_tool_call(event, **kwargs)
        if event.tool_use["name"] != STOP_SANDBOX_INSTANCE_TOOL_NAME:
            return action
        if not isinstance(action, Confirm):
            return action
        tool_input = event.tool_use.get("input")
        if not isinstance(tool_input, dict) or set(tool_input) != {"proposal_id"}:
            return Deny(reason="Mutation request must contain only one durable proposal reference.")
        try:
            proposal_id = UUID(str(tool_input["proposal_id"]))
            proposal = self._repository.get_proposal(proposal_id)
            if proposal is None or proposal.state is not ProposalState.AWAITING_APPROVAL:
                raise ValueError("proposal is not durably awaiting approval")
            payload = build_approval_payload(proposal)
            payload_json = json.dumps(
                payload.model_dump(mode="json"),
                allow_nan=False,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            )
        except Exception:
            return Deny(reason="Durable approval payload could not be proven.")
        return Confirm(
            prompt=f"Approve proposal-bound sandbox STOP?\n  Payload: {payload_json}",
            reason=action.reason,
            response=action.response,
            evaluate=action.evaluate,
        )
