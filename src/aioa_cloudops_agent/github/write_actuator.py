"""Deterministic, approval-bound Phase 8 Git/GitHub write actuator."""

from __future__ import annotations

import hashlib
import os
import stat
import tempfile
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Protocol
from uuid import UUID

from aioa_cloudops_agent.execution import (
    ExecutionAuthorityDenied,
    ExecutionCapsule,
    require_execution_authority,
)
from aioa_cloudops_agent.nz import generate_event_id
from aioa_cloudops_agent.patchset import (
    BoundedPatchSetPolicy,
    PatchOperation,
    PatchSet,
    PatchSetPolicyDenied,
)
from aioa_cloudops_agent.repair_loop import (
    DeterministicSemanticReviewer,
    DockerValidationBackend,
    ValidationOutcome,
)
from aioa_cloudops_agent.sandbox import DOCKER_SANDBOX_V1, DockerToolboxIdentity
from aioa_cloudops_agent.workspace.contracts import canonical_workspace_json_digest

from .effect_repository import (
    GitEffectRepositoryError,
    LocalFileGitEffectRepository,
)
from .repository_service import (
    GitHubWriteCredential,
    GitRemoteWriteUnknown,
    GitRepositoryError,
    RepositoryService,
)
from .write_contracts import (
    GitCommitIdentity,
    GitEffectOwnership,
    GitPushAcknowledgement,
    GitReconciliationMarker,
    GitRemoteCommitReadback,
    GitRemoteObservation,
    GitRemoteWriteReceipt,
    GitVerificationReceipt,
    GitWriteActuationResult,
    GitWriteDisposition,
)


class ExactPatchVerifier(Protocol):
    """Rootless sandbox adapter; the actuator accepts only a strict PASS receipt."""

    def verify(
        self,
        *,
        workspace: Path,
        capsule: ExecutionCapsule,
        patchset: PatchSet,
    ) -> GitVerificationReceipt: ...


class _ActuationDenied(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def build_git_verification_receipt(
    capsule: ExecutionCapsule,
    patchset: PatchSet,
    *,
    verified_at: datetime,
    execution_evidence_sha256: str,
) -> GitVerificationReceipt:
    """Build the strict receipt after an external verifier has actually passed."""

    values: dict[str, object] = {
        "capsule_sha256": capsule.capsule_sha256,
        "patchset_sha256": patchset.patchset_sha256,
        "workspace_tree_sha256": patchset.final_tree_sha256,
        "repair_loop_receipt_sha256": capsule.verification.repair_loop_receipt_sha256,
        "sandbox_receipt_sha256": capsule.sandbox.sandbox_receipt_sha256,
        "execution_evidence_sha256": execution_evidence_sha256,
        "verified_at": verified_at,
    }
    provisional = GitVerificationReceipt.model_construct(
        **values,
        result="PASS",
        network_mode="NONE",
        github_credentials_present=0,
        aws_credentials_present=0,
        ssh_credentials_present=0,
        receipt_sha256="0" * 64,
    )
    return GitVerificationReceipt(
        **values,
        receipt_sha256=canonical_workspace_json_digest(
            provisional.model_dump(mode="json", exclude={"receipt_sha256"})
        ),
    )


class DockerExactPatchVerifier:
    """Re-run the approved Python profile in the rootless network-none sandbox."""

    def __init__(
        self,
        *,
        base_root: Path,
        toolbox: DockerToolboxIdentity,
        targeted_test_path: str,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._base_root = base_root
        self._toolbox = toolbox
        self._targeted_test_path = targeted_test_path
        self._clock = clock or (lambda: datetime.now(UTC))

    def verify(
        self,
        *,
        workspace: Path,
        capsule: ExecutionCapsule,
        patchset: PatchSet,
    ) -> GitVerificationReceipt:
        if (
            self._toolbox.image_digest != capsule.sandbox.toolbox_image_sha256
            or DOCKER_SANDBOX_V1.policy_sha256 != capsule.sandbox.policy_sha256
        ):
            raise _ActuationDenied("GIT_SANDBOX_IDENTITY_MISMATCH")
        BoundedPatchSetPolicy().recheck(
            base_root=self._base_root,
            final_root=workspace,
            patchset=patchset,
            checked_at=self._clock(),
        )
        backend = DockerValidationBackend(
            base_root=self._base_root,
            toolbox=self._toolbox,
            targeted_test_path=self._targeted_test_path,
        )
        session = backend.open(workspace, patchset)
        cleanup_orphans = 1
        try:
            fast_and_targeted = session.validate_fast_and_targeted()
            review = DeterministicSemanticReviewer().review(patchset)
            final = session.validate_final()
        finally:
            cleanup_orphans = session.close()
        receipts = (*fast_and_targeted, review, final)
        if cleanup_orphans or any(
            receipt.outcome is not ValidationOutcome.PASS for receipt in receipts
        ):
            raise _ActuationDenied("GIT_SANDBOX_VERIFICATION_FAILED")
        evidence_sha256 = canonical_workspace_json_digest(
            {
                "cleanup_orphans": cleanup_orphans,
                "network_mode": "NONE",
                "patchset_sha256": patchset.patchset_sha256,
                "receipts": [receipt.model_dump(mode="json") for receipt in receipts],
            }
        )
        return build_git_verification_receipt(
            capsule,
            patchset,
            verified_at=self._clock(),
            execution_evidence_sha256=evidence_sha256,
        )
class DeterministicGitHubWriteActuator:
    """One closed remote effect; no shell, merge, tag, force or default-ref API exists."""

    def __init__(
        self,
        service: RepositoryService,
        repository: LocalFileGitEffectRepository,
        verifier: ExactPatchVerifier,
        *,
        clock: Callable[[], datetime] | None = None,
        effect_id_factory: Callable[[], UUID] = generate_event_id,
    ) -> None:
        if not isinstance(repository, LocalFileGitEffectRepository):
            raise TypeError("repository must be LocalFileGitEffectRepository")
        if not callable(getattr(verifier, "verify", None)):
            raise TypeError("verifier must implement verify")
        if clock is not None and not callable(clock):
            raise TypeError("clock must be callable")
        if not callable(effect_id_factory):
            raise TypeError("effect_id_factory must be callable")
        self._service = service
        self._repository = repository
        self._verifier = verifier
        self._clock = clock or (lambda: datetime.now(UTC))
        self._effect_id_factory = effect_id_factory
        self._remote_write_attempts = 0

    @property
    def remote_write_attempts(self) -> int:
        return self._remote_write_attempts

    def execute(
        self,
        capsule: ExecutionCapsule,
        *,
        patchset: PatchSet,
        base_root: Path,
        final_root: Path,
        credential: GitHubWriteCredential | None = None,
    ) -> GitWriteActuationResult:
        """Execute only the exact durable decision already stored for this capsule."""

        ownership: GitEffectOwnership | None = None
        acknowledgement = GitPushAcknowledgement.UNKNOWN
        try:
            if not isinstance(capsule, ExecutionCapsule) or not isinstance(patchset, PatchSet):
                raise _ActuationDenied("GIT_EXECUTION_INPUT_INVALID")

            # Security order 1: independent remote truth precedes authority evaluation.
            observation = self._service.observe(
                base_ref=capsule.base_ref,
                target_branch=capsule.target_branch,
            )

            # Security order 2: decision is durable and independently loaded, never inferred.
            decision = self._repository.get_decision(capsule.approval_request.request_id)
            authority = require_execution_authority(
                capsule,
                decision,
                validated_at=self._clock(),
                completed_operation_ids=self._repository.completed_operation_ids(),
            )
            self._validate_inputs(capsule, patchset, observation, require_target_absent=False)
            if self._service.requires_write_credential and not isinstance(
                credential, GitHubWriteCredential
            ):
                raise _ActuationDenied("GITHUB_WRITE_CREDENTIAL_REQUIRED")

            existing_receipt = self._repository.get_receipt(capsule.operation_id)
            if existing_receipt is not None:
                raise _ActuationDenied("GIT_OPERATION_REPLAY_DENIED")
            existing_marker = self._repository.get_reconciliation(capsule.operation_id)
            if existing_marker is not None:
                return GitWriteActuationResult(
                    disposition=GitWriteDisposition.UNKNOWN,
                    reconciliation=existing_marker,
                )
            ownership = self._repository.get_ownership(capsule.operation_id)
            if ownership is not None:
                return self._reconcile_existing(ownership)
            if observation.target_head is not None:
                raise _ActuationDenied("GIT_TARGET_ALREADY_EXISTS")

            policy = BoundedPatchSetPolicy()
            policy.recheck(
                base_root=base_root,
                final_root=final_root,
                patchset=patchset,
                checked_at=self._clock(),
            )

            with tempfile.TemporaryDirectory(prefix="aioa-w7a-git-actuator-") as temporary:
                root = Path(temporary).resolve()
                root.chmod(0o700)
                workspace = root / "worktree"
                verification_workspace = root / "verification-workspace"
                committed_checkout = root / "committed-checkout"

                # Security order 4: exact base in a disposable AIOA-owned worktree.
                self._service.prepare_exact_base(
                    base_head=capsule.base_head,
                    destination=workspace,
                )

                # Security order 5: re-derive the approved PatchSet before and after materialization.
                _materialize_patchset(
                    workspace=workspace,
                    final_root=final_root,
                    patchset=patchset,
                    operation_id=str(capsule.operation_id),
                )
                _assert_materialized_files(workspace, patchset)
                _export_plain_worktree(final_root, verification_workspace)
                policy.recheck(
                    base_root=base_root,
                    final_root=verification_workspace,
                    patchset=patchset,
                    checked_at=self._clock(),
                )

                # Security order 6: a credential-free/no-network verifier must issue exact proof.
                verification = self._verifier.verify(
                    workspace=verification_workspace,
                    capsule=capsule,
                    patchset=patchset,
                )
                self._validate_verification(capsule, patchset, verification)

                # Security order 7: deterministic commit identity exists before remote authority.
                commit = self._service.create_deterministic_commit(
                    workspace=workspace,
                    base_head=capsule.base_head,
                    changed_paths=capsule.changed_files,
                    operation_id=str(capsule.operation_id),
                    timestamp=capsule.created_at,
                )
                self._service.prepare_commit_snapshot(
                    source_workspace=workspace,
                    commit_sha=commit.commit_sha,
                    destination=committed_checkout,
                )
                _assert_materialized_files(committed_checkout, patchset)
                policy.recheck(
                    base_root=base_root,
                    final_root=final_root,
                    patchset=patchset,
                    checked_at=self._clock(),
                )

                # A second independent read closes base/target drift before ownership is claimed.
                final_precondition = self._service.observe(
                    base_ref=capsule.base_ref,
                    target_branch=capsule.target_branch,
                )
                self._validate_inputs(
                    capsule,
                    patchset,
                    final_precondition,
                    require_target_absent=True,
                )

                # Security order 8: durable claim is fsynced before the first remote write.
                ownership = self._build_ownership(
                    capsule=capsule,
                    authority_receipt_sha256=authority.receipt_sha256,
                    approval_decision_sha256=decision.decision_sha256,
                    commit=commit,
                    verification=verification,
                )
                ownership = self._repository.claim(ownership)

                # Security order 9/10: exactly one structured non-force feature-ref push.
                self._remote_write_attempts += 1
                try:
                    acknowledgement = self._service.push_feature_ref_once(
                        workspace=workspace,
                        commit_sha=commit.commit_sha,
                        target_branch=capsule.target_branch,
                        credential=credential,
                    )
                except GitRemoteWriteUnknown:
                    acknowledgement = GitPushAcknowledgement.UNKNOWN

                # Security order 11/12: ACK and lost ACK both require independent readback.
                return self._close_from_readback(ownership, acknowledgement)
        except ExecutionAuthorityDenied as error:
            return self._denied(error.code)
        except _ActuationDenied as error:
            return self._denied(error.code)
        except (PatchSetPolicyDenied, GitRepositoryError, GitEffectRepositoryError) as error:
            code = getattr(error, "code", "GIT_ACTUATION_DENIED")
            if ownership is None:
                return self._denied(code)
            return self._record_unknown(ownership, code, None)
        except (OSError, ValueError):
            if ownership is None:
                return self._denied("GIT_ACTUATION_VALIDATION_FAILED")
            return self._record_unknown(ownership, "GIT_POST_CLAIM_STATE_UNKNOWN", None)
        except Exception:
            if ownership is None:
                return self._denied("GIT_ACTUATION_DEPENDENCY_FAILED")
            return self._record_unknown(ownership, "GIT_POST_CLAIM_STATE_UNKNOWN", None)

    def _validate_inputs(
        self,
        capsule: ExecutionCapsule,
        patchset: PatchSet,
        observation: GitRemoteObservation,
        *,
        require_target_absent: bool,
    ) -> None:
        if (
            capsule.repository != observation.repository
            or capsule.repository != self._service.identity
        ):
            raise _ActuationDenied("GIT_REMOTE_IDENTITY_MISMATCH")
        if observation.default_branch != capsule.default_branch:
            raise _ActuationDenied("GIT_DEFAULT_BRANCH_DRIFT")
        if capsule.target_branch.casefold() == observation.default_branch.casefold():
            raise _ActuationDenied("GIT_DEFAULT_BRANCH_WRITE_DENIED")
        if observation.base_ref != capsule.base_ref or observation.base_head != capsule.base_head:
            raise _ActuationDenied("GIT_BASE_DRIFT_DENIED")
        if observation.target_branch != capsule.target_branch:
            raise _ActuationDenied("GIT_TARGET_IDENTITY_MISMATCH")
        if require_target_absent and observation.target_head is not None:
            raise _ActuationDenied("GIT_TARGET_ALREADY_EXISTS")
        if (
            patchset.patchset_sha256 != capsule.patchset_sha256
            or patchset.base_head != capsule.base_head
            or tuple(change.path for change in patchset.files) != capsule.changed_files
        ):
            raise _ActuationDenied("GIT_PATCHSET_BINDING_MISMATCH")

    @staticmethod
    def _validate_verification(
        capsule: ExecutionCapsule,
        patchset: PatchSet,
        receipt: GitVerificationReceipt,
    ) -> None:
        if not isinstance(receipt, GitVerificationReceipt):
            raise _ActuationDenied("GIT_VERIFICATION_RECEIPT_INVALID")
        expected = (
            (receipt.capsule_sha256, capsule.capsule_sha256),
            (receipt.patchset_sha256, patchset.patchset_sha256),
            (receipt.workspace_tree_sha256, patchset.final_tree_sha256),
            (
                receipt.repair_loop_receipt_sha256,
                capsule.verification.repair_loop_receipt_sha256,
            ),
            (receipt.sandbox_receipt_sha256, capsule.sandbox.sandbox_receipt_sha256),
        )
        if any(left != right for left, right in expected):
            raise _ActuationDenied("GIT_VERIFICATION_BINDING_MISMATCH")

    def _build_ownership(
        self,
        *,
        capsule: ExecutionCapsule,
        authority_receipt_sha256: str,
        approval_decision_sha256: str,
        commit: GitCommitIdentity,
        verification: GitVerificationReceipt,
    ) -> GitEffectOwnership:
        idempotency_key = "github-write/" + hashlib.sha256(
            f"{capsule.operation_id}:{capsule.capsule_sha256}".encode("ascii")
        ).hexdigest()
        values: dict[str, object] = {
            "operation_id": capsule.operation_id,
            "effect_id": self._effect_id_factory(),
            "idempotency_key": idempotency_key,
            "capsule_sha256": capsule.capsule_sha256,
            "approval_request_sha256": capsule.approval_request.request_sha256,
            "approval_decision_sha256": approval_decision_sha256,
            "authority_receipt_sha256": authority_receipt_sha256,
            "repository": capsule.repository,
            "base_ref": capsule.base_ref,
            "base_head": capsule.base_head,
            "target_branch": capsule.target_branch,
            "expected_commit": commit,
            "verification_receipt_sha256": verification.receipt_sha256,
            "claimed_at": self._clock(),
        }
        provisional = GitEffectOwnership.model_construct(
            **values,
            remote_write_started=False,
            ownership_sha256="0" * 64,
        )
        return GitEffectOwnership(
            **values,
            ownership_sha256=canonical_workspace_json_digest(
                provisional.model_dump(mode="json", exclude={"ownership_sha256"})
            ),
        )

    def _close_from_readback(
        self,
        ownership: GitEffectOwnership,
        acknowledgement: GitPushAcknowledgement,
    ) -> GitWriteActuationResult:
        try:
            observed = self._service.readback_feature_ref(
                target_branch=ownership.target_branch
            )
        except GitRepositoryError as error:
            return self._record_unknown(ownership, error.code, None)
        if observed is None or (
            observed.commit_sha != ownership.expected_commit.commit_sha
            or observed.tree_sha != ownership.expected_commit.tree_sha
        ):
            return self._record_unknown(
                ownership,
                "GIT_REMOTE_READBACK_MISMATCH",
                observed,
            )
        values: dict[str, object] = {
            "operation_id": ownership.operation_id,
            "effect_id": ownership.effect_id,
            "ownership_sha256": ownership.ownership_sha256,
            "capsule_sha256": ownership.capsule_sha256,
            "repository": ownership.repository,
            "base_head": ownership.base_head,
            "target_branch": ownership.target_branch,
            "expected_commit": ownership.expected_commit,
            "observed_commit_sha": observed.commit_sha,
            "observed_tree_sha": observed.tree_sha,
            "push_acknowledgement": acknowledgement,
            "verified_at": self._clock(),
        }
        provisional = GitRemoteWriteReceipt.model_construct(
            **values,
            product_runtime_writes=1,
            force_pushes=0,
            tag_writes=0,
            default_branch_writes=0,
            merges=0,
            receipt_sha256="0" * 64,
        )
        receipt = GitRemoteWriteReceipt(
            **values,
            receipt_sha256=canonical_workspace_json_digest(
                provisional.model_dump(mode="json", exclude={"receipt_sha256"})
            ),
        )
        return GitWriteActuationResult(
            disposition=GitWriteDisposition.VERIFIED,
            receipt=self._repository.save_receipt(receipt),
        )

    def _reconcile_existing(
        self,
        ownership: GitEffectOwnership,
    ) -> GitWriteActuationResult:
        """Resume only by readback; an owned operation is never pushed twice."""

        return self._close_from_readback(ownership, GitPushAcknowledgement.UNKNOWN)

    def _record_unknown(
        self,
        ownership: GitEffectOwnership,
        reason_code: str,
        observed: GitRemoteCommitReadback | None,
    ) -> GitWriteActuationResult:
        values: dict[str, object] = {
            "operation_id": ownership.operation_id,
            "effect_id": ownership.effect_id,
            "ownership_sha256": ownership.ownership_sha256,
            "expected_commit_sha": ownership.expected_commit.commit_sha,
            "expected_tree_sha": ownership.expected_commit.tree_sha,
            "observed_commit_sha": None if observed is None else observed.commit_sha,
            "observed_tree_sha": None if observed is None else observed.tree_sha,
            "reason_code": reason_code,
            "recorded_at": self._clock(),
        }
        provisional = GitReconciliationMarker.model_construct(
            **values,
            write_attempted=True,
            blind_retry_allowed=False,
            marker_sha256="0" * 64,
        )
        marker = GitReconciliationMarker(
            **values,
            marker_sha256=canonical_workspace_json_digest(
                provisional.model_dump(mode="json", exclude={"marker_sha256"})
            ),
        )
        with suppress(GitEffectRepositoryError):
            marker = self._repository.save_reconciliation(marker)
        return GitWriteActuationResult(
            disposition=GitWriteDisposition.UNKNOWN,
            reconciliation=marker,
        )

    @staticmethod
    def _denied(code: str) -> GitWriteActuationResult:
        return GitWriteActuationResult(
            disposition=GitWriteDisposition.DENIED,
            failure_code=code,
        )


def _export_plain_worktree(source: Path, destination: Path) -> None:
    """Export regular single-link files while refusing repository-tree tricks."""

    source = source.resolve(strict=True)
    if destination.exists() or not destination.is_absolute():
        raise _ActuationDenied("GIT_EXPORT_DESTINATION_INVALID")
    destination.mkdir(mode=0o700)
    for current_text, directories, files in os.walk(source, topdown=True, followlinks=False):
        current = Path(current_text)
        relative_dir = current.relative_to(source)
        if relative_dir == Path(".") and ".git" in directories:
            metadata = (current / ".git").lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                raise _ActuationDenied("GIT_METADATA_PATH_INVALID")
            directories.remove(".git")
        for directory in tuple(directories):
            metadata = (current / directory).lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                raise _ActuationDenied("GIT_WORKTREE_SYMLINK_DENIED")
            target_directory = destination / relative_dir / directory
            target_directory.mkdir(mode=stat.S_IMODE(metadata.st_mode), parents=True, exist_ok=True)
        for name in files:
            source_file = current / name
            metadata = source_file.lstat()
            if (
                stat.S_ISLNK(metadata.st_mode)
                or not stat.S_ISREG(metadata.st_mode)
                or metadata.st_nlink != 1
            ):
                raise _ActuationDenied("GIT_WORKTREE_NONREGULAR_FILE_DENIED")
            relative = source_file.relative_to(source)
            target = destination / relative
            target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
            content = _read_regular(source_file, metadata)
            descriptor = os.open(
                target,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                stat.S_IMODE(metadata.st_mode),
            )
            try:
                _write_all(descriptor, content)
                os.fchmod(descriptor, stat.S_IMODE(metadata.st_mode))
            finally:
                os.close(descriptor)


def _read_regular(path: Path, expected: os.stat_result) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        before = os.fstat(descriptor)
        identity = (expected.st_dev, expected.st_ino, expected.st_size, expected.st_mtime_ns)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != identity
        ):
            raise _ActuationDenied("GIT_FILE_IDENTITY_DRIFT")
        content = bytearray()
        while len(content) < before.st_size:
            chunk = os.read(descriptor, min(64 * 1024, before.st_size - len(content)))
            if not chunk:
                raise _ActuationDenied("GIT_FILE_SHORT_READ")
            content.extend(chunk)
        if os.read(descriptor, 1):
            raise _ActuationDenied("GIT_FILE_GREW_DURING_READ")
        after = os.fstat(descriptor)
        if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != identity:
            raise _ActuationDenied("GIT_FILE_IDENTITY_DRIFT")
        return bytes(content)
    finally:
        os.close(descriptor)


def _write_all(descriptor: int, content: bytes) -> None:
    offset = 0
    while offset < len(content):
        written = os.write(descriptor, content[offset:])
        if written <= 0:
            raise OSError("short write")
        offset += written
    os.fsync(descriptor)


def _materialize_patchset(
    *,
    workspace: Path,
    final_root: Path,
    patchset: PatchSet,
    operation_id: str,
) -> None:
    root_descriptor = os.open(
        workspace,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        for change in patchset.files:
            parts = PurePosixPath(change.path).parts
            parent = _open_parent(root_descriptor, parts[:-1], create=change.operation is PatchOperation.ADD)
            try:
                name = parts[-1]
                before = _read_target_identity(parent, name)
                if change.operation is PatchOperation.ADD:
                    if before is not None:
                        raise _ActuationDenied("GIT_ADD_TARGET_EXISTS")
                elif before != change.before:
                    raise _ActuationDenied("GIT_MATERIALIZATION_BEFORE_MISMATCH")
                if change.operation is PatchOperation.DELETE:
                    os.unlink(name, dir_fd=parent)
                    os.fsync(parent)
                    continue
                assert change.after is not None
                source = final_root.joinpath(*parts)
                try:
                    source_metadata = source.lstat()
                except OSError as error:
                    raise _ActuationDenied("GIT_AFTER_CONTENT_MISSING") from error
                if (
                    stat.S_ISLNK(source_metadata.st_mode)
                    or not stat.S_ISREG(source_metadata.st_mode)
                    or source_metadata.st_nlink != 1
                ):
                    raise _ActuationDenied("GIT_AFTER_CONTENT_NONREGULAR")
                content = _read_regular(source, source_metadata)
                if (
                    hashlib.sha256(content).hexdigest() != change.after.sha256
                    or len(content) != change.after.size
                    or stat.S_IMODE(source_metadata.st_mode) != change.after.mode
                ):
                    raise _ActuationDenied("GIT_AFTER_CONTENT_IDENTITY_MISMATCH")
                temporary = f".aioa-{operation_id}.tmp"
                descriptor = os.open(
                    temporary,
                    os.O_WRONLY
                    | os.O_CREAT
                    | os.O_EXCL
                    | getattr(os, "O_NOFOLLOW", 0),
                    change.after.mode,
                    dir_fd=parent,
                )
                try:
                    _write_all(descriptor, content)
                    os.fchmod(descriptor, change.after.mode)
                finally:
                    os.close(descriptor)
                try:
                    current = _read_target_identity(parent, name)
                    if change.operation is PatchOperation.ADD:
                        if current is not None:
                            raise _ActuationDenied("GIT_ADD_TARGET_DRIFT")
                    elif current != change.before:
                        raise _ActuationDenied("GIT_MATERIALIZATION_TOCTOU_DRIFT")
                    os.replace(temporary, name, src_dir_fd=parent, dst_dir_fd=parent)
                    os.fsync(parent)
                finally:
                    with suppress(OSError):
                        os.unlink(temporary, dir_fd=parent)
            finally:
                os.close(parent)
    finally:
        os.close(root_descriptor)


def _assert_materialized_files(workspace: Path, patchset: PatchSet) -> None:
    """Re-hash every approved path from the actual Git worktree/commit snapshot."""

    root_descriptor = os.open(
        workspace,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        for change in patchset.files:
            parts = PurePosixPath(change.path).parts
            parent = _open_parent(root_descriptor, parts[:-1], create=False)
            try:
                observed = _read_target_identity(parent, parts[-1])
            finally:
                os.close(parent)
            if change.operation is PatchOperation.DELETE:
                if observed is not None:
                    raise _ActuationDenied("GIT_DELETED_PATH_REAPPEARED")
            elif observed != change.after:
                raise _ActuationDenied("GIT_MATERIALIZED_AFTER_MISMATCH")
    finally:
        os.close(root_descriptor)


def _open_parent(root_descriptor: int, parts: tuple[str, ...], *, create: bool) -> int:
    current = os.dup(root_descriptor)
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        for part in parts:
            try:
                following = os.open(part, flags, dir_fd=current)
            except FileNotFoundError:
                if not create:
                    raise _ActuationDenied("GIT_PATCH_PARENT_MISSING") from None
                os.mkdir(part, mode=0o755, dir_fd=current)
                following = os.open(part, flags, dir_fd=current)
            os.close(current)
            current = following
        return current
    except Exception:
        os.close(current)
        raise


def _read_target_identity(parent: int, name: str):
    try:
        metadata = os.stat(name, dir_fd=parent, follow_symlinks=False)
    except FileNotFoundError:
        return None
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
    ):
        raise _ActuationDenied("GIT_PATCH_TARGET_NONREGULAR")
    descriptor = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent)
    try:
        content = bytearray()
        while True:
            chunk = os.read(descriptor, 64 * 1024)
            if not chunk:
                break
            content.extend(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if (metadata.st_dev, metadata.st_ino, metadata.st_size) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
    ):
        raise _ActuationDenied("GIT_PATCH_TARGET_DRIFT")
    from aioa_cloudops_agent.patchset import FileContentIdentity

    return FileContentIdentity(
        sha256=hashlib.sha256(content).hexdigest(),
        size=len(content),
        mode=stat.S_IMODE(after.st_mode),
    )
