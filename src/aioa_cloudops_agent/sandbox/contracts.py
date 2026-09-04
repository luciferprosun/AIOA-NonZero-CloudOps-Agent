"""Closed contracts for disposable, credentialless coding sandboxes."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from aioa_cloudops_agent.nz import Sha256Digest, Uuid7Identifier
from aioa_cloudops_agent.nz.contracts import NonZeroContract
from aioa_cloudops_agent.nz.redaction import contains_sensitive_material

SANDBOX_WORKSPACE = "/workspace"
SANDBOX_USER = "65532:65532"
SANDBOX_TAINT = "UNTRUSTED_REPOSITORY_CODE"

_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_RESOURCE_NAME = re.compile(r"^aioa-w7a-[0-9a-f-]{36}$")
_IMAGE = re.compile(r"^aioa/sandbox-toolbox@sha256:(?P<digest>[0-9a-f]{64})$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_FORBIDDEN_ENV_PARTS = (
    "AWS",
    "AZURE",
    "CODEX",
    "CREDENTIAL",
    "GCP",
    "GH_",
    "GITHUB",
    "KEY",
    "OPENAI",
    "PASSWORD",
    "SECRET",
    "SSH",
    "TOKEN",
)
_ALLOWED_SANDBOX_ENV_NAMES = frozenset(
    {
        "NPM_CONFIG_AUDIT",
        "NPM_CONFIG_FUND",
        "NPM_CONFIG_IGNORE_SCRIPTS",
        "NPM_CONFIG_UPDATE_NOTIFIER",
        "PIP_DISABLE_PIP_VERSION_CHECK",
        "PIP_NO_INPUT",
        "UV_NO_PROGRESS",
    }
)


def canonical_sandbox_digest(value: object) -> str:
    """Hash strict canonical JSON for setup, policy, and receipt identity."""

    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def normalize_sandbox_relative_path(value: object) -> str:
    """Accept one visible canonical path relative to the sandbox workspace."""

    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("sandbox path must be non-empty canonical text")
    if "\\" in value or "\x00" in value:
        raise ValueError("sandbox path contains a forbidden character")
    candidate = PurePosixPath(value)
    if candidate.is_absolute() or candidate.as_posix() != value or not candidate.parts:
        raise ValueError("sandbox path must be canonical relative POSIX text")
    for part in candidate.parts:
        if part in {"", ".", ".."} or part.startswith(".") or len(part) > 128:
            raise ValueError("sandbox path contains a forbidden segment")
        if part.casefold() in {
            "credentials",
            "id_ed25519",
            "id_rsa",
            "known_hosts",
        }:
            raise ValueError("sandbox path is secret-sensitive")
    if len(value) > 1024:
        raise ValueError("sandbox path is too long")
    return value


class SandboxLifecycleState(StrEnum):
    """Closed success and failure states; unknown never means ready."""

    CREATED = "CREATED"
    REPOSITORY_STAGED = "REPOSITORY_STAGED"
    SETUP = "SETUP"
    READY = "READY"
    CODING_OFFLINE = "CODING_OFFLINE"
    COLLECTING = "COLLECTING"
    DESTROYED = "DESTROYED"
    SETUP_FAILED = "SETUP_FAILED"
    COMMAND_FAILED = "COMMAND_FAILED"
    POLICY_DENIED = "POLICY_DENIED"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"
    CLEANUP_FAILED = "CLEANUP_FAILED"
    SANDBOX_CRASHED = "SANDBOX_CRASHED"


class SetupEcosystem(StrEnum):
    PYTHON_REQUIREMENTS = "PYTHON_REQUIREMENTS"
    PYTHON_UV = "PYTHON_UV"
    NODE_NPM = "NODE_NPM"


class SandboxCommandProfile(StrEnum):
    PYTHON_TEST = "PYTHON_TEST"
    NODE_TEST = "NODE_TEST"


class SandboxResourceLimits(NonZeroContract):
    """Finite v1 bounds applied to every planned container invocation."""

    cpu_count: float = Field(default=1.0, gt=0, le=2.0)
    memory_mebibytes: int = Field(default=512, ge=128, le=2048)
    pids: int = Field(default=128, ge=16, le=256)
    open_files: int = Field(default=1024, ge=64, le=4096)
    command_timeout_seconds: int = Field(default=300, ge=1, le=900)
    output_bytes: int = Field(default=128 * 1024, ge=1024, le=1024 * 1024)


class SandboxPolicy(NonZeroContract):
    """Server-owned Docker v1 ceiling; callers cannot enable unsafe controls."""

    profile_id: Literal["DOCKER_SANDBOX_V1"] = "DOCKER_SANDBOX_V1"
    run_as_user: Literal["65532:65532"] = SANDBOX_USER
    privileged: Literal[False] = False
    cap_drop_all: Literal[True] = True
    no_new_privileges: Literal[True] = True
    read_only_root: Literal[True] = True
    docker_socket_mounted: Literal[False] = False
    host_home_mounted: Literal[False] = False
    arbitrary_host_mounts: Literal[False] = False
    repository_copy_only: Literal[True] = True
    setup_network: Literal["PACKAGE_REGISTRY_ONLY"] = "PACKAGE_REGISTRY_ONLY"
    coding_network: Literal["NONE"] = "NONE"
    setup_credentials: Literal[False] = False
    snapshot_mode: Literal["CONTENT_MANIFEST_ONLY"] = "CONTENT_MANIFEST_ONLY"
    host_package_install: Literal[False] = False
    allowed_setup_hosts: tuple[
        Literal["files.pythonhosted.org"],
        Literal["pypi.org"],
        Literal["registry.npmjs.org"],
    ] = ("files.pythonhosted.org", "pypi.org", "registry.npmjs.org")
    limits: SandboxResourceLimits = Field(default_factory=SandboxResourceLimits)

    @property
    def policy_sha256(self) -> str:
        return canonical_sandbox_digest(self.model_dump(mode="json"))


DOCKER_SANDBOX_V1 = SandboxPolicy()


class DockerToolboxIdentity(NonZeroContract):
    """Content-addressed external image identity; tags alone are forbidden."""

    image_reference: str = Field(min_length=1, max_length=256)
    image_digest: Sha256Digest
    source_commit: str
    non_root_user: Literal["65532:65532"] = SANDBOX_USER
    contains_git: Literal[True] = True
    contains_python: Literal[True] = True
    contains_node: Literal[True] = True
    contains_ripgrep: Literal[True] = True
    secrets_baked_in: Literal[False] = False

    @field_validator("source_commit")
    @classmethod
    def validate_source_commit(cls, value: str) -> str:
        if _COMMIT.fullmatch(value) is None:
            raise ValueError("toolbox source commit must be a full lowercase SHA")
        return value

    @model_validator(mode="after")
    def validate_reference_digest(self) -> Self:
        match = _IMAGE.fullmatch(self.image_reference)
        if match is None or match.group("digest") != self.image_digest:
            raise ValueError("toolbox image must be addressed by its matching digest")
        return self


class SandboxRef(NonZeroContract):
    sandbox_id: Uuid7Identifier
    provider: Literal["docker"] = "docker"
    resource_name: str
    workspace_volume: str
    state: SandboxLifecycleState
    policy_sha256: Sha256Digest
    created_at: datetime

    @field_validator("resource_name", "workspace_volume")
    @classmethod
    def validate_owned_resource_name(cls, value: str) -> str:
        if _RESOURCE_NAME.fullmatch(value) is None:
            raise ValueError("sandbox resource is not an AIOA-owned UUID name")
        return value

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("sandbox timestamp must use timezone-aware UTC")
        return value


class RepositorySourceIdentity(NonZeroContract):
    tree_sha256: Sha256Digest
    source_commit: str | None = None
    file_count: int = Field(ge=1, le=256)
    total_bytes: int = Field(ge=1, le=16 * 1024 * 1024)

    @field_validator("source_commit")
    @classmethod
    def validate_optional_commit(cls, value: str | None) -> str | None:
        if value is not None and _COMMIT.fullmatch(value) is None:
            raise ValueError("repository commit identity is invalid")
        return value


class StagedRepoRef(NonZeroContract):
    sandbox_id: Uuid7Identifier
    repository: RepositorySourceIdentity
    archive_sha256: Sha256Digest
    workspace_path: Literal["/workspace"] = SANDBOX_WORKSPACE
    state: Literal[SandboxLifecycleState.REPOSITORY_STAGED] = (
        SandboxLifecycleState.REPOSITORY_STAGED
    )
    staged_as_copy: Literal[True] = True
    host_bind_mounted: Literal[False] = False


class SetupManifest(NonZeroContract):
    relative_path: str
    sha256: Sha256Digest
    size: int = Field(gt=0, le=1024 * 1024)

    @field_validator("relative_path")
    @classmethod
    def validate_relative_path(cls, value: str) -> str:
        return normalize_sandbox_relative_path(value)


class SetupEnvironmentVariable(NonZeroContract):
    name: str
    value: str = Field(max_length=256)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if (
            _ENV_NAME.fullmatch(value) is None
            or value not in _ALLOWED_SANDBOX_ENV_NAMES
            or any(part in value for part in _FORBIDDEN_ENV_PARTS)
        ):
            raise ValueError("setup environment name is not credentialless")
        return value

    @field_validator("value")
    @classmethod
    def validate_value(cls, value: str) -> str:
        if contains_sensitive_material(value):
            raise ValueError("setup environment value contains credential-shaped material")
        return value


class SetupPlan(NonZeroContract):
    """Deterministic installer plan generated only from reviewed manifest evidence."""

    schema_version: Literal[1] = 1
    authority: Literal["AIOA_DETERMINISTIC_SETUP_PLANNER"] = "AIOA_DETERMINISTIC_SETUP_PLANNER"
    repository_tree_sha256: Sha256Digest
    ecosystem: SetupEcosystem
    manifests: tuple[SetupManifest, ...] = Field(min_length=1, max_length=2)
    argv: tuple[str, ...] = Field(min_length=3, max_length=16)
    environment: tuple[SetupEnvironmentVariable, ...] = Field(max_length=8)
    network_mode: Literal["PACKAGE_REGISTRY_ONLY"] = "PACKAGE_REGISTRY_ONLY"
    lifecycle_scripts: Literal[False] = False
    custom_registry: Literal[False] = False
    temporary_credentials: Literal[False] = False
    host_install: Literal[False] = False
    plan_sha256: Sha256Digest

    @model_validator(mode="after")
    def validate_closed_plan(self) -> Self:
        paths = tuple(item.relative_path for item in self.manifests)
        if paths != tuple(sorted(set(paths))):
            raise ValueError("setup manifests must be unique and canonically sorted")
        expected_argv, expected_environment, expected_paths = _expected_setup_contract(
            self.ecosystem
        )
        if self.argv != expected_argv or self.environment != expected_environment:
            raise ValueError("setup argv/environment is not the fixed ecosystem contract")
        if paths != expected_paths:
            raise ValueError("setup manifest set does not match ecosystem")
        if any(not part or "\x00" in part for part in self.argv):
            raise ValueError("setup argv contains an invalid element")
        material = self.model_dump(mode="json", exclude={"plan_sha256"})
        if canonical_sandbox_digest(material) != self.plan_sha256:
            raise ValueError("setup plan digest does not match canonical content")
        return self

    @classmethod
    def build(
        cls,
        repository_tree_sha256: str,
        ecosystem: SetupEcosystem,
        manifests: tuple[SetupManifest, ...],
    ) -> SetupPlan:
        argv, environment, _ = _expected_setup_contract(ecosystem)
        material = {
            "schema_version": 1,
            "authority": "AIOA_DETERMINISTIC_SETUP_PLANNER",
            "repository_tree_sha256": repository_tree_sha256,
            "ecosystem": ecosystem.value,
            "manifests": [item.model_dump(mode="json") for item in manifests],
            "argv": list(argv),
            "environment": [item.model_dump(mode="json") for item in environment],
            "network_mode": "PACKAGE_REGISTRY_ONLY",
            "lifecycle_scripts": False,
            "custom_registry": False,
            "temporary_credentials": False,
            "host_install": False,
        }
        return cls(**material, plan_sha256=canonical_sandbox_digest(material))


class SetupReceipt(NonZeroContract):
    sandbox_id: Uuid7Identifier
    plan_sha256: Sha256Digest
    ecosystem: SetupEcosystem
    package_manager_version: str = Field(min_length=1, max_length=128)
    exit_code: Literal[0] = 0
    duration_milliseconds: int = Field(ge=0, le=900_000)
    stdout_sha256: Sha256Digest
    stderr_sha256: Sha256Digest
    installed_manifest_sha256: Sha256Digest
    setup_network_used: Literal[True] = True
    coding_network_disabled: Literal[True] = True
    temporary_credentials_remaining: Literal[0] = 0
    github_credentials_present: Literal[0] = 0
    aws_credentials_present: Literal[0] = 0
    ssh_credentials_present: Literal[0] = 0
    state: Literal[SandboxLifecycleState.READY] = SandboxLifecycleState.READY


class SandboxCommand(NonZeroContract):
    profile: SandboxCommandProfile
    argv: tuple[str, ...] = Field(min_length=2, max_length=32)
    cwd: Literal["/workspace"] = SANDBOX_WORKSPACE
    environment: tuple[SetupEnvironmentVariable, ...] = Field(default=(), max_length=8)
    timeout_seconds: int = Field(default=300, ge=1, le=900)

    @model_validator(mode="after")
    def validate_profile_argv(self) -> Self:
        if self.profile is SandboxCommandProfile.PYTHON_TEST:
            if self.argv[:3] != ("python", "-m", "pytest"):
                raise ValueError("Python test profile requires python -m pytest")
        else:
            if self.argv[0] != "node" or not self.argv[1].endswith(".js"):
                raise ValueError("Node test profile requires a relative JavaScript entrypoint")
            normalize_sandbox_relative_path(self.argv[1])
        if self.argv[0] in {"apt", "apt-get", "bash", "docker", "pkexec", "sh", "sudo", "su"}:
            raise ValueError("sandbox command requests a forbidden host/control executable")
        for part in self.argv:
            if not part or "\x00" in part or "\n" in part or "\r" in part:
                raise ValueError("sandbox argv contains an invalid element")
        return self


class CommandReceipt(NonZeroContract):
    sandbox_id: Uuid7Identifier
    profile: SandboxCommandProfile
    argv_sha256: Sha256Digest
    exit_code: int = Field(ge=0, le=255)
    duration_milliseconds: int = Field(ge=0, le=900_000)
    stdout_sha256: Sha256Digest
    stderr_sha256: Sha256Digest
    output_truncated: bool
    network_mode: Literal["NONE"] = "NONE"
    state: SandboxLifecycleState


class FileReceipt(NonZeroContract):
    sandbox_id: Uuid7Identifier
    relative_path: str
    sha256: Sha256Digest
    size: int = Field(ge=0, le=16 * 1024 * 1024)

    @field_validator("relative_path")
    @classmethod
    def validate_relative_path(cls, value: str) -> str:
        return normalize_sandbox_relative_path(value)


class WriteReceipt(FileReceipt):
    previous_sha256: Sha256Digest | None = None
    atomic_replace: Literal[True] = True


class SnapshotRef(NonZeroContract):
    sandbox_id: Uuid7Identifier
    repository_tree_sha256: Sha256Digest
    environment_manifest_sha256: Sha256Digest
    mode: Literal["CONTENT_MANIFEST_ONLY"] = "CONTENT_MANIFEST_ONLY"
    container_image_committed: Literal[False] = False
    credentials_captured: Literal[False] = False


class DiffReceipt(NonZeroContract):
    sandbox_id: Uuid7Identifier
    base_tree_sha256: Sha256Digest
    current_tree_sha256: Sha256Digest
    changed_paths: tuple[str, ...] = Field(max_length=256)
    diff_sha256: Sha256Digest
    truncated: bool = False

    @field_validator("changed_paths")
    @classmethod
    def validate_changed_paths(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(normalize_sandbox_relative_path(path) for path in value)
        if normalized != tuple(sorted(set(normalized))):
            raise ValueError("changed paths must be unique and canonically sorted")
        return normalized


class CleanupReceipt(NonZeroContract):
    sandbox_id: Uuid7Identifier
    owned_resource_name: str
    removed: Literal[True] = True
    unrelated_resources_touched: Literal[0] = 0
    orphaned_resources: Literal[0] = 0
    state: Literal[SandboxLifecycleState.DESTROYED] = SandboxLifecycleState.DESTROYED

    @field_validator("owned_resource_name")
    @classmethod
    def validate_owned_resource_name(cls, value: str) -> str:
        if _RESOURCE_NAME.fullmatch(value) is None:
            raise ValueError("cleanup receipt resource is not AIOA-owned")
        return value


def _expected_setup_contract(
    ecosystem: SetupEcosystem,
) -> tuple[
    tuple[str, ...],
    tuple[SetupEnvironmentVariable, ...],
    tuple[str, ...],
]:
    if ecosystem is SetupEcosystem.PYTHON_REQUIREMENTS:
        return (
            (
                "python",
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--no-input",
                "--require-hashes",
                "-r",
                "requirements.txt",
            ),
            (
                SetupEnvironmentVariable(name="PIP_DISABLE_PIP_VERSION_CHECK", value="1"),
                SetupEnvironmentVariable(name="PIP_NO_INPUT", value="1"),
            ),
            ("requirements.txt",),
        )
    if ecosystem is SetupEcosystem.PYTHON_UV:
        return (
            ("uv", "sync", "--frozen", "--no-install-project"),
            (SetupEnvironmentVariable(name="UV_NO_PROGRESS", value="1"),),
            ("pyproject.toml", "uv.lock"),
        )
    return (
        ("npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"),
        (
            SetupEnvironmentVariable(name="NPM_CONFIG_AUDIT", value="false"),
            SetupEnvironmentVariable(name="NPM_CONFIG_FUND", value="false"),
            SetupEnvironmentVariable(name="NPM_CONFIG_IGNORE_SCRIPTS", value="true"),
            SetupEnvironmentVariable(name="NPM_CONFIG_UPDATE_NOTIFIER", value="false"),
        ),
        ("package-lock.json", "package.json"),
    )
