import hashlib
import os
import stat
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from pydantic import ValidationError

from aioa_cloudops_agent.nz import FailureKind, ResultStatus
from aioa_cloudops_agent.workspace import (
    FIXTURE_VERSION,
    WORKSPACE_REMEDIATION_V1,
    FixtureIntegrityError,
    WorkspaceCapabilityProfile,
    WorkspaceEvidenceService,
    WorkspaceJail,
    WorkspaceOperation,
    WorkspacePolicyOutcome,
    WorkspaceRef,
    inspect_fixture_tree,
    materialize_sealed_fixture,
    normalize_workspace_relative_path,
)

ROOT = Path(__file__).parents[2]
FIXTURE_ROOT = ROOT / "demo" / "workspace_render_incident_v1"
RUN_ID = UUID("01890f6c-3311-7abc-8f4a-6e4f7f0b9b3a")
OTHER_RUN_ID = UUID("01890f6c-3311-7abc-8f4a-6e4f7f0b9b4a")
TRACE_ID = UUID("01890f6c-3311-7abc-8f4a-6e4f7f0b9b3b")
NOW = datetime(2026, 9, 2, 20, 0, tzinfo=UTC)


def _service(tmp_path: Path, *, run_id: UUID = RUN_ID):
    sealed = materialize_sealed_fixture(
        run_id=run_id,
        fixture_source=FIXTURE_ROOT,
        workspace_parent=tmp_path,
        profile=WORKSPACE_REMEDIATION_V1,
    )
    service = WorkspaceEvidenceService(
        WorkspaceJail(sealed),
        trace_id=TRACE_ID,
        clock=lambda: NOW,
        event_id_factory=_event_id_factory(),
    )
    return sealed, service


def _event_id_factory():
    counter = 0

    def next_id() -> UUID:
        nonlocal counter
        counter += 1
        suffix = f"{counter:012x}"
        return UUID(f"01890f6c-3311-7abc-8f4a-{suffix}")

    return next_id


def _file_snapshot(root: Path) -> tuple[tuple[object, ...], ...]:
    records: list[tuple[object, ...]] = []
    for path in sorted(root.rglob("*")):
        metadata = path.lstat()
        relative = path.relative_to(root).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        records.append(
            (
                relative,
                stat.S_IFMT(metadata.st_mode),
                stat.S_IMODE(metadata.st_mode),
                metadata.st_size,
                metadata.st_mtime_ns,
                digest,
            )
        )
    return tuple(records)


def test_valid_sealed_workspaces_receive_distinct_server_identities(tmp_path: Path) -> None:
    first, _ = _service(tmp_path, run_id=RUN_ID)
    second, _ = _service(tmp_path, run_id=RUN_ID)

    assert first.ref.workspace_id != second.ref.workspace_id
    assert first.root != second.root
    assert first.root.parent == second.root.parent == tmp_path
    assert first.ref.run_id == second.ref.run_id == RUN_ID
    assert first.ref.fixture_version == second.ref.fixture_version == FIXTURE_VERSION


def test_root_digest_is_deterministic_for_same_fixture_version(tmp_path: Path) -> None:
    source_artifacts, source_digest = inspect_fixture_tree(
        FIXTURE_ROOT,
        WORKSPACE_REMEDIATION_V1,
    )
    first, _ = _service(tmp_path)
    second, _ = _service(tmp_path)

    assert len(source_artifacts) == 5
    assert first.ref.root_digest == second.ref.root_digest == source_digest
    assert first.ref.created_from_digest == source_digest


@pytest.mark.parametrize(
    "path",
    (
        "../../etc/passwd",
        "scripts/../../render.yaml",
        "scripts/../render_start.sh",
        "scripts\\render_start.sh",
        "render.yaml/..",
    ),
)
def test_parent_and_non_posix_path_escape_is_rejected(tmp_path: Path, path: str) -> None:
    sealed, service = _service(tmp_path)

    result = service.read_allowed_path(sealed.ref, path)

    assert result.status is ResultStatus.FAILURE
    assert result.failure is not None
    assert result.failure.kind is FailureKind.POLICY_DENIAL
    assert result.failure.code == "WORKSPACE_PATH_INVALID"


@pytest.mark.parametrize("path", ("/etc/passwd", "/proc/self/environ", "C:/secrets.txt"))
def test_absolute_paths_are_rejected(tmp_path: Path, path: str) -> None:
    sealed, service = _service(tmp_path)

    result = service.hash_allowed_path(sealed.ref, path)

    assert result.status is ResultStatus.FAILURE
    assert result.failure is not None
    assert result.failure.code == "WORKSPACE_PATH_INVALID"


@pytest.mark.parametrize(
    "path",
    ("render\x00.yaml", "render\n.yaml", "render\r.yaml", "render\t.yaml", "render\u202e.yaml"),
)
def test_nul_control_and_format_characters_are_rejected(tmp_path: Path, path: str) -> None:
    sealed, service = _service(tmp_path)

    result = service.read_allowed_path(sealed.ref, path)

    assert result.status is ResultStatus.FAILURE
    assert result.failure is not None
    assert result.failure.code == "WORKSPACE_PATH_INVALID"


def test_symlink_inside_workspace_is_rejected_without_reading_target(tmp_path: Path) -> None:
    sealed, service = _service(tmp_path)
    outside = tmp_path / "private-host-marker.txt"
    outside.write_text("must-not-be-read", encoding="utf-8")
    target = sealed.root / "deployment.log"
    target.chmod(0o600)
    target.unlink()
    target.symlink_to(outside)

    result = service.read_allowed_path(sealed.ref, "deployment.log")

    assert result.status is ResultStatus.FAILURE
    assert result.failure is not None
    assert result.failure.code == "WORKSPACE_TAMPER_DETECTED"
    assert "private-host-marker" not in result.failure.message
    assert str(tmp_path) not in result.failure.message


@pytest.mark.parametrize("special_mode", (stat.S_IFIFO, stat.S_IFSOCK, stat.S_IFCHR))
def test_fifo_socket_and_device_artifact_modes_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
    special_mode: int,
) -> None:
    target = FIXTURE_ROOT / "deployment.log"
    original_lstat = Path.lstat

    def controlled_lstat(path: Path):
        if path == target:
            return SimpleNamespace(st_mode=special_mode)
        return original_lstat(path)

    monkeypatch.setattr(Path, "lstat", controlled_lstat)

    with pytest.raises(FixtureIntegrityError, match="special file"):
        inspect_fixture_tree(FIXTURE_ROOT, WORKSPACE_REMEDIATION_V1)


def test_hardlink_to_outside_inode_is_detected(tmp_path: Path) -> None:
    sealed, service = _service(tmp_path)
    outside = tmp_path / "outside-hardlink-source.txt"
    outside.write_text("external inode", encoding="utf-8")
    target = sealed.root / "deployment.log"
    target.chmod(0o600)
    target.unlink()
    os.link(outside, target)

    result = service.read_allowed_path(sealed.ref, "deployment.log")

    assert result.status is ResultStatus.FAILURE
    assert result.failure is not None
    assert result.failure.code == "WORKSPACE_TAMPER_DETECTED"


def test_cross_workspace_reference_is_rejected(tmp_path: Path) -> None:
    _, first_service = _service(tmp_path, run_id=RUN_ID)
    second, _ = _service(tmp_path, run_id=OTHER_RUN_ID)

    result = first_service.list_allowed_artifacts(second.ref)

    assert result.status is ResultStatus.FAILURE
    assert result.failure is not None
    assert result.failure.kind is FailureKind.POLICY_DENIAL
    assert result.failure.code == "WORKSPACE_CROSS_IDENTITY_DENIED"


def test_unknown_artifact_path_is_rejected(tmp_path: Path) -> None:
    sealed, service = _service(tmp_path)

    result = service.read_allowed_path(sealed.ref, "unknown.txt")

    assert result.status is ResultStatus.FAILURE
    assert result.failure is not None
    assert result.failure.code == "WORKSPACE_ARTIFACT_NOT_ALLOWED"


@pytest.mark.parametrize(
    "path",
    (".env", ".git/config", ".ssh/id_rsa", ".aws/credentials", "secrets.txt"),
)
def test_hidden_and_secret_sensitive_paths_fail_closed(tmp_path: Path, path: str) -> None:
    sealed, service = _service(tmp_path)

    result = service.read_allowed_path(sealed.ref, path)

    assert result.status is ResultStatus.FAILURE
    assert result.failure is not None
    assert result.failure.code == "WORKSPACE_PATH_INVALID"


def test_oversized_text_is_explicitly_truncated_with_full_digest(tmp_path: Path) -> None:
    source = tmp_path / "source"
    workspace_parent = tmp_path / "workspaces"
    source.mkdir()
    workspace_parent.mkdir()
    content = "0123456789abcdefghijklmnop"
    (source / "large.txt").write_text(content, encoding="utf-8")
    profile = WorkspaceCapabilityProfile(
        allowed_artifacts=("large.txt",),
        max_file_bytes=128,
        max_read_bytes=8,
        max_files=1,
    )
    sealed = materialize_sealed_fixture(
        run_id=RUN_ID,
        fixture_source=source,
        workspace_parent=workspace_parent,
        profile=profile,
    )
    service = WorkspaceEvidenceService(
        WorkspaceJail(sealed),
        trace_id=TRACE_ID,
        clock=lambda: NOW,
        event_id_factory=_event_id_factory(),
    )

    result = service.read_allowed_path(sealed.ref, "large.txt")

    assert result.status is ResultStatus.SUCCESS
    assert result.value is not None
    assert result.value.text == content[:8]
    assert result.value.receipt.returned_bytes == 8
    assert result.value.receipt.observed_size == len(content)
    assert result.value.receipt.truncated is True
    assert result.value.receipt.sha256 == hashlib.sha256(content.encode()).hexdigest()


def test_list_result_is_capped_sorted_and_deterministic(tmp_path: Path) -> None:
    sealed, service = _service(tmp_path)

    first = service.list_allowed_artifacts(sealed.ref)
    second = service.list_allowed_artifacts(sealed.ref)

    assert first.value is not None and second.value is not None
    first_paths = tuple(artifact.relative_path for artifact in first.value.artifacts)
    second_paths = tuple(artifact.relative_path for artifact in second.value.artifacts)
    assert len(first_paths) == WORKSPACE_REMEDIATION_V1.max_files == 5
    assert first_paths == second_paths == tuple(sorted(first_paths))
    assert first.value.receipt.sha256 == second.value.receipt.sha256 == sealed.ref.root_digest


def test_read_receipt_digest_matches_independent_server_read(tmp_path: Path) -> None:
    sealed, service = _service(tmp_path)

    result = service.read_allowed_path(sealed.ref, "render.yaml")
    independent = hashlib.sha256((sealed.root / "render.yaml").read_bytes()).hexdigest()

    assert result.value is not None
    assert result.value.receipt.sha256 == independent
    assert result.value.receipt.artifact.sha256 == independent
    assert result.value.receipt.policy.outcome is WorkspacePolicyOutcome.ALLOW


def test_hash_capability_performs_separate_full_read_receipt(tmp_path: Path) -> None:
    sealed, service = _service(tmp_path)

    result = service.hash_allowed_path(sealed.ref, "scripts/render_start.sh")

    assert result.value is not None
    assert result.value.receipt.operation is WorkspaceOperation.HASH
    assert result.value.receipt.returned_bytes == 0
    assert result.value.receipt.truncated is False
    assert result.value.sha256 == hashlib.sha256(
        (sealed.root / "scripts/render_start.sh").read_bytes()
    ).hexdigest()


def test_tampered_fixture_root_digest_is_detected(tmp_path: Path) -> None:
    sealed, service = _service(tmp_path)
    target = sealed.root / "render.yaml"
    target.chmod(0o600)
    target.write_text(target.read_text(encoding="utf-8") + "# tampered\n", encoding="utf-8")

    result = service.list_allowed_artifacts(sealed.ref)

    assert result.status is ResultStatus.FAILURE
    assert result.failure is not None
    assert result.failure.kind is FailureKind.VALIDATION_FAILURE
    assert result.failure.code == "WORKSPACE_ROOT_DIGEST_MISMATCH"


def test_unapproved_extra_file_is_detected_as_tamper(tmp_path: Path) -> None:
    sealed, service = _service(tmp_path)
    (sealed.root / "extra.txt").write_text("unexpected", encoding="utf-8")

    result = service.list_allowed_artifacts(sealed.ref)

    assert result.status is ResultStatus.FAILURE
    assert result.failure is not None
    assert result.failure.code == "WORKSPACE_TAMPER_DETECTED"


def test_read_operations_create_or_modify_no_workspace_file(tmp_path: Path) -> None:
    sealed, service = _service(tmp_path)
    before = _file_snapshot(sealed.root)

    assert service.inspect_workspace_incident(sealed.ref).status is ResultStatus.SUCCESS
    assert service.list_allowed_artifacts(sealed.ref).status is ResultStatus.SUCCESS
    assert service.read_allowed_path(sealed.ref, "deployment.log").status is ResultStatus.SUCCESS
    assert service.hash_allowed_path(sealed.ref, "render.yaml").status is ResultStatus.SUCCESS

    assert _file_snapshot(sealed.root) == before


def test_profile_registers_no_mutation_or_network_capability() -> None:
    assert WORKSPACE_REMEDIATION_V1.mutation_allowed is False
    assert WORKSPACE_REMEDIATION_V1.network_allowed is False
    assert WORKSPACE_REMEDIATION_V1.allowed_operations == (
        WorkspaceOperation.INSPECT,
        WorkspaceOperation.LIST,
        WorkspaceOperation.READ,
        WorkspaceOperation.HASH,
    )


def test_profile_cannot_expand_operations_or_exceed_server_bounds() -> None:
    with pytest.raises(ValidationError, match="fixed and cannot be expanded"):
        WorkspaceCapabilityProfile(
            allowed_artifacts=("only.txt",),
            max_file_bytes=128,
            max_read_bytes=64,
            max_files=1,
            allowed_operations=(WorkspaceOperation.READ,),
        )
    with pytest.raises(ValidationError, match="exceeds max_files"):
        WorkspaceCapabilityProfile(
            allowed_artifacts=("one.txt", "two.txt"),
            max_file_bytes=128,
            max_read_bytes=64,
            max_files=1,
        )


def test_workspace_ref_rejects_unbound_origin_digest() -> None:
    with pytest.raises(ValidationError, match="must match its fixture origin"):
        WorkspaceRef(
            run_id=RUN_ID,
            workspace_id=OTHER_RUN_ID,
            fixture_version=FIXTURE_VERSION,
            root_digest="0" * 64,
            created_from_digest="1" * 64,
        )


def test_fixture_contains_no_canonical_secret_scan_finding() -> None:
    from scripts.phase3.scan_secrets import scan_files

    paths = tuple(
        path.relative_to(ROOT).as_posix()
        for path in FIXTURE_ROOT.rglob("*")
        if path.is_file()
    )
    result = scan_files(ROOT, paths)

    assert result["status"] == "PASS"
    assert result["findings_count"] == 0
    assert result["secret_values_emitted"] is False


def test_concurrent_reads_cannot_cross_workspace_identities(tmp_path: Path) -> None:
    first, first_service = _service(tmp_path, run_id=RUN_ID)
    second, second_service = _service(tmp_path, run_id=OTHER_RUN_ID)

    def read_own(service: WorkspaceEvidenceService, workspace_ref: WorkspaceRef) -> str:
        result = service.read_allowed_path(workspace_ref, "deployment.log")
        assert result.value is not None
        return str(result.value.receipt.workspace_id)

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [
            executor.submit(read_own, first_service, first.ref),
            executor.submit(read_own, second_service, second.ref),
            executor.submit(read_own, first_service, first.ref),
            executor.submit(read_own, second_service, second.ref),
        ]
    identities = [future.result() for future in futures]

    assert identities == [
        str(first.ref.workspace_id),
        str(second.ref.workspace_id),
        str(first.ref.workspace_id),
        str(second.ref.workspace_id),
    ]
    denied = first_service.read_allowed_path(second.ref, "deployment.log")
    assert denied.failure is not None
    assert denied.failure.code == "WORKSPACE_CROSS_IDENTITY_DENIED"


def test_failure_mapping_redacts_private_host_detail(tmp_path: Path) -> None:
    sealed, service = _service(tmp_path)
    target = sealed.root / "render.yaml"
    target.chmod(0o600)
    target.unlink()

    result = service.read_allowed_path(sealed.ref, "render.yaml")

    assert result.failure is not None
    assert result.failure.retryable is False
    assert str(tmp_path) not in result.failure.message
    assert "No such file" not in result.failure.message
    assert result.failure.message == "Sealed workspace integrity validation failed"


def test_fixture_provenance_and_identity_appear_in_evidence_timeline(tmp_path: Path) -> None:
    sealed, service = _service(tmp_path)

    service.inspect_workspace_incident(sealed.ref)
    service.read_allowed_path(sealed.ref, "deployment.log")
    service.hash_allowed_path(sealed.ref, "render.yaml")

    timeline = service.evidence_timeline
    assert tuple(event.operation for event in timeline) == (
        WorkspaceOperation.INSPECT,
        WorkspaceOperation.READ,
        WorkspaceOperation.HASH,
    )
    assert all(event.run_id == RUN_ID for event in timeline)
    assert all(event.trace_id == TRACE_ID for event in timeline)
    assert all(event.workspace_id == sealed.ref.workspace_id for event in timeline)
    assert all(event.fixture_version == FIXTURE_VERSION for event in timeline)
    assert all(
        event.provenance == "sealed_fixture:workspace_render_incident_v1"
        for event in timeline
    )
    assert all(event.observed_at == NOW for event in timeline)


def test_normalizer_returns_only_exact_canonical_allowlist_shape() -> None:
    assert normalize_workspace_relative_path("scripts/render_start.sh") == (
        "scripts/render_start.sh"
    )
    for invalid in (" ./render.yaml", "render.yaml ", "a//b.txt", "./render.yaml"):
        with pytest.raises(ValueError):
            normalize_workspace_relative_path(invalid)
