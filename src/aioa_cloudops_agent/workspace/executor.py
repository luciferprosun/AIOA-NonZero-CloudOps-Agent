"""Private W3 at-most-once atomic executor for the exact approved W2 patch."""

from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime
from uuid import UUID

from aioa_cloudops_agent.nz import (
    ApprovalDecision,
    ControlResult,
    FailureDetail,
    FailureKind,
    generate_event_id,
)

from .authority_contracts import (
    PatchApplyReceipt,
    WorkspaceAuthorityState,
    WorkspaceEffectOwnership,
    WorkspaceReconciliationMarker,
    build_workspace_approval_payload,
    workspace_approval_request_hash,
)
from .authority_repository import (
    LocalFileWorkspaceAuthorityRepository,
    WorkspaceAuthorityConflict,
    WorkspaceAuthorityStorageError,
)
from .contracts import W2_TARGET_PATH, WorkspaceArtifactRef, WorkspacePatchProposal
from .fixture import FixtureIntegrityError, inspect_fixture_tree
from .jail import WorkspaceJail

WorkspacePatchApplyResult = ControlResult[PatchApplyReceipt]


class _PreEffectDenied(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class WorkspaceAtomicPatchExecutor:
    """Apply durable proposal bytes once; never execute or verify the patched config."""

    def __init__(
        self,
        jail: WorkspaceJail,
        repository: LocalFileWorkspaceAuthorityRepository,
        *,
        clock: Callable[[], datetime] | None = None,
        effect_id_factory: Callable[[], UUID] = generate_event_id,
    ) -> None:
        if not isinstance(jail, WorkspaceJail):
            raise TypeError("jail must be WorkspaceJail")
        if not isinstance(repository, LocalFileWorkspaceAuthorityRepository):
            raise TypeError("repository must be LocalFileWorkspaceAuthorityRepository")
        if clock is not None and not callable(clock):
            raise TypeError("clock must be callable")
        if not callable(effect_id_factory):
            raise TypeError("effect_id_factory must be callable")
        self._jail = jail
        self._repository = repository
        self._clock = clock or (lambda: datetime.now(UTC))
        self._effect_id_factory = effect_id_factory
        self._mutation_count = 0
        try:
            root_stat = jail.server_root.lstat()
        except OSError as error:
            raise ValueError("workspace root is unavailable") from error
        if (
            not stat.S_ISDIR(root_stat.st_mode)
            or stat.S_ISLNK(root_stat.st_mode)
            or root_stat.st_uid != os.getuid()
        ):
            raise ValueError("workspace root is not a private owned directory")
        self._root_identity = (root_stat.st_dev, root_stat.st_ino)

    @property
    def mutation_count(self) -> int:
        return self._mutation_count

    @property
    def jail(self) -> WorkspaceJail:
        return self._jail

    @property
    def repository(self) -> LocalFileWorkspaceAuthorityRepository:
        return self._repository

    def apply(self, proposal_id: UUID) -> WorkspacePatchApplyResult:
        """Load proposal_id-only authority and perform or reconcile one exact effect."""

        root_descriptor = -1
        temporary_name: str | None = None
        ownership: WorkspaceEffectOwnership | None = None
        try:
            record = self._repository.get_proposal_record(proposal_id)
            if record is None:
                raise _PreEffectDenied(
                    "WORKSPACE_PROPOSAL_NOT_FOUND",
                    "Durable workspace proposal does not exist.",
                )
            existing_receipt = self._repository.get_receipt(proposal_id)
            if existing_receipt is not None:
                return WorkspacePatchApplyResult.succeeded(existing_receipt)
            if self._repository.get_reconciliation(proposal_id) is not None:
                return self._failed(
                    FailureKind.RECOVERY_REQUIREMENT,
                    "WORKSPACE_RECONCILIATION_REQUIRED",
                    "Workspace effect requires independent reconciliation.",
                )

            proposal = record.proposal
            decision = self._repository.get_decision(proposal_id)
            request = self._repository.get_request(proposal_id)
            self._validate_authority(record.state, proposal, request, decision)
            root_descriptor = self._open_root()

            ownership = self._repository.get_ownership(proposal_id)
            if record.state is WorkspaceAuthorityState.APPLYING:
                if ownership is None:
                    raise _PreEffectDenied(
                        "WORKSPACE_EFFECT_OWNERSHIP_MISSING",
                        "Applying state lacks durable effect ownership.",
                    )
                observed = self._try_target_digest(root_descriptor)
                if observed == proposal.canonical_after_sha256:
                    self._mark_reconciliation(
                        proposal,
                        ownership,
                        observed,
                        "TARGET_ALREADY_AFTER_WITHOUT_RECEIPT",
                    )
                    return self._failed(
                        FailureKind.RECOVERY_REQUIREMENT,
                        "WORKSPACE_EFFECT_RECEIPT_MISSING",
                        "Target is at approved after bytes but receipt requires reconciliation.",
                    )
                if observed != proposal.target_before_sha256:
                    self._mark_reconciliation(
                        proposal,
                        ownership,
                        observed,
                        "TARGET_DIGEST_AMBIGUOUS",
                    )
                    return self._failed(
                        FailureKind.RECOVERY_REQUIREMENT,
                        "WORKSPACE_TARGET_STATE_AMBIGUOUS",
                        "Target state is ambiguous; patch will not be reapplied.",
                    )

            before_artifacts = self._pre_effect_revalidate(root_descriptor, proposal)
            if ownership is None:
                assert decision is not None
                ownership = WorkspaceEffectOwnership.create(
                    proposal,
                    decision,
                    effect_id=self._effect_id_factory(),
                    registered_at=self._clock(),
                )
                ownership, _ = self._repository.claim_effect(ownership)

            self._pre_effect_revalidate(root_descriptor, proposal)
            temporary_name = f".aioa-w3-{ownership.effect_id}.tmp"
            self._write_private_candidate(
                root_descriptor,
                temporary_name,
                proposal.preview.after_text.encode("utf-8"),
            )
            self._before_replace()
            self._assert_exact_target_before(root_descriptor, proposal)
            started_at = ownership.registered_at
            os.replace(
                temporary_name,
                W2_TARGET_PATH,
                src_dir_fd=root_descriptor,
                dst_dir_fd=root_descriptor,
            )
            temporary_name = None
            self._mutation_count += 1
            os.fsync(root_descriptor)

            after_bytes, after_metadata = self._read_relative(
                root_descriptor,
                W2_TARGET_PATH,
            )
            after_sha256 = hashlib.sha256(after_bytes).hexdigest()
            if (
                after_sha256 != proposal.canonical_after_sha256
                or stat.S_IMODE(after_metadata.st_mode) != 0o400
                or after_metadata.st_nlink != 1
            ):
                raise _PreEffectDenied(
                    "WORKSPACE_POST_WRITE_MISMATCH",
                    "Atomic target replacement could not be proven exact.",
                )
            after_artifacts, post_root_digest = inspect_fixture_tree(
                self._jail.server_root,
                self._jail.profile,
            )
            self._assert_exact_scope(before_artifacts, after_artifacts, proposal)
            receipt = PatchApplyReceipt(
                effect_id=ownership.effect_id,
                idempotency_key=ownership.idempotency_key,
                proposal_id=proposal.proposal_id,
                run_id=proposal.run_id,
                trace_id=proposal.trace_id,
                workspace_id=proposal.workspace_id,
                fixture_version=proposal.fixture_version,
                target_path=proposal.target_path,
                before_sha256=proposal.target_before_sha256,
                after_sha256=after_sha256,
                patch_digest=proposal.patch_digest,
                approval_request_hash=ownership.approval_request_hash,
                changed_paths=(W2_TARGET_PATH,),
                post_apply_root_digest=post_root_digest,
                started_at=started_at,
                completed_at=self._clock(),
            )
            return WorkspacePatchApplyResult.succeeded(
                self._repository.save_receipt(receipt)
            )
        except _PreEffectDenied as error:
            if ownership is not None:
                self._reconcile_after_failure(ownership, error.code, root_descriptor)
            return self._failed(
                FailureKind.POLICY_DENIAL,
                error.code,
                error.message,
            )
        except FixtureIntegrityError:
            if ownership is not None:
                self._reconcile_after_failure(
                    ownership,
                    "WORKSPACE_SCOPE_PROOF_FAILED",
                    root_descriptor,
                )
            return self._failed(
                FailureKind.VALIDATION_FAILURE,
                "WORKSPACE_INTEGRITY_DENIED",
                "Workspace integrity could not be proven.",
            )
        except WorkspaceAuthorityConflict:
            return self._failed(
                FailureKind.IDEMPOTENCY_CONFLICT,
                "WORKSPACE_EFFECT_CONFLICT",
                "Durable workspace effect truth conflicts with this request.",
            )
        except WorkspaceAuthorityStorageError:
            return self._failed(
                FailureKind.DEPENDENCY_UNAVAILABLE,
                "WORKSPACE_AUTHORITY_UNAVAILABLE",
                "Durable workspace authority truth is unavailable.",
                retryable=True,
            )
        except (OSError, ValueError):
            if ownership is not None:
                self._reconcile_after_failure(
                    ownership,
                    "WORKSPACE_ATOMIC_WRITE_FAILED",
                    root_descriptor,
                )
            return self._failed(
                FailureKind.EXECUTION_FAILURE,
                "WORKSPACE_ATOMIC_APPLY_FAILED",
                "Exact atomic workspace replacement could not be completed.",
            )
        finally:
            if root_descriptor >= 0 and temporary_name is not None:
                with suppress(OSError):
                    os.unlink(temporary_name, dir_fd=root_descriptor)
            if root_descriptor >= 0:
                os.close(root_descriptor)

    def _validate_authority(self, state, proposal, request, decision) -> None:
        if self._clock() > proposal.expires_at:
            raise _PreEffectDenied(
                "WORKSPACE_PROPOSAL_EXPIRED",
                "Workspace proposal expired before apply.",
            )
        if state is WorkspaceAuthorityState.DENIED_BY_HUMAN:
            raise _PreEffectDenied(
                "WORKSPACE_PATCH_DENIED_BY_HUMAN",
                "Human denial is terminal for this workspace proposal.",
            )
        if state not in {
            WorkspaceAuthorityState.APPROVED,
            WorkspaceAuthorityState.APPLYING,
        }:
            raise _PreEffectDenied(
                "WORKSPACE_PATCH_NOT_APPROVED",
                "Exact durable human approval is required before apply.",
            )
        if request is None or decision is None or decision.decision is not ApprovalDecision.APPROVED:
            raise _PreEffectDenied(
                "WORKSPACE_APPROVAL_MISSING",
                "Approved durable decision is unavailable.",
            )
        payload = build_workspace_approval_payload(proposal)
        request_hash = workspace_approval_request_hash(payload)
        if (
            request.payload != payload
            or request.request_hash != request_hash
            or decision.proposal_id != proposal.proposal_id
            or decision.run_id != proposal.run_id
            or decision.trace_id != proposal.trace_id
            or decision.workspace_id != proposal.workspace_id
            or decision.request_hash != request_hash
            or decision.proposal_digest != proposal.proposal_digest
            or decision.patch_digest != proposal.patch_digest
            or decision.evidence_digest != proposal.evidence_digest
            or decision.base_root_digest != proposal.base_root_digest
        ):
            raise _PreEffectDenied(
                "WORKSPACE_APPROVAL_BINDING_MISMATCH",
                "Durable approval does not bind the exact current proposal.",
            )

    def _open_root(self) -> int:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_DIRECTORY", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(self._jail.server_root, flags)
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or (metadata.st_dev, metadata.st_ino) != self._root_identity
            or metadata.st_uid != os.getuid()
        ):
            os.close(descriptor)
            raise _PreEffectDenied(
                "WORKSPACE_ROOT_REPLACED",
                "Workspace root identity no longer matches the sealed run.",
            )
        return descriptor

    def _pre_effect_revalidate(
        self,
        root_descriptor: int,
        proposal: WorkspacePatchProposal,
    ) -> tuple[WorkspaceArtifactRef, ...]:
        ref = self._jail.workspace_ref
        if (
            proposal.run_id != ref.run_id
            or proposal.workspace_id != ref.workspace_id
            or proposal.fixture_version != ref.fixture_version
            or proposal.base_root_digest != ref.root_digest
            or proposal.root_digest != ref.root_digest
            or proposal.target_path != W2_TARGET_PATH
        ):
            raise _PreEffectDenied(
                "WORKSPACE_IDENTITY_MISMATCH",
                "Proposal does not bind this exact sealed workspace.",
            )
        artifacts, root_digest = inspect_fixture_tree(
            self._jail.server_root,
            self._jail.profile,
        )
        if root_digest != proposal.base_root_digest:
            raise _PreEffectDenied(
                "WORKSPACE_BASE_DIGEST_MISMATCH",
                "Workspace base digest changed before apply.",
            )
        by_path = {artifact.relative_path: artifact for artifact in artifacts}
        expected = {
            W2_TARGET_PATH: proposal.target_before_sha256,
            "scripts/render_start.sh": proposal.supporting_start_script_sha256,
            "expected_runtime_contract.json": proposal.expected_runtime_contract_sha256,
        }
        for relative_path, expected_sha256 in expected.items():
            content, metadata = self._read_relative(root_descriptor, relative_path)
            artifact = by_path.get(relative_path)
            if (
                artifact is None
                or metadata.st_nlink != 1
                or hashlib.sha256(content).hexdigest() != expected_sha256
                or artifact.sha256 != expected_sha256
            ):
                raise _PreEffectDenied(
                    "WORKSPACE_SUPPORT_OR_TARGET_DRIFT",
                    "Target or supporting artifact changed before apply.",
                )
        candidate = proposal.preview.after_text.encode("utf-8")
        if (
            hashlib.sha256(candidate).hexdigest() != proposal.canonical_after_sha256
            or proposal.preview.canonical_patch_digest() != proposal.patch_digest
            or proposal.preview.before_sha256 != proposal.target_before_sha256
        ):
            raise _PreEffectDenied(
                "WORKSPACE_PATCH_IDENTITY_MISMATCH",
                "Durable proposal candidate identity could not be proven.",
            )
        return artifacts

    def _assert_exact_target_before(
        self,
        root_descriptor: int,
        proposal: WorkspacePatchProposal,
    ) -> None:
        content, metadata = self._read_relative(root_descriptor, W2_TARGET_PATH)
        if (
            metadata.st_nlink != 1
            or hashlib.sha256(content).hexdigest() != proposal.target_before_sha256
        ):
            raise _PreEffectDenied(
                "WORKSPACE_TARGET_TOCTOU_DENIED",
                "Target changed immediately before atomic replacement.",
            )

    def _write_private_candidate(
        self,
        root_descriptor: int,
        name: str,
        content: bytes,
    ) -> None:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(name, flags, 0o600, dir_fd=root_descriptor)
        try:
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.getuid()
                or metadata.st_nlink != 1
            ):
                raise OSError("private candidate metadata rejected")
            offset = 0
            while offset < len(content):
                written = os.write(descriptor, content[offset:])
                if written <= 0:
                    raise OSError("private candidate write made no progress")
                offset += written
            os.fchmod(descriptor, 0o400)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _read_relative(
        self,
        root_descriptor: int,
        relative_path: str,
    ) -> tuple[bytes, os.stat_result]:
        parts = relative_path.split("/")
        parent_descriptor = os.dup(root_descriptor)
        try:
            for part in parts[:-1]:
                flags = (
                    os.O_RDONLY
                    | getattr(os, "O_CLOEXEC", 0)
                    | getattr(os, "O_DIRECTORY", 0)
                    | getattr(os, "O_NOFOLLOW", 0)
                )
                next_descriptor = os.open(part, flags, dir_fd=parent_descriptor)
                os.close(parent_descriptor)
                parent_descriptor = next_descriptor
            flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(parts[-1], flags, dir_fd=parent_descriptor)
            try:
                before = os.fstat(descriptor)
                if (
                    not stat.S_ISREG(before.st_mode)
                    or before.st_uid != os.getuid()
                    or before.st_nlink != 1
                    or before.st_size > self._jail.profile.max_file_bytes
                ):
                    raise _PreEffectDenied(
                        "WORKSPACE_TARGET_METADATA_DENIED",
                        "Workspace artifact is not a private single-link regular file.",
                    )
                chunks: list[bytes] = []
                remaining = self._jail.profile.max_file_bytes + 1
                while remaining > 0:
                    chunk = os.read(descriptor, min(64 * 1024, remaining))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    remaining -= len(chunk)
                content = b"".join(chunks)
                after = os.fstat(descriptor)
                if (
                    len(content) > self._jail.profile.max_file_bytes
                    or (
                        before.st_dev,
                        before.st_ino,
                        before.st_size,
                        before.st_mtime_ns,
                        before.st_ctime_ns,
                    )
                    != (
                        after.st_dev,
                        after.st_ino,
                        after.st_size,
                        after.st_mtime_ns,
                        after.st_ctime_ns,
                    )
                ):
                    raise _PreEffectDenied(
                        "WORKSPACE_ARTIFACT_CHANGED_DURING_READ",
                        "Workspace artifact changed during revalidation.",
                    )
                return content, after
            finally:
                os.close(descriptor)
        finally:
            os.close(parent_descriptor)

    @staticmethod
    def _assert_exact_scope(
        before: tuple[WorkspaceArtifactRef, ...],
        after: tuple[WorkspaceArtifactRef, ...],
        proposal: WorkspacePatchProposal,
    ) -> None:
        before_by_path = {item.relative_path: item for item in before}
        after_by_path = {item.relative_path: item for item in after}
        if set(before_by_path) != set(after_by_path):
            raise _PreEffectDenied(
                "WORKSPACE_UNEXPECTED_PATH_CHANGE",
                "Workspace artifact set changed during apply.",
            )
        changed = tuple(
            path
            for path in sorted(before_by_path)
            if before_by_path[path] != after_by_path[path]
        )
        if (
            changed != (W2_TARGET_PATH,)
            or after_by_path[W2_TARGET_PATH].sha256 != proposal.canonical_after_sha256
        ):
            raise _PreEffectDenied(
                "WORKSPACE_UNEXPECTED_ARTIFACT_CHANGE",
                "Atomic apply changed an artifact outside the exact proposal scope.",
            )

    def _try_target_digest(self, root_descriptor: int) -> str | None:
        try:
            content, _ = self._read_relative(root_descriptor, W2_TARGET_PATH)
        except (OSError, ValueError):
            return None
        return hashlib.sha256(content).hexdigest()

    def _mark_reconciliation(
        self,
        proposal: WorkspacePatchProposal,
        ownership: WorkspaceEffectOwnership,
        observed_sha256: str | None,
        reason_code: str,
    ) -> None:
        marker = WorkspaceReconciliationMarker(
            effect_id=ownership.effect_id,
            proposal_id=proposal.proposal_id,
            run_id=proposal.run_id,
            workspace_id=proposal.workspace_id,
            target_path=proposal.target_path,
            observed_sha256=observed_sha256,
            before_sha256=proposal.target_before_sha256,
            after_sha256=proposal.canonical_after_sha256,
            reason_code=reason_code,
            recorded_at=self._clock(),
        )
        self._repository.save_reconciliation(marker)

    def _reconcile_after_failure(
        self,
        ownership: WorkspaceEffectOwnership,
        failure_code: str,
        root_descriptor: int,
    ) -> None:
        if root_descriptor < 0:
            return
        try:
            record = self._repository.get_proposal_record(ownership.proposal_id)
            if record is None or record.state is not WorkspaceAuthorityState.APPLYING:
                return
            observed = self._try_target_digest(root_descriptor)
            if observed == ownership.before_sha256:
                return
            reason = (
                "TARGET_ALREADY_AFTER_WITHOUT_RECEIPT"
                if observed == ownership.after_sha256
                else "TARGET_DIGEST_AMBIGUOUS"
            )
            if failure_code == "WORKSPACE_POST_WRITE_MISMATCH":
                reason = "POST_WRITE_PROOF_INCOMPLETE"
            self._mark_reconciliation(record.proposal, ownership, observed, reason)
        except (OSError, ValueError, WorkspaceAuthorityStorageError, WorkspaceAuthorityConflict):
            return

    def _before_replace(self) -> None:
        """Test seam immediately before the mandatory second target check."""

    @staticmethod
    def _failed(
        kind: FailureKind,
        code: str,
        message: str,
        *,
        retryable: bool = False,
    ) -> WorkspacePatchApplyResult:
        return WorkspacePatchApplyResult.failed(
            FailureDetail(
                kind=kind,
                code=code,
                message=message,
                retryable=retryable,
            )
        )
