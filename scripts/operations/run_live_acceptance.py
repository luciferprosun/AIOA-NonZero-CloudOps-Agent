#!/usr/bin/env python3
"""Run bounded, public-safe acceptance checks against an AIOA portable service.

The target URL and operator credential deliberately come only from the process
environment.  A credential is never accepted as a command-line argument, so it
cannot be copied into shell history or a process listing.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import ipaddress
import json
import os
import re
import ssl
import stat
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final
from urllib.parse import quote, quote_plus, urlsplit

ROOT: Final = Path(__file__).resolve().parents[2]
DEFAULT_RECEIPT: Final = ROOT / ".local" / "live-acceptance" / "acceptance-receipt.json"
DEFAULT_TIMEOUT_SECONDS: Final = 10
MAX_TIMEOUT_SECONDS: Final = 20
MAX_RESPONSE_BYTES: Final = 64 * 1024
MAX_TOKEN_BYTES: Final = 1_024
TOKEN_MIN_LENGTH: Final = 32
TOKEN_MAX_LENGTH: Final = 256
SOURCE_COMMIT_PATTERN: Final = re.compile(r"^[0-9a-f]{7,64}$")
HOSTNAME_PATTERN: Final = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$")
FORBIDDEN_TOKEN_ARGUMENTS: Final = frozenset(
    {
        "--token",
        "--operator-token",
        "--aioa-operator-token",
    }
)
HEALTH_BODY: Final = {
    "mode": "mock",
    "service": "aioa-local-hitl",
    "status": "ok",
}
SESSION_BODY: Final = {
    "ok": True,
    "result": {
        "authenticated": True,
        "storage": "http_only_session_cookie",
    },
}
NOT_FOUND_BODY: Final = {
    "error": "NOT_FOUND",
    "ok": False,
    "retryable": False,
}
METHOD_NOT_ALLOWED_BODY: Final = {
    "error": "METHOD_NOT_ALLOWED",
    "ok": False,
    "retryable": False,
}
UNAUTHORIZED_BODY: Final = {
    "error": "UNAUTHORIZED",
    "ok": False,
    "retryable": False,
}
SENSITIVE_PATTERNS: Final = (
    re.compile(r"(?i)\b(?:akia|asia)[a-z0-9]{16}\b"),
    re.compile(r"(?i)\bghp_[a-z0-9]{20,}\b"),
    re.compile(r"(?i)\bgithub_pat_[a-z0-9_]{20,}\b"),
    re.compile(r"(?i)\b(?:bearer|basic)\s+[a-z0-9._~+/=-]{8,}"),
    re.compile(
        r"(?i)\b(?:api[_-]?key|authorization|cookie|set-cookie|password|"
        r"secret(?:[_-]?(?:key|token))?|aioa_operator_token|aws_access_key_id|"
        r"aws_secret_access_key|openai_api_key)\s*[:=]"
    ),
)
STACK_TRACE_MARKERS: Final = (
    "traceback (most recent call last)",
    "stack trace",
    "exception:",
    'file "',
    "/home/",
    "/var/lib/",
)


class AcceptanceError(RuntimeError):
    """One stable, public-safe reason for a failed acceptance condition."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class Target:
    """Validated URL origin, deliberately without paths, credentials, or query data."""

    scheme: str
    host: str
    port: int
    origin: str
    is_loopback: bool


@dataclass(frozen=True, slots=True)
class HttpResponse:
    """A bounded response captured without retaining request headers or credentials."""

    status_code: int
    headers: tuple[tuple[str, str], ...]
    body: bytes


def _environment_value(environment: Mapping[str, str], name: str) -> str | None:
    value = environment.get(name)
    return value if isinstance(value, str) else None


def _is_loopback_host(host: str) -> bool:
    if host.rstrip(".").casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def validate_target_url(value: str | None, mode: str) -> Target:
    """Validate a root URL and enforce the local/live transport boundary."""

    if mode not in {"check", "local", "live"}:
        raise AcceptanceError("ACCEPTANCE_MODE_INVALID")
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise AcceptanceError("PUBLIC_URL_MISSING")
    try:
        parsed = urlsplit(value)
        raw_port = parsed.port
    except ValueError as error:
        raise AcceptanceError("PUBLIC_URL_INVALID") from error
    scheme = parsed.scheme.casefold()
    if scheme not in {"http", "https"} or not parsed.netloc:
        raise AcceptanceError("PUBLIC_URL_INVALID")
    if parsed.username is not None or parsed.password is not None:
        raise AcceptanceError("PUBLIC_URL_CREDENTIALS_FORBIDDEN")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise AcceptanceError("PUBLIC_URL_ROOT_REQUIRED")
    host = parsed.hostname
    if host is None:
        raise AcceptanceError("PUBLIC_URL_INVALID")
    host = host.rstrip(".").casefold()
    if not host:
        raise AcceptanceError("PUBLIC_URL_INVALID")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        try:
            host.encode("ascii")
        except UnicodeEncodeError as error:
            raise AcceptanceError("PUBLIC_URL_INVALID") from error
        if HOSTNAME_PATTERN.fullmatch(host) is None:
            raise AcceptanceError("PUBLIC_URL_INVALID") from None
    port = raw_port if raw_port is not None else (443 if scheme == "https" else 80)
    if not 1 <= port <= 65_535:
        raise AcceptanceError("PUBLIC_URL_INVALID")
    loopback = _is_loopback_host(host)
    if mode == "local" and not loopback:
        raise AcceptanceError("LOCAL_MODE_REQUIRES_LOOPBACK_URL")
    if mode == "live":
        if scheme != "https":
            raise AcceptanceError("LIVE_MODE_REQUIRES_HTTPS")
        if loopback or host.startswith("localhost."):
            raise AcceptanceError("LIVE_MODE_LOOPBACK_FORBIDDEN")
    if scheme == "http" and not loopback:
        raise AcceptanceError("NON_LOOPBACK_HTTP_FORBIDDEN")
    rendered_host = f"[{host}]" if ":" in host else host
    default_port = 443 if scheme == "https" else 80
    origin = f"{scheme}://{rendered_host}"
    if port != default_port:
        origin = f"{origin}:{port}"
    return Target(
        scheme=scheme,
        host=host,
        port=port,
        origin=origin,
        is_loopback=loopback,
    )


def _validate_token(token: str) -> str:
    if (
        not isinstance(token, str)
        or token != token.strip()
        or "\n" in token
        or "\r" in token
        or not TOKEN_MIN_LENGTH <= len(token) <= TOKEN_MAX_LENGTH
    ):
        raise AcceptanceError("OPERATOR_TOKEN_INVALID")
    return token


def _read_token_file(path_value: str) -> str:
    if not path_value or path_value != path_value.strip():
        raise AcceptanceError("OPERATOR_TOKEN_FILE_INVALID")
    path = Path(path_value)
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents if parent.exists()):
        raise AcceptanceError("OPERATOR_TOKEN_FILE_SYMLINK_FORBIDDEN")
    descriptor = -1
    try:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise AcceptanceError("OPERATOR_TOKEN_FILE_INVALID")
        if hasattr(os, "getuid") and (
            metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) & 0o077
        ):
            raise AcceptanceError("OPERATOR_TOKEN_FILE_PERMISSIONS_INVALID")
        if metadata.st_size <= 0 or metadata.st_size > MAX_TOKEN_BYTES:
            raise AcceptanceError("OPERATOR_TOKEN_FILE_INVALID")
        chunks: list[bytes] = []
        remaining = MAX_TOKEN_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) > MAX_TOKEN_BYTES:
            raise AcceptanceError("OPERATOR_TOKEN_FILE_INVALID")
        try:
            token = raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise AcceptanceError("OPERATOR_TOKEN_FILE_INVALID") from error
        return _validate_token(token.removesuffix("\n"))
    except AcceptanceError:
        raise
    except OSError as error:
        raise AcceptanceError("OPERATOR_TOKEN_FILE_UNAVAILABLE") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def load_operator_token(
    environment: Mapping[str, str] | None = None,
) -> tuple[str, str]:
    """Load a file credential or inherited environment credential, never CLI input."""

    values = os.environ if environment is None else environment
    file_path = _environment_value(values, "AIOA_OPERATOR_TOKEN_FILE")
    inherited = _environment_value(values, "AIOA_OPERATOR_TOKEN")
    if file_path and inherited:
        raise AcceptanceError("OPERATOR_TOKEN_SOURCE_AMBIGUOUS")
    if file_path:
        return _read_token_file(file_path), "owner_only_file"
    if inherited:
        return _validate_token(inherited), "inherited_environment"
    raise AcceptanceError("OPERATOR_TOKEN_SOURCE_MISSING")


def _timeout_from_environment(environment: Mapping[str, str]) -> int:
    raw = _environment_value(environment, "AIOA_ACCEPTANCE_TIMEOUT_SECONDS")
    if raw is None:
        return DEFAULT_TIMEOUT_SECONDS
    try:
        value = int(raw)
    except ValueError as error:
        raise AcceptanceError("ACCEPTANCE_TIMEOUT_INVALID") from error
    if not 1 <= value <= MAX_TIMEOUT_SECONDS:
        raise AcceptanceError("ACCEPTANCE_TIMEOUT_INVALID")
    return value


def redact_sensitive_text(value: str, token: str | None = None) -> str:
    """Return text suitable for a receipt or fixed error path without raw credentials."""

    redacted = value
    if token:
        for candidate in sorted(
            {token, quote(token, safe=""), quote_plus(token, safe="")},
            key=len,
            reverse=True,
        ):
            redacted = redacted.replace(candidate, "[REDACTED]")
    for pattern in SENSITIVE_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def _response_text(response: HttpResponse) -> str:
    try:
        return response.body.decode("utf-8")
    except UnicodeDecodeError as error:
        raise AcceptanceError("PUBLIC_RESPONSE_ENCODING_INVALID") from error


def _ensure_public_safe(
    response: HttpResponse,
    token: str,
    *,
    allow_session_cookie: bool = False,
) -> str:
    """Reject reflected credentials, generic credential markers, and traceback leakage."""

    body_text = _response_text(response)
    values = [body_text]
    for name, header_value in response.headers:
        if name == "set-cookie" and allow_session_cookie:
            if token in header_value or quote(token, safe="") in header_value:
                raise AcceptanceError("PUBLIC_RESPONSE_SENSITIVE_MATERIAL")
            continue
        values.append(f"{name}: {header_value}")
    for value in values:
        if "[REDACTED]" in redact_sensitive_text(value, token):
            raise AcceptanceError("PUBLIC_RESPONSE_SENSITIVE_MATERIAL")
    lowered = body_text.casefold()
    if any(marker in lowered for marker in STACK_TRACE_MARKERS):
        raise AcceptanceError("PUBLIC_RESPONSE_STACKTRACE_FORBIDDEN")
    return body_text


def _strict_json(text: str, reason: str) -> object:
    def reject_duplicates(values: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for name, value in values:
            if name in result:
                raise ValueError("duplicate JSON key")
            result[name] = value
        return result

    try:
        return json.loads(
            text,
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("non-finite")),
        )
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise AcceptanceError(reason) from error


def _header_values(response: HttpResponse, name: str) -> tuple[str, ...]:
    expected = name.casefold()
    return tuple(value for key, value in response.headers if key.casefold() == expected)


def _validate_ready_body(value: object) -> None:
    if not isinstance(value, dict) or set(value) != {
        "status",
        "process_status",
        "provider_status",
        "sandbox_status",
        "runtime",
    }:
        raise AcceptanceError("READY_BODY_INVALID")
    if any(
        value.get(name) != expected
        for name, expected in (
            ("status", "ready"),
            ("process_status", "READY"),
            ("provider_status", "READY"),
            ("sandbox_status", "READY"),
        )
    ):
        raise AcceptanceError("READY_BODY_INVALID")
    runtime = value.get("runtime")
    expected_runtime_keys = {
        "runtime_mode",
        "experience_mode",
        "model_mode",
        "provider",
        "model_id",
        "agent_framework",
        "aws_calls_allowed",
        "real_cloud_mutations_enabled",
        "external_network_allowed",
        "process_provider_calls",
        "process_external_network_calls",
        "process_sandbox_mutations",
    }
    if not isinstance(runtime, dict) or set(runtime) != expected_runtime_keys:
        raise AcceptanceError("READY_BODY_INVALID")
    if any(
        runtime.get(name) != expected
        for name, expected in (
            ("runtime_mode", "portable"),
            ("experience_mode", "DEMO_SANDBOX"),
            ("model_mode", "DETERMINISTIC_MODEL"),
            ("provider", "mock"),
            ("agent_framework", "strands-agents"),
            ("aws_calls_allowed", False),
            ("real_cloud_mutations_enabled", False),
            ("external_network_allowed", False),
        )
    ):
        raise AcceptanceError("READY_BODY_INVALID")
    model_id = runtime.get("model_id")
    counters = (
        runtime.get("process_provider_calls"),
        runtime.get("process_external_network_calls"),
        runtime.get("process_sandbox_mutations"),
    )
    if (
        not isinstance(model_id, str)
        or not model_id
        or len(model_id) > 256
        or any(isinstance(counter, bool) or not isinstance(counter, int) or counter < 0 for counter in counters)
    ):
        raise AcceptanceError("READY_BODY_INVALID")


def _new_connection(target: Target, timeout_seconds: int) -> http.client.HTTPConnection:
    if target.scheme == "https":
        context = ssl.create_default_context()
        if context.verify_mode != ssl.CERT_REQUIRED or not context.check_hostname:
            raise AcceptanceError("TLS_VERIFICATION_REQUIRED")
        return http.client.HTTPSConnection(
            target.host,
            target.port,
            timeout=timeout_seconds,
            context=context,
        )
    return http.client.HTTPConnection(target.host, target.port, timeout=timeout_seconds)


def _request(
    target: Target,
    method: str,
    path: str,
    *,
    timeout_seconds: int,
    headers: Mapping[str, str] | None = None,
    body: bytes | None = None,
) -> HttpResponse:
    """Issue one direct bounded request without redirects or debug output."""

    if not path.startswith("/") or "?" in path or "#" in path:
        raise AcceptanceError("ACCEPTANCE_PATH_INVALID")
    request_headers = {
        "Accept": "application/json",
        "Connection": "close",
        "User-Agent": "aioa-live-acceptance/1",
        **(dict(headers) if headers is not None else {}),
    }
    connection: http.client.HTTPConnection | None = None
    try:
        connection = _new_connection(target, timeout_seconds)
        connection.request(method, path, body=body, headers=request_headers)
        raw_response = connection.getresponse()
        response_headers = tuple(
            (name.casefold(), value)
            for name, value in raw_response.getheaders()
            if isinstance(name, str) and isinstance(value, str)
        )
        content_lengths = _header_values(
            HttpResponse(raw_response.status, response_headers, b""), "content-length"
        )
        if len(content_lengths) > 1:
            raise AcceptanceError("HTTP_RESPONSE_INVALID")
        if content_lengths:
            try:
                content_length = int(content_lengths[0])
            except ValueError as error:
                raise AcceptanceError("HTTP_RESPONSE_INVALID") from error
            if content_length < 0 or content_length > MAX_RESPONSE_BYTES:
                raise AcceptanceError("HTTP_RESPONSE_TOO_LARGE")
        payload = raw_response.read(MAX_RESPONSE_BYTES + 1)
        if len(payload) > MAX_RESPONSE_BYTES:
            raise AcceptanceError("HTTP_RESPONSE_TOO_LARGE")
        return HttpResponse(raw_response.status, response_headers, payload)
    except AcceptanceError:
        raise
    except TimeoutError as error:
        raise AcceptanceError("HTTP_TIMEOUT") from error
    except ssl.SSLError as error:
        raise AcceptanceError("TLS_VALIDATION_FAILED") from error
    except (http.client.HTTPException, OSError) as error:
        raise AcceptanceError("HTTP_REQUEST_FAILED") from error
    finally:
        if connection is not None:
            connection.close()


def _check_result(
    identifier: str,
    method: str,
    path: str,
    response: HttpResponse,
) -> dict[str, object]:
    return {
        "content_sha256": hashlib.sha256(response.body).hexdigest(),
        "id": identifier,
        "method": method,
        "path": path,
        "status_code": response.status_code,
    }


def _expect_exact(
    response: HttpResponse,
    *,
    expected_status: int,
    expected_body: Mapping[str, object],
    invalid_status_reason: str,
    invalid_body_reason: str,
    token: str,
    allow_session_cookie: bool = False,
) -> None:
    text = _ensure_public_safe(
        response,
        token,
        allow_session_cookie=allow_session_cookie,
    )
    if response.status_code != expected_status:
        raise AcceptanceError(invalid_status_reason)
    if _strict_json(text, invalid_body_reason) != expected_body:
        raise AcceptanceError(invalid_body_reason)


def _check_health(target: Target, timeout_seconds: int, token: str) -> dict[str, object]:
    response = _request(target, "GET", "/health", timeout_seconds=timeout_seconds)
    _expect_exact(
        response,
        expected_status=200,
        expected_body=HEALTH_BODY,
        invalid_status_reason="HEALTH_STATUS_INVALID",
        invalid_body_reason="HEALTH_BODY_INVALID",
        token=token,
    )
    return _check_result("health", "GET", "/health", response)


def _check_ready(target: Target, timeout_seconds: int, token: str) -> dict[str, object]:
    response = _request(target, "GET", "/ready", timeout_seconds=timeout_seconds)
    text = _ensure_public_safe(response, token)
    if response.status_code != 200:
        raise AcceptanceError("READY_STATUS_INVALID")
    _validate_ready_body(_strict_json(text, "READY_BODY_INVALID"))
    return _check_result("ready", "GET", "/ready", response)


def _check_unknown_path(target: Target, timeout_seconds: int, token: str) -> dict[str, object]:
    path = "/_aioa_live_acceptance_unknown"
    response = _request(target, "GET", path, timeout_seconds=timeout_seconds)
    _expect_exact(
        response,
        expected_status=404,
        expected_body=NOT_FOUND_BODY,
        invalid_status_reason="UNKNOWN_PATH_STATUS_INVALID",
        invalid_body_reason="UNKNOWN_PATH_BODY_INVALID",
        token=token,
    )
    return _check_result("unknown_path", "GET", path, response)


def _check_unsupported_method(target: Target, timeout_seconds: int, token: str) -> dict[str, object]:
    response = _request(target, "POST", "/health", timeout_seconds=timeout_seconds)
    _expect_exact(
        response,
        expected_status=405,
        expected_body=METHOD_NOT_ALLOWED_BODY,
        invalid_status_reason="UNSUPPORTED_METHOD_STATUS_INVALID",
        invalid_body_reason="UNSUPPORTED_METHOD_BODY_INVALID",
        token=token,
    )
    return _check_result("unsupported_method", "POST", "/health", response)


def _session_cookie(response: HttpResponse) -> str:
    cookies = _header_values(response, "set-cookie")
    if len(cookies) != 1:
        raise AcceptanceError("SESSION_COOKIE_INVALID")
    cookie = cookies[0]
    pair, separator, attributes = cookie.partition(";")
    if not separator or not pair.startswith("aioa_operator_session="):
        raise AcceptanceError("SESSION_COOKIE_INVALID")
    value = pair.removeprefix("aioa_operator_session=")
    if not value or value != value.strip():
        raise AcceptanceError("SESSION_COOKIE_INVALID")
    normalized_attributes = {item.strip().casefold() for item in attributes.split(";")}
    if not {"httponly", "samesite=strict", "path=/"}.issubset(normalized_attributes):
        raise AcceptanceError("SESSION_COOKIE_INVALID")
    return pair


def _check_session_bootstrap(
    target: Target,
    timeout_seconds: int,
    token: str,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    unauthenticated = _request(target, "GET", "/api/session", timeout_seconds=timeout_seconds)
    _expect_exact(
        unauthenticated,
        expected_status=401,
        expected_body=UNAUTHORIZED_BODY,
        invalid_status_reason="SESSION_UNAUTHENTICATED_STATUS_INVALID",
        invalid_body_reason="SESSION_UNAUTHENTICATED_BODY_INVALID",
        token=token,
    )
    bootstrap = _request(
        target,
        "POST",
        "/api/session",
        timeout_seconds=timeout_seconds,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        body=b"{}",
    )
    _expect_exact(
        bootstrap,
        expected_status=200,
        expected_body=SESSION_BODY,
        invalid_status_reason="SESSION_BOOTSTRAP_STATUS_INVALID",
        invalid_body_reason="SESSION_BOOTSTRAP_BODY_INVALID",
        token=token,
        allow_session_cookie=True,
    )
    cookie = _session_cookie(bootstrap)
    session = _request(
        target,
        "GET",
        "/api/session",
        timeout_seconds=timeout_seconds,
        headers={"Cookie": cookie},
    )
    _expect_exact(
        session,
        expected_status=200,
        expected_body=SESSION_BODY,
        invalid_status_reason="SESSION_COOKIE_STATUS_INVALID",
        invalid_body_reason="SESSION_COOKIE_BODY_INVALID",
        token=token,
    )
    return (
        _check_result("session_unauthenticated", "GET", "/api/session", unauthenticated),
        _check_result("session_bootstrap", "POST", "/api/session", bootstrap),
        _check_result("session_cookie", "GET", "/api/session", session),
    )


def _source_commit(environment: Mapping[str, str]) -> str:
    for name in ("AIOA_ACCEPTANCE_SOURCE_COMMIT", "SOURCE_COMMIT"):
        candidate = _environment_value(environment, name)
        if candidate is None:
            continue
        if SOURCE_COMMIT_PATTERN.fullmatch(candidate) is None:
            raise AcceptanceError("ACCEPTANCE_SOURCE_COMMIT_INVALID")
        return candidate
    try:
        result = subprocess.run(
            ("git", "-C", str(ROOT), "rev-parse", "HEAD"),
            capture_output=True,
            check=False,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    candidate = result.stdout.strip()
    return candidate if result.returncode == 0 and SOURCE_COMMIT_PATTERN.fullmatch(candidate) else "unknown"


def _timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _ensure_receipt_redacted(receipt: Mapping[str, object], token: str) -> None:
    rendered = json.dumps(receipt, allow_nan=False, separators=(",", ":"), sort_keys=True)
    if "[REDACTED]" in redact_sensitive_text(rendered, token):
        raise AcceptanceError("ACCEPTANCE_RECEIPT_REDACTION_FAILED")


def run_acceptance(
    *,
    mode: str = "check",
    environment: Mapping[str, str] | None = None,
    timeout_seconds: int | None = None,
) -> dict[str, object]:
    """Run the full read-only acceptance suite and return a public-safe receipt."""

    values = os.environ if environment is None else environment
    target = validate_target_url(_environment_value(values, "AIOA_PUBLIC_URL"), mode)
    token, credential_source = load_operator_token(values)
    timeout = _timeout_from_environment(values) if timeout_seconds is None else timeout_seconds
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= MAX_TIMEOUT_SECONDS:
        raise AcceptanceError("ACCEPTANCE_TIMEOUT_INVALID")
    started_at = _timestamp()
    started_monotonic = time.monotonic()
    checks = [
        _check_health(target, timeout, token),
        _check_ready(target, timeout, token),
        _check_unknown_path(target, timeout, token),
        _check_unsupported_method(target, timeout, token),
        *_check_session_bootstrap(target, timeout, token),
    ]
    completed_at = _timestamp()
    receipt: dict[str, object] = {
        "checks": checks,
        "completed_at": completed_at,
        "credential_source": credential_source,
        "duration_ms": round((time.monotonic() - started_monotonic) * 1_000),
        "mode": mode,
        "schema_version": 1,
        "secure_cookie_status": (
            "NOT_APPLICABLE_LOCAL_HTTP"
            if target.is_loopback and target.scheme == "http"
            else "NOT_MEASURED_UNIT1"
        ),
        "source_commit": _source_commit(values),
        "started_at": started_at,
        "status": "PASS",
        "timeout_seconds": timeout,
        "tls_verification": target.scheme == "https",
        "url_origin": target.origin,
    }
    _ensure_receipt_redacted(receipt, token)
    return receipt


def write_receipt(path: Path, receipt: Mapping[str, object]) -> None:
    """Atomically write a public-safe receipt without following a receipt symlink."""

    if not isinstance(path, Path) or not str(path).strip():
        raise AcceptanceError("ACCEPTANCE_RECEIPT_PATH_INVALID")
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents if parent.exists()):
        raise AcceptanceError("ACCEPTANCE_RECEIPT_SYMLINK_FORBIDDEN")
    try:
        rendered = json.dumps(receipt, allow_nan=False, indent=2, sort_keys=True) + "\n"
    except (TypeError, ValueError) as error:
        raise AcceptanceError("ACCEPTANCE_RECEIPT_INVALID") from error
    if "[REDACTED]" in redact_sensitive_text(rendered):
        raise AcceptanceError("ACCEPTANCE_RECEIPT_REDACTION_FAILED")
    descriptor = -1
    temporary_path: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=".aioa-live-acceptance-",
            suffix=".json",
        )
        temporary_path = Path(temporary_name)
        os.fchmod(descriptor, 0o600)
        payload = rendered.encode("utf-8")
        written = 0
        while written < len(payload):
            written += os.write(descriptor, payload[written:])
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary_path, path)
    except OSError as error:
        raise AcceptanceError("ACCEPTANCE_RECEIPT_UNAVAILABLE") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _reject_token_cli_argument(argv: Sequence[str]) -> None:
    for value in argv:
        lowered = value.casefold()
        if lowered in FORBIDDEN_TOKEN_ARGUMENTS or any(
            lowered.startswith(f"{argument}=") for argument in FORBIDDEN_TOKEN_ARGUMENTS
        ):
            raise AcceptanceError("OPERATOR_TOKEN_CLI_ARGUMENT_FORBIDDEN")


def _arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    values = tuple(sys.argv[1:] if argv is None else argv)
    _reject_token_cli_argument(values)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("check", "local", "live"), default="check")
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    return parser.parse_args(values)


def _failure_payload(reason: str) -> str:
    return json.dumps({"reason": reason, "status": "FAIL"}, sort_keys=True)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI with redacted fixed errors and no token-bearing diagnostics."""

    try:
        arguments = _arguments(argv)
        receipt = run_acceptance(mode=arguments.mode)
        write_receipt(arguments.receipt, receipt)
        print(json.dumps(receipt, allow_nan=False, indent=2, sort_keys=True))
        return 0
    except AcceptanceError as error:
        print(_failure_payload(error.reason), file=sys.stderr)
        return 1
    except Exception:
        print(_failure_payload("ACCEPTANCE_INTERNAL_ERROR"), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
