"""Phase 4 offline proofs for sandbox policy and deterministic setup planning."""

from __future__ import annotations

import inspect
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from aioa_cloudops_agent.sandbox import (
    DOCKER_SANDBOX_V1,
    CleanupReceipt,
    DeterministicSetupPlanner,
    DockerCommandPlanBuilder,
    DockerInvocationPlan,
    DockerSandboxProvider,
    DockerToolboxIdentity,
    RepositorySourceIdentity,
    SandboxCommand,
    SandboxCommandProfile,
    SandboxLifecycle,
    SandboxLifecycleState,
    SandboxPolicy,
    SandboxPolicyDenied,
    SandboxProvider,
    SandboxResourceLimits,
    SandboxUnavailable,
    SetupEcosystem,
    SetupEnvironmentVariable,
    SetupPlan,
    SetupPlannerError,
    SnapshotRef,
    canonical_sandbox_digest,
    new_sandbox_ref,
    normalize_sandbox_relative_path,
)

CURRENT_COMMIT = "01eb2c3d90735999f197d447c88ad945aad43598"
IMAGE_DIGEST = "a" * 64
DEPENDENCY_DIGEST = "b" * 64


def _toolbox() -> DockerToolboxIdentity:
    return DockerToolboxIdentity(
        image_reference=f"aioa/sandbox-toolbox@sha256:{IMAGE_DIGEST}",
        image_digest=IMAGE_DIGEST,
        source_commit=CURRENT_COMMIT,
    )


def _python_fixture(root: Path) -> Path:
    root.mkdir(mode=0o700)
    (root / "requirements.txt").write_text(
        f"demo-package==1.2.3 --hash=sha256:{DEPENDENCY_DIGEST}\n",
        encoding="utf-8",
    )
    (root / "test_demo.py").write_text("def test_demo():\n    assert True\n", encoding="utf-8")
    return root


def _uv_fixture(root: Path) -> Path:
    root.mkdir(mode=0o700)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "fixture"\nversion = "1.0.0"\n',
        encoding="utf-8",
    )
    (root / "uv.lock").write_text("version = 1\nrevision = 3\n", encoding="utf-8")
    return root


def _node_fixture(root: Path) -> Path:
    root.mkdir(mode=0o700)
    package = {"name": "fixture", "version": "1.0.0", "scripts": {"postinstall": "false"}}
    lock = {
        "name": "fixture",
        "version": "1.0.0",
        "lockfileVersion": 3,
        "requires": True,
        "packages": {"": {"name": "fixture", "version": "1.0.0"}},
    }
    (root / "package.json").write_text(json.dumps(package, sort_keys=True), encoding="utf-8")
    (root / "package-lock.json").write_text(json.dumps(lock, sort_keys=True), encoding="utf-8")
    (root / "test.js").write_text("process.exit(0);\n", encoding="utf-8")
    return root


def _identity(root: Path) -> RepositorySourceIdentity:
    return DeterministicSetupPlanner().inspect_repository(root, source_commit=CURRENT_COMMIT)


def test_provider_surface_is_neutral_and_contains_no_remote_or_host_installer() -> None:
    provider = DockerSandboxProvider()

    assert isinstance(provider, SandboxProvider)
    required = {
        "availability",
        "collect_diff",
        "create",
        "destroy",
        "exec",
        "read_file",
        "restore",
        "setup_environment",
        "snapshot",
        "stage_repository",
        "write_file",
    }
    assert required <= set(dir(provider))
    assert {
        "commit",
        "create_branch",
        "merge",
        "push",
        "sudo",
    }.isdisjoint(dir(provider))
    source = inspect.getsource(type(provider))
    assert "apt-get" not in source
    assert "sudo" not in source
    assert "boto" not in source.casefold()


def test_missing_docker_is_explicit_and_never_attempts_host_install(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("aioa_cloudops_agent.sandbox.provider.shutil.which", lambda _name: None)
    provider = DockerSandboxProvider()

    availability = provider.availability()

    assert availability.available is False
    assert availability.status == "DOCKER_EXECUTABLE_MISSING"
    assert availability.host_install_attempted is False
    with pytest.raises(SandboxUnavailable, match="DOCKER_EXECUTABLE_MISSING"):
        provider.create(DOCKER_SANDBOX_V1)


def test_invalid_or_unproven_engine_never_becomes_available(tmp_path: Path) -> None:
    missing = DockerSandboxProvider((tmp_path / "missing-docker").as_posix())
    assert missing.availability().status == "DOCKER_EXECUTABLE_INVALID"

    candidate = tmp_path / "docker"
    candidate.write_text("not executed\n", encoding="utf-8")
    candidate.chmod(0o700)
    unproven = DockerSandboxProvider(candidate.as_posix())
    assert unproven.availability().available is False
    assert unproven.availability().status == "DOCKER_DAEMON_UNPROVEN"
    assert unproven.availability().engine_path_sha256 is not None
    with pytest.raises(SandboxUnavailable, match="DAEMON_AND_TOOLBOX_UNCERTIFIED"):
        unproven.create(DOCKER_SANDBOX_V1)


@pytest.mark.parametrize(
    "field,value",
    [
        ("run_as_user", "0:0"),
        ("privileged", True),
        ("cap_drop_all", False),
        ("no_new_privileges", False),
        ("read_only_root", False),
        ("docker_socket_mounted", True),
        ("host_home_mounted", True),
        ("arbitrary_host_mounts", True),
        ("repository_copy_only", False),
        ("setup_network", "UNRESTRICTED"),
        ("coding_network", "BRIDGE"),
        ("setup_credentials", True),
        ("snapshot_mode", "DOCKER_COMMIT"),
        ("host_package_install", True),
        ("allowed_setup_hosts", ("attacker.invalid",)),
    ],
)
def test_security_policy_cannot_be_weakened(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        SandboxPolicy(**{field: value})


def test_resource_limits_are_finite_and_bounded() -> None:
    limits = DOCKER_SANDBOX_V1.limits
    assert limits == SandboxResourceLimits()
    assert limits.cpu_count == 1.0
    assert limits.memory_mebibytes == 512
    assert limits.pids == 128
    assert limits.open_files == 1024
    assert limits.command_timeout_seconds == 300
    with pytest.raises(ValidationError):
        SandboxResourceLimits(memory_mebibytes=4096)
    with pytest.raises(ValidationError):
        SandboxResourceLimits(command_timeout_seconds=0)


def test_lifecycle_happy_path_is_exact_and_unknown_cannot_be_ready() -> None:
    lifecycle = SandboxLifecycle(
        new_sandbox_ref(DOCKER_SANDBOX_V1, now=datetime(2026, 9, 4, 14, 0, tzinfo=UTC))
    )
    expected = (
        SandboxLifecycleState.CREATED,
        SandboxLifecycleState.REPOSITORY_STAGED,
        SandboxLifecycleState.SETUP,
        SandboxLifecycleState.READY,
        SandboxLifecycleState.CODING_OFFLINE,
        SandboxLifecycleState.COLLECTING,
        SandboxLifecycleState.DESTROYED,
    )
    for state in expected[1:]:
        lifecycle.transition(state)

    assert lifecycle.history == expected
    assert lifecycle.reference.state is SandboxLifecycleState.DESTROYED
    with pytest.raises(SandboxPolicyDenied, match="TRANSITION_DENIED"):
        lifecycle.transition(SandboxLifecycleState.READY)


@pytest.mark.parametrize(
    "failure",
    [
        SandboxLifecycleState.SETUP_FAILED,
        SandboxLifecycleState.COMMAND_FAILED,
        SandboxLifecycleState.POLICY_DENIED,
        SandboxLifecycleState.RESOURCE_LIMIT,
        SandboxLifecycleState.CLEANUP_FAILED,
        SandboxLifecycleState.SANDBOX_CRASHED,
    ],
)
def test_failure_or_ambiguous_state_never_maps_to_ready(
    failure: SandboxLifecycleState,
) -> None:
    lifecycle = SandboxLifecycle(new_sandbox_ref(DOCKER_SANDBOX_V1))
    if failure is SandboxLifecycleState.CLEANUP_FAILED:
        lifecycle.transition(SandboxLifecycleState.POLICY_DENIED)
    lifecycle.transition(failure)
    with pytest.raises(SandboxPolicyDenied):
        lifecycle.transition(SandboxLifecycleState.READY)
    assert lifecycle.reference.state is failure


def test_python_requirements_plan_is_deterministic_hash_pinned_and_non_host(
    tmp_path: Path,
) -> None:
    root = _python_fixture(tmp_path / "python-fixture")
    identity = _identity(root)
    planner = DeterministicSetupPlanner()

    first = planner.plan_python(root, identity.tree_sha256)
    second = planner.plan_python(root, identity.tree_sha256)

    assert first == second
    assert first.ecosystem is SetupEcosystem.PYTHON_REQUIREMENTS
    assert first.argv == (
        "python",
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-input",
        "--require-hashes",
        "-r",
        "requirements.txt",
    )
    assert first.authority == "AIOA_DETERMINISTIC_SETUP_PLANNER"
    assert first.lifecycle_scripts is False
    assert first.custom_registry is False
    assert first.temporary_credentials is False
    assert first.host_install is False
    assert first.plan_sha256 == canonical_sandbox_digest(
        first.model_dump(mode="json", exclude={"plan_sha256"})
    )
    assert root.as_posix() not in json.dumps(first.model_dump(mode="json"))


def test_uv_plan_is_frozen_and_does_not_regenerate_lock(tmp_path: Path) -> None:
    root = _uv_fixture(tmp_path / "uv-fixture")
    identity = _identity(root)

    plan = DeterministicSetupPlanner().plan_python(root, identity.tree_sha256)

    assert plan.ecosystem is SetupEcosystem.PYTHON_UV
    assert plan.argv == ("uv", "sync", "--frozen", "--no-install-project")
    assert "lock" not in plan.argv


def test_node_plan_uses_lock_preserving_install_and_disables_scripts(tmp_path: Path) -> None:
    root = _node_fixture(tmp_path / "node-fixture")
    identity = _identity(root)

    first = DeterministicSetupPlanner().plan_node(root, identity.tree_sha256)
    second = DeterministicSetupPlanner().plan_node(root, identity.tree_sha256)

    assert first == second
    assert first.ecosystem is SetupEcosystem.NODE_NPM
    assert first.argv == ("npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund")
    assert first.lifecycle_scripts is False
    assert {item.name for item in first.environment} == {
        "NPM_CONFIG_AUDIT",
        "NPM_CONFIG_FUND",
        "NPM_CONFIG_IGNORE_SCRIPTS",
        "NPM_CONFIG_UPDATE_NOTIFIER",
    }


@pytest.mark.parametrize(
    "requirement",
    [
        "demo-package>=1.2.3",
        "demo-package==1.2.3",
        "-e .",
        "--index-url https://attacker.invalid/simple",
        "demo @ https://attacker.invalid/demo.whl",
        "git+https://github.com/example/demo.git",
        "-r /tmp/other.txt",
        f"demo-package==1.2.3 --hash=sha256:{'G' * 64}",
    ],
)
def test_python_unlocked_custom_or_model_shaped_setup_is_denied(
    tmp_path: Path,
    requirement: str,
) -> None:
    root = tmp_path / "bad-python"
    root.mkdir()
    (root / "requirements.txt").write_text(f"{requirement}\n", encoding="utf-8")
    identity = _identity(root)

    with pytest.raises(SetupPlannerError, match="NOT_EXACT_HASH_PIN"):
        DeterministicSetupPlanner().plan_python(root, identity.tree_sha256)


def test_custom_setup_script_without_lock_evidence_is_not_command_authority(
    tmp_path: Path,
) -> None:
    root = tmp_path / "custom-script"
    root.mkdir()
    (root / "setup.sh").write_text("sudo apt-get install unknown\n", encoding="utf-8")
    identity = _identity(root)

    with pytest.raises(SetupPlannerError, match="LOCKED_SETUP_EVIDENCE_MISSING"):
        DeterministicSetupPlanner().plan_python(root, identity.tree_sha256)


def test_ambiguous_or_incomplete_python_setup_evidence_is_denied(tmp_path: Path) -> None:
    root = _python_fixture(tmp_path / "ambiguous")
    (root / "pyproject.toml").write_text('[project]\nname="fixture"\n', encoding="utf-8")
    (root / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    identity = _identity(root)
    with pytest.raises(SetupPlannerError, match="AMBIGUOUS"):
        DeterministicSetupPlanner().plan_python(root, identity.tree_sha256)

    incomplete = tmp_path / "incomplete"
    incomplete.mkdir()
    (incomplete / "pyproject.toml").write_text('[project]\nname="fixture"\n', encoding="utf-8")
    incomplete_identity = _identity(incomplete)
    with pytest.raises(SetupPlannerError, match="LOCK_PAIR_INCOMPLETE"):
        DeterministicSetupPlanner().plan_python(incomplete, incomplete_identity.tree_sha256)


def test_custom_npm_registry_and_lock_drift_are_denied(tmp_path: Path) -> None:
    root = _node_fixture(tmp_path / "node-custom")
    lock_path = root / "package-lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    lock["packages"]["node_modules/demo"] = {
        "version": "1.0.0",
        "resolved": "https://attacker.invalid/demo.tgz",
    }
    lock_path.write_text(json.dumps(lock, sort_keys=True), encoding="utf-8")
    identity = _identity(root)
    with pytest.raises(SetupPlannerError, match="CUSTOM_REGISTRY_DENIED"):
        DeterministicSetupPlanner().plan_node(root, identity.tree_sha256)

    clean = _node_fixture(tmp_path / "node-drift")
    clean_identity = _identity(clean)
    (clean / "test.js").write_text("process.exit(1);\n", encoding="utf-8")
    with pytest.raises(SetupPlannerError, match="IDENTITY_MISMATCH"):
        DeterministicSetupPlanner().plan_node(clean, clean_identity.tree_sha256)


def test_link_hardlink_special_and_secret_paths_are_rejected(tmp_path: Path) -> None:
    source = _python_fixture(tmp_path / "source")
    outside = tmp_path / "outside"
    outside.write_text("outside\n", encoding="utf-8")
    (source / "linked.txt").symlink_to(outside)
    with pytest.raises((SetupPlannerError, ValueError), match=r"LINK_FORBIDDEN|IDENTITY_INVALID"):
        DeterministicSetupPlanner().inspect_repository(source)

    hardlinked = _python_fixture(tmp_path / "hardlinked")
    os.link(hardlinked / "requirements.txt", hardlinked / "duplicate.txt")
    with pytest.raises(
        (SetupPlannerError, ValueError), match=r"FILE_TYPE_FORBIDDEN|IDENTITY_INVALID"
    ):
        DeterministicSetupPlanner().inspect_repository(hardlinked)

    secret = _python_fixture(tmp_path / "secret")
    (secret / ".env").write_text("TOKEN=synthetic\n", encoding="utf-8")
    with pytest.raises((SetupPlannerError, ValueError), match=r"SECRET_PATH|IDENTITY_INVALID"):
        DeterministicSetupPlanner().inspect_repository(secret)


@pytest.mark.parametrize(
    "path",
    [
        "/etc/passwd",
        "../outside",
        "safe/../../outside",
        ".ssh/id_rsa",
        "safe/.config/value",
        "safe\\windows",
        "safe\x00value",
        " safe",
    ],
)
def test_absolute_traversal_hidden_and_control_paths_are_denied(path: str) -> None:
    with pytest.raises(ValueError):
        normalize_sandbox_relative_path(path)


def test_docker_setup_and_offline_argv_preserve_security_profile(tmp_path: Path) -> None:
    root = _python_fixture(tmp_path / "python-plan")
    identity = _identity(root)
    setup_plan = DeterministicSetupPlanner().plan_python(root, identity.tree_sha256)
    reference = new_sandbox_ref(DOCKER_SANDBOX_V1)
    builder = DockerCommandPlanBuilder("/usr/bin/docker", _toolbox(), DOCKER_SANDBOX_V1)

    setup = builder.setup(reference, setup_plan)
    offline = builder.offline(
        reference,
        SandboxCommand(
            profile=SandboxCommandProfile.PYTHON_TEST,
            argv=("python", "-m", "pytest", "-q"),
        ),
    )

    for invocation in (setup, offline):
        assert invocation.privileged is False
        assert invocation.host_bind_mounts == 0
        assert invocation.docker_socket_mounts == 0
        assert invocation.host_home_mounts == 0
        assert invocation.structured_argv is True
        assert "--read-only" in invocation.argv
        assert "--cap-drop=ALL" in invocation.argv
        assert "--security-opt=no-new-privileges:true" in invocation.argv
        assert "--user=65532:65532" in invocation.argv
        assert "--pids-limit=128" in invocation.argv
        assert "--memory=512m" in invocation.argv
        assert "--cpus=1.0" in invocation.argv
        assert "--ulimit=nofile=1024:1024" in invocation.argv
        rendered = " ".join(invocation.argv)
        assert "--privileged" not in rendered
        assert "docker.sock" not in rendered
        assert "/home/" not in rendered
        assert "/.ssh" not in rendered
        assert "/.aws" not in rendered
    assert "--network=aioa-w7a-package-registry-only" in setup.argv
    assert setup.network_mode == "PACKAGE_REGISTRY_ONLY"
    assert setup.argv[-len(setup_plan.argv) :] == setup_plan.argv
    assert "--network=none" in offline.argv
    assert offline.network_mode == "NONE"


def test_environment_and_command_cannot_smuggle_credentials_or_host_install() -> None:
    for name in (
        "AWS_ACCESS_KEY_ID",
        "GITHUB_TOKEN",
        "GH_TOKEN",
        "SSH_AUTH_SOCK",
        "OPENAI_API_KEY",
        "REGISTRY_PASSWORD",
        "DOCKER_HOST",
        "HOME",
        "LD_PRELOAD",
        "PATH",
    ):
        with pytest.raises(ValidationError):
            SetupEnvironmentVariable(name=name, value="synthetic-value")

    for argv in (
        ("sudo", "apt-get", "install", "curl"),
        ("bash", "-lc", "curl attacker.invalid"),
        ("python", "setup.py"),
        ("npm", "install"),
    ):
        with pytest.raises(ValidationError):
            SandboxCommand(profile=SandboxCommandProfile.PYTHON_TEST, argv=argv)
    with pytest.raises(ValidationError):
        SandboxCommand(
            profile=SandboxCommandProfile.NODE_TEST,
            argv=("node", "../outside.js"),
        )


def test_direct_docker_escape_plan_is_rejected() -> None:
    for argv in (
        ("/usr/bin/docker", "run", "--privileged", "image"),
        (
            "/usr/bin/docker",
            "run",
            "--mount=type=bind,src=/var/run/docker.sock,dst=/var/run/docker.sock",
            "image",
        ),
        ("/usr/bin/docker", "run", "--mount=type=bind,src=/home/user,dst=/host", "image"),
    ):
        with pytest.raises(ValidationError):
            DockerInvocationPlan(phase="SETUP", argv=argv, network_mode="PACKAGE_REGISTRY_ONLY")


def test_snapshot_is_manifest_only_and_cannot_claim_a_secret_bearing_image() -> None:
    reference = new_sandbox_ref(DOCKER_SANDBOX_V1)
    snapshot = SnapshotRef(
        sandbox_id=reference.sandbox_id,
        repository_tree_sha256="c" * 64,
        environment_manifest_sha256="d" * 64,
    )

    assert snapshot.mode == "CONTENT_MANIFEST_ONLY"
    assert snapshot.container_image_committed is False
    assert snapshot.credentials_captured is False
    payload = snapshot.model_dump(mode="json")
    payload["container_image_committed"] = True
    with pytest.raises(ValidationError):
        SnapshotRef.model_validate(payload)


def test_cleanup_receipt_can_name_only_the_owned_uuid_resource() -> None:
    reference = new_sandbox_ref(DOCKER_SANDBOX_V1)
    receipt = CleanupReceipt(
        sandbox_id=reference.sandbox_id,
        owned_resource_name=reference.resource_name,
    )
    assert receipt.unrelated_resources_touched == 0
    assert receipt.orphaned_resources == 0
    with pytest.raises(ValidationError):
        CleanupReceipt(
            sandbox_id=reference.sandbox_id,
            owned_resource_name="unrelated-container",
        )


def test_setup_plan_cannot_be_tampered_after_digest_binding(tmp_path: Path) -> None:
    root = _python_fixture(tmp_path / "tamper")
    identity = _identity(root)
    plan = DeterministicSetupPlanner().plan_python(root, identity.tree_sha256)
    payload = plan.model_dump(mode="json")
    payload["argv"] = ["python", "-m", "pip", "install", "attacker-package"]

    with pytest.raises(ValidationError):
        SetupPlan.model_validate(payload)


def test_toolbox_requires_matching_digest_and_non_root_identity() -> None:
    assert _toolbox().non_root_user == "65532:65532"
    with pytest.raises(ValidationError):
        DockerToolboxIdentity(
            image_reference=f"aioa/sandbox-toolbox@sha256:{IMAGE_DIGEST}",
            image_digest="b" * 64,
            source_commit=CURRENT_COMMIT,
        )
    with pytest.raises(ValidationError):
        DockerToolboxIdentity(
            image_reference="aioa/sandbox-toolbox:latest",
            image_digest=IMAGE_DIGEST,
            source_commit=CURRENT_COMMIT,
        )
