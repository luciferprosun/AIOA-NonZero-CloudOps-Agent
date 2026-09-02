"""Fixed server-owned W1 capability profile; no dynamic registry."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from aioa_cloudops_agent.nz.contracts import NonZeroContract

from .contracts import WorkspaceOperation, normalize_workspace_relative_path

WORKSPACE_REMEDIATION_PROFILE_ID = "WORKSPACE_REMEDIATION_V1"
WORKSPACE_REMEDIATION_PROFILE_VERSION = "1"


class WorkspaceCapabilityProfile(NonZeroContract):
    """The complete immutable authority envelope for W1."""

    profile_id: Literal["WORKSPACE_REMEDIATION_V1"] = WORKSPACE_REMEDIATION_PROFILE_ID
    version: Literal["1"] = WORKSPACE_REMEDIATION_PROFILE_VERSION
    allowed_artifacts: tuple[str, ...] = Field(min_length=1, max_length=64)
    max_file_bytes: int = Field(gt=0, le=16 * 1024 * 1024)
    max_read_bytes: int = Field(gt=0, le=16 * 1024 * 1024)
    max_files: int = Field(gt=0, le=64)
    allowed_operations: tuple[WorkspaceOperation, ...] = (
        WorkspaceOperation.INSPECT,
        WorkspaceOperation.LIST,
        WorkspaceOperation.READ,
        WorkspaceOperation.HASH,
    )
    network_allowed: Literal[False] = False
    mutation_allowed: Literal[False] = False

    @field_validator("allowed_artifacts")
    @classmethod
    def validate_allowed_artifacts(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(normalize_workspace_relative_path(path) for path in value)
        if normalized != tuple(sorted(set(normalized))):
            raise ValueError("allowed_artifacts must be unique and canonically ordered")
        return normalized

    @field_validator("allowed_operations")
    @classmethod
    def validate_allowed_operations(
        cls,
        value: tuple[WorkspaceOperation, ...],
    ) -> tuple[WorkspaceOperation, ...]:
        canonical = (
            WorkspaceOperation.INSPECT,
            WorkspaceOperation.LIST,
            WorkspaceOperation.READ,
            WorkspaceOperation.HASH,
        )
        if value != canonical:
            raise ValueError("W1 operations are fixed and cannot be expanded")
        return value

    @model_validator(mode="after")
    def validate_server_bounds(self) -> Self:
        if len(self.allowed_artifacts) > self.max_files:
            raise ValueError("allowlisted artifact count exceeds max_files")
        if self.max_read_bytes > self.max_file_bytes:
            raise ValueError("max_read_bytes cannot exceed max_file_bytes")
        return self


WORKSPACE_REMEDIATION_V1 = WorkspaceCapabilityProfile(
    allowed_artifacts=(
        "README.md",
        "deployment.log",
        "expected_runtime_contract.json",
        "render.yaml",
        "scripts/render_start.sh",
    ),
    max_file_bytes=32 * 1024,
    max_read_bytes=4 * 1024,
    max_files=5,
)
