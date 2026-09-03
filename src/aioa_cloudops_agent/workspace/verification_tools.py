"""Exact seven-tool adapter for W4 independent workspace verification."""

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
from .authority_tools import WorkspaceAuthorityToolSet, create_workspace_authority_tools
from .contracts import WorkspaceRef
from .evidence import WorkspaceEvidenceService
from .executor import WorkspaceAtomicPatchExecutor
from .tools import WORKSPACE_TOOL_NAMES
from .verifier import WorkspaceIndependentVerifier

VERIFY_WORKSPACE_REMEDIATION_TOOL_NAME: Final = "verify_workspace_remediation"
WORKSPACE_VERIFICATION_TOOL_NAMES: Final = (
    *WORKSPACE_TOOL_NAMES,
    "apply_approved_workspace_patch",
    VERIFY_WORKSPACE_REMEDIATION_TOOL_NAME,
)


@dataclass(frozen=True, slots=True)
class WorkspaceVerificationToolSet:
    """The exact W3 surface plus one proposal-id-only W4 verifier."""

    inspect_deployment_incident: DecoratedFunctionTool
    list_workspace_artifacts: DecoratedFunctionTool
    read_workspace_artifact: DecoratedFunctionTool
    hash_workspace_artifact: DecoratedFunctionTool
    build_workspace_patch_proposal: DecoratedFunctionTool
    apply_approved_workspace_patch: DecoratedFunctionTool
    verify_workspace_remediation: DecoratedFunctionTool

    @property
    def ordered(self) -> tuple[DecoratedFunctionTool, ...]:
        return (
            self.inspect_deployment_incident,
            self.list_workspace_artifacts,
            self.read_workspace_artifact,
            self.hash_workspace_artifact,
            self.build_workspace_patch_proposal,
            self.apply_approved_workspace_patch,
            self.verify_workspace_remediation,
        )


def create_workspace_verification_tools(
    service: WorkspaceEvidenceService,
    workspace_ref: WorkspaceRef,
    authority: WorkspaceAuthorityService,
    executor: WorkspaceAtomicPatchExecutor,
    verifier: WorkspaceIndependentVerifier,
    *,
    tracer: Tracer | None = None,
) -> WorkspaceVerificationToolSet:
    """Expose fixed verification while accepting only one durable proposal identity."""

    if not isinstance(verifier, WorkspaceIndependentVerifier):
        raise ContractValidationError("verifier must be WorkspaceIndependentVerifier")
    if verifier.repository is not authority.repository:
        raise ContractValidationError("verifier must share exact durable authority truth")
    base: WorkspaceAuthorityToolSet = create_workspace_authority_tools(
        service,
        workspace_ref,
        authority,
        executor,
        tracer=tracer,
    )
    active_tracer = tracer or trace.get_tracer("aioa_cloudops_agent.workspace")

    @tool(name=VERIFY_WORKSPACE_REMEDIATION_TOOL_NAME)
    def verify_workspace_remediation(proposal_id: UUID) -> dict[str, object]:
        """Verify one exact approved effect through the fixed server-owned profile."""

        with _verification_span(active_tracer, workspace_ref, proposal_id):
            return verifier.verify(proposal_id).model_dump(mode="json")

    return WorkspaceVerificationToolSet(
        inspect_deployment_incident=base.inspect_deployment_incident,
        list_workspace_artifacts=base.list_workspace_artifacts,
        read_workspace_artifact=base.read_workspace_artifact,
        hash_workspace_artifact=base.hash_workspace_artifact,
        build_workspace_patch_proposal=base.build_workspace_patch_proposal,
        apply_approved_workspace_patch=base.apply_approved_workspace_patch,
        verify_workspace_remediation=verify_workspace_remediation,
    )


@contextmanager
def _verification_span(
    tracer: Tracer,
    workspace_ref: WorkspaceRef,
    proposal_id: UUID,
):
    with tracer.start_as_current_span("workspace.verify_workspace_remediation") as active:
        active.set_attribute("aioa.run_id", str(workspace_ref.run_id))
        active.set_attribute("aioa.workspace_id", str(workspace_ref.workspace_id))
        active.set_attribute("aioa.proposal_id", str(proposal_id))
        active.set_attribute("aioa.authority_gate", "AUTO_AFTER_EXACT_APPROVED_EFFECT")
        active.set_attribute("aioa.operation_class", "FIXED_INDEPENDENT_VERIFICATION")
        active.set_attribute("aioa.model_process_capabilities", 0)
        active.set_attribute("aioa.workspace_code_executions", 0)
        yield active
