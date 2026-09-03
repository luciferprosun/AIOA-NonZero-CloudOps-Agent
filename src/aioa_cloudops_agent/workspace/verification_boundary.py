"""Fresh descriptor-confined read-back for the W4 workspace verifier."""

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from .contracts import W2_TARGET_PATH, WorkspaceArtifactRef, WorkspacePatchProposal
from .fixture import (
    MaterializedWorkspace,
    artifact_type_for_path,
    canonical_artifact_set_digest,
    inspect_fixture_tree,
)

_MAX_OBSERVED_ENTRIES = 32
_UNPROVEN_ENTRY = "UNPROVEN_WORKSPACE_ENTRY"


class WorkspaceVerificationBoundaryError(RuntimeError):
    """A server-owned workspace mapping or trusted baseline is unavailable."""


@dataclass(frozen=True, slots=True)
class _RootBinding:
    materialized: MaterializedWorkspace
    fixture_source: Path
    root_device: int
    root_inode: int


@dataclass(frozen=True, slots=True)
class _DiskArtifact:
    relative_path: str
    sha256: str | None
    size: int
    mode: int
    nlink: int
    regular: bool
    owned: bool


@dataclass(frozen=True, slots=True)
class IndependentWorkspaceObservation:
    """Internal fresh state; host paths and file content never enter public contracts."""

    workspace_id: UUID
    provenance_proven: bool
    integrity_proven: bool
    base_root_digest: str
    observed_root_digest: str | None
    actual_changed_paths: tuple[str, ...]
    target_sha256: str | None
    start_script_sha256: str | None
    runtime_contract_sha256: str | None
    render_text: str | None
    issue_code: str | None = None


class WorkspaceVerificationBoundary:
    """Server-owned workspace-id to root mapping with fresh independent reads."""

    def __init__(
        self,
        materialized: MaterializedWorkspace,
        fixture_source: Path,
    ) -> None:
        if not isinstance(materialized, MaterializedWorkspace):
            raise TypeError("materialized must be MaterializedWorkspace")
        if not isinstance(fixture_source, Path):
            raise TypeError("fixture_source must be Path")
        try:
            source = fixture_source.resolve(strict=True)
            source_artifacts, source_digest = inspect_fixture_tree(
                source,
                materialized.profile,
            )
            metadata = materialized.root.lstat()
        except (OSError, ValueError) as error:
            raise WorkspaceVerificationBoundaryError(
                "workspace verification mapping is unavailable"
            ) from error
        if (
            fixture_source.is_symlink()
            or source_digest != materialized.ref.root_digest
            or not source_artifacts
            or not stat.S_ISDIR(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid != os.getuid()
        ):
            raise WorkspaceVerificationBoundaryError(
                "workspace verification mapping does not match its sealed lineage"
            )
        self._bindings = {
            materialized.ref.workspace_id: _RootBinding(
                materialized=materialized,
                fixture_source=source,
                root_device=metadata.st_dev,
                root_inode=metadata.st_ino,
            )
        }

    def reopen(self, proposal: WorkspacePatchProposal) -> IndependentWorkspaceObservation:
        """Reopen by durable identity and recompute both manifests from disk."""

        if not isinstance(proposal, WorkspacePatchProposal):
            raise TypeError("proposal must be WorkspacePatchProposal")
        binding = self._bindings.get(proposal.workspace_id)
        if binding is None:
            raise WorkspaceVerificationBoundaryError(
                "durable workspace identity has no server-owned root mapping"
            )
        materialized = binding.materialized
        if (
            materialized.ref.run_id != proposal.run_id
            or materialized.ref.workspace_id != proposal.workspace_id
            or materialized.ref.fixture_version != proposal.fixture_version
            or materialized.ref.root_digest != proposal.base_root_digest
            or materialized.ref.created_from_digest != proposal.base_root_digest
        ):
            return self._unproven(proposal, "WORKSPACE_PROVENANCE_MISMATCH")
        try:
            base_artifacts, base_digest = inspect_fixture_tree(
                binding.fixture_source,
                materialized.profile,
            )
        except (OSError, ValueError) as error:
            raise WorkspaceVerificationBoundaryError(
                "trusted workspace baseline is unavailable"
            ) from error
        if base_digest != proposal.base_root_digest:
            raise WorkspaceVerificationBoundaryError(
                "trusted workspace baseline no longer matches durable identity"
            )
        try:
            root_metadata = materialized.root.lstat()
        except OSError as error:
            raise WorkspaceVerificationBoundaryError(
                "mapped workspace root is unavailable"
            ) from error
        root_matches = (
            stat.S_ISDIR(root_metadata.st_mode)
            and not stat.S_ISLNK(root_metadata.st_mode)
            and root_metadata.st_uid == os.getuid()
            and (root_metadata.st_dev, root_metadata.st_ino)
            == (binding.root_device, binding.root_inode)
        )
        if not root_matches:
            return self._unproven(proposal, "WORKSPACE_ROOT_IDENTITY_MISMATCH")

        try:
            observed, content, secure_shape = self._scan(binding)
        except OSError:
            return self._unproven(proposal, "WORKSPACE_READ_BACK_FAILED")
        expected_by_path = {artifact.relative_path: artifact for artifact in base_artifacts}
        observed_by_path = {artifact.relative_path: artifact for artifact in observed}
        expected_paths = set(expected_by_path)
        observed_paths = set(observed_by_path)
        changed_paths = set(expected_paths ^ observed_paths)
        for path in expected_paths & observed_paths:
            actual = observed_by_path[path]
            expected = expected_by_path[path]
            if (
                actual.sha256 != expected.sha256
                or actual.size != expected.size
                or actual.mode != 0o400
                or actual.nlink != 1
                or not actual.regular
                or not actual.owned
            ):
                changed_paths.add(path)
        canonical_paths = tuple(sorted(changed_paths))
        if any(self._unsafe_report_path(path) for path in canonical_paths):
            canonical_paths = (_UNPROVEN_ENTRY,)
            secure_shape = False

        exact_shape = secure_shape and observed_paths == expected_paths
        artifact_refs: tuple[WorkspaceArtifactRef, ...] = ()
        if exact_shape:
            artifact_refs = tuple(
                WorkspaceArtifactRef(
                    relative_path=item.relative_path,
                    type=artifact_type_for_path(item.relative_path),
                    size=item.size,
                    sha256=item.sha256,
                    nlink=item.nlink,
                )
                for item in sorted(observed, key=lambda entry: entry.relative_path)
                if item.sha256 is not None
            )
            exact_shape = len(artifact_refs) == len(observed)
        observed_root_digest = (
            canonical_artifact_set_digest(materialized.profile, artifact_refs)
            if exact_shape
            else None
        )
        render_bytes = content.get(W2_TARGET_PATH)
        try:
            render_text = None if render_bytes is None else render_bytes.decode("utf-8")
        except UnicodeDecodeError:
            render_text = None
            secure_shape = False
        return IndependentWorkspaceObservation(
            workspace_id=proposal.workspace_id,
            provenance_proven=True,
            integrity_proven=exact_shape and secure_shape,
            base_root_digest=base_digest,
            observed_root_digest=observed_root_digest,
            actual_changed_paths=canonical_paths,
            target_sha256=self._digest_for(observed_by_path, W2_TARGET_PATH),
            start_script_sha256=self._digest_for(
                observed_by_path,
                "scripts/render_start.sh",
            ),
            runtime_contract_sha256=self._digest_for(
                observed_by_path,
                "expected_runtime_contract.json",
            ),
            render_text=render_text,
            issue_code=None if exact_shape and secure_shape else "WORKSPACE_SHAPE_UNPROVEN",
        )

    def _scan(
        self,
        binding: _RootBinding,
    ) -> tuple[tuple[_DiskArtifact, ...], dict[str, bytes], bool]:
        root_flags = (
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        root_descriptor = os.open(binding.materialized.root, root_flags)
        try:
            opened = os.fstat(root_descriptor)
            if (
                not stat.S_ISDIR(opened.st_mode)
                or opened.st_uid != os.getuid()
                or (opened.st_dev, opened.st_ino)
                != (binding.root_device, binding.root_inode)
            ):
                raise OSError("workspace root changed during reopen")
            artifacts: list[_DiskArtifact] = []
            content: dict[str, bytes] = {}
            secure = self._scan_directory(
                root_descriptor,
                "",
                binding.materialized.profile.max_file_bytes,
                artifacts,
                content,
                [0],
            )
            return tuple(artifacts), content, secure
        finally:
            os.close(root_descriptor)

    def _scan_directory(
        self,
        descriptor: int,
        prefix: str,
        max_file_bytes: int,
        artifacts: list[_DiskArtifact],
        content: dict[str, bytes],
        entry_count: list[int],
    ) -> bool:
        secure = True
        for name in sorted(os.listdir(descriptor)):
            entry_count[0] += 1
            if entry_count[0] > _MAX_OBSERVED_ENTRIES:
                return False
            relative_path = f"{prefix}/{name}" if prefix else name
            metadata = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            if stat.S_ISDIR(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode):
                flags = (
                    os.O_RDONLY
                    | getattr(os, "O_CLOEXEC", 0)
                    | getattr(os, "O_DIRECTORY", 0)
                    | getattr(os, "O_NOFOLLOW", 0)
                )
                child = os.open(name, flags, dir_fd=descriptor)
                try:
                    child_metadata = os.fstat(child)
                    if (
                        child_metadata.st_uid != os.getuid()
                        or stat.S_IMODE(child_metadata.st_mode) != 0o700
                    ):
                        secure = False
                    secure = (
                        self._scan_directory(
                            child,
                            relative_path,
                            max_file_bytes,
                            artifacts,
                            content,
                            entry_count,
                        )
                        and secure
                    )
                finally:
                    os.close(child)
                continue
            regular = stat.S_ISREG(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode)
            owned = metadata.st_uid == os.getuid()
            file_content: bytes | None = None
            if regular and owned and metadata.st_nlink == 1 and metadata.st_size <= max_file_bytes:
                file_content = self._read_file(descriptor, name, metadata, max_file_bytes)
                content[relative_path] = file_content
            else:
                secure = False
            artifacts.append(
                _DiskArtifact(
                    relative_path=relative_path,
                    sha256=(
                        None
                        if file_content is None
                        else hashlib.sha256(file_content).hexdigest()
                    ),
                    size=metadata.st_size,
                    mode=stat.S_IMODE(metadata.st_mode),
                    nlink=metadata.st_nlink,
                    regular=regular,
                    owned=owned,
                )
            )
        return secure

    @staticmethod
    def _read_file(
        parent_descriptor: int,
        name: str,
        before: os.stat_result,
        max_file_bytes: int,
    ) -> bytes:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(name, flags, dir_fd=parent_descriptor)
        try:
            opened = os.fstat(descriptor)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_uid != os.getuid()
                or opened.st_nlink != 1
                or opened.st_size > max_file_bytes
                or (opened.st_dev, opened.st_ino, opened.st_size)
                != (before.st_dev, before.st_ino, before.st_size)
            ):
                raise OSError("workspace artifact changed before independent read")
            chunks: list[bytes] = []
            remaining = max_file_bytes + 1
            while remaining > 0:
                chunk = os.read(descriptor, min(64 * 1024, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            value = b"".join(chunks)
            after = os.fstat(descriptor)
            if (
                len(value) > max_file_bytes
                or (
                    opened.st_dev,
                    opened.st_ino,
                    opened.st_size,
                    opened.st_mtime_ns,
                    opened.st_ctime_ns,
                )
                != (
                    after.st_dev,
                    after.st_ino,
                    after.st_size,
                    after.st_mtime_ns,
                    after.st_ctime_ns,
                )
            ):
                raise OSError("workspace artifact changed during independent read")
            return value
        finally:
            os.close(descriptor)

    @staticmethod
    def _digest_for(values: dict[str, _DiskArtifact], path: str) -> str | None:
        artifact = values.get(path)
        return None if artifact is None else artifact.sha256

    @staticmethod
    def _unsafe_report_path(path: str) -> bool:
        return (
            not path
            or len(path) > 255
            or path.startswith(".")
            or ".." in Path(path).parts
            or any(ord(character) < 32 for character in path)
        )

    @staticmethod
    def _unproven(
        proposal: WorkspacePatchProposal,
        issue_code: str,
    ) -> IndependentWorkspaceObservation:
        return IndependentWorkspaceObservation(
            workspace_id=proposal.workspace_id,
            provenance_proven=False,
            integrity_proven=False,
            base_root_digest=proposal.base_root_digest,
            observed_root_digest=None,
            actual_changed_paths=(),
            target_sha256=None,
            start_script_sha256=None,
            runtime_contract_sha256=None,
            render_text=None,
            issue_code=issue_code,
        )
