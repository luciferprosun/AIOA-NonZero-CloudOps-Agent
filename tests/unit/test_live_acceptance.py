from __future__ import annotations

import json
import ssl
import stat
import time
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest
from scripts.operations import run_live_acceptance as acceptance

from aioa_cloudops_agent.agent import create_local_hitl_runtime
from aioa_cloudops_agent.config import LocalHitlSettings
from aioa_cloudops_agent.local_api import (
    LocalApiApplication,
    LocalApiTokenAuthorizer,
    create_local_http_server,
)

TOKEN = "live-acceptance-" + "s" * 48
SOURCE_COMMIT = "a" * 40


@contextmanager
def _canonical_server(tmp_path: Path) -> Iterator[str]:
    runtime = create_local_hitl_runtime(
        LocalHitlSettings(
            state_path=tmp_path / "truth.json",
            inventory_path=tmp_path / "inventory.json",
        )
    )
    application = LocalApiApplication(runtime, LocalApiTokenAuthorizer(TOKEN))
    server = create_local_http_server(application, port=0)
    thread = Thread(
        target=server.serve_forever,
        kwargs={"poll_interval": 0.01},
        daemon=True,
    )
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


@contextmanager
def _reflecting_server(token: str) -> Iterator[str]:
    class ReflectingHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            body = json.dumps(acceptance.HEALTH_BODY).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("X-AIOA-Debug", token)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format: str, *args: object) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), ReflectingHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


def _token_file(tmp_path: Path, value: str = TOKEN) -> Path:
    path = tmp_path / "private" / "operator.token"
    path.parent.mkdir(exist_ok=True)
    path.write_text(f"{value}\n", encoding="utf-8")
    path.chmod(0o600)
    return path


def _environment(url: str, token_file: Path) -> dict[str, str]:
    return {
        "AIOA_ACCEPTANCE_SOURCE_COMMIT": SOURCE_COMMIT,
        "AIOA_ACCEPTANCE_TIMEOUT_SECONDS": "2",
        "AIOA_OPERATOR_TOKEN_FILE": str(token_file),
        "AIOA_PUBLIC_URL": url,
    }


def test_acceptance_runs_against_canonical_loopback_server_and_writes_redacted_receipt(
    tmp_path: Path,
) -> None:
    token_file = _token_file(tmp_path)
    with _canonical_server(tmp_path) as url:
        receipt = acceptance.run_acceptance(
            mode="local",
            environment=_environment(url, token_file),
        )

    assert receipt["status"] == "PASS"
    assert receipt["url_origin"] == url
    assert receipt["source_commit"] == SOURCE_COMMIT
    assert receipt["credential_source"] == "owner_only_file"
    assert receipt["tls_verification"] is False
    assert receipt["secure_cookie_status"] == "NOT_APPLICABLE_LOCAL_HTTP"
    assert [check["id"] for check in receipt["checks"]] == [
        "health",
        "ready",
        "unknown_path",
        "unsupported_method",
        "session_unauthenticated",
        "session_bootstrap",
        "session_cookie",
    ]
    assert [check["status_code"] for check in receipt["checks"]] == [
        200,
        200,
        404,
        405,
        401,
        200,
        200,
    ]
    rendered = json.dumps(receipt, sort_keys=True)
    assert TOKEN not in rendered
    assert "aioa_operator_session" not in rendered
    assert "authorization" not in rendered.casefold()

    output = tmp_path / "receipt" / "acceptance.json"
    acceptance.write_receipt(output, receipt)

    assert json.loads(output.read_text(encoding="utf-8")) == receipt
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert TOKEN not in output.read_text(encoding="utf-8")


def test_cli_uses_environment_credential_without_printing_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    token_file = _token_file(tmp_path)
    output = tmp_path / "cli-receipt.json"
    with _canonical_server(tmp_path) as url:
        environment = _environment(url, token_file)
        for name, value in environment.items():
            monkeypatch.setenv(name, value)
        monkeypatch.delenv("AIOA_OPERATOR_TOKEN", raising=False)

        code = acceptance.main(["--mode", "local", "--receipt", str(output)])

    captured = capsys.readouterr()
    assert code == 0
    assert captured.err == ""
    assert TOKEN not in captured.out + captured.err
    assert json.loads(captured.out)["status"] == "PASS"
    assert TOKEN not in output.read_text(encoding="utf-8")


def test_file_credential_requires_regular_owner_only_file(tmp_path: Path) -> None:
    token_file = _token_file(tmp_path)
    token_file.chmod(0o644)

    with pytest.raises(
        acceptance.AcceptanceError,
        match="OPERATOR_TOKEN_FILE_PERMISSIONS_INVALID",
    ):
        acceptance.load_operator_token({"AIOA_OPERATOR_TOKEN_FILE": str(token_file)})

    target = _token_file(tmp_path, "t" * 48)
    linked = tmp_path / "linked.token"
    linked.symlink_to(target)
    with pytest.raises(
        acceptance.AcceptanceError,
        match="OPERATOR_TOKEN_FILE_SYMLINK_FORBIDDEN",
    ):
        acceptance.load_operator_token({"AIOA_OPERATOR_TOKEN_FILE": str(linked)})


def test_credential_sources_are_explicit_and_redacted() -> None:
    token, source = acceptance.load_operator_token({"AIOA_OPERATOR_TOKEN": TOKEN})

    assert token == TOKEN
    assert source == "inherited_environment"
    assert TOKEN not in acceptance.redact_sensitive_text(f"Bearer {TOKEN}", TOKEN)
    with pytest.raises(acceptance.AcceptanceError, match="OPERATOR_TOKEN_SOURCE_AMBIGUOUS"):
        acceptance.load_operator_token(
            {
                "AIOA_OPERATOR_TOKEN": TOKEN,
                "AIOA_OPERATOR_TOKEN_FILE": "/private/operator.token",
            }
        )


@pytest.mark.parametrize(
    ("url", "mode", "reason"),
    (
        ("http://example.test", "check", "NON_LOOPBACK_HTTP_FORBIDDEN"),
        ("https://localhost", "live", "LIVE_MODE_LOOPBACK_FORBIDDEN"),
        ("http://127.0.0.1:10000", "live", "LIVE_MODE_REQUIRES_HTTPS"),
        ("http://127.0.0.1:0", "local", "PUBLIC_URL_INVALID"),
        ("https://example.test/not-root", "check", "PUBLIC_URL_ROOT_REQUIRED"),
        ("https://operator@example.test", "check", "PUBLIC_URL_CREDENTIALS_FORBIDDEN"),
    ),
)
def test_target_url_policy_rejects_unsafe_or_ambiguous_targets(
    url: str,
    mode: str,
    reason: str,
) -> None:
    with pytest.raises(acceptance.AcceptanceError, match=reason):
        acceptance.validate_target_url(url, mode)


def test_target_url_policy_supports_local_and_verified_live_https() -> None:
    local = acceptance.validate_target_url("http://127.0.0.1:10000/", "local")
    live = acceptance.validate_target_url("https://demo.example.test:9443", "live")

    assert local.origin == "http://127.0.0.1:10000"
    assert local.is_loopback is True
    assert live.origin == "https://demo.example.test:9443"
    assert live.is_loopback is False


def test_timeout_is_bounded_and_explicit() -> None:
    assert acceptance._timeout_from_environment({}) == acceptance.DEFAULT_TIMEOUT_SECONDS
    assert acceptance._timeout_from_environment({"AIOA_ACCEPTANCE_TIMEOUT_SECONDS": "1"}) == 1
    for invalid in ("0", str(acceptance.MAX_TIMEOUT_SECONDS + 1), "not-an-integer"):
        with pytest.raises(acceptance.AcceptanceError, match="ACCEPTANCE_TIMEOUT_INVALID"):
            acceptance._timeout_from_environment({"AIOA_ACCEPTANCE_TIMEOUT_SECONDS": invalid})


def test_response_body_and_connection_waits_are_bounded() -> None:
    class LimitedHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/large":
                self.send_response(200)
                self.send_header("Content-Length", str(acceptance.MAX_RESPONSE_BYTES + 1))
                self.end_headers()
                return
            if self.path == "/chunked":
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"x" * (acceptance.MAX_RESPONSE_BYTES + 1))
                return
            time.sleep(1.2)
            try:
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")
            except BrokenPipeError:
                return

        def log_message(self, _format: str, *args: object) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), LimitedHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    target = acceptance.validate_target_url(
        f"http://127.0.0.1:{server.server_port}",
        "local",
    )
    try:
        with pytest.raises(acceptance.AcceptanceError, match="HTTP_RESPONSE_TOO_LARGE"):
            acceptance._request(target, "GET", "/large", timeout_seconds=1)
        with pytest.raises(acceptance.AcceptanceError, match="HTTP_RESPONSE_TOO_LARGE"):
            acceptance._request(target, "GET", "/chunked", timeout_seconds=1)
        with pytest.raises(acceptance.AcceptanceError, match="HTTP_TIMEOUT"):
            acceptance._request(target, "GET", "/slow", timeout_seconds=1)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    assert not thread.is_alive()


def test_token_cli_argument_is_refused_without_echoing_secret(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = acceptance.main(["--token", TOKEN])

    captured = capsys.readouterr()
    assert code == 1
    assert "OPERATOR_TOKEN_CLI_ARGUMENT_FORBIDDEN" in captured.err
    assert TOKEN not in captured.out + captured.err


def test_reflected_token_is_rejected_and_never_written_or_printed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "must-not-exist.json"
    with _reflecting_server(TOKEN) as url:
        monkeypatch.setenv("AIOA_PUBLIC_URL", url)
        monkeypatch.setenv("AIOA_OPERATOR_TOKEN", TOKEN)
        monkeypatch.setenv("AIOA_ACCEPTANCE_SOURCE_COMMIT", SOURCE_COMMIT)
        monkeypatch.delenv("AIOA_OPERATOR_TOKEN_FILE", raising=False)

        code = acceptance.main(["--mode", "local", "--receipt", str(output)])

    captured = capsys.readouterr()
    assert code == 1
    assert "PUBLIC_RESPONSE_SENSITIVE_MATERIAL" in captured.err
    assert TOKEN not in captured.out + captured.err
    assert not output.exists()


def test_https_connection_uses_the_default_verifying_tls_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        status = 200

        @staticmethod
        def getheaders() -> list[tuple[str, str]]:
            return [("Content-Length", "2")]

        @staticmethod
        def read(_limit: int) -> bytes:
            return b"{}"

    class FakeConnection:
        def __init__(self, *args: object, **kwargs: object) -> None:
            captured["context"] = kwargs["context"]

        @staticmethod
        def request(*_args: object, **_kwargs: object) -> None:
            return None

        @staticmethod
        def getresponse() -> FakeResponse:
            return FakeResponse()

        @staticmethod
        def close() -> None:
            return None

    monkeypatch.setattr(acceptance.http.client, "HTTPSConnection", FakeConnection)
    target = acceptance.validate_target_url("https://demo.example.test", "live")
    response = acceptance._request(target, "GET", "/health", timeout_seconds=1)

    context = captured["context"]
    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
    assert response.status_code == 200
