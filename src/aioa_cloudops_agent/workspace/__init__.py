"""Heritage-aware sealed workspace foundation for AIOA W1."""

from .contracts import (
    WorkspaceArtifactRef,
    WorkspaceArtifactType,
    WorkspaceEvidenceOutcome,
    WorkspaceEvidenceReceipt,
    WorkspaceHashResult,
    WorkspaceListResult,
    WorkspaceObservation,
    WorkspaceOperation,
    WorkspacePolicyDecision,
    WorkspacePolicyOutcome,
    WorkspaceReadReceipt,
    WorkspaceReadResult,
    WorkspaceRef,
    normalize_workspace_relative_path,
)
from .fixture import (
    FIXTURE_VERSION,
    FixtureIntegrityError,
    MaterializedWorkspace,
    canonical_artifact_set_digest,
    inspect_fixture_tree,
    materialize_sealed_fixture,
)
from .profile import (
    WORKSPACE_REMEDIATION_PROFILE_ID,
    WORKSPACE_REMEDIATION_PROFILE_VERSION,
    WORKSPACE_REMEDIATION_V1,
    WorkspaceCapabilityProfile,
)

__all__ = [
    "FIXTURE_VERSION",
    "WORKSPACE_REMEDIATION_PROFILE_ID",
    "WORKSPACE_REMEDIATION_PROFILE_VERSION",
    "WORKSPACE_REMEDIATION_V1",
    "FixtureIntegrityError",
    "MaterializedWorkspace",
    "WorkspaceArtifactRef",
    "WorkspaceArtifactType",
    "WorkspaceCapabilityProfile",
    "WorkspaceEvidenceOutcome",
    "WorkspaceEvidenceReceipt",
    "WorkspaceHashResult",
    "WorkspaceListResult",
    "WorkspaceObservation",
    "WorkspaceOperation",
    "WorkspacePolicyDecision",
    "WorkspacePolicyOutcome",
    "WorkspaceReadReceipt",
    "WorkspaceReadResult",
    "WorkspaceRef",
    "canonical_artifact_set_digest",
    "inspect_fixture_tree",
    "materialize_sealed_fixture",
    "normalize_workspace_relative_path",
]
