"""Materialize and fingerprint the deterministic sanitized W1 incident fixture."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from aioa_cloudops_agent.domain import ContractValidationError, generate_correlation_id

from .contracts import WorkspaceArtifactRef, WorkspaceArtifactType, WorkspaceRef
from .profile import WorkspaceCapabilityProfile

FIXTURE_VERSION = "workspace_render_incident_v1"


class FixtureIntegrityError(ValueError):
    """The server-owned fixture is missing, unsafe, oversized or changed."""


@dataclass(frozen=True, slots=True)
class MaterializedWorkspace:
    """Server-only root binding; the host path is never placed in model contracts."""

    ref: WorkspaceRef
    root: Path
    profile: WorkspaceCapabilityProfile


def artifact_type_for_path(relative_path: str) -> WorkspaceArtifactType:
    """Return the closed artifact type selected from a server-allowlisted name."""

    if relative_path.endswith(".json"):
        return WorkspaceArtifactType.JSON
    if relative_path.endswith(".md"):
        return WorkspaceArtifactType.MARKDOWN
    if relative_path.endswith(".sh"):
        return WorkspaceArtifactType.SHELL
    if relative_path.endswith(('.yaml', '.yml')):
        return WorkspaceArtifactType.YAML
    return WorkspaceArtifactType.TEXT


def canonical_artifact_set_digest(
    profile: WorkspaceCapabilityProfile,
    artifacts: tuple[WorkspaceArtifactRef, ...],
) -> str:
    """Hash deterministic names and content identities, never host metadata."""

    payload = {
        "artifacts": [
            {
                "relative_path": artifact.relative_path,
                "sha256": artifact.sha256,
                "size": artifact.size,
                "type": artifact.type.value,
            }
            for artifact in artifacts
        ],
        "fixture_version": FIXTURE_VERSION,
        "profile_id": profile.profile_id,
        "profile_version": profile.version,
    }
    encoded = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def inspect_fixture_tree(
    root: Path,
    profile: WorkspaceCapabilityProfile,
) -> tuple[tuple[WorkspaceArtifactRef, ...], str]:
    """Inspect an exact regular-file tree and return its deterministic digest."""

    if not isinstance(root, Path) or not isinstance(profile, WorkspaceCapabilityProfile):
        raise TypeError("fixture inspection requires Path and WorkspaceCapabilityProfile")
    try:
        root_stat = root.lstat()
    except OSError as error:
        raise FixtureIntegrityError("sealed fixture root is unavailable") from error
    if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
        raise FixtureIntegrityError("sealed fixture root must be a real directory")

    expected_files = set(profile.allowed_artifacts)
    expected_directories = {
        parent.as_posix()
        for path in profile.allowed_artifacts
        for parent in Path(path).parents
        if parent != Path(".")
    }
    observed_files: set[str] = set()
    observed_directories: set[str] = set()
    artifacts: list[WorkspaceArtifactRef] = []

    for candidate in sorted(root.rglob("*"), key=lambda path: path.relative_to(root).as_posix()):
        relative_path = candidate.relative_to(root).as_posix()
        try:
            metadata = candidate.lstat()
        except OSError as error:
            raise FixtureIntegrityError("sealed fixture entry is unavailable") from error
        if stat.S_ISLNK(metadata.st_mode):
            raise FixtureIntegrityError("sealed fixture contains a symlink")
        if stat.S_ISDIR(metadata.st_mode):
            observed_directories.add(relative_path)
            continue
        if not stat.S_ISREG(metadata.st_mode):
            raise FixtureIntegrityError("sealed fixture contains a special file")
        if relative_path not in expected_files:
            raise FixtureIntegrityError("sealed fixture contains an unapproved artifact")
        if metadata.st_nlink != 1:
            raise FixtureIntegrityError("sealed fixture contains a multi-link artifact")
        if metadata.st_size > profile.max_file_bytes:
            raise FixtureIntegrityError("sealed fixture artifact exceeds the server quota")
        content = _read_source_file(candidate, metadata)
        artifacts.append(
            WorkspaceArtifactRef(
                relative_path=relative_path,
                type=artifact_type_for_path(relative_path),
                size=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
                nlink=metadata.st_nlink,
            )
        )
        observed_files.add(relative_path)

    if observed_files != expected_files or observed_directories != expected_directories:
        raise FixtureIntegrityError("sealed fixture shape does not match the server allowlist")
    if len(artifacts) > profile.max_files:
        raise FixtureIntegrityError("sealed fixture exceeds the server file-count quota")
    ordered = tuple(sorted(artifacts, key=lambda artifact: artifact.relative_path))
    return ordered, canonical_artifact_set_digest(profile, ordered)


def materialize_sealed_fixture(
    *,
    run_id: UUID,
    fixture_source: Path,
    workspace_parent: Path,
    profile: WorkspaceCapabilityProfile,
    workspace_id_factory: Callable[[], UUID] = generate_correlation_id,
) -> MaterializedWorkspace:
    """Copy one trusted fixture into a new server-owned, content-bound root."""

    if not isinstance(fixture_source, Path) or not isinstance(workspace_parent, Path):
        raise ContractValidationError("fixture_source and workspace_parent must be Paths")
    if not isinstance(profile, WorkspaceCapabilityProfile):
        raise ContractValidationError("profile must be WorkspaceCapabilityProfile")
    if not callable(workspace_id_factory):
        raise ContractValidationError("workspace_id_factory must be callable")
    try:
        parent = workspace_parent.resolve(strict=True)
        source = fixture_source.resolve(strict=True)
    except OSError as error:
        raise FixtureIntegrityError("server workspace or fixture root is unavailable") from error
    if workspace_parent.is_symlink() or not parent.is_dir():
        raise FixtureIntegrityError("server workspace parent must be a real directory")
    if fixture_source.is_symlink() or not source.is_dir():
        raise FixtureIntegrityError("fixture source must be a real directory")

    source_artifacts, source_digest = inspect_fixture_tree(source, profile)
    workspace_id = workspace_id_factory()
    try:
        workspace_ref_candidate = WorkspaceRef(
            run_id=run_id,
            workspace_id=workspace_id,
            fixture_version=FIXTURE_VERSION,
            root_digest=source_digest,
            created_from_digest=source_digest,
        )
    except (TypeError, ValueError) as error:
        raise ContractValidationError("run and workspace identities must be UUIDv7") from error

    root = Path(
        tempfile.mkdtemp(
            prefix=f"aioa-w1-{str(workspace_ref_candidate.workspace_id)[:8]}-",
            dir=parent,
        )
    )
    root.chmod(0o700)
    try:
        for artifact in source_artifacts:
            source_path = source / artifact.relative_path
            destination = root / artifact.relative_path
            destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            content = _read_source_file(source_path, source_path.lstat())
            with destination.open("xb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            destination.chmod(0o400)
        materialized_artifacts, materialized_digest = inspect_fixture_tree(root, profile)
    except Exception:
        _cleanup_incomplete_root(root)
        raise
    if materialized_artifacts != source_artifacts or materialized_digest != source_digest:
        _cleanup_incomplete_root(root)
        raise FixtureIntegrityError("materialized fixture does not match its sealed source")
    return MaterializedWorkspace(
        ref=workspace_ref_candidate,
        root=root,
        profile=profile,
    )


def _read_source_file(path: Path, before: os.stat_result) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise FixtureIntegrityError("sealed fixture artifact cannot be opened safely") from error
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
            raise FixtureIntegrityError("sealed fixture artifact is not a single-link regular file")
        if (opened.st_dev, opened.st_ino, opened.st_size) != (
            before.st_dev,
            before.st_ino,
            before.st_size,
        ):
            raise FixtureIntegrityError("sealed fixture artifact changed before read")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 64 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise FixtureIntegrityError("sealed fixture artifact changed during read")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _cleanup_incomplete_root(root: Path) -> None:
    """Remove only a just-created private root after failed server setup."""

    for candidate in sorted(root.rglob("*"), key=lambda path: len(path.parts), reverse=True):
        try:
            if candidate.is_dir() and not candidate.is_symlink():
                candidate.rmdir()
            else:
                candidate.unlink()
        except OSError:
            pass
    with suppress(OSError):
        root.rmdir()
