"""Structured Git repository services for the isolated Phase 8 actuator."""

from __future__ import annotations

import base64
import hashlib
import os
import shutil
import stat
import subprocess
import tempfile
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from pydantic import SecretStr

from aioa_cloudops_agent.execution import (
    TARGET_BRANCH_PREFIX,
    ExecutionRepositoryIdentity,
    normalize_branch,
)
from aioa_cloudops_agent.nz.redaction import redact_sensitive_text
from aioa_cloudops_agent.workspace.contracts import canonical_workspace_json_digest

from .write_contracts import (
    GitCommitIdentity,
    GitPushAcknowledgement,
    GitRemoteCommitReadback,
    GitRemoteObservation,
)

_ZERO_OID = "0" * 40
_MAX_GIT_OUTPUT = 1024 * 1024
_GIT_ENV_ALLOWLIST = frozenset({"PATH", "SYSTEMROOT", "TMPDIR"})


class GitRepositoryError(RuntimeError):
    """Stable value-free repository failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class GitRemoteWriteUnknown(GitRepositoryError):
    """The write transport ended without a trustworthy acknowledgement."""


class GitHubWriteCredential:
    """Non-serializable credential exposed only to the Git push subprocess."""

    __slots__ = ("_secret",)

    def __init__(self, secret: SecretStr) -> None:
        if not isinstance(secret, SecretStr) or len(secret.get_secret_value()) < 8:
            raise ValueError("GitHub write credential is unavailable")
        self._secret = secret

    def _git_environment(self) -> dict[str, str]:
        raw = self._secret.get_secret_value()
        encoded = base64.b64encode(f"x-access-token:{raw}".encode()).decode("ascii")
        return {
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
            "GIT_CONFIG_VALUE_0": f"Authorization: Basic {encoded}",
        }

    def destroy(self) -> None:
        self._secret = SecretStr("destroyed")


class RepositoryService(Protocol):
    """No method accepts a shell command, argv, refspec, URL, tag or merge request."""

    @property
    def identity(self) -> ExecutionRepositoryIdentity: ...

    @property
    def requires_write_credential(self) -> bool: ...

    @property
    def child_environment_names(self) -> tuple[str, ...]: ...

    def observe(self, *, base_ref: str, target_branch: str) -> GitRemoteObservation: ...

    def prepare_exact_base(self, *, base_head: str, destination: Path) -> None: ...

    def create_deterministic_commit(
        self,
        *,
        workspace: Path,
        base_head: str,
        changed_paths: tuple[str, ...],
        operation_id: str,
        timestamp: datetime,
    ) -> GitCommitIdentity: ...

    def prepare_commit_snapshot(
        self,
        *,
        source_workspace: Path,
        commit_sha: str,
        destination: Path,
    ) -> None: ...

    def push_feature_ref_once(
        self,
        *,
        workspace: Path,
        commit_sha: str,
        target_branch: str,
        credential: GitHubWriteCredential | None,
    ) -> GitPushAcknowledgement: ...

    def readback_feature_ref(self, *, target_branch: str) -> GitRemoteCommitReadback | None: ...


class _GitRunner:
    def __init__(self, *, timeout_seconds: float = 30.0) -> None:
        git = shutil.which("git")
        if git is None:
            raise GitRepositoryError("GIT_EXECUTABLE_UNAVAILABLE")
        self._git = git
        self._timeout = timeout_seconds
        self._last_environment_names: tuple[str, ...] = ()

    @property
    def last_environment_names(self) -> tuple[str, ...]:
        return self._last_environment_names

    def run(
        self,
        arguments: tuple[str, ...],
        *,
        cwd: Path,
        failure_code: str,
        extra_environment: Mapping[str, str] | None = None,
        allow_failure: bool = False,
        write_boundary: bool = False,
    ) -> str | None:
        if not cwd.is_absolute():
            raise GitRepositoryError("GIT_WORKSPACE_PATH_INVALID")
        environment = {
            key: value for key, value in os.environ.items() if key in _GIT_ENV_ALLOWLIST
        }
        environment.update(
            {
                "GIT_ASKPASS": "/bin/false",
                "GIT_CONFIG_GLOBAL": "/dev/null",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_TERMINAL_PROMPT": "0",
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
                "SSH_ASKPASS": "/bin/false",
            }
        )
        if extra_environment is not None:
            environment.update(extra_environment)
        self._last_environment_names = tuple(sorted(environment))
        try:
            completed = subprocess.run(
                (self._git, *arguments),
                cwd=cwd,
                env=environment,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                check=False,
                timeout=self._timeout,
            )
        except subprocess.TimeoutExpired as error:
            if write_boundary:
                raise GitRemoteWriteUnknown("GIT_REMOTE_WRITE_ACK_UNKNOWN") from error
            raise GitRepositoryError(failure_code) from error
        except OSError as error:
            if write_boundary:
                raise GitRemoteWriteUnknown("GIT_REMOTE_WRITE_ACK_UNKNOWN") from error
            raise GitRepositoryError(failure_code) from error
        if len(completed.stdout) + len(completed.stderr) > _MAX_GIT_OUTPUT:
            raise GitRepositoryError("GIT_OUTPUT_LIMIT_EXCEEDED")
        if completed.returncode != 0:
            if allow_failure:
                return None
            if write_boundary:
                # A rejected push is still reconciled read-only before any final claim.
                raise GitRemoteWriteUnknown("GIT_REMOTE_WRITE_RESULT_UNKNOWN")
            raise GitRepositoryError(failure_code)
        try:
            decoded = completed.stdout.decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            raise GitRepositoryError("GIT_OUTPUT_ENCODING_INVALID") from error
        # Keep accidental diagnostics from retaining secret-shaped material.
        return redact_sensitive_text(decoded)


def _observation(
    *,
    repository: ExecutionRepositoryIdentity,
    default_branch: str,
    base_ref: str,
    base_head: str,
    target_branch: str,
    target_head: str | None,
) -> GitRemoteObservation:
    values: dict[str, object] = {
        "repository": repository,
        "default_branch": default_branch,
        "base_ref": base_ref,
        "base_head": base_head,
        "target_branch": target_branch,
        "target_head": target_head,
        "observed_at": datetime.now(UTC),
    }
    provisional = GitRemoteObservation.model_construct(
        **values,
        authority="INDEPENDENT_READ_ONLY_GIT",
        observation_sha256="0" * 64,
    )
    return GitRemoteObservation(
        **values,
        observation_sha256=canonical_workspace_json_digest(
            provisional.model_dump(mode="json", exclude={"observation_sha256"})
        ),
    )


def _validate_sha(value: str) -> str:
    if len(value) != 40 or any(character not in "0123456789abcdef" for character in value):
        raise GitRepositoryError("GIT_OBJECT_ID_INVALID")
    return value


def _validate_target(value: str) -> str:
    target = normalize_branch(value)
    if not target.startswith(TARGET_BRANCH_PREFIX):
        raise GitRepositoryError("GIT_TARGET_NAMESPACE_DENIED")
    return target


def _validate_private_directory(path: Path, code: str) -> Path:
    if not isinstance(path, Path) or not path.is_absolute():
        raise GitRepositoryError(code)
    try:
        metadata = path.lstat()
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise GitRepositoryError(code) from error
    if (
        resolved != path
        or stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
    ):
        raise GitRepositoryError(code)
    return path


def _create_deterministic_commit(
    runner: _GitRunner,
    *,
    workspace: Path,
    base_head: str,
    changed_paths: tuple[str, ...],
    operation_id: str,
    timestamp: datetime,
) -> GitCommitIdentity:
    base = _validate_sha(base_head)
    if not changed_paths or tuple(sorted(set(changed_paths))) != changed_paths:
        raise GitRepositoryError("GIT_CHANGED_PATH_SET_INVALID")
    runner.run(
        (
            "-C",
            workspace.as_posix(),
            "-c",
            "core.hooksPath=/dev/null",
            "add",
            "-A",
            "--",
            *changed_paths,
        ),
        cwd=workspace,
        failure_code="GIT_INDEX_MATERIALIZATION_FAILED",
    )
    staged = runner.run(
        ("-C", workspace.as_posix(), "diff", "--cached", "--name-only", "-z"),
        cwd=workspace,
        failure_code="GIT_INDEX_READ_FAILED",
    )
    assert staged is not None
    staged_paths = tuple(sorted(item for item in staged.split("\0") if item))
    if staged_paths != changed_paths:
        raise GitRepositoryError("GIT_STAGED_PATH_SET_MISMATCH")
    tree = runner.run(
        ("-C", workspace.as_posix(), "write-tree"),
        cwd=workspace,
        failure_code="GIT_TREE_WRITE_FAILED",
    )
    assert tree is not None
    tree_sha = _validate_sha(tree.strip())
    message = f"aioa(w7a): apply verified patch {operation_id}"
    epoch = int(timestamp.timestamp())
    date = f"@{epoch} +0000"
    environment = {
        "GIT_AUTHOR_DATE": date,
        "GIT_AUTHOR_EMAIL": "w7a-actuator@aioa.invalid",
        "GIT_AUTHOR_NAME": "AIOA W7A Actuator",
        "GIT_COMMITTER_DATE": date,
        "GIT_COMMITTER_EMAIL": "w7a-actuator@aioa.invalid",
        "GIT_COMMITTER_NAME": "AIOA W7A Actuator",
    }
    commit = runner.run(
        (
            "-C",
            workspace.as_posix(),
            "-c",
            "commit.gpgsign=false",
            "commit-tree",
            tree_sha,
            "-p",
            base,
            "-m",
            message,
        ),
        cwd=workspace,
        failure_code="GIT_COMMIT_CREATE_FAILED",
        extra_environment=environment,
    )
    assert commit is not None
    return GitCommitIdentity(
        commit_sha=_validate_sha(commit.strip()),
        tree_sha=tree_sha,
        parent_sha=base,
        message_sha256=hashlib.sha256(message.encode("utf-8")).hexdigest(),
    )


def _prepare_commit_snapshot(
    runner: _GitRunner,
    *,
    source_workspace: Path,
    commit_sha: str,
    destination: Path,
) -> None:
    commit = _validate_sha(commit_sha)
    if destination.exists() or not destination.is_absolute():
        raise GitRepositoryError("GIT_COMMIT_SNAPSHOT_PATH_INVALID")
    runner.run(
        (
            "clone",
            "--no-checkout",
            "--no-hardlinks",
            "--no-tags",
            "--",
            source_workspace.as_posix(),
            destination.as_posix(),
        ),
        cwd=destination.parent,
        failure_code="GIT_COMMIT_SNAPSHOT_CLONE_FAILED",
    )
    runner.run(
        (
            "-C",
            destination.as_posix(),
            "-c",
            "core.hooksPath=/dev/null",
            "checkout",
            "--detach",
            "--no-recurse-submodules",
            commit,
        ),
        cwd=destination,
        failure_code="GIT_COMMIT_SNAPSHOT_CHECKOUT_FAILED",
    )


class LocalBareGitRepositoryService:
    """Local bare-remote proof adapter; it performs no network operation."""

    def __init__(self, remote_path: Path, identity: ExecutionRepositoryIdentity) -> None:
        self._remote = _validate_private_directory(remote_path, "LOCAL_BARE_REMOTE_INVALID")
        self._identity = identity
        self._runner = _GitRunner()

    @property
    def identity(self) -> ExecutionRepositoryIdentity:
        return self._identity

    @property
    def requires_write_credential(self) -> bool:
        return False

    @property
    def child_environment_names(self) -> tuple[str, ...]:
        return self._runner.last_environment_names

    def observe(self, *, base_ref: str, target_branch: str) -> GitRemoteObservation:
        base = normalize_branch(base_ref)
        target = _validate_target(target_branch)
        default = self._runner.run(
            ("--git-dir", self._remote.as_posix(), "symbolic-ref", "--short", "HEAD"),
            cwd=self._remote,
            failure_code="GIT_DEFAULT_BRANCH_READ_FAILED",
        )
        base_head = self._runner.run(
            (
                "--git-dir",
                self._remote.as_posix(),
                "rev-parse",
                "--verify",
                f"refs/heads/{base}^{{commit}}",
            ),
            cwd=self._remote,
            failure_code="GIT_BASE_REF_READ_FAILED",
        )
        target_head = self._runner.run(
            (
                "--git-dir",
                self._remote.as_posix(),
                "rev-parse",
                "--verify",
                f"refs/heads/{target}^{{commit}}",
            ),
            cwd=self._remote,
            failure_code="GIT_TARGET_REF_READ_FAILED",
            allow_failure=True,
        )
        assert default is not None and base_head is not None
        return _observation(
            repository=self._identity,
            default_branch=normalize_branch(default.strip()),
            base_ref=base,
            base_head=_validate_sha(base_head.strip()),
            target_branch=target,
            target_head=None if target_head is None else _validate_sha(target_head.strip()),
        )

    def prepare_exact_base(self, *, base_head: str, destination: Path) -> None:
        base = _validate_sha(base_head)
        if destination.exists() or not destination.is_absolute():
            raise GitRepositoryError("GIT_DISPOSABLE_WORKSPACE_INVALID")
        self._runner.run(
            ("clone", "--no-checkout", "--no-tags", "--", self._remote.as_posix(), destination.as_posix()),
            cwd=destination.parent,
            failure_code="GIT_BASE_CLONE_FAILED",
        )
        self._runner.run(
            (
                "-C",
                destination.as_posix(),
                "-c",
                "core.hooksPath=/dev/null",
                "checkout",
                "--detach",
                "--no-recurse-submodules",
                base,
            ),
            cwd=destination,
            failure_code="GIT_BASE_CHECKOUT_FAILED",
        )
        observed = self._runner.run(
            ("-C", destination.as_posix(), "rev-parse", "HEAD"),
            cwd=destination,
            failure_code="GIT_BASE_IDENTITY_FAILED",
        )
        if observed is None or observed.strip() != base:
            raise GitRepositoryError("GIT_BASE_IDENTITY_MISMATCH")

    def push_feature_ref_once(
        self,
        *,
        workspace: Path,
        commit_sha: str,
        target_branch: str,
        credential: GitHubWriteCredential | None,
    ) -> GitPushAcknowledgement:
        del credential
        commit = _validate_sha(commit_sha)
        target = _validate_target(target_branch)
        self._runner.run(
            (
                "-C",
                workspace.as_posix(),
                "-c",
                "core.hooksPath=/dev/null",
                "push",
                "--porcelain",
                "origin",
                f"{commit}:refs/heads/{target}",
            ),
            cwd=workspace,
            failure_code="GIT_REMOTE_WRITE_FAILED",
            write_boundary=True,
        )
        return GitPushAcknowledgement.ACKNOWLEDGED

    def create_deterministic_commit(
        self,
        *,
        workspace: Path,
        base_head: str,
        changed_paths: tuple[str, ...],
        operation_id: str,
        timestamp: datetime,
    ) -> GitCommitIdentity:
        return _create_deterministic_commit(
            self._runner,
            workspace=workspace,
            base_head=base_head,
            changed_paths=changed_paths,
            operation_id=operation_id,
            timestamp=timestamp,
        )

    def prepare_commit_snapshot(
        self,
        *,
        source_workspace: Path,
        commit_sha: str,
        destination: Path,
    ) -> None:
        _prepare_commit_snapshot(
            self._runner,
            source_workspace=source_workspace,
            commit_sha=commit_sha,
            destination=destination,
        )

    def readback_feature_ref(self, *, target_branch: str) -> GitRemoteCommitReadback | None:
        target = _validate_target(target_branch)
        commit = self._runner.run(
            (
                "--git-dir",
                self._remote.as_posix(),
                "rev-parse",
                "--verify",
                f"refs/heads/{target}^{{commit}}",
            ),
            cwd=self._remote,
            failure_code="GIT_REMOTE_READBACK_FAILED",
            allow_failure=True,
        )
        if commit is None:
            return None
        commit_sha = _validate_sha(commit.strip())
        tree = self._runner.run(
            (
                "--git-dir",
                self._remote.as_posix(),
                "rev-parse",
                f"{commit_sha}^{{tree}}",
            ),
            cwd=self._remote,
            failure_code="GIT_REMOTE_TREE_READBACK_FAILED",
        )
        assert tree is not None
        return GitRemoteCommitReadback(
            target_branch=target,
            commit_sha=commit_sha,
            tree_sha=_validate_sha(tree.strip()),
            observed_at=datetime.now(UTC),
        )


class GitHubHttpsRepositoryService:
    """Canonical GitHub HTTPS adapter; only its push method accepts write authority."""

    def __init__(self, identity: ExecutionRepositoryIdentity) -> None:
        self._identity = identity
        self._runner = _GitRunner()

    @property
    def identity(self) -> ExecutionRepositoryIdentity:
        return self._identity

    @property
    def requires_write_credential(self) -> bool:
        return True

    @property
    def child_environment_names(self) -> tuple[str, ...]:
        return self._runner.last_environment_names

    def _url(self) -> str:
        return f"{self._identity.canonical_url}.git"

    def observe(self, *, base_ref: str, target_branch: str) -> GitRemoteObservation:
        base = normalize_branch(base_ref)
        target = _validate_target(target_branch)
        output = self._runner.run(
            (
                "ls-remote",
                "--symref",
                self._url(),
                "HEAD",
                f"refs/heads/{base}",
                f"refs/heads/{target}",
            ),
            cwd=Path("/tmp"),
            failure_code="GITHUB_PRECONDITION_READ_FAILED",
        )
        assert output is not None
        default: str | None = None
        refs: dict[str, str] = {}
        for line in output.splitlines():
            left, separator, right = line.partition("\t")
            if separator != "\t":
                raise GitRepositoryError("GITHUB_PRECONDITION_FORMAT_INVALID")
            if left.startswith("ref: refs/heads/") and right == "HEAD":
                default = left.removeprefix("ref: refs/heads/")
            elif right.startswith("refs/heads/"):
                refs[right.removeprefix("refs/heads/")] = _validate_sha(left)
        if default is None or base not in refs:
            raise GitRepositoryError("GITHUB_PRECONDITION_INCOMPLETE")
        return _observation(
            repository=self._identity,
            default_branch=normalize_branch(default),
            base_ref=base,
            base_head=refs[base],
            target_branch=target,
            target_head=refs.get(target),
        )

    def prepare_exact_base(self, *, base_head: str, destination: Path) -> None:
        base = _validate_sha(base_head)
        if destination.exists() or not destination.is_absolute():
            raise GitRepositoryError("GIT_DISPOSABLE_WORKSPACE_INVALID")
        self._runner.run(
            ("clone", "--no-checkout", "--no-tags", "--", self._url(), destination.as_posix()),
            cwd=destination.parent,
            failure_code="GITHUB_BASE_CLONE_FAILED",
        )
        self._runner.run(
            (
                "-C",
                destination.as_posix(),
                "-c",
                "core.hooksPath=/dev/null",
                "checkout",
                "--detach",
                "--no-recurse-submodules",
                base,
            ),
            cwd=destination,
            failure_code="GITHUB_BASE_CHECKOUT_FAILED",
        )

    def push_feature_ref_once(
        self,
        *,
        workspace: Path,
        commit_sha: str,
        target_branch: str,
        credential: GitHubWriteCredential | None,
    ) -> GitPushAcknowledgement:
        if not isinstance(credential, GitHubWriteCredential):
            raise GitRepositoryError("GITHUB_WRITE_CREDENTIAL_REQUIRED")
        commit = _validate_sha(commit_sha)
        target = _validate_target(target_branch)
        environment = credential._git_environment()
        try:
            self._runner.run(
                (
                    "-C",
                    workspace.as_posix(),
                    "-c",
                    "core.hooksPath=/dev/null",
                    "push",
                    "--porcelain",
                    self._url(),
                    f"{commit}:refs/heads/{target}",
                ),
                cwd=workspace,
                failure_code="GITHUB_REMOTE_WRITE_FAILED",
                extra_environment=environment,
                write_boundary=True,
            )
        finally:
            credential.destroy()
        return GitPushAcknowledgement.ACKNOWLEDGED

    def create_deterministic_commit(
        self,
        *,
        workspace: Path,
        base_head: str,
        changed_paths: tuple[str, ...],
        operation_id: str,
        timestamp: datetime,
    ) -> GitCommitIdentity:
        return _create_deterministic_commit(
            self._runner,
            workspace=workspace,
            base_head=base_head,
            changed_paths=changed_paths,
            operation_id=operation_id,
            timestamp=timestamp,
        )

    def prepare_commit_snapshot(
        self,
        *,
        source_workspace: Path,
        commit_sha: str,
        destination: Path,
    ) -> None:
        _prepare_commit_snapshot(
            self._runner,
            source_workspace=source_workspace,
            commit_sha=commit_sha,
            destination=destination,
        )

    def readback_feature_ref(self, *, target_branch: str) -> GitRemoteCommitReadback | None:
        target = _validate_target(target_branch)
        output = self._runner.run(
            ("ls-remote", self._url(), f"refs/heads/{target}"),
            cwd=Path("/tmp"),
            failure_code="GITHUB_REMOTE_READBACK_FAILED",
        )
        assert output is not None
        if not output.strip():
            return None
        commit_sha = _validate_sha(output.split("\t", maxsplit=1)[0])
        with tempfile.TemporaryDirectory(prefix="aioa-github-readback-") as temporary:
            root = Path(temporary).resolve()
            root.chmod(0o700)
            self._runner.run(
                ("init", "--bare", root.as_posix()),
                cwd=root.parent,
                failure_code="GITHUB_READBACK_INIT_FAILED",
            )
            self._runner.run(
                ("--git-dir", root.as_posix(), "fetch", "--no-tags", "--depth=1", self._url(), commit_sha),
                cwd=root,
                failure_code="GITHUB_REMOTE_COMMIT_READ_FAILED",
            )
            tree = self._runner.run(
                ("--git-dir", root.as_posix(), "rev-parse", f"{commit_sha}^{{tree}}"),
                cwd=root,
                failure_code="GITHUB_REMOTE_TREE_READBACK_FAILED",
            )
        assert tree is not None
        return GitRemoteCommitReadback(
            target_branch=target,
            commit_sha=commit_sha,
            tree_sha=_validate_sha(tree.strip()),
            observed_at=datetime.now(UTC),
        )
