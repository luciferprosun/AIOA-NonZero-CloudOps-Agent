"""Deterministic actual-filesystem policy for provider-neutral PatchSets."""

from __future__ import annotations

import difflib
import hashlib
import os
import stat
import unicodedata
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath

from aioa_cloudops_agent.agent import digest_workspace_tree
from aioa_cloudops_agent.nz import FailureKind
from aioa_cloudops_agent.nz.redaction import contains_sensitive_material
from aioa_cloudops_agent.sandbox import RepositorySourceIdentity
from aioa_cloudops_agent.workspace.contracts import canonical_workspace_json_digest

from .contracts import (
    FileContentIdentity,
    PatchFileChange,
    PatchOperation,
    PatchPolicyResult,
    PatchSecretScanSummary,
    PatchSet,
    PatchSetContext,
    PatchSetRecheckReceipt,
    PatchTotals,
)

MAX_FILES_CHANGED = 3
MAX_CHANGED_LINES = 300
MAX_DELETED_FILES = 1
MAX_DELETED_LINES = 150
MAX_TREE_FILES = 256
MAX_TREE_BYTES = 16 * 1024 * 1024

_ZERO_DIGEST = "0" * 64
_GENERATED_NAMES = frozenset(
    {
        ".coverage",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
        "build",
        "coverage",
        "dist",
        "htmlcov",
        "node_modules",
    }
)
_SECRET_PARTS = frozenset(
    {
        ".aws",
        ".env",
        ".ssh",
        "auth.json",
        "credentials",
        "id_ed25519",
        "id_rsa",
        "keychain",
        "known_hosts",
        "secrets",
        "tokens",
    }
)
_PROTECTED_ROOT_NAMES = frozenset(
    {
        ".coveragerc",
        ".gitignore",
        ".gitmodules",
        "pytest.ini",
        "ruff.toml",
        "tox.ini",
    }
)
_PROTECTED_CONFIG_NAMES = frozenset(
    {
        "package-lock.json",
        "package.json",
        "pyproject.toml",
        "requirements.txt",
        "uv.lock",
    }
)
_PROTECTED_AUDIT_PREFIXES = (
    "B5_",
    "B6_",
    "W7_",
    "W7A_AGENT_EXECUTION_DISCOVERY",
    "W7A_PHASES_2_4_",
    "W7A_PHASE_1_",
    "W7A_PHASE_2_",
    "W7A_PHASE_3_",
    "W7A_PHASE_4_",
)


class PatchSetPolicyDenied(ValueError):
    """Value-free fail-closed decision from actual workspace inspection."""

    def __init__(
        self,
        code: str,
        *,
        failure_kind: FailureKind = FailureKind.POLICY_DENIAL,
    ) -> None:
        self.code = code
        self.failure_kind = failure_kind
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class _FileRecord:
    path: str
    content: bytes
    identity: FileContentIdentity


@dataclass(frozen=True, slots=True)
class _TreeSnapshot:
    tree_sha256: str
    records: dict[str, _FileRecord]
    total_bytes: int


def normalize_patch_relative_path(value: object) -> str:
    """Validate one exact NFC POSIX path without optimistic canonicalization."""

    if not isinstance(value, str) or not value or value != value.strip():
        raise PatchSetPolicyDenied("PATCHSET_PATH_INVALID")
    if value != unicodedata.normalize("NFC", value):
        raise PatchSetPolicyDenied("PATCHSET_PATH_UNICODE_AMBIGUOUS")
    if "\\" in value or any(unicodedata.category(char).startswith("C") for char in value):
        raise PatchSetPolicyDenied("PATCHSET_PATH_INVALID")
    candidate = PurePosixPath(value)
    if candidate.is_absolute() or candidate.as_posix() != value or not candidate.parts:
        raise PatchSetPolicyDenied("PATCHSET_PATH_TRAVERSAL_DENIED")
    if any(part in {"", ".", ".."} or len(part) > 128 for part in candidate.parts):
        raise PatchSetPolicyDenied("PATCHSET_PATH_TRAVERSAL_DENIED")
    if len(value) > 1024:
        raise PatchSetPolicyDenied("PATCHSET_PATH_INVALID")
    return value


class BoundedPatchSetPolicy:
    """Derive and recheck PatchSets exclusively from actual base/final trees."""

    def evaluate(
        self,
        *,
        base_root: Path,
        final_root: Path,
        base_head: str,
        context: PatchSetContext,
    ) -> PatchSet:
        if not isinstance(context, PatchSetContext):
            raise PatchSetPolicyDenied("PATCHSET_CONTEXT_INVALID")
        if (
            not isinstance(base_head, str)
            or len(base_head) != 40
            or any(character not in "0123456789abcdef" for character in base_head)
        ):
            raise PatchSetPolicyDenied("PATCHSET_BASE_HEAD_INVALID")
        base = _snapshot_tree(base_root)
        final = _snapshot_tree(final_root)
        changed_paths = tuple(
            sorted(
                path
                for path in set(base.records) | set(final.records)
                if _identity(base.records.get(path)) != _identity(final.records.get(path))
            )
        )
        if not changed_paths:
            raise PatchSetPolicyDenied("PATCHSET_EMPTY_DENIED")
        if len(changed_paths) > MAX_FILES_CHANGED:
            raise PatchSetPolicyDenied("PATCHSET_FILE_LIMIT_EXCEEDED")

        changes: list[PatchFileChange] = []
        diff_parts: list[str] = []
        scan_records: list[dict[str, object]] = []
        total_added = 0
        total_deleted = 0
        deletion_count = 0
        for path in changed_paths:
            _reject_protected_path(path)
            before = base.records.get(path)
            after = final.records.get(path)
            if (
                before is not None
                and after is not None
                and before.identity.mode != after.identity.mode
            ):
                raise PatchSetPolicyDenied("PATCHSET_MODE_CHANGE_DENIED")
            before_text = _decode_text(before)
            after_text = _decode_text(after)
            if after is not None and contains_sensitive_material(after_text):
                raise PatchSetPolicyDenied("PATCHSET_SECRET_CONTENT_DENIED")
            operation = (
                PatchOperation.ADD
                if before is None
                else PatchOperation.DELETE
                if after is None
                else PatchOperation.MODIFY
            )
            added, deleted = _line_counts(before_text, after_text)
            total_added += added
            total_deleted += deleted
            if total_added + total_deleted > MAX_CHANGED_LINES:
                raise PatchSetPolicyDenied("PATCHSET_LINE_LIMIT_EXCEEDED")
            deletion_count += operation is PatchOperation.DELETE
            changes.append(
                PatchFileChange(
                    path=path,
                    operation=operation,
                    before=None if before is None else before.identity,
                    after=None if after is None else after.identity,
                    lines_added=added,
                    lines_deleted=deleted,
                )
            )
            diff_parts.append(_canonical_file_diff(path, before, after, before_text, after_text))
            if after is not None:
                scan_records.append({"path": path, "sha256": after.identity.sha256})

        changed_lines = total_added + total_deleted
        if deletion_count > MAX_DELETED_FILES or total_deleted > MAX_DELETED_LINES:
            raise PatchSetPolicyDenied("PATCHSET_MASS_DELETION_DENIED")

        canonical_diff = "".join(diff_parts)
        canonical_diff_sha256 = hashlib.sha256(canonical_diff.encode("utf-8")).hexdigest()
        scan_payload = {
            "finding_count": 0,
            "files_scanned": len(scan_records),
            "result": PatchPolicyResult.PASS.value,
            "scanned_content_sha256": canonical_workspace_json_digest(scan_records),
            "scanner_version": "NZ_PROVIDER_NEUTRAL_SECRET_SCAN_V1",
            "secret_values_retained": False,
        }
        secret_scan = PatchSecretScanSummary(
            **scan_payload,
            receipt_sha256=canonical_workspace_json_digest(scan_payload),
        )
        repository = RepositorySourceIdentity(
            tree_sha256=base.tree_sha256,
            source_commit=base_head,
            file_count=len(base.records),
            total_bytes=base.total_bytes,
        )
        values: dict[str, object] = {
            **context.model_dump(),
            "repository": repository,
            "base_head": base_head,
            "final_tree_sha256": final.tree_sha256,
            "canonical_diff": canonical_diff,
            "canonical_diff_sha256": canonical_diff_sha256,
            "files": tuple(changes),
            "totals": PatchTotals(
                files_changed=len(changes),
                lines_added=total_added,
                lines_deleted=total_deleted,
                changed_lines=changed_lines,
                deletion_count=deletion_count,
            ),
            "secret_scan": secret_scan,
        }
        digest = canonical_workspace_json_digest(
            PatchSet.model_construct(**values, patchset_sha256=_ZERO_DIGEST).content_payload()
        )
        return PatchSet(**values, patchset_sha256=digest)

    def recheck(
        self,
        *,
        base_root: Path,
        final_root: Path,
        patchset: PatchSet,
        checked_at: datetime,
    ) -> PatchSetRecheckReceipt:
        """Re-derive the complete decision; any later edit fails closed."""

        if not isinstance(patchset, PatchSet):
            raise PatchSetPolicyDenied("PATCHSET_RECHECK_INPUT_INVALID")
        context = PatchSetContext(
            patchset_id=patchset.patchset_id,
            task_id=patchset.task_id,
            operation_correlation_id=patchset.operation_correlation_id,
            run_id=patchset.run_id,
            trace_id=patchset.trace_id,
            worker_run_id=patchset.worker_run_id,
            workspace_id=patchset.workspace_id,
            observed_at=patchset.observed_at,
        )
        try:
            current = self.evaluate(
                base_root=base_root,
                final_root=final_root,
                base_head=patchset.base_head,
                context=context,
            )
        except PatchSetPolicyDenied as error:
            raise PatchSetPolicyDenied(
                "PATCHSET_TOCTOU_DRIFT_DETECTED",
                failure_kind=FailureKind.VALIDATION_FAILURE,
            ) from error
        if current != patchset:
            raise PatchSetPolicyDenied(
                "PATCHSET_TOCTOU_DRIFT_DETECTED",
                failure_kind=FailureKind.VALIDATION_FAILURE,
            )
        values = {
            "patchset_id": patchset.patchset_id,
            "patchset_sha256": patchset.patchset_sha256,
            "base_tree_sha256": patchset.repository.tree_sha256,
            "final_tree_sha256": patchset.final_tree_sha256,
            "checked_at": checked_at,
        }
        provisional = PatchSetRecheckReceipt.model_construct(
            **values,
            result=PatchPolicyResult.PASS,
            drift_detected=False,
            receipt_sha256=_ZERO_DIGEST,
        )
        return PatchSetRecheckReceipt(
            **values,
            receipt_sha256=canonical_workspace_json_digest(
                provisional.model_dump(mode="json", exclude={"receipt_sha256"})
            ),
        )

    def bound_after_contents(
        self,
        *,
        final_root: Path,
        patchset: PatchSet,
    ) -> tuple[tuple[str, bytes], ...]:
        """Return exact verified after-bytes for an internal isolated-sandbox bridge."""

        if not isinstance(patchset, PatchSet):
            raise PatchSetPolicyDenied("PATCHSET_CONTENT_EXPORT_INPUT_INVALID")
        snapshot = _snapshot_tree(final_root)
        if snapshot.tree_sha256 != patchset.final_tree_sha256:
            raise PatchSetPolicyDenied(
                "PATCHSET_TOCTOU_DRIFT_DETECTED",
                failure_kind=FailureKind.VALIDATION_FAILURE,
            )
        exported: list[tuple[str, bytes]] = []
        for change in patchset.files:
            if change.operation is PatchOperation.DELETE:
                raise PatchSetPolicyDenied("PATCHSET_SANDBOX_DELETE_UNSUPPORTED")
            record = snapshot.records.get(change.path)
            if record is None or record.identity != change.after:
                raise PatchSetPolicyDenied(
                    "PATCHSET_TOCTOU_DRIFT_DETECTED",
                    failure_kind=FailureKind.VALIDATION_FAILURE,
                )
            exported.append((change.path, record.content))
        return tuple(exported)


def _identity(record: _FileRecord | None) -> FileContentIdentity | None:
    return None if record is None else record.identity


def _snapshot_tree(root: Path) -> _TreeSnapshot:
    if not isinstance(root, Path) or not root.is_absolute():
        raise PatchSetPolicyDenied("PATCHSET_WORKSPACE_ROOT_INVALID")
    try:
        before_root = root.lstat()
        resolved = root.resolve(strict=True)
    except OSError as error:
        raise PatchSetPolicyDenied("PATCHSET_WORKSPACE_UNAVAILABLE") from error
    if (
        resolved != root
        or stat.S_ISLNK(before_root.st_mode)
        or not stat.S_ISDIR(before_root.st_mode)
    ):
        raise PatchSetPolicyDenied("PATCHSET_WORKSPACE_ROOT_INVALID")
    if before_root.st_uid != os.getuid():
        raise PatchSetPolicyDenied("PATCHSET_WORKSPACE_OWNER_INVALID")

    records: dict[str, _FileRecord] = {}
    folded_paths: dict[str, str] = {}
    total_bytes = 0
    try:
        candidates = sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix())
    except OSError as error:
        raise PatchSetPolicyDenied("PATCHSET_WORKSPACE_ENUMERATION_FAILED") from error
    for candidate in candidates:
        relative = normalize_patch_relative_path(candidate.relative_to(root).as_posix())
        folded = unicodedata.normalize("NFC", relative).casefold()
        prior = folded_paths.setdefault(folded, relative)
        if prior != relative:
            raise PatchSetPolicyDenied("PATCHSET_PATH_IDENTITY_AMBIGUOUS")
        try:
            metadata = candidate.lstat()
        except OSError as error:
            raise PatchSetPolicyDenied("PATCHSET_WORKSPACE_ENTRY_UNAVAILABLE") from error
        if stat.S_ISLNK(metadata.st_mode):
            raise PatchSetPolicyDenied("PATCHSET_SYMLINK_DENIED")
        if stat.S_ISDIR(metadata.st_mode):
            continue
        if not stat.S_ISREG(metadata.st_mode):
            raise PatchSetPolicyDenied("PATCHSET_SPECIAL_FILE_DENIED")
        if metadata.st_nlink != 1:
            raise PatchSetPolicyDenied("PATCHSET_HARDLINK_DENIED")
        content = _secure_read(root, relative, metadata)
        total_bytes += len(content)
        if len(records) >= MAX_TREE_FILES or total_bytes > MAX_TREE_BYTES:
            raise PatchSetPolicyDenied("PATCHSET_TREE_SIZE_LIMIT_EXCEEDED")
        records[relative] = _FileRecord(
            path=relative,
            content=content,
            identity=FileContentIdentity(
                sha256=hashlib.sha256(content).hexdigest(),
                size=len(content),
                mode=stat.S_IMODE(metadata.st_mode),
            ),
        )
    try:
        existing_digest = digest_workspace_tree(root)
        after_root = root.lstat()
    except (OSError, ValueError) as error:
        raise PatchSetPolicyDenied("PATCHSET_TREE_DIGEST_FAILED") from error
    expected_digest = canonical_workspace_json_digest(
        [[path, record.identity.sha256, record.identity.mode] for path, record in records.items()]
    )
    if existing_digest != expected_digest:
        raise PatchSetPolicyDenied("PATCHSET_TREE_IDENTITY_MISMATCH")
    if (before_root.st_dev, before_root.st_ino) != (after_root.st_dev, after_root.st_ino):
        raise PatchSetPolicyDenied("PATCHSET_WORKSPACE_ROOT_DRIFT")
    return _TreeSnapshot(existing_digest, records, total_bytes)


def _secure_read(root: Path, relative: str, expected: os.stat_result) -> bytes:
    file_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    directory_flags = file_flags | getattr(os, "O_DIRECTORY", 0)
    descriptors: list[int] = []
    expected_identity = (
        expected.st_dev,
        expected.st_ino,
        expected.st_size,
        expected.st_mtime_ns,
        expected.st_ctime_ns,
    )
    try:
        current = os.open(root, directory_flags)
        descriptors.append(current)
        for part in PurePosixPath(relative).parts[:-1]:
            current = os.open(part, directory_flags, dir_fd=current)
            descriptors.append(current)
        descriptor = os.open(PurePosixPath(relative).parts[-1], file_flags, dir_fd=current)
        descriptors.append(descriptor)
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
                before.st_ctime_ns,
            )
            != expected_identity
            or before.st_size > MAX_TREE_BYTES
        ):
            raise OSError("file identity changed")
        content = bytearray()
        while len(content) < before.st_size:
            chunk = os.read(descriptor, min(64 * 1024, before.st_size - len(content)))
            if not chunk:
                raise OSError("short read")
            content.extend(chunk)
        if os.read(descriptor, 1):
            raise OSError("file grew")
        after = os.fstat(descriptor)
        if (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ) != expected_identity:
            raise OSError("file changed during read")
        return bytes(content)
    except OSError as error:
        raise PatchSetPolicyDenied("PATCHSET_SECURE_READ_FAILED") from error
    finally:
        for descriptor in reversed(descriptors):
            with suppress(OSError):
                os.close(descriptor)


def _reject_protected_path(path: str) -> None:
    parts = PurePosixPath(path).parts
    folded = tuple(part.casefold() for part in parts)
    name = folded[-1]
    if folded[0] == ".git" or ".git" in folded:
        raise PatchSetPolicyDenied("PATCHSET_GIT_AUTHORITY_PATH_DENIED")
    if any(part in _GENERATED_NAMES or part.endswith((".pyc", ".pyo")) for part in folded):
        raise PatchSetPolicyDenied("PATCHSET_GENERATED_ARTIFACT_DENIED")
    if any(
        part in _SECRET_PARTS
        or part.startswith(".env")
        or "credential" in part
        or "token" in part
        or part.endswith((".key", ".pem", ".p12", ".pfx"))
        for part in folded
    ):
        raise PatchSetPolicyDenied("PATCHSET_SECRET_PATH_DENIED")
    if len(parts) == 1 and (name in _PROTECTED_ROOT_NAMES or name in _PROTECTED_CONFIG_NAMES):
        raise PatchSetPolicyDenied("PATCHSET_POLICY_CONFIGURATION_DENIED")
    if folded[0] in {".github", ".circleci"}:
        raise PatchSetPolicyDenied("PATCHSET_REMOTE_AUTHORITY_CONFIG_DENIED")
    if path.startswith("src/aioa_cloudops_agent/patchset/") or path in {
        "src/aioa_cloudops_agent/nz/redaction.py",
        "scripts/run_p0_gate.py",
        "scripts/run_p1_gate.py",
    }:
        raise PatchSetPolicyDenied("PATCHSET_POLICY_OWNED_FILE_DENIED")
    if path.startswith(("docs/evidence/release/", "docs/evidence/submission/")):
        raise PatchSetPolicyDenied("PATCHSET_FROZEN_RELEASE_EVIDENCE_DENIED")
    if path.startswith("docs/evidence/w7a/") and any(
        marker in name for marker in ("phase1", "phase2", "phase3", "phase4")
    ):
        raise PatchSetPolicyDenied("PATCHSET_FROZEN_W7A_EVIDENCE_DENIED")
    if path.startswith("docs/audits/") and any(
        PurePosixPath(path).name.startswith(prefix) for prefix in _PROTECTED_AUDIT_PREFIXES
    ):
        raise PatchSetPolicyDenied("PATCHSET_FROZEN_AUDIT_DENIED")


def _decode_text(record: _FileRecord | None) -> str:
    if record is None:
        return ""
    if b"\0" in record.content:
        raise PatchSetPolicyDenied("PATCHSET_BINARY_CHANGE_DENIED")
    try:
        return record.content.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise PatchSetPolicyDenied("PATCHSET_UNSUPPORTED_ENCODING_DENIED") from error


def _line_counts(before: str, after: str) -> tuple[int, int]:
    added = 0
    deleted = 0
    matcher = difflib.SequenceMatcher(a=before.splitlines(), b=after.splitlines(), autojunk=False)
    for tag, before_start, before_end, after_start, after_end in matcher.get_opcodes():
        if tag in {"replace", "delete"}:
            deleted += before_end - before_start
        if tag in {"replace", "insert"}:
            added += after_end - after_start
    return added, deleted


def _canonical_file_diff(
    path: str,
    before: _FileRecord | None,
    after: _FileRecord | None,
    before_text: str,
    after_text: str,
) -> str:
    before_sha = _ZERO_DIGEST if before is None else before.identity.sha256
    after_sha = _ZERO_DIGEST if after is None else after.identity.sha256
    before_mode = 0 if before is None else before.identity.mode
    after_mode = 0 if after is None else after.identity.mode
    from_name = "/dev/null" if before is None else f"a/{path}"
    to_name = "/dev/null" if after is None else f"b/{path}"
    rendered = [
        f"diff --aioa a/{path} b/{path}\n",
        f"index {before_sha}..{after_sha} {before_mode:04o}->{after_mode:04o}\n",
        f"eof-newline {int(before_text.endswith(chr(10)))}->{int(after_text.endswith(chr(10)))}\n",
    ]
    rendered.extend(
        f"{line}\n"
        for line in difflib.unified_diff(
            before_text.splitlines(),
            after_text.splitlines(),
            fromfile=from_name,
            tofile=to_name,
            lineterm="",
        )
    )
    return "".join(rendered)
