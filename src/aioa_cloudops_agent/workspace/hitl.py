"""Native Strands pre-dispatch gate for the proposal-id-only W3 apply tool."""

from __future__ import annotations

from uuid import UUID

from strands.hooks.events import BeforeToolCallEvent
from strands.interventions import Confirm, Deny, InterventionAction
from strands.vended_interventions.hitl import HumanInTheLoop

from .authority import WorkspaceAuthorityDenied, WorkspaceAuthorityService


class WorkspacePatchHumanInTheLoop(HumanInTheLoop):
    """Allow W1/W2 reads/proposal; require durable exact confirmation for W3 apply."""

    def __init__(
        self,
        authority: WorkspaceAuthorityService,
        *,
        freely_allowed_tools: tuple[str, ...],
        apply_tool_name: str,
    ) -> None:
        if not isinstance(authority, WorkspaceAuthorityService):
            raise TypeError("authority must be WorkspaceAuthorityService")
        if not apply_tool_name or apply_tool_name in freely_allowed_tools:
            raise ValueError("apply tool must be distinct from freely allowed tools")
        self._authority = authority
        self._apply_tool_name = apply_tool_name
        self._complete_tool_surface = frozenset((*freely_allowed_tools, apply_tool_name))
        self._last_denial_code: str | None = None
        super().__init__(
            allowed_tools=list(freely_allowed_tools),
            classifier=None,
            enable_trust=False,
            ask=None,
        )

    @property
    def last_denial_code(self) -> str | None:
        return self._last_denial_code

    async def before_tool_call(
        self,
        event: BeforeToolCallEvent,
        **kwargs: object,
    ) -> InterventionAction:
        tool_name = event.tool_use.get("name")
        if tool_name not in self._complete_tool_surface:
            self._last_denial_code = "WORKSPACE_UNKNOWN_TOOL_DENIED"
            return Deny(reason="Tool is outside the fixed workspace capability surface.")
        if tool_name != self._apply_tool_name:
            return await super().before_tool_call(event, **kwargs)

        tool_input = event.tool_use.get("input")
        if not isinstance(tool_input, dict) or set(tool_input) != {"proposal_id"}:
            self._last_denial_code = "WORKSPACE_APPLY_SCHEMA_DENIED"
            return Deny(reason="Patch apply accepts exactly one durable proposal_id.")
        try:
            proposal_id = UUID(str(tool_input["proposal_id"]))
            payload = self._authority.durable_payload_for_interrupt(proposal_id)
        except (TypeError, ValueError, WorkspaceAuthorityDenied):
            self._last_denial_code = "WORKSPACE_DURABLE_PAYLOAD_DENIED"
            return Deny(reason="Durable workspace approval payload could not be proven.")

        action = await super().before_tool_call(event, **kwargs)
        if not isinstance(action, Confirm):
            self._last_denial_code = "WORKSPACE_NATIVE_CONFIRMATION_DENIED"
            return Deny(reason="Native workspace confirmation could not be established.")
        self._last_denial_code = None
        return Confirm(
            prompt=self._authority.approval_prompt(payload),
            reason=action.reason,
            response=action.response,
            evaluate=action.evaluate,
        )
