"""Official GitHub MCP v1.0.5 read-only context plane."""

from __future__ import annotations

import hashlib
import json
import os
import queue
import signal
import stat
import tempfile
import threading
from collections.abc import Callable, Mapping
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol, cast

from pydantic import Field, SecretStr, ValidationError, field_validator

from aioa_cloudops_agent.agent.codex_app_server import JsonlFramer
from aioa_cloudops_agent.agent.owned_process import OwnedProcess, OwnedProcessTimeout
from aioa_cloudops_agent.nz import (
    ControlResult,
    FailureDetail,
    FailureKind,
    generate_event_id,
)
from aioa_cloudops_agent.nz.contracts import NonZeroContract
from aioa_cloudops_agent.nz.redaction import redact_sensitive_text

from .contracts import (
    ActionsContext,
    ActionsContextPage,
    GitHubObservation,
    GitHubRepositoryIdentity,
    GitHubToolDescriptor,
    GitHubToolInventory,
    GitHubVisibility,
    IssueContext,
    IssueContextPage,
    PullRequestContext,
    PullRequestContextPage,
    RepoContext,
)

GITHUB_MCP_VERSION = "1.0.5"
GITHUB_MCP_COMMIT = "c471ae94bb04059dc26e12c305e219c8fd4299e4"
GITHUB_MCP_PROTOCOL_VERSION = "2025-06-18"
GITHUB_MCP_LINUX_X86_64_ARCHIVE_SHA256 = (
    "201082f569a846eaefd4318f13bccb5d9227c2cec45037d1d292ee83111173c1"
)
GITHUB_MCP_LINUX_X86_64_BINARY_SHA256 = (
    "e38247271e98ea3e0771db747523914b35e37787fa2c120ab6864ee6b4a2c87c"
)
GITHUB_MCP_TOOLSETS = ("repos", "issues", "pull_requests", "actions")

_WRITE_PREFIXES = (
    "add_",
    "assign_",
    "cancel_",
    "create_",
    "delete_",
    "dismiss_",
    "fork_",
    "lock_",
    "manage_",
    "mark_",
    "merge_",
    "push_",
    "remove_",
    "request_",
    "rerun_",
    "run_workflow",
    "submit_",
    "trigger_",
    "unlock_",
    "update_",
)
_WRITE_NAMES = frozenset(
    {
        "create_or_update_file",
        "push_files",
        "resolve_review_thread",
        "unresolve_review_thread",
    }
)
_TRANSPORT_ENV_ALLOWLIST = frozenset(
    {
        "HTTPS_PROXY",
        "HTTP_PROXY",
        "NO_PROXY",
        "PATH",
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
        "https_proxy",
        "http_proxy",
        "no_proxy",
    }
)


class GitHubMcpError(RuntimeError):
    """Base stable failure at the GitHub MCP read boundary."""


class GitHubMcpProtocolError(GitHubMcpError):
    """Malformed, unsupported, or write-capable MCP behavior."""


class GitHubMcpTimeout(GitHubMcpError):
    """One MCP request exceeded its bounded deadline."""


class GitHubMcpUnavailable(GitHubMcpError):
    """The pinned official MCP process or credential is unavailable."""


class GitHubMcpConfig(NonZeroContract):
    """Pinned server and exact authorized repository for one read plane."""

    binary_path: str = Field(min_length=1, max_length=4096)
    binary_sha256: str = GITHUB_MCP_LINUX_X86_64_BINARY_SHA256
    server_version: str = GITHUB_MCP_VERSION
    server_commit: str = GITHUB_MCP_COMMIT
    protocol_version: str = GITHUB_MCP_PROTOCOL_VERSION
    toolsets: tuple[
        Literal["repos"],
        Literal["issues"],
        Literal["pull_requests"],
        Literal["actions"],
    ] = (
        "repos",
        "issues",
        "pull_requests",
        "actions",
    )
    repository: GitHubRepositoryIdentity
    request_timeout_seconds: float = Field(default=20.0, gt=0, le=120)
    shutdown_timeout_seconds: float = Field(default=3.0, gt=0, le=10)
    max_message_bytes: int = Field(default=1024 * 1024, ge=4096, le=4 * 1024 * 1024)
    max_diagnostic_bytes: int = Field(default=32 * 1024, ge=1024, le=128 * 1024)
    read_only: bool = True
    lockdown_mode: bool = True

    @field_validator("binary_path")
    @classmethod
    def validate_binary_path(cls, value: str) -> str:
        path = Path(value)
        if not path.is_absolute() or path.as_posix() != value:
            raise ValueError("GitHub MCP binary_path must be absolute and canonical")
        return value

    @field_validator("binary_sha256")
    @classmethod
    def validate_binary_sha256(cls, value: str) -> str:
        if value != GITHUB_MCP_LINUX_X86_64_BINARY_SHA256:
            raise ValueError("GitHub MCP executable digest is not the reviewed v1.0.5 binary")
        return value

    @field_validator("server_version")
    @classmethod
    def validate_server_version(cls, value: str) -> str:
        if value != GITHUB_MCP_VERSION:
            raise ValueError("GitHub MCP version is not reviewed")
        return value

    @field_validator("server_commit")
    @classmethod
    def validate_server_commit(cls, value: str) -> str:
        if value != GITHUB_MCP_COMMIT:
            raise ValueError("GitHub MCP commit is not reviewed")
        return value

    @field_validator("protocol_version")
    @classmethod
    def validate_protocol_version(cls, value: str) -> str:
        if value != GITHUB_MCP_PROTOCOL_VERSION:
            raise ValueError("GitHub MCP protocol version is not reviewed")
        return value

    @field_validator("read_only", "lockdown_mode")
    @classmethod
    def require_security_modes(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("GitHub MCP read-only and lockdown modes are mandatory")
        return value


class McpTransport(Protocol):
    """Minimal transport implemented by the pinned stdio server and test fakes."""

    def start(self) -> None: ...

    def request(self, method: str, params: dict[str, object], *, timeout: float) -> object: ...

    def notify(self, method: str, params: dict[str, object] | None = None) -> None: ...

    def diagnostics(self) -> str: ...

    def close(self) -> None: ...


class GitHubMcpStdioTransport:
    """Credential-custody boundary for the official local GitHub MCP server."""

    def __init__(self, config: GitHubMcpConfig, credential: SecretStr) -> None:
        if not isinstance(credential, SecretStr) or len(credential.get_secret_value()) < 8:
            raise ValueError("GitHub MCP credential is unavailable")
        self._config = config
        self._credential = credential
        self._process: OwnedProcess | None = None
        self._temporary: tempfile.TemporaryDirectory[str] | None = None
        self._framer = JsonlFramer(max_message_bytes=config.max_message_bytes)
        self._pending: dict[int, queue.Queue[dict[str, object]]] = {}
        self._pending_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._diagnostic_lock = threading.Lock()
        self._diagnostic_bytes = bytearray()
        self._fatal: GitHubMcpError | None = None
        self._next_request_id = 1
        self._threads: tuple[threading.Thread, ...] = ()
        self._closed = False
        self._notification_count = 0

    @property
    def argv(self) -> tuple[str, ...]:
        return (
            self._config.binary_path,
            "stdio",
            "--read-only",
            "--toolsets=repos,issues,pull_requests,actions",
            "--lockdown-mode",
            "--content-window-size=5000",
        )

    @property
    def child_environment_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._child_environment()))

    def start(self) -> None:
        if self._process is not None or self._closed:
            raise RuntimeError("GitHub MCP transport cannot start twice")
        binary = _validated_binary(self._config)
        self._temporary = tempfile.TemporaryDirectory(prefix="aioa-github-mcp-")
        root = Path(self._temporary.name).resolve()
        root.chmod(0o700)
        try:
            self._process = OwnedProcess.spawn(
                (binary.as_posix(), *self.argv[1:]),
                cwd=root,
                environment=self._child_environment(),
            )
        except OSError as error:
            self._temporary.cleanup()
            self._temporary = None
            raise GitHubMcpUnavailable("GITHUB_MCP_START_FAILED") from error
        stdout_thread = threading.Thread(
            target=self._read_stdout,
            name=f"aioa-github-mcp-stdout-{self._process.pid}",
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=self._read_stderr,
            name=f"aioa-github-mcp-stderr-{self._process.pid}",
            daemon=True,
        )
        self._threads = (stdout_thread, stderr_thread)
        for thread in self._threads:
            thread.start()

    def request(self, method: str, params: dict[str, object], *, timeout: float) -> object:
        if timeout <= 0:
            raise ValueError("GitHub MCP request timeout must be positive")
        with self._pending_lock:
            request_id = self._next_request_id
            self._next_request_id += 1
            response_queue: queue.Queue[dict[str, object]] = queue.Queue(maxsize=1)
            self._pending[request_id] = response_queue
        try:
            self._write(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": method,
                    "params": params,
                }
            )
            try:
                response = response_queue.get(timeout=timeout)
            except queue.Empty as error:
                if self._fatal is not None:
                    raise self._fatal from error
                if self._process is not None and self._process.poll() is not None:
                    raise GitHubMcpUnavailable("GITHUB_MCP_EXITED_DURING_REQUEST") from error
                raise GitHubMcpTimeout("GITHUB_MCP_REQUEST_TIMEOUT") from error
        finally:
            with self._pending_lock:
                self._pending.pop(request_id, None)
        if "error" in response:
            raise GitHubMcpProtocolError("GITHUB_MCP_JSONRPC_ERROR")
        if "result" not in response:
            raise GitHubMcpProtocolError("GITHUB_MCP_RESULT_MISSING")
        return response["result"]

    def notify(self, method: str, params: dict[str, object] | None = None) -> None:
        message: dict[str, object] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        self._write(message)

    def diagnostics(self) -> str:
        with self._diagnostic_lock:
            decoded = bytes(self._diagnostic_bytes).decode("utf-8", errors="replace")
        return redact_sensitive_text(decoded)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        process = self._process
        if process is not None:
            with suppress(OSError, ValueError):
                process.stdin.close()
            if process.poll() is None:
                self._signal_owned(signal.SIGTERM)
                try:
                    process.wait(timeout=self._config.shutdown_timeout_seconds)
                except OwnedProcessTimeout:
                    self._signal_owned(signal.SIGKILL)
                    with suppress(OwnedProcessTimeout):
                        process.wait(timeout=self._config.shutdown_timeout_seconds)
            for thread in self._threads:
                if thread is not threading.current_thread():
                    thread.join(timeout=self._config.shutdown_timeout_seconds)
        if self._temporary is not None:
            self._temporary.cleanup()
            self._temporary = None
        self._credential = SecretStr("destroyed")

    def _child_environment(self) -> dict[str, str]:
        environment = {
            key: value for key, value in os.environ.items() if key in _TRANSPORT_ENV_ALLOWLIST
        }
        environment.update(
            {
                "GITHUB_LOCKDOWN_MODE": "1",
                "GITHUB_MCP_SERVER_NAME": "github-mcp-server",
                "GITHUB_PERSONAL_ACCESS_TOKEN": self._credential.get_secret_value(),
                "GITHUB_READ_ONLY": "1",
                "GITHUB_TOOLSETS": "repos,issues,pull_requests,actions",
            }
        )
        return environment

    def _write(self, payload: dict[str, object]) -> None:
        process = self._process
        if process is None or process.poll() is not None:
            raise GitHubMcpUnavailable("GITHUB_MCP_NOT_RUNNING")
        encoded = _canonical_json(payload).encode("utf-8") + b"\n"
        with self._write_lock:
            try:
                process.stdin.write(encoded)
                process.stdin.flush()
            except (BrokenPipeError, OSError) as error:
                raise GitHubMcpUnavailable("GITHUB_MCP_STDIN_CLOSED") from error

    def _read_stdout(self) -> None:
        assert self._process is not None
        try:
            while chunk := self._process.stdout.read(4096):
                for message in self._framer.feed(chunk):
                    self._dispatch(message)
            self._framer.finish()
        except Exception as error:
            self._fatal = GitHubMcpProtocolError("GITHUB_MCP_PROTOCOL_STREAM_FAILED")
            del error

    def _dispatch(self, message: dict[str, object]) -> None:
        response_id = message.get("id")
        if response_id is not None and "method" not in message:
            if not isinstance(response_id, int):
                self._fatal = GitHubMcpProtocolError("GITHUB_MCP_RESPONSE_ID_INVALID")
                return
            with self._pending_lock:
                response_queue = self._pending.get(response_id)
            if response_queue is not None:
                with suppress(queue.Full):
                    response_queue.put_nowait(message)
            return
        if response_id is not None:
            self._fatal = GitHubMcpProtocolError("GITHUB_MCP_SERVER_REQUEST_DENIED")
            self._signal_owned(signal.SIGTERM)
            return
        self._notification_count += 1
        if self._notification_count > 128:
            self._fatal = GitHubMcpProtocolError("GITHUB_MCP_NOTIFICATION_LIMIT_EXCEEDED")
            self._signal_owned(signal.SIGTERM)

    def _read_stderr(self) -> None:
        assert self._process is not None
        while chunk := self._process.stderr.read(4096):
            with self._diagnostic_lock:
                remaining = self._config.max_diagnostic_bytes - len(self._diagnostic_bytes)
                if remaining > 0:
                    self._diagnostic_bytes.extend(chunk[:remaining])

    def _signal_owned(self, selected_signal: signal.Signals) -> None:
        process = self._process
        if process is None or process.poll() is not None:
            return
        try:
            if os.getpgid(process.pid) != process.pid:
                raise ProcessLookupError
            os.killpg(process.pid, selected_signal)
        except (OSError, ProcessLookupError):
            with suppress(OSError):
                process.send_signal(selected_signal)


RepoReadResult = ControlResult[RepoContext]
IssueReadResult = ControlResult[IssueContextPage]
PullRequestReadResult = ControlResult[PullRequestContextPage]
ActionsReadResult = ControlResult[ActionsContextPage]


class GitHubMcpReadPlane:
    """AIOA-owned normalizer over a server-enforced read-only MCP inventory."""

    def __init__(
        self,
        config: GitHubMcpConfig,
        transport: McpTransport,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._config = config
        self._transport = transport
        self._clock = clock or (lambda: datetime.now(UTC))
        self._inventory: GitHubToolInventory | None = None
        self._closed = False

    @property
    def inventory(self) -> GitHubToolInventory:
        if self._inventory is None:
            raise RuntimeError("GitHub MCP inventory is unavailable before start")
        return self._inventory

    def start(self) -> GitHubToolInventory:
        if self._inventory is not None or self._closed:
            raise RuntimeError("GitHub MCP read plane cannot start twice")
        self._transport.start()
        try:
            initialized = _mapping(
                self._transport.request(
                    "initialize",
                    {
                        "protocolVersion": self._config.protocol_version,
                        "capabilities": {},
                        "clientInfo": {
                            "name": "aioa-nonzero-cloudops-agent",
                            "version": "w7a-phase3",
                        },
                    },
                    timeout=self._config.request_timeout_seconds,
                ),
                "initialize result",
            )
            if initialized.get("protocolVersion") != self._config.protocol_version:
                raise GitHubMcpProtocolError("GITHUB_MCP_PROTOCOL_VERSION_MISMATCH")
            server = _mapping(initialized.get("serverInfo"), "server info")
            if (
                server.get("name") != "github-mcp-server"
                or server.get("version") != self._config.server_version
            ):
                raise GitHubMcpProtocolError("GITHUB_MCP_SERVER_IDENTITY_MISMATCH")
            self._transport.notify("notifications/initialized")
            tools = self._list_all_tools()
            descriptors = tuple(
                sorted((_tool_descriptor(item) for item in tools), key=lambda x: x.name)
            )
            forbidden = tuple(item.name for item in descriptors if _is_write_tool(item.name))
            if forbidden:
                raise GitHubMcpProtocolError("GITHUB_MCP_WRITE_TOOL_EXPOSED")
            inventory_material = {
                "protocol_version": self._config.protocol_version,
                "server_name": server["name"],
                "server_version": server["version"],
                "server_commit": self._config.server_commit,
                "toolsets": self._config.toolsets,
                "tools": [item.model_dump(mode="json") for item in descriptors],
                "read_only": True,
                "lockdown_mode": True,
                "runtime_write_tools": 0,
            }
            self._inventory = GitHubToolInventory(
                **inventory_material,
                inventory_sha256=_sha256_json(inventory_material),
            )
            return self._inventory
        except Exception:
            self._transport.close()
            raise

    def read_repository(self, requested_ref: str) -> RepoReadResult:
        try:
            self._require_started()
            repository_payload, _ = self._call(
                "search_repositories",
                {
                    "query": (
                        f"repo:{self._config.repository.owner}/{self._config.repository.name}"
                    ),
                    "minimal_output": False,
                    "perPage": 5,
                },
            )
            candidates = _items(repository_payload, ("items", "repositories"))
            expected_full_name = f"{self._config.repository.owner}/{self._config.repository.name}"
            repository = next(
                (
                    item
                    for item in candidates
                    if str(item.get("full_name", item.get("fullName", ""))).casefold()
                    == expected_full_name.casefold()
                ),
                None,
            )
            if repository is None:
                raise GitHubMcpProtocolError("GITHUB_REPOSITORY_IDENTITY_MISMATCH")
            branch_name = requested_ref.removeprefix("refs/heads/")
            branches_payload, _ = self._call(
                "list_branches",
                {
                    "owner": self._config.repository.owner,
                    "repo": self._config.repository.name,
                    "perPage": 100,
                },
            )
            branches = _items(branches_payload, ("branches", "items"))
            branch = next((item for item in branches if item.get("name") == branch_name), None)
            if branch is None:
                raise GitHubMcpProtocolError("GITHUB_REQUESTED_REF_NOT_FOUND")
            raw_commit = branch.get("commit")
            sha = (
                _mapping(raw_commit, "branch commit").get("sha")
                if raw_commit is not None
                else branch.get("sha")
            )
            default_branch = repository.get("default_branch", repository.get("defaultBranch"))
            if not isinstance(default_branch, str) or not isinstance(sha, str):
                raise GitHubMcpProtocolError("GITHUB_REPOSITORY_CONTEXT_INVALID")
            combined = {"repository": repository, "branch": branch}
            observation = self._observation(
                "list_branches",
                {"repository": expected_full_name, "requested_ref": requested_ref},
                combined,
            )
            context = RepoContext(
                repository=self._config.repository,
                default_branch=default_branch,
                requested_ref=requested_ref,
                observed_sha=sha.lower(),
                visibility=_visibility(repository),
                observation=observation,
            )
            return RepoReadResult.succeeded(context)
        except (GitHubMcpError, ValidationError, TypeError, ValueError):
            return RepoReadResult.failed(_read_failure("GITHUB_REPOSITORY_READ_FAILED"))

    def read_issues(self, *, per_page: int = 20) -> IssueReadResult:
        try:
            self._require_started()
            _bounded_page_size(per_page)
            payload, observation = self._call(
                "list_issues",
                {
                    "owner": self._config.repository.owner,
                    "repo": self._config.repository.name,
                    "perPage": per_page,
                },
            )
            contexts: list[IssueContext] = []
            truncated = False
            for item in _items(payload, ("issues", "items")):
                title, title_cut = _bounded_text(item.get("title", ""), 512)
                body, body_cut = _bounded_text(item.get("body", ""), 64 * 1024)
                truncated = truncated or title_cut or body_cut
                state = str(item.get("state", "")).upper()
                if state not in {"OPEN", "CLOSED"}:
                    raise GitHubMcpProtocolError("GITHUB_ISSUE_STATE_INVALID")
                contexts.append(
                    IssueContext(
                        repository=self._config.repository,
                        number=_positive_int(item.get("number"), "issue number"),
                        title=title,
                        body=body,
                        state=cast("str", state),
                        labels=_labels(item.get("labels", [])),
                        author=_author(item),
                        url=_url(item),
                        observation=observation,
                    )
                )
            if truncated:
                observation = observation.model_copy(update={"truncated": True})
                contexts = [
                    item.model_copy(update={"observation": observation}) for item in contexts
                ]
            return IssueReadResult.succeeded(
                IssueContextPage(
                    repository=self._config.repository,
                    issues=tuple(contexts),
                    observation=observation,
                )
            )
        except (GitHubMcpError, ValidationError, TypeError, ValueError):
            return IssueReadResult.failed(_read_failure("GITHUB_ISSUE_READ_FAILED"))

    def read_pull_requests(self, *, per_page: int = 20) -> PullRequestReadResult:
        try:
            self._require_started()
            _bounded_page_size(per_page)
            payload, observation = self._call(
                "list_pull_requests",
                {
                    "owner": self._config.repository.owner,
                    "repo": self._config.repository.name,
                    "state": "all",
                    "perPage": per_page,
                },
            )
            contexts: list[PullRequestContext] = []
            truncated = False
            for item in _items(payload, ("pull_requests", "pullRequests", "items")):
                base = _mapping(item.get("base"), "pull request base")
                head = _mapping(item.get("head"), "pull request head")
                title, title_cut = _bounded_text(item.get("title", ""), 512)
                body, body_cut = _bounded_text(item.get("body", ""), 64 * 1024)
                truncated = truncated or title_cut or body_cut
                state = (
                    "MERGED"
                    if item.get("merged_at") or item.get("merged") is True
                    else str(item.get("state", "")).upper()
                )
                if state not in {"OPEN", "CLOSED", "MERGED"}:
                    raise GitHubMcpProtocolError("GITHUB_PULL_REQUEST_STATE_INVALID")
                contexts.append(
                    PullRequestContext(
                        repository=self._config.repository,
                        number=_positive_int(item.get("number"), "pull request number"),
                        title=title,
                        body=body,
                        state=cast("str", state),
                        base_ref=str(base.get("ref", "")),
                        base_sha=str(base.get("sha", "")).lower(),
                        head_ref=str(head.get("ref", "")),
                        head_sha=str(head.get("sha", "")).lower(),
                        changed_files=_optional_nonnegative_int(item.get("changed_files")),
                        commits=_optional_nonnegative_int(item.get("commits")),
                        checks_summary="",
                        url=_url(item),
                        observation=observation,
                    )
                )
            if truncated:
                observation = observation.model_copy(update={"truncated": True})
                contexts = [
                    item.model_copy(update={"observation": observation}) for item in contexts
                ]
            return PullRequestReadResult.succeeded(
                PullRequestContextPage(
                    repository=self._config.repository,
                    pull_requests=tuple(contexts),
                    observation=observation,
                )
            )
        except (GitHubMcpError, ValidationError, TypeError, ValueError):
            return PullRequestReadResult.failed(_read_failure("GITHUB_PULL_REQUEST_READ_FAILED"))

    def read_actions(self, *, per_page: int = 20) -> ActionsReadResult:
        try:
            self._require_started()
            _bounded_page_size(per_page)
            payload, observation = self._call(
                "actions_list",
                {
                    "method": "list_workflow_runs",
                    "owner": self._config.repository.owner,
                    "repo": self._config.repository.name,
                    "per_page": per_page,
                },
            )
            contexts: list[ActionsContext] = []
            for item in _items(payload, ("workflow_runs", "workflowRuns", "items")):
                contexts.append(
                    ActionsContext(
                        repository=self._config.repository,
                        workflow_id=_optional_identifier(item.get("workflow_id")),
                        run_id=_optional_positive_int(item.get("id")),
                        name=_bounded_text(item.get("name", item.get("display_title", "")), 512)[0],
                        status=str(item.get("status", "UNKNOWN"))[:64],
                        conclusion=_optional_text(item.get("conclusion"), 64),
                        head_branch=_optional_text(item.get("head_branch"), 256),
                        head_sha=_optional_text(item.get("head_sha"), 40),
                        url=_optional_text(
                            item.get("html_url", item.get("url")),
                            2048,
                        ),
                        observation=observation,
                    )
                )
            return ActionsReadResult.succeeded(
                ActionsContextPage(
                    repository=self._config.repository,
                    actions=tuple(contexts),
                    observation=observation,
                )
            )
        except (GitHubMcpError, ValidationError, TypeError, ValueError):
            return ActionsReadResult.failed(_read_failure("GITHUB_ACTIONS_READ_FAILED"))

    def assert_read_tool(self, name: str) -> None:
        """Fail closed before transport if a caller asks for an unlisted/write tool."""

        names = {item.name for item in self.inventory.tools}
        if name not in names or _is_write_tool(name):
            raise GitHubMcpProtocolError("GITHUB_MCP_TOOL_NOT_READ_AUTHORIZED")

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._transport.close()

    def _list_all_tools(self) -> tuple[Mapping[str, object], ...]:
        tools: list[Mapping[str, object]] = []
        cursor: str | None = None
        for _ in range(10):
            params: dict[str, object] = {}
            if cursor is not None:
                params["cursor"] = cursor
            result = _mapping(
                self._transport.request(
                    "tools/list",
                    params,
                    timeout=self._config.request_timeout_seconds,
                ),
                "tools/list result",
            )
            raw_tools = result.get("tools")
            if not isinstance(raw_tools, list):
                raise GitHubMcpProtocolError("GITHUB_MCP_TOOL_LIST_INVALID")
            tools.extend(_mapping(item, "tool descriptor") for item in raw_tools)
            next_cursor = result.get("nextCursor")
            if next_cursor is None:
                return tuple(tools)
            if not isinstance(next_cursor, str) or not next_cursor:
                raise GitHubMcpProtocolError("GITHUB_MCP_CURSOR_INVALID")
            cursor = next_cursor
        raise GitHubMcpProtocolError("GITHUB_MCP_TOOL_PAGINATION_LIMIT")

    def _call(
        self,
        tool: str,
        arguments: dict[str, object],
    ) -> tuple[object, GitHubObservation]:
        self.assert_read_tool(tool)
        _validate_repository_arguments(arguments, self._config.repository)
        result = _mapping(
            self._transport.request(
                "tools/call",
                {"name": tool, "arguments": arguments},
                timeout=self._config.request_timeout_seconds,
            ),
            "tools/call result",
        )
        if result.get("isError") is True:
            raise GitHubMcpProtocolError("GITHUB_MCP_TOOL_READ_FAILED")
        payload = _extract_mcp_payload(result, self._config.max_message_bytes)
        return payload, self._observation(tool, arguments, payload)

    def _observation(
        self,
        tool: str,
        arguments: object,
        payload: object,
    ) -> GitHubObservation:
        request_digest = _sha256_json(arguments)
        content_digest = _sha256_json(payload)
        evidence_key = _sha256_json(
            {"source_tool": tool, "request": request_digest, "content": content_digest}
        )
        return GitHubObservation(
            observation_id=generate_event_id(),
            source_tool=tool,
            request_sha256=request_digest,
            content_sha256=content_digest,
            evidence_key=evidence_key,
            observed_at=self._clock(),
        )

    def _require_started(self) -> None:
        if self._inventory is None or self._closed:
            raise GitHubMcpUnavailable("GITHUB_MCP_READ_PLANE_NOT_STARTED")


def _validated_binary(config: GitHubMcpConfig) -> Path:
    path = Path(config.binary_path)
    try:
        metadata = path.lstat()
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise GitHubMcpUnavailable("GITHUB_MCP_BINARY_UNAVAILABLE") from error
    if resolved != path or stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise GitHubMcpUnavailable("GITHUB_MCP_BINARY_TYPE_INVALID")
    if metadata.st_uid != os.getuid() or not os.access(path, os.X_OK):
        raise GitHubMcpUnavailable("GITHUB_MCP_BINARY_AUTHORITY_INVALID")
    if hashlib.sha256(path.read_bytes()).hexdigest() != config.binary_sha256:
        raise GitHubMcpUnavailable("GITHUB_MCP_BINARY_DIGEST_MISMATCH")
    return path


def _tool_descriptor(raw: Mapping[str, object]) -> GitHubToolDescriptor:
    name = raw.get("name")
    annotations = _mapping(raw.get("annotations", {}), "tool annotations")
    if not isinstance(name, str) or annotations.get("readOnlyHint") is not True:
        raise GitHubMcpProtocolError("GITHUB_MCP_TOOL_NOT_READ_ONLY")
    return GitHubToolDescriptor(
        name=name,
        schema_sha256=_sha256_json(raw.get("inputSchema", {})),
        description_sha256=_sha256_json(str(raw.get("description", ""))),
    )


def _is_write_tool(name: str) -> bool:
    lowered = name.casefold()
    return lowered in _WRITE_NAMES or lowered.startswith(_WRITE_PREFIXES)


def _extract_mcp_payload(result: Mapping[str, object], max_bytes: int) -> object:
    structured = result.get("structuredContent")
    if structured not in (None, {}):
        if len(_canonical_json(structured).encode("utf-8")) > max_bytes:
            raise GitHubMcpProtocolError("GITHUB_MCP_RESPONSE_TOO_LARGE")
        return structured
    content = result.get("content")
    if not isinstance(content, list) or not content:
        raise GitHubMcpProtocolError("GITHUB_MCP_RESPONSE_CONTENT_MISSING")
    fragments: list[str] = []
    size = 0
    for block in content:
        item = _mapping(block, "MCP content block")
        if item.get("type") != "text" or not isinstance(item.get("text"), str):
            raise GitHubMcpProtocolError("GITHUB_MCP_RESPONSE_CONTENT_INVALID")
        text = cast(str, item["text"])
        size += len(text.encode("utf-8"))
        if size > max_bytes:
            raise GitHubMcpProtocolError("GITHUB_MCP_RESPONSE_TOO_LARGE")
        fragments.append(text)
    try:
        return json.loads("".join(fragments))
    except json.JSONDecodeError as error:
        raise GitHubMcpProtocolError("GITHUB_MCP_RESPONSE_JSON_INVALID") from error


def _validate_repository_arguments(
    arguments: Mapping[str, object],
    repository: GitHubRepositoryIdentity,
) -> None:
    owner = arguments.get("owner")
    repo = arguments.get("repo")
    if owner is not None and owner != repository.owner:
        raise GitHubMcpProtocolError("GITHUB_MCP_CROSS_REPOSITORY_OWNER_DENIED")
    if repo is not None and repo != repository.name:
        raise GitHubMcpProtocolError("GITHUB_MCP_CROSS_REPOSITORY_NAME_DENIED")
    query = arguments.get("query")
    if query is not None:
        expected = f"repo:{repository.owner}/{repository.name}"
        if query != expected:
            raise GitHubMcpProtocolError("GITHUB_MCP_CROSS_REPOSITORY_QUERY_DENIED")


def _items(payload: object, keys: tuple[str, ...]) -> tuple[Mapping[str, object], ...]:
    current = payload
    if isinstance(current, dict) and "result" in current and len(current) == 1:
        current = current["result"]
    if isinstance(current, list):
        raw_items = current
    elif isinstance(current, dict):
        raw_items = next((current[key] for key in keys if isinstance(current.get(key), list)), [])
    else:
        raise GitHubMcpProtocolError("GITHUB_MCP_CONTEXT_PAYLOAD_INVALID")
    return tuple(_mapping(item, "GitHub context item") for item in raw_items)


def _visibility(item: Mapping[str, object]) -> GitHubVisibility:
    raw = str(item.get("visibility", "")).upper()
    if raw in {member.value for member in GitHubVisibility}:
        return GitHubVisibility(raw)
    if item.get("private") is True:
        return GitHubVisibility.PRIVATE
    if item.get("private") is False:
        return GitHubVisibility.PUBLIC
    return GitHubVisibility.UNKNOWN


def _labels(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise GitHubMcpProtocolError("GITHUB_ISSUE_LABELS_INVALID")
    labels: list[str] = []
    for raw in value:
        if isinstance(raw, str):
            label = raw
        elif isinstance(raw, dict) and isinstance(raw.get("name"), str):
            label = cast(str, raw["name"])
        else:
            raise GitHubMcpProtocolError("GITHUB_ISSUE_LABEL_INVALID")
        labels.append(label[:256])
    return tuple(sorted(set(labels)))


def _author(item: Mapping[str, object]) -> str | None:
    raw = item.get("user", item.get("author"))
    if raw is None:
        return None
    if isinstance(raw, str):
        return raw[:256]
    if isinstance(raw, dict):
        name = raw.get("login", raw.get("name"))
        return str(name)[:256] if name is not None else None
    raise GitHubMcpProtocolError("GITHUB_AUTHOR_INVALID")


def _url(item: Mapping[str, object]) -> str:
    value = item.get("html_url", item.get("url"))
    if not isinstance(value, str) or not value.startswith("https://github.com/"):
        raise GitHubMcpProtocolError("GITHUB_CONTEXT_URL_INVALID")
    return value[:2048]


def _bounded_text(value: object, limit: int) -> tuple[str, bool]:
    text = "" if value is None else str(value)
    encoded = text.encode("utf-8")
    if len(encoded) <= limit:
        return text, False
    truncated = encoded[:limit].decode("utf-8", errors="ignore")
    return truncated, True


def _positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise GitHubMcpProtocolError(f"{label} is invalid")
    return value


def _optional_positive_int(value: object) -> int | None:
    if value is None:
        return None
    return _positive_int(value, "optional identifier")


def _optional_nonnegative_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise GitHubMcpProtocolError("optional count is invalid")
    return value


def _optional_identifier(value: object) -> str | None:
    if value is None:
        return None
    rendered = str(value)
    if not rendered or len(rendered) > 256:
        raise GitHubMcpProtocolError("optional identifier is invalid")
    return rendered


def _optional_text(value: object, limit: int) -> str | None:
    if value is None:
        return None
    return _bounded_text(value, limit)[0]


def _bounded_page_size(value: int) -> None:
    if isinstance(value, bool) or not 1 <= value <= 100:
        raise ValueError("GitHub page size is outside the supported bound")


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise GitHubMcpProtocolError(f"{label} must be an object")
    return cast(Mapping[str, object], value)


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def _sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _read_failure(code: str) -> FailureDetail:
    return FailureDetail(
        kind=FailureKind.TOOL_ADAPTER_FAILURE,
        code=code,
        message="GitHub read context could not be proven.",
        retryable=True,
    )
