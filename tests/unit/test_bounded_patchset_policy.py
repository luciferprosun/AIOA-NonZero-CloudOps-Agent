from __future__ import annotations

import hashlib
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from aioa_cloudops_agent.nz import FailureKind
from aioa_cloudops_agent.patchset import (
    MAX_CHANGED_LINES,
    MAX_FILES_CHANGED,
    BoundedPatchSetPolicy,
    PatchOperation,
    PatchSetContext,
    PatchSetPolicyDenied,
    normalize_patch_relative_path,
)

BASE_HEAD = "1" * 40
OBSERVED_AT = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
IDS = tuple(UUID(f"01890f6c-3311-7abc-8f4a-6e4f7f0b9c{value:02x}") for value in range(7))


def _context() -> PatchSetContext:
    return PatchSetContext(
        patchset_id=IDS[0],
        task_id=IDS[1],
        operation_correlation_id=IDS[2],
        run_id=IDS[3],
        trace_id=IDS[4],
        worker_run_id=IDS[5],
        workspace_id=IDS[6],
        observed_at=OBSERVED_AT,
    )


def _workspace_pair(tmp_path: Path, files: dict[str, str] | None = None) -> tuple[Path, Path]:
    base = tmp_path / "base"
    final = tmp_path / "final"
    payload = files or {
        "src/example.py": "def answer() -> int:\n    return 1\n",
        "tests/test_example.py": "def test_answer() -> None:\n    assert True\n",
    }
    for relative, content in payload.items():
        target = base / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    shutil.copytree(base, final)
    return base.resolve(), final.resolve()


def _evaluate(base: Path, final: Path):
    return BoundedPatchSetPolicy().evaluate(
        base_root=base,
        final_root=final,
        base_head=BASE_HEAD,
        context=_context(),
    )


def _assert_denied(base: Path, final: Path, code: str) -> PatchSetPolicyDenied:
    with pytest.raises(PatchSetPolicyDenied) as captured:
        _evaluate(base, final)
    assert captured.value.code == code
    assert captured.value.failure_kind is FailureKind.POLICY_DENIAL
    return captured.value


def test_p0_source_and_test_change_under_budget_is_canonical_and_passes(tmp_path: Path) -> None:
    base, final = _workspace_pair(tmp_path)
    (final / "src/example.py").write_text(
        "def answer() -> int:\n    return 42\n",
        encoding="utf-8",
    )
    (final / "tests/test_example.py").write_text(
        "from src.example import answer\n\ndef test_answer() -> None:\n    assert answer() == 42\n",
        encoding="utf-8",
    )

    patchset = _evaluate(base, final)

    assert patchset.policy_result == "PASS"
    assert patchset.totals.files_changed == 2
    assert patchset.totals.changed_lines <= MAX_CHANGED_LINES
    assert tuple(change.path for change in patchset.files) == (
        "src/example.py",
        "tests/test_example.py",
    )
    assert all(change.operation is PatchOperation.MODIFY for change in patchset.files)
    assert patchset.repository.source_commit == BASE_HEAD
    assert (
        patchset.canonical_diff_sha256
        == hashlib.sha256(patchset.canonical_diff.encode("utf-8")).hexdigest()
    )
    rendered = patchset.model_dump_json()
    assert str(base) not in rendered
    assert str(final) not in rendered
    assert patchset.github_authority is False
    assert patchset.aws_authority is False


def test_p0_fourth_changed_file_is_denied_from_actual_state(tmp_path: Path) -> None:
    base, final = _workspace_pair(tmp_path, {f"src/f{number}.py": "x = 1\n" for number in range(4)})
    for number in range(4):
        (final / f"src/f{number}.py").write_text("x = 2\n", encoding="utf-8")

    _assert_denied(base, final, "PATCHSET_FILE_LIMIT_EXCEEDED")
    assert MAX_FILES_CHANGED == 3


def test_p0_more_than_300_changed_lines_is_denied(tmp_path: Path) -> None:
    base, final = _workspace_pair(tmp_path, {"src/large.py": ""})
    (final / "src/large.py").write_text(
        "".join(f"value_{number} = {number}\n" for number in range(301)),
        encoding="utf-8",
    )

    _assert_denied(base, final, "PATCHSET_LINE_LIMIT_EXCEEDED")


@pytest.mark.parametrize(
    ("mutator", "code"),
    [
        (
            lambda final: (final / "src/example.py").write_bytes(b"safe\0binary\n"),
            "PATCHSET_BINARY_CHANGE_DENIED",
        ),
        (
            lambda final: (final / ".gitmodules").write_text(
                '[submodule "outside"]\npath=outside\n',
                encoding="utf-8",
            ),
            "PATCHSET_POLICY_CONFIGURATION_DENIED",
        ),
        (
            lambda final: (final / "src/example.py").chmod(0o755),
            "PATCHSET_MODE_CHANGE_DENIED",
        ),
    ],
)
def test_p0_binary_submodule_and_mode_surprise_are_denied(
    tmp_path: Path,
    mutator,
    code: str,
) -> None:
    base, final = _workspace_pair(tmp_path)
    mutator(final)
    _assert_denied(base, final, code)


def test_p0_path_traversal_is_denied() -> None:
    with pytest.raises(PatchSetPolicyDenied, match="PATCHSET_PATH_TRAVERSAL_DENIED"):
        normalize_patch_relative_path("../outside.py")


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "special"])
def test_p0_link_and_special_file_entries_are_denied(tmp_path: Path, kind: str) -> None:
    base, final = _workspace_pair(tmp_path)
    target = final / "src/untrusted"
    if kind == "symlink":
        target.symlink_to("example.py")
        expected = "PATCHSET_SYMLINK_DENIED"
    elif kind == "hardlink":
        os.link(final / "src/example.py", target)
        expected = "PATCHSET_HARDLINK_DENIED"
    else:
        os.mkfifo(target)
        expected = "PATCHSET_SPECIAL_FILE_DENIED"
    _assert_denied(base, final, expected)


@pytest.mark.parametrize(
    ("path", "code"),
    [
        (".git/config", "PATCHSET_GIT_AUTHORITY_PATH_DENIED"),
        (
            "docs/audits/W7A_PHASE_4_SANDBOX_SETUP_INSTALLER_2026-09-04.md",
            "PATCHSET_FROZEN_AUDIT_DENIED",
        ),
        (
            "docs/evidence/release/build-complete.json",
            "PATCHSET_FROZEN_RELEASE_EVIDENCE_DENIED",
        ),
    ],
)
def test_p0_git_and_frozen_evidence_mutation_is_denied(
    tmp_path: Path,
    path: str,
    code: str,
) -> None:
    base, final = _workspace_pair(tmp_path, {path: "historical evidence\n"})
    (final / path).write_text("rewritten evidence\n", encoding="utf-8")
    _assert_denied(base, final, code)


def test_p0_secret_content_is_denied_without_echoing_value(tmp_path: Path) -> None:
    base, final = _workspace_pair(tmp_path)
    secret = "ghp_" + "A" * 40
    (final / "src/example.py").write_text(f"credential = '{secret}'\n", encoding="utf-8")

    denied = _assert_denied(base, final, "PATCHSET_SECRET_CONTENT_DENIED")

    assert secret not in str(denied)
    assert secret not in repr(denied)


def test_p0_workspace_edit_after_decision_invalidates_toctou_recheck(tmp_path: Path) -> None:
    base, final = _workspace_pair(tmp_path)
    (final / "src/example.py").write_text("value = 2\n", encoding="utf-8")
    policy = BoundedPatchSetPolicy()
    patchset = policy.evaluate(
        base_root=base,
        final_root=final,
        base_head=BASE_HEAD,
        context=_context(),
    )
    (final / "src/example.py").write_text("value = 3\n", encoding="utf-8")

    with pytest.raises(PatchSetPolicyDenied) as captured:
        policy.recheck(
            base_root=base,
            final_root=final,
            patchset=patchset,
            checked_at=OBSERVED_AT,
        )
    assert captured.value.code == "PATCHSET_TOCTOU_DRIFT_DETECTED"
    assert captured.value.failure_kind is FailureKind.VALIDATION_FAILURE


def test_p1_same_base_and_final_twice_produces_identical_patchset_and_hash(tmp_path: Path) -> None:
    base, final = _workspace_pair(tmp_path)
    (final / "src/example.py").write_text("value = 2\n", encoding="utf-8")

    first = _evaluate(base, final)
    second = _evaluate(base, final)

    assert first == second
    assert first.patchset_sha256 == second.patchset_sha256
    assert first.canonical_diff == second.canonical_diff


def test_p1_model_claim_of_fewer_files_is_ignored_actual_diff_wins(tmp_path: Path) -> None:
    base, final = _workspace_pair(tmp_path)
    (final / "src/example.py").write_text("value = 2\n", encoding="utf-8")
    (final / "tests/test_example.py").write_text("assert 2 == 2\n", encoding="utf-8")
    untrusted_model_claim = ("src/example.py",)

    patchset = _evaluate(base, final)

    assert tuple(change.path for change in patchset.files) != untrusted_model_claim
    assert tuple(change.path for change in patchset.files) == (
        "src/example.py",
        "tests/test_example.py",
    )


def test_recheck_of_unchanged_state_produces_content_bound_receipt(tmp_path: Path) -> None:
    base, final = _workspace_pair(tmp_path)
    (final / "src/example.py").write_text("value = 2\n", encoding="utf-8")
    policy = BoundedPatchSetPolicy()
    patchset = _evaluate(base, final)

    receipt = policy.recheck(
        base_root=base,
        final_root=final,
        patchset=patchset,
        checked_at=OBSERVED_AT,
    )

    assert receipt.patchset_sha256 == patchset.patchset_sha256
    assert receipt.final_tree_sha256 == patchset.final_tree_sha256
    assert receipt.drift_detected is False


def test_ambiguous_case_identity_and_generated_artifact_are_denied(tmp_path: Path) -> None:
    base, final = _workspace_pair(tmp_path)
    (final / "src/Example.py").write_text("value = 2\n", encoding="utf-8")
    _assert_denied(base, final, "PATCHSET_PATH_IDENTITY_AMBIGUOUS")

    base2, final2 = _workspace_pair(tmp_path / "other")
    generated = final2 / "src/__pycache__/example.pyc"
    generated.parent.mkdir(parents=True)
    generated.write_bytes(b"generated")
    _assert_denied(base2, final2, "PATCHSET_GENERATED_ARTIFACT_DENIED")


def test_mass_delete_is_denied(tmp_path: Path) -> None:
    base, final = _workspace_pair(
        tmp_path,
        {
            "src/one.py": "one = 1\n",
            "src/two.py": "two = 2\n",
        },
    )
    (final / "src/one.py").unlink()
    (final / "src/two.py").unlink()

    _assert_denied(base, final, "PATCHSET_MASS_DELETION_DENIED")
