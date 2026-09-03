"""Exact six-tool adapter for W3 human-bound workspace patch authority."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Final
from uuid import UUID

from opentelemetry import trace
from opentelemetry.trace import Tracer
from strands import tool
from strands.tools.decorator import DecoratedFunctionTool

from aioa_cloudops_agent.domain import ContractValidationError

from .authority import WorkspaceAuthorityService
from .contracts import WorkspaceRef
from .evidence import WorkspaceEvidenceService
from .executor import WorkspaceAtomicPatchExecutor
from .tools import WORKSPACE_TOOL_NAMES, create_workspace_tools

APPLY_APPROVED_WORKSPACE_PATCH_TOOL_NAME: Final = "apply_approved_workspace_patch"
WORKSPACE_AUTHORITY_TOOL_NAMES: Final = (
    *WORKSPACE_TOOL_NAMES,
    APPLY_APPROVED_WORKSPACE_PATCH_TOOL_NAME,
)


@dataclass(frozen=True, slots=True)
class WorkspaceAuthorityToolSet:
    """The exact W1/W2 tools plus one proposal-id-only W3 mutation boundary."""

    inspect_deployment_incident: DecoratedFunctionTool
    list_workspace_artifacts: DecoratedFunctionTool
    read_workspace_artifact: DecoratedFunctionTool
    hash_workspace_artifact: DecoratedFunctionTool
    build_workspace_patch_proposal: DecoratedFunctionTool
    apply_approved_workspace_patch: DecoratedFunctionTool

    @property
    def ordered(self) -> tuple[DecoratedFunctionTool, ...]:
        return (
            self.inspect_deployment_incident,
            self.list_workspace_artifacts,
            self.read_workspace_artifact,
            self.hash_workspace_artifact,
            self.build_workspace_patch_proposal,
            self.apply_approved_workspace_patch,
        )


def create_workspace_authority_tools(
    service: WorkspaceEvidenceService,
    workspace_ref: WorkspaceRef,
    authority: WorkspaceAuthorityService,
    executor: WorkspaceAtomicPatchExecutor,
    *,
    tracer: Tracer | None = None,
) -> WorkspaceAuthorityToolSet:
    """Bind all mutation facts in durable state; the model supplies proposal_id only."""

    if not isinstance(authority, WorkspaceAuthorityService):
        raise ContractValidationError("authority must be WorkspaceAuthorityService")
    if not isinstance(executor, WorkspaceAtomicPatchExecutor):
        raise ContractValidationError("executor must be WorkspaceAtomicPatchExecutor")
    if executor.repository is not authority.repository or executor.jail.workspace_ref != workspace_ref:
        raise ContractValidationError("authority executor must bind this exact workspace")
    base = create_workspace_tools(
        service,
        workspace_ref,
        proposal_sink=authority.persist_proposal,
        tracer=tracer,
    )
    active_tracer = tracer or trace.get_tracer("aioa_cloudops_agent.workspace")

    @tool(name=APPLY_APPROVED_WORKSPACE_PATCH_TOOL_NAME)
    def apply_approved_workspace_patch(proposal_id: UUID) -> dict[str, object]:
        """Apply only the exact durably approved proposal; emit unverified effect truth."""

        with _apply_span(active_tracer, workspace_ref, proposal_id):
            return executor.apply(proposal_id).model_dump(mode="json")

    return WorkspaceAuthorityToolSet(
        inspect_deployment_incident=base.inspect_deployment_incident,
        list_workspace_artifacts=base.list_workspace_artifacts,
        read_workspace_artifact=base.read_workspace_artifact,
        hash_workspace_artifact=base.hash_workspace_artifact,
        build_workspace_patch_proposal=base.build_workspace_patch_proposal,
        apply_approved_workspace_patch=apply_approved_workspace_patch,
    )


@contextmanager
def _apply_span(tracer: Tracer, workspace_ref: WorkspaceRef, proposal_id: UUID):
    with tracer.start_as_current_span("workspace.apply_approved_workspace_patch") as active:
        active.set_attribute("aioa.run_id", str(workspace_ref.run_id))
        active.set_attribute("aioa.workspace_id", str(workspace_ref.workspace_id))
        active.set_attribute("aioa.proposal_id", str(proposal_id))
        active.set_attribute("aioa.authority_gate", "PLAN_AND_CONFIRM")
        active.set_attribute("aioa.operation_class", "EXACT_ATOMIC_PATCH")
        active.set_attribute("aioa.verification_required", True)
        yield active
