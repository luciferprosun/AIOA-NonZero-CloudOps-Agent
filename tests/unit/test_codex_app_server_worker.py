"""Phase 2 proofs for the bounded Codex App Server coding worker."""

from __future__ import annotations

import os
import queue
import sys
from collections.abc import Mapping
from pathlib import Path

import pytest
from pydantic import ValidationError

from aioa_cloudops_agent.agent import (
    AppServerCrash,
    AppServerProtocolError,
    AppServerTimeout,
    CodexAppServerWorker,
    JsonlFramer,
    SubprocessJsonRpcTransport,
    WorkerEventKind,
    WorkerTask,
    WorkerTerminalStatus,
    WorkerWorkspaceIdentity,
    digest_workspace_tree,
    sanitized_app_server_environment,
)
from aioa_cloudops_agent.nz import generate_event_id, generate_run_id

THREAD_ID = "019c0000-0000-7000-8000-abcdefabcdef"
TURN_ID = "019c0000-0000-7000-8000-fedcbafedcba"


class ScriptedTransport:
    """Protocol-accurate deterministic transport; it grants no process authority."""

    def __init__(
        self,
        messages: list[dict[str, object]] | None = None,
        *,
        initialize: object | None = None,
        crash: bool = False,
    ) -> None:
        self.messages: queue.Queue[dict[str, object]] = queue.Queue()
        for message in messages or []:
            self.messages.put(message)
        self.initialize = initialize or {
            "codexHome": "/private/codex",
            "platformFamily": "unix",
            "platformOs": "linux",
            "userAgent": "codex_cli_rs/0.151.0",
        }
        self.crash = crash
        self.started = False
        self.closed = False
        self.close_calls = 0
        self.requests: list[tuple[str, dict[str, object]]] = []
        self.notifications: list[tuple[str, dict[str, object] | None]] = []
        self.responses: list[tuple[object, object]] = []
        self.errors: list[tuple[object, int, str]] = []

    def start(self, *, cwd: Path, max_events: int) -> None:
        assert cwd.is_dir()
        assert 8 <= max_events <= 4096
        self.started = True

    def request(self, method: str, params: dict[str, object], *, timeout: float) -> object:
        assert timeout > 0
        self.requests.append((method, params))
        if method == "initialize":
            return self.initialize
        if method == "thread/start":
            return {"thread": {"id": THREAD_ID}}
        if method == "turn/start":
            return {"turn": {"id": TURN_ID}}
        if method == "turn/interrupt":
            return {}
        raise AssertionError(f"unexpected request: {method}")

    def notify(self, method: str, params: dict[str, object] | None = None) -> None:
        self.notifications.append((method, params))

    def next_message(self, *, timeout: float) -> dict[str, object]:
        if self.crash:
            raise AppServerCrash("fixture crash")
        try:
            return self.messages.get_nowait()
        except queue.Empty as error:
            raise AppServerTimeout("fixture timeout") from error

    def respond(self, request_id: object, result: object) -> None:
        self.responses.append((request_id, result))

    def respond_error(self, request_id: object, *, code: int, message: str) -> None:
        self.errors.append((request_id, code, message))

    def diagnostics(self) -> str:
        return ""

    def close(self) -> None:
        self.close_calls += 1
        self.closed = True


def _workspace(tmp_path: Path) -> Path:
    root = tmp_path.resolve() / "fixture"
    root.mkdir(mode=0o700, parents=True)
    (root / "app.py").write_text("VALUE = 'broken'\n", encoding="utf-8")
    (root / "test_app.py").write_text(
        "from app import VALUE\n\ndef test_value():\n    assert VALUE == 'fixed'\n",
        encoding="utf-8",
    )
    return root


def _task(
    root: Path,
    *,
    timeout_seconds: float = 2.0,
    max_events: int = 64,
) -> WorkerTask:
    return WorkerTask(
        run_id=generate_run_id(),
        task_id=generate_event_id(),
        workspace=WorkerWorkspaceIdentity(
            workspace_id=generate_event_id(),
            root_path=root.as_posix(),
            expected_base_digest=digest_workspace_tree(root),
        ),
        instruction=(
            "Change only app.py so the local test passes. Do not use network or paths outside "
            "this disposable workspace. Return the final diff and test result."
        ),
        timeout_seconds=timeout_seconds,
        max_events=max_events,
    )


def _success_messages(root: Path) -> list[dict[str, object]]:
    diff = (
        "diff --git a/app.py b/app.py\n"
        "--- a/app.py\n"
        "+++ b/app.py\n"
        "@@ -1 +1 @@\n"
        "-VALUE = 'broken'\n"
        "+VALUE = 'fixed'\n"
    )
    return [
        {
            "jsonrpc": "2.0",
            "method": "turn/started",
            "params": {"threadId": THREAD_ID, "turnId": TURN_ID},
        },
        {
            "jsonrpc": "2.0",
            "method": "item/completed",
            "params": {
                "threadId": THREAD_ID,
                "turnId": TURN_ID,
                "item": {
                    "id": "command-1",
                    "type": "commandExecution",
                    "command": "python -m pytest -q",
                    "status": "completed",
                    "exitCode": 0,
                    "aggregatedOutput": "1 passed",
                },
            },
        },
        {
            "jsonrpc": "2.0",
            "method": "item/completed",
            "params": {
                "threadId": THREAD_ID,
                "turnId": TURN_ID,
                "item": {
                    "id": "change-1",
                    "type": "fileChange",
                    "status": "completed",
                    "changes": [
                        {
                            "path": (root / "app.py").as_posix(),
                            "kind": "update",
                            "diff": diff,
                        }
                    ],
                },
            },
        },
        {
            "jsonrpc": "2.0",
            "method": "turn/diff/updated",
            "params": {"threadId": THREAD_ID, "turnId": TURN_ID, "diff": diff},
        },
        {
            "jsonrpc": "2.0",
            "method": "item/completed",
            "params": {
                "threadId": THREAD_ID,
                "turnId": TURN_ID,
                "item": {"id": "message-1", "type": "agentMessage", "text": "Test passed."},
            },
        },
        {
            "jsonrpc": "2.0",
            "method": "turn/completed",
            "params": {
                "threadId": THREAD_ID,
                "turn": {"id": TURN_ID, "status": "completed", "items": []},
            },
        },
    ]


def _run(
    task: WorkerTask,
    transport: ScriptedTransport,
) -> tuple[tuple[object, ...], object, CodexAppServerWorker]:
    worker = CodexAppServerWorker(transport)
    worker.start(task)
    handle = worker.send_task(task)
    events = tuple(worker.stream_events(handle))
    return events, worker.receive_result(handle), worker


def test_jsonl_framer_reassembles_partial_and_multiple_frames() -> None:
    framer = JsonlFramer(max_message_bytes=1024)
    assert framer.feed(b'{"jsonrpc":"2.0","id":') == ()
    messages = framer.feed(b'1,"result":{}}\n\n{"method":"turn/started"}\r\n')
    assert messages == (
        {"jsonrpc": "2.0", "id": 1, "result": {}},
        {"method": "turn/started"},
    )
    framer.finish()


@pytest.mark.parametrize(
    "payload,expected",
    [
        (b"not-json\n", "APP_SERVER_MALFORMED_JSON"),
        (b"[]\n", "APP_SERVER_MESSAGE_NOT_OBJECT"),
        (b'"text"\n', "APP_SERVER_MESSAGE_NOT_OBJECT"),
    ],
)
def test_jsonl_framer_rejects_malformed_or_nonobject_frames(
    payload: bytes,
    expected: str,
) -> None:
    framer = JsonlFramer(max_message_bytes=1024)
    with pytest.raises(AppServerProtocolError, match=expected):
        framer.feed(payload)


def test_jsonl_framer_rejects_oversized_and_truncated_frames() -> None:
    framer = JsonlFramer(max_message_bytes=1024)
    with pytest.raises(AppServerProtocolError, match="MESSAGE_TOO_LARGE"):
        framer.feed(b"x" * 1025)
    truncated = JsonlFramer(max_message_bytes=1024)
    truncated.feed(b'{"id":1}')
    with pytest.raises(AppServerProtocolError, match="TRUNCATED_FRAME"):
        truncated.finish()


def test_real_worker_contract_normalizes_events_diff_and_command(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    task = _task(root)
    transport = ScriptedTransport(_success_messages(root))
    events, result, worker = _run(task, transport)

    assert transport.started is True
    assert transport.notifications == [("initialized", None)]
    assert [request[0] for request in transport.requests] == [
        "initialize",
        "thread/start",
        "turn/start",
    ]
    thread_config = transport.requests[1][1]
    turn_config = transport.requests[2][1]
    assert thread_config["approvalPolicy"] == "never"
    assert thread_config["sandbox"] == "workspace-write"
    assert turn_config["sandboxPolicy"] == {
        "type": "workspaceWrite",
        "writableRoots": [root.as_posix()],
        "networkAccess": False,
        "excludeSlashTmp": True,
        "excludeTmpdirEnvVar": True,
    }
    assert result.status is WorkerTerminalStatus.SUCCESS
    assert result.changed_files == ("app.py",)
    assert "VALUE = 'fixed'" in result.candidate_diff
    assert result.commands[0].exit_code == 0
    assert result.github_mutations == 0
    assert result.aws_calls == 0
    assert events[-1].kind is WorkerEventKind.TURN_COMPLETED
    assert [event.sequence for event in events] == list(range(1, len(events) + 1))
    worker.close()


def test_unknown_protocol_initialize_contract_fails_explicitly(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    transport = ScriptedTransport(initialize={"userAgent": "unknown"})
    worker = CodexAppServerWorker(transport)
    with pytest.raises(AppServerProtocolError, match="UNSUPPORTED_INITIALIZE_RESULT"):
        worker.start(_task(root))
    assert transport.closed is True


def test_server_approval_and_unknown_tool_requests_are_denied(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    messages = [
        {
            "jsonrpc": "2.0",
            "id": 77,
            "method": "item/commandExecution/requestApproval",
            "params": {"command": "curl example.invalid"},
        },
        {
            "jsonrpc": "2.0",
            "id": 78,
            "method": "item/tool/call",
            "params": {"tool": "github_push"},
        },
        *_success_messages(root),
    ]
    events, result, _ = _run(_task(root), ScriptedTransport(messages))
    assert result.status is WorkerTerminalStatus.SUCCESS
    assert [event.kind for event in events].count(WorkerEventKind.APPROVAL_DENIED) == 2


def test_server_request_responses_are_fail_closed(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    transport = ScriptedTransport(
        [
            {
                "jsonrpc": "2.0",
                "id": 77,
                "method": "item/fileChange/requestApproval",
                "params": {},
            },
            {
                "jsonrpc": "2.0",
                "id": 78,
                "method": "item/permissions/requestApproval",
                "params": {},
            },
            *_success_messages(root),
        ]
    )
    _run(_task(root), transport)
    assert transport.responses == [(77, {"decision": "decline"})]
    assert transport.errors == [
        (78, -32001, "AIOA worker capability profile denies this request")
    ]


def test_sensitive_environment_never_reaches_app_server_process() -> None:
    source = {
        "PATH": "/usr/bin",
        "HOME": "/safe-auth-home",
        "OPENAI_API_KEY": "model-auth-is-trusted-at-app-server-only",
        "AWS_ACCESS_KEY_ID": "forbidden",
        "GITHUB_TOKEN": "forbidden",
        "GH_TOKEN": "forbidden",
        "SSH_AUTH_SOCK": "/forbidden/socket",
        "PROJECT_SECRET": "forbidden",
        "DATABASE_PASSWORD": "forbidden",
    }
    sanitized = sanitized_app_server_environment(source)
    assert sanitized == {
        "PATH": "/usr/bin",
        "HOME": "/safe-auth-home",
        "OPENAI_API_KEY": "model-auth-is-trusted-at-app-server-only",
    }


def test_worker_task_schema_has_no_remote_authority_or_credential_fields(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    task = _task(root)
    fields = set(type(task).model_fields)
    assert fields.isdisjoint(
        {
            "github_token",
            "github_write",
            "aws_credentials",
            "ssh_auth_sock",
            "remote_url",
        }
    )
    with pytest.raises(ValidationError):
        WorkerTask.model_validate({**task.model_dump(), "github_token": "forbidden"})


def test_changed_path_outside_workspace_fails_without_candidate_result(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    messages = _success_messages(root)
    item = messages[2]["params"]
    assert isinstance(item, dict)
    changes = item["item"]
    assert isinstance(changes, dict)
    changes["changes"] = [{"path": "/etc/passwd", "kind": "update", "diff": ""}]
    _, result, _ = _run(_task(root), ScriptedTransport(messages))
    assert result.status is WorkerTerminalStatus.PROTOCOL_FAILURE
    assert result.failure_code == "WORKER_PROTOCOL_FAILURE"
    assert result.candidate_diff == ""
    assert result.changed_files == ()


def test_timeout_is_terminal_and_closes_owned_transport(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    transport = ScriptedTransport()
    _, result, worker = _run(
        _task(root, timeout_seconds=0.01),
        transport,
    )
    assert result.status is WorkerTerminalStatus.TIMEOUT
    assert result.failure_code == "WORKER_TASK_TIMEOUT"
    assert transport.closed is True
    worker.close()


def test_cancel_is_idempotent_and_cannot_become_success(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    task = _task(root)
    transport = ScriptedTransport(_success_messages(root))
    worker = CodexAppServerWorker(transport)
    worker.start(task)
    handle = worker.send_task(task)
    worker.cancel(handle)
    worker.cancel(handle)
    result = worker.receive_result(handle)
    assert result.status is WorkerTerminalStatus.CANCELLED
    assert [method for method, _ in transport.requests].count("turn/interrupt") == 1
    assert transport.close_calls == 1
    worker.close()


def test_app_server_crash_has_no_fake_diff_or_success(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    transport = ScriptedTransport(crash=True)
    _, result, _ = _run(_task(root), transport)
    assert result.status is WorkerTerminalStatus.WORKER_CRASH
    assert result.failure_code == "WORKER_APP_SERVER_CRASH"
    assert result.candidate_diff == ""
    assert result.changed_files == ()


def test_event_limit_is_fail_closed_and_bounded(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    messages = []
    for index in range(12):
        messages.append(
            {
                "jsonrpc": "2.0",
                "method": "item/started",
                "params": {
                    "threadId": THREAD_ID,
                    "turnId": TURN_ID,
                    "item": {"id": f"item-{index}", "type": "reasoning"},
                },
            }
        )
    _, result, _ = _run(_task(root, max_events=8), ScriptedTransport(messages))
    assert result.status is WorkerTerminalStatus.PROTOCOL_FAILURE
    assert result.failure_code == "WORKER_EVENT_LIMIT_EXCEEDED"


def test_sequential_workers_do_not_leak_task_or_event_identity(tmp_path: Path) -> None:
    roots = (_workspace(tmp_path / "one"), _workspace(tmp_path / "two"))
    outputs = []
    for root in roots:
        task = _task(root)
        events, result, worker = _run(task, ScriptedTransport(_success_messages(root)))
        outputs.append((task, events, result))
        worker.close()
    first, second = outputs
    assert first[0].task_id != second[0].task_id
    assert {event.event_id for event in first[1]}.isdisjoint(
        {event.event_id for event in second[1]}
    )
    assert first[2].task_id != second[2].task_id


def test_close_is_repeat_safe(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    transport = ScriptedTransport(_success_messages(root))
    _, _, worker = _run(_task(root), transport)
    worker.close()
    worker.close()
    assert transport.close_calls == 1


def test_workspace_digest_rejects_links_and_hardlinks(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    (root / "linked.py").symlink_to(root / "app.py")
    with pytest.raises(ValueError, match="LINK_FORBIDDEN"):
        digest_workspace_tree(root)
    (root / "linked.py").unlink()
    os.link(root / "app.py", root / "hardlinked.py")
    with pytest.raises(ValueError, match="FILE_TYPE_FORBIDDEN"):
        digest_workspace_tree(root)


def test_subprocess_diagnostics_are_bounded_and_redacted(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    script = (
        "import sys; "
        "sys.stderr.write('token=' + 'fixture-sensitive-value' + 'x' * 5000); "
        "sys.stderr.flush()"
    )
    transport = SubprocessJsonRpcTransport(
        (sys.executable, "-c", script),
        max_diagnostic_bytes=1024,
        shutdown_timeout=0.5,
        source_environment={"PATH": os.environ.get("PATH", "")},
    )
    transport.start(cwd=root, max_events=8)
    with pytest.raises(AppServerCrash):
        transport.next_message(timeout=2)
    transport.close()
    diagnostics = transport.diagnostics()
    assert "fixture-sensitive-value" not in diagnostics
    assert "[REDACTED]" in diagnostics
    assert len(diagnostics.encode("utf-8")) <= 1024


def test_transport_child_environment_is_sanitized_without_starting_process() -> None:
    transport = SubprocessJsonRpcTransport(
        source_environment={
            "PATH": "/usr/bin",
            "GITHUB_TOKEN": "forbidden",
            "AWS_SECRET_ACCESS_KEY": "forbidden",
            "SSH_AUTH_SOCK": "/forbidden",
        }
    )
    assert transport.child_environment == {"PATH": "/usr/bin"}


def test_task_rejects_secret_shaped_instruction(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    task = _task(root)
    with pytest.raises(ValidationError):
        WorkerTask.model_validate(
            {**task.model_dump(), "instruction": "Use token=fixture-sensitive-value now"}
        )


def test_mapping_helper_contract_does_not_accept_protocol_arrays() -> None:
    framer = JsonlFramer(max_message_bytes=1024)
    with pytest.raises(AppServerProtocolError, match="MESSAGE_NOT_OBJECT"):
        framer.feed(b"[1,2,3]\n")


def test_fake_transport_type_surface_remains_read_only() -> None:
    public = {name for name in dir(ScriptedTransport) if not name.startswith("_")}
    assert public == {
        "close",
        "diagnostics",
        "next_message",
        "notify",
        "request",
        "respond",
        "respond_error",
        "start",
    }


def test_no_shell_or_remote_write_field_is_present_in_transport_request(
    tmp_path: Path,
) -> None:
    root = _workspace(tmp_path)
    transport = ScriptedTransport(_success_messages(root))
    _run(_task(root), transport)
    rendered = repr(transport.requests)
    for forbidden in ("github_token", "AWS_ACCESS_KEY_ID", "ssh_auth_sock", "shell=True"):
        assert forbidden not in rendered
    assert isinstance(transport.requests[0][1], Mapping)
