"""Exact four-tool Strands adapter for W1 read-only workspace evidence."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Final

from opentelemetry import trace
from opentelemetry.trace import Tracer
from strands import tool
from strands.tools.decorator import DecoratedFunctionTool

from aioa_cloudops_agent.domain import ContractValidationError

from .contracts import WorkspaceRef
from .evidence import WorkspaceEvidenceService

INSPECT_DEPLOYMENT_INCIDENT_TOOL_NAME: Final = "inspect_deployment_incident"
LIST_WORKSPACE_ARTIFACTS_TOOL_NAME: Final = "list_workspace_artifacts"
READ_WORKSPACE_ARTIFACT_TOOL_NAME: Final = "read_workspace_artifact"
HASH_WORKSPACE_ARTIFACT_TOOL_NAME: Final = "hash_workspace_artifact"
WORKSPACE_TOOL_NAMES: Final = (
    INSPECT_DEPLOYMENT_INCIDENT_TOOL_NAME,
    LIST_WORKSPACE_ARTIFACTS_TOOL_NAME,
    READ_WORKSPACE_ARTIFACT_TOOL_NAME,
    HASH_WORKSPACE_ARTIFACT_TOOL_NAME,
)


@dataclass(frozen=True, slots=True)
class WorkspaceToolSet:
    """Fixed tool references used by one workspace Strands profile."""

    inspect_deployment_incident: DecoratedFunctionTool
    list_workspace_artifacts: DecoratedFunctionTool
    read_workspace_artifact: DecoratedFunctionTool
    hash_workspace_artifact: DecoratedFunctionTool

    @property
    def ordered(self) -> tuple[DecoratedFunctionTool, ...]:
        return (
            self.inspect_deployment_incident,
            self.list_workspace_artifacts,
            self.read_workspace_artifact,
            self.hash_workspace_artifact,
        )


def create_workspace_tools(
    service: WorkspaceEvidenceService,
    workspace_ref: WorkspaceRef,
    *,
    tracer: Tracer | None = None,
) -> WorkspaceToolSet:
    """Bind run/workspace identity so the model can supply only artifact names."""

    if not isinstance(service, WorkspaceEvidenceService):
        raise ContractValidationError("service must be WorkspaceEvidenceService")
    if not isinstance(workspace_ref, WorkspaceRef) or workspace_ref != service.workspace_ref:
        raise ContractValidationError("workspace_ref must match the evidence service")
    active_tracer = tracer or trace.get_tracer("aioa_cloudops_agent.workspace")

    @tool(name=INSPECT_DEPLOYMENT_INCIDENT_TOOL_NAME)
    def inspect_deployment_incident() -> dict[str, object]:
        """Inspect bounded incident symptoms, evidence scope and fixture provenance."""

        with _span(active_tracer, service, INSPECT_DEPLOYMENT_INCIDENT_TOOL_NAME):
            return service.inspect_workspace_incident(workspace_ref).model_dump(mode="json")

    @tool(name=LIST_WORKSPACE_ARTIFACTS_TOOL_NAME)
    def list_workspace_artifacts() -> dict[str, object]:
        """List only server-allowlisted artifacts in the current sealed workspace."""

        with _span(active_tracer, service, LIST_WORKSPACE_ARTIFACTS_TOOL_NAME):
            return service.list_allowed_artifacts(workspace_ref).model_dump(mode="json")

    @tool(name=READ_WORKSPACE_ARTIFACT_TOOL_NAME)
    def read_workspace_artifact(relative_path: str) -> dict[str, object]:
        """Read bounded UTF-8 text from one allowlisted relative artifact path."""

        with _span(active_tracer, service, READ_WORKSPACE_ARTIFACT_TOOL_NAME):
            return service.read_allowed_path(workspace_ref, relative_path).model_dump(mode="json")

    @tool(name=HASH_WORKSPACE_ARTIFACT_TOOL_NAME)
    def hash_workspace_artifact(relative_path: str) -> dict[str, object]:
        """Compute SHA-256 for one allowlisted regular file through an independent read."""

        with _span(active_tracer, service, HASH_WORKSPACE_ARTIFACT_TOOL_NAME):
            return service.hash_allowed_path(workspace_ref, relative_path).model_dump(mode="json")

    return WorkspaceToolSet(
        inspect_deployment_incident=inspect_deployment_incident,
        list_workspace_artifacts=list_workspace_artifacts,
        read_workspace_artifact=read_workspace_artifact,
        hash_workspace_artifact=hash_workspace_artifact,
    )


@contextmanager
def _span(
    tracer: Tracer,
    service: WorkspaceEvidenceService,
    tool_name: str,
) -> Iterator[object]:
    with tracer.start_as_current_span(f"workspace.{tool_name}") as active:
        ref = service.workspace_ref
        active.set_attribute("aioa.run_id", str(ref.run_id))
        active.set_attribute("aioa.workspace_id", str(ref.workspace_id))
        active.set_attribute("aioa.fixture_version", ref.fixture_version)
        active.set_attribute("aioa.tool_name", tool_name)
        active.set_attribute("aioa.authority_gate", "AUTO")
        active.set_attribute("aioa.operation_class", "READ_ONLY")
        active.set_attribute("aioa.network_allowed", False)
        active.set_attribute("aioa.mutation_allowed", False)
        yield active
