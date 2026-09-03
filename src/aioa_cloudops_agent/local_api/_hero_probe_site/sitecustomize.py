"""Deny and record every non-loopback socket attempt in the fixed hero probe."""

from __future__ import annotations

import ipaddress
import os
import socket
from typing import Final

_AUDIT_PATH_ENV: Final = "AIOA_W5_HERO_EGRESS_AUDIT_PATH"
_ORIGINAL_CONNECT: Final = socket.socket.connect
_ORIGINAL_CONNECT_EX: Final = socket.socket.connect_ex
_ORIGINAL_CREATE_CONNECTION: Final = socket.create_connection
_ORIGINAL_SENDTO: Final = socket.socket.sendto


def _is_loopback(address: object) -> bool:
    if isinstance(address, str):
        return True
    if not isinstance(address, tuple) or not address or not isinstance(address[0], str):
        return False
    host = address[0]
    if host.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.split("%", 1)[0]).is_loopback
    except ValueError:
        return False


def _deny_external(address: object) -> None:
    if _is_loopback(address):
        return
    audit_path = os.environ.get(_AUDIT_PATH_ENV)
    if audit_path:
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(audit_path, flags, 0o600)
        try:
            os.write(descriptor, b"EXTERNAL_EGRESS_ATTEMPT\n")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    raise RuntimeError("W5_HERO_EXTERNAL_EGRESS_DENIED")


def _guarded_connect(instance: socket.socket, address: object) -> None:
    _deny_external(address)
    _ORIGINAL_CONNECT(instance, address)  # type: ignore[arg-type]


def _guarded_connect_ex(instance: socket.socket, address: object) -> int:
    _deny_external(address)
    return _ORIGINAL_CONNECT_EX(instance, address)  # type: ignore[arg-type]


def _guarded_create_connection(
    address: object,
    timeout: object = socket._GLOBAL_DEFAULT_TIMEOUT,
    source_address: object = None,
    *,
    all_errors: bool = False,
) -> socket.socket:
    _deny_external(address)
    return _ORIGINAL_CREATE_CONNECTION(
        address,  # type: ignore[arg-type]
        timeout,  # type: ignore[arg-type]
        source_address,  # type: ignore[arg-type]
        all_errors=all_errors,
    )


def _guarded_sendto(instance: socket.socket, data: bytes, *args: object) -> int:
    if not args:
        raise RuntimeError("W5_HERO_EXTERNAL_EGRESS_DENIED")
    _deny_external(args[-1])
    return _ORIGINAL_SENDTO(instance, data, *args)  # type: ignore[arg-type]


socket.socket.connect = _guarded_connect
socket.socket.connect_ex = _guarded_connect_ex
socket.create_connection = _guarded_create_connection
socket.socket.sendto = _guarded_sendto
