"""Race-conscious path confinement for one server-created sealed workspace."""

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from aioa_cloudops_agent.nz import FailureKind

from .contracts import (
    WorkspaceArtifactRef,
    WorkspaceOperation,
    WorkspacePolicyDecision,
    WorkspacePolicyOutcome,
    WorkspaceRef,
    normalize_workspace_relative_path,
)
from .fixture import FixtureIntegrityError, MaterializedWorkspace, inspect_fixture_tree


class WorkspaceJailViolation(ValueError):
    """Safe typed denial which never includes a private host path."""

    def __init__(
        self,
        decision: WorkspacePolicyDecision,
        *,
        failure_kind: FailureKind = FailureKind.POLICY_DENIAL,
    ) -> None:
        self.decision = decision
        self.failure_kind = failure_kind
        super().__init__(decision.reason)


@dataclass(frozen=True, slots=True)
class JailedArtifactRead:
    """Server-internal full bytes read from one revalidated regular file."""

    artifact: WorkspaceArtifactRef
    content: bytes
    policy: WorkspacePolicyDecision


class WorkspaceJail:
    """Bind all W1 reads to one opaque workspace identity and one root inode."""

    def __init__(self, materialized: MaterializedWorkspace) -> None:
        if not isinstance(materialized, MaterializedWorkspace):
            raise TypeError("WorkspaceJail requires MaterializedWorkspace")
        self._root = materialized.root
        self._profile = materialized.profile
        self._ref = materialized.ref
        try:
            metadata = self._root.lstat()
        except OSError as error:
            raise FixtureIntegrityError("sealed workspace root is unavailable") from error
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise FixtureIntegrityError("sealed workspace root must be a real directory")
        self._root_identity = (metadata.st_dev, metadata.st_ino)
        artifacts = self._validated_artifacts(WorkspaceOperation.INSPECT)
        if not artifacts:
            raise FixtureIntegrityError("sealed workspace must contain allowed artifacts")

    @property
    def workspace_ref(self) -> WorkspaceRef:
        """Return only the opaque model-safe root identity."""

        return self._ref

    @property
    def profile(self):
        """Return the fixed immutable capability profile."""

        return self._profile

    @property
    def server_root(self) -> Path:
        """Return the host root for server lifecycle/tests; tools never serialize it."""

        return self._root

    def policy_decision(
        self,
        operation: WorkspaceOperation,
        workspace_ref: WorkspaceRef,
        relative_path: object | None = None,
    ) -> WorkspacePolicyDecision:
        """Evaluate only server-owned identity, operation and allowlist state."""

        if not isinstance(operation, WorkspaceOperation):
            raise TypeError("operation must be WorkspaceOperation")
        if not isinstance(workspace_ref, WorkspaceRef) or workspace_ref != self._ref:
            return self._deny(
                operation,
                "WORKSPACE_CROSS_IDENTITY_DENIED",
                "Workspace identity is outside this sealed run",
            )
        if operation not in self._profile.allowed_operations:
            return self._deny(
                operation,
                "WORKSPACE_CAPABILITY_DENIED",
                "Workspace capability is not registered in W1",
            )
        if operation in {WorkspaceOperation.READ, WorkspaceOperation.HASH}:
            try:
                normalized = normalize_workspace_relative_path(relative_path)
            except ValueError:
                return self._deny(
                    operation,
                    "WORKSPACE_PATH_INVALID",
                    "Artifact path is not a canonical allowed relative path",
                )
            if normalized not in self._profile.allowed_artifacts:
                return self._deny(
                    operation,
                    "WORKSPACE_ARTIFACT_NOT_ALLOWED",
                    "Artifact is outside the server allowlist",
                    artifact_path=normalized,
                )
            return self._allow(operation, artifact_path=normalized)
        if relative_path is not None:
            return self._deny(
                operation,
                "WORKSPACE_PATH_UNEXPECTED",
                "Workspace-wide operation does not accept an artifact path",
            )
        return self._allow(operation)

    def list_artifacts(
        self,
        workspace_ref: WorkspaceRef,
        *,
        operation: WorkspaceOperation = WorkspaceOperation.LIST,
    ) -> tuple[tuple[WorkspaceArtifactRef, ...], WorkspacePolicyDecision]:
        """Return the exact capped manifest after identity and root revalidation."""

        decision = self.policy_decision(operation, workspace_ref)
        self._require_allow(decision)
        return self._validated_artifacts(operation), decision

    def artifact_ref(
        self,
        workspace_ref: WorkspaceRef,
        relative_path: object,
        *,
        operation: WorkspaceOperation,
    ) -> tuple[WorkspaceArtifactRef, WorkspacePolicyDecision]:
        """Resolve an allowlisted name to a current content identity."""

        decision = self.policy_decision(operation, workspace_ref, relative_path)
        self._require_allow(decision)
        artifacts = self._validated_artifacts(operation, decision.artifact_path)
        for artifact in artifacts:
            if artifact.relative_path == decision.artifact_path:
                return artifact, decision
        raise self._violation(
            operation,
            "WORKSPACE_ARTIFACT_MISSING",
            "Allowlisted artifact is missing from the sealed workspace",
            artifact_path=decision.artifact_path,
            failure_kind=FailureKind.NOT_FOUND,
        )

    def read_artifact(
        self,
        workspace_ref: WorkspaceRef,
        artifact_ref: WorkspaceArtifactRef,
        *,
        operation: WorkspaceOperation = WorkspaceOperation.READ,
    ) -> JailedArtifactRead:
        """Open and revalidate one file through root-relative no-follow descriptors."""

        if not isinstance(artifact_ref, WorkspaceArtifactRef):
            raise self._violation(
                operation,
                "WORKSPACE_ARTIFACT_REF_INVALID",
                "Artifact reference is invalid",
                failure_kind=FailureKind.VALIDATION_FAILURE,
            )
        current, decision = self.artifact_ref(
            workspace_ref,
            artifact_ref.relative_path,
            operation=operation,
        )
        if current != artifact_ref:
            raise self._violation(
                operation,
                "WORKSPACE_ARTIFACT_REF_STALE",
                "Artifact reference no longer matches sealed evidence",
                artifact_path=current.relative_path,
                failure_kind=FailureKind.VALIDATION_FAILURE,
            )
        content, metadata = self._secure_read(current.relative_path, operation)
        digest = hashlib.sha256(content).hexdigest()
        if (
            len(content) != current.size
            or digest != current.sha256
            or metadata.st_nlink != current.nlink
        ):
            raise self._violation(
                operation,
                "WORKSPACE_TAMPER_DETECTED",
                "Sealed artifact identity changed during read",
                artifact_path=current.relative_path,
                failure_kind=FailureKind.VALIDATION_FAILURE,
            )
        after = self._validated_artifacts(operation, current.relative_path)
        after_ref = next(
            (artifact for artifact in after if artifact.relative_path == current.relative_path),
            None,
        )
        if after_ref != current:
            raise self._violation(
                operation,
                "WORKSPACE_TAMPER_DETECTED",
                "Sealed artifact changed after read",
                artifact_path=current.relative_path,
                failure_kind=FailureKind.VALIDATION_FAILURE,
            )
        return JailedArtifactRead(artifact=current, content=content, policy=decision)

    def _validated_artifacts(
        self,
        operation: WorkspaceOperation,
        artifact_path: str | None = None,
    ) -> tuple[WorkspaceArtifactRef, ...]:
        self._validate_root_anchor(operation, artifact_path)
        try:
            artifacts, digest = inspect_fixture_tree(self._root, self._profile)
        except FixtureIntegrityError as error:
            raise self._violation(
                operation,
                "WORKSPACE_TAMPER_DETECTED",
                "Sealed workspace integrity validation failed",
                artifact_path=artifact_path,
                failure_kind=FailureKind.VALIDATION_FAILURE,
            ) from error
        if digest != self._ref.root_digest:
            raise self._violation(
                operation,
                "WORKSPACE_ROOT_DIGEST_MISMATCH",
                "Sealed workspace root digest no longer matches its reference",
                artifact_path=artifact_path,
                failure_kind=FailureKind.VALIDATION_FAILURE,
            )
        return artifacts

    def _validate_root_anchor(
        self,
        operation: WorkspaceOperation,
        artifact_path: str | None,
    ) -> None:
        try:
            metadata = self._root.lstat()
        except OSError as error:
            raise self._violation(
                operation,
                "WORKSPACE_ROOT_UNAVAILABLE",
                "Sealed workspace root is unavailable",
                artifact_path=artifact_path,
                failure_kind=FailureKind.DEPENDENCY_UNAVAILABLE,
            ) from error
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISDIR(metadata.st_mode)
            or (metadata.st_dev, metadata.st_ino) != self._root_identity
        ):
            raise self._violation(
                operation,
                "WORKSPACE_ROOT_REPLACED",
                "Sealed workspace root identity changed",
                artifact_path=artifact_path,
                failure_kind=FailureKind.VALIDATION_FAILURE,
            )

    def _secure_read(
        self,
        relative_path: str,
        operation: WorkspaceOperation,
    ) -> tuple[bytes, os.stat_result]:
        nofollow = getattr(os, "O_NOFOLLOW", None)
        directory_flag = getattr(os, "O_DIRECTORY", None)
        if nofollow is None or directory_flag is None:
            raise self._violation(
                operation,
                "WORKSPACE_PLATFORM_UNSUPPORTED",
                "Host cannot provide required no-follow directory reads",
                artifact_path=relative_path,
                failure_kind=FailureKind.CONFIGURATION_ERROR,
            )
        base_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | nofollow
        directory_fds: list[int] = []
        file_descriptor: int | None = None
        try:
            root_fd = os.open(self._root, base_flags | directory_flag)
            directory_fds.append(root_fd)
            root_metadata = os.fstat(root_fd)
            if (root_metadata.st_dev, root_metadata.st_ino) != self._root_identity:
                raise OSError("root identity changed")
            parts = PurePosixPath(relative_path).parts
            current_fd = root_fd
            for part in parts[:-1]:
                next_fd = os.open(part, base_flags | directory_flag, dir_fd=current_fd)
                directory_fds.append(next_fd)
                current_fd = next_fd
            file_descriptor = os.open(
                parts[-1],
                base_flags | getattr(os, "O_NONBLOCK", 0),
                dir_fd=current_fd,
            )
            before = os.fstat(file_descriptor)
            if not stat.S_ISREG(before.st_mode):
                raise OSError("artifact is not regular")
            if before.st_nlink != 1:
                raise OSError("artifact has multiple links")
            if before.st_size > self._profile.max_file_bytes:
                raise OSError("artifact exceeds quota")
            chunks: list[bytes] = []
            observed = 0
            while True:
                chunk = os.read(file_descriptor, min(64 * 1024, self._profile.max_file_bytes + 1))
                if not chunk:
                    break
                chunks.append(chunk)
                observed += len(chunk)
                if observed > self._profile.max_file_bytes:
                    raise OSError("artifact exceeds quota")
            after = os.fstat(file_descriptor)
            identity_before = (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
                before.st_ctime_ns,
            )
            identity_after = (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            )
            if identity_before != identity_after:
                raise OSError("artifact changed during read")
            return b"".join(chunks), after
        except WorkspaceJailViolation:
            raise
        except OSError as error:
            raise self._violation(
                operation,
                "WORKSPACE_SAFE_READ_FAILED",
                "Artifact could not be read through the sealed boundary",
                artifact_path=relative_path,
                failure_kind=FailureKind.VALIDATION_FAILURE,
            ) from error
        finally:
            if file_descriptor is not None:
                os.close(file_descriptor)
            for descriptor in reversed(directory_fds):
                os.close(descriptor)

    def _allow(
        self,
        operation: WorkspaceOperation,
        *,
        artifact_path: str | None = None,
    ) -> WorkspacePolicyDecision:
        return WorkspacePolicyDecision(
            operation=operation,
            workspace_id=self._ref.workspace_id,
            artifact_path=artifact_path,
            outcome=WorkspacePolicyOutcome.ALLOW,
            reason_code="WORKSPACE_READ_ONLY_ALLOWED",
            reason="Operation is bound to the sealed read-only allowlist",
        )

    def _deny(
        self,
        operation: WorkspaceOperation,
        reason_code: str,
        reason: str,
        *,
        artifact_path: str | None = None,
    ) -> WorkspacePolicyDecision:
        return WorkspacePolicyDecision(
            operation=operation,
            workspace_id=self._ref.workspace_id,
            artifact_path=artifact_path,
            outcome=WorkspacePolicyOutcome.DENY,
            reason_code=reason_code,
            reason=reason,
        )

    def _violation(
        self,
        operation: WorkspaceOperation,
        reason_code: str,
        reason: str,
        *,
        artifact_path: str | None = None,
        failure_kind: FailureKind = FailureKind.POLICY_DENIAL,
    ) -> WorkspaceJailViolation:
        return WorkspaceJailViolation(
            self._deny(
                operation,
                reason_code,
                reason,
                artifact_path=artifact_path,
            ),
            failure_kind=failure_kind,
        )

    @staticmethod
    def _require_allow(decision: WorkspacePolicyDecision) -> None:
        if decision.outcome is not WorkspacePolicyOutcome.ALLOW:
            raise WorkspaceJailViolation(decision)
