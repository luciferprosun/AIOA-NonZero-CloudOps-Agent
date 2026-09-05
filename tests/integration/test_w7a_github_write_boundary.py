"""Local bare-remote proof of the complete Phase 8 mutation boundary."""

from __future__ import annotations

from datetime import timedelta

from tests.w7a_phase8_fixtures import (
    NOW,
    TARGET_BRANCH,
    build_phase8_fixture,
    git,
    uuid7,
)

from aioa_cloudops_agent.github.repository_service import GitRemoteWriteUnknown
from aioa_cloudops_agent.github.write_actuator import DeterministicGitHubWriteActuator
from aioa_cloudops_agent.github.write_contracts import (
    GitPushAcknowledgement,
    GitWriteDisposition,
)


class _ServiceProxy:
    def __init__(self, delegate) -> None:
        self.delegate = delegate
        self.push_calls = 0

    def __getattr__(self, name):
        return getattr(self.delegate, name)


class _OwnershipAssertingService(_ServiceProxy):
    def __init__(self, delegate, repository, operation_id) -> None:
        super().__init__(delegate)
        self.repository = repository
        self.operation_id = operation_id

    def push_feature_ref_once(self, **kwargs):
        self.push_calls += 1
        assert self.repository.get_ownership(self.operation_id) is not None
        return self.delegate.push_feature_ref_once(**kwargs)


class _LostAckAfterWriteService(_ServiceProxy):
    def push_feature_ref_once(self, **kwargs):
        self.push_calls += 1
        self.delegate.push_feature_ref_once(**kwargs)
        raise GitRemoteWriteUnknown("GIT_REMOTE_WRITE_ACK_UNKNOWN")


class _UnknownWithoutWriteService(_ServiceProxy):
    def push_feature_ref_once(self, **kwargs):
        del kwargs
        self.push_calls += 1
        raise GitRemoteWriteUnknown("GIT_REMOTE_WRITE_ACK_UNKNOWN")


def _actuator(fixture, service):
    return DeterministicGitHubWriteActuator(
        service,
        fixture.repository,
        fixture.verifier,
        clock=lambda: NOW + timedelta(minutes=5),
        effect_id_factory=lambda: uuid7(30),
    )


def test_exact_approved_patch_is_committed_pushed_and_independently_verified(tmp_path):
    fixture = build_phase8_fixture(tmp_path)
    service = _OwnershipAssertingService(
        fixture.service,
        fixture.repository,
        fixture.capsule.operation_id,
    )
    actuator = _actuator(fixture, service)

    result = actuator.execute(
        fixture.capsule,
        patchset=fixture.patchset,
        base_root=fixture.base_root.resolve(),
        final_root=fixture.final_root.resolve(),
    )

    assert result.disposition is GitWriteDisposition.VERIFIED
    assert result.receipt is not None
    assert result.receipt.push_acknowledgement is GitPushAcknowledgement.ACKNOWLEDGED
    assert result.receipt.product_runtime_writes == 1
    assert result.receipt.force_pushes == 0
    assert result.receipt.tag_writes == 0
    assert result.receipt.default_branch_writes == 0
    assert result.receipt.merges == 0
    assert service.push_calls == 1
    assert actuator.remote_write_attempts == 1
    assert fixture.repository.get_ownership(fixture.capsule.operation_id) is not None
    assert fixture.repository.get_receipt(fixture.capsule.operation_id) == result.receipt
    assert git("rev-parse", "refs/heads/main", cwd=fixture.bare) == fixture.default_head
    assert git("rev-parse", f"refs/heads/{TARGET_BRANCH}", cwd=fixture.bare) == (
        result.receipt.expected_commit.commit_sha
    )
    assert git(
        "show",
        f"refs/heads/{TARGET_BRANCH}:solver.py",
        cwd=fixture.bare,
    ) == "def add(a, b):\n    return a + b"


def test_lost_ack_is_closed_by_matching_independent_readback(tmp_path):
    fixture = build_phase8_fixture(tmp_path)
    service = _LostAckAfterWriteService(fixture.service)
    actuator = _actuator(fixture, service)

    result = actuator.execute(
        fixture.capsule,
        patchset=fixture.patchset,
        base_root=fixture.base_root.resolve(),
        final_root=fixture.final_root.resolve(),
    )

    assert result.disposition is GitWriteDisposition.VERIFIED
    assert result.receipt is not None
    assert result.receipt.push_acknowledgement is GitPushAcknowledgement.UNKNOWN
    assert service.push_calls == 1
    assert actuator.remote_write_attempts == 1


def test_exact_inputs_produce_the_same_commit_identity(tmp_path):
    first_fixture = build_phase8_fixture(tmp_path / "first")
    second_fixture = build_phase8_fixture(tmp_path / "second")

    first = first_fixture.actuator.execute(
        first_fixture.capsule,
        patchset=first_fixture.patchset,
        base_root=first_fixture.base_root.resolve(),
        final_root=first_fixture.final_root.resolve(),
    )
    second = second_fixture.actuator.execute(
        second_fixture.capsule,
        patchset=second_fixture.patchset,
        base_root=second_fixture.base_root.resolve(),
        final_root=second_fixture.final_root.resolve(),
    )

    assert first.disposition is GitWriteDisposition.VERIFIED
    assert second.disposition is GitWriteDisposition.VERIFIED
    assert first.receipt is not None and second.receipt is not None
    assert first.receipt.expected_commit == second.receipt.expected_commit


def test_bounded_patchset_remains_exact_against_a_larger_remote_repository(tmp_path):
    fixture = build_phase8_fixture(tmp_path, remote_extra_files=300)

    result = fixture.actuator.execute(
        fixture.capsule,
        patchset=fixture.patchset,
        base_root=fixture.base_root.resolve(),
        final_root=fixture.final_root.resolve(),
    )

    assert result.disposition is GitWriteDisposition.VERIFIED
    assert result.receipt is not None
    assert git("ls-tree", "-r", "--name-only", result.receipt.observed_commit_sha, cwd=fixture.bare).count(
        "\n"
    ) >= 300


def test_unresolved_write_becomes_durable_unknown_and_never_retries_blindly(tmp_path):
    fixture = build_phase8_fixture(tmp_path)
    service = _UnknownWithoutWriteService(fixture.service)
    actuator = _actuator(fixture, service)

    first = actuator.execute(
        fixture.capsule,
        patchset=fixture.patchset,
        base_root=fixture.base_root.resolve(),
        final_root=fixture.final_root.resolve(),
    )
    second = actuator.execute(
        fixture.capsule,
        patchset=fixture.patchset,
        base_root=fixture.base_root.resolve(),
        final_root=fixture.final_root.resolve(),
    )

    assert first.disposition is GitWriteDisposition.UNKNOWN
    assert first.reconciliation is not None
    assert first.reconciliation.blind_retry_allowed is False
    assert second.disposition is GitWriteDisposition.UNKNOWN
    assert second.reconciliation == first.reconciliation
    assert service.push_calls == 1
    assert actuator.remote_write_attempts == 1
    assert fixture.service.readback_feature_ref(target_branch=TARGET_BRANCH) is None


def test_completed_operation_replay_is_denied_without_second_effect(tmp_path):
    fixture = build_phase8_fixture(tmp_path)

    first = fixture.actuator.execute(
        fixture.capsule,
        patchset=fixture.patchset,
        base_root=fixture.base_root.resolve(),
        final_root=fixture.final_root.resolve(),
    )
    second = fixture.actuator.execute(
        fixture.capsule,
        patchset=fixture.patchset,
        base_root=fixture.base_root.resolve(),
        final_root=fixture.final_root.resolve(),
    )

    assert first.disposition is GitWriteDisposition.VERIFIED
    assert second.disposition is GitWriteDisposition.DENIED
    assert second.failure_code == "EXECUTION_OPERATION_REPLAY_DENIED"
    assert fixture.actuator.remote_write_attempts == 1
    assert git("rev-parse", "refs/heads/main", cwd=fixture.bare) == fixture.default_head


def test_local_git_children_receive_no_github_aws_or_ssh_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "synthetic-value-never-forwarded")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "synthetic-value-never-forwarded")
    monkeypatch.setenv("SSH_AUTH_SOCK", "/tmp/synthetic-agent.sock")
    fixture = build_phase8_fixture(tmp_path)

    result = fixture.actuator.execute(
        fixture.capsule,
        patchset=fixture.patchset,
        base_root=fixture.base_root.resolve(),
        final_root=fixture.final_root.resolve(),
    )

    assert result.disposition is GitWriteDisposition.VERIFIED
    names = set(fixture.service.child_environment_names)
    assert names.isdisjoint({"GH_TOKEN", "AWS_SECRET_ACCESS_KEY", "SSH_AUTH_SOCK"})
